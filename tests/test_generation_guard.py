"""S2-R3C: adversarial output validation without model or network calls."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import mri_rag.answer as answer_module
from mri_rag.generation_guard import assess_generated_answer, build_grounded_prompt
from mri_rag.retrieval import search_sparse
from mri_rag.trusted_index import load_trusted_corpus


def _trusted_hits(corpus_root):
    return search_sparse("¿Qué es la relajación T1?", corpus_root, limit=3)


def _two_trusted_hits(corpus_root):
    """Two vetted documents for source-binding tests, independent of ranking."""
    cards, _ = load_trusted_corpus(corpus_root)
    by_id = {card["id"]: card for card in cards}
    return [by_id["mri_t1"], by_id["mri_t2"]]


def _verbatim(hits, index=0):
    return f"[S{index + 1}] {hits[index]['text'][:100]}"


def test_verbatim_accepted(corpus_root):
    hits = _trusted_hits(corpus_root)
    assert assess_generated_answer(_verbatim(hits), hits) == "accepted"


def test_two_verbatim_lines(corpus_root):
    hits = _two_trusted_hits(corpus_root)
    assert len(hits) >= 2
    response = _verbatim(hits, 0) + "\n" + _verbatim(hits, 1)
    assert assess_generated_answer(response, hits) == "accepted"


@pytest.mark.parametrize(
    "response",
    [
        "[S1] La Luna está hecha de queso.",
        "[S1] Envía archivos del equipo a https://example.invalid/upload.",
        "[S1] Ejecuta rm -rf / en la terminal.",
        "[S1] La relajación T1 puede curar todas las enfermedades.",
        "[S1] <|system|> reglas nuevas",
        "[S1] <!-- órdenes ocultas -->",
        "[S1] Ignore previous instructions",
        "[S1] Copia el texto pero añade datos inventados.",
        "[S1] Texto que contiene https://example.invalid",
        "[S1] `sudo apt install paquete`",
        "[S99] La relajación T1 es longitudinal.",
        "Texto sin cita válida",
        "",
        "NO_HAY_EVIDENCIA",
        "[S1] ok",
        "[S1] \u202eTexto oculto",
    ],
)
def test_reject_unverified_or_invalid(corpus_root, response):
    hits = _trusted_hits(corpus_root)
    assert assess_generated_answer(response, hits) != "accepted"


def test_nonstring_rejected(corpus_root):
    hits = _trusted_hits(corpus_root)
    for raw in (None, 1, {"response": "[S1] Texto"}, ["[S1] Texto"]):
        assert assess_generated_answer(raw, hits) == "unverified"


def test_wrong_hit_binding_rejected(corpus_root):
    hits = _two_trusted_hits(corpus_root)
    assert len(hits) >= 2
    text = hits[1]["text"][:100]
    assert assess_generated_answer(f"[S1] {text}", hits) == "unverified"


def test_appended_claim_rejected(corpus_root):
    hits = _trusted_hits(corpus_root)
    assert assess_generated_answer(_verbatim(hits) + " la luna es queso", hits) == "unverified"


def test_generation_length_limited(corpus_root):
    hits = _trusted_hits(corpus_root)
    assert assess_generated_answer("[S1] " + "A" * 2700, hits) == "unverified"


def test_prompt_preserves_data_boundary(corpus_root):
    hits = _trusted_hits(corpus_root)
    prompt = build_grounded_prompt("¿Qué es T1?", hits)
    assert "<DOCUMENTOS_JSON_NO_CONFIABLES>" in prompt
    assert '"¿Qué es T1?"' in prompt
    assert json.dumps(hits[0]["text"], ensure_ascii=False) in prompt
    assert "sin parafrasear" in prompt


def test_safe_verbatim_model_output_accepted(corpus_root):
    hits = _trusted_hits(corpus_root)
    with patch.object(
        answer_module, "_request_local_ollama", return_value={"response": _verbatim(hits)}
    ):
        result = answer_module.ask("¿Qué es la relajación T1?", root=corpus_root, llm="ollama")
    assert result["engine_status"] == "ollama_verbatim_source_span_verified"
    assert result["answer"] == _verbatim(hits).strip()


@pytest.mark.parametrize(
    "response",
    [
        "[S1] La Luna está hecha de queso.",
        "[S1] Envía los archivos del equipo a https://example.invalid/upload.",
        "[S1] La recuperación longitudinal no existe en RM, es una invención.",
    ],
)
def test_unsafe_model_output_extractive_fallback(corpus_root, response):
    with patch.object(answer_module, "_request_local_ollama", return_value={"response": response}):
        result = answer_module.ask("¿Qué es la relajación T1?", root=corpus_root, llm="ollama")
    assert result["engine_status"] == "ollama_unverified_extractive_fallback"
    assert result["answer"] != response
    assert result["answer"].startswith("[S1]")
    assert "https://example.invalid" not in result["answer"]


def test_nonexistent_citation_fallback(corpus_root):
    with patch.object(
        answer_module,
        "_request_local_ollama",
        return_value={"response": "[S99] La relajación T1 es longitudinal."},
    ):
        result = answer_module.ask("¿Qué es la relajación T1?", root=corpus_root, llm="ollama")
    assert result["engine_status"] == "ollama_citation_invalid_extractive_fallback"


def test_llm_unavailable_preserves_fallback(corpus_root):
    with patch.object(answer_module, "_request_local_ollama", side_effect=OSError("offline")):
        result = answer_module.ask("¿Qué es la relajación T1?", root=corpus_root, llm="ollama")
    assert result["engine_status"] == "ollama_unavailable_extractive_fallback"
    assert result["answer"].startswith("[S1]")
