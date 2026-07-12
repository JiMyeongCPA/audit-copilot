import os
import glob
import json
import time
import numpy as np
from google import genai
from google.genai import errors
from config import GEMINI_API_KEY

client = genai.Client(api_key=GEMINI_API_KEY)

STANDARDS_DIR = "auditing_standards"
CHUNK_TARGET_SIZE = 700
EMBEDDING_MODEL = "gemini-embedding-001"
CHECKPOINT_FILE = "standards_embeddings_checkpoint.jsonl"
REQUEST_DELAY = 0.5


def chunk_file(filepath):
    """문단(빈 줄로 구분)들을 순서대로 이어붙여서 목표 크기(약 700자) 청크로 묶음"""
    text = open(filepath, encoding="utf-8").read()
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    chunks = []
    current = ""
    for para in paragraphs:
        if current and len(current) + len(para) > CHUNK_TARGET_SIZE:
            chunks.append(current)
            current = para
        else:
            current = current + "\n\n" + para if current else para
    if current:
        chunks.append(current)
    return chunks


def collect_all_chunks():
    all_chunks = []
    for filepath in sorted(glob.glob(os.path.join(STANDARDS_DIR, "*.txt"))):
        standard_no = os.path.basename(filepath).replace("감사기준서_", "").replace(".txt", "")
        for chunk in chunk_file(filepath):
            all_chunks.append({"기준서": standard_no, "text": chunk})
    return all_chunks


def embed_text(text, max_retries=6):
    delay = 8
    for attempt in range(max_retries):
        try:
            result = client.models.embed_content(model=EMBEDDING_MODEL, contents=text)
            return result.embeddings[0].values
        except errors.ClientError as e:
            if "RESOURCE_EXHAUSTED" in str(e) and attempt < max_retries - 1:
                print(f"  429 대기 후 재시도... ({delay}초)")
                time.sleep(delay)
                delay = min(delay * 2, 60)
            else:
                raise


def load_checkpoint():
    done = 0
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, encoding="utf-8") as f:
            done = sum(1 for _ in f)
    return done


def build_index():
    all_chunks = collect_all_chunks()
    print(f"총 청크 수: {len(all_chunks)}")

    already_done = load_checkpoint()
    if already_done:
        print(f"이어서 진행: {already_done}개는 이미 완료됨")

    with open(CHECKPOINT_FILE, "a", encoding="utf-8") as f:
        for i in range(already_done, len(all_chunks)):
            item = all_chunks[i]
            vec = embed_text(item["text"])
            f.write(json.dumps({"기준서": item["기준서"], "text": item["text"], "embedding": vec}, ensure_ascii=False) + "\n")
            f.flush()
            if (i + 1) % 20 == 0:
                print(f"임베딩 진행: {i + 1}/{len(all_chunks)}")
            time.sleep(REQUEST_DELAY)

    finalize_index()


def finalize_index():
    chunks = []
    embeddings = []
    with open(CHECKPOINT_FILE, encoding="utf-8") as f:
        for line in f:
            row = json.loads(line)
            chunks.append({"기준서": row["기준서"], "text": row["text"]})
            embeddings.append(row["embedding"])

    embeddings_array = np.array(embeddings, dtype=np.float32)
    np.save("standards_embeddings.npy", embeddings_array)

    with open("standards_chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False)

    print("완료:", embeddings_array.shape)


if __name__ == "__main__":
    build_index()
