"""静态地图参数、编号标注与失败降级的单元测试。"""

import io

import httpx
import pytest
from PIL import Image

from app.core.config import settings
from app.services.static_map import (
    StaticMapError,
    build_static_map_params,
    fetch_static_map,
)


def test_build_params_centers_and_fits_points() -> None:
    params = build_static_map_params(
        [(116.40, 39.90), (116.41, 39.91)], key="test-key"
    )
    values = dict(params)

    assert values["key"] == "test-key"
    assert values["size"] == "750*420"
    assert values["location"] == "116.405000,39.905000"
    assert 10 <= int(values["zoom"]) <= 16
    assert all(name != "markers" for name, _ in params)


def test_fetch_rejects_non_png_response(monkeypatch) -> None:
    monkeypatch.setattr(settings, "amap_mode", "live")
    monkeypatch.setattr(settings, "amap_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "0", "info": "INVALID"})

    with pytest.raises(StaticMapError):
        fetch_static_map(
            [(116.40, 39.90)],
            client=httpx.Client(transport=httpx.MockTransport(handler)),
        )


def _png() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (750, 420), "white").save(output, format="PNG")
    return output.getvalue()


def test_fetch_draws_numbered_markers(monkeypatch) -> None:
    monkeypatch.setattr(settings, "amap_mode", "live")
    monkeypatch.setattr(settings, "amap_api_key", "test-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_png(), headers={"content-type": "image/png"})

    result = fetch_static_map(
        [(116.40, 39.90), (116.41, 39.91)],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert result.startswith(b"\x89PNG")
    image = Image.open(io.BytesIO(result))
    assert image.size == (750, 420)


def test_mock_mode_returns_local_map_without_http(monkeypatch) -> None:
    monkeypatch.setattr(settings, "amap_mode", "mock")

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("mock 模式不应请求高德")

    result = fetch_static_map(
        [(116.40, 39.90), (116.41, 39.91)],
        client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert result.startswith(b"\x89PNG")
    assert Image.open(io.BytesIO(result)).size == (750, 420)
