# PowerBI 看板搭建 —— 新手 step-by-step 教程

> 每一步都写清楚"点哪里 → 选什么 → 预期结果是什么"。
> 如果某一步卡壳了，看每节最后的 ✅ 检查点。

---

## 🧰 准备工作（先一次性做完）

### 第 0 步：下载安装 PowerBI Desktop

- 微软官网下载（免费）：https://www.microsoft.com/zh-cn/power-platform/products/power-bi/desktop
- 安装完打开，会看到一个"开始"页面，点右上角 **×** 关掉就行

---

## 📥 第一阶段：导入数据（只做一次）

### 第 1 步：导入 4 个 CSV 文件

1. 打开 PowerBI Desktop
2. 点左侧工具栏 **"获取数据"** 按钮（↑ 箭头图标，或者顶部菜单 → 开始 → 获取数据）
3. 弹出窗口里选 **"文本/CSV"** → 点 **连接**
4. 找到文件夹 `E:\olist-brazil-ecommerce-analysis\output\csv\`，**按住 Ctrl 键，同时点选 4 个文件**：
   - `clean_wide.csv`
   - `rfm_result.csv`
   - `category_sales_stats.csv`
   - `category_review_stats.csv`
5. 点 **打开**
6. 会弹出一个"文件预览"窗口，右上角有个 **"组合并加载"** 按钮 → 点它
7. 等待几秒钟加载完成（左下角会转圈圈）

✅ **检查点**：左侧"字段"面板（就是一列小方块图标那里）应该能看到 4 张表：clean_wide、rfm_result、category_sales_stats、category_review_stats

---

### 第 2 步：建立表关系（非常重要！）

1. 点左侧 **"模型"** 图标（黄色小方块在左边那个）
2. 你会看到 4 个表的方框，像这样摆着
3. 在 `clean_wide` 方框里找到 **customer_unique_id** 这一列，**按住鼠标左键拖出来**，拖到 `rfm_result` 方框里的 **customer_unique_id** 上，松开
4. 会弹出一个"编辑关系"窗口，确认：
   - 基数：**多对一** ← 如果不是，点下拉菜单改成这个
   - 交叉筛选方向：**双向** ← 如果不是，点下拉菜单改成这个
   - 点 **确定**

✅ **检查点**：两个表之间出现一条连线，箭头从 clean_wide 指向 rfm_result

---

### 第 3 步：把时间列标记为日期表（日期切片器才能用）

1. 回到 **"数据"** 视图（左侧工具栏，表格图标）
2. 左边字段面板里点 **clean_wide** 左边的小三角 → 展开列
3. 找到 **order_purchase_timestamp**，**右键点它**
4. 菜单里选 **"标记为日期"** → 子菜单选 **"标记为日期表"**
5. 弹出确认窗口 → 点 **确定**

---

## 📐 第二阶段：创建 DAX 度量值（14 个，逐个新建）

> 度量值 = 一个自定义公式，算出来的值可以用在任何图表里。
> 所有 DAX 代码在同目录下 `scripts/powerbi_dax.txt` 里，复制粘贴即可。

### 通用操作：怎么新建一个度量值

1. 顶部工具栏 **"建模"** 标签 → 点 **"新建度量值"** 按钮
2. 会弹出一个公式栏，已经帮你写了 `Measure = `
3. **把我的公式里的 `总销售额` 换成你想要的名字**（其实已经写好了），然后复制粘贴等号后面的代码
4. 按 **Enter** 键确认

### 现在逐个创建（按顺序）

#### 度量值 1：总销售额

复制这段代码：
```dax
总销售额 = SUM(clean_wide[订单总金额])
```
粘贴进去，回车。✅ 创建完字段面板的 clean_wide 表下面会出现"总销售额"

#### 度量值 2：订单总数

```dax
订单总数 = DISTINCTCOUNT(clean_wide[order_id])
```

#### 度量值 3：用户数

```dax
用户数 = DISTINCTCOUNT(clean_wide[customer_unique_id])
```

#### 度量值 4：延迟订单数量

```dax
延迟订单数量 = CALCULATE(DISTINCTCOUNT(clean_wide[order_id]), clean_wide[是否延迟] = "是")
```

#### 度量值 5：延迟订单占比（记得设百分比格式）

```dax
延迟订单占比 = DIVIDE([延迟订单数量], [订单总数], 0)
```
创建完之后：字段面板里点一下这个度量值 → 顶部工具栏"格式"区域 → 点 **"%"** 按钮 → 设为百分比。

#### 度量值 6：平均配送时长

```dax
平均配送时长 = AVERAGEX(VALUES(clean_wide[order_id]), CALCULATE(MAX(clean_wide[实际配送天数])))
```

> ⚠️ 为什么不用 `AVERAGE`？`clean_wide` 是**商品明细表**，一单多件会重复参与平均，算出来是 12.01；按订单算才是 **12.09**。
> `AVERAGEX(VALUES(order_id), ...)` 的意思是「先按订单取一次值，再对订单求平均」，和 Python / SQL 口径一致（详见 `docs/指标口径表.md`）。

#### 度量值 7-14：剩余的全部复制粘贴

```dax
月均销售额 = DIVIDE([总销售额], DISTINCTCOUNT(clean_wide[下单月份]), 0)

类目平均订单金额 = DIVIDE([总销售额], [订单总数], 0)

RFM用户数 = DISTINCTCOUNT(rfm_result[customer_unique_id])

各层用户平均消费 = AVERAGE(rfm_result[Monetary])

RFM分层占比 = DIVIDE([RFM用户数], CALCULATE([RFM用户数], ALL(rfm_result[客户分层])), 0)

类目平均配送时长 = AVERAGEX(VALUES(clean_wide[order_id]), CALCULATE(MAX(clean_wide[实际配送天数])))

类目延迟率 = DIVIDE(CALCULATE(DISTINCTCOUNT(clean_wide[order_id]), clean_wide[是否延迟] = "是"), [订单总数], 0)

平均评分 = AVERAGEX(VALUES(clean_wide[order_id]), CALCULATE(MAX(clean_wide[review_score])))

差评订单数 = CALCULATE(DISTINCTCOUNT(clean_wide[order_id]), clean_wide[review_score] IN {1, 2})

差评率 = DIVIDE(CALCULATE(DISTINCTCOUNT(clean_wide[order_id]), clean_wide[review_score] IN {1, 2}), CALCULATE(DISTINCTCOUNT(clean_wide[order_id]), NOT ISBLANK(clean_wide[review_score])), 0)
```

✅ **检查点**：字段面板里应该能看到 clean_wide 下面有 14 个度量值（带 Σ 图标的）

---

## 🖼️ 第三阶段：搭建 4 页看板

> 点左侧工具栏的 **"报表"** 图标（方格那个），开始做可视化。
> 新建页面：底部页面标签栏 → 右键 → 重命名为"1 业务总览"，然后右键旁边 → 新建页面...

---

### 页面 1：业务总览（首页）

#### 1.1 添加日期切片器

1. 左边字段面板 → 展开 clean_wide → 找到 **order_purchase_timestamp**
2. **拖到页面空白处**（默认是日期切片器）
3. 拉成一条横条放在页面顶部
4. 点切片器右上角的 **向下箭头 → 下拉列表**，让它变成下拉框样式

#### 1.2 添加 5 个 KPI 卡片

**卡片图操作**：
- 顶部 **"可视化"** 面板里点 **"卡片"** 图标（长得像一张扑克牌）
- 选中卡片 → 拖字段面板里的度量值到卡片中间

依次拖这 5 个度量值做成 5 张卡片：
1. `[总销售额]` → 卡片标题改一下：点卡片 → 顶栏出现标题 → 改成"总销售额（雷亚尔）"
2. `[订单总数]`
3. `[用户数]`
4. `[延迟订单占比]`
5. `[平均配送时长]`

把 5 张卡片排成一行，放在切片器下面。

#### 1.3 添加销售趋势折线图

1. 可视化面板 → 选 **"折线和堆叠柱形图"**（或纯"折线图"）
2. 拖字段：
   - X 轴 = `clean_wide[下单月份]`（clean_wide 里的文本列）
   - Y 轴 = `[总销售额]`
3. 点图表右上角 **"..." → 排序 → 按下单月份升序**

#### 1.4 添加 RFM 分层饼图

1. 可视化面板 → 选 **"环形图"**（比饼图好看）
2. 拖字段：
   - 图例 = `rfm_result[客户分层]`
   - 值 = `[RFM用户数]`

✅ **页面 1 效果**：顶部日期切片器 + 5 张 KPI 卡片 + 左边销售趋势折线图 + 右边环形图

---

### 页面 2：类目分析

底部页面标签 → **右键 → 新建页面** → 改名为"2 类目分析"

#### 2.1 添加类目切片器

左边字段面板 → clean_wide → **category_cn** → 拖到页面顶部 → 设为"下拉列表"

#### 2.2 TOP10 类目柱状图

1. 可视化面板 → 选 **"簇状柱状图"**
2. 拖字段：
   - X 轴 = `category_sales_stats[category_cn]`（⚠️ 从 category_sales_stats 表拖！不要从 clean_wide 拖）
   - Y 轴 = `category_sales_stats[销售总额]`
3. 点击图表 → 顶栏出现 X 轴标题 → 改成"类目"，Y 轴改成"销售额"
4. **⚠️ 如果图只显示一个类目**：点图表上方切片器右上角的 **"清除筛选"**（小橡皮擦图标）

#### 2.3 明细表

1. 可视化面板 → 选 **"表格"**
2. 拖字段（都从 category_sales_stats 拖）：
   - category_cn、订单数量、销售总额、延迟率
3. 表头可以点击排序

✅ **页面 2 效果**：顶部类目下拉切片器 + 左边柱状图 + 右边明细表

---

### 页面 3：RFM 用户分层

新建页面 → 改名为"3 RFM分层"

#### 3.1 RFM 分层切片器

字段面板 → rfm_result → **客户分层** → 拖到顶部 → 下拉列表

#### 3.2 分层饼图

可视化面板 → 环形图
- 图例 = `rfm_result[客户分层]`
- 值 = `[RFM用户数]`

#### 3.3 各层客单价柱图

可视化面板 → 簇状柱形图
- X 轴 = `rfm_result[客户分层]`
- Y 轴 = `[各层用户平均消费]`

#### 3.4 用户明细表

可视化面板 → 表格
- 从 rfm_result 拖：customer_unique_id、Recency、Frequency、Monetary、客户分层

✅ **页面 3 效果**：顶部切片器 + 左环形图 + 右柱图 + 底部明细表

---

### 页面 4：物流分析

新建页面 → 改名为"4 物流分析"

#### 4.1 双切片器（类目 + 日期）

- clean_wide[category_cn] → 切片器 → 页面左上
- clean_wide[order_purchase_timestamp] → 切片器 → 页面右上

#### 4.2 类目订单量柱状图

可视化面板 → 簇状柱形图
- X 轴 = `clean_wide[category_cn]`
- Y 轴 = `[订单总数]`

#### 4.3 类目配送时长柱状图

可视化面板 → 簇状柱形图
- X 轴 = `clean_wide[category_cn]`
- Y 轴 = `[类目平均配送时长]`

#### 4.4 底部 2 张卡片

- 卡片图 → `[延迟订单占比]`
- 卡片图 → `[平均配送时长]`

✅ **页面 4 效果**：顶部 2 个切片器 + 左订单量柱图 + 右配送时长柱图 + 底部 2 卡片

---

## 💾 第四阶段：保存 & 美化

1. Ctrl + S → 文件名：`olist_brazilian_dashboard.pbix` → 保存到项目根目录
2. 顶部 **"视图" → "主题"** → 选一个深色主题（比如 "Executive Dark"），看起来更专业
3. 所有图表的标题、KPI 卡片标题都改成中文
4. 点图表 → 顶栏有个 **"数据标签"** 按钮 → 打开，让数值直接显示在柱图上

---

## 🆘 常见问题快速解答

| 问题 | 解决 |
|------|------|
| 度量值创建错了 / 想删 | 字段面板右键度量值 → 删除 |
| 图表显示空白 | 检查切片器是否筛掉了所有数据 → 点切片器上的"清除筛选" |
| 切片器不联动 | 表关系没建好或没设双向 → 回"模型"视图检查 |
| 找不到饼图 | 可视化面板上有个小三角可以翻页，或者直接搜索框搜"饼" |
| 卡片图显示的是日期不是数值 | 确认拖进去的是度量值（带 Σ 图标），不是列 |
| 想改页面顺序 | 底部页面标签栏 → 左键拖动页面标签 |
