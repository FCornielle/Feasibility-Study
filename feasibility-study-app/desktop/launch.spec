# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec (one-folder) para la app de escritorio.
# powerfactory.pyd NO se empaqueta: se resuelve en runtime desde la instalación de PowerFactory.
import os
from PyInstaller.utils.hooks import collect_all, collect_submodules

APP_ROOT = os.path.dirname(os.path.abspath(SPECPATH))  # feasibility-study-app/
PF_WORKER = os.path.join(APP_ROOT, "pf_worker")
BACKEND = os.path.join(APP_ROOT, "backend")

datas = [
    (os.path.join(APP_ROOT, "frontend", "out"), "frontend/out"),
    (os.path.join(APP_ROOT, "results", "substations.json"), "results"),
    (os.path.join(APP_ROOT, "results", "grid_map.geojson"), "results"),
    (os.path.join(PF_WORKER, "refdata"), "pf_worker/refdata"),  # coords enriquecidas (modom + PDF)
]
binaries = []
hidden = []

# Paquetes con imports dinámicos que PyInstaller no rastrea solo.
for pkg in ("uvicorn", "webview", "fastapi", "starlette", "pydantic", "pydantic_core", "anyio"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hidden += h

# Nuestros módulos (algunos se importan dinámicamente).
hidden += [
    "connect", "jobstore", "export", "sandbox", "paths", "pv_bess",
    "criteria", "dynamics", "oc_client", "worker",
    "studies.steady_state", "studies.voltage", "studies.small_signal",
    "studies.transient", "studies.frequency", "studies.quasi_dynamic", "studies.report",
    "app.main", "app.config", "app.models",
    "app.routers.runs", "app.routers.substations", "app.routers.oc",
    "tkinter", "tkinter.ttk", "tkinter.messagebox",
]

a = Analysis(
    [os.path.join(APP_ROOT, "desktop", "launch.py")],
    pathex=[APP_ROOT, PF_WORKER, BACKEND],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    runtime_hooks=[],
    excludes=["powerfactory"],  # se carga en runtime desde PF
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [], exclude_binaries=True,
    name="InterconexionPVBESS",
    console=False,            # app de ventana (sin consola)
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe, a.binaries, a.datas,
    strip=False, upx=False,
    name="InterconexionPVBESS",
)
