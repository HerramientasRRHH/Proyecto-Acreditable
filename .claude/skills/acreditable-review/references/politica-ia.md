# Política de IA — cuándo hace falta la key de MiniMax

> Parte del skill `acreditable-review`. **Ésta es la fuente de verdad de "¿acá hay que llamar a la
> IA o no?"**. Antes de agregar, mover o sacar cualquier llamada a `va_iaLeerImagen`, leer las 4
> reglas y actualizar la tabla de abajo. Última revisión: 23-08-2026.

## Las 4 reglas

### 1. Primero gratis, siempre. La IA es el último escalón, nunca el primero

El orden de escalones es siempre el mismo: **texto nativo del PDF → OCR (Tesseract) → regex /
checksum → match por nombre contra la nómina → IA**. Cada escalón es varios órdenes de magnitud más
barato que el siguiente.

Esto no es teórico: en la auditoría del 22-08-2026, el escalón por NOMBRE (gratis, un regex sobre
el encabezado "Sr(a):") resolvió **9 de los 11** casos de `SIN_LIQUIDACION`. Solo 2 llegaron a IA.
Antes de escribir una llamada a IA nueva, preguntá si un escalón gratis ya la haría innecesaria —
y medilo contra documentos reales, no lo supongas.

Ver también, en las bitácoras: "Documentos con casillas de RUT manuscritas: mirá el nombre antes de
gastar IA" y "Jubilados de Antofagasta = mismo formulario que Exención de Lo Barnechea".

### 2. Recorte, no página entera

Si se sabe qué zona de la página importa (la franja de firma, el encabezado con nombre y RUT, la
casilla de fechas), se manda **esa zona recortada**. Es más barato, más rápido y —lo importante—
**más preciso**: la IA no tiene que buscar dónde mirar.

Medido el 22-08-2026 con recortes reales de la zona de firma (franja de 6% del alto): **8 de 8
respuestas correctas**, incluidos 4 casos límite que la medición de tinta no podía separar sola.

**Dos correcciones del 23-08-2026, las dos por el recorte y no por el prompt:**

- **Un recorte que no contiene el dato produce un "no lo veo" que parece un fallo de la IA.** El
  recorte del 22% superior para atribución no llegaba a la línea `Sr(a):` (que cae entre 19.1% y
  23.9% del alto según la página). La IA devolvía `null` correctamente. Antes de tocar un prompt,
  **renderizá el recorte exacto que produce el código y miralo**: si vos no ves el dato, la IA
  tampoco.
- **Para leer un número chico, más resolución gana a más contexto.** Mismo prompt, mismas páginas:
  recorte ancho a escala 1.5 → 3/4; recorte chico a escala 3.0 → 4/4. Vale la pena re-renderizar la
  página a mayor escala para el recorte en vez de reusar el canvas que ya se tiene.

### 3. El gate depende de EN QUÉ DIRECCIÓN falla el escalón gratis

Ésta es la regla que faltaba y la que causó el bug de la corrida del 22-08-2026.

- Si el escalón gratis **solo puede fallar por defecto** (no encuentra nada, devuelve null), alcanza
  con un gate `if(!resultado)`. La IA solo rescata falsos negativos. Así funcionan Exención,
  Jubilados, Libro de Asistencia, Contratos.
- Si el escalón gratis **también puede fallar por exceso** (dice "sí" cuando la respuesta es "no"),
  un gate `if(!resultado)` **no toca nunca el error** — y el falso positivo es invisible para
  siempre. Ahí el gate tiene que incluir la **banda ambigua** del indicador, y la IA tiene que
  poder responder **que no**, sobrescribiendo el resultado gratis.

  Caso real: la firma física de la liquidación se decidía midiendo densidad de tinta. Con un gate de
  "solo si no detecté firma", la IA jamás se enteraba de los 326 de 330 trabajadores marcados
  "firmada" por error. La medición tenía que llamar a la IA justamente cuando *creía* haber
  encontrado algo pero el valor caía cerca del umbral.

**Cómo aplicarla en la práctica**: calibrá el indicador contra casos reales con verdad de terreno,
mirá la separación entre las dos poblaciones, y definí tres tramos — claramente no / **ambiguo** /
claramente sí. El tramo ambiguo es el gate de la IA. Si no podés medir la separación, no tenés
derecho a un umbral: mandá todo el tramo dudoso a IA.

### 3.b La IA tampoco es infalible: aceptala solo si confirma un valor ya conocido

Cuando la IA se usa para desempatar entre dos lecturas (OCR vs referencia), puede traer un **tercer
valor distinto** y ninguno de los tres ser el correcto. Caso real (San Martin Vega): OCR 22, IA 26,
LH 29 — el papel dice 29. Aceptar la respuesta a ciegas cambia un falso positivo por otro, ahora con
sello de "verificado con IA", que es peor porque frena la revisión manual.

Regla: **la IA se acepta solo si confirma uno de los dos valores que ya se tienen.** Si trae un
tercero, el resultado es `ilegible — revisar a mano`. Aplica a `Días y Montos`; el mismo criterio
debería usarse en cualquier desempate futuro.

### 4. Todo llamado se loguea en `va_iaAuditLog` Y se conecta a la hoja de Excel de su módulo

Las dos cosas, no una. `va_iaAuditLog.push({modulo, pagina, tipo, nombreLeido, resultado,
atribuidoA, motivo})` y después `va_iaAuditRowsExcel('<mismo modulo>')` agregado a la hoja del
módulo en `va_exportExcel`. Si falta lo segundo, la lectura con IA queda registrada pero invisible
en todos lados (los paneles ya no muestran el detalle — decisión explícita del usuario, ver bitácora
de cruces-rendimiento).

Sin esto no se puede contestar la pregunta que el usuario hace siempre: *"¿qué leyó la IA y por qué
decidió eso?"*.

---

## Dónde se llama hoy a la IA

Endpoint MiniMax configurado en el panel `⚙ Configuración del motor IA` (`#iav-key`). Los gates se
evalúan **por página**; ningún módulo llama a IA en el 100% de sus páginas por defecto.

| Módulo (`modulo` del log) | Función / línea aprox. | Gate | Qué se manda | Qué se pide |
|---|---|---|---|---|
| **Firma Liquidación** | `va_validarLiquidaciones` (bloque firma física) | tinta en banda ambigua (2.2%–3.3%) **o** etiqueta "FIRMA CONFORME" no anclable | **recorte** de la franja de firma | `{firmada, que_hay}` — puede corregir en las dos direcciones |
| **Atribución Liquidación** | `va_validarLiquidaciones` (cascada de RUT) | página que es liquidación y ningún escalón gratis identificó al trabajador | **recorte** del 35% superior | `{nombre_trabajador, rut_trabajador}` |
| **Días y Montos** | `va_validarLiquidaciones` | los días de la liquidación NO coinciden con el LH, o el monto del comprobante NO coincide con el líquido | **recorte** 18%-32% a escala 3.0 (días) / página del comprobante (monto) | `{dias_trabajados}` / `{monto}` — solo se acepta si confirma un valor ya conocido |
| Libro de Asistencia | `va_validarLiquidaciones` (página no clasificada) | página ambigua sin clasificar, o Libro sin nombre leído | página entera (scale 2.0) | tipo de página + nombre + faltas/permisos/licencias |
| Licencia Médica (inline) | idem, misma llamada | idem | página entera | nombre + fechas + días |
| Contrato (firma QR) | `va_validarLiquidaciones` | — | página entera | firmantes |
| Licencias Médicas | `va_validarLicenciasMedicas` (Fase 1) | sin RUT por OCR, checksum ni RUN recortado | página entera | nombre + fechas |
| Licencias Médicas (reintento) | `va_validarLicenciasMedicas` (Fase 3) | sin fecha válida ni siquiera tras reintentar el OCR a escala 4.0 | página entera | fechas |
| Exención Cotizar | `va_validarExenciones` | fallaron los niveles 1 / 1.5 / 1.75 | página entera | RUT / nombre |
| Contrato (Antofagasta) | `va_validarContratosAntofagasta` | sin firmante QR **y** (ninguna firma detectada **o** alguna de las dos partes en `banda_ambigua`/`sin_etiqueta`) | página entera | firmantes + `firma_trabajador`/`firma_empleador` |
| Discapacidad | `va_validarDiscapacidad` | sin RUT directo, sin RUT por checksum **y** sin match por nombre en la pagina | pagina entera (puede venir rotada) | `personas[{rut,nombre}]`, `tipo_documento`, `folio`, `porcentaje_discapacidad`, `grado` |
| Libro de Asistencia (Antofagasta) | `va_validarLibroAsist` | el OCR no identificó al trabajador (~80-85% de las páginas) | página entera | nombre |
| **Finiquitos (sello notaría)** | `va_validarFiniquitos` | página de finiquito **sin** texto de notaría legible **y con** tinta ≥5% en la zona del sello (banda ambigua — regla 3) | **recorte** del 30% inferior | `{notaria:bool, detalle}` — puede corregir en las dos direcciones |
| **Finiquitos (clasificación)** | `va_validarFiniquitos` | página con tinta que no se pudo clasificar ni con OCR ni rotada 90/270 | página entera | `{tipo, rut, detalle}` |

Topes de los módulos de Finiquitos: `IA_FINIQ_MAX_SELLO` (30) e `IA_FINIQ_MAX_CLASIF` (20).
Costo real medido sobre el `Finiquitos.pdf` de Antofagasta (23 págs, 11 trabajadores):
**1 sola llamada** — los otros 3 finiquitos notariados se resuelven gratis por texto y los 7 sin
notaría gratis por tinta. Detalle y calibración en `bitacora-finiquitos.md`.

Topes manuales opcionales (por defecto sin tope): `window.VA_IA_LIBRO_MAX`, `VA_IA_FIRMA_MAX`,
`VA_IA_ATRIB_MAX`, `VA_IA_MONTOS_MAX`.

## Costo real medido (Antofagasta, 411 páginas de liquidación en 21 archivos)

- Firma: ~20% de las páginas de liquidación (~80). Calibrado sobre la letra A: ~10% cae en la banda
  ambigua y ~10% no tiene etiqueta anclable. **Costo aceptado explícitamente por el usuario.**
- Atribución: un puñado por corrida (2 de 11 en la muestra auditada).
- Libro de Asistencia de Antofagasta es, de lejos, el módulo más caro (~80-85% de sus páginas, y son
  cientos). Cualquier cambio que suba ese porcentaje se nota de inmediato en el tiempo total: subirlo
  al 100% llevó una corrida real a más de 30 minutos y hubo que revertirlo.

## Antes de agregar una llamada a IA nueva — checklist

1. ¿Qué escalón gratis podría resolverlo? ¿Lo probaste contra documentos reales?
2. ¿Podés recortar la zona relevante en vez de mandar la página entera?
3. ¿En qué dirección falla el escalón gratis? (regla 3 — definí el tramo ambiguo con datos)
4. ¿Con qué frecuencia real se va a disparar el gate? Multiplicalo por el documento **más grande**
   que pase por ese código, no por el típico.
5. ¿Logueás en `va_iaAuditLog` y lo conectás a la hoja de Excel del módulo?
6. ¿El prompt le advierte del error más probable? (ej. "Fecha Otorgamiento no es fecha de inicio",
   "el RUT del Empleador no es el del trabajador", "la línea impresa no es una firma"). Y si el
   error es identificable con una regla determinística, **codificala en vez de confiar en el
   prompt** — pedirle a un LLM que no cometa un error baja la probabilidad, no la elimina (caso
   Rojas Flores, ver bitácora de licencias).
