"""Límites preventivos: no convierte el RAG en evaluador clínico."""

from __future__ import annotations

import html
import re
import unicodedata
from urllib.parse import urlparse

INJECTION = re.compile(
    r"(?i)(ignora\s+(?:(?:todas?|las|tus|mis|sus|anteriores|previas)\s+)*instrucciones|"
    r"olvida\s+(?:(?:todas?|las|tus|anteriores|previas)\s+)*instrucciones|"
    r"revela (tu |el )?(prompt|system)|"
    r"ignore (all |previous )?instructions|system prompt|act[uú]a como sistema|"
    r"desactiva (tus |las )?restricciones|\bdeveloper message\b)"
)
PATIENT = re.compile(
    r"(?i)\b(mi paciente|paciente con|tengo un|tengo una|me puedo|puedo entrar|puedo hacerme|"
    r"puede entrar|estoy embarazada|mi madre|mi padre|mi hijo|a este paciente|"
    r"debo administrar|qu[eé] dosis|me hago una|me har[aá]n|es seguro hacer|"
    r"cu[aá]ntos?\s+(?:mililitros|ml|mg|mmol)\s+de\s+"
    r"(?:gadolinio|contraste)\s+debo\s+recibir)\b"
)
RISK = re.compile(
    r"(?i)\b(marcapasos|implante|gadolinio|contraste|embarazad[ao]|"
    r"resonancia|rm|3t|1[.,]5t|sar|renal|desfibrilador)\b"
)


# These checks are high-signal *input-boundary* rules, not a general AI firewall.
# Retrieved documents need independent scanning and separate trust boundaries.
ROLE_MARKERS = re.compile(
    r"(?im)(?:<\|(?:system|developer|assistant|tool|im_start|im_end)\|>|"
    r"\[/?INST\]|\[(?:im_start|im_end)\]|<<\s*/?SYS\s*>>|"
    r"^\s*(?:system|developer|assistant|tool)\s*:|"
    r"^\s*#{1,6}\s*(?:system|developer|assistant)\b)"
)
HIDDEN_MARKUP = re.compile(
    r"(?is)(?:<!--|-->|<\s*/?script\b|<\s*/?style\b|"
    r"\bdisplay\s*:\s*none\b|\bvisibility\s*:\s*hidden\b|"
    r"\bfont-size\s*:\s*0\b)"
)


def screen_question(question: str) -> tuple[bool, str]:
    """Reject high-signal injection carriers before retrieval or generation."""
    if not isinstance(question, str) or not question.strip():
        return False, "Ingrese una pregunta."
    if len(question) > 1500:
        return False, "Pregunta demasiado larga (máximo 1500 caracteres)."
    if any(
        unicodedata.category(char) in {"Cf", "Cs"}
        or (unicodedata.category(char) == "Cc" and char not in "\n\r\t")
        for char in question
    ):
        return False, "Consulta con caracteres de control u ocultos no permitidos."

    normalized = unicodedata.normalize("NFKC", question)
    # At most two rounds of HTML entity decoding; bound expanded length.
    for _ in range(2):
        decoded = html.unescape(normalized)
        if decoded == normalized:
            break
        normalized = decoded
    if len(normalized) > 1500:
        return False, "Pregunta demasiado larga tras normalización."
    if any(
        unicodedata.category(char) in {"Cf", "Cs"}
        or (unicodedata.category(char) == "Cc" and char not in "\n\r\t")
        for char in normalized
    ):
        return False, "Consulta con caracteres de control u ocultos no permitidos."
    if (
        INJECTION.search(normalized)
        or ROLE_MARKERS.search(normalized)
        or HIDDEN_MARKUP.search(normalized)
    ):
        return False, (
            "He detectado una instrucción que intenta modificar las reglas de seguridad "
            "o verificación de fuentes del asistente. No puedo seguirla. "
            "Puede formular una pregunta educativa sobre resonancia magnética; "
            "responderé únicamente con evidencia del corpus autorizado."
        )
    if PATIENT.search(normalized) and RISK.search(normalized):
        return False, (
            "No puedo determinar la seguridad ni decidir un procedimiento para una "
            "persona concreta. Consulte al equipo de RM y verifique las condiciones del "
            "fabricante y el protocolo institucional. Referencia: "
            "https://www.fda.gov/radiation-emitting-products/mri-magnetic-resonance-imaging/"
            "benefits-and-risks"
        )
    return True, ""


def checked_ollama_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Ollama solo está permitido en loopback HTTP local")
    if (
        parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError("URL de Ollama no permitida")
    if parsed.port not in {11434, None}:
        raise ValueError("Se exige el puerto local estándar de Ollama")
    return url.rstrip("/")
