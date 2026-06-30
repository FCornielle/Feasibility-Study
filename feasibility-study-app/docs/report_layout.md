# Layout del reporte de interconexión al SENI (estructura de referencia)

> Estructura objetivo de un **estudio de acceso/interconexión** al SENI según el *Código de Conexión*.
> La app conecta **PV + BESS**; este documento mapea cada sección del reporte a las **pestañas** de la app
> y a los **gráficos/tablas** que cada estudio debe generar.

## Mapa: sección del reporte → pestaña de la app → salidas

| § Reporte | Contenido | Pestaña app | Gráficos / Tablas a generar |
|---|---|---|---|
| 1 Resumen | Síntesis de resultados y veredicto por estudio | (auto) Resumen/portada del run | Tabla resumen PASA/FALLA por estudio |
| 2–3 Marco de referencia | Regulaciones, ubicación, punto de conexión, tecnología, modelo, demanda, **criterios** | Encabezado del run + `criteria.md` | Ficha del proyecto (PV MW, BESS MW/MWh, PCC, tensión), mapa de ubicación |
| 4 Metodología y escenarios | Escenarios de demanda (máx/media/mín) y generación (worst case) | Config. del run | Tabla de escenarios; selección demanda/despacho |
| 5 Despachos y transferencias inter-regionales | Despacho de máquinas, balances por región (Sur/Norte/DN/Este) | Steady State (contexto) | Cuadros de despacho; tabla de balance por región |
| **6 Comportamiento estático (perfiles de tensión)** | Niveles de tensión con/sin planta, demanda máx y mín | **Steady State** | Gráfico comparativo de tensión por barra (con/sin), tabla kV y pu por barra |
| **7 Comportamiento estático (confiabilidad n-1)** | Carga de circuitos ante contingencias simples | **Steady State** (sub: N-1) | Vista global de cargas %, tabla carga vs límite térmico % |
| **8 Cortocircuito** | Ikss máx/mín, 3φ y 1φ, barras cercanas, con/sin planta | **Steady State** (sub: cortocircuito) | Gráfico comparativo Ikss [kA] con/sin, tabla potencias/corrientes de CC por barra |
| **9.1 Autovalores y amortiguamiento** | Modos de oscilación, raíces, damping | **Small Signal Stability** | Mapa de polos (raíces) con/sin planta, tabla de modos electromecánicos y damping |
| **9.2 Estabilidad transitoria** | Oscilación de rotores, fallas en SSEE, duración máx de falla sin pérdida de sincronismo | **Transient Stability** | Curvas de ángulo de rotor/tensión/frecuencia post-falla por SE, tabla de tiempos críticos de despeje |
| **9.3 Estabilidad de tensión** | Falla 1φ con recierre, respuesta a variaciones de tensión en el PCC, FRT/aporte reactivo | **Voltage Stability** | Curvas de tensión durante falla-despeje-recierre, respuesta Q vs variación V en PCC |
| **9.4 Estabilidad de frecuencia** | Frecuencia ante desconexión de la planta / de una unidad grande | **Frequency Stability** | Curva f(t) ante desconexión, nadir y RoCoF |
| 10 Conclusiones | Resultados por estudio + **cumplimiento del Código de Conexión** | (auto) Conclusión del run | Tabla final de cumplimiento normativo |
| Anexos 1–6 | Tecnología, intercambios, flujos/tensiones, cargas n-1, cortocircuitos, gráficos de estabilidad | Descargas/adjuntos por pestaña | Export de tablas crudas y gráficos por estudio |

## Índice de FIGURAS del reporte (patrón visual a emular)
- Ubicación geográfica y esquema de conexión (→ **mapa** de la app).
- Curva de potencia de la planta solar + perfil del BESS.
- **Comparación de niveles de tensión en barras** (con/sin planta, líneas de límite ±0.05 pu).
- Aporte de corriente reactiva en huecos de tensión; tolerancias FRT ante caídas de tensión.
- **Comparación de corrientes Ikss [kA] de cortocircuito** (sin vs con).
- **Raíces de los modos de oscilación** (sin vs con).
- **Oscilaciones de rotores** (sin vs con).
- **Fallas por SE** (curvas durante falla, con/sin planta), múltiples SSEE a 138/345 kV.
- Tensiones durante falla/despeje/**recierre**.
- Respuesta de los grupos a la **variación de tensión** en el PCC.
- **Frecuencia eléctrica** ante desconexión de la planta y ante desconexión de una unidad grande.

## Índice de CUADROS (tablas) del reporte
- Demandas consideradas (máx/mín, laborable/feriado).
- Parque de generación conectado/previsto (Fuente OC) y **orden de mérito** (Fuente OC) → alimenta despacho.
- Despachos de máquinas (convencionales/no convencionales) en demanda máx y mín.
- Balances por región (Sur, DN, Este, Norte).
- **Niveles de tensión kV y pu** por barra, con/sin planta (demanda máx y mín).
- **Carga vs límite térmico %** (datos de fábrica).
- **Potencias y corrientes de cortocircuito** (máx/mín) por barra, con/sin planta.
- **Duración de estabilidad transitoria** ante falla severa sin pérdida de sincronismo.

## Patrón clave para TODAS las pestañas
Cada estudio se presenta como **comparación "sin planta" vs "con planta"** (caso base vs caso con PV+BESS),
sobre los **escenarios críticos** (demanda máxima día laborable y demanda mínima día feriado; planta a 0 MW y a
~98% de su potencia). El veredicto final es el **cumplimiento del Código de Conexión** (ver `criteria.md`).
