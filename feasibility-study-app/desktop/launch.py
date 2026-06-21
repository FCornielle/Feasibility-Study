"""App de escritorio (PyWebView) — Estudios de Interconexión PV+BESS.

Un solo ejecutable con varios roles (para que el .exe empaquetado se reinvoque a sí mismo):
  (sin args)      Shell: muestra 2 popups (versión PF + proyecto), lanza worker + backend y abre la ventana.
  --worker        Corre el worker de PowerFactory (lo invoca el shell como subproceso).
  --probe         Conecta a PF (PF_VERSION) y escribe en stdout el JSON de proyectos; usado por las popups.
  --print-env     Diagnóstico sin GUI: imprime versiones detectadas y la configuración que usaría.

Arquitectura: backend FastAPI (sirve el frontend estático + /api) en 127.0.0.1:PORT, worker PF en
proceso aparte (GetApplicationExt una sola vez por proceso), ventana WebView2 apuntando al backend.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
APP_ROOT = os.path.dirname(HERE)                 # feasibility-study-app/
PF_WORKER = os.path.join(APP_ROOT, "pf_worker")
BACKEND = os.path.join(APP_ROOT, "backend")
for _p in (APP_ROOT, PF_WORKER, BACKEND):
    if _p not in sys.path:
        sys.path.insert(0, _p)

PORT = int(os.environ.get("APP_PORT", "8000"))


# --------------------------------------------------------------------------- roles secundarios
def role_worker():
    import worker  # pf_worker/worker.py (usa PF_VERSION/PF_PROJECT del entorno)
    worker.main()


def role_probe():
    """Lista los proyectos de PowerFactory para la versión elegida (stdout = JSON)."""
    import connect
    try:
        app = connect.get_app(project=None, pf_version=os.environ.get("PF_VERSION"))
        # No activamos proyecto (project=None evita ActivateProject); solo listamos.
        print(json.dumps({"projects": connect.list_projects(app)}))
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"error": str(e)}))


def role_print_env():
    import connect
    versions = [v for v in connect.detect_pf_versions() if v["pythons"]]
    print("Versiones PF usables:", [v["version"] for v in versions])
    print("PF_VERSION:", os.environ.get("PF_VERSION", connect.DEFAULT_VERSION))
    print("PF_PROJECT:", os.environ.get("PF_PROJECT", connect.DEFAULT_PROJECT))
    print("Frontend out/ existe:", os.path.isdir(os.path.join(APP_ROOT, "frontend", "out")))


# --------------------------------------------------------------------------- shell (GUI)
def _self_cmd(*extra):
    """Comando para reinvocar este mismo programa (frozen o desde fuente)."""
    if getattr(sys, "frozen", False):
        return [sys.executable, *extra]
    return [sys.executable, os.path.abspath(__file__), *extra]


def pick(title: str, options: list[str], default: str | None = None) -> str:
    """Popup modal con un desplegable (Tkinter, stdlib)."""
    import tkinter as tk
    from tkinter import ttk

    root = tk.Tk()
    root.title(title)
    root.geometry("440x150")
    root.eval("tk::PlaceWindow . center")
    var = tk.StringVar(value=default or options[0])
    ttk.Label(root, text=title, font=("Segoe UI", 10)).pack(padx=20, pady=(18, 6))
    ttk.Combobox(root, textvariable=var, values=options, state="readonly", width=46).pack(padx=20)
    chosen = {"v": var.get()}

    def ok():
        chosen["v"] = var.get()
        root.destroy()

    ttk.Button(root, text="Aceptar", command=ok).pack(pady=16)
    root.protocol("WM_DELETE_WINDOW", ok)
    root.mainloop()
    return chosen["v"]


def probe_projects(version: str) -> list[str]:
    env = dict(os.environ, PF_VERSION=version)
    try:
        out = subprocess.run(_self_cmd("--probe"), env=env, capture_output=True, text=True, timeout=120)
        data = json.loads(out.stdout.strip().splitlines()[-1])
        return data.get("projects", [])
    except Exception:
        return []


def wait_port(port: int, timeout: float = 40.0) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.4)
    return False


def start_backend(port: int):
    import uvicorn
    from app.main import app as backend_app  # backend/app/main.py

    def _run():
        uvicorn.run(backend_app, host="127.0.0.1", port=port, log_level="warning")

    threading.Thread(target=_run, daemon=True).start()


def role_shell():
    import connect

    versions = [v["version"] for v in connect.detect_pf_versions() if v["pythons"]]
    if not versions:
        _error("No se encontró PowerFactory con bindings de Python instalados.")
        return
    version = versions[0] if len(versions) == 1 else pick("Versión de PowerFactory", versions)

    projects = probe_projects(version)
    if not projects:
        _error(f"No se pudieron listar proyectos de PowerFactory {version}.\n"
               f"¿Está PF disponible y la licencia libre?")
        return
    default_proj = connect.DEFAULT_PROJECT if connect.DEFAULT_PROJECT in projects else projects[0]
    project = projects[0] if len(projects) == 1 else pick("Proyecto de PowerFactory", projects, default_proj)

    os.environ["PF_VERSION"] = version
    os.environ["PF_PROJECT"] = project

    worker_proc = subprocess.Popen(_self_cmd("--worker"), env=dict(os.environ))
    start_backend(PORT)
    wait_port(PORT)

    import webview
    webview.create_window(
        f"Estudios de Interconexión PV+BESS — {project} (PF {version})",
        f"http://127.0.0.1:{PORT}/",
        width=1500, height=950,
    )
    try:
        webview.start()
    finally:
        try:
            worker_proc.terminate()
        except Exception:
            pass


def _error(msg: str):
    try:
        import tkinter as tk
        from tkinter import messagebox
        r = tk.Tk(); r.withdraw()
        messagebox.showerror("Estudios de Interconexión", msg)
        r.destroy()
    except Exception:
        print("ERROR:", msg)


def main():
    if "--worker" in sys.argv:
        role_worker()
    elif "--probe" in sys.argv:
        role_probe()
    elif "--print-env" in sys.argv:
        role_print_env()
    else:
        role_shell()


if __name__ == "__main__":
    main()
