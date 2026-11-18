# TravelMind 开发交接（Handoff）

> 最后更新：2026-11-17
>
> 读者：接手的开发者或 AI。只读本文件 + [`PROJECT_PLAN.md`](./PROJECT_PLAN.md) + [`API_CONTRACT_V0.3.md`](./API_CONTRACT_V0.3.md)，就能恢复当前上下文。
>
> 本项目是软件工程课程设计期末作业，目标是**完整可运行的单城多日规划 Demo**，不是全国商业旅游平台。

## 0. 五分钟恢复上下文

1. `git status`：工作区有未提交改动，**保留与当前任务无关的文件，不要回滚**。
2. `cd backend && python -m pytest -q`：期望 **155 passed, 1 warning**。
   - 默认 `AMAP_MODE=mock`：不调用高德，路线/天气/餐厅/住宿均为演示数据。
   - 切真实数据：在 `backend/.env` 写 `AMAP_MODE=cache`（缓存优先）或 `AMAP_MODE=live`（每次真实调用），重启后端。
   - `cache` 的进程内缓存：路线 24h、天气 30min、餐厅/住宿 6h；重启进程会清空。
3. 按顺序读：
   - 本文件：当前状态、已锁定决策、下一步、禁止事项；
   - [`PROJECT_PLAN.md`](./PROJECT_PLAN.md)：唯一需求/范围依据；
   - [`API_CONTRACT_V0.3.md`](./API_CONTRACT_V0.3.md)：目标接口契约。
4. 下一项任务：**准备福州/北京 15–20 个 POI 与官方核验**（见 §6 第 3 步）。

## 1. 一句话目标

用户输入城市、日期、天数、人数、预算和偏好后，系统生成**单城市多日行程**，包含真实路线、近 4 天天气、开放时间、门票/市内交通/餐饮/住宿费用、每天 `1→2→3` 静态顺序图、来源与未知标记；方案可保存为版本，改条件后重新生成新版本。

## 2. 已锁定决策（不要重新讨论）

| 项目 | 已确定 |
|---|---|
| 验收城市 | **福州 + 北京**；上海为可选扩展，不纳入首版验收 |
| 景点数据 | 每城 **15–20 个 POI**；每城 **5 个重点景点**核验官方票价/开放时间；其余标未知/估算 |
| 数据来源 | 高德 Web 服务 + 官方渠道人工核验；**不建通用爬虫、不运行时抓官网** |
| 行程 | 单目的地城市、多日；同一景点不跨日重复 |
| 方案数量 | 首版 **1 个方案**；用版本对比体现“比较”；现有多方案接口保留但不作为验收 |
| 路线 | 高德真实路线；失败标 `failed`，**不得用直线距离冒充** |
| 天气 | 高德近 4 天预报，以实际返回日期为准；超出/失败/不完整标未知；不接第二天气源 |
| 地图 | 每天 `1→2→3` 静态顺序图；**不做导航、不做 JS 交互地图、不申请 JS API Key** |
| 费用 | 整单总费用 = 门票 + 市内交通 + 餐饮 + 住宿；区分已确认/估算/未知；未知不能按 0 元 |
| 费用默认 | 住宿 2 人/间、晚数 = 天数 − 1；餐饮按人数 × 天数 × 人均日预算 |
| 修改 | 改条件后整趟重新生成新版本；**不做单点锁定/删除/替换、不做局部动态调整** |
| 持久化 | `Trip` + `PlanVersion`；v1 用 `plan_json` 快照，不先拆很多表；旧版本不覆盖 |
| 出行执行清单 | **Phase 2 加分项**：景点官方购票/预约指引、住宿区域+预算、餐饮区域+预算；**不站内下单/支付/承诺库存** |
| AI | 不纳入首版 |

### 为什么这样砍

- 课程只有约两个月，可研报告结论是“有条件可行”，建议先做单城市闭环；
- 福州是本地城市，演示和核验方便；北京复用现有演示数据；上海数据成本高，降为可选；
- 全国扩张的主要瓶颈是门票/开放时间的数据与运营，不是算法；首版先不背这个包袱；
- AI、跨城、订票、动态重规划都会显著扩大范围，收益不如把闭环做完整。

## 3. 当前代码真实状态

已实现：

- v0.2 多日规则排程：连续日期、开放时间过滤、每日时间窗、每日条目上限、跨日去重、全程费用累计、`ok/partial/empty`。
- v0.3 持久化骨架：`Trip` 改为单城市容器（`destination_city_id` + 标题），新增 `PlanVersion`（`request_json`、`plan_json`、`data_snapshot`、费用摘要、唯一 `(trip_id, version_no)`）；方案生成即保存新版本，旧版本不覆盖。
- 规划器已接入高德路线与天气：相邻景点按 GCJ-02 调用步行/公交/驾车/骑行；路线耗时进入当天时间表，步行距离累计并校验 `max_walk_km`；按日期取天气影响户外候选评分；失败路段标 `failed` 并用带标记的保守回退耗时。
  - 接入点是 v0.3 的 `POST /api/v1/trips/{id}/plans`；旧 `/api/v1/planner/*` 仍是无状态兼容接口，不接路线/天气。
- 新增 `planners/transport_selector.py`：每段生成主动出行（步行/骑行）、公交、打车/自驾候选，按时间、费用、步行、天气和偏好评分；`transport_preference` 是软偏好，不再强制全程同一种方式。骑行并入主动出行，排程用步行耗时做上限，页面同时显示步行/骑行耗时。公交不覆盖时不会强行回退，打车/骑行费用为估算，路段费用会进入整趟费用拆分。
- 公交方案中的每段 ≥300 m 接驳步行也会补一个骑行耗时；页面把首行标为“公共交通总计”，分段用 ①②③ 编号，并在天气中高风险时提示“步行和骑行体验可能受影响”。
- 公交/地铁明细已解析：线路名、类型、上车站、下车站、经停站数、该段距离/耗时，以及前后步行接驳；结果页在交通段下方逐条显示。
- 新增整趟费用模型：`app/services/costs.py` 合计门票（未核验时标 unknown）、市内交通、餐饮估算、住宿估算；餐饮按人数×天数、住宿按房间×晚数，城市参考值可被请求覆盖；响应新增 `costs` 拆分和 `budget_complete/unknown_items`。
- 用餐时间块：午餐 12:00–13:00（60 分钟）、晚餐 18:00–19:30（90 分钟），景点访问与用餐重叠时整体顺延；结果页显示用餐块和“推荐餐厅”按钮。
- 用餐推荐：`GET /plans/{id}/days/{day_index}/meals/{meal_type}/suggestions` 用高德 place/around 返回附近餐厅（名称、地址、距离、人均、评分），前端弹窗展示，用户选择只保存在当前页面，不做订座。
- 住宿推荐：`GET /plans/{id}/stays/suggestions` 按行程景点质心查高德附近住宿，按到全部景点的平均直线距离排序；`100000` 大类中过滤招待所/青年旅舍/旅馆/民宿/客栈/公寓和校内场所，只保留宾馆酒店类；前端独立“住宿推荐”页，当前整趟选一家，可扩展为多晚/多酒店，不做订房。
- 高德调用模式：`AMAP_MODE=mock|cache|live`，默认 `mock`；mock 不发起外部请求并生成本地示意图；cache 使用进程内跨请求缓存（路线 24h、天气 30min、餐厅/住宿 6h），未命中才调高德；live 绕过跨请求缓存。Mock 方案的 notes 和 `data_snapshot` 标 `mock`。
- 高德一次公交查询返回的多个 `transits` 全部保留为备选方案，按时间、费用、步行等评分选择；不再只取第一条。
- 请求级缓存与最小调用间隔：同一路段/城市只查一次，默认 0.05 s 间隔；未配置 Key 或无 adcode 时显式降级为 unknown。
- `PlanningCandidate.weather_sensitive` 由类别/类型关键词映射填充（公园、景区、自然类为敏感；博物馆等按不敏感）。
- `/api/v1/trips` 创建/列表/详情/更新/删除，`/api/v1/trips/{id}/plans` 生成与版本列表，`/api/v1/plans/{id}` 查看/删除。
- 福州、北京各接入 **16 个 POI**（高德 place/text + 人工类别/标签/游玩时长），Fuzhou adcode `350100`、北京 `110000`；旧 3 个“（演示）”POI 已移除。
- 每日静态顺序图：`GET /api/v1/plans/{id}/days/{day_index}/map` 后端代理高德底图，再用 Pillow 按 Web Mercator 画 1→2→3 编号；失败返回 502，前端降级为列表。
- 前端闭环：`frontend/src/api.ts` + `App.vue` 已接 `/trips` 与 `/trips/{id}/plans`，结果页展示逐日景点、路线段、天气、步行距离、静态图、预算差额和边界说明；生成后自动保存版本，可重新生成。
- GCJ-02/WGS84 坐标转换。
- 后端测试 **155 passed, 1 warning**；前端 `vue-tsc --noEmit` 和 `vite build` 通过。

未实现：

- 每城 5 个重点景点的官方票价/开放时间核验；当前 Ticket 为空，页面逐项标“票价待核”；
- 前端版本历史列表/加载/删除（后端接口已有）、账号体系；
- `PlanCost` / `PlanDay` / `PlanItem` / `PlanLeg` 规范化拆表；
- 门票按人数放大、门票/交通的 confirmed/estimated/unknown 三态和 `PlanCost` 规范化；当前费用拆分已有但门票仍为空。
- 跨请求缓存/全局限流、Alembic 迁移、城市 adcode/别名批量维护。

### 贡献归属（内部记录，不写入课程报告）

- 截至 2026-10-30，仓库内已完成的产品设计、代码、测试和文档工作均由**吴梓豪**完成。
- 其他成员尚未参与上述已完成内容；此记录只用于项目交接与组内贡献说明，**不写入第二次实验计划书**，以免与“项目尚未开始”的报告口径冲突。
- 课程报告中的 108 / 108 / 72 人时仍是**计划分工**，不代表实际已完成贡献。

## 4. 明确不做（看到也不要重新加）

- AI 自然语言规划/对话修改；
- 跨城交通、航班、火车；
- 站内订票、支付、退改、库存、抢票；
- 地图导航、交互式 JS 地图、路线拖拽；
- 全国城市覆盖、全国通用爬虫、定时全量抓取；
- 旅行期间实时监控/动态局部调整；
- 固定数量的多方案优化；
- 和风天气等第二天气源（保留接口，首版不接）。

## 5. 接口与数据口径

以 [`API_CONTRACT_V0.3.md`](./API_CONTRACT_V0.3.md) 为准。关键点：

- 请求：`city`、`start_date` + `days`、`adults`/`children`、`budget_total`、`interests` 0–100、`pace` 0–100、`transport_preference`、`daily_start`/`daily_end`、`max_daily_items`、`max_walk_km`、餐饮/住宿预算、`rooms`/`nights`。
- 响应：逐日 `items`、`legs`、`weather`、`walk_km`、`map`；整趟 `costs`、`budget_difference`、`over_budget`、`status`、`unknown_items`、`data_snapshot`。
- 状态：`plan.status`、`weather.status`、`route.status`、`opening.status`、`ticket.status`、`cost.status`、`map.status`、`walk_constraint.status`。
- 路线失败：距离/耗时为 `null`，不得伪造；步行约束标 `unknown`。
- 天气未知：中性评分，不声称已按天气优化。
- 费用未知：金额 `null`，不计入“已确认+估算”，预算差额标“至少”。
- 地图：后端代理高德静态图，前端不接触 Key；失败降级为顺序列表。

## 6. 下一步顺序（按这个做）

1. ✅ **持久化模型（2026-11-17 完成）**：`PlanVersion`（`trip_id`、`version_no`、`request_json`、`plan_json`、摘要字段）；`Trip` 改单城市；v1 不拆 `PlanDay/Item` 表。迁移脚本见 `backend/scripts/migrate_v03_trips_plans.py`。
2. ✅ **接入规划器（2026-11-17 完成）**：`AmapClient` 已用于路线段、步行累计、`max_walk_km` 硬约束和按日期天气；请求级缓存/最小间隔/失败降级已补；测试用固定 fixture。
3. 🟡 **数据（2026-11-17 第一版）**：福州、北京各 16 个 POI 已入库，福州 adcode 已补；**每城 5 个重点景点的官方票价/开放时间核验尚未完成**，Ticket 仍为空。
4. ✅ **静态地图（2026-11-17 完成）**：后端代理高德底图 + Pillow 画编号，按 1→2→3 标注；失败 502、前端降级。
5. ✅ **前端闭环（2026-11-17 完成）**：表单 → 创建 Trip → 生成 Plan → 逐日行程/路线/天气/步行/静态图 → 自动保存版本 → 重新生成；版本历史列表 UI 尚未做。
6. **补费用与官方数据**：人数计价、餐饮/住宿/市内交通估算、费用三态；每城 5 个重点景点官方核验。
7. **Phase 2（有余力再做）**：出行执行清单/购票指引（官方渠道、预约规则、链接、住宿区域、餐饮预算）；不做下单。
8. **回归/试用**：路线失败、天气未知、票价未知、超预算、闭馆、两城、版本复现、Key 不泄露。

## 7. 代码地图

- 规划器：`backend/app/planners/`（`models.py`、`generator.py`、`transport_selector.py`、`trip.py`、`multi_plan.py`、`scorer.py`、`opening_filter.py`）。
- 高德适配：`backend/app/services/amap.py`（路线/天气；已接入 v0.3 规划接口）。
- 候选检索：`backend/app/services/candidates.py`；城市名精确匹配，City 已有 `amap_adcode`。
- 接口：`backend/app/api/v1/planner.py`（无状态生成）；`trips.py`（旅行容器）；`plans.py`（版本生成/读取/删除/静态图）；schema：`backend/app/schemas/planner.py`、`trip.py`、`plan.py`。
- 静态图：`backend/app/services/static_map.py`（高德底图 + Pillow 编号）。
- 数据脚本：`backend/scripts/fetch_city_pois.py`、`seed_city_data.py`，快照在 `backend/app/db/city_pois.json`。
- 前端：`frontend/src/api.ts`、`frontend/src/App.vue`、`frontend/src/styles.css`；Vite 代理 `/api` → `127.0.0.1:8000`。
- 持久化：`backend/app/models/trip.py`（`Trip`/`PlanVersion`，旧 `TripDay`/`ItineraryItem` 保留只读）；`app/services/plan_versions.py`（版本号、摘要、快照序列化）。
- 路线/天气装配：`app/services/planning_services.py`（请求级缓存、最小调用间隔、未配置 Key 时降级）、`app/planners/routing.py`（规划器协议）。
- 迁移：`backend/scripts/migrate_v03_trips_plans.py`（PostgreSQL 可重复执行）。
- 种子：`backend/scripts/seed_city_data.py`（福州/北京 16+16 POI）；`seed_demo.py` 仅保留为旧演示种子，不再使用。
- 测试：`backend/tests/`（现有 131 个）。
- 前端：`frontend/src/App.vue`（视觉 Demo，尚无 API 调用）。
- 文档：本文件、`PROJECT_PLAN.md`、`API_CONTRACT_V0.3.md`、`FEASIBILITY_STUDY.md`（课程可研报告，不覆盖当前规划）。

## 8. 验证命令

```powershell
cd backend
python -m pytest -q
# 期望：155 passed, 1 warning
```

- 单元测试不访问真实高德接口；新适配器测试用 `httpx.MockTransport`。
- 真实接口探测（可选，会消耗配额）：`python -m scripts.probe_amap`、`python -m scripts.probe_coverage`。
- 不要把 `AMAP_API_KEY` 写进前端、日志、测试或文档。

## 9. 已知坑与限制

- 旧 `trips` 列（`from_city_id`、`to_city_id`、日期、人数等）仍保留，迁移后均为可空；新代码不再读写，不要用它们判断当前行程。
- `PlanVersion.plan_json` 是快照，字段随生成时 schema 固定；读取旧版本时不要假设一定有最新字段。
- `City.amap_adcode` 目前只给北京 `110000`、福州 `350100` 填了值；其他城市要先补 adcode，否则天气直接标 unknown。
- 城市检索仍是精确名称，没有别名/adcode 自动解析。
- 路线/天气缓存和 0.05 s 最小间隔只在单个规划请求内生效；没有跨请求缓存、全局限流和 Alembic。
- 当前迁移脚本只针对 PostgreSQL，且只做加列/建表。
- 高德 `biz_ext.cost` 不能当门票：2026-10-30 北京 526 个景点覆盖 0/526；重点景点必须官方核验。
- 天气只覆盖近 4 天；超出必须标未知。
- 静态地图：后端先取无标注高德底图，再用 Pillow 按 Web Mercator 画编号；多 marker 不能靠重复参数，已用本地绘制解决。
- 住宿/餐饮是城市级估算，不绑定具体酒店/餐厅，不承诺实时价格/库存。
- 首版不建模“住宿点→首景点/最后景点→住宿”的接驳，步行只算相邻景点之间。
- `transport_preference` 是软偏好：主动出行（步行/骑行）、公交、打车/自驾按时间、费用、步行、天气、偏好评分；公交不覆盖时不会强行保留。骑行不单独决定排程，排程用步行耗时作为上限，页面同时给出步行/骑行耗时。打车/骑行费用是估算，不能当真实计价。
- 八达岭没有地铁直达；市郊铁路 S2 线、京张高铁八达岭长城站属于铁路，不是地铁。高德 `transit/integrated` 当前不返回这两条线（`railway` 为空），只给地铁+877 路公交；要支持需单独维护时刻表/票价/站点接驳。
- 877 路名称可能包含“地铁北土城站”，不能按名称含“地铁”判为地铁；已改为按线路 `type` 判断。
- `HTTP_PROXY/NO_PROXY` 若包含畸形项（如 `[::1]`），httpx 创建 Client 时会直接报 `InvalidURL`，导致规划接口 500。高德/静态图客户端已设 `trust_env=False`；需要代理访问高德时必须显式配置。

### 待定数据项（不是决策冲突）

- 福州、北京各 5 个重点景点的核验名单、官方票价/开放时间和购票链接仍待完成；当前 Ticket 为空，页面标“票价待核”。
- 上海是否扩展未定；不阻塞首版。
- 静态地图的具体视觉样式未定；接口、Key 代理和失败降级已定。
- `PlanVersion` 的摘要字段最终以什么粒度展示，可在实现时再定；`plan_json` 是确定的。

## 10. 变更记录

| 日期 | 变更 |
|---|---|
| 2026-10-30 | 冻结多日 v0.2 契约；确认首版产品规则；新增 v0.3 目标契约 |
| 2026-10-30 | 高德能力实测；新增 `AmapClient` 适配层与 7 个测试；测试 113 passed |
| 2026-10-30 | 验收范围收敛为福州 + 北京，上海可选；单方案 + 版本；动态局部调整/AI 不做；出行清单列为 Phase 2 |
| 2026-11-17 | 完成 v0.3 持久化骨架：Trip 改单城市，新增 PlanVersion/plan_json、版本接口与迁移脚本；测试 120 passed |
| 2026-11-17 | 规划器接入高德路线/天气：步行累计与 max_walk 硬约束、按日期天气、请求级缓存/限流/失败降级；测试 131 passed |
| 2026-11-17 | 福州/北京各 16 个 POI、福州 adcode、Pillow 编号静态图、前端结果页闭环；测试 137 passed，前端构建通过 |
| 2026-11-17 | auto 交通按 1.5 km 选择步行/公交，前端绑定交通偏好；测试 138 passed |
| 2026-11-17 | 新增 transport_selector：逐段候选、费用估算、软偏好评分与公交降级；测试 143 passed |
| 2026-11-17 | 公交/地铁明细解析、877 路误判修复；测试 144 passed |
| 2026-11-17 | 保留并比较高德返回的全部公交备选方案；测试 146 passed |
| 2026-11-17 | 骑行并入主动出行：排程按步行耗时上限，页面同时显示步行/骑行耗时；测试 147 passed |
| 2026-11-17 | 公交接驳步行补骑行耗时、公共交通总计/分段编号、天气提示；测试 147 passed |
| 2026-11-17 | 新增整趟费用拆分：门票/市内交通/餐饮/住宿、预算差额与未知项；测试 147 passed |
| 2026-11-17 | 用餐时间块 + 餐厅推荐弹窗、四类费用展示；测试 148 passed |
| 2026-11-17 | 住宿推荐接口与独立页面；整趟一家、可扩展多晚，不做订房；测试 148 passed |
| 2026-11-17 | 住宿类型过滤：排除招待所/青旅/民宿，只保留宾馆酒店；测试 149 passed |
| 2026-11-17 | AMAP_MODE=mock/cache/live、进程内跨请求缓存、Mock 静态图；测试 155 passed |
