# Espacio de Datos Industrial

Plataforma para la integración, el modelado y la explotación de datos industriales, que conecta la capa de operaciones (OT) con la de información (IT) sobre un espacio de datos basado en NGSI-LD. El sistema combina la adquisición de datos por OPC-UA, un modelo de datos compartido, la orquestación segura de servicios, el histórico de series temporales y un conjunto de agentes de IA para el control y la interacción en lenguaje natural.

> **Idioma:** [English](README.md) | Español

## Descripción general

El sistema toma datos de dispositivos y sistemas industriales (PLCs, SCADAs, sensores), los normaliza y los lleva a un espacio de datos donde pueden modelarse, consultarse y ser consumidos por servicios de analítica e IA.

Las fuentes industriales exponen sus datos por OPC-UA. Un IoT Agent traduce esa información al estándar NGSI-LD y la integra en el espacio de datos, respaldado por el context broker Orion-LD. Sobre esa base se articulan un modelador de datos, la persistencia histórica y varios servicios de IA que consumen y actúan sobre la información.

La plataforma es **multitenant**: cada modelo de datos de fábrica vive en su propio tenant. Cada petición se autentica y autoriza — todo el tráfico pasa por el API gateway Kong, que valida los tokens de identidad emitidos por Keycloak y aplica el control de acceso por tenant. Todo el stack está contenedorizado y orquestado con Docker Compose.

## Diagrama de arquitectura

![Arquitectura de la solución](architecture.svg)

## Despliegue

Las instrucciones completas, paso a paso, para levantar el stack en una máquina limpia —prerrequisitos, provisión de `.env`, build, configuración de Keycloak y Kong, y resolución de problemas— están en la **[Guía de Despliegue](DEPLOYMENT.es.md)**.

## Arquitectura

El sistema se organiza en contenedores desacoplados, orquestados con Docker Compose y expuestos a través de un gateway común. Las aplicaciones cliente nunca hablan directamente con los servicios internos: todo el tráfico se enruta y se protege a través de Kong.

### API Gateway y seguridad

- **Kong** — API gateway y punto de entrada único de todo el sistema (`:8010` proxy público, `:8011` Admin API). Enruta las peticiones a los servicios internos y aplica la seguridad en dos capas: validación de JWT (verificando los tokens emitidos por Keycloak) y un plugin propio **`tenant-role`** que autoriza cada petición contra el tenant declarado en la cabecera `NGSILD-Tenant`. Las peticiones de token también se canalizan a través de Kong hacia Keycloak. Desde el punto de vista del usuario, todo apunta a Kong, nunca a los componentes ni a Keycloak directamente.
- **Keycloak** — Proveedor de identidad (IdP) de la plataforma (`:8085`), con el realm `fiware`. Gestiona usuarios, clientes y roles, y emite tokens OpenID Connect (JWT de acceso + refresco), habilitando SSO y gestión centralizada de identidades. La autorización sigue un modelo multitenant: cada tenant se corresponde con un rol de realm `tenant_<nombre-del-tenant>` (el tenant por defecto es `sdm`, con el rol `tenant_sdm`).

### Cliente

- **Modelador** — Aplicación de modelado de entidades NGSI-LD y principal cliente de cara al usuario (interfaz React, `:8844`). El usuario se conecta seleccionando un tenant y autenticándose contra Keycloak; todas las peticiones posteriores llevan ese ámbito de tenant a través del gateway.

### Núcleo del espacio de datos

- **Orion-LD** — Context broker NGSI-LD de FIWARE, núcleo del sistema (`:1027`); gestiona las entidades y su ciclo de vida, aisladas por tenant.
- **Context Provider** — Servidor de `@context` JSON-LD (Nginx, `:8080`) que sirve el modelo de datos compartido. Define los términos y tipos NGSI-LD usados en toda la plataforma, de modo que las entidades de Orion-LD y las aplicaciones que las consumen compartan un vocabulario común y resoluble.
- **QuantumLeap** — Persistencia de series temporales de datos NGSI-LD (`:8669`), almacenando el histórico sobre CrateDB.

### Servicios de IA

- **MCP Server** — Servidor Model Context Protocol (`:8082`); agente conversacional industrial que expone las capacidades del sistema a herramientas de IA (API de chat / LLM).
- **RAG Manager** — Gestor de Retrieval-Augmented Generation (`:8300`) para consultas en lenguaje natural sobre manuales técnicos e información del sistema; se apoya en el almacén vectorial ChromaDB.
- **Voice Agent** — Agente de interacción por voz (`:8014`): wake word, ASR (Whisper) y TTS.

### Ingesta industrial (OT)

- **IoT Agent OPC-UA** — Ingesta datos industriales por OPC-UA y traduce las variables de dispositivo a NGSI-LD (`:4041` API north). El puente entre la capa de operaciones y la de información.
- **OPC-UA Linker — Backend** — API REST (`:8020`) que mueve el vinculador, más un servidor OPC-UA simulado integrado (`:5679`) para desarrollo y pruebas sin hardware físico.

El **OPC-UA Linker — Frontend** (dashboard React servido por Nginx, `:8030`) es la interfaz de usuario de esta capa: relaciona visualmente la topología industrial (los NodeId del servidor OPC-UA) con el modelo semántico de Orion-LD, aprovisionando dispositivos de forma declarativa y estableciendo los tiempos de muestreo/publicación. Se comunica con el Linker Backend por REST.

### Almacenes de datos

- **ChromaDB** (`:8012`) — Almacén vectorial para los embeddings del RAG, consumido por el RAG Manager.
- **MongoDB** (`:27020`) — Almacén de respaldo de Orion-LD y el IoT Agent (entidades NGSI-LD, por tenant).
- **CrateDB** (`:4202`) — Almacén de respaldo del histórico de series temporales de QuantumLeap.
- **PostgreSQL** (`:5433`) — Almacén de respaldo de Keycloak (usuarios, roles, clientes).

## Flujo de una petición

1. Un cliente (p. ej. la aplicación Modelador) se autentica contra Keycloak —a través de Kong— y obtiene un token de acceso OpenID Connect.
2. Cada petición posterior se envía a Kong, incluyendo la cabecera `Authorization: Bearer <token>` y la cabecera `NGSILD-Tenant` que indica el tenant destino.
3. Kong valida el JWT contra Keycloak y ejecuta el plugin `tenant-role`, comprobando que el token lleva el rol `tenant_<nombre>` correspondiente al tenant solicitado (p. ej. `tenant_sdm` para el tenant `sdm`).
4. Si la validación pasa, Kong enruta la petición al servicio interno correspondiente (Orion-LD, QuantumLeap, RAG manager, MCP Server o Voice Agent).

## Stack tecnológico

- **Estándares industriales / datos:** OPC-UA, NGSI-LD, FIWARE
- **Identidad y seguridad:** Keycloak (OpenID Connect), Kong API Gateway, JWT
- **Backend:** Python
- **Frontend:** React
- **IA:** RAG, ChromaDB (base de datos vectorial), MCP, Whisper (ASR)
- **Almacenes de datos:** MongoDB, CrateDB, PostgreSQL, ChromaDB
- **Infraestructura:** Docker, Docker Compose, Nginx

## Documentación

- **[Guía de Despliegue](DEPLOYMENT.es.md)** — prerrequisitos, instalación, build y configuración en una máquina limpia.
- **Guía de Uso** — configuración de usuarios y ejecución de los ejemplos.
