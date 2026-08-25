from __future__ import annotations

import hashlib
import os
from typing import Any

# Cloud edition data adapters.
# Default: demo data only.
# For live use, replace/extend collect_all() with official or authorized feeds
# from NAVER / KB / HOGANGNONO. Do not rely on unstable private endpoints.


def fp(*parts: Any) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()


def demo_rows() -> list[dict[str, Any]]:
    base = [
        ("NAVER", "더포레스트힐", "111동", 640_000_000, 110.0, 84.96, 3, 25, "남동향", "데모 매물", "https://new.land.naver.com/"),
        ("KB", "더포레스트힐", "110동", 630_000_000, 110.0, 84.96, 6, 25, "남동향", "데모 매물", "https://kbland.kr/"),
        ("HOGANGNONO", "더포레스트힐", "110동", 600_000_000, 110.0, 84.96, 1, 25, "남동향", "데모 매물", "https://hogangnono.com/"),
        ("NAVER", "휴먼시아", "204동", 615_000_000, 79.0, 59.8, 9, 20, "남향", "데모 매물", "https://new.land.naver.com/"),
        ("KB", "휴먼시아", "207동", 625_000_000, 81.0, 59.9, 12, 20, "남동향", "데모 매물", "https://kbland.kr/"),
    ]
    out: list[dict[str, Any]] = []
    for i, row in enumerate(base, 1):
        source, complex_name, building, price, supply, exclusive, floor, total, direction, realtor, url = row
        out.append(
            {
                "fingerprint": fp(source, complex_name, building, supply, exclusive, floor),
                "source": source,
                "source_id": f"demo-{i}",
                "complex_name": complex_name,
                "building": building,
                "price": price,
                "supply_m2": supply,
                "exclusive_m2": exclusive,
                "floor": floor,
                "total_floor": total,
                "direction": direction,
                "realtor": realtor,
                "source_url": url,
            }
        )
    return out


def filter_targets(rows: list[dict[str, Any]], cfg: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        if int(row.get("price", 10**18)) > int(cfg["max_price"]):
            continue
        target = next((x for x in cfg["targets"] if x["complex"] in str(row.get("complex_name", ""))), None)
        if not target:
            continue
        pyeong = float(row.get("supply_m2") or 0) / 3.3058
        if abs(pyeong - float(target["target_pyeong"])) <= float(target["tolerance"]):
            out.append(row)
    return out


def collect_all(cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    mode = os.getenv("DATA_MODE", "demo").lower()
    if mode == "demo":
        rows = filter_targets(demo_rows(), cfg)
        return rows, {
            "NAVER": {"status": "demo", "count": sum(1 for x in rows if x["source"] == "NAVER")},
            "KB": {"status": "demo", "count": sum(1 for x in rows if x["source"] == "KB")},
            "HOGANGNONO": {"status": "demo", "count": sum(1 for x in rows if x["source"] == "HOGANGNONO")},
        }

    raise RuntimeError(
        "DATA_MODE=live is not configured. Connect official/authorized source adapters in sources.py first."
    )
