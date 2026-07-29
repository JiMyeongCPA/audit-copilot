import time

from google import genai
from google.genai import errors, types
from config import GEMINI_API_KEY, GEMINI_MODEL
from rag_search import search

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_INSTRUCTION = """당신은 숙련된 회계감사인입니다. 당신은 성격이 서로 다른 두 가지 입력을 받습니다.
- [재무 분석 상황]: 지금 이 감사대상 회사(피감회사)에게 실제로 일어나고 있는 '사실'입니다 (회사·계정·수치·증감 등). 질문에 담기는 회사의 사실 근거는 오직 여기에서만 가져와야 합니다.
- [참고할 감사기준서 발췌문]: 그런 상황에서 감사인이 어떻게 접근하고 무엇을 검토·질문해야 하는지에 대한 '방법·관점·절차'의 근거입니다. 여기서는 '방법'을 가져오는 것이지 '사실'을 가져오는 것이 아닙니다.
이 둘을 결합하여 "감사인이 감사대상회사에게 직접 물어볼 질문"을 추천합니다. 질문의 방향은 항상 감사인 → 회사(귀사)입니다.

반드시 지켜야 할 규칙:
1. 두 입력의 역할을 엄격히 구분하십시오. 질문에 담기는 '회사의 사실'(구체적 상황·날짜·수치)은 오직 [재무 분석 상황]에서만 가져오고, [참고할 감사기준서 발췌문]에서는 '감사 방법·관점·절차'만 가져오십시오. 감사기준서 발췌문에 나오는 구체적인 회사 상황·날짜·수치(예: '20X1년', 'XXX', 특정 회사에서 일어난 사건)는 기준서를 설명하기 위한 예시일 뿐 이 회사의 실제 사실이 아니므로, 절대로 이 회사의 상황으로 인용하거나 사실로 가정하지 마십시오. 또한 발췌문에 없는 기준서 조항·번호를 지어내지 마십시오.
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
    """재무 상황을 자연어 문장으로 요약 (RAG 검색 쿼리 + 프롬프트에 재사용).

    선택한 지표 하나가 아니라, 그 계정의 관련 비율 여러 개와 관련 계정(금액·증감)을
    함께 요약해서 AI가 단일 지표가 아닌 종합적인 상황을 보고 질문을 뽑도록 함.
    """
    회사 = context["회사명"]
    계정 = context["계정"]
    업종 = context["업종"]

    parts = [f"{업종} 업종에 속한 {회사}의 {계정} 계정을 감사 관점에서 검토 중이다."]

    if context.get("선택계정_증감률") is not None:
        parts.append(f"{계정}의 당기 금액은 전년 대비 {context['선택계정_증감률']:.1f}% 변동했다.")

    ratio_segs = []
    for r in context.get("관련_비율", []):
        seg = f"{r['지표명']}은 {r['회사값']}(업종 중앙값 {r['업종중앙값']}"
        seg += ", 업종 내 이상치 구간)" if r.get("이상치") else ")"
        ratio_segs.append(seg)
    if ratio_segs:
        parts.append("이 계정과 관련된 재무비율은 다음과 같다: " + ", ".join(ratio_segs) + ".")

    acc_segs = []
    for a in context.get("관련_계정", []):
        seg = f"{a['계정']} {a['당기금액_억원']:,}억원"
        if a.get("증감률") is not None:
            seg += f"(전년 대비 {a['증감률']:.1f}%)"
        acc_segs.append(seg)
    if acc_segs:
        parts.append(
            "함께 검토할 관련 계정(비율 산식에 직접 쓰이는 계정)의 당기 금액과 증감은 다음과 같다: "
            + ", ".join(acc_segs) + "."
        )

    if context.get("통합계정_경고"):
        parts.append(f"이 회사는 {계정} 관련 계정을 다른 계정과 통합하여 공시하고 있다.")

    if context.get("계약자산_포함"):
        parts.append("계약자산(미청구공사)을 매출채권 회전율 계산에 포함했다.")

    return " ".join(parts)


def generate_audit_questions(context, num_questions=4):
    query = build_context_query(context)
    retrieved = search(query, top_k=5)

    standards_text = "\n\n".join(
        f"[감사기준서 {r['기준서']}]\n{r['text']}" for r in retrieved
    )

    prompt = f"""[재무 분석 상황 — 이 회사에게 실제로 일어나고 있는 사실]
{query}

[참고할 감사기준서 발췌문 — 이런 상황에 대한 감사 방법·관점의 근거이며, 여기 나오는 구체적 회사 사례·날짜·수치는 기준서의 예시일 뿐 이 회사의 사실이 아님]
{standards_text}

위 [재무 분석 상황]의 실제 사실에 [감사기준서 발췌문]의 방법·관점을 적용하여, 이 회사에 맞는 감사 질문 {num_questions}개를 작성하세요. 회사의 사실은 [재무 분석 상황]에서만 가져오고, 기준서 발췌문의 예시 상황을 이 회사의 사실로 쓰지 마십시오."""

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
