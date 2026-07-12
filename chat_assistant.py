import time

from google import genai
from google.genai import errors, types
from config import GEMINI_API_KEY, GEMINI_MODEL
from rag_search import search

client = genai.Client(api_key=GEMINI_API_KEY)

CHAT_SYSTEM_INSTRUCTION = """너는 사용자와 같이 회계·감사를 공부하는 동기인데, 사용자보다 조금 더 많이 알고 있는 친구야.
사용자가 지금 이 앱 화면에서 어떤 회사·계정·재무비율을 보고 있는지 맥락을 전달받고, 필요하면 그 맥락을 활용해서 대화해.

말투와 태도:
- 편하게 대화하는 동기처럼 자연스럽게 말해. 딱딱한 보고서 문체나 격식체("~습니다", "~하십시오")는 쓰지 마.
- 답을 정해주거나 명령하지 마. "~해야 해", "~하십시오" 같은 단정적인 지시보다는 "~해보는 건 어때?", "~일 수도 있을 것 같은데?"처럼 제안하고 추천하는 식으로 말해.
- 확실하지 않은 건 확실하지 않다고 솔직히 말해. 모르면 모른다고 해.
- 감사기준서를 인용할 때는 아래 제공되는 발췌문에 실제로 있는 문장만 그대로 인용해. 발췌문에 없는 조항이나 문장을 지어내지 마.
  다만 답변을 감사기준서 내용으로만 제한할 필요는 없어 — 일반적인 회계·재무 지식이나 실무적인 조언도 자유롭게 섞어서 답해도 돼.
  관련된 감사기준서 조항이 마땅히 없으면 "관련 기준서 조항은 못 찾겠는데" 라고 솔직히 말하고 너의 지식으로 답해.
- 사용자 질문이 화면 맥락과 관련 있으면 그 맥락을 적극 활용해서 구체적으로 답해. 맥락과 무관한 질문이면 맥락에 얽매이지 말고 자유롭게 답해도 돼.
"""


def generate_chat_reply(context_summary, history, user_message):
    """동기 챗봇 답변 생성.

    history: [{"role": "user"|"model", "text": str}, ...] (아직 user_message는 포함 안 됨)
    """
    try:
        retrieved = search(user_message, top_k=3)
    except Exception:
        retrieved = []

    standards_text = (
        "\n\n".join(f"[감사기준서 {r['기준서']}]\n{r['text']}" for r in retrieved)
        if retrieved
        else "(관련 감사기준서 발췌문 없음)"
    )

    contents = []
    if context_summary:
        contents.append(
            types.Content(role="user", parts=[types.Part(text=f"[지금 화면에서 보고 있는 내용]\n{context_summary}")])
        )
        contents.append(
            types.Content(role="model", parts=[types.Part(text="어, 그 상황 보고 있구나. 궁금한 거 물어봐!")])
        )
    for turn in history:
        contents.append(types.Content(role=turn["role"], parts=[types.Part(text=turn["text"])]))
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part(text=f"{user_message}\n\n[참고할 수 있는 감사기준서 발췌문]\n{standards_text}")],
        )
    )

    response = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=CHAT_SYSTEM_INSTRUCTION, temperature=0.7),
            )
            break
        except errors.ServerError:
            if attempt == 2:
                raise
            time.sleep(3)

    return response.text
