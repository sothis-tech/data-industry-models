# Guía de Uso — Primeros pasos

Guía rápida mínima: cómo abrir la plataforma y acceder a los modelos de datos de ejemplo (`ibermot`, `metapan`, `sdm`) que se cargaron al final de la [Guía de Despliegue](DEPLOYMENT.es.md). Cubre solo lo esencial: crear un usuario, conceder acceso al tenant y conectar el Modelador a un tenant. Para la referencia completa de funcionalidades, consulta la Guía de Uso completa.

> **Idioma:** [English](USER_GUIDE.md) | Español · Parte de la documentación de [Espacio de Datos Industrial](README.es.md).

## Requisitos previos

- El stack está levantado y en ejecución (ver la [Guía de Despliegue](DEPLOYMENT.es.md)).
- Los datos de ejemplo están cargados (Guía de Despliegue → *Validación funcional*), de modo que Orion-LD ya contiene los tenants `ibermot` y `metapan`.
- Keycloak es accesible en **http://localhost:8085** y el Modelador en **http://localhost:8844**.

## Paso 1 — Crear un usuario en Keycloak

1. Abre la consola de administración de Keycloak en **http://localhost:8085** y selecciona el realm **`fiware`**.
2. Ve a **Users** y crea el usuario (p. ej. `ummc`).
3. Marca **Email verified** en **Yes**, para que el usuario esté activo sin confirmación de correo (entorno de pruebas).
4. En la pestaña **Credentials**, asigna una contraseña y pon **Temporary** en **Off**, para que el sistema no exija el cambio de contraseña en el primer inicio de sesión.

## Paso 2 — Crear un rol de tenant

Los roles controlan a qué tenant puede acceder cada usuario. Se crea **un rol por cada tenant de Orion-LD**.

1. En el realm `fiware`, ve a **Realm roles**.
2. Crea un rol con el formato `tenant_<nombre-del-tenant>`. Para los ejemplos cargados durante el despliegue:
   - `tenant_sdm` — tenant por defecto
   - `tenant_ibermot` — ejemplo ibermot
   - `tenant_metapan` — ejemplo metapan

## Paso 3 — Asignar el rol al usuario

1. Entra en el usuario (p. ej. `ummc`).
2. En la pestaña **Role mapping**, asigna el rol del tenant que quieras conceder (p. ej. `tenant_ibermot`).

De esta forma, cuando el usuario se conecte indicando ese tenant en el Modelador, sus peticiones llevarán el rol `tenant_<nombre>` en el token, y Kong validará que tiene permiso para acceder a él.

## Paso 4 — Abrir el Modelador y conectar a un tenant

1. Abre el Modelador en **http://localhost:8844**. Se abre en la pantalla de **Configuración**, que es siempre el punto de entrada.
2. En la tarjeta **Conexión Orion (tenant)**, rellena:

   | Campo | Valor |
   | --- | --- |
   | **Nombre** | Una etiqueta amigable para la conexión (p. ej. `ejemplo ibermot`) |
   | **URL base Kong** | La dirección del gateway Kong, p. ej. `http://kong:8000` |
   | **Tenant** | El tenant a abrir — `ibermot`, `metapan` o `sdm` |

3. Introduce el **usuario y contraseña de Keycloak** del usuario del Paso 1. (La contraseña no se guarda en el navegador; solo se usa para obtener el token de acceso.)
4. Pulsa **Conectar**.
5. Verifica que la barra de estado cambia a un **punto verde** con «sesión iniciada» — ya estás conectado a ese tenant.

Una vez conectado, las entidades del ejemplo seleccionado están disponibles en las pantallas de **Entidades** y **Visualización**.

## Cambiar entre ejemplos

Para abrir un ejemplo distinto, vuelve a **Configuración** y crea una nueva conexión o edita el campo **Tenant** (p. ej. cambia `ibermot` por `metapan`); luego pulsa **Conectar** de nuevo. Recuerda que el usuario debe tener el rol `tenant_<nombre>` correspondiente (Pasos 2–3) para cada tenant al que acceda.
