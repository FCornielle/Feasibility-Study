"""PFRunSandbox — ejecución NO destructiva de estudios en PowerFactory.

Garantía central del proyecto: cualquier estudio debe poder crear objetos (Study Case dedicado,
planta PV+BESS, punto de conexión, escenarios, resultados) y, al terminar —incluso si lanza una
excepción—, **borrar todo lo creado y dejar el proyecto exactamente como estaba**.

Hechos del API validados contra el modelo `PDD 30-09-2025`:
  - `obj.Delete()` saca el objeto del proyecto; el conteo recursivo `prj.GetContents('*',1)` vuelve
    a la línea base y la papelera de usuario (`RecBin`) no acumula basura visible.
  - `GetApplicationExt()` solo puede llamarse una vez por proceso (el worker es persistente).
  - El Study Case activo original debe restaurarse al final.

Uso:
    with PFRunSandbox(app, run_id="r123") as sb:
        sb.create(folder, "ElmTerm", "PCC")      # cualquier objeto creado queda rastreado
        sb.attach_pv_bess(...)                    # (Etapa 3)
        run_steady_state(sb)                      # corre en el Study Case del sandbox
    # __exit__: borra lo creado, restaura Study Case original y verifica integridad.
"""
from __future__ import annotations

import time


class IntegrityError(RuntimeError):
    """El proyecto no quedó idéntico tras el teardown (señal de fuga de objetos)."""


class PFRunSandbox:
    #: Prefijo único para identificar todo lo que crea el sandbox (permite barrer huérfanos de crashes).
    TAG_PREFIX = "SBX_"

    def __init__(self, app, run_id: str | None = None, verify: bool = True):
        self.app = app
        self.prj = app.GetActiveProject()
        if self.prj is None:
            raise RuntimeError("No hay proyecto activo; activa el proyecto antes de abrir el sandbox.")
        self.run_id = run_id or time.strftime("%Y%m%d_%H%M%S")
        self.tag = f"{self.TAG_PREFIX}{self.run_id}_"
        self.verify = verify
        self._created: list = []          # objetos creados, en orden de creación
        self._attr_changes: list = []     # (obj, attr, old_value) para revertir mutaciones del modelo
        self._orig_studycase = None       # Study Case a restaurar
        self._orig_scenario = None        # Escenario de operación a restaurar
        self._studycase = None            # Study Case dedicado del run
        self._baseline = None             # conteo de integridad inicial

    # ---- ciclo de vida -----------------------------------------------------
    def __enter__(self) -> "PFRunSandbox":
        if self.verify:
            self._baseline = self._integrity()
        self._orig_studycase = self.app.GetActiveStudyCase()
        # Capturar el ESCENARIO DE OPERACIÓN activo (loads/despacho/switches): un Study Case nuevo
        # nace sin escenario, lo que da un punto de operación equivocado (demanda baja, el slack
        # absorbiendo). Hay que reactivarlo para que la red tenga el despacho real.
        self._orig_scenario = self.app.GetActiveScenario()
        # Capturar los grids activos: un Study Case nuevo nace vacío (sin red), hay que reactivarlos.
        active_grids = self.app.GetCalcRelevantObjects("*.ElmNet")
        # Study Case dedicado: aísla settings de cálculo y resultados (ElmRes) del run.
        study_folder = self.app.GetProjectFolder("study")
        self._studycase = self.create(study_folder, "IntCase", "studycase")
        self._studycase.Activate()
        for g in active_grids:
            try:
                g.Activate()
            except Exception:
                pass
        if self._orig_scenario is not None:
            try:
                self._orig_scenario.Activate()
            except Exception:
                pass
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        # Teardown SIEMPRE, incluso ante excepción. No se traga la excepción del cuerpo.
        self.teardown()
        return False

    # ---- creación rastreada ------------------------------------------------
    def _tagged(self, name: str) -> str:
        return f"{self.tag}{name}"

    def create(self, folder, classname: str, name: str):
        """Crea un objeto en `folder`, lo etiqueta y lo rastrea para su borrado."""
        obj = folder.CreateObject(classname, self._tagged(name))
        if obj is None:
            raise RuntimeError(f"No se pudo crear {classname} '{name}' en {folder.loc_name}.")
        self._created.append(obj)
        return obj

    def track(self, obj):
        """Rastrea un objeto creado por fuera de `create()` (p. ej. por un método de PF)."""
        if obj is not None:
            self._created.append(obj)
        return obj

    def set_attr(self, obj, attr: str, value) -> None:
        """Modifica un atributo de un objeto EXISTENTE del modelo guardando su valor previo.

        El teardown lo revierte. Necesario porque el chequeo de integridad (conteo de objetos) no
        detecta cambios de atributos; así garantizamos que el estado operacional también se restaura
        (p. ej. togglear `outserv` de líneas en el análisis N-1)."""
        self._attr_changes.append((obj, attr, obj.GetAttribute(attr)))
        obj.SetAttribute(attr, value)

    # ---- modelado de la planta (placeholder para Etapa 3) ------------------
    def attach_pv_bess(self, *args, **kwargs):
        raise NotImplementedError("attach_pv_bess se implementa en la Etapa 3 (modelado PV+BESS y PCC).")

    # ---- teardown ----------------------------------------------------------
    def teardown(self) -> None:
        # 1) Restaurar el Study Case original antes de borrar el del sandbox.
        try:
            if self._orig_studycase is not None and not self._orig_studycase.IsDeleted():
                self._orig_studycase.Activate()
            if self._orig_scenario is not None and not self._orig_scenario.IsDeleted():
                self._orig_scenario.Activate()
        except Exception:
            pass
        # 2) Revertir mutaciones de atributos sobre objetos del modelo, en orden inverso.
        for obj, attr, old in reversed(self._attr_changes):
            try:
                if obj is not None and not obj.IsDeleted():
                    obj.SetAttribute(attr, old)
            except Exception:
                pass
        self._attr_changes.clear()
        # 3) Borrar todo lo creado, en orden inverso, sin que un fallo detenga el resto.
        for obj in reversed(self._created):
            try:
                if obj is not None and not obj.IsDeleted():
                    obj.Delete()
            except Exception:
                pass
        self._created.clear()
        # 4) Verificar que el proyecto quedó idéntico.
        if self.verify:
            after = self._integrity()
            if after != self._baseline:
                raise IntegrityError(
                    f"El proyecto no quedó idéntico: baseline={self._baseline} after={after}. "
                    f"Revisar objetos huérfanos del run {self.run_id}."
                )

    # ---- utilidades --------------------------------------------------------
    def _integrity(self) -> int:
        """Conteo recursivo de objetos del proyecto (firma de integridad)."""
        return len(self.prj.GetContents("*", 1))

    @classmethod
    def sweep_orphans(cls, app) -> int:
        """Borra objetos etiquetados que hayan quedado de corridas previas abortadas. Devuelve cuántos."""
        prj = app.GetActiveProject()
        orphans = [o for o in prj.GetContents("*", 1) if o.loc_name.startswith(cls.TAG_PREFIX)]
        for o in orphans:
            try:
                if not o.IsDeleted():
                    o.Delete()
            except Exception:
                pass
        return len(orphans)
