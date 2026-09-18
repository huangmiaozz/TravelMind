"""高德地图 Web 服务 API 能力探测（Phase 0 技术验证）。

逐个调用高德的 REST 接口，确认在当前账号下：

  - 接口是否可用 —— 高德用 HTTP 200 + 业务 ``status`` 字段表达成败，两者都要看
  - 返回哪些关键字段（距离、时间、坐标……）
  - 单次耗时，用于判断规划请求里能否同步逐段调用
  - 失败时的 ``info`` / ``infocode``，用于区分是配额、权限还是参数问题

结果决定规划器的交通模型怎么设计 —— 尤其是**公交路径**能否使用，
它直接关系到需求 11.3「优先考虑公共交通」。在验证之前不做任何假设。

用法::

    cd backend
    python -m scripts.probe_amap

只从 .env 读取 AMAP_API_KEY，且不会打印它的内容（异常信息里的 key 也会被抹掉）。
"""

import time
from dataclasses import dataclass, field

import httpx

from app.core.config import settings

REST_BASE = "https://restapi.amap.com"
TIMEOUT = 10.0

# 探测用的一对真实坐标：故宫 -> 中国国家博物馆，直线约 1.4 km
ORIGIN = "116.3972,39.9163"
DESTINATION = "116.4074,39.9042"
CITY = "北京"

# (名称, 用途, 路径, 查询参数)
PROBES: list[tuple[str, str, str, dict[str, str]]] = [
    ("地理编码", "地址 -> 坐标", "/v3/geocode/geo", {"address": "北京市东城区景山前街4号"}),
    ("逆地理编码", "坐标 -> 地址", "/v3/geocode/regeo", {"location": ORIGIN}),
    ("POI 搜索", "关键词 -> POI", "/v3/place/text", {"keywords": "博物馆", "city": CITY}),
    ("驾车路径", "距离 / 时间", "/v3/direction/driving", {"origin": ORIGIN, "destination": DESTINATION}),
    ("步行路径", "距离 / 时间", "/v3/direction/walking", {"origin": ORIGIN, "destination": DESTINATION}),
    # 端点名是 integrated（过去式），不是 integration —— 写错会返回
    # 10002 SERVICE_NOT_AVAILABLE，容易被误判成"账号未开通该服务"
    (
        "公交路径",
        "距离 / 时间 / 换乘 / 票价",
        "/v3/direction/transit/integrated",
        {"origin": ORIGIN, "destination": DESTINATION, "city": CITY, "cityd": CITY},
    ),
    ("骑行路径", "距离 / 时间", "/v4/direction/bicycling", {"origin": ORIGIN, "destination": DESTINATION}),
    (
        "距离测量",
        "1 对多批量距离",
        "/v3/distance",
        {"origins": f"{ORIGIN}|{DESTINATION}", "destination": DESTINATION, "type": "1"},
    ),
]


@dataclass
class Probe:
    name: str
    purpose: str
    http_status: int | None = None
    # v3 接口用 status（"1" 为成功）；v4 接口（如骑行）用 errcode（0 为成功）
    biz_status: str | None = None
    errcode: int | None = None
    info: str | None = None
    infocode: str | None = None
    elapsed_ms: int | None = None
    highlights: list[str] = field(default_factory=list)
    error: str | None = None

    @property
    def ok(self) -> bool:
        if self.error is not None:
            return False
        if self.errcode is not None:
            return self.errcode == 0
        return self.biz_status == "1"

    @property
    def reason(self) -> str:
        """把失败信息拼成一行可读描述。"""
        parts: list[str] = []
        if self.http_status is not None:
            parts.append(f"HTTP {self.http_status}")
        if self.biz_status is not None:
            parts.append(f"status={self.biz_status}")
        if self.errcode is not None:
            parts.append(f"errcode={self.errcode}")
        if self.info:
            parts.append(f"info={self.info}")
        if self.infocode:
            parts.append(f"infocode={self.infocode}")
        return "  ".join(parts) or "（无错误信息）"


def short(value: object, limit: int = 64) -> str:
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize(name: str, payload: dict) -> list[str]:
    """从响应里挑出对设计有决策价值的字段。"""
    if name == "地理编码":
        geocodes = payload.get("geocodes") or []
        if geocodes:
            return [f"匹配 {len(geocodes)} 条；首条 location={geocodes[0].get('location')}"]
    if name == "逆地理编码":
        address = (payload.get("regeocode") or {}).get("formatted_address")
        if address:
            return [f"formatted_address={short(address)}"]
    if name == "POI 搜索":
        pois = payload.get("pois") or []
        if pois:
            return [
                f"count={payload.get('count')}；首条 {short(pois[0].get('name'))} "
                f"@ {pois[0].get('location')}"
            ]

    # 距离测量：results[].distance / duration，支持 1 对多批量查询
    if name == "距离测量":
        results = payload.get("results") or []
        if results:
            return [
                f"返回 {len(results)} 条；首条 "
                f"{results[0].get('distance')} 米 / {results[0].get('duration')} 秒"
            ]
        return []

    # 公交换乘：route.transits。注意 duration 才是时间，cost 是票价（元）
    transits = (payload.get("route") or {}).get("transits") or []
    if transits:
        first = transits[0]
        found: list[str] = []
        if "duration" in first:
            found.append(f"耗时 {first['duration']} 秒")
        if "cost" in first:
            found.append(f"票价 {first['cost']} 元")
        if "walking_distance" in first:
            found.append(f"步行 {first['walking_distance']} 米")
        if first.get("segments"):
            found.append(f"换乘段 {len(first['segments'])} 段")
        return found

    # 路径类：v3 放在 route.paths，v4 骑行放在 data.paths
    paths = (payload.get("route") or {}).get("paths") or (payload.get("data") or {}).get("paths") or []
    if paths:
        first = paths[0]
        found: list[str] = []
        if "distance" in first:
            found.append(f"距离 {first['distance']} 米")
        if "duration" in first:
            found.append(f"耗时 {first['duration']} 秒")
        if first.get("steps"):
            found.append(f"分段 {len(first['steps'])} 段")
        return found
    return []


def run_probe(
    client: httpx.Client, name: str, purpose: str, path: str, params: dict[str, str]
) -> Probe:
    probe = Probe(name=name, purpose=purpose)
    query = dict(params)
    query["key"] = settings.amap_api_key

    started = time.perf_counter()
    try:
        response = client.get(REST_BASE + path, params=query)
        probe.elapsed_ms = int((time.perf_counter() - started) * 1000)
        probe.http_status = response.status_code
        payload = response.json()
    except Exception as exc:  # noqa: BLE001 - 探测脚本要如实记录任何失败
        probe.elapsed_ms = int((time.perf_counter() - started) * 1000)
        # httpx 的异常消息会带上完整 URL（含 key），必须抹掉后再保存
        message = str(exc).replace(settings.amap_api_key or "", "***")
        probe.error = f"{type(exc).__name__}: {short(message, 120)}"
        return probe

    if "status" in payload:  # v3 系列
        probe.biz_status = str(payload.get("status"))
        probe.info = payload.get("info")
        probe.infocode = payload.get("infocode")
    elif "errcode" in payload:  # v4 系列（骑行）
        probe.errcode = payload.get("errcode")
        probe.info = payload.get("errmsg")
    else:
        probe.error = f"响应结构未知，顶层键：{sorted(payload)[:8]}"

    if probe.ok:
        probe.highlights = summarize(name, payload)
    return probe


def main() -> int:
    if not settings.amap_api_key:
        print("未配置 AMAP_API_KEY —— 请在 backend/.env 中填写后重试。")
        return 2

    print(f"高德 Web 服务 API 探测 | Key 已配置（长度 {len(settings.amap_api_key)}，不显示内容）")
    print(f"探测坐标 {ORIGIN} -> {DESTINATION}，城市 {CITY}")
    print("=" * 76)

    results: list[Probe] = []
    with httpx.Client(timeout=TIMEOUT) as client:
        for name, purpose, path, params in PROBES:
            probe = run_probe(client, name, purpose, path, params)
            results.append(probe)

            print(f"[{'可用' if probe.ok else '不可用'}] {name}（{purpose}）  {probe.elapsed_ms} ms")
            if probe.ok:
                for line in probe.highlights or ["（响应成功，但未提取到预期字段）"]:
                    print(f"          · {line}")
            else:
                print(f"          · {probe.error or probe.reason}")
            print()

    print("=" * 76)
    usable = [probe for probe in results if probe.ok]
    print(f"合计 {len(usable)}/{len(results)} 个接口可用")
    if len(usable) < len(results):
        blocked = "、".join(probe.name for probe in results if not probe.ok)
        print(f"不可用：{blocked}")
    return 0 if usable else 1


if __name__ == "__main__":
    raise SystemExit(main())
