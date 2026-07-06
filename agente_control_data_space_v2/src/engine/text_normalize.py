# src/engine/text_normalize.py
# -*- coding: utf-8 -*-
"""
Utilidades genéricas de normalización de texto para fragmentos de búsqueda.

Son MECANISMO puro (sin dominio): el proyecto decide qué stopwords/sinónimos
aplicar y a qué tools; aquí solo están las funciones que transforman texto.

  - strip_accents(s): quita tildes/diacríticos (presión → presion).
  - normalize_fragment(s, stopwords, synonyms): pipeline completo —
    minúsculas, sin acentos, aplica sinónimos token a token, elimina
    stopwords, colapsa espacios. Conserva el orden de los tokens restantes.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, Mapping, Optional

_WS_RE = re.compile(r"\s+")
# Separadores que tratamos como espacio al tokenizar (guiones, barras, comas…).
_SEP_RE = re.compile(r"[\-_/.,;:]+")


def strip_accents(s: str) -> str:
    """Elimina diacríticos: 'batería' → 'bateria', 'presión' → 'presion'."""
    if not s:
        return s
    nfkd = unicodedata.normalize("NFKD", s)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def normalize_fragment(
    s: str,
    stopwords: Optional[Iterable[str]] = None,
    synonyms: Optional[Mapping[str, str]] = None,
) -> str:
    """
    Normaliza un fragmento de búsqueda de forma determinista:
      1. minúsculas + sin acentos
      2. separadores (-, _, /, …) → espacio
      3. sustitución de sinónimos token a token (claves ya sin acento)
      4. eliminación de stopwords (ya sin acento)
      5. colapso de espacios

    Devuelve el fragmento limpio. Si tras limpiar no queda nada, devuelve el
    original normalizado (sin stopwords-stripping) para no romper la búsqueda.
    """
    if not s or not isinstance(s, str):
        return s

    base = strip_accents(s.lower())
    base = _SEP_RE.sub(" ", base)
    tokens = _WS_RE.sub(" ", base).strip().split(" ")

    sw = {strip_accents(w.lower()) for w in (stopwords or [])}
    syn = {strip_accents(k.lower()): v for k, v in (synonyms or {}).items()}

    out = []
    for tok in tokens:
        if not tok:
            continue
        tok = syn.get(tok, tok)        # aplicar sinónimo si existe
        if tok in sw:
            continue                    # descartar stopword
        out.append(tok)

    cleaned = " ".join(out).strip()
    if cleaned:
        return cleaned
    # Si las stopwords se lo comieron todo, devolver al menos el texto sin acentos.
    return _WS_RE.sub(" ", base).strip()


__all__ = ["strip_accents", "normalize_fragment"]