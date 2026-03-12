"""
api.py — Agent Memory 测试接口服务
=====================================
为 MemTest-Mini 测试框架暴露标准 HTTP API，将本项目的 AgentMemory
接入外部测试工具。

启动方式（本地）：
    python api.py

启动方式（Docker，见 docker-compose.yml）：
    docker compose up api

接口概览：
    POST /chat              对话接口，含记忆提取与检索
    GET  /memory/{user_id}  白盒读取完整记忆库（测试专用）
    POST /reset             清空用户状态，确保测试隔离
    GET  /health            健康检查
"""

from __future__ import annotations

import asyncio
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from openai import OpenAI

from src.memory.manager import AgentMemory
from config import cfg


# ---------------------------------------------------------------------------
# Schema 定义（与 MemTest-Mini agent_api/example_agent.py 结构一致）
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    user_id: str = Field(..., description="用户唯一标识符", examples=["user_001"])
    message: str = Field(..., description="用户输入的文本消息", examples=["我对海鲜严重过敏。"])


class ChatResponse(BaseModel):
    response: str = Field(..., description="Agent 生成的文本回复")
    retrieved_memories: Optional[List[str]] = Field(
        default=None,
        description="本次检索到的相关记忆片段列表（可选）",
    )


class MemoryResponse(BaseModel):
    memories: Any = Field(..., description="当前用户的完整记忆库内容")


class ResetRequest(BaseModel):
    user_id: str = Field(..., description="需要清空所有记忆和对话历史的用户标识符")


class ResetResponse(BaseModel):
    status: str = Field(..., description="操作状态，成功时为 'ok'")
    message: Optional[str] = Field(default=None, description="可选附加说明")


# ---------------------------------------------------------------------------
# FastAPI 应用
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Agent Memory — MemTest-Mini 测试接口",
    description=(
        "将 Agent Memory 项目接入 MemTest-Mini 测试框架的标准 RESTful API。\n\n"
        "| 接口 | 方法 | 用途 |\n"
        "|------|------|------|\n"
        "| `/chat` | POST | 对话接口，含记忆提取与检索 |\n"
        "| `/memory/{user_id}` | GET | 白盒读取完整记忆库 |\n"
        "| `/reset` | POST | 清空用户状态，确保测试隔离 |"
    ),
    version="1.0.0",
)

# 每个 user_id 对应独立的 AgentMemory 实例
_user_memories: Dict[str, AgentMemory] = {}


def _get_memory(user_id: str) -> AgentMemory:
    """获取或创建指定用户的独立记忆实例。"""
    if user_id not in _user_memories:
        _user_memories[user_id] = AgentMemory(
            short_term_limit=cfg.SHORT_TERM_LIMIT,
            user_id=user_id,
        )
    return _user_memories[user_id]


# ---------------------------------------------------------------------------
# 接口实现
# ---------------------------------------------------------------------------

@app.post("/chat", response_model=ChatResponse, tags=["Core API"], summary="对话接口")
async def chat(req: ChatRequest) -> ChatResponse:
    """
    处理用户消息，执行记忆检索与更新，返回 LLM 回复。

    内部流程：
    1. 构建携带历史记忆的 messages（system + 短期历史 + 当前问题）
    2. 调用 LLM 生成回复
    3. 将本轮对话写入短期记忆
    4. 同步执行记忆整理（提取并持久化关键事实）
    """
    if not cfg.CHAT_API_KEY:
        return JSONResponse(status_code=503, content={"detail": "CHAT_API_KEY 未配置"})

    user_id = req.user_id
    message = req.message
    memory = _get_memory(user_id)

    # 检索相关记忆（用于响应中的 retrieved_memories 字段）
    retrieved = memory.retrieve(message)
    retrieved_texts = [m["fact"] for m in retrieved] if retrieved else []

    # 组装 messages（注入静态记忆 + 动态记忆 + 知识库）
    messages = memory.build_messages(query=message, system_prompt=cfg.SYSTEM_PROMPT)

    # 调用 LLM
    client = OpenAI(api_key=cfg.CHAT_API_KEY, base_url=cfg.CHAT_BASE_URL)
    response = client.chat.completions.create(
        model=cfg.CHATMODEL,
        messages=messages,
    )
    reply = response.choices[0].message.content

    # 写入短期记忆
    memory.add_message("user", message)
    memory.add_message("assistant", reply)

    # 同步记忆整理：在独立线程池中执行，避免阻塞 asyncio 事件循环
    # （consolidate_now 内含多次同步 LLM 调用，直接 await 会拖死所有并发请求）
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(
        None,
        lambda: memory.consolidate_now([
            {"role": "user",      "content": message},
            {"role": "assistant", "content": reply},
        ]),
    )

    return ChatResponse(response=reply, retrieved_memories=retrieved_texts or None)


@app.get(
    "/memory/{user_id}",
    response_model=MemoryResponse,
    tags=["Core API"],
    summary="记忆探查接口（白盒测试专用）",
)
async def get_memory(
    user_id: str = Path(..., description="需要查询记忆的用户标识符"),
) -> MemoryResponse:
    """
    返回指定用户当前所有生效的记忆内容，供测试框架进行白盒验证。

    包含：
    - 静态记忆（固定属性：姓名、职业等）
    - 动态记忆（ChromaDB 中所有已提取的事实）
    - 短期记忆（当前对话窗口，尚未整理的消息）
    """
    memory = _get_memory(user_id)

    static_items   = [item["fact"] for item in memory.static_memory.get_all()]
    dynamic_items  = [item["fact"] for item in memory.long_term_memory.get_all()]
    short_term_items = [
        f"{m['role']}: {m['content']}"
        for m in memory.short_term_memory.history
    ]

    return MemoryResponse(memories={
        "static":     static_items,
        "dynamic":    dynamic_items,
        "short_term": short_term_items,
    })


@app.post("/reset", response_model=ResetResponse, tags=["Core API"], summary="环境重置接口")
async def reset(req: ResetRequest) -> ResetResponse:
    """
    清空指定用户的所有对话历史和记忆数据，将其恢复到初始状态。

    清空范围：
    - 短期记忆（对话窗口）
    - 动态长期记忆（ChromaDB 集合）
    - 静态长期记忆（MongoDB / JSON 文件）
    - 冲突队列和后台整理任务队列
    """
    user_id = req.user_id
    memory = _get_memory(user_id)
    memory.reset()

    return ResetResponse(
        status="ok",
        message=f"用户 '{user_id}' 的对话历史和记忆已全部清空。",
    )


@app.get("/health", tags=["Utility"], summary="健康检查")
async def health_check():
    """返回服务运行状态，测试框架启动前可调用此接口确认 Agent 已就绪。"""
    return JSONResponse({"status": "ok", "service": "Agent Memory API"})


# ---------------------------------------------------------------------------
# 启动入口
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    print("=" * 55)
    print("  Agent Memory API 已启动")
    print("=" * 55)
    print("  Swagger UI  : http://127.0.0.1:8000/docs")
    print("  健康检查    : http://127.0.0.1:8000/health")
    print("  按 Ctrl+C 停止服务")
    print("=" * 55)

    uvicorn.run(app, host="0.0.0.0", port=8000)
