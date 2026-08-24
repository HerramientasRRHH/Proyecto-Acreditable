# Bitácora — Libro de Asistencia y Contratos

> Parte del skill `acreditable-review`. Registro histórico de hallazgos REALES con su
> evidencia — se lee **solo cuando se está trabajando en este módulo**, no en cada sesión.
> El proceso de auditoría y la política de IA viven en `SKILL.md`.
> Las secciones están en orden cronológico: si dos se contradicen, gana la más nueva
> (varias documentan código que después se revirtió y lo dicen explícitamente).

## "Verificá que esté el documento" no es lo mismo que "verificá que exista alguna firma"

Cuando un tipo de documento en realidad empaqueta VARIOS documentos exigidos
(ej. Contrato de Antofagasta = Contrato + Anexo Cargo + Anexo Pacto Horas
Extras, 3 documentos con firma propia cada uno), no alcanza con revisar "¿hay
alguna firma en algún lado del archivo?" — hay que confirmar que CADA
documento exigido esté presente Y firmado por separado. Preguntale al
usuario cuáles son los documentos exactos si no es obvio por la carpeta (acá
no había carpeta de CI/Antecedentes como en Lo Barnechea, así que en vez de
asumir que faltaba subir algo, se preguntó directo — la respuesta confirmó
que Antofagasta simplemente no exige esos dos ahí). El patrón de rastreo
pegajoso (`enContratoHasta` en Lo Barnechea, `tipoActual` en
`va_validarContratosAntofagasta`) sirve para esto: el título de cada
documento solo aparece en su primera página, las páginas de firma/
continuación heredan el tipo del último título visto.

## Firma física: buscar por la ETIQUETA impresa, no por una zona fija

Una misma base puede mezclar modalidades de firma archivo por archivo — en
Antofagasta algunos trabajadores firman por QR (texto "Firmado
electrónicamente por:") y otros a mano, en el mismo lote de contratos. Para
detectar firma física, NO calibres una zona fija de la página (ej. "70%-90%
de la altura") — la posición real cambia según si la firma tiene página
propia o comparte página con el cuerpo del documento. En cambio:

1. Usá el resultado de OCR con posiciones (`ren_ocrWorker.recognize(blob)` —
   confirmado que Tesseract.js v5 en este proyecto devuelve `data.words[]`
   con `.text` y `.bbox:{x0,y0,x1,y1}` por defecto, sin config extra).
2. Buscá la ÚLTIMA aparición de la etiqueta impresa ("TRABAJADOR"/
   "EMPLEADOR"/nombre de la empresa) — la última, porque esas palabras
   también aparecen sueltas dentro del texto de las cláusulas ("el
   trabajador", "el empleador"), y el bloque de firma real siempre es lo
   último de la página.
3. Revisá la densidad de tinta en una franja arriba de esa etiqueta (`va_detectarFirmaFisicaPorEtiqueta()`,
   ~70px de alto en la escala de render usada, umbral ≥1% de píxeles oscuros).

Esto reemplaza (y valida por primera vez con datos reales) la heurística de
zona fija que había quedado sin verificar en el Contrato de Lo Barnechea.
Probá primero con un canvas sintético (dibujar un garabato arriba de un
texto conocido) contra el `ren_ocrWorker` real del navegador antes de
confiar en el resultado — así se confirmó que funciona sin necesitar una
página real todavía disponible.

## Pestaña Contratos nueva en Lo Barnechea: la lectura ya existía, solo faltaba mostrarla

El usuario pidió un módulo de Contratos dedicado en Lo Barnechea (igual que
ya tiene Antofagasta/Vitacura), pero ahí Contrato/CI/Antecedentes van
intercalados DENTRO del PDF de Liquidaciones, no en archivos separados.
Antes de escribir lectura nueva, se confirmó que `w.tieneContrato`/
`tieneCI`/`tieneAntec`/`contratoFirmaTrabajador(Fisica)`/
`contratoFirmaEmpleador(Fisica)`/`tieneConstanciaNoFirma` en `va_liqMap` YA
se llenan para TODOS los trabajadores durante el loop de páginas de
`va_validarLiquidaciones` — no están condicionados al caso NUEVO. Lo único
que faltaba era una pestaña que los mostrara aparte; `va_clasificar()` solo
los usa (rama NUEVO) para decidir docsFalt, nunca los expone para el resto.
Por eso `va_renderContratosLoBarnechea()` es una función de render pura, sin
tocar ninguna lógica de detección — mismo espíritu que "grepeá el nombre del
slot/función antes de asumir que hace falta escribir algo desde cero" de
más arriba, aplicado a un campo de datos en vez de a un slot completo.

**Decisión de alcance explícita del usuario**: la pestaña lista SOLO a
quien tenga Contrato, CI o Antecedentes encontrado en el PDF de ESTE mes —
no a todos los activos. Un trabajador antiguo normalmente no vuelve a traer
esos documentos cada mes (ya están archivados de otro período), así que
tratarlo como "❌ faltante" habría sido un falso positivo sistemático, no
un hallazgo real. Mismo principio que ya aplicaba de forma implícita la
rama NUEVO de `va_clasificar` — acá se hizo explícito.

## Contratos Antofagasta asumía "un archivo = un trabajador" — no soportaba archivos agrupados

El usuario reportó "0/9 firmado completo" en Contratos, con los 9 nuevos
del período mostrando "❌ Sin archivo de contrato" — y adjuntó los
archivos reales que estaba subiendo: `Contratos de trabajos.pdf` (53
páginas) junto con dos "Listado ingresos..." que no son contratos.

Causa confirmada con el archivo real: `va_validarContratosAntofagasta`
identificaba al trabajador de un archivo por su NOMBRE DE ARCHIVO
(`va_matchNombreNomina(nombreArchivo, nuevosLH)`) y descartaba el archivo
ENTERO (`if(!worker)return;`) si no matcheaba — funciona bien cuando cada
trabajador tiene su propio PDF ("Contrato de trabajo de Juan Perez.pdf"),
pero `Contratos de trabajos.pdf` es UN SOLO archivo con los contratos de
~9 trabajadores distintos seguidos (~6 páginas cada uno: Contrato + Anexo
Cargo + Anexo HHEE) — su nombre de archivo no matchea a nadie, así que el
archivo se ignoraba completo sin mirar ni una página, aunque el contenido
fuera perfectamente legible (confirmado con Tesseract.js real: la primera
página del archivo es el contrato real de "Marcelina Aguirre Limachi",
RUT 29.088.873-5 leído correctamente).

**Fix**: se generalizó `procesarArchivoContrato` para detectar al
trabajador LEYENDO el contenido de cada página con título nueva
(`va_detectarWorkerEnTituloContrato`, nueva función: RUT primero vía
`va_findAllRuts`, nombre como respaldo vía el patrón "Don (ña) NOMBRE, de
nacionalidad"), no solo por el nombre del archivo. El nombre de archivo
sigue siendo la SEMILLA inicial (`worker` puede arrancar ya asignado) —
si el archivo es de un solo trabajador y la lectura de contenido falla en
alguna página, se sigue usando esa semilla sin romper nada (mismo
comportamiento de siempre). Si en cambio una página titulada nueva trae
el RUT de OTRO trabajador de la nómina, se cierra la cuenta del anterior
(`finalizarWorkerActual()`, la misma lógica de faltantes/incompletos que
antes corría una sola vez al final, ahora reutilizable) y arranca el
siguiente — permitiendo que un archivo agrupado procese a TODOS sus
trabajadores, no solo el primero.

Validado: (a) con OCR real (Tesseract.js) contra la página real del
archivo agrupado, `va_detectarWorkerEnTituloContrato` identifica
correctamente a la trabajadora por su RUT; (b) simulación completa del
loop de páginas con 2 trabajadores seguidos (uno incompleto, uno
completo) — cierra las cuentas en el momento correcto; (c) simulación del
caso de un solo trabajador por archivo con la detección por contenido
fallando en TODAS las páginas — sigue funcionando igual que antes gracias
a la semilla del nombre de archivo, sin regresión.

**Nota sobre Finiquitos, mismo reporte del usuario**: se sospechó al
principio que era el mismo bug, pero `va_validarFiniquitos` NO identifica
por nombre de archivo — busca RUTs en el texto completo del PDF
directamente. Probado con Tesseract.js real contra la página real del
Finiquito de uno de los reportados como "faltante": se lee perfecto (RUT
correcto, frase "Finiquito al contrato de trabajo" detectada). No se
encontró una causa de código — probablemente una corrida vieja/parcial
vista en pantalla en medio de los otros incidentes del día. Si vuelve a
reportarse después de una corrida fresca, investigar de nuevo con datos
reales, no asumir que es el mismo bug de Contratos solo por la
coincidencia de síntomas.

## Libro de Asistencia (Antofagasta): no leía Faltas/Permisos/Licencias — solo atribuía la página

El usuario pidió que el Libro de Asistencia (el cuaderno manuscrito, no la
Asistencia Semanal en Excel de otras bases) también verificara si el
trabajador tiene Faltas, Permisos o Licencias marcadas que coincidan con
el Libro de Haberes. Antes de escribir nada, se comparó qué YA existía
para Lo Barnechea (donde el Libro va intercalado dentro de Liquidaciones,
caso MENOS_30) contra Antofagasta (`va_validarLibroAsist`, módulo
dedicado):

- **Lo Barnechea YA tenía esto** (`libroFaltasIA`/`libroPermisosIA`/
  `libroLicDiasIA`/`libroNotasIA` en `va_liqMap`, poblados por el prompt de
  IA dentro de `va_validarLiquidaciones`, comparados en
  `va_renderLibroDetalle` contra `w.inasistencias`/`w.permisos`/
  `w.licencias` — estos últimos sacados del TEXTO de la Liquidación, no
  directo del LH).
- **Antofagasta NO tenía nada de esto** — `va_validarLibroAsist` solo hacía
  atribución de página→trabajador (OCR del nombre, con fallback a IA SOLO
  si el OCR no identificaba a nadie). Nunca leía ni Faltas ni Permisos ni
  Licencias del cuaderno, y nunca las cruzaba contra nada.

**Hallazgo real revisando el Libro de Haberes real de Antofagasta**
(`Documentos Antofagasta/2026-08-17 Libro de haberes Revisión Nuevo
2026-07-01.xlsx`, fila 6 = encabezados): el archivo SÍ trae columnas
nativas "Días Permisos" y "Días Ausencias" (al lado de "Días Licencias
(reales)" que ya se leía) — pero `va_cargarLH` nunca las leía. Es decir,
existía una fuente 100% confiable (Excel nativo del LH, no depende de
ningún OCR) para Permisos/Ausencias que el validador ignoraba por
completo, mientras el resto del código solo tenía el sustituto menos
confiable (`w.permisos`/`w.inasistencias`, sacados con regex del texto OCR
de la Liquidación).

**Cambios** (index.html):
1. `va_cargarLH` (~línea 11381+): agrega `iPermisos=col('Días Permisos')`,
   `iAusencias=col('Días Ausencias')` y guarda `permisosLH`/`ausenciasLH`
   en cada fila de `va_lhAll` — misma técnica `col()` tolerante que ya
   usaba el resto (exact match o `.includes` fallback).
2. `va_validarLibroAsist` (~línea 14078+): el prompt de IA que antes solo
   pedía `{"nombre_trabajador":...}` ahora pide el mismo esquema que ya
   usa Lo Barnechea (`faltas`/`permisos`/`licencias_dias`/`notas`) —
   **decisión consciente de costo**: como no hay heurística de OCR/regex
   confiable para marcas manuscritas de días (ya documentado más arriba en
   este mismo Skill), la IA ahora se llama en TODA página con key
   configurada, no solo cuando el OCR falla en leer el nombre — antes
   ~80-85% de páginas ya necesitaban IA (para el nombre); ahora es 100%
   cuando hay key. Los resultados se acumulan en `va_liqMap` con los
   MISMOS nombres de campo que Lo Barnechea (`libroFaltasIA` etc.) — si se
   toca el prompt de cualquiera de los dos módulos, revisar si el otro
   también necesita el mismo ajuste (mismo principio ya documentado arriba
   para Licencias Médicas: "cuando dos vías de código hacen lo mismo,
   cualquier fix hay que replicarlo en la otra").
3. `va_renderAntofagastaLibroDetalle` + `va_exportExcel` (hoja
   `LibroAsist`): nueva sección "Faltas / Permisos / Licencias — Libro vs
   Libro de Haberes", comparando contra `x.ausenciasLH`/`x.permisosLH`/
   `x.diasLic` (las columnas nativas del LH, no el sustituto de
   Liquidaciones) — el cálculo se hace UNA vez dentro de
   `va_validarLibroAsist` (`d.detalleFPL`) y tanto el panel como el Excel
   lo reusan, para no duplicar la lógica de comparación en dos lugares.

**No se pudo validar de punta a punta con datos reales en este sandbox**
(misma limitación de siempre: Tesseract.js/render de PDF real no corre acá,
y la key de MiniMax real no se puede cargar en el navegador sandbox) — se
verificó sintaxis (index.html carga sin errores de consola) y que los
nombres de campo/flujo de datos son consistentes con el patrón ya probado
de Lo Barnechea. Pendiente que el usuario corra una validación real de
Antofagasta con key de IA configurada y confirme: (a) que aparecen
conteos de Faltas/Permisos/Licencias por página en el detalle, (b) que las
discrepancias contra el LH tienen sentido comparándolas a mano contra 2-3
páginas reales del cuaderno, y (c) el costo/tiempo real de IA con el
prompt ampliado en TODA página (antes ~80-85%, ahora 100% de las páginas
con key configurada) — si el tiempo total sube demasiado, la primera
palanca a considerar es acotar esto por archivo/letra en vez de revertir
la funcionalidad completa.

## Corrida real de 318 páginas del Libro (Antofagasta): 30+ min, y la IA alucinaba "Licencia: 31" en un mes 100% trabajado

El usuario corrió el validador real después de las mejoras de esta sesión y
reportó dos problemas serios sobre el módulo de Faltas/Permisos/Licencias
del Libro de Asistencia (agregado más arriba en este mismo Skill, sección
"Libro de Asistencia (Antofagasta): no leía Faltas/Permisos/Licencias"):

1. **Regresión de rendimiento, autoinfligida**: esa misma mejora había
   cambiado el gate de IA de `va_validarLibroAsist` de "solo si el OCR no
   identificó a nadie" (~80-85% de las páginas) a "SIEMPRE, en toda página
   con key configurada" (100%) -- para poder leer Faltas/Permisos/Licencia
   incluso en páginas donde el OCR ya identificaba bien el nombre. Con 318
   páginas reales, esto llevó la corrida a más de 30 minutos -- reportado
   por el usuario como demasiado lento. **Revertido** a "IA solo si el OCR
   falló" -- vuelve al ~80-85% original. Costo real del revert: las páginas
   donde el OCR YA identifica al trabajador (fuente='OCR') se quedan sin
   lectura de Faltas/Permisos/Licencia esa corrida (caen en "sin conteo
   IA"). Sin este dato no se puede paralelizar de verdad DENTRO de un mismo
   archivo (ver sección "Paralelización de Liquidaciones" más arriba para
   el precedente de por qué esto no se intentó a la ligera) -- pendiente
   si se pide recuperar esa cobertura sin repetir el problema de velocidad.

2. **La IA alucinaba licencias médicas que no existen -- confirmado
   mirando la imagen real, no solo el texto OCR**. El caso más extremo:
   Arias Gallo Luz Estela (letra A, página 30 real) salió "Licencia LH=0
   vs Libro=31" -- un mes ENTERO de licencia médica que el LH dice que no
   existe. Se renderizó la página real a PNG y se miró directamente (no el
   texto OCR, que en un cuaderno manuscrito sale ilegible igual): es una
   planilla de firma de ENTRADA/SALIDA normal, con los 31 días del mes
   trabajados, donde la trabajadora firma su propio nombre de pila ("Luz")
   en cada casilla de entrada Y salida -- NO HAY ninguna marca de Falta,
   Permiso o Licencia en toda la hoja. La hipótesis más plausible: el
   prompt original le pedía a la IA contar marcas de "Licencia"/"L", y ver
   "LUZ" escrito ~60 veces en la página (31 días × 2 firmas) parece haber
   disparado que la IA asociara esa "L" repetida con licencias, en vez de
   reconocerla como la firma normal de la trabajadora.

   **Fix**: se reescribió el prompt de `va_validarLibroAsist` (y por
   consistencia, quedó pendiente aplicar el mismo criterio al prompt
   gemelo de Lo Barnechea si vuelve a aparecer el mismo síntoma ahí) con
   guardarraíles explícitos: (a) describe la estructura real de la
   planilla (fila por día, columnas Entrada/Salida con hora+firma, firmar
   con el propio nombre es NORMAL); (b) exige que la marca de ausencia sea
   la PALABRA COMPLETA ("Falta"/"Permiso"/"Licencia" o su abreviación
   estándar) ocupando el lugar de la firma, no una letra suelta parecida
   al nombre del trabajador; (c) ejemplo explícito con el caso real
   (trabajador que se llama "Luz" y firma "Luz" cada día NO es una
   licencia); (d) instrucción explícita de preferir 0 ante la duda en vez
   de inventar.

   **No se pudo re-ejecutar la corrida real para confirmar que el prompt
   nuevo arregla esto** (mismas limitaciones de sandbox de siempre) --
   pendiente que el usuario corra de nuevo y compare los números de
   Faltas/Permisos/Licencias contra el LH. Dado que ESTE fue el primer uso
   real en producción de una funcionalidad agregada la misma sesión (sin
   validación previa contra una corrida completa), conviene tratar
   cualquier resultado de este módulo con escepticismo hasta tener una
   segunda corrida real que lo confirme -- mismo principio que "una
   corrida real encuentra bugs que ninguna muestra chica encuentra", ya
   documentado varias veces arriba en este Skill.

**Lección nueva**: cuando se le pide a un LLM visual que cuente ocurrencias
de una letra/código corto (ej. "L" de Licencia) en una imagen con texto
manuscrito repetitivo (firmas), hay riesgo real de que confunda el código
buscado con texto NORMAL que casualmente se parece (el propio nombre del
trabajador, sobre todo si es corto o empieza con la misma letra) -- pedir
la palabra completa en vez de la abreviación de una sola letra, y dar un
ejemplo explícito del falso positivo más probable, reduce mucho este
riesgo.


## Contratos Antofagasta: el gate de IA solo cubría "no vi nada" (23-08-2026)

Reporte del usuario: el panel de Contratos "dice que no hay" documentos que
sí existen, y duda de que la calidad de detección de firma que se logró en
Liquidaciones haya llegado también acá. Al comparar los dos módulos
aparecieron tres diferencias reales, no una:

1. **El gate de IA violaba la regla 3 de `politica-ia.md`.** Era
   `if(!firmantes.length && !firmaFisicaTrab && !firmaFisicaEmp && iaKeyOk)`:
   bastaba detectar UNA de las dos firmas para que la página no llegara nunca
   a la IA, y la otra quedaba en "no firmada" sin que nadie la mirara. Ese
   gate solo podía corregir el error "no vi nada"; jamás el error "dije que
   sí/no sin fundamento" -- exactamente la falla que produjo los 326/330
   falsos positivos de firma en Liquidaciones, acá en la dirección contraria
   (falsos faltantes).
2. **No existía banda ambigua.** `va_detectarFirmaFisicaPorEtiqueta` devolvía
   un booleano pelado. Un 0,8% de tinta (justo debajo del umbral de 1%) se
   reportaba como "sin firma" con la misma seguridad que un 0%.
3. **`sin_etiqueta` se perdía en silencio.** Si el OCR no encontraba la
   etiqueta "TRABAJADOR"/"EMPLEADOR", la función devolvía `false`. En
   Liquidaciones ya está medido que la causa típica de eso NO es que no haya
   firma, sino al revés: una firma grande y oscura tapa su propia etiqueta.

**Fix**: `va_medirFirmaFisicaPorEtiqueta` (nueva) devuelve
`{firmada, ratio, motivo, zona}` con el mismo vocabulario de motivos que la
firma de Liquidación (`'sin_etiqueta'` | `'banda_ambigua'` | `null`).
`va_detectarFirmaFisicaPorEtiqueta` queda como envoltorio booleano para los
dos call sites viejos (Contrato dentro del PDF de Liquidaciones, Lo
Barnechea), sin cambio de comportamiento.

Los UMBRALES ya validados no se tocaron (1% arriba de la etiqueta, 3% debajo
de la línea del RUT). Lo que se agregó es una banda ambigua que **cruza** cada
umbral -- 0,6%–1,6% y 2,4%–4,0% -- donde la tinta igual da su veredicto
provisional pero la página se marca para que la IA lo confirme o lo desmienta.
Dentro de la banda la IA manda en las dos direcciones; fuera de ella un
positivo firme de tinta no se deja borrar (regla 4). Sin key configurada se
conserva el veredicto de la tinta y la duda queda anotada en
`docs[tipo].dudas`, visible en el panel y en el Excel -- nunca se afirma un
faltante que nadie verificó.

Verificado con canvas sintético contra la función real en el navegador:
0% y 0,4% → `false` concluyente (no gasta IA) · 0,8% → `false` +
`banda_ambigua` (escala) · 1,3% → `true` + `banda_ambigua` (escala) · 3% →
`true` concluyente · 90% → `false` (zona negra corrupta, no firma) · sin
etiqueta → `sin_etiqueta`. El envoltorio booleano sigue dando lo mismo que
antes en todos los casos.

**Además, lo que hacía indistinguible "no está" de "no se pudo leer"**: el
loop hacía `if(!tipoActual||!worker)continue;` sin dejar ningún rastro. Un
trabajador cuyo contrato SÍ estaba en el PDF pero cuya página no se pudo
atribuir terminaba en "Sin archivo de contrato", idéntico a uno que
efectivamente no trajo el documento. Ahora se cuenta y se muestra:
`diag.pagsSinTitulo`, `diag.pagsSinWorker`, `diag.ambiguas`,
`diag.sinEtiqueta`, `diag.pagsIA`, `diag.pagsIATope`, un desglose por archivo
(páginas / títulos / atribuidas / sin atribuir / trabajadores) y la lista de
RUTs de contratos que pertenecen a trabajadores del LH que **no** son
ingresos del período (por eso no se exigen, pero antes esas páginas se
descartaban sin decir nada).

El panel y la hoja `Contratos` del Excel pasaron de una frase de texto
("falta ANEXO_HHEE") a una **identificación documento por documento**:
Contrato / Anexo de Cargo / Anexo Pacto HH.EE., cada uno con NO ENCONTRADO /
SIN NINGUNA FIRMA / FALTA FIRMA TRABAJADOR / FALTA FIRMA EMPLEADOR / OK ambas
firmas, más las páginas donde apareció y el archivo de origen.

Tope opcional de llamadas: `window.VA_IA_CONTRATO_MAX` (por defecto sin
tope), mismo patrón que `VA_IA_FIRMA_MAX` de Liquidaciones. Lo que queda
fuera del tope se cuenta en `diag.pagsIATope` y se muestra como "sin
verificar", nunca como faltante.

**Sigue sin validarse de punta a punta con documentos reales**: Tesseract.js
no arranca en el navegador sandbox (`Tesseract.createWorker` falla, ya
documentado en la entrada del Libro de Asistencia). Pendiente que el usuario
corra Antofagasta con key de IA y confirme cuántos de los "no encontrado"
actuales pasan a identificarse.
