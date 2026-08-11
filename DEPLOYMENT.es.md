# Guía de Despliegue

Este documento describe el procedimiento oficial para el despliegue completo de la plataforma **Espacio de Datos Industrial** sobre una máquina limpia, partiendo únicamente de un clon del repositorio. Está redactado para que cualquier persona con conocimientos básicos de Docker pueda dejar el stack operativo de forma reproducible, siguiendo pasos verificables y sin depender de conocimiento implícito del equipo de desarrollo.

> **Idioma:** [English](DEPLOYMENT.md) | Español · Parte de la documentación de [Espacio de Datos Industrial](README.es.md).

## Contenido

- [Descripción del sistema](#descripción-del-sistema)
- [Alcance](#alcance)
- [Prerrequisitos](#prerrequisitos)
  - [Software base](#software-base)
  - [Recursos de hardware](#recursos-de-hardware-ram-y-disco)
  - [Puertos del host](#puertos-del-host)
  - [Acceso al repositorio](#acceso-al-repositorio)
  - [Servicio de IA (LLM del agente)](#servicio-de-ia-llm-del-agente)
- [Estructura del repositorio](#estructura-del-repositorio)
- [Guía de despliegue](#guía-de-despliegue)
- [Validación funcional](#validación-funcional)
- [Roles de acceso a tenant](#roles-de-acceso-a-tenant)
- [Resolución de problemas](#resolución-de-problemas)
- [Referencias](#referencias)

## Descripción del sistema

La plataforma es un **monorepo** (con todo el código vendorizado, sin submódulos) que orquesta alrededor de **17 servicios** del ecosistema FIWARE e IoT industrial mediante Docker Compose. El stack integra, entre otros, un broker de contexto Orion-LD, persistencia histórica con QuantumLeap + CrateDB, ingesta industrial vía IoT Agent OPC-UA, una capa de seguridad y multitenencia con Keycloak + Kong, y componentes de IA (un servidor MCP de agente conversacional, RAG sobre ChromaDB y un agente de voz).

La arquitectura es **multitenant**: cada modelo de datos de fábrica se crea bajo su propio tenant (la cabecera `Fiware-Service` / `NGSILD-Tenant`), de modo que los datos de cada modelo quedan aislados. Ejemplos de modelos son `ibermot` o `metapan`; los valores que aparecen en esta guía (p. ej. `ibermot` en los comandos de ejemplo y en la configuración del IoT Agent) son únicamente ilustrativos y deben sustituirse por el tenant correspondiente a cada modelo.

## Alcance

Esta guía cubre el ciclo completo de puesta en marcha: prerrequisitos, clonado del repositorio, provisión de variables de entorno (`.env`), ajustes según el host, validación del docker-compose, construcción de imágenes, arranque de los servicios y validación funcional del stack.

**Queda fuera del alcance:** la configuración interna de cada microservicio, el desarrollo o modificación del código, y la operación en producción a largo plazo (escalado, copias de seguridad, monitorización).

### Consideraciones sobre el contenido del repositorio

El repositorio contiene **fuentes y recetas** (Dockerfiles, `docker-compose.yml`, ficheros `*.lock`, configuraciones y plantillas `.env.example`), pero **no incluye secretos ni artefactos pesados**. No se versionan los `.env` reales, los certificados, los modelos de ML ni los directorios `node_modules` / `.venv`. Los `.env` se provisionan manualmente a partir de las plantillas; el resto de artefactos los regenera el proceso de build o se descargan en tiempo de ejecución.

## Prerrequisitos

Antes de iniciar el despliegue, la máquina de destino debe cumplir los siguientes requisitos.

### Software base

- **Docker** y **Docker Compose v2**, instalados y operativos. Todo el ciclo de despliegue (build, arranque y validación) se realiza a través de Docker Compose.
- Acceso a la línea de comandos en un entorno **Linux** (cualquier distribución con Docker, p. ej. Ubuntu) o WSL.
- **Git**, necesario para clonar el proyecto.
- **Conectividad de red saliente**, necesaria para descargar las imágenes base (`mongo`, `orion-ld`, `crate`, `quantumleap`, `chromadb`, `postgres`, `keycloak`, `nginx`) y, en tiempo de ejecución, los modelos de ML y demás artefactos no versionados.
- **Python 3 en el host** (`python3`), necesario únicamente para ejecutar el script de carga de datos de ejemplo durante la validación funcional. El script utiliza solo la biblioteca estándar de Python, por lo que no requiere dependencias adicionales (no necesita `pip install`). A diferencia de los runtimes de los servicios —que viven dentro de los contenedores—, este script se ejecuta directamente en el host. En la mayoría de distribuciones Linux modernas debe invocarse como `python3` (el alias `python` puede no existir).

### Recursos de hardware (RAM y disco)

Los valores siguientes se basan en mediciones del stack completo en ejecución, validadas en dos entornos distintos. Deben tomarse como referencia: el consumo real varía según el volumen de datos cargados y el proveedor de IA seleccionado.

**Memoria RAM.** Con los 17 servicios levantados, el consumo real de memoria se sitúa en torno a los **9–11 GB**. Los servicios más exigentes son el agente de voz (~2,4–3,1 GB, por el modelo Whisper *medium*), el MCP server (~1,5–1,8 GB), Keycloak (~1,6 GB), el RAG manager (~1,0 GB) y Kong (~1,0 GB); el resto se mantiene por debajo de 700 MB cada uno.

- **Mínimo:** 16 GB — el stack arranca, pero opera al límite y recurre a swap.
- **Recomendado:** 32 GB — para operar con holgura, absorber picos de carga y dejar margen al SO y a la carga de datos.

> Si se opta por servir un LLM local con vLLM en la misma máquina, los requisitos de memoria (RAM y, sobre todo, VRAM) aumentan significativamente y deben dimensionarse aparte según el modelo elegido.

**Espacio en disco.** El peso principal proviene de las imágenes Docker construidas, que incluyen entornos de ML (PyTorch/CUDA) y son de gran tamaño: el agente conversacional (MCP server), el RAG manager y el voice agent superan cada uno los 10 GB. El conjunto de imágenes en uso ocupa del orden de **50–55 GB**. Los volúmenes de datos en estado inicial son modestos (~6 GB); el grueso del disco corresponde, por tanto, a las imágenes, no a los datos, si bien los volúmenes crecerán con el histórico de CrateDB/MongoDB.

- **Mínimo:** 80 GB libres, contemplando imágenes, volúmenes, caché de build y modelos descargados en tiempo de ejecución.
- **Recomendado:** 120 GB o más, especialmente si se prevé crecimiento de los datos históricos.

> Durante el build, Docker genera caché intermedia que puede alcanzar ~30 GB de forma temporal, por lo que el pico de disco durante la construcción es mayor que el resultado final. Esta caché puede liberarse después con `docker builder prune`.

**GPU (opcional).** El stack funciona íntegramente sobre CPU. Una **GPU NVIDIA** solo la aprovecha el servicio `voice-agent`, que la utiliza para acelerar la transcripción de voz mediante el modelo **Whisper medium** (ASR). El resto de la inteligencia conversacional (LLM vía proveedor en la nube) y la síntesis de voz no dependen de la GPU.

Para habilitar la aceleración por GPU, el host debe disponer de:

- Una **GPU NVIDIA** con drivers propietarios instalados y funcionales (`nvidia-smi` operativo).
- El **NVIDIA Container Toolkit** instalado, que permite a los contenedores acceder a la GPU.
- **VRAM:** mínimo **6 GB**, recomendado **8 GB**. Whisper medium requiere ~5 GB en GPU (FP16); el margen adicional cubre el overhead de CUDA y el procesamiento de audio.

En un **host sin GPU (CPU / WSL)** debe eliminarse o comentarse el bloque `deploy:` de reserva de GPU del servicio `voice-agent` en `docker-compose.yml`. El servicio arrancará y funcionará sobre CPU, con un rendimiento de transcripción notablemente menor (el modelo *medium* es exigente en CPU).

### Puertos del host

El despliegue publica numerosos servicios en puertos del host, que deben estar libres antes de levantar el stack. El mapeo principal es:

| Servicio | Puerto(s) host | Descripción |
| --- | --- | --- |
| mongo | 27020 | MongoDB; persistencia de Orion-LD y del IoT Agent |
| orion-ld | 1027 | Broker de contexto FIWARE Orion-LD (NGSI-LD); núcleo del sistema |
| crate | 4202 / 4302 | CrateDB: HTTP/admin (4202) y protocolo PostgreSQL (4302) |
| quantumleap | 8669 | Persistencia histórica de series temporales sobre CrateDB |
| chromadb | 8012 | Base de datos vectorial para el RAG (almacén de embeddings) |
| rag-manager | 8300 | Gestión del RAG (indexado y consulta de manuales técnicos) |
| modelador | 8844 | Herramienta de modelado de entidades NGSI-LD |
| postgres | 5433 | Base de datos PostgreSQL de Keycloak |
| keycloak | 8085 | Gestión de identidades y autenticación (IAM) |
| kong | 8010 / 8011 | API Gateway: proxy público (8010) y Admin API (8011) |
| mcp-server | 8082 | Agente conversacional industrial (API de chat / LLM) |
| voice-agent | 8014 | Agente de voz (wake word, ASR Whisper y TTS) |
| iot-agent | 4041 / 9229 | IoT Agent OPC-UA: API North (4041) y depuración Node.js (9229) |
| context-provider | 8080 | Servidor de contextos JSON-LD (Nginx) |
| opcua-linker-backend | 8020 / 5679 | Backend vinculador: API REST (8020) y servidor OPC-UA simulado (5679) |
| opcua-linker-frontend | 8030 | Frontend web (dashboard React servido por Nginx) |

> **Nota:** Orion-LD se publica en el host en el puerto **1027** (no en el habitual 1026). Conviene tenerlo presente en todos los comandos de validación y carga de datos.

### Acceso al repositorio

El repositorio del proyecto es **público** y está alojado en GitHub (`github.com/sothis-tech/data-industry-models`). Al ser público, el clonado no requiere credenciales; basta con Git instalado y conectividad hacia GitHub.

### Servicio de IA (LLM del agente)

El servicio `mcp-server` (agente conversacional) requiere un proveedor de modelo de lenguaje (LLM) para responder al chat. La plataforma admite tres proveedores, seleccionables por configuración:

- **Azure OpenAI** (por defecto) — API externa. Requiere `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` y `AZURE_OPENAI_API_VERSION`. Sin una clave válida, el MCP server no responde al chat.
- **OpenAI Cloud** — API externa. Requiere `OPENAI_API_KEY`.
- **vLLM local** — servidor de inferencia self-hosted; no requiere conectividad externa para la inferencia. Sus requisitos de hardware dependen del modelo LLM que se decida servir y no están predefinidos por la plataforma.

Si se utiliza un proveedor externo (Azure u OpenAI), el host necesita **conectividad saliente** hacia el endpoint correspondiente y **credenciales válidas**. Con el proveedor local (vLLM) no se requiere salida a Internet para la inferencia, pero sí disponer del servidor vLLM operativo.

## Estructura del repositorio

El repositorio es un **monorepo** que agrupa todos los servicios del stack. La estructura principal (primer y segundo nivel):

```
07_inn_espacio_de_datos/
|-- docker-compose.yml             # Orquestacion principal del stack (~17 servicios)
|-- DockerfileKong                 # Imagen de Kong con el plugin tenant-role
|-- README.md
|-- .gitignore
|
|-- agente_control_data_space_v2/  # MCP server: agente conversacional industrial (LLM)
|   |-- config/                    # .env, config_docker.yaml, providers/ (Azure/OpenAI/vLLM)
|   |-- src/                       # Codigo fuente del agente
|   |-- manuales/                  # Documentacion tecnica de apoyo
|   |-- tests/
|   |-- var/                       # Logs y resultados en runtime
|   |-- Dockerfile
|   `-- pyproject.toml
|
|-- data_space/                    # Nucleo del espacio de datos (NGSI-LD)
|   |-- context/                   # Contextos JSON-LD (servidos por context-provider)
|   |-- schemas/                   # Esquemas de modelos de datos
|   |-- scripts/                   # Utilidades de carga y mantenimiento
|   |-- examples/
|   |-- docs/
|   `-- requirements.txt
|
|-- modelador/                     # Herramienta de modelado de entidades NGSI-LD
|   |-- backend/
|   |-- frontend/
|   |-- Dockerfile
|   `-- .env.example / .env.docker.example
|
|-- rag-manager/                   # Gestion del RAG (indexado y consulta de manuales)
|   |-- backend/
|   `-- frontend/
|
|-- chromadb_service/              # Base de datos vectorial para el RAG
|   `-- manuales/                  # Documentos fuente a indexar
|
|-- voice_agent/                   # Agente de voz (wake word, ASR Whisper, TTS)
|   |-- backend/
|   |-- frontend/
|   |-- scripts/
|   |-- Dockerfile.backend / Dockerfile.frontend
|   `-- config.env / config.dev.env / config.prod.env (+ .example)
|
|-- iotagent-opcua/                # IoT Agent OPC-UA (ingesta industrial -> Orion-LD)
|   |-- lib/                       # Codigo fuente (Node.js)
|   |-- conf/                      # Configuracion del agente
|   |-- docker/                    # Dockerfile
|   |-- bin/
|   `-- package.json
|
|-- kong/                          # Configuracion declarativa del API Gateway
|   |-- kong.yml                   # Rutas y servicios (modo DB-less)
|   `-- plugins/                   # Plugin tenant-role (multitenencia)
|
|-- simulador/                     # Vinculador OPC-UA + simulador (opcua-linker)
|   |-- backend/                   # API REST + servidor OPC-UA simulado
|   `-- frontend/                  # Dashboard web (React)
|
|-- backend/
|   `-- plant_state.yaml           # Estado de planta del simulador OPC-UA
|
`-- examples/                      # Ejemplos de carga de modelos de datos
    |-- factory-01/                # load_ibermot.py (modelo de fabrica de ejemplo)
    `-- factory-02/
```

> **Ficheros `docker-compose.yml` internos:** varios servicios (`agente_control_data_space_v2`, `chromadb_service`, `data_space`, `modelador`, `simulador`, `voice_agent`) incluyen su propio `docker-compose.yml` para desarrollo aislado. El despliegue oficial descrito aquí utiliza **exclusivamente** el `docker-compose.yml` de la raíz.

## Guía de despliegue

Levanta el stack completo en una máquina limpia, partiendo de un clon del repositorio. Los pasos deben ejecutarse **en orden**.

### Paso 1 — Clonar el repositorio

```bash
git clone https://github.com/sothis-tech/data-industry-models.git
cd data-industry-models
```

En hosts con una versión antigua de Git puede aparecer el aviso "older Git" de Azure; es inofensivo y no afecta al clonado.

### Paso 2 — Provisionar los ficheros `.env`

Copia cada plantilla a su `.env` y rellena los valores requeridos:

```bash
cp modelador/.env.example                          modelador/.env
cp agente_control_data_space_v2/config/.env.example agente_control_data_space_v2/config/.env
cp voice_agent/config.env.example                  voice_agent/config.env
cp voice_agent/config.dev.env.example              voice_agent/config.dev.env
```

Claves mínimas para que el stack sea funcional:

- **`agente_control_data_space_v2/config/.env`** → credenciales del proveedor de IA (por defecto Azure OpenAI: `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`). Sin clave válida, el MCP server no responde al chat.
- **`modelador/.env`** → el modelador requiere autenticación de forma obligatoria (el servicio no está preparado para operar sin ella). Debe configurarse `ORION_AUTH_REQUIRED=true` y rellenar los parámetros de Keycloak `ORION_KEYCLOAK_REALM`, `ORION_KEYCLOAK_CLIENT_ID` y `ORION_KEYCLOAK_CLIENT_SECRET` (ver Paso 7).
- **`voice_agent/*`** → parámetros de ajuste; no contienen secretos obligatorios.

### Paso 3 — Ajustes según el host

- **Host sin GPU (CPU / WSL):** en `docker-compose.yml`, servicio `voice-agent`, eliminar o comentar el bloque `deploy:` de reserva de GPU NVIDIA.
- **Host con GPU NVIDIA:** dejar el bloque `deploy:` tal cual (ver requisitos de GPU en Prerrequisitos).

### Paso 4 — Validar el docker-compose

Resuelve y valida todas las rutas de build y volúmenes **sin construir nada**:

```bash
docker compose config >/dev/null && echo "COMPOSE OK"
```

Si falla aquí, lo más habitual es un `env_file` inexistente (falta copiar un `.env`) o una ruta de build/volumen incorrecta.

### Paso 5 — Construir las imágenes

Servicios que se construyen desde el repo: `kong`, `rag-manager`, `modelador`, `mcp-server`, `voice-agent`, `iot-agent`, `opcua-linker-backend`, `opcua-linker-frontend`. El resto son imágenes que se descargan.

```bash
docker compose build
```

El `iot-agent` construye la imagen `iotagent-opcua:sothis` desde `./iotagent-opcua`. En una máquina nueva esa imagen no existe, por lo que el primer arranque debe realizarse con `--build`.

> **El build puede tardar más de una hora.** Espera hasta que finalice completamente antes de continuar.

### Paso 6 — Levantar el stack

```bash
docker compose up -d
docker compose ps
docker compose logs -f --tail=50
```

El primer comando arranca los 17 servicios en segundo plano (`-d`). Los dos siguientes permiten comprobar el estado del arranque.

**Resultado deseado:**

- `docker compose ps` debe mostrar todos los servicios en estado `Up`. Los servicios que definen healthcheck (`orion-ld`, `mcp-server`, `kong`, `modelador`, `iot-agent`) aparecerán primero como `health: starting` y pasarán a `healthy` transcurrido su periodo de arranque (15–40 s). Es normal que tarden unos segundos en estabilizarse; conviene esperar y volver a ejecutar `docker compose ps`.
- Ningún servicio debe quedar en `Restarting` de forma continua ni en `Exited`. Un contenedor que se reinicia en bucle indica un error de arranque (habitualmente un `.env` mal provisionado o una dependencia no disponible).
- `docker compose logs -f` no debe mostrar errores repetidos ni trazas de excepción en bucle. Es esperable ver mensajes de espera mientras unos servicios aguardan a que otros estén listos (p. ej. el MCP server esperando a que Orion-LD esté healthy); desaparecen cuando las dependencias quedan operativas.

Ejemplo de salida de `docker compose ps` con el stack correctamente levantado (puertos abreviados al lado del host):

```
NAME                          STATUS         PORTS (host)
dataspace-mongo               Up             27020
dataspace-orion-ld            Up (healthy)   1027
dataspace-crate-db            Up             4202, 4302
dataspace-quantumleap         Up             8669
dataspace-rag-chromadb        Up             8012
dataspace-rag-manager         Up             8300
dataspace-modelador           Up (healthy)   8844
dataspace-postgres_kc         Up             5433
dataspace-keycloak            Up             8085
dataspace-kong                Up (healthy)   8010, 8011
dataspace-mcp-server          Up (healthy)   8082
dataspace-voice-agent         Up             8014
dataspace-iotagent-opcua      Up (healthy)   4041, 9229
dataspace-context-provider    Up             8080
dataspace-opcua-backend       Up             8020, 5679
dataspace-opcua-frontend      Up             8030
```

> **Nota:** puede aparecer un aviso indicando que el atributo `version` del `docker-compose.yml` está obsoleto. Es inofensivo; puede eliminarse esa línea para evitar el aviso.

Para salir del seguimiento de logs (`logs -f`) sin detener los servicios, pulsa `Ctrl+C`: esto solo interrumpe la visualización; los contenedores siguen ejecutándose en segundo plano.

### Paso 7 — Configuración de Keycloak (realm y cliente del modelador)

El servicio `modelador` requiere autenticación contra Keycloak de forma obligatoria. El realm y el cliente se configuran **manualmente desde la consola de administración de Keycloak** una vez levantado el stack. Los valores resultantes se trasladan a `modelador/.env`.

1. Acceder a la consola en **http://localhost:8085**. Credenciales de administrador por defecto: usuario `admin`, contraseña `admin_kc` (definidas en `docker-compose.yml`; deben cambiarse en producción).
2. **Crear un realm**, que equivale a la zona/espacio de autenticación. El realm creado durante las pruebas del proyecto es **`fiware`**. Selecciona siempre el realm `fiware` antes de configurar cualquier otra cosa. La variable `ORION_KEYCLOAK_REALM` del modelador tomará después este nombre de realm (`fiware`).
3. **Dentro del realm, crear el cliente** necesario para solicitar tokens de acceso. Durante las pruebas se creó el cliente **`orion-client`** con tipo de autenticación **OpenID Connect**. Activa **Client authentication** y **Service accounts roles**. En la última pantalla, **Login settings**, no hace falta activar más opciones. Una vez creado, el cliente aparece en el listado de **Clients**. La variable `ORION_KEYCLOAK_CLIENT_ID` tomará este id de cliente (`orion-client`).
4. **Obtener el client secret** del cliente (pestaña **Credentials**) → será el valor de `ORION_KEYCLOAK_CLIENT_SECRET`.
5. **Trasladar los tres valores a `modelador/.env`:**

```dotenv
ORION_AUTH_REQUIRED=true
ORION_KEYCLOAK_REALM=<nombre-del-realm>       # fiware, si no se ha creado otro distinto
ORION_KEYCLOAK_CLIENT_ID=<client-id>          # orion-client, si no se ha creado otro distinto
ORION_KEYCLOAK_CLIENT_SECRET=<client-secret>  # valor obtenido en el paso anterior
```

### Paso 8 — Configuración de Kong (validación de tokens)

Kong valida los tokens JWT emitidos por Keycloak. Su configuración es declarativa y reside en `kong/kong.yml`. Para un despliegue nuevo hay que ajustar en ese fichero, dentro de la sección `jwt_secrets`, los dos valores ligados al realm de Keycloak (ver Paso 7):

- **`key`** → el *issuer* del realm, con formato `http://<host-keycloak>:8085/realms/<nombre-del-realm>`. Por defecto apunta al realm `fiware`; sustitúyelo por el realm real del despliegue.
- **`rsa_public_key`** → la clave pública RSA de ese realm de Keycloak. La incluida en el fichero es de ejemplo y no es válida para otro realm; reemplázala por la del realm creado (disponible en la consola de Keycloak, en **Realm settings → Keys**).

### Paso 9 — Recargar los servicios afectados por la configuración

Los pasos 7 y 8 modifican configuración que los servicios solo leen al arrancar: el modelador toma sus credenciales de Keycloak de `modelador/.env`, y Kong lee su configuración declarativa de `kong/kong.yml`. Como el stack ya estaba levantado (Paso 6), ambos contenedores mantienen la configuración anterior y deben recrearse:

```bash
docker compose up -d --force-recreate kong
docker compose up -d --force-recreate modelador
```

> **¿Por qué `up -d --force-recreate` y no `docker compose restart`?** `restart` reinicia el contenedor existente sin volver a leer la configuración (compose, `env_file`, variables), mientras que `--force-recreate` lo recrea releyendo todo. Este mismo criterio aplica a cualquier servicio cuyo `.env` se modifique con el stack ya en marcha.

Si se prefiere reiniciar el stack completo (p. ej. si se han tocado varios `.env` o el propio `docker-compose.yml`):

```bash
docker compose down
docker compose up -d
```

> **Importante:** usa `docker compose down` **sin** la opción `-v`. La opción `-v` elimina los volúmenes, lo que borraría los datos persistentes (entre otros, la base de datos de Keycloak y su configuración de realm/cliente), obligando a reconfigurarlo todo desde cero.

## Validación funcional

```bash
# Orion-LD vivo (host 1027)
curl -s http://localhost:1027/version

# Carga de datos de ejemplo (en Linux usar python3, no python) — ejecutar desde la raíz del proyecto.
# Durante las pruebas se usó el tenant `ibermot` para el ejemplo ibermot y `metapan` para metapan.
python3 examples/factory-01/load_ibermot.py --broker http://localhost:1027 --tenant ibermot
python3 examples/factory-02/load_metapan.py --broker http://localhost:1027 --tenant metapan

# context-provider sirviendo el JSON-LD
curl -s http://localhost:8080/ -I

# iot-agent operativo
curl -s http://localhost:4041/iot/about
```

Sustituye `<tenant>` por el tenant del modelo de datos que quieras cargar (p. ej. `ibermot`). Después, abre el **modelador** en **http://localhost:8844** para empezar a trabajar con los datos.

## Roles de acceso a tenant

Para que los usuarios puedan acceder a los tenants de los ejemplos, hay que crear roles de acceso en Keycloak. Los roles se crean en el realm **`fiware`**, uno por tenant, en formato `tenant_<nombre-del-tenant-de-orion-ld>`. Por defecto, crea el rol **`tenant_sdm`** para el tenant `sdm` (usado por defecto). Además, crea **`tenant_ibermot`** y **`tenant_metapan`** para acceder a los ejemplos creados.

La configuración de usuarios y la ejecución de los ejemplos se describen en la **Guía de Uso**.

## Resolución de problemas

Errores frecuentes durante el despliegue, con su causa y su solución.

| Síntoma | Causa y solución |
| --- | --- |
| `docker compose config` falla con un error de `env_file` no encontrado. | Falta copiar alguna plantilla `.env`. **Solución:** revisar el Paso 2 y copiar todos los `.env.example` a sus `.env`. |
| El contenedor `voice-agent` se reinicia en bucle. En los logs: `CUDA error: no kernel image is available for execution on the device`. | La build de PyTorch de la imagen no incluye kernels para la arquitectura de la GPU del host. Ocurre con GPU muy recientes (RTX 50xx / Blackwell, sm_120) sobre PyTorch compilado para cu121 (soporta hasta sm_90). **Solución:** ajustar `TORCH_VARIANT` en `Dockerfile.backend` al valor correspondiente a la GPU (`cu121` para V100/sm_70; `cu128` para RTX 50xx/Blackwell) y reconstruir con `docker compose build voice-agent`. La arquitectura se consulta con `nvidia-smi --query-gpu=compute_cap --format=csv,noheader`. |
| El `mcp-server` arranca pero el chat no responde. En los logs: `APIConnectionError` / `All connection attempts failed`. | El agente no alcanza el proveedor LLM. Con Azure/OpenAI: falta la clave o no hay conectividad saliente. Con vLLM local: el servidor no está levantado, o la URL apunta a `localhost` desde dentro del contenedor. **Solución:** verificar la clave en `config/.env`; para vLLM, levantar el servidor y usar el nombre de servicio de Docker (p. ej. `http://vllm:8000/v1`) o `host.docker.internal`, nunca `localhost`. |
| En los logs del `mcp-server`: `Error gestionando Docker: No such file or directory: 'sudo'`. | El agente intenta gestionar el contenedor de vLLM ejecutando `sudo` desde dentro de su propio contenedor, donde `sudo` no existe. **Solución:** vLLM debe desplegarse como servicio independiente; el agente solo debe conectarse a él por red, no arrancarlo. |
| El modelador no funciona o rechaza las peticiones. | El modelador requiere autenticación contra Keycloak. **Solución:** completar el Paso 7 (crear realm y cliente) y rellenar `ORION_AUTH_REQUIRED=true` junto con los parámetros de Keycloak en `modelador/.env`. |
| Tras regenerar el client secret en Keycloak, el modelador sigue fallando en la autenticación, aunque el nuevo valor esté en `modelador/.env`. | El servicio lee su `.env` únicamente al arrancar: un contenedor en ejecución mantiene el secret antiguo en memoria. **Solución:** tras actualizar `ORION_KEYCLOAK_CLIENT_SECRET`, recrear el contenedor para que relea la configuración: `docker compose up -d --force-recreate modelador`. Un `docker compose restart` no es suficiente. |
| Kong rechaza todas las peticiones autenticadas (error de validación de token). | Los valores de `jwt_secrets` en `kong/kong.yml` no coinciden con el realm de Keycloak: el issuer (`key`) o la `rsa_public_key` son de otro realm. **Solución:** actualizar ambos valores (Paso 8) y recargar Kong con `docker compose up -d --force-recreate kong`. |
| Tras modificar `kong/kong.yml`, los cambios no tienen efecto. | Kong opera en modo DB-less y lee su configuración declarativa al arrancar. **Solución:** recrear el contenedor: `docker compose up -d --force-recreate kong`. |
| El `iot-agent` falla al arrancar en una máquina nueva: imagen `iotagent-opcua:sothis` no encontrada. | Esa imagen se construye desde el repositorio y no existe hasta el primer build. **Solución:** ejecutar el build completo (Paso 5) o arrancar con `docker compose up -d --build`. |
| Un servicio no arranca: `address already in use`. | Otro proceso del host ocupa uno de los puertos publicados. **Solución:** consultar la tabla de puertos, identificar el conflicto con `ss -tulpn | grep <puerto>` y liberar o remapear el puerto en `docker-compose.yml`. |
| El agente responde que Orion-LD está vacío (0 tipos · 0 entidades). | El broker está operativo pero no se han cargado datos, o se cargaron bajo un tenant distinto al consultado. **Solución:** cargar el modelo con el tenant correcto y verificar que la cabecera de tenant coincide en la consulta. |
| Tras reiniciar el stack se ha perdido la configuración de Keycloak (realm, cliente). | Se ejecutó `docker compose down -v`; `-v` elimina los volúmenes y con ellos la base de datos de Keycloak. **Solución:** usar siempre `docker compose down` sin `-v`. Si ya ocurrió, rehacer el Paso 7 y actualizar la clave RSA en Kong (Paso 8). |
| El build se queda sin espacio en disco. | Las imágenes con entornos de ML son muy pesadas y la caché de build puede alcanzar ~30 GB. **Solución:** garantizar el espacio recomendado y liberar caché con `docker builder prune`. |
| Aviso al ejecutar comandos: `the attribute 'version' is obsolete`. | El `docker-compose.yml` conserva el atributo `version`, obsoleto en Compose v2. **Solución:** es inofensivo; puede eliminarse esa línea para evitar el aviso. |

## Referencias

Documentación oficial de los principales componentes que integran la plataforma.

**Plataforma FIWARE y gestión de contexto**

| Componente | Enlace |
| --- | --- |
| FIWARE (catálogo) | https://www.fiware.org/catalogue/ |
| Orion-LD (Context Broker NGSI-LD) | https://github.com/FIWARE/context.Orion-LD |
| Especificación NGSI-LD (ETSI) | https://www.etsi.org/ |

**Ingesta industrial (OPC-UA)**

| Componente | Enlace |
| --- | --- |
| IoT Agent OPC-UA (documentación) | https://iotagent-opcua.readthedocs.io/ |
| IoT Agent OPC-UA (repositorio) | https://github.com/Engineering-Research-and-Development/iotagent-opcua |

**Persistencia histórica**

| Componente | Enlace |
| --- | --- |
| QuantumLeap | https://quantumleap.readthedocs.io/ |
| CrateDB | https://cratedb.com/docs/ |

**Seguridad y API Gateway**

| Componente | Enlace |
| --- | --- |
| Keycloak (documentación) | https://www.keycloak.org/documentation |
| Keycloak (guía de administración) | https://www.keycloak.org/docs/latest/server_admin/ |
| Kong Gateway (modo DB-less) | https://developer.konghq.com/gateway/db-less-mode/ |
| Kong Gateway (configuración) | https://developer.konghq.com/gateway/configuration/ |

**Bases de datos**

| Componente | Enlace |
| --- | --- |
| MongoDB | https://www.mongodb.com/docs/ |
| PostgreSQL | https://www.postgresql.org/docs/ |
| ChromaDB (base vectorial) | https://docs.trychroma.com/ |

**Contenedores**

| Componente | Enlace |
| --- | --- |
| Docker | https://docs.docker.com/ |
| Docker Compose | https://docs.docker.com/compose/ |
