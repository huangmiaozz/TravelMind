from datetime import date, datetime, time

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

# PostgreSQL 用 JSONB，SQLite（测试）用普通 JSON；两者都按结构化文档读写。
JSONDocument = JSON().with_variant(JSONB(), "postgresql")


class Trip(Base):
    """一次单城市旅行的容器。

    v0.3 起 Trip 只保存“目的地”和标题；日期、人数、预算和偏好都属于
    ``PlanVersion``，因此改条件重新规划只新增版本，不覆盖旧版本。
    ``destination_city_name`` 是创建时的城市名快照，便于列表展示；
    ``destination_city_id`` 才是关联城市表的外键。
    """

    __tablename__ = "trips"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    destination_city_id: Mapped[int] = mapped_column(
        ForeignKey("cities.id"), index=True
    )
    destination_city_name: Mapped[str] = mapped_column(String(128))
    # 创建时快照高德 adcode；城市表后来补 adcode 也不会改变旧行程。
    destination_city_adcode: Mapped[str | None] = mapped_column(String(16))
    title: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="trips")
    destination_city: Mapped["City"] = relationship(back_populates="trips")
    plans: Mapped[list["PlanVersion"]] = relationship(
        back_populates="trip",
        cascade="all, delete-orphan",
        order_by="PlanVersion.version_no",
    )


class PlanVersion(Base):
    """某次规划的条件快照与结果快照。

    首版不拆 ``PlanDay/PlanItem/PlanLeg/PlanCost``，而是把完整响应存进
    ``plan_json``；摘要字段单独列出，便于“我的方案”列表和版本比较。
    旧版本只读，重新规划只追加新行。
    """

    __tablename__ = "plan_versions"
    __table_args__ = (
        UniqueConstraint(
            "trip_id", "version_no", name="uq_plan_versions_trip_version"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    version_no: Mapped[int] = mapped_column(Integer)

    status: Mapped[str] = mapped_column(String(16), index=True)
    start_date: Mapped[date] = mapped_column(Date)
    days_count: Mapped[int] = mapped_column(Integer)
    adults_count: Mapped[int] = mapped_column(Integer, default=1)
    children_count: Mapped[int] = mapped_column(Integer, default=0)
    budget_total: Mapped[float] = mapped_column(Numeric(12, 2), default=0)

    total_estimated_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    budget_difference: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    over_budget: Mapped[bool] = mapped_column(Boolean, default=False)
    weather_known: Mapped[bool] = mapped_column(Boolean, default=False)

    request_json: Mapped[dict] = mapped_column(JSONDocument, default=dict)
    plan_json: Mapped[dict] = mapped_column(JSONDocument, default=dict)
    data_snapshot: Mapped[dict] = mapped_column(JSONDocument, default=dict)
    # 用户对餐厅/住宿的选择；与只读的 plan_json 分开保存。
    selection_json: Mapped[dict] = mapped_column(JSONDocument, default=dict)

    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trip: Mapped["Trip"] = relationship(back_populates="plans")


# ---------------------------------------------------------------------------
# 旧版表结构：保留以兼容历史数据，v0.3 的规划结果不再写入这两张表。
# 规范化的 PlanDay / PlanItem / PlanLeg / PlanCost 是后续目标，不阻塞首版。
# ---------------------------------------------------------------------------


class TripDay(Base):
    __tablename__ = "trip_days"
    __table_args__ = (
        UniqueConstraint("trip_id", "day_index", name="uq_trip_days_trip_index"),
        UniqueConstraint("trip_id", "travel_date", name="uq_trip_days_trip_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_id: Mapped[int] = mapped_column(ForeignKey("trips.id"), index=True)
    day_index: Mapped[int] = mapped_column(Integer)
    travel_date: Mapped[date] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    trip: Mapped["Trip"] = relationship()
    itinerary_items: Mapped[list["ItineraryItem"]] = relationship(
        back_populates="trip_day", cascade="all, delete-orphan"
    )


class ItineraryItem(Base):
    __tablename__ = "itinerary_items"
    __table_args__ = (
        UniqueConstraint(
            "trip_day_id", "sequence_no", name="uq_itinerary_day_sequence"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    trip_day_id: Mapped[int] = mapped_column(ForeignKey("trip_days.id"), index=True)
    poi_id: Mapped[int | None] = mapped_column(ForeignKey("pois.id"), index=True)
    start_time: Mapped[time | None] = mapped_column(Time)
    end_time: Mapped[time | None] = mapped_column(Time)
    item_type: Mapped[str] = mapped_column(String(32))
    sequence_no: Mapped[int] = mapped_column(Integer)
    estimated_cost: Mapped[float] = mapped_column(Numeric(12, 2), default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    trip_day: Mapped["TripDay"] = relationship(back_populates="itinerary_items")
