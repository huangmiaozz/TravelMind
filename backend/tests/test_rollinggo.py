"""RollingGo 酒店价格适配：精确匹配、回退和失败降级。"""

from datetime import date

import httpx

from app.services.rollinggo import RollingGoHotelClient, normalize_hotel_name


def detail_payload(name: str = "示例酒店") -> dict:
    return {
        "success": True,
        "hotelId": 123,
        "name": name,
        "roomRatePlans": [
            {
                "roomName": "标准大床房",
                "averagePrice": 420,
                "cancelPolicy": "免费取消截止至入住前一天",
            },
            {
                "roomName": "高级大床房",
                "averagePrice": 380,
                "cancelPolicy": "不可取消",
            },
        ],
    }


def search_payload(name: str = "示例酒店", price: float = 260) -> dict:
    return {
        "success": True,
        "hotelInformationList": [
            {
                "hotelId": 123,
                "name": name,
                "price": {
                    "hasPrice": True,
                    "lowestPrice": price,
                    "message": f"查价成功。1晚总价：{price}CNY",
                },
            }
        ],
    }


def test_name_normalization_ignores_spacing_and_punctuation() -> None:
    assert normalize_hotel_name(" 示例酒店（前门店） ") == normalize_hotel_name(
        "示例酒店(前门店)"
    )


def test_detail_price_is_used_and_cheapest_room_is_selected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/hoteldetail")
        return httpx.Response(200, json=detail_payload())

    client = RollingGoHotelClient(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )
    price = client.price_for_hotel(
        "示例酒店", check_in=date(2026, 12, 1), nights=1
    )

    assert price is not None
    assert price.amount == 380
    assert price.status == "quoted"
    assert price.source == "rollinggo"
    assert "标准大床房" not in price.note
    assert price.hotel_id == 123


def test_same_hotel_with_different_branch_name_and_matching_address() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/hoteldetail"):
            return httpx.Response(200, json=detail_payload("北京景山花园酒店 (故宫王府井店)"))
        return httpx.Response(
            200,
            json={
                "success": True,
                "hotelInformationList": [
                    {
                        "hotelId": 43719,
                        "name": "北京景山花园酒店 (故宫王府井店)",
                        "address": "景山东街三眼井胡同丙68号院",
                        "price": {
                            "hasPrice": True,
                            "lowestPrice": 1142,
                            "message": "查价成功。1晚总价：1142CNY",
                        },
                    }
                ],
            },
        )

    client = RollingGoHotelClient(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )
    price = client.price_for_hotel(
        "景山花园酒店(三眼井胡同)",
        address="景山东街三眼井胡同丙68号",
        check_in=date(2026, 12, 1),
        nights=1,
    )

    assert price is not None
    assert price.amount == 1142
    assert "同地址" in price.note


def test_same_brand_different_hotel_is_still_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/hoteldetail"):
            return httpx.Response(200, json=detail_payload("大正酒店(北京中关村大钟寺地铁站店)"))
        return httpx.Response(
            200,
            json=search_payload("大正酒店(北京中关村大钟寺地铁站店)", 408),
        )

    client = RollingGoHotelClient(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )

    price = client.price_for_hotel(
        "汉庭酒店(北京中关村大钟寺地铁店)",
        address="中关村大街 1 号",
        check_in=date(2026, 12, 1),
        nights=1,
    )
    assert price is not None
    assert price.status == "not_found"


def test_search_fallback_is_used_when_detail_has_no_rates() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/hoteldetail"):
            return httpx.Response(
                200,
                json={"success": True, "hotelId": 123, "name": "示例酒店", "roomRatePlans": []},
            )
        return httpx.Response(200, json=search_payload())

    client = RollingGoHotelClient(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )
    price = client.price_for_hotel(
        "示例酒店", check_in=date(2026, 12, 1), nights=1
    )

    assert price is not None
    assert price.amount == 260
    assert price.status == "quoted"
    assert calls[-1].endswith("/hotelsearch")


def test_fuzzy_name_mismatch_is_rejected() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/hoteldetail"):
            return httpx.Response(200, json=detail_payload("另一家酒店"))
        return httpx.Response(200, json=search_payload("另一家酒店"))

    client = RollingGoHotelClient(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )

    price = client.price_for_hotel(
        "汉庭酒店(示例店)", check_in=date(2026, 12, 1), nights=1
    )
    assert price is not None
    assert price.status == "not_found"


def test_hotel_without_rates_is_reported_as_no_availability() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/hoteldetail"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "hotelId": 123,
                    "name": "示例酒店",
                    "roomRatePlans": [],
                },
            )
        return httpx.Response(
            200,
            json={
                "success": True,
                "hotelInformationList": [
                    {
                        "hotelId": 123,
                        "name": "示例酒店",
                        "address": "示例路 1 号",
                        "price": {"hasPrice": False, "lowestPrice": None},
                    }
                ],
            },
        )

    client = RollingGoHotelClient(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )
    price = client.price_for_hotel(
        "示例酒店",
        address="示例路 1 号",
        check_in=date(2026, 12, 1),
        nights=1,
    )

    assert price is not None
    assert price.amount is None
    assert price.status == "no_availability"


def test_missing_key_never_calls_provider() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url)
        return httpx.Response(500)

    client = RollingGoHotelClient(api_key="", transport=httpx.MockTransport(handler))

    assert client.configured is False
    assert client.price_for_hotel("示例酒店", check_in=date(2026, 12, 1), nights=1) is None
    assert calls == []


def test_price_is_cached_for_repeated_requests() -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        return httpx.Response(200, json=detail_payload())

    client = RollingGoHotelClient(
        api_key="test-key", transport=httpx.MockTransport(handler)
    )
    args = dict(check_in=date(2026, 12, 1), nights=1)

    assert client.price_for_hotel("示例酒店", **args) is not None
    assert client.price_for_hotel("示例酒店", **args) is not None
    assert len(calls) == 1
