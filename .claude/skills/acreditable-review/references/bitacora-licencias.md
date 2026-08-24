# Bitácora — Licencias Médicas (.oxps, fechas, días, IA)

> Parte del skill `acreditable-review`. Registro histórico de hallazgos REALES con su
> evidencia — se lee **solo cuando se está trabajando en este módulo**, no en cada sesión.
> El proceso de auditoría y la política de IA viven en `SKILL.md`.
> Las secciones están en orden cronológico: si dos se contradicen, gana la más nueva
> (varias documentan código que después se revirtió y lo dicen explícitamente).

## "No lee bien" en Licencias Médicas: antes de tocar código, verificar qué archivos se subieron esa corrida

El usuario reportó Licencias Médicas "no leyendo bien todas" en una corrida
real de Antofagasta (export `Validacion_Acreditable_Antofagasta_Base
única_2026-08-18.xlsx`, hoja "Licencias": 49 con licencia en LH, 30
cubiertos, 19 faltantes). Antes de sospechar del código, se cruzó cada uno
de los 19 RUT faltantes contra `Listado de licencia medica.oxps` (el
listado tabular limpio, ya arreglado y validado en la sesión anterior —
commit `fe2eb5d`, 68/68 filas resueltas) replicando en Python la MISMA
lógica de extracción que usa `va_procesarFilasOxpsLicencia` (incluye el
recorte de dígito-de-fila-pegado con desambiguación por DV).

Resultado: **18 de los 19 faltantes SÍ están correctamente listados y
legibles en el `.oxps`** — incluyendo el caso exacto que el commit `fe2eb5d`
usa como ejemplo documentado (Alballay Villagran Pedro). El fix del `.oxps`
funciona; lo que pasó es que **esa corrida no incluyó el archivo `.oxps`
entre los documentos subidos al slot de Licencias** — solo `licencia
medica.pdf` (75 páginas escaneadas) y/o `carta lm.pdf`. No era un bug de
lectura, era un archivo de entrada faltante para esa corrida puntual.

El 1 caso restante (Pelaez Pelaez Ana Leonor, 6.573.181-9, ausente del
`.oxps`) SÍ tiene un comprobante individual real dentro de `licencia
medica.pdf` (formulario DIAT/DIEP, texto OCR: "ANA LEONOR PELAEZ PELAEZ 3
6573181-9"). Se replicó la extracción con los mismos parámetros que usa
`va_validarLicenciasMedicas` en producción (OCR a escala 2.5,
`va_ocrPaginaMejorRotacion` con scoring por fecha/palabra clave) y
`va_findAllRuts` sí encuentra ese RUT en el texto — así que en teoría el
código actual ya debería resolverlo. No se pudo confirmar en el navegador
real (Tesseract.js) por la lentitud del sandbox; si tras resubir con el
`.oxps` incluido este caso puntual sigue fallando, ahí sí vale la pena un
test en navegador real acotado a esa sola página antes de sospechar del
regex.

**Lección general**: cuando un módulo "no lee bien" en una corrida real,
antes de re-auditar el código, preguntar/confirmar qué archivos exactos se
subieron esa vez — sobre todo en módulos que aceptan más de un tipo de
archivo por slot (PDF + `.oxps`). Un archivo omitido produce el mismo
síntoma ("cubre menos de lo esperado") que un bug real de lectura, pero el
fix es "avisar al usuario que falta adjuntar X", no tocar código.

### Actualización: el caso de Pelaez SÍ era un bug real — colisión de checksum al recortar el dígito de fila pegado

El usuario preguntó si el caso restante (Pelaez Pelaez Ana Leonor) era por
tratarse de una "licencia mutual" (tipo distinto de licencia). No era eso —
al auditar las 68 filas del `.oxps` completo replicando la lógica exacta de
`va_procesarFilasOxpsLicencia`, se encontró que **3 de 68 filas** (Barrera
Zarate Clementina, Maguida Alvarez Estela, y Pelaez Pelaez Ana Leonor) tienen
un número de fila glued al RUT (ej. fila 40 + RUT "6.573.181-9" →
"406.573.181-9") donde, al recortar el primer dígito, la regex encuentra
"06.573.181-9" -- y ese candidato SIN recortar TAMBIÉN pasa el dígito
verificador chileno por pura casualidad (~1/11 de probabilidad, mismo
fenómeno ya documentado para `va_findAllRuts` en tablas de montos). El
código original probaba el candidato directo primero y solo intentaba el
recortado `if(!candidatos.size)` -- es decir, SOLO si el directo había
fallado el checksum. Como acá el directo (inventado, "06573181-9") SÍ
pasaba el checksum, el código nunca llegaba a probar el recortado (el real,
"6573181-9"), y como el inventado no está en la nómina, la fila se
descartaba entera.

**Fix aplicado** (`va_procesarFilasOxpsLicencia`, index.html ~línea 12440):
probar SIEMPRE ambos candidatos (directo y recortado) y preferir el que
efectivamente esté en `lhRutSet` (la nómina), en vez de quedarse con "el
primero que pase el DV". Validado con las 68 filas reales del `.oxps`: las
65 filas no ambiguas no cambian, y las 3 ambiguas ahora resuelven al RUT
real de la nómina (antes se perdían). Con este fix + el `.oxps` incluido en
la corrida, los 19/19 faltantes reportados por el usuario resuelven.

Lección: cuando una heurística de rescate prueba "candidato A, si falla
candidato B", y ambos pueden pasar una validación de checksum por
casualidad, no alcanza con "el primero que pase" -- hay que preferir
explícitamente el que además coincide con una fuente de verdad ya conocida
(acá, la nómina). Mismo principio que `match_rut_cercano` en Liquidaciones,
aplicado a un lugar donde antes no estaba.

## Vitácora: Licencias Médicas lenta -- paralelización por página (implementada, velocidad no verificable en este sandbox)

El usuario reportó que Licencias "se demora mucho" y preguntó si tenía
sentido dado que ya integramos OCR+IA. Medición real (no adivinada): con el
código de producción (`va_ocrPaginaMejorRotacion`, la función real que usa
`va_validarLicenciasMedicas`) corriendo contra la página 5 real de
`licencia medica.pdf` en el navegador (Tesseract.js), **una sola página con
sus 2 rotaciones (0°/180°) tardó 82.7 segundos**. Causa raíz estructural
(no es OCR duplicado -- ese patrón ya estaba bien evitado acá, `let txtLen`
se reasigna tras el OCR): el archivo tiene 75 páginas, 100% escaneadas, y se
procesan una por una, totalmente secuencial, cada una con 2 pasadas de OCR
completo de página. Sin paralelismo esto escala linealmente con el número de
páginas.

**Fix implementado** (`va_validarLicenciasMedicas`, index.html ~línea
12471+): se separó el trabajo en 2 fases. Fase 1 extrae el texto de CADA
página (nativo, y OCR de página completa con ambas rotaciones si hace
falta) EN PARALELO usando el mismo pool de workers ya construido para
Liquidaciones (`va_cargarOCRPool`/`va_procesarArchivosEnParalelo`,
`va_ocrPaginaMejorRotacion` ya aceptaba un `worker` opcional). Fase 2
procesa cada página EN ORDEN, una a la vez, con la lógica ORIGINAL sin
tocar (matching de RUT, tabla vs formulario individual, suma de días) --
esto es deliberado: Licencias no tiene estado pegajoso entre páginas como
Contratos, pero SÍ tiene un acumulador compartido
(`va_licMedDiasPorRut`, un Map que SUMA días si la misma persona aparece en
más de una página) que sería una condición de carrera real si se
mutara desde workers concurrentes (dos páginas del mismo RUT resolviendo
casi al mismo tiempo podrían pisarse la suma). Separar "leer" (paralelo) de
"acumular" (secuencial, en orden) elimina el riesgo por diseño, sin
necesitar ningún candado. Se agregó `va_liberarOCRPool()` al final de la
función, mismo motivo que Liquidaciones (Licencias corre temprano en el
pipeline, antes de Libro Remuneraciones/Asistencia/Contratos que dependen
del worker único global).

Validado: sintaxis OK (servido local, sin errores JS en consola). **No se
pudo medir la mejora de velocidad real en este sandbox** -- un test con
pool de 4 workers sobre solo 4 páginas reales corrió más de 9 minutos sin
terminar (mismo límite ya documentado para el intento de paralelizar
Liquidaciones: este navegador sandbox no tiene CPU real disponible para
correr varios workers de Tesseract genuinamente en paralelo, así que
"paralelo" acá compite por el mismo núcleo en vez de acelerar). Esto no
invalida el fix -- la lógica es la misma que ya se usa y probó sirviendo
para Liquidaciones en producción, y el diseño de 2 fases evita por
construcción la única condición de carrera posible -- pero la velocidad
real solo se puede confirmar en un navegador de verdad (Chrome de
escritorio del usuario), que es justo el siguiente paso pendiente: el
usuario dijo que lo iba a probar en la página real antes de aprobar el
push a GitHub/Render.

## Actualización: se agregó respaldo de IA visual a Licencias Médicas (no existía)

El usuario probó el fix del `.oxps` en local (`http://localhost:8080/index.html`,
confirmado que SÍ era la versión correcta) y el caso de Pelaez Pelaez Ana
Leonor seguía sin resolver -- pero probando `va_addRut` directo en consola
contra su fila real, el candidato correcto SÍ se generaba. La explicación
más probable: esa corrida de prueba no tenía adjunto el `.oxps` (solo
`licencia medica.pdf`), así que el fix de esa fila nunca se ejecutó -- su
única vía de lectura ahí es el comprobante individual escaneado dentro del
PDF, un formulario DIAT/DIEP donde el OCR puede fallar sin ningún respaldo,
porque **Licencias Médicas nunca llamaba a la IA (MiniMax)**, a diferencia
de Contratos/Libro/Exenciones que sí tienen un nivel de respaldo visual.

Se agregó ese nivel (mismo patrón "escalera de confianza" que
`va_validarExenciones`): si una página queda sin RUT reconocido por OCR
normal, checksum, NI el RUN recortado, y hay key de MiniMax configurada,
se manda la página como imagen a la IA (`va_iaLeerLicenciaMedica`, nuevo
helper cerca de `va_iaLeerNombreRut`, ~línea 11228) pidiendo el MISMO
esquema JSON que ya usa `licMedIA` dentro de `va_validarLiquidaciones`
(`{"nombre_trabajador","fecha_inicio","fecha_termino","numero_dias"}`) --
mantiene consistencia entre ambos módulos. El nombre leído se cruza con
`va_matchNombreNomina` contra el LH (más confiable que el RUT en formularios
de mala calidad); si matchea, se usan las fechas/días que trajo la IA para
el cálculo de "días en el período" en vez de re-intentar extraerlos del
texto OCR (que ya sabemos que salió ilegible en ese caso). Cada intento
queda en `va_iaAuditLog` con módulo `'Licencias Médicas'`, y
`va_renderLicencias()` ahora muestra el banner de páginas leídas con IA +
`va_renderIAAuditSection('Licencias Médicas')`, igual que Exenciones.

Validado: sintaxis OK. La conexión real con MiniMax se probó con una imagen
sintética (canvas con texto dibujado a mano, sin pasar por el render de PDF)
-- respondió en 2.8s con el JSON exacto esperado, incluso calculando bien
los días entre las dos fechas. **No se pudo probar contra una página PDF
real en este sandbox**: `page.render()` a canvas (el mismo paso que ya usa
`va_ocrPaginaMejorRotacion`, no es código nuevo) quedó colgado >80s sin
completar -- limitación de renderizado de PDF ya documentada para este
entorno específico, independiente de si hay OCR o IA de por medio. Pendiente
que el usuario confirme en su navegador real que la IA efectivamente
resuelve el caso de Pelaez cuando el `.oxps` no está adjunto.

## Confirmado con una corrida real completa: la ausencia del .oxps es la causa raíz de TODO lo que parecía "falla de días" -- y van 3 veces

El usuario corrió la validación real (con el respaldo de IA ya activo,
`Validacion_Acreditable_Antofagasta_Base única_2026-08-19.xlsx` + el panel
completo pegado en el chat) y pidió auditar por qué "la lógica de días"
seguía fallando -- 9 personas con "días no coinciden" y 2 sin documento.

**El panel de auditoría de IA que el usuario pegó fue suficiente para
diagnosticar TODO sin tocar el navegador ni la carpeta de documentos**:

1. **Bug real #1 -- nombre leído por IA con un token de más rompe el match.**
   El log mostraba "ALBALLAY VILLAGRÁN, PEDRO JULIO" y "VERGARA ROJAS, ROSA
   BERTINA" como "sin match", pero el LH tiene "Alballay Villagran Pedro" y
   "Vergara Rojas Rosa" -- la IA lee el nombre legal completo (con segundo
   nombre) y el LH no lo tiene. `va_matchNombreNomina` exige cobertura 1.0
   de TODOS los tokens leídos, así que un token de más (que siempre cae al
   final, porque el formato es "Apellidos, Nombres") tira el match. Fix:
   usar `va_matchNombreConRecorte` (ya existía, se usa en Libro de
   Asistencia) en vez de `va_matchNombreNomina` directo para el match de IA
   en Licencias -- recorta desde el final hasta encontrar match. Validado
   con los 2 casos reales + un candidato trampa que comparte tokens con
   ambos (para confirmar que no generaba una atribución cruzada falsa).

2. **NO había bug de días -- era el .oxps ausente, otra vez.** Calculado a
   mano desde el `.oxps` real (sumando TODOS los períodos de cada persona
   con la misma fórmula que `va_diasLicenciaEnPeriodo`), las 9 personas con
   "días no coinciden" dieron un match EXACTO 9/9 contra el "Días LH" del
   Libro de Haberes (ej. Yañez Iriarte: 6+25=31, calza con LH=31; Monroy
   Monroy: 2+14+14=30, calza con LH=30). Esto prueba que la fórmula de días
   está perfecta y que el LH fue armado con exactamente esa misma lógica de
   sumar períodos -- lo que falla es que la app, esa corrida, no estaba
   usando el `.oxps` como fuente (los valores que mostró son siempre MÁS
   BAJOS, consistentes con juntar solo fragmentos sueltos de páginas
   individuales del PDF escaneado, que no siempre cubren todos los períodos
   de una persona con licencias repetidas/renovadas en el mes).

   Es la TERCERA vez en esta misma sesión que el síntoma "no se lee bien"
   resulta ser el `.oxps` no adjuntado (antes: 18/19 faltantes de un
   corrida, y el caso de Pelaez). Como patrón ya es demasiado recurrente
   para seguir re-diagnosticándolo cada vez -- se agregó una alerta directa
   en la UI (`va_renderLicencias`, banner amarillo) que avisa apenas no
   detecta un archivo `.oxps`/`.xps` entre los documentos subidos a
   Licencias, explicando el riesgo concreto (períodos múltiples subcontados)
   en vez de dejar que el usuario tenga que adivinarlo por los resultados.

**Lección para este módulo en particular**: antes de investigar cualquier
reporte de "Licencias lee mal", lo primero es preguntar/verificar si el
`.oxps` fue adjuntado esta vez -- es, con mucha diferencia, la causa más
probable de cualquier síntoma de cobertura o días incompletos acá. El panel
de "🔍 Detalle de lectura con IA" que ya se agregó es una fuente de
diagnóstico muy rica por sí sola (qué leyó, en qué página, si matcheó) --
pedirle al usuario que lo pegue en el chat suele alcanzar para diagnosticar
sin gastar tiempo en el navegador o en releer PDFs reales.

## Dos mejoras más pedidas tras la corrida real de 11 minutos: mover la IA a la fase paralela + Excel con el mismo detalle de los paneles

Con la corrida real (75 páginas, 37 necesitando IA) tardando 11 minutos, el
usuario pidió acelerar más y que el Excel exportado traiga el mismo detalle
que se ve en los paneles de la app (no solo el resumen).

**Rendimiento**: el RUN-crop-OCR de respaldo y la llamada a IA vivían en la
Fase 2 (secuencial a propósito, para proteger la suma de días). Pero
ninguno de los dos depende de otras páginas -- solo necesitan la página y un
worker, igual que el OCR de página completa. Se movieron los 3 (OCR
completo, RUN-crop, IA) a la Fase 1 paralela; la Fase 2 quedó como una
reducción puramente secuencial y rápida (sin ningún `await` de I/O) que solo
decide qué hacer con los resultados ya calculados. Esto no cambia NINGUNA
regla de negocio, solo dónde ocurre la espera -- con 37 páginas necesitando
IA y un pool de 4, en teoría deberían pasar de -3min serializadas a
-1min en paralelo. Mismo cuidado de siempre: la escritura a
`va_licMedRuts`/`va_licMedDiasPorRut` sigue 100% en Fase 2, así que la
condición de carrera del día-sumado sigue evitada por diseño.

**Excel con detalle completo**: la hoja "Licencias" del export
(`va_exportExcel`, ~línea 15541) solo traía el resumen + faltantes. Ahora
también incluye la sección "Listado .oxps adjunto" (Sí/No, con la
advertencia si falta), "Días que no coinciden con el LH", y el detalle
completo de lectura con IA (`va_iaAuditLog` filtrado por
`modulo==='Licencias Médicas'`) -- exactamente las mismas 3 tablas que ya
se veían en `va_renderLicencias()`. Validado armando la hoja con datos
simulados (mock de `va_docResults['licencias']` + `va_iaAuditLog`) y
confirmando que el array de filas queda idéntico en estructura al panel.

Ninguno de los dos cambios se pudo medir/probar de punta a punta en este
sandbox (mismas limitaciones de render/OCR ya documentadas arriba) --
sintaxis verificada, lógica verificada por revisión de código + prueba con
datos simulados. Pendiente que el usuario confirme tiempo real y que el
Excel se vea bien en su máquina.

## El bug real de "días no coinciden": el hueco del regex FONASA era demasiado angosto (encontrado renderizando páginas reales)

Con el `.oxps` ya adjunto y el nombre-match arreglado, seguían apareciendo
9-11 personas con "días no coinciden" -- esta vez SÍ hubo que entrar a la
carpeta real (`licencia medica.pdf`, 75 páginas) y mirar el texto OCR
página por página, siguiendo el proceso del skill (`fitz`/PyMuPDF +
`pytesseract`, comparando contra el mismo regex que usa
`va_extraerDatosLicencia` en producción).

**Hallazgo**: el documento real de Antofagasta es mayormente un
"Comprobante de Licencia Médica Electrónica" (FONASA), con las fechas como
texto plano etiquetado -- `Fecha Inicio * DD-MM-AAAA ... Fecha término *
DD-MM-AAAA` -- NO el formato viejo de casillas dígito-por-dígito de Minsal.
Ya existía un regex para este formato, pero con un hueco de `{0,100}`
caracteres entre "Fecha Inicio" y "Fecha término" para saltar la columna de
Lugar/Dirección que el OCR mezcla en el medio. Midiendo las 51 apariciones
reales de "Fecha Inicio" en el PDF, el hueco real va de 22 a 132
caracteres -- **36 de 51 (70%) superan el cupo de 100** y fallan en
silencio, dejando esa página con 0 días aportados aunque el RUT/nombre sí
se haya atribuido bien. Caso real: Yañez Iriarte Guillermo Carlos tiene 2
períodos (páginas 74 y 75) -- el de la página 75 (25 días de julio) se
perdía por completo porque su dirección medía 125 caracteres, y el total
quedaba en 6 (solo el período de la página 74) en vez de 31.

También se midió el hueco chico entre CADA etiqueta y su propia fecha
("Fecha Inicio" → primer dígito): normalmente 5-7 caracteres, pero hasta 36
en algunos casos reales -- el cupo de 20 también se subió a 40.

**Fix**: `{0,100}` → `{0,200}` para el hueco grande (Inicio↔término),
`{0,20}` → `{0,40}` para los dos huecos chicos (línea ~10876 de
index.html). Validado con el texto OCR real y exacto de la página 75 de
Yañez (incluyendo el "95-08-2026" mal leído por OCR en vez de "05-08-2026"
-- se confirmó que el desborde de fecha no rompe el conteo de días de
julio, porque `va_diasLicenciaEnPeriodo` solo cuenta día por día si cae en
el mes/año pedido, así que un rango demasiado largo por un dígito mal leído
no suma de más, solo no resta): el resultado da exactamente los 25 días de
julio esperados. También se confirmó anti-falso-positivo: la misma página
tiene una sección 6 más abajo ("Desde 17-07-2026 ... Hasta 05-08-2026") que
da un resultado DISTINTO -- el regex ampliado sigue tomando la sección 3
correcta (Datos Reposo) y no la 6, porque el `[\s\S]{0,200}?` es lazy y
para en la PRIMERA "Fecha término" que encuentra, no en cualquiera.

**Metodología para seguir puliendo este tipo de lectura** (pedido explícito
del usuario, para ir armando un catálogo reusable): el patrón que funcionó
acá fue (1) confirmar el caso real con el panel de auditoría de IA que ya
pegó el usuario en el chat (no hace falta el navegador para esto), (2)
renderizar la página real exacta a texto con PyMuPDF+pytesseract
(`scripts/`, ver ejemplo de este hallazgo) para ver el layout real del
campo, (3) medir el hueco/patrón real contra TODAS las apariciones del
mismo campo en el documento (no solo el caso que falló) para elegir un
cupo que cubra la variabilidad real en vez de adivinar un número, (4)
validar el fix con `va_extraerDatosLicencia` real en el navegador (no una
réplica en Python -- ojo, una réplica en Python corrida en este entorno
puede arrastrar artefactos de encoding con acentos que no reflejan lo que
hace Tesseract.js en el navegador real, hay que preferir probar la función
JS real cuando el texto tiene tildes/ñ). Cuando el usuario pida "que más
adelante pueda leer con librerías" -- este archivo (FONASA, formato
consistente y bien etiquetado) es un buen candidato a una extracción 100%
por regex/estructura sin necesitar IA en absoluto, una vez que los cupos
de los huecos estén bien calibrados contra suficientes casos reales.

## Segundo bug de días (el del regex solo arreglaba la mitad): la IA leía bien las fechas pero mal la casilla "N° de días" -- había que calcular por rango, no confiar en esa casilla

Después del fix del regex FONASA, el usuario corrió de nuevo: Yañez Iriarte
(el caso que motivó el fix) ya NO aparecía en "días no coinciden" --
confirma que el fix funciona en el navegador real. Pero el resto de los
casos (Vilca Taipe, Pino Lagos, Santana Herrera, Alballay, Perez Carvajal,
Perez Vargas, Vergara Rojas, Fredes Jeraldo, Rojas Flores, Monroy Monroy)
seguían casi idénticos.

La diferencia: Yañez se resolvía por OCR barato (usa
`va_extraerDatosLicencia`, el regex que se arregló). Los demás se resuelven
por el respaldo de IA (`va_iaLeerLicenciaMedica`) -- una vía de código
totalmente distinta que el fix del regex nunca tocó. El prompt de la IA le
pedía tres cosas: `fecha_inicio`, `fecha_termino`, Y `numero_dias` -- este
último es la MISMA casilla "N° DE DÍAS" que ya sabíamos que el OCR lee mal
(por eso el fix del regex calcula los días por diferencia de fechas en vez
de leer esa casilla) -- pero el código que consume la respuesta de la IA
todavía confiaba directo en `leidoIA.numeroDias` sin ese mismo resguardo.
Cuando la IA lee bien las dos fechas pero falla en leer bien esa casilla
puntual (mismo tipo de error, ahora del lado de la IA en vez del OCR), el
resultado sale `null` o mal, y ese período aporta 0 días -- explica los
casos que quedaban en exactamente 0 (Fredes Jeraldo, Alballay) pese a que
el nombre sí matcheaba bien.

**Fix**: en el bloque que arma `datosIA` (~línea 12630 de index.html),
ahora se calcula `dias` como `(fechaTermino - fechaInicio + 1)` cuando la
IA devolvió ambas fechas parseables, y solo se cae a `numeroDias` si no se
pudo. Validado con datos simulados reproduciendo el caso real de Fredes
Jeraldo (`numeroDias:null`, fechas del `.oxps` real) -- el resultado ahora
da los 10 días de julio esperados, en vez de 0.

**Mejora pedida explícitamente por el usuario**: quería ver, junto al
número de días, las fechas de cada período encontrado como observación
auditable ("cuántos de esos días son del mes que estamos auditando, y si
hay más de un período, que se vea la suma"). Se agregó
`va_licMedFechasPorRut` (Map rutNorm → lista de `{inicio,termino,
diasEnPeriodo}`) y el helper `va_registrarDiasLicencia()` que centraliza
las 3 vías que antes escribían directo en `va_licMedDiasPorRut` (tabla
oxps, tabla PDF escaneada, formulario individual) para que todas alimenten
también este nuevo registro sin duplicar lógica. La tabla "Días que no
coinciden" (panel y Excel) ahora trae una columna "Observación (períodos
encontrados)" con cada rango de fechas y cuántos días de ese rango caen en
el mes auditado -- validado con datos simulados reproduciendo el caso de
Yañez (2 períodos, 22-06→06-07 y 07-07→05-08, 6+25=31 días, reconstruye
las fechas exactas desde fechaInicio+dias).

**Metodología reafirmada**: cuando dos vías de código distintas hacen lo
mismo (leer fecha+días de una licencia), CUALQUIER fix de robustez
aplicado a una (ej. "calcular por rango, no por casilla") hay que
replicarlo en la otra explícitamente -- no basta con arreglar el síntoma
más visible. La pista de que faltaba la segunda mitad del fix fue mirar
CUÁL caso se arregló solo (Yañez, vía OCR) contra cuáles no (el resto, vía
IA) y preguntarse por qué la misma clase de fix no aplicaba a ambos.

## Con la columna de observación ya se ve el patrón real: no son bugs de código, es calidad de escaneo -- y eso también hay que hacerlo visible

Con la observación de fechas ya en pantalla, el usuario preguntó por qué
"seguía saltándose" tantas hojas y pidió que el motor "por capas" encuentre
TODAS las posibilidades sin retroceder. Se investigó cada caso real
(Vilca Taipe, Pino Lagos, Santana Herrera, Perez Vargas, Monroy Monroy)
buscando su RUT en el texto OCR completo de las 75 páginas reales:

- **Vilca Taipe, Perez Vargas**: su RUT aparece 0-1 veces en TODO el PDF
  escaneado -- solo uno de sus 2 períodos tiene una página física en este
  archivo. El otro período genuinamente NO ESTÁ en el PDF (solo en el
  `.oxps`). No hay nada que leer ahí -- no es un bug, es una fuente que
  falta.
- **Santana Herrera, Monroy Monroy**: acá SÍ hay una página por cada
  período (2 y 2 apariciones de RUT respectivamente), pero mirando el texto
  OCR real de esas páginas se encontraron dígitos de fecha corruptos:
  Santana tiene `Fecha Inicio * 23-08-2026` cuando el real es `23-06-2026`
  (mes "06" leído "08" -- la fecha queda inconsistente, término antes que
  inicio, y el código la rechaza correctamente); Monroy tiene
  `Fecha Inicio * 26-06-2025` cuando el año real es 2026. Son errores de
  OCR sobre una foto de mala calidad, no algo recuperable con un regex más
  permisivo sin arriesgarse a inventar fechas.

**Lo que SÍ se hizo** (aditivo, sin tocar nada que ya funcionaba -- pedido
explícito "sin retroceder"): antes, cuando el RUT/nombre se atribuía bien
pero la fecha no se podía leer, esa página contribuía 0 días EN SILENCIO,
sin ningún rastro -- indistinguible de "esta persona no tiene licencia esos
días". Se agregó `va_licMedPaginasSinFecha` (lista de
`{pagina,rut,nombre}`, poblada en el único punto donde ya se decide
`rutFinal` y se intenta leer la fecha) y una sección nueva en el panel +
Excel: "⚠ Páginas con trabajador identificado pero fecha ilegible (revisar
a mano)". Esto no arregla el dato faltante (no se puede, físicamente no es
legible) pero lo saca de la invisibilidad -- ahora se sabe EXACTAMENTE qué
páginas necesitan revisión humana en vez de asumir en silencio que el
período no existe.

**Conclusión para el usuario, importante repetir cada vez que se vuelva a
preguntar por esto**: el techo de cobertura de SOLO el PDF escaneado está
limitado por (a) qué períodos tienen página física en el archivo (algunos
genuinamente no la tienen) y (b) la calidad de la foto/escaneo de cada una.
Ninguno de los dos se arregla con más regex. El `.oxps` es la única fuente
sin ninguno de estos dos problemas (texto nativo, no escaneado, 68/68
filas ya confirmadas 100% correctas) -- es la vía de máxima cobertura real,
no una opción secundaria. El banner de "no se detectó el .oxps" debe
tomarse como el bloqueador #1, no como una advertencia opcional.

## El panel solo mostraba las EXCEPCIONES -- daba la falsa impresión de que se perdía gente que en realidad estaba bien

El usuario, viendo que solo aparecían ~7 filas en el panel pese a que el LH
tiene ~50 trabajadores con licencia, pidió explícitamente "que APAREZCAN
TODOS los que tienen licencia médica". El diseño anterior de
`va_renderLicencias()` solo mostraba dos tablas: "sin documento adjunto"
(faltantes) y "días que no coinciden" -- cualquier trabajador con TODO bien
(nombre atribuido, RUT encontrado, días coincidiendo exacto con el LH)
nunca aparecía en ninguna tabla, solo contaba en el número del KPI
"Cubiertos". Con ~40 de 50 casos típicamente en ese estado "todo bien", el
panel visualmente parecía estar "perdiendo" la mayoría de la gente cuando
en realidad la mayoría SÍ estaba correcta -- un problema de presentación,
no de lectura.

**Fix**: se agregó `va_docResults['licencias'].detalleCompleto` -- un
array con los `conLicLH.length` trabajadores (TODOS los que tienen licencia
en el LH, sin filtrar), cada uno con su estado (✅/⚠/❌), días LH, días
doc, y observación de períodos. Se renderiza como una tabla nueva
"📋 Detalle completo" al tope del panel (antes de las tablas de
excepciones, que se mantienen igual como resumen rápido) y se agregó
también al Excel como su propia sección. Validado con datos simulados (3
casos: sin doc, con diferencia, y uno 100% OK) confirmando que el caso
"OK" -- que antes era invisible -- ahora aparece en la tabla.

**Lección de UX para este tipo de auditoría**: cuando el pedido es "cotejar"
o "cruzar" contra una nómina completa, mostrar SOLO las excepciones (por
más que sea lo más "accionable") puede hacer parecer que el sistema está
fallando mucho más de lo que realmente está fallando -- el usuario no tiene
forma de distinguir "no veo a Fulano porque está bien" de "no veo a Fulano
porque se perdió". Siempre que la nómina base es chica/mediana (acá ~50),
vale la pena mostrar el universo completo con estado por fila, no solo el
subconjunto con problemas.

## Reintento a escala alta para las páginas "fecha ilegible" + progreso real de la barra

El usuario pidió confirmar entrando yo mismo al PDF si las 14 páginas
marcadas "fecha ilegible" realmente no se podían leer mejor (con OCR "por
rangos" o con IA), y por separado señaló que la barra de progreso de la
validación no es "real" (1% a 100% proporcional al trabajo real).

**Páginas ilegibles**: se renderizaron las 14 páginas reales a escala 4.0
(el pipeline normal usa 2.5) y se OCR'earon con pytesseract. Resultado
mixto real: algunas mejoran mucho (página 35 de Monroy Monroy pasa de
irrecuperable a perfectamente legible), otras mejoran parcialmente (página
60 de Santana Herrera: "Fecha Inicio" pasa a leerse bien pero "Fecha
término" sigue con basura), y varias siguen sin dar ningún match de
"Fecha Inicio/término" ni a escala alta (19, 24, 25, 47, 55, 62, 73 --
probablemente otro layout o daño físico del escaneo, no resoluble con más
escala). Se encontraron además 2 problemas de regex reales en el camino:
el separador de fecha a veces es "." no "-" (ej. "25.07-2026", página 49
de Pino Lagos), y cuando "Fecha término" queda irrecuperable pero "Fecha
Inicio" + "N° Días" SÍ se leen limpios por separado (caso Santana), se
puede calcular el término desde ahí en vez de descartar la página entera.

**Fix implementado** (`va_extraerDatosLicencia`, ~línea 10897): separador
`[-.\s]?` en vez de `[-\s]?`; nuevo fallback de último recurso
Inicio+N°Días cuando el rango completo no matchea (acotado a 1-150 días
para no confiar ciegamente en una casilla que ya sabíamos poco fiable).
Y una **Fase 3 nueva** en `va_validarLicenciasMedicas`: después de la Fase
2, para las páginas que quedaron en `va_licMedPaginasSinFecha` de ESE
archivo, se re-renderiza SOLO esas páginas a escala 4.0 y se reintenta la
extracción -- si esta vez sí da fecha válida, se registra el aporte de
días y la página sale de la lista de "sin fecha". Acotado a un puñado de
páginas (normalmente <15 de 75), así que el costo extra en tiempo es
chico comparado con re-hacer TODO el archivo a escala alta. Validado con
el texto OCR real de la página 60 (Santana Herrera) a escala 4.0: antes
daba `null`, con los 2 fixes de regex juntos da exactamente los 22 días de
julio esperados (coincide con el `.oxps`).

**Progreso real de la barra**: se confirmó que `va_validarLiquidaciones` sí
llama a `va_setProg` proporcional a páginas/archivos completados, pero
`va_validarLicenciasMedicas` NUNCA llamaba a `va_setProg` -- la barra
quedaba clavada en 42% (el checkpoint de "validando licencias médicas...")
durante los varios minutos que tarda ese paso, y saltaba de golpe a 50% al
terminar. Se agregó una llamada a `va_setProg` dentro del consumidor de la
Fase 1 (paralelo), proporcional a páginas completadas del archivo,
mapeada al rango 42-49% -- mismo patrón que ya usa Liquidaciones (rango
6-34%).

Ninguno de los cambios de esta ronda se pudo probar de punta a punta en
este sandbox (misma limitación de render/OCR ya documentada); validado
por: sintaxis OK, regex probado contra texto OCR real capturado de la
carpeta, y revisión de código para la Fase 3/progreso (lógica análoga a
patrones ya probados en producción para Liquidaciones).

## La corrida real confirmó el salto (44/49 ✅) pero destapó una regresión propia: año corrupto colando un total inflado

El usuario corrió de nuevo con todos los fixes de la ronda anterior: pasó
de ~37 a 44 de 49 trabajadores en ✅. Pero Pino Lagos pasó de "24/17" (antes,
subcontando) a "24/**42**" (ahora, SOBRE-contando) -- la observación mostraba
un período con año "19-07-**2006**" en vez de 2026. Causa: el reintento a
escala alta (Fase 3, agregado en el commit anterior) leyó el año de
"Fecha Inicio" con un dígito perdido/corrupto (2026→2006), pero como
"Fecha término" sí leyó bien (2026), el rango `dFin-dIni` daba ~20 años =
miles de días -- y ese rango gigante, aunque construido sobre una fecha de
inicio falsa, igual "pasaba por" julio 2026 en algún punto del conteo día a
día y colaba un número de días fantasma (25 en vez de los 7 reales de ese
período). Antes del reintento a escala alta esta página simplemente no
daba ningún match (quedaba en "sin fecha", visible) -- el reintento, al
mejorar la lectura de UNA fecha pero no la otra, la empeoró silenciosamente
en vez de dejarla afuera.

**Fix**: tope de 200 días en el rango completo (Inicio↔término) antes de
aceptarlo -- las licencias reales de este documento no superan ~84 días
corridos, así que cualquier rango de miles de días es, por construcción,
un año mal leído en alguna de las dos fechas, nunca un dato real. Se
agregó el mismo resguardo (año dentro de `va_periodoAnio ± 1`) al fallback
de "Inicio + N° Días" que ya existía, por el mismo tipo de corrupción
posible ahí. Validado con el texto real corrupto (año 2006): antes de
este fix habría colado un aporte de 0 días con una fecha de inicio
inventada (2006) mostrada en la observación -- ahora correctamente da
`null` (queda en "sin fecha legible" para revisión manual). Re-validado el
caso ya confirmado de Santana Herrera (22 días) sin regresión.

**Lección**: cuando se agrega un reintento con una fuente de lectura más
generosa/agresiva (acá, escala 4.0) como red de seguridad para casos que
ya fallaban, hay que sumarle SUS PROPIOS resguardos de sanidad -- no basta
con que "ya había un check antes" (el `dFin>=dIni` existía, pero no
alcanza para detectar un año mal leído que igual da un rango cronológicamente
válido, solo absurdamente largo). Cada vez que se ensancha un rango de
tolerancia (más caracteres de hueco, más escala de imagen, un fallback
nuevo), conviene preguntarse explícitamente "¿qué pasa si UNA sola cifra
sale mal en vez de todas?" antes de darlo por seguro.

**También ajustado por pedido explícito del usuario**: se sacó la sección
"🔍 Detalle de lectura con IA" del panel de Licencias (`va_renderLicencias`)
-- la considera información de diagnóstico interno, no algo que el reporte
final necesite mostrar. Las dos secciones de arriba ("días que no
coinciden" y "páginas con fecha ilegible") se mantienen. El log
(`va_iaAuditLog`) sigue completo internamente y en el Excel exportado, solo
se dejó de renderizar en el panel de esta pestaña.

## "¿Qué falta para 49/49?" -- mirar las páginas reales como IMAGEN (no solo texto OCR) destapó 3 bugs más y una lección de metodología

El usuario preguntó directo qué hacía falta para llegar a 49/49. En vez de
seguir iterando a ciegas sobre texto OCR, se renderizaron las 7 páginas
reales que seguían fallando a PNG (`fitz`, matrix 2.2) y se miraron
literalmente como imagen con el tool `Read` (paso 3.5 del proceso de este
skill) -- reveló que casi todas eran perfectamente legibles a simple vista,
lo que apuntaba a bugs de código, no de calidad de escaneo:

1. **Trampa de mi propia metodología de testing**: los primeros intentos
   de reproducir el texto OCR real en Python vía `print()`/Bash mostraban
   "�" (U+FFFD) en vez de tildes -- confundí esto con corrupción real del
   OCR y perdí tiempo pensando que "Fecha término" no se reconocía por eso.
   Guardando el mismo OCR a un archivo con `encoding='utf-8'` y leyéndolo
   con el tool `Read` (en vez de imprimir por consola), las tildes salían
   perfectas -- el "�" era 100% un artefacto de la consola de Windows en
   este entorno, nunca algo que Tesseract.js seguiría el navegador real.
   **Lección: para depurar texto OCR con tildes/ñ, siempre guardar a
   archivo UTF-8 y leer con `Read`, nunca confiar en lo que imprime la
   consola de este entorno.**

2. **Bug real: dos formatos más sin regex propio.** Página 24/25
   (González González) resultó ser "ORDEN DE REPOSO LEY N° 16.744" (Mutual
   de Seguridad/ACHS) -- formato que YA tenía regex (`Fecha de Reposo
   Laboral Desde/Hasta`), simplemente no se había verificado contra este
   caso real todavía; funcionó perfecto al probarlo. Página 33 (Mizunuma
   Pool) es formato MEDIPASS, con la fecha repetida DOS VECES en el mismo
   documento -- una limpia arriba ("Inicio de Reposo: 09-07-2026") y otra
   con ruido de OCR más abajo ("Fecha Inicio: 38-07-2026", sección
   "Datos de reposo"). Se agregó "Inicio de Reposo" como alias de
   "Fecha Inicio" en el fallback Inicio+N°Días -- como aparece ANTES en el
   texto, el regex la encuentra primero y nunca llega a necesitar la
   versión corrupta.

3. **Bug real más sutil, encontrado recién al re-testear TODO junto**: el
   candado de huecos que ya existía (`{0,40}`/`{0,200}`) no evita que el
   regex arranque el grupo de dígitos A MITAD de un número corrupto -- caso
   real Santana Herrera: OCR real dio "229.07-2026" en vez de "22-07-2026"
   (un "9" de más). Como el separador es opcional, el motor de regex
   simplemente "resbala" un carácter y arranca en "29" en vez de fallar --
   coló un día equivocado (29 en vez de 22) DESPUÉS de que el tope de 200
   días ya lo dejaba pasar como válido. Se agregó `(?<![\d.])` antes de
   cada grupo de día (mismo patrón anti-"regex se come el número vecino"
   ya usado en `va_findAllRuts` para RUTs pegados a montos) -- con esto,
   el intento a mitad de número ya no matchea, y la página cae
   correctamente al fallback Inicio+N°Días, que sí da el valor real.

**Validado**: batería de 8 casos reales juntos (los 4 nuevos + Santana +
Pino Lagos + los 2 casos de regresión ya confirmados antes) -- 8/8 dan el
resultado esperado con la versión final del código.

**Nota de entorno importante**: el servidor `python -m http.server` no
manda cabeceras `no-cache`, así que el navegador puede servir una copia
vieja de `index.html` desde caché incluso con `navigate force:true` --
hay que agregar un query string distinto cada vez (`?v=<algo>`) para
forzar la recarga real, y confirmar con algo como
`fn.toString().includes('texto que se acaba de agregar')` antes de confiar
en cualquier resultado de prueba. Esto costó tiempo real esta sesión (un
fix que ya estaba en el archivo parecía "no funcionar" porque el navegador
seguía corriendo la versión anterior).

**Con estos fixes, la expectativa realista para 49/49**:
- Los 4 casos que solo necesitaban lectura mejor (Araya Araya, Ferrada
  Muñoz, González González, Mizunuma Pool) deberían resolverse solos en la
  próxima corrida real -- validado con el texto real de cada uno.
- Santana Herrera y Rojas Flores (diferencias chicas, 1-9 días) deberían
  mejorar bastante o cerrar del todo con el fix del candado `(?<![\d.])`.
- Vilca Taipe es el único caso confirmado como NO resoluble por más que se
  mejore el código: su segundo período (10-07 a 01-10, 84 días) tiene CERO
  apariciones de su RUT en las 75 páginas del PDF escaneado -- ese dato
  físicamente no está ahí. Solo el `.oxps` lo tiene. Sin ese archivo
  adjunto, 49/49 no es alcanzable para ella pase lo que pase con el código.

## El "49/49" resultó falso: pytesseract (mi entorno de prueba) y Tesseract.js (el navegador real) NO leen igual la misma imagen

El usuario corrió de nuevo con los fixes anteriores y las 4 páginas que yo
había confirmado "perfectamente legibles" (Araya Araya, Ferrada Muñoz,
González González, Mizunuma Pool) SEGUÍAN sin dar ninguna fecha, pese a
que el texto que yo obtuve con pytesseract sí daba resultado limpio con el
regex ya arreglado. Esto confirma algo que el skill ya advertía como
riesgo teórico (ver nota más arriba sobre "�") pero que acá se volvió
real: **el motor OCR real del navegador (Tesseract.js) puede leer la MISMA
imagen peor que pytesseract**, aunque a simple vista la página se vea
perfecta -- son implementaciones/versiones distintas del mismo algoritmo
base, no intercambiables para efectos de qué tan bien leen letra chica.

**Lección dura**: nunca declarar "arreglado" ni dar una cifra final (tipo
"49/49") basándose solo en texto capturado con pytesseract fuera del
navegador -- eso prueba que el REGEX/LÓGICA es correcto, no que el OCR
real del usuario va a producir un texto lo bastante limpio para que ese
regex lo alcance a matchear. Frasear los hallazgos como "el regex ya
soporta este formato, validado con texto real" en vez de "esto va a
funcionar en tu navegador" -- son afirmaciones distintas y hay que ser
explícito sobre cuál de las dos se está haciendo.

**Fix estructural** (no otro ajuste de regex): se extendió la Fase 3
(reintento a escala alta) para que, si el reintento con OCR a escala 4.0
TAMPOCO da una fecha válida, pruebe con IA visual como último recurso
(`va_iaLeerLicenciaMedica`, ya existía para la atribución de RUT/nombre,
ahora también se usa para las fechas cuando ambos intentos de OCR
fallan). La IA lee la imagen completa de la página en vez de depender de
que el OCR carácter-por-carácter salga limpio -- no importa qué tan mal
lea Tesseract.js el texto, la IA ve la misma imagen que vería una
persona. Cada intento queda registrado en `va_iaAuditLog` con tipo
`LICENCIA_MEDICA_REINTENTO` para poder auditar cuántas páginas
necesitaron llegar hasta este último nivel.

**También ajustado** (pedido del usuario): "Días que no coinciden con el
LH" ahora incluye TANTO los casos donde se leyó un número distinto COMO
los casos donde no se pudo leer ningún día -- antes estos últimos
quedaban solo en la tabla separada de abajo ("páginas con fecha
ilegible"), dando la impresión de que la tabla principal de discrepancias
no traía todas las diferencias reales. Ambas siguen existiendo (la de
abajo da el detalle de página/motivo), pero ahora "días no coinciden" es
la vista consolidada de TODO lo que no calza, sin tener que cruzar dos
tablas mentalmente.

## Licencias Médicas: año "plausible" (±1) pero incorrecto colaba períodos con 0 días — confirmado con 2 páginas reales

El usuario reportó dos casos reales de la corrida: Fredes Jeraldo Ana Maria
mostraba "21-06-2025 a 10-07-2025 (0d)" pese a tener 10 días de licencia en
el LH, y Rojas Flores Lucia Del Carmen mostraba una fecha de inicio rara.
Se confirmó el primero con la página real (22 de `licencia medica.pdf`):
"Fecha Inicio: 21-06-2025" (año mal leído) mientras "Fecha término:
10-07-2026" sale bien -- inicio real = término - 19 días = 21-06-**2026**,
confirmando que es un dígito de año mal leído, no un dato real de 2025.

Causa: el fallback `mIniSolo` de `va_extraerDatosLicencia` (Inicio +
N° Días) ya tenía un chequeo "¿el año está a ±1 del auditado?" para
descartar años muy lejanos (ej. 2006) -- pero un año a EXACTAMENTE ±1 del
real (2025 vs 2026, el caso típico de UN dígito mal leído) pasaba ese
chequeo sin problema, y como el período completo caía en el año
equivocado, aportaba 0 días al mes auditado -- se registraba igual,
mostrando la fecha falsa en la observación en vez de quedar para revisión
manual. La rama `mComp` (Fecha Inicio + Fecha término en tabla) no tenía
NINGÚN chequeo de año, protegida solo por casualidad por el tope de 200
días (que si ambas fechas comparten el mismo año equivocado, no dispara).

**Fix**: `va_anioAceptable(fecha,dias)` (función global, no anidada,
reutilizable desde el camino de IA también) -- si el año es EXACTO, se
acepta siempre; si es "cercano" (±1, para permitir licencias que
genuinamente cruzan diciembre→enero), solo se acepta si el período
resultante aporta AL MENOS 1 día real al mes auditado (calculado con
`va_diasLicenciaEnPeriodo`, la misma función que ya se usa para el conteo
final) -- un período con año "cercano" que aporta 0 días es más señal de
dígito mal leído que de licencia vieja genuina. Aplicado a las 3 ramas de
`va_extraerDatosLicencia` (mFechas, mRango, mComp, mIniSolo) y al camino de
IA (`va_validarLicenciasMedicas`, Fase 2 y Fase 3). Validado en el
navegador real (no Python) contra el texto OCR real de la página 22 de
Fredes: antes del fix devolvía `{fechaInicio:"21-06-2025",dias:20}`
(el bug reportado), después del fix devuelve `{fechaInicio:null,dias:null}`
(cae correctamente a "sin fecha legible" para revisión manual) -- validado
también que un caso normal (año exacto, página 57 de Rojas Flores) sigue
funcionando sin cambios.

**Bug relacionado, mismo archivo**: cuando la IA matcheaba el nombre pero
`fecha_inicio` no parseaba (`va_parseFechaDDMMYYYY` exige separador `-`
exacto), el código armaba igual `datosIA={fechaInicio:null,dias:...}` --
un objeto VERDADERO aunque vacío por dentro -- y `datos=datosIA||regex`
preferÍa ese objeto vacío sobre una posible lectura buena del regex/OCR,
perdiendo una lectura potencialmente correcta. Fix: `datosIA` solo se arma
si `fiIA`/`diasIA` son utilizables Y pasan `va_anioAceptable`; si no, queda
`null` y el código cae al regex como red de seguridad. También se hizo
`va_parseFechaDDMMYYYY` tolerante a "/" además de "-" (la IA no siempre
respeta el separador pedido en el prompt).

**Actualización -- el caso de Rojas Flores SÍ se identificó, mirando la
imagen real de la página (no solo el texto OCR)**: el usuario insistió en
que "esa no es la fecha de inicio", lo que llevó a renderizar la página 58
real como PNG y mirarla directamente. "30-06-2026" SÍ está impreso en esa
página real -- pero es el valor de **"Fecha Otorgamiento"** (arriba de
todo, cuándo se emitió el documento), un campo COMPLETAMENTE DISTINTO de
"Fecha Inicio" (sección "3. Datos Reposo", que dice 02-07-2026, la fecha
real de inicio del reposo). Confirmado que ninguna rama de regex
(`mComp`/`mIniSolo`) puede confundir esto -- ambas exigen literalmente la
palabra "Inicio" antes de la fecha, y "Otorgamiento" no la contiene -- así
que la única vía que puede devolver "Fecha Otorgamiento" como
"fecha_inicio" es la IA visual (`va_iaLeerLicenciaMedica`, y su
equivalente inline en `va_validarLiquidaciones` para Lo Barnechea): el
prompt pedía "las fechas del período de reposo" sin aclarar que
"Fecha Otorgamiento" es una fecha DISTINTA que aparece prominentemente al
inicio de la página, fácil de confundir para un LLM. Fix: ambos prompts
ahora advierten explícitamente que "Fecha Otorgamiento" NO es la fecha de
inicio y señalan la sección exacta ("3. Datos Reposo") + el respaldo
("Desde"/"Hasta" en la sección "6") de donde sacar la fecha correcta.

**Lección**: cuando un valor mal leído coincide EXACTAMENTE con otro dato
real de la misma página (no es ruido/basura, es un número perfectamente
válido) es señal de que la IA/OCR agarró el CAMPO EQUIVOCADO, no que leyó
mal los dígitos -- conviene mirar la imagen completa de la página (no solo
grepear el texto OCR por el valor esperado) para encontrar dónde más
aparece ese valor exacto en la página real.

## Corregir el prompt de la IA no basta cuando el bug es determinístico -- Rojas Flores necesitó un chequeo en código

El usuario volvió a pegar el mismo dato roto de Rojas Flores Lucia Del
Carmen (período "30-06-2026 a 16-07-2026") DESPUÉS de que ya se había
"arreglado" el prompt de `va_iaLeerLicenciaMedica` (sección "Actualización
-- el caso de Rojas Flores SÍ se identificó..." más arriba) pidiéndole
explícitamente a la IA que no confundiera "Fecha Otorgamiento" con "Fecha
Inicio". **Lección: pedirle a un LLM que no cometa un error específico
reduce la probabilidad, pero no la elimina — no es una garantía.** Cuando
el error es identificable con una regla simple y determinística (acá:
"¿el valor que devolvió coincide EXACTO con otro campo real de la misma
página que no es el que pedimos?"), esa regla hay que codificarla, no
delegarla al prompt.

**Fix real**: `va_extraerFechaOtorgamiento(txt)` (index.html, junto a
`va_anioAceptable`) extrae por regex la Fecha Otorgamiento de la misma
página (texto OCR, no la imagen) — barato, ya tenemos el texto ahí. En los
2 puntos donde se consume `fecha_inicio` devuelto por la IA (Fase 2 y Fase
3 de `va_validarLicenciasMedicas`), se compara: si `fiIA` coincide EXACTO
con la Fecha Otorgamiento extraída del mismo texto, se descarta (`fiIA =
null`) y el código cae al regex normal (`va_extraerDatosLicencia`) como
red de seguridad — que si el texto no está corrompido, si encuentra la
fecha real. Validado con el texto real de la página 58 de Rojas Flores:
`va_extraerFechaOtorgamiento` extrae "30-06-2026" correctamente, coincide
con lo que la IA había devuelto como fecha_inicio, confirmando el
diagnóstico.

**Segundo fix relacionado, mismo commit**: se agregó el fallback simétrico
que faltaba en `va_extraerDatosLicencia` — "Fecha término" + "N° Días" →
derivar Inicio (ya existía el espejo "Inicio + N° Días → término", pero no
al revés). Caso real: Fredes Jeraldo Ana Maria, página 22 -- "Fecha
Inicio" tiene el año corrupto (rechazado correctamente por
`va_anioAceptable`), pero "Fecha término: 10-07-2026" y "N° Días: 20" SALEN
LIMPIOS por separado — sin este fallback, la página quedaba en "sin fecha
legible" (mejor que antes, que mostraba una fecha falsa, pero seguía sin
resolver el caso). Validado en el navegador real contra el texto OCR real
de la página: `fechaInicio` se deriva correctamente a 21-06-2026 (no
21-06-2025), dando exactamente 10 días de julio -- coincide 100% con el
LH.

**Metodología reforzada**: cuando un fix basado en "mejorar el prompt de
la IA" no se puede confirmar con una corrida real inmediata, no darlo por
resuelto — si el mismo síntoma vuelve a aparecer, buscar si existe una
regla determinística (comparar contra otro campo real de la página, un
tope numérico, un patrón de texto) que se pueda codificar en vez de seguir
ajustando el texto del prompt a ciegas.
