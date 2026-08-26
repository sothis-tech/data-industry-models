# User Guide — Getting Started

[![Overview](https://img.shields.io/badge/Overview-1f6feb?style=for-the-badge)](README.md)
[![Deployment](https://img.shields.io/badge/Deployment-2c6b46?style=for-the-badge)](DEPLOYMENT.md)
[![Getting Started](https://img.shields.io/badge/Getting_Started-8a5c1c?style=for-the-badge)](USER_GUIDE.md)

This is a minimal quick-start: how to open the platform and access the example data models (`ibermot`, `metapan`, `sdm`) that were loaded at the end of the [Deployment Guide](DEPLOYMENT.md). It covers only the essentials — creating a user, granting tenant access, and connecting the Modelador to a tenant. For the full feature reference, see the complete User Guide.

> **Language:** English | [Español](USER_GUIDE.es.md) · Part of the [Industrial Data Space](README.md) documentation.

## Prerequisites

- The stack is up and running (see the [Deployment Guide](DEPLOYMENT.md)).
- The example data has been loaded (Deployment Guide → *Functional validation*), so Orion-LD already holds the `ibermot` and `metapan` tenants.
- Keycloak is reachable at **http://localhost:8085** and the Modelador at **http://localhost:8844**.

## Step 1 — Create a user in Keycloak

1. Open the Keycloak admin console at **http://localhost:8085** and select the **`fiware`** realm.
2. Go to **Users** and create the user (e.g. `ummc`).
3. Set **Email verified** to **Yes**, so the user is active without email confirmation (test environment).
4. On the **Credentials** tab, set a password and turn **Temporary** **Off**, so the system does not force a password change on first login.

## Step 2 — Create a tenant role

Roles control which tenant each user can access. You create **one role per Orion-LD tenant**.

1. In the `fiware` realm, go to **Realm roles**.
2. Create a role named `tenant_<tenant-name>`. For the examples loaded during deployment:
   - `tenant_sdm` — default tenant
   - `tenant_ibermot` — ibermot example
   - `tenant_metapan` — metapan example

## Step 3 — Assign the role to the user

1. Open the user (e.g. `ummc`).
2. On the **Role mapping** tab, assign the tenant role you want to grant (e.g. `tenant_ibermot`).

This way, when the user connects specifying that tenant in the Modelador, their requests carry the `tenant_<name>` role in the token, and Kong validates that they are allowed to access it.

## Step 4 — Open the Modelador and connect to a tenant

1. Open the Modelador at **http://localhost:8844**. It opens on the **Configuration** screen, which is always the entry point.
2. In the **Orion Connection (tenant)** card, fill in:

   | Field | Value |
   | --- | --- |
   | **Name** | A friendly label for the connection (e.g. `ibermot example`) |
   | **Kong base URL** | The Kong gateway address, e.g. `http://kong:8000` |
   | **Tenant** | The tenant to open — `ibermot`, `metapan`, or `sdm` |

3. Enter the **Keycloak username and password** of the user from Step 1. (The password is not stored in the browser; it is only used to obtain the access token.)
4. Click **Connect**.
5. Check that the status bar turns to a **green dot** with "session started" — you are now connected to that tenant.

Once connected, the entities of the selected example are available under the **Entities** and **Visualization** screens.

## Switching between examples

To open a different example, return to **Configuration** and either create a new connection or edit the **Tenant** field (e.g. change `ibermot` to `metapan`), then **Connect** again. Remember the user must have the matching `tenant_<name>` role (Steps 2–3) for each tenant they access.
