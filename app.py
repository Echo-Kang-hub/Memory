"""
app.py - Agent Memory MVP
streamlit run app.py
"""

import streamlit as st
from openai import OpenAI
from src.memory.manager import AgentMemory
from config import cfg

from PIL import Image

# == 页面配置（必须是第一个 Streamlit 调用）==
icon = Image.open("./assets/favicon.png")
st.set_page_config(page_title="Agent Memory", page_icon=icon, layout="wide")

# 注入 Font Awesome 4.7 CDN（set_page_config 之后注入）
st.markdown(
    '<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css">',
    unsafe_allow_html=True,
)

st.markdown('<h1><i class="fa fa-database"></i> Agent Memory</h1>', unsafe_allow_html=True)

# == 状态初始化（使用 config 参数）==
if "memory" not in st.session_state:
    st.session_state.memory = AgentMemory(short_term_limit=cfg.SHORT_TERM_LIMIT)
if "chat_log" not in st.session_state:
    st.session_state.chat_log = []
if "auto_extract" not in st.session_state:
    st.session_state.auto_extract = True

memory: AgentMemory = st.session_state.memory


# == 记忆显示：普通函数，由侧边栏上下文调用 ==
# 侧边栏的刷新由下方的 _memory_watcher fragment 检测到变化后触发 st.rerun() 完成

def render_memory_sidebar(mem: AgentMemory):
    st.markdown("**🔒 静态记忆**（MongoDB）")
    static_items = mem.static_memory.get_all()
    if static_items:
        for item in static_items:
            st.markdown(f"• {item['fact']}")
    else:
        st.caption("无静态记忆。")

    st.markdown("**🌀 动态记忆**（ChromaDB）")
    dynamic_items = mem.long_term_memory.get_all()
    if dynamic_items:
        for i, item in enumerate(dynamic_items):
            st.markdown(f"`[{i}]` {item['fact']}")
    else:
        st.caption("No Dynamic Memories Yet.")

    kb_count = len(mem.knowledge_store)
    if kb_count:
        st.caption(f"共 {kb_count} 个文档块")
        for src in mem.knowledge_store.list_sources():
            st.markdown(f"• `{src}`")
    else:
        st.caption("知识库为空，请运行 demo/load_knowledge.py 导入文档。")


@st.fragment(run_every="4s")
def render_memory_debug(mem: AgentMemory):
    with st.expander("Current Memory State (Debug)"):
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.subheader("Short-Term")
            st.json(mem.short_term)
        with col2:
            st.subheader("🔒 Static (MongoDB)")
            st.caption(f"backend: {mem.static_memory.backend}")
            st.json(mem.static_memory.get_all())
        with col3:
            st.subheader("🌀 Dynamic (ChromaDB)")
            st.json(mem.long_term_memory.get_all())
        with col4:
            st.subheader("📖 Knowledge Base")
            st.caption(f"{len(mem.knowledge_store)} 块 | {mem.knowledge_store.list_sources()}")
            st.json(mem.knowledge_store.get_all())


@st.fragment(run_every="3s")
def _memory_watcher(mem: AgentMemory):
    """
    静默监听 fragment（主内容区，3 秒轮询）。
    检测到动态/静态记忆数量变化时调用 st.rerun()，触发整页刷新，
    从而同步更新侧边栏（fragment 内无法直接写入侧边栏）。
    """
    dyn = len(mem.long_term_memory)
    sta = len(mem.static_memory.get_all())
    prev_dyn = st.session_state.get("_watcher_dyn")
    prev_sta = st.session_state.get("_watcher_sta")
    st.session_state._watcher_dyn = dyn
    st.session_state._watcher_sta = sta
    if prev_dyn is not None and (dyn != prev_dyn or sta != prev_sta):
        st.rerun()

# == 侧边栏 ==
with st.sidebar:
    st.markdown('<h3><i class="fa fa-cog"></i> 配置</h3>', unsafe_allow_html=True)

    # 模型可在运行时覆盖，默认读取 .env 中的 MODEL
    model_list = ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo", "deepseek-chat", "qwen-plus", "custom"]
    model = st.selectbox(
        "模型",
        model_list,
        index=model_list.index(cfg.CHATMODEL)
        if cfg.CHATMODEL in model_list
        else model_list.index("custom"),   # 不在列表时自动选 custom
    )
    if model == "custom":
        model = st.text_input("自定义模型名", value=cfg.CHATMODEL)

    # 显示当前 .env 中的服务配置（只读提示，不暴露完整 key）
    key_preview = f"{cfg.CHAT_API_KEY[:8]}..." if cfg.CHAT_API_KEY else "<i class=\"fa fa-exclamation-triangle\"></i> 未设置"
    st.caption(f"CHAT_BASE_URL: `{cfg.CHAT_BASE_URL}`")
    st.caption(f"CHAT_API_KEY: `{key_preview}`")

    st.divider()
    st.markdown('<h3><i class="fa fa-magic"></i> 自动提取</h3>', unsafe_allow_html=True)
    st.session_state.auto_extract = st.toggle(
        "每轮对话后后台提取记忆",
        value=st.session_state.auto_extract,
    )
    if st.session_state.auto_extract:
        st.caption("开启：每次 assistant 回复后将对话快照提交后台整理。")
    else:
        st.caption("关闭：仅当短期记忆窗口满载（FIFO 弹出）时触发后台整理。")

    st.divider()
    st.markdown('<h3><i class="fa fa-book"></i> 长期记忆</h3>', unsafe_allow_html=True)

    new_fact = st.text_input("手动写入动态事实", placeholder="例：用户喜欢 Python")
    if st.button("写入记忆") and new_fact:
        memory.save_fact(new_fact)
        st.success("已写入！")

    render_memory_sidebar(memory)

    st.divider()
    if st.button("Clear Short-Term Memory"):
        memory.clear_short_term()
        st.session_state.chat_log.clear()
        st.rerun()

# == 冲突检测（每次渲染时检查待确认冲突）==
conflicts = memory.peek_conflicts()
if conflicts:
    st.warning(f"⚠️ 发现 {len(conflicts)} 条记忆冲突，请确认后才会更新记忆。")
    for conflict in conflicts:
        with st.container(border=True):
            mem_tag = "🔒 静态" if conflict.memory_type == "static" else "🌀 动态"
            st.markdown(f"**冲突类型** {mem_tag} · {conflict.reason}")
            col_old, col_new = st.columns(2)
            with col_old:
                st.error(f"✖ 已有记忆\n\n{conflict.old_content}")
            with col_new:
                st.info(f"➕ 新记忆\n\n{conflict.new_content}")
            btn1, btn2 = st.columns(2)
            with btn1:
                if st.button("✓ 确认更新", key=f"accept_{conflict.cid}", type="primary"):
                    memory.resolve_conflict(conflict, accepted=True)
                    st.toast("已更新记忆！")
                    st.rerun()
            with btn2:
                if st.button("✕ 保留原记忆", key=f"reject_{conflict.cid}"):
                    memory.resolve_conflict(conflict, accepted=False)
                    st.toast("已保留原记忆。")
                    st.rerun()

# == 主对话区 ==
for msg in st.session_state.chat_log:
    with st.chat_message(msg["role"]):
        st.write(msg["content"])

user_input = st.chat_input("input your message here...")
if user_input:
    if not cfg.CHAT_API_KEY:
        st.error("Please set CHAT_API_KEY in the .env file")
        st.stop()

    with st.chat_message("user"):
        st.write(user_input)

    # 组装消息（短期 + 长期记忆 -> Prompt）
    messages = memory.build_messages(
        query=user_input,
        system_prompt=cfg.SYSTEM_PROMPT,
    )

    # BASE_URL 支持任意兼容 OpenAI 接口的服务
    client = OpenAI(api_key=cfg.CHAT_API_KEY, base_url=cfg.CHAT_BASE_URL)
    with st.chat_message("assistant"):
        with st.spinner("Thinking…"):
            response = client.chat.completions.create(
                model=model,
                messages=messages,
            )
        reply = response.choices[0].message.content
        st.write(reply)

    memory.add_message("user", user_input)
    memory.add_message("assistant", reply)
    st.session_state.chat_log.append({"role": "user",      "content": user_input})
    st.session_state.chat_log.append({"role": "assistant", "content": reply})

    # 后台记忆整理（异步，立即返回）
    if st.session_state.auto_extract:
        memory.submit_for_consolidation()
        st.toast("🧠 记忆正在后台整理中…")

# == Debug：当前记忆状态 ==
render_memory_debug(memory)

# == 后台记忆变化监听（3 秒轮询，检测到新记忆时触发整页刷新）==
_memory_watcher(memory)
