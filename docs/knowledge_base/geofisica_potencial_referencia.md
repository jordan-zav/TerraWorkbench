# Geofísica de Campos Potenciales — Referencia Técnica

Documento de referencia para el módulo de geofísica (magnetometría, gravimetría, radiometría gamma, filtros FFT, preparación de levantamientos e inversión 3D) implementado en QGIS. Cada entrada indica fórmula, fundamento, qué resalta/calcula, aplicación en exploración mineral y limitaciones u observaciones de implementación.

Cada herramienta declara explícitamente en la interfaz su dominio numérico — `[SPATIAL / FINITE DIFFERENCE]`, `[FFT / HARMONICA]`, `[FFT / MAGMAP-LIKE]`, `[MIXED GRID / FFT]`, `[PHYSICAL CORRECTION / GRID]`. Ver la taxonomía completa en §9.

---

## 1. Magnetometría — Realces y derivadas

### 1.1 DX — Derivada horizontal Este
**Fórmula:** Dx = ∂T/∂x

**Qué hace:** Calcula la tasa de cambio del campo magnético total (T) en la dirección Este. Un cambio lateral en susceptibilidad (contacto litológico, falla, borde de intrusivo) produce un máximo en Dx.

**Aplicación:** Contactos litológicos, bordes de intrusivos (pórfidos, skarns, epitermales), diques/sills como lineamientos de alto gradiente, fallas y zonas de cizalla orientadas favorablemente al eje X.

**Limitación:** No indica profundidad, composición ni tipo de depósito; combinar con AS, THDR, Tilt y geología. Depende de la orientación de la estructura respecto al eje X.

**Dominio:** `[SPATIAL / FINITE DIFFERENCE]` por defecto — menos problemas de borde. Desde v0.12.0 existe también **DX FFT** (operador espectral ikx, `[FFT / HARMONICA]`), útil cuando se va a encadenar con otros filtros que ya operan en número de onda (Butterworth, continuaciones, etc.) dentro del Filter Stack.

---

### 1.2 DY — Derivada horizontal Norte
**Fórmula:** Dy = ∂T/∂y

**Qué hace:** Equivalente a Dx pero en dirección Norte. Complementa Dx: un contacto N-S responde fuerte en Dx y débil en Dy, y a la inversa en un contacto E-W.

**Aplicación:** Lineamientos estructurales orientados favorablemente al eje Y, fallas regionales, corredores tectónicos, dominios magnéticos en cinturones metamórficos/greenstone belts. Por commodity: oro (zonas de cizalla, contactos volcánico-sedimentarios), níquel (contactos máfico-ultramáficos), hierro (delimitación de BIF).

**Nota de implementación:** Se combina con Dx para THDR, eliminando la dependencia direccional individual.

**Dominio:** `[SPATIAL / FINITE DIFFERENCE]` por defecto. Desde v0.12.0 existe también **DY FFT** (operador espectral iky, `[FFT / HARMONICA]`), análogo a DX FFT.

---

### 1.3 DZ — Primera derivada vertical
**Fórmula:** Dz = ∂T/∂z (convención vertical positiva hacia arriba, Harmonica)

**Qué hace:** Mide el cambio del campo al alejarse verticalmente de la fuente. Actúa como filtro de alta frecuencia: realza fuentes someras y bordes, atenúa tendencias regionales.

**Aplicación:** Mineralización superficial (magnetita, cuerpos máficos, skarns magnéticos), geometría de diques/vetas/cuerpos tabulares, exploración bajo cobertura (regolito, aluvión).

**Limitación:** Amplifica ruido — requiere control de calidad, nivelación y desruido previos.

**Dominio:** `[FFT / HARMONICA]` — la derivada vertical no tiene una definición de diferencias finitas consistente sobre una sola grilla 2D, por lo que siempre se calculó espectralmente. Desde v0.12.0 esto además se expone como algoritmo explícito ("derivada vertical por FFT") en vez de estar solo implícito dentro de otras herramientas (THDR, Tilt, ASA, etc.).

---

### 1.4 DZ2 — Segunda derivada vertical
**Fórmula:** Dzz = ∂²T/∂z²

**Qué hace:** Resolución espacial aún mayor que Dz; extremadamente sensible a cambios rápidos.

**Aplicación:** Blancos pequeños (magnetita en pocos cientos de metros, vetillas magnéticas, alteración hidrotermal), separación de anomalías cercanas (un solo máximo en MAG puede resolverse en varios centros), estructuras menores/fallas secundarias.

**Nota de implementación:** Interpretar junto con Dz, AS y RS — un máximo fuerte en Dz2 puede ser cuerpo real, ruido o artefacto de procesamiento.

---

### 1.5 UC — Continuación ascendente (altura configurable)
**Fórmula:** T̂ₕ = T̂₀·e^(−kh)

**Qué hace:** Transformación en dominio de frecuencia que simula la respuesta a mayor altura de vuelo. Suprime progresivamente anomalías pequeñas/someras y conserva estructuras grandes/profundas.

**Implementación:** la altura h es un parámetro configurable, compartido con el operador genérico de §5.2 ("Continuación ascendente configurable"). El nombre y el ID del algoritmo no codifican una altura fija.

**Aplicación:** Arquitectura tectónica regional, dominios corticales, intrusivos profundos (pórfidos Cu-Au, sistemas Sn-W), fallas y corredores estructurales mayores.

**Limitación:** No usar para blancos pequeños — pueden desaparecer por completo. Combinar con Dz, Dz2, RS, AS.

---

### 1.6 RS — Realce residual
**Fórmula:** T_res = T − T_UC(h)

**Qué hace:** Diferencia entre el campo y su continuación ascendente; extrae la componente de alta frecuencia (fuentes someras/pequeñas) tras remover la componente regional.

**Aplicación:** Selección de blancos de perforación, cuerpos pequeños magnéticos, oro asociado a magnetita hidrotermal/su destrucción, IOCG (magnetita, hematita, alteración).

**Limitación:** Valores altos deben validarse con geología, geoquímica y perforación — no distinguen tipo de fuente por sí solos.

---

### 1.7 THDR — Derivada horizontal total
**Fórmula:** THDR = √(Dx² + Dy²)

**Qué hace:** Magnitud del gradiente horizontal, independiente de la dirección del contacto. Uno de los filtros de borde más usados.

**Aplicación:** Contactos litológicos (granito-volcánico, intrusivo-sedimento), delimitación de intrusivos (tamaño/forma/extensión en pórfidos y skarns), fallas y zonas de cizalla.

**Limitación:** Marca bordes pero no profundidad ni composición; combinar con AS, Tilt, TDX.

---

### 1.8 Tilt — Ángulo tilt
**Fórmula:** Tilt = tan⁻¹(Dz / THDR)

**Qué hace:** Normaliza la respuesta convirtiendo amplitud en ángulo, reduciendo la dependencia del tamaño/intensidad de la anomalía. Cuando Dz = THDR, Tilt = 45°.

**Aplicación:** Detección de bordes/contactos/fallas (uso principal), estructuras profundas enterradas, exploración bajo cobertura sedimentaria o aluvial.

**Limitación:** Respuestas múltiples en cuerpos complejos o con magnetización remanente; interpretar junto con THDR, AS y RTP si está disponible.

---

### 1.9 HG azimutal — Gradiente horizontal direccional
**Fórmula:** HGθ = sin(θ)·Dx + cos(θ)·Dy — el usuario selecciona el azimut θ entre 0° y 360°, medido desde el Norte.

**Qué hace:** Proyecta el gradiente horizontal sobre una dirección específica (a diferencia de THDR, que es la magnitud total sin orientación preferente). Realza estructuras cuya orientación es favorable respecto al azimut de proyección.

**Aplicación:** Fallas inversas/transcurrentes, zonas de cizalla, fracturas dilatantes, corredores hidrotermales — especialmente útil cuando el contraste magnético del borde es débil en el campo original. Mejora continuidad de lineamientos bajo cobertura.

**Limitación:** La respuesta depende fuertemente del azimut elegido; estructuras con orientación desfavorable pierden contraste. No interpretar una única orientación como rasgo geológico real sin contrastar con THDR/AS.

---

### 1.10 AS / ASA — Amplitud de señal analítica
**Fórmula:** ASA = √(Dx² + Dy² + Dz²) = ‖∇T‖

**Qué hace:** Magnitud total del gradiente (componentes horizontales + vertical). Reduce el efecto de inclinación, declinación y polarización de la anomalía.

**Aplicación:** Localización de cuerpos magnéticos (magnetita, intrusivos máficos/ultramáficos, skarns), hierro (BIF, magnetita masiva), Ni-Cu (canales magmáticos, cuerpos diferenciados), alteración hidrotermal (creación/destrucción de magnetita secundaria).

**Limitación:** Detecta contraste magnético, no mineral económico ni ley; integrar con geología/geoquímica/perforación.

---

### 1.11 TDX — Ángulo tilt horizontal
**Fórmula:** TDX = tan⁻¹(THDR / |Dz|)

**Qué hace:** Relación inversa del Tilt convencional; enfatiza la relación entre cambio lateral y componente vertical, respondiendo fuerte a contactos y discontinuidades laterales, incluso cuando Dz es pequeño.

**Aplicación:** Contactos débiles (roca débilmente magnética frente a sedimento), estructuras profundas/fallas/límites tectónicos enterrados, refinamiento de blancos combinado con AS/THDR/Tilt.

**Nota:** Complementa al Tilt — algunos contactos se definen mejor con la relación inversa.

---

### 1.12 Theta Map
**Fórmula:** Θ = cos⁻¹(THDR / ASA)

**Qué hace:** Relación angular entre el gradiente horizontal total y el gradiente total; mide cómo se distribuye la energía del gradiente entre componente horizontal y vertical.

**Aplicación:** Delimitación de bordes/contactos, separación de fuentes magnéticas cercanas, análisis de geometría/orientación de cuerpos.

**Secuencia de lectura:** AS → "¿dónde está el cuerpo?"; THDR → "¿dónde está el borde?"; Theta → "¿cómo está orientado el gradiente?".

---

## 2. Magnetometría — Dirección del campo magnético

**Estado (v0.11.1):** RTP, RTE e IGRF ya están agrupados y nombrados con claridad en la UI (grupo separado dentro de magnetometría) — antes daban la impresión de estar ausentes por mezclarse visualmente con otros filtros. Los cuatro operadores de esta sección son, en dominio de cálculo, **FFT propio** (ver tabla de dominios en el Apéndice, §9).

### 2.1 RTP manual — Reducción al polo
**Qué hace:** Transforma la anomalía magnética a la que se observaría si el cuerpo estuviera en el polo magnético (I=90°), centrando la anomalía sobre la fuente y eliminando la asimetría dipolar. Inclinación y declinación se ingresan manualmente.

**Aplicación:** Estandariza la interpretación de bordes y centros de cuerpos magnéticos, especialmente relevante fuera de latitudes altas donde la anomalía original está desplazada respecto a la fuente.

---

### 2.2 RTP automática (IGRF-14)
**Qué hace:** Calcula inclinación y declinación en el centro del raster a partir de fecha del levantamiento, ubicación y altitud (modelo IGRF-14). Permite incorporar remanencia. Limita la ganancia espectral para estabilizar el cálculo en latitudes bajas (donde el RTP clásico es inestable).

**Aplicación:** Igual que RTP manual, pero automatizado y geográficamente consistente; preferible cuando se cuenta con metadatos de fecha/ubicación del vuelo.

---

### 2.3 RTE — Reducción al ecuador
**Fórmula/objetivo:** Campo objetivo I = 0°; conserva la declinación calculada o introducida.

**Qué hace:** Análogo al RTP pero transformando hacia inclinación cero, apropiado quirúrgicamente para zonas de baja latitud magnética donde el RTP es inestable.

**Aplicación:** Levantamientos en o cerca del ecuador magnético (relevante para Perú y gran parte de Sudamérica), donde RTP convencional degrada la señal.

---

### 2.4 Transformación general de dirección
**Fórmula (dominio de frecuencia):**
H(kx,ky) = F²_objetivo / (F_campo · F_magnetización), con límite configurable de ganancia.

**Qué hace:** Convierte cualquier combinación de inclinación/declinación de origen hacia una dirección objetivo arbitraria (generaliza RTP y RTE como casos particulares).

**Aplicación:** Casos con magnetización remanente conocida o distinta a la del campo inductor actual, o cuando se requiere una dirección de referencia distinta al polo/ecuador para comparar con otros levantamientos.

---

## 3. Gravimetría — Realces

Las derivadas y realces siguen la misma lógica que en magnetometría, aplicadas al campo gravimétrico g:

| # | Filtro | Fórmula | Qué resalta |
|---|--------|---------|-------------|
| 1 | DX | gx = ∂g/∂x | Cambio lateral Este |
| 2 | DY | gy = ∂g/∂y | Cambio lateral Norte |
| 3 | DZ | gz = ∂g/∂z | Fuentes someras/bordes |
| 4 | DZ2 | ∂²g/∂z² | Anomalías pequeñas, alta resolución |
| 5 | Continuación ascendente | altura configurable | Tendencias regionales/profundas |
| 6 | Regional gaussiano | paso bajo | Componente regional suave |
| 7 | Residual | g_res = g − g_UC(h) | Componente local/somera |
| 8 | THDR | √(gx² + gy²) | Bordes de densidad, sin dependencia direccional |
| 9 | Tilt | tan⁻¹(gz/THDR) | Bordes normalizados por amplitud |
| 10 | TGA | √(gx² + gy² + gz²) | Magnitud total del gradiente de gravedad |

**Aplicación general:** Igual lógica que en magnetometría pero para contraste de densidad — delimitación de cuerpos densos/menos densos, contactos litológicos, estructuras, y selección de blancos donde la densidad es el proxy relevante (p. ej. cuerpos masivos de sulfuros, intrusivos vs. caja).

---

## 4. Gravimetría — Cadena de corrección (TerraWorkbench v0.11.0)

**Estado real:** implementado como 10 algoritmos nuevos y separados (más la placa de Bouguer original = 11 en total para esta cadena). Las convenciones de placa siguen la formulación de Harmonica (`harmonica.bouguer_correction`), y la secuencia de Bouguer completa sigue **SBA + terreno − curvatura**, consistente con la reducción descrita en USGS Professional Paper 646-A. Cada algoritmo indica explícitamente si produce una **corrección** (mGal a sumar/restar) o una **anomalía** (resultado acumulado) — evita el problema de "nombre correcto, resultado ambiguo".

> **Diferencia respecto a la versión anterior de este documento:** la fórmula de Bouguer completa NO es `SBA + terreno` a secas — hay que **restar la curvatura**: `CBA = SBA + terreno − curvatura`. Corregido abajo en §4.9. También la isostasia dejó de ser una sola herramienta "corrección y anomalía"; se implementó como **dos algoritmos separados**: profundidad de Moho (§4.10) y anomalía residual isostática (§4.11). Y la corrección de latitud se documenta junto con el concepto de *gravity disturbance*, que es una cantidad distinta de la anomalía clásica (§4.3).

### 4.1 Corrección de placa de Bouguer (base original, v anterior)
**Fórmula (aproximación de placa infinita):** ΔgB = 2πGρh

**Parámetros configurables:** densidad de corteza (por defecto 2670 kg/m³), densidad del agua (por defecto 1040 kg/m³), alturas geométricas en metros, salida en mGal.

**Estado:** es la base sobre la que se construyó toda la cadena; no se renombró ni se rompió al agregar los 10 algoritmos nuevos.

---

### 4.2 Gravedad normal GRS80
**Fórmula (Somigliana, elipsoide GRS80/WGS84):**
γ(φ) = γₑ · (1 + k·sin²φ) / √(1 − e²·sin²φ)

con γₑ = 978032.67715 mGal, k = 0.001931851353, e² = 0.00669438002290.

**Forma serie equivalente (fórmula internacional de gravedad 1980):**
γ(φ) = 978032.67715·(1 + 0.0052790414·sin²φ + 0.0000232718·sin⁴φ + 0.0000001262·sin⁶φ + 0.0000000007·sin⁸φ) mGal

**Qué hace:** Calcula la gravedad teórica del elipsoide de referencia en función de la latitud (φ). Es el insumo (γ) para todas las correcciones/anomalías siguientes.

**Aplicación:** Primer paso obligatorio de cualquier cadena de reducción gravimétrica — sin γ(φ) toda anomalía posterior queda contaminada por la tendencia latitudinal regional (~0.8 mGal/km N-S).

---

### 4.3 Corrección de latitud / gravity disturbance
**Fórmula:** δg = g_obs − γ(φ)

**Qué hace:** Remueve la tendencia latitudinal regular comparando la gravedad observada con la gravedad normal **en el mismo punto** (sin reducción de altura). Esto es conceptualmente la *gravity disturbance* en el sentido clásico de geodesia física (Hofmann-Wellenhof & Moritz): distinta de una "anomalía" propiamente dicha, que compara g_obs con γ evaluada en el teluroide (a la altura normal, vía reducción de aire libre). TerraWorkbench expone ambas nociones por separado para no mezclar terminología.

**Aplicación:** Insumo directo para la corrección de aire libre y, en general, cualquier reducción posterior.

---

### 4.4 Corrección de aire libre
**Fórmula implementada (aproximación lineal, configurable):** Δg_FA = 0.3086 · h (mGal; h en metros)

**Fórmula extendida (dependiente de latitud + término cuadrático — documentada pero NO implementada como opción independiente):**
Δg_FA = (0.3087691 − 0.0004398·sin²φ)·h − 7.2125×10⁻⁸·h²

**Qué hace:** Corrige el decaimiento de la gravedad con la altura (1/r²), sin remover masa alguna — solo compensa la distancia al centro de la Tierra. Es una corrección pura (mGal), no una anomalía todavía.

**Nota de implementación (v0.11.1):** Actualmente TerraWorkbench solo ofrece la aproximación lineal (con el coeficiente configurable, no fijo). La forma extendida con dependencia latitudinal y término cuadrático está documentada aquí como referencia pero todavía no existe como algoritmo separado — es la única fórmula de toda la revisión de este documento que aún no tiene equivalente en el código.

---

### 4.5 Anomalía de aire libre (FAA)
**Fórmula:** FAA = g_obs − γ(φ) + Δg_FA

**Qué hace:** Primera anomalía de la cadena — combina la gravity disturbance (§4.3) con la corrección de aire libre (§4.4). Implementada como algoritmo separado de la corrección de aire libre (a diferencia de la versión anterior de este documento, que las trataba como un solo paso).

**Aplicación:** Útil de forma independiente para estudios regionales/isostáticos donde no se quiere remover aún el efecto de la masa topográfica.

---

### 4.6 Curvatura terrestre (Bullard B)
**Qué hace:** Ajusta la aproximación de placa infinita/plana por la curvatura real de la Tierra en el cálculo de la masa entre la estación y el datum, relevante a radios grandes (~decenas de km). Es el término clásico "Bullard B" (Bullard A = placa de Bouguer, Bullard B = curvatura, Bullard C = terreno).

**Aplicación:** Se **resta** en la secuencia de Bouguer completa (§4.9) — no se suma como se documentó antes. Su efecto es pequeño a escala de yacimiento pero significativo en estudios crustales/regionales.

---

### 4.7 Anomalía de Bouguer simple (SBA)
**Fórmula:** SBA = FAA − ΔgB = g_obs − γ(φ) + Δg_FA − 2πGρh

**Qué hace:** Remueve el efecto de altura (aire libre) y el de la masa topográfica aproximada por placa infinita, con la densidad de reducción configurada.

**Aplicación:** Primera anomalía "interpretable" en términos de contraste de densidad, aunque todavía contaminada por el relieve real (valles/cerros no capturados por la placa infinita).

---

### 4.8 Corrección de terreno mediante prismas DEM
**Fórmula (método de Nagy):** δg_terreno = Gρ · Σᵢ [efecto_prisma(xᵢ, yᵢ, zᵢ, estación)] — fórmula cerrada de Nagy (1966) para el potencial de un prisma rectangular, evaluada sobre la grilla del DEM (esquema tipo Hammer por zonas o directo sobre la grilla).

**Qué hace:** Corrige el exceso/déficit de masa real que la placa infinita no representa — cerros cercanos que faltan por remover, valles que la placa "rellena" incorrectamente. Siempre suma (positiva por construcción).

**Aplicación:** Imprescindible en terreno montañoso (Andes). Sin ella, SBA puede tener errores de varios mGal cerca de relieve abrupto.

**Nota de implementación:** en v0.11.0 se agregaron límites de celdas para evitar congelamientos en terreno/isostasia (datasets grandes de DEM) y controles de alineación entre gravedad, elevación y terreno (evita mezclar rasters con distinta grilla/resolución/CRS sin advertencia).

---

### 4.9 Anomalía de Bouguer completa (CBA)
**Fórmula (corregida — secuencia Harmonica/USGS PP 646-A):**
CBA = SBA + δg_terreno − δg_curvatura

**Qué hace:** Incorpora latitud, aire libre, placa de Bouguer, terreno y curvatura en un único resultado. Es el producto estándar de una reducción gravimétrica de exploración y el insumo típico para inversión.

**Aplicación:** Base para inversión gravimétrica (§7.1) y análisis de contraste de densidad en exploración mineral.

**Referencias:** [Harmonica — `bouguer_correction`](https://www.fatiando.org/harmonica/latest/api/generated/harmonica.bouguer_correction.html); USGS Professional Paper 646-A.

---

### 4.10 Profundidad de Moho Airy
**Fórmula (raíz de compensación, Airy-Heiskanen):**
r = [ρc / (ρm − ρc)] · h

donde ρc = densidad de la corteza, ρm = densidad del manto, h = elevación topográfica sobre el nivel de compensación de referencia (profundidad t configurable).

**Qué hace:** No es una corrección en mGal sino un **modelo de profundidad** (raster de la interfaz corteza-manto/Moho) bajo el supuesto de compensación local de Airy. Es el insumo geométrico para §4.11.

**Aplicación:** Visualización directa de la arquitectura cortical modelada; también diagnóstico de qué tan razonable es el modelo de compensación antes de calcular la anomalía residual.

---

### 4.11 Anomalía residual isostática Airy
**Fórmula:** Anomalía isostática residual = CBA − δg_isostática(Moho de §4.10)

**Qué hace:** Calcula el efecto gravitacional de la raíz cortical modelada en §4.10 (mismo esquema de prismas que la corrección de terreno, aplicado al contraste ρm−ρc en profundidad) y lo remueve de CBA.

**Aplicación:** Remueve la componente regional de largo periodo asociada a la compensación cortical, dejando una anomalía más "local" — útil en arquitectura cortical regional y para separar señal de cuenca/cinturón de la compensación isostática de fondo.

**Nota de implementación:** Modelo Airy local configurable (densidades y profundidad de compensación ajustables), presentado explícitamente como tal — no como "caja negra" — para no dejar ambigüedad sobre si se está usando Airy o Pratt.

> Con las 10 herramientas de §4.2–4.11 más la placa base (§4.1), la cadena de corrección gravimétrica queda completa: latitud/disturbance → aire libre (corrección + anomalía) → curvatura → Bouguer simple → terreno → Bouguer completa → Moho Airy → anomalía isostática residual. El vacío original identificado en la revisión previa queda cerrado en v0.11.0.

---

## 5. Filtros FFT compartidos (magnetometría y gravimetría)

Aplicables a ambos dominios; encadenables entre sí en un panel tipo *Filter Stack*.

### 5.1 Derivadas configurables
- Derivada Este, orden 1–5
- Derivada Norte, orden 1–5
- Derivada vertical, orden 1–5

**Qué hace:** Generaliza Dx/Dy/Dz/Dz2 a cualquier orden, permitiendo mayor resolución (órdenes altos) a costa de mayor sensibilidad al ruido.

### 5.2 Continuaciones
**Continuación ascendente configurable:** H(k) = e^(−kh)
**Continuación descendente estabilizada:** H(k) = min(e^(kh), G_max) · B_LP(k) — combina límite de ganancia con Butterworth paso bajo para evitar inestabilidad numérica.

**Qué hace:** La ascendente atenúa altas frecuencias (aleja la fuente); la descendente amplifica altas frecuencias (acerca la fuente) pero es inherentemente inestable sin estabilización — de ahí el límite de ganancia y el paso bajo combinados.

**Aplicación:** Ascendente para separación regional/residual; descendente para intentar recuperar resolución somera, con precaución sobre amplificación de ruido.

### 5.3 Gaussianos
- Gaussiano paso bajo
- Gaussiano paso alto

**Qué hace:** Suavizado/realce espectral con caída suave (sin oscilaciones de Gibbs), útil como alternativa más estable a los filtros ideales.

### 5.4 Butterworth
**Paso bajo:** B_LP(k) = 1/√(1+(k/kc)^2n)
**Paso alto:** B_HP(k) = 1/√(1+(kc/k)^2n)
**Paso banda:** B_BP = B_HP·B_LP
**Notch (rechazo de banda):** B_BR = 1 − B_BP

**Qué hace:** Filtros con corte configurable (kc) y orden (n) que controla la abruptez de la transición. El paso banda aísla un rango de longitudes de onda; el notch remueve una banda específica (útil para ruido periódico, p. ej. líneas de vuelo).

### 5.5 Filtros ideales y coseno
- Paso banda ideal / rechazo de banda ideal (corte abrupto, sin transición)
- Cosine roll-off paso bajo / paso alto (transición suave tipo coseno)

**Qué hace:** Los ideales dan control exacto de la banda pero generan artefactos (ringing); los cosine roll-off suavizan la transición para reducir esos artefactos.

### 5.6 Direccionales
- Coseno direccional — pass
- Coseno direccional — reject

**Qué hace:** Favorecen o eliminan estructuras según un azimut geológico específico en el dominio de frecuencia (análogo direccional a los filtros anteriores, pero orientado en vez de radial).

**Aplicación:** Aislar o remover tendencias estructurales conocidas (p. ej. remover el efecto de líneas de vuelo, o aislar un sistema de fallas de rumbo conocido).

### 5.7 Integraciones
- Integración horizontal Este: Hx = 1/(i·kx)
- Integración horizontal Norte: Hy = 1/(i·ky)
- Integración vertical: Hz = 1/k

**Qué hace:** Operación inversa a la derivada en frecuencia; recupera el campo "integrado" (útil para reconstruir el potencial a partir de un componente derivado, o para pasar de gradiente a campo total).

---

## 6. Preparación de levantamientos

### 6.1 Gridding de puntos a GeoTIFF
**Métodos:**
- IDW: Z(x) = Σwᵢ·Zᵢ / Σwᵢ, con wᵢ = 1/dᵢᵖ
- Vecino más cercano

**Parámetros:** tamaño de celda, radio de búsqueda, NoData configurables.

**Qué hace:** Interpola datos de línea de vuelo/estación a una malla regular como paso previo indispensable a cualquier filtro FFT.

### 6.2 Control de crossovers y nivelación traverse/tie
**Qué hace:**
- Interpola el valor en las intersecciones entre líneas
- Calcula residuales: rᵢⱼ = Tᵢ − Tⱼ
- Rechaza outliers mediante mediana y MAD
- Resuelve correcciones constantes por línea mediante mínimos cuadrados
- Reporta RMS antes y después

**Aplicación:** Control de calidad esencial antes de cualquier realce — un levantamiento mal nivelado genera artefactos de línea que se amplifican fuertemente en Dz, Dz2 y filtros paso alto.

### 6.3 Microleveling direccional
**Qué hace:** Separación espectral tipo Minty; aísla corrugaciones cortas transversales y largas en la dirección de vuelo. Entrega raster corregido y raster de corrección (diferencia) por separado.

**Aplicación:** Elimina el "efecto peine" de líneas de vuelo que sobrevive a la nivelación de crossovers, previo a derivadas de alto orden.

**Formatos de importación soportados por la GUI:** GeoTIFF, Geosoft GRD (si GDAL puede leerlo), GXF, AAIGrid/ASC, XYZ regular, CSV/ASCII, Esri FileGDB y GeoDatabase Geosoft de archivo único. En Windows, la GDB se lee con el runtime público BSD de GX Developer sin requerir Oasis montaj; `omscore.exe` queda solo como respaldo opcional.

---

## 7. Inversión 3D

### 7.1 Inversión gravimétrica
**Fórmula:** min_m ‖W_d(G_g·m − d_g)‖² + β·φ_m(m)

**Qué recupera:** Contraste de densidad (m) por celda, con límites de densidad configurables.

### 7.2 Inversión magnética escalar
**Fórmula:** min_χ ‖W_d(G_m·χ − d_m)‖² + β·φ_m(χ)

**Qué recupera:** Susceptibilidad (χ) por celda. Utiliza intensidad, inclinación y declinación del campo inductor.

### 7.3 MVI — Magnetic Vector Inversion
**Qué recupera:** Tres componentes de magnetización por celda: **m** = (mx, my, mz), permitiendo magnetización no paralela al campo inductor actual (relevante en presencia de remanencia significativa).

### 7.4 Inversión conjunta gravedad–magnetismo
**Fórmula:** Φ = Φ_g + Φ_m + β_g·R(ρ) + β_m·R(χ) + λ‖∇ρ × ∇χ‖²

**Qué hace:** Recupera simultáneamente densidad (ρ) y susceptibilidad (χ). El término cross-gradient (λ‖∇ρ×∇χ‖²) favorece que los límites estructurales coincidan entre ambos modelos, sin imponer una relación fija densidad–susceptibilidad.

**Aplicación:** Integración de evidencia gravimétrica y magnética cuando ambas responden a la misma geometría estructural pero con física distinta (p. ej. delimitar un intrusivo con expresión tanto densa como magnética).

### Capacidades comunes a las cuatro inversiones
- Malla: TensorMesh uniforme o TreeMesh/OcTree adaptativo
- Topografía y celdas activas
- Bounds (límites físicos por parámetro)
- Incertidumbre por observación
- Matriz de sensibilidad en disco (para datasets grandes)
- Salidas: VTK, NPZ, JSON, y CSV de observado/predicho/residual

---

## 8. Estado del módulo — resumen de cobertura

| Componente | Cobertura actual |
|---|---|
| Procesamiento magnético 2D y filtros espectrales | Alta — bien cubierto, ahora con dominio declarado por herramienta (§9) |
| Gravimetría: realces | Cubierto |
| Cadena de corrección gravimétrica (§4.1–4.11, 10 algoritmos) | Cubierto — latitud/disturbance, aire libre (corrección+anomalía), curvatura, Bouguer simple, terreno, Bouguer completa, Moho Airy, anomalía isostática residual |
| Preparación de levantamientos (gridding, crossovers, microleveling) | Cubierto |
| Inversión 3D (gravedad, magnética escalar, MVI, conjunta) | Cubierto, con soporte de malla adaptativa y topografía |
| Diferenciación espacial vs. FFT como parte visible del producto | **Nuevo en v0.12.0** — etiquetas de dominio en la UI (§9) + motor MAGMAP-like con acondicionamiento de bordes (§9.2) |

**Versión y validación actual (v0.14.0):** 79 algoritmos registrados, pruebas locales y Ruff correctos, y prueba integral validada en QGIS 3.44. El registro incluye herramientas radiométricas de grilla y una cadena para puntos crudos previa al gridding, además de la cobertura MAG/GRAV anterior.

**Resuelto en v0.11.1–v0.12.0 (ya no son limitaciones abiertas):**
- La continuación ascendente usa una altura configurable (§1.5) y su identidad no codifica una distancia fija.
- RTP/RTE/IGRF ya están agrupados y nombrados con claridad en la UI (§2).
- El selector de algoritmos que ocupaba toda la pantalla fue reemplazado por una ventana compacta a la izquierda del dock.
- El dominio numérico de cada herramienta (espacial/FFT/mixto/físico) ya no vive solo en este documento — es una etiqueta visible en la UI (§9).
- El motor espectral propio ya no es una FFT desnuda — incorpora detrend, padding reflejado y taper cosenoidal antes de filtrar (§9.2).

**Limitaciones abiertas:**
- **Corrección de aire libre extendida** (§4.4) — la forma dependiente de latitud + término cuadrático no existe como opción independiente; solo está implementada la aproximación lineal Δg_FA = 0.3086·h (con coeficiente configurable).
- **Combinación de operadores en una sola FFT** dentro del Filter Stack (H_final = H₁·H₂·H₃, al estilo MAGMAP) — no confirmado si ya está resuelto en v0.12.0; verificar contra `spectral.py` (ver nota en §9.2).
- **Operadores especializados de MAGMAP** aún ausentes: pseudogravedad, susceptibilidad/densidad aparente, filtro de Wiener, conversión entre componentes del campo, y otros (lista completa en §9.2).

**Nota sobre fórmulas:** Las de §4.2–4.11 siguen las convenciones estándar de geodesia física (Somigliana/GRS80, Nagy para prismas, Bullard A/B/C, Airy-Heiskanen), y la secuencia de Bouguer completa fue confirmada como `SBA + terreno − curvatura` (Harmonica + USGS PP 646-A). Para el resto de módulos, si el código usa una convención de signos, densidad de referencia o radio de terreno distinto, verificar contra el registro exacto antes de dar por definitiva la equivalencia fórmula-a-fórmula.

---

## 9. Apéndice — Dominio de cálculo por herramienta (espacial vs. FFT)

Distinción relevante frente a software como Oasis montaj: ahí "filtros normales" suelen ser operaciones espaciales sobre la grilla/canales, mientras que **MAGMAP** es un motor FFT 2D dedicado. Desde v0.12.0, TerraWorkbench **declara este dominio explícitamente en la propia UI** (etiqueta visible junto a cada algoritmo), no solo en este documento:

| Etiqueta en UI | Significado | Ejemplos |
|---|---|---|
| `[SPATIAL / FINITE DIFFERENCE]` | Operación entre celdas vecinas, sin pasar por frecuencia | DX, DY, THDR, gradiente horizontal direccional configurable |
| `[FFT / HARMONICA]` | Transformación espectral provista por Harmonica | DZ, DZ2, DX FFT, DY FFT, DZ FFT, continuación ascendente/descendente, RTP manual |
| `[FFT / MAGMAP-LIKE]` | Motor espectral propio con acondicionamiento geofísico (detrend/padding/taper — ver §9.2) | Butterworth, ideal, coseno, direccional, RTP/RTE/IGRF estabilizados, transformación general de dirección, integraciones X/Y/Z |
| `[MIXED GRID / FFT]` | Combina componentes espaciales y espectrales | Tilt, ASA, TDX, Theta, TGA |
| `[PHYSICAL CORRECTION / GRID]` | Corrección/anomalía física sobre la grilla, sin FFT | Bouguer (§4.1), aire libre, terreno, isostasia (§4) |

**Por qué DX/DY son espaciales y DZ es FFT:** Harmonica usa diferencias finitas por defecto para Dx/Dy porque reducen los efectos de borde respecto al cálculo espectral; Dz, en cambio, no tiene una definición de diferencias finitas consistente sobre una sola grilla 2D y se calcula necesariamente en número de onda. Ver `magnetic_filters.py` y `spectral_filters.py` en el repositorio.

### 9.1 Grupo FFT explícito
17 operadores FFT dedicados (14 de v0.11.1 + 3 nuevos en v0.12.0): Butterworth (low-pass, high-pass, band-pass, notch), ideal (band-pass, band-reject), cosine roll-off (low-pass, high-pass), coseno direccional (pass, reject), continuación descendente estabilizada, integración horizontal X, integración horizontal Y, integración vertical, **derivada Este FFT, derivada Norte FFT, derivada vertical FFT**. A esto se suman RTP, RTE y la transformación general de dirección, también FFT aunque agrupados visualmente dentro de magnetometría (§2).

### 9.2 Motor MAGMAP-like — pipeline real (v0.12.0)
Antes (v0.11.x) el Filter Stack ejecutaba cada filtro como transformación independiente sin acondicionamiento de bordes:

```
FFT → filtro 1 → inversa → GeoTIFF
FFT → filtro 2 → inversa → GeoTIFF
```

Desde v0.12.0, el motor `[FFT / MAGMAP-LIKE]` sigue el flujo:

```
Grilla
  → remoción de media o plano (detrend)
  → padding reflejado
  → taper cosenoidal en el margen
  → una FFT 2D
  → combinación de operadores
  → FFT inversa
  → recorte al tamaño original
  → restauración opcional de tendencia
```

Esto sigue la arquitectura general de MAGMAP (preprocesamiento → FFT → operadores → inversa → posprocesamiento) descrita por [Seequent — MAGMAP Filtering](https://help.seequent.com/Oasismontaj/2026.1/Content/gxhelp/m/geosoft_gx_fft2d_magmapfiltering.htm), identificada explícitamente como **"MAGMAP-like"** (no como copia exacta) — distinción honesta que evita sobre-vender equivalencia con el motor comercial de Seequent.

**Aún no cubierto — combinación H_final = H₁·H₂·H₃ en una sola FFT** para múltiples filtros encadenados en el Filter Stack (a la fecha de este registro no se confirma si v0.12.0 ya combina operadores dentro de una misma pasada o si el acondicionamiento MAGMAP-like se aplica por filtro individual dentro del stack — verificar contra `spectral.py` si esto es crítico para el flujo de trabajo).

**Operadores de MAGMAP que TerraWorkbench aún no tiene (confirmado explícitamente en el registro de v0.12.0):**
- Pseudogravedad
- Susceptibilidad aparente
- Densidad aparente
- Filtro de Wiener
- Conversión entre componentes del campo
- Otros operadores especializados (lista extendida de referencia, MAGMAP tiene 29 operadores en total): RTP diferencial, transformación desde el polo, Gravity Earth filter, filtro radial general definido por el usuario, variantes adicionales de ideal/notch, separaciones regional/residual adicionales, decorrugación MAGMAP completa.

**Conclusión (v0.12.0):** TerraWorkbench ahora declara el dominio numérico de cada herramienta como parte visible del producto (peso geofísico real, no solo un botón que finge equivalencia entre métodos distintos), y el motor espectral propio incorpora el acondicionamiento de bordes que le faltaba frente a MAGMAP. La brecha restante frente a MAGMAP es de **cobertura de operadores especializados** (pseudogravedad, susceptibilidad/densidad aparente, Wiener, conversión de componentes), no de arquitectura de dominio.

---

## 10. Referencias bibliográficas — papers originales y mejoras posteriores

Verificadas por búsqueda directa antes de citarlas (no recuperadas de memoria). Organizadas por sección del documento y separando, donde aplica, el **paper que introdujo el concepto** del **paper que lo mejoró/estabilizó** — que suele ser el que importa para entender por qué la implementación actual difiere de la formulación original.

### 10.1 Magnetometría — realces y derivadas (§1)

**Amplitud de señal analítica (AS/ASA, §1.10):**
- Origen: Nabighian, M.N. (1972). *The analytic signal of two-dimensional magnetic bodies with polygonal cross-section: its properties and use for automated anomaly interpretation.* Geophysics, 37(3), 507–517.
- Extensión al caso 3D (la forma √(Dx²+Dy²+Dz²) que usa TerraWorkbench): Roest, W.R., Verhoef, J. & Pilkington, M. (1992). *Magnetic interpretation using the 3-D analytic signal.* Geophysics, 57(1), 116–125.

**Tilt (§1.8) y TDX (§1.11):**
- Origen del tilt: Miller, H.G. & Singh, V. (1994). *Potential field tilt — a new concept for location of potential field sources.* Journal of Applied Geophysics, 32(2–3), 213–217.
- Mejora — horizontal tilt angle normalizado (TDX): Cooper, G.R.J. & Cowan, D.R. (2006). *The application of fractional calculus to potential field data.* Exploration Geophysics, 37(4), 352–357 (TDX descrito y difundido en esta línea de trabajo de Cooper & Cowan; ver también su síntesis en Cooper & Cowan, 2008, sobre filtros de fase normalizada).

**THDR — derivada horizontal total (§1.7) y HG azimutal (§1.9):**
- Origen del método de gradiente horizontal: Cordell, L. & Grauch, V.J.S. (1985). *Mapping basement magnetization zones from aeromagnetic data in the San Juan Basin, New Mexico.* En Hinze, W.J. (ed.), *The Utility of Regional Gravity and Magnetic Anomaly Maps*, SEG, 181–197 (basado en el planteamiento previo de Cordell, L., 1979, sobre gradiente horizontal de gravedad).
- Mejora — automatización de la localización de máximos de cresta: Blakely, R.J. & Simpson, R.W. (1986). *Approximating edges of source bodies from magnetic or gravity anomalies.* Geophysics, 51(7), 1494–1498.

**Theta Map (§1.12):**
- Origen: Wijns, C., Perez, C. & Kowalczyk, P. (2005). *Theta map: Edge detection in magnetic data.* Geophysics, 70(4), L39–L43.

### 10.2 Magnetometría — dirección del campo magnético (§2)

**RTP — reducción al polo (§2.1–2.2):**
- Origen: Baranov, V. (1957). *A new method for interpretation of aeromagnetic maps: pseudo-gravimetric anomalies.* Geophysics, 22(2), 359–383; extendido en Baranov, V. & Naudy, H. (1964). *Numerical calculation of the formula of reduction to the magnetic pole.* Geophysics, 29(1), 67–79.
- Mejora — formulación práctica en dominio de Fourier (la base de cómo se calcula RTP con FFT hoy): Bhattacharyya, B.K. (1965). *Two-dimensional harmonic analysis as a tool for magnetic interpretation.* Geophysics, 30(5), 829–857.
- Mejora — estabilización en bajas latitudes (relevante para Perú/Sudamérica, y para el límite de ganancia espectral que usa la RTP automática de TerraWorkbench, §2.2): Hansen, R.O. & Pawlowski, R.S. (1989). *Reduction to the pole at low latitude by Wiener filtering.* Geophysics, 54(12), 1607–1613.

**RTE — reducción al ecuador (§2.3):** no tiene un paper fundacional propio independiente de RTP; se deriva del mismo marco de Baranov (1957)/Bhattacharyya (1965) fijando el objetivo a I=0° en vez de I=90°, práctica consolidada en la literatura de bajas latitudes geomagnéticas citada arriba.

### 10.3 Gravimetría — cadena de corrección (§4)

**Gravedad normal / GRS80 (§4.2):**
- Origen teórico del elipsoide equipotencial: Pizzetti, P. (1894), formalizado por Somigliana, C. (1929) — la fórmula que TerraWorkbench implementa lleva su nombre por esto.
- Adopción como estándar geodésico (GRS80): Moritz, H. (1980). *Geodetic Reference System 1980.* Bulletin Géodésique, 54, 395–405 (reimpreso con corrigenda, Journal of Geodesy, 74, 2000).

**Corrección de terreno por prismas DEM (§4.8):**
- Origen: Nagy, D. (1966). *The gravitational attraction of a right rectangular prism.* Geophysics, 31(2), 362–371.
- Mejora — forma numéricamente estable, evita singularidades en bordes/vértices: Nagy, D., Papp, G. & Benedek, J. (2000). *The gravitational potential and its derivatives for the prism.* Journal of Geodesy, 74(7–8), 552–560; corregido en Nagy, D., Papp, G. & Benedek, J. (2002). *Corrections to "The gravitational potential and its derivatives for the prism".* Journal of Geodesy, 76(8), 475.

**Curvatura terrestre / Bullard B (§4.6):**
- Origen: Bullard, E.C. (1936). *Gravity measurements in East Africa.* Philosophical Transactions of the Royal Society of London A, 235, 486–532.
- Mejora — solución cerrada más precisa/eficiente: LaFehr, T.R. (1991). *Standardization in gravity reduction.* Geophysics, 56(8), 1170–1178 (con discusión y solución exacta adicional en Whitman, W.W., 1991, y en el intercambio Hensel–LaFehr, Geophysics 57(8), 1992).

**Isostasia Airy (§4.10–4.11):**
- Origen: Airy, G.B. (1855). *On the computation of the effect of the attraction of mountain-masses.* Philosophical Transactions of the Royal Society of London, 145, 101–104.
- Formalización geodésica del modelo Airy–Heiskanen que usan las implementaciones modernas: Heiskanen, W.A. & Vening Meinesz, F.A. (1958). *The Earth and Its Gravity Field.* McGraw-Hill; consolidado en Heiskanen, W.A. & Moritz, H. (1967). *Physical Geodesy.* W.H. Freeman.

**Secuencia CBA = SBA + terreno − curvatura (§4.9):** ya citada en el propio §4.9 (Harmonica `bouguer_correction`; USGS Professional Paper 646-A); la convención Bullard A/B/C que estructura toda la cadena viene de Bullard (1936), arriba.

### 10.4 Filtros FFT compartidos (§5)

**Butterworth (§5.4):**
- Origen (fuera de geofísica — filtro eléctrico adaptado luego al procesamiento de campos potenciales): Butterworth, S. (1930). *On the theory of filter amplifiers.* Experimental Wireless & the Wireless Engineer, 7, 536–541.

**Ideal, coseno, direccionales, integraciones (§5.5–5.7):** son operadores estándar de filtrado en dominio de número de onda sin un paper fundacional único; su tratamiento sistemático para campos potenciales sigue el marco expuesto en Gunn, P.J. (1975). *Linear transformations of gravity and magnetic fields.* Geophysical Prospecting, 23(2), 300–312, y en los textos de referencia de Blakely, R.J. (1995). *Potential Theory in Gravity and Magnetic Applications.* Cambridge University Press.

### 10.5 Preparación de levantamientos (§6)

**IDW (§6.1):**
- Origen: Shepard, D. (1968). *A two-dimensional interpolation function for irregularly-spaced data.* Proceedings of the 1968 23rd ACM National Conference, 517–524.

**Microleveling direccional (§6.3):**
- Origen: Minty, B.R.S. (1991). *Simple micro-levelling for aeromagnetic data.* Exploration Geophysics, 22(4), 591–592.
- Mejora — variantes estadísticas/robustas posteriores: Mauring, E., Beard, L.P., Kihle, O. & Smethurst, M.A. (2002). *A comparison of aeromagnetic levelling techniques with an introduction to median levelling.* Geophysical Prospecting, 50(1), 43–54.

### 10.6 Inversión 3D (§7)

**Inversión gravimétrica y magnética con depth weighting (§7.1–7.2):**
- Magnética: Li, Y. & Oldenburg, D.W. (1996). *3-D inversion of magnetic data.* Geophysics, 61(2), 394–408.
- Gravimétrica: Li, Y. & Oldenburg, D.W. (1998). *3-D inversion of gravity data.* Geophysics, 63(1), 109–119.
(Ambos introducen la función de depth weighting Wz que compensa la caída de sensibilidad con la profundidad; es el estándar de facto que TerraWorkbench sigue en su malla adaptativa.)

**MVI — Magnetic Vector Inversion (§7.3):**
- Antecedente directo: Kubota, R. & Uchiyama, A. (2005). *Three-dimensional magnetization vector inversion of a seamount.* Earth, Planets and Space, 57, 691–699.
- Formulación comprehensiva (cartesiana/esférica): Lelièvre, P.G. & Oldenburg, D.W. (2009). *A 3D total magnetization inversion applicable when significant, complicated remanence is present.* Geophysics, 74(3), L21–L30.
- Paper canónico de referencia para MVI tal como se usa comercialmente hoy: Ellis, R.G., de Wet, B. & Macleod, I.N. (2012). *Inversion of magnetic data for remanent and induced sources.* ASEG Extended Abstracts 2012, 1–4.

**Inversión conjunta gravedad–magnetismo con cross-gradient (§7.4):**
- Origen del concepto cross-gradient (aplicado originalmente a resistividad DC + sísmica, no a gravedad/magnetismo): Gallardo, L.A. & Meju, M.A. (2003). *Characterization of heterogeneous near-surface materials by joint 2D inversion of dc resistivity and seismic data.* Geophysical Research Letters, 30(13), 1658; extendido en Gallardo, L.A. & Meju, M.A. (2004). *Joint two-dimensional DC resistivity and seismic travel time inversion with cross-gradients constraints.* Journal of Geophysical Research, 109(B3), B03311.
- Extensión específica a gravedad + magnetismo en 3D (la que corresponde directamente a §7.4): Fregoso, E. & Gallardo, L.A. (2009). *Cross-gradients joint 3D inversion with applications to gravity and magnetic data.* Geophysics, 74(4), L31–L42.

### 10.7 Nota sobre cobertura de esta bibliografía

Esta lista cubre los conceptos con fórmula explícita en el documento (§1–§7). No incluye MAGMAP en sí (Seequent/Geosoft, software comercial, ya referenciado en §9.2 con su propio enlace) ni papers de implementación numérica interna de TerraWorkbench (no publicados). Si algún algoritmo del §5 (Gaussianos, coseno direccional) requiere cita más específica que la que dan Gunn (1975)/Blakely (1995), verificar contra la literatura de procesamiento de señales aplicada — no se encontró un paper fundacional único y verificable para esas variantes puntuales, y se prefirió señalarlo aquí en vez de inventar una atribución.

---

## 11. Repositorios y librerías abiertas de referencia

Enlaces verificados (no de memoria). Pensados como lectura complementaria a §10 al portar cada algoritmo al plugin de QGIS — la mayoría tiene código fuente legible directamente, útil para verificar signos, convenciones de ejes y casos borde antes de implementar.

### 11.1 Librerías Python — implementación de referencia (código + docs)

- **Harmonica** — https://www.fatiando.org/harmonica/latest/ — derivadas, RTP, continuación ascendente/descendente, Bouguer, prisma de Nagy. Ya citada en §4 y §9; es la referencia más literal para verificar convenciones de signo, ya que varias fórmulas del documento se basan en ella directamente.
- **Verde** — https://www.fatiando.org/verde/latest/ — gridding e interpolación (IDW, splines biarmónicos) del ecosistema Fatiando a Terra, relevante para §6.1.
- **Boule** — https://www.fatiando.org/boule/latest/ — elipsoides de referencia (incluye GRS80/WGS84) y gravedad normal (Somigliana), relevante para §4.2.
- **SimPEG** — https://simpeg.xyz/ — inversión 3D de gravedad, magnética y MVI, con depth weighting y notebooks ejecutables. Cubre todo el §7.
- **PyGIMLi** — https://www.pygimli.org/ — inversión conjunta con cross-gradient, notebooks con el ejemplo de Li & Oldenburg (1996) ya referenciado en §10.6.
- **PyGMI** — https://github.com/Patrick-Cole/pygmi — GUI abierta orientada específicamente a grillas de magnetometría/gravimetría (RTP, tilt, THDR, continuación, microleveling). Es el más cercano en alcance y espíritu a TerraWorkbench; útil como referencia de decisiones de diseño de UI y de algoritmos, no solo de fórmulas.
- **PyGMT** — https://www.pygmt.org/latest/ — filtros FFT (Butterworth, continuación, direccionales) sobre el motor de GMT, con ejemplos ya graficados.
- **GMG** — https://github.com/btozer/gmg — modelado 2D de perfiles gravimétricos/magnéticos, inspirado en Fatiando a Terra y GMT.

### 11.2 Enciclopedias y referencia teórica

- **SEG Wiki** — https://wiki.seg.org/ — entradas tipo enciclopedia para RTP, tilt, analytic signal y filtros de borde en general, con derivación y referencias cruzadas a los papers originales.
- **USGS Potential-Field Geophysical Software** — buscar en https://pubs.usgs.gov/ como "USGS potential-field software" — código y documentación históricos de Phillips, Blakely, Cordell y otros; en varios casos es literalmente donde se publicaron por primera vez las implementaciones de referencia de los filtros de §1.
- Blakely, R.J., *Potential Theory in Gravity and Magnetic Applications* (Cambridge University Press, 1995) — no es repositorio abierto, pero es el libro que casi todos los papers de §10.1 y §10.4 citan como fuente madre de las fórmulas; vale la pena tenerlo como referencia de cabecera.

### 11.3 Listas curadas del ecosistema (para rastrear herramientas nuevas)

- **awesome-open-geoscience** — https://github.com/softwareunderground/awesome-open-geoscience — mantenida por Software Underground; cubre desde Fatiando a Terra/SimPEG hasta datasets abiertos (ICGEM para modelos esféricos de gravedad, SEG Open Data Catalog).
- **awesome-geophysics** — https://github.com/aradfarahani/awesome-geophysics — orientada a libros de texto y material educativo, incluye *Gravity and Magnetic Exploration* de Hinze, von Frese & Saad, citado indirectamente en varios papers de §10.3 y §10.6.
# 11. Radiometría gamma — K, eU y eTh

TerraWorkbench v0.14.0 incorpora radiometría como una familia separada de MAG y
GRAV. No es un filtro de campo potencial: mide la radiación gamma superficial y
sus productos dependen de la adquisición, el sistema detector y el equilibrio de
las series de decaimiento.

Los productos sobre grillas calibradas incluyen razones configurables, ternario
K-rojo/eTh-verde/eU-azul, ternario normalizado, dosis terrestre, parámetro
interpretativo `F = K·eU/eTh` y reporte JSON de calidad. K se expresa normalmente
en porcentaje; eU y eTh, en ppm equivalentes. Las divisiones enmascaran
denominadores pequeños y todas las entradas deben compartir exactamente SRC,
extensión y malla.

Para conteos crudos se ofrecen corrección no paralizable por tiempo muerto,
sustracción explícita de fondos de aeronave/cósmico/radón, normalización
exponencial por altura, calibración por sensibilidad y stripping mediante una
matriz de respuesta 3×3. Los coeficientes deben proceder del informe del sistema
y del levantamiento. No deben aplicarse nuevamente a productos publicados que ya
fueron corregidos. La humedad, cobertura vegetal, geometría, altura, radón y
desequilibrio secular limitan la interpretación geológica.

Lecturas confiables: [IAEA, Guidelines for radioelement mapping](https://www-pub.iaea.org/MTCD/publications/PDF/te_1363_web/PDF/Contents.pdf)
y [Geoscience Australia, Radiometrics](https://www.ga.gov.au/scientific-topics/disciplines/geophysics/radiometrics).
