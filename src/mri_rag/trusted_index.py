"""S2-R3B: verify approved corpus and read an index in a read-only snapshot.

Local filesystem integrity is not an authentication scheme. This guard assumes
application code and pinned release digest are trustworthy; it does not stop an
attacker who can replace executable code or compromise the Python environment.
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
import unicodedata
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .corpus import load_corpus, sha256_bytes, verify_manifest

# Approved RC0 manifest; deliberate corpus releases must update this trusted pin.
APPROVED_MANIFEST_SHA256 = "219d05a6b449b213c70673cbd24ee61080f035b82a4a004f5bb8778fd7f32aa1"
APPROVED_FILES = {"corpus/cards.jsonl", "corpus/sources.json"}

ROLE_MARKERS = re.compile(
    r"(?im)(?:<\|(?:system|developer|assistant|tool|im_start|im_end)\|>|"
    r"\[(?:im_start|im_end|/?INST)\]|<<\s*/?SYS\s*>>|"
    r"^\s*(?:system|developer|assistant|tool)\s*:|"
    r"^\s*#{1,6}\s*(?:system|developer|assistant)\b)"
)
INSTRUCTIONS = re.compile(
    r"(?i)(?:ignora\s+(?:todas?\s+|las\s+)?instrucciones|"
    r"ignore\s+(?:all\s+|previous\s+)?instructions|"
    r"revela\s+(?:el\s+|tu\s+)?(?:system\s+)?prompt|"
    r"system\s+prompt|developer\s+message|"
    r"desactiva\s+(?:tus\s+|las\s+)?restricciones)"
)
HIDDEN_MARKUP = re.compile(
    r"(?is)(?:<!--|-->|<\s*/?script\b|<\s*/?style\b|"
    r"\bdisplay\s*:\s*none\b|\bvisibility\s*:\s*hidden\b)"
)


def inspect_document_text(value: str) -> None:
    """High-signal heuristic check for *untrusted* fields, never LLM authority."""
    if not isinstance(value, str):
        raise ValueError("SECURITY_BLOCK: campo no textual")
    if any(
        unicodedata.category(char) in {"Cf", "Cs"}
        or (unicodedata.category(char) == "Cc" and char not in "\r\n\t")
        for char in value
    ):
        raise ValueError("SECURITY_BLOCK: caracteres ocultos en documento")
    normalized = unicodedata.normalize("NFKC", value)
    for _ in range(2):
        decoded = html.unescape(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    if any(unicodedata.category(char) in {"Cf", "Cs"} for char in normalized):
        raise ValueError("SECURITY_BLOCK: control Unicode tras decodificación")
    if (
        ROLE_MARKERS.search(normalized)
        or HIDDEN_MARKUP.search(normalized)
        or INSTRUCTIONS.search(normalized)
    ):
        raise ValueError("SECURITY_BLOCK: posible instrucción incrustada en documento")


def load_trusted_corpus(root: Path) -> tuple[list[dict], dict[str, dict]]:
    root = Path(root)
    manifest_path = root / "corpus" / "manifest.json"
    files = [manifest_path, root / "corpus" / "cards.jsonl", root / "corpus" / "sources.json"]
    if any(not f.is_file() or f.is_symlink() for f in files):
        raise ValueError("SECURITY_BLOCK: corpus faltante o enlace simbólico")
    if sha256_bytes(manifest_path.read_bytes()) != APPROVED_MANIFEST_SHA256:
        raise ValueError("SECURITY_BLOCK: manifiesto no corresponde a la versión aprobada")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if set(manifest.get("sha256", {})) != APPROVED_FILES:
        raise ValueError("SECURITY_BLOCK: inventario de corpus no aprobado")
    checks = verify_manifest(root)
    if len(checks) != len(APPROVED_FILES) or not all(checks.values()):
        raise ValueError("SECURITY_BLOCK: hash del corpus incorrecto")
    cards, sources = load_corpus(root)
    if len(cards) != 20 or len(sources) != 15:
        raise ValueError("SECURITY_BLOCK: tamaño inesperado del corpus RC0")
    for card in cards:
        for field in ("title", "keywords", "text"):
            inspect_document_text(card[field])
    return cards, sources


@contextmanager
def open_verified_index(root: Path, index: Path) -> Iterator[sqlite3.Connection]:
    """Same SQLite read-only transaction for parity checks and retrieval."""
    cards, _ = load_trusted_corpus(root)
    reference = {card["id"]: card for card in cards}
    if len(reference) != len(cards):
        raise ValueError("SECURITY_BLOCK: IDs duplicados en corpus")
    index = Path(index)
    if not index.is_file() or index.is_symlink():
        raise ValueError("SECURITY_BLOCK: índice ausente o enlace simbólico")
    db = sqlite3.connect(index.resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    try:
        db.execute("PRAGMA query_only=ON")
        db.execute("PRAGMA trusted_schema=OFF")
        db.execute("BEGIN")
        if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise ValueError("SECURITY_BLOCK: estructura SQLite inválida")
        indexed_rows = db.execute("SELECT id, payload FROM cards").fetchall()
        fts_rows = db.execute("SELECT id, title, keywords, text FROM search").fetchall()
        if len(indexed_rows) != len(fts_rows) or len(indexed_rows) != len(cards):
            raise ValueError("SECURITY_BLOCK: cardinalidad SQLite diferente del corpus")
        indexed = dict(indexed_rows)
        if len(indexed) != len(indexed_rows) or set(indexed) != set(reference):
            raise ValueError("SECURITY_BLOCK: IDs SQLite incompatibles")
        if any(json.loads(payload) != reference[card_id] for card_id, payload in indexed.items()):
            raise ValueError("SECURITY_BLOCK: payload SQLite manipulado")
        seen = set()
        for card_id, title, keywords, text in fts_rows:
            if card_id in seen or card_id not in reference:
                raise ValueError("SECURITY_BLOCK: ID FTS duplicado o no autorizado")
            seen.add(card_id)
            card = reference[card_id]
            if (title, keywords, text) != (card["title"], card["keywords"], card["text"]):
                raise ValueError("SECURITY_BLOCK: texto FTS manipulado")
        if seen != set(reference):
            raise ValueError("SECURITY_BLOCK: faltan documentos FTS")
        yield db
    except (sqlite3.DatabaseError, json.JSONDecodeError) as exc:
        raise ValueError("SECURITY_BLOCK: índice no verificable") from exc
    finally:
        db.close()
