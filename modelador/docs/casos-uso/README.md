# Casos de uso NGSI-LD (IBERMOT y METAPAN)

Espacio reservado para las **guías puente**: operar cada espacio de datos con el modelador web (carga del `.zip`, broker, sesión, visualización y gestión de entidades).

## Fuente oficial

La especificación completa está en:

`**Casos de Uso NGSI-LD.docx`**

Ruta de evidencias del proyecto (ajustar si tu copia local difiere):

`NUNSYS\Proyectos Innovación - Subvenciones\INNOVACION\APROBADOS\07-SMART DATA MODELS\03_Tecnico\PT2\Evidencias\`

## Casos definidos en el documento


| ID    | Caso             | Resumen                                                                                                                  |
| ----- | ---------------- | ------------------------------------------------------------------------------------------------------------------------ |
| CU-01 | **IBERMOT S.A.** | Planta de fabricación de vehículos eléctricos (Valladolid): Building, BuildingSpace, ~40 máquinas, sensores, operaciones |
| CU-02 | **METAPAN S.A.** | Planta de baguettes congeladas (Sevilla): cadena harina → IQF → envasado; trazabilidad por lote en `operationOutput`     |


La sección 4 del Word describe la **metodología común** (contexto + schemas + ejemplos → `.zip` → carga en el modelador).

## Artefactos en `07_inn_espacio_de_datos`


| Caso          | Población masiva Orion (demo)         | Paquete para modelador                                                   |
| ------------- | ------------------------------------- | ------------------------------------------------------------------------ |
| CU-01 IBERMOT | `load_factory.py` → **415** entidades | ZIP basado en plantilla `mi_modelo.zip`, **contenido distinto** al horno |
| CU-02 METAPAN | `load_metapan.py` → **363** entidades | Idem                                                                     |


Análisis scripts + ZIP + desalineaciones (`hasPart` vs `componentes`, `refDevice` vs `device`): **[REFERENCIA-PAQUETE-Y-SCRIPTS.md](REFERENCIA-PAQUETE-Y-SCRIPTS.md)**.

## Guías en este repositorio (pendientes)


| Fichero            | Estado                                                               |
| ------------------ | -------------------------------------------------------------------- |
| `CU-01-ibermot.md` | Por redactar (requiere paquete `.zip` y URL de broker de referencia) |
| `CU-02-metapan.md` | Por redactar (idem)                                                  |


Cuando existan los paquetes de modelo versionados, enlazarlos aquí con nombre de archivo, versión y checklist de validación (`scripts/validate.py` del paquete).

## Relación con otros modelos

El caso **horno industrial E-Therm** (Industrial Oven) es un espacio de datos aparte; no forma parte de CU-01 ni CU-02. Su documentación vive en el repositorio/carpeta *Data Spaces / Industrial Oven*.