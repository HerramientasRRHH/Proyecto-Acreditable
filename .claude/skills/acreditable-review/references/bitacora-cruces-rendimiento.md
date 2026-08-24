# Bitácora — Cruces de documentos, rendimiento y decisiones revertidas

> Parte del skill `acreditable-review`. Registro histórico de hallazgos REALES con su
> evidencia — se lee **solo cuando se está trabajando en este módulo**, no en cada sesión.
> El proceso de auditoría y la política de IA viven en `SKILL.md`.
> Las secciones están en orden cronológico: si dos se contradicen, gana la más nueva
> (varias documentan código que después se revirtió y lo dicen explícitamente).

## Trampas encontradas al auditar una carpeta completa (no solo un caso puntual)

Cuando el pedido es "revisá/integrá todo lo que hay en esta carpeta" en vez
de "arreglá este caso puntual", además del proceso de arriba conviene
chequear estas cosas — todas se encontraron auditando Antofagasta carpeta
por carpeta contra documentos reales, ninguna se ve leyendo el código solo:

- **Un mismo PDF puede mezclar formatos distintos en páginas distintas.**
  El "Licencia médica" de Antofagasta arranca con un listado tabular
  (varias filas por página) y sigue con comprobantes individuales de
  respaldo (Caja18) — el parser tiene que reconocer AMBOS o al menos no
  romperse con el que no maneja. No asumas que todo el archivo sigue el
  mismo layout que la primera página que viste.
- **Una página puede estar físicamente escaneada boca abajo.**
  `page.rotation` del PDF puede decir 0 (sin flag de rotación) mientras el
  contenido real está invertido 180° — un error de quien alimentó la hoja
  al scanner, no metadata del PDF. El síntoma es un OCR que da texto
  irreconocible/espejado. `va_ocrPaginaMejorRotacion()` prueba 0° y 180° y
  se queda con el que tenga más coincidencias de fecha/palabras clave —
  reusala en vez de asumir que la orientación siempre viene bien.
- **Los topes de página de `va_getPdfTextOCR(buf, maxPagesOCR)` NO son
  "leer las primeras N páginas".** Si el PDF completo tiene MÁS páginas que
  `maxPagesOCR`, se salta el OCR de TODO el archivo (es un freno de
  rendimiento, no un límite de lectura parcial). Un documento con más
  páginas de las esperadas para esa función (ej. un listado de 95 páginas
  contra un tope viejo de 10) queda totalmente sin leer, no parcialmente —
  hay que subir el tope, no asumir que "algo se lee igual".
- **Verificá que el ID del documento esté excluido del sweep genérico**
  (`va_validarGenerico`, loop en `va_ejecutar`) antes de agregar una función
  de validación dedicada nueva — si no, el resultado dedicado se pisa
  silenciosamente después de correr (encontrado con 'contratos': el bug ya
  existía para Vitacura, no introducido por el cambio de Antofagasta, pero
  hay que revisarlo cada vez que se agrega una función nueva para un slot
  que ya existía).

## Rendimiento: buscá OCR duplicado antes de pensar en paralelizar

El usuario reportó Antofagasta tardando más de una hora en su navegador
real. Antes de saltar a algo grande (pool de workers Tesseract en paralelo),
grepeá `textoUtil`/`txtLen` en la función sospechosa: si la variable que
decide "¿hace falta OCR/otro OCR acá?" se declara `const` a partir del texto
NATIVO del PDF y nunca se actualiza después de que el OCR tiene éxito,
cualquier chequeo posterior que la reuse (ej. una "red de seguridad" pensada
para un subconjunto chico de páginas, como licencia médica) va a disparar en
TODAS las páginas escaneadas, no solo las que de verdad lo necesitan — un
doble OCR completo (render + recognize) silencioso y sistemático. Así se
encontró en `va_validarLiquidaciones` (409 páginas en Antofagasta, la red de
seguridad de Licencia Médica se disparaba en casi todas). El fix es trivial
(`const`→`let`, reasignar tras el OCR) y CERO riesgo para los resultados —
no toca ninguna clasificación ni detección, solo evita repetir OCR ya hecho.
`va_validarLicenciasMedicas` ya usaba `let txtLen` correctamente — sirve de
referencia de cómo se ve el patrón bien hecho.

Lo que SÍ queda pendiente y es una mejora más grande (no se intentó esta
sesión): todo el pipeline usa un único `ren_ocrWorker` (un solo worker
Tesseract), así que el OCR está 100% serializado aunque distintos ARCHIVOS
sean independientes entre sí (cada archivo de Liquidaciones/Contrato/Libro
resetea su propio estado pegajoso — `currentRut`, `tipoActual` — al empezar,
así que los archivos SÍ se podrían procesar en paralelo entre ellos, aunque
las páginas DENTRO de un mismo archivo deban seguir en orden). Un pool de
2-4 workers Tesseract + correr los archivos de un mismo slot con
`Promise.all` en vez de un `for` secuencial podría dar una mejora real
adicional — pero no se implementó porque el navegador sandbox de Claude Code
resultó tener renderizado de PDF anormalmente lento incluso SIN OCR de por
medio (>30s para renderizar una sola página), así que no hay forma de medir
ni validar el cambio acá — haría falta probarlo en un navegador real.

## Documentos con casillas de RUT manuscritas: mirá el nombre antes de gastar IA

Caso real (Lo Barnechea, formularios AFP de Exención de Cotizar): el RUT
viene escrito a mano en casillas separadas ("RUT| |7[1[9"), que el OCR
destroza sistemáticamente — pero el NOMBRE está impreso/tipeado cerca
("Barraza Espinoza / Carmela de la Merced") y el OCR sí lo lee bien. El
código ya tenía niveles gratis para el RUT (regex + ventana de checksum)
antes de cortar a IA, pero ninguno miraba el nombre — se agregó un nivel
extra: probar cada línea (y pares de líneas consecutivas, por si el layout
separa Apellidos/Nombres) contra la nómina de referencia con
`va_matchNombreNomina`, ANTES de gastar una llamada a IA. Con el documento
real: 4 de 6 páginas que antes necesitaban IA se resuelven así, gratis — las
otras 2 genuinamente no tienen texto legible ni de RUT ni de nombre (esas sí
necesitan IA). Mismo principio ya usado en el Libro de Asistencia de
Antofagasta ("si no lee el RUT, mirá el nombre") — aplicable a cualquier
documento nuevo con esta misma estructura (RUT en casillas + nombre
impreso cerca).

## Paralelizar OCR por archivo: el patrón que sí se pudo probar, y el que no

Se implementó paralelismo real (varios workers de Tesseract a la vez, cada
uno tomando el SIGUIENTE archivo libre de una cola) para `va_validarLibroAsist`
como piloto — quedan pendientes Contratos y Liquidaciones con el mismo
patrón. Infraestructura nueva junto a `cargarOCR()`: `va_ocrPool` (array de
workers), `va_cargarOCRPool(n)`, `va_procesarArchivosEnParalelo(items,
poolSize,procesarUno)`.

**El truco clave para no reescribir la lógica interna**: la función se separó
en un `async function procesarArchivoX(buf,worker){ const ren_ocrWorker=worker;
... }` — esa única línea de "shadow" (una `const` local con el MISMO nombre
que la variable global `ren_ocrWorker`) hace que TODO el código de adentro
(que ya usaba `ren_ocrWorker.recognize(...)` en varios lugares) automáticamente
use el worker que le tocó a ESE archivo, sin tener que buscar y reemplazar
cada referencia una por una. Bajo riesgo porque el cuerpo interno queda
copiado tal cual, carácter por carácter — el único cambio real es la firma
de la función y este shadow.

**Qué SÍ se puede paralelizar así**: solo si no hay estado que dependa del
ORDEN entre archivos distintos (`va_liqMap`, contadores compartidos como
`totalPags`, `va_iaAuditLog` — todos son seguros entre tareas async
concurrentes en JS de un solo hilo, no hace falta lock). Sí tiene que
importar el orden DENTRO de un mismo archivo si ese archivo tiene estado
pegajoso entre sus propias páginas (`tipoActual` en Contratos, `currentRut`/
`enContratoHasta` en Liquidaciones) — por eso el patrón reparte ARCHIVOS
completos por worker, nunca páginas sueltas de un mismo archivo.

**No se pudo probar de punta a punta en el sandbox de Claude Code** — dos
obstáculos reales, no simulados:
1. El renderizado de PDF (`page.render()`) es anormalmente lento acá incluso
   sin OCR de por medio (>30s por página), así que correr archivos reales
   completos para medir tiempo no es viable.
2. **`pdfjsLib.getDocument` no se puede sobreescribir/mockear** en este
   entorno — `pdfjsLib.getDocument = miStub` no tira error pero tampoco
   cambia nada (`pdfjsLib.getDocument !== miStub` después de la asignación,
   confirmado directo en consola). Esto bloqueó armar un test rápido con
   PDFs falsos para probar la lógica de reparto sin la lentitud del
   renderizado real.

Lo que SÍ se validó: (a) `va_procesarArchivosEnParalelo` reparte bien una
cola de items entre N workers (probado con items sintéticos, sin PDF de por
medio — todos los índices se procesan exactamente una vez, sin duplicados ni
saltos); (b) con buffers inválidos reales, `procesarArchivoLibro` sí llega a
llamar `pdfjsLib.getDocument` y maneja el error correctamente (confirmado
agregando un log temporal adentro de la función, después removido). No se
pudo confirmar el resultado final contra datos reales ni medir la mejora de
velocidad — hace falta que el usuario lo corra real y reporte.

## Una corrida real en producción encontró 6 bugs que ninguna auditoría con datos de muestra había visto

El usuario corrió el validador real (con su propia API key, en su propio
navegador) contra Antofagasta completo y bajó el Excel exportado — comparar
ESE Excel real contra lo que la app mostraba en pantalla (screenshot) destapó
varios bugs que las auditorías anteriores (con muestras chicas, o simulando
en Python) no habían agarrado. Lección: una corrida completa real, con
export a Excel, encuentra clases de bug que una muestra no encuentra —
sobre todo bugs de "cablear el número equivocado" que no dependen de que el
OCR/IA lea bien o mal.

1. **RUT normalizado con dos formatos incompatibles en la misma función**
   (`va_validarImput`): un normalizador LOCAL sacaba el guión
   ("123456789") mientras el resto de la app usa `va_normRut` que lo
   mantiene ("12345678-9") — el cruce daba 0% de coincidencia SIEMPRE,
   aunque ambos lados tuvieran los mismos RUT reales. Cuando una función
   define su PROPIO normalizador de RUT en vez de reusar `va_normRut`,
   sospechá de esto primero si el cruce da un 0% sospechoso con datos que a
   simple vista deberían calzar.
2. **`XLSX.read()` no lanza excepción con un buffer que NO es Excel** — en
   `va_validarMujeres`, el patrón "probar como Excel, si tira error caer a
   OCR de PDF" nunca caía al OCR real porque SheetJS lee un PDF sin fallar
   y devuelve un workbook vacío/basura. Con un slot que acepta más de un
   tipo de archivo (`.pdf,.xlsx,.xls`), decidí SIEMPRE por la extensión real
   del archivo (`dd.files[i].name`), nunca por si una librería permisiva
   tira o no una excepción.
3. **Bug de orden en una cadena de `else if` de dispatch de tabs**
   (`va_subtab`): había un `else if(['jubilados','librorem','libroasist',
   'mujeres','discapacidad'].includes(tab)...)` que agarraba 'libroasist'
   ANTES de que la rama específica de Antofagasta (unas líneas más abajo)
   pudiera evaluarse — así que el módulo de Libro Asistencia de Antofagasta
   se renderizaba con la función GENÉRICA (`va_renderAntTab`, campos
   `pagsEsperadas`/`ratio` que ni existen en ese resultado) en vez de la
   dedicada (`va_renderAntofagastaLibroDetalle`, campos reales
   `esperados`/`totalPags`/`identificados`) — de ahí el "0 páginas
   esperadas · 0% cobertura" en pantalla mientras el texto de nota (que sí
   usa el campo correcto `nota`) mostraba los números reales al lado. Ante
   un KPI en 0 que contradice el texto de la misma tarjeta, sospechá
   SIEMPRE de un problema de qué función renderiza, no de qué encontró la
   validación — son cosas separadas y hay que confirmar cuál función
   realmente corrió.
4. **El exportador de Excel genérico para los "otros documentos de
   Antofagasta" asume la forma `{rutsDoc,rutsLH,coincidencia}`** de un
   cruce por RUT — pero Libro Asistencia matchea por NOMBRE (OCR/IA), su
   resultado tiene campos totalmente distintos (`esperados`,
   `identificados`, `totalPags`). El exportador genérico caía en sus
   fallbacks (`dd.totalPags||0`, `dd.coincidencia||dd.cubiertos||0` → 0) y
   sacaba "RUTs en doc: 338, Coincidencia: 0" con datos reales sanos atrás.
   Cuando un módulo no calce con la forma que asume un exportador/render
   genérico, dale hoja/función propia en vez de forzarlo a los mismos
   nombres de campo.
5. **Exención de Cotizar y Jubilados daban números DISTINTOS para
   poblaciones que deberían ser casi la misma** — resultó que el usuario
   había cargado el Impositivo.pdf en el slot separado 'exencion' (que
   YA habíamos decidido, en una sesión anterior, que no hace falta para
   Antofagasta — está cubierto por Jubilados). Se sacó el slot 'exencion'
   de la config de Antofagasta directamente, para que no quede la opción de
   volver a cargar ahí un archivo que después confunde comparando contra
   otro módulo que en teoría mide lo mismo.
6. **Tesseract.js usa por defecto el paquete de idioma "fast" (liviano,
   menos preciso)**, no "best" — nunca se había configurado explícitamente.
   Dado que este proyecto lee manuscritos y escaneos de mala calidad todo
   el tiempo, se cambió a `langPath:'https://tessdata.projectnaptha.com/4.0.0_best'`
   en `cargarOCR()`. Es un cambio barato (una línea) con impacto
   potencialmente amplio — sospechá de esto como causa raíz compartida
   cuando VARIOS módulos distintos "no leen bien" al mismo tiempo con
   documentos que en una prueba con Python (que usa el Tesseract nativo,
   normalmente con el paquete "best" del sistema) sí leían bien. No se pudo
   medir la mejora real de precisión en el sandbox de Claude Code — hay que
   confirmarlo con una corrida real del usuario.

## Checklist por carpeta (A-M) no es solo "está/no está" — puede haber slots sin cablear

Auditando Antofagasta carpeta por carpeta (letras A-M según la nomenclatura
real de carpetas del usuario) salieron hallazgos que vale la pena dejar
documentados porque el patrón se va a repetir:

- **No todas las carpetas del cliente corresponden a un documento de RRHH.**
  A) Carta solicitud estado de pago, B) Factura, C) OC (Portal Mercado
  Público), D) Autorización Estado de Pago, L) Comprobante pago de multas son
  documentación de pago/facturación municipal, no de cumplimiento laboral —
  confirmado con el usuario ("eso no lo integres no aplica a RRHH"). No les
  busques slot ni función de validación.
- **Un doc "sin auditar todavía" puede ya estar bien resuelto por una función
  genérica compartida.** Previred de Antofagasta (73 pág, texto nativo) ya
  pasaba al 100% (352/352 RUT) por `va_validarCruceDoc('previred',...)`
  — la misma función que usa Lo Barnechea, corrida sin condicional de base.
  Antes de escribir lógica nueva para un doc, confirmá con datos reales que
  la función genérica compartida ya no lo resuelve.
- **Puede existir un slot Y su función de lectura, sin estar cableados al
  resultado final.** El slot `cartanofirma` (label "Carta No Firma") y
  `va_validarCartaNoFirma()` ya extraían los RUT de la carta a
  `va_docResults['cartanofirma'].cartaRuts` — pero `va_clasificar()` nunca lo
  leía, así que no bajaba el estado SIN_FIRMA de nadie. Grepeá el nombre del
  slot/función en TODO el archivo antes de asumir que hace falta escribir
  algo desde cero — puede que solo falte una línea de cruce.
- **Un "carta explicativa" real puede venir intercalada DENTRO del mismo PDF
  que documenta, no solo como archivo aparte.** En Liquidaciones de
  Antofagasta, la página "no firmó su liquidación... debido a vacaciones"
  aparece tanto en un PDF separado (`cartas explicativas de vacaciones.pdf`)
  como pegada justo después de la liquidación del mismo trabajador dentro del
  PDF por letra — el detector tiene que buscar el patrón de texto en
  CUALQUIER página del slot compartido (acá `liq`), no asumir que vive en un
  archivo dedicado. Regex usado: `/no\s+firm\w*\s+su\s+liquidaci[oó]n/i`
  (`\w*` para cubrir firmo/firmó/firma/firmaron sin perseguir cada conjugación).
- **Los slots "carta explicativa" son baratos de sumar por comprobante Y por
  carta — no asumas que un doc sin firma solo necesita el comprobante.**
  Pedido explícito del usuario: liquidación sin firma en Antofagasta exige
  comprobante de pago (ya existía, `esComprobanteText`/`tieneComprobante`) Y
  carta explicativa del motivo (nuevo, `tieneCartaNoFirmaLiq`) — las dos
  vías (inline en `liq` o slot dedicado `cartanofirma`) cuentan como válidas.
- **Un archivo .docx real (no .pdf) puede ser la única forma en que llega una
  carta explicativa** (ej. "carta explicativa Fe de Erratas.docx" del Libro
  de Asistencia — tabla N°/Nombre/RUT/Caso con la descripción de cada
  corrección manuscrita). La librería `docx@8.5.0` ya cargada en el proyecto
  es solo para ESCRIBIR Word, no sirve para leer — pero `JSZip` (también ya
  cargada) sí permite leerlo: un .docx es un .zip con `word/document.xml`
  adentro, y el texto vive en tags `<w:t>`. Ver `va_readDocxText()`. Al
  reconstruir texto con saltos de línea por fila de tabla, cortá SOLO en
  `</w:tr>` (fin de fila) — cortar también en `</w:p>` (fin de párrafo/celda)
  rompe cada fila en fragmentos de una sola celda ("9 Alballay..." queda
  separado de su propio RUT). Validado contra el archivo real: 18/18 filas
  extraídas con RUT + nombre + motivo correctos.
- **No hay forma automática de saber si una página del Libro TIENE una
  anotación manuscrita al pie** sin visión (no hay heurística de texto/OCR
  confiable para eso) — el alcance honesto es: leer y mostrar la carta
  explicativa (RUT + motivo) al lado del módulo del Libro para que quien
  revisa cruce manualmente contra el cuaderno físico, no prometer un cruce
  automático que no se puede validar con lo que hay hoy.

## Escalera de confianza: medir cuánta IA se gasta de verdad, no intuirlo

Inspirado en el diseño de `MOTOR VISUAL MULTICAPA` (proyecto Python separado
del usuario, `perception/confidence_router.py`/`escalation.py`): cada vez que
un módulo con niveles "gratis primero, IA al final" (Exención de Cotizar,
Libro de Asistencia Lo Barnechea y Antofagasta) resuelve una página, llama a
`va_registrarResolucion(modulo, via)` con `via` ∈ `'gratis'|'ia'|'sinResolver'`
(cualquier string que no sea `'gratis'`/`'ia'` cuenta como `sinResolver`) —
solo incrementa contadores en `va_iaMetricas[modulo]`, no cambia ninguna
decisión existente. `va_renderIAAuditSection(nombreModulo)` (que ya se
renderiza al final del detalle de cada módulo) ahora muestra un resumen
"📊 De N resoluciones: X sin gastar IA (Y%)" **incluso si el módulo se
resolvió 100% gratis y nunca dejó una entrada en `va_iaAuditLog`** — antes
esos casos (los más interesantes: "no hizo falta IA para nada") eran
invisibles porque la función devolvía `''` si `va_iaAuditLog` no tenía
entradas para ese módulo.

Al agregar el patrón a un módulo nuevo: llamar `va_registrarResolucion` en
CADA punto de resolución existente (no crear ninguno nuevo), justo al lado
de donde ya se decide el resultado — es una línea agregada, nunca un cambio
de la condición que decide. Verificado en consola del navegador (no hay forma
de correr el flujo completo con archivos reales en este sandbox, ver sección
de abajo): los contadores suman bien y `va_renderIAAuditSection` combina
métricas + detalle sin romper el render existente cuando ambos coexisten.

Reset: `va_iaMetricas={}` se limpia junto con `va_iaAuditLog=[]` al arrancar
`va_ejecutar()` — si se agrega un reset nuevo en otro lugar, no olvidar este.

## Evidencia con página por dato: generalizar el patrón, no reinventarlo por módulo

El Libro de Asistencia (Lo Barnechea) ya guardaba `libroPaginas` (array de
páginas donde se encontró el match de cada trabajador) — se generalizó el
MISMO patrón, mismo shape (`if(!X.campo)X.campo=[]; if(!X.campo.includes(p))
X.campo.push(p);`), a dos módulos más:

- **Licencia Médica inline** (`va_validarLiquidaciones`, bloque `licMedIA`):
  nuevo campo `licMedPaginas` en el objeto de `va_liqMap` (`wLic`), poblado en
  el mismo punto donde ya se marca `wLic.tieneLicMed=true` — sea que `wLic`
  venga del match por nombre o del rastreo de RUT pegajoso (`w`), ambos casos
  quedan cubiertos porque el campo se agrega DESPUÉS de que `wLic` ya está
  resuelto a uno u otro. Columna "Pág." nueva en la tabla de detalle de
  `va_renderLicencias()` (rama `basesConLicEnLiq`).
- **Exención de Cotizar** (`va_validarExenciones`): a diferencia del Libro,
  acá no hay un objeto persistente por trabajador (`va_liqMap`) — es un
  `Set` plano de RUTs encontrados. Se agregó un `Map` local
  `paginasPorRut`+helper `regPag(rut,p)` dentro de la función, llamado en
  los 4 puntos de resolución (Nivel 1/1.5/1.75/IA, los mismos que ya
  instrumenta la escalera de confianza de arriba), y se expone en
  `va_docResults['exencion'].cubiertosDetalle` (nuevo campo, no reemplaza
  `cubiertos`/`faltantes` que ya existían). El render (`va_renderExencion`)
  lo muestra en un `<details>` colapsado por defecto ("Ver dónde se encontró
  cada uno") — no se agregó una tabla abierta por defecto porque antes no
  existía ningún listado de "cubiertos" en pantalla, solo el contador; una
  tabla nueva abierta habría sido ruido para el caso común (todo ✅).

**Antes de replicar este patrón a un módulo nuevo**: fijarse si ya existe un
objeto persistente por trabajador para ese módulo (`va_liqMap` para todo lo
que vive dentro de Liquidaciones/Libro/Contrato) o si hay que crear un `Map`
local como en Exención — son dos formas del mismo patrón, no dos patrones
distintos, y la decisión depende solo de si el módulo ya tenía ese objeto o
no. Verificado en consola de navegador con datos sintéticos (mismo shape que
los reales): sin duplicados al registrar la misma página dos veces, columna
"Pág." y `<details>` renderizan correctamente.

## Motor de decisión determinista: evaluado, descartado por sobre-generalización

Se evaluó portar el patrón `decision/engine.py` de MOTOR VISUAL MULTICAPA
(cascada pura `findings → PASS/REVIEW/FAIL`) a `va_clasificar()`
(~línea 12535+), asumiendo que 3 ramas (NUEVO, MENOS_30, OK) repetían el
mismo ternario `estado = docsFalt.length?'⚠':'✅'`. Al releer el código con
cuidado ANTES de tocar nada (como pide este mismo proceso), resultó que la
premisa era falsa:

- **OK** sí tiene el ternario limpio.
- **NUEVO** arranca en `'⚠'` fijo y solo sube a `'✅'` si no faltan
  documentos, agregando texto al mensaje en vez de reemplazarlo — nunca
  llega a `❌`. Parecido, pero no igual.
- **MENOS_30** no tiene el patrón en absoluto: el estado queda en `'⚠'`
  fijo siempre, independientemente de si falta el Libro o no — es una
  decisión de diseño (trabajar <30 días ya es de por sí una advertencia),
  no un ternario que se pueda generalizar.

Con solo 1 aparición real del patrón (no 3 casi-idénticas), forzar una
función genérica tipo `va_decidirDoc(findings)` habría requerido un
config-object con tanta rama como el código actual — no es DRY real, es
complejidad nueva a cambio de nada, justo el tipo de riesgo que hay que
evitar al tocar `va_clasificar`. Se decidió NO implementarlo.

**Lección para la próxima vez que se evalúe portar un patrón de MVM (o de
cualquier otro lado) a este código**: la similitud "a simple vista" entre
ramas de `va_clasificar` no alcanza para asumir que comparten lógica —
hay que leer cada rama completa (qué valor por defecto tiene `r.estado`
ANTES del bloque en cuestión, si el mensaje se reemplaza o se le agrega
texto, si `❌` es alcanzable o no) antes de diseñar la abstracción. Mismo
principio que "no arregles adivinando" del resto de este skill, aplicado
a refactors en vez de a bugs de lectura.

## Una corrida real de Antofagasta destapó 4 causas raíz distintas en Mujeres/Discapacidad/Jubilados/Libro

El usuario mandó el Excel exportado de una corrida real (Antofagasta, "Base
única", 2026-08-17) mostrando fallas severas: Mujeres 0.6% (1/175),
Discapacidad 0% (0/6), Jubilados 53.3% (49/92), Libro Asistencia con
`viaOCR: 0` (todo pasando por IA pagada). Se auditó cada una con los
documentos reales de `Documentos Antofagasta/` (no con muestras ni
suposiciones) y salieron 4 causas completamente distintas — ninguna era
"la IA lee mal":

### 1. Candado anti-monto rechaza RUT pegado a número de fila (Mujeres, Jubilados)

El fix de esta misma sesión para Libro de Remuneraciones agregó un candado
`(?<![\d.,])` al inicio del Patrón 1 de `va_findAllRuts` (RUT no puede estar
precedido por dígito/punto/coma) para no "morder" RUT reales en tablas
densas de montos. Efecto secundario no anticipado: en tablas con columna
`N°` pegada a la columna RUT, el OCR muchas veces junta ambas sin espacio
(`"119.397.510-0"` = fila `"1"` + RUT real `"19.397.510-0"`) — el candado
rechaza el RUT completo. Confirmado con PaddleOCR contra la página real
(`Dotación femenina.pdf`, confianza 0.94-1.00): la LECTURA era perfecta, el
regex era el problema.

**Fix**: `va_extraerRutConChecksum(linea, referenciaEsperada)` (ya existía,
usado en Exención de Lo Barnechea) como Nivel 1.5, línea por línea, gateado
contra el set de RUT ESPERADOS del módulo (mujeres/jubilados de la nómina)
— nunca "acepta cualquier RUT con checksum válido", solo uno que además
esté en la referencia real. Aplicado en `va_validarMujeres` y
`va_validarJubilados` (y por prevención también en `va_validarDiscapacidad`,
mismo tipo de tabla). Validado: 16/16 RUT rescatados con datos reales de
Mujeres, 0 falsos positivos (incluye sanity check contra líneas de ruido:
headers, nombres, números sueltos → ninguno genera un match espurio).

### 2. Documentos escaneados de costado, 90°/270° (Discapacidad, Libro Asistencia)

`Discapacidad.pdf` y las fotos del Libro de Asistencia vienen con el
contenido rotado ~90° dentro de una hoja en formato vertical —
`page.rotation` sigue diciendo `0` (no es un flag de PDF, es cómo se
alimentó la hoja al escáner/cámara). `va_ocrPaginaMejorRotacion` ya existía
para el caso de 180° (boca abajo) pero nunca probaba 90°/270°, y encima
ni `va_getPdfTextOCR` ni el OCR del Libro de Asistencia la usaban.

**Fix**: se generalizó `va_ocrPaginaMejorRotacion(page,scale,angulos,worker)`
para aceptar cualquier lista de ángulos (antes `[0,180]` fijo) — los casos
90°/270° arman el canvas con ancho/alto TRANSPUESTOS respecto al original
(a diferencia de 180°, que mantiene la proporción). Verificado con un test
numérico (sin necesitar screenshot, que no funciona en este sandbox): un
punto dibujado cerca de la esquina inferior-izquierda del canvas original
aparece en la esquina superior-izquierda tras rotar 90°, que es
matemáticamente lo correcto para una rotación horaria.

Se agregó `worker` como parámetro explícito (antes usaba el `ren_ocrWorker`
global directo) — necesario porque esta función, al estar definida afuera,
NO ve la sombra local `const ren_ocrWorker=worker` de un
`procesarArchivoX(buf,worker)` dentro de un pool paralelo (ver sección de
paralelización más abajo) — sin este parámetro, llamarla desde adentro de
un archivo paralelizado usaría el worker global equivocado en vez del que
le tocó a ESE archivo, rompiendo el aislamiento del pool. Default
`worker||ren_ocrWorker` mantiene compatible el único llamado viejo que no
pasaba este parámetro.

Se conecta como fallback de costo acotado (solo si la pasada recta a 0° ya
dio poco texto útil, no en cada página):
- `va_getPdfTextOCR` (usado por Mujeres/Discapacidad/Jubilados/F30/Libro
  Remuneraciones y más) — beneficio amplio, un solo punto de cambio.
- El OCR de `TRABAJADOR_RE` en el Libro de Asistencia de Antofagasta
  (`va_validarLibroAsist`), pasando explícito el `ren_ocrWorker` LOCAL del
  archivo (ver el problema del parámetro `worker` arriba).

### 3. Jubilados de Antofagasta = mismo formulario que Exención de Lo Barnechea, sin la misma resiliencia

`Jubilados.pdf` (95 páginas) mezcla 3 páginas de listado tabular (mismo
problema #1 de arriba) con ~90 páginas de certificado individual AFP —
estructuralmente IDÉNTICO al formulario de Exención de Cotizar ya resuelto
en Lo Barnechea (RUT dentro de una casilla que el OCR tiende a destrozar,
nombre impreso cerca que se lee bien). Pero `va_validarJubilados` nunca
tuvo el nivel de fallback por nombre que `va_validarExenciones` sí tiene
— se portó el mismo patrón (Nivel 1.5 checksum + Nivel 1.75 nombre, línea
y par de líneas consecutivas) validado con un caso sintético que reproduce
el escenario real (RUT con dígitos confundidos por letras vía OCR, nombre
en líneas separadas Apellidos/Nombres) — rescata correctamente por nombre
cuando ni el regex ni el checksum encuentran nada.

**Lección**: cuando dos bases usan el MISMO tipo de documento de origen
(acá, formulario AFP de exención), la resiliencia de lectura que ya se
validó en una debería portarse a la otra directamente, no reinventarse
desde cero con menos niveles — `va_validarJubilados` llevaba toda la
sesión con un solo nivel (regex puro) mientras el equivalente de Lo
Barnechea ya tenía 4.

### 4. Código muerto: doble definición de va_getPdfTextOCR

Existían DOS `async function va_getPdfTextOCR` en el archivo — en JS, la
SEGUNDA declaración con el mismo nombre en el mismo scope gana siempre, así
que la primera (sin parámetro `maxPagesOCR`) nunca se ejecutaba pasara lo
que pasara. Se eliminó para que no haya ambigüedad sobre cuál función
editar la próxima vez.

## Un fallback "barato por página" puede ser carísimo a escala del documento — medí el peor caso, no solo el caso típico

El fallback de rotación (0/90/180/270°) de la sección anterior se conectó
en dos lugares sin pensar el PEOR caso, y una corrida real de Antofagasta
quedó colgada ~3 horas antes de que el usuario avisara:

- **`va_getPdfTextOCR`** es compartida por documentos CHICOS (Discapacidad,
  7 páginas) y GRANDES (Jubilados, 95 páginas; F30, Libro Remuneraciones).
  "4 OCR completos extra por página que falla" es aceptable en 7 páginas y
  catastrófico en 95 — sobre todo porque las ~90 páginas de certificado
  individual de Jubilados son justo el tipo de página que dispara el
  umbral (`<40 caracteres útiles`) sin estar necesariamente rotadas (texto
  dentro de casillas, sellos superpuestos). **Fix**: el fallback pasó a ser
  OPT-IN (`va_getPdfTextOCR(buf,maxPagesOCR,intentarRotacion)`, default
  `false`) — solo lo activa el llamador de Discapacidad, el único
  confirmado chico. Los otros 8 llamadores (Jubilados, F30, Libro Rem.,
  etc.) quedan con el comportamiento de siempre, sin este costo.
- **Libro de Asistencia de Antofagasta** dispara su reintento cuando
  `TRABAJADOR_RE` no matchea — pero ese regex YA falla en **~80-85% de las
  páginas** por diseño (la mayoría son cuadernos manuscritos, no fotos
  rotadas — dato ya documentado arriba en este mismo Skill). Agregarle un
  reintento de 4 ángulos a esa proporción multiplica el costo de OCR de
  TODO el Libro (cientos de páginas entre todas las letras) varias veces.
  **Fix**: se sacó por completo — la página ya cae al fallback de IA que
  YA funciona, no hacía falta la rotación ahí.

**Lección para la próxima vez que se agregue un fallback "más caro pero
más preciso"**: antes de conectarlo, preguntate (a) ¿con qué frecuencia
real se va a disparar? (si el gate ya se sabe que falla en la mayoría de
los casos — como acá, 80-85% — un fallback caro ahí NO es un fallback
raro, es el camino común) y (b) ¿cuál es el documento más grande real que
pasa por esta función compartida? Un costo "aceptable por página" hay que
multiplicarlo por el peor caso de páginas antes de conectarlo sin tope, no
asumir que el caso típico representa el peor caso. Esto no se detectó
antes de pushear porque el sandbox no permite medir tiempos reales con
PDFs — la única señal fue el usuario reportando una corrida colgada en
producción. Para cambios de este tipo (fallback caro en un loop de
páginas), preferir bloquear el alcance con un parámetro opt-in explícito
en vez de "activar para todos y ver qué pasa".

## va_getPdfText (sin OCR) vs va_getPdfTextOCR — no todos los módulos usaban la que tiene fallback

El usuario reportó F30-1 "no lo lee por ser un escáner". Causa: `va_validarCruceDoc`
(usada por F30-1 y PreviRed) llamaba a `va_getPdfText(buf)` — una función
que SOLO extrae texto nativo embebido, sin ningún intento de OCR — a
diferencia de la inmensa mayoría de los módulos, que usan
`va_getPdfTextOCR` (con fallback de OCR si hay poco texto). Un F30-1
escaneado (0 texto nativo) daba 0 RUT siempre, sin ningún aviso — el mismo
patrón de "hueco de wiring, no de calidad de OCR/IA" que ya se documentó
varias veces en este Skill.

**Fix**: `va_validarCruceDoc` (F30-1, PreviRed) y su carta explicativa
(`f301carta`) pasaron de `va_getPdfText` a `va_getPdfTextOCR` — mismo
patrón ya probado y seguro de Mujeres/Discapacidad, **sin** `intentarRotacion`
(no hay evidencia de que estos documentos vengan de costado, y después del
incidente de hoy no se prende ese parámetro sin evidencia real). Tope de
100 páginas (cubre PreviRed, hasta 73 páginas reales) para el documento
principal, 30 para la carta explicativa (documento corto).

**Sigue pendiente, mismo hueco, no tocado todavía**: `va_validarGenerico`
(línea ~12530, usado para cualquier `docId` sin validador dedicado) también
usa `va_getPdfText` sin OCR — si algún día un documento que cae en el sweep
genérico reporta "no lo lee" y es un escaneo, es la misma causa.

## Tesseract se pierde en tablas densas — el modo de segmentación de página (PSM) importa

Después de conectar OCR a F30-1/PreviRed (sección anterior), el usuario
probó con el F30-1 real de Antofagasta y siguió fallando (4 RUT de 329,
1.2%) — CON el fix ya desplegado y confirmado. Se investigó con el
archivo real (`B:\Antofagasta\...\F).-F30-1\F 30-1.pdf`, 11 páginas, 100%
escaneado — visualmente limpio, no manuscrito, no rotado).

Primero se confirmó que el documento SÍ es legible (PaddleOCR, vía el
entorno de MOTOR VISUAL MULTICAPA: 95-100% de confianza en la tabla de
trabajadores). El problema apareció al probar con **Tesseract.js real**
(el motor que usa la app, cargado en el navegador vía `cargarOCR()`/
`ren_ocrWorker`, contra la MISMA imagen pre-renderizada a la escala real
de `va_getPdfTextOCR`, scale 2.5): de una página con ~2000 caracteres
útiles, Tesseract en su modo automático (`tessedit_pageseg_mode` default,
PSM 3) solo devolvía **119 caracteres** — leía bien la primera fila de la
tabla ("32 26.378.694-7 Luz Estela Arias Gallo") y después se perdía por
completo, confundido por las líneas divisorias finas de una tabla con
muchas filas por página.

**Diagnóstico**: no es un problema de calidad de imagen ni de rotación —
es que el modo de segmentación AUTOMÁTICO de Tesseract (que decide solo
cómo dividir la página en bloques de texto) falla específicamente con
tablas densas de filas finas. Probado directo contra `ren_ocrWorker` real
con `setParameters({tessedit_pageseg_mode:...})`:
- PSM 3 (automático, default): 1 RUT encontrado, 119 caracteres.
- PSM 6 (bloque uniforme de texto): igual que el default, sin mejora.
- **PSM 4 (columna única de texto de tamaño variable): 46 RUT
  encontrados, 2011 caracteres — la tabla completa.**

También se confirmó que PSM 4 NO rompe páginas que no son tablas (probado
contra la portada del mismo certificado, con logo/texto suelto — sigue
leyendo bien, 1570 caracteres, encuentra los 2 RUT reales de esa página).

**Fix**: nuevo parámetro opcional `psm` en `va_getPdfTextOCR(buf,maxPagesOCR,
intentarRotacion,psm)` — si se pasa, se aplica con `setParameters` ANTES
del `recognize()` y se restaura a `'3'` (default) en un `finally`, para no
dejar el `ren_ocrWorker` compartido en un modo raro que afecte a otros
módulos que corran después en la misma sesión (mismo tipo de cuidado que
ya costó caro hoy con el pool de Liquidaciones). Solo `va_validarCruceDoc`
(F30-1/PreviRed) lo activa (`psm:'4'`) — es el único caso confirmado con
datos reales; no se generalizó a otros módulos sin evidencia.

**Costo**: ~4-5x más lento por página con PSM 4 (~12-14s vs ~3s en la
prueba real) — aceptable para un certificado de ~11 páginas, cada OCR de
más solo se paga si la página ya tenía poco texto nativo (el 99% de las
veces con texto nativo, esto ni se ejecuta).

**Lección**: cuando Tesseract "no lee nada" en un documento que a simple
vista es legible y no está rotado, antes de asumir que hace falta IA
(pagada) probá primero variar `tessedit_pageseg_mode` contra el
`ren_ocrWorker` real — es gratis, es una sola línea, y en este caso fue
la diferencia entre 1 y 46 RUT en la misma página exacta.

## PSM 4 revertido: mejoraba en pruebas aisladas, empeoró en la corrida real

El fix de PSM de la sección anterior (`psm:'4'` para tablas densas) se
probó de punta a punta contra el `ren_ocrWorker` real con la imagen real
del F30-1 (46/46 RUT) — pero en la corrida REAL del usuario, con el fix ya
desplegado, el resultado fue PEOR que antes de agregarlo: 0 RUT
encontrados (antes, sin PSM, ya encontraba 4). Revertido de inmediato
(vuelta a `va_getPdfTextOCR(buf,100)` sin el 4° parámetro) — no se
esperó a entender la causa antes de revertir, dado el patrón repetido hoy
de cambios que se ven bien en una prueba aislada pero fallan en la corrida
real completa.

**Por qué la prueba aislada no alcanzó a predecir esto**: la prueba
usó un `ren_ocrWorker` recién cargado (`cargarOCR()` en una página en
blanco, sin nada más corriendo). En la corrida real, ese mismo worker ya
viene de procesar cientos de páginas (Liquidaciones, Finiquitos,
Licencias) antes de llegar a F30-1 — es la hipótesis más probable (no
confirmada) de por qué `setParameters` o el `recognize` posterior se
comportó distinto: algo relacionado al estado acumulado de un worker de
Tesseract después de mucho uso en la misma sesión, no reproducible en una
prueba aislada de una sola página. **No se pudo confirmar la causa real**
porque este sandbox no permite correr un pipeline completo con PDFs
reales de principio a fin.

**Lección, más fuerte todavía después de este caso**: una prueba aislada
(worker fresco, una sola página) que sale perfecta NO garantiza el mismo
resultado dentro de una corrida real larga, donde el worker compartido ya
acumuló uso. Para cualquier cambio futuro que toque `ren_ocrWorker`
(parámetros, estado, lo que sea) y se vaya a activar en un módulo que
corre DESPUÉS de otros módulos pesados en el mismo pipeline, hay que
decirle esto al usuario explícitamente ANTES de pushear — "esto lo probé
aislado, no puedo garantizar que se comporte igual en una corrida larga
real" — en vez de reportarlo como validado sin esa salvedad.

## "Base única" filtraba por sub-área igual que las bases con varios sectores — perdía gente real

El usuario notó que Cruce 2 (Despedidos F30-1 vs Desvinculados LH) mostraba
10 desvinculados cuando el LH real (`2026-08-17 Libro de haberes...
2026-07-01.xlsx`) tenía 11 con Fecha Término Trabajo. Confirmado con el
Excel real: los 10 mostrados tienen `Sub-área = "Antofagasta Ciudad 2022"`,
el 11° (Torrejón Campusano Felipe Alejandro) tiene
`Sub-área = "Base Antofagasta AK"` — una etiqueta distinta.

Causa: `va_applySector()` filtraba `va_lhFiltered` por coincidencia EXACTA
de texto contra la sub-área configurada en `VA_BASES[base].sectores[sec]`
— sin importar si la base tenía 1 sector configurado ("Base única", como
Antofagasta y Mejillones) o varios (Lo Barnechea, Vitacura, Las Condes).
Para bases de varios sectores esto es correcto (cada sector es una
validación separada de verdad). Para "Base única" es un bug: el nombre ya
promete "no hay división acá", pero el LH real puede traer varias
etiquetas de Sub-área internas igual (distintos frentes de trabajo del
mismo contrato) — y cualquiera que no calzara con el string exacto
configurado quedaba excluido EN SILENCIO de absolutamente todo el
validador (no solo del cruce F30-1 donde se notó), sin ningún aviso.

**Fix**: en `va_applySector()`, si la base tiene un solo sector
configurado (`Object.keys(VA_BASES[base].sectores).length===1`), se usa
`va_lhAll` completo sin filtrar por sub-área — coincide con lo que "Base
única" ya debería significar. Bases con varios sectores reales (verificado
con datos sintéticos que reproducen Lo Barnechea Sector A/C) siguen
filtrando exactamente igual que antes, sin cambios.

**Alcance real del bug** (verificado contra el LH real completo, no solo
el caso reportado): de 341 personas totales, 338 en "Antofagasta Ciudad
2022" y 3 en "Base Antofagasta AK" — el fix agrega esas 3 personas a
absolutamente todos los módulos de Antofagasta (Liquidaciones, Contratos,
Mujeres, Jubilados, etc.), no solo al cruce de F30-1 donde se detectó.
Antes de este fix, esas 3 personas nunca aparecían en NINGÚN resultado de
Antofagasta, ni como cubiertas ni como faltantes — simplemente no
existían para el validador.

## Revertidos los 3 "mecanismos" de MVM y la pestaña Contratos Lo Barnechea — decisión explícita del usuario

Después de la ronda de arreglos reales de lectura (secciones de arriba,
todos disparados por reportes de bugs del usuario), el usuario pidió
volver el archivo al estado de ANTES de evaluar MOTOR VISUAL MULTICAPA,
manteniendo solo las mejoras de lectura/OCR reales. Se identificaron y
revirtieron limpiamente (`git diff eebfb99 8ba7b59 -- index.html` en
reversa, sin conflictos — confirma que ningún arreglo posterior tocó las
mismas líneas):

- **Mecanismo 1** (`va_registrarResolucion`, `va_iaMetricas`, extensión de
  `va_renderIAAuditSection`) — commit `084522b`.
- **Mecanismo 3** (`licMedPaginas`, `cubiertosDetalle` en Exención/
  Licencias — NO confundir con `libroPaginas` del Libro de Asistencia, que
  es de ANTES de MVM, un pedido real del usuario, y sigue existiendo) —
  commit `df24996`.
- **Pestaña Contratos en Lo Barnechea/Las Condes/Mejillones**
  (`va_renderContratosLoBarnechea`, dispatch en `va_subtab`) — commit
  `8ba7b59`.

**Las secciones de este Skill que documentan estos 3 mecanismos (arriba,
tituladas "Escalera de confianza...", "Evidencia con página + confianza
por dato", y "Nueva pestaña Contratos...") describen código que YA NO
EXISTE.** Se dejan como registro histórico de qué se intentó y por qué se
sacó — no como referencia de código actual. Si en el futuro se quiere
retomar alguna de estas ideas, hay que revisar si siguen aplicando contra
el código de ESE momento, no asumir que el código descrito ahí sigue ahí.

**Lo que SÍ se mantuvo** (no es "MVM", son arreglos reales disparados por
reportes de bugs del propio usuario, verificados uno por uno que no
dependían de nada del Grupo A antes de revertir): rescate de RUT pegado a
fila en Mujeres/Discapacidad/Jubilados, resiliencia de Exención portada a
Jubilados, OCR conectado en F30-1/PreviRed, Contratos Antofagasta
soportando archivos agrupados, y el fix de "Base única" no filtrando por
sub-área. La paralelización de `va_validarLiquidaciones` (commit
`ebf68eb`, también parte de la misma ronda) ya se había revertido antes
por separado (causó 2 corridas reales colgadas — ver sección
correspondiente arriba).

## Finiquitos: mismo bug de tope de páginas que Jubilados y F30-1, tercera vez en el día

El usuario insistió en que Finiquitos seguía sin leer nada (0/11) incluso
después de una corrida fresca — descartando la hipótesis inicial de
"corrida vieja en pantalla". `va_validarFiniquitos` llamaba a
`va_getPdfTextOCR(buf)` **sin segundo argumento**, es decir con el tope
por defecto de 30 páginas — el mismo bug ya encontrado y arreglado en
Jubilados y F30-1/PreviRed esta sesión ("si el PDF completo tiene MÁS
páginas que maxPagesOCR, se salta el OCR de TODO el archivo, no de las
páginas de más"). Se subió a `,100`, mismo criterio que los otros dos.

**No se pudo confirmar el conteo exacto de páginas del archivo real** —
dos lectores de PDF (PyMuPDF y pypdf) coincidieron en 23 páginas para
`Finiquitos.pdf`, pero el conteo que se había visto antes para ese mismo
archivo decía 52 (y el mismo patrón de discrepancia ~2x apareció también
con `Contratos de trabajos.pdf`: 132 vs 53 páginas según distintas
herramientas). No se investigó a fondo el porqué de esta discrepancia
(hipótesis sin confirmar: páginas escaneadas como "spread" que algún
lector cuenta como 2 páginas lógicas) — se optó por subir el tope de
todas formas porque es de bajo riesgo y ya se demostró necesario 2 veces
antes en esta misma sesión con el mismo síntoma exacto.

**Patrón para la próxima vez**: si un módulo de Antofagasta reporta "no
lee nada" y el documento se ve legible a simple vista (no rotado, no
manuscrito), lo primero a revisar es si su llamado a `va_getPdfTextOCR`
tiene un tope de páginas explícito y suficientemente alto — no asumir que
es un problema de calidad de OCR sin antes descartar esto, que ya salió 3
veces en un solo día.

## Sesión de auditoría completa (Finiquitos → Liquidaciones): 8 causas raíz reales, todas con datos reales

El usuario reportó "se rompió el reconocimiento documental" de forma
genérica — en vez de adivinar un solo fix, se auditó módulo por módulo
contra los documentos reales de `Documentos Antofagasta/` (341 trabajadores,
LH real del período). Resumen de lo encontrado, para no repetir el mismo
diagnóstico dos veces:

1. **Finiquitos "no reconoce nada"**: no era el tope de páginas (ya se
   había subido a 100 antes) — era que `va_getPdfTextOCR` nunca se
   auto-cargaba el motor OCR (`cargarOCR()`); dependía 100% de que
   `va_validarLiquidaciones` ya lo hubiera hecho antes, pero esa función
   corta con `return` si el slot `'liq'` no tiene archivos ESE mes/corrida
   — dejando `ren_ocrWorker` en `null` para siempre. Fix: la función se
   auto-carga el OCR si hace falta.
2. **Libro de Remuneraciones 0% → 66.3%**: el documento viene escaneado con
   orientación MEZCLADA por página (90°/180°, no fija) — el mecanismo de
   rotación existente nunca se disparaba porque su gate ("¿salió poco
   texto?") no sirve cuando la rotación equivocada igual produce miles de
   caracteres de basura. Fix acotado a este módulo: prueba las 4 rotaciones
   siempre y elige la que encuentra más RUT con DV válido.
3. **Libro de Asistencia**: dos causas reales para el "0 vía OCR, todo por
   IA" — (a) el regex `TRABAJADOR_RE` a veces captura una palabra de ruido
   extra al final (ej. real: "MBARGUEN LILIA mes JoMo"), y el matcher exige
   cobertura EXACTA de 1.0 así que una sola palabra de más lo rechaza — fix:
   `va_matchNombreConRecorte`, reintenta recortando desde el final. (b) los
   archivos vienen organizados por letra de apellido — restringir el pool de
   matching a esa letra (`va_candidatosLibroPorLetra`) elimina la mayoría de
   los empates por ambigüedad entre personas de letras distintas.
4. **Contratos "dice que faltan documentos que sí están"**: el título del
   Anexo HHEE a veces sale con 1-2 caracteres OCR-corruptos (real: "ANEXO DE
   CONTRA O DE TRABAJO"), el regex exacto no matchea, y el fallback genérico
   de "CONTRATO" escaneaba la página ENTERA — encontrando la frase dentro
   del propio cuerpo del Anexo (que menciona el contrato original) y
   reclasificando mal. Fix: tolerancia por Levenshtein en el título + el
   fallback genérico ahora solo mira los primeros 100 caracteres.
5. **Licencias Médicas 0% real de cobertura**: el listado tabular completo
   vivía en un `.oxps` (formato XPS de Windows) que el input ni aceptaba
   (`accept='.pdf'` solo). Es un ZIP igual que `.docx` — nueva función
   `va_readOxpsText`. Complicación real: el texto extraído no trae espacios
   entre columnas y el RUT sale con el N° de fila pegado adelante (mismo
   patrón ya visto en Libro de Remuneraciones) — se resuelve probando el
   RUT capturado tal cual y, si no pasa el DV, recortándole el primer
   dígito.
6. **Cálculo de días de licencia que cruzan de mes**: verificado explícito
   con un caso real (licencia 19-jun a 02-jul, 14 días totales, 2 en julio)
   — `va_diasLicenciaEnPeriodo` YA lo calculaba bien, en todos los caminos
   (formulario individual, tabla PDF, `.oxps` nuevo). No hizo falta ajuste;
   quedó documentado para no re-auditar esto de nuevo sin motivo.
7. **Liquidaciones — regla de negocio, no bug de lectura**: pedido explícito
   del usuario, "TODOS los que aparecen en el LH del mes deben tener
   liquidación, sin excepción". `va_clasificar` eximía a quien tuviera
   `Total Haberes Imponibles=0` ese mes (`SIN_ACTIVIDAD`, no contaba como
   faltante) — 16 trabajadores activos reales quedaban sin chequear. Se
   sacó la excepción.
8. **Firma física en Anexos de Contrato — dos causas reales, una arreglada,
   una documentada sin fix**. El intento de verificar en vivo contra
   Tesseract.js real no terminó en el sandbox (>10 min), así que se cambió
   de estrategia: `pytesseract.image_to_data` (rápido en este sandbox) da
   la MISMA estructura de datos que `data.words` de Tesseract.js (texto +
   bbox por palabra), así que se pudo replicar `va_detectarFirmaFisicaPorEtiqueta`
   exacta en Python contra las páginas reales de los 3 trabajadores
   reportados, después de confirmar visualmente (PyMuPDF → PNG, mirado
   directamente) que las 3 SÍ tenían firma real.
   - **Causa 1 (arreglada)**: caso real de Rojas Leyton Priscilla Andrea —
     la firma va DEBAJO de la línea del RUT, no arriba de la etiqueta
     "FIRMA DEL TRABAJADOR" (layout distinto al resto de los trabajadores
     del mismo archivo). El algoritmo solo miraba arriba de la etiqueta —
     zona vacía, 0.034% de tinta medida. Fix: `va_detectarFirmaFisicaPorEtiqueta`
     ahora también busca la línea "Rut" más cercana debajo de la etiqueta y
     mira la tinta debajo de ESA (no debajo de la etiqueta directamente —
     eso daría falso positivo siempre, ahí está impreso el RUT). Umbral más
     alto para este camino (3% vs 1% del camino normal) porque el borde
     punteado de la caja mete ~2.4% de tinta de fondo aunque no haya firma
     real — medido en 2 páginas reales sí firmadas por el camino normal.
     Validado con síntesis en el navegador real (no solo réplica Python):
     detecta el patrón de Rojas, sigue detectando el patrón normal, y sigue
     rechazando correctamente una caja realmente vacía (sin tinta en
     ningún lado) — los 3 casos verificados en consola contra
     `va_detectarFirmaFisicaPorEtiqueta` real.
   - **Causa 2 (documentada, sin fix)**: caso real de Yucra Geronimo
     Ruperto — el algoritmo depende de que OCR lea la palabra "TRABAJADOR"
     de la etiqueta para anclar la zona a revisar; en esta página la firma
     manuscrita cruza/tapa justo la etiqueta impresa y Tesseract simplemente
     NO la reconoce como ninguna palabra (0 apariciones de "trabajador" en
     mayúsculas en toda la página, solo 4 menciones en minúscula dentro del
     CUERPO del contrato — "en poder del trabajador", "liga al trabajador",
     etc). El algoritmo cae de vuelta a la ÚLTIMA mención que sí pudo leer
     (texto de una cláusula, nada que ver con la firma) y mide tinta en el
     lugar equivocado. No se intentó un fix — cualquier heurística de
     posición (ej. "solo mirar el 20% inferior de la página") seguiría
     fallando acá porque la mención errónea de "trabajador" TAMBIÉN cae en
     esa franja inferior (cláusula QUINTO, justo antes del bloque de firma).
     La salida real para este caso ya existe en el código: si la detección
     física falla, `va_validarContratosAntofagasta` cae a IA visual
     (`iaKeyOk` configurada) — confirmar con el usuario si tenía la key de
     IA activa en la corrida donde vio este caso, antes de asumir que sigue
     roto.

## Barra de progreso: saltos hacia atrás reales + módulos sin ningún avance visible

El usuario pidió explícitamente que la barra de carga sea "fidedigna", de
1 a 100%, mostrando cantidad de hojas y avance en TODO lo que carga
(incluyendo Libro de Asistencia, que "tampoco está mostrando eso"). Se
encontraron 3 bugs reales de código, no solo una mejora cosmética:

1. **Retroceso real 80%→78%**: en `va_ejecutar`, justo después de
   `setPg(80,...)` + PreviRed, el bloque `if(va_baseKey==='Antofagasta')`
   empezaba en `setPg(78,...)` -- la barra literalmente retrocedía en
   TODA corrida real de Antofagasta. Mismo bug en el bloque Vitacura.
   Renumerado para que sea monótono (81→98 para Antofagasta, 81→97 para
   Vitacura), y el `setPg(90,...)` final ("Clasificando trabajadores")
   subido a 99 (antes retrocedía desde 98 también).
2. **Libro de Asistencia se congelaba en 89% tras ~30 páginas**: el
   cálculo era `Math.min(86+Math.round(totalPags/10),89)` -- con
   cientos de páginas reales (Antofagasta reparte Libro en ~24 archivos
   por letra), el tope de 89% se alcanzaba casi de inmediato y la barra
   quedaba "clavada" ahí el resto de la corrida real, dando la impresión
   de que no avanzaba (exactamente el síntoma reportado). Fix: pre-conteo
   de páginas TOTALES de todos los archivos del slot (barato, no
   renderiza nada) para repartir un rango real 87-96% proporcional al
   trabajo real, mensaje ahora dice "página X/Y".
3. **Contratos Antofagasta tenía un `va_setProg(84,...)` fijo** que ni
   siquiera correspondía a dónde corre este módulo en la secuencia real
   (corre AL FINAL, después de Mujeres/Discapacidad) -- otro retroceso
   real. Se agregó el mismo patrón de pre-conteo + progreso proporcional
   (rango 98-99%) con mensaje "página X/Y".
4. **Jubilados nunca llamaba a `va_setProg`** durante su ejecución (puede
   tener 90+ páginas de certificados individuales) -- la barra quedaba
   congelada en el mensaje "Validando Listado Jubilados..." sin ningún
   avance hasta terminar. Se agregó un parámetro `onProgress` OPCIONAL
   (5º parámetro, con valor por defecto `undefined` -- cero cambio de
   comportamiento para los demás ~10 llamadores existentes de
   `va_getPdfTextOCR`) que llama al callback después de cada página --
   usado en Jubilados para mostrar "página X/Y" real dentro de un rango
   82-85%.

**Alcance deliberadamente acotado**: no se tocaron Anexos Reemplazos,
Carta No Firma, Libro Remuneraciones, Mujeres ni Discapacidad (documentos
más chicos, de menor impacto visual) ni F30/F30-1/PreviRed/Exenciones
(compartidos con otras bases, mayor riesgo si algo sale mal) -- se
priorizaron los módulos con más páginas reales y done el usuario señaló
el síntoma explícitamente (Libro). El parámetro `onProgress` de
`va_getPdfTextOCR` queda disponible para sumar progreso real a esos
módulos más adelante sin tener que rediseñar nada.

**No se pudo medir el comportamiento real en una corrida larga en este
sandbox** (misma limitación de siempre: render de PDF/OCR real no corre
acá a velocidad usable) -- validado por sintaxis (index.html carga sin
errores de consola) y lectura de código verificando que los rangos son
monótonos de principio a fin. Pendiente que el usuario confirme en una
corrida real que la barra ahora avanza de forma continua sin retrocesos ni
congelamientos.

## Se sacó "🔍 Detalle de lectura con IA" de todos los paneles — pedido explícito del usuario, queda solo en Excel

Hasta ahora cada módulo con lectura IA (Libro, Licencia inline, Contrato
firma QR, Exención, Contrato Antofagasta, Libro Antofagasta) pintaba su
propio detalle página-por-página en el panel vía `va_renderIAAuditSection`
(pensado en su momento como mejora de UX, ver sección histórica "Detalle de
lectura con IA, integrado en cada módulo" más arriba). El usuario pidió
sacarlo de todos los paneles ("no aplica que se vea en el módulo") y que
ese detalle quede solo en el Excel exportado.

**Cambio**: `va_renderIAAuditSection` (la función que pintaba HTML) se
eliminó por completo -- confirmado sin otros usos antes de borrarla. Se
creó `va_iaAuditRowsExcel(nombreModulo)`, equivalente pero devolviendo
filas en formato aoa para Excel en vez de HTML, y se conectó a la hoja de
Excel correspondiente de cada módulo: Liquidaciones (`Contrato (firma
QR)`), una hoja nueva `Libro` para Lo Barnechea/Las Condes/Mejillones
(antes NO tenía hoja propia en el Excel en absoluto -- el panel
`va_renderLibroDetalle` nunca se había conectado al exportador), Exenciones,
Contratos (Antofagasta) y LibroAsist (Antofagasta, sumado al lado del
detalle de Faltas/Permisos/Licencias ya agregado antes). Licencias Médicas
ya tenía esto desde una sesión anterior, sin cambios ahí.

**Ojo para la próxima vez que se agregue lectura con IA a un módulo
nuevo**: ya no alcanza con loguear a `va_iaAuditLog` y listo -- hay que
además conectar `va_iaAuditRowsExcel('Nombre Del Módulo')` a la hoja de
Excel de ese módulo específico, si no el detalle queda registrado pero
invisible en cualquier lado (ni panel ni Excel).


## Dos pestañas para el mismo chequeo: Exenciones y Jubilados (23-08-2026)

El usuario reportó ver dos opciones equivalentes en el panel de Antofagasta.
Causa: `va_renderResultados` armaba `baseTabs` con `'exencion'` **fijo para
todas las bases**, pero Antofagasta no tiene ese slot en `VA_BASES` (su
Listado de Jubilados ya cubre la exención de cotizar). Resultado: la pestaña
Exenciones salía siempre vacía al lado de la de Jubilados. Ahora la pestaña
se agrega solo si la base declara el documento
(`VA_BASES[va_baseKey].docs.some(d=>d.id==='exencion')`) -- verificado que Lo
Barnechea la conserva y Antofagasta ya no la muestra.

Al mismo tiempo, Jubilados era el único panel de cruce **sin listado
nominal**: `va_validarJubilados` guardaba contadores y faltantes, pero nunca
quiénes eran los jubilados del mes. Se agregó `detalleJubilados` (todos los
`Jubilado = Sí` del LH del período con RUT, nombre, cargo, días, marca de
desvinculado y si aparecen o no en el documento) y un renderizador propio
`va_renderJubilados()` en vez de reusar `va_renderAntTab`. El mismo listado
va a la hoja `Jubilados` del Excel.

## La barra de progreso mostraba un número y pintaba otro (23-08-2026)

Reporte: "lo mostrado de verde nunca coincide con los porcentajes mostrados".
Dos causas reales:

1. El ancho del relleno usaba el valor crudo (a veces decimal) mientras el
   texto mostraba el avance LOCAL del módulo ("página 45/300") -- dos números
   sin relación visible. Ahora `va_setProg` redondea una vez y usa ese mismo
   entero para el ancho, para un `%` escrito al lado de la barra
   (`#va-ppct`) y para el sufijo "— NN% del total" del mensaje.
2. Varios módulos podían hacer **retroceder** la barra (un `setPg` fijo más
   bajo que el punto proporcional al que ya había llegado el anterior).
   `va_setProg` ahora es monótona: nunca baja dentro de una corrida
   (`va_resetProg()` al arrancar `va_ejecutar`).

Y un desbalance de bandas que era el caso más visible: **Contratos tenía 1
punto (98→99)** para cientos de páginas de OCR, así que el texto decía
"página 120/500" con la barra clavada en 98%. Rebalanceo Antofagasta:
IMPUT 81 · Jubilados 81→84 · Anexos/CartaNoFirma 84 · LibroRem 85 · Libro
Asistencia 85→92 · Mujeres 92 · Discapacidad 93 · **Contratos 93→99**.

## Carga masiva: un solo nivel de identificación no alcanzaba (23-08-2026)

Reporte: "hay momentos donde cargo documentos y no lo reconoce". Había UN
solo escalón (regex sobre el nombre del archivo), así que cualquier nombre
mal escrito, genérico o vacío de pistas caía en "sin identificar". Medido
contra los 28 nombres reales de `Documentos Antofagasta`, fallaban entre
otros `O. libro de asistecia leytraO.pdf` (typo doble: "asistecia" +
"leytra", ninguno de los dos patrones viejos pegaba) y `carta explicativa.pdf`.

Ahora la escalera es la misma filosofía que el resto del validador -- lo
barato primero:

0. Descarte de temporales de Office (`~$…`) y extensiones no soportadas.
   Los archivos reales traen media docena de `~$*.docx` que antes ensuciaban
   la lista de "sin identificar" en cada carga.
1. Regex sobre el nombre (patrones ampliados: `LIBRO\s*(DE)?\s*A\w{0,10}CIA`
   cubre todas las variantes de "asistencia" mal escrita vistas, sin chocar
   con "Libro de Remuneraciones" ni "Libro de Haberes", que empiezan con otra
   letra).
2. La **carpeta** de origen, cuando se arrastra una carpeta entera -- se
   agregó recorrido recursivo con `webkitGetAsEntry()` en el drop. Las
   carpetas reales dicen "J).-Libro de Asistencia", muchísimo más informativo
   que el nombre del archivo.
3. Fuzzy por palabra con Levenshtein (tolerancia 2-3), para el typo que
   todavía no está en la lista de patrones.
4. **Contenido**: texto nativo de las primeras páginas y, si el PDF es un
   escaneo, OCR de la página 1. Es el único nivel que no depende de cómo
   alguien nombró el archivo.

Cada archivo queda etiquetado con **cómo** se identificó, y el resumen lo
muestra en una tabla plegable con las asignaciones de escalón flojo
resaltadas -- para poder desconfiar de las que no salieron del nombre. Se
respeta además el `accept` de cada casillero, para no mandar un `.xlsx` a un
slot que solo lee PDF solo porque el nombre pegó con su patrón.

Ojo con un falso positivo que NO hay que introducir: el propio Libro de
Haberes (`... Libro de haberes Revisión Nuevo ....xlsx`) se carga en el paso
1, no es un casillero de documento -- verificado que ningún patrón lo captura.


## Los informes hablaban de módulos que nadie adjuntó (23-08-2026)

El usuario mandó un PDF real de 11 páginas: **10 de esas 11** eran la tabla de
Liquidaciones con 341 filas "Activo sin liquidación en PDF"... en una corrida
donde lo único adjuntado fue el IMPUT. El módulo que sí se cargó no aparecía
en ninguna parte del informe, y el veredicto decía **NO VIABLE**.

Causa: ni el PDF ni el Excel miraban `va_docsData` para saber qué se subió.
La tabla de Liquidaciones se armaba siempre desde `va_resultados` (que tiene
una fila por trabajador del LH, exista o no el documento), y el veredicto
solo miraba `sinLiq>0`. Con el PDF de Liquidaciones ausente, TODO el Libro de
Haberes cae por definición en `SIN_LIQUIDACION` — un número que mide lo que
falta por adjuntar, no un incumplimiento.

Tres helpers compartidos nuevos, usados por panel + Excel + PDF para que los
tres digan lo mismo:

- `va_adjuntos()` — por cada casillero de la base: si se adjuntó, cuántos
  archivos, sus nombres, tamaño, páginas leídas y estado.
- `va_moduloCargado(id)` — atajo sobre `va_docsData[id].files`.
- `va_veredicto()` — distingue **INCOMPLETO — FALTAN DOCUMENTOS POR ADJUNTAR**
  (el módulo nunca se subió) de **NO VIABLE** (el documento está y falta
  gente), y devuelve el motivo en texto.

Cambios concretos: el PDF abre con "1. Documentos adjuntos en esta corrida"
(tabla completa, con los no adjuntados en ámbar) antes que cualquier
hallazgo; la sección de Liquidaciones se **omite** si el PDF no se adjuntó y
en su lugar va una alerta explicando por qué; el Excel gana una hoja
`Adjuntos` y la hoja `Liquidaciones` arranca con una fila de aviso cuando el
módulo no se cargó. Verificado en las dos direcciones con la misma corrida
sintética: sin Liquidaciones el informe pasa de 11 páginas a **3**; volviendo
a adjuntarlo vuelve a 13 con la tabla completa y el veredicto a NO VIABLE.

**IMPUT no tenía sección propia en el PDF.** El loop genérico de cruces
espera la forma `{rutsDoc, rutsLH, coincidencia}`; el IMPUT no la tiene (trae
sub-bloques MATRIZ / CONTRATOS / FINIQUITADOS / JUBILADOS / LICENCIAS), así
que salía como un título vacío — justo el único módulo adjuntado en la
corrida reportada. Ahora tiene bloque propio con los cinco sub-cruces, y se
sacó del loop genérico.

## El cruce del Libro de Haberes nunca mostró dotación ni montos (23-08-2026)

Los KPIs del LH eran cuatro conteos (Total / Activos / Finiquitados /
Jubilados) sobre `va_lhAll` — nunca el **monto** ni la **dotación** del sector
efectivamente auditado. Peor: al elegir sector los KPIs no se recalculaban,
así que seguían mostrando los números del archivo completo aunque
`va_lhFiltered` fuera un subconjunto.

`va_resumenLH()` (nueva) devuelve período, registros del archivo, dotación
del sector, activos, finiquitados, jubilados, mujeres, discapacidad, con
licencia, días trabajados, y los montos **Total Haberes Imponibles** y
**Total Sueldo Líquido**. La usan los KPIs del paso 1 (ahora 8, en dos filas),
la línea de info del sector, el Excel (bloque LIBRO DE HABERES en la hoja
Resumen), el PDF (sección 2) y el resumen que se copia al portapapeles.

**Trampa que introduje y tuve que corregir**: el primer fallback era
`va_lhFiltered.length ? va_lhFiltered : va_lhAll`, para poder pintar KPIs
antes de elegir sector. Pero eso hace que un sector cuya sub-área **no
matchea ningún registro** informe la dotación del archivo entero en vez de 0
— tapando justo el problema que hay que ver. Ahora el fallback solo aplica
mientras `va_sectorKey` es null; elegido el sector se usa `va_lhFiltered`
aunque quede vacío, y el panel muestra en rojo "Dotación 0 en <sector> —
ninguno de los N registros tiene esa Sub-área". Además cargar un LH nuevo
resetea `va_sectorKey`/`va_subarea`/`va_lhFiltered`, si no los KPIs quedarían
calculados con el filtro del archivo anterior.


## Discapacidad daba 0% y la causa era el GATE de rotacion, no el documento (23-08-2026)

Reporte del usuario: el panel de Personal con Discapacidad marcaba **0 RUTs
en el documento y 0.0% de match**, con los 6 trabajadores del LH como
faltantes. Mujeres, en la misma corrida, daba 50.6%.

Mirando el archivo real (paso 3.5 del proceso) `Discapacidad.pdf` — 7
paginas, **cero texto nativo**:
- **pag. 1**: "Listado de capacidades diferentes" (RUT + nombre + tipo),
  girada **90 grados**. Los 6 RUTs de la tabla son exactamente los 6 que el
  informe reportaba como faltantes. Estaban todos ahi.
- **pags. 2-7**: los CERTIFICADOS individuales, girados **180 grados** —
  Credencial del Registro Nacional de la Discapacidad (folio, codigo de
  barras, QR, "GRADO DE DISCAPACIDAD PSIQUICA O MENTAL: 70.00%") y Resolucion
  de Certificacion de Discapacidad de COMPIN (Rut, Organo Principal,
  Porcentaje, Movilidad Reducida, Fecha de Reevaluacion).

**La causa raiz, y es compartida por todo el validador**: en
`va_getPdfTextOCR` el fallback de rotacion estaba detras de

    if(intentarRotacion && txt.replace(/\s/g,'').length < 40)

o sea, solo se probaban otras orientaciones cuando el OCR a 0 grados habia
devuelto **casi nada**. Pero una pagina escaneada de costado **no falla por
defecto, falla por exceso**: Tesseract igual escupe cientos de caracteres de
ruido. El gate no disparaba nunca y la pagina se quedaba con su texto
ilegible. Es exactamente la regla 3 de `politica-ia.md` aplicada al OCR en
vez de a la IA: *el gate tiene que mirar la direccion en la que el escalon
gratis falla*.

Ademas, cuando si disparaba, elegia la rotacion **por cantidad de
caracteres** — la metrica equivocada, porque la orientacion mala produce MAS
caracteres que la buena.

**Fix (compartido, beneficia a todos los modulos)**:
- Gate nuevo: `if(intentarRotacion && va_findAllRuts(txt).size===0)` — mira la
  SENAL que se busca, no el largo.
- `va_scoreTextoRut()`: puntua un texto por **RUTs con DV valido**, con el
  largo solo como desempate.
- `va_ocrPaginaMejorRotacion` ahora **acumula** el texto de toda rotacion que
  haya aportado al menos un RUT, en vez de quedarse solo con "la mejor" (cada
  angulo es evidencia independiente; en una tabla densa es normal que una
  rotacion lea bien la mitad de arriba y otra la de abajo). Si se le pasa un
  `scorer` propio (Finiquitos) mantiene el comportamiento viejo, sin regresion.
- El texto rotado se **suma** al de 0 grados en vez de reemplazarlo.

**Nota**: `va_validarLibroRem` ya tenia esta misma correccion resuelta de
forma LOCAL, con el mismo diagnostico escrito en su comentario ("su gate es
'salio poco texto?', y aca siempre sale mucho texto, solo que ilegible").
Confirmacion independiente de que el analisis es correcto — ahora esta
generalizada al helper compartido. A LibroRem se le agrego ademas la
acumulacion de rotaciones (antes se quedaba solo con la mejor).

## Bug de mayusculas: ningun RUT terminado en K matcheaba (23-08-2026)

`va_extraerRutConChecksum` devolvia el candidato con
`cuerpo+'-'+dv.toUpperCase()`, pero `va_normRut` normaliza el DV a
**minuscula** y todos los Set de nomina se arman con `va_normRut`. Resultado:
`candidatos.find(r=>listaValidos.has(r))` no podia encontrar jamas un RUT
terminado en K, y `ruts.add(rc)` insertaba una clave que nunca iba a cruzar.
Solo en la lista de Mujeres de Antofagasta hay ~9 RUT asi (19.102.768-k,
8.600.657-k, 12.131.410-k, 26.635.536-k, 19.441.630-k, 15.020.951-k,
18.219.333-k, 28.773.932-k). Corregido a `.toLowerCase()`.

## Cuanto suma cada escalon — medido contra la nomina real (23-08-2026)

Con `pytesseract` sobre los PDF reales y el Libro de Haberes real
(341 registros: 170 mujeres, 6 con discapacidad):

| Documento | Solo regex RUT | + checksum por linea | + match por NOMBRE |
|---|---|---|---|
| Dotacion femenina (170) | 92.9% | 94.7% | **99.4%** (169/170) |
| Discapacidad (6) | 100% | 100% | **100%** |

El unico que sigue faltando en Mujeres es `26232604-7 Quinones Reyes Lucia`
— probablemente no esta en el documento. Conclusion: **el nivel por nombre es
el que cierra la brecha** (+4.7pp en Mujeres), y es gratis. Se agrego a
Mujeres y a Discapacidad, con el mismo patron linea-a-linea + par de lineas
consecutivas que ya usaban Exenciones y Jubilados.

Ojo con la trampa de siempre: esto se midio con **pytesseract**, no con
Tesseract.js. Demuestra que el regex y la logica de escalones son correctos;
NO demuestra la cobertura que dara el navegador.

## Discapacidad: el listado no acredita, el certificado si (23-08-2026)

Pedido explicito del usuario: "me interesa MUCHO que reconozca, asi sea con
IA, los certificados de Discapacidad". El modulo solo miraba si el RUT
aparecia en cualquier parte del PDF — sin distinguir entre estar en el
listado tabular y tener el certificado individual, que es lo que la
acreditacion realmente exige.

`va_validarDiscapacidad` se reescribio con su propio loop pagina por pagina:
- `va_tipoDocDiscapacidad(txt)` clasifica cada pagina: LISTADO /
  RESOLUCION_COMPIN / CREDENCIAL / REGISTRO_NACIONAL / CERTIFICADO.
- `va_datosCertDiscapacidad(txt)` extrae folio, porcentaje, grado y fecha de
  reevaluacion como evidencia auditable. **Cuidado con el grado**: la
  Credencial lista TODOS los tipos con su porcentaje y casi todos en 0.00%
  ("PSIQUICA O MENTAL: 70.00% / FISICA: 0.00% / SENSORIAL: 0.00%") — hay que
  quedarse con el tipo cuyo porcentaje es el MAS ALTO, no con el primero que
  matchee un regex (el primer intento decia "fisica" para un caso 70% psiquica).
- Escalera: RUT directo -> checksum contra la nomina de discapacidad ->
  NOMBRE -> **IA visual**. El prompt de IA le avisa explicitamente que la
  pagina puede venir rotada 90/180/270 y le pide `{personas:[{rut,nombre}],
  tipo_documento, folio, porcentaje_discapacidad, grado}`. La IA solo se
  acepta si el RUT esta en la nomina de discapacidad del LH o si el nombre
  matchea — un RUT "valido" que no es de nadie de la base es ruido.
- Tope `window.VA_IA_DISC_MAX` (40 por defecto).
- Panel, PDF y Excel muestran, por trabajador, **que certificado lo respalda**
  (tipo + pagina + folio/porcentaje/grado), separando "con certificado" de
  "solo en el listado" de "sin respaldo", mas las paginas que no se pudieron
  atribuir a nadie y el diagnostico de lectura.

## Barrida con OSD de toda la carpeta de Antofagasta (23-08-2026)

`pytesseract.image_to_osd` sobre una muestra de paginas de cada PDF, para
saber que material viene girado. Resultado: **casi todo el material escaneado
de esta base viene rotado**, y ninguno tiene texto nativo:

| Documento | Pags | Nativas | Orientaciones detectadas |
|---|---|---|---|
| Libro de Remuneraciones | 9 | 0 | **270 en las 5 muestreadas** |
| Libro de Asistencia (23 archivos) | 1-38 | 0 | mayoria **90**, varios 270 |
| Liquidaciones (21 archivos) | 2-52 | 0 | mezcla **180** y 0 |
| Contratos de trabajos.pdf | 53 | 0 | **180** en las 6 muestreadas |
| Finiquitos.pdf | 23 | 0 | **180** y 270 |
| Jubilados.pdf | 96 | 0 | 0 y algunas 180 |
| Discapacidad.pdf | 7 | 0 | **90 + 180** |
| carta lm.pdf | 1 | 1 | 180 |
| Dotacion femenina.pdf | 5 | 0 | 0 (no rotado) |
| F30, F30-1, PreviRed, Impositivo | — | casi todas | 0 |

Con el gate viejo, TODO ese material dependia de que el OCR acertara a la
primera. Se activo `intentarRotacion=true` en los modulos que usan el helper
compartido y leen documentos escaneados: **Jubilados, Anexos de Reemplazo,
Carta No Firma y Carta Fe de Erratas** (Mujeres y Discapacidad ya quedaron
cubiertos arriba). Es barato porque el gate nuevo solo gasta OCR extra en las
paginas que no aportaron ningun RUT.

**Pendiente, decision de costo del usuario**: `va_validarLibroAsist` tuvo su
reintento de rotacion **removido a proposito** (documentado mas arriba: 318
paginas, mas de 30 min). La barrida ahora muestra que ~90% de esas paginas
estan a 90/270 grados, asi que la razon que se habia anotado ("son
manuscritos, no rotacion") era solo parte del cuadro. Hoy lo cubre la IA
visual. Si se quiere recuperar cobertura gratis ahi, la rotacion con gate por
senal es el camino — pero hay que medir el costo antes.
`va_validarLiquidaciones` tampoco intenta rotacion; ahi la deteccion de firma
esta calibrada y funcionando, asi que no se toco.

## El informe PDF hablaba de lo que no se adjunto (23-08-2026)

Segunda tanda del mismo pedido. Sacados del informe:
- **"Resumen por caso"**: es 100% derivado del cruce de Liquidaciones. Sin
  ese PDF adjunto son seis ceros y un total enganoso. Ahora solo aparece si
  Liquidaciones se adjunto.
- **"Estado de cada documento"**: redundante — la tabla de adjuntos ya trae
  una columna Estado y ademas dice si el documento se subio. Eliminada.
- **Seccion de Liquidaciones**: solo aparece si el PDF se adjunto.
- **El parrafo largo debajo del veredicto** (enumeraba todos los modulos sin
  adjuntar): sacado del panel, del PDF, del Excel y del resumen que se copia.
  La tabla de adjuntos ya dice que falta; repetirlo era ruido.

Resultado medido con la corrida real del usuario (solo Mujeres +
Discapacidad adjuntados): el informe paso de **6 paginas** con la mitad
dedicada a Liquidaciones inexistentes, a **2 paginas** que hablan solo de lo
que se subio.

## 23-08-2026 — Coherencia del IMPUT: el "Libro Haberes" embebido gobierna las dinámicas

Pedido del usuario: *"es un excel con tablas dinámicas el cual lo gobierna el Libro de haberes, pero
la gracia es que esté actualizado y que todas sus hojas sean coherentes, o que reporte que está
mal"*.

El IMPUT real (`Imput del mes de julio.xlsx`, 11 hojas, 341 trabajadores) es una hoja fuente
**`Libro Haberes`** (encabezados en la fila 6, igual que el LH suelto) más 10 vistas derivadas:
MATRIZ, CARGO, DISCAPACIDAD, MUJERES, JUBILADOS, IMPOSITIVOS, CONTRATOS, FINIQUITADOS,
LICENCIA MEDICA, VACACIONES. Dos cosas pueden fallar y ninguna se veía antes:

1. **IMPUT desactualizado** — su hoja `Libro Haberes` no coincide con el LH que se subió.
2. **Dinámicas sin refrescar** — la hoja fuente está bien pero los pivotes muestran el recorte de
   una versión anterior.

`va_imputCoherencia` chequea las dos: la primera contra `va_lhAll`, la segunda recalculando el
subconjunto esperado de cada hoja desde la propia hoja `Libro Haberes`.

**El hallazgo que evita un reporte lleno de falsos positivos**: las hojas derivadas **NO están
filtradas por sub-área** — cubren el Libro Haberes completo. Comparar contra `va_lhFiltered` (que sí
filtra por `Antofagasta Ciudad 2022`) marcaba **5 de 7 hojas como incoherentes** por 3 personas de
la sub-área `Base Antofagasta AK` (Torrejón Campusano, Alfaro Díaz, Opazo Díaz) que están en el
Libro pero fuera del sector auditado. Con el alcance corregido al Libro Haberes entero: **7/7 hojas
coherentes**. Moraleja general: antes de declarar una diferencia como error, verificá que los dos
conjuntos tengan el mismo ALCANCE.

Columnas usadas de `Libro Haberes` (se buscan por nombre de encabezado, no por índice): Número de
Documento, Nombre Completo, Fecha Ingreso Compañía, Fecha Término Trabajo, Sexo, Nombre Sub-área
Asignada(o), En Situación de Discapacidad, Fondo de Cotización, Días Licencias (reales).

Ojo con los nombres de hoja: vienen con espacios de más (`" CONTRATOS"`, `"FINIQUITADOS "`), por eso
el match usa `String(s).trim()`.

**Resultado sobre el archivo real de julio**: actualizado (341 = 341, 0 diferencias) y 7/7 hojas
coherentes — MATRIZ 341, MUJERES 170, DISCAPACIDAD 6, JUBILADOS 94, FINIQUITADOS 11, CONTRATOS 9,
LICENCIA MEDICA 50. Idéntico en el prototipo Python y en el JS real corrido en el navegador.

**Control negativo** (sin esto no se puede afirmar que el detector sirva): sacando una fila de
MUJERES lo reporta como `faltan 1` nombrando a la persona; agregando alguien al LH lo reporta como
`actualizado=false`. El render marca ❌ solo en esos casos.

## 23-08-2026 — Antofagasta: tres casillas que se sacaron

Pedido del usuario. Las tres se quitaron de `VA_BASES.Antofagasta.docs`, de las pestañas y de
`va_ejecutar`:

- **Carta No Firma** — viene DENTRO del PDF de Liquidaciones. Ya había detección inline
  (`liq.tieneCartaNoFirmaLiq`); el slot era la segunda de dos vías y `va_clasificar` sigue
  aceptando la inline. Confirmado en el archivo real: `A. Liquidaciones letra A.pdf` trae esas
  cartas intercaladas en las páginas 11, 21 y 26.
- **Carta Fe de Erratas** — se quitó también la validación (decisión explícita del usuario). El
  parser `va_parseCartaFeErratas` y su render se mantienen porque Vitacura tiene su propio slot
  `libroasist_carta`.
- **Acreditación Mujeres** — la dotación femenina ya sale del Libro de Haberes (columna Sexo, ver
  `va_resumenLH`, que la muestra en los KPIs) y de la hoja MUJERES del IMPUT. Pedir un PDF aparte
  duplicaba lo mismo.
