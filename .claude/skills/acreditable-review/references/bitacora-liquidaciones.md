# Bitácora — Liquidaciones (firma, atribución RUT/nombre, SIN_LIQUIDACION)

> Parte del skill `acreditable-review`. Registro histórico de hallazgos REALES con su
> evidencia — se lee **solo cuando se está trabajando en este módulo**, no en cada sesión.
> El proceso de auditoría y la política de IA viven en `SKILL.md`.
> Las secciones están en orden cronológico: si dos se contradicen, gana la más nueva
> (varias documentan código que después se revirtió y lo dicen explícitamente).

## va_findAllRuts puede perder el RUT real Y colar uno inventado en tablas densas de montos

Corriendo una revisión de prueba completa contra los 82 archivos reales de
Antofagasta (ver "Trampas encontradas..." abajo para el resto), el Libro de
Remuneraciones (`va_validarLibroRem`) daba solo 73.5% de cobertura contra la
nómina — mucho peor que Previred (100%) leído con la misma función. La causa:
el Patrón 1 de `va_findAllRuts` (RUT con puntos, sin ancla de inicio) es un
regex sin límite de arranque, y en una tabla con VARIAS columnas de montos
formateados con punto de miles justo antes de la columna RUT (ej.
`"22.459\n105.294\n28.740.905-2\nAndia"`), el motor puede empezar a
"leer RUT" a mitad de un monto vecino, produciendo un candidato falso — que
además a veces pasa el dígito verificador chileno por pura casualidad (~1/11
de las veces) y termina agregándose al set — y en el proceso consume los
caracteres donde arrancaba el RUT real, perdiéndolo por completo (no es un
falso negativo por OCR, es el propio regex "comiéndose" el match correcto).
`va_addRut()` ya valida DV antes de aceptar un candidato, pero eso solo
filtra los inventados que fallan el checksum — no rescata el RUT real que
quedó tapado.

Fix aplicado: anclar el inicio del Patrón 1 con `(?<![\d.,])` (no debe estar
precedido por dígito, punto o coma) para forzar que el match arranque en un
límite real de número, no a mitad de otro. Validado con los archivos reales:
Libro de Remuneraciones subió de 73.5% a 93.1% de cobertura; Previred y
F30-1 se mantuvieron exactamente igual (100% y 97.2%) — el fix solo saca
falsos positivos/negativos, no toca ningún match que ya era válido.

**Esto aplica a cualquier documento que junte una columna RUT con columnas de
montos en pesos chilenos (formato punto de miles) sin separador robusto entre
ellas** — no es exclusivo del Libro de Remuneraciones. Si un doc nuevo da una
cobertura sorprendentemente baja contra la nómina real (y no es por OCR malo:
`va_getPdfText` nativo, texto limpio), sospechá primero de este patrón antes
de asumir que faltan archivos o que el documento está incompleto — probá el
regex aislado contra un fragmento real con `re.finditer` y mirá los `span()`
de cada match, no solo el resultado final.

## "Sin liquidación en el PDF" puede ser 1 dígito mal leído, no un documento faltante

Siguiendo el hallazgo de arriba, 4 trabajadores de la corrida de prueba
salían como "sin liquidación detectada" en TODO el archivo. Antes de asumir
que la página no está, se buscó su APELLIDO (no el RUT) en los 25 archivos
completos — y en los 4 casos la página SÍ existe, está completa y legible,
pero el RUT específicamente salió mal por OCR:
`RUT: 12.214.857-k` (real: `12.214.867-k`, 1 dígito), o directo el label
"RUT:" se lee como basura y se pierde el primer dígito
(`'5.090.140-2` en vez de `25.090.140-2`). Como `va_addRut()` exige que el
dígito verificador calce, estos candidatos ni siquiera llegan a `pageRuts` —
y ya existía `va_matchRutCercano()` (Levenshtein distancia 1, exige que el
mejor candidato le gane por más de 1 al segundo) para rescatar justo este
caso, pero solo se aplicaba sobre `pageRuts` (que ya viene filtrado por
checksum) — nunca le llegaban estos candidatos porque el propio checksum
inválido los descartaba antes.

Fix: `va_findAllRutsRaw()` (mismos Patrones 1 y 2 de `va_findAllRuts`, SIN
`va_addRut`/validación de DV) como fuente adicional para
`va_matchRutCercano()` cuando ni el match exacto ni el "cercano" sobre
`pageRuts` encontraron a nadie. Validado contra los 4 casos reales, cruzando
contra la nómina COMPLETA (350 RUT reales, no una muestra) — los 4 resuelven
sin ambigüedad (la segunda mejor coincidencia siempre quedó a distancia ≥3).
Este patrón (RUT con 1 dígito mal leído, o roto/truncado por el label
"RUT:" mal reconocido) es específico de Liquidaciones porque ahí el RUT es
central para el tracking del trabajador de la página — en otros documentos
(Previred, F30-1, etc.) un RUT perdido por esto no rompe nada porque se
cruza el SET completo contra la nómina, no un RUT individual por página.

## Cuando "no coincide con nadie de la nómina" en realidad es ambigüedad, no ausencia

Caso real (Lo Barnechea): la IA leyó "Juan Bustos" en una foto del Libro y
el audit log dijo "no coincide con ningún trabajador de la nómina" — pero
"Bustos Proboste Juan Esteban" SÍ está en la nómina real. La causa: OTRO
trabajador real ("Naipil Burgos Juan Alex") tiene un apellido ("Burgos") a
distancia Levenshtein 2 de "Bustos" — dentro de la tolerancia difusa de
`token_match` para palabras >5 caracteres — así que los dos alcanzan
cobertura 1.0 contra "Juan Bustos" y `va_matchNombreNomina` rechaza por
AMBIGÜEDAD (correcto: mejor no adivinar mal a quién pertenece). El bug real
no era el matching — era que el mensaje de error no distinguía "nadie
coincide" de "2+ personas reales empatan" — al usuario/reviewer le parecía
que el sistema no encontraba a la persona, cuando en realidad SÍ la conocía,
solo que no podía decidir sola entre 2 candidatos reales.

Fix: `va_matchNombreNominaConMotivo()` (nueva, `va_matchNombreNomina` sigue
igual por compatibilidad) devuelve también POR QUÉ rechazó
(`sin_tokens`/`sin_cobertura`/`ambiguo`) y, si es ambiguo, los nombres de
los candidatos empatados — el audit log ahora se lo puede mostrar al humano
en vez de un genérico "no coincide con nadie". **Antes de asumir que un
"sin match" es un problema de LECTURA (IA/OCR leyó mal), revisá primero si
es un problema de DESAMBIGUACIÓN (leyó bien, pero hay 2+ personas reales
parecidas)** — son bugs completamente distintos con fixes distintos: el
primero necesita mejor OCR/IA, el segundo necesita mejor mensaje + revisión
humana (nunca "adivinar" automáticamente entre dos personas reales, el
costo de atribuir mal una liquidación/libro a la persona equivocada es
mucho peor que dejarlo sin resolver).

## Paralelizar OCR DENTRO de un mismo archivo (no solo entre archivos)

El patrón de paralelización anterior (pool de workers, uno por ARCHIVO
completo — ver sección de arriba) no sirve cuando la base sube un solo PDF
unificado (confirmado con el usuario: Lo Barnechea siempre sube así) — no
hay varios archivos entre los que repartir. `va_validarLiquidaciones()`
(index.html:11443+) se reestructuró en 3 pasadas para paralelizar el OCR
DENTRO de un mismo archivo, sin tocar la lógica de clasificación:

1. **Pasada 1 (secuencial, barata)**: recorre las páginas extrayendo texto
   nativo (`getTextContent`) y, si `textoUtil<40` (mismo umbral de
   siempre), renderiza y junta el blob — pero NO llama a `recognize()`
   todavía. Guarda todo en un caché por página (`cachePorPagina`, incluye
   `tcItems`/`imgCount`/`fnArrayLength` — los valores que la clasificación
   necesita más adelante y que NO dependen de si hubo OCR o no). Se procesa
   en lotes de 20 páginas (`LOTE_OCR`) para no acumular demasiados blobs en
   memoria a la vez, con `page.cleanup()` al final de cada página (mismo
   patrón que ya usa `iav_escanearGrande`, comentario "clave para no
   reventar la memoria con 30–50 MB").
2. **Pasada 2 (la única parte realmente paralela)**: los blobs juntados en
   cada lote se procesan con `va_procesarArchivosEnParalelo` (función
   GENÉRICA ya existente, index.html:2233 — no hace falta escribir un
   pool nuevo, acepta cualquier lista de items) contra `va_ocrPool`
   (hasta 4 workers, `Math.min(4,navigator.hardwareConcurrency||4)`, mismo
   criterio que Libro/Contratos). Los resultados van a un
   `Map(página→texto)`.
3. **Pasada 3 (secuencial, lógica ORIGINAL sin cambios)**: el loop de
   clasificación de siempre — `currentRut`, `enContratoHasta`, todos los
   detectores de tipo de documento, población de `va_liqMap` — copiado tal
   cual, con el único cambio de que `txt`/`textoUtil`/`imgCount`/`tcItems`
   salen del caché de la Pasada 1 (o de `ocrResultados` si esa página tuvo
   OCR) en vez de recalcularse inline.

**Por qué es más seguro que tocar la clasificación directamente**: el orden
y la lógica de `currentRut`/`enContratoHasta` (de los que depende TODA la
atribución RUT↔documento) no cambian en absoluto — se siguen calculando en
la Pasada 3, en el mismo orden de páginas de siempre. Lo único que cambia
es CUÁNDO y con cuántos workers se hace el trabajo caro (OCR), que es
independiente entre páginas por diseño (el texto OCR de la página P no
depende de la página P-1).

**Alcance deliberadamente acotado**: la función tiene 5 puntos distintos de
render+OCR/IA por página (el OCR principal recién descrito, la IA de
página ambigua, la firma física del Contrato, el thumbnail de firma, y una
"red de seguridad" de recuperación de RUT) — solo se paralelizó el
primero (el más frecuente, se dispara en casi todas las páginas
escaneadas de Antofagasta). Los otros 4 siguen usando el `ren_ocrWorker`
global, en fila, exactamente como antes. Paralelizar los 5 habría
requerido una reestructuración de 3-4 fases (uno de ellos,
`enContratoHasta`, depende de páginas ANTERIORES) — decisión explícita del
usuario de no encarar eso todavía, para no arriesgar la función más grande
y con más estado interno del proyecto de una sola vez.

**Validación en esta sesión**: se confirmó que la función sigue parseando
sin errores de sintaxis, que ninguna otra parte del archivo referencia
`tc`/`opList` fuera de la Pasada 1 (`grep` dedicado, encontró y corrigió
una referencia a `opList.fnArray.length` en `esFirmaBUKEstructural` que se
había pasado por alto al planificar — se agregó `fnArrayLength` al caché),
y que `va_procesarArchivosEnParalelo` reparte páginas sintéticas (33-47
items) entre 4 workers falsos sin duplicados ni saltos. **No se pudo medir
la mejora de velocidad real ni confirmar el resultado final contra un
archivo de Lo Barnechea real** — misma limitación de sandbox de siempre —
hace falta que el usuario lo corra y reporte.

## Se revirtió la paralelización de va_validarLiquidaciones — sospecha de degradación sistémica

Después del fix urgente de arriba (acotar el fallback de rotación), el
usuario reportó una SEGUNDA corrida real colgada — esta vez ~1 hora en
"validando licencias médicas", con Libro de Asistencia ni siquiera
cargado. Como Licencias no pasa por el código que se acababa de acotar,
esto apuntaba a algo más de fondo: la paralelización de
`va_validarLiquidaciones` (3 pasadas, pool de hasta 4 workers de
Tesseract) crea esos workers una sola vez y los deja VIVOS el resto de la
corrida (`va_ocrPool` es global, nunca se destruye) — compitiendo por CPU
con el worker único que usan los pasos siguientes (Finiquitos, Licencias),
aunque esos pasos no usen el pool directamente. Es una sospecha razonada,
no confirmada con medición real (mismo límite de sandbox de siempre), pero
con DOS corridas reales colgadas en el mismo día y sin forma de medir acá,
no correspondía seguir iterando a ciegas con el usuario esperando en
producción.

**Se revirtió por completo la paralelización de `va_validarLiquidaciones`**
(commit `ebf68eb`) — volvió a la versión secuencial original de un solo
worker, byte por byte (extraída de `git show ebf68eb^:index.html`, no
reescrita a mano, para no introducir una segunda diferencia sutil encima
del problema que se está revirtiendo). Quedan pendientes/sin tocar:
- La paralelización por ARCHIVO de Libro/Contratos de Antofagasta
  (`va_procesarArchivosEnParalelo`, commits `f5513c9`/`b5e809b`) — esa NO
  se tocó, es un patrón distinto (un worker por archivo completo, no un
  pool que quede compitiendo con el resto del pipeline de la misma
  manera) y no hay evidencia de que cause el mismo problema.
- Los fixes de lectura (Mujeres/Discapacidad/Jubilados, checksum y
  rotación acotada a 7 páginas) — no tocan rendimiento, se mantienen.

**Lección**: un pool de workers que se crea una vez y queda vivo para
"la próxima vez que haga falta" (optimización razonable en teoría) puede
degradar TODO lo que corre después en la misma sesión de navegador, no
solo el paso que lo creó — sobre todo si esos pasos siguientes ya estaban
diseñados para un solo worker. Antes de reintentar esta paralelización,
haría falta o (a) destruir/liberar el pool explícitamente al terminar
Liquidaciones, o (b) medirlo de verdad en un navegador real con datos
reales — ninguna de las dos se hizo la primera vez, y las dos corridas
reales colgadas de este mismo día son la evidencia de por qué hacía falta.

## Paralelización de Liquidaciones (segundo intento, con la salvaguarda)

El primer intento de paralelizar `va_validarLiquidaciones` (commit `ebf68eb`,
documentado arriba en "Se revirtió la paralelización...") paralelizaba
PÁGINAS dentro de un mismo PDF grande (patrón pensado para Lo Barnechea, que
sube un solo PDF) y dejaba el pool de workers vivo el resto de la corrida —
sospecha razonada (nunca confirmada con medición real) de que esto causó 2
corridas reales colgadas, porque Finiquitos/Licencias/Exenciones/F30/F30-1/
PreviRed corren DESPUÉS en el pipeline y dependen del worker único global.

Este segundo intento es un patrón DISTINTO, pedido explícito del usuario:
Antofagasta divide Liquidaciones en ~24 archivos (uno por letra de
apellido, no un PDF único) — cada archivo ya resetea su propio estado
pegajoso (`currentRut`, `enContratoHasta`) al empezar, exactamente el mismo
patrón ya validado sin incidentes en Contratos y Libro de Asistencia
(paralelizar por ARCHIVO completo, nunca páginas sueltas de un mismo
archivo). La diferencia clave con el intento revertido: **el pool se libera
explícitamente** (`va_liberarOCRPool()`, nueva función — termina cada
worker y limpia `va_ocrPool`) apenas termina `va_validarLiquidaciones`,
ANTES de que corran los pasos secuenciales que le siguen — la salvaguarda
que el intento anterior no tenía.

Detalle técnico que casi se pasa por alto: `va_ocrRunLicenciaMedica`
(llamada dentro del loop, en la "red de seguridad" de RUT no encontrado)
usaba el `ren_ocrWorker` GLOBAL hardcodeado, no un parámetro — si se
paraleliza sin arreglar esto, todas las llamadas desde archivos distintos
pisarían el mismo worker global (incluyendo `setParameters` de whitelist de
caracteres, mutación de estado compartida) en vez de usar cada una su
worker del pool. Se le agregó parámetro `worker` opcional (default al
global, mismo patrón que `va_ocrPaginaMejorRotacion`) y se actualizó el
único llamado interno para pasar el worker local.

**Verificado en el navegador real (no en Python)**: se armó una corrida con
4 archivos reales chicos (letras I/J/K/U, 1-2 páginas cada uno) y se
confirmó en consola que arrancan los 4 EN PARALELO ("4 en curso
simultáneamente") — la mecánica de reparto funciona. **No se pudo confirmar
en el sandbox que la corrida completa (con archivos reales de hasta 44
páginas, 24 archivos) termine y libere el pool sin problemas** — la misma
limitación de siempre (Tesseract.js en este sandbox es demasiado lento para
correr un caso real completo, ni con archivos chicos: 6 páginas repartidas
en 4 workers no terminaron en >10 minutos). Antes de dar esto por
completamente validado, hace falta que el usuario lo corra real y confirme
en su consola: que aparecen múltiples "archivo N iniciado" simultáneos
(paralelismo real), que aparecen los "archivo N terminado" correspondientes
(no se cuelga ningún archivo), y que los pasos siguientes (Finiquitos,
Licencias) arrancan con normalidad después (el pool efectivamente se
liberó).

## SIN_LIQUIDACION masivo puede ser un archivo de letra faltante, no un bug — chequealo ANTES de auditar lectura

El usuario mandó el Excel exportado de una corrida real (Antofagasta, 341
LH, 58 SIN_LIQUIDACION de 330 activos) pidiendo auditar por qué. Antes de
tocar código: agrupar los casos flageados por PRIMERA LETRA DEL APELLIDO
(no por RUT) — 17 de los 58 tenían apellido con V, y el LH real tiene
EXACTAMENTE 17 activos de apellido V (coincidencia perfecta). La carpeta de
Liquidaciones de Antofagasta reparte los PDF por letra de apellido
(`A. liquidación letra A.pdf`, `B. liquidaciones letra B.pdf`, etc.) — y no
había archivo de la letra V. No es un bug de lectura, es un documento que
falta subir. **Antes de auditar lectura/OCR sobre un `SIN_LIQUIDACION` (o
cualquier módulo con documentos repartidos por letra), agrupar los
faltantes por letra primero** — si una letra completa explica un bloque
grande de los faltantes, es más rápido confirmar/descartar eso que auditar
página por página.

**Mejora de proceso pendiente, sugerida al usuario, no implementada
todavía**: al cargar los archivos de Liquidaciones (o cualquier slot
repartido por letra), calcular qué letras de apellido hacen falta según
`va_lhFiltered` (activos) y avisar ANTES de correr toda la validación si
alguna letra tiene 0 archivos cargados — hoy este gap solo se descubre
auditando el Excel exportado después de una corrida completa.

## Firma física de Liquidaciones tenía el mismo bug de raíz que Contratos — substring exacto en vez de palabra individual

Mismo Excel real: 137 de 330 activos (41.5%) salían `SIN_FIRMA`. El
detector de tinta física de Liquidaciones (bloque `esFirmaFisica`, DENTRO
de `va_validarLiquidaciones`, no confundir con
`va_detectarFirmaFisicaPorEtiqueta` de Contratos) usaba una zona FIJA
(60%-82% del alto de página) — a diferencia de Contratos, que YA usaba
anclaje por etiqueta. Se auditó la letra A completa (8 páginas reales, con
nombre por página vía OCR + cruce contra el caso real de cada uno en el
Excel): 3 casos reales (Acuña Valencia, Aguirre Armijo, Aguirre Saavedra)
tenían tinta real de sobra (2.3%-4.8%, muy por encima del umbral 0.3%) en
esa misma zona fija — la zona en sí no era el problema.

La causa real: el gate que HABILITA el chequeo de tinta (`esLiqEscaneada`)
exigía el substring EXACTO `"FIRMA CONFORME"` en el texto ya unido — si el
OCR real separa/corrompe esas 2 palabras (aunque cada una individualmente
se reconozca bien), el chequeo de tinta ni se intenta. Mismo patrón de raíz
que el caso de Yucra Geronimo en Contratos (la firma tapaba la etiqueta
impresa y el substring exacto fallaba) — portado el mismo fix acá: (1) el
gate ahora también acepta si cualquier PALABRA individual del OCR
(`ocrWordsLiq`, capturada del mismo `recognize()` que ya se llamaba, antes
solo se usaba `.text`) dice "CONFORME"; (2) la zona de tinta ya no es un
porcentaje fijo — se ancla a la posición real de la etiqueta detectada por
OCR, traducida por FRACCIÓN de altura entre el canvas del OCR (escala 3.0)
y el canvas del chequeo de tinta (escala 1.0/1.5, para no encarecer el
render) — cae al rango fijo de siempre solo si no se detectó ninguna
etiqueta. Validado con réplica fiel en Python contra las 8 páginas reales
de letra A, mismas escalas exactas que usa el código: los 3 casos rotos
ahora detectan firma=True, los que ya andaban bien siguen andando bien.

**Patrón para la próxima vez**: cualquier detector de firma física nuevo
(o ya existente) que dependa de un substring exacto en texto OCR ya unido,
o de un porcentaje fijo de página, es candidato a este mismo bug — preferí
desde el inicio anclar por PALABRA individual (con su propio bbox) sobre
un texto ya reconstruido/unido.

## "58 sin liquidación" era 3 cosas distintas — auditoría completa de los 41 no-V

Después de confirmar que 17/58 eran la letra V faltante, el usuario pidió
explícitamente "no asumas, hacé vos la lectura" para los 41 restantes.
Auditoría completa (301 páginas reales, los 12 archivos necesarios,
réplica fiel en Python corrida en background) dio:

- **29/41**: el apellido SÍ aparece legible en el documento real (la
  página existe) pero el RUT específicamente no matcheaba contra la
  nómina — mismo patrón "1 dígito mal leído" ya documentado antes, pero a
  mucho mayor escala de la que se había visto. Causa raíz encontrada con
  un caso real (Astete Gutierrez, RUT real ...630-**0**, la página dice
  "RUT: ...630-**2**"): el rescate por Levenshtein (`va_matchRutCercano`)
  YA existía y funciona bien, pero su ÚNICA fuente de candidatos crudos
  (`va_findAllRutsRaw`) solo implementaba los Patrones 1/2 de
  `va_findAllRuts` (puntuación tipo "NN.NNN.NNN-N") — en la página real,
  ni siquiera el RUT del EMPLEADOR (que aparece 2 veces en la misma
  página) calzaba con esa puntuación esperada (OCR real: "87.645. 000-3"
  y "+7.645.000-3", ninguno de los dos matchea el patrón). Fix:
  `va_findAllRutsRaw` ahora también incluye el Patrón 4 (ancla en la
  etiqueta impresa "RUT:", mucho más tolerante al ruido de puntuación).
  Validado en el navegador real con 2 casos independientes de letras
  distintas (Astete en A, Salinas Menchaca en S).
- **9/41**: el RUT SÍ se encuentra con el regex normal (con checksum) en
  el archivo completo — pero la persona sigue saliendo SIN_LIQUIDACION en
  producción. Caso real confirmado visualmente: Fredes Jeraldo Ana Maria
  (archivo "E y F", página 22 de 22, liquidación real, firmada, RUT
  perfectamente legible "5.859.211-0"). **No resuelto** — esto no es un
  problema de extracción de RUT (ya se confirmó que el RUT se lee bien),
  es más probablemente un problema de ATRIBUCIÓN página↔trabajador dentro
  del loop de `currentRut`, o una diferencia real entre Tesseract.js (el
  motor real) y pytesseract (usado para auditar) que no se pudo reproducir
  en este sandbox. Sospecha sin confirmar, pendiente si se repite después
  del fix del RUT.
- **3/41**: genuinamente no se encontró ni RUT ni apellido en el texto del
  archivo completo (Duran Ragua, Sevillano Zelada, Landazuri Cuero) — sin
  confirmar todavía si es una ausencia real o una diferencia de escritura
  del nombre entre el LH y el documento (ej. apellido materno distinto,
  nombre de casada vs soltera). Pendiente si se pide.

**Archivos de letras mixtas ("E y F", "Y , Z")**: se inspeccionaron
visualmente — la estructura en sí no tiene nada roto (cada trabajador
sigue con su propia liquidación de 1 página, sin importar si es de la
letra E o F dentro del mismo archivo). Lo que SÍ se confirmó: estos
archivos combinados intercalan además OTROS tipos de documento
(certificados de pago BancoEstado — comprobantes de depósito — mezclados
entre las liquidaciones, de personas que a veces ni siquiera están en el
tramo alfabético del archivo, ej. "Zarate Salazar" apareciendo en el
archivo "Y , Z" junto a los Y/Z reales). El código YA maneja esto
(`esComprobanteText`/`tieneComprobante`, vía RUT propio en cada
comprobante) — no se encontró un bug estructural nuevo específico de
archivos combinados, más allá de los 2 ya documentados arriba (que
también aparecen en archivos de una sola letra).

## va_findAllRutsRaw v1 vs v2: auditar a la escala EQUIVOCADA da un número falso

Con v1 desplegado, el usuario corrió la validación real: 58→51
SIN_LIQUIDACION, solo 7 de 41 resueltos — muy por debajo de lo esperado.
Se investigó con Correa Castañeda Nila (RUT real 23.162.740-5): la página
es perfectamente legible a simple vista, pero a escala 2.5 Tesseract pierde
el dígito verificador por completo ("23,162.7:10-", sin nada después del
guión) — a escala 3.0 SÍ aparece, aunque mal leído ("...7:10-5", el ":" no
estaba en la lista de separadores tolerados de v1). Fix v2: en vez de
enumerar separadores, captura TODO el bloque entre "RUT:" y la siguiente
etiqueta del formulario, sin importar el ruido intermedio.

**Trampa real al validar esto**: el primer intento de medir "¿cuántos
resuelve v2?" corriendo el audit completo (33 casos, ~280 páginas) dio
resultados que NO coincidían con lo ya confirmado a mano (Correa salía
"no resuelto" pese a haberse verificado que SÍ funciona) — la causa era
que el script de auditoría usaba `get_pdf_text_ocr` con su escala default
(2.5, la misma que la `va_getPdfTextOCR` COMPARTIDA), pero
`va_validarLiquidaciones` hace su PROPIO OCR inline a escala 3.0 (no pasa
por la función compartida). Auditar a la escala equivocada literalmente
reproduce el bug v1 estaba resolviendo (pérdida del dígito a 2.5) y da un
resultado sistemáticamente peor de lo real. **Antes de auditar cualquier
lectura, confirmar a qué escala hace su OCR el código real que se está
probando — no asumir que toda la app usa la misma escala en todos
lados.**

Con la escala corregida (3.0): **18 de 34 casos no-V resueltos (53%)** —
validado con réplica fiel contra los 12 archivos reales completos. Quedan
16 sin resolver + 17 de letra V (archivo faltante) = 33, bajando de los
58 originales. Los 16 restantes no se investigaron caso por caso todavía
— candidatos para una vuelta futura si el usuario la pide, probablemente
mezclan el mismo patrón "dígito perdido a cierta escala" (posible mejora:
probar 2-3 escalas y quedarse con la que da más texto útil, como ya se
hace para rotación) con casos de atribución página-trabajador distintos.

## Auditoría real de Liquidaciones Antofagasta: 4 hallazgos con evidencia real, no adivinados

El usuario reportó 4 síntomas juntos sobre una corrida real
(`Validacion_Acreditable_Antofagasta_Base única_2026-08-19.xlsx`, 26
SIN_LIQUIDACION, 40 SIN_FIRMA, mensajes "Nuevo contrato" en Liquidaciones,
porcentaje de carga "no real"). Siguiendo el proceso de este Skill (mirar
documentos reales antes de tocar código), cada uno resultó ser una causa
distinta:

1. **14 de 26 SIN_LIQUIDACION eran un archivo faltante, no un bug**: la
   carpeta de Liquidaciones tenía A-J y saltaba a M-V — faltaba
   "L. Liquidaciones letra L.pdf". Confirmado listando la carpeta real
   antes de sospechar del código (mismo patrón ya documentado arriba para
   la letra V en una sesión anterior — **va dos veces que "muchos
   SIN_LIQUIDACION agrupados por la misma letra inicial" resulta ser un
   archivo de letra faltante**, revisar eso primero siempre).
2. **`tieneMarcadorLiq` (el marcador que dice "esta página es una
   Liquidación") podía fallar aunque la página fuera 100% legible y
   firmada**: caso real, Fredes Jeraldo Ana Maria (archivo letra F, página
   17/17) — el OCR corrompió las 6 variantes de frase que reconoce el
   marcador ("Alcance Líquido" → "Alcance Líquiz'o", "Líquido a recibir" →
   "¡ÍQUIDO A RECP3/R" con la L caída) mientras el encabezado "Sr(a):
   NOMBRE ... RUT: ... Tipo Contrato:" seguía perfectamente legible.
   Validado con OCR real (pytesseract, escala 3.0 — la misma que usa
   `va_getPdfTextOCR`/el bloque inline de Liquidaciones) contra la página
   real: las 6 variantes fallan a la vez, el encabezado no. Se agregó ese
   encabezado como 7ª variante del marcador (`tieneMarcadorLiq`,
   index.html ~línea 11769) — más robusto porque no depende de una sola
   frase completa sobreviviendo el OCR.
3. **Firma física: umbral de tinta demasiado bajo (0.3%) sin evidencia que
   lo respaldara**. Midiendo el zona de firma de TODA la letra A real (52
   páginas, réplica fiel de `esFirmaFisica` en Python con
   `pytesseract.image_to_data` + PIL para el ratio de tinta): toda firma
   física confirmada visualmente midió entre 2.1% y 4.9% — muy por encima
   de 0.3%. Se subió el umbral a 1.2% (margen de sobra bajo toda firma
   real medida, por encima del ruido típico de fondo/línea impresa vacía).
   También se agregó captura de palabras (desvinculado/vacaciones/
   renuncia/finiquito/licencia/reposo/permiso/no firma) dentro de la misma
   zona de firma, mostradas en la Observación cuando aparecen — pedido
   explícito del usuario, para poder verificar a mano el motivo real en
   vez de un genérico "sin firma".
   **Divergencia sin resolver, documentada para la próxima vez**: el caso
   real de Aquea Contreras Yovani Alejandro (letra A, página 27) tiene una
   firma física real y clara (confirmado visualmente) — mi réplica en
   Python la detecta bien (CONFORME + darkRatio 3.91%), pero la corrida de
   producción real (Tesseract.js) la marcó SIN_FIRMA. Mismo patrón ya
   documentado arriba (pytesseract ≠ Tesseract.js) — no se pudo confirmar
   la causa exacta en este sandbox. Si se vuelve a reportar un firmado real
   marcado SIN_FIRMA después de estos cambios, ese es el primer caso a
   revisar (ya se sabe que la imagen es legible y el problema no es de
   calidad de escaneo).
4. **"Nuevo — Contrato/CI/Antecedentes" en la Observación de Liquidaciones
   de Antofagasta estaba mal cableado, no solo "duplicado"**: `liq.tieneContrato`
   ahí sale de páginas DENTRO del PDF de Liquidaciones — pero en
   Antofagasta el Contrato vive en un archivo separado por trabajador
   (slot `contratos`, leído por `va_validarContratosAntofagasta`), así que
   ese chequeo en `va_clasificar` (rama NUEVO) SIEMPRE salía "falta
   Contrato" sin importar si el trabajador ya tenía su Contrato firmado y
   validado en la pestaña dedicada. Tampoco aplica CI/Antecedentes en esta
   base (ya documentado más arriba: "no había carpeta de CI/Antecedentes
   como en Lo Barnechea"). Se agregó una rama `else if(va_baseKey==='Antofagasta')`
   (mismo patrón que ya existía para Vitacura) que NO repite ese chequeo —
   solo dice "Ingresó el día X — ver detalle de Contrato/Anexos en la
   pestaña Contratos".
5. **Progreso "no real" — confirmado en Licencias Médicas, no en
   Liquidaciones**: `paginasLicCompletadas`/`pdf.numPages` se declaraban
   DENTRO del loop `for(bi...)` de archivos del slot — con más de un
   archivo real (ej. un PDF + el `.oxps`, o dos PDF), la barra volvía a
   arrancar en 42% con cada archivo nuevo en vez de seguir avanzando
   (retrocedía visualmente en plena corrida real). Se agregó un conteo
   GLOBAL de páginas de TODOS los archivos del slot ANTES del loop
   (`paginasLicTotalGlobal`/`paginasLicCompletadasGlobal`) para repartir el
   mismo rango 42-49% entre todos — mismo patrón que ya usa Liquidaciones
   con `totalArchivosLiq`. Se revisó Liquidaciones específicamente y ahí
   el cálculo YA escalaba correctamente contra `dd.buffers.length` (lo
   realmente subido, no un total esperado) — no se encontró bug ahí; si
   vuelve a reportarse, pedir el mensaje/porcentaje exacto en vez de
   asumir que es el mismo bug.

**Metodología reforzada por este caso**: cuando el usuario reporta varios
síntomas juntos en una sola corrida, no asumas que comparten una causa —
acá 4 síntomas → 4 causas raíz completamente independientes (archivo
faltante, regex de clasificación frágil, umbral de detección sin calibrar,
y wiring cruzado entre módulos). Diagnosticar cada uno con su propia
evidencia real (listar la carpeta, OCR real de la página específica,
medición real de tinta en una muestra completa) fue lo que evitó "arreglar"
el síntoma equivocado.

## Hallazgo mayor: la firma física NUNCA se detectaba si su propia tinta tapaba la etiqueta "FIRMA CONFORME" -- paradoja real, confirmada con Python, no adivinada

El usuario reportó firmas reales marcadas SIN_FIRMA en producción (y
viceversa) y pidió un análisis completo, no parches sueltos. Se tomaron 2
casos reales de la letra G (García Argentino Mario, González González
Humberto Antonio) — ambas páginas con firmas GRANDES y muy oscuras,
confirmadas a simple vista renderizando la página real a PNG.

**La causa no era el umbral de tinta (ya subido a 1.2% en una sesión
anterior)** — el chequeo de tinta ni siquiera llegaba a ejecutarse. La
condición para activar `esLiqFisica`/`esLiqEscaneada` exigía encontrar la
palabra "CONFORME" en el OCR de la página (substring o palabra individual
con bbox) ANTES de intentar medir tinta. Réplica exacta en Python
(`pytesseract.image_to_data`, misma escala 3.0 de producción) contra las 2
páginas reales: `tieneConforme` daba **False en ambas**, pese a que
"FIRMA CONFORME" es perfectamente legible a simple vista en la imagen.

**La causa real, confirmada mirando la imagen**: en ambos casos la tinta de
la firma se extiende hacia abajo y toca/tapa parcialmente el propio texto
impreso "FIRMA CONFORME" — cualquier OCR (pytesseract acá, Tesseract.js en
el navegador real) falla en leer esa palabra específica ahí. Es una
paradoja real: **mientras más grande y oscura la firma (más confiable a
simple vista), más probable que ella misma tape su etiqueta y la
detección falle por completo** — exactamente lo opuesto de lo esperado.
Con el diseño anterior, esto convertía firmas obviamente reales en
"sin firma" de forma sistemática, no ocasional.

**Fix**: se sacó el requisito de encontrar "CONFORME" para HABILITAR el
chequeo de tinta — ahora alcanza con que la página sea una Liquidación
escaneada (`imgCount>=1 && tcItems<5`, confirmado por `tieneMarcadorLiq`,
ya robusto por sí solo con el fallback de encabezado Sr(a)/RUT/Tipo
Contrato agregado antes). "CONFORME" se sigue usando para ANCLAR la zona
de tinta con precisión cuando SÍ se encuentra (más preciso); si no se
encuentra, cae al rango fijo (60%-82% del alto de página) que ya existía
como fallback en el código pero antes era **inalcanzable** (nunca se
llegaba a él porque el gate de arriba ya había cortado el flujo). Validado
con las 2 páginas reales: el `darkRatio` en la zona fallback ya daba 2.94%
y 3.59% (bien por encima del umbral 1.2%) incluso ANTES del fix -- solo no
se usaba porque nunca se llegaba a calcularlo con intención de aceptar el
resultado.

**Verificación adicional del cruce Faltas/Permisos/Licencias del Libro**
(mismo pedido del usuario, "mira bien el tema del cruce"): se tomaron 3
casos reales de discrepancia y se cruzaron a mano contra el Libro de
Haberes real (columnas `Días Ausencias`/`Días Permisos`/`Días Licencias
(reales)`) -- los 3 coincidieron EXACTO con lo que el panel ya mostraba
como "LH". Esto confirma que el lado de la referencia (columnas nativas
del LH, agregadas en una sesión anterior) está funcionando bien -- toda la
discrepancia observada viene del lado de la LECTURA con IA del cuaderno
(la alucinación tipo "Luz"→"Licencia" ya documentada y arreglada arriba),
no de un bug en el cruce en sí.

**Rendimiento (pedido explícito: "verifica el paralelismo")**: auditado
con datos reales -- 395 páginas repartidas en 20 archivos MUY desparejos
(2 a 52 páginas por archivo). El pool ya reparte por cola compartida (cada
worker toma el siguiente archivo libre, no uno fijo — buen diseño), pero
el ORDEN de entrada igual importa: si a un mismo worker le toca encadenar
2-3 de los archivos más grandes porque los demás ya vaciaron los chicos y
siguen tomando de la cola, esa sola cadena puede explicar 15-20+ minutos
sin que exista ningún bug de lectura. Fix de bajo riesgo (pura
reordenación, sin tocar lógica): los archivos ahora se pre-cuentan
(páginas, barato — no renderiza nada) y se ordenan de MAYOR a MENOR antes
de repartirlos al pool ("Longest Processing Time first", técnica de
scheduling clásica que acota mejor el peor caso) — aplicado a
Liquidaciones, Libro de Asistencia y Contratos (los 3 módulos con este
mismo patrón de paralelización por archivo). Para Libro de Asistencia
específicamente, esto requirió que el nombre de archivo viaje JUNTO al
buffer en el item reordenado (antes se buscaba por índice original
`dd.files[idxArchivo]`, que se habría roto al reordenar).

**No se pudo medir el tiempo real de ninguno de estos 2 fixes en este
sandbox** (misma limitación de siempre) — ambos están respaldados con
evidencia real (imágenes reales, réplica exacta en Python, conteo real de
páginas), no adivinados, pero falta la confirmación de una corrida
completa real. Pendiente que el usuario confirme: (a) cuántos de los 41
SIN_FIRMA se resuelven ahora, (b) si el tiempo de Liquidaciones baja de
forma perceptible, (c) si el cruce de Faltas/Permisos/Licencias del Libro
mejora con el prompt anti-alucinación ya aplicado.


## 22-08-2026 — La zona de firma medía el párrafo impreso, no la firma: 326 de 330 "firmadas" por error

Corrida real (`Validacion_Acreditable_Antofagasta_Base única_2026-08-22.xlsx`, 330 activos): solo 4
`SIN_FIRMA`. El usuario reportó que hay liquidaciones sin firmar marcadas como firmadas.

**La causa no era el umbral** (que ya se había subido a 1.2% en una sesión anterior) **sino la
ZONA.** El bloque medía una franja de 12% del alto por 65% del ancho arriba de la etiqueta — que
cae de lleno sobre el párrafo IMPRESO *"Certifico que he recibido de Akro Diseños SpA
(87.645.000-3) a mi entera satisfacción..."* que trae toda liquidación, firmada o no. Medido con
réplica fiel en Python sobre las 52 páginas reales de la letra A: la tinta en esa zona va de
**2.11% a 5.22% en TODAS**, incluidas las 7 confirmadas visualmente sin firmar. Cualquier umbral
por debajo de 2% marca todo como firmado; cualquiera por encima empieza a perder firmas reales. La
zona no era separable, punto.

Dos causas secundarias, ambas reales:
- **El ancla enganchaba la palabra equivocada.** El patrón era `/CONFORME|FIRMA/i` sobre cualquier
  palabra OCR: en 5 páginas de la letra A ancló en `"firmaron"` (de la carátula *"…de los
  trabajadores que no firmaron su liquidación"*) a un 38% del alto, en hojas que ni siquiera son
  liquidaciones.
- **El fallback sin etiqueta era peor que no hacer nada.** Si el OCR no leía la etiqueta, se caía a
  la franja fija 60%-82% — que por lo mismo de arriba da "firmada" SIEMPRE. Y ése es justo el caso
  de la paradoja ya documentada (una firma grande tapa su propia etiqueta): el caso que más
  verificación necesitaba era el que peor se resolvía.

**Fix**: franja de **6% del alto** inmediatamente arriba de la etiqueta y **±18% del ancho** en
torno al centro X de la etiqueta (antes x arrancaba en 0 y arrastraba los agujeros de perforado);
ancla restringida a tokens con `CONFOR` en la **mitad inferior** de la página (`FIRMA` como
segunda, excluyendo `FIRMAR*`); umbral **2.5%**.

Calibración con verdad de terreno obtenida mirando los recortes reales (letras A, B y S):

| | n | tinta en la zona nueva |
|---|---|---|
| SIN firma (línea vacía) | 12 | 1.76% – 2.35% |
| CON firma | 26 | 2.98% – 15.5% |

**38/38 bien clasificadas.** La separación es limpia y no fue elegida a ojo.

**Escalón de IA nuevo (no existía en Liquidaciones)**: banda ambigua `2.2%–3.3%` o etiqueta no
anclable → se manda **el recorte** de la franja a MiniMax con un prompt binario, y **la IA puede
corregir en las dos direcciones** (si dice `false`, la página queda sin firma aunque la tinta
hubiera pasado el umbral). Sin eso el falso positivo no se arregla: un gate de "solo si no encontré
nada" nunca lo toca. Probado contra el endpoint real con 8 recortes reales, incluidos los 4 casos
de la banda ambigua: **8/8 correctos**. Log en `va_iaAuditLog` con módulo `Firma Liquidación`,
conectado a la hoja Liquidaciones del Excel. Costo esperado ~20% de las páginas de liquidación.

Ojo: el ancla depende de que el OCR lea "CONFORME", así que en el navegador real (Tesseract.js, que
lee peor que pytesseract) es esperable que **más** páginas caigan al escalón de IA que en esta
calibración. La medición de tinta en sí no depende del OCR y transfiere directo.

## 22-08-2026 — Los 11 `SIN_LIQUIDACION` tenían su página presente: falla la atribución, no el documento

Los 11 casos de la misma corrida. Primero se descartó lo barato (ver *"SIN_LIQUIDACION masivo puede
ser un archivo de letra faltante"* más arriba): la carpeta tenía las 21 letras, ninguna faltaba.
Después se OCR-earon los 8 archivos de letra involucrados y se buscó RUT + apellido:
**11 de 11 tienen su página, legible.** Ninguno es un documento faltante.

**Mecanismo real** (corregido respecto de la primera hipótesis): el RUT del trabajador sale corrupto
del OCR — caso real `"RUT: 13.357.03C-6"`, que ni siquiera llega a 9 caracteres y muere en
`va_addRut` — así que `pageRuts` queda **vacío**, ningún escalón difuso encuentra nada, `pageRut`
queda null y **`currentRut` conserva el del trabajador ANTERIOR**: la liquidación se le atribuye a
esa otra persona y el dueño real queda `SIN_LIQUIDACION`.

Se había sospechado del RUT del empleador (`87.645.000-3`, impreso en el encabezado de cada
liquidación y presente en 40%-70% de las páginas OCR). **No era eso**: ese RUT ya está en
`VA_RUT_CORP` y `va_findAllRuts` lo descarta vía `va_addRut` → `va_isCorpRut`. Pero
`va_findAllRutsRaw` **no** valida nada de eso, y las variantes que el OCR corrompe — capturadas
reales: `87.645.060-3`, `87.65.090-3`, `87.645,900-3`, `87.645.£200-3` — ni siquiera coinciden con
la entrada de `VA_RUT_CORP`, así que llegan enteras a `va_matchRutCercano` y pueden caer a
distancia 1 de un trabajador real. Por eso igual se excluyen por posición (pegadas a la etiqueta
`Empleador:`/`División:`).

**Fixes**:
1. **El escalón por NOMBRE subió antes que los difusos por RUT.** El encabezado `Sr(a): Apellidos,
   Nombres` es texto impreso y mucho más redundante que acertar 8 dígitos, y no arrastra el riesgo
   de cruzar identidades por distancia 1 que sí tiene `va_matchRutCercano`. Antes era el ÚLTIMO
   escalón.
2. **El regex de ese nombre se sacó a `va_extraerNombreCabeceraLiq()` y se hizo tolerante.** El
   anterior exigía el literal `Tipo Contrato` como terminador y tenía tope de 60 caracteres: medido
   sobre las 20 páginas de la letra B, fallaba en 2 donde el nombre era perfectamente legible,
   porque el OCR entrega `"fipo Contrato"` / `"Tipo Corirato"` y entonces nunca se alcanza el `\n`.
   Ahora la etiqueta se tolera corrupta (`Sr(a)`/`S1(a)`/`Sr{a)`/`Sr a :`), el corte es por fin de
   línea o por la siguiente etiqueta conocida con tolerancia, y se descartan hasta 2 tokens finales
   con caracteres que no son de un nombre (solo del final: un token corrupto en el medio —
   `"B:istamante"` por `"Bustamante"` — lo tolera `va_matchNombreNomina` por Levenshtein).
3. **Nunca aceptar un `pageRut` que no esté en la nómina.** Antes, `pageRut=[...pageRuts][0]` tomaba
   cualquier RUT válido de la página (ej. el de otra persona en un comprobante intercalado) y, como
   `currentRut` es pegajoso, ese error se arrastraba a las páginas siguientes.
4. **Último recurso: IA sobre el encabezado** (recorte del 22% superior), pidiendo
   `{nombre_trabajador, rut_trabajador}` con la advertencia explícita de que el RUT junto a
   `Empleador:` es el de la empresa. Log con módulo `Atribución Liquidación`.

**Validación** (réplica fiel en Python de `va_extraerNombreCabeceraLiq` + `match_nombre.py` contra
la nómina real de 330 activos, usando el texto OCR real de las 11 páginas): **9 de 11 resueltos por
el escalón gratis, 0 atribuciones equivocadas**. Los 2 restantes van a IA — Gahona Zaragoza
(`"Marco Nica”:or Tiro Contyzto"`, el corte no reconoce "Tipo Contrato" tan corrupto) y Sevillano
Zelada (`"Ziada"` por `"Zelada"`, distancia 2 en una palabra de 6 → fuera de tolerancia). Los dos
devuelven `null`, nunca la persona equivocada. Sanity check anti-falsos-positivos: 0 errores en
330/330.

**Pendiente de confirmar en corrida real del usuario** (limitación de siempre: pytesseract ≠
Tesseract.js): que los 11 desaparecen, cuántos `SIN_FIRMA` aparecen ahora, y cuánto tiempo agregó la
IA de firma. La consola imprime `[Firma IA]` y `[Atribución IA]` con los contadores.


## 23-08-2026 — Cruces de días y montos, y por qué el recorte para la IA importa más que el prompt

Corrida real con los fixes del 22-08 ya puestos: `SIN_LIQUIDACION` 11 → **1**, `SIN_FIRMA` 4 → **34**.
El usuario pidió cuatro cosas más; las cuatro salieron de mirar los documentos reales.

### El recorte de la IA para atribución era demasiado corto (el "por qué no funcionó la key")

El único `SIN_LIQUIDACION` que quedó (Gahona Zaragoza) **sí disparó la IA** — el log decía
`sin_match`, "la IA leyó el encabezado pero no coincide con nadie". Parecía un fallo de la IA. No lo
era: el recorte del **22% superior** de la página no llega a la línea `Sr(a):`. Medido con OCR sobre
6 páginas reales de letras distintas, `Sr(a):` cae entre **19.1% y 23.9%** del alto y `RUT:` entre
**20.7% y 25.3%** — en las páginas corridas hacia abajo (Gahona: 23.9%) el recorte cortaba justo
antes del nombre. La IA respondía `null/null` porque **el dato no estaba en la imagen**.

Con el recorte al **35%**, la misma página devuelve `Gahona Zaragoza, Marco Nicanor` y
`20.543.463-1`, ambos correctos (verificado contra la IA real).

**Lección**: cuando una lectura con IA devuelve "no lo veo", lo primero a revisar es **qué le
mandaste**, no el prompt. Renderizá el recorte exacto que produce el código y miralo con `Read` — si
vos no ves el dato ahí, la IA tampoco.

### Resolución > contexto: el mismo prompt acierta o falla según el recorte

Para leer "Días Trabajados" se probaron dos recortes con el prompt IDÉNTICO contra 4 páginas reales:

| Recorte | Aciertos |
|---|---|
| escala 1.5, 12%-45% del alto (ancho, baja resolución) | 3/4 — en San Martin Vega devolvió 25 y 26 en dos intentos, el papel dice 29 |
| escala 3.0, 18%-32% del alto (chico, alta resolución) | **4/4** |

Para leer un NÚMERO CHICO, más contexto no ayuda: ayuda más resolución. Por eso el código
re-renderiza la página a escala 3.0 para este caso en vez de reusar el canvas de 1.5 que ya tiene.

### Salvaguarda del "tercer valor": la IA también se equivoca en un dígito

El caso de San Martin Vega dejó tres números distintos sobre la mesa: OCR 22, IA 26, LH 29 (el papel
dice 29). Si la respuesta de la IA se acepta a ciegas, un falso positivo se cambia por **otro** falso
positivo, ahora con sello de "verificado con IA" — peor que antes.

Regla implementada, para días y para montos: la IA solo se acepta si **confirma uno de los dos
valores que ya se tienen** (el del LH / el de la liquidación, o el del OCR). Si trae un tercer
número, no se afirma nada: queda `ilegible — revisar a mano`. Es honesto y no rompe la confianza en
el resto de las filas.

### Los cruces nuevos (puntos 1-3 del pedido)

Etiquetas leídas con **tolerancia por Levenshtein** sobre sus letras, porque el OCR real las destroza
— casos capturados: `LÍQUIDO A RECIHIR`, `EXQUIDO A PI.CIBIR`, `LÍQU:DO A RECIBIR`,
`Alcance Líquidi'`, `Alcance Líquido, $`. Medido sobre 104 páginas de liquidación reales:
**104/104 montos leídos (100%)**, contra 88/117 con un regex literal. Días: de 52 a **73 limpios**
con el mismo cambio.

1. **Días de la liquidación vs LH** (`va_extraerDiasTrabajadosLiq`): 74/76 coinciden en la muestra
   real. Ojo con los dígitos: `"3% días"` son 30 y `"O días"` es 0 — esos se marcan `dudoso` y **no**
   generan discrepancia. `"33 días"` se descarta por imposible.
2. **Monto del comprobante vs líquido de la liquidación** (`va_extraerMontoLiquidoLiq`,
   `va_extraerMontoComprobante`): se compara contra **LÍQUIDO A RECIBIR**, no contra *Alcance
   Líquido* — caso real Meza Escobar: Alcance 664.547, Líquido a recibir 487.336, comprobante
   509.488. Verificado con la IA: en Choque Alfaro el OCR leía 32.076 y la IA confirmó 38.076 (=
   liquidación, falso positivo eliminado); en Meza confirmó 509.488 ≠ 487.336, **diferencia real**.
3. **Líquido $0 ⇒ no aplica comprobante**: si `LÍQUIDO A RECIBIR: $ 0` no hay pago que respaldar.
   Texto real de la carta que lo acompaña: *"por el cual el monto de su liquidación resulto en $0"*
   (`va_esCartaMontoCero`). Antes estos trabajadores salían con "Comprobante de pago" como documento
   faltante para siempre — en la corrida del 22-08 eran ~16 de los 34 `SIN_FIRMA`.

El Excel suma 5 columnas (`Días Liq. (doc)`, `Cruce días`, `Líquido (doc)`, `Monto comprobante`,
`Cruce monto`) y el detalle de IA del módulo `Días y Montos`.

**Cosmético relacionado**: el mensaje del caso OK tenía `'30 días + firmada'` con el 30 hardcodeado,
lo que quedaba contradictorio al lado del cruce nuevo ("29 días trabajados... liquidación 22 vs LH
29"). Ahora usa los días reales del LH de ese trabajador.

**Validación**: extractores probados en Python contra el OCR real y después contra el JS real en el
navegador — resultados idénticos en los 11 casos. Los 3 prompts nuevos probados contra el endpoint
real de MiniMax con las imágenes reales. **Sin corrida completa todavía**: falta que el usuario corra
y confirme cuántos `SIN_FIRMA` bajan por el líquido $0 y cuántas discrepancias de días/monto quedan.

## 23-08-2026 — Días trabajados: anclar en la ETIQUETA, no en la palabra "días"

Reporte del usuario: *"las liquidaciones de sueldo están teniendo un problema, algunas al leer los
días trabajados"*. Medido sobre el Excel de la corrida real: de 459 filas, **98 (21.4%) decían
"no se pudo leer en la liquidación"** y 0 daban discrepancia.

La versión anterior de `va_extraerDiasTrabajadosLiq` exigía que **después** del número apareciera la
palabra "días" (con una lista cerrada de variantes de OCR) y recién ahí miraba la etiqueta. Sobre el
OCR real (escala 3.0, la misma que usa `va_validarLiquidaciones` inline) eso falla seguido:

| Lo que lee el OCR | Por qué fallaba |
|---|---|
| `Días Trabajados: 30'días` | apóstrofe pegado al número, `\s*` no lo cubre |
| `Días Trabajados: 30 dízs` | "dízs" no estaba en la lista de variantes |
| `Días Trabajados: 30 díaz` | termina en z |
| `Bías Trabajados: 30 sas` | ni la etiqueta ni "días" son legibles, pero `Trabajados: 30` sí |
| `Días Tralaiados: 30 días` | etiqueta a distancia 6, la tolerancia era 5 |

**Fix**: se ancla en la etiqueta (`DIASTRABAJADOS`, Levenshtein ≤ 4 sobre las últimas 14 letras
antes del número) y se toma el primer número 0–31 que le sigue. La palabra "días" posterior pasa a
ser decoración y ya no se exige.

**Dos trampas que costaron una iteración cada una** — la primera versión "mejorada" devolvía 0 en 12
páginas que la vieja leía bien:

1. **La "O" de "TrabajadOs" se leía como un cero.** O es una lectura válida de 0, así que el regex
   la tomaba y la etiqueta a su izquierda (`...DIASTRABAJAD`) quedaba a distancia 4 — dentro de
   tolerancia. Lo bloquea un lookbehind de letra: `(?<![A-Za-z\d.,])`.
2. **`Horas no Trabajadas: 0 horas` queda a distancia 5 de `DIASTRABAJADOS`** — más cerca que varias
   etiquetas reales dañadas por el OCR. Lo bloquea un veto explícito de `HORA` en la ventana de la
   etiqueta. Con tolerancia 4 tampoco entraría, pero el veto está igual porque el margen es chico.

Y una tercera que casi se cuela: al acortar el token a `{1,2}` se perdía el `%` de `3% días` (que es
30 mal leído). Ese `%` es lo que activa la marca **`dudoso`**, y sin ella el caso pasaba de "no
genera discrepancia" a "discrepancia en firme" contra el LH — un falso positivo nuevo. El token
volvió a admitir `[.,%]`.

**Medición final** — 91 páginas de liquidación reales (letras A, C, M, S):

| | antes | después |
|---|---|---|
| días leídos | 66 (72.5%) | **90 (98.9%)** |
| perdidas respecto de la versión vieja | — | **0** |

Exactitud contra los días del LH: **62 coinciden**, 1 marcado `dudoso` correctamente (`3%` → 30), y
1 sola discrepancia en firme — San Martin Vega, el caso ya documentado más arriba donde el papel
dice 29 y el OCR lee 22 (se escala a IA y la IA trae un tercer valor, así que queda "revisar a
mano", que es lo correcto).

Validado además contra el JS real en el navegador con 15 casos (los 5 patrones rescatados, las 2
trampas y 3 etiquetas vecinas que NO deben leerse): **15/15 idéntico a la validación en Python**.

## 23-08-2026 — "—" mudo en la tabla de documentos adjuntos

El usuario mostró la tabla de adjuntos donde 11 de 14 filas tenían `—` en ESTADO en vez de decir que
el documento no estaba. Causa: `estado:(r&&r.estado)||(files.length?'—':'No adjuntado')`. Varios
validadores escriben un resultado con `estado:'—'` (o `'⚪ No cargado'`) al salir temprano **sin
archivos** — ese `'—'` ganaba sobre el fallback. Ahora el estado del módulo solo se usa si
`files.length>0`; si no, siempre `'No adjuntado'`. Mismo criterio aplicado a la hoja Resumen del
Excel, que iteraba `va_docResults` y mostraba `d.estado||'—'`.
