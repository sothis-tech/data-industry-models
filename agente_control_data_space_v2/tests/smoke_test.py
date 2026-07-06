#!/usr/bin/env python3
# tests/smoke_test.py
"""
SMOKE TEST — verifica que la reorganización arranca y que la separación
motor/proyecto se respeta. NO necesita servidores MCP levantados ni una API
key real: solo comprueba el cableado (imports, rutas, registro de reglas,
construcción del cliente).

Ejecutar desde la raíz del proyecto:
    python tests/smoke_test.py
    # o
    python -m tests.smoke_test

Salida esperada: una lista de checks en verde y "SMOKE TEST OK" al final.
Devuelve código de salida 0 si todo pasa, 1 si algo falla.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# tests/smoke_test.py → la raíz del proyecto es el padre de tests/; el código
# importable vive en src/.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

# Una API key dummy basta: solo construimos el cliente, no llamamos al LLM.
os.environ.setdefault("AZURE_OPENAI_API_KEY", "dummy-smoke-test-key")

OK, FAIL = "✅", "❌"
_errors: list[str] = []


def check(label: str, cond: bool, detail: str = "") -> None:
    mark = OK if cond else FAIL
    print(f"{mark} {label}" + (f" │ {detail}" if detail else ""))
    if not cond:
        _errors.append(label)


def main() -> int:
    print("═" * 70)
    print("SMOKE TEST │ chatmcp_unified — separación motor/proyecto + arranque")
    print("═" * 70)

    # ── 1. Motor en modo BÁSICO (antes de importar project) ──────────────
    from engine import validators as V
    check(
        "REGLA DE ORO: sin project, run_validators no rechaza nada",
        V.run_validators("quantumleap", "ql_get_last_value", {"entity_id": "x"}) is None,
    )
    check(
        "REGLA DE ORO: sin project, prompt genérico por defecto",
        V.get_system_prompt("orion_ld").startswith("Eres un asistente"),
    )
    check(
        "REGLA DE ORO: sin project, anti-evasión desactivada",
        V.should_retry_for_dodge("¿quieres que liste?", 0) is False,
    )

    # ── 2. Importar project => registra reglas/prompts/comportamiento ────
    import project  # noqa: F401
    regs = V.registered_validators()
    check("import project registra los validadores", len(regs) == 5, f"{len(regs)} reglas: {regs}")

    # ── 3. Guardrails NGSI-LD ────────────────────────────────────────────
    r = V.run_validators("quantumleap", "ql_get_last_value",
                         {"entity_id": "prensa-001", "attr_name": "numValue"})
    check("QL rechaza entity_id no canónico", bool(r) and "canónica" in r)

    r = V.run_validators("quantumleap", "ql_get_last_value",
                         {"entity_id": "urn:ngsi-ld:Press:001", "attr_name": "fuerza-meas"})
    check("QL rechaza attr_name con guion", bool(r) and "numValue" in r)

    r = V.run_validators("orion_ld", "list_entities", {"q": "prensa"})
    check("Orion rechaza q sin operador NGSI-LD", bool(r) and "operador" in r)

    r = V.run_validators("orion_ld", "get_entity_attributes",
                         {"entity_id": "urn:ngsi-ld:Press:001"})
    check("Orion redirige get_entity_attributes -> get_entity (404)", bool(r) and "404" in r)

    r = V.run_validators("quantumleap", "ql_get_attribute_history",
                         {"entity_id": "urn:ngsi-ld:Press:001", "attr_name": "numValue"})
    check("QL empuja serie cruda -> get_historical_aggregate",
          bool(r) and ("aggregate" in r.lower() or "agregad" in r.lower()))

    check("QL get_historical_aggregate (alto nivel) NO se rechaza",
          V.run_validators("quantumleap", "get_historical_aggregate",
                           {"asset_fragment": "prensa 1 temp"}) is None)

    # ── 4. Anti-evasión + reconcile ──────────────────────────────────────
    check("Anti-evasión detecta oferta sin tools",
          V.should_retry_for_dodge("¿Quieres que liste las prensas?", 0) is True)
    check("Anti-evasión ignora respuesta con tools",
          V.should_retry_for_dodge("Temperatura: 45 C", 1) is False)
    check("Anti-evasión tiene sufijo de reintento", bool(V.get_dodge_retry_suffix()))

    class _FakeLI:
        prompt_llm_token_count = 1200
        completion_llm_token_count = 300
        total_llm_token_count = 1500
    rec = V.reconcile_metrics(
        {"prompt_tokens": 16, "completion_tokens": 0, "total_tokens": 16, "num_llm_calls": 3},
        _FakeLI(),
    )
    check("Reconcile toma el máximo (16 -> 1500)", rec["total_tokens"] == 1500,
          f"total={rec['total_tokens']}, calls={rec['num_llm_calls']}")

    # ── 5. Construcción del cliente (cableado de rutas) ──────────────────
    try:
        from engine.client import MCPChatClient
        client = MCPChatClient(config_path="config/config.local.yaml")
        ok_client = True
        detail = f"provider={client.provider}, model={client._cost_model_name}, tenant={client.default_tenant}"
    except Exception as e:  # pragma: no cover
        ok_client = False
        detail = f"ERROR: {type(e).__name__}: {e}"
    check("MCPChatClient se construye con config/config.local.yaml", ok_client, detail)
    if ok_client:
        check("agent_mode leído del config", client.agent_mode in ("multi", "single"),
              f"modo={client.agent_mode}")

    # ── 5b. Modos de prompt multi vs single ──────────────────────────────
    import prompts as _prompts
    _prompts.activate("multi")
    agg   = V.get_system_prompt("aggregator")
    orion = V.get_system_prompt("orion_ld")
    check("modo multi: prompt por rol (aggregator != orion_ld)", agg != orion and len(agg) > 100)

    _prompts.activate("single")
    s_agg   = V.get_system_prompt("aggregator")
    s_orion = V.get_system_prompt("orion_ld")
    check("modo single: prompt único para todos los roles", s_agg == s_orion and len(s_agg) > 100)
    # Restaurar multi por defecto para no afectar a otros checks.
    _prompts.activate("multi")

    # ── 5c. Normalizador de fragmentos de búsqueda (guardrail determinista) ─
    from engine.validators import run_normalizers, registered_arg_normalizers
    norms = registered_arg_normalizers()
    check("normalizador de fragmentos registrado por el proyecto",
          "normalize_search_fragment" in norms, f"registrados: {norms}")

    def _norm(server, tool, param, frag):
        return run_normalizers(server, tool, {param: frag}).get(param)

    n_acc = _norm("orion_ld", "resolve_entity_ids", "name_fragment", "prensa 002 presión hid")
    check("normaliza acentos (presión→presion)", n_acc == "prensa 002 presion hid", f"→ {n_acc!r}")

    n_sw = _norm("orion_ld", "resolve_entity_ids", "name_fragment", "presion planta")
    check("elimina stopwords de relleno (planta)", n_sw == "presion", f"→ {n_sw!r}")

    n_pad = _norm("quantumleap", "get_historical_aggregate", "asset_fragment",
                  "agv carroceria 2 nivel bateria")
    check("padding numérico + quita 'nivel' (2→002)", n_pad == "agv carroceria 002 bateria", f"→ {n_pad!r}")

    n_keep = _norm("orion_ld", "get_entity", "entity_id", "urn:ngsi-ld:Device:prensa-001")
    check("no toca tools fuera de _FRAGMENT_TARGETS", n_keep == "urn:ngsi-ld:Device:prensa-001", f"→ {n_keep!r}")

    # ── 5d. Guarda de enrutamiento RAG↔Orion (determinista, conservadora) ──
    from engine.validators import should_redirect_routing, notify_schema_loaded
    notify_schema_loaded("test", (
        "TYPE ManufacturingMachineOperation (15 entities)\n"
        "  id keywords: agv, carroceria\n"
        "TYPE ManufacturingMachine (36 entities)\n"
        "  id keywords: agv, prensa\n"
    ))
    check("routing: estructural mal enrutada a RAG → redirige",
          should_redirect_routing("rag_knowledge", "¿Qué operaciones están registradas y su estado?") is True)
    check("routing: documental a RAG → NO redirige (manual)",
          should_redirect_routing("rag_knowledge", "¿Qué dice el manual del AGV de carrocería?") is False)
    check("routing: ambigua a RAG → NO redirige (info sobre AGV)",
          should_redirect_routing("rag_knowledge", "información sobre el AGV") is False)
    check("routing: destino no-RAG nunca redirige",
          should_redirect_routing("orion_ld", "Lista las operaciones registradas.") is False)

    # ── 6. Coste no nulo para gpt-4.1-nano (patch PRICING) ───────────────
    from engine.metrics import calculate_cost
    cost = calculate_cost(1000, 1000, "azure", "gpt-4.1-nano")
    check("PRICING incluye gpt-4.1-nano (coste > 0)", cost > 0, f"coste 1k/1k = ${cost:.6f}")

    # ── 7. Logging escribe los 4 ficheros mínimos, cada uno en su carpeta ─
    logs_dir = _PROJECT_ROOT / "var" / "logs"
    expected = {
        "app/app.log",
        "errors/errors.log",
        "conversations/conversations.jsonl",
        "metrics/metrics.jsonl",
    }
    present = {
        str(p.relative_to(logs_dir))
        for p in logs_dir.rglob("*")
        if p.is_file() and p.name != ".gitkeep"
    }
    check("var/logs/ tiene app/ errors/ conversations/ metrics/",
          expected.issubset(present), f"presentes: {sorted(present & expected)}")

    # ── Resultado ────────────────────────────────────────────────────────
    print("═" * 70)
    if _errors:
        print(f"{FAIL} SMOKE TEST FALLÓ │ {len(_errors)} check(s): {_errors}")
        return 1
    print(f"{OK} SMOKE TEST OK │ motor reutilizable + proyecto NGSI-LD enchufado correctamente")
    print("   El cliente arranca; las reglas deterministas están activas; logging operativo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())