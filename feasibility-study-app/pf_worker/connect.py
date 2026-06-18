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

# Nombre del proyecto objetivo dentro de PowerFactory (ya importado por el usuario).
DEFAULT_PROJECT = "PDD 30-09-2025"

# Raíz de instalación de PowerFactory 2024.
PF_INSTALL = r"C:\Program Files\DIgSILENT\PowerFactory 2024"


def _pf_python_dir() -> str:
    """Carpeta de `powerfactory.pyd` acorde a la versión de Python en ejecución."""
    ver = f"{sys.version_info.major}.{sys.version_info.minor}"
    path = os.path.join(PF_INSTALL, "Python", ver)
    if not os.path.isdir(path):
        raise RuntimeError(
            f"PowerFactory 2024 no trae binding para Python {ver}. "
            f"Versiones disponibles: {os.listdir(os.path.join(PF_INSTALL, 'Python'))}. "
            f"Ejecuta el worker con uno de esos intérpretes."
        )
    return path


def get_app(project: str = DEFAULT_PROJECT):
    """Importa powerfactory, obtiene la aplicación en modo engine y activa `project`.

    Devuelve el objeto `app` de PowerFactory con el proyecto ya activado.
    """
    pf_dir = _pf_python_dir()
    if pf_dir not in sys.path:
        sys.path.insert(0, pf_dir)
    # La DLL del engine necesita estar en el PATH del proceso.
    os.environ["PATH"] = PF_INSTALL + os.pathsep + os.environ.get("PATH", "")
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(PF_INSTALL)

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
