import time

from google import genai
from google.genai import errors, types
from config import GEMINI_API_KEY, GEMINI_MODEL
from rag_search import search

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """당신은 숙련된 회계감사인입니다. 사용자가 제공하는 재무 분석 상황과 감사기준서 발췌문을 바탕으로,
"감사인이 감사대상회사(피감회사)에게 직접 물어볼 질문"을 추천합니다. 질문의 방향은 항상 감사인 → 회사(귀사)입니다.

반드시 지켜야 할 규칙:
1. 반드시 제공된 감사기준서 발췌문 내용에만 근거하십시오. 발췌문에 없는 조항이나 내용을 지어내지 마십시오.
2. 인사말, 소개 문장, 결론 문장을 절대 쓰지 마세요 (예: "네,", "다음은 ~입니다", "~하겠습니다" 같은 서두 문장도 금지). 응답의 첫 글자부터 바로 "**추천 질문 1**"로 시작하십시오.
3. "질문 1:", "근거:"처럼 번호만 붙이는 옛날 형식은 절대 사용하지 마세요.
4. **추천 질문**은 두 부분으로 구성하십시오: 먼저 "다음 질문을 회사 측에 하시는 것을 추천드립니다" 같은 명확한 추천 문장을 쓰고, 그 다음 실제로 회사에 던질 질문 문장을 따옴표로 인용하십시오. 인용된 질문은 반드시 "귀사는 ~하셨습니까?", "~에 대해 설명해 주시겠습니까?"처럼 감사인이 회사 측에 직접 묻는 2인칭 문장이어야 합니다. (AI가 감사인에게 무언가를 확인하라고 지시하는 문장이 아닙니다.)
5. 아래 3개 항목은 각각 반드시 줄바꿈을 두 번(빈 줄 하나를 사이에 두고) 하여 별도 문단으로 분리하십시오. 하나의 문단으로 붙여 쓰면 안 됩니다.

각 항목의 형식 (다음 항목 예시의 줄바꿈 구조를 정확히 그대로 따르십시오):

**추천 질문 N**: 다음 질문을 회사 측에 하시는 것을 추천드립니다 — "귀사는 (구체적인 상황)에 대하여 (구체적으로 무엇)을 어떻게 하고 계십니까?"

**근거**: (왜 이 질문을 추천하는지, 이 회사의 실제 숫자를 활용한 쉬운 설명 — 원문 표현을 그대로 따라갈 필요 없음)

**감사기준서 원문**: "(해당 감사기준서 문장을 의역·요약 없이 그대로 인용)" (감사기준서 XXX)

(다음 추천 질문이 있다면 위 3개 문단을 한 세트로 반복하고, 세트 사이에는 구분선 "---"을 넣으십시오.)
"""


def build_context_query(context):
    """재무 상황을 자연어 문장으로 요약 (RAG 검색 쿼리 + 프롬프트에 재사용)"""
    parts = [
        f"{context['회사명']}의 {context['계정']} 관련 {context['지표명']}은 {context['지표값']}로, "
        f"{context['업종']} 평균({context['업종평균']})과 비교했을 때 "
    ]
    if context.get("이상치"):
        parts.append("업종 분포에서 중앙값을 크게 벗어난 이상치 구간에 있다.")
    else:
        parts.append("업종 평균과 비슷한 수준이다.")

    if context.get("당기금액_증감률") is not None:
        parts.append(f"전년 대비 {context['당기금액_증감률']:.1f}% 변동했다.")

    if context.get("통합계정_경고"):
        parts.append(f"이 회사는 {context['계정']} 관련 계정을 다른 계정과 통합하여 공시하고 있다.")

    if context.get("계약자산_포함"):
        parts.append("계약자산(미청구공사)을 매출채권 회전율 계산에 포함했다.")

    return " ".join(parts)


def generate_audit_questions(context, num_questions=4):
    query = build_context_query(context)
    retrieved = search(query, top_k=5)

    standards_text = "\n\n".join(
        f"[감사기준서 {r['기준서']}]\n{r['text']}" for r in retrieved
    )

    prompt = f"""[재무 분석 상황]
{query}

[참고할 감사기준서 발췌문]
{standards_text}

위 내용을 바탕으로 감사 질문 {num_questions}개를 작성하세요."""

    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_INSTRUCTION,
                    temperature=0.2,
                ),
            )
            break
        except errors.ServerError:
            if attempt == 2:
                raise
            time.sleep(3)

    return {
        "questions_text": response.text,
        "retrieved_standards": sorted(set(r["기준서"] for r in retrieved)),
    }
