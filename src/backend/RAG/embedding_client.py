import os
import numpy as np
import requests
from dotenv import load_dotenv

load_dotenv()

EMBED_URL = os.getenv("EMBED_URL")

def embed(texts: list[str], is_query: bool = False) -> np.ndarray:
    r = requests.post(
        f"{os.environ['EMBED_URL']}/embed",
        json={"texts": texts, "is_query": is_query},
        timeout=60,
    )
    r.raise_for_status()
    return np.array(r.json()["embeddings"])

def similarity(query_emb: np.ndarray, doc_emb: np.ndarray) -> np.ndarray:
    return query_emb @ doc_emb.T

if __name__ == "__main__":
    q = embed(["What is the capital of China?"], is_query=True)
    d = embed(["The capital of China is Beijing."])
    print(similarity(q, d))  # should be close to [[0.76, 0.14], [0.14, 0.60]]