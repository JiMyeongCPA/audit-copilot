import json
import numpy as np
from google import genai
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

EMBEDDING_MODEL = "gemini-embedding-001"
CHUNKS_FILE = "standards_chunks.json"
EMBEDDINGS_FILE = "standards_embeddings.npy"

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
