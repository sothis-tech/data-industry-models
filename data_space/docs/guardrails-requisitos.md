# Requisitos de gobernanza del espacio de datos – Criterios de aceptación

En un **espacio de datos** (p. ej. siguiendo referencias como el [IDSA Rulebook](https://docs.internationaldataspaces.org/ids-knowledgebase/idsa-rulebook) o Gaia-X), las reglas se organizan en **gobernanza** (principios, requisitos funcionales, técnicos y organizativos) y **modelo semántico** (entidades, atributos y sus restricciones). Este documento define los requisitos de **gobernanza** que aplican al espacio de datos del horno: quién puede escribir, auditoría, alertas y políticas opcionales. Los **límites de valor** (rangos de temperatura, humedad) pertenecen al **modelo de datos** (documentación y/o schemas), no al rulebook. La **interpretación** del lenguaje natural es responsabilidad del agente que integra el LLM y queda fuera del alcance del espacio de datos.

---

## 1. Requisitos de seguridad (gobernanza)

| Id | Guardrail | Dónde | Criterios de aceptación |
|----|-----------|--------|-------------------------|
| S1 | **Autenticación del canal** | Agente | Solo se aceptan y ejecutan órdenes de voz/texto de usuarios o canales autorizados (ej. operario identificado). Las peticiones de origen desconocido o no autenticado se rechazan y no generan escritura en el broker. |
| S2 | **Validación de rangos antes de escribir** | Agente y/o Middleware | Antes de hacer PATCH en el broker se validan los valores contra los rangos definidos en el **modelo de datos** (véase [data-model-horno-industrial.md](./data-model-horno-industrial.md) y, si se definen, `minimum`/`maximum` en los schemas). Si el valor está fuera de rango, se rechaza el comando y no se escribe en el broker. |
| S3 | **Escritura solo vía agente o API controlada** | Middleware / Broker | El middleware solo aplica al horno físico los cambios que recibe del broker. El broker solo acepta escrituras desde el agente (o desde una API con autenticación/autorización definida). No se permiten escrituras directas al broker desde orígenes no autorizados. |
| S4 | **Auditoría de comandos** | Agente o Middleware | Se registra por cada comando: quién/cuándo, intención (ej. “subir temperatura”), valor enviado, resultado (ok / rechazado y motivo). Los registros son consultables para detectar intentos anómalos o maliciosos. |
| S5 | **Límite de cambio brusco (opcional)** | Middleware | Si el setpoint solicitado implica un salto muy grande respecto al valor actual en un intervalo corto (ej. de 30 °C a 140 °C en 1 min), el comando se rechaza salvo que exista confirmación explícita del usuario. |

---

## 2. Requisitos de alertas

| Id | Guardrail | Dónde | Criterios de aceptación |
|----|-----------|--------|-------------------------|
| A1 | **Alerta cuando el equipo dispara alarma** | Middleware | Cuando se actualiza `ManufacturingMachine.status` o `operationOutput.alarms` con un código de alarma del horno, se genera una alerta (notificación, dashboard, email o canal acordado) para que un operario o responsable actúe. |
| A2 | **Alerta cuando se rechaza un comando** | Agente | Cuando un comando se rechaza por validación de rango o por regla de seguridad, además de informar al usuario, se dispara una alerta interna (log y, si se define, notificación) para revisión. |
| A3 | **Alerta de disponibilidad** | Monitor / Middleware | Si el broker o el middleware deja de responder, o no se reciben lecturas de sensores (DeviceMeasurement) durante un tiempo definido (ej. X minutos), se genera una alerta para revisar conectividad o estado del sistema. |

---

## 3. Interpretación (intents y sinónimos) – responsabilidad del agente/LLM

La deducción de la intención del usuario ("pon el horno más caliente", "apaga", "¿qué temperatura hay?") y el manejo de sinónimos es **responsabilidad del agente que integra el LLM**, no de este modelo de reglas. Este repo solo define:

- **Dónde se escribe cada tipo de comando:** en [extensions.md](./extensions.md) (operationOutput para setpoints y parámetros de ciclo; ManufacturingMachine.status para encender/apagar). El equipo del agente usa ese documento para traducir la salida del LLM a la acción NGSI-LD correcta (entidad, atributo, valor).
- **Qué rangos validar:** los rangos permitidos forman parte del **modelo de datos** (documentación y/o schemas), no de la gobernanza; el agente y el middleware los aplican en S2.

No corresponde al espacio de datos definir intents ni listas de sinónimos; el LLM deduce la intención y el agente mapea a la entidad/atributo indicado en el modelo de datos.


---

## 4. Cómo encaja con los estándares de espacios de datos

En iniciativas como **IDSA Rulebook**, **Gaia-X** o el **Common European Data Space**, la gobernanza cubre requisitos funcionales, técnicos y organizativos (confianza, roles, auditoría, control de acceso), no la definición de intents ni los rangos numéricos por atributo. En este proyecto:

| Ámbito | Dónde se define | Contenido |
|--------|-----------------|-----------|
| **Gobernanza (rulebook)** | Este documento | Requisitos S1–S5, A1–A3: autenticación, quién puede escribir, auditoría, alertas, política opcional de cambio brusco. |
| **Modelo semántico** | [data-model-horno-industrial.md](./data-model-horno-industrial.md), [mapa-decisiones-data-model-horno.md](./mapa-decisiones-data-model-horno.md), schemas | Entidades, atributos, relaciones; **rangos permitidos** (p. ej. temperatura cámara 0–150 °C) como parte del modelo o del schema. |
| **Interpretación (lenguaje → acción)** | Fuera del espacio de datos | Responsabilidad del agente/LLM; el modelo de datos indica solo qué atributos existen y dónde se escriben los comandos. |

Los límites de valor (mín/máx por parámetro) son **restricciones del modelo de datos**, alineadas con Smart Data Models (donde los schemas pueden incluir `minimum`/`maximum`). La gobernanza del espacio de datos no incluye un archivo de “reglas” con rangos numéricos; esos se documentan o se definen en el schema.

---

## 5. Resumen por capa

| Capa | Guardrails asignados |
|------|----------------------|
| **Agente** | S1, S2, S4, A2; interpretación (intents/sinónimos) a cargo del LLM y del equipo del agente. Los rangos para S2 se obtienen del modelo de datos. |
| **Middleware** | S2 (doble chequeo), S3, S5, A1, A3 |
| **Broker** | S3 (políticas de acceso a escritura) |

---

## 6. Modelo de entidades vs políticas de gobernanza

El **modelo de entidades** (ManufacturingMachine, ManufacturingMachineOperation, etc.) describe qué entidades y atributos existen y, en la documentación o en los schemas, los **rangos permitidos** (p. ej. temperatura cámara 0–150 °C). Eso es parte del modelo semántico del espacio de datos (Smart Data Models).

Las **políticas de gobernanza** (este documento) definen requisitos de comportamiento: quién puede escribir (S3), autenticación (S1), auditoría (S4), alertas (A1–A3), y opcionalmente S5 (cambio brusco). No contienen listas de intents, sinónimos ni rangos numéricos; los rangos viven en el modelo de datos.

**Configuración opcional (S5):** Si se implementa el límite de cambio brusco, el middleware o el agente pueden usar parámetros (p. ej. máximo cambio por minuto, umbral de confirmación) en un archivo de configuración propio. Esa configuración es operativa, no parte del rulebook del espacio de datos.

---

## 7. Referencias

- **Gobernanza de espacios de datos:** [IDSA Rulebook](https://docs.internationaldataspaces.org/ids-knowledgebase/idsa-rulebook) (requisitos funcionales, técnicos, organizativos y legales).
- **Modelo de datos y atributos seteados:** [mapa-decisiones-data-model-horno.md](./mapa-decisiones-data-model-horno.md), [extensions.md](./extensions.md) (operationOutput, status).
- **Rangos permitidos (modelo de datos):** [data-model-horno-industrial.md](./data-model-horno-industrial.md) (límites de temperatura y humedad).
