# Feasibility Study — Estudios de Interconexión PV + BESS al SENI

Plataforma de **estudios de acceso/interconexión** de plantas **fotovoltaicas con almacenamiento (PV + BESS)**
al **Sistema Eléctrico Nacional Interconectado (SENI)** de la República Dominicana, automatizando
**DIgSILENT PowerFactory 2024** a través de su API de Python.

El usuario selecciona una subestación en un mapa, define la planta (MW de PV, MW/MWh de BESS) y la hora de
operación, y la aplicación ejecuta —de forma **no destructiva** sobre el modelo del SENI— toda la batería de
estudios requeridos por el **Código de Conexión**, presentando resultados, tablas y gráficos comparando el
sistema **con y sin** la nueva planta.

> Reemplaza el flujo manual de un estudio de interconexión (ej. el *Estudio de Acceso al SENI – PE Sajoma*)
> por una herramienta interactiva, reproducible y verificable.

---

## ✨ Características

- **Selección en mapa**: subestaciones del SENI georreferenciadas (Leaflet) con sus nombres legibles; al correr
  un flujo, el mapa se convierte en un **heatmap de tensiones** (azul → blanco → naranja → rojo).
- **Modelado PV + BESS coherente con la hora**: el PV genera según el sol y el BESS **carga al mediodía /
  descarga en la noche**, según el escenario de operación seleccionado (P01…P24 = las 24 horas del PDD).
- **Ejecución NO destructiva**: cada estudio corre en un *sandbox* que crea su propio Study Case, escenario y
  objetos, y al terminar **borra todo y deja el proyecto exactamente como estaba** (verificado por conteo de
  objetos, incluso ante excepciones).
- **Estudios implementados** (pestañas):
  | Pestaña | Contenido |
  |---|---|
  | **Steady State** | Flujo de carga + balance del sistema (demanda/generación/pérdidas) + despacho por tecnología + perfil de tensión de barras vecinas (radar) + **Análisis de Contingencia (N-1)** + **Cortocircuito** con/sin planta. |
  | **Small Signal Stability** | (A) Autovalores y amortiguamiento por *matrix-pencil* + (B) velocidad de los generadores más distantes ante una perturbación. |
  | Transient / Voltage / Frequency | Estabilidad transitoria, de tensión y de frecuencia (RMS / curvas P-V). |
  | **Quasi-dinámicas (OC)** | Perfil horario de 24 h con la demanda real del **Organismo Coordinador (OC)**. |
  | **Reporte de Interconexión** | Corre todos los estudios y arma un informe consolidado estilo Sajoma (imprimible a PDF). |
- **Veredicto por delta**: la planta no debe *introducir ni empeorar* violaciones (criterio del Código de Conexión).
- **Datos reales del OC**: cliente del API del Organismo Coordinador (demanda/despacho horario).
- **Distribuible como app de escritorio** (`.exe`, PyWebView) además de webapp local.

---

## 🏗️ Arquitectura

```
┌──────────────────────┐   REST + WebSocket    ┌───────────────────────┐   cola en disco   ┌─────────────────────┐
│  Frontend (Next.js)  │ ───────────────────►  │  Backend (FastAPI)    │ ───────────────►  │  Worker PowerFactory │
│  mapa · pestañas ·   │ ◄───────────────────  │  API · cola de jobs   │ ◄───────────────  │  (proceso persistente│
│  gráficos (Plotly)   │   resultados (JSON)   │  cliente OC           │   results/*.json  │   import powerfactory)│
└──────────────────────┘                       └───────────────────────┘                   └──────────┬──────────┘
                                                                                                       ▼
                                                                                       DIgSILENT PowerFactory 2024
                                                                                          proyecto "PDD 30-09-2025"
```

- **Worker persistente**: `powerfactory.GetApplicationExt()` solo puede llamarse una vez por proceso y PF no es
  *thread-safe* → el worker es un único proceso que atiende los estudios en serie. El backend se comunica con él
  por una **cola basada en archivos** (`JobStore`), lo que desacopla el frontend del motor y permite empaquetar
  todo sin infraestructura extra.
- **`powerfactory.pyd` no se empaqueta**: se resuelve en *runtime* desde la instalación de PowerFactory detectada.

---

## 🧱 Tecnologías

- **Frontend**: Next.js 14 (React 18, TypeScript), React-Leaflet (mapas), Plotly (gráficos).
- **Backend**: FastAPI + Uvicorn; cola de trabajos en disco (stdlib).
- **Motor**: Python 3.9 + módulo `powerfactory` (DIgSILENT PowerFactory 2024); NumPy (identificación modal).
- **Escritorio**: PyWebView + PyInstaller (`.exe` *one-folder*).

---

## 📁 Estructura del proyecto

```
feasibility-study-app/
├── frontend/            # Next.js (mapa, pestañas, gráficos)
│   ├── app/             # layout, página principal, estilos
│   ├── components/      # GridMap, SteadyState, SmallSignalStudy, Charts, ...
│   └── lib/             # cliente del API, definición de pestañas
├── backend/             # FastAPI
│   └── app/             # main, config, modelos, routers (runs, substations, oc, environment)
├── pf_worker/           # Motor PowerFactory
│   ├── connect.py       # conexión al engine, detección de versiones/proyectos/escenarios
│   ├── sandbox.py       # PFRunSandbox (ejecución no destructiva)
│   ├── pv_bess.py       # modelado de la planta PV+BESS (perfiles por hora)
│   ├── dynamics.py      # RMS, matrix-pencil, generadores distantes
│   ├── criteria.py      # umbrales del Código de Conexión
│   ├── studies/         # steady_state, small_signal, transient, voltage, frequency, quasi_dynamic, report
│   └── worker.py        # proceso persistente que consume la cola
├── desktop/             # app de escritorio (launch.py, spec PyInstaller, build.ps1)
├── jobstore.py          # cola de trabajos (compartida backend/worker)
├── paths.py             # rutas con conciencia de empaquetado
├── oc_client.py         # cliente del API del Organismo Coordinador
├── docs/                # layout del reporte, criterios, pendientes
├── run.sh               # lanzador para Git Bash
└── results/             # artefactos generados (no versionado)
```

---

## ⚙️ Requisitos

- **DIgSILENT PowerFactory 2024** instalado y con licencia, y el proyecto del SENI (ej. `PDD 30-09-2025`) importado.
- **Python 3.9** (debe coincidir con un *binding* de `powerfactory.pyd`; PF 2024 trae 3.8–3.12).
- **Node.js** (LTS) para el frontend.

> ⚠️ La aplicación **requiere PowerFactory local**: el motor de simulación no puede ejecutarse en la nube
> (licencia + modelo locales). El frontend sí puede servirse en red local.

---

## 🚀 Ejecución (desarrollo, localhost)

Se necesitan **3 procesos** (el worker primero; tarda ~20 s en conectar a PowerFactory):

```bash
# 1) Worker PowerFactory
cd feasibility-study-app && python pf_worker/worker.py

# 2) Backend (API en :8000)
cd feasibility-study-app/backend && python -m uvicorn app.main:app --port 8000

# 3) Frontend (en :3000)
cd feasibility-study-app/frontend && npm install && npm run dev
```

Luego abrir **http://localhost:3000**.

Atajos:
- **Git Bash**: `./feasibility-study-app/run.sh` (abre las 3 ventanas + el navegador).
- **Windows**: doble clic a un `.bat` lanzador.

### App de escritorio (.exe)
```powershell
cd feasibility-study-app/desktop
.\build.ps1     # exporta el frontend estático + empaqueta con PyInstaller
```
Genera `dist/InterconexionPVBESS/InterconexionPVBESS.exe`. Al abrir, selecciona versión de PowerFactory y
proyecto, y lanza todo en una ventana nativa.

---

## 📐 Metodología y criterios

Los estudios siguen el **Código de Conexión del SENI** (en el marco de la Ley General de Electricidad 125-01) y
toman como referencia de formato el *Estudio de Acceso al SENI – PE Sajoma*. Criterios principales:

- **Tensión**: ±5 % (0.95–1.05 pu) en barras de 69/138/345 kV.
- **Confiabilidad N-1**: sin sobrecarga en los circuitos influenciados.
- **Cortocircuito**: el aporte de la nueva planta no debe superar la capacidad de ruptura de los equipos.
- **Frecuencia**: el nadir debe mantenerse por encima del 1.er escalón del EDAC (**59.2 Hz**).
- **Amortiguamiento**: la planta no debe reducir el amortiguamiento de los modos electromecánicos.

El veredicto es **por delta** (con vs sin planta): la planta no debe *introducir ni empeorar* violaciones
preexistentes del escenario de operación.

---

## 🔌 Fuentes de datos

- **Modelo de red**: proyecto de PowerFactory del SENI (PDD), con 24 escenarios de operación P01…P24 (las horas).
- **Organismo Coordinador (OC)**: API público (WSDL/JSON) para demanda y despacho horario del SENI.
- **Coordenadas geográficas**: GPS del modelo, complementado con datos del proyecto `modom-pypsa` (SMC del OC).

> Por confidencialidad, **el modelo, la base legal/normativa y la documentación del API del OC no se incluyen en
> el repositorio** (ver `.gitignore`). Deben proveerse localmente.

---

## ⏱️ Nota sobre rendimiento

Los estudios dinámicos (RMS: small-signal, transient, frequency) son **mucho más lentos en horas de alta
generación solar** (≈ P09–P17), porque los inversores hacen que el paso interno del integrador se reduzca. Para
pruebas rápidas conviene usar **horas nocturnas** (P20–P05). El worker es asíncrono y muestra el progreso.

---

## ⚠️ Aviso

Los resultados son artefactos analíticos para apoyo a la ingeniería de interconexión y deben validarse contra
estudios oficiales antes de usarse con fines regulatorios o de operación. Estado: en desarrollo activo
(ver `feasibility-study-app/docs/PENDIENTES.md`).
