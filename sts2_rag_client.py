"""
Convenience client for querying the local STS2 Chroma knowledge base.

Example:
    from sts2_rag_client import STS2RAGClient

    client = STS2RAGClient()
    result = client.search_archetypes("silent poison core cards", character="silent")
    print(result["matches"][0]["document"])
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "chroma_db"
DEFAULT_COLLECTION = "sts2_knowledge"


class STS2RAGClient:
    def __init__(
        self,
        persist_dir: str | Path | None = None,
        collection_name: str = DEFAULT_COLLECTION,
    ) -> None:
        self.persist_dir = Path(persist_dir) if persist_dir else DEFAULT_DB_PATH
        self.collection_name = collection_name
        self._client = None
        self._collection = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        collection = self._get_collection()
        count = collection.count()
        return {
            "persist_dir": str(self.persist_dir),
            "collection_name": self.collection_name,
            "document_count": count,
        }

    def search(
        self,
        query: str,
        *,
        top_k: int = 5,
        character: str | None = None,
        doc_types: list[str] | None = None,
    ) -> dict[str, Any]:
        collection = self._get_collection()
        where = self._build_where(character=character, doc_types=doc_types)
        result = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where,
        )
        return {
            "query": query,
            "matches": self._format_query_result(result),
        }

    def search_cards(
        self,
        query: str,
        *,
        top_k: int = 5,
        character: str | None = None,
        include_relations: bool = True,
    ) -> dict[str, Any]:
        doc_types = ["card", "card_archetype_relation"] if include_relations else ["card"]
        return self.search(query, top_k=top_k, character=character, doc_types=doc_types)

    def search_archetypes(
        self,
        query: str,
        *,
        top_k: int = 5,
        character: str | None = None,
        include_relations: bool = True,
    ) -> dict[str, Any]:
        doc_types = ["archetype", "card_archetype_relation"] if include_relations else ["archetype"]
        return self.search(query, top_k=top_k, character=character, doc_types=doc_types)

    def search_relics(
        self,
        query: str,
        *,
        top_k: int = 5,
        character: str | None = None,
        include_relations: bool = True,
    ) -> dict[str, Any]:
        doc_types = ["relic", "relic_archetype_relation"] if include_relations else ["relic"]
        return self.search(query, top_k=top_k, character=character, doc_types=doc_types)

    def character_overview(self, character: str) -> dict[str, Any]:
        return self.search(
            query=f"{character} archetypes overview",
            top_k=3,
            character=character,
            doc_types=["character_overview"],
        )

    def build_context(
        self,
        query: str,
        *,
        top_k: int = 5,
        character: str | None = None,
        doc_types: list[str] | None = None,
    ) -> dict[str, Any]:
        result = self.search(
            query,
            top_k=top_k,
            character=character,
            doc_types=doc_types,
        )
        parts = []
        for idx, match in enumerate(result["matches"], start=1):
            parts.append(
                f"[{idx}] {match['id']} ({match['doc_type']})\n{match['document']}"
            )
        return {
            "query": query,
            "matches": result["matches"],
            "context_text": "\n\n".join(parts),
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_collection(self):
        if self._collection is not None:
            return self._collection

        try:
            import chromadb
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is not installed. Run `python -m pip install chromadb` first."
            ) from exc

        if not self.persist_dir.exists():
            raise FileNotFoundError(
                f"Chroma DB not found at {self.persist_dir}. "
                "Run scripts/import_rag_to_chroma.py first."
            )

        self._client = chromadb.PersistentClient(path=str(self.persist_dir))
        self._collection = self._client.get_collection(self.collection_name)
        return self._collection

    @staticmethod
    def _build_where(
        *,
        character: str | None,
        doc_types: list[str] | None,
    ) -> dict[str, Any] | None:
        clauses = []
        if character:
            clauses.append({"character": character})
        if doc_types:
            if len(doc_types) == 1:
                clauses.append({"doc_type": doc_types[0]})
            else:
                clauses.append({"$or": [{"doc_type": value} for value in doc_types]})

        if not clauses:
            return None
        if len(clauses) == 1:
            return clauses[0]
        return {"$and": clauses}

    @staticmethod
    def _format_query_result(result: dict[str, Any]) -> list[dict[str, Any]]:
        ids = result.get("ids", [[]])[0]
        distances = result.get("distances", [[]])[0] if result.get("distances") else []
        metadatas = result.get("metadatas", [[]])[0] if result.get("metadatas") else []
        documents = result.get("documents", [[]])[0] if result.get("documents") else []

        matches = []
        for idx, item_id in enumerate(ids):
            metadata = metadatas[idx] if idx < len(metadatas) else {}
            matches.append(
                {
                    "id": item_id,
                    "distance": distances[idx] if idx < len(distances) else None,
                    "doc_type": metadata.get("doc_type"),
                    "metadata": metadata,
                    "document": documents[idx] if idx < len(documents) else None,
                }
            )
        return matches


def build_default_client() -> STS2RAGClient:
    return STS2RAGClient()
