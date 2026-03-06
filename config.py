"""
config.py - 集中管理所有可配置项
从 .env 文件加载
"""

import os
from dotenv import load_dotenv

# 优先加载项目根目录的 .env
load_dotenv(override=True)


class Config:
    # ── LLM 连接（对话模型）──────────────────────────────────────────
    # CHAT_BASE_URL 可换成任何兼容 OpenAI 接口的服务地址，例如：
    #   OpenRouter : https://openrouter.ai/api/v1
    #   DeepSeek   : https://api.deepseek.com/v1
    #   本地 Ollama: http://localhost:11434/v1
    CHAT_API_KEY:  str = os.getenv("CHAT_API_KEY", "")
    CHAT_BASE_URL: str = os.getenv("CHAT_BASE_URL", "https://api.openai.com/v1")
    CHATMODEL:    str = os.getenv("CHATMODEL", "gpt-4o-mini")

    # ── Embedding 模式（LongTermMemory 使用）────────────────────────────
    # EMBED_TYPE 可选值: local | ollama | api
    EMBED_TYPE: str = os.getenv("EMBED_TYPE", "local")

    # local 模式：纯本地，通过 sentence-transformers 加载 HuggingFace 模型
    EMBED_LOCAL_MODEL:  str = os.getenv("EMBED_LOCAL_MODEL",  "Qwen/Qwen3-Embedding-0.6B")
    EMBED_LOCAL_DEVICE: str = os.getenv("EMBED_LOCAL_DEVICE", "cpu")   # cpu / cuda / mps

    # ollama 模式：本地 Ollama 服务
    EMBED_OLLAMA_MODEL: str = os.getenv("EMBED_OLLAMA_MODEL", "qwen3-embedding")
    EMBED_OLLAMA_URL:   str = os.getenv("EMBED_OLLAMA_URL",   "http://localhost:11434")

    # api 模式：兼容 OpenAI 接口的远程 API
    EMBED_API_KEY:  str = os.getenv("EMBED_API_KEY",  os.getenv("CHAT_API_KEY", ""))
    EMBED_API_BASE: str = os.getenv("EMBED_API_BASE", "https://api.openai.com/v1")
    EMBED_MODEL:    str = os.getenv("EMBED_MODEL",    "text-embedding-3-small")

    # ChromaDB 持久化路径（三种模式共用）
    VECTOR_DB_PATH: str = os.getenv("VECTOR_DB_PATH", "./data/chroma")

    # ── 系统提示词 ─────────────────────────────────────────────────
    SYSTEM_PROMPT: str = os.getenv(
        "SYSTEM_PROMPT",
        "你是一个具备记忆能力的智能助手，请结合已知记忆给出个性化回复。",
    )

    # ── MongoDB（静态记忆）────────────────────────────────────────────
    MONGO_URI:               str = os.getenv("MONGO_URI",               "mongodb://localhost:27017")
    MONGO_DB:                str = os.getenv("MONGO_DB",                "agent_memory")
    MONGO_STATIC_COLLECTION: str = os.getenv("MONGO_STATIC_COLLECTION", "static_memories")

    # ── 记忆整理 LLM（Consolidator）─────────────────────────────────────
    # CONSOLIDATE_TYPE 可选值: api（默认）| ollama | local
    CONSOLIDATE_TYPE: str = os.getenv("CONSOLIDATE_TYPE", "api")

    # api 模式：兼容 OpenAI 接口的远程服务，可配置独立于对话模型的 key / url / model
    # 留空则分别复用 CHAT_API_KEY / CHAT_BASE_URL / CHATMODEL
    CONSOLIDATE_API_KEY:  str = os.getenv("CONSOLIDATE_API_KEY",  os.getenv("CHAT_API_KEY",  ""))
    CONSOLIDATE_API_BASE: str = os.getenv("CONSOLIDATE_API_BASE", os.getenv("CHAT_BASE_URL", "https://api.openai.com/v1"))
    CONSOLIDATE_MODEL:    str = os.getenv("CONSOLIDATE_MODEL",    os.getenv("CHATMODEL",     "gpt-4o-mini"))

    # ollama 模式：本地 Ollama 服务（原生客户端，无需 OpenAI 兼容层）
    CONSOLIDATE_OLLAMA_MODEL: str = os.getenv("CONSOLIDATE_OLLAMA_MODEL", "qwen2.5:7b")
    CONSOLIDATE_OLLAMA_URL:   str = os.getenv("CONSOLIDATE_OLLAMA_URL",   "http://localhost:11434")

    # local 模式：直接加载 HuggingFace 模型（transformers，无需外部服务）
    CONSOLIDATE_LOCAL_MODEL:  str = os.getenv("CONSOLIDATE_LOCAL_MODEL",  "Qwen/Qwen2.5-1.5B-Instruct")
    CONSOLIDATE_LOCAL_DEVICE: str = os.getenv("CONSOLIDATE_LOCAL_DEVICE", "cpu")   # cpu / cuda / mps

    # 动态记忆去重阈值：distance < 此值才触发 LLM 比对（ChromaDB cosine distance，越低越相似）
    MEMORY_DEDUP_THRESHOLD:  float = float(os.getenv("MEMORY_DEDUP_THRESHOLD", "0.4"))

    # ── 知识库（Knowledge Base）参数 ────────────────────────────────
    # KB_COLLECTION：ChromaDB 中知识库使用的 Collection 名称，
    #                与记忆（agent_memories）完全隔离。
    KB_COLLECTION:    str = os.getenv("KB_COLLECTION",    "knowledge_base")
    KB_CHUNK_SIZE:    int = int(os.getenv("KB_CHUNK_SIZE",    "500"))  # 每块字符数
    KB_CHUNK_OVERLAP: int = int(os.getenv("KB_CHUNK_OVERLAP", "50"))   # 相邻块重叠量
    KB_TOP_K:         int = int(os.getenv("KB_TOP_K",         "3"))    # 检索返回条数

    # ── Agent Memory 参数 ──────────────────────────────────────────
    SHORT_TERM_LIMIT: int = int(os.getenv("SHORT_TERM_LIMIT", "10"))

    def __repr__(self) -> str:
        key_preview = f"{self.CHAT_API_KEY[:6]}..." if self.CHAT_API_KEY else "（未设置）"
        return (
            f"Config(chat_base_url={self.CHAT_BASE_URL}, chat_model={self.CHATMODEL}, "
            f"chat_api_key={key_preview}, short_term_limit={self.SHORT_TERM_LIMIT})"
        )


# 全局单例，直接 from config import cfg 使用
cfg = Config()
