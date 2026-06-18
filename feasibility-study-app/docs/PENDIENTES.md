# Pendientes acumulados (para retomar luego)

Lista viva de tareas que dejamos abiertas al avanzar. Cada una indica de qué etapa viene.

## De Etapa 0 (criterios / normativa)
- [ ] **OCR de las resoluciones SIE escaneadas** para extraer umbrales numéricos exactos: puntos de la **curva FRT**,
      **límite de RoCoF**, **escalones del EDAC** posteriores al primero (59.2 Hz ya confirmado), y valor numérico de
      **damping** mínimo. Los PDFs en `Base Legal/04_Resoluciones` no tienen texto (son imágenes).
- [ ] **Confirmar el número exacto** del reglamento de conexión/operación en transmisión del **paquete SIE 2026**
      (SIE-007-2026-REG es Generación Distribuida, no transmisión). Candidatos por tamaño: SIE-061-2025-REG,
      SIE-013-2025-REG, SIE-155-2025-REG.
- [ ] **Revisión de Fernando** de `sajoma_layout.md` y `criteria.md` (criterio de aceptación de Etapa 0).
- [ ] Definir alcance y datos del **Estudio de Recurso** (pestaña 1) — se aborda en Etapa 8.

## De Etapa 1 (modelo / mapa)
- [ ] **Completar las 34 subestaciones sin coordenadas** (mayormente conexiones de planta en MT 13.8/12.5/20/34.5 kV):
      usar `plano_substation_matches.csv` de modom-pypsa o añadir overrides manuales en `coordinate_overrides.csv`.
- [ ] `connect.py::summary()` devuelve `pf_version: ?` — encontrar la API correcta para la versión de PowerFactory.
- [ ] Confirmar si una subestación puede tener **varias barras candidatas a PCC** (afecta selección en el mapa y
      el modelado del punto de conexión en Etapa 3).

## De Etapa 3 (Steady State)
- [ ] **El Study Case BASE del modelo tiene violaciones preexistentes** (≈92 tensiones fuera de ±5% y 5
      sobrecargas, máx ~354%): no es un escenario despachado/afinado. Los estudios reales deben correr sobre
      **escenarios de demanda/despacho** (máx/mín) — se resuelve con los Operation Scenarios y datos del OC (Etapa 7).
      Mientras tanto, el veredicto **por delta** (con vs sin planta) aísla correctamente el impacto de la planta.
- [ ] **Selección del PCC**: hoy = barra de mayor tensión energizada de la subestación. Hacerlo **configurable**
      (p. ej. preferir 138 kV para una PV, o que el usuario elija la barra en el mapa de Etapa 5).
- [ ] **Modelado PV/BESS**: hoy `ElmGenstat` en modo PQ (av_mode='constq', Q=0). Añadir **control de tensión/reactivo**
      (constv) y curva FRT; el BESS con modos carga/descarga ya parametrizados pero sin límite de energía (MWh) aplicado.
- [ ] **Tamaño del JSON** (~980 KB): base y with_plant guardan las 4084 barras; recortar para el frontend (Etapa 5)
      a violaciones + resumen + barras de la zona influenciada.
- [ ] **N-1**: hoy solo sobre líneas de evacuación del PCC (10) y solo con planta; comparar también contra N-1 base.

## De Etapa 1 (datos de referencia)
- [ ] `pf_worker/refdata/` está gitignored (data de modom-pypsa). Si se quiere reproducibilidad sin el otro repo,
      considerar precomputar un `substation_coords.csv` mínimo (Z-code → lat/lon/source) y versionarlo.
