import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import json
from pathlib import Path

current_dir = Path(__file__).parent
json_path = current_dir / "text_chunking.json"


with open(json_path, "r", encoding="utf-8") as file:
    data = json.load(file)

title_chunk = []

for i in range(len(data)):
    title_chunk.append(data[i]["title"])

# print(title_chunk)

model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

embeddings = model.encode(title_chunk, batch_size=32, convert_to_numpy=True, normalize_embeddings=True).astype("float32")

dimension = embeddings.shape[1]

index = faiss.IndexFlatIP(dimension)
index.add(embeddings)

def search(query, top_k=3):
    query_embedding = model.encode([query], batch_size=32, convert_to_numpy=True, normalize_embeddings=True)

    scores, indices = index.search(query_embedding, top_k)
    return scores, indices


scr_raw, idx_raw = search("SEGMENT TREE", top_k=10)
index = idx_raw[0]
score = scr_raw[0]

for i in range(len(index)):
    print(f"Score: {score[i]}, Top {i + 1}: {title_chunk[index[i]]}")