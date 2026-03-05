"""
manager.py — Agent Memory 管理器
=============================================
整合短期记忆（对话窗口） + 长期记忆（向量检索） + LLM 自动提取
"""

from src.memory.short_term import ShortTermMemory
from src.memory.long_term import LongTermMemory


class AgentMemory:
    """Agent 记忆管理器：统一管理短期与长期记忆。"""

    def __init__(self, short_term_limit: int = 10):
        self.short_term_memory = ShortTermMemory(limit=short_term_limit)
        self.long_term_memory = LongTermMemory()

    # ── 让 app.py 的 st.json(memory.short_term) 仍能直接访问列表 ──
    @property
    def short_term(self) -> list[dict]:
        return self.short_term_memory.history

    # ================================================================
    # 写入（Write）
    # ================================================================

    def add_message(self, role: str, content: str) -> None:
        """追加一条对话消息进短期记忆。role = 'user' | 'assistant'"""
        self.short_term_memory.add_memory(role, content)

    def save_fact(self, fact: str) -> None:
        """手动向长期记忆写入一条事实。"""
        self.long_term_memory.add_memory(fact)


    # ================================================================
    # LLM 自动提取：短期记忆 → 长期记忆
    # ================================================================

    def extract_to_long_term(self, client, model: str) -> list[str]:
        """
        把当前短期对话发给 LLM，提取值得长期记住的事实写入向量库。
        返回提取到的事实列表（空列表表示本轮无新事实）。
        建议在每次 assistant 回复后调用。
        """
        if not self.short_term_memory.history:
            return []

        history_text = self.short_term_memory.get_as_text()
        extract_prompt = (
            "你是一个记忆提取助手。请从下面的对话中提取值得长期记住的事实，"
            "例如用户的姓名、偏好、重要经历、明确的需求等。\n"
            "要求：\n"
            "- 每条事实单独一行，以 '- ' 开头\n"
            "- 只提取明确提到的信息，不要推测\n"
            "- 如果对话中没有值得记忆的事实，只输出：无\n\n"
            f"对话记录：\n{history_text}"
        )

        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": extract_prompt}],
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()

        if raw == "无" or not raw:
            return []

        facts = [
            line.lstrip("- ").strip()
            for line in raw.splitlines()
            if line.strip().startswith("- ")
        ]

        for fact in facts:
            self.long_term_memory.add_memory(fact, metadata={"source": "llm_extract"})

        return facts

    # ================================================================
    # 检索（Retrieve）
    # ================================================================

    def retrieve(self, query: str, top_k: int = 3) -> list[dict]:
        """从长期记忆中语义检索最相关的 top_k 条事实。"""
        return self.long_term_memory.retrieve(query, top_k)

    # ================================================================
    # 合成（Synthesize）
    # ================================================================

    def build_messages(self, query: str, system_prompt: str = "") -> list[dict]:
        """
        组装发给 LLM 的 messages 列表：
          [system（含相关长期记忆）] + [短期对话历史] + [当前用户提问]
        """
        messages: list[dict] = []

        # System 消息：注入语义检索到的长期记忆
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

        # 短期记忆：近期对话历史
        for msg in self.short_term_memory.get_recent_history():
            messages.append({"role": msg["role"], "content": msg["content"]})

        # 当前用户提问
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
            f"short_term={len(self.short_term_memory)}/{self.short_term_memory.limit}, "
            f"long_term={len(self.long_term_memory)})"
        )
