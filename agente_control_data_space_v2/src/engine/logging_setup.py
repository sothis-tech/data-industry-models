"""
logging_setup.py
~~~~~~~~~~~~~~~~

Sistema centralizado de logging para el proyecto MCP industrial.

Proporciona:
- Configuración declarativa desde YAML con fallback robusto.
- Contexto por petición vía contextvars (request_id, session_id, user_id).
- Loggers especializados: conversations, metrics, tools, agent.
- Filtros de redacción de secretos.
- Formateo JSON estructurado para análisis posterior.
- Idempotencia: múltiples llamadas no duplican handlers.

Variables de entorno:
    LOG_CFG       Ruta al YAML (default: logging_config.yaml junto al módulo)
    LOG_LEVEL     Nivel del fallback si no hay YAML (default: INFO)
    LOG_DIR       Directorio de logs (default: ./logs)
"""
from __future__ import annotations

import json
import logging
import logging.config
import os
import re
import sys
import time
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

try:
    import yaml  # type: ignore
except ImportError:
    yaml = None


# ═══════════════════════════════════════════════════════════════════════
# CONTEXTO POR PETICIÓN (contextvars — seguro en async)
# ═══════════════════════════════════════════════════════════════════════

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
_session_id_var: ContextVar[str] = ContextVar("session_id", default="-")
_user_id_var:    ContextVar[str] = ContextVar("user_id",    default="-")
_client_id_var:  ContextVar[str] = ContextVar("client_id",  default="-")


def set_log_context(
    request_id: Optional[str] = None,
    session_id: Optional[str] = None,
    user_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> None:
    """Establece contexto de logging para la petición actual."""
    if request_id is not None: _request_id_var.set(request_id)
    if session_id is not None: _session_id_var.set(session_id)
    if user_id is not None:    _user_id_var.set(user_id)
    if client_id is not None:  _client_id_var.set(client_id)


def clear_log_context() -> None:
    """Limpia el contexto al finalizar la petición."""
    _request_id_var.set("-")
    _session_id_var.set("-")
    _user_id_var.set("-")
    _client_id_var.set("-")


def get_log_context() -> dict:
    """Devuelve el contexto actual como dict."""
    return {
        "request_id": _request_id_var.get(),
        "session_id": _session_id_var.get(),
        "user_id":    _user_id_var.get(),
        "client_id":  _client_id_var.get(),
    }


# ═══════════════════════════════════════════════════════════════════════
# FILTROS
# ═══════════════════════════════════════════════════════════════════════

class ContextFilter(logging.Filter):
    """Inyecta request_id, session_id, user_id, client_id en cada LogRecord."""
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get()
        record.session_id = _session_id_var.get()
        record.user_id    = _user_id_var.get()
        record.client_id  = _client_id_var.get()
        return True


class SecretRedactionFilter(logging.Filter):
    """Redacta patrones sensibles en mensajes de log."""
    PATTERNS = [
        (re.compile(r"(api[_-]?key['\"]?\s*[:=]\s*['\"]?)([^'\",\s}]+)", re.I), r"\1***REDACTED***"),
        (re.compile(r"(password['\"]?\s*[:=]\s*['\"]?)([^'\",\s}]+)", re.I),    r"\1***REDACTED***"),
        (re.compile(r"(secret['\"]?\s*[:=]\s*['\"]?)([^'\",\s}]+)", re.I),      r"\1***REDACTED***"),
        (re.compile(r"(token['\"]?\s*[:=]\s*['\"]?)([^'\",\s}]+)", re.I),       r"\1***REDACTED***"),
        (re.compile(r"(Bearer\s+)([A-Za-z0-9._\-]+)"),                          r"\1***REDACTED***"),
        (re.compile(r"(sk-[A-Za-z0-9]{10,})"),                                  r"***REDACTED***"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            for pattern, repl in self.PATTERNS:
                msg = pattern.sub(repl, msg)
            record.msg = msg
            record.args = ()
        except Exception:
            pass
        return True


# ═══════════════════════════════════════════════════════════════════════
# FORMATTER JSON
# ═══════════════════════════════════════════════════════════════════════

class JsonFormatter(logging.Formatter):
    """
    Formatter JSON para logs estructurados (conversations, metrics).
    - Timestamp ISO8601 con microsegundos REALES.
    - Filtra campos internos ruidosos (taskName, etc.).
    - Serializa cualquier atributo extra pasado vía logger.info(..., extra={...}).
    """
    RESERVED = {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "message", "asctime",
        # Campos internos de asyncio que no aportan valor
        "taskName",
    }

    def format(self, record: logging.LogRecord) -> str:
        # Timestamp con microsegundos correctos usando record.created
        dt = datetime.fromtimestamp(record.created)
        timestamp = dt.isoformat(timespec="microseconds")

        payload: dict[str, Any] = {
            "timestamp":  timestamp,
            "level":      record.levelname,
            "logger":     record.name,
            "message":    record.getMessage(),
            "request_id": getattr(record, "request_id", "-"),
            "session_id": getattr(record, "session_id", "-"),
            "user_id":    getattr(record, "user_id", "-"),
            "client_id":  getattr(record, "client_id", "-"),
        }
        for key, value in record.__dict__.items():
            if key not in self.RESERVED and key not in payload and not key.startswith("_"):
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = str(value)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


# ═══════════════════════════════════════════════════════════════════════
# GESTOR CENTRAL
# ═══════════════════════════════════════════════════════════════════════

class LoggingManager:
    _instance: Optional["LoggingManager"] = None
    _configured: bool = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_init"):
            return
        self._init = True
        # src/engine/logging_setup.py → la raíz del proyecto está dos niveles
        # por encima (src/engine → src → <root>). Los logs viven en var/logs/.
        _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
        self.log_dir = Path(os.getenv("LOG_DIR", _PROJECT_ROOT / "var" / "logs"))
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.default_level = os.getenv("LOG_LEVEL", "INFO").upper()

    def setup(self, config_path: Optional[os.PathLike] = None, force: bool = False) -> None:
        if self._configured and not force:
            return

        cfg_path = (
            Path(os.getenv("LOG_CFG"))
            if os.getenv("LOG_CFG")
            else Path(config_path) if config_path
            else Path(__file__).resolve().parent.parent.parent / "config" / "logging_config.yaml"
        )

        if yaml is None or not cfg_path.exists():
            self._install_basic_config()
            self._silence_third_party()
            self._install_excepthook()
            self._configured = True
            logging.getLogger("mcp").warning(
                "Usando logging básico (yaml=%s, exists=%s, path=%s)",
                yaml is not None, cfg_path.exists(), cfg_path,
            )
            return

        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
            self._rewrite_file_paths(config)
            logging.config.dictConfig(config)
            self._silence_third_party()
            self._install_excepthook()
            self._configured = True
            logging.getLogger("mcp").info(
                "Logging configurado │ config=%s │ logs=%s", cfg_path, self.log_dir
            )
        except Exception as e:
            self._install_basic_config()
            self._silence_third_party()
            self._install_excepthook()
            self._configured = True
            logging.getLogger("mcp").exception("Fallo cargando %s: %s", cfg_path, e)

    def _rewrite_file_paths(self, config: dict) -> None:
        for h_cfg in config.get("handlers", {}).values():
            if "filename" in h_cfg:
                path = Path(h_cfg["filename"])
                if not path.is_absolute():
                    path = self.log_dir / path
                    path.parent.mkdir(parents=True, exist_ok=True)
                    h_cfg["filename"] = str(path)

    def _install_basic_config(self) -> None:
        from logging.handlers import RotatingFileHandler
        root = logging.getLogger()
        for h in list(root.handlers):
            root.removeHandler(h)
        root.setLevel(self.default_level)
        fmt = logging.Formatter(
            "%(asctime)s [%(levelname)-7s] %(name)s [%(session_id)s/%(request_id)s] %(message)s"
        )
        ctx_filter = ContextFilter()
        redact = SecretRedactionFilter()
        # Mismo esquema de subcarpetas que el YAML: var/logs/<categoría>/<fichero>.
        (self.log_dir / "app").mkdir(parents=True, exist_ok=True)
        (self.log_dir / "errors").mkdir(parents=True, exist_ok=True)
        for handler, level in [
            (logging.StreamHandler(sys.stdout), self.default_level),
            (RotatingFileHandler(self.log_dir / "app" / "app.log",
                                 maxBytes=5_000_000, backupCount=5, encoding="utf-8"),
             self.default_level),
            (RotatingFileHandler(self.log_dir / "errors" / "errors.log",
                                 maxBytes=5_000_000, backupCount=10, encoding="utf-8"),
             logging.WARNING),
        ]:
            handler.setLevel(level)
            handler.setFormatter(fmt)
            handler.addFilter(ctx_filter)
            handler.addFilter(redact)
            root.addHandler(handler)

    def _silence_third_party(self) -> None:
        # Silenciamos asyncio agresivamente: los GeneratorExit del cierre
        # del stdio_client en Python 3.13 + MCP son ruidosos pero inofensivos.
        noisy = {
            "httpx": logging.WARNING,
            "httpcore": logging.WARNING,
            "openai": logging.WARNING,
            "openai._base_client": logging.WARNING,
            "urllib3": logging.WARNING,
            "uvicorn.access": logging.WARNING,
            "asyncio": logging.CRITICAL,  # muy ruidoso durante Ctrl+C
        }
        for name, level in noisy.items():
            logging.getLogger(name).setLevel(level)

    def _install_excepthook(self) -> None:
        def _hook(exc_type, exc_value, exc_tb):
            if issubclass(exc_type, KeyboardInterrupt):
                # Ctrl+C: salir limpiamente sin traceback
                sys.stderr.write("\n👋 Cerrando por interrupción de usuario (Ctrl+C)\n")
                return
            logging.getLogger("mcp.uncaught").critical(
                "Excepción no manejada", exc_info=(exc_type, exc_value, exc_tb)
            )
        sys.excepthook = _hook


# ═══════════════════════════════════════════════════════════════════════
# API PÚBLICA
# ═══════════════════════════════════════════════════════════════════════

_manager = LoggingManager()


def setup_logging(config_path: Optional[os.PathLike] = None, force: bool = False) -> None:
    """Inicializa el sistema de logging (idempotente)."""
    _manager.setup(config_path, force)


def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger del proyecto."""
    return logging.getLogger(name)


def log_startup_banner(component: str, mode: str = "", extra: Optional[dict] = None) -> None:
    """
    Emite un banner visual de arranque para diferenciar ejecuciones en el log.
    Útil cuando el servidor se reinicia varias veces.

    Ejemplo:
        log_startup_banner("API Gateway", mode="FastAPI", extra={"port": 8081})

    Produce:
        ══════════════════════════════════════════════════════════════
        🚀 ARRANQUE │ API Gateway │ FastAPI │ pid=12345 │ port=8081
        ══════════════════════════════════════════════════════════════
    """
    logger = logging.getLogger("mcp")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pid = os.getpid()

    parts = [f"🚀 ARRANQUE", component]
    if mode:
        parts.append(mode)
    parts.append(f"pid={pid}")
    parts.append(timestamp)
    if extra:
        for k, v in extra.items():
            parts.append(f"{k}={v}")

    banner_line = " │ ".join(parts)
    separator = "═" * min(len(banner_line) + 4, 100)

    logger.info(separator)
    logger.info(banner_line)
    logger.info(separator)


def log_shutdown_banner(component: str, reason: str = "cierre normal") -> None:
    """Emite un banner visual de cierre para marcar el fin de ejecución."""
    logger = logging.getLogger("mcp")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("─" * 80)
    logger.info("🛑 CIERRE │ %s │ %s │ %s", component, reason, timestamp)
    logger.info("─" * 80)


def log_conversation(
    question: str,
    answer: str,
    *,
    status: str = "success",
    error_code: str = "",
    modality: str = "text",
    metadata: Optional[dict] = None,
) -> None:
    """Registra un turno Q&A en conversations.jsonl."""
    logger = logging.getLogger("mcp.conversations")
    extra = {
        "event":      "conversation",
        "question":   question,
        "answer":     answer,
        "status":     status,
        "error_code": error_code or None,
        "modality":   modality,
    }
    if metadata:
        extra["metadata"] = metadata
    logger.info("conversation_turn", extra=extra)


def log_metrics(metrics: dict) -> None:
    """Registra métricas en metrics.jsonl."""
    logger = logging.getLogger("mcp.metrics")
    logger.info("request_metrics", extra={"event": "metrics", **metrics})


def log_tool_call(
    server: str,
    tool: str,
    *,
    args: Optional[dict] = None,
    result_preview: Optional[str] = None,
    duration_ms: Optional[float] = None,
    error: Optional[str] = None,
) -> None:
    """
    Registra una llamada a tool MCP.
    - INFO si ok, ERROR si error, WARNING si el resultado contiene HTTP 4xx/5xx.
    Resultado completo, sin truncado.
    """
    logger = logging.getLogger("mcp.tools")
    if error:
        logger.error(
            "tool_call_failed │ %s.%s │ error=%s │ args=%s",
            server, tool, error, args,
        )
        return

    duration_str = f"{duration_ms:.1f}ms" if duration_ms is not None else "-"
    preview = result_preview or ""

    # Heurística: detectar errores HTTP embebidos en el resultado
    has_http_error = any(
        marker in preview
        for marker in ("❌ HTTP 4", "❌ HTTP 5", '"found": false', "isError=True")
    )

    level = logger.warning if has_http_error else logger.info
    status_tag = "tool_call_partial" if has_http_error else "tool_call_ok"
    level(
        "%s │ %s.%s │ %s │ args=%s │ result=%s",
        status_tag, server, tool, duration_str, args, preview,
    )


def log_agent_flow(
    direction: str,           # "request" o "response"
    agent: str,               # nombre del especialista o "Gestor"
    message: str,
    *,
    duration_ms: Optional[float] = None,
    metadata: Optional[dict] = None,
) -> None:
    """
    Registra el flujo de mensajes entre el Gestor y los Especialistas.
    Visible en app.log para depurar cómo el orquestador descompone las peticiones.

    Uso:
        log_agent_flow("request",  "orion_ld", "Obtener velocidad cinta")
        log_agent_flow("response", "orion_ld", "Velocidad=1.58 m/s", duration_ms=950)
    """
    logger = logging.getLogger("mcp.agent")

    if direction == "request":
        arrow = "→"
        prefix = "Gestor"
        target = agent
    else:
        arrow = "←"
        prefix = agent
        target = "Gestor"

    # Truncar el mensaje en consola pero completo en fichero
    msg_preview = message if len(message) <= 300 else message[:300] + "…"

    duration_str = f" │ {duration_ms:.0f}ms" if duration_ms is not None else ""
    meta_str = f" │ {metadata}" if metadata else ""

    logger.info(
        "%s %s %s%s │ %s%s",
        prefix, arrow, target, duration_str, msg_preview, meta_str,
    )