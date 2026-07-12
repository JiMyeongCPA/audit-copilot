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


def search(query, top_k=5):
    """질문(query)과 가장 관련 있는 감사기준서 문단 top_k개를 찾아서 반환"""
    chunks, embeddings = _load()
    query_vec = embed_query(query)

    norms = np.linalg.norm(embeddings, axis=1) * np.linalg.norm(query_vec)
    scores = (embeddings @ query_vec) / norms

    top_idx = np.argsort(-scores)[:top_k]
    return [
        {
            "기준서": chunks[i]["기준서"],
            "text": chunks[i]["text"],
            "score": float(scores[i]),
        }
        for i in top_idx
    ]
