"""
manager.py — Agent Memory 管理器
=============================================
统一管理四层存储：
  · ShortTermMemory  — FIFO 对话窗口（短期）
  · StaticMemory     — MongoDB 固定属性（长期·静态）
  · LongTermMemory   — ChromaDB 动态事实（长期·动态）
  · KnowledgeStore   — 只读知识库（RAG）

后台整理线程（MemoryConsolidator）负责：
  FIFO 弹出 / auto_extract 提交 → LLM 提取 → 去重比对 → ADD/UPDATE/CONFLICT
前端路径（build_messages）只做只读检索，不等待整理完成。
"""

import threading

from src.memory.short_term import ShortTermMemory
from src.memory.long_term import LongTermMemory
from src.memory.static_memory import StaticMemory
from src.memory.consolidator import MemoryConsolidator, ConflictItem
from src.knowledge.store import KnowledgeStore


class AgentMemory:
    """Agent 记忆管理器：统一管理短期、静态长期、动态长期记忆与只读知识库。"""

    def __init__(self, short_term_limit: int = 10):
        self.short_term_memory = ShortTermMemory(limit=short_term_limit)
        self.long_term_memory  = LongTermMemory()   # 动态记忆（ChromaDB）
        self.static_memory     = StaticMemory()      # 静态记忆（MongoDB / JSON fallback）
        self.knowledge_store   = KnowledgeStore()    # 只读知识库

        # 待确认冲突队列（线程安全）
        self._pending_conflicts: list[ConflictItem] = []
        self._conflict_lock = threading.Lock()

        # 后台整理线程（持有 self 引用，通过 add_conflict 回写冲突）
        self._consolidator = MemoryConsolidator(manager=self)

    # ── 让 app.py 的 st.json(memory.short_term) 仍能直接访问列表 ──
    @property
    def short_term(self) -> list[dict]:
        return self.short_term_memory.history

    # ================================================================
    # 写入（Write）
    # ================================================================

    def add_message(self, role: str, content: str) -> None:
        """
        追加一条对话消息到短期记忆。
        若 FIFO 发生弹出，自动提交被弹出的消息到后台整理器。
        关闭 auto_extract 时，这是唯一触发后台整理的时机。
        """
        evicted = self.short_term_memory.add_memory(role, content)
        if evicted is not None:
            self._consolidator.submit([evicted])

    def save_fact(self, fact: str) -> None:
        """手动向动态长期记忆写入一条事实（不经过去重流程）。"""
        self.long_term_memory.add_memory(fact)

    # ================================================================
    # 后台整理（async）
    # ================================================================

    def submit_for_consolidation(self) -> None:
        """
        将当前短期记忆快照提交给后台整理器（立即返回）。
        auto_extract=ON 时在每轮 assistant 回复后调用。
        """
        history = list(self.short_term_memory.history)
        if history:
            self._consolidator.submit(history)

    # ================================================================
    # 冲突管理（Conflict Management）
    # ================================================================

    def add_conflict(self, conflict: ConflictItem) -> None:
        """由后台整理器调用，将冲突加入待确认队列。（线程安全）"""
        with self._conflict_lock:
            self._pending_conflicts.append(conflict)

    def peek_conflicts(self) -> list[ConflictItem]:
        """返回当前所有待确认冲突的副本（不消耗队列）。"""
        with self._conflict_lock:
            return list(self._pending_conflicts)

    def resolve_conflict(self, conflict: ConflictItem, accepted: bool) -> None:
        """
        用户确认或拒绝一条冲突。
        accepted=True  → 执行记忆更新（新内容覆盖旧内容）
        accepted=False → 丢弃新内容，保留原记忆
        """
        with self._conflict_lock:
            if conflict in self._pending_conflicts:
                self._pending_conflicts.remove(conflict)

        if accepted:
            if conflict.memory_type == "static":
                self.static_memory.update(conflict.old_id, conflict.new_content)
            else:
                self.long_term_memory.delete_by_id(conflict.old_id)
                self.long_term_memory.add_memory(
                    conflict.new_content,
                    metadata={"source": "conflict_resolved"},
                )

    # ================================================================
    # 检索（Retrieve）
    # ================================================================

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """从动态长期记忆中语义检索最相关的 top_k 条事实。"""
        return self.long_term_memory.retrieve(query, top_k)

    def retrieve_knowledge(self, query: str, top_k: int | None = None) -> list[dict]:
        """从只读知识库中语义检索最相关的知识片段。"""
        return self.knowledge_store.retrieve(query, top_k)

    # ================================================================
    # 合成（Synthesize）
    # ================================================================

    def build_messages(self, query: str, system_prompt: str = "") -> list[dict]:
        """
        组装发给 LLM 的 messages 列表（快速路径，只做只读检索）：
          [system（静态记忆 + 相关动态记忆 + 知识库参考）]
          + [短期对话历史]
          + [当前用户提问]
        """
        messages: list[dict] = []

        static_facts       = self.static_memory.get_all_text()
        relevant_dynamic   = self.retrieve(query)
        relevant_knowledge = self.retrieve_knowledge(query)

        context_sections: list[str] = []
        if static_facts:
            static_text = "\n".join(f"- {f}" for f in static_facts)
            context_sections.append(f"[用户固定信息（静态记忆）]\n{static_text}")
        if relevant_dynamic:
            dynamic_text = "\n".join(f"- {m['fact']}" for m in relevant_dynamic)
            context_sections.append(f"[相关动态记忆]\n{dynamic_text}")
        if relevant_knowledge:
            knowledge_text = "\n".join(
                f"- {k['text']}" + (f"（来源：{k['source']}）" if k["source"] else "")
                for k in relevant_knowledge
            )
            context_sections.append(f"[知识库参考]\n{knowledge_text}")

        if context_sections:
            sys_content = (
                f"{system_prompt}\n\n" + "\n\n".join(context_sections)
            ).strip()
        else:
            sys_content = system_prompt or "你是一个具备记忆能力的智能助手。"

        messages.append({"role": "system", "content": sys_content})

        for msg in self.short_term_memory.get_recent_history():
            messages.append({"role": msg["role"], "content": msg["content"]})

        messages.append({"role": "user", "content": query})
        return messages

    # ================================================================
    # 工具方法
    # ================================================================

    def clear_short_term(self) -> None:
        """清空短期记忆（开始新对话时调用）。"""
        self.short_term_memory.clear()

    def __repr__(self) -> str:
        return (
            f"AgentMemory("
            f"short={len(self.short_term_memory)}/{self.short_term_memory.limit}, "
            f"static={len(self.static_memory)}, "
            f"dynamic={len(self.long_term_memory)}, "
            f"conflicts={len(self._pending_conflicts)})"
        )
