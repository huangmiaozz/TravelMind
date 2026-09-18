"""开放时间解析器测试。

样例文案直接取自高德 `biz_ext.opentime2` 的**真实返回**（2026-09-18 实取），
不是编造的 —— 解析器的意义就在于消化这些写法各异的自然语言。
"""

from datetime import time

from app.services.opening_hours import WEEKDAYS, parse_opening_hours

GUGONG = (
    "旺季4月1日至10月31日 周二至周日 08:30-17:00 16:00停止检票，"
    "淡季11月1日至3月31日 周二至周日 08:30-16:30 15:30停止检票，"
    "周一全天关闭，节假日营业时间以官方通知为准"
)
GUOBO = (
    "周一全天关闭(法定节假日除外)；"
    "11月1日至次年5月31日周二至周日09:00-17:00(16:00停止入馆)；"
    "6月1日至10月31日周二至周日09:00-17:30(16:30停止入馆)"
)
BEIHAI = "周一至周日 06:00-21:00"


# —— 真实样例 ——


def test_gugong_closes_on_monday() -> None:
    parsed = parse_opening_hours(GUGONG)

    assert parsed.closed_days == frozenset({"mon"})


def test_gugong_takes_intersection_of_peak_and_off_peak() -> None:
    """旺季 08:30-17:00 与淡季 08:30-16:30 取交集，关门时间取更早的那个。

    保守是有意的：宁可把关门判早，也不能把已关门的景点当成还开着。
    """
    parsed = parse_opening_hours(GUGONG)

    assert parsed.open_time == time(8, 30)
    assert parsed.close_time == time(16, 30)
    assert any("交集" in note for note in parsed.notes)


def test_guobo_closes_on_monday_despite_trailing_parenthesis() -> None:
    """「周一全天关闭(法定节假日除外)」——括号内容不应妨碍识别闭馆日。"""
    parsed = parse_opening_hours(GUOBO)

    assert parsed.closed_days == frozenset({"mon"})


def test_guobo_handles_missing_space_before_time() -> None:
    """国博的写法是「周二至周日09:00-17:00」，周与时间之间没有空格。"""
    parsed = parse_opening_hours(GUOBO)

    assert parsed.open_time == time(9, 0)
    assert parsed.close_time == time(17, 0)


def test_beihai_opens_all_week_without_closed_day() -> None:
    parsed = parse_opening_hours(BEIHAI)

    assert parsed.closed_days == frozenset()
    assert parsed.open_time == time(6, 0)
    assert parsed.close_time == time(21, 0)


def test_weekday_range_is_not_counted_twice_as_single_day() -> None:
    """「周一至周日 06:00-21:00」中的「周日」前面是「至」，不应被单日写法再记一条。"""
    parsed = parse_opening_hours(BEIHAI)

    assert not any("组时段" in note for note in parsed.notes)


def test_real_samples_yield_usable_signal() -> None:
    for raw in (GUGONG, GUOBO, BEIHAI):
        parsed = parse_opening_hours(raw)
        assert parsed.has_signal is True
        assert parsed.confidence > 0.5


# —— 边界 ——


def test_empty_text_yields_zero_confidence_and_no_signal() -> None:
    for raw in (None, "", "   "):
        parsed = parse_opening_hours(raw)

        assert parsed.confidence == 0.0
        assert parsed.has_signal is False


def test_unparseable_text_keeps_closed_days_but_lowers_confidence() -> None:
    """只认出闭馆日、认不出时段时，不应该假装知道开门时间。"""
    parsed = parse_opening_hours("周一闭馆，具体时间以现场公告为准")

    assert parsed.closed_days == frozenset({"mon"})
    assert parsed.open_time is None
    assert parsed.close_time is None
    assert parsed.confidence < 0.5


def test_time_only_text_without_weekday_is_reported_as_unparsed() -> None:
    """「08:00-12:00，14:00-17:30」这类不含周几的写法目前不解析。

    这是当前已知的限制（分时段开放的景点会走到这里）。它降级为「未知」
    而不是猜一个区间 —— 未知时调用方会放行，猜错则可能排出不可行的行程。
    """
    parsed = parse_opening_hours("08:00-12:00，14:00-17:30")

    assert parsed.open_time is None
    assert parsed.has_signal is False
    assert any("未识别" in note for note in parsed.notes)


def test_midnight_written_as_24_00_is_accepted() -> None:
    """公园常写「24:00」，Python 的 time 不接受 24 点，需要折算。"""
    parsed = parse_opening_hours("周一至周日 06:00-24:00")

    assert parsed.close_time == time(23, 59)


def test_disjoint_windows_fall_back_to_first_group() -> None:
    """构造的边界用例：两组时段完全不相交时退回第一组，而不是给出空区间。"""
    parsed = parse_opening_hours(
        "夏季6月1日至8月31日 周一至周日 06:00-12:00，"
        "冬季12月1日至2月28日 周一至周日 14:00-20:00"
    )

    assert parsed.open_time == time(6, 0)
    assert parsed.close_time == time(12, 0)
    assert any("无交集" in note for note in parsed.notes)


def test_closed_day_aliases_cover_sunday_and_tian() -> None:
    assert parse_opening_hours("周日全天关闭").closed_days == frozenset({"sun"})
    assert parse_opening_hours("周天闭馆").closed_days == frozenset({"sun"})


def test_weekdays_constant_covers_seven_days() -> None:
    assert len(WEEKDAYS) == 7
    assert WEEKDAYS[0] == "mon"
    assert WEEKDAYS[-1] == "sun"
