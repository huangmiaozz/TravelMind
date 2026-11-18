# TravelMind

> 把下一段路，想得更清楚。

TravelMind 是一个面向国内城市的**单城市多日旅行规划 Demo**。用户输入目的地、日期、天数、人数、预算和偏好后，系统生成可解释、可保存的多日行程，并展示真实路线、天气、步行距离、交通分段、用餐与住宿建议以及费用拆分。

当前仓库是软件工程课程设计项目，验收城市为**福州 + 北京**。

## 当前状态

- 前端与后端已联通：Vue 3 页面调用 FastAPI 接口生成和读取方案。
- 已接入高德 Web 服务：步行/骑行/公交/驾车路线、城市天气、静态顺序图、附近餐厅和附近住宿。
- 高德调用支持三种模式：`mock`（默认，不调用外部接口）、`cache`（缓存优先）、`live`（每次真实调用）。
- 已实现用餐时间块、餐厅推荐弹窗、住宿推荐页和四类费用拆分。
- 后端测试 **155 passed**；前端 `vue-tsc` 和 `vite build` 通过。

### 已实现

- **目的地探索**：3D 地球 → 中国地图 → 规划表单的三屏叙事。
- **多日规划**：开放时间过滤、每日时间窗、每日条目上限、跨日去重、步行上限校验。
- **路线与交通**：相邻景点之间比较步行/骑行、公交、打车；公交保留多个备选并逐段展示上车站、下车站、经停站。
- **天气提示**：按日期取预报；天气中高风险时提示“步行和骑行体验可能受影响”，但不篡改排程时间。
- **用餐**：午餐 12:00–13:00（60 分钟）、晚餐 18:00–19:30（90 分钟）固定预留；景点与用餐冲突时顺延；可按附近餐厅推荐并选择。
- **住宿**：按行程景点中心推荐附近酒店，当前整趟选一家，结构上为后续多晚/多酒店预留。
- **费用**：门票 + 市内交通 + 餐饮 + 住宿；门票未核验时标 unknown，不按 0 元确认。
- **版本**：每次生成保存为新的 `PlanVersion`，旧版本不覆盖。

### 明确未实现

- 官方门票价格/开放时间的完整人工核验（当前 Ticket 为空，页面标“票价待核”）。
- 订票、订座、订房、支付和库存。
- 账号体系、多人协作、跨城交通。
- 酒店价格实时校准；高德返回的人均/评分/房价可能缺失。
- 多酒店/按晚拆分和酒店锚点重排。

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Vue 3 · TypeScript · Vite · ECharts · Three.js（earth-flyline） |
| 后端 | FastAPI · SQLAlchemy 2 · PostgreSQL + PostGIS · Pydantic v2 |
| 外部数据 | 高德地图 Web 服务（路线、天气、POI、静态图） |

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
python scripts/migrate_v03_trips_plans.py   # 旧库升级时执行
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

## 主要接口

```text
POST   /api/v1/trips
GET    /api/v1/trips
POST   /api/v1/trips/{trip_id}/plans
GET    /api/v1/plans/{plan_id}
GET    /api/v1/plans/{plan_id}/days/{day_index}/map
GET    /api/v1/plans/{plan_id}/days/{day_index}/meals/{meal_type}/suggestions
GET    /api/v1/plans/{plan_id}/stays/suggestions
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

- 景点名称、坐标、开放时间原文来自高德 Web 服务；坐标经 GCJ-02 → WGS84 转换后入库。
- 餐厅/酒店来自高德 `place/around`，只作为推荐；价格、评分、营业时间可能缺失或过期。
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
