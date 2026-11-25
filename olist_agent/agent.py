# -*- coding: utf-8 -*-
"""
LangChain Agent 核心模块
========================
架构：ReAct（Reasoning + Acting）
  LLM 思考 → 选择工具 → 工具返回结果 → LLM 继续思考 → 最终回答

可用工具：
  1. Pandas DataFrame Tool  — 对 4 张 CSV 数据表执行自然语言查询
  2. Python REPL Tool       — 执行 Python 代码（用于画图等复杂逻辑）

数据源：data/ 目录下的 4 张 CSV（直接复用 Olist 项目产出）
"""

import os
import time
from dotenv import load_dotenv
import pandas as pd
import matplotlib
matplotlib.use("Agg")  # 后台运行不弹窗
import matplotlib.pyplot as plt

# ========== 加载环境变量 ==========
load_dotenv()

# ========== 读取 4 张数据表 ==========
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

clean_wide = pd.read_csv(os.path.join(DATA_DIR, "orders_base.csv"))  # df1：订单粒度，一单一行
rfm_result = pd.read_csv(os.path.join(DATA_DIR, "rfm_result.csv"))
category_sales = pd.read_csv(os.path.join(DATA_DIR, "category_sales_stats.csv"))
category_review = pd.read_csv(os.path.join(DATA_DIR, "category_review_stats.csv"))

# 时间列转 datetime（pandas agent 能直接处理）
if "order_purchase_timestamp" in clean_wide.columns:
    clean_wide["order_purchase_timestamp"] = pd.to_datetime(
        clean_wide["order_purchase_timestamp"], errors="coerce"
    )
if "下单月份" in clean_wide.columns:
    clean_wide["下单月份"] = clean_wide["下单月份"].astype(str)

# 设置 matplotlib 中文字体
plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False

# ========== 修正代码块包裹问题 ==========
# qwen 系列常把 Action Input 写成 ```py ... ```，
# 而 PythonAstREPLTool 的 sanitize 只识别 "python" 标记，
# 会把 "py" 当成变量名执行，报 NameError: name 'py' is not defined，
# 导致 Agent 反复重试直到耗尽步数。这里在执行前统一去掉代码块标记。
from langchain_experimental.tools.python.tool import PythonAstREPLTool

_original_tool_run = PythonAstREPLTool._run


def _strip_code_fence(text: str) -> str:
    """如果模型用 ```py 包裹代码，只保留第一个代码块内部的代码，
    丢弃代码块后面多写的说明文字（否则会拼成语法错误）。"""
    s = str(text).strip()
    if "```" not in s:
        return s
    rest = s[s.find("```") + 3:]
    if "\n" in rest:
        first_line, rest = rest.split("\n", 1)
        if first_line.strip().lower() not in ("", "py", "python", "python3"):
            rest = first_line + "\n" + rest
    end = rest.find("```")
    if end != -1:
        rest = rest[:end]
    return rest.strip()


def _patched_tool_run(self, query, run_manager=None):
    return _original_tool_run(self, _strip_code_fence(query), run_manager)


PythonAstREPLTool._run = _patched_tool_run


def build_agent():
    """构建并返回 LangChain Agent"""
    from langchain_openai import ChatOpenAI
    from langchain_experimental.agents.agent_toolkits import create_pandas_dataframe_agent
    from langchain.agents import AgentType

    # 初始化 LLM（支持 OpenAI 兼容接口）
    llm = ChatOpenAI(
        model=os.getenv("OPENAI_MODEL", "qwen-plus"),
        temperature=0,  # 数据分析要确定性
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_BASE_URL"),
        timeout=30,  # 单次 API 调用 30 秒超时，防止网络卡死
        max_retries=1,  # 失败只重试 1 次，避免长时间等待
    )

    # ========== 自定义解析错误处理（让 Agent 自己重试，而不是崩溃）==========
    def _handle_parse_error(error):
        return (
            "输出格式不正确。你只能输出以下两种形式之一：\n"
            "1) 继续调工具：\nThought: 你的思考\nAction: python_repl_ast\nAction Input: 纯 Python 代码\n"
            "2) 给出最终答案：\nThought: 我已得到结果\nFinal Answer: 你的结论\n"
            "注意「Final Answer:」必须用英文，不能写成「最终答案」。一次只调用一个工具。"
        )

    # ========== 系统提示：字段清单 + 统计口径 + 效率要求 ==========
    prefix = """你在分析 Olist 巴西电商数据，共有 4 个 pandas DataFrame。
字段清单已给出，不要再打印列名或数据结构去探查：

- df1 = clean_wide（订单明细，110189 行）：order_id, customer_id, order_status,
  order_purchase_timestamp, order_approved_at, order_delivered_carrier_date,
  order_delivered_customer_date, order_estimated_delivery_date, customer_unique_id,
  customer_zip_code_prefix, customer_city, customer_state, order_item_id, product_id,
  seller_id, shipping_limit_date, price, freight_value, category_cn, review_score,
  订单总金额, 实际配送天数, 是否延迟, 下单月份
- df2 = rfm_result：customer_unique_id, Recency, Frequency, Monetary, R_score, F_score, M_score, 客户分层
- df3 = category_sales_stats：category_cn, 订单数量, 销售总额, 延迟订单数量, 延迟率
- df4 = category_review_stats：category_cn, 有评价订单数, 平均评分, 差评率

统计规则（必须遵守）：
1. 只有在做「按分组排名」的比率分析（如各品类差评率/延迟率排名）时，才过滤小样本，
   默认门槛：df4 用「有评价订单数 >= 30」，df1 / df3 用订单数 >= 30。
   整体指标（如全量订单的差评率、平均评分、客单价）直接用全量数据计算，不要过滤、不要和 df4 关联。
2. 如果用户明确指定了样本量门槛，以用户说的为准。
3. 直接给结论，不复述问题、不写推导过程。禁止出现「依据：」「通过…计算」「df1 中…」
   「共 xxx 行」这类铺垫，除非用户明确问「怎么算的 / 为什么」。
4. 长度：一句话说清，全文不超过 60 字；列表题最多 5 行。
5. 需要说明口径时压缩成括号短语，如「（评价数≥30）」「（2017-11）」。
6. 列表类问题只输出「名称：数值」，一行一个，不加解释，不输出表格。
   排名/最值类问题必须带上对应数值和口径，如「办公家具（差评率 22.0%，评价数≥30）」。
   示例：问「2017年11月GMV是多少」→ 答「2017年11月GMV 115.32 万元（环比 +53.5%）。」
7. 问「A 和 B 有什么关系」时，先算相关系数，再分箱对比均值，最后给一句结论。
8. 「客单价」= 订单总金额合计 / 去重订单数（df1.order_id.nunique()），不是按行求均值。
9. df2 的「客户分层」只有 6 个固定取值：高价值客户、潜力客户、一般客户、新客户、
   流失客户、流失高价值；不要臆造「重要价值客户」等其他标签，查不到就说明原因。
10. 「延迟率」=「是否延迟」为"是"的去重订单数 / 去重订单数（df1 已是已送达订单）。
11. df1（订单表）已是一单一行，直接计算即可，不要再去重；评价类指标只统计 review_score 非空的订单。
12. GMV = df1["订单总金额"].sum()（已含运费）；客单价 = GMV / len(df1)；平均配送 = df1["配送天数"].mean()；
    延迟率 = df1["是否延迟"].mean()。不要再用 clean_wide 这类商品明细表。

效率要求（重要）：
- 禁止先 print 列名、shape、head 来探查数据，直接用上面给出的字段计算。
- 成功执行一次代码、拿到 Observation 后，必须马上用「Final Answer: ...」给出结论，
  禁止把同一段代码再执行一遍。
- 最多 2~3 步就要给出答案，不要反复验证。
- Action Input 直接写纯 Python 代码，不要用 ``` 代码块包裹。
- 一次只调用一个工具，严格使用 Thought / Action / Action Input 格式。
- 最终结论必须写成「Final Answer: 结论」（英文关键字），不能写成「最终答案：」。

"""

    # ========== 创建 Pandas Agent ==========
    # 用 ZERO_SHOT_REACT_DESCRIPTION（纯文本 ReAct），
    # 对国产大模型（qwen/通义）兼容性最好，避免 function calling 的 JSON 解析错误
    agent = create_pandas_dataframe_agent(
        llm=llm,
        df=[clean_wide, rfm_result, category_sales, category_review],
        agent_type=AgentType.ZERO_SHOT_REACT_DESCRIPTION,
        prefix=prefix,  # 系统提示：约束统计口径
        verbose=False,  # 关闭终端日志，改由界面展示思考过程
        allow_dangerous_code=True,  # 允许执行代码（数据分析场景必须）
        return_intermediate_steps=True,  # 返回中间思考步骤，用于界面展示
        max_iterations=10,  # 最多思考 10 步，保持响应较快
        max_execution_time=90,  # 整轮问答总耗时上限 90 秒，到点强制中断
        # 解析出错时把错误回传给模型让它重试，而不是直接崩溃
        agent_executor_kwargs={"handle_parsing_errors": _handle_parse_error},
    )

    return agent


def _format_thinking(steps) -> list:
    """把中间步骤格式化成可读的思考过程列表（过滤掉解析错误产生的伪步骤）"""
    valid = [
        (action, observation)
        for action, observation in steps
        if getattr(action, "tool", "") != "_Exception"
    ]
    formatted = []
    for i, (action, observation) in enumerate(valid, 1):
        if isinstance(action.tool_input, dict):
            code = action.tool_input.get("query", str(action.tool_input))
        else:
            code = str(action.tool_input)
        obs = str(observation)[:400]  # 结果太长就截断
        formatted.append(f"**步骤 {i}**\n🛠️ 执行代码：`{code}`\n📋 返回结果：\n```\n{obs}\n```")
    return formatted


def _build_context(history, max_rounds: int = 3, answer_len: int = 300) -> str:
    """把最近几轮问答拼成上下文，供 Agent 理解「它 / 这个品类 / 那个月」等指代"""
    if not history:
        return ""
    lines = []
    for item in history[-max_rounds:]:
        q = str(item.get("q", ""))[:200]
        a = str(item.get("a", ""))[:answer_len]
        lines.append(f"用户：{q}\n助手：{a}")
    return (
        "以下是此前的对话，仅用于理解指代关系（如「它」「这个品类」「那个月」）：\n"
        + "\n".join(lines)
        + "\n\n"
    )


def ask(agent, question: str, history=None):
    """
    向 Agent 提问。
    返回 (回答, 思考过程列表)。
    history: 之前的问答列表 [{"q": 问题, "a": 回答}, ...]，用于多轮上下文。
    自动识别画图请求并保存图片到 output_chart.png。
    """
    # 对画图类请求追加指令
    question_lower = question.lower()
    draw_keywords = ["画", "图", "plot", "chart", "图表", "可视化", "柱状", "折线", "饼图", "分布"]
    if any(kw in question_lower for kw in draw_keywords):
        question += (
            "。这是绘图任务：必须调用工具执行一段包含 plt.savefig('output_chart.png', "
            "dpi=120, bbox_inches='tight') 的 matplotlib 代码（中文字体），不要只用文字描述趋势。"
        )

    # 注入历史对话，实现多轮上下文
    context = _build_context(history)
    prompt = f"{context}当前问题：{question}" if context else question

    # 网络抖动 / 限流时自动重试一次，避免偶发 Connection error 直接失败
    result, last_err = None, ""
    for attempt in range(2):
        try:
            result = agent.invoke({"input": prompt})
            break
        except Exception as e:
            last_err = str(e)
            low = last_err.lower()
            retryable = "connection" in low or "rate limit" in low or "429" in last_err
            if attempt == 0 and retryable:
                time.sleep(1.5)
                continue
            break

    if result is not None:
        answer = result.get("output", "抱歉，我没理解你的问题。")
        steps = result.get("intermediate_steps", [])
        thinking = _format_thinking(steps) if steps else []
        # Agent 达到步数 / 时间上限时，langchain 会返回一句英文兜底
        if isinstance(answer, str) and answer.startswith("Agent stopped due to"):
            return (
                "⏱️ 这个问题让 Agent 思考超时了（最多 90 秒 / 10 步）。"
                "建议把问题拆小一点，例如先问「哪个品类差评率最高」，再追问细节。",
                thinking,
            )
        return answer, thinking

    msg = last_err
    if "timed out" in msg.lower() or "timeout" in msg.lower():
        return (
            "⏱️ 模型响应超时了（可能是网络波动或问题太复杂）。"
            "建议把问题拆小一点再问，或者稍后重试。",
            [],
        )
    if "Arrearage" in msg or "Access denied" in msg:
        return (
            "💳 大模型账户额度不足或已欠费，无法调用。"
            "请到阿里云百炼控制台充值 / 领取免费额度，或在 .env 里换一个可用的 API Key。",
            [],
        )
    if "429" in msg or "budget" in msg.lower() or "quota" in msg.lower():
        return (
            "💳 账户预算或免费额度已用尽（429），调用被拒绝。"
            "请到百炼控制台的「费用与成本 / 预算管理」调整预算或领取新额度后再试。",
            [],
        )
    # 兜底：任何异常都不让页面崩，给个友好提示
    return (
        f"分析过程中出了点小问题：{msg[:150]}。你可以换个方式重新提问试试～",
        [],
    )


if __name__ == "__main__":
    # 命令行快速测试
    agent = build_agent()
    print("🤖 Olist 分析 Agent 已就绪，输入 'quit' 退出\n")
    history = []
    while True:
        q = input("你: ")
        if q.lower() in ["quit", "exit", "退出"]:
            break
        ans, thinking = ask(agent, q, history)
        history.append({"q": q, "a": ans})
        print(f"Agent: {ans}")
        if thinking:
            print("—— 思考过程 ——")
            for t in thinking:
                print(t)
        print()
