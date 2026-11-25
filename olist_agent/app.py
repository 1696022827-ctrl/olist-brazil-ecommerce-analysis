# -*- coding: utf-8 -*-
"""
Streamlit 交互界面
==================
运行方式：streamlit run app.py
"""

import os
import sys
import time

import streamlit as st

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)  # 固定工作目录，保证 Agent 画的图落在当前目录
from agent import build_agent, ask

CHART_PATH = os.path.join(BASE_DIR, "output_chart.png")

# ========== 页面配置 ==========
st.set_page_config(
    page_title="Olist 电商智能分析 Agent",
    page_icon="🤖",
    layout="wide",
)

st.title("🤖 Olist 巴西电商数据智能分析 Agent")
st.caption("基于 LangChain + Streamlit | 用自然语言提问，让 AI 帮你查数据、画图")


# ========== 初始化 Agent（缓存，只构建一次）==========
@st.cache_resource
def get_agent():
    return build_agent()


try:
    agent = get_agent()
except Exception as e:
    st.error(f"Agent 初始化失败，请检查 .env 里的 API Key：\n{e}")
    st.stop()

# ========== 会话状态 ==========
if "messages" not in st.session_state:
    st.session_state["messages"] = []
if "history" not in st.session_state:
    st.session_state["history"] = []

# ========== 侧边栏 ==========
with st.sidebar:
    st.header("💡 试试这些问题")
    example_groups = {
        "销售与 GMV": [
            "2017年11月的GMV是多少？",
            "2018年全年GMV是多少？",
            "客单价是多少？",
            "哪个月GMV最高？",
            "全部订单的总GMV是多少？",
        ],
        "品类与评价": [
            "哪个品类的差评率最高？只看评价数大于100的",
            "销售总额最高的5个品类是哪些？",
            "评价数大于30的品类里，平均评分最低的是哪个？",
            "评价数大于30的品类里，差评率TOP5是哪些？",
            "配送天数超过30天的订单，差评率是多少？",
        ],
        "物流与履约": [
            "平均配送天数是多少？",
            "订单延迟率是多少？",
            "哪些商品类目延迟率超过10%？",
            "配送时长和用户评分有什么关系？",
        ],
        "用户与 RFM": [
            "RFM高价值客户有多少人？平均消费多少？",
            "客户一共分成几层？各层多少人？",
            "流失客户有多少人？",
            "高价值客户的平均消费是多少？",
        ],
        "可视化": [
            "画一个月度GMV趋势图",
            "画各品类销售总额TOP10柱状图",
            "画客户分层占比饼图",
        ],
    }
    # 点击按钮 -> 写入待处理问题，主区域读到后自动提问
    for gi, (group, questions) in enumerate(example_groups.items()):
        with st.expander(group, expanded=(gi == 0)):
            for qi, ex in enumerate(questions):
                if st.button(ex, use_container_width=True, key=f"example_{gi}_{qi}"):
                    st.session_state["pending_question"] = ex

    st.divider()
    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state["messages"] = []
        st.session_state["history"] = []
        st.rerun()

    st.divider()
    st.caption(f"🧠 模型：{os.getenv('OPENAI_MODEL', '未配置')}")
    st.caption("📁 数据源：orders_base（订单粒度）/ rfm_result / category_sales / category_review")
    st.caption("⏱️ 每轮问答最多等 90 秒，超时会自动中断并提示")

# ========== 显示历史对话 ==========
for msg in st.session_state["messages"]:
    with st.chat_message(msg["role"]):
        if msg["role"] == "assistant" and msg.get("is_error"):
            st.warning(msg["content"])
        else:
            st.write(msg["content"])

        # 思考过程（可折叠）
        if msg.get("thinking"):
            title = f"🔍 查看 Agent 的思考过程（{len(msg['thinking'])} 步"
            if msg.get("elapsed") is not None:
                title += f"，耗时 {msg['elapsed']:.1f} 秒"
            title += "）"
            with st.expander(title):
                for t in msg["thinking"]:
                    st.markdown(t)

        # 图表：用存下来的字节流渲染，不依赖临时文件
        if msg.get("chart"):
            st.image(msg["chart"])

# ========== 输入区 ==========
typed = st.chat_input("问我任何关于 Olist 电商数据的问题...")
pending = st.session_state.pop("pending_question", None)
question = typed or pending

if question:
    st.session_state["messages"].append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        start = time.time()
        with st.spinner("🤔 Agent 正在分析数据（会自动展示思考过程，请稍候）..."):
            answer, thinking = ask(agent, question, st.session_state["history"])
        elapsed = time.time() - start

        is_error = answer.startswith("⏱️") or answer.startswith("分析过程中出了点小问题")
        if is_error:
            st.warning(answer)
        else:
            st.write(answer)

        if thinking:
            with st.expander(
                f"🔍 查看 Agent 的思考过程（{len(thinking)} 步，耗时 {elapsed:.1f} 秒）"
            ):
                for t in thinking:
                    st.markdown(t)
        elif not is_error:
            st.caption(f"⚡ 直接回答，未调用工具（耗时 {elapsed:.1f} 秒）")

        # 图表：读成字节流再删文件，避免下次 rerun 找不到文件
        chart_bytes = None
        if os.path.exists(CHART_PATH):
            with open(CHART_PATH, "rb") as f:
                chart_bytes = f.read()
            os.remove(CHART_PATH)
            st.image(chart_bytes)

    st.session_state["messages"].append(
        {
            "role": "assistant",
            "content": answer,
            "thinking": thinking,
            "elapsed": elapsed,
            "is_error": is_error,
            "chart": chart_bytes,
        }
    )
    # 记录到会话历史，供下一轮追问使用
    st.session_state["history"].append({"q": question, "a": answer})
