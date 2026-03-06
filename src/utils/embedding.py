"""
utils/embedding.py — 统一的 Embedding 构建工厂
================================================
LongTermMemory 与 KnowledgeStore 共用，保证两者使用相同的向量化策略。
"""

from chromadb.utils import embedding_functions
from config import Config


def build_embedding():
    """根据 EMBED_TYPE 构建对应的 ChromaDB EmbeddingFunction。"""
    embed_type = Config.EMBED_TYPE.lower()

    if embed_type == "local":
        return embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=Config.EMBED_LOCAL_MODEL,
            device=Config.EMBED_LOCAL_DEVICE,
        )

    elif embed_type == "ollama":
        return embedding_functions.OllamaEmbeddingFunction(
            model_name=Config.EMBED_OLLAMA_MODEL,
            url=Config.EMBED_OLLAMA_URL,
        )

    elif embed_type == "api":
        return embedding_functions.OpenAIEmbeddingFunction(
            api_key=Config.EMBED_API_KEY,
            api_base=Config.EMBED_API_BASE,
            model_name=Config.EMBED_MODEL,
        )

    else:
        raise ValueError(
            f"不支持的 EMBED_TYPE='{Config.EMBED_TYPE}'，"
            "请在 .env 中设置为 local / ollama / api"
        )
