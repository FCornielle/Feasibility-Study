"""Conexión al motor de DIgSILENT PowerFactory 2024 (modo engine/unattended).

PowerFactory 2024 trae `powerfactory.pyd` compilado para CPython 3.8–3.12. Este módulo
detecta la versión de Python en ejecución, agrega la carpeta correspondiente al `sys.path`,
importa `powerfactory` y activa el proyecto objetivo.

Uso como script:
    python connect.py
Imprime versión de PF, proyecto activo y conteos básicos (subestaciones, líneas, terminales).
"""
from __future__ import annotations

import os
import sys

# Defaults (se pueden sobreescribir por argumento o variables de entorno PF_PROJECT / PF_VERSION).
DEFAULT_PROJECT = os.environ.get("PF_PROJECT", "PDD 30-09-2025")
DEFAULT_VERSION = os.environ.get("PF_VERSION", "2024")

# Raíz donde DIgSILENT instala las versiones de PowerFactory.
PF_ROOT = r"C:\Program Files\DIgSILENT"


def pf_install_dir(version: str = DEFAULT_VERSION) -> str:
    return os.path.join(PF_ROOT, f"PowerFactory {version}")


def detect_pf_versions() -> list[dict]:
    """Versiones de PowerFactory instaladas y sus bindings de Python (sin conectar al motor)."""
    out = []
    if not os.path.isdir(PF_ROOT):
        return out
    for name in sorted(os.listdir(PF_ROOT)):
        if not name.startswith("PowerFactory "):
            continue
        path = os.path.join(PF_ROOT, name)
        pydir = os.path.join(path, "Python")
        pythons = sorted(os.listdir(pydir)) if os.path.isdir(pydir) else []
        out.append({"version": name.replace("PowerFactory ", "").strip(), "path": path, "pythons": pythons})
    return out


def _pf_python_dir(install: str) -> str:
    """Carpeta de `powerfactory.pyd` acorde a la versión de Python en ejecución."""
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    path = os.path.join(install, "Python", ver)
    if not os.path.isdir(path):
        avail = os.listdir(os.path.join(install, "Python")) if os.path.isdir(os.path.join(install, "Python")) else []
        raise RuntimeError(
            f"{os.path.basename(install)} no trae binding para Python {ver}. "
            f"Versiones disponibles: {avail}. Ejecuta el worker con uno de esos intérpretes."
        )
    return path


def get_app(project: str | None = None, pf_version: str | None = None):
    """Importa powerfactory, obtiene la aplicación en modo engine y activa `project`.

    `project`/`pf_version` toman el valor de los argumentos, luego de PF_PROJECT/PF_VERSION, luego el default.
    Devuelve el objeto `app` de PowerFactory con el proyecto ya activado.
    """
    project = project or DEFAULT_PROJECT
    install = pf_install_dir(pf_version or DEFAULT_VERSION)
    pf_dir = _pf_python_dir(install)
    if pf_dir not in sys.path:
        sys.path.insert(0, pf_dir)
    # La DLL del engine necesita estar en el PATH del proceso.
    os.environ["PATH"] = install + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(install)

    import powerfactory  # noqa: E402  (import dinámico tras ajustar sys.path)

    # Modo engine sin GUI. IMPORTANTE: GetApplicationExt() solo puede llamarse UNA vez por proceso
    # ("PowerFactory cannot be started again in the same process"); por eso el worker es un proceso
    # persistente que la invoca una sola vez y atiende muchas corridas. Si falla con 4002/4003/4004,
    # suele ser que otra instancia (otro proceso) aún tiene tomada la licencia: esperar y reintentar
    # el PROCESO completo, no la llamada.
    try:
        app = powerfactory.GetApplicationExt()
    except powerfactory.ExitError as e:
        raise RuntimeError(
            f"No se pudo obtener PowerFactory (código {e}). "
            f"¿Hay otra instancia/engine usando la licencia? Cierra el proceso previo y reintenta."
        )
    if app is None:
        raise RuntimeError("GetApplicationExt() devolvió None (licencia/engine).")
    # En modo engine la aplicación ya es headless; no se llama a Show().

    if project:
        activate_project(app, project)
    return app


def activate_project(app, name: str) -> None:
    """Activa el proyecto por nombre; lanza error claro si no existe."""
    err = app.ActivateProject(name)
    if err:  # ActivateProject devuelve 0 en éxito
        raise RuntimeError(f"No se pudo activar el proyecto '{name}' (código {err}).")
    prj = app.GetActiveProject()
    if prj is None:
        raise RuntimeError(f"Proyecto '{name}' no quedó activo tras ActivateProject.")


def list_projects(app) -> list[str]:
    """Proyectos del usuario activo de PowerFactory (para el selector de la app)."""
    user = app.GetCurrentUser()
    if user is None:
        return []
    return sorted({o.loc_name.strip() for o in user.GetContents("*.IntPrj")})


def summary(app) -> dict:
    """Conteos básicos del proyecto activo para validar la conexión."""
    prj = app.GetActiveProject()
    return {
        "pf_version": app.GetVersion() if hasattr(app, "GetVersion") else "?",
        "project": prj.loc_name if prj else None,
        "n_substations": len(app.GetCalcRelevantObjects("*.ElmSubstat")),
        "n_terminals": len(app.GetCalcRelevantObjects("*.ElmTerm")),
        "n_lines": len(app.GetCalcRelevantObjects("*.ElmLne")),
    }


if __name__ == "__main__":
    app = get_app()
    info = summary(app)
    print("Conexión PF OK")
    for k, v in info.items():
        print(f"  {k}: {v}")
