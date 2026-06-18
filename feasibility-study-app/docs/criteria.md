# Criterios de aceptación (umbrales) — Estudios de interconexión PV+BESS al SENI

> Borrador derivado del *Estudio de Acceso al SENI – PE Sajoma* (§3.1, §3.6, §10) y de la normativa citada.
> Estos umbrales se codifican luego en `pf_worker/criteria.py`. Cada estudio emite **PASA/FALLA** comparando el
> resultado de PowerFactory contra el umbral, sobre los escenarios críticos (demanda máx/mín, planta 0% y ~98%).

## Norma que gobierna
- **Código de Conexión** del SENI, en el marco de la **Ley General de Electricidad 125-01**. Evolución de la norma:
  - **Res. SIE 28-2004** — versión citada por el estudio Sajoma (2018), cap. **CC8**, acápite **CC8.3** ("Estudios Eléctricos").
  - **Res. SIE-060-2015** — **Código de Conexión del SENI vigente** que reemplazó a la 28-2004 (referencia base actual).
  - **Paquete 2026 de la SIE (20 reglamentos del sector eléctrico)** — contiene la **actualización 2026** que indicó Fernando.
    ⚠️ **A confirmar el número exacto del reglamento de conexión/operación en transmisión.** Ojo: `SIE-007-2026-REG`
    es el **Reglamento de Generación Distribuida** (MV/BT, IEEE 1547) — *no* es el código de interconexión en transmisión.
- Complementos: **Reglamento de Regulación de Frecuencia SIE-136-2024-MEM** (frecuencia/RPF), *Reglamento 555-02*, *Código Eléctrico Nacional*.

> **⚠️ Limitación de extracción:** los PDFs de resoluciones SIE en la base legal están **escaneados como imágenes**
> (0 caracteres de texto extraíble). Fijar los umbrales numéricos exactos del Código 2026 (puntos de la curva FRT,
> escalones del EDAC más allá del primero, límites de RoCoF) requerirá **OCR** de esos PDFs. Tarea de seguimiento
> antes de congelar `criteria.py`. Candidatos por tamaño a revisar con OCR: `SIE-007-2026-REG`(146pg, GD),
> `SIE-061-2025-REG`(171pg), `SIE-013-2025-REG`(181pg), `SIE-155-2025-REG`(149pg).

## Tabla de criterios

| Estudio (pestaña) | Magnitud evaluada | Umbral / criterio | PASA si… | Fuente |
|---|---|---|---|---|
| **Steady State – Tensión** | Tensión en barras de generadores y barras de 69/138/345 kV (operación sin fallas) | **±5%** del valor nominal (±0.05 pu) | todas las barras dentro de 0.95–1.05 pu | Sajoma §3.1.1.a, §3.6; Cód. Conexión |
| **Steady State – n-1** | Carga de circuitos (líneas/trafos) vs límite térmico ante contingencias simples | **Sin sobrecarga**; mantener condición n-1 en barras 138 kV que ya cumplían antes de conectar la planta | ningún circuito influenciado supera su límite térmico (% < 100) en n-1 | Sajoma §3.1.1.a, §7, §10.2.g |
| **Steady State – Cortocircuito** | Aporte de corriente de CC (3φ y 1φ, Ikss máx/mín) en cada barra influenciada | El total **con** la nueva generación **no debe superar la capacidad de ruptura / valor máximo admisible** del equipamiento existente | Ikss_total ≤ capacidad nominal de interrupción del equipo en cada SE | Sajoma §3.1.1.b, §8, §10.2.b |
| **Small Signal Stability** | Modos de oscilación electromecánicos (autovalores) y amortiguamiento | La planta **no debe disminuir** el amortiguamiento del SENI; modos estables | parte real de eigenvalores < 0 (estables) y damping ≥ caso base (referencia práctica ≥3–5%) | Sajoma §3.1.1.c, §9.1, §10.2.e |
| **Transient Stability** | Estabilidad angular ante falla severa (CC 3φ sin impedancia) hasta despeje y post-falla | El sistema mantiene sincronismo hasta el despeje; la planta **no reduce** la capacidad existente. Margen vs **tiempo crítico de despeje** | sin pérdida de sincronismo (no pole-slip) para el tiempo de despeje de protecciones | Sajoma §3.1.1.c, §9.2, §10.2.d |
| **Transient – FRT** | Fault Ride Through de la planta PV/BESS ante hueco de tensión | Permanecer conectada e inyectar reactivo: **≥450 ms a tensión 0**, aumentando el tiempo en proporción a tensiones entre 0 y 80% nominal | la planta no se desconecta dentro de la curva FRT y aporta Q | Sajoma §3.2 (nota 4), §9.3 |
| **Voltage Stability** | Falla 1φ con recierre exitoso; respuesta a variaciones de tensión en el PCC | La estabilidad de tensión **no se ve afectada**; la planta aporta al control de tensión (reactivo) | recuperación de tensión tras despeje/recierre; respuesta Q adecuada ante ΔV en PCC | Sajoma §9.3, §10.1.b |
| **Frequency Stability** | Frecuencia ante desconexión intempestiva de la planta (y ante pérdida de unidad grande) | **El nadir debe mantenerse por encima del PRIMER ESCALÓN del EDAC = 59.2 Hz** (esquema de alivio de carga por subfrecuencia del SENI). El RoCoF no debe provocar el cruce de 59.2 Hz antes de la respuesta. Reserva rotante RPF **3%** | nadir ≥ **59.2 Hz** (no se activa el 1.er escalón del EDAC); RoCoF dentro de límite | Sajoma §9.4, §3.6; SIE-136-2024-MEM; **EDAC SENI (1.er escalón 59.2 Hz)** |

## Parámetros y supuestos de modelado (de §3.6)
- **Niveles de tensión simulados:** 345, 138, 69 kV (y MT para conexión de generación).
- **Modelo de carga:** dependiente de tensión, **1 [%/%]** (autorregulación).
- **Reserva rotante para RPF:** 3% del valor nominal en la generación despachada.
- **Escenarios de demanda (ejemplo Sajoma 2023):** máx laborable 2720 MW / mín 2134 MW; máx feriado 2477 MW / mín 1815 MW. *(En la app, la demanda/despacho por escenario se toma del OC — pestaña quasi-dinámica.)*
- **Generación de la planta:** caso "sin recurso" (0 MW) y caso ~**98%** de potencia (worst case, baja ocurrencia anual).
- **Comparación obligatoria:** todos los estudios se reportan **con planta vs sin planta**.

## Manejo de la batería (BESS) — escenarios obligatorios
- **Dos juegos de casos por subestación:** (a) **PV sin batería** y (b) **PV + batería**. Cada estudio se corre para
  ambos para aislar el efecto del BESS.
- **Lógica operativa del BESS:** desplazar energía del **mediodía** (excedente solar → **carga** de la batería) hacia
  las **horas de punta** (→ **descarga**). En la pestaña quasi-dinámica (24 h con datos del OC) esto define el perfil
  horario de carga/descarga; en los estudios estáticos/dinámicos se evalúan los **dos extremos**: BESS **cargando**
  (mediodía, mayor inyección PV) y BESS **descargando** (punta, máxima entrega).
- **Criterios aplican igual** a los casos con BESS (tensión ±5%, n-1 sin sobrecarga, CC ≤ ruptura, frecuencia ≥59.2 Hz,
  FRT). El BESS además **debe ayudar** (no perjudicar) al soporte de tensión/frecuencia.

## Estado de cierre de criterios (Etapa 0)
**Cerrados:**
- Tensión ±5%; n-1 sin sobrecarga; CC ≤ capacidad de ruptura; FRT ≥450 ms a tensión 0; reserva RPF 3%; carga 1%/%.
- **Frecuencia: nadir ≥ 59.2 Hz** (primer escalón del EDAC del SENI) — confirmado.
- **Casos con y sin batería** definidos; lógica BESS mediodía→punta definida.
- Norma vigente identificada: Código de Conexión SENI **SIE-060-2015** (+ actualización 2026 por confirmar nº).

**Pendientes (requieren OCR de PDFs escaneados o confirmación de Fernando):**
1. Número exacto del reglamento de **conexión/operación en transmisión** del paquete SIE 2026.
2. Umbral numérico de **damping** mínimo (Sajoma lo evalúa cualitativo "no disminuye"; fijar valor, p.ej. ≥3–5%).
3. **Curva FRT** exacta para PV + BESS según el Código vigente (puntos tensión-tiempo).
4. **Límite de RoCoF** y escalones del EDAC posteriores al primero, del Reglamento SIE-136-2024-MEM (vía OCR).
