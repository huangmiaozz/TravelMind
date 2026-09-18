"""坐标转换验证。

要回答三个问题：

1. 本地实现的正向转换与高德的转换 API 是否一致？
2. 反向迭代能否把 GCJ-02 还原回 WGS84？
3. 往返残差有多大，能不能忽略？

之所以不拿数据库里的 POI 坐标来验证：那些坐标是早期手写的，本身基准不明、
精度未知（实测与高德 POI 的标注点相差数百米，部分原因是景区占地很大、
标注点与中心点本就不是同一个位置）。用它们做参照只会把两个误差混在一起。

真正需要保证的是**算法的自洽性** —— 因为生产里要走的正是这两条路：
高德取回的 GCJ-02 转成 WGS84 入库，以及把库里的 WGS84 转成 GCJ-02 发给高德。

用法::

    cd backend
    python -m scripts.probe_coord
"""

import time

import httpx

from app.core.config import settings
from app.services.coordinates import (
    gcj02_to_wgs84,
    meters_between,
    wgs84_to_gcj02,
)

CONVERT_URL = "https://restapi.amap.com/v3/assistant/coordinate/convert"
TIMEOUT = 10.0

# 转换 API 的 QPS 很低 —— 实测连续请求会返回 10021 CUQPS_HAS_EXCEEDED_THE_LIMIT。
# 这也正说明生产上应当用本地算法而不是这个接口。
API_CALL_DELAY = 1.2

# 覆盖中国不同区域 —— GCJ-02 的偏移量随位置非线性变化，只测北京说明不了问题
TEST_POINTS: list[tuple[str, float, float]] = [
    ("北京·故宫", 116.3972, 39.9163),
    ("上海·外滩", 121.4737, 31.2304),
    ("广州·珠江新城", 113.3245, 23.1066),
    ("哈尔滨·中央大街", 126.6167, 45.7710),
    ("乌鲁木齐·市中心", 87.6168, 43.8256),
    ("三亚·大东海", 109.5089, 18.2273),
    # 境外点：不应发生偏移
    ("境外·东京", 139.6917, 35.6895),
]


def amap_wgs84_to_gcj02(client: httpx.Client, lon: float, lat: float) -> tuple[float, float]:
    """调用高德的坐标转换 API（coordsys=gps 表示输入是 WGS84）。"""
    response = client.get(
        CONVERT_URL,
        params={
            "locations": f"{lon},{lat}",
            "coordsys": "gps",
            "key": settings.amap_api_key,
        },
    )
    payload = response.json()
    if payload.get("status") != "1":
        raise RuntimeError(
            f"高德转换失败: {payload.get('info')} ({payload.get('infocode')})"
        )
    out_lon, out_lat = str(payload["locations"]).split(",")
    return float(out_lon), float(out_lat)


def main() -> int:
    if not settings.amap_api_key:
        print("未配置 AMAP_API_KEY —— 请在 backend/.env 中填写后重试。")
        return 2

    print("坐标转换验证  |  单位：米")
    print("=" * 92)
    print(f"{'地点':<20}{'本地正向 vs 高德':>20}{'本地往返残差':>18}{'高德正向 + 本地反向':>24}")

    worst_vs_amap = 0.0
    worst_local_roundtrip = 0.0
    worst_api_roundtrip = 0.0
    offset_km: list[float] = []

    with httpx.Client(timeout=TIMEOUT) as client:
        for index, (name, lon, lat) in enumerate(TEST_POINTS):
            # 往返不需要 API
            local_lon, local_lat = wgs84_to_gcj02(lon, lat)
            back_lon, back_lat = gcj02_to_wgs84(local_lon, local_lat)
            local_roundtrip = meters_between(lon, lat, back_lon, back_lat)
            worst_local_roundtrip = max(worst_local_roundtrip, local_roundtrip)

            if index:
                time.sleep(API_CALL_DELAY)
            try:
                amap_lon, amap_lat = amap_wgs84_to_gcj02(client, lon, lat)
            except RuntimeError as exc:
                # API 不可用时保留往返结果，不中断整轮验证
                print(f"{name:<20}{'—':>20}{local_roundtrip:>18.2f}   {exc}")
                continue

            drift = meters_between(local_lon, local_lat, amap_lon, amap_lat)
            api_back_lon, api_back_lat = gcj02_to_wgs84(amap_lon, amap_lat)
            api_roundtrip = meters_between(lon, lat, api_back_lon, api_back_lat)

            worst_vs_amap = max(worst_vs_amap, drift)
            worst_api_roundtrip = max(worst_api_roundtrip, api_roundtrip)
            if not name.startswith("境外"):
                offset_km.append(meters_between(lon, lat, amap_lon, amap_lat) / 1000.0)

            print(f"{name:<20}{drift:>20.2f}{local_roundtrip:>18.2f}{api_roundtrip:>24.2f}")

    print("=" * 92)
    print(f"本地正向与高德 API 的最大偏差 : {worst_vs_amap:.2f} m")
    print(f"本地往返的最大残差           : {worst_local_roundtrip:.2f} m")
    print(f"高德正向 + 本地反向的最大残差 : {worst_api_roundtrip:.2f} m")
    if offset_km:
        print(
            f"境内 WGS84 -> GCJ-02 的实际偏移量: "
            f"{min(offset_km):.2f} ~ {max(offset_km):.2f} km"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
