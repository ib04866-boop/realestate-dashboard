# 비산동 매물 모니터 - 무료 클라우드판

기존 로컬 FastAPI 버전과 별개의 **GitHub Pages + GitHub Actions** 버전입니다.
PC를 꺼도 외부/모바일에서 URL로 접속할 수 있고, GitHub Actions가 2시간마다 `collector.py`를 실행한 뒤 사이트를 다시 배포합니다.

## 현재 필터

- 거래: 매매
- 유형: 아파트
- 최대 가격: 6억 6천만원
- 더포레스트힐: 공급면적 약 33평, ±2평
- 휴먼시아: 공급면적 약 24평, ±2평
- 출처 표시: NAVER / KB / HOGANGNONO

## 중요: 현재 데이터는 데모

이 프로젝트는 비공개/비공식 API를 임의 호출하지 않습니다. 기본 `DATA_MODE=demo`이며, 실제 매물은 `sources.py`에 각 서비스의 공식 또는 승인된 데이터 피드를 연결한 뒤 `live` 모드로 전환해야 합니다.

## 월 0원으로 배포하기

1. GitHub 계정을 만듭니다.
2. 새 **Public repository**를 만듭니다. 예: `realestate-dashboard-cloud`
3. 이 폴더의 모든 파일을 저장소 루트에 업로드합니다.
4. 저장소 `Settings` → `Pages`에서 Source를 **GitHub Actions**로 설정합니다.
5. `Actions` 탭 → `Update listings and deploy Pages` → `Run workflow`를 한 번 실행합니다.
6. 완료 후 `Settings` → `Pages`에 표시되는 주소로 접속합니다.

보통 주소는 아래 형태입니다.

`https://사용자이름.github.io/realestate-dashboard-cloud/`

## 2시간 자동 업데이트

`.github/workflows/update-and-deploy.yml`에 다음 스케줄이 들어 있습니다.

```yaml
schedule:
  - cron: "17 */2 * * *"
    timezone: "Asia/Seoul"
```

정각 부하를 피하기 위해 한국시간 기준 2시간마다 17분에 실행됩니다. GitHub의 예약 실행은 정확히 그 분에 시작된다고 보장되지는 않으며 지연될 수 있습니다.

## 비용

- GitHub Pages: GitHub Free의 Public repository에서 사용 가능
- GitHub Actions: Public repository의 표준 GitHub-hosted runner는 무료

비공개 저장소로 운영하거나 GitHub의 무료 제공량/정책이 바뀌면 조건이 달라질 수 있습니다.

## 로컬 테스트

정적 사이트이므로 간단히 다음처럼 테스트할 수 있습니다.

```bash
python collector.py
python -m http.server 8000
```

브라우저에서 `http://localhost:8000`

## 실제 데이터 연결 지점

`sources.py`의 `collect_all()`에 승인된 공급자별 adapter를 연결하세요. 반환 항목 예시는 다음과 같습니다.

```python
{
    "fingerprint": "stable-id",
    "source": "NAVER",
    "source_id": "...",
    "complex_name": "더포레스트힐",
    "building": "110동",
    "price": 630000000,
    "supply_m2": 110.0,
    "exclusive_m2": 84.96,
    "floor": 6,
    "total_floor": 25,
    "direction": "남동향",
    "realtor": "중개사명",
    "source_url": "https://..."
}
```

실데이터 adapter를 연결한 뒤 workflow의 `DATA_MODE: demo`를 `DATA_MODE: live`로 변경하면 됩니다.
