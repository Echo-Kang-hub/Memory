"""
memory/consolidator.py — 后台记忆整理器
==========================================
与前端（用户聊天路径）完全解耦的后台线程。

工作流程：
  1. 接收被 FIFO 弹出或 auto_extract 提交的对话片段
  2. LLM 提取 → 区分 static（固定属性）与 dynamic（动态记忆）
  3. 检索已有相似记忆
  4. LLM 比对 → ADD / UPDATE（无冲突融合）/ CONFLICT（阻塞写，推送前端）
  5. 执行写入或将冲突放入 AgentMemory._pending_conflicts 等待用户确认
"""

import json
import queue
import re
import threading
import traceback
import uuid
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from openai import OpenAI
from config import Config

if TYPE_CHECKING:
    from src.memory.manager import AgentMemory


# ── Prompts ─────────────────────────────────────────────────────────

_EXTRACT_PROMPT = """\
请从以下对话片段中提取值得长期记忆的事实，分为两类：
- static（静态）：用户的固定属性，如姓名/昵称、职业/职位、居住地、家庭关系、长期固定偏好
- dynamic（动态）：用户近期的状态、临时偏好、当前关注的话题、正在进行的计划、观点看法

规则：
- 只提取对话中明确出现的信息，不要推测
- 每条记忆应是独立、完整的短句
- 若无值得记忆的内容，返回 {{"memories": []}}

以纯 JSON 格式输出，不要包含任何其他文字：
{{
  "memories": [
    {{"type": "static",  "content": "用户的姓名是小明"}},
    {{"type": "dynamic", "content": "用户最近在学习机器学习"}}
  ]
}}

对话片段：
{text}"""


_COMPARE_PROMPT = """\
你是记忆去重助手，请判断新记忆相对于已有记忆应执行什么操作。

新记忆：{new_memory}

相关已有记忆（格式：[id=...] 内容）：
{existing_list}

以纯 JSON 格式输出，不要包含任何其他文字。

若无相关已有记忆，或新记忆是完全不重叠的新信息，输出：
{{"operation": "ADD", "reason": "..."}}

若新记忆是对已有记忆的补充/完善，信息不矛盾，输出：
{{"operation": "UPDATE", "reason": "...", "existing_id": "...", "existing_content": "...", "merged_content": "融合后的完整记忆"}}

若新记忆与已有记忆存在明显矛盾（姓名/地址/职业等关键信息出现根本性变化），输出：
{{"operation": "CONFLICT", "reason": "...", "existing_id": "...", "existing_content": "...", "conflict_reason": "具体冲突原因"}}

注意：若 existing_list 为空，始终返回 ADD。"""


# ── 数据类 ───────────────────────────────────────────────────────────

@dataclass
class ConflictItem:
    """记忆冲突项，等待用户在前端确认后才执行写入。"""
    memory_type:  str   # "static" | "dynamic"
    new_content:  str   # 新提取的记忆
    old_content:  str   # 已有的冲突记忆内容
    old_id:       str   # 已有记忆的 ID
    reason:       str   # 冲突原因
    # 唯一标识，用于前端按钮 key
    cid: str = field(default_factory=lambda: uuid.uuid4().hex[:8])


# ── 整理器 ───────────────────────────────────────────────────────────

class MemoryConsolidator:
    """
    后台记忆整理器。

    - 以 daemon 线程运行，进程退出时自动回收
    - submit() 立即返回，不阻塞调用方
    - 内部以 3 秒超时批量收集，再统一处理
    """

    def __init__(self, manager: "AgentMemory"):
        self._manager = manager
        self._queue: queue.Queue[list[dict]] = queue.Queue()
        self._thread = threading.Thread(
            target=self._worker, daemon=True, name="MemoryConsolidator"
        )
        self._thread.start()

    def submit(self, messages: list[dict]) -> None:
        """提交一批对话消息做后台整理，立即返回。"""
        if messages:
            self._queue.put(list(messages))

    # ── 工作线程 ────────────────────────────────────────────────────

    def _worker(self) -> None:
        while True:
            batch: list[dict] = []
            try:
                # 最多等 3 秒收集第一条
                first = self._queue.get(timeout=3.0)
                batch.extend(first)
                # 非阻塞地继续合并队列里的其余批次
                while True:
                    try:
                        batch.extend(self._queue.get_nowait())
                    except queue.Empty:
                        break
            except queue.Empty:
                continue

            if batch:
                try:
                    self._process(batch)
                except Exception:
                    traceback.print_exc()

    def _process(self, messages: list[dict]) -> None:
        if not Config.CHAT_API_KEY:
            return  # API Key 未配置，跳过

        # 去重，防止同一内容被重复提交
        seen: set[tuple] = set()
        unique: list[dict] = []
        for m in messages:
            key = (m.get("role", ""), m.get("content", ""))
            if key not in seen:
                seen.add(key)
                unique.append(m)

        text = "\n".join(f"{m['role']}: {m['content']}" for m in unique)

        client = OpenAI(api_key=Config.CHAT_API_KEY, base_url=Config.CHAT_BASE_URL)
        model = Config.CONSOLIDATE_MODEL or Config.CHATMODEL

        # Step 1: LLM 提取
        extracted = self._extract(client, model, text)
        if not extracted:
            return

        # Step 2: 逐条检索 + 比对 + 写入
        for item in extracted:
            try:
                self._process_one(client, model, item.get("type", "dynamic"), item.get("content", ""))
            except Exception:
                traceback.print_exc()

    # ── LLM 调用 ────────────────────────────────────────────────────

    def _extract(self, client: OpenAI, model: str, text: str) -> list[dict]:
        """调用 LLM，从对话文本中提取 static/dynamic 事实列表。"""
        raw = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": _EXTRACT_PROMPT.format(text=text)}],
            temperature=0,
        ).choices[0].message.content.strip()
        result = _parse_json(raw)
        if result is None:
            traceback.print_exc()
            return []
        return result.get("memories", [])

    def _compare(
        self, client: OpenAI, model: str, new_memory: str, existing_text: str
    ) -> dict:
        """调用比对 LLM，返回操作指令字典。JSON 解析失败时默认返回 ADD。"""
        raw = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": _COMPARE_PROMPT.format(
                        new_memory=new_memory,
                        existing_list=existing_text or "（无）",
                    ),
                }
            ],
            temperature=0,
        ).choices[0].message.content.strip()
        result = _parse_json(raw)
        if result is None:
            # LLM 返回了无法解析的内容，保守起见执行 ADD
            print(f"[Consolidator] _compare JSON解析失败，原始输出（前200字）: {raw[:200]}")
            return {"operation": "ADD", "reason": "JSON解析失败，默认ADD"}
        return result

    # ── 单条记忆处理 ────────────────────────────────────────────────

    def _process_one(self, client: OpenAI, model: str, mem_type: str, content: str) -> None:
        if not content.strip():
            return

        # 构建"已有相似记忆"列表文本
        existing_text = ""
        if mem_type == "static":
            all_static = self._manager.static_memory.get_all()[:20]
            existing_text = "\n".join(f"[id={e['id']}] {e['fact']}" for e in all_static)
        else:
            similar = self._manager.long_term_memory.retrieve(content, top_k=5)
            filtered = [s for s in similar if s["distance"] < Config.MEMORY_DEDUP_THRESHOLD]
            existing_text = "\n".join(f"[id={s['id']}] {s['fact']}" for s in filtered)

        # 无相似记忆 → 直接 ADD，省去一次 LLM 调用
        if not existing_text.strip():
            self._do_add(mem_type, content)
            return

        op = self._compare(client, model, content, existing_text)
        operation = op.get("operation", "ADD")

        if operation == "ADD":
            self._do_add(mem_type, content)
        elif operation == "UPDATE":
            self._do_update(
                mem_type,
                op.get("existing_id", ""),
                op.get("merged_content", content),
            )
        elif operation == "CONFLICT":
            self._manager.add_conflict(
                ConflictItem(
                    memory_type=mem_type,
                    new_content=content,
                    old_content=op.get("existing_content", ""),
                    old_id=op.get("existing_id", ""),
                    reason=op.get("conflict_reason", op.get("reason", "")),
                )
            )

    # ── 写入操作 ────────────────────────────────────────────────────

    def _do_add(self, mem_type: str, content: str) -> None:
        meta = {"source": "auto_extract"}
        if mem_type == "static":
            self._manager.static_memory.add(content, metadata=meta)
        else:
            self._manager.long_term_memory.add_memory(content, metadata=meta)

    def _do_update(self, mem_type: str, existing_id: str, merged_content: str) -> None:
        if not existing_id:
            self._do_add(mem_type, merged_content)
            return
        if mem_type == "static":
            self._manager.static_memory.update(existing_id, merged_content)
        else:
            self._manager.long_term_memory.delete_by_id(existing_id)
            self._manager.long_term_memory.add_memory(merged_content, metadata={"source": "auto_merge"})


# ── 工具函数 ──────────────────────────────────────────────────────────

def _strip_fence(text: str) -> str:
    """去除 LLM 输出中可能包裹的 markdown 代码块标记及 <think> 思考链标签。"""
    # 去掉 <think>...</think>（DeepSeek-R1 / Qwen3 thinking 模式）
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
    if text.startswith("```"):
        lines = text.split("\n")
        # 去掉第一行 ```json / ``` 和最后一行 ```
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return text


def _parse_json(text: str) -> dict | None:
    """
    容错 JSON 解析：先直接尝试，失败后从文本中提取最外层 {...} 块。
    返回 None 表示彻底无法解析。
    """
    text = _strip_fence(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # 找第一个 '{' 到最后一个 '}' 之间的内容再试一次
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None
