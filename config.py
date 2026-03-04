"""
config.py - 集中管理所有可配置项
从 .env 文件加载，后续只需改 .env，不用动代码。
"""

import os
from dotenv import load_dotenv

# 优先加载项目根目录的 .env
load_dotenv(override=True)


class Config:
    # ── LLM 连接 ──────────────────────────────────────────────────
    # BASE_URL 可换成任何兼容 OpenAI 接口的服务地址，例如：
    #   OpenRouter : https://openrouter.ai/api/v1
    #   DeepSeek   : https://api.deepseek.com/v1
    #   本地 Ollama: http://localhost:11434/v1
    API_KEY:  str = os.getenv("API_KEY", "")
    BASE_URL: str = os.getenv("BASE_URL", "https://api.openai.com/v1")
    MODEL:    str = os.getenv("MODEL", "gpt-4o-mini")

    # ── 系统提示词 ─────────────────────────────────────────────────
    SYSTEM_PROMPT: str = os.getenv(
        "SYSTEM_PROMPT",
        "你是一个具备记忆能力的智能助手，请结合已知记忆给出个性化回复。",
    )

    # ── Agent Memory 参数 ──────────────────────────────────────────
    SHORT_TERM_LIMIT: int = int(os.getenv("SHORT_TERM_LIMIT", "10"))

    def __repr__(self) -> str:
        key_preview = f"{self.API_KEY[:6]}..." if self.API_KEY else "（未设置）"
        return (
            f"Config(base_url={self.BASE_URL}, model={self.MODEL}, "
            f"api_key={key_preview}, short_term_limit={self.SHORT_TERM_LIMIT})"
        )


# 全局单例，直接 from config import cfg 使用
cfg = Config()
