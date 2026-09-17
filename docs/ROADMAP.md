# TravelMind 路线图与偏差登记

> 基线：[`REQUIREMENTS.md`](./REQUIREMENTS.md)（Phase 0 需求规格说明）
> 核对日期：2026-09-17 ｜ 当前版本：`v0.1.0`

本文档记录三件事：**不可改变的目标**、**已实现/未实现的进度**、**与原需求的每一处偏差及其性质**。

---

## 一、不可改变的核心目标

摘自 `REQUIREMENTS.md` 第 2.2 与 6.3 节：

**核心业务目标**

1. 自动生成一套完整旅行方案
2. 满足用户约束条件（预算、时间、**步行距离**、交通偏好等）
3. 兼顾兴趣匹配度和**旅行舒适度**
4. 输出多个方案以便用户比较
5. 为后续扩展留出动态规划和 AI 对话空间

**系统边界原则**

- 数据源必须可审计
- 规划计算必须有明确规则和评分模型
- **AI 仅作为自然语言理解和解释层，不替代规划计算器**

**由此得出的判定标准**

> 判断某个差异是否可以保留，只看一件事：
> **它是否让"方案可执行"这件事变弱了。**
>
> - 视觉、组件库、页面形态 → 让产品更好看更好用 → **可以保留**
> - 距离、时间、开放时间、约束 → 决定方案能不能照着走 → **不可动摇**

---

## 二、Phase 状态总览

| Phase | 内容 | 状态 | 说明 |
|:---:|---|:---:|---|
| 0 | 需求分析与技术验证 | 🟡 部分 | PostGIS / Vue / FastAPI 已验证；**高德、Open-Meteo、Amadeus 未验证** |
| 1 | 数据库（ER / 表 / 字段 / 索引 / PostGIS） | 🟢 基本完成 | 需求 17 个实体中已实现 14 个，另加 `City` |
| 2 | FastAPI（结构 / 模型 / Schema / CRUD / REST） | 🟢 基本完成 | 18 个端点，全部可运行 |
| 3 | Vue（页面 / 路由 / 状态 / API 请求 / 地图 / UI） | 🟡 部分 | 页面与地图完成；路由、状态管理、API 请求未做 |
| 4 | 数据采集（API Service / 爬虫 / 清洗 / 入库） | ⚪ 未开始 | 表结构已预留 source / confidence 等字段 |
| 5 | 旅行规划算法 | 🟡 后半段 | 评分与排程完成；**候选检索、数据整合、开放时间、距离缺失** |
| 6 | 多方案 | 🟡 4 / 5 | 缺"最省时" |
| 7 | 动态规划 | ⚪ 未开始 | `/planner/replan` 端点存在，但无自动触发 |
| 8 | AI | ⚪ 未开始 | — |

---

## 三、已完成

### 3.1 后端

**Phase 1 — 数据模型（15 个类）**

| 模型 | 表 | 需求中的对应实体 |
|---|---|---|
| `City` | `cities` | （需求未列，实现需要） |
| `POI` | `pois` | POI |
| `OpeningHour` | `opening_hours` | OpeningHours |
| `Ticket` | `tickets` | Ticket |
| `Hotel` | `hotels` | Hotel |
| `HotelOffer` | `hotel_offers` | HotelOffer |
| `TransportPlan` | `transport_plans` | TransportPlan |
| `TransportOption` | `transport_options` | TransportOption |
| `User` | `users` | User |
| `UserPreference` | `user_preferences` | UserPreference |
| `Trip` | `trips` | Trip |
| `TripDay` | `trip_days` | TripDay |
| `ItineraryItem` | `itinerary_items` | ItineraryItem |
| `Weather` | `weather` | Weather |
| `Expense` | `expenses` | Expense |

**数据可追溯字段已落地** —— `POI` / `OpeningHour` / `Ticket` 三张表均含 `source`、`source_url`、`crawl_time`、`confidence`、`updated_at`，符合需求 4.2 / 5.4 / 11.6。

**空间索引已就绪** —— `POI.geom` 为 PostGIS `POINT`（SRID 4326）。

**Phase 2 — API（18 个端点）**

| 模块 | 端点 |
|---|---|
| system | `GET /health` |
| users | `POST /users` · `GET /users/{id}` · `PUT /users/{id}/preferences` |
| trips | `POST /trips` · `GET /trips` · `GET /trips/{id}` · `PUT /trips/{id}` · `DELETE /trips/{id}` |
| pois | `GET /pois/search` · `GET /pois/{id}` |
| weather | `GET /weather` |
| hotels | `GET /hotels/search` |
| routes | `POST /routes/calculate` · `POST /routes/search` |
| planner | `POST /planner/generate` · `POST /planner/generate-options` · `POST /planner/replan` |
| expenses | `POST /expenses/estimate` |

统一前缀 `/api/v1`。5 组 pytest 测试（health / db_init / models / planner / seed_demo）。

**Phase 5 后半段 — 评分与排程**

- `scorer.py`：4 维加权评分（interest 0.45 / cost 0.20 / confidence 0.20 / weather 0.15）
- `generator.py`：按时间窗排程，尊重每日起止时间、单日条目上限、缓冲时间
- `multi_plan.py`：4 种方案取向

### 3.2 前端

| 项 | 状态 |
|---|---|
| 三屏滚动叙事（3D 地球 → 中国地图 → 规划表单） | ✅ 离散分页，600ms 冷却 |
| 可拖拽 3D 地球 | ✅ 自转已关闭，拖拽旋转 + 松手惯性 |
| 纬度钳制 ±90° | ✅ 不会转过南北极，无方向反转 |
| 地球 → 中国过渡 | ✅ 固定时长 1.6s，旋转占 0.65，之后放大 + 左移 + 淡出 |
| 由锚点自动计算朝向 | ✅ 运行时从真实摄像机推导 |
| 中国地图省份钻取 | ✅ 可下钻、可返回全国 |
| 交叉溶解 | ✅ 地球淡出与地图淡入重叠 |
| 第三页地图落位 | ✅ 由 DOM 插槽实测，误差约 7px |
| 创建旅行页 | 🟡 表单可用，但字段不全，不提交后端 |
| 我的方案页 | 🟡 空状态视觉预览 |
| 响应式 | ✅ 900px / 620px 断点 |
| 对比度与原生控件深色适配 | ✅ |

---

## 四、核心缺口

### 4.1 根因：Phase 2 与 Phase 5 之间缺一层

需求 8.1 的核心流程里，"候选 POI 检索 → 数据整合"是规划之前的必经步骤。**这一层目前不存在。**

代码证据 —— `app/schemas/planner.py`：

```python
class PlannerGenerateRequest(BaseModel):
    travel_date: date
    candidates: list[PlannerCandidateInput] = Field(min_length=1)   # ← 客户端必须自己传
```

规划器 API **不查数据库**，要求调用方把候选 POI 列表准备好再传入。而数据库里**已经有**：

```python
class POI(Base):
    geom: Mapped[object] = mapped_column(Geometry("POINT", srid=4326), nullable=False)
    opening_hours: Mapped[list["OpeningHour"]] = relationship(...)
    tickets: Mapped[list["Ticket"]] = relationship(...)
```

坐标有、开放时间表有、门票表有，但**没有任何代码把它们搬进规划器**。

**连锁后果**

| 受影响项 | 说明 |
|---|---|
| 需求 4.3「空间距离计算」 | 输入端没有坐标，无法实现 |
| 需求 4.3「交通时间计算」 | 同上 |
| 需求 11.3「景点顺序折减总距离」 | 同上 |
| 需求 11.2「过滤旅行日期不开放的景点」 | `PlanningCandidate` 无开放时间字段 |
| 需求 11.1「开放时间满足当日访问窗口」 | 同上 |
| 需求 4.1「每天最大步行距离」输入 | `PlanningPreferences` 无此字段，收了也用不上 |
| 需求 8.2「过滤不满足步行距离的候选」 | 同上 |
| 需求 4.1「交通偏好」「住宿偏好」「每天出行时间」 | 前端未采集，规划器未接收 |
| 前端调用 | 浏览器必须先自行拼装候选 POI 列表才能发请求，不合理 |

### 4.2 规划器评分维度不足

| 需求（第 8 节） | 当前实现 |
|---|---|
| `Score = w1·Interest + w2·Time + w3·Cost + w4·Route + w5·Weather + w6·Comfort` | `interest 0.45 + cost 0.20 + confidence 0.20 + weather 0.15` |

- **缺** `Time` / `Route` / `Comfort`
- **多** `Confidence`（需求未列，但符合"数据可信度"精神，建议保留）
- 需求第 9 节的动态权重表（省钱型 / 舒适型 / 兴趣优先）未实现，权重为硬编码

### 4.3 多方案缺一种

需求 4.1 要求 5 种：综合最优 / 最省钱 / 最舒适 / **最省时** / 兴趣最优。

当前 4 种：`best_overall` / `cheapest` / `most_comfortable` / `best_interest_match`。

"最省时"依赖时间维度计算，属 4.1 的连锁缺口。且多方案评分只用了 2 个权重（interest、cost），与需求第 9 节的 4 维权重表不符。

### 4.4 前端缺 4 个页面

需求第十五节列了 7 个页面：

| 页面 | 状态 |
|---|---|
| 1. 首页 | ✅ |
| 2. 创建旅行 | 🟡 字段不全 |
| 3. 规划过程（进度反馈） | ❌ |
| 4. 规划结果（评分/费用/多方案标签页 + 每日行程） | ❌ 仅空状态 |
| 5. 地图（Day 切换 + 景点顺序连线） | ❌ 有地图，无路线与 Day 切换 |
| 6. 费用（交通/住宿/门票/餐饮/市内交通/其他 + 人均 + 预算使用率） | ❌ |
| 7. 旅行详情（每日行程 + 交通 + 酒店 + 天气 + 费用 + 地图） | ❌ |

### 4.5 前端缺的基础设施

- 无路由（用 `activeView` ref 切换视图，非 `vue-router`）
- 无状态管理（无 Pinia）
- 无 API 请求层（前后端未联通）

---

## 五、偏差登记

「性质」列按第一节的判定标准分类。

| # | 需求 | 当前实现 | 性质 | 决定 |
|:---:|---|---|:---:|---|
| 1 | 前端 Element Plus | 手写 CSS | 表面 | **保留** —— 更贴合 `DESIGN.md` 的 Midnight atlas 气质 |
| 2 | 高德地图（地图渲染） | ECharts + china-geojson + Three.js | 表面 | **保留** —— 观感更好，且实现了省份下钻 |
| 3 | API 路径 `/api/...` | `/api/v1/...` | 改进 | **保留** —— 加了版本前缀 |
| 4 | 首页 = 单个表单 | 三屏滚动叙事 | 表面（更优） | **保留** —— 产品表达升级，不影响可执行性 |
| 5 | 评分含 `Confidence` | 已实现 | 超出 | **保留** —— 符合数据可信度精神 |
| 6 | 高德地图（地理编码 / 路线 / 交通时间） | 未接 | **核心** | **补** —— 需求 14.1 指定的核心数据源 |
| 7 | 6 维评分 | 4 维 | **核心** | **补** |
| 8 | 路线规则（折减总距离 / 步行阈值） | 无法实现 | **核心** | **补** |
| 9 | 开放时间过滤 | 未接 | **核心** | **补** |
| 10 | 5 种方案 | 4 种 | **核心** | **补** |
| 11 | 12 个输入字段 | 前端采集 5 个 + 4 个兴趣标签 | **核心** | **补** |
| 12 | `GET /api/pois/nearby` | 未实现 | 次要 | **补**（PostGIS 已就绪，成本低） |
| 13 | `GET /api/transport/search` | 实为 `POST /routes/search` | 表面 | **保留** |
| 14 | 候选 POI 检索 + 数据整合层 | 不存在 | **核心** | **补**（见 4.1） |
| 15 | 规划过程页 / 费用页 / 详情页 | 未实现 | 核心 | **补** |
| 16 | Phase 0 技术验证（高德 / Open-Meteo / Amadeus） | 未验证 | Phase 尾巴 | **补** —— 高德需先取得 API Key |
| 17 | Phase 4 数据采集 | 未开始 | 时序 | 按 Phase 推进 |
| 18 | Phase 7 / 8 动态规划、AI | 未开始 | 时序 | 按 Phase 推进 |

---

## 六、下一步

按依赖顺序，不按 Phase 编号：

**第 1 步 — 补「候选检索 + 数据整合」层**（对应偏差 #14）

- 新增 service：输入「目的地城市 + 旅行日期 + 用户约束」→ 输出 `PlanningCandidate` 列表
- 数据来源：按城市查 `pois` → 关联 `opening_hours` / `tickets` → 从 `geom` 取坐标
- 扩展 `PlanningCandidate`：加坐标、开放时间、门票价
- 扩展 `PlanningPreferences`：加 `max_walk_distance`、每日出行时间窗
- 调整 `/planner/generate` 签名：从「客户端传 candidates」改为「客户端传目的地 + 约束」

**第 2 步 — 规划器接入新字段**（对应偏差 #7 / #8 / #9 / #10）

- 距离计算（先用直线距离 × 道路系数，明确标记为估算）
- 开放时间过滤
- 补齐 6 维评分与动态权重
- 补第 5 种方案「最省时」

**第 3 步 — Phase 0 收尾**（对应偏差 #6 / #16）

- 申请高德 API Key
- 把距离从「直线估算」换成真实路线时间

**第 4 步 — 前端补齐**（对应偏差 #11 / #15）

- 补全创建旅行页字段
- 规划过程页、规划结果页、费用页、旅行详情页
- 接入 API

**第 5 步 — Phase 4 数据采集**

按原计划推进，第一阶段先做一个城市（北京）。

---

## 七、记录约定

- 任何与基线不一致的地方，都要在上表登记一行，并注明「性质」与「决定」
- 「性质 = 表面」的偏离只需登记，不阻塞进度
- 「性质 = 核心」的偏离必须在进入后续 Phase 前解决
- 完成一项后，更新第二节的 Phase 状态与对应条目的「决定」列
