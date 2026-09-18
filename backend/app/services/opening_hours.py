"""开放时间文本解析。

高德把开放时间放在一段自然语言里（`biz_ext.opentime2`），各景区写法差异很大。
实测三个北京景点：

    故宫  旺季4月1日至10月31日 周二至周日 08:30-17:00 16:00停止检票，
          淡季11月1日至3月31日 周二至周日 08:30-16:30 15:30停止检票，
          周一全天关闭，节假日营业时间以官方通知为准

    国博  周一全天关闭(法定节假日除外)；11月1日至次年5月31日周二至周日09:00-17:00(16:00停止入馆)；
          6月1日至10月31日周二至周日09:00-17:30(16:30停止入馆)

    北海  周一至周日 06:00-21:00

因此这里只提取排程真正需要的两个事实：**哪天不开门**，以及**开门时段的保守边界**。

「保守」的含义：识别到多组时段（旺季/淡季）时取**交集**。宁可把关门时间判早，
也不能把已经关门的景点当成还开着 —— 前者的代价是少排一个点，
后者会让用户走到门口才发现进不去。

节假日特例、临时公告这类信息用文本表达不出精确规则，本模块**不解析**，
它们保留在原文中 —— 也正因为如此，解析结果的可信度不会给满分。
"""

import re
from dataclasses import dataclass
from datetime import time

WEEKDAYS: tuple[str, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_WEEKDAY_ALIAS = {
    "一": "mon",
    "二": "tue",
    "三": "wed",
    "四": "thu",
    "五": "fri",
    "六": "sat",
    "日": "sun",
    "天": "sun",
}

# 「周一全天关闭」「周三闭馆」这类表述
_CLOSED_RE = re.compile(r"周([一二三四五六日天])\s*(?:全天)?\s*(?:关闭|闭馆|不开放|休息)")

# 「周二至周日 08:30-17:00」；空格可有可无，连接符允许多种写法
_RANGE_RE = re.compile(
    r"周([一二三四五六日天])\s*(?:至|到|-|—|~)\s*周([一二三四五六日天])\s*"
    r"(\d{1,2}):(\d{2})\s*(?:-|—|~|至|到)\s*(\d{1,2}):(\d{2})"
)

# 「周一 09:00-17:00」。前面的负向后顾避免误吃到 _RANGE_RE 里的结束日，
# 否则「周一至周日 06:00-21:00」会被当成单日写法多记一条。
_SINGLE_RE = re.compile(
    r"(?<![至到\-—~])周([一二三四五六日天])\s*"
    r"(\d{1,2}):(\d{2})\s*(?:-|—|~|至|到)\s*(\d{1,2}):(\d{2})"
)


@dataclass(frozen=True)
class ParsedOpeningHours:
    """解析结果。

    `closed_days` 之外的日期统一使用 `open_time` / `close_time` 这组保守边界。
    两者都为 None 时表示**未知** —— 调用方不应据此过滤，而应放行并等待人工核对。
    """

    closed_days: frozenset[str]
    open_time: time | None
    close_time: time | None
    confidence: float
    notes: tuple[str, ...] = ()

    @property
    def has_signal(self) -> bool:
        """是否解析出了可用于排程的信息。"""
        return bool(self.closed_days) or (self.open_time is not None and self.close_time is not None)


def _to_time(hour: str, minute: str) -> time | None:
    """把「08:30」这类文本转成 time，非法值返回 None。"""
    hours, minutes = int(hour), int(minute)
    if hours == 24 and minutes == 0:
        # 公园常见的「24:00」写法，Python 的 time 不接受 24 点
        return time(23, 59)
    try:
        return time(hours, minutes)
    except ValueError:
        return None


def parse_opening_hours(raw: str | None) -> ParsedOpeningHours:
    """从高德 `opentime2` 原文中提取闭馆日与保守开放窗口。"""
    if raw is None or not raw.strip():
        return ParsedOpeningHours(frozenset(), None, None, 0.0, ("无原始文本",))

    text = raw.strip()
    notes: list[str] = []

    closed_days = {
        _WEEKDAY_ALIAS[match.group(1)]
        for match in _CLOSED_RE.finditer(text)
        if match.group(1) in _WEEKDAY_ALIAS
    }

    windows: list[tuple[time, time]] = []
    for match in _RANGE_RE.finditer(text):
        opened = _to_time(match.group(3), match.group(4))
        closed = _to_time(match.group(5), match.group(6))
        if opened is not None and closed is not None and opened < closed:
            windows.append((opened, closed))

    for match in _SINGLE_RE.finditer(text):
        opened = _to_time(match.group(2), match.group(3))
        closed = _to_time(match.group(4), match.group(5))
        if opened is not None and closed is not None and opened < closed:
            windows.append((opened, closed))

    if not windows:
        notes.append("未识别出开放时段，需人工核对原文")
        confidence = 0.3 if closed_days else 0.1
        return ParsedOpeningHours(frozenset(closed_days), None, None, confidence, tuple(notes))

    open_time = max(window[0] for window in windows)
    close_time = min(window[1] for window in windows)

    if open_time >= close_time:
        # 多组时段完全不相交（例如分白天场 / 夜场），保守地退回第一组
        open_time, close_time = windows[0]
        notes.append("多组时段无交集，已退回第一组，需人工核对原文")

    if len(windows) > 1:
        notes.append(
            f"识别到 {len(windows)} 组时段（多为旺季/淡季），已取交集 "
            f"{open_time:%H:%M}-{close_time:%H:%M} 以保持保守"
        )

    confidence = 0.55
    if closed_days:
        confidence += 0.15
    if len(windows) > 1:
        confidence -= 0.1

    return ParsedOpeningHours(
        frozenset(closed_days),
        open_time,
        close_time,
        round(max(0.0, min(1.0, confidence)), 2),
        tuple(notes),
    )
