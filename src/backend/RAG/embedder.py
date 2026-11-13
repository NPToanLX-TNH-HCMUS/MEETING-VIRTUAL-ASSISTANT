import os

import numpy as np
import requests
from dotenv import load_dotenv


class EmbeddingClient:

    def __init__(self, timeout: float = 60):
        load_dotenv()
        base_url = os.getenv("EMBED_URL")
        if not base_url:
            raise ValueError("EMBED_URL is not set")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def embed(self, texts: list[str], is_query: bool = False) -> np.ndarray:
        r = requests.post(
            f"{self.base_url}/embed",
            json={"texts": texts, "is_query": is_query},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return np.array(r.json()["embeddings"])

    @staticmethod
    def similarity(query_emb: np.ndarray, doc_emb: np.ndarray) -> np.ndarray:
        return query_emb @ doc_emb.T


if __name__ == "__main__":
    client = EmbeddingClient()
    q = client.embed(["What is the capital of China?"], is_query=True)
    d = client.embed(["The capital of China is Beijing."])
    print(client.similarity(q, d)) 