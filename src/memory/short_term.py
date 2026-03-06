from datetime import datetime

class ShortTermMemory:
    def __init__(self, limit: int = 10):
        self.history: list[dict] = []   # {"role", "content", "ts"}
        self.limit = limit

    def add_memory(self, role: str, content: str) -> dict | None:
        """追加消息。若发生 FIFO 弹出，返回被弹出的消息字典；否则返回 None。"""
        self.history.append({"role": role, "content": content, "ts": datetime.now().isoformat(timespec="seconds")})
        if len(self.history) > self.limit:
            return self.history.pop(0)
        return None
    def get_recent_history(self, n: int = None) -> list[dict]:   # 取最近 n 条
        return self.history[-n:] if n else self.history
    def get_as_text(self) -> str:   # 格式化成纯文本，供 LLM 提取时用
        return "\n".join([f"{item['role']}: {item['content']}" for item in self.history])
    def clear(self): 
        self.history.clear()
    def is_full(self) -> bool:   # 窗口满时触发记忆提取
        return len(self.history) >= self.limit
    def __len__(self): 
        return len(self.history)