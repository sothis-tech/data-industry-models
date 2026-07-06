#!/usr/bin/env python3
"""
Valida los ejemplos JSON contra los schemas.
Requiere: pip install jsonschema requests
"""
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, RefResolver, ValidationError

# Rutas base
ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "schemas"
EXAMPLES_DIR = ROOT / "examples"

# Mapeo: carpeta de ejemplos -> schema
EXAMPLE_TO_SCHEMA = {
    "Building": "Building.json",
    "Device": "Device.json",
    "DeviceMeasurement": "DeviceMeasurement.json",
    "ManufacturingMachine": "ManufacturingMachine.json",
    "ManufacturingMachineModel": "ManufacturingMachineModel.json",
    "ManufacturingMachineOperation": "ManufacturingMachineOperation.json",
    "Person": "Person.json",
}


def validate_all():
    """Valida todos los ejemplos contra sus schemas."""
    errors = []
    validated = 0

    for example_folder, schema_file in EXAMPLE_TO_SCHEMA.items():
        schema_path = SCHEMAS_DIR / schema_file
        examples_path = EXAMPLES_DIR / example_folder

        if not schema_path.exists():
            print(f"  [SKIP] Schema no encontrado: {schema_file}")
            continue

        if not examples_path.exists():
            print(f"  [SKIP] Carpeta no encontrada: {example_folder}")
            continue

        with open(schema_path, encoding="utf-8") as f:
            schema = json.load(f)

        # Resolver para $ref (incluye URLs remotas)
        schema_uri = schema_path.as_uri()
        resolver = RefResolver(base_uri=schema_uri, referrer=schema)
        validator = Draft202012Validator(schema, resolver=resolver)

        for example_file in sorted(examples_path.glob("*.json")):
            try:
                with open(example_file, encoding="utf-8") as f:
                    data = json.load(f)
                validator.validate(data)
                validated += 1
                print(f"  [OK] {example_folder}/{example_file.name}")
            except ValidationError as e:
                msg = f"  [ERROR] {example_folder}/{example_file.name}: {e.message}"
                errors.append(msg)
                print(msg)
            except json.JSONDecodeError as e:
                msg = f"  [ERROR] {example_folder}/{example_file.name}: JSON inválido - {e}"
                errors.append(msg)
                print(msg)

    return validated, errors


def main():
    print("Validando ejemplos contra schemas...\n")
    validated, errors = validate_all()
    print(f"\n--- {validated} ejemplos válidos, {len(errors)} errores ---")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
