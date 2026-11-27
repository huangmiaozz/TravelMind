# TravelMind API Contract v0.3

> 目标契约，2026-10-30 冻结；2026-11-26 补充当前已落地的费用三态、版本历史和餐食/住宿选择接口。当前运行代码已实现持久化、路线/天气、门票人数计价与三态费用、版本历史 UI 和选择保存；规范拆表（PlanDay/Item/Leg/Cost）仍未完成。本文件仍是接口/字段目标，当前真实状态与下一步见 [`HANDOFF.md`](./HANDOFF.md)。
>
> 范围：单一目的地城市（首版验收：福州、北京；上海为可选扩展）、多日、保存版本；**不做导航、交互地图、跨城交通、订票或 AI**。
>
> 示例中的景点、价格和时间只用于说明字段，不代表真实数据。

## 1. 通用约定

| 项目 | 约定 |
|---|---|
| 城市 | 每次行程一个目的地城市；首版验收福州、北京，上海可选 |
| 日期 | ISO 8601（`2026-11-02`）；`days` 为含首日的连续天数 |
| 时间 | `HH:MM`；`daily_end > daily_start` |
| 金额 | CNY，保留两位小数 |
| 距离/耗时 | 米 / 秒 |
| 坐标 | 数据库存 WGS84；调用高德和生成地图前转 GCJ-02 |
| 未知数据 | 必须显式标记，不能填 0、空字符串或假装已确认 |
| 真实/估算 | 外部服务数据带 `source`、`status`；Mock 数据额外带 `is_mock=true`，界面据此标注 |

### 1.1 状态枚举

| 枚举 | 取值 | 含义 |
|---|---|---|
| `plan.status` | `ok` / `partial` / `empty` | 全部日期有安排 / 部分日期为空 / 完全排不出 |
| `weather.status` | `known` / `unknown` | 该日有可靠预报 / 无可靠预报 |
| `route.status` | `ok` / `failed` / `mock` | 真实路线成功 / 调用失败 / 明确标注的估算 |
| `opening.status` | `confirmed` / `estimated` / `unknown` | 官方核验 / 按原文保守解析 / 无可用信息 |
| `ticket.status` | `confirmed` / `estimated` / `unknown` | 官方票价 / 参考估算 / 未知 |
| `cost.status` | `confirmed` / `quoted` / `estimated` / `partial` / `unknown` | 已确认 / 实时报价 / 估算 / 部分未知 / 未知项 |
| `map.status` | `ready` / `failed` | 静态图可用 / 生成失败，方案仍可用 |
| `walk_constraint.status` | `satisfied` / `violated` / `unknown` | 步行约束通过 / 超出 / 路线未知无法校验 |

## 2. 规划请求

`POST /api/v1/trips/{trip_id}/plans` 的 body：

```json
{
  "city": "福州",
  "start_date": "2026-11-02",
  "days": 3,
  "adults": 2,
  "children": 1,
  "budget_total": 6000,
  "interests": { "history": 80, "nature": 60, "food": 40 },
  "pace": 55,
  "transport_preference": "transit",
  "daily_start": "09:00",
  "daily_end": "20:00",
  "max_daily_items": 4,
  "max_walk_km": 8,
  "meal_budget_per_person_day": 120,
  "hotel_budget_per_room_night": 450,
  "rooms": 1,
  "nights": 2
}
```

| 字段 | 类型 | 说明 |
|---|---|---|
| `city` | string | 目的地城市名；必须与 Trip 的目的地一致 |
| `start_date` + `days` | date + int(1–30) | 从首日起连续 `days` 天 |
| `adults` / `children` | int ≥1 / int ≥0 | 用于门票、餐饮、房间数；至少一名成人 |
| `budget_total` | number ≥0 | **整趟、所有同行人员**的总预算；0 表示未设置 |
| `interests` | `{tag: 0–100}` | 兴趣滑动条，进入规划器归一化为 0–1 |
| `pace` | int 0–100 | 0 最轻松、100 最充实；影响每日条目上限、间隔和评分 |
| `transport_preference` | enum | `auto` / `walk` / `transit` / `drive` / `bicycle` |
| `daily_start` / `daily_end` | time | 每日可出行窗口；`daily_end > daily_start` |
| `max_daily_items` | int 1–20 | 每日最多景点数 |
| `max_walk_km` | number 或 null | 每日最大步行距离；null 表示不限制 |
| `meal_budget_per_person_day` | number 或 null | 用户覆盖的餐饮预算；null 用城市参考值 |
| `hotel_budget_per_room_night` | number 或 null | 用户覆盖的住宿预算；null 用城市参考值 |
| `rooms` | int 或 null | 默认 `ceil((adults + children) / 2)` |
| `nights` | int 或 null | 默认 `max(0, days - 1)`；不得为负 |

规则：

- `budget_total` 是**软约束**：超预算不淘汰方案，只影响费用评价并显示负差额。
- `max_walk_km` 是硬约束：按真实步行路线累计；路线未知时不能声称已满足。
- 兴趣、节奏、交通偏好只影响排序和评分，不能抵消硬约束违规。
- `Trip` 只保存目的地容器；日期、人数、预算和偏好属于 `PlanVersion`，因此改条件只影响新版本。

## 3. 规划响应

`GET /api/v1/plans/{plan_id}` 返回：

```json
{
  "plan_id": 101,
  "trip_id": 12,
  "version_no": 2,
  "status": "ok",
  "city": "福州",
  "start_date": "2026-11-02",
  "generated_at": "2026-10-30T10:30:00+08:00",
  "data_snapshot": {
    "poi_data_version": "2026-10-30T09:00:00+08:00",
    "weather_source": "amap_web_service",
    "route_source": "amap_web_service"
  },
  "days": [
    {
      "day_index": 1,
      "date": "2026-11-02",
      "weather": {
        "status": "known",
        "condition": "多云",
        "temperature_min": 15,
        "temperature_max": 21,
        "precipitation": 0,
        "risk_level": "low",
        "source": "amap_web_service",
        "fetched_at": "2026-10-30T09:30:00+08:00"
      },
      "items": [
        {
          "order": 1,
          "poi_id": 101,
          "name": "示例景点 A",
          "category": "park",
          "indoor": false,
          "opening_status": "confirmed",
          "ticket_price": 20,
          "ticket_child_price": 10,
          "ticket_status": "confirmed",
          "ticket_source": "official_website",
          "ticket_source_url": "https://example.invalid/official-page",
          "ticket_verified_at": "2026-10-30",
          "start_time": "09:00",
          "end_time": "11:00",
          "visit_minutes": 120,
          "opening": {
            "status": "confirmed",
            "known": true,
            "open_time": "06:00",
            "close_time": "18:00",
            "raw": "周一至周日 06:00-18:00",
            "source": "official_website",
            "source_url": "https://example.invalid/official-page",
            "verified_at": "2026-10-30"
          },
          "ticket": {
            "status": "confirmed",
            "price": 20,
            "currency": "CNY",
            "ticket_type": "adult",
            "applies_to": "adult",
            "source": "official_website",
            "source_url": "https://example.invalid/official-page",
            "verified_at": "2026-10-30"
          }
        }
      ],
      "legs": [
        {
          "order": 1,
          "from_poi_id": 101,
          "to_poi_id": 102,
          "mode": "transit",
          "distance_m": 5200,
          "duration_s": 1800,
          "cost": {
            "amount": 4,
            "currency": "CNY",
            "status": "estimated",
            "basis": "per_person"
          },
          "route_status": "ok",
          "source": "amap_web_service",
          "is_mock": false
        }
      ],
      "walk_km": 1.2,
      "walk_constraint": { "limit_km": 8, "status": "satisfied" },
      "estimated_cost": 300,
      "map": {
        "status": "ready",
        "image_url": "/api/v1/plans/101/days/1/map",
        "points": [
          { "order": 1, "poi_id": 101, "name": "示例景点 A" },
          { "order": 2, "poi_id": 102, "name": "示例景点 B" }
        ]
      }
    }
  ],
  "costs": {
    "currency": "CNY",
    "tickets": { "amount": 180, "status": "estimated", "note": "按成人/儿童票种与人数估算" },
    "tickets_confirmed_amount": 0,
    "tickets_estimated_amount": 180,
    "tickets_unknown_count": 0,
    "city_transport": { "amount": 24, "status": "estimated", "note": "公交/地铁按人，出租车按车" },
    "meals": { "amount": 1080, "status": "estimated", "note": "3 天 × 3 人 × 120 元/人/日" },
    "lodging": { "amount": 900, "status": "estimated", "note": "1 间 × 2 晚 × 450 元" },
    "total_confirmed": 0,
    "total_estimated": 2184,
    "unknown_items": [
      { "kind": "ticket", "day_index": 2, "poi_id": 103, "reason": "官方票价未核验" }
    ],
    "budget_total": 6000,
    "budget_difference": 3816,
    "over_budget": false,
    "budget_complete": false,
    "budget_note": "差额按已确认+估算计算，另有 1 项未知费用未计入",
    "intercity_transport_included": false
  },
  "notes": [
    "天气：2026-11-05 超出高德预报范围，标记未知，未参与该日评分。",
    "路线：调用高德 Web 服务，不含导航和实时路况。"
  ],
  "unknown_items": [
    { "kind": "weather", "day_index": 4, "reason": "超出可用预报日期范围" }
  ]
}
```

### 3.1 字段语义

- `days[].items[].order` 从 1 开始，决定当天的游览顺序，也是静态地图上的编号。
- `days[].items[].opening_status`：`confirmed` 表示开放时间来自官方核验，`estimated` 表示高德/第三方解析，`unknown` 表示无可用信息；它与 `opening_known` 同时保留，兼容旧版本。
- `days[].items[].ticket_price` / `ticket_child_price` 是单人单价；`build_costs` 再乘成人和儿童人数。`ticket_status=unknown` 时金额不计入已确认/估算，只进入 `unknown_items`。
- `costs.tickets_confirmed_amount` 与 `costs.tickets_estimated_amount` 是门票金额的三态拆分；`tickets_unknown_count` 是待核景点数。
- `days[].legs[]` 表示 `order` 与 `order+1` 之间的交通；`from_poi_id` / `to_poi_id` 必须对应相邻条目。
- `days[].map.image_url` 指向后端静态图接口；**前端不直接拼高德 Key**。
- `costs.unknown_items` 只列金额未知的项；`total_estimated` 不包含未知项。
- 某类费用 `status=unknown` 时 `amount` 必须为 `null`，**不得填 0**；`total_estimated` 只累加 confirmed/estimated。
- `budget_total=0` 时 `budget_difference=0`、`budget_complete=false`，并注明“未设置预算”，不能把未设置预算当成超支。
- `budget_complete=false` 时，预算差额必须按“已确认+估算”解释，界面显示“至少”。
- `days[].map.status=failed` 时 `image_url=null`，用条目列表展示顺序，不阻塞方案。
- 生成方案即保存为 `PlanVersion`（首版不做未保存预览）；旧版本不因重新生成而改变。
- `data_snapshot` 用于复现旧版本；至少包含 POI 数据时间、天气和路线来源版本。

## 4. 规则与降级

### 4.1 硬约束

1. 开放时间：已知时，访问必须落在窗口内；未知时放行并标 `opening.status=unknown`，不得当作闭馆。
2. 每日时间窗：所有条目和路线耗时不得超出 `daily_start`–`daily_end`。
3. 每日最大步行距离：按当天所有步行路线距离之和计算；超过则不排入该候选。
4. 同一景点不跨日重复；每日条目不超过 `max_daily_items`。
5. 违反硬约束不得用兴趣、天气或预算评分补偿。

### 4.2 路线失败

- 先重试；仍失败时 `route.status=failed`，`distance_m` / `duration_s` 为 null。
- 不得用直线距离冒充真实路线，也不得在 `walk_km` 未知时声称步行约束通过。
- 如为保证排程使用保守回退耗时，必须写 `fallback_duration_s`、`is_estimate=true`，并在 `notes` 说明。
- 路线失败不导致整趟 500；该天可以 `partial`，或整趟 `empty`。

### 4.3 天气

- 只使用天气服务实际返回的日期；不写死“4 天”。
- 日期超出、调用失败、字段不完整 → `weather.status=unknown` + `reason`。
- 未知天气按中性分参与评分，不声称“已按天气优化”。
- 天气只影响软评分和户外/室内选择，不能替代开放时间、路线和出行前核实。

### 4.4 费用

- 门票：按票种和人数计算；票价未知时标 `unknown`，不得按 0 元计入总额。
- 市内交通：公交/地铁按人计费；出租车按车计费；步行 0；驾车缺少可靠费用时标估算或未知。
- 餐饮：默认 `人数 × 天数 × 城市人均每日预算`；用户可覆盖。
- 住宿：默认 `房间数 × 晚数 × 城市每间每晚预算`；用户可覆盖；不做实时价格/库存。
- 总费用 = 已确认 + 估算；未知项单列，`budget_complete=false`。
- 不含城际交通；结果页必须注明。

### 4.5 地图

- 每天按 `1 → 2 → 3 …` 顺序展示景点和相邻路段，**不做导航、不做交互、不申请 JS API Key**。
- 使用高德静态地图（Web 服务 Key），由后端代理生成/缓存 PNG，前端不接触 Key。
- 静态图失败时 `map.status=failed`、`image_url=null`，方案仍可查看，用列表展示顺序。
- 使用 GCJ-02 生成地图；遵守高德静态地图服务协议和缓存限制。

## 5. 持久化与版本

### 5.1 资源关系

```
Trip（用户的一次旅行）
 ├── PlanVersion V1（规划条件快照、数据快照、生成时间、状态、费用摘要）
 │     ├── PlanDay
 │     │     ├── PlanItem
 │     │     └── PlanLeg
 │     └── PlanCost
 ├── PlanVersion V2
 └── ...
```

- 重新规划 = 新增 `PlanVersion`，不覆盖旧版本。
- 首版不支持单个景点锁定、删除、替换；修改只通过改条件后重新生成。
- 旧版本必须可查看、可删除；`data_snapshot` 用于解释当时使用的数据。

### 5.2 接口

创建旅行容器：

```json
POST /api/v1/trips
{ "city": "福州", "title": "福州三日" }
```

`Trip` 只约束目的地；每次 `POST /plans` 提交完整的日期、人数、预算和偏好，保存为新版本。`city` 必须与 Trip 一致；要换城市请新建 Trip。

| 方法 | 路径 | 用途 |
|---|---|---|
| POST | `/api/v1/trips` | 创建单城市旅行容器（目的地、标题） |
| GET | `/api/v1/trips` | “我的方案”列表（含最新版本摘要） |
| GET | `/api/v1/trips/{trip_id}` | 旅行详情与版本列表 |
| POST | `/api/v1/trips/{trip_id}/plans` | 按请求生成并保存新版本 |
| GET | `/api/v1/trips/{trip_id}/plans` | 版本列表/摘要 |
| GET | `/api/v1/plans/{plan_id}` | 完整方案 |
| DELETE | `/api/v1/plans/{plan_id}` | 删除某版本 |
| GET | `/api/v1/plans/{plan_id}/selections` | 读取该版本的餐厅/住宿选择 |
| PUT | `/api/v1/plans/{plan_id}/selections` | 保存该版本的餐厅/住宿选择 |
| POST | `/api/v1/plans/{plan_id}/costs/recalculate` | 按已选餐厅/酒店重算并保存费用 |
| GET | `/api/v1/plans/{plan_id}/days/{day_index}/map` | 当天的静态顺序地图 PNG |

### 5.3 餐食、住宿与选择保存

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/v1/plans/{plan_id}/days/{day_index}/meals/{meal_type}/areas` | 按实际路线时间筛选可用用餐区域 |
| GET | `.../areas/{area_id}/restaurants` | 区域内餐厅，带质量标签 |
| GET | `.../areas/{area_id}/restaurants/search?q=` | 区域内搜索 |
| GET | `.../nearby` | 附近其他餐厅，排除已列区域 |
| GET | `.../nearby/search?q=` | 在“附近其他”内搜索 |
| GET | `/api/v1/plans/{plan_id}/stays/suggestions` | 住宿推荐（热度初筛 + 通勤排序 + RollingGo 查价） |
| GET | `/api/v1/plans/{plan_id}/stays/search?q=` | 按酒店/品牌搜索，仍计算通勤并查价 |

住宿返回的 `StaySuggestion` 价格字段：

```json
{
  "cost_amount": 452,
  "over_budget": false,
  "price_status": "quoted",
  "price_source": "rollinggo",
  "price_checked_at": "2026-11-27T01:00:00+00:00",
  "price_note": "最低可订房型：...；免费取消截止至..."
}
```

- `cost_amount` 是每晚最低可订价；查不到时保持 `null`。
- `price_status`：`quoted` 有实时报价；`no_availability` 酒店存在但当前日期无房型/满房；`not_found` 未匹配到该酒店；`query_failed` 查价失败。前端必须区分“无房型”和“价格待核”，不能把无房展示成 0 元或免费。
- `over_budget` 只在已知价格且超过请求的 `hotel_budget_per_room_night` 时为 true。
- 过去入住日期不查价（避免供应商回退到未来默认日期）；优先精确名称，名称仅因城市前缀/分店括注不同且基础名与地址一致时接受；品牌不同或地址不能互相印证时拒绝。

选择保存请求：

```json
PUT /api/v1/plans/101/selections
{
  "meals": [
    { "day_index": 1, "meal_type": "lunch", "name": "示例餐厅", "address": "示例路 1 号", "area_id": "qianmen", "travel_minutes": 12, "cost_amount": 50 }
  ],
  "stay": { "name": "示例酒店", "address": "示例路 2 号", "business_area": "前门", "tier": "舒适型", "cost_amount": 420, "rating": 4.6 }
}
```

- 选择写入 `PlanVersion.selection_json`，不修改只读的 `plan_json`；同一 Trip 的不同版本各自保存自己的选择。
- 删除版本时选择随版本删除；未选择时返回 `{ "meals": [], "stay": null }`。
- 选择只用于展示和后续出行参考，不做订座/订房/支付。
- `POST /costs/recalculate` 会按已选餐厅人均价和已选酒店每晚价重算餐食/住宿费用；未选餐次按日均餐饮预算拆分，未选酒店保留原估算。重算结果写入 `selection_json.costs/totals`，读取方案时覆盖展示，不修改 `plan_json`。
- RollingGo 酒店实时价对应的住宿状态为 `quoted`（实时报价），不是 `confirmed`；只有实际付款/订单确认才应使用 confirmed。餐饮仍按人均参考价标 estimated。重算返回 `costs.updated_at`，前端显示“已按选择更新”。

## 6. 数据模型调整（相对当前代码）

当前模型已有 `Trip` / `TripDay` / `ItineraryItem` / `Expense`，但不足以支撑 v0.3：

1. `Trip` 改为单城市容器：`user_id`、`destination_city_id`、`title`、`created_at`；不再保存 `from_city_id`/`to_city_id` 和行程日期。
2. 新增 `PlanVersion`：`trip_id`、`version_no`、`status`、`start_date`、`days`、`adults`、`children`、`budget_total`、`request_snapshot`、`data_snapshot`、`selection_json`、`generated_at`、费用摘要；唯一约束 `(trip_id, version_no)`。
3. 日期统一为“含首日”：`days = (end_date - start_date).days + 1`；若保留 `end_date`，它表示最后一个旅行日，不再使用容易 off-by-one 的等值校验。
4. 规范化目标是 `PlanDay`、`PlanItem`、`PlanLeg`、`PlanCost`；v1 可先用 `PlanVersion.plan_json` 快照（见下方说明），稳定后再拆表。
5. 新增 `CityCostProfile`：城市、餐饮人均/日、住宿每间/晚、来源、可信度、状态、更新时间。
6. `POI` 增加 `indoor`（bool 或 null）和 `data_status`；`Ticket` 已增加 `applies_to`、`status`、`verified_at`、`raw_text`；`OpeningHour` 保留 `source`/`confidence`，API 的 `opening_status` 由来源派生（官方来源且置信度足够高才 confirmed）。
7. 不再用 `Expense` 直接存 trip 级费用；改为 `PlanCost` 按版本存，避免重新规划覆盖。
8. 迁移前先修单城市 `Trip` 和日期口径；旧数据可保留只读，不覆盖。

> **v1 简化实施：** `PlanVersion` 可以先保存 `request_json` + `plan_json` + 摘要字段（总费用、状态、生成时间），响应结构不变；`PlanDay/PlanItem/PlanLeg/PlanCost` 作为后续规范化目标，不阻塞首版。这样少做联表和迁移，课程设计仍能展示版本、数据快照和费用汇总。

## 7. 外部数据来源

- **高德 Web 服务**：路线（步行/公交/驾车/骑行）、天气（近 4 天，以实际返回为准）、静态地图、POI/地理编码/行政区划。Key 只在后端使用。
- **RollingGo Hotel MCP**：仅用于酒店搜索和详情查价（`searchHotels` / `getHotelDetail`），不接下单、支付、库存承诺。返回价格带 `price_status/price_source/price_checked_at`、取消政策；名称不匹配/无房型/查价失败保持 `cost_amount=null`，分别用 `not_found/no_availability/query_failed` 标明。
- **官方数据**：景点官网、文旅/政府公开页面、官方公开接口；白名单适配器 + 人工维护。
- **采集原则**：不登录、不绕验证码、不调用未授权内部接口、不批量复制图片；逐站检查 robots/条款；禁止自动抓取的站点转人工。采集只写数据库，运行时规划不抓官网。
- **来源字段**：`source_type`、`source_url`、`collected_at`、`verified_at`、`status`、`confidence`、`raw_text`。
- **室内/户外**：按高德 typecode/category 建立映射并支持人工覆盖；不把 `indoor_map` 当作室内景点属性。
- **票价**：高德 `biz_ext.cost` 不能当门票价格（2026-10-30 北京 526 个景点覆盖 0/526）；重点景点以官方票价为准。

## 8. 验收测试矩阵

- 多日连续日期、同一景点不跨日重复、每日条目上限。
- 已知开放时间不满足 → 不排；未知开放时间 → 放行但标注。
- 真实步行路线累计超过 `max_walk_km` → 不排或调整顺序。
- 路线失败 → `route.status=failed`，不用直线距离冒充，不声称步行约束通过。
- 天气有预报 → 影响户外/室内评分；天气未知/超范围/调用失败 → `unknown`，中性评分，备注。
- 门票未知 → 不计 0，`budget_complete=false`；超预算仍返回并显示差额。
- 门票按成人/儿童人数乘单价；confirmed/estimated/partial/unknown 三态和待核数量正确。
- 重点景点官方票价/开放时间可从数据文件追溯到来源 URL 和核验日期。
- 餐饮/住宿估算按人数/房间/晚数计算；用户覆盖生效；城际交通不计入。
- 版本历史可查看/删除；餐厅/住宿选择写入当前版本并在重新打开时恢复。
- 酒店实时价按入住日期/人数/房间数查询；名称不匹配、过去日期、无报价或服务失败时保持 `null`，不得挂到另一家酒店；无房型必须用 `price_status=no_availability` 明确展示。
- 福州、北京各跑通至少一条 2–3 天行程；上海可选。
- 重新规划生成新版本，旧版本仍可读取；`data_snapshot` 可解释。
- 静态地图按 1→2→3 顺序生成；地图失败不阻塞方案；前端无 Key 泄露。
- 外部服务测试使用固定 fixture，不在单元测试里打真实接口。

## 9. 不在 v0.3 范围

- 地图导航、交互式 JS 地图、路线拖拽、实时路况。
- 跨城交通、航班、火车、订票、支付、实时酒店库存。
- 单个景点锁定/删除/替换。
- 行程中的局部调整（延长/缩短单个景点、局部替换）和“最小变更”优化。
- AI 对话规划或自动改行程。
- 全国性通用爬虫、定时全量抓取。
- 第二天气源（保留 `WeatherProvider` 接口，后续评估）。
- 多方案比较；首版只做 1 个方案 + 版本对比，现有 `/generate-options` 仅保留为旧实现。
- 站内下单/支付/库存；“出行执行清单/购票指引”作为 Phase 2，不在 v0.3 规划响应中。
- 住宿点到首个景点、最后景点回住宿的接驳建模；首版步行/交通只计算相邻景点之间，住宿按城市参考价。
