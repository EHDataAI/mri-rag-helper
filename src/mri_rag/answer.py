"""Respuesta extractiva por defecto; opcional Ollama con citas validadas."""

from __future__ import annotations

import json
import re
from http.client import HTTPConnection, HTTPException
from urllib.parse import urlsplit

from .corpus import default_root, load_corpus
from .generation_guard import assess_generated_answer, build_grounded_prompt
from .retrieval import search_hybrid, search_sparse, terms
from .security import checked_ollama_url, screen_question
from .trusted_index import load_trusted_corpus

NOTICE = "Material educativo, no diagnóstico ni autorización para procedimientos clínicos."


def _compose_approved_excerpts(question: str, hits: list[dict]) -> tuple[dict, str] | None:
    """Select question-relevant, literal evidence; no paraphrasing or inferred claims.

    This is a lexical sufficiency heuristic, not evidence of semantic entailment.
    Return no answer rather than unrelated text when the text lacks question terms.
    """
    required_terms = set(terms(question))
    if not required_terms:
        return None
    for hit in hits:
        sentences = re.split(r"(?<=[.!?])\s+", hit["text"].strip())
        options = []
        for index, sentence in enumerate(sentences):
            sentence = sentence.strip()
            if len(sentence) < 24 or len(sentence) > 750:
                continue
            overlap = required_terms & set(terms(sentence, max_terms=None))
            if overlap:
                options.append((index, sentence, overlap))
        if not options:
            continue
        chosen = []
        covered = set()
        # For comparisons, prefer distinct sentences that define each concept
        # before a later sentence that merely mentions both terms together.
        if "diferencia" in question.casefold() and len(required_terms) >= 2:
            for index, _sentence, overlap in options:
                if len(overlap) == 1 and overlap - covered:
                    chosen.append(index)
                    covered.update(overlap)
                if len(covered) >= len(required_terms) or len(chosen) >= 3:
                    break
        for _ in range(3 - len(chosen)):
            remaining = [item for item in options if item[0] not in chosen]
            if not remaining:
                break
            definition = "significa" in question.casefold()
            best = max(
                remaining,
                key=lambda item: (
                    len(item[2] - covered),
                    int(definition and "significa" in item[1].casefold()),
                    len(item[2]),
                    -item[0],
                ),
            )
            if not (best[2] - covered):
                break
            chosen.append(best[0])
            covered.update(best[2])
            if covered >= required_terms:
                break
        # Multi-concept questions need support from the approved card; at least
        # one question concept must also be explicit in the quoted sentence.
        metadata = hit["title"] + " " + hit["keywords"] + " " + hit["text"]
        document_coverage = required_terms & set(terms(metadata, max_terms=None))
        if len(document_coverage) < min(2, len(required_terms)) or not covered:
            continue
        excerpt = "\n".join(f"[S1] {sentences[index].strip()}" for index in sorted(chosen))
        if assess_generated_answer(excerpt, [hit]) == "accepted":
            return hit, excerpt
    return None


def _comparison_needs_distinct_evidence(question: str) -> list[str]:
    """Recognize explicit comparisons without treating context words as concepts."""
    normalized = question.casefold()

    comparative = (
        "diferencia" in normalized or "diferencian" in normalized or "diferenciar" in normalized
    )

    if not comparative:
        return []

    concepts = terms(question)

    # T1/T2 definitions must not be replaced by a contrast-agent discussion.
    if {"t1", "t2"} <= set(concepts) and not any(
        word in normalized for word in ("gadolinio", "contraste", "gbca")
    ):
        return ["t1", "t2"]

    # Preserve the existing generic two-concept comparison behavior.
    if "diferencia" in normalized and len(concepts) == 2:
        return concepts

    return []


def _independent_excerpt_support(text: str, concepts: list[str]) -> bool:
    """Reject a co-mention that does not explain both concepts separately."""
    parts = [set(terms(line, max_terms=None)) & set(concepts) for line in text.splitlines()]
    return all(any(part == {concept} for part in parts) for concept in concepts)


def _compose_two_card_comparison(question: str, root) -> tuple[list[dict], str] | None:
    """Use two trusted title-anchored definition excerpts if both exist."""
    concepts = _comparison_needs_distinct_evidence(question)
    if not concepts:
        return None
    cards, _ = load_trusted_corpus(root or default_root())
    selections = []
    for concept in concepts:
        matched = []
        for card in cards:
            title_terms = set(terms(card["title"], max_terms=None))
            if (title_terms & set(concepts)) != {concept}:
                continue
            sentences = re.split(r"(?<=[.!?])\s+", card["text"].strip())
            for sentence in sentences:
                sentence_terms = set(terms(sentence, max_terms=None)) & set(concepts)
                if sentence_terms == {concept} and 24 <= len(sentence) <= 750:
                    matched.append((card, sentence))
                    break
        # Ambiguous title-to-concept mapping must never be silently resolved.
        if len(matched) != 1:
            return None
        selections.append(matched[0])
    hits = [selection[0] for selection in selections]
    if len({hit["id"] for hit in hits}) != len(concepts):
        return None
    answer = "\n".join(
        f"[S{position}] {selection[1]}" for position, selection in enumerate(selections, 1)
    )
    if assess_generated_answer(answer, hits) != "accepted":
        return None
    return hits, answer


def _compose_intent_bound_evidence(question: str, root):
    """Narrow, auditable evidence routing for documented educational intents.

    Returns:
        (True, evidence): handled with validated evidence or abstention.
        (False, None): leave the decision to the existing general composer.

    This is not a general semantic entailment engine.
    """
    query = set(terms(question, max_terms=None))
    cards, _ = load_trusted_corpus(root or default_root())
    by_id = {card["id"]: card for card in cards}

    def select(card_id: str, fragment: str):
        card = by_id.get(card_id)
        if card is None:
            return True, None

        sentences = re.split(r"(?<=[.!?])\s+", card["text"].strip())
        matches = [sentence.strip() for sentence in sentences if fragment in sentence]

        if len(matches) != 1:
            return True, None

        excerpt = f"[S1] {matches[0]}"

        if assess_generated_answer(excerpt, [card]) != "accepted":
            return True, None

        return True, (card, excerpt)

    # An explicit T2 versus T2* comparison requires the approved
    # intrinsic-relaxation distinction, not an unrelated TR/TE card.
    normalized = question.casefold()
    if (
        re.search(r"\bt2\s*\*", normalized)
        and re.search(r"\bt2\b(?!\s*\*)", normalized)
        and any(marker in normalized for marker in ("diferencia", "diferencian", "diferenciar"))
    ):
        return select(
            "mri_t2",
            "Se debe diferenciar el T2 intrínseco de T2*",
        )

    # An absolute disease claim cannot be inferred from retention alone.
    if {"retencion", "gadolinio", "enfermedad"} <= query:
        return True, None

    # Select the direct T2 signal statement for this absolute claim.
    if {"gadolinio", "siempre", "t2"} <= query and ("aumenta" in query or "aumentar" in query):
        return select(
            "mri_contraste",
            "El acortamiento de T2 y T2* puede disminuir",
        )

    # Recover the authorized safety explanation, not an incidental keyword hit.
    if {"riesgo", "implantes"} <= query and ("mecanismos" in query or "mecanismo" in query):
        return select(
            "mri_cribado",
            "Es importante verificar los implantes y objetos",
        )

    return False, None


def _request_local_ollama(url: str, payload: bytes) -> dict:
    """Call only validated local Ollama; redirects are never followed."""
    safe = checked_ollama_url(url)
    parsed = urlsplit(safe)
    host = parsed.hostname
    if host is None:
        raise ValueError("Ollama host inválido")
    if host == "localhost":
        host = "127.0.0.1"

    connection = HTTPConnection(host, parsed.port or 11434, timeout=45)
    try:
        connection.request(
            "POST",
            "/api/generate",
            body=payload,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
        )
        response = connection.getresponse()
        if response.status != 200:
            raise ValueError(f"Respuesta HTTP inesperada: {response.status}")
        max_bytes = 512 * 1024
        raw = response.read(max_bytes + 1)
        if len(raw) > max_bytes:
            raise ValueError("Respuesta Ollama demasiado grande")
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError("Respuesta Ollama con formato inválido")
        return result
    finally:
        connection.close()


def ask(
    question: str,
    *,
    root=None,
    mode: str = "sparse",
    llm: str = "none",
    model: str = "qwen3:1.7b",
    ollama_url: str = "http://127.0.0.1:11434",
    top_k: int = 3,
) -> dict:
    good, why = screen_question(question)
    if not good:
        return {"status": "blocked", "answer": why, "citations": [], "hits": [], "notice": NOTICE}
    if mode not in {"sparse", "hybrid"} or llm not in {"none", "ollama"}:
        raise ValueError("Modo inválido")
    if top_k not in range(1, 9):
        raise ValueError("top_k debe estar entre 1 y 8")
    hits = (
        search_sparse(question, root, limit=top_k)
        if mode == "sparse"
        else search_hybrid(question, root, limit=top_k)
    )
    evidence = _compose_approved_excerpts(question, hits) if hits else None
    concepts = _comparison_needs_distinct_evidence(question)
    handled, intent_evidence = _compose_intent_bound_evidence(question, root)
    if handled:
        evidence = intent_evidence
    if concepts and not handled:
        comparison = _compose_two_card_comparison(question, root)
        if comparison is not None:
            evidence = comparison
        elif evidence is None or not _independent_excerpt_support(evidence[1], concepts):
            evidence = None
    if evidence is None:
        return {
            "status": "insufficient_evidence",
            "answer": "No encuentro evidencia suficiente en el corpus local para responder. "
            "Reformule la pregunta o consulte las fuentes oficiales.",
            "citations": [],
            "hits": [],
            "notice": NOTICE,
        }
    chosen, extractive = evidence
    hits = chosen if isinstance(chosen, list) else [chosen]
    _, sources = load_corpus(root)
    citations = []
    for i, h in enumerate(hits, 1):
        for sid in h["source_ids"]:
            source = sources[sid]
            citations.append(
                {
                    "ref": f"S{i}",
                    "card_id": h["id"],
                    "source_id": sid,
                    "title": source["title"],
                    "url": source["url"],
                    "rights": source["rights"],
                }
            )
    response = extractive
    engine_status = "extractive"
    if llm == "ollama":
        url = checked_ollama_url(ollama_url)
        prompt = build_grounded_prompt(question, hits)
        payload = json.dumps(
            {
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": 0, "num_predict": 300},
                "think": False,
            }
        ).encode()
        try:
            output = _request_local_ollama(url, payload)
            result = output.get("response")
            assessment = assess_generated_answer(result, hits)
            if assessment == "accepted":
                response = result.strip()
                engine_status = "ollama_verbatim_source_span_verified"
            elif assessment == "citation_invalid":
                engine_status = "ollama_citation_invalid_extractive_fallback"
            else:
                engine_status = "ollama_unverified_extractive_fallback"
        except (OSError, ValueError, KeyError, TimeoutError, HTTPException):
            engine_status = "ollama_unavailable_extractive_fallback"
    return {
        "status": "ok",
        "answer": response,
        "citations": citations,
        "hits": [
            {
                "id": x["id"],
                "title": x["title"],
                "module": x["module"],
                "coverage": x.get("term_coverage"),
                "rrf": x.get("rrf_score"),
            }
            for x in hits
        ],
        "engine_status": engine_status,
        "notice": NOTICE,
    }
