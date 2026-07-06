# Extensiones al modelo – Industrial Oven (local)

Este documento describe las extensiones aplicadas a los Smart Data Models para el caso de uso del horno industrial E-Therm. Son de uso **local**; los modelos oficiales no se modifican.

---

## 1. ManufacturingMachine.hasPart

| Atributo | Tipo | Obligatorio | Descripción |
|----------|------|-------------|-------------|
| `hasPart` | array[string] (URI) | No | Lista de URIs de entidades Device (componentes y sondas) que forman parte del horno. Origen: [schema.org/hasPart](https://schema.org/hasPart). |

---

## 2. ManufacturingMachineModel.standardOperations (valores extendidos)

El atributo `standardOperations` (array de string) admite los siguientes valores para el perfil E-Therm:

- `reddeningWarming`
- `roastingBaking`
- `drying`
- `smoking`
- `cooking`
- `evacuation`
- `airCirculation`
- `dryingMaturing`
- `maturing`
- `cleaning0`
- `cleaning1`
- `cleaning2`

---

## 3. ManufacturingMachineOperation.operationOutput (perfil E-Therm)

Objeto con la siguiente estructura:

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `programName` / `programId` | string | Identificador o nombre del programa ejecutado. |
| `temperatureSetPoint` | number | Temperatura objetivo (°C). |
| `temperatureMin` / `temperatureMax` | number | Temperatura mín./máx. registrada en el ciclo. |
| `humiditySetPoint` | number | Humedad objetivo (% RH). |
| `humidityMin` / `humidityMax` | number | Humedad mín./máx. registrada. |
| `controlMode` | string | `Time` \| `RoomTemperature` \| `ProductTemperature`. |
| `rhControl` | boolean | Uso de control de humedad (RH). |
| `processSteps` | array[string] | Lista de procesos por paso. |
| `durationMinutes` | number | Duración total del ciclo (minutos). |
| `alarms` / `errors` | array | Códigos de alarma o error durante el ciclo. |
| `batchId` / `productType` | string | (Opcional) Trazabilidad de lote o producto. |

---

## 4. Uso para comandos y setpoints (integración agente / middleware)

Se adopta **operationOutput** como el lugar donde se expresan los parámetros seteados del ciclo (temperatura, humedad, modo de control, etc.). El encendido/apagado del horno se expresa en la entidad de la máquina.

| Acción | Dónde setear | Atributo / ruta |
|--------|----------------|------------------|
| **Encender / apagar horno** | ManufacturingMachine | `status` (ej. `"running"`, `"off"`). Valor estándar del modelo. |
| **Setpoint temperatura** | ManufacturingMachineOperation (operación en curso) | `operationOutput.temperatureSetPoint` (number, °C). |
| **Setpoint humedad** | ManufacturingMachineOperation (operación en curso) | `operationOutput.humiditySetPoint` (number, % RH). |
| **Modo de control** | ManufacturingMachineOperation (operación en curso) | `operationOutput.controlMode` (`"Time"` \| `"RoomTemperature"` \| `"ProductTemperature"`). |
| **Control humedad (RH) on/off** | ManufacturingMachineOperation (operación en curso) | `operationOutput.rhControl` (boolean). |
| **Programa / duración** | ManufacturingMachineOperation (operación en curso) | `operationOutput.programId` / `programName`, `operationOutput.durationMinutes`. |

**Flujo:** El agente (o cualquier consumidor NGSI-LD) hace **PATCH** de la entidad `ManufacturingMachineOperation` con `status: "ongoing"` y el objeto `operationOutput` actualizado con los campos anteriores. El middleware del horno, suscrito o en polling a esa entidad, traduce los valores al Touch-Control (TC). No se definen atributos de setpoint en `ManufacturingMachine`; todo lo setable del ciclo va en **operationOutput** de la operación en curso.

---

## Referencias

- [data-model-horno-industrial.md](./data-model-horno-industrial.md)
- [mapa-decisiones-data-model-horno.md](./mapa-decisiones-data-model-horno.md)
- [device-schema.json](https://smart-data-models.github.io/dataModel.Device/device-schema.json)
