"""미필적고의 분석용 사건 추출 스크립트.

preprocessing.py와 별도로 동작하며,
processed/fraud_crime_judgment.json에서 "적당히 복잡한" 사건을 선별한다.

출력:
  processed/dolus_samples.json
    - dolus_eventualis   : 미필적고의 인정/쟁점 사건 5건
    - non_dolus_eventualis: 미필적고의 아닌 사건 5건

복잡도 기준:
  1. crime_fact + judgment 합산 글자 수 (중앙값~상위 25% 범위)
  2. judgment에 실질적 판단 논증이 포함되어 있을 것
  3. 텍스트가 너무 짧거나(< 2000자) 너무 긴(> 15000자) 케이스 제외
"""

import json
import re
import random
from pathlib import Path

# ─── 경로 설정 ───
INPUT_PATH  = Path(__file__).parent / "processed" / "fraud_crime_judgment.json"
OUTPUT_DIR  = Path(__file__).parent / "target_data"
OUTPUT_PATH = OUTPUT_DIR / "dolus_samples.json"

# ─── 추출 파라미터 ───
SAMPLE_COUNT   = 5          # 각 그룹에서 추출할 건수
MIN_LENGTH     = 2000       # 최소 합산 글자 수
MAX_LENGTH     = 15000      # 최대 합산 글자 수
SEED           = 42         # 재현 가능한 랜덤 시드


# ─── 미필적고의 키워드 ───
INTENT_KEYWORDS = [
    "미필적 고의",
    "미필적인 고의",
    "미필적고의",
]


def load_data(path: Path) -> list[dict]:
    """전처리된 JSON 로드."""
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def total_length(case: dict) -> int:
    """crime_fact + judgment 합산 글자 수."""
    return len(case.get("crime_fact", "")) + len(case.get("judgment", ""))


def contains_dolus_keywords(case: dict) -> bool:
    """미필적고의 관련 키워드가 crime_fact 또는 judgment에 포함되어 있는지."""
    text = case.get("crime_fact", "") + " " + case.get("judgment", "")
    return any(kw in text for kw in INTENT_KEYWORDS)


def has_substantive_judgment(case: dict) -> bool:
    """judgment에 실질적 판단 논증이 포함되어 있는지 검증.

    단순 양형이유만 있는 게 아니라, 구체적 사실관계 판단이 있는지 확인.
    """
    judgment = case.get("judgment", "")
    if not judgment or len(judgment.strip()) < 200:
        return False

    # 논증 지표: 번호 리스트(① ② 또는 1 2), 종합하여/종합하면, 인정되는/인정할
    argumentation_markers = [
        r"\d\s",          # 번호 매기기 (1 xxx, 2 xxx)
        r"[①②③④⑤]",     # 원문자 번호
        r"종합하[여면]",
        r"인정[되할]",
        r"다음과\s*같은\s*사[실정]",
        r"증거[들에]",
    ]
    matches = sum(
        1 for pat in argumentation_markers
        if re.search(pat, judgment)
    )
    return matches >= 2  # 2개 이상 논증 지표가 있으면 실질적 판단으로 간주


def is_complex_enough(case: dict) -> bool:
    """'적당히 복잡한' 사건인지 판별.

    조건:
      - 합산 글자 수가 MIN_LENGTH ~ MAX_LENGTH
      - judgment에 실질적 논증이 있음
    """
    length = total_length(case)
    if length < MIN_LENGTH or length > MAX_LENGTH:
        return False
    if not has_substantive_judgment(case):
        return False
    return True


def compute_complexity_score(case: dict) -> float:
    """복잡도 점수 계산 (선별 우선순위 결정용).

    높을수록 분석에 적합한 사건:
      - crime_fact 길이 (사실관계가 상세할수록 좋음)
      - judgment 길이 (판단이 풍부할수록 좋음)
      - 피고인/피해자 수 (다수 관여 = 복잡)
    """
    cf = case.get("crime_fact", "")
    jd = case.get("judgment", "")

    # 기본 길이 점수 (정규화)
    length_score = (len(cf) + len(jd)) / MAX_LENGTH

    # 피고인 수 (피고인 A, B, C... 패턴)
    defendant_count = len(set(re.findall(r"피고인\s*[A-Z가-힣]", cf)))
    defendant_score = min(defendant_count / 3, 1.0)

    # 피해자 수
    victim_count = len(set(re.findall(r"피해자\s*[A-Z가-힣]", cf)))
    victim_score = min(victim_count / 3, 1.0)

    # 금액 언급 횟수 (금전거래가 복잡할수록)
    amount_count = len(re.findall(r"\d{1,3}(?:,\d{3})*\s*원", cf))
    amount_score = min(amount_count / 5, 1.0)

    return (
        length_score * 0.4
        + defendant_score * 0.2
        + victim_score * 0.2
        + amount_score * 0.2
    )


def select_diverse_samples(
    candidates: list[tuple[int, dict, float]],
    n: int,
    seed: int = SEED
) -> list[dict]:
    """복잡도 점수 기반으로 다양한 사건을 선별.

    상위 복잡도에서만 뽑지 않고, 3개 구간(상/중/하)에서 골고루 선택.
    """
    if len(candidates) <= n:
        return [c[1] for c in candidates]

    # 복잡도 기준 정렬
    candidates.sort(key=lambda x: x[2], reverse=True)

    # 3개 구간으로 분할
    chunk_size = len(candidates) // 3
    top    = candidates[:chunk_size]
    mid    = candidates[chunk_size:chunk_size*2]
    bottom = candidates[chunk_size*2:]

    rng = random.Random(seed)

    selected = []
    # 상위에서 2건, 중위에서 2건, 하위에서 1건
    pools = [(top, 2), (mid, 2), (bottom, 1)]
    for pool, count in pools:
        if len(pool) >= count:
            selected.extend(rng.sample(pool, count))
        else:
            selected.extend(pool)

    # 부족분 채우기
    remaining = [c for c in candidates if c not in selected]
    while len(selected) < n and remaining:
        pick = rng.choice(remaining)
        selected.append(pick)
        remaining.remove(pick)

    return [c[1] for c in selected[:n]]


def add_metadata(case: dict, group: str) -> dict:
    """분석용 메타데이터 추가."""
    cf = case.get("crime_fact", "")
    jd = case.get("judgment", "")

    return {
        "id":           case["id"],
        "group":        group,
        "crime_fact":   cf,
        "judgment":     jd,
        "judicial_decision": case.get("judicial_decision", ""),
        "_meta": {
            "crime_fact_length": len(cf),
            "judgment_length":   len(jd),
            "total_length":      len(cf) + len(jd),
            "complexity_score":  round(compute_complexity_score(case), 3),
            "dolus_keywords_found": [
                kw for kw in INTENT_KEYWORDS
                if kw in (cf + " " + jd)
            ],
        }
    }


def main():
    print("=" * 60)
    print("미필적고의 분석용 사건 추출")
    print("=" * 60)

    # ── 1. 데이터 로드 ──
    print(f"\n[1/5] 로딩: {INPUT_PATH}")
    data = load_data(INPUT_PATH)
    print(f"      전체 케이스: {len(data):,}건")

    # ── 2. 미필적고의 여부 분류 ──
    dolus_pool = []       # 미필적고의 언급 케이스
    non_dolus_pool = []   # 미필적고의 미언급 케이스

    for i, case in enumerate(data):
        if contains_dolus_keywords(case):
            dolus_pool.append((i, case))
        else:
            non_dolus_pool.append((i, case))

    print(f"[2/5] 분류 완료")
    print(f"      미필적고의 언급: {len(dolus_pool):,}건")
    print(f"      미필적고의 미언급: {len(non_dolus_pool):,}건")

    # ── 3. 복잡도 필터링 ──
    dolus_complex = [
        (i, case, compute_complexity_score(case))
        for i, case in dolus_pool
        if is_complex_enough(case)
    ]
    non_dolus_complex = [
        (i, case, compute_complexity_score(case))
        for i, case in non_dolus_pool
        if is_complex_enough(case)
    ]

    print(f"[3/5] 복잡도 필터 통과")
    print(f"      미필적고의 후보: {len(dolus_complex):,}건")
    print(f"      non-미필적고의 후보: {len(non_dolus_complex):,}건")

    # ── 4. 다양한 사건 선별 ──
    dolus_selected     = select_diverse_samples(dolus_complex, SAMPLE_COUNT)
    non_dolus_selected = select_diverse_samples(non_dolus_complex, SAMPLE_COUNT)

    print(f"[4/5] 선별 완료: 미필적고의 {len(dolus_selected)}건, "
          f"non-미필적고의 {len(non_dolus_selected)}건")

    # ── 5. 결과 저장 ──
    output = {
        "meta": {
            "description": "미필적고의 분석용 사건 샘플",
            "source": INPUT_PATH.name,
            "total_cases":    len(data),
            "intent_pool":     len(dolus_pool),
            "non_intent_pool": len(non_dolus_pool),
            "complexity_filter": {
                "min_length":  MIN_LENGTH,
                "max_length":  MAX_LENGTH,
                "intent_passed":     len(dolus_complex),
                "non_dolus_passed": len(non_dolus_complex),
            },
            "sample_count": SAMPLE_COUNT,
            "seed": SEED,
        },
        "intent_cases": [
            add_metadata(c, "intent_cases") for c in dolus_selected
        ],
        "non_intent_cases": [
            add_metadata(c, "non_intent_cases") for c in non_dolus_selected
        ],
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    mb = OUTPUT_PATH.stat().st_size / (1024 * 1024)
    print(f"[5/5] 저장 완료: {OUTPUT_PATH}  ({mb:.2f} MB)")

    # ── 요약 출력 ──
    print("\n" + "=" * 60)
    print("선별 결과 요약")
    print("=" * 60)

    for group_name, group_key in [
        ("미필적고의 (intent_cases)", "intent_cases"),
        ("비-미필적고의 (non_intent_cases)", "non_intent_cases"),
    ]:
        print(f"\n── {group_name} ──")
        for item in output[group_key]:
            m = item["_meta"]
            print(f"  [{item['id']}]")
            print(f"    범죄사실: {m['crime_fact_length']:,}자 | "
                  f"판결: {m['judgment_length']:,}자 | "
                  f"합계: {m['total_length']:,}자 | "
                  f"복잡도: {m['complexity_score']}")
            if m["dolus_keywords_found"]:
                print(f"    키워드: {', '.join(m['dolus_keywords_found'])}")


if __name__ == "__main__":
    main()
