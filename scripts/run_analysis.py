"""판결문 고의(Dolus) 분석 파이프라인.

Phase 1: judgment → 고의 판단 요소(factor) 추출
Phase 2: factor → crime_fact 사실관계 매칭

사용법:
  python scripts/run_analysis.py                    # 전체 실행
  python scripts/run_analysis.py --phase 1          # Phase 1만
  python scripts/run_analysis.py --phase 2          # Phase 2만 (Phase 1 결과 필요)
  python scripts/run_analysis.py --limit 1          # 1건만 테스트
  python scripts/run_analysis.py --dry-run          # LLM 호출 없이 구조 확인
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from llm_client import LLMClient, load_config, load_prompt


# ─── 경로 설정 ───
DATA_DIR    = Path(__file__).parent.parent / "data" / "legal_case"
INPUT_PATH  = DATA_DIR / "target_data" / "dolus_samples.json"
RESULTS_DIR = DATA_DIR / "results"

PHASE1_OUTPUT = RESULTS_DIR / "phase1_factors.json"
PHASE2_OUTPUT = RESULTS_DIR / "phase2_matchings.json"
SUMMARY_OUTPUT = RESULTS_DIR / "summary_report.json"


def load_samples() -> dict:
    """dolus_samples.json 로드."""
    with open(INPUT_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data: any) -> None:
    """JSON 파일 저장."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    mb = path.stat().st_size / (1024 * 1024)
    print(f"  → 저장: {path} ({mb:.2f} MB)")


# ═══════════════════════════════════════════
# Phase 1: 고의 판단 요소 추출
# ═══════════════════════════════════════════

def run_phase1(
    cases: list[dict],
    client: LLMClient,
    dry_run: bool = False,
) -> list[dict]:
    """Phase 1: judgment에서 고의 판단 요소 추출."""
    prompt_template = load_prompt("phase1_factor_extraction.md")

    results = []
    for i, case in enumerate(cases):
        case_id = case["id"]
        group = case["group"]
        print(f"\n[Phase 1] ({i+1}/{len(cases)}) {case_id} [{group}]")

        if dry_run:
            print("  → dry-run: LLM 호출 건너뜀")
            results.append({
                "case_id": case_id,
                "group": group,
                "intent_conclusion": "dry-run",
                "intent_type": "dry-run",
                "legal_standard": "",
                "factors": [],
            })
            continue

        # 프롬프트 구성
        user_message = f"[JUDGMENT]\n{case['judgment']}\n[/JUDGMENT]"

        # LLM 호출
        try:
            result = client.call_json(
                system_prompt=prompt_template,
                user_message=user_message,
            )
            # case_id와 group 보정 (LLM이 틀릴 수 있으므로)
            result["case_id"] = case_id
            result["group"] = group
            print(f"  → 추출 완료: {len(result.get('factors', []))}개 요소")
            results.append(result)
        except Exception as e:
            print(f"  → 오류: {e}")
            results.append({
                "case_id": case_id,
                "group": group,
                "error": str(e),
            })

    return results


# ═══════════════════════════════════════════
# Phase 2: Factor → Crime Fact 매칭
# ═══════════════════════════════════════════

def run_phase2(
    cases: list[dict],
    phase1_results: list[dict],
    client: LLMClient,
    dry_run: bool = False,
) -> list[dict]:
    """Phase 2: factor를 crime_fact와 매칭."""
    prompt_template = load_prompt("phase2_factor_matching.md")

    # case_id → phase1 결과 매핑
    p1_map = {r["case_id"]: r for r in phase1_results if "error" not in r}

    results = []
    for i, case in enumerate(cases):
        case_id = case["id"]
        group = case["group"]
        print(f"\n[Phase 2] ({i+1}/{len(cases)}) {case_id} [{group}]")

        p1 = p1_map.get(case_id)
        if not p1:
            print("  → Phase 1 결과 없음, 건너뜀")
            results.append({
                "case_id": case_id,
                "group": group,
                "error": "Phase 1 결과 없음",
            })
            continue

        factors = p1.get("factors", [])
        if not factors:
            print("  → 추출된 요소 없음, 건너뜀")
            results.append({
                "case_id": case_id,
                "group": group,
                "matchings": [],
                "coverage_summary": {
                    "total_factors": 0,
                    "matched_direct": 0,
                    "matched_inferred": 0,
                    "unmatched": 0,
                },
            })
            continue

        if dry_run:
            print("  → dry-run: LLM 호출 건너뜀")
            results.append({
                "case_id": case_id,
                "group": group,
                "matchings": [],
                "coverage_summary": {
                    "total_factors": len(factors),
                    "matched_direct": 0,
                    "matched_inferred": 0,
                    "unmatched": 0,
                },
            })
            continue

        # 프롬프트 구성
        factors_json = json.dumps(factors, ensure_ascii=False, indent=2)
        user_message = (
            f"[CRIME_FACT]\n{case['crime_fact']}\n[/CRIME_FACT]\n\n"
            f"[FACTORS]\n{factors_json}\n[/FACTORS]"
        )

        # LLM 호출
        try:
            result = client.call_json(
                system_prompt=prompt_template,
                user_message=user_message,
            )
            result["case_id"] = case_id
            result["group"] = group
            summary = result.get("coverage_summary", {})
            print(
                f"  → 매칭 완료: "
                f"직접={summary.get('matched_direct', '?')}, "
                f"추론={summary.get('matched_inferred', '?')}, "
                f"미언급={summary.get('unmatched', '?')}"
            )
            results.append(result)
        except Exception as e:
            print(f"  → 오류: {e}")
            results.append({
                "case_id": case_id,
                "group": group,
                "error": str(e),
            })

    return results


# ═══════════════════════════════════════════
# 요약 리포트
# ═══════════════════════════════════════════

def generate_summary(
    phase1_results: list[dict],
    phase2_results: list[dict],
) -> dict:
    """Phase 1 + 2 결과를 종합한 요약 리포트 생성."""
    summary = {
        "generated_at": datetime.now().isoformat(),
        "total_cases": len(phase1_results),
        "phase1_summary": {},
        "phase2_summary": {},
        "per_case": [],
    }

    # Phase 1 집계
    all_factors = []
    category_dist = {}
    direction_dist = {"positive": 0, "negative": 0}

    for r in phase1_results:
        if "error" in r:
            continue
        for f in r.get("factors", []):
            all_factors.append(f)
            cat = f.get("category", "미분류")
            category_dist[cat] = category_dist.get(cat, 0) + 1
            d = f.get("direction", "unknown")
            if d in direction_dist:
                direction_dist[d] += 1

    summary["phase1_summary"] = {
        "total_factors_extracted": len(all_factors),
        "avg_factors_per_case": round(
            len(all_factors) / max(len(phase1_results), 1), 1
        ),
        "category_distribution": dict(
            sorted(category_dist.items(), key=lambda x: x[1], reverse=True)
        ),
        "direction_distribution": direction_dist,
    }

    # Phase 2 집계
    total_matched_direct = 0
    total_matched_inferred = 0
    total_unmatched = 0

    for r in phase2_results:
        if "error" in r:
            continue
        cs = r.get("coverage_summary", {})
        total_matched_direct += cs.get("matched_direct", 0)
        total_matched_inferred += cs.get("matched_inferred", 0)
        total_unmatched += cs.get("unmatched", 0)

    total_all = total_matched_direct + total_matched_inferred + total_unmatched
    summary["phase2_summary"] = {
        "total_matchings": total_all,
        "matched_direct": total_matched_direct,
        "matched_inferred": total_matched_inferred,
        "unmatched": total_unmatched,
        "coverage_rate": round(
            (total_matched_direct + total_matched_inferred)
            / max(total_all, 1),
            3,
        ),
    }

    # 케이스별 요약
    p2_map = {r["case_id"]: r for r in phase2_results}
    for r1 in phase1_results:
        case_id = r1["case_id"]
        r2 = p2_map.get(case_id, {})
        summary["per_case"].append({
            "case_id": case_id,
            "group": r1.get("group", ""),
            "intent_conclusion": r1.get("intent_conclusion", ""),
            "intent_type": r1.get("intent_type", ""),
            "factor_count": len(r1.get("factors", [])),
            "coverage_summary": r2.get("coverage_summary", {}),
        })

    return summary


# ═══════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="판결문 고의(Dolus) 분석 파이프라인"
    )
    parser.add_argument(
        "--phase",
        choices=["1", "2", "all"],
        default="all",
        help="실행할 단계 (기본: all)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="처리할 최대 케이스 수 (0=전체)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="LLM 호출 없이 구조만 확인",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("판결문 고의(Dolus) 분석 파이프라인")
    print(f"  Phase: {args.phase}  |  Limit: {args.limit or '전체'}"
          f"  |  Dry-run: {args.dry_run}")
    print("=" * 60)

    # ── 데이터 로드 ──
    data = load_samples()
    all_cases = data["intent_cases"] + data["non_intent_cases"]
    if args.limit > 0:
        all_cases = all_cases[:args.limit]
    print(f"\n대상 케이스: {len(all_cases)}건")

    # ── LLM 클라이언트 초기화 ──
    config = load_config()
    client = None
    if not args.dry_run:
        client = LLMClient(config)
        print(f"LLM: {client.provider} / {client.model}")

    # ── Phase 1 ──
    phase1_results = []
    if args.phase in ("1", "all"):
        print("\n" + "─" * 40)
        print("Phase 1: 고의 판단 요소 추출")
        print("─" * 40)
        phase1_results = run_phase1(all_cases, client, dry_run=args.dry_run)
        save_json(PHASE1_OUTPUT, phase1_results)

    # Phase 2에서 기존 Phase 1 결과 로드
    if args.phase == "2":
        if PHASE1_OUTPUT.exists():
            print(f"\n기존 Phase 1 결과 로드: {PHASE1_OUTPUT}")
            with open(PHASE1_OUTPUT, "r", encoding="utf-8") as f:
                phase1_results = json.load(f)
        else:
            print("오류: Phase 1 결과 파일이 없습니다. Phase 1을 먼저 실행하세요.")
            sys.exit(1)

    # ── Phase 2 ──
    phase2_results = []
    if args.phase in ("2", "all"):
        print("\n" + "─" * 40)
        print("Phase 2: Factor → Crime Fact 매칭")
        print("─" * 40)
        phase2_results = run_phase2(
            all_cases, phase1_results, client, dry_run=args.dry_run
        )
        save_json(PHASE2_OUTPUT, phase2_results)

    # ── 요약 리포트 ──
    if phase1_results and phase2_results:
        print("\n" + "─" * 40)
        print("요약 리포트 생성")
        print("─" * 40)
        summary = generate_summary(phase1_results, phase2_results)
        save_json(SUMMARY_OUTPUT, summary)

        # 콘솔 출력
        p1s = summary["phase1_summary"]
        p2s = summary["phase2_summary"]
        print(f"\n{'='*60}")
        print("결과 요약")
        print(f"{'='*60}")
        print(f"  총 케이스: {summary['total_cases']}건")
        print(f"  추출 요소: {p1s['total_factors_extracted']}개"
              f" (평균 {p1s['avg_factors_per_case']}개/건)")
        print(f"  카테고리: {p1s['category_distribution']}")
        print(f"  매칭률: {p2s['coverage_rate']*100:.1f}%"
              f" (직접={p2s['matched_direct']},"
              f" 추론={p2s['matched_inferred']},"
              f" 미언급={p2s['unmatched']})")

    print("\n완료!")


if __name__ == "__main__":
    main()
