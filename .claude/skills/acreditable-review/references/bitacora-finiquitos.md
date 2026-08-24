# Bitácora — Finiquitos (legalización notarial y respaldos alternativos)

> Parte del skill `acreditable-review`. Registro histórico de hallazgos REALES con su
> evidencia — se lee **solo cuando se está trabajando en este módulo**, no en cada sesión.
> El proceso de auditoría y la política de IA viven en `SKILL.md` y `politica-ia.md`.

## Cómo vienen los Finiquitos por base

| Base | Estructura | Respaldos del finiquito NO notariado |
|---|---|---|
| **Antofagasta** | `Finiquitos.pdf` único, 23 págs, **100% escaneado, cero texto nativo**. Bloque por trabajador: Finiquito → Declaración Jurada → Razón de Pago. Los trabajadores notariados **no traen respaldos** (el sello los reemplaza) | **Solo dos**: Declaración Jurada (pago/retención de pensiones alimenticias) y **Vale Vista, cuyo título impreso es "RAZÓN DE PAGO"** |
| **Lo Barnechea** | `3.3 Finiquitos de Trabajadores.pdf`, 12 págs, también escaneado. Bloque variable: Finiquito → DJ → Carta aviso DT → Carta empresa → Correo certificado / Renuncia DT / Razón de Pago | Los 6 tipos de `va_tipoComprobanteFiniquitoAlt` |

Antofagasta usa **firma física ante notario** (sello circular + timbre rectangular
"LEYÓ, FIRMÓ Y RATIFICÓ ANTE MÍ" de la 3ª Notaría de Antofagasta), no firma electrónica.

---

## 23-08-2026 — Los dos bugs de Finiquitos de Antofagasta

Reporte del usuario: *"los respaldos de los finiquitos no firmados sí están […] pero no los
está reconociendo nuestro motor de lectura"* y *"está marcando unos como legalizados que no
están"*. La corrida real que trajo (Excel exportado) decía: Total LH 11, Cubiertos 11,
**Legalizados 3**.

**Verdad de terreno** (las 23 páginas miradas una por una con el tool `Read`):
11 finiquitos, de los cuales **4 están notariados** (págs. 7, 14, 15, 23 — Bolívar, Dinamarca,
Estacio, Villca) y 7 no; 7 Declaraciones Juradas y 5 Razón de Pago.

### Bug 1 — el split por texto fusionaba trabajadores y la notaría "sangraba" al vecino

`va_validarFiniquitos` concatenaba el OCR de TODO el archivo y lo cortaba con
`txt.split(/Finiquito al contrato de trabajo/i)`. Sobre el archivo real, el OCR lee ese
encabezado como:

| Pág. | Lo que lee el OCR | ¿Matchea el split? |
|---|---|---|
| 1, 8, 11, 14, 15, 16, 19 | `Finiquito al contrato de trabajo` | sí |
| 4 | `Finiquito al con'rato de trabajo` | **no** |
| 7, 23 | `Finiquito al contreto de trabajo` | **no** |
| 21 | `Finiquito al cotrtrato de trabajo` | **no** |

Resultado medido: **8 bloques para 11 finiquitos**. El bloque 1 se comió a Alcalde Moreno +
Angulo Viveros + Bolívar, y como Bolívar SÍ está notariado, los tres quedaron marcados
`legalizado` → **2 falsos positivos**. El bloque 7 fusionó Torrejón + Villca + Sánchez y produjo
**3 falsos negativos** por el lado inverso.

**Lección general**: un `split()` sobre texto de OCR concatenado de todo un archivo no es una
segmentación, es una apuesta — y cuando falla no falla "un poco": fusiona registros y hace que
un atributo de UNO contamine a TODOS los del bloque. Segmentá **por página**, y evaluá cada
atributo (firma, sello, monto) sobre la página que lo contiene.

**Fix**: `va_finiqClasificarPagina(txt)` clasifica cada página por separado
(`FINIQUITO` / tipo de respaldo / `null`) y el sello se evalúa solo sobre la página del
finiquito. El encabezado ahora se matchea con `/FINIQUITO\s+AL\s+\S{0,15}\s*DE\s+TRABA[JI]O/i`
(tolera cualquier destrozo de la palabra "contrato", que es la única que el OCR rompe — la
palabra "Finiquito" y "de trabajo" salieron limpias en las 11 páginas), más dos anclas de
respaldo: `LÍQUIDO A PAGAR FINIQUITO`, o `FERIADO PROPORCIONAL` + `INDEMNIZACIÓN AVISO PREVIO`.

**Resultado**: 23/23 páginas clasificadas correctamente (validado en Python y después contra el
JS real en el navegador, mismo resultado).

### Bug 2 — los respaldos: uno faltaba en la lista y el otro venía rotado 90°

`va_tipoComprobanteFiniquitoAlt` reconocía 0 de 11 respaldos. Dos causas independientes:

1. **La Declaración Jurada ni siquiera estaba en la lista de tipos.** Se agregó
   (`/DECLARACI[OÓ]N\s+JURADA/i` — sale limpio en las 7 páginas reales).
2. **El Vale Vista de Antofagasta viene escaneado ROTADO 90°** y su título es
   `R A Z O N   D E   P A G O` con letra espaciada, que el OCR directamente se come. El OCR sin
   rotar escupe ~900 caracteres de basura (`"Z'IIHO MIONVINVS ODNVA"`), así que ni matcheaba
   `/VALE VISTA/` ni se disparaba el fallback de rotación de `va_getPdfTextOCR` — **ese fallback
   exige que el OCR haya devuelto menos de 40 caracteres**, y acá hay 900 de ruido.

   **Lección general y transferible**: un gate de "reintentá si el OCR no devolvió nada" NO
   detecta una página rotada. Una página rotada devuelve MUCHO texto, solo que todo inútil. El
   gate correcto es *"reintentá si no pude clasificar la página y la página tiene tinta"*.

   Rotando 90°, la misma página se lee perfecta: `DATOS BENEFICIARIO`, `DATOS TOMADOR`,
   `QUEDA DEPOSITADO EN ESTA OFICINA A NOMBRE DE ...`, y el RUT del trabajador. El título
   espaciado sigue sin leerse, así que las anclas útiles son las etiquetas, no el título.
   El regex del título igual se dejó tolerante a espacios entre letras
   (`/R\s*A\s*Z\s*[OÓ]\s*N\s+D\s*E\s+P\s*A\s*G\s*O/i`) para otras bases.

También se aflojó el regex de Correo certificado: pedía
`ENV[IÍ]OS\s+REGISTRAD…` pero el formulario real de Correos Chile de Lo Barnechea (pág. 6) se
lee `FORMULARIO ADMISION Envios REGISTRAL` — se corta antes. Ahora ancla hasta `ENVÍOS`.
Eso recupera un respaldo que también se perdía en Lo Barnechea.

### Cómo se detecta ahora el sello de notaría (3 escalones, regla 3 de politica-ia)

El escalón gratis acá puede fallar **en las dos direcciones**, así que el gate de IA no es
"si no encontré nada" sino la **banda ambigua** (ver `politica-ia.md`, regla 3):

1. **Texto de notaría legible** → legalizado, gratis. Anclas:
   `/NOTARIO\s+P[UÚ]BLIC/i`, `/\d\s*[ªº°*.,]?\s*NOTAR[IÍ]A\b/i` (el "3ª NOTARIA" del timbre
   redondo), `ESTE DOCUMENTO NO FUE REDACTADO`, `IMPRESIÓN PULGAR`, `ratificó … ante mí`,
   `LEYÓ FIRMÓ Y RATIFICÓ`.
   Medido: da positivo en **3 de las 4** páginas notariadas y en **0 de las 7** sin notaría.
   A propósito NO se incluyó `ANTOFAGASTA - CHILE` (que también está en el sello): es
   redundante con las dos anclas NOTARI* y abre superficie de falso positivo contra cualquier
   membrete de empresa de esa ciudad.
   Salvaguarda: si la página matchea `VA_CARTA_FINIQ_PENDIENTE_RE` ("no se han acercado a
   notaría a firmar"), nunca cuenta como legalizada — habla de la notaría justo para decir que
   NO fueron.
2. **Densidad de tinta en la zona del sello** (fracciones del canvas 0.28–0.75 x, 0.80–0.97 y;
   gris < 200, mismo umbral que la firma física de las liquidaciones). Medido sobre las 11
   páginas reales, **en el navegador con el canvas real**:

   | | rango |
   |---|---|
   | sin notaría (7 págs) | 1.40% – **1.76%** |
   | con notaría (4 págs) | **11.93%** – 17.27% |

   Umbral en **5%**: 2.8× de margen por abajo, 2.4× por arriba. Debajo del umbral →
   **no legalizado, gratis y con alta confianza**. Esta medición es de píxeles, así que
   transfiere directo del entorno de auditoría al navegador (los números de PyMuPDF/PIL y los
   del canvas coincidieron con <0.05 pp de diferencia).
3. **Banda ambigua (≥5% sin texto de notaría) → IA visual sobre el recorte** del 30% inferior
   de la página. Es el caso de la pág. 14, donde el sello está tapado por las firmas y el OCR
   solo rescata `"O FUE"` y `".TARIA"`.

**Costo real: 1 sola llamada a IA en las 23 páginas** (los otros 3 notariados se resuelven
gratis por texto, y los 7 sin notaría gratis por tinta).

**Si no hay key de IA**, la banda ambigua cae a `no legalizado` (fallar hacia el lado
conservador — el falso positivo era justamente el síntoma reportado) y la página se lista en
`sinVerificar` para revisión manual, en la app y en el Excel.

### El escalón de IA para páginas ilegibles

Página con tinta que no se pudo clasificar ni siquiera rotada → se manda entera a la IA
pidiendo `{tipo, rut, detalle}`. Caso real que lo justifica: **Lo Barnechea pág. 11** es una
Razón de Pago escaneada tan desvaída que ningún OCR devuelve **un solo caracter** — probado con
rotación 0/90/270 y con realce de contraste (autocontrast cutoff 1 y 5, y binarización a 215):
todos devuelven cadena vacía. La IA la lee sin problema y hasta saca el RUT correcto. Ese
respaldo se venía perdiendo silenciosamente desde siempre.

### Validación de los prompts

Los dos prompts **exactos que quedaron en el código** se probaron contra el endpoint real de
MiniMax con las imágenes reales: **9/9 correctos** — sello `true` en las 4 páginas notariadas,
`false` en 4 no notariadas (la IA menciona explícitamente que el timbre de Akro Diseños SpA es
de la empresa y no de una notaría), y `vale_vista` + RUT correcto en la pág. 11 de Lo Barnechea.

⚠ **Ojo con el campo `detalle`**: el booleano `notaria` fue correcto 8/8, pero el texto libre
del detalle **alucina** nombres y fechas (dijo "PABLO HURTADO PERALTA" y "GONZALO FUENTES
PERALTA" para el mismo notario que se llama Gonzalo Hurtado Peralta; fechas 2022/2025 donde el
papel dice 2026). El código solo consume el booleano; el detalle va al log de auditoría como
contexto y siempre prefijado con "confirmado por IA" — no usarlo nunca como dato duro.

### Hallazgo de documentación (no es un bug de código)

De los 7 finiquitos no notariados, **5 tienen los dos respaldos** (DJ + Razón de Pago) pero
**Sánchez Rojas Serafín (24.662.550-6) y Torrejón Campusano Felipe (18.219.333-k) tienen solo
la Declaración Jurada** — no hay Razón de Pago para ellos en el PDF. El criterio de aprobación
NO se cambió (sigue siendo "al menos un respaldo"), pero se agregó una lista aparte
`respaldoIncompleto` que lo muestra explícito en el panel y en el Excel, para que no quede
tapado bajo un ✅ genérico.

### Resultado final validado

Los 11 trabajadores, contra la verdad de terreno: **0 falsos positivos, 0 falsos negativos,
23/23 páginas clasificadas, 11/11 respaldos atribuidos** (antes: 3 legalizados de los cuales 2
mal, y 0 respaldos reconocidos).

**Nota de alcance**: validado hasta el nivel de "el JS da el mismo resultado que la validación
en Python contra el texto OCR real, y la medición de tinta coincide en el navegador". **No hubo
corrida completa de `va_ejecutar()` con los archivos reales** — en el sandbox el render de
pdf.js de estas páginas escaneadas no termina (limitación conocida del entorno, ver
`entorno.md`). Falta que el usuario corra y confirme los números.

### Otros arreglos de la misma sesión

- `va_ocrPaginaMejorRotacion` acepta ahora un 5º parámetro opcional `scorer` — el puntaje
  genérico (años + "Documento/Número/Nombre") no sirve para decidir la rotación de un
  comprobante bancario. Finiquitos pasa `va_finiqScoreRotacion`, que premia fuerte que la
  página quede CLASIFICADA.
- El render a escala 2.5 del loop es **perezoso**: una página de respaldo que ya se clasificó
  con su texto nativo (los PDFs digitales) no se renderiza nunca.
- La hoja `Finiquitos` del Excel traía solo 4 números y la lista de faltantes — imposible
  auditar POR QUÉ el motor marcaba a alguien como legalizado. Ahora baja el detalle completo
  por trabajador (página, respaldos detectados, evidencia del sello), el respaldo incompleto,
  las páginas sin verificar y el detalle de lectura con IA de los dos módulos nuevos.
