"""高德 POI 字段覆盖率普查。

回答一个具体问题：**只靠高德，景点的开放时间和门票价格能拿到多少？**

项目计划要求评估地图数据对景点信息的覆盖情况。本脚本以一批北京景点类型的 POI 实测字段覆盖率，
作为数据补充范围的参考：

  - 各字段的非空比例（坐标 / 地址 / 电话 / biz_ext.* ……）
  - `opentime2` 原文的**可解析率** —— 不只是「有没有」，而是「能不能用」
  - `biz_ext` 里实际出现过哪些键（发现未知字段，而不是靠猜）

注意高德用**空数组 `[]`** 表示「没有这个字段」，不能当成有值。
所以判定必须递归看内容，不能只看键是否存在。

用法::

    cd backend
    python -m scripts.probe_coverage

只从 .env 读取 AMAP_API_KEY，不打印其内容。
"""

import sys
import time

import httpx

from app.core.config import settings
from app.services.opening_hours import parse_opening_hours

REST_BASE = "https://restapi.amap.com"
TIMEOUT = 12.0

CITY = "北京"
CITYLIMIT = "true"
OFFSET = 25  # 高德单页上限
PAGES = 3  # 每个查询取 3 页
CALL_DELAY = 0.5  # 高德 Web 服务 QPS 很低，必须限速

# 用多种入口取样，避免只覆盖某一类景点。
# 类型码两次尝试是刻意的：如果不确定类型码是否有效，就用实测的 count 说话。
QUERIES: list[tuple[str, dict[str, str]]] = [
    ("类型码 110000（风景名胜）", {"types": "110000"}),
    ("类型码 110100（公园广场）", {"types": "110100"}),
    ("关键词·博物馆", {"keywords": "博物馆"}),
    ("关键词·公园", {"keywords": "公园"}),
    ("关键词·景点", {"keywords": "景点"}),
    ("关键词·寺", {"keywords": "寺"}),
    ("关键词·纪念馆", {"keywords": "纪念馆"}),
    ("关键词·美术馆", {"keywords": "美术馆"}),
]

# (响应路径, 显示名)
TRACKED: list[tuple[str, str]] = [
    ("location", "坐标"),
    ("address", "地址"),
    ("tel", "电话"),
    ("typecode", "分类码"),
    ("photos", "图片"),
    ("biz_ext.opentime2", "开放时间原文"),
    ("biz_ext.open_time", "开放时间(结构化)"),
    ("biz_ext.cost", "人均/门票消费"),
    ("biz_ext.rating", "评分"),
]


def dig(poi: dict, path: str) -> object:
    """按点号路径取值，任一层缺失都返回 None。"""
    node: object = poi
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node


def has_value(value: object) -> bool:
    """判断字段是否**真的有内容**。空数组、空串、字符串 "[]" 都算没有。"""
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() not in ("", "[]", "null", "None")
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


class Fetcher:
    """带限速的高德 POI 搜索调用器，同时累计统计。"""

    def __init__(self, client: httpx.Client) -> None:
        self.client = client
        self.calls = 0
        self.failed: list[str] = []

    def search(self, params: dict[str, str]) -> list[dict]:
        """跑完一个查询的所有分页，返回原始 POI 列表（未去重）。"""
        collected: list[dict] = []
        for page in range(1, PAGES + 1):
            query = dict(params)
            query.update(
                {
                    "key": settings.amap_api_key,
                    "city": CITY,
                    "citylimit": CITYLIMIT,
                    "offset": str(OFFSET),
                    "page": str(page),
                    "extensions": "all",  # 不开这个就不返回 biz_ext
                }
            )
            time.sleep(CALL_DELAY)
            try:
                response = self.client.get(REST_BASE + "/v3/place/text", params=query)
                payload = response.json()
                self.calls += 1
            except Exception as exc:  # noqa: BLE001 - 普查要如实记录任何失败
                message = str(exc).replace(settings.amap_api_key or "", "***")
                self.failed.append(f"{type(exc).__name__}: {message[:120]}")
                break

            if str(payload.get("status")) != "1":
                info = payload.get("info")
                code = payload.get("infocode")
                self.failed.append(f"status={payload.get('status')} info={info} infocode={code}")
                # 配额 / QPS 类错误继续跑没有意义
                if code in {"10003", "10021", "10044"}:
                    self.failed.append("（配额或 QPS 受限，已提前停止）")
                    return collected
                break

            pois = payload.get("pois") or []
            if not pois:
                break  # 该查询已无更多结果
            collected.extend(pois)
        return collected


def pct(hit: int, total: int) -> str:
    return f"{hit / total * 100:.1f}%" if total else "—"


def main() -> int:
    try:  # Windows 控制台默认不是 UTF-8，避免中文输出直接崩掉
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[union-attr]
    except Exception:  # noqa: BLE001
        pass

    if not settings.amap_api_key:
        print("未配置 AMAP_API_KEY —— 请在 backend/.env 中填写后重试。")
        return 2

    print(f"高德 POI 字段覆盖率普查 | 城市 {CITY} | Key 已配置（不显示内容）")
    print(f"每查询 {PAGES} 页 × {OFFSET} 条，调用间隔 {CALL_DELAY}s")
    print("=" * 78)

    unique: dict[str, dict] = {}
    per_query: list[tuple[str, int, int, int]] = []  # (查询, 条数, opentime2, cost)
    # biz_ext 每个键的 [出现次数, 非空次数, 首个样例值]
    biz_key_stats: dict[str, list] = {}

    with httpx.Client(timeout=TIMEOUT) as client:
        fetcher = Fetcher(client)
        for label, params in QUERIES:
            pois = fetcher.search(params)
            hits_hours = sum(
                1 for poi in pois if has_value(dig(poi, "biz_ext.opentime2"))
            )
            hits_cost = sum(1 for poi in pois if has_value(dig(poi, "biz_ext.cost")))
            per_query.append((label, len(pois), hits_hours, hits_cost))

            for poi in pois:
                biz = poi.get("biz_ext")
                # 注意：biz_ext 有时是 dict、有时是空列表；值本身也可能是 list 或 str。
                # 因此只能逐键看内容，不能用 Counter.update(biz) —— 那会把**值**当成计数。
                if isinstance(biz, dict):
                    for key, value in biz.items():
                        stats = biz_key_stats.setdefault(key, [0, 0, value])
                        stats[0] += 1
                        if has_value(value):
                            stats[1] += 1
                poi_id = poi.get("id")
                if poi_id and poi_id not in unique:
                    unique[poi_id] = poi

            print(
                f"  {label:<24} 返回 {len(pois):>3} 条"
                f" | 开放时间 {hits_hours:>3} | 消费 {hits_cost:>3}"
            )

    print("=" * 78)
    print(f"调用 {fetcher.calls} 次，去重后 POI {len(unique)} 个")
    if fetcher.failed:
        print("失败记录：")
        for item in fetcher.failed:
            print(f"  · {item}")
    print()

    if not unique:
        print("没有取到任何 POI —— 无法给出覆盖率结论。")
        return 1

    pois = list(unique.values())
    total = len(pois)

    # ---- 字段覆盖率 ----
    print("## 字段覆盖率")
    print()
    print("| 字段 | 有值 | 占比 |")
    print("|---|---:|---:|")
    coverage: dict[str, int] = {}
    for path, label in TRACKED:
        hit = sum(1 for poi in pois if has_value(dig(poi, path)))
        coverage[path] = hit
        print(f"| {label} (`{path}`) | {hit} / {total} | {pct(hit, total)} |")
    print()

    has_biz = sum(1 for poi in pois if has_value(poi.get("biz_ext")))
    print(f"含 `biz_ext` 的 POI：{has_biz} / {total}（{pct(has_biz, total)}）")
    print()

    # ---- 开放时间：从"有原文"到"能用" ----
    print("## 开放时间可用性（关键结论）")
    print()
    with_text = [poi for poi in pois if has_value(dig(poi, "biz_ext.opentime2"))]
    usable = 0
    confidences: list[float] = []
    for poi in with_text:
        raw = str(dig(poi, "biz_ext.opentime2"))
        parsed = parse_opening_hours(raw)
        confidences.append(parsed.confidence)
        if parsed.has_signal:
            usable += 1

    print("| 阶段 | 数量 | 占总 POI |")
    print("|---|---:|---:|")
    print(f"| 有 `opentime2` 原文 | {len(with_text)} | {pct(len(with_text), total)} |")
    print(f"| 解析出有效信号（可用） | {usable} | {pct(usable, total)} |")
    print()
    print(
        f"> 拿到原文不等于能用：**{len(with_text) - usable} 条原文解析不出有效信号**"
        f"（占已获取原文的 {pct(len(with_text) - usable, len(with_text))}）。"
    )
    if confidences:
        print(
            f"> 解析置信度：最低 {min(confidences):.2f} / "
            f"最高 {max(confidences):.2f} / "
            f"均值 {sum(confidences) / len(confidences):.2f}"
        )
    print()

    # ---- 分查询看差异 ----
    print("## 分查询对比")
    print()
    print("| 查询 | 返回 | 开放时间 | 消费 |")
    print("|---|---:|---:|---:|")
    for label, count, hours, cost in per_query:
        print(f"| {label} | {count} | {pct(hours, count)} | {pct(cost, count)} |")
    print()

    # ---- biz_ext 实际字段 ----
    print("## `biz_ext` 实际出现过的键")
    print()
    if biz_key_stats:
        print("| 键 | 出现 | 非空 | 非空占比 | 首个样例 |")
        print("|---|---:|---:|---:|---|")
        for key, (seen, filled, sample) in sorted(
            biz_key_stats.items(), key=lambda item: -item[1][0]
        ):
            shown = str(sample)[:24]
            kind = type(sample).__name__
            print(f"| `{key}` | {seen} | {filled} | {pct(filled, seen)} | `{shown}`（{kind}） |")
    else:
        print("（没有任何 POI 返回 `biz_ext`）")
    print()

    # ---- 原文样例 ----
    print("## `opentime2` 原文样例（前 12 条）")
    print()
    for poi in with_text[:12]:
        raw = str(dig(poi, "biz_ext.opentime2"))
        parsed = parse_opening_hours(raw)
        flag = "可用" if parsed.has_signal else "解析不出"
        name = str(poi.get("name", "?"))[:20]
        print(f"- [{flag}] {name}：`{raw[:70]}`")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
