# Frontend — NGSI-LD Modelador

Frontend React + TypeScript del modelador de espacios de datos NGSI-LD.
Construido con **Vite 8**, **React 19** y **TypeScript**.

---

## Requisitos

| Herramienta | Versión requerida |
|-------------|-------------------|
| Node.js | `>=20.19.0 <23` (fijado en `.nvmrc` y `engines` en `package.json`) |
| npm | `>=10` |

Si usas [`nvm`](https://github.com/nvm-sh/nvm), ejecuta `nvm use` en esta carpeta para activar automáticamente la versión correcta.

---

## Instalación

```bash
npm install
```

---

## Scripts

| Comando | Descripción |
|---------|-------------|
| `npm run dev` | Servidor de desarrollo con HMR en `http://localhost:5173` |
| `npm run build` | Compilación TypeScript + bundle de producción en `dist/` |
| `npm run lint` | ESLint sobre todos los archivos `.ts` / `.tsx` |
| `npm run preview` | Sirve localmente el `dist/` generado por `build` |

> El servidor de desarrollo usa un proxy: `/api` → `http://127.0.0.1:8000` (FastAPI).  
> Asegúrate de que el backend esté corriendo antes de arrancar `dev`.

---

## Dependencias principales

| Paquete | Para qué se usa |
|---------|-----------------|
| `react` + `react-dom` | Biblioteca de UI |
| `react-router-dom` | Routing SPA (`/`, `/entidades`, `/visualizacion`) |
| `d3` | Grafos de fuerza interactivos en la vista Visualización |
| `react-select` | Dropdown con búsqueda integrada (filtro de tipo en `/entidades`) |

Las dependencias de desarrollo (`@types/*`, `vite`, `eslint`, etc.) están en `devDependencies` dentro de `package.json`.

---

## Estructura del código

```
frontend/src/
├── types/          # Interfaces TypeScript puras (sin lógica)
│   ├── broker.ts
│   ├── entity.ts
│   └── graph.ts
├── lib/            # Utilidades sin React (http, storage, parsers)
│   ├── http.ts
│   ├── storage.ts
│   ├── model-parser.ts
│   └── graph-utils.ts
├── api/            # Clientes HTTP hacia el backend FastAPI
│   ├── orion.ts
│   ├── model.ts
│   ├── validation.ts
│   └── graph.ts
├── hooks/          # Hooks React reutilizables
│   ├── useAppStatus.ts
│   ├── useBroker.ts
│   ├── useModel.ts
│   ├── useEntityList.ts
│   └── useSplitResize.ts
├── components/     # Componentes de UI genéricos
│   ├── StatusBar.tsx
│   ├── StatusMessage.tsx
│   └── ConfirmModal.tsx
├── pages/          # Una carpeta por ruta
│   ├── config/         # Ruta /
│   ├── entities/       # Ruta /entidades
│   └── viz/            # Ruta /visualizacion
├── styles/         # CSS modular (importado desde index.css)
│   ├── tokens.css      # Custom properties globales
│   ├── base.css        # Reset y elementos base
│   ├── layout.css      # Shell, topbar, tabs
│   ├── components.css  # StatusBar, modales, onboarding
│   └── pages/
│       ├── config.css
│       ├── entities.css
│       └── visualization.css
├── App.tsx         # Router principal y Layout
├── main.tsx        # Punto de entrada
└── index.css       # Solo @import — no estilos directos aquí
```

---

## Despliegue en producción

El frontend se compila a archivos estáticos que FastAPI sirve directamente.

```bash
# 1. Desde la carpeta frontend, generar el build
npm run build        # genera frontend/dist/

# 2. Arrancar el backend (sirve API + frontend compilado en el mismo puerto)
cd ../backend
uvicorn main:app --host 0.0.0.0 --port 8000
```

> `dist/` está en `.gitignore`. Hay que ejecutar `npm run build` en cada despliegue antes de arrancar el servidor.

---

## Convenciones

- **Imports**: rutas relativas — sin alias `@/`
- **Tipos**: en `types/` si se comparten; inline si son locales al archivo
- **CSS**: todas las custom properties en `tokens.css`; un archivo por página en `styles/pages/`
- **PowerShell (Windows)**: usar comandos separados en lugar de `&&`  
  (`npm run build` y `npm run lint` por separado, no `npm run build && npm run lint`)
