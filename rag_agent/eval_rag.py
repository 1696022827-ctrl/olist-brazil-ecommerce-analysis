# -*- coding: utf-8 -*-
"""
RAG 评测：自建 16 道问答集，评估
  1) 检索召回率 hit@k：正确来源文件是否出现在 Top-K 检索结果里
  2) 答案准确率：回答是否包含所有关键事实（关键字匹配，确定可复现）
  3) 平均响应时间
运行：python eval_rag.py  →  生成 eval_result.csv
"""
import sys, csv, time
sys.stdout.reconfigure(encoding="utf-8")
from rag import load_index, answer

# 评测集：q=问题, keywords=回答必须包含的关键事实, source=应命中的来源文件
EVAL = [
    {"q": "入职满4年的员工每年有多少天年假？", "keywords": ["10"], "source": "hr_leave_policy.md"},
    {"q": "入职满6年有多少天年假？", "keywords": ["15"], "source": "hr_leave_policy.md"},
    {"q": "报销金额超过2000元需要额外经过谁审批？", "keywords": ["部门总监"], "source": "hr_reimbursement.md"},
    {"q": "员工报销的当月截止日是几号？", "keywords": ["25"], "source": "hr_reimbursement.md"},
    {"q": "新员工试用期是几个月？", "keywords": ["3"], "source": "hr_probation.md"},
    {"q": "最短试用期不能少于多久？", "keywords": ["1个月"], "source": "hr_probation.md"},
    {"q": "数据看板Pro支持多少种图表类型？", "keywords": ["14"], "source": "product_dashboard.md"},
    {"q": "数据看板Pro数据刷新频率最快是多少？", "keywords": ["5分钟"], "source": "product_dashboard.md"},
    {"q": "OpenAPI免费版每天调用上限是多少次？", "keywords": ["100"], "source": "product_api_rate_limit.md"},
    {"q": "API调用超限后返回什么HTTP状态码？", "keywords": ["429"], "source": "product_api_rate_limit.md"},
    {"q": "版本发布的灰度放量比例依次是多少？", "keywords": ["5%", "20%", "100%"], "source": "product_release.md"},
    {"q": "员工每周最多可以远程办公几天？", "keywords": ["2"], "source": "it_remote_work.md"},
    {"q": "远程办公需要提前多久申请？", "keywords": ["1天"], "source": "it_remote_work.md"},
    {"q": "客户手机号在展示时如何脱敏？", "keywords": ["前3", "后4"], "source": "it_data_security.md"},
    {"q": "公司核心服务部署在哪几个城市？", "keywords": ["北京", "上海", "深圳"], "source": "infra_regions.md"},
    {"q": "深圳灾备中心的RPO不超过多少？", "keywords": ["5分钟"], "source": "infra_regions.md"},
    {"q": "P0级故障承诺多久内响应？", "keywords": ["15分钟"], "source": "support_sla.md"},
    {"q": "今天天气怎么样？", "keywords": ["没有找到"], "source": None},  # 兜底：知识库无此信息
]

db = load_index()
rows = []
hit_count = 0
correct_count = 0
times = []

for i, item in enumerate(EVAL, 1):
    t0 = time.time()
    res = answer(db, item["q"])
    elapsed = round(time.time() - t0, 2)
    times.append(elapsed)

    ans = res["answer"]
    retrieved_sources = [r["source"] for r in res["retrieved"]]

    # 检索召回：期望来源是否被检索到
    if item["source"] is None:
        retrieval_ok = True  # 兜底题不考核检索
        hit_count += 1
    else:
        retrieval_ok = item["source"] in retrieved_sources
        hit_count += int(retrieval_ok)

    # 答案准确：所有关键字都出现在回答里（去掉空格再比，避免"5 分钟" vs "5分钟"误判）
    ans_norm = ans.replace(" ", "")
    answer_ok = all(kw.replace(" ", "") in ans_norm for kw in item["keywords"])
    correct_count += int(answer_ok)

    rows.append({
        "idx": i,
        "question": item["q"],
        "keywords": "|".join(item["keywords"]),
        "expected_source": item["source"] or "-",
        "retrieved_sources": "|".join(retrieved_sources),
        "retrieval_hit": "Y" if retrieval_ok else "N",
        "answer_correct": "Y" if answer_ok else "N",
        "elapsed_s": elapsed,
        "answer": ans.replace("\n", " ")[:200],
    })
    print(f"[{i:2}] 检索{'✓' if retrieval_ok else '✗'} 答案{'✓' if answer_ok else '✗'} ({elapsed}s) {item['q']}")
    if not answer_ok:
        print(f"     期望关键字: {item['keywords']}  实际: {ans[:80]}")

n = len(EVAL)
recall = hit_count / n
accuracy = correct_count / n
avg_t = sum(times) / n

summary = (
    f"\n{'='*50}\n"
    f"评测总数: {n}\n"
    f"检索召回率 hit@k: {hit_count}/{n} = {recall:.1%}\n"
    f"答案准确率: {correct_count}/{n} = {accuracy:.1%}\n"
    f"平均响应时间: {avg_t:.2f}s (最快 {min(times)}s / 最慢 {max(times)}s)\n"
    f"{'='*50}"
)
print(summary)

# 保存明细
out = "eval_result.csv"
with open(out, "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print(f"明细已保存: {out}")
