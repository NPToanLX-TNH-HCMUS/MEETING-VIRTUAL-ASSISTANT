import faiss
import numpy as np
from sentence_transformers import SentenceTransformer
import json
from pathlib import Path

# path
current_dir = Path(__file__).parent
json_path = current_dir / "text_chunking.json"
chunk_path = current_dir.parent / "cache" / "title_chunks.faiss"

# read data file
with open(json_path, "r", encoding="utf-8") as file:
    data = json.load(file)

# title list
title_chunk = []

for i in range(len(data)):
    title_chunk.append(data[i]["title"])

# create model
model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# Cache embedded vectors
if chunk_path.exists() and chunk_path.stat().st_size > 0:
    index = faiss.read_index(str(chunk_path))
    print("Loaded vectors from cache")
else:
    embeddings = model.encode(title_chunk, batch_size=32, convert_to_numpy=True, normalize_embeddings=True).astype("float32")

    dimension = embeddings.shape[1]

    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings)
    faiss.write_index(index, str(chunk_path))
    print("Created and saved vectors")

# similarity between query and titles
def search(query, top_k=3):
    query_embedding = model.encode([query], batch_size=32, convert_to_numpy=True, normalize_embeddings=True)

    scores, indices = index.search(query_embedding, top_k)
    return scores[0], indices[0]

# Process query
while True:
    query = input()
    if (query.lower() == "exit"):
        break
    score, indices = search(query, top_k=3)

    for i in range(len(indices)):
        if (indices[i] < 0):
            continue
        print(f"Score: {score[i]}, Top {i + 1}: {title_chunk[indices[i]]}")