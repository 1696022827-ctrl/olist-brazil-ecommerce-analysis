# -*- coding: utf-8 -*-
"""
Agent 准确率评测脚本
====================
用 20 道有标准答案的业务问题考察 Agent 的代码生成与取数能力，
自动判分并输出准确率（结果同时写入 eval_result.csv）。

判分规则：
  - keywords：答案里必须出现的关键词（如品类名、州名）
  - numbers ：答案里出现的数字，与期望值相对误差 <= 1% 即算命中

运行方式：python eval_agent.py
注意：会真实调用 20 次大模型 API，消耗少量免费额度。
"""

import csv
import os
import re
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)
sys.path.insert(0, BASE_DIR)

from agent import build_agent, ask

# ========== 20 道评测题（期望值由 scripts 全量数据直接计算得出）==========
CASES = [
    {"q": "有多少个品类？", "numbers": [56]},
    {"q": "全部订单的总GMV是多少？", "numbers": [15418394.83, 1541.84]},
    {"q": "客单价是多少？", "numbers": [159.83]},
    {"q": "平均评分是多少？", "numbers": [4.16, 4.156]},
    {"q": "差评率是多少？差评指评分小于等于2分", "numbers": [12.8, 0.128]},
    {"q": "平均配送天数是多少？", "numbers": [12.09]},
    {"q": "订单延迟率是多少？", "numbers": [8.11, 0.0811]},
    {"q": "订单最多的州是哪个？", "keywords": ["SP"]},
    {"q": "2017年11月的GMV是多少？", "numbers": [1153229.37, 115.32, 115.3]},
    {"q": "GMV最高的月份是哪个月？", "any_keywords": ["2017-11", "2017年11月"]},
    {"q": "2018年全年的GMV是多少？", "numbers": [8450534.68, 845.05, 845.1]},
    {"q": "配送天数超过30天的订单，差评率是多少？", "numbers": [65.3, 0.653]},
    {"q": "平均运费是多少？", "numbers": [22.79]},
    {"q": "RFM里高价值客户有多少人？", "numbers": [6498]},
    {"q": "高价值客户的平均消费是多少？", "numbers": [311.96]},
    {"q": "客户一共分成哪几层？", "keywords": ["高价值客户", "流失客户", "新客户", "一般客户"]},
    {"q": "销售总额最高的品类是哪个？", "keywords": ["其他类目"]},
    {"q": "订单数不少于30的品类里，延迟率最高的是哪个？", "keywords": ["音频设备"]},
    {"q": "评价数不少于30的品类里，差评率最高的是哪个？", "keywords": ["男士服饰"], "numbers": [22.86, 0.2286]},
    {"q": "评价数不少于30的品类里，平均评分最低的是哪个？", "keywords": ["办公家具"], "numbers": [3.64, 3.645]},
]


def extract_numbers(text: str):
    """从回答中提取数字（先去掉千分位逗号）"""
    nums = []
    for m in re.findall(r"-?\d+(?:\.\d+)?", str(text).replace(",", "")):
        try:
            nums.append(float(m))
        except ValueError:
            pass
    return nums


def judge(answer: str, case: dict) -> bool:
    text = str(answer)
    # 1) 关键词必须全部出现（不区分大小写）
    for kw in case.get("keywords", []):
        if kw.lower() not in text.lower():
            return False
    # 1.5) 任一关键词出现即可
    any_kw = case.get("any_keywords", [])
    if any_kw and not any(kw.lower() in text.lower() for kw in any_kw):
        return False
    # 2) 数字命中任意一个期望值即可
    expected = case.get("numbers", [])
    if not expected:
        return True
    nums = extract_numbers(text)
    for exp in expected:
        for got in nums:
            if abs(got - exp) <= max(abs(exp) * 0.01, 0.01):
                return True
    return False


def main():
    agent = build_agent()
    rows = []
    for i, case in enumerate(CASES, 1):
        start = time.time()
        answer, _ = ask(agent, case["q"], history=[])
        cost = time.time() - start
        ok = judge(answer, case)
        rows.append(
            {
                "序号": i,
                "问题": case["q"],
                "回答": str(answer).replace("\n", " ")[:300],
                "耗时(秒)": round(cost, 1),
                "判定": "通过" if ok else "未通过",
            }
        )
        print(f"[{i:02d}/{len(CASES)}] {'✅' if ok else '❌'} {cost:5.1f}s  {case['q']}")
        print(f"      {str(answer)[:160]}")

    passed = sum(1 for r in rows if r["判定"] == "通过")
    total = len(rows)
    avg_cost = sum(r["耗时(秒)"] for r in rows) / total
    print("=" * 60)
    print(f"准确率：{passed}/{total} = {passed / total * 100:.1f}%")
    print(f"平均响应：{avg_cost:.1f} 秒")

    out = os.path.join(BASE_DIR, "eval_result.csv")
    with open(out, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"明细已写入 {out}")


if __name__ == "__main__":
    main()
