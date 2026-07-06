# Guía de integración para el desarrollador del LLM/Agente

Guía para conectar el agente/LLM al Context Broker (Orion-LD), al contexto JSON-LD y al modelo de datos del horno industrial E-Therm. Sigue estas prácticas para que tu componente use el mismo “espacio de datos” que el resto del sistema.

---

## 1. Principio: el LLM solo habla con el broker

- El **agente/LLM** se comunica **únicamente** con el **Context Broker (Orion-LD)** mediante la API NGSI-LD (HTTP).
- No debe hablar directamente con el horno ni con el middleware: el middleware ya traduce broker ↔ horno físico.
- Toda la “fuente de verdad” del estado digital está en el broker (entidades, mediciones, operaciones, setpoints).

---

## 2. Qué necesita tu compañero

### 2.1 URL del broker

- **Desarrollo local:** `http://localhost:1026` (tras `docker compose up -d` en la raíz del proyecto).
- **Otros entornos:** una variable de configuración, p. ej. `ORION_BROKER_URL`, que vosotros defináis (staging, producción).

### 2.2 Contexto JSON-LD (obligatorio)

- **Archivo:** `context/industrial-oven-context.jsonld` (en este repositorio).
- **Uso:**  
  - O bien **registrar el contexto** en el broker una vez (recomendado),  
  - O bien **enviar el `@context`** en cada petición de creación/actualización.

**Registrar el contexto en Orion-LD (una vez por entorno):**

```bash
curl -X POST http://localhost:1026/ngsi-ld/v1/jsonldContexts \
  -H "Content-Type: application/json" \
  -H "NGSILD-Context: http://example.org/industrial-oven-context" \
  -d @context/industrial-oven-context.jsonld
```

Si el contexto está registrado, en las peticiones se puede usar el **Link header** en lugar de incluir el JSON del contexto en el body:

```http
Link: <http://example.org/industrial-oven-context>; rel="http://www.w3.org/ns/json-ld#context"; type="application/ld+json"
```

### 2.3 Documentación y artefactos del modelo

| Recurso | Ubicación | Para qué |
|--------|-----------|----------|
| Contrato de integración (qué consultar/escribir) | [_local/arquitectura-e-integracion.md](../_local/arquitectura-e-integracion.md) | Acciones del LLM → entidades/atributos |
| Especificación del modelo (entidades, atributos, tipos) | [docs/mapa-decisiones-data-model-horno.md](mapa-decisiones-data-model-horno.md) | Saber qué existe y cómo se llama |
| URIs de entidades de ejemplo | [examples/README.md](../examples/README.md) | IDs fijos para horno, operación, dispositivos, mediciones |
| Extensiones (hasPart, operationOutput, standardOperations) | [docs/extensions.md](extensions.md) | Detalle de extensiones propias del dominio |
| Requisitos y gobernanza | [docs/guardrails-requisitos.md](guardrails-requisitos.md) | Seguridad, alertas, criterios de aceptación |

---

## 3. Buenas prácticas para integrar el LLM

1. **Usar la misma URL de broker** que el resto del equipo (variable de entorno o config compartida).
2. **Usar siempre el mismo contexto**  
   - Mismo archivo `context/industrial-oven-context.jsonld` y, si se registra, la misma URI `http://example.org/industrial-oven-context`.
3. **Respetar los IDs de entidades**  
   - Los ejemplos definen URIs estables (p. ej. `urn:ngsi-ld:ManufacturingMachine:horno-001`, `urn:ngsi-ld:Device:probe-room-1`). El LLM debe usar estos IDs (o los acordados en vuestro entorno) para no duplicar entidades ni romper relaciones.
4. **Solo HTTP al broker**  
   - GET para consultas, POST para crear entidades, PATCH para actualizar atributos. No implementar lógica de bajo nivel ni protocolos del horno.
5. **Content-Type y Link**  
   - Crear/actualizar con `Content-Type: application/ld+json` si envías `@context` en el body, o con `Content-Type: application/json` y el header `Link` anterior si el contexto está registrado.
6. **Orden al crear entidades**  
   - Si el LLM o algún script crea entidades, seguir el orden recomendado en [examples/README.md](../examples/README.md): contexto → ManufacturingMachineModel, Building, Person → Device(s) → ManufacturingMachine → ManufacturingMachineOperation → DeviceMeasurement.
7. **No inventar tipos ni atributos**  
   - Limitarse a los tipos y atributos del [mapa de decisiones](mapa-decisiones-data-model-horno.md) y [extensiones](extensions.md); así el modelo se mantiene interoperable.

---

## 4. Contrato de integración (resumen para el LLM)

Traducir las “intenciones” del usuario en llamadas NGSI-LD como sigue:

| Acción del usuario | Acción en el broker | Entidad / atributos |
|--------------------|---------------------|----------------------|
| Consultar temperatura / humedad | GET entities (o query por tipo/refDevice) | **DeviceMeasurement**: `refDevice`, `numValue`, `unit`, `dateObserved`, `controlledProperty` |
| Estado del horno | GET entity por ID del horno | **ManufacturingMachine**: `status`, `online` |
| Operación en curso | GET entity operación (p. ej. op-001) | **ManufacturingMachineOperation**: `machine`, `status`, `operationOutput` |
| Consultar/cambiar setpoint temperatura | GET/PATCH operación o máquina | **ManufacturingMachineOperation**.`operationOutput`.`temperatureSetPoint` o atributo equivalente en el modelo |
| Apagar horno / cambiar estado | PATCH ManufacturingMachine | **ManufacturingMachine**.`status` (p. ej. `"off"`) |

**IDs de referencia (ver [examples/README.md](../examples/README.md) para la lista completa):**

- Horno: `urn:ngsi-ld:ManufacturingMachine:horno-001`
- Operación ejemplo: `urn:ngsi-ld:ManufacturingMachineOperation:op-001`
- Sondas (temperatura/humedad): `urn:ngsi-ld:Device:probe-product-temp`, `probe-room-1` … `probe-room-4`, `probe-humidity`, etc.

---

## 5. Endpoints NGSI-LD útiles (Orion-LD)

- Base: `{ORION_BROKER_URL}` (ej. `http://localhost:1026`).
- **Listar entidades por tipo:**  
  `GET /ngsi-ld/v1/entities?type=Device`  
  `GET /ngsi-ld/v1/entities?type=DeviceMeasurement`  
  `GET /ngsi-ld/v1/entities?type=ManufacturingMachine`
- **Una entidad por ID:**  
  `GET /ngsi-ld/v1/entities/{id}`  
  (ej. `GET /ngsi-ld/v1/entities/urn:ngsi-ld:ManufacturingMachine:horno-001`)
- **Crear entidad:**  
  `POST /ngsi-ld/v1/entities`  
  Body: JSON con `@context` (o usar Link header) + atributos según el modelo.
- **Actualizar atributos:**  
  `PATCH /ngsi-ld/v1/entities/{id}/attrs`  
  Body: objeto con solo los atributos a actualizar (y `@context` o Link).
- **Registrar contexto:**  
  `POST /ngsi-ld/v1/jsonldContexts`  
  (como en el apartado 2.2).

Más detalles en [docker/README.md](../docker/README.md) y en la documentación de [FIWARE NGSI-LD](https://www.etsi.org/deliver/etsi_gs/CIM/001_099/009/01.04.01_60/gs_CIM009v010401p.pdf) / Orion-LD.

---

## 6. Checklist para el desarrollador del LLM

- [ ] Tener acceso a la URL del broker (local o compartida).
- [ ] Registrar o usar el contexto `context/industrial-oven-context.jsonld` en todas las peticiones que creen o actualicen entidades.
- [ ] Usar los IDs de entidades acordados (repositorio o convención del equipo).
- [ ] Implementar solo llamadas HTTP al broker (GET/POST/PATCH); no conectar al horno ni al middleware.
- [ ] Consultar [mapa-decisiones-data-model-horno.md](mapa-decisiones-data-model-horno.md) y [arquitectura-e-integracion.md](../_local/arquitectura-e-integracion.md) para el contrato exacto de atributos y relaciones.
- [ ] Respetar [guardrails-requisitos.md](guardrails-requisitos.md) en cuanto a seguridad y criterios de aceptación que apliquen al agente.

Si seguís esta guía, el LLM usará tu servidor Orion, tu contexto y tu modelo de datos de forma coherente con el resto del espacio de datos.
