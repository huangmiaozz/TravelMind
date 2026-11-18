"""高德静态地图代理。

高德静态图本身只负责底图；多标注点用重复 ``markers`` 参数时只会保留一个，
因此这里先取无标注底图，再用 Pillow 按 Web Mercator 投影画 1→2→3 编号。
失败时抛 ``StaticMapError``，由调用方降级为顺序列表。
"""

from __future__ import annotations

import io
import math

import httpx
from PIL import Image, ImageDraw, ImageFont

from app.core.config import settings

STATIC_MAP_URL = "https://restapi.amap.com/v3/staticmap"
MAP_WIDTH = 750
MAP_HEIGHT = 420
MARKER_COLOR = "#E8A33D"
INK_COLOR = "#0D1820"


class StaticMapError(RuntimeError):
    pass


def _fit_zoom(
    points: list[tuple[float, float]], width: int, height: int
) -> int:
    if len(points) <= 1:
        return 14
    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    lon_span = max(lons) - min(lons)
    lat_span = max(lats) - min(lats)
    mean_lat = math.radians((max(lats) + min(lats)) / 2)
    for zoom in range(16, 9, -1):
        pixels_per_degree = 256 * (2**zoom) / 360
        span_x = lon_span * pixels_per_degree
        span_y = lat_span * pixels_per_degree / max(0.2, math.cos(mean_lat))
        if span_x <= width - 120 and span_y <= height - 120:
            return zoom
    return 10


def build_static_map_params(
    points: list[tuple[float, float]],
    *,
    key: str,
    size: str = f"{MAP_WIDTH}*{MAP_HEIGHT}",
    zoom: int | None = None,
) -> list[tuple[str, str]]:
    """points 为 GCJ-02 的 (经度, 纬度)；底图不带 marker。"""
    if not points:
        raise StaticMapError("no points for static map")

    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    center_lon = (max(lons) + min(lons)) / 2
    center_lat = (max(lats) + min(lats)) / 2
    width, height = (int(value) for value in size.split("*"))
    return [
        ("key", key),
        ("location", f"{center_lon:.6f},{center_lat:.6f}"),
        ("zoom", str(zoom if zoom is not None else _fit_zoom(points, width, height))),
        ("size", size),
    ]


def _project(
    lon: float,
    lat: float,
    *,
    center_lon: float,
    center_lat: float,
    zoom: int,
    width: int,
    height: int,
) -> tuple[float, float]:
    world = 256 * (2**zoom)
    x = (lon + 180.0) / 360.0 * world
    sin_lat = math.sin(math.radians(lat))
    y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * world
    center_x = (center_lon + 180.0) / 360.0 * world
    center_sin = math.sin(math.radians(center_lat))
    center_y = (
        0.5 - math.log((1 + center_sin) / (1 - center_sin)) / (4 * math.pi)
    ) * world
    return x - center_x + width / 2, y - center_y + height / 2


def _font(size: int) -> ImageFont.ImageFont:
    for path in (
        "C:/Windows/Fonts/arialbd.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def draw_numbered_markers(
    image_bytes: bytes,
    points: list[tuple[float, float]],
    *,
    center: tuple[float, float],
    zoom: int,
) -> bytes:
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)
    font = _font(14)
    for index, (lon, lat) in enumerate(points, start=1):
        x, y = _project(
            lon,
            lat,
            center_lon=center[0],
            center_lat=center[1],
            zoom=zoom,
            width=image.width,
            height=image.height,
        )
        radius = 13
        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=MARKER_COLOR,
            outline=INK_COLOR,
            width=3,
        )
        label = str(index)
        left, top, right, bottom = draw.textbbox((0, 0), label, font=font)
        draw.text(
            (x - (right - left) / 2, y - (bottom - top) / 2 - top),
            label,
            fill=INK_COLOR,
            font=font,
        )
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def fetch_static_map(
    points: list[tuple[float, float]],
    *,
    size: str = f"{MAP_WIDTH}*{MAP_HEIGHT}",
    zoom: int | None = None,
    client: httpx.Client | None = None,
) -> bytes:
    if settings.amap_mode == "mock":
        return _mock_map(points, size=size, zoom=zoom)
    if not settings.amap_api_key:
        raise StaticMapError("AMAP_API_KEY is not configured")

    params = build_static_map_params(
        points, key=settings.amap_api_key, size=size, zoom=zoom
    )
    owns_client = client is None
    http = client or httpx.Client(timeout=15.0, trust_env=False)
    try:
        response = http.get(STATIC_MAP_URL, params=params)
        response.raise_for_status()
    except Exception as exc:  # noqa: BLE001 - 外部服务失败统一转成可降级错误
        raise StaticMapError(f"static map request failed: {exc}") from exc
    finally:
        if owns_client:
            http.close()

    if not response.content.startswith(b"\x89PNG"):
        raise StaticMapError("static map response is not a PNG")

    center_lon = float(dict(params)["location"].split(",")[0])
    center_lat = float(dict(params)["location"].split(",")[1])
    return draw_numbered_markers(
        response.content,
        points,
        center=(center_lon, center_lat),
        zoom=int(dict(params)["zoom"]),
    )


def _mock_map(
    points: list[tuple[float, float]],
    *,
    size: str,
    zoom: int | None,
) -> bytes:
    """Mock 模式下的本地示意图，不访问高德。"""
    width, height = (int(value) for value in size.split("*"))
    image = Image.new("RGB", (width, height), "#e8efeb")
    draw = ImageDraw.Draw(image)
    for x in range(0, width, 60):
        draw.line((x, 0, x, height), fill="#d5dfd9", width=1)
    for y in range(0, height, 60):
        draw.line((0, y, width, y), fill="#d5dfd9", width=1)
    draw.line((0, height * 0.7, width, height * 0.35), fill="#f3d9a4", width=4)
    draw.line((width * 0.2, 0, width * 0.55, height), fill="#c7d8cf", width=6)
    draw.text((18, 16), "MOCK MAP · 未调用高德", fill="#5f7469", font=_font(13))

    lons = [point[0] for point in points]
    lats = [point[1] for point in points]
    center = ((max(lons) + min(lons)) / 2, (max(lats) + min(lats)) / 2)
    fitted_zoom = zoom if zoom is not None else _fit_zoom(points, width, height)

    output = io.BytesIO()
    image.save(output, format="PNG")
    return draw_numbered_markers(
        output.getvalue(),
        points,
        center=center,
        zoom=fitted_zoom,
    )
