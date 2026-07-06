"""
Configuración centralizada de logging.

- Por defecto las líneas van en JSON (una línea = un objeto), apto para agregadores.
- En local: LOG_FORMAT=text para salida legible sin JSON.
- Nivel: LOG_LEVEL=DEBUG|INFO|WARNING|ERROR|CRITICAL (por defecto INFO).

Uvicorn y la app comparten el mismo handler tras llamar a setup_logging().
"""
from __future__ import annotations

import logging
import os
import sys

from pythonjsonlogger.json import JsonFormatter

_LEVEL_BY_NAME: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "WARN": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def _resolve_log_level() -> int:
    raw = (os.environ.get("LOG_LEVEL") or "INFO").strip().upper()
    return _LEVEL_BY_NAME.get(raw, logging.INFO)


def setup_logging() -> None:
    log_format = (os.environ.get("LOG_FORMAT") or "json").strip().lower()
    level = _resolve_log_level()

    handler = logging.StreamHandler(sys.stdout)
    if log_format == "text":
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"),
        )
    else:
        handler.setFormatter(
            JsonFormatter(
                "%(timestamp)s %(level)s %(name)s %(message)s",
                rename_fields={"levelname": "level", "name": "logger"},
                timestamp=True,
            ),
        )

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)

    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        log = logging.getLogger(name)
        log.handlers.clear()
        log.addHandler(handler)
        log.setLevel(level)
        log.propagate = False
