"""GCJ-02 与 WGS84 坐标转换。

高德所有接口的输入与输出都是 **GCJ-02**（俗称火星坐标），而本项目的数据库用
**WGS84**（`SRID 4326`）。两者不能混用 —— 在北京同一地点的两种坐标相差约 500 米，
足以让路径规划走错路口。

高德的「坐标转换 API」只支持**单向**：把其他坐标系转成 GCJ-02。
把 GCJ-02 转回 WGS84 需要自己实现，因此本模块提供双向转换。
（这一点是实测确认的，见 `docs/API_FEASIBILITY.md`。）

算法是偏移量的公开形式：

- **正向**（WGS84 -> GCJ-02）是闭式公式，直接算出偏移量；
- **反向**（GCJ-02 -> WGS84）没有解析解，用不动点迭代逼近：
  把当前的 WGS84 估计值正向变换后与目标比较，差量作为修正。

中国境外不做偏移 —— GCJ-02 的加密只在国境内生效。
"""

import math

# 克拉索夫斯基椭球参数（该偏移算法固定使用这套参数，与 WGS84 椭球不同）
_ELLIPSOID_A = 6378245.0
_ELLIPSOID_EE = 0.00669342162296594323

# 反向迭代次数。实测 3 次即可把残差压到 1 米以内，再增加收益极小。
DEFAULT_ITERATIONS = 3


def is_out_of_china(lon: float, lat: float) -> bool:
    """粗略判断是否在中国境外。境外不做偏移。"""
    return not (73.66 < lon < 135.05 and 3.86 < lat < 53.55)


def _delta_lat(x: float, y: float) -> float:
    delta = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * math.sqrt(abs(x))
    delta += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    delta += (20.0 * math.sin(y * math.pi) + 40.0 * math.sin(y / 3.0 * math.pi)) * 2.0 / 3.0
    delta += (160.0 * math.sin(y / 12.0 * math.pi) + 320.0 * math.sin(y * math.pi / 30.0)) * 2.0 / 3.0
    return delta


def _delta_lon(x: float, y: float) -> float:
    delta = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * math.sqrt(abs(x))
    delta += (20.0 * math.sin(6.0 * x * math.pi) + 20.0 * math.sin(2.0 * x * math.pi)) * 2.0 / 3.0
    delta += (20.0 * math.sin(x * math.pi) + 40.0 * math.sin(x / 3.0 * math.pi)) * 2.0 / 3.0
    delta += (150.0 * math.sin(x / 12.0 * math.pi) + 300.0 * math.sin(x / 30.0 * math.pi)) * 2.0 / 3.0
    return delta


def wgs84_to_gcj02(lon: float, lat: float) -> tuple[float, float]:
    """WGS84 转 GCJ-02。"""
    if is_out_of_china(lon, lat):
        return lon, lat

    d_lat = _delta_lat(lon - 105.0, lat - 35.0)
    d_lon = _delta_lon(lon - 105.0, lat - 35.0)

    rad_lat = lat / 180.0 * math.pi
    magic = math.sin(rad_lat)
    magic = 1 - _ELLIPSOID_EE * magic * magic
    sqrt_magic = math.sqrt(magic)

    d_lat = (d_lat * 180.0) / ((_ELLIPSOID_A * (1 - _ELLIPSOID_EE)) / (magic * sqrt_magic) * math.pi)
    d_lon = (d_lon * 180.0) / (_ELLIPSOID_A / sqrt_magic * math.cos(rad_lat) * math.pi)
    return lon + d_lon, lat + d_lat


def gcj02_to_wgs84(
    lon: float, lat: float, *, iterations: int = DEFAULT_ITERATIONS
) -> tuple[float, float]:
    """GCJ-02 转 WGS84（不动点迭代）。

    每轮把当前的 WGS84 估计值正向变换到 GCJ-02，与目标求差并修正。
    因为正向变换的偏移量随位置缓慢变化，迭代收敛很快。
    """
    if is_out_of_china(lon, lat):
        return lon, lat

    est_lon, est_lat = lon, lat
    for _ in range(iterations):
        fwd_lon, fwd_lat = wgs84_to_gcj02(est_lon, est_lat)
        est_lon += lon - fwd_lon
        est_lat += lat - fwd_lat
    return est_lon, est_lat


def meters_between(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """两个坐标间的近似地面距离（米）。

    用等距圆柱投影的局部近似，在几百米到几公里的尺度上误差远小于 1%。
    仅供校验与展示使用，规划用的真实距离一律走高德的路径规划接口。
    """
    mean_lat = math.radians((lat1 + lat2) / 2.0)
    dx = (lon2 - lon1) * 111_320.0 * math.cos(mean_lat)
    dy = (lat2 - lat1) * 110_574.0
    return math.hypot(dx, dy)
