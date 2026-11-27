# TravelMind

> 把下一段路，想得更清楚。

TravelMind 是一个面向国内城市的**单城市多日旅行规划 Demo**。用户输入目的地、日期、天数、人数、预算和偏好后，系统生成可解释、可保存的多日行程，并展示真实路线、天气、步行距离、交通分段、用餐与住宿建议以及费用拆分。

当前仓库是软件工程课程设计项目，验收城市为**福州 + 北京**。

## 当前状态

- 前端与后端已联通：Vue 3 页面调用 FastAPI 接口生成和读取方案。
- 已接入高德 Web 服务：步行/骑行/公交/驾车路线、城市天气、静态顺序图、附近餐厅和附近住宿。
- 高德调用支持三种模式：`mock`（默认，不调用外部接口）、`cache`（缓存优先）、`live`（每次真实调用）。
- 已实现用餐时间块、餐厅推荐弹窗、住宿推荐页、四类费用三态、版本历史和选择保存。
- 后端测试 **190 passed**；前端 `vue-tsc` 和 `vite build` 通过。

### 已实现

- **目的地探索**：3D 地球 → 中国地图 → 规划表单的三屏叙事。
- **多日规划**：开放时间过滤、每日时间窗、每日条目上限、跨日去重、步行上限校验。
- **兴趣与节奏**：历史文化/自然风光/本地美食 3 个 0–100 滑动条，以及 0–100 旅行节奏滑动条；节奏会调整每日条目上限和行程缓冲。
- **路线与交通**：相邻景点之间比较步行/骑行、公交、打车；公交按“最快捷”取耗时最短的备选，并逐段展示上车站、下车站、经停站。
- **天气提示**：按日期取预报；天气中高风险时提示“步行和骑行体验可能受影响”，但不篡改排程时间。
- **用餐**：午餐 12:00–14:00（120 分钟，含往返）、晚餐 18:00–19:30（90 分钟）固定预留；景点与用餐冲突时顺延；按“用餐区域 → 区域内餐厅”两级推荐，区域分美食街/商场/商圈，先过实际路线时间闸门；区域内餐厅按评分/连锁/本地精选打标。
- **住宿**：先按高德综合热度取前 25 家，再过滤低评分/超预算/纯宾馆，按档次和区域多样性排序；支持按酒店/品牌名搜索，搜索结果也计算每天首尾通勤。酒店价格由 RollingGo 按入住日期查询；精确名称优先，同基础名且地址一致时可接受，品牌不同或地址不符不挂价；无房型显示“该日期暂无可订房型”，未匹配/查价失败分别标注，超出预算会标记。
- **费用**：门票 + 市内交通 + 餐饮 + 住宿；门票按成人/儿童人数计价，四类费用标 confirmed/quoted/estimated/partial/unknown，未知不按 0 元确认。选择餐厅/酒店后可点“更新花销”，按已选餐厅和 RollingGo 酒店价重算。
- **官方数据**：福州、北京各 5 个重点景点的人工核验票价/开放时间，记录来源、核验日期和 URL；季节价/儿童价无法精确建模时标 estimated。
- **版本与选择**：每次生成保存为新的 `PlanVersion`，旧版本不覆盖；结果页可查看/删除版本，餐厅和住宿选择随版本保存并在重新打开时恢复。
- **订票/订座/订房/支付/库存**：不做，只做推荐和指引。

### 明确未实现

- 账号体系、多人协作、跨城交通。
- 酒店价格依赖 RollingGo 的覆盖和报价；高德酒店 `biz_ext.cost`/`lowest_price` 常为空。RollingGo 无房型时显示“该日期暂无可订房型”，未匹配显示“未匹配到该酒店报价”，接口失败显示“查价失败”，不再统一标“价格待核”。
- 订房、支付、库存承诺不做；RollingGo 只使用搜索/详情接口。
- 多酒店/按晚拆分和酒店锚点重排。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 · TypeScript · Vite · ECharts · Three.js（earth-flyline） |
| 后端 | FastAPI · SQLAlchemy 2 · PostgreSQL + PostGIS · Pydantic v2 |
| 外部数据 | 高德地图 Web 服务（路线、天气、POI、静态图）+ RollingGo Hotel MCP（酒店实时房价） |

## 快速开始

### 环境要求

- Python 3.11+
- Node.js 20+
- PostgreSQL + PostGIS

### 后端

```powershell
cd backend
python -m pip install -r requirements.txt

# 复制模板，填写数据库连接
Copy-Item .env.example .env

python -m app.db.init_db
python scripts/migrate_v03_trips_plans.py       # 旧库升级时执行
python scripts/migrate_v04_ticket_status.py     # 旧库补票价核验字段
python scripts/migrate_v04_plan_selections.py   # 旧库补选择字段
python scripts/seed_city_data.py
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

- 健康检查：`http://127.0.0.1:8000/health`
- 交互式文档：`http://127.0.0.1:8000/docs`
- 测试：`cd backend && python -m pytest -q`

### 前端

```powershell
cd frontend
npm install
npm run dev
```

默认访问 `http://127.0.0.1:5173/`。前端通过 Vite 代理访问 `http://127.0.0.1:8000`，需要后端同时运行。

### 高德调用模式

默认 `AMAP_MODE=mock`：不调用高德，路线/天气/餐厅/住宿使用演示数据，反复调 UI 不消耗配额。

在 `backend/.env` 中切换：

```text
AMAP_MODE=mock    # 本地演示，不请求高德
AMAP_MODE=cache   # 先读进程内缓存，未命中再请求高德
AMAP_MODE=live    # 每次请求高德，不读跨请求缓存
```

修改后重启后端。`cache` 模式缓存：路线 24 小时、天气 30 分钟、餐厅/住宿 6 小时；重启进程会清空。`cache/live` 需要配置 `AMAP_API_KEY`。

### 酒店实时房价

在 `backend/.env` 配置 RollingGo 开发者 Key：

```text
ROLLINGGO_API_KEY=你的key
```

未配置时住宿价格保持 `unknown`，其他功能不受影响。RollingGo 只用于 `searchHotels` / `getHotelDetail`，不做下单和支付。

## 主要接口

```text
POST   /api/v1/trips
GET    /api/v1/trips
POST   /api/v1/trips/{trip_id}/plans
GET    /api/v1/trips/{trip_id}/plans
GET    /api/v1/plans/{plan_id}
GET    /api/v1/plans/{plan_id}/selections
PUT    /api/v1/plans/{plan_id}/selections
DELETE /api/v1/plans/{plan_id}
GET    /api/v1/plans/{plan_id}/days/{day_index}/map
GET    /api/v1/plans/{plan_id}/days/{day_index}/meals/{meal_type}/areas
GET    /api/v1/plans/{plan_id}/days/{day_index}/meals/{meal_type}/areas/{area_id}/restaurants
GET    /api/v1/plans/{plan_id}/days/{day_index}/meals/{meal_type}/areas/{area_id}/restaurants/search?q=烤鸭
GET    /api/v1/plans/{plan_id}/days/{day_index}/meals/{meal_type}/nearby
GET    /api/v1/plans/{plan_id}/days/{day_index}/meals/{meal_type}/nearby/search?q=烤鸭
GET    /api/v1/plans/{plan_id}/stays/suggestions
GET    /api/v1/plans/{plan_id}/stays/search?q=汉庭
```

方案生成后会自动保存版本；修改条件重新生成不会覆盖旧版本。

## 项目结构

```text
TravelMind/
├── README.md
├── AGENTS.md                    # 给后续 AI/开发者的约定
├── docs/
│   ├── PROJECT_PLAN.md          # 需求与范围依据
│   ├── HANDOFF.md               # 当前状态、决策与下一步
│   ├── API_CONTRACT_V0.3.md     # 目标接口契约
│   └── FEASIBILITY_STUDY.md     # 可行性报告
├── backend/
│   ├── app/
│   │   ├── api/v1/              # trips / plans / planner 接口
│   │   ├── planners/            # 排程、评分、交通选择
│   │   ├── services/            # 高德、费用、静态图、缓存
│   │   └── db/                  # 模型、种子数据、城市 POI
│   └── tests/
└── frontend/
    └── src/                     # Vue 3 页面与 API 客户端
```

## 数据说明

- 景点名称、坐标、开放时间原文基础来自高德 Web 服务；重点景点的官方票价/开放时间另存于 `tickets.json`/`openings.json`，并记录来源和核验日期。
- 坐标经 GCJ-02 → WGS84 转换后入库；餐厅/酒店 POI 来自高德 `place/around`，只作为推荐；酒店房价由 RollingGo 按日期查询，价格、库存和取消政策以供应商为准。
- `mock` 模式下所有外部数据均为演示值，方案 notes 和 `data_snapshot` 会显式标 `mock`。
- 未知和估算不会被写成“已确认”。

## Git 分支

- `main`：当前项目基线。
- `develop`：开发集成分支。

```powershell
git switch develop
git pull
```

## 文档

- [当前状态与交接](docs/HANDOFF.md)
- [需求与范围](docs/PROJECT_PLAN.md)
- [接口契约](docs/API_CONTRACT_V0.3.md)
- [可行性研究](docs/FEASIBILITY_STUDY.md)

## 借鉴

- [dongkelun/vue-echarts-map](https://github.com/dongkelun/vue-echarts-map) — 中国地图省份钻取
- [hululuuuuu/GlobeStream3D](https://github.com/hululuuuuu/GlobeStream3D)（npm: `earth-flyline`）— 3D 地球基础

感谢这两个项目的作者。

## 许可

尚未确定。
