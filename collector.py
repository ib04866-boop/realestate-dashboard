from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sources import collect_all

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
LISTINGS_FILE = DATA_DIR / "listings.json"
HISTORY_FILE = DATA_DIR / "history.json"
KST = timezone(timedelta(hours=9))

TARGETS = {
    "transaction_type": "매매",
    "property_type": "아파트",
    "max_price": 660_000_000,
    "targets": [
        {"complex": "더포레스트힐", "dong": "비산동", "target_pyeong": 33, "tolerance": 2},
        {"complex": "휴먼시아", "dong": "비산동", "target_pyeong": 24, "tolerance": 2},
    ],
}


def now_iso() -> str:
    return datetime.now(KST).isoformat(timespec="seconds")


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    ts = now_iso()
    previous = load_json(LISTINGS_FILE, {"listings": []})
    previous_map = {x.get("fingerprint"): x for x in previous.get("listings", [])}
    history = load_json(HISTORY_FILE, {"events": []})

    rows, source_status = collect_all(TARGETS)
    current: list[dict[str, Any]] = []
    seen = set()
    new_count = 0
    price_changed = 0

    for row in rows:
        fp = row["fingerprint"]
        seen.add(fp)
        old = previous_map.get(fp)
        item = dict(row)
        item["first_seen_at"] = old.get("first_seen_at", ts) if old else ts
        item["last_seen_at"] = ts
        item["active"] = True
        if old is None:
            new_count += 1
            history["events"].append({"type": "new", "fingerprint": fp, "price": row["price"], "at": ts})
        elif int(old.get("price", row["price"])) != int(row["price"]):
            price_changed += 1
            history["events"].append(
                {
                    "type": "price_change",
                    "fingerprint": fp,
                    "old_price": old.get("price"),
                    "price": row["price"],
                    "at": ts,
                }
            )
        current.append(item)

    for fp, old in previous_map.items():
        if fp not in seen:
            history["events"].append({"type": "inactive", "fingerprint": fp, "price": old.get("price"), "at": ts})

    # Keep history reasonably small for a static site.
    history["events"] = history["events"][-2000:]
    payload = {
        "generated_at": ts,
        "mode": "demo" if all(v.get("status") == "demo" for v in source_status.values()) else "live",
        "targets": TARGETS,
        "stats": {"active": len(current), "new": new_count, "price_changed": price_changed},
        "sources": source_status,
        "listings": sorted(current, key=lambda x: (x["price"], x["complex_name"], x["source"])),
    }
    save_json(LISTINGS_FILE, payload)
    save_json(HISTORY_FILE, history)
    print(f"updated {len(current)} listings at {ts}")


if __name__ == "__main__":
    main()
