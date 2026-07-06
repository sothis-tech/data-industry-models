#!/usr/bin/env python3
"""
Publica una entidad de ejemplo en el broker Orion-LD.
Uso: python scripts/post-example.py examples/Device/example-burner.json
Requiere: pip install requests
"""
import json
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    print("Requiere: pip install requests")
    sys.exit(1)

ROOT = Path(__file__).resolve().parent.parent
BROKER = "http://localhost:1026"
CONTEXT_PATH = ROOT / "context" / "industrial-oven-context.jsonld"


def main():
    if len(sys.argv) < 2:
        print("Uso: python post-example.py <ruta-al-json>")
        print("Ejemplo: python post-example.py examples/Device/example-burner.json")
        sys.exit(1)

    entity_path = Path(sys.argv[1])
    if not entity_path.is_absolute():
        entity_path = ROOT / entity_path

    if not entity_path.exists():
        print(f"Archivo no encontrado: {entity_path}")
        sys.exit(1)

    with open(CONTEXT_PATH, encoding="utf-8") as f:
        ctx = json.load(f)
    with open(entity_path, encoding="utf-8") as f:
        entity = json.load(f)

    payload = {"@context": ctx["@context"], **entity}

    resp = requests.post(
        f"{BROKER}/ngsi-ld/v1/entities",
        json=payload,
        headers={"Content-Type": "application/ld+json"},
        timeout=10,
    )

    if resp.status_code in (201, 204):
        print(f"OK: entidad creada ({entity.get('id', '?')})")
    else:
        print(f"Error {resp.status_code}: {resp.text}")
        sys.exit(1)


if __name__ == "__main__":
    main()
