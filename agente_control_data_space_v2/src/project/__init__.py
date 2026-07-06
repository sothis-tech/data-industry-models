# src/project/__init__.py
"""
Capa ESPECÍFICA del proyecto (NGSI-LD: IBERMOT / METAPAN).

Importar este paquete REGISTRA en el motor:
  - los guardarraíles deterministas    (project.guardrails)
  - el comportamiento anti-evasión y
    la reconciliación de tokens        (project.behavior_guards)
  - el mapa de inyección de tenant     (project.tenant_config)

Los PROMPTS ya NO viven aquí: están en el paquete `prompts/` (multi.py /
single.py) y los activa el cliente según `agent.agent_mode`, porque dependen
del modo agéntico, no solo del proyecto.

Las interfaces (interfaces/cli.py, interfaces/api.py) y los scripts
(tests/benchmark.py) hacen `import project` al arrancar para activar todo
esto. Para portar el motor a otro proyecto se reescribe ESTE paquete (+ config
+ servers + prompts) sin tocar `engine/`.
"""
from . import guardrails       # noqa: F401  → registra los validadores
from . import behavior_guards  # noqa: F401  → registra anti-evasión + reconcile
from . import tenant_config    # noqa: F401  → registra el mapa de tenant
