"""Recuperación lexical SQLite FTS5; opcionalmente dense E5 + RRF."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path

from .corpus import default_root, sha256_bytes
from .trusted_index import load_trusted_corpus, open_verified_index

STOP = set(
    "de del la las los el un una unos unas para por con en que cual cuales es son se al como "
    "a o y su sus qué cómo cuál dónde explica sobre sirve tiene hay puede entre rm resonancia magnetica mri irm "
    "diferencia diferencias significa significado usa hacer preparar alguien utiliza secuencia "
    "secuencias generar".split()
)


def terms(s: str, *, max_terms: int | None = 20) -> list[str]:
    norm = "".join(
        c for c in unicodedata.normalize("NFKD", s.casefold()) if not unicodedata.combining(c)
    )
    return list(
        dict.fromkeys(
            w
            for w in re.findall(r"[a-z0-9]+", norm)
            if (len(w) >= 3 or w in {"t1", "t2", "tr", "te", "b0"}) and w not in STOP
        )
    )[:max_terms]


def build_index(root: Path | None = None, dest: Path | None = None) -> dict:
    root = root or default_root()
    cards, _ = load_trusted_corpus(root)
    dest = dest or root / "local_data/mri_index.sqlite3"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        dest.unlink()
    with sqlite3.connect(dest) as db:
        db.execute("CREATE TABLE cards (id TEXT PRIMARY KEY, payload TEXT NOT NULL)")
        db.execute("""CREATE VIRTUAL TABLE search USING fts5(
            id UNINDEXED, title, keywords, text, tokenize="unicode61 remove_diacritics 2"
        )""")
        for card in cards:
            db.execute(
                "INSERT INTO cards VALUES (?, ?)",
                (card["id"], json.dumps(card, ensure_ascii=False)),
            )
            db.execute(
                "INSERT INTO search(id,title,keywords,text) VALUES(?,?,?,?)",
                (card["id"], card["title"], card["keywords"], card["text"]),
            )
        db.commit()
    return {
        "indexed_cards": len(cards),
        "index": str(dest),
        "manifest_sha256": sha256_bytes((root / "corpus/manifest.json").read_bytes()),
    }


def search_sparse(
    question: str, root: Path | None = None, index: Path | None = None, limit: int = 5
) -> list[dict]:
    root = root or default_root()
    index = index or root / "local_data/mri_index.sqlite3"
    if not index.exists():
        build_index(root, index)
    query_terms = terms(question)
    if not query_terms:
        return []
    # FTS5 solo recibe tokens validados [a-z0-9]; valores SQL siempre parametrizados.
    query = " OR ".join(f'"{term}"' for term in query_terms)
    with open_verified_index(root, index) as db:
        rows = db.execute(
            """SELECT c.payload, bm25(search,0,4,3,1) AS score
            FROM search JOIN cards c ON c.id=search.id
            WHERE search MATCH ? ORDER BY score ASC LIMIT ?""",
            (query, max(10, limit * 3)),
        ).fetchall()
    results = []
    for raw, score in rows:
        card = json.loads(raw)
        doc_terms = set(
            terms(card["title"] + " " + card["keywords"] + " " + card["text"], max_terms=None)
        )
        overlap = len(set(query_terms) & doc_terms)
        coverage = overlap / len(query_terms)
        # For two-concept questions, one incidental word is not enough.
        # Preserve the original broad-query rule until independently calibrated.
        required = 2 if len(query_terms) == 2 or len(query_terms) >= 5 else 1
        if overlap < required:
            continue
        results.append(
            {
                **card,
                "lexical_score": round(float(score), 5),
                "term_coverage": round(coverage, 4),
                "matched_terms": overlap,
            }
        )
    return results[:limit]


def search_hybrid(
    question: str,
    root: Path | None = None,
    index: Path | None = None,
    limit: int = 5,
    model_name: str = "intfloat/multilingual-e5-small",
) -> list[dict]:
    """Ejecuta embedding local solo si el usuario eligió modo híbrido explícitamente."""
    import numpy as np  # optional dependency
    from sentence_transformers import SentenceTransformer  # optional dependency

    root = root or default_root()
    sparse = search_sparse(question, root, index, limit=20)
    cards, _ = load_trusted_corpus(root)
    encoder = SentenceTransformer(model_name)
    passages = ["passage: " + c["title"] + " " + c["text"] for c in cards]
    dense = encoder.encode(passages, normalize_embeddings=True)
    q_vector = encoder.encode(["query: " + question], normalize_embeddings=True)[0]
    scores = np.asarray(dense) @ q_vector
    dense_order = list(np.argsort(-scores)[:20])
    combined = {}
    for rank, card in enumerate(sparse, 1):
        combined[card["id"]] = 1 / (60 + rank)
    for rank, idx in enumerate(dense_order, 1):
        card = cards[int(idx)]
        # Evitar que una similitud embebida sin evidencia lexical dé certeza falsa.
        if float(scores[int(idx)]) < 0.50:
            continue
        combined[card["id"]] = combined.get(card["id"], 0) + 1 / (60 + rank)
    by_id = {c["id"]: c for c in cards}
    return [
        {**by_id[id_], "rrf_score": round(score, 6)}
        for id_, score in sorted(combined.items(), key=lambda kv: -kv[1])[:limit]
    ]
