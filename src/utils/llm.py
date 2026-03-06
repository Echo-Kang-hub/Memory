"""
utils/llm.py — 统一的 Consolidator LLM 构建工厂
================================================
MemoryConsolidator 使用，与 embedding.py 的设计风格一致。

三种模式：
  api    — 兼容 OpenAI 接口的远程服务（默认），可配置独立于 CHATMODEL 的 key/url/model
  ollama — 本地 Ollama 服务（使用 ollama 原生客户端）
  local  — 直接加载 HuggingFace 模型（transformers，无需启动外部服务）

返回统一的 callable，签名：
    llm(messages: list[dict], temperature: float = 0) -> str
"""

from typing import Callable
from config import Config


def build_consolidate_llm() -> Callable[[list[dict], float], str]:
    """
    根据 CONSOLIDATE_TYPE 构建 Consolidator 所用的 LLM 调用函数。
    返回 callable(messages, temperature=0) -> str（模型的纯文本输出）。
    """
    llm_type = Config.CONSOLIDATE_TYPE.lower()

    if llm_type == "api":
        from openai import OpenAI
        client = OpenAI(
            api_key=Config.CONSOLIDATE_API_KEY,
            base_url=Config.CONSOLIDATE_API_BASE,
        )
        model = Config.CONSOLIDATE_MODEL

        def call_api(messages: list[dict], temperature: float = 0) -> str:
            return client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
            ).choices[0].message.content.strip()

        return call_api

    elif llm_type == "ollama":
        import ollama as _ollama
        model = Config.CONSOLIDATE_OLLAMA_MODEL

        def call_ollama(messages: list[dict], temperature: float = 0) -> str:
            resp = _ollama.chat(
                model=model,
                messages=messages,
                options={"temperature": temperature},
            )
            return resp["message"]["content"].strip()

        return call_ollama

    elif llm_type == "local":
        from transformers import pipeline as hf_pipeline
        pipe = hf_pipeline(
            "text-generation",
            model=Config.CONSOLIDATE_LOCAL_MODEL,
            device=Config.CONSOLIDATE_LOCAL_DEVICE,
            max_new_tokens=512,
        )

        def call_local(messages: list[dict], temperature: float = 0) -> str:
            # transformers >= 4.43 聊天模型支持直接传入 messages 列表
            result = pipe(
                messages,
                do_sample=temperature > 0,
                temperature=temperature if temperature > 0 else None,
            )
            # 输出格式：result[0]["generated_text"][-1]["content"]
            return result[0]["generated_text"][-1]["content"].strip()

        return call_local

    else:
        raise ValueError(
            f"不支持的 CONSOLIDATE_TYPE='{Config.CONSOLIDATE_TYPE}'，"
            "请在 .env 中设置为 api / ollama / local"
        )
