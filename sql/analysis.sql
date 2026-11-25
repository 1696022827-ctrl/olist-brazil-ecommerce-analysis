-- =============================================================
-- Olist 巴西电商 —— SQL 取数层
-- 依赖 MySQL 8.0+（使用 CTE 与窗口函数）
-- -------------------------------------------------------------
-- 口径说明（与 scripts/analysis.py 的清洗规则保持一致）：
--   1) 有效订单：order_status = 'delivered'，交付时间/预计交付时间非空，
--      且 交付时间 >= 下单时间
--   2) 金额：商品金额 = SUM(price)，运费 = SUM(freight_value)，
--      订单总金额 = 商品金额 + 运费（Python 侧同名指标口径一致）
--   3) 订单数一律 COUNT(DISTINCT order_id)：order_items 一单多行
--   4) 延迟：order_delivered_customer_date > order_estimated_delivery_date
--   5) 评价：一个订单可能有多条评价，取 MIN(review_score) 近似「首条评价」
--   6) 月度趋势剔除 2016 年样本极少月份，区间 2017-01 ~ 2018-08
-- 涉及表：olist_orders / olist_order_items / olist_products /
--        olist_cat_trans（品类翻译） / olist_customers /
--        olist_reviews（订单评价）
-- =============================================================


-- =============================================================
-- 1. 销售维度：按月统计订单量、销售额、客单价
-- =============================================================
SELECT
    DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS 月份,
    COUNT(DISTINCT o.order_id) AS 订单总数,
    ROUND(SUM(oi.price), 2) AS 商品销售额,
    ROUND(SUM(oi.freight_value), 2) AS 运费收入,
    ROUND(SUM(oi.price + oi.freight_value), 2) AS 订单总金额,
    ROUND(SUM(oi.price + oi.freight_value) / COUNT(DISTINCT o.order_id), 2) AS 客单价
FROM olist_orders o
-- 用 LEFT JOIN 保留「无商品行」的订单，订单数与 Python 侧自动对齐
LEFT JOIN olist_order_items oi
       ON oi.order_id = o.order_id
      AND oi.price > 0
      AND oi.freight_value >= 0
WHERE o.order_status = 'delivered'
  AND o.order_purchase_timestamp >= '2017-01-01'
  AND o.order_purchase_timestamp <  '2018-09-01'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
  AND o.order_delivered_customer_date >= o.order_purchase_timestamp
GROUP BY DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m')
ORDER BY 月份;


-- =============================================================
-- 2. 商品维度 + 履约维度：各品类销售规模与延迟情况
--    注：平均配送天数按明细行加权，与 Python 逐行 agg 的口径一致
-- =============================================================
SELECT
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS 品类,
    COUNT(DISTINCT o.order_id) AS 订单数量,
    ROUND(SUM(oi.price), 2) AS 商品销售额,
    ROUND(SUM(oi.freight_value), 2) AS 运费收入,
    ROUND(SUM(oi.price + oi.freight_value), 2) AS 订单总金额,
    COUNT(DISTINCT CASE
        WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
        THEN o.order_id END) AS 延迟订单数,
    ROUND(COUNT(DISTINCT CASE
        WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
        THEN o.order_id END) / COUNT(DISTINCT o.order_id), 4) AS 延迟率,
    ROUND(AVG(DATEDIFF(o.order_delivered_customer_date, o.order_purchase_timestamp)), 1) AS 平均配送天数
FROM olist_orders o
JOIN olist_order_items oi ON oi.order_id = o.order_id
LEFT JOIN olist_products p ON p.product_id = oi.product_id
-- 按类目去重后再关联，避免翻译表重复导入导致金额翻倍
LEFT JOIN (SELECT DISTINCT product_category_name, product_category_name_english
           FROM olist_cat_trans) t
       ON t.product_category_name = p.product_category_name
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
  AND o.order_delivered_customer_date >= o.order_purchase_timestamp
  AND oi.price > 0
  AND oi.freight_value >= 0
GROUP BY 1
HAVING 订单数量 >= 10
ORDER BY 订单总金额 DESC;


-- =============================================================
-- 3. 用户维度：按州统计订单、GMV、客单价与履约表现
--    先用 order_base 把数据降到「订单粒度」，避免一单多行导致均值失真
-- =============================================================
WITH item_amount AS (
    SELECT order_id,
           SUM(price) AS 商品金额,
           SUM(freight_value) AS 运费金额,
           SUM(price + freight_value) AS 订单总金额
    FROM olist_order_items
    WHERE price > 0 AND freight_value >= 0
    GROUP BY order_id
),
order_base AS (
    SELECT o.order_id,
           o.order_purchase_timestamp,
           o.order_delivered_customer_date,
           o.order_estimated_delivery_date,
           c.customer_state,
           COALESCE(a.商品金额, 0) AS 商品金额,
           COALESCE(a.订单总金额, 0) AS 订单总金额
    FROM olist_orders o
    JOIN olist_customers c ON c.customer_id = o.customer_id
    LEFT JOIN item_amount a ON a.order_id = o.order_id
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_estimated_delivery_date IS NOT NULL
      AND o.order_delivered_customer_date >= o.order_purchase_timestamp
)
SELECT
    customer_state AS 州,
    COUNT(*) AS 订单数,
    ROUND(SUM(商品金额), 2) AS GMV,
    ROUND(SUM(订单总金额) / COUNT(*), 2) AS 客单价,
    ROUND(AVG(DATEDIFF(order_delivered_customer_date, order_purchase_timestamp)), 1) AS 平均配送天数,
    ROUND(SUM(CASE WHEN order_delivered_customer_date > order_estimated_delivery_date
                   THEN 1 ELSE 0 END) / COUNT(*), 4) AS 延迟率
FROM order_base
GROUP BY customer_state
ORDER BY GMV DESC;


-- =============================================================
-- 4. 履约 × 评价：配送时长分段对评分与差评率的影响
-- =============================================================
WITH review_per_order AS (
    SELECT order_id, MIN(review_score) AS review_score
    FROM olist_reviews
    GROUP BY order_id
),
order_base AS (
    SELECT o.order_id,
           DATEDIFF(o.order_delivered_customer_date, o.order_purchase_timestamp) AS 配送天数
    FROM olist_orders o
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_estimated_delivery_date IS NOT NULL
      AND o.order_delivered_customer_date >= o.order_purchase_timestamp
)
SELECT
    CASE
        WHEN ob.配送天数 <= 3  THEN '0-3天'
        WHEN ob.配送天数 <= 7  THEN '4-7天'
        WHEN ob.配送天数 <= 14 THEN '8-14天'
        WHEN ob.配送天数 <= 30 THEN '15-30天'
        ELSE '30天以上'
    END AS 配送时长分段,
    COUNT(DISTINCT ob.order_id) AS 订单数,
    ROUND(AVG(r.review_score), 2) AS 平均评分,
    ROUND(SUM(CASE WHEN r.review_score IN (1, 2) THEN 1 ELSE 0 END) / COUNT(*), 4) AS 差评率
FROM order_base ob
JOIN review_per_order r ON r.order_id = ob.order_id
GROUP BY 1
ORDER BY MIN(ob.配送天数);


-- =============================================================
-- 5. 评价维度：各品类评分与差评率
--    注：平均评分按明细行加权；样本量 < 30 的品类不参与排名
-- =============================================================
WITH review_per_order AS (
    SELECT order_id, MIN(review_score) AS review_score
    FROM olist_reviews
    GROUP BY order_id
)
SELECT
    COALESCE(t.product_category_name_english, p.product_category_name, 'unknown') AS 品类,
    COUNT(DISTINCT o.order_id) AS 有评价订单数,
    ROUND(AVG(r.review_score), 2) AS 平均评分,
    COUNT(DISTINCT CASE WHEN r.review_score IN (1, 2) THEN o.order_id END) AS 差评订单数,
    ROUND(COUNT(DISTINCT CASE WHEN r.review_score IN (1, 2) THEN o.order_id END)
          / COUNT(DISTINCT o.order_id), 4) AS 差评率
FROM olist_orders o
JOIN olist_order_items oi ON oi.order_id = o.order_id
JOIN review_per_order r ON r.order_id = o.order_id
LEFT JOIN olist_products p ON p.product_id = oi.product_id
-- 按类目去重后再关联，避免翻译表重复导入导致金额翻倍
LEFT JOIN (SELECT DISTINCT product_category_name, product_category_name_english
           FROM olist_cat_trans) t
       ON t.product_category_name = p.product_category_name
WHERE o.order_status = 'delivered'
  AND o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
  AND o.order_delivered_customer_date >= o.order_purchase_timestamp
  AND oi.price > 0
  AND oi.freight_value >= 0
GROUP BY 1
HAVING 有评价订单数 >= 30
ORDER BY 差评率 DESC;


-- =============================================================
-- 6. 用户维度：RFM 原始指标与分层（对应 Python 的 rfm_result）
--    R：距最后一次下单天数（越大越差）→ 分位分数取反
--    F：下单次数；M：累计消费金额
--    分层规则与 scripts/analysis.py 的 rfm_label 完全一致
-- =============================================================
WITH item_amount AS (
    SELECT order_id, SUM(price + freight_value) AS 订单总金额
    FROM olist_order_items
    WHERE price > 0 AND freight_value >= 0
    GROUP BY order_id
),
valid_orders AS (
    SELECT o.order_id, o.customer_id, o.order_purchase_timestamp
    FROM olist_orders o
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_estimated_delivery_date IS NOT NULL
      AND o.order_delivered_customer_date >= o.order_purchase_timestamp
),
user_base AS (
    SELECT c.customer_unique_id,
           v.order_id,
           v.order_purchase_timestamp,
           COALESCE(a.订单总金额, 0) AS 订单总金额
    FROM valid_orders v
    JOIN olist_customers c ON c.customer_id = v.customer_id
    LEFT JOIN item_amount a ON a.order_id = v.order_id
),
rfm_raw AS (
    SELECT customer_unique_id,
           DATEDIFF((SELECT MAX(order_purchase_timestamp) FROM valid_orders),
                    MAX(order_purchase_timestamp)) AS Recency,
           COUNT(DISTINCT order_id) AS Frequency,
           ROUND(SUM(订单总金额), 2) AS Monetary
    FROM user_base
    GROUP BY customer_unique_id
),
rfm_score AS (
    -- 必须带上 customer_unique_id 作为并列时的次级排序键：
    -- 93% 的用户 Frequency = 1，只按 Frequency 排序时各引擎的并列处理不同，
    -- 分层结果会随引擎/版本漂移；固定次级键后结果可复现。
    -- 该排序与 Python 的 qcut(rank(method='first')) 顺序一致，便于两边对账。
    SELECT r.*,
           6 - NTILE(5) OVER (ORDER BY Recency ASC, customer_unique_id ASC) AS R_score,
           NTILE(5) OVER (ORDER BY Frequency ASC, customer_unique_id ASC) AS F_score,
           NTILE(5) OVER (ORDER BY Monetary ASC, customer_unique_id ASC) AS M_score
    FROM rfm_raw r
)
SELECT
    customer_unique_id,
    Recency,
    Frequency,
    Monetary,
    R_score,
    F_score,
    M_score,
    CASE
        WHEN R_score >= 4 AND F_score >= 4 AND M_score >= 4 THEN '高价值客户'
        WHEN R_score >= 3 AND F_score >= 3 AND M_score >= 3 THEN '潜力客户'
        WHEN R_score <= 2 AND F_score >= 3 AND M_score >= 3 THEN '流失高价值'
        WHEN R_score >= 4 AND F_score <= 2 THEN '新客户'
        WHEN R_score <= 2 AND F_score <= 2 THEN '流失客户'
        ELSE '一般客户'
    END AS 客户分层
FROM rfm_score
ORDER BY Monetary DESC;


-- =============================================================
-- 7. 月度环比：GMV 环比增速 + 近 3 个月移动平均
--    面试考点：LAG 窗口函数、除零保护、移动窗口
-- =============================================================
WITH monthly AS (
    SELECT DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS 月份,
           COUNT(DISTINCT o.order_id) AS 订单数,
           SUM(oi.price + oi.freight_value) AS 订单总金额
    FROM olist_orders o
    LEFT JOIN olist_order_items oi
           ON oi.order_id = o.order_id AND oi.price > 0 AND oi.freight_value >= 0
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_delivered_customer_date >= o.order_purchase_timestamp
      AND o.order_purchase_timestamp >= '2017-01-01'
    GROUP BY 1
)
SELECT 月份,
       订单数,
       ROUND(订单总金额, 2) AS 订单总金额,
       ROUND(订单总金额 - LAG(订单总金额) OVER (ORDER BY 月份), 2) AS 环比增量,
       ROUND((订单总金额 - LAG(订单总金额) OVER (ORDER BY 月份))
             / NULLIF(LAG(订单总金额) OVER (ORDER BY 月份), 0), 4) AS 环比增速,
       ROUND(AVG(订单总金额) OVER (ORDER BY 月份 ROWS BETWEEN 2 PRECEDING AND CURRENT ROW), 2) AS 近3月均值
FROM monthly
ORDER BY 月份;


-- =============================================================
-- 8. 新老客拆分：按用户首单月份判断当月是新客还是老客
--    面试考点：窗口函数取首单时间、按首单月份分组
-- =============================================================
WITH valid_orders AS (
    SELECT o.order_id, o.customer_id, o.order_purchase_timestamp
    FROM olist_orders o
    WHERE o.order_status = 'delivered'
      AND o.order_delivered_customer_date IS NOT NULL
      AND o.order_delivered_customer_date >= o.order_purchase_timestamp
),
user_orders AS (
    SELECT v.order_id,
           c.customer_unique_id,
           DATE_FORMAT(v.order_purchase_timestamp, '%Y-%m') AS 月份,
           MIN(DATE_FORMAT(v.order_purchase_timestamp, '%Y-%m'))
               OVER (PARTITION BY c.customer_unique_id) AS 首单月份
    FROM valid_orders v
    JOIN olist_customers c ON c.customer_id = v.customer_id
)
SELECT 月份,
       CASE WHEN 月份 = 首单月份 THEN '新客' ELSE '老客' END AS 客户类型,
       COUNT(DISTINCT order_id) AS 订单数,
       COUNT(DISTINCT customer_unique_id) AS 客户数
FROM user_orders
GROUP BY 月份, 客户类型
ORDER BY 月份, 客户类型;


-- =============================================================
-- 9. 复购分析：复购用户占比 + 复购用户平均下单次数与间隔
--    面试考点：HAVING 过滤、DATEDIFF 计算复购间隔
-- =============================================================
WITH user_order AS (
    SELECT c.customer_unique_id,
           o.order_id,
           o.order_purchase_timestamp,
           ROW_NUMBER() OVER (PARTITION BY c.customer_unique_id
                              ORDER BY o.order_purchase_timestamp) AS 第几次下单
    FROM olist_orders o
    JOIN olist_customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
)
SELECT COUNT(*) AS 用户总数,
       SUM(CASE WHEN 下单次数 >= 2 THEN 1 ELSE 0 END) AS 复购用户数,
       ROUND(SUM(CASE WHEN 下单次数 >= 2 THEN 1 ELSE 0 END) / COUNT(*), 4) AS 复购率,
       ROUND(AVG(CASE WHEN 下单次数 >= 2 THEN 下单次数 END), 2) AS 复购用户平均下单次数
FROM (
    SELECT customer_unique_id, COUNT(*) AS 下单次数 FROM user_order GROUP BY 1
) t;

-- 复购用户的首单 → 第二单平均间隔天数（衡量回购周期）
WITH ranked AS (
    SELECT c.customer_unique_id,
           o.order_purchase_timestamp,
           ROW_NUMBER() OVER (PARTITION BY c.customer_unique_id
                              ORDER BY o.order_purchase_timestamp) AS rn
    FROM olist_orders o
    JOIN olist_customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
)
SELECT ROUND(AVG(DATEDIFF(b.order_purchase_timestamp, a.order_purchase_timestamp)), 1) AS 首单到二单平均间隔天数
FROM ranked a
JOIN ranked b ON b.customer_unique_id = a.customer_unique_id AND b.rn = 2
WHERE a.rn = 1;


-- =============================================================
-- 10. 品类内 TOP3 商品：每个品类销售额最高的 3 个商品
--     面试考点：ROW_NUMBER() OVER (PARTITION BY ...) 取组内 TOPN
-- =============================================================
WITH product_sales AS (
    SELECT p.product_category_name,
           oi.product_id,
           SUM(oi.price) AS 销售额,
           COUNT(DISTINCT oi.order_id) AS 订单数
    FROM olist_order_items oi
    JOIN olist_orders o ON o.order_id = oi.order_id AND o.order_status = 'delivered'
    LEFT JOIN olist_products p ON p.product_id = oi.product_id
    WHERE oi.price > 0
    GROUP BY 1, 2
),
ranked AS (
    SELECT product_category_name, product_id, 销售额, 订单数,
           ROW_NUMBER() OVER (PARTITION BY product_category_name ORDER BY 销售额 DESC) AS 排名
    FROM product_sales
)
SELECT product_category_name AS 品类, 排名, product_id AS 商品ID,
       ROUND(销售额, 2) AS 销售额, 订单数
FROM ranked
WHERE 排名 <= 3
ORDER BY 品类, 排名;


-- =============================================================
-- 11. 州维度帕累托：GMV 排名 + 累计占比（找出贡献 80% GMV 的州）
--     面试考点：SUM() OVER (ORDER BY ...) 累计求和
-- =============================================================
WITH state_gmv AS (
    SELECT c.customer_state AS 州,
           SUM(oi.price + oi.freight_value) AS GMV
    FROM olist_orders o
    JOIN olist_order_items oi ON oi.order_id = o.order_id AND oi.price > 0
    JOIN olist_customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
    GROUP BY 1
)
SELECT 州,
       ROUND(GMV, 2) AS GMV,
       ROUND(GMV / SUM(GMV) OVER (), 4) AS 单州占比,
       ROUND(SUM(GMV) OVER (ORDER BY GMV DESC) / SUM(GMV) OVER (), 4) AS 累计占比,
       ROW_NUMBER() OVER (ORDER BY GMV DESC) AS 排名
FROM state_gmv
ORDER BY GMV DESC;


-- =============================================================
-- 12. 支付方式：各支付方式的订单量、金额占比与分期情况
--     涉及表：olist_payments（order_id, payment_type, payment_installments, payment_value）
-- =============================================================
SELECT payment_type AS 支付方式,
       COUNT(DISTINCT order_id) AS 订单数,
       ROUND(SUM(payment_value), 2) AS 支付总额,
       ROUND(AVG(payment_value), 2) AS 笔均金额,
       ROUND(AVG(payment_installments), 1) AS 平均分期数,
       ROUND(SUM(CASE WHEN payment_installments > 1 THEN 1 ELSE 0 END) / COUNT(*), 4) AS 分期订单占比
FROM olist_payments
GROUP BY payment_type
ORDER BY 支付总额 DESC;


-- =============================================================
-- 13. 卖家维度：GMV TOP10 卖家的规模与履约质量（样本 >= 30 单）
--     涉及表：olist_sellers（seller_id, seller_state）
-- =============================================================
SELECT oi.seller_id AS 卖家ID,
       s.seller_state AS 卖家所在州,
       COUNT(DISTINCT o.order_id) AS 订单数,
       ROUND(SUM(oi.price + oi.freight_value), 2) AS GMV,
       ROUND(SUM(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date
                      THEN 1 ELSE 0 END) / COUNT(DISTINCT o.order_id), 4) AS 延迟率,
       ROUND(AVG(r.review_score), 2) AS 平均评分
FROM olist_order_items oi
JOIN olist_orders o ON o.order_id = oi.order_id AND o.order_status = 'delivered'
LEFT JOIN olist_sellers s ON s.seller_id = oi.seller_id
LEFT JOIN (SELECT order_id, MIN(review_score) AS review_score
           FROM olist_reviews GROUP BY order_id) r ON r.order_id = o.order_id
WHERE o.order_delivered_customer_date IS NOT NULL
  AND o.order_estimated_delivery_date IS NOT NULL
GROUP BY 1, 2
HAVING 订单数 >= 30
ORDER BY GMV DESC
LIMIT 10;


-- =============================================================
-- 14. 品类月度环比：定位「连续两个月下滑」的品类（预警用）
--     面试考点：多层 CTE + LAG 分组内比较
-- =============================================================
WITH cat_month AS (
    SELECT p.product_category_name AS 品类,
           DATE_FORMAT(o.order_purchase_timestamp, '%Y-%m') AS 月份,
           SUM(oi.price + oi.freight_value) AS GMV
    FROM olist_orders o
    JOIN olist_order_items oi ON oi.order_id = o.order_id AND oi.price > 0
    LEFT JOIN olist_products p ON p.product_id = oi.product_id
    WHERE o.order_status = 'delivered'
      AND o.order_purchase_timestamp >= '2017-01-01'
      AND o.order_purchase_timestamp <  '2018-09-01'
    GROUP BY 1, 2
),
with_prev AS (
    SELECT 品类, 月份, GMV,
           LAG(GMV) OVER (PARTITION BY 品类 ORDER BY 月份) AS 上月GMV,
           LAG(GMV, 2) OVER (PARTITION BY 品类 ORDER BY 月份) AS 前两月GMV
    FROM cat_month
)
SELECT 品类, 月份,
       ROUND(GMV, 2) AS GMV,
       ROUND(GMV / NULLIF(上月GMV, 0) - 1, 4) AS 环比增速,
       ROUND(上月GMV / NULLIF(前两月GMV, 0) - 1, 4) AS 上月环比增速
FROM with_prev
WHERE 上月GMV IS NOT NULL AND 前两月GMV IS NOT NULL
  AND GMV < 上月GMV AND 上月GMV < 前两月GMV
ORDER BY 月份 DESC, GMV DESC;


-- =============================================================
-- 15. 首单月留存：按首单月份分群，统计 +30 / +60 天内是否再次下单
--     面试考点：cohort 分析、条件聚合
-- =============================================================
WITH valid AS (
    SELECT c.customer_unique_id, o.order_purchase_timestamp
    FROM olist_orders o
    JOIN olist_customers c ON c.customer_id = o.customer_id
    WHERE o.order_status = 'delivered'
),
first_order AS (
    SELECT customer_unique_id, MIN(order_purchase_timestamp) AS 首单时间
    FROM valid
    GROUP BY 1
),
retention AS (
    SELECT f.customer_unique_id,
           DATE_FORMAT(f.首单时间, '%Y-%m') AS 首单月份,
           MAX(CASE WHEN DATEDIFF(v.order_purchase_timestamp, f.首单时间) BETWEEN 1 AND 30
                    THEN 1 ELSE 0 END) AS 是否30天内复购,
           MAX(CASE WHEN DATEDIFF(v.order_purchase_timestamp, f.首单时间) BETWEEN 1 AND 60
                    THEN 1 ELSE 0 END) AS 是否60天内复购
    FROM first_order f
    JOIN valid v ON v.customer_unique_id = f.customer_unique_id
    GROUP BY 1, 2
)
SELECT 首单月份,
       COUNT(*) AS 新客数,
       ROUND(AVG(是否30天内复购), 4) AS 次月留存率,
       ROUND(AVG(是否60天内复购), 4) AS 60天留存率
FROM retention
GROUP BY 首单月份
ORDER BY 首单月份;
