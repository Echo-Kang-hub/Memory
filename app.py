import streamlit as st
import streamlit.components.v1 as components
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

# --- CSS + Font Awesome（通过 JS 注入父页面，避免 Markdown 解析破坏 CSS）---
components.html("""
<script>
(function() {
    var p = window.parent.document;

    // 注入 Font Awesome
    if (!p.querySelector('link[href*="font-awesome"]')) {
        var fa = p.createElement('link');
        fa.rel = 'stylesheet';
        fa.href = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/4.7.0/css/font-awesome.min.css';
        p.head.appendChild(fa);
    }

    // 注入 CSS
    if (!p.getElementById('memory-custom-css')) {
        var s = p.createElement('style');
        s.id = 'memory-custom-css';
        s.textContent = `
            html, body, #root,
            [data-testid="stApp"],
            [data-testid="stAppViewContainer"],
            [data-testid="stMain"],
            section.main,
            .main .block-container {
                overflow: hidden !important;
                height: 100vh !important;
            }
            .main .block-container {
                padding-top: 0.3rem !important;
                padding-bottom: 0 !important;
                max-width: 100% !important;
            }
            /* ── 标题高低位置在这里调：margin-top 越小越靠上 ── */
            .main .block-container h1 {
                margin-top: 0 !important;
                margin-bottom: 0.3rem !important;
                padding-top: 0 !important;
            }
            [data-testid="stVerticalBlockBorderWrapper"] > div[style*="overflow"] {
                height: calc(100vh - 185px) !important;
                max-height: calc(100vh - 185px) !important;
                overflow-y: auto !important;
            }

            /* ── 主题 CSS 变量（暗色默认） ── */
            [data-testid="stApp"] {
                --chat-user-bg:        #282A2C;
                --chat-user-color:     #ffffff;
                --chat-avatar-bg:      #444444;
                --chat-avatar-color:   #aaaaaa;
                --chat-ai-color:       #e8eaed;
                --mem-item-bg:         #1e1e24;
                --sidebar-btn-bg:      #2a2a2a;
                --sidebar-btn-color:   #dddddd;
                --sidebar-btn-border:  #555555;
            }
            /* ── 亮色主题覆盖 ── */
            [data-testid="stApp"][data-theme="light"] {
                --chat-user-bg:        #F5F5F5;
                --chat-user-color:     #131314;
                --chat-avatar-bg:      #d0d8e8;
                --chat-avatar-color:   #555555;
                --chat-ai-color:       #000000;
                --mem-item-bg:         #eef2ff;
                --sidebar-btn-bg:      #282A2C;
                --sidebar-btn-color:   #000000;
                --sidebar-btn-border:  #cccccc;
            }
        `;
        p.head.appendChild(s);
    }
})();
</script>
""", height=0)

# --- 2. 左侧边栏 ---
with st.sidebar:
    st.markdown('<button style="width:100%;padding:0.45rem;border-radius:6px;border:1px solid var(--sidebar-btn-border);background:var(--sidebar-btn-bg);color:var(--sidebar-btn-color);cursor:pointer;font-size:0.9rem;"><i class="fa fa-plus"></i> &nbsp;New chat</button>', unsafe_allow_html=True)
    st.markdown("---")
    st.markdown('<p style="font-weight:600;margin-bottom:6px;">Chats</p>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:0.9rem;"><i class="fa fa-file-text-o"></i> &nbsp;图片内容提取与翻译需求</p>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:0.9rem;"><i class="fa fa-file-text-o"></i> &nbsp;Markdown/HTML 链接跳转</p>', unsafe_allow_html=True)
    st.markdown('<p style="font-size:0.9rem;"><i class="fa fa-file-text-o"></i> &nbsp;探讨 Memory 机制设计</p>', unsafe_allow_html=True)
    for _ in range(15):
        st.write("")
    st.markdown('<p style="font-size:0.9rem;"><i class="fa fa-cog"></i> &nbsp;Settings &amp; help</p>', unsafe_allow_html=True)

# --- 3. 顶部标题与控制按钮 ---
head_col = st.columns([9, 1])
with head_col[0]:
    st.markdown('<h1 style="margin:0;padding:0;"><i class="fa fa-database" style="font-size:1.8rem;background:linear-gradient(135deg,#4285f4,#9b72cb,#d96570);-webkit-background-clip:text;-webkit-text-fill-color:transparent;"></i> &nbsp;Memory Agent</h1>', unsafe_allow_html=True)
with head_col[1]:
    icon = "fa-chevron-right" if st.session_state.show_memory else "fa-chevron-left"
    label = "收起" if st.session_state.show_memory else "展开"
    if st.button(f"{label}", use_container_width=True, key="toggle_memory"):
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
        bubbles_html = '<div id="chat-messages" style="display:flex;flex-direction:column;gap:18px;padding:6px 4px;">'
        for msg in st.session_state.messages:
            content = msg["content"].replace("\n", "<br>")
            if msg["role"] == "user":
                bubbles_html += f"""
                <div style="display:flex;justify-content:flex-end;align-items:flex-end;gap:10px;">
                  <div style="max-width:70%;background:var(--chat-user-bg,#282A2C);color:var(--chat-user-color,#ffffff);
                              padding:11px 16px;border-radius:20px 20px 4px 20px;
                              font-size:0.93rem;line-height:1.6;word-wrap:break-word;">
                    {content}
                  </div>
                  <div style="width:34px;height:34px;border-radius:50%;
                              background:var(--chat-avatar-bg,#444444);color:var(--chat-avatar-color,#aaaaaa);flex-shrink:0;
                              display:flex;align-items:center;justify-content:center;font-size:15px;">
                    <i class="fa fa-user"></i>
                  </div>
                </div>"""
            else:
                bubbles_html += f"""
                <div style="display:flex;flex-direction:column;gap:6px;max-width:85%;">
                  <div style="display:flex;align-items:center;gap:10px;">
                    <div style="width:30px;height:30px;border-radius:50%;flex-shrink:0;
                                background:linear-gradient(135deg,#4285f4 0%,#9b72cb 50%,#d96570 100%);
                                display:flex;align-items:center;justify-content:center;color:#fff;font-size:14px;">
                      <i class="fa fa-star"></i>
                    </div>
                    <span style="font-size:0.82rem;color:#9aa0a6;font-weight:500;letter-spacing:.3px;">Memory Agent</span>
                  </div>
                  <div style="padding-left:40px;color:var(--chat-ai-color);font-size:0.93rem;line-height:1.7;">
                    {content}
                  </div>
                </div>"""
        # 锚点：JS 会找到它并滚动其父容器到底部
        bubbles_html += '<div id="chat-end" style="height:1px;"></div></div>'
        st.markdown(bubbles_html, unsafe_allow_html=True)

    # 自动滚到最新消息：找到 chat-end 锚点，向上遍历找到可滚动父节点
    components.html("""
    <script>
    (function() {
        function scrollChatToBottom() {
            var p = window.parent.document;
            var anchor = p.getElementById('chat-end');
            if (!anchor) return;
            // 向上找第一个 overflow 为 auto/scroll 的祖先
            var el = anchor.parentElement;
            while (el) {
                var style = window.parent.getComputedStyle(el);
                var overflow = style.overflow + style.overflowY;
                if (/auto|scroll/.test(overflow) && el.scrollHeight > el.clientHeight) {
                    el.scrollTop = el.scrollHeight;
                    return;
                }
                el = el.parentElement;
            }
        }
        setTimeout(scrollChatToBottom, 100);
        setTimeout(scrollChatToBottom, 400);
    })();
    </script>
    """, height=1)

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
            st.markdown('<h4><i class="fa fa-search"></i> &nbsp;检索到的记忆 $R$</h4>', unsafe_allow_html=True)
            st.caption("用户提问时从记忆库中召回的相关片段及相似度分数")
            retrieved = panel.get("retrieved", [])
            if retrieved:
                for r in retrieved:
                    score = r["score"]
                    bar_color = "#28a745" if score >= 0.7 else "#fd7e14" if score >= 0.5 else "#dc3545"
                    st.markdown(
                        f"<div style='background:var(--mem-item-bg);border-left:4px solid {bar_color};"
                        f"padding:0.5rem 0.8rem;border-radius:4px;margin-bottom:0.3rem;font-size:0.88rem'>"
                        f"<i class='fa fa-comment-o'></i> &nbsp;{r['fact']}</div>",
                        unsafe_allow_html=True
                    )
                    st.progress(score, text=f"Similarity Score = **{score}**")
            else:
                st.info("暂无检索结果，先和我聊几句让记忆库积累内容！")

            st.divider()

            # ── 模块2：记忆变动日志 (P / W) ──────────
            st.markdown('<h4><i class="fa fa-pencil-square-o"></i> &nbsp;记忆库变动日志 $P$ / $W$</h4>', unsafe_allow_html=True)
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
            st.markdown('<h4><i class="fa fa-brain" style="font-size:1rem;"></i><i class="fa fa-microchip"></i> &nbsp;合成后的 Prompt</h4>', unsafe_allow_html=True)
            st.caption("记忆注入后，真正发送给大模型的完整提示词")
            final_prompt = panel.get("final_prompt", "")
            if final_prompt:
                st.code(final_prompt, language="markdown")
            else:
                st.info("等待第一次对话触发…")

            st.divider()

            # ── 模块4：性能与评估指标 ─────────────────
            st.markdown('<h4><i class="fa fa-tachometer"></i> &nbsp;性能与评估指标</h4>', unsafe_allow_html=True)
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