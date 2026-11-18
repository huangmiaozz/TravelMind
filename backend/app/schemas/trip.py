from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.plan import PlanVersionSummary


class TripCreate(BaseModel):
    """创建单城市旅行容器。

    ``user_id`` 暂默认 1，对应种子脚本创建的演示用户；接入登录后应改为从
    当前用户上下文读取，而不是由客户端任意指定。
    """

    user_id: int = Field(default=1, gt=0)
    city: str = Field(min_length=1, max_length=128)
    title: str | None = Field(default=None, max_length=200)


class TripUpdate(BaseModel):
    # 目的地由 Trip 固定；换城市请新建 Trip，避免旧版本被悄悄改到另一座城市。
    title: str | None = Field(default=None, min_length=1, max_length=200)


class TripRead(BaseModel):
    id: int
    user_id: int
    destination_city_id: int
    destination_city_name: str
    destination_city_adcode: str | None = None
    title: str
    created_at: datetime
    updated_at: datetime
    plan_count: int = 0
    latest_plan: PlanVersionSummary | None = None


class TripDetail(TripRead):
    plans: list[PlanVersionSummary] = Field(default_factory=list)


class TripList(BaseModel):
    items: list[TripRead]
    total: int
