"""按人工白名单抓取福州/北京演示 POI（只写数据库快照，不做通用爬虫）。

每个城市 16 个候选，名称来自人工挑选的公开景点；高德 place/text 只负责返回
坐标、地址和开放时间原文。脚本输出 JSON，由 seed_city_data.py 落库；运行时
规划不访问本脚本。

用法::

    cd backend
    python -m scripts.fetch_city_pois
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.core.config import settings

OUTPUT = Path(__file__).resolve().parents[1] / "app" / "db" / "city_pois.json"
REST_BASE = "https://restapi.amap.com"

# (查询名, 类别, 兴趣标签, 建议游玩分钟)
CITIES: dict[str, dict] = {
    "北京": {
        "adcode": "110000",
        "center_gcj02": (116.407387, 39.904179),
        "pois": [
            ("故宫博物院", "history", {"history": 1.0, "culture": 0.9}, 180),
            ("中国国家博物馆", "museum", {"history": 0.9, "culture": 1.0}, 150),
            ("天坛公园", "history", {"history": 1.0, "culture": 0.8}, 120),
            ("颐和园", "nature", {"history": 0.8, "nature": 1.0}, 180),
            ("八达岭长城", "history", {"history": 1.0, "nature": 0.8}, 180),
            ("北海公园", "park", {"nature": 1.0, "photography": 0.7}, 90),
            ("景山", "park", {"nature": 0.8, "photography": 0.9}, 60),
            ("恭王府", "history", {"history": 1.0, "culture": 0.8}, 90),
            ("雍和宫", "culture", {"culture": 1.0, "history": 0.7}, 60),
            ("中国科学技术馆", "museum", {"culture": 0.8, "history": 0.4}, 150),
            ("首都博物馆", "museum", {"history": 0.8, "culture": 1.0}, 120),
            ("什刹海", "culture", {"food": 0.8, "culture": 0.7}, 90),
            ("南锣鼓巷", "culture", {"food": 1.0, "culture": 0.6}, 60),
            ("圆明园", "history", {"history": 1.0, "nature": 0.7}, 150),
            ("香山公园", "park", {"nature": 1.0, "photography": 0.8}, 150),
            ("北京动物园", "park", {"nature": 0.9, "photography": 0.5}, 120),
        ],
    },
    "福州": {
        "adcode": "350100",
        "center_gcj02": (119.296494, 26.074508),
        "pois": [
            ("三坊七巷", "history", {"history": 1.0, "culture": 0.9, "food": 0.7}, 150),
            ("福州国家森林公园", "park", {"nature": 1.0, "photography": 0.6}, 180),
            ("鼓山", "nature", {"nature": 1.0, "history": 0.6}, 180),
            ("西湖公园", "park", {"nature": 1.0, "photography": 0.7}, 90),
            ("上下杭历史文化街区", "history", {"history": 0.9, "food": 0.9}, 120),
            ("林则徐纪念馆", "history", {"history": 1.0, "culture": 0.8}, 60),
            ("福建博物院", "museum", {"history": 0.8, "culture": 1.0}, 120),
            ("乌塔公园", "history", {"history": 0.8, "culture": 0.7}, 45),
            ("烟台山", "history", {"history": 0.8, "photography": 0.9}, 90),
            ("福州文庙", "history", {"history": 0.9, "culture": 0.8}, 45),
            ("于山风景区", "park", {"nature": 0.8, "history": 0.7}, 90),
            ("屏山公园", "park", {"nature": 1.0, "history": 0.5}, 60),
            ("左海公园", "park", {"nature": 0.9, "photography": 0.5}, 60),
            ("温泉公园", "park", {"nature": 0.8, "photography": 0.4}, 60),
            ("闽江公园", "park", {"nature": 0.9, "photography": 0.7}, 90),
            ("船政文化景区", "history", {"history": 1.0, "culture": 0.8}, 120),
        ],
    },
}


def fetch_poi(client: httpx.Client, city: str, query: str) -> dict | None:
    params = {
        "key": settings.amap_api_key,
        "keywords": query,
        "city": city,
        "citylimit": "true",
        "offset": 5,
        "page": 1,
        "extensions": "all",
    }
    for attempt in range(2):
        response = client.get(REST_BASE + "/v3/place/text", params=params)
        response.raise_for_status()
        payload = response.json()
        pois = payload.get("pois") or []
        if pois:
            # 优先取名称与查询名一致/包含查询名的条目，避免拿到停车场等附属点。
            for poi in pois:
                if query in (poi.get("name") or ""):
                    return poi
            return pois[0]
        # 高德 QPS 限流时可能返回空列表；稍等重试一次。
        time.sleep(0.4 + attempt * 0.4)
    return None


def main() -> int:
    if not settings.amap_api_key:
        print("AMAP_API_KEY 未配置")
        return 2

    output: dict = {
        "source": "Amap API (place/text)",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "cities": {},
    }
    with httpx.Client(timeout=15.0) as client:
        for city, spec in CITIES.items():
            rows = []
            for query, category, tags, minutes in spec["pois"]:
                poi = fetch_poi(client, city, query)
                if poi is None:
                    print(f"[miss] {city} / {query}")
                    continue
                biz = poi.get("biz_ext") or {}
                rows.append(
                    {
                        "query_name": query,
                        "name": poi.get("name") or query,
                        "category": category,
                        "tags": tags,
                        "visit_minutes": minutes,
                        "location_gcj02": poi.get("location"),
                        "address": poi.get("address"),
                        "type": poi.get("type"),
                        "typecode": poi.get("typecode"),
                        "opening_hours_raw": biz.get("opentime2") or None,
                        "amap_rating": biz.get("rating") or None,
                    }
                )
                print(f"[ok] {city} / {query} -> {poi.get('name')}")
                time.sleep(0.15)
            output["cities"][city] = {
                "adcode": spec["adcode"],
                "center_gcj02": spec["center_gcj02"],
                "pois": rows,
            }

    OUTPUT.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"wrote {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
