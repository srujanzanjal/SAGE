from functools import lru_cache

from app.core.config import get_settings


MODEL_PREFIXES = {
    "e5": ("query: ", "passage: "),
    "bge-": ("Represent this sentence for searching relevant passages: ", ""),
}


class EmbeddingService:
    def __init__(self) -> None:
        settings = get_settings()
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "sentence-transformers is not installed. Run: pip install -r backend/requirements.txt"
            ) from exc
        self.model = SentenceTransformer(settings.embedding_model_name)
        # Some models are trained with role prefixes and retrieve noticeably
        # worse without them; MiniLM uses none.
        name = settings.embedding_model_name.lower()
        self.query_prefix, self.document_prefix = next(
            (prefixes for key, prefixes in MODEL_PREFIXES.items() if key in name), ("", "")
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        texts = [self.document_prefix + t for t in texts]
        vectors = self.model.encode(texts, normalize_embeddings=True, show_progress_bar=False)
        return vectors.tolist()

    def embed_query(self, text: str) -> list[float]:
        vector = self.model.encode([self.query_prefix + text], normalize_embeddings=True, show_progress_bar=False)[0]
        return vector.tolist()


@lru_cache
def get_embedding_service() -> EmbeddingService:
    return EmbeddingService()
