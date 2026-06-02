"""ChromaDB-backed knowledge store for finance glossary and accounting policy notes."""

import os
import chromadb
from chromadb.utils import embedding_functions

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..")
_CHROMA_PATH = os.path.join(os.path.dirname(__file__), "..", "chroma_db")
_COLLECTION = "fpa_knowledge"

_SOURCE_FILES = [
    os.path.join(_DATA_DIR, "finance_glossary.md"),
    os.path.join(_DATA_DIR, "accounting_policy_notes.md"),
]

_ef = embedding_functions.DefaultEmbeddingFunction()


def _chunk_text(text: str, chunk_size: int = 300) -> list[str]:
    """Split text into overlapping word-level chunks."""
    words = text.split()
    chunks, step = [], max(1, chunk_size // 2)
    for i in range(0, len(words), step):
        chunk = " ".join(words[i : i + chunk_size])
        if chunk:
            chunks.append(chunk)
    return chunks


def _build_index(collection: chromadb.Collection) -> None:
    docs, ids, metas = [], [], []
    idx = 0
    for path in _SOURCE_FILES:
        with open(path, "r") as f:
            text = f.read()
        source = os.path.basename(path)
        for chunk in _chunk_text(text):
            docs.append(chunk)
            ids.append(f"{source}_{idx}")
            metas.append({"source": source})
            idx += 1
    collection.add(documents=docs, ids=ids, metadatas=metas)


def _get_collection() -> chromadb.Collection:
    client = chromadb.PersistentClient(path=_CHROMA_PATH)
    existing = [c.name for c in client.list_collections()]
    if _COLLECTION in existing:
        return client.get_collection(name=_COLLECTION, embedding_function=_ef)
    collection = client.create_collection(name=_COLLECTION, embedding_function=_ef)
    _build_index(collection)
    return collection


def query_kb(query: str, n_results: int = 4) -> str:
    """Return top relevant passages from the knowledge base for *query*."""
    collection = _get_collection()
    results = collection.query(query_texts=[query], n_results=n_results)
    docs = results.get("documents", [[]])[0]
    return "\n\n---\n\n".join(docs) if docs else ""
