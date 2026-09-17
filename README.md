# TravelMind

> 把下一段路，想得更清楚。

国内旅行规划系统。把用户约束、可追溯的旅行数据与规划算法连起来，生成**可比较、可解释、可调整**的旅行方案。

当前版本 **v0.1.0（初步开发 Demo）**：前端叙事与地图体验已完成，后端 API 与规则规划器可独立运行，两端尚未联通。

## 功能

**沉浸式目的地探索**（概览页）

`3D 地球  →  中国地图  →  规划表单`，三屏滚动叙事，每屏一屏高，滚轮逐屏切换。

- 可拖拽旋转的 3D 地球，松手后带惯性滑行，旋转被限制在地球南北极之间
- 地球转向中国后放大淡出，中国地图随之淡入接管
- 中国地图支持点击省份下钻，逐级查看并返回全国

**旅行规划**

- 设定出发地、目的地、日期、天数、预算与交通偏好
- 节奏偏好多选：历史文化 / 自然风光 / 本地美食 / 慢一点
- 结果页预留四种方案取向：综合最优 / 更省钱 / 更舒适 / 兴趣优先

## 技术栈

| | |
|---|---|
| 前端 | Vue 3 · TypeScript · Vite · ECharts · Three.js（经 earth-flyline） |
| 后端 | FastAPI · SQLAlchemy 2 · PostgreSQL + PostGIS · Pydantic |

## 快速开始

### 前端

```powershell
cd frontend
npm install
npm run dev
```

自包含运行，不需要后端。

### 后端

需要启用了 PostGIS 的 PostgreSQL。

```powershell
cd backend
python -m pip install -r requirements.txt

$env:DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/travelmind"
python -m app.db.init_db
python -m app.db.seed_demo
python -m uvicorn app.main:app --reload
```

- 健康检查：`http://127.0.0.1:8000/health`
- 交互式文档：`http://127.0.0.1:8000/docs`
- 测试：`python -m pytest -q`

更多后端细节见 [`backend/README.md`](./backend/README.md)。

## 项目结构

```text
TravelMind/
├── PRODUCT.md      # 产品定义：用户、目标、设计原则
├── DESIGN.md       # 设计系统：色板、字体、动效
├── docs/           # 需求基线与路线图
├── frontend/       # Vue 3 前端
└── backend/        # FastAPI 后端
```

需求基线与开发进度见 [`docs/ROADMAP.md`](./docs/ROADMAP.md)。

## 数据说明

当前版本不接入真实外部数据源。路线为直线估算，演示数据明确标记为 mock —— 刻意不伪造票价、路线与天气。相关接口会返回明确的 mock 标记，而不是看起来像真数据的假值。

## 借鉴

- [dongkelun/vue-echarts-map](https://github.com/dongkelun/vue-echarts-map) — 中国地图省份钻取的实现思路
- [hululuuuuu/GlobeStream3D](https://github.com/hululuuuuu/GlobeStream3D)（npm: `earth-flyline`）— 3D 地球组件基础

感谢这两个项目的作者。

## 许可

尚未确定。
