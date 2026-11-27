"""高德适配层测试：全部使用固定响应，不访问真实接口。"""

from datetime import date

import httpx

from app.services.amap import AmapClient


def make_client(handler) -> AmapClient:
    return AmapClient(
        api_key="test-key",
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def test_walking_route_returns_distance_duration() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/direction/walking"
        assert request.url.params["origin"] == "116.397200,39.916300"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "route": {
                    "paths": [
                        {"distance": "2316", "duration": "1853"}
                    ]
                },
            },
        )

    leg = make_client(handler).route(
        (116.3972, 39.9163), (116.4074, 39.9042), "walk"
    )

    assert leg.status == "ok"
    assert leg.distance_m == 2316
    assert leg.duration_s == 1853
    assert leg.walking_distance_m == 2316
    assert leg.is_mock is False


def test_transit_route_parses_fare_and_walking_distance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/direction/transit/integrated"
        assert request.url.params["city"] == "北京"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "route": {
                    "transits": [
                        {
                            "distance": "5200",
                            "duration": "1800",
                            "walking_distance": "1340",
                            "cost": "2.0",
                            "segments": [
                                {
                                    "walking": {
                                        "distance": "300",
                                        "duration": "240",
                                    }
                                },
                                {
                                    "bus": {
                                        "buslines": [
                                            {
                                                "name": "地铁1号线(苹果园--四惠东)",
                                                "type": "地铁线路",
                                                "departure_stop": {"name": "东单"},
                                                "arrival_stop": {"name": "国贸"},
                                                "via_num": "3",
                                                "distance": "4200",
                                                "duration": "900",
                                            }
                                        ]
                                    }
                                },
                                {
                                    "bus": {
                                        "buslines": [
                                            {
                                                "name": "公交1路(四惠枢纽--老山公交场)",
                                                "type": "普通公交线路",
                                                "departure_stop": {"name": "国贸"},
                                                "arrival_stop": {"name": "日坛路"},
                                                "via_num": "2",
                                                "distance": "700",
                                                "duration": "300",
                                            }
                                        ]
                                    }
                                },
                            ],
                        }
                    ]
                },
            },
        )

    leg = make_client(handler).route(
        (116.3972, 39.9163),
        (116.4074, 39.9042),
        "transit",
        city="北京",
        cityd="北京",
    )

    assert leg.status == "ok"
    assert leg.distance_m == 5200
    assert leg.duration_s == 1800
    assert leg.walking_distance_m == 1340
    assert leg.cost_amount == 2.0
    assert leg.cost_basis == "per_person"
    assert [segment.mode for segment in leg.segments] == [
        "walk",
        "subway",
        "bus",
    ]
    assert leg.segments[1].line_name == "地铁1号线(苹果园--四惠东)"
    assert leg.segments[1].departure_stop == "东单"
    assert leg.segments[1].arrival_stop == "国贸"
    assert leg.segments[1].via_stops == 3
    assert leg.segments[2].line_name.startswith("公交1路")


def test_route_failure_does_not_return_fake_distance() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"status": "0", "info": "INVALID_PARAMS", "infocode": "20000"},
        )

    leg = make_client(handler).route(
        (116.3972, 39.9163), (116.4074, 39.9042), "walk"
    )

    assert leg.status == "failed"
    assert leg.distance_m is None
    assert leg.duration_s is None
    assert "INVALID_PARAMS" in (leg.error or "")


def test_transit_requires_city() -> None:
    leg = make_client(lambda request: httpx.Response(500)).route(
        (116.3972, 39.9163), (116.4074, 39.9042), "transit"
    )

    assert leg.status == "failed"
    assert "city" in (leg.error or "")


def test_transit_parser_keeps_all_alternatives() -> None:
    client = make_client(lambda request: httpx.Response(200))
    leg = client._parse_transit(
        {
            "status": "1",
            "route": {
                "transits": [
                    {
                        "distance": "5000",
                        "duration": "1800",
                        "walking_distance": "800",
                        "cost": "2",
                        "segments": [],
                    },
                    {
                        "distance": "5200",
                        "duration": "1500",
                        "walking_distance": "300",
                        "cost": "4",
                        "segments": [],
                    },
                ]
            },
        }
    )

    assert [item.duration_s for item in leg.alternatives] == [1800, 1500]
    assert [item.cost_amount for item in leg.alternatives] == [2.0, 4.0]
    assert leg.duration_s == 1800


def test_bus_line_with_metro_station_name_is_not_subway() -> None:
    segments = AmapClient._parse_transit_segments(
        {
            "segments": [
                {
                    "bus": {
                        "buslines": [
                            {
                                "name": "877路(地铁北土城站--八达岭长城)",
                                "type": "普通公交线路",
                                "departure_stop": {"name": "地铁北土城站"},
                                "arrival_stop": {"name": "八达岭长城"},
                                "via_num": "3",
                            }
                        ]
                    }
                }
            ]
        }
    )

    assert segments[0].mode == "bus"
    assert segments[0].departure_stop == "地铁北土城站"


def test_nearby_hotels_filters_guesthouses() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/place/around"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "pois": [
                    {
                        "name": "示例酒店",
                        "type": "住宿服务;宾馆酒店;宾馆酒店",
                        "typecode": "100100",
                        "location": "119.30,26.08",
                    },
                    {
                        "name": "示例招待所",
                        "type": "住宿服务;旅馆招待所;旅馆招待所",
                        "typecode": "100200",
                        "location": "119.30,26.08",
                    },
                    {
                        "name": "示例青年旅舍",
                        "type": "住宿服务;旅馆招待所;青年旅舍",
                        "typecode": "100201",
                        "location": "119.30,26.08",
                    },
                    {
                        "name": "某大学学术交流中心",
                        "type": "住宿服务;宾馆酒店;宾馆酒店",
                        "typecode": "100100",
                        "location": "119.30,26.08",
                    },
                    {
                        "name": "北京邮电会议中心",
                        "type": "住宿服务;宾馆酒店;宾馆酒店",
                        "typecode": "100100",
                        "location": "119.30,26.08",
                    },
                ],
            },
        )

    hotels = make_client(handler).nearby_hotels((119.30, 26.08), "福州")

    assert [hotel.name for hotel in hotels] == ["示例酒店"]


def test_weather_parses_forecast_days_and_risk() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v3/weather/weatherInfo"
        assert request.url.params["city"] == "350100"
        return httpx.Response(
            200,
            json={
                "status": "1",
                "forecasts": [
                    {
                        "casts": [
                            {
                                "date": "2026-10-30",
                                "dayweather": "晴",
                                "nighttemp": "16",
                                "daytemp": "25",
                            },
                            {
                                "date": "2026-10-31",
                                "dayweather": "小雨",
                                "nighttemp": "18",
                                "daytemp": "22",
                            },
                        ]
                    }
                ],
            },
        )

    days = make_client(handler).weather("350100")

    assert [day.forecast_date for day in days] == [
        date(2026, 10, 30),
        date(2026, 10, 31),
    ]
    assert days[0].risk_level == "low"
    assert days[1].risk_level == "medium"
    assert days[1].temperature_min == 18.0


def test_weather_failure_returns_empty_for_unknown_handling() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "0", "info": "QUOTA"})

    assert make_client(handler).weather("350100") == []


def test_weather_by_date_omits_dates_outside_forecast() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "status": "1",
                "forecasts": [
                    {"casts": [{"date": "2026-10-30", "dayweather": "晴"}]}
                ],
            },
        )

    result = make_client(handler).weather_by_date(
        "350100", [date(2026, 10, 30), date(2026, 11, 5)]
    )

    assert set(result) == {date(2026, 10, 30)}
