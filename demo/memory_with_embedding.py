"""
memory.py — Agent Memory 核心模块
=============================================
架构：短期记忆（对话窗口） + 长期记忆（事实列表） + 语义检索

后续可在此基础上扩展：
  - 加入遗忘曲线、记忆重要性评分
  - 用 LLM 自动提取事实写入长期记忆
"""

from datetime import datetime
from src.memory.long_term import LongTermMemory


class AgentMemory:
    """Agent 记忆模块（最小实现）。"""
    def __init__(self, short_term_limit: int = 10):
        # ── 短期记忆：最近的对话消息列表（超出窗口自动丢弃最旧的） ──
        self.short_term: list[dict] = []
        self.long_term_memory = LongTermMemory()
        # 窗口大小
        self.short_term_limit = short_term_limit

    # ================================================================
    # 写入（Write）
    # ================================================================

    def add_message(self, role: str, content: str) -> None:
        """把一条对话消息追加进短期记忆。role = 'user' | 'assistant'"""
        self.short_term.append({
            "role": role,
            "content": content,
            "ts": datetime.now().isoformat(timespec="seconds"),
        })
        # 超出窗口：丢弃最旧的一条
        if len(self.short_term) > self.short_term_limit:
            self.short_term.pop(0)

    def save_fact(self, fact: str) -> None:
        """向长期记忆手动写入一条事实。"""
        self.long_term_memory.add_memory(fact)

    # ================================================================
    # 检索（Retrieve）
    # ================================================================

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """
        从长期记忆中用语义相似度检索最相关的事实。
        返回得分最高的 top_k 条（得分 = 相似度）。
        """
        return self.long_term_memory.retrieve(query, top_k)

    # ================================================================
    # 合成（Synthesize）
    # ================================================================

    def build_messages(self, query: str, system_prompt: str = "") -> list[dict]:
        """
        把记忆组装成发给 LLM 的 messages 列表：
          [system(长期记忆)] + [短期记忆消息] + [当前用户提问]
        """
        messages: list[dict] = []

        # 1. System 消息：把检索到的长期记忆注入进去
        relevant = self.retrieve(query)
        if relevant:
            memories_text = "\n".join(f"- {m['fact']}" for m in relevant)
            sys_content = (
                f"{system_prompt}\n\n"
                f"[已知的相关记忆]\n{memories_text}"
            ).strip()
        else:
            sys_content = system_prompt or "你是一个具备记忆能力的智能助手。"
        messages.append({"role": "system", "content": sys_content})

        # 2. 短期记忆：对话历史（不含即将追加的当前 query）
        for msg in self.short_term:
            messages.append({"role": msg["role"], "content": msg["content"]})

        # 3. 当前用户提问
        messages.append({"role": "user", "content": query})
        return messages

    # ================================================================
    # 工具方法
    # ================================================================

    def clear_short_term(self) -> None:
        """清空短期记忆（开始新对话时调用）。"""
        self.short_term.clear()

    def __repr__(self) -> str:
        return (
            f"AgentMemory("
            f"short_term={len(self.short_term)}/{self.short_term_limit}, "
            f"long_term={len(self.long_term_memory)})"
        )
