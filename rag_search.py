import json
import re
import numpy as np
from google import genai
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

EMBEDDING_MODEL = "gemini-embedding-001"
CHUNKS_FILE = "standards_chunks.json"
EMBEDDINGS_FILE = "standards_embeddings.npy"

# 감사기준서의 '예시(illustrative)' 문단을 걸러내기 위한 마커.
# 예시 감사보고서는 가상의 연도(20X1)·금액 placeholder(XXX)·가상 회사명(ABC주식회사/XYZ)을 씀.
# 이런 문단이 검색되면 AI가 예시 속 허구 사실·문장을 이 회사의 근거로 인용하므로 검색 대상에서 제외한다.
# (요구사항 본문에는 이런 마커가 없어 그대로 검색됨 — 예시만 정확히 제거)
_EXAMPLE_MARKER = re.compile(r"20X[0-9]|XXX|ABC\s?주식회사|ABC회사|XYZ")

_chunks = None
_embeddings = None


def _load():
    global _chunks, _embeddings
    if _chunks is None:
        with open(CHUNKS_FILE, encoding="utf-8") as f:
            _chunks = json.load(f)
        _embeddings = np.load(EMBEDDINGS_FILE)
    return _chunks, _embeddings


def embed_query(text):
    result = client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
    return np.array(result.embeddings[0].values, dtype=np.float32)


def search(query, top_k=5, extra_diverse=3):
    """질문(query)과 가장 관련 있는 감사기준서 문단을 찾아서 반환.

    유사도 상위 top_k개(가장 관련 높은 순)를 그대로 가져오고, 그 위에
    상위권에 아직 등장하지 않은 '다른 기준서'에서 점수가 가장 높은 청크를
    extra_diverse개까지 덧붙임(augment). 상위 top_k을 줄이지 않으므로 특정
    기준서(예: 520)가 정당하게 상위를 차지하면 그대로 유지되고, 그 외에
    540·505·315 같은 다른 기준서도 검색에 함께 올라와 질문마다 더 맞는
    원문을 인용할 수 있게 됨.
    """
    chunks, embeddings = _load()
    query_vec = embed_query(query)

    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec)
    scores = (embeddings @ query_vec) / norms

    order = np.argsort(-scores)
    # 예시 문단 청크는 검색 대상에서 제외 (가상 사례를 원문으로 인용하는 것 방지)
    order = [i for i in order if not _EXAMPLE_MARKER.search(chunks[i]["text"])]

    primary_idx = list(order[:top_k])

    seen_standards = {chunks[i]["기준서"] for i in primary_idx}
    extra_idx = []
    for i in order[top_k:]:
        std = chunks[i]["기준서"]
        if std not in seen_standards:
            extra_idx.append(i)
            seen_standards.add(std)
            if len(extra_idx) >= extra_diverse:
                break

    return [
        {
            "기준서": chunks[i]["기준서"],
            "text": chunks[i]["text"],
            "score": float(scores[i]),
        }
        for i in primary_idx + extra_idx
    ]
