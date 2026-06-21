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

## De Etapa 6 (estudios dinámicos) — refinar en el barrido
Los 4 estudios corren end-to-end y dan resultados sensatos (transient especialmente limpio: falla 3φ → V=0 →
despeje → recuperación 0.998 pu, ángulo 83.7°). Refinamientos pendientes:
- [ ] **Señal de frecuencia**: hoy se monitorea la velocidad del mayor generador (Punta Catalina), que es
      una oscilación local, no la frecuencia del sistema. Usar COI o la frecuencia de barra del PCC; el nadir
      de una máquina distante no es el nadir del SENI.
- [ ] **Small-signal damping**: `damping_ratio` a menudo da `None` (señal distante / bien amortiguada) y se
      reporta FALLA. Tratar `None` como indeterminado; monitorear un generador cercano al PCC; o configurar
      `ComMod` (modal) que hoy no converge (ierr=1).
- [ ] **Transient**: validar ubicación/tiempo de falla por esquema de protecciones; añadir curva LVRT/HVRT;
      fallas en varias SSEE (Sajoma evalúa Naranjo/Sajoma/Navarrete/etc.). Confirmado `EvtShc i_shc=0` (3φ) y `=4` (despeje).
- [ ] **Voltage (P-V)**: el sistema no colapsa a 1.6× carga; extender el rango o usar flujo de continuación
      (CPF) para hallar el punto de colapso real; añadir curvas Q-V.
- [ ] **Comparación con/sin planta** en los 4 dinámicos (hoy solo con planta).
- [ ] **dt/tstop**: ajustados para que completen rápido (~50 s); afinar precisión vs velocidad en el barrido.

## De Etapa 7 (quasi-dinámico / OC) — refinar en el barrido
Corre end-to-end (24/24 horas, demanda real del OC; PV solar y BESS mediodía→punta; PCC 0.967–0.983 pu PASA).
Refinamientos:
- [ ] Usar **ComStatsim/QDS con características** de PF en vez de flujos de carga repetidos.
- [ ] **Mapear el despacho del OC por planta** a los generadores del modelo (hoy solo se escala la demanda total
      uniformemente; ignora distribución espacial y el mix de generación por hora).
- [ ] **Perfil solar real** (pronóstico renovable del OC / medición) en vez de la campana sintética.
- [ ] **Restricción de energía del BESS (MWh)** no aplicada; hoy potencia fija por hora.
- [ ] **Selección de fecha** en el frontend (hoy fija a hace 4 días) y exponer el mix de generación.
- [ ] Compliance **por delta** vs base por hora (hoy absoluto sobre la tensión del PCC).
- [ ] `pf_worker/refdata/` está gitignored (data de modom-pypsa). Si se quiere reproducibilidad sin el otro repo,
      considerar precomputar un `substation_coords.csv` mínimo (Z-code → lat/lon/source) y versionarlo.

## De la etapa Desktop (.exe) — siguientes pasos
La app empaqueta y arranca: detecta PF, resuelve el frontend bundleado, siembra el modelo y muestra
los selectores. Para producto final:
- [ ] **Instalador** (NSIS/Inno Setup/MSIX) sobre `dist/InterconexionPVBESS/` con accesos directos.
- [ ] **Ícono** (.ico) en el EXE (`icon=` en el spec) y branding.
- [ ] **Firma de código** (certificado) para evitar SmartScreen.
- [ ] Confirmar en vivo el **worker congelado** conectando a PF (popups → ventana → correr un estudio).
- [ ] Manejar **selección de versión PF** cuando haya >1 usable (hoy 2021 SP2 no tiene bindings → se filtra).
- [ ] Persistir la última selección (versión/proyecto) y permitir cambiarla desde la app.
- [ ] Reducir tamaño del bundle (excludes de Qt/test) y considerar one-file con dir de datos en %LOCALAPPDATA%.

## De Etapa 8 (reporte / recurso)
- [ ] **Estudio de Recurso** (pestaña 1): definir fuente de datos del recurso solar (irradiancia GHI/POA, estación
      meteorológica, TMY) y el cálculo de energía/factor de planta. Es un estudio DISTINTO al de interconexión
      (el de Sajoma es de interconexión). Hoy es un stub que lo explica.
- [ ] **Exportar PDF real** del reporte (hoy = HTML imprimible desde el navegador, estilo self-contained de
      modom-pypsa). Evaluar reportlab/weasyprint para PDF server-side.
- [ ] **Reusar resultados ya corridos**: el reporte re-ejecuta los 6 estudios en serie (~5 min); permitir
      ensamblar resultados existentes en vez de recalcular.
- [ ] Añadir anexos (tablas crudas por estudio) y portada formal estilo Sajoma.
