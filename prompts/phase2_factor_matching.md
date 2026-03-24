# Phase 2: 고의 판단 요소 → 범죄사실(Crime Fact) 매칭

## 역할

당신은 한국 형법 전문가입니다. Phase 1에서 추출한 **고의 판단 요소(factor)** 각각이 **범죄사실(crime_fact)** 텍스트에서 어떤 사실관계에 근거하는지 매칭합니다.

## 입력

```
[CRIME_FACT]
{crime_fact_text}
[/CRIME_FACT]

[FACTORS]
{factors_json}
[/FACTORS]
```

## 지시사항

1. 각 factor의 `description`을 기준으로, `crime_fact` 텍스트에서 **대응하는 사실관계**를 찾으세요.
2. 매칭 유형(`match_type`)을 판단하세요:
   - **직접언급**: crime_fact에 해당 사실이 명시적으로 기술되어 있음
   - **추론가능**: 직접 기술되지는 않았으나, crime_fact의 다른 사실로부터 합리적으로 추론 가능
   - **미언급**: crime_fact에 대응하는 사실관계가 전혀 없음 (judgment에서만 나타나는 논증)
3. 매칭된 경우, crime_fact에서 **해당 부분을 직접 인용**하세요.
4. 매칭 신뢰도(`confidence`)를 0.0~1.0으로 평가하세요.

## 출력 형식

아래 JSON 형식으로만 응답하세요. 설명이나 마크다운 없이 순수 JSON만 출력합니다.

```json
{
  "case_id": "{case_id}",
  "matchings": [
    {
      "factor_id": "F1",
      "factor_description": "Phase 1에서 추출한 요소 설명",
      "matched": true,
      "crime_fact_evidence": "crime_fact에서 매칭되는 원문 발췌 (1~3문장)",
      "match_type": "직접언급 | 추론가능 | 미언급",
      "confidence": 0.95,
      "reasoning": "이 factor가 crime_fact의 해당 부분과 매칭되는 이유"
    }
  ],
  "coverage_summary": {
    "total_factors": 4,
    "matched_direct": 2,
    "matched_inferred": 1,
    "unmatched": 1
  }
}
```

### 필드 설명

- **matched**: `true` = 직접언급 또는 추론가능, `false` = 미언급
- **crime_fact_evidence**: `matched`가 `true`인 경우만 crime_fact 원문 인용. `false`이면 빈 문자열
- **confidence**: 직접언급(0.8~1.0), 추론가능(0.4~0.7), 미언급(0.0~0.3) 범위 권장
- **reasoning**: 매칭 판단의 구체적 근거. 미언급인 경우 "crime_fact에 해당 내용 없음" 등 기재

## 주의사항

- crime_fact에 없는 사실을 만들어내지 마세요. **원문에 있는 내용만** 인용하세요.
- judgment에서 나타나는 법리적 논증이나 대법원 판례 인용은 crime_fact에 매칭할 수 없습니다 → `미언급`
- 하나의 factor가 crime_fact의 여러 부분에 대응할 수 있습니다. 가장 핵심적인 부분을 인용하세요.
- `coverage_summary`의 숫자가 `matchings` 배열의 실제 내용과 일치해야 합니다.
