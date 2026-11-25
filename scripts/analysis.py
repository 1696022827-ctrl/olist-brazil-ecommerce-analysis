# -*- coding: utf-8 -*-
"""
Olist 巴西电商数据分析主脚本
=========================
完整流程：数据读取 → 清洗 → RFM 用户分层 → 类目 EDA → 评价分析 → 月度趋势 → 图表输出

数据来源：data/ 目录（原始 CSV）
产出目录：
  output/csv/   清洗后数据（给 PowerBI 用）
  output/charts/ 所有 PNG 图表
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

# ============================================================
# 路径配置（基于脚本位置，从任意目录运行都能找到数据）
# ============================================================
BASE_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR  = os.path.join(BASE_DIR, "data")
OUT_CSV   = os.path.join(BASE_DIR, "output", "csv")
OUT_PNG   = os.path.join(BASE_DIR, "output", "charts")
os.makedirs(OUT_CSV, exist_ok=True)
os.makedirs(OUT_PNG, exist_ok=True)

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
plt.rcParams["axes.unicode_minus"] = False


# ============================================================
# 1. 读取原始数据
# ============================================================
orders      = pd.read_csv(os.path.join(DATA_DIR, "olist_orders_dataset.csv"))
order_items = pd.read_csv(os.path.join(DATA_DIR, "olist_order_items_dataset.csv"))
products    = pd.read_csv(os.path.join(DATA_DIR, "olist_products_dataset.csv"))
cat_trans   = pd.read_csv(os.path.join(DATA_DIR, "product_category_name_translation.csv"))
customers   = pd.read_csv(os.path.join(DATA_DIR, "olist_customers_dataset.csv"))
reviews     = pd.read_csv(os.path.join(DATA_DIR, "olist_order_reviews_dataset.csv"))

print("==== 1. 原始数据加载完成 ====")
print(f"orders: {len(orders)} 行 | order_items: {len(order_items)} 行 | products: {len(products)} 行")


# ============================================================
# 2. 清洗 orders 表：只保留已交付且时间合法的订单
# ============================================================
for c in ["order_purchase_timestamp", "order_approved_at",
          "order_delivered_carrier_date", "order_delivered_customer_date",
          "order_estimated_delivery_date"]:
    orders[c] = pd.to_datetime(orders[c], errors="coerce")

orders = (
    orders.drop_duplicates(subset="order_id")
          .query("order_status == 'delivered'")
          .query("order_delivered_customer_date.notna()")
          .query("order_estimated_delivery_date.notna()")
          .query("order_delivered_customer_date >= order_purchase_timestamp")
          .copy()
)
print(f"\n==== 2. 清洗后有效订单：{len(orders)} ====")


# ============================================================
# 3. 清洗 order_items 表（价格、运费合法性校验）
# ============================================================
order_items = (
    order_items.drop_duplicates()
               .query("price > 0 and freight_value >= 0")
               .copy()
)


# ============================================================
# 4. 类目翻译（葡语 → 中文）
#    cat_map 的 key 是葡语，必须映射到葡语字段 product_category_name
#    而不是英文字段 product_category_name_english
# ============================================================
cat_map = {
    "utilidades_domesticas": "家居用品",
    "beleza_saude": "美妆健康",
    "esporte_lazer": "运动休闲",
    "informatica_acessorios": "数码配件",
    "cama_mesa_banho": "床品卫浴",
    "relogios_presentes": "钟表礼品",
    "telefonia": "手机通讯",
    "brinquedos": "玩具",
    "ferramentas_jardim": "园艺工具",
    "automotivo": "汽车用品",
    "cool_stuff": "新奇好物",
    "moveis_decoracao": "家具装饰",
    "pet_shop": "宠物用品",
    "eletronicos": "电子产品",
    "livros_interesse_geral": "书籍",
    "alimentos": "食品",
    "bebes": "母婴",
    "fashion_bolsas_e_acessorios": "时尚包袋配饰",
    "fashion_calcados": "鞋履",
    "fashion_roupa_masculina": "男士服饰",
    "fashion_roupa_feminina": "女士服饰",
    "fashion_underwear_beach": "内衣沙滩装",
    "fashion_joalheria": "珠宝首饰",
    "artes": "艺术品",
    "artes_e_artesanato": "手工艺品",
    "seguros_e_servicos": "保险服务",
    "musica": "音乐周边",
    "casa_conforto": "居家舒适用品",
    "portateis_casa_forno_e_cafe": "便携厨电",
    "portateis_cozinha_e_preparadores_de_alimentos": "便携料理设备",
    "pc_gamer": "游戏主机",
    "sinalizacao_e_seguranca": "安防标识",
    "pcs": "台式电脑",
    "papelaria": "文具",
    "climatizacao": "温控设备",
    "construcao_ferramentas_iluminacao": "照明工具",
    "construcao_ferramentas_seguranca": "建筑安全工具",
    "construcao_ferramentas_jardim": "园林施工工具",
    "construcao_ferramentas_ferramentas": "施工工具",
    "audio": "音频设备",
    "dvds_blu_ray": "影音碟片",
    "flores": "鲜花",
    "frigorificos": "制冷设备",
    "la_cuisine": "法式厨具",
    "moveis_escritorio": "办公家具",
    "moveis_sala": "客厅家具",
    "moveis_quarto": "卧室家具",
    "malas_acessorios": "箱包配件",
    "consoles_games": "游戏主机配件",
    "eletrodomesticos": "大家电",
    "eletrodomesticos_2": "小家电",
    "agro_industria_e_comercio": "农工商业",
    "artigos_de_natal": "圣诞用品",
    "bebidas": "酒水饮料",
    "cds_dvds_musicais": "音乐碟片",
    "cha_de_cozinha": "厨房茶饮",
    "livros_tecnicos": "技术书籍",
    "market_place": "第三方市集",
    "moda_acessorios": "时尚配饰",
    "musica_instrumentos": "乐器",
    "fashion_roupa_infanto_juvenil": "童装",
    "festas": "节庆用品",
}

products = products.merge(cat_trans, how="left", on="product_category_name")
products["category_cn"] = products["product_category_name"].map(cat_map).fillna("其他类目")

print(f"\n==== 3. 类目翻译 ====")
print(products["category_cn"].value_counts().head(10))


# ============================================================
# 5. 合并宽表 + 衍生字段
# ============================================================
# 评价表预处理：取每个订单第一条评价
reviews_per_order = reviews.drop_duplicates(subset="order_id")[["order_id", "review_score"]].copy()

order_wide = (
    orders.merge(customers, on="customer_id", how="left")
          .merge(order_items, on="order_id", how="left")
          .merge(products[["product_id", "category_cn"]], on="product_id", how="left")
          .merge(reviews_per_order, on="order_id", how="left")  # 带上评价分数给 PowerBI
)

order_wide["订单总金额"] = order_wide["price"] + order_wide["freight_value"]
order_wide["实际配送天数"] = (
    order_wide["order_delivered_customer_date"] - order_wide["order_purchase_timestamp"]
).dt.days
order_wide["是否延迟"] = np.where(
    order_wide["order_delivered_customer_date"] > order_wide["order_estimated_delivery_date"],
    "是", "否",
)

print(f"\n==== 4. 宽表构建完成：{len(order_wide)} 行 ====")


# ============================================================
# 4.1 订单粒度基础表（统一口径：一单一行）
#     与 SQL 完全一致：
#       GMV = 商品价 + 运费（SUM 到订单）
#       延迟 = 实际送达 > 预计送达（订单级判定）
#       比率类指标的分母统一为「订单」，不再用商品明细行
# ============================================================
item_amt = order_items.groupby("order_id", as_index=False).agg(
    商品金额=("price", "sum"),
    运费金额=("freight_value", "sum"),
)
item_amt["订单总金额"] = item_amt["商品金额"] + item_amt["运费金额"]

order_base = (
    orders.merge(customers, on="customer_id", how="left")
          .merge(item_amt, on="order_id", how="left")
          .merge(reviews_per_order, on="order_id", how="left")
)
for c in ["商品金额", "运费金额", "订单总金额"]:
    order_base[c] = order_base[c].fillna(0.0)
order_base["配送天数"] = (
    order_base["order_delivered_customer_date"] - order_base["order_purchase_timestamp"]
).dt.days
order_base["是否延迟"] = (
    order_base["order_delivered_customer_date"] > order_base["order_estimated_delivery_date"]
)
print(f"==== 4.1 订单粒度基础表：{len(order_base)} 单 ====")


# ============================================================
# 6. RFM 用户分层（Monetary 含商品价 + 运费）
# ============================================================
max_date = order_wide["order_purchase_timestamp"].max()

rfm = order_wide.groupby("customer_unique_id").agg(
    Recency   = ("order_purchase_timestamp", lambda x: (max_date - x.max()).days),
    Frequency = ("order_id", "nunique"),
    Monetary  = ("订单总金额", "sum"),
).reset_index()

rfm["R_score"] = pd.qcut(rfm["Recency"], 5, labels=[5, 4, 3, 2, 1])
rfm["F_score"] = pd.qcut(rfm["Frequency"].rank(method="first"), 5,
                         labels=[1, 2, 3, 4, 5])
rfm["M_score"] = pd.qcut(rfm["Monetary"], 5, labels=[1, 2, 3, 4, 5])

def rfm_label(row):
    r, f, m = int(row["R_score"]), int(row["F_score"]), int(row["M_score"])
    if r >= 4 and f >= 4 and m >= 4: return "高价值客户"
    elif r >= 3 and f >= 3 and m >= 3: return "潜力客户"
    elif r <= 2 and f >= 3 and m >= 3: return "流失高价值"
    elif r >= 4 and f <= 2:           return "新客户"
    elif r <= 2 and f <= 2:           return "流失客户"
    else:                              return "一般客户"

rfm["客户分层"] = rfm.apply(rfm_label, axis=1)

print(f"\n==== 5. RFM 结果（用户数 {len(rfm)}）====\n{rfm['客户分层'].value_counts()}")


# ============================================================
# 7. 类目销售统计（订单粒度）
#    一单多品类时该订单在各品类下各计一次，与 SQL
#    「COUNT(DISTINCT order_id) + GROUP BY 品类」一致
# ============================================================
order_cat = order_wide[["order_id", "category_cn"]].drop_duplicates()
cat_base = order_cat.merge(
    order_base[["order_id", "订单总金额", "是否延迟"]], on="order_id", how="left"
)

category_stats = cat_base.groupby("category_cn").agg(
    订单数量     = ("order_id", "nunique"),
    销售总额     = ("订单总金额", "sum"),
    延迟订单数量 = ("是否延迟", "sum"),
).reset_index()
category_stats["延迟率"] = category_stats["延迟订单数量"] / category_stats["订单数量"]
category_stats = category_stats.sort_values("销售总额", ascending=False)

print(f"\n==== 6. 类目销售 TOP10 ====\n{category_stats.head(10).to_string(index=False)}")


# ============================================================
# 8. 评价维度分析
# ============================================================
print("\n" + "=" * 60)
print("==== 7. 评价维度分析 ====")
print("=" * 60)

# 统一口径：评价按订单统计（一单一条评价），不再按商品明细行重复计算
order_review = order_base.dropna(subset=["review_score"]).copy()
order_review["是否差评"] = order_review["review_score"].isin([1, 2])

# 整体指标（分母 = 有评价订单 / 全部订单，与 SQL 对齐）
print(f"\n整体评价：有评价订单 {len(order_review)} 单 | "
      f"平均评分 {order_review['review_score'].mean():.4f} | "
      f"差评率 {order_review['是否差评'].mean():.4%}")
print(f"整体履约：订单 {len(order_base)} 单 | "
      f"平均配送 {order_base['配送天数'].mean():.4f} 天 | "
      f"延迟率 {order_base['是否延迟'].mean():.4%}")
slow = order_base[order_base["配送天数"] > 30].dropna(subset=["review_score"])
if len(slow):
    print(f"配送>30天：{len(slow)} 单 | 差评率 {slow['review_score'].le(2).mean():.4%}")

# 各品类差评率（订单粒度）
order_review_cat = order_review.merge(order_cat, on="order_id", how="left")
review_by_cat = order_review_cat.groupby("category_cn").agg(
    有评价订单数=("order_id", "nunique"),
    平均评分=("review_score", "mean"),
    差评率=("是否差评", "mean"),
).reset_index().sort_values("差评率", ascending=False)

print(f"\n品类差评率 TOP10：")
print(review_by_cat[["category_cn", "有评价订单数", "平均评分", "差评率"]].head(10).to_string(index=False))

# 配送时长 vs 评分（订单粒度）
order_review["配送时间段"] = pd.cut(
    order_review["配送天数"],
    bins=[-1, 3, 7, 14, 30, 500],
    labels=["0-3天", "4-7天", "8-14天", "15-30天", "30天以上"],
)
logistics_review = order_review.groupby("配送时间段", observed=False).agg(
    订单数=("order_id", "nunique"),
    平均评分=("review_score", "mean"),
    差评率=("是否差评", "mean"),
).reset_index()

print(f"\n配送时长 vs 评分：")
print(logistics_review.to_string(index=False))


# ============================================================
# 9. 月度趋势
# ============================================================
print("\n" + "=" * 60)
print("==== 8. 月度趋势 ====")
print("=" * 60)

order_wide["下单月份"] = order_wide["order_purchase_timestamp"].dt.to_period("M")
monthly_stats = order_wide.groupby("下单月份").agg(
    订单数=("order_id", "nunique"),
    GMV=("订单总金额", "sum"),
).reset_index()
monthly_stats["客单价"] = monthly_stats["GMV"] / monthly_stats["订单数"]
monthly_stats["月份标签"] = monthly_stats["下单月份"].astype(str)

print(monthly_stats[["月份标签", "订单数", "GMV", "客单价"]].to_string(index=False))


# ============================================================
# 10. 导出 CSV（给 PowerBI 用）
# ============================================================
order_wide.to_csv(os.path.join(OUT_CSV, "clean_wide.csv"), index=False, encoding="utf-8-sig")
rfm.to_csv(os.path.join(OUT_CSV, "rfm_result.csv"), index=False, encoding="utf-8-sig")
category_stats.to_csv(os.path.join(OUT_CSV, "category_sales_stats.csv"), index=False, encoding="utf-8-sig")
review_by_cat.to_csv(os.path.join(OUT_CSV, "category_review_stats.csv"), index=False, encoding="utf-8-sig")

# 订单粒度宽表：给 Agent 自然语言问数用，一单一行，避免明细行重复计算
order_base_out = order_base.copy()
order_base_out["下单月份"] = order_base_out["order_purchase_timestamp"].dt.strftime("%Y-%m")
order_base_out[[
    "order_id", "customer_unique_id", "customer_state", "order_purchase_timestamp", "下单月份",
    "商品金额", "运费金额", "订单总金额", "review_score", "配送天数", "是否延迟",
]].to_csv(os.path.join(OUT_CSV, "orders_base.csv"), index=False, encoding="utf-8-sig")


# ============================================================
# 11. 导出 PNG 图表
# ============================================================

# 图 1：TOP10 类目销售额
top10 = category_stats.head(10)
plt.figure(figsize=(14, 6))
plt.bar(top10["category_cn"], top10["销售总额"] / 1e6, color="#4472C4")
plt.xticks(rotation=30, ha="right")
plt.title("销售额 TOP10 商品类目")
plt.ylabel("销售总额（百万雷亚尔）")
plt.tight_layout()
plt.savefig(os.path.join(OUT_PNG, "top10_category_sales.png"), dpi=300, bbox_inches="tight")
plt.close()

# 图 2：RFM 用户分层饼图
plt.figure(figsize=(7, 7))
rfm_pie = rfm["客户分层"].value_counts()
plt.pie(rfm_pie.values, labels=rfm_pie.index, autopct="%.1f%%",
        startangle=90, colors=plt.cm.Set3.colors[:len(rfm_pie)])
plt.title("RFM 用户分层分布")
plt.tight_layout()
plt.savefig(os.path.join(OUT_PNG, "rfm_user_pie.png"), dpi=300, bbox_inches="tight")
plt.close()

# 图 3：RFM 客户分层柱状图
plt.figure(figsize=(10, 5))
layer_count = rfm["客户分层"].value_counts()
plt.bar(layer_count.index, layer_count.values, color="#2E86AB")
plt.xticks(rotation=30, ha="right")
plt.title("RFM 客户分层分布")
plt.ylabel("客户数量")
plt.tight_layout()
plt.savefig(os.path.join(OUT_PNG, "rfm_segment_bar.png"), dpi=300, bbox_inches="tight")
plt.close()

# 图 4：配送天数分布
plt.figure(figsize=(10, 5))
valid_days = order_base[(order_base["配送天数"] >= 0) & (order_base["配送天数"] <= 30)]["配送天数"]
plt.hist(valid_days, bins=20, color="#4472C4", alpha=0.7)
plt.title("订单实际配送天数分布（0-30天）")
plt.xlabel("配送天数")
plt.ylabel("订单数量")
plt.tight_layout()
plt.savefig(os.path.join(OUT_PNG, "delivery_days_hist.png"), dpi=300, bbox_inches="tight")
plt.close()

# 图 5：差评率 TOP10 品类
plt.figure(figsize=(12, 6))
top10_bad = review_by_cat.head(10).iloc[::-1]
plt.barh(top10_bad["category_cn"], top10_bad["差评率"] * 100, color="#C0504D")
plt.xlabel("差评率 (%)")
plt.title("差评率最高的 TOP10 品类")
plt.tight_layout()
plt.savefig(os.path.join(OUT_PNG, "category_bad_review_top10.png"), dpi=300, bbox_inches="tight")
plt.close()

# 图 6：配送时长 vs 平均评分
plt.figure(figsize=(10, 5))
x = logistics_review["配送时间段"].astype(str)
plt.plot(x, logistics_review["平均评分"], marker="o", linewidth=2, color="#4472C4")
for i, v in enumerate(logistics_review["平均评分"]):
    plt.annotate(f"{v:.2f}", (x.iloc[i], v),
                 textcoords="offset points", xytext=(0, 10), ha="center")
plt.title("配送时长与用户评价的关系")
plt.xlabel("配送时长区间")
plt.ylabel("平均评分")
plt.ylim(3.5, 5.0)
plt.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(OUT_PNG, "delivery_vs_review.png"), dpi=300, bbox_inches="tight")
plt.close()

# 图 7：月度 GMV + 订单量
fig, ax1 = plt.subplots(figsize=(14, 6))
ax1.plot(monthly_stats["月份标签"], monthly_stats["GMV"] / 1e6,
         marker="o", color="#4472C4", linewidth=2, label="GMV（百万雷亚尔）")
ax1.set_xlabel("月份")
ax1.set_ylabel("GMV（百万雷亚尔）", color="#4472C4")
ax1.tick_params(axis="y", labelcolor="#4472C4")
ax1.tick_params(axis="x", rotation=45)

ax2 = ax1.twinx()
ax2.bar(monthly_stats["月份标签"], monthly_stats["订单数"],
        alpha=0.3, color="#ED7D31", label="订单数")
ax2.set_ylabel("订单数", color="#ED7D31")
ax2.tick_params(axis="y", labelcolor="#ED7D31")

peak_idx = monthly_stats["GMV"].idxmax()
peak_row = monthly_stats.iloc[peak_idx]
ax1.annotate(
    f"峰值 {peak_row['月份标签']}\nGMV {peak_row['GMV']/1e6:.1f}M",
    xy=(peak_idx, peak_row["GMV"] / 1e6),
    xytext=(peak_idx - 2, peak_row["GMV"] / 1e6 + 2),
    arrowprops=dict(arrowstyle="->", color="black"),
    ha="center", fontsize=9,
)
plt.title("月度 GMV 与订单量趋势")
fig.legend(loc="upper left", bbox_to_anchor=(0.12, 0.98))
plt.tight_layout()
plt.savefig(os.path.join(OUT_PNG, "monthly_sales_trend.png"), dpi=300, bbox_inches="tight")
plt.close()


print("\n" + "=" * 60)
print("✅ 分析完成！")
print(f"  CSV 输出 → {OUT_CSV}")
print(f"  PNG 输出 → {OUT_PNG}")
print("=" * 60)
