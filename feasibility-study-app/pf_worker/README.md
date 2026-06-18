# pf_worker — Motor DIgSILENT PowerFactory

Proceso que habla con PowerFactory 2024 vía el módulo `powerfactory` (modo engine).

## Requisitos
- **PowerFactory 2024** instalado en `C:\Program Files\DIgSILENT\PowerFactory 2024`.
- Proyecto **`PDD 30-09-2025`** ya importado y accesible para el usuario de PF.
- **Python 3.9** (binding `Python\3.9\powerfactory.pyd`). PF 2024 también soporta 3.8/3.10/3.11/3.12;
  `connect.py` elige la carpeta según la versión de Python en ejecución.

## Módulos (orden de ejecución)
1. `connect.py` — conecta al engine y activa el proyecto. `python connect.py` imprime conteos del modelo.
2. `substations.py` — `enumerate_substations()` → `results/substations.json` (nombre, tensiones kV, GPS del modelo).
3. `geo.py` — `build_grid_geojson()` → `results/grid_map.geojson` (subestaciones + rutas de líneas).
4. `enrich_coords.py` — completa coordenadas faltantes cruzando con datos de **modom-pypsa** (no requiere PF).
   Reescribe `substations.json` (añade `coord_source`) y regenera los puntos del GeoJSON.
5. `sandbox.py` — **`PFRunSandbox`**: ejecución NO destructiva. Crea un Study Case dedicado, rastrea todo lo
   creado y en el teardown lo borra, restaura el Study Case original y verifica que el proyecto quedó idéntico
   (conteo recursivo == línea base). `test_sandbox.py` valida la garantía (incluso ante excepción): `python test_sandbox.py` → 9/9 PASS.

## Estudio Steady State (Etapa 3)
- `studies/steady_state.py` — flujo de carga base (sin planta) vs con **PV+BESS**, N-1 sobre líneas de evacuación
  del PCC, y cortocircuito (Ikss 3φ/1φ) en el PCC. Veredicto **por delta** (la planta no debe introducir/empeorar
  violaciones), exportado a `results/<run_id>/steady_state.json`.
- `pv_bess.py` — modela PV (`ElmGenstat` cat. Photovoltaic) + BESS (cat. Storage) en el PCC (barra de mayor
  tensión **energizada** de la subestación). `criteria.py` centraliza umbrales (±5%, <100%, 59.2 Hz).
- Ejecutar: `python studies/steady_state.py <SUBESTACION> <PV_MW> <BESS_MW> <BESS_MWH>`
  (ej.: `python studies/steady_state.py ZNARAD 50 20 80`). Usar `PYTHONIOENCODING=utf-8` en consola Windows.
- Validado en ZNARAD (Naranjo, punto de conexión del estudio Sajoma): PCC 345 kV, Ikss 3φ≈6.6 kA; proyecto limpio.

## Notas de operación del engine
- **`GetApplicationExt()` solo una vez por proceso** ("cannot be started again in the same process"); por eso el
  worker será un proceso persistente (Etapa 4) que la llama una vez y atiende muchas corridas.
- Tras una terminación anormal, la licencia puede quedar tomada ~30 s; esperar y reintentar el proceso.
- Hechos del API validados: `obj.Delete()` saca el objeto del proyecto (el conteo recursivo vuelve a la base);
  la papelera de usuario `RecBin` no acumula basura visible; el Study Case activo se restaura en el teardown.

## refdata/ (no versionado — proviene de modom-pypsa)
`enrich_coords.py` necesita estos CSV en `refdata/`, copiados del repo `modom-pypsa` (`data/external/`):
- `buses_with_coords.csv` — bus_id_modom → lat/lon (match SMC del OC).
- `coordinate_overrides.csv` — overrides manuales confirmados por Fernando.
- `pdd_barras.csv` — export del modelo (`barras.csv`) que mapea subestación (Z) → barra (`for_name`, W).
Enlace: `buses_with_coords.bus_id_modom == pdd_barras.for_name`.

## Estado del modelo (PDD 30-09-2025)
- 217 subestaciones, 5177 terminales, 769 líneas (187 con ruta GPS).
- Coordenadas dentro de RD (lat ~17.8–19.9, lon ~−71.7…−68.7).
- **Cobertura de subestaciones tras enriquecimiento: 183/217** (103 GPS del modelo + 62 SMC del OC + 18 override manual).
- 34 sin coordenadas (mayormente puntos de conexión de planta en MT 13.8/12.5/20/34.5 kV) — completar luego con
  `plano_substation_matches.csv` u overrides manuales.
