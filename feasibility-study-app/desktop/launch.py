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
def _ensure_streams(name: str):
    """En el .exe 'windowed' sys.stdout/stderr son None -> uvicorn (isatty) y print() fallan.
    Redirige a un archivo de log en la carpeta escribible para que existan (y queden para diagnóstico)."""
    if sys.stdout is not None and sys.stderr is not None:
        return
    try:
        import paths
        logdir = paths.RESULTS_DIR
    except Exception:
        logdir = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "results")
    try:
        os.makedirs(logdir, exist_ok=True)
        f = open(os.path.join(logdir, f"_{name}.log"), "a", buffering=1, encoding="utf-8", errors="replace")
    except Exception:
        f = open(os.devnull, "w")
    if sys.stdout is None:
        sys.stdout = f
    if sys.stderr is None:
        sys.stderr = f


def role_worker():
    _ensure_streams("worker")
    import worker  # pf_worker/worker.py (usa PF_VERSION/PF_PROJECT del entorno)
    worker.main()


def role_backend():
    """Corre el backend FastAPI en su PROPIO proceso (evita problemas de hilos/señales del .exe)."""
    _ensure_streams("backend")
    import uvicorn
    from app.main import app as backend_app  # backend/app/main.py
    port = int(os.environ.get("APP_PORT", str(PORT)))
    uvicorn.run(backend_app, host="127.0.0.1", port=port, log_level="warning", log_config=None)


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
    import paths
    versions = [v for v in connect.detect_pf_versions() if v["pythons"]]
    print("Versiones PF usables:", [v["version"] for v in versions])
    print("PF_VERSION:", os.environ.get("PF_VERSION", connect.DEFAULT_VERSION))
    print("PF_PROJECT:", os.environ.get("PF_PROJECT", connect.DEFAULT_PROJECT))
    print("frozen:", getattr(sys, "frozen", False))
    print("FRONTEND_OUT:", paths.FRONTEND_OUT, "->", os.path.isdir(paths.FRONTEND_OUT))
    print("RESULTS_DIR:", paths.RESULTS_DIR, "->", os.path.isdir(paths.RESULTS_DIR))
    print("substations.json:", os.path.exists(os.path.join(paths.RESULTS_DIR, "substations.json")))


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
    root.geometry("440x160")
    root.eval("tk::PlaceWindow . center")
    var = tk.StringVar(value=default or options[0])
    ttk.Label(root, text=title, font=("Segoe UI", 10)).pack(padx=20, pady=(18, 6))
    cb = ttk.Combobox(root, textvariable=var, values=options, state="readonly", width=46)
    cb.pack(padx=20)
    chosen = {"v": var.get()}

    def ok(_evt=None):
        chosen["v"] = var.get()
        root.destroy()

    btn = ttk.Button(root, text="Aceptar (Enter)", command=ok)
    btn.pack(pady=16)
    root.protocol("WM_DELETE_WINDOW", ok)
    # Confirmar con Enter sobre la opción ya seleccionada (autoseleccionada por defecto), sin tener que
    # hacer clic. La ventana toma el foco al frente para poder pulsar Enter directamente.
    root.bind("<Return>", ok)
    root.bind("<KP_Enter>", ok)
    root.attributes("-topmost", True)
    root.after(50, lambda: (root.focus_force(), btn.focus_set()))
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


def free_port() -> int:
    """Un puerto TCP libre (evita choques con otra instancia o con el dev server en :8000)."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def splash_wait(port: int, timeout: float = 150.0) -> bool:
    """Pantalla 'Iniciando…' que se cierra cuando el backend responde /api/health. True si quedó listo."""
    import tkinter as tk
    import urllib.request
    from tkinter import ttk

    root = tk.Tk()
    root.title("Estudios de Interconexión PV+BESS")
    root.geometry("440x150")
    root.eval("tk::PlaceWindow . center")
    ttk.Label(root, text="Iniciando aplicación…\nConectando a PowerFactory (puede tardar unos segundos)",
              font=("Segoe UI", 10), justify="center").pack(pady=(22, 12))
    pb = ttk.Progressbar(root, mode="indeterminate", length=340)
    pb.pack()
    pb.start(12)
    state = {"ok": False, "t0": time.time()}
    url = f"http://127.0.0.1:{port}/api/health"

    def poll():
        try:
            with urllib.request.urlopen(url, timeout=1) as r:
                if r.status == 200:
                    state["ok"] = True
                    root.destroy()
                    return
        except Exception:
            pass
        if time.time() - state["t0"] > timeout:
            root.destroy()
            return
        root.after(600, poll)

    root.protocol("WM_DELETE_WINDOW", lambda: None)   # no cerrable durante el arranque
    root.after(500, poll)
    root.mainloop()
    return state["ok"]


def role_shell():
    import connect

    versions = [v["version"] for v in connect.detect_pf_versions() if v["pythons"]]
    if not versions:
        _error("No se encontró PowerFactory con bindings de Python instalados.")
        return
    # Siempre mostramos el selector con las versiones de DigSILENT detectadas en la computadora.
    version = pick("Versión de DigSILENT PowerFactory detectada:", versions)

    projects = probe_projects(version)
    if not projects:
        _error(f"No se pudieron listar proyectos de PowerFactory {version}.\n"
               f"¿Está PF disponible y la licencia libre?")
        return
    default_proj = connect.DEFAULT_PROJECT if connect.DEFAULT_PROJECT in projects else projects[0]
    project = projects[0] if len(projects) == 1 else pick("Proyecto de PowerFactory", projects, default_proj)

    port = free_port()
    os.environ["PF_VERSION"] = version
    os.environ["PF_PROJECT"] = project
    os.environ["APP_PORT"] = str(port)
    env = dict(os.environ)

    import threading
    procs = {"worker": subprocess.Popen(_self_cmd("--worker"), env=env), "stop": False}
    backend_proc = subprocess.Popen(_self_cmd("--backend"), env=env)

    def _worker_watchdog():
        # Reinicia el worker si muere (p.ej. el motor PF crashea en un RMS pesado): así la cola no se
        # bloquea. Espera para que se libere la licencia; el nuevo worker marca el job 'running' como error.
        while not procs["stop"]:
            procs["worker"].wait()
            if procs["stop"]:
                break
            time.sleep(5)
            procs["worker"] = subprocess.Popen(_self_cmd("--worker"), env=env)
    threading.Thread(target=_worker_watchdog, daemon=True).start()

    if not splash_wait(port):
        _error("El servidor interno no respondió a tiempo.\n"
               "Revisa que PowerFactory esté disponible y la licencia libre, y reintenta.")
        procs["stop"] = True
        for p in (procs["worker"], backend_proc):
            try:
                p.terminate()
            except Exception:
                pass
        return

    import webview
    # Abre maximizada (ocupa toda la pantalla, conservando los controles de la ventana).
    webview.create_window(
        f"Estudios de Interconexión PV+BESS — {project} (PF {version})",
        f"http://127.0.0.1:{port}/",
        width=1500, height=950, maximized=True,
    )
    try:
        webview.start()
    finally:
        procs["stop"] = True
        for p in (procs["worker"], backend_proc):
            try:
                p.terminate()
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
    elif "--backend" in sys.argv:
        role_backend()
    elif "--probe" in sys.argv:
        role_probe()
    elif "--print-env" in sys.argv:
        role_print_env()
    else:
        role_shell()


if __name__ == "__main__":
    main()
