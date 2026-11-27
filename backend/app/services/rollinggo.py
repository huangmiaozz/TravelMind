"""RollingGo 酒店实时价格适配。

只使用其酒店搜索/详情接口，不接下单、支付或订单接口。RollingGo 是第三方
供应商，返回价格可能随日期、房型和取消政策变化；失败时保持 unknown，绝不
用估算值冒充实时价。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone

import httpx

from app.core.config import settings

BASE_URL = "https://mcp.rollinggo.cn/mcp"
CACHE_TTL_SECONDS = 30 * 60
REQUEST_TIMEOUT_SECONDS = 15.0

_NAME_CLEAN_RE = re.compile(r"[\s\-—_（）()·.,，。/]+")
_CITY_PREFIXES = (
    "北京",
    "上海",
    "广州",
    "深圳",
    "福州",
    "杭州",
    "成都",
    "西安",
    "南京",
    "重庆",
    "天津",
    "苏州",
    "武汉",
    "长沙",
    "青岛",
    "厦门",
)


def normalize_hotel_name(name: str) -> str:
    return _NAME_CLEAN_RE.sub("", name or "").lower()


def hotel_name_base(name: str) -> str:
    """去掉分店括注和常见城市前缀，用于同酒店不同分店名的匹配。"""
    without_branch = re.sub(r"[(（][^)）]*[)）]\s*$", "", name or "")
    normalized = normalize_hotel_name(without_branch)
    for prefix in _CITY_PREFIXES:
        if normalized.startswith(prefix) and len(normalized) > len(prefix) + 2:
            normalized = normalized[len(prefix):]
            break
    return normalized


def address_matches(left: str | None, right: str | None) -> bool:
    a = normalize_hotel_name(left or "")
    b = normalize_hotel_name(right or "")
    if len(a) < 6 or len(b) < 6:
        return False
    return a.startswith(b) or b.startswith(a) or a in b or b in a


@dataclass(frozen=True)
class HotelPrice:
    amount: float | None
    status: str  # quoted / no_availability / not_found / query_failed
    source: str
    checked_at: str
    note: str
    hotel_id: int | None
    matched_name: str


class RollingGoHotelClient:
    """RollingGo 酒店价格客户端；未配置 Key 时所有查询返回 None。"""

    def __init__(
        self,
        api_key: str | None = None,
        *,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._api_key = api_key if api_key is not None else settings.rollinggo_api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport
        self._cache: dict[tuple, tuple[float, HotelPrice | None]] = {}

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def _post(self, path: str, payload: dict) -> dict:
        if not self._api_key:
            return {}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }
        with httpx.Client(
            timeout=REQUEST_TIMEOUT_SECONDS,
            transport=self._transport,
            trust_env=False,
        ) as client:
            response = client.post(f"{self._base_url}{path}", json=payload, headers=headers)
            response.raise_for_status()
            return response.json()

    def price_for_hotel(
        self,
        name: str,
        *,
        address: str | None = None,
        check_in: date,
        nights: int,
        adults: int = 2,
        children: int = 0,
        rooms: int = 1,
    ) -> HotelPrice | None:
        """按酒店名/地址匹配 RollingGo 的实时最低可订价。

        返回结果会区分 quoted（有价）、no_availability（酒店存在但当前日期
        无房型/无报价）、not_found（未匹配到酒店）和 query_failed。
        """
        if not self.configured or not name or nights < 1:
            return None
        nights = max(1, int(nights))
        key = (
            normalize_hotel_name(name),
            normalize_hotel_name(address or ""),
            check_in.isoformat(),
            nights,
            max(1, adults),
            max(0, children),
            max(1, rooms),
        )
        now = time.time()
        cached = self._cache.get(key)
        if cached is not None and now - cached[0] <= CACHE_TTL_SECONDS:
            return cached[1]

        detail = self._fetch_detail(
            name,
            check_in=check_in,
            nights=nights,
            adults=adults,
            children=children,
            rooms=rooms,
        )
        if detail is not None and detail.amount is not None:
            result = detail
        else:
            search = self._fetch_search(
                name,
                address=address,
                check_in=check_in,
                nights=nights,
                adults=adults,
                children=children,
                rooms=rooms,
            )
            if search is not None and search.status != "not_found":
                result = search
            else:
                result = detail or search or HotelPrice(
                    amount=None,
                    status="not_found",
                    source="rollinggo",
                    checked_at=datetime.now(timezone.utc).isoformat(),
                    note="RollingGo 未匹配到该酒店，未使用其他酒店价格",
                    hotel_id=None,
                    matched_name=name,
                )
        self._cache[key] = (now, result)
        return result

    def _fetch_detail(
        self,
        name: str,
        *,
        check_in: date,
        nights: int,
        adults: int,
        children: int,
        rooms: int,
    ) -> HotelPrice | None:
        try:
            payload = {
                "name": name,
                "dateParam": {
                    "checkInDate": check_in.isoformat(),
                    "checkOutDate": _add_days(check_in, nights).isoformat(),
                },
                "occupancyParam": {
                    "adultCount": max(1, adults),
                    "childCount": max(0, children),
                    "roomCount": max(1, rooms),
                },
                "localeParam": {"countryCode": "CN", "currency": "CNY"},
            }
            data = self._post("/hoteldetail", payload)
        except Exception:
            return HotelPrice(
                amount=None,
                status="query_failed",
                source="rollinggo",
                checked_at=datetime.now(timezone.utc).isoformat(),
                note="RollingGo 查价失败，价格待核",
                hotel_id=None,
                matched_name=name,
            )
        if not data.get("success"):
            return None
        if normalize_hotel_name(str(data.get("name") or "")) != normalize_hotel_name(name):
            return None
        rates = [
            rate
            for rate in data.get("roomRatePlans") or []
            if rate.get("averagePrice") is not None
            and float(rate.get("averagePrice") or 0) > 0
        ]
        if not rates:
            return None
        rate = min(rates, key=lambda item: float(item["averagePrice"]))
        amount = round(float(rate["averagePrice"]), 2)
        cancel = rate.get("cancelPolicy") or "取消政策以供应商页面为准"
        return HotelPrice(
            amount=amount,
            status="quoted",
            source="rollinggo",
            checked_at=datetime.now(timezone.utc).isoformat(),
            note=f"最低可订房型：{rate.get('roomName') or '未命名房型'}；{cancel}",
            hotel_id=int(data["hotelId"]) if data.get("hotelId") is not None else None,
            matched_name=str(data.get("name") or name),
        )

    def _fetch_search(
        self,
        name: str,
        *,
        address: str | None = None,
        check_in: date,
        nights: int,
        adults: int,
        children: int,
        rooms: int,
    ) -> HotelPrice | None:
        try:
            payload = {
                "originQuery": f"查询{name}的房价",
                "place": name,
                "placeType": "酒店",
                "checkInParam": {
                    "adultCount": max(1, adults),
                    "checkInDate": check_in.isoformat(),
                    "stayNights": nights,
                },
                "size": 5,
            }
            data = self._post("/hotelsearch", payload)
        except Exception:
            return HotelPrice(
                amount=None,
                status="query_failed",
                source="rollinggo",
                checked_at=datetime.now(timezone.utc).isoformat(),
                note="RollingGo 查价失败，价格待核",
                hotel_id=None,
                matched_name=name,
            )
        if not data.get("success"):
            return HotelPrice(
                amount=None,
                status="query_failed",
                source="rollinggo",
                checked_at=datetime.now(timezone.utc).isoformat(),
                note="RollingGo 返回查价失败，价格待核",
                hotel_id=None,
                matched_name=name,
            )
        target = normalize_hotel_name(name)
        target_base = hotel_name_base(name)
        for hotel in data.get("hotelInformationList") or []:
            candidate_name = str(hotel.get("name") or "")
            exact = normalize_hotel_name(candidate_name) == target
            same_base = (
                bool(target_base)
                and hotel_name_base(candidate_name) == target_base
                and address_matches(address, hotel.get("address"))
            )
            if not exact and not same_base:
                continue
            price = hotel.get("price") or {}
            hotel_id = (
                int(hotel["hotelId"]) if hotel.get("hotelId") is not None else None
            )
            if not price.get("hasPrice") or price.get("lowestPrice") is None:
                return HotelPrice(
                    amount=None,
                    status="no_availability",
                    source="rollinggo",
                    checked_at=datetime.now(timezone.utc).isoformat(),
                    note="RollingGo 显示该入住日期暂无可订房型/满房",
                    hotel_id=hotel_id,
                    matched_name=candidate_name,
                )
            note = str(price.get("message") or "价格来自 RollingGo")
            if not exact:
                note = f"按同酒店/同地址匹配：{candidate_name}；{note}"
            return HotelPrice(
                amount=round(float(price["lowestPrice"]), 2),
                status="quoted",
                source="rollinggo",
                checked_at=datetime.now(timezone.utc).isoformat(),
                note=note,
                hotel_id=hotel_id,
                matched_name=candidate_name,
            )
        return HotelPrice(
            amount=None,
            status="not_found",
            source="rollinggo",
            checked_at=datetime.now(timezone.utc).isoformat(),
            note="RollingGo 未匹配到该酒店，未使用其他酒店价格",
            hotel_id=None,
            matched_name=name,
        )


def _add_days(value: date, days: int) -> date:
    from datetime import timedelta

    return value + timedelta(days=days)
