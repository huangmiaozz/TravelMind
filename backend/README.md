# TravelMind Backend

> 后端子模块文档。项目总览、整体结构与设计说明见 [根 README](../README.md)。

国内版 TravelMind MVP 的 FastAPI 后端。当前阶段包含：

- FastAPI 应用入口和健康检查
- SQLAlchemy 2.x 基础模型
- 共 15 个数据模型：城市、POI、开放时间、门票、酒店、酒店报价、交通方案、交通选项、用户、用户偏好、旅行、行程日、行程项、天气、费用
- Pydantic 请求与响应校验模型
- 数据库会话和初始化入口
- 第一阶段规则加权规划器

## 当前 API

- `GET /health`
- `POST /api/v1/users`
- `GET /api/v1/users/{user_id}`
- `PUT /api/v1/users/{user_id}/preferences`
- `POST|GET /api/v1/trips`
- `GET|PUT|DELETE /api/v1/trips/{trip_id}`
- `GET /api/v1/pois/search`
- `GET /api/v1/pois/{poi_id}`
- `GET /api/v1/weather`
- `GET /api/v1/hotels/search`
- `POST /api/v1/routes/calculate`
- `POST /api/v1/routes/search`
- `POST /api/v1/planner/generate`
- `POST /api/v1/planner/generate-options`
- `POST /api/v1/planner/replan`
- `POST /api/v1/expenses/estimate`

路线接口当前返回明确标记的 `Mock Data - straight-line estimate`，规划接口当前使用规则加权算法。它们不会调用外部地图或天气服务，也不会伪造真实价格和路线。

## 本地运行

在 `backend` 目录执行：

```powershell
python -m pip install -r requirements.txt
# 先配置 PostgreSQL + PostGIS 的 DATABASE_URL
python -m app.db.init_db
python -m app.db.seed_demo
python -m uvicorn app.main:app --reload
```

打开 `http://127.0.0.1:8000/health` 应返回：

```json
{"status":"ok","service":"travelmind-api"}
```

## 测试

```powershell
python -m pytest -q
```

## 数据库说明

POI、城市和酒店模型使用 PostGIS 的 `POINT` 类型，因此数据库初始化必须连接启用了 PostGIS 的 PostgreSQL。当前默认 SQLite 仅用于不执行空间建表的模型和接口单元测试；如果直接执行初始化命令，会得到明确的配置提示，而不是生成不完整的数据库。

## 外部环境待配置

真实持久化验证前需要手动准备 PostgreSQL + PostGIS，并设置：

```powershell
$env:DATABASE_URL = "postgresql+psycopg://user:password@localhost:5432/travelmind"
python -m app.db.init_db
```

高德地图、天气服务和官方数据采集尚未配置 API Key，因此当前不会自动访问这些外部服务。

## 本地演示数据

数据库初始化后可执行：

```powershell
python -m app.db.seed_demo
```

该命令写入的所有记录都标记为 `Mock Data (local demo)`，仅用于本地联调，不代表真实景点、票价、天气或酒店信息。
