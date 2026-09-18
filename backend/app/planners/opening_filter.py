"""开放时间过滤与排程约束。

需求原文「七、旅行规划算法」把「开放时间过滤」列为规划流程的一环，
其派生的 REQUIREMENTS.md 展开成两条规则：

  - §11.2「过滤在旅行日期不开放的景点」
  - §11.1「景点开放时间必须满足当日访问窗口」

判定依据是 ``PlanningCandidate.opening_windows``，由数据整合层从 ``OpeningHour``
表填充。这里必须区分**三种**情况，不能混为一谈：

===============  ==============================  ==========================
情况              数据表现                        处理
===============  ==============================  ==========================
当日闭馆          有窗口且 ``is_closed=True``      **排除**
有开放时段        有窗口且有起止时间               可排程，访问须落在时段内
开放时间未知      无窗口 / 该日无记录 / 起止为空    **不据此排除**
===============  ==============================  ==========================

第三种是刻意的。把「不知道」当成「不开门」，会让规划器丢掉大量候选；
而需求原文「二十、非常重要的开发原则」第 1 条要求的是**不冒充**，
不是把未知也当成已知。未知只应影响可信度，不该变成过滤依据 ——
与 `DATA_STRATEGY.md` 第六节「低可信度不参与关键决策」是同一条边界：
放行但标注，而不是静默丢弃。

实测背景（见 `docs/DATA_STRATEGY.md`）：北京 520 个景点里 `opentime2` 覆盖率
82.3%，经解析后真正可用于排程的只有 73.8%。也就是说**约四分之一的候选
本就处于「未知」状态** —— 把它们全部排除是灾难性的。
"""

from dataclasses import dataclass
from datetime import date, time

from app.planners.models import OpeningWindow, PlanningCandidate

# date.weekday() 的索引 -> 星期键。
# 取值必须与 app.services.opening_hours.WEEKDAYS 保持一致。
_DAY_KEYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


@dataclass(frozen=True)
class VisitWindow:
    """某候选在某一日的可访问区间。

    ``known=False`` 表示开放时间**未知**，此时起止时间无意义，
    调用方除「不排除」外不应做任何时间推断。
    """

    known: bool = False
    open_time: time | None = None
    close_time: time | None = None


UNKNOWN_WINDOW = VisitWindow()


def weekday_key(travel_date: date) -> str:
    """把日期转成开放时间表使用的星期键。"""
    return _DAY_KEYS[travel_date.weekday()]


def window_for(
    candidate: PlanningCandidate, travel_date: date
) -> OpeningWindow | None:
    """取候选在指定日期的开放窗口记录；没有任何信息时返回 None。"""
    if not candidate.opening_windows:
        return None
    key = weekday_key(travel_date)
    for window in candidate.opening_windows:
        if window.day_of_week == key:
            return window
    return None


def is_closed_on(candidate: PlanningCandidate, travel_date: date) -> bool:
    """当日是否**明确**闭馆。

    只有拿到明确的 ``is_closed=True`` 才返回 True —— 未知一律返回 False，
    即不排除。这样「不知道」不会被误当成「不开门」。
    """
    window = window_for(candidate, travel_date)
    return window is not None and window.is_closed


def visit_window(candidate: PlanningCandidate, travel_date: date) -> VisitWindow:
    """取可用于排程的访问区间。

    闭馆的候选应先用 :func:`is_closed_on` 过滤掉；
    若仍传进来，这里会返回未知窗口（不排除），由排程阶段的其它约束兜底。
    """
    window = window_for(candidate, travel_date)
    if window is None or window.is_closed:
        return UNKNOWN_WINDOW
    if window.open_time is None or window.close_time is None:
        # 解析器对「只写了时间、没写周几」这类原文会给出 None，
        # 语义是「未知」而不是「全天开放」。
        return UNKNOWN_WINDOW
    return VisitWindow(
        known=True,
        open_time=window.open_time,
        close_time=window.close_time,
    )


def filter_closed_on(
    candidates: list[PlanningCandidate], travel_date: date
) -> list[PlanningCandidate]:
    """删除在旅行日期明确闭馆的候选（§11.2）。

    保持原有顺序 —— 调用方可能已经排过序。
    """
    return [candidate for candidate in candidates if not is_closed_on(candidate, travel_date)]
