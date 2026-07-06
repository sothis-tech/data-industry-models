# src/engine/response_processing.py
# -*- coding: utf-8 -*-
"""
Procesado de respuestas del agente.

Responsabilidades:
  1. Extraer texto plano del objeto AgentOutput / ChatMessage sin que aparezca
     el prefijo 'assistant:' u otros prefijos de rol.
  2. Detectar si el LLM ha producido JSON (por el prompt actual) y usar sus
     campos text/speech/data si están bien formados.
  3. Si no hay JSON válido, reconstruir el payload {text, speech, data} desde
     el texto plano.
  4. Garantizar que el campo `text` se sirve con markdown intacto para el
     navegador y el campo `speech` se sirve corto y sin formato para TTS.

NO se eliminan las respuestas — siempre devolvemos algo útil al usuario.
"""

import json
import re
from typing import Any, Optional

try:
    from llama_index.core.base.llms.types import ChatMessage
except Exception:
    ChatMessage = None  # type: ignore


# ══════════════════════════════════════════════════════════════════════════════
# 1. EXTRACCIÓN DE TEXTO PLANO (sin prefijos 'assistant:')
# ══════════════════════════════════════════════════════════════════════════════

_ROLE_PREFIX_RE = re.compile(
    r"^\s*(assistant|user|system|tool|function)\s*:\s*",
    re.IGNORECASE,
)


def _strip_role_prefix(text: str) -> str:
    """Elimina prefijos 'assistant:', 'user:', etc. del inicio, incluso repetidos."""
    if not text:
        return ""
    prev = None
    while prev != text:
        prev = text
        text = _ROLE_PREFIX_RE.sub("", text, count=1).lstrip()
    return text


def _to_text(obj: Any) -> str:
    """
    Convierte AgentOutput / ChatMessage / str / lista en texto plano.

    El problema del prefijo 'assistant:' venía de que el código antiguo caía
    a `str(obj)` cuando obj era un ChatMessage, y ChatMessage.__str__ formatea
    como "role: content". Aquí extraemos primero por .response/.content y solo
    caemos a str() como último recurso, limpiando siempre el prefijo.
    """
    if obj is None:
        return ""

    # 1. AgentOutput tiene .response (suele ser ChatMessage)
    response_attr = getattr(obj, "response", None)
    if response_attr is not None:
        if hasattr(response_attr, "content"):
            return _extract_content(response_attr.content)
        if isinstance(response_attr, str):
            return _strip_role_prefix(response_attr)
        if response_attr is not obj:
            return _to_text(response_attr)

    # 2. ChatMessage directo
    content = getattr(obj, "content", None)
    if content is not None:
        return _extract_content(content)

    # 3. Lista de mensajes
    if isinstance(obj, list):
        return "\n".join(_to_text(m) for m in obj if m is not None)

    # 4. String puro
    if isinstance(obj, str):
        return _strip_role_prefix(obj)

    # 5. Último recurso
    return _strip_role_prefix(str(obj).strip())


def _extract_content(content: Any) -> str:
    """Extrae texto de un content (str, lista de bloques, o cualquier objeto)."""
    if content is None:
        return ""
    if isinstance(content, str):
        return _strip_role_prefix(content)
    if isinstance(content, list):
        parts = []
        for block in content:
            text = getattr(block, "text", None)
            if text:
                parts.append(str(text))
            elif isinstance(block, str):
                parts.append(block)
            elif block is not None:
                parts.append(_strip_role_prefix(str(block)))
        return "\n".join(parts)
    return _strip_role_prefix(str(content))


# ══════════════════════════════════════════════════════════════════════════════
# 2. DETECCIÓN DE JSON EN LA RESPUESTA (prompt actual lo pide al LLM)
# ══════════════════════════════════════════════════════════════════════════════

def _try_parse_json_response(text: str) -> Optional[dict]:
    """
    Si el LLM produjo {"text": ..., "speech": ..., "data": ...} (con o sin
    fences ```json), devuelve el dict. Si no, None.

    Tolerante: el JSON puede estar embebido en texto ('Aquí tienes: {...}'),
    con fences, o como dict suelto.
    """
    if not text:
        return None

    candidates = []

    # 1. Bloque con fences ```json ... ```
    fenced = re.search(r"```(?:json|JSON)?\s*(\{[\s\S]*?\})\s*```", text)
    if fenced:
        candidates.append(fenced.group(1))

    # 2. Primer dict suelto que aparezca
    bare = re.search(r"(\{[\s\S]*\})", text)
    if bare:
        candidates.append(bare.group(1))

    for cand in candidates:
        try:
            obj = json.loads(cand)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict) and ("text" in obj or "speech" in obj):
            return obj

    return None


# ══════════════════════════════════════════════════════════════════════════════
# 3. LIMPIEZA DE FRASES PROHIBIDAS (red de seguridad: aunque el LLM se rebele
#    contra el prompt, quitamos las muletillas de cierre)
# ══════════════════════════════════════════════════════════════════════════════

_FORBIDDEN_PATTERNS = [
    re.compile(r"\bsi\s+necesitas\s+(más\s+)?información[^.!?\n]*[.!?]?", re.IGNORECASE),
    re.compile(r"\bsi\s+deseas[^.!?\n]*[.!?]?", re.IGNORECASE),
    re.compile(r"\bespero\s+haberte\s+ayudado[^.!?\n]*[.!?]?", re.IGNORECASE),
    re.compile(r"\bházmelo\s+saber[^.!?\n]*[.!?]?", re.IGNORECASE),
    re.compile(r"\bhazmelo\s+saber[^.!?\n]*[.!?]?", re.IGNORECASE),
    re.compile(r"\bno\s+dudes\s+en\s+preguntar[^.!?\n]*[.!?]?", re.IGNORECASE),
    re.compile(r"\bsi\s+necesitas\s+(algo\s+)?más[^.!?\n]*[.!?]?", re.IGNORECASE),
    re.compile(r"\b(estoy|quedo)\s+a\s+tu\s+disposición[^.!?\n]*[.!?]?", re.IGNORECASE),
    re.compile(r"\bavísame\s+si[^.!?\n]*[.!?]?", re.IGNORECASE),
    re.compile(r"\bavisame\s+si[^.!?\n]*[.!?]?", re.IGNORECASE),
]


def _strip_forbidden_phrases(text: str) -> str:
    s = text
    for pat in _FORBIDDEN_PATTERNS:
        s = pat.sub("", s)
    return s


# ══════════════════════════════════════════════════════════════════════════════
# 4. LIMPIEZA DEL CAMPO `text` (mantiene Markdown, quita prefijos y muletillas)
# ══════════════════════════════════════════════════════════════════════════════

def clean_text_response(text: str) -> str:
    """
    Para servir en navegador / UI con Markdown intacto.
    - Quita prefijos 'assistant:'
    - Quita muletillas de cierre prohibidas
    - Colapsa saltos múltiples
    - NO toca el markdown (negritas, listas, tablas, código)
    """
    if not text:
        return ""
    s = _strip_role_prefix(text)
    s = _strip_forbidden_phrases(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# ══════════════════════════════════════════════════════════════════════════════
# 5. LIMPIEZA DEL CAMPO `speech` (texto plano corto para TTS)
# ══════════════════════════════════════════════════════════════════════════════

# Rango Unicode amplio para emojis (no exhaustivo, pero pilla la inmensa mayoría)
_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"    # símbolos misceláneos
    "\U00002600-\U000027BF"    # dingbats
    "\U0001F900-\U0001F9FF"    # símbolos suplementarios
    "\U0001F600-\U0001F64F"    # emoticonos
    "]+",
    flags=re.UNICODE,
)


def clean_speech_response(text: str, max_sentences: int = 2) -> str:
    """
    Produce un texto plano apto para TTS:
      - Sin Markdown (negritas, listas, código, tablas, links)
      - Sin URLs
      - Sin emojis ni símbolos decorativos
      - Sin URNs largos (sustituidos por su última parte)
      - Limitado a `max_sentences` frases (2 por defecto)
      - Espacios colapsados

    Diseñado para no hacer al usuario escuchar 30 segundos de markdown leído.
    """
    if not text:
        return ""

    s = clean_text_response(text)

    # --- Markdown ---
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)              # **negrita**
    s = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"\1", s)  # *cursiva*
    s = re.sub(r"```[\s\S]*?```", "", s)                # bloques de código
    s = re.sub(r"`([^`]+?)`", r"\1", s)                 # `inline code`
    s = re.sub(r"^#+\s*", "", s, flags=re.MULTILINE)    # encabezados
    s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", s)    # [texto](url) → texto
    s = re.sub(r"^\s*[-*+]\s+", "", s, flags=re.MULTILINE)  # bullets
    s = re.sub(r"^\s*\d+\.\s+", "", s, flags=re.MULTILINE)  # listas numeradas
    s = re.sub(r"\|", " ", s)                            # separadores de tabla

    # --- URLs y URNs ---
    s = re.sub(r"https?://\S+", "", s)
    # urn:ngsi-ld:Person:operador-001 → operador-001
    s = re.sub(r"urn:[^\s:`)\]]+(?::[^\s:`)\]]+)+", lambda m: m.group(0).split(":")[-1], s)

    # --- Emojis y símbolos decorativos ---
    s = _EMOJI_RE.sub("", s)
    s = re.sub(r"[⚠✅❌🔥💡📊📋🚀🎯🤖👤💬🌐💾🧠📄→←↑↓•·]", "", s)

    # --- Espacios ---
    s = re.sub(r"\s+", " ", s).strip()

    if not s:
        return ""

    # --- Limitar a N frases ---
    sentences = [seg.strip() for seg in re.split(r"(?<=[.!?])\s+", s) if seg.strip()]
    if not sentences:
        return s
    return " ".join(sentences[:max_sentences])


# ══════════════════════════════════════════════════════════════════════════════
# 6. CONSTRUCTOR DEL PAYLOAD FINAL
# ══════════════════════════════════════════════════════════════════════════════

def build_response_payload(
    raw_text: str,
    modality: str = "text",
    data: Optional[dict] = None,
) -> dict:
    """
    Devuelve {"text": ..., "speech": ..., "data": ...} listo para servir.

    Estrategia híbrida:
      1. Si el LLM emitió JSON válido con text/speech → se usan esos campos.
      2. Si no → se usa el texto plano para text, y se sintetiza el speech
         desde text cuando modality=speech.
      3. El text siempre conserva su markdown.
      4. El speech es siempre texto plano corto (2 frases máx).
      5. Si modality=text → speech queda en None.
    """
    raw_text = raw_text or ""

    parsed       = _try_parse_json_response(raw_text)
    parsed_data: dict = {}
    speech_raw   = ""

    if parsed:
        text_raw   = str(parsed.get("text") or "").strip()
        speech_raw = str(parsed.get("speech") or "").strip()
        p_data     = parsed.get("data")
        if isinstance(p_data, dict):
            parsed_data = p_data
        # Si el JSON venía vacío, usamos el raw como text
        if not text_raw:
            text_raw = raw_text
    else:
        text_raw = raw_text

    cleaned_text = clean_text_response(text_raw)
    if not cleaned_text:
        cleaned_text = "No se obtuvo respuesta del sistema."

    if modality == "speech":
        # Preferimos el speech que vino del LLM (suele estar mejor focalizado)
        if speech_raw:
            speech = clean_speech_response(speech_raw, max_sentences=2)
        else:
            speech = clean_speech_response(cleaned_text, max_sentences=2)

        if not speech:
            # Último recurso: primeras 200 chars planas
            fallback = re.sub(r"\s+", " ", cleaned_text)[:200]
            speech = fallback or "Sin respuesta disponible."
    else:
        speech = None

    merged_data = {**parsed_data, **(data or {})}

    return {
        "text":   cleaned_text,
        "speech": speech,
        "data":   merged_data,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Exportación pública
# ══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "_to_text",
    "clean_text_response",
    "clean_speech_response",
    "build_response_payload",
]