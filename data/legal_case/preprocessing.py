"""v1.4_hallym_case_fraud_first.json에서 단일 사기 사건 + 판결문 있는 케이스만 추출.

출력:
  1) processed/single_fraud_with_judgment.json  — 전체 필드
  2) processed/fraud_crime_judgment.json        — id, crime_fact(정제), judgment만
"""

import json
import re
from pathlib import Path


SOURCE = Path(__file__).parent / "source_data" / "v1.4_hallym_case_fraud_first.json"
OUTPUT_DIR = Path(__file__).parent / "processed"


def is_single_fraud(case: dict) -> bool:
    """case_name_type이 1개이고 '사기'가 포함된 단일 사기 사건인지 판별."""
    types = case.get("case_meta", {}).get("case_name_type", [])
    return len(types) == 1 and "사기" in types[0]


def has_judgment(case: dict) -> bool:
    """case_main_parasplit.judgment에 실제 판결 내용이 있는지 확인."""
    j = case.get("case_main_parasplit", {}).get("judgment", "")
    return bool(j) and j.strip() != "" and j.strip() != "null"


def save_json(path: Path, data) -> float:
    """JSON 저장 후 파일 크기(MB) 반환."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return path.stat().st_size / (1024 * 1024)


def clean_crime_fact(text: str) -> str:
    """crime_fact에서 '증거의 요지' 이후 텍스트를 제거."""
    # \n증거의 요지\n 또는 공백 포함 변형 매칭
    match = re.search(r"\s*증거의\s*요지\s*", text)
    if match:
        return text[: match.start()].strip()
    return text.strip()


def main():
    print(f"[1/4] 로딩: {SOURCE}")
    with open(SOURCE, "r", encoding="utf-8") as f:
        raw = json.load(f)

    all_cases = raw.get("data", [])
    print(f"      전체 케이스: {len(all_cases):,}건")

    # ── 필터링 ──
    filtered = [c for c in all_cases if is_single_fraud(c) and has_judgment(c)]
    print(f"[2/4] 단일 사기 + 판결문 보유: {len(filtered):,}건")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── 전체 필드 저장 ──
    full_path = OUTPUT_DIR / "single_fraud_with_judgment.json"
    full_output = {
        "meta": {
            "source": SOURCE.name,
            "filter": "단일 사기 사건 (case_name_type 1개 + '사기' 포함) & judgment 존재",
            "original_count": len(all_cases),
            "filtered_count": len(filtered),
        },
        "data": filtered,
    }
    mb = save_json(full_path, full_output)
    print(f"[3/4] 전체 필드 저장: {full_path}  ({mb:.1f} MB)")

    # ── id, crime_fact(정제), judgment만 추출 저장 ──
    cleaned_count = 0
    slim = []
    for c in filtered:
        raw_cf = c["case_main_parasplit"]["crime_fact"]
        cleaned_cf = clean_crime_fact(raw_cf)
        if len(cleaned_cf) < len(raw_cf.strip()):
            cleaned_count += 1
        slim.append({
            "id": c["case_meta"]["id"],
            "crime_fact": cleaned_cf,
            "judgment": c["case_main_parasplit"]["judgment"],
            "judicial_decision": c["case_meta"]["judicial_decision"]
        })

    slim_path = OUTPUT_DIR / "fraud_crime_judgment.json"
    mb = save_json(slim_path, slim)
    print(f"[4/4] 경량 저장(id+crime_fact+judgment): {slim_path}  ({mb:.1f} MB)")
    print(f"      → '증거의 요지' 제거: {cleaned_count}/{len(slim)}건")


if __name__ == "__main__":
    main()
