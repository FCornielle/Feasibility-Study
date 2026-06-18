"""Test de PFRunSandbox: el proyecto queda IDÉNTICO tras cada run, incluso con excepción.

No usa framework (corre con `python test_sandbox.py`) para no exigir pytest en el intérprete de PF.
"""
from __future__ import annotations

import connect
from sandbox import IntegrityError, PFRunSandbox

PASS, FAIL = "PASS", "FAIL"
results = []


def check(name, cond):
    results.append((PASS if cond else FAIL, name))
    print(f"  [{PASS if cond else FAIL}] {name}")


def main():
    app = connect.get_app()
    prj = app.GetActiveProject()
    netdat = app.GetProjectFolder("netdat")

    def count():
        return len(prj.GetContents("*", 1))

    orig_sc = app.GetActiveStudyCase().loc_name
    baseline = count()
    print(f"baseline objetos={baseline}  study case original={orig_sc!r}")

    # --- Caso 1: run normal ---
    print("Caso 1: run normal")
    with PFRunSandbox(app, run_id="test_ok") as sb:
        grid = sb.create(netdat, "ElmNet", "grid")
        sb.create(grid, "ElmTerm", "PCC")
        during = count()
        check("se crean objetos dentro del with", during > baseline)
        # PF devuelve un wrapper nuevo en cada llamada; comparar por nombre, no por identidad.
        check("study case activo es el del sandbox", app.GetActiveStudyCase().loc_name == sb._studycase.loc_name)
    check("conteo vuelve a baseline tras el with", count() == baseline)
    check("study case original restaurado", app.GetActiveStudyCase().loc_name == orig_sc)

    # --- Caso 2: excepción dentro del with ---
    print("Caso 2: excepción dentro del with")
    raised = False
    try:
        with PFRunSandbox(app, run_id="test_exc") as sb:
            sb.create(netdat, "ElmNet", "grid")
            raise ValueError("fallo simulado a mitad del estudio")
    except ValueError:
        raised = True
    except IntegrityError:
        check("teardown NO debe fallar por integridad", False)
    check("la excepción del cuerpo se propaga", raised)
    check("conteo vuelve a baseline tras excepción", count() == baseline)
    check("study case original restaurado tras excepción", app.GetActiveStudyCase().loc_name == orig_sc)

    # --- Caso 3: no quedan huérfanos etiquetados ---
    print("Caso 3: barrido de huérfanos")
    check("sweep_orphans no encuentra basura", PFRunSandbox.sweep_orphans(app) == 0)
    check("conteo final idéntico al baseline", count() == baseline)

    n_fail = sum(1 for r, _ in results if r == FAIL)
    print(f"\nRESULTADO: {len(results) - n_fail}/{len(results)} PASS")
    return n_fail


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
