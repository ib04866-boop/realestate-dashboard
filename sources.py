from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


# 사용자께서 보내준 네이버페이 부동산 단지 링크.
# fin.land.naver.com 쪽 화면을 실제 Chromium으로 열고,
# 브라우저가 받은 JSON 응답에서 매물 데이터를 찾아낸다.
TARGET_PAGES = {
    "휴먼시아": "https://fin.land.naver.com/map?layer=NobwRAlgJmBcYGMD2BbADgGwKYA8D6UWALgIYQZgA0YaJATiSgM5zjLrY4CSMsATHwCcAVgDsAX2pMs9BAAsACvUYtY4UgCM4YekQgJsVHXT0GsAFQaFzATzRZVYAIIBGMOPEBdIA&center=3zfsqX-2AF7k4&zoom=15",
    "더포레스트힐": "https://fin.land.naver.com/map?layer=NobwRAlgJmBcYGMD2BbADgGwKYA8D6UWALgIYQZgA0YaJATiSgM5zjLrY4CSMsAzAAYAHAIC%2B1JlnoIAFgAV6jFrHCkARnDD0iEBNipa6OvVgAqDQqYCeaLMrABBAIxhRogLpA",
}

NAVER_HOME = "https://fin.land.naver.com/"


def fp(*parts: Any) -> str:
    return hashlib.sha1("|".join(map(str, parts)).encode("utf-8")).hexdigest()


def parse_price(value: Any) -> int:
    """네이버 가격 값을 원 단위 정수로 변환."""
    if value is None:
        return 0

    if isinstance(value, (int, float)):
        n = int(value)
        # 네이버 부동산 API는 종종 만원 단위 숫자를 사용한다.
        if 0 < n < 10_000_000:
            return n * 10_000
        return n

    s = str(value).strip().replace(",", "").replace(" ", "")
    if not s:
        return 0

    # 예: "6억5000", "6억 5,000", "65000"
    total = 0
    m = re.search(r"(\d+(?:\.\d+)?)억", s)
    if m:
        total += int(float(m.group(1)) * 100_000_000)
        rest = s[m.end():]
        digits = re.search(r"(\d+(?:\.\d+)?)", rest)
        if digits:
            total += int(float(digits.group(1)) * 10_000)
        return total

    digits = re.sub(r"[^\d]", "", s)
    if not digits:
        return 0

    n = int(digits)
    if n < 10_000_000:
        return n * 10_000
    return n


def as_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(str(value).replace(",", ""))
    except (TypeError, ValueError):
        return None


def pick(d: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return None


def looks_like_article(d: dict[str, Any]) -> bool:
    keys = set(d)
    has_id = bool(
        {"articleNo", "article_no", "articleId", "listingId", "id"} & keys
    )
    has_price = bool(
        {
            "dealOrWarrantPrc",
            "dealPrice",
            "price",
            "tradePrice",
            "deal_price",
        }
        & keys
    )
    return has_id and has_price


def walk_articles(obj: Any) -> list[dict[str, Any]]:
    """중첩 JSON 어디에 있든 매물처럼 보이는 dict를 수집."""
    out: list[dict[str, Any]] = []

    def walk(x: Any) -> None:
        if isinstance(x, dict):
            if looks_like_article(x):
                out.append(x)
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(obj)
    return out


def parse_floor(value: Any) -> tuple[int | None, int | None]:
    if value is None:
        return None, None

    s = str(value)
    if "/" not in s:
        m = re.search(r"-?\d+", s)
        return (int(m.group()) if m else None), None

    a, b = s.split("/", 1)

    def to_int(v: str) -> int | None:
        m = re.search(r"-?\d+", v)
        return int(m.group()) if m else None

    return to_int(a), to_int(b)


def normalize_article(
    article: dict[str, Any],
    display_complex_name: str,
) -> dict[str, Any] | None:
    article_no = str(
        pick(
            article,
            "articleNo",
            "article_no",
            "articleId",
            "listingId",
            "id",
        )
        or ""
    ).strip()

    price = parse_price(
        pick(
            article,
            "dealOrWarrantPrc",
            "dealPrice",
            "tradePrice",
            "price",
            "deal_price",
        )
    )

    if not article_no or price <= 0:
        return None

    # 다른 단지가 같은 응답에 섞이는 경우 방지.
    raw_complex = str(
        pick(
            article,
            "complexName",
            "complex_name",
            "complexNm",
            "aptName",
            "name",
        )
        or ""
    ).strip()

    if raw_complex:
        aliases = (
            ["휴먼시아", "안양임곡휴먼시아", "임곡휴먼시아"]
            if display_complex_name == "휴먼시아"
            else ["더포레스트힐"]
        )
        if not any(a in raw_complex for a in aliases):
            return None

    supply = as_float(
        pick(
            article,
            "area1",
            "supplyArea",
            "supply_m2",
            "spc1",
            "area",
        )
    )

    exclusive = as_float(
        pick(
            article,
            "area2",
            "exclusiveArea",
            "exclusive_m2",
            "spc2",
        )
    )

    floor, total_floor = parse_floor(
        pick(article, "floorInfo", "floor_info", "floor")
    )

    building = str(
        pick(
            article,
            "buildingName",
            "building",
            "dongName",
            "buildingNo",
            "dong",
        )
        or ""
    )

    direction = str(
        pick(article, "direction", "directionName", "directionNm") or ""
    )

    realtor = str(
        pick(
            article,
            "realtorName",
            "realtor",
            "cpName",
            "brokerName",
            "agentName",
        )
        or ""
    )

    source_url = str(
        pick(article, "articleUrl", "url", "source_url") or ""
    )

    if not source_url:
        source_url = f"https://fin.land.naver.com/articles/{article_no}"

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
        "source_url": source_url,
    }


def filter_targets(
    rows: list[dict[str, Any]],
    cfg: dict[str, Any],
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []

    for row in rows:
        price = int(row.get("price") or 0)
        if price <= 0 or price > int(cfg["max_price"]):
            continue

        target = next(
            (
                x
                for x in cfg["targets"]
                if x["complex"] in str(row.get("complex_name", ""))
            ),
            None,
        )
        if not target:
            continue

        supply = float(row.get("supply_m2") or 0)

        # 공급면적을 찾지 못한 경우에는 잘못 제외하지 않고 유지.
        # 브라우저 응답 구조가 바뀌면 로그를 보고 면적 키를 추가할 수 있다.
        if supply > 0:
            pyeong = supply / 3.3058
            if abs(pyeong - float(target["target_pyeong"])) > float(
                target["tolerance"]
            ):
                continue

        out.append(row)

    # 동일 articleNo 중복 제거
    unique: dict[str, dict[str, Any]] = {}
    for row in out:
        unique[row["fingerprint"]] = row
    return list(unique.values())


def collect_page(
    page,
    display_name: str,
    url: str,
) -> list[dict[str, Any]]:
    captured: list[dict[str, Any]] = []
    response_urls: list[str] = []

    def on_response(response) -> None:
        u = response.url
        host = urlparse(u).netloc.lower()

        # 네이버/네이버페이 부동산 관련 JSON만 본다.
        if "naver.com" not in host:
            return

        ct = (response.headers.get("content-type") or "").lower()
        interesting_url = any(
            token in u.lower()
            for token in (
                "article",
                "listing",
                "complex",
                "land",
                "estate",
                "property",
            )
        )

        if "json" not in ct and not interesting_url:
            return

        try:
            data = response.json()
        except Exception:
            return

        found = walk_articles(data)
        if found:
            captured.extend(found)
            response_urls.append(u)
            print(
                f"[NAVER] {display_name}: JSON 응답에서 매물 후보 {len(found)}건 발견",
                flush=True,
            )

    page.on("response", on_response)

    print(f"[NAVER] {display_name}: 페이지 열기", flush=True)
    print(f"[NAVER] URL={url}", flush=True)

    try:
        page.goto(
            url,
            wait_until="domcontentloaded",
            timeout=30_000,
        )
    except PlaywrightTimeoutError:
        print(
            f"[NAVER] {display_name}: 최초 페이지 로드는 타임아웃이지만 계속 진행",
            flush=True,
        )

    # 지도/단지 UI가 추가 요청을 보낼 시간을 준다.
    page.wait_for_timeout(8_000)

    # 화면에 "매물" 탭이 있으면 눌러 추가 요청을 유도한다.
    for label in ("매물", "매매"):
        try:
            loc = page.get_by_text(label, exact=True)
            if loc.count() > 0:
                loc.first.click(timeout=3_000)
                page.wait_for_timeout(5_000)
                print(
                    f"[NAVER] {display_name}: '{label}' 클릭",
                    flush=True,
                )
                break
        except Exception:
            pass

    print(
        f"[NAVER] {display_name}: 네트워크 매물 후보 총 {len(captured)}건",
        flush=True,
    )

    if response_urls:
        print(
            "[NAVER] 매물 응답 예시: " + response_urls[-1],
            flush=True,
        )

    normalized: list[dict[str, Any]] = []

    for raw in captured:
        item = normalize_article(raw, display_name)
        if item:
            normalized.append(item)

    return normalized


def collect_all(
    cfg: dict[str, Any],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    print("[NAVER] Playwright/Chromium 실매물 수집 시작", flush=True)

    rows: list[dict[str, Any]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--disable-dev-shm-usage",
                "--no-sandbox",
            ],
        )

        context = browser.new_context(
            locale="ko-KR",
            timezone_id="Asia/Seoul",
            viewport={"width": 1440, "height": 1100},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
        )

        # 먼저 홈에 들어가 세션/쿠키를 만든다.
        page = context.new_page()
        try:
            page.goto(
                NAVER_HOME,
                wait_until="domcontentloaded",
                timeout=20_000,
            )
            page.wait_for_timeout(2_000)
        except PlaywrightTimeoutError:
            print("[NAVER] 홈 초기 로드 타임아웃 - 계속 진행", flush=True)

        for display_name, url in TARGET_PAGES.items():
            print(f"[NAVER] ===== {display_name} =====", flush=True)
            target_page = context.new_page()

            try:
                found = collect_page(
                    target_page,
                    display_name,
                    url,
                )
                print(
                    f"[NAVER] {display_name}: 정규화 성공 {len(found)}건",
                    flush=True,
                )
                rows.extend(found)
            finally:
                target_page.close()

        browser.close()

    rows = filter_targets(rows, cfg)

    print(
        f"[NAVER] 최종 조건 통과 매물 {len(rows)}건",
        flush=True,
    )

    # 빈 결과를 정상 결과로 저장하면 기존 실제 매물이 전부 사라질 수 있으므로
    # 반드시 실패 처리한다.
    if not rows:
        raise RuntimeError(
            "네이버에서 실제 매물을 1건도 추출하지 못했습니다. "
            "기존 listings.json 보호를 위해 업데이트를 중단합니다."
        )

    return rows, {
        "NAVER": {
            "status": "live",
            "count": len(rows),
        }
    }
