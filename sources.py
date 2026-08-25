from __future__ import annotations

import hashlib
import json
import random
import re
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


BISAN_CORTAR_NO = "4117310100"

BASE = "https://new.land.naver.com"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Referer": "https://new.land.naver.com/complexes",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

# 네이버의 실제 단지명과 우리 화면에서 사용할 이름
TARGET_COMPLEXES = {
    "더포레스트힐": [
        "더포레스트힐",
    ],
    "휴먼시아": [
        "안양임곡휴먼시아",
        "임곡휴먼시아",
        "휴먼시아",
    ],
}


def fp(*parts: Any) -> str:
    return hashlib.sha1(
        "|".join(map(str, parts)).encode("utf-8")
    ).hexdigest()


def request_json(url: str, retries: int = 1) -> dict[str, Any]:
    print(f"[NAVER] request: {url}", flush=True)

    try:
        req = Request(url, headers=HEADERS)

        with urlopen(req, timeout=8) as response:
            print(f"[NAVER] status={response.status}", flush=True)

            raw = response.read().decode("utf-8")
            print(f"[NAVER] received {len(raw)} bytes", flush=True)

            return json.loads(raw)

    except HTTPError as e:
        print(f"[NAVER] HTTP ERROR {e.code}: {e.reason}", flush=True)
        raise

    except URLError as e:
        print(f"[NAVER] URL ERROR: {e}", flush=True)
        raise

    except TimeoutError:
        print("[NAVER] TIMEOUT after 8 seconds", flush=True)
        raise

    except Exception as e:
        print(f"[NAVER] ERROR: {type(e).__name__}: {e}", flush=True)
        raise


def parse_price(value: Any) -> int:
    """
    네이버 가격을 원 단위 integer로 변환.
    예:
      6억 3,000 -> 630000000
      63000     -> 630000000 (만원 단위)
    """

    if value is None:
        return 0

    if isinstance(value, (int, float)):
        n = int(value)

        # API 값이 만원 단위인 경우
        if 0 < n < 10_000_000:
            return n * 10_000

        return n

    s = str(value).strip().replace(",", "").replace(" ", "")

    if not s:
        return 0

    total = 0

    billion = re.search(r"(\d+(?:\.\d+)?)억", s)
    if billion:
        total += int(float(billion.group(1)) * 100_000_000)

    rest = re.sub(r".*?억", "", s) if "억" in s else s
    man = re.search(r"(\d+(?:\.\d+)?)만?", rest)

    if man:
        total += int(float(man.group(1)) * 10_000)

    if total:
        return total

    digits = re.sub(r"[^\d]", "", s)

    if not digits:
        return 0

    n = int(digits)

    if n < 10_000_000:
        return n * 10_000

    return n


def normalize_float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def get_complexes() -> list[dict[str, Any]]:
    print("[NAVER] 비산동 단지 목록 조회 시작", flush=True)
    """
    비산동의 아파트 단지 목록 조회.
    네이버 API 형태가 변경될 가능성을 고려해
    여러 응답 키를 처리한다.
    """

    candidates = [
        (
            f"{BASE}/api/regions/complexes?"
            + urlencode({
                "cortarNo": BISAN_CORTAR_NO,
                "realEstateType": "APT",
            })
        ),
        (
            f"{BASE}/api/complexes/single-markers/2.0?"
            + urlencode({
                "cortarNo": BISAN_CORTAR_NO,
                "zoom": 15,
                "realEstateType": "APT",
                "tradeType": "A1",
                "priceType": "RETAIL",
            })
        ),
    ]

    errors = []

    for url in candidates:
        try:
            data = request_json(url)

            for key in (
                "complexList",
                "complexes",
                "result",
                "markers",
            ):
                value = data.get(key)

                if isinstance(value, list) and value:
                    return value

        except Exception as e:
            errors.append(str(e))

    raise RuntimeError(
        "비산동 단지 목록을 가져오지 못했습니다. "
        + " | ".join(errors)
    )


def complex_name(row: dict[str, Any]) -> str:
    return str(
        row.get("complexName")
        or row.get("complex_name")
        or row.get("name")
        or row.get("markerName")
        or ""
    ).strip()


def complex_no(row: dict[str, Any]) -> str:
    value = (
        row.get("complexNo")
        or row.get("complex_no")
        or row.get("id")
    )

    return str(value or "").strip()


def find_target_complexes(
    complexes: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:

    found: dict[str, dict[str, Any]] = {}

    for display_name, aliases in TARGET_COMPLEXES.items():
        for row in complexes:
            name = complex_name(row)

            if any(alias in name for alias in aliases):
                if complex_no(row):
                    found[display_name] = row
                    break

    missing = [
        name for name in TARGET_COMPLEXES
        if name not in found
    ]

    if missing:
        names = [
            complex_name(x)
            for x in complexes
            if complex_name(x)
        ]

        raise RuntimeError(
            "대상 단지를 찾지 못했습니다: "
            + ", ".join(missing)
            + " / 검색된 단지 일부: "
            + ", ".join(names[:30])
        )

    return found


def article_request(
    complex_id: str,
    page: int,
) -> dict[str, Any]:

    params = {
        "realEstateType": "APT",
        "tradeType": "A1",
        "tag": "::::::::",
        "rentPriceMin": 0,
        "rentPriceMax": 900000000,
        "priceMin": 0,
        "priceMax": 66000,
        "areaMin": 0,
        "areaMax": 900000000,
        "showArticle": "false",
        "sameAddressGroup": "false",
        "priceType": "RETAIL",
        "page": page,
        "complexNo": complex_id,
        "type": "list",
        "order": "rank",
    }

    # 현재 가장 흔히 사용되는 단지별 매물 경로
    url = (
        f"{BASE}/api/articles/complex/{complex_id}?"
        + urlencode(params)
    )

    return request_json(url)


def get_articles(complex_id: str) -> list[dict[str, Any]]:
    print(f"[NAVER] complexNo={complex_id} 매물 조회 시작", flush=True)
    all_rows: list[dict[str, Any]] = []

    for page in range(1, 11):
        data = article_request(complex_id, page)

        rows = (
            data.get("articleList")
            or data.get("articles")
            or data.get("list")
            or []
        )

        if not isinstance(rows, list):
            rows = []

        all_rows.extend(rows)

        more = data.get("isMoreData")

        if more is False or not rows:
            break

        time.sleep(random.uniform(1.2, 2.0))

    return all_rows


def convert_article(
    article: dict[str, Any],
    display_complex_name: str,
) -> dict[str, Any] | None:

    article_no = str(
        article.get("articleNo")
        or article.get("article_no")
        or ""
    )

    if not article_no:
        return None

    price = parse_price(
        article.get("dealOrWarrantPrc")
        or article.get("dealPrice")
        or article.get("price")
    )

    if price <= 0:
        return None

    building = (
        article.get("buildingName")
        or article.get("building")
        or article.get("dongName")
        or ""
    )

    supply = normalize_float(
        article.get("area1")
        or article.get("supplyArea")
        or article.get("spc1")
    )

    exclusive = normalize_float(
        article.get("area2")
        or article.get("exclusiveArea")
        or article.get("spc2")
    )

    floor_info = str(
        article.get("floorInfo")
        or article.get("floor")
        or ""
    )

    floor = None
    total_floor = None

    if "/" in floor_info:
        a, b = floor_info.split("/", 1)

        try:
            floor = int(re.sub(r"[^\d-]", "", a))
        except Exception:
            pass

        try:
            total_floor = int(re.sub(r"[^\d-]", "", b))
        except Exception:
            pass

    direction = (
        article.get("direction")
        or article.get("directionName")
        or ""
    )

    realtor = (
        article.get("realtorName")
        or article.get("cpName")
        or article.get("realtor")
        or ""
    )

    return {
        "fingerprint": fp("NAVER", article_no),
        "source": "NAVER",
        "source_id": article_no,
        "complex_name": display_complex_name,
        "building": building,
        "price": price,
        "supply_m2": supply,
        "exclusive_m2": exclusive,
        "floor": floor,
        "total_floor": total_floor,
        "direction": direction,
        "realtor": realtor,
        "source_url": (
            f"https://fin.land.naver.com/articles/{article_no}"
        ),
    }


def filter_targets(
    rows: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:

    out: list[dict[str, Any]] = []

    for row in rows:
        price = int(row.get("price") or 0)

        if price <= 0:
            continue

        if price > int(cfg["max_price"]):
            continue

        target = next(
            (
                x for x in cfg["targets"]
                if x["complex"]
                in str(row.get("complex_name", ""))
            ),
            None,
        )

        if not target:
            continue

        supply = float(row.get("supply_m2") or 0)

        if supply <= 0:
            continue

        pyeong = supply / 3.3058

        if (
            abs(
                pyeong
                - float(target["target_pyeong"])
            )
            <= float(target["tolerance"])
        ):
            out.append(row)

    return out


def collect_all(
    cfg: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:

    # 1. 비산동 단지 목록 조회
    complexes = get_complexes()

    # 2. 더포레스트힐 / 안양임곡휴먼시아 찾기
    targets = find_target_complexes(complexes)

    rows: list[dict[str, Any]] = []
    status: dict[str, Any] = {
        "NAVER": {
            "status": "live",
            "count": 0,
        }
    }

    # 한 단지라도 수집 실패하면 전체 작업을 실패시킨다.
    # 그래야 기존 정상 listings.json을 빈 데이터로 덮어쓰지 않는다.
    for display_name, complex_row in targets.items():
        cid = complex_no(complex_row)

        if not cid:
            raise RuntimeError(
                f"{display_name}: complexNo 없음"
            )

        articles = get_articles(cid)

        for article in articles:
            item = convert_article(
                article,
                display_name,
            )

            if item:
                rows.append(item)

        time.sleep(random.uniform(1.5, 2.5))

    rows = filter_targets(rows, cfg)

    status["NAVER"]["count"] = len(rows)

    return rows, status
