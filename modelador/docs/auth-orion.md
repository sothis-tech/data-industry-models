# Autenticación Orion / tenant (TO-BE)

Este documento resume el contrato técnico del fichero `TO_BE_TECNICO AUTENTICACION.docx` y cómo lo consume el modelador.

## Arquitectura

- Todas las consultas de cliente pasan por **Kong**.
- **Keycloak** gestiona usuarios, roles, clientes y emisión de tokens.
- El modelador solicita tokens a Keycloak **a través de Kong**.
- Las llamadas a Orion-LD mantienen la misma ruta NGSI-LD que una llamada directa, pero usando la URL/puerto de Kong.
- El tenant se envía con `NGSILD-Tenant`.
- Kong valida:
  - `Authorization: Bearer <access_token>`
  - expiración del JWT
  - rol `tenant_<tenant>` en `realm_access.roles`

## Flujo de login

Endpoint de token, por defecto:

```text
POST {kong_base_url}/realms/fiware/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded
```

Campos:

- `grant_type=password`
- `client_id=orion-client`
- `client_secret=<secret del cliente Keycloak>`
- `username=<usuario>`
- `password=<contraseña>`

Respuesta esperada:

- `access_token`
- `expires_in`
- `refresh_token`
- `refresh_expires_in`
- `token_type=Bearer`

El frontend no guarda contraseña ni tokens. Envía usuario/contraseña al BFF, el BFF guarda tokens en sesión de servidor y devuelve una cookie HTTP-only opaca.

## Refresh

Cuando el `access_token` caduca, el BFF renueva con:

```text
POST {kong_base_url}/realms/fiware/protocol/openid-connect/token
Content-Type: application/x-www-form-urlencoded
```

Campos:

- `grant_type=refresh_token`
- `client_id=orion-client`
- `client_secret=<secret del cliente Keycloak>`
- `refresh_token=<refresh_token>`

Si el refresh falla o caduca, las rutas proxy devuelven `401` con `error_code=orion_token_expired` cuando `ORION_AUTH_REQUIRED=true`.

## Logout

El BFF cierra sesión en Keycloak con:

```text
POST {kong_base_url}/realms/fiware/protocol/openid-connect/logout
Content-Type: application/x-www-form-urlencoded
```

Campos:

- `client_id=orion-client`
- `client_secret=<secret del cliente Keycloak>`
- `refresh_token=<refresh_token>`

Después elimina la sesión local y la cookie.

## Headers hacia Orion-LD vía Kong

Las peticiones del BFF a Orion-LD incluyen:

```text
Authorization: Bearer <access_token>
NGSILD-Tenant: <tenant>
```

Por defecto el BFF no envía `Fiware-Service` al proxy Kong. Para ejecución local directa contra Orion-LD puede activarse `ORION_SEND_FIWARE_SERVICE=true`.

## Variables de entorno

| Variable | Default | Uso |
| --- | --- | --- |
| `ORION_AUTH_REQUIRED` | `true` | Si `true`, los proxies Orion exigen sesión válida y responden 401 si falta/expira. Puede ponerse a `false` para desarrollo local contra Orion sin Kong. |
| `ORION_KEYCLOAK_REALM` | `fiware` | Realm Keycloak. |
| `ORION_KEYCLOAK_CLIENT_ID` | `orion-client` | Cliente OIDC. |
| `ORION_KEYCLOAK_CLIENT_SECRET` | requerido | Secret del cliente Keycloak. El TO-BE usa cliente con autenticación habilitada; el BFF falla si no está configurado. |
| `ORION_KEYCLOAK_TOKEN_URL` | derivado de `{broker}/realms/{realm}/.../token` | Override del endpoint de token. |
| `ORION_KEYCLOAK_LOGOUT_URL` | derivado de `{broker}/realms/{realm}/.../logout` | Override del endpoint logout. |
| `ORION_AUTH_TIMEOUT_SECONDS` | `10` | Timeout de llamadas a Keycloak. |
| `ORION_SEND_FIWARE_SERVICE` | `false` | Compatibilidad local: si `true`, además de `NGSILD-Tenant` se envía `Fiware-Service`. En Kong/TO-BE debe quedar `false`. |

## Endpoints del BFF

- `POST /api/auth/orion/login`: recibe `broker_base_url`, `fiware_service`, `username`, `password`; obtiene tokens y fija cookie.
- `POST /api/auth/orion/logout`: recibe `broker_base_url` y `fiware_service` por query; cierra Keycloak y sesión local.
- `GET /api/auth/orion/status`: indica si hay sesión válida para broker + tenant.
- `POST /api/health/orion`: exige credenciales, valida login contra Keycloak y prueba el token contra Orion/Kong con `NGSILD-Tenant`.

## Uso en configuración

La URL guardada para el broker debe ser la URL base de **Kong**, por ejemplo:

```text
http://kong:8000
```

En Docker Compose, esa URL debe ser accesible desde el contenedor del modelador, por eso se usa el nombre de servicio `kong` y el puerto interno `8000`. Si ejecutas el backend fuera de Docker, puedes usar el puerto publicado del host (`http://localhost:8010`).

No debe configurarse la URL directa de Orion (`1026`) para el modo TO-BE, porque el endpoint de token, logout y las rutas protegidas se resuelven a través de Kong.

