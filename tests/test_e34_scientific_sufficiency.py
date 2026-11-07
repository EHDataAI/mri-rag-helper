"""RC17-E34: scientific answer sufficiency acceptance tests."""

import re

from mri_rag.answer import ask


def _answer(question):
    result = ask(question, mode="sparse", llm="none", top_k=8)
    assert result["status"] == "ok", result
    assert result["citations"], result
    assert result["answer"].strip(), result
    return result["answer"].casefold()


def test_e34_contrast_explains_relaxation_mechanism():
    answer = _answer("¿Qué hacen los medios de contraste en resonancia magnética?")

    assert re.search(r"\bt1\b", answer)
    assert re.search(r"\bt2\b", answer)
    assert any(word in answer for word in ("acort", "reduc", "disminu"))
    assert any(word in answer for word in ("señal", "intensidad"))


def test_e34_implant_screening_explains_actual_risks():
    answer = _answer(
        "¿Por qué es importante verificar los implantes antes de una resonancia magnética?"
    )

    thermal = any(word in answer for word in ("quemadura", "calentamiento", "térmica"))

    mechanical = any(word in answer for word in ("desplazamiento", "torque", "proyectil", "fuerza"))

    electronic = any(
        word in answer for word in ("malfuncionamiento", "funcionamiento", "interferencia")
    )

    assert thermal
    assert mechanical
    assert electronic
