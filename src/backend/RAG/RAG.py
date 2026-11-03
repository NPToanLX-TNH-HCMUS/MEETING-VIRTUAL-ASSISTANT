import json
from pathlib import Path
import numpy as np

import faiss
from sentence_transformers import SentenceTransformer


# Project paths
PROJECT_DIR = Path(__file__).resolve().parents[2]

JSON_PATH = PROJECT_DIR / "data" / "presentation_points.json"
CACHE_DIR = PROJECT_DIR / "cache"
CACHE_PATH = CACHE_DIR / "title_points.faiss"

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def initialize_rag():
    # Read presentation points
    with open(JSON_PATH, "r", encoding="utf-8") as file:
        data = json.load(file)

    points = data["points"]

    # Extract titles and keep their corresponding point IDs
    titles = [point["title"] for point in points]
    point_ids = [point["id"] for point in points]
 
    # Create embedding model
    model = SentenceTransformer(MODEL_NAME)

    # Create cache directory if it does not exist
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    # Load existing FAISS index or create a new one
    if CACHE_PATH.exists() and CACHE_PATH.stat().st_size > 0:
        index_data = np.frombuffer(CACHE_PATH.read_bytes(), dtype=np.uint8)
        index = faiss.deserialize_index(index_data)

        print("Loaded vectors from cache")

    else:
        embeddings = model.encode(
            titles,
            batch_size=32,
            convert_to_numpy=True,
            normalize_embeddings=True
        ).astype("float32")

        dimension = embeddings.shape[1]

        index = faiss.IndexFlatIP(dimension)
        index.add(embeddings)

        index_data = faiss.serialize_index(index)
        CACHE_PATH.write_bytes(index_data.tobytes())

        print("Created and saved vectors")

    # Return everything needed for searching
    return {
        "model": model,
        "index": index,
        "titles": titles,
        "point_ids": point_ids
    }


def search(rag, query, top_k=3):
    """
    Search for presentation point titles similar to the query.
    """

    model = rag["model"]
    index = rag["index"]

    query_embedding = model.encode(
        [query],
        convert_to_numpy=True,
        normalize_embeddings=True
    ).astype("float32")

    scores, indices = index.search(query_embedding, top_k)

    results = []

    for i in range(len(indices[0])):
        index_id = indices[0][i]

        if index_id < 0:
            continue

        results.append({
            "point_id": rag["point_ids"][index_id],
            "title": rag["titles"][index_id],
            "score": float(scores[0][i])
        })

    return results


def run_debug():
    """
    Run RAG independently for debugging.
    """

    transcript = (
        "Hôm nay nhóm mình sẽ trình bày về Segment Tree. "
        "Đầu tiên, chúng ta sẽ tìm hiểu cấu trúc của cây, "
        "cách xây dựng cây từ mảng và cách truy vấn tổng trên một đoạn."
    )

    rag = initialize_rag()
    results = search(rag, transcript, top_k=3)

    print("\nTranscript:")
    print(transcript)

    print("\nSearch results:")

    for i, result in enumerate(results):
        print(f"\nTop {i + 1}")
        print(f"Point ID: {result['point_id']}")
        print(f"Title: {result['title']}")
        print(f"Score: {result['score']:.4f}")


if __name__ == "__main__":
    run_debug()