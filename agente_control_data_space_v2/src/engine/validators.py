# src/engine/validators.py
# -*- coding: utf-8 -*-
"""
Registro genérico de extensiones del MOTOR.

REGLA DE ORO
------------
`engine/` NO importa nada de `project/`. Este módulo es el ÚNICO punto de
acoplamiento: el motor expone "huecos" (hooks) y `project/`, al importarse,
los RELLENA registrando aquí sus reglas, prompts y comportamientos.

Si `project/` no se importa (o está vacío), el motor sigue funcionando en
modo básico:
  - run_validators(...)      → siempre None (ninguna tool se rechaza)
  - get_system_prompt(...)   → un prompt genérico de asistente
  - should_retry_for_dodge   → False (sin anti-evasión)
  - reconcile_metrics(...)   → devuelve los totales directos tal cual

Prueba de fuego: para otro proyecto se reescribe `project/` (+ `config/` +
`servers/`) SIN tocar este fichero ni el resto de `engine/`.

Tipos esperados de cada hook
----------------------------
  validator(server: str, tool: str, kwargs: dict) -> str | None
      Devuelve None si la llamada es válida; si no, el motivo del rechazo
      (string), que el motor entrega al LLM como tool-error.

  prompt_provider(server_type: str, modality: str = "text") -> str
      Devuelve el system prompt para un rol/servidor concreto.

  dodge_detector(text: str, num_tools: int) -> bool
      True si la respuesta es una evasión (ofrecer/preguntar en vez de actuar).

  metrics_reconciler(direct_totals: dict, li_token_counter) -> dict
      Devuelve los totales de tokens reconciliados.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, List, Optional

logger = logging.getLogger("mcp.engine.validators")

# Firmas de tipos (solo documentación)
ValidatorFn = Callable[[str, str, dict], Optional[str]]
PromptProviderFn = Callable[..., str]
DodgeDetectorFn = Callable[[str, int], bool]
MetricsReconcilerFn = Callable[[dict, Any], dict]


# ════════════════════════════════════════════════════════════════════════
# 1. VALIDADORES DE TOOL CALLS  (guardarraíles deterministas)
# ════════════════════════════════════════════════════════════════════════

_VALIDATORS: List[ValidatorFn] = []


def register_validator(fn: ValidatorFn) -> ValidatorFn:
    """
    Registra un validador. Usable como decorador:

        @register_validator
        def mi_regla(server, tool, kwargs):
            ...
            return None  # o un mensaje de rechazo
    """
    if fn not in _VALIDATORS:
        _VALIDATORS.append(fn)
        logger.debug("Validador registrado │ %s (total=%d)",
                     getattr(fn, "__name__", repr(fn)), len(_VALIDATORS))
    return fn


def run_validators(server: str, tool: str, kwargs: dict) -> Optional[str]:
    """
    Ejecuta TODOS los validadores registrados en orden. Devuelve el motivo
    del PRIMER rechazo, o None si todos pasan. Si no hay validadores
    registrados (project vacío) devuelve None: el motor no rechaza nada.
    """
    for fn in _VALIDATORS:
        try:
            reason = fn(server, tool, kwargs)
        except Exception as e:  # un validador roto nunca tumba la petición
            logger.warning("Validador %s lanzó excepción (ignorada): %s",
                           getattr(fn, "__name__", repr(fn)), e)
            continue
        if reason:
            return reason
    return None


def clear_validators() -> None:
    """Vacía el registro (útil en tests)."""
    _VALIDATORS.clear()


def registered_validators() -> List[str]:
    return [getattr(fn, "__name__", repr(fn)) for fn in _VALIDATORS]


# ════════════════════════════════════════════════════════════════════════
# 2. PROVEEDOR DE PROMPTS  (lo aporta el proyecto)
# ════════════════════════════════════════════════════════════════════════

def _default_prompt_provider(server_type: str, modality: str = "text") -> str:
    """Prompt genérico cuando no hay proyecto cargado. El motor arranca igual."""
    return (
        "Eres un asistente útil. Responde con datos devueltos por las "
        "herramientas disponibles; si no hay datos, dilo con claridad. "
        "Responde en español salvo que el usuario use otro idioma."
    )


_prompt_provider: PromptProviderFn = _default_prompt_provider


def register_prompt_provider(fn: PromptProviderFn) -> PromptProviderFn:
    """Registra el proveedor de prompts del proyecto."""
    global _prompt_provider
    _prompt_provider = fn
    logger.debug("Proveedor de prompts registrado │ %s",
                 getattr(fn, "__name__", repr(fn)))
    return fn


def reset_prompt_provider() -> None:
    global _prompt_provider
    _prompt_provider = _default_prompt_provider


def get_system_prompt(server_type: str, modality: str = "text") -> str:
    """Punto único que usa el motor para obtener un prompt."""
    try:
        return _prompt_provider(server_type, modality=modality)
    except TypeError:
        # Proveedor con firma antigua sin modality
        return _prompt_provider(server_type)
    except Exception as e:
        logger.warning("Proveedor de prompts falló (%s); uso el genérico", e)
        return _default_prompt_provider(server_type, modality)


# ════════════════════════════════════════════════════════════════════════
# 3. ANTI-EVASIÓN  (dodge detector + sufijo de reintento)
# ════════════════════════════════════════════════════════════════════════

_dodge_detector: Optional[DodgeDetectorFn] = None
_dodge_retry_suffix: str = ""


def register_dodge_detector(fn: DodgeDetectorFn, retry_suffix: str = "") -> DodgeDetectorFn:
    """Registra el detector de evasiones y el sufijo imperativo de reintento."""
    global _dodge_detector, _dodge_retry_suffix
    _dodge_detector = fn
    if retry_suffix:
        _dodge_retry_suffix = retry_suffix
    logger.debug("Detector anti-evasión registrado │ %s",
                 getattr(fn, "__name__", repr(fn)))
    return fn


def should_retry_for_dodge(text: str, num_tools: int) -> bool:
    """True si hay detector registrado y considera la respuesta una evasión."""
    if _dodge_detector is None:
        return False
    try:
        return bool(_dodge_detector(text, num_tools))
    except Exception as e:
        logger.warning("Detector anti-evasión falló (ignorado): %s", e)
        return False


def get_dodge_retry_suffix() -> str:
    return _dodge_retry_suffix


def reset_dodge_detector() -> None:
    global _dodge_detector, _dodge_retry_suffix
    _dodge_detector = None
    _dodge_retry_suffix = ""

# ════════════════════════════════════════════════════════════════════════
# 3b. GUARDA DE ENRUTAMIENTO  (lo aporta el proyecto)
# ════════════════════════════════════════════════════════════════════════
# Decide si una instrucción que el Gestor va a delegar a un especialista está
# MAL dirigida hacia documentación (RAG) cuando en realidad es estructural
# (Orion/QL).  routing_guard(target, instruction) -> bool
#   True  → mal enrutada, redirigir.   False → dejar pasar (legítima o duda).
# Sin guard registrado, nunca redirige (REGLA DE ORO).

RoutingGuardFn = Callable[[str, str], bool]

_routing_guard: Optional[RoutingGuardFn] = None
_routing_redirect_msg: str = ""


def register_routing_guard(fn: RoutingGuardFn, redirect_msg: str = "") -> RoutingGuardFn:
    """Registra la guarda de enrutamiento y el mensaje de redirección."""
    global _routing_guard, _routing_redirect_msg
    _routing_guard = fn
    _routing_redirect_msg = redirect_msg or ""
    logger.debug("Guarda de enrutamiento registrada │ %s",
                 getattr(fn, "__name__", repr(fn)))
    return fn


def should_redirect_routing(target: str, instruction: str) -> bool:
    """True si la instrucción hacia `target` está mal enrutada (debe redirigir)."""
    if _routing_guard is None:
        return False
    try:
        return bool(_routing_guard(target, instruction))
    except Exception as e:
        logger.warning("Guarda de enrutamiento falló (ignorada): %s", e)
        return False


def get_routing_redirect_msg() -> str:
    return _routing_redirect_msg


def reset_routing_guard() -> None:
    global _routing_guard, _routing_redirect_msg
    _routing_guard = None
    _routing_redirect_msg = ""


# ════════════════════════════════════════════════════════════════════════
# 3c. OBSERVADORES DEL SCHEMA  (el proyecto se entera del schema cargado)
# ════════════════════════════════════════════════════════════════════════
# Cuando el cliente construye/cachea el schema de un tenant, notifica a los
# observadores con (tenant, schema_text). El proyecto extrae así keywords
# estructurales del data space SIN que el motor conozca el dominio.

SchemaObserverFn = Callable[[str, str], None]

_schema_observers: List[SchemaObserverFn] = []


def register_schema_observer(fn: SchemaObserverFn) -> SchemaObserverFn:
    """Registra una función a la que notificar cuando se carga un schema."""
    if fn not in _schema_observers:
        _schema_observers.append(fn)
        logger.debug("Observador de schema registrado │ %s",
                     getattr(fn, "__name__", repr(fn)))
    return fn


def notify_schema_loaded(tenant: str, schema_text: str) -> None:
    """Notifica a todos los observadores del schema (errores ignorados)."""
    for fn in _schema_observers:
        try:
            fn(tenant, schema_text)
        except Exception as e:
            logger.warning("Observador de schema %s falló (ignorado): %s",
                           getattr(fn, "__name__", repr(fn)), e)


def reset_schema_observers() -> None:
    _schema_observers.clear()

# ════════════════════════════════════════════════════════════════════════
# 4. RECONCILIACIÓN DE MÉTRICAS DE TOKENS  (lo aporta el proyecto)
# ════════════════════════════════════════════════════════════════════════

_metrics_reconciler: Optional[MetricsReconcilerFn] = None


def register_metrics_reconciler(fn: MetricsReconcilerFn) -> MetricsReconcilerFn:
    """Registra la función que reconcilia tokens (directo vs LlamaIndex)."""
    global _metrics_reconciler
    _metrics_reconciler = fn
    logger.debug("Reconciliador de métricas registrado │ %s",
                 getattr(fn, "__name__", repr(fn)))
    return fn


def reconcile_metrics(direct_totals: dict, li_token_counter: Any = None) -> dict:
    """
    Si hay reconciliador registrado lo usa; si no, devuelve los totales
    directos tal cual (modo básico del motor).
    """
    if _metrics_reconciler is None:
        return direct_totals
    try:
        return _metrics_reconciler(direct_totals, li_token_counter)
    except Exception as e:
        logger.warning("Reconciliador de métricas falló (ignorado): %s", e)
        return direct_totals


def reset_metrics_reconciler() -> None:
    global _metrics_reconciler
    _metrics_reconciler = None

# ════════════════════════════════════════════════════════════════════════
# 4b. NORMALIZADORES DE ARGUMENTOS  (lo aporta el proyecto)
# ════════════════════════════════════════════════════════════════════════
# A diferencia de los validadores (que solo aceptan/rechazan), un normalizador
# REESCRIBE los kwargs de una tool ANTES de ejecutarla y antes de validar. Sirve
# para limpiar fragmentos de búsqueda (quitar acentos, palabras de relleno, etc.)
# de forma determinista. El motor aporta el mecanismo; el proyecto, las reglas.
#
#   normalizer(server: str, tool: str, kwargs: dict) -> dict
#       Devuelve el dict de kwargs (posiblemente modificado). DEBE devolver
#       siempre un dict; si no aplica, devuelve kwargs sin tocar.

ArgNormalizerFn = Callable[[str, str, dict], dict]

_ARG_NORMALIZERS: List[ArgNormalizerFn] = []


def register_arg_normalizer(fn: ArgNormalizerFn) -> ArgNormalizerFn:
    """Registra un normalizador de argumentos. Usable como decorador."""
    if fn not in _ARG_NORMALIZERS:
        _ARG_NORMALIZERS.append(fn)
        logger.debug("Normalizador de args registrado │ %s (total=%d)",
                     getattr(fn, "__name__", repr(fn)), len(_ARG_NORMALIZERS))
    return fn


def run_normalizers(server: str, tool: str, kwargs: dict) -> dict:
    """
    Ejecuta todos los normalizadores en orden, encadenando el resultado.
    Si no hay ninguno registrado, devuelve kwargs intacto. Un normalizador
    que falle se ignora (nunca tumba la tool call).
    """
    result = kwargs
    for fn in _ARG_NORMALIZERS:
        try:
            out = fn(server, tool, result)
            if isinstance(out, dict):
                result = out
        except Exception as e:
            logger.warning("Normalizador %s lanzó excepción (ignorada): %s",
                           getattr(fn, "__name__", repr(fn)), e)
    return result


def clear_arg_normalizers() -> None:
    _ARG_NORMALIZERS.clear()


def registered_arg_normalizers() -> List[str]:
    return [getattr(fn, "__name__", repr(fn)) for fn in _ARG_NORMALIZERS]

# ════════════════════════════════════════════════════════════════════════
# 5. MAPA DE INYECCIÓN DE TENANT POR SERVIDOR  (lo aporta el proyecto)
# ════════════════════════════════════════════════════════════════════════
# El MECANISMO de forzar el tenant en cada tool call vive en el motor
# (engine.tool_wrapper). Pero el NOMBRE del parámetro de tenant es específico
# del dominio: NGSI-LD usa 'ngsild_tenant' en Orion y 'fiware_service' en
# QuantumLeap. El proyecto registra aquí el mapa {servidor: nombre_param};
# si no registra nada, el motor no inyecta tenant (modo básico).

_TENANT_PARAM_BY_SERVER: dict = {}


def register_tenant_params(mapping: dict) -> None:
    """
    Registra el mapa {nombre_servidor: nombre_parametro_tenant}.
    Ej. {"orion_ld": "ngsild_tenant", "quantumleap": "fiware_service"}.
    """
    global _TENANT_PARAM_BY_SERVER
    _TENANT_PARAM_BY_SERVER = dict(mapping or {})
    logger.debug("Mapa de tenant por servidor registrado │ %s",
                 list(_TENANT_PARAM_BY_SERVER.keys()))


def get_tenant_param(server: str) -> Optional[str]:
    """Nombre del parámetro de tenant para `server`, o None si no aplica."""
    return _TENANT_PARAM_BY_SERVER.get(server)


def reset_tenant_params() -> None:
    global _TENANT_PARAM_BY_SERVER
    _TENANT_PARAM_BY_SERVER = {}


__all__ = [
    "register_validator", "run_validators", "clear_validators", "registered_validators",
    "register_prompt_provider", "reset_prompt_provider", "get_system_prompt",
    "register_dodge_detector", "should_retry_for_dodge", "get_dodge_retry_suffix",
    "reset_dodge_detector",
    "register_routing_guard", "should_redirect_routing", "get_routing_redirect_msg",
    "reset_routing_guard",
    "register_schema_observer", "notify_schema_loaded", "reset_schema_observers",
    "register_metrics_reconciler", "reconcile_metrics", "reset_metrics_reconciler",
    "register_arg_normalizer", "run_normalizers", "clear_arg_normalizers", "registered_arg_normalizers",
    "register_tenant_params", "get_tenant_param", "reset_tenant_params",
    
]
