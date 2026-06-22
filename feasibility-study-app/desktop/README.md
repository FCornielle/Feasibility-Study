# Desktop — App de escritorio (.exe)

Empaqueta toda la webapp en una sola aplicación de Windows con **PyWebView** (ventana WebView2) +
backend FastAPI embebido + worker de PowerFactory. Al abrir muestra **dos ventanas de selección**:
versión de PowerFactory y proyecto.

## Cómo funciona
- `launch.py` es el único punto de entrada y tiene varios roles (para que el .exe se reinvoque a sí mismo):
  - sin args → **shell**: popup de versión de DigSILENT (siempre) + popup de proyecto → lanza worker y
    backend (subprocesos) → muestra una pantalla **"Iniciando…"** que espera a que el backend responda
    `/api/health` → abre la ventana. Así nunca aparece "127.0.0.1 refused to connect".
  - `--worker`  → corre el worker de PowerFactory (subproceso; usa `PF_VERSION`/`PF_PROJECT`).
  - `--backend` → corre el backend FastAPI en su propio proceso (evita problemas de hilos/señales del .exe).
  - `--probe`   → conecta a PF y lista proyectos (alimenta la popup de proyecto).
  - `--print-env` → diagnóstico sin GUI.
- El backend usa un **puerto libre** (no fijo a 8000, para no chocar con el dev server ni otra instancia);
  sirve el frontend **estático** (`frontend/out`) y la API en `127.0.0.1:<puerto>` (mismo origen, sin CORS).
- **No** abrir el .exe con el stack de desarrollo corriendo: PowerFactory tiene una sola licencia/engine.
- `powerfactory.pyd` **no** se empaqueta: se resuelve en runtime desde la instalación de PF detectada
  (`connect.detect_pf_versions()` escanea `C:\Program Files\DIgSILENT\PowerFactory *`).

## Construir el .exe
Requisitos: Python 3.9, Node (winget), PowerFactory 2024, y `pip install -r desktop/requirements.txt`.

```powershell
cd feasibility-study-app\desktop
.\build.ps1
```
Genera `dist\InterconexionPVBESS\InterconexionPVBESS.exe` (carpeta one-folder). El instalador (NSIS/MSI)
se arma luego sobre esa carpeta.

Pasos que hace `build.ps1`:
1. `DESKTOP=1 npm run build` → exporta el frontend a `frontend/out/`.
2. Verifica `results/substations.json` y `grid_map.geojson` (artefactos del modelo que se bundlean).
3. `pyinstaller desktop/launch.spec` → one-folder con el frontend y los datos del modelo.

## Probar desde fuente (sin empaquetar)
```bash
python desktop/launch.py            # abre las popups y la ventana
python desktop/launch.py --print-env
```

## Notas
- **one-folder** (no one-file): `results/` queda escribible junto al .exe; `paths.py` resuelve la base.
- El worker mantiene la licencia de PF mientras la app esté abierta.
- Para regenerar los artefactos del modelo antes de construir:
  `python pf_worker/substations.py && python pf_worker/geo.py && python pf_worker/enrich_coords.py`
