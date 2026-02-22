import streamlit as st
import time
import random

# 1. 页面基本设置
st.set_page_config(page_title="Memory UI", layout="wide", initial_sidebar_state="expanded")

# --- 状态初始化区 ---
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "你好！我是具备记忆机制的智能体。请问今天探讨点什么？"}]
if "show_memory" not in st.session_state:
    st.session_state.show_memory = False
if "memory_db" not in st.session_state:
    # 每条记忆格式：{"fact": str}
    st.session_state.memory_db = []
if "panel" not in st.session_state:
    st.session_state.panel = {
        "retrieved": [],
        "change_log": [],
        "final_prompt": "",
        "metrics": {}
    }

# --- 核心逻辑：模拟完整记忆流水线 ---
def simulate_memory_pipeline(user_input: str) -> str:
    """每次用户发消息时调用，模拟检索→管理→合成→计时四个环节。"""
    panel = {"retrieved": [], "change_log": [], "final_prompt": "", "metrics": {}}

    # ── 模块1：检索 (R) ──────────────────────────────
    # 兼容旧格式（纯字符串）与新格式（{"fact": str}）
    st.session_state.memory_db = [
        m if isinstance(m, dict) else {"fact": m}
        for m in st.session_state.memory_db
    ]

    t0 = time.time()
    retrieved = []
    if st.session_state.memory_db:
        for mem in st.session_state.memory_db:
            keywords = set(mem["fact"].replace("，", " ").replace("。", " ").split())
            input_words = set(user_input)
            overlap = len(keywords & input_words)
            score = round(min(0.99, 0.45 + overlap * 0.15 + random.uniform(0, 0.1)), 2)
            retrieved.append({"fact": mem["fact"], "score": score})
        retrieved = sorted(retrieved, key=lambda x: x["score"], reverse=True)[:3]
    retrieval_time = round((time.time() - t0) * 1000 + random.uniform(20, 80), 1)
    panel["retrieved"] = retrieved

    # ── 模块2：记忆管理 (P / W) ──────────────────────
    change_log = []
    keywords_new  = ["名字", "叫", "喜欢", "养了", "住在", "工作", "下班", "爱好", "擅长", "学习"]
    keywords_edit = ["改成", "其实", "不对", "更新", "变成", "现在是", "已经"]
    is_edit = any(k in user_input for k in keywords_edit)
    is_new  = any(k in user_input for k in keywords_new)

    if is_edit and st.session_state.memory_db:
        old_fact = st.session_state.memory_db[-1]["fact"]
        new_fact = user_input.strip("。！？")
        st.session_state.memory_db[-1]["fact"] = new_fact
        change_log.append({"type": "UPDATE", "content": f"旧：{old_fact}  →  新：{new_fact}"})
    elif is_new:
        new_fact = user_input.strip("。！？")
        st.session_state.memory_db.append({"fact": new_fact})
        change_log.append({"type": "NEW", "content": new_fact})
    else:
        change_log.append({"type": "NOOP", "content": "本轮对话为闲聊，无需写入记忆库。"})
    panel["change_log"] = change_log

    # ── 模块3：合成最终 Prompt ────────────────────────
    memory_block = ""
    if retrieved:
        lines = "\n".join([f"- {r['fact']} (similarity={r['score']})" for r in retrieved])
        memory_block = f"[RETRIEVED MEMORIES]\n{lines}\n\n"
    final_prompt = (
        f"{memory_block}"
        f"[USER MESSAGE]\n{user_input}\n\n"
        f"[SYSTEM INSTRUCTION]\n请结合以上记忆，给出个性化且连贯的回复。"
    )
    panel["final_prompt"] = final_prompt

    # ── 模块4：性能指标 ───────────────────────────────
    prompt_tokens = int(len(final_prompt) * 1.5)
    reply_tokens  = random.randint(40, 120)
    panel["metrics"] = {
        "retrieval_time": retrieval_time,
        "prompt_tokens":  prompt_tokens,
        "reply_tokens":   reply_tokens,
        "total_tokens":   prompt_tokens + reply_tokens,
    }
    st.session_state.panel = panel

    # 生成回复
    if retrieved:
        mem_hint = "、".join([r["fact"] for r in retrieved[:2]])
        return f"（已检索到相关记忆：{mem_hint}）\n\n我已收到：「{user_input}」，并结合历史记忆为你作答。"
    return f"我已收到：「{user_input}」。暂无相关历史记忆，这是一次全新对话。"

# --- CSS：锁死所有层级的滚动，气泡式对话样式 ---
st.markdown("""
<style>
/* ══ 1. 锁死整体页面所有层级的滚动 ══ */
html, body,
#root,
[data-testid="stApp"],
[data-testid="stAppViewContainer"],
[data-testid="stMain"],
section.main,
.main .block-container {
    overflow: hidden !important;
    height: 100vh !important;
}
.main .block-container {
    padding-top: 0.5rem !important;
    padding-bottom: 0 !important;
    max-width: 100% !important;
}

/* ══ 2. 用 calc 让内部滚动容器撑满剩余高度 ══
        210px ≈ 顶栏48 + 标题72 + 输入框72 + 间距18 */
[data-testid="stVerticalBlockBorderWrapper"] > div[style*="overflow"] {
    height: calc(100vh - 210px) !important;
    max-height: calc(100vh - 210px) !important;
    overflow-y: auto !important;
}

/* ══ 3. 消除 st.markdown 气泡外层多余间距 ══ */
.chat-bubble-wrapper [data-testid="stMarkdown"] {
    padding: 0 !important;
    margin: 0 !important;
}
</style>
""", unsafe_allow_html=True)

# --- 2. 左侧边栏 ---
with st.sidebar:
    st.button("➕ New chat", use_container_width=True)
    st.markdown("---")
    st.markdown("### Chats")
    st.markdown("📝 图片内容提取与翻译需求")
    st.markdown("📝 Markdown/HTML 链接跳转")
    st.markdown("📝 探讨 Memory 机制设计")
    
    # 强行撑开底部空间，把设置按钮挤到最下面
    for _ in range(15):
        st.write("")
    st.markdown("⚙️ Settings & help")

# --- 3. 顶部标题与控制按钮 ---
head_col = st.columns([8, 2])
with head_col[0]:
    st.title("✨ Memory 演示台")
with head_col[1]:
    button_label = "👉 收起" if st.session_state.show_memory else "👈 展开"
    if st.button(button_label, use_container_width=True, key="toggle_memory"):
        st.session_state.show_memory = not st.session_state.show_memory
        st.rerun()

# --- 4. 动态主布局 ---
if st.session_state.show_memory:
    chat_col, mem_col = st.columns([6, 4], gap="large")
else:
    chat_col = st.container()
    mem_col = None

# --- 5. 主聊天区 ---
with chat_col:
    chat_container = st.container(height=730, border=False)
    with chat_container:
        # 构建所有消息的气泡 HTML（一次渲染，避免 Streamlit 多余包装）
        bubbles_html = '<div style="display:flex;flex-direction:column;gap:10px;padding:4px 2px;">'
        for msg in st.session_state.messages:
            content = msg["content"].replace("\n", "<br>")
            if msg["role"] == "user":
                bubbles_html += f"""
                <div style="display:flex;justify-content:flex-end;align-items:flex-end;gap:8px;">
                    <div style="max-width:72%;background:#282A2C;color:#fff;
                                padding:10px 14px;border-radius:18px 18px 4px 18px;
                                font-size:0.93rem;line-height:1.55;word-wrap:break-word;
                                box-shadow:0 1px 2px rgba(0,0,0,.15);">
                        {content}
                    </div>
                    <div style="width:34px;height:34px;border-radius:50%;background:#cce0ff;
                                display:flex;align-items:center;justify-content:center;
                                flex-shrink:0;font-size:16px;">👤</div>
                </div>"""
            else:
                bubbles_html += f"""
                <div style="display:flex;justify-content:flex-start;align-items:flex-end;gap:8px;">
                    <div style="width:34px;height:34px;border-radius:50%;background:#e8eaed;
                                display:flex;align-items:center;justify-content:center;
                                flex-shrink:0;font-size:16px;">🤖</div>
                    <div style="max-width:72%;background:#131314;color:#fff;
                                padding:10px 14px;border-radius:18px 18px 18px 4px;
                                font-size:0.93rem;line-height:1.55;word-wrap:break-word;
                                box-shadow:0 1px 2px rgba(0,0,0,.10);">
                        {content}
                    </div>
                </div>"""
        bubbles_html += "</div>"
        st.markdown(bubbles_html, unsafe_allow_html=True)

    prompt = st.chat_input("Ask anything")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        reply = simulate_memory_pipeline(prompt)
        st.session_state.messages.append({"role": "assistant", "content": reply})
        st.rerun()

# --- 6. 右侧：四模块记忆透视面板 ---
if mem_col:
    with mem_col:
        panel = st.session_state.panel
        mem_container = st.container(height=800, border=False)
        with mem_container:

            # ── 模块1：检索到的记忆 (R) ──────────────
            st.markdown("#### 🔍 检索到的记忆 $R$")
            st.caption("用户提问时从记忆库中召回的相关片段及相似度分数")
            retrieved = panel.get("retrieved", [])
            if retrieved:
                for r in retrieved:
                    score = r["score"]
                    bar_color = "#28a745" if score >= 0.7 else "#fd7e14" if score >= 0.5 else "#dc3545"
                    st.markdown(
                        f"<div style='background:#f8f9fa;border-left:4px solid {bar_color};"
                        f"padding:0.5rem 0.8rem;border-radius:4px;margin-bottom:0.3rem;font-size:0.88rem'>"
                        f"💬 {r['fact']}</div>",
                        unsafe_allow_html=True
                    )
                    st.progress(score, text=f"Similarity Score = **{score}**")
            else:
                st.info("暂无检索结果，先和我聊几句让记忆库积累内容！")

            st.divider()

            # ── 模块2：记忆变动日志 (P / W) ──────────
            st.markdown("#### 📝 记忆库变动日志 $P$ / $W$")
            st.caption("本轮对话对记忆库执行的写入或编辑操作")
            change_log = panel.get("change_log", [])
            if change_log:
                for entry in change_log:
                    t = entry["type"]
                    if t == "NEW":
                        st.success(f"**[新增]** {entry['content']}")
                    elif t == "UPDATE":
                        st.warning(f"**[更新/编辑]** {entry['content']}")
                    else:
                        st.info(f"**[无操作]** {entry['content']}")
            else:
                st.info("等待第一次对话触发…")

            st.divider()

            # ── 模块3：合成后的最终 Prompt ────────────
            st.markdown("#### 🧠 合成后的 Prompt")
            st.caption("记忆注入后，真正发送给大模型的完整提示词")
            final_prompt = panel.get("final_prompt", "")
            if final_prompt:
                st.code(final_prompt, language="markdown")
            else:
                st.info("等待第一次对话触发…")

            st.divider()

            # ── 模块4：性能与评估指标 ─────────────────
            st.markdown("#### ⏱️ 性能与评估指标")
            metrics = panel.get("metrics", {})
            if metrics:
                c1, c2 = st.columns(2)
                with c1:
                    st.metric(label="检索耗时 Δt",  value=f"{metrics.get('retrieval_time', 0)} ms")
                    st.metric(label="Prompt Tokens", value=metrics.get("prompt_tokens", 0))
                with c2:
                    st.metric(label="总 Token 消耗", value=metrics.get("total_tokens", 0))
                    st.metric(label="Reply Tokens",  value=metrics.get("reply_tokens", 0))
            else:
                st.info("等待第一次对话触发…")