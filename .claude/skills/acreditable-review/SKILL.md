---
name: acreditable-review
description: Auditar y corregir problemas de lectura con IA (MiniMax) dentro del Validador Acreditable de este proyecto (index.html) — cuando el usuario dice que el Libro de Asistencia, el Contrato, la Licencia Médica u otro documento "no se está leyendo bien", "dice faltante y no debería", "el matching falla", o cualquier reporte donde el Diagnóstico IA muestre resultados que no calzan con lo esperado. Usar SIEMPRE que se toque va_validarLiquidaciones, va_matchNombreNomina, va_clasificar, o cualquier lógica de lectura/atribución con IA en este repo, incluso si el usuario no pide una "auditoría" explícitamente — cualquier cambio a esa lógica debe pasar por este proceso antes de commitear.
---

# Auditoría de lectura con IA — Validador Acreditable

Este skill encapsula cómo se diagnosticó y arregló, con datos reales, dos bugs
de la lectura con IA en este proyecto (matching de nombres del Libro de
Asistencia, detección de firma de Contrato). La lección central: **nunca
arregles esto adivinando** — la IA (MiniMax) y el matching de nombres fallan
de formas específicas y no intuitivas (orden de nombre invertido, apellido
intermedio omitido, páginas fuera de orden) que solo se descubren mirando
datos reales.

## Por qué este proceso y no "leer el código y arreglar"

Este código junta tres fuentes de incertidumbre a la vez: OCR/lectura visual
de manuscritos, matching de nombres con variaciones de transcripción, y un
PDF armado por terceros (BUK/Akro) cuyo orden interno no es confiable. Un
"❌ faltante" en el reporte puede significar tres cosas completamente
distintas — la IA nunca leyó la página, la leyó pero el nombre no matcheó, o
el documento genuinamente no está en el PDF — y cada una requiere un fix (o
ningún fix) diferente. Sin mirar la página real y la respuesta real de la IA,
es fácil "arreglar" el caso equivocado.

## El proceso (en orden — no saltear pasos)

### 1. Descartar problema de conexión primero
Mirar el cuadro "🔧 Diagnóstico IA" del reporte (`va_iaDiag`, renderizado en
`va_renderLiq`, ~línea 13100+ de index.html): dice si está "conectada" y
cuántas páginas se leyeron ok vs con error. Si hay errores de conexión, el
problema es la key/CORS/cuota — no tiene sentido seguir a los pasos
siguientes hasta resolver eso.

### 2. Conseguir los documentos reales de la corrida cuestionada
Necesitás el PDF fuente (Liquidaciones — incluye Libro y Contrato
intercalados, no son archivos separados en Lo Barnechea/Las Condes/
Mejillones) y el Libro de Haberes (nómina `.xlsx`, headers en fila 6,
columnas clave: `Nombre Completo`, `Número de Documento` = RUT,
`Fecha Ingreso Compañía`, `Fecha Término Trabajo`). Pedíselos al usuario si
no los tenés — no se puede auditar nada sin los archivos reales.

### 3. Elegir una muestra de casos flageados, con controles
Tomá 5-10 casos ❌/⚠ del reporte, y 2-3 casos ✅ como control (para confirmar
que el comparador funciona en el caso positivo también).

### 3.5. Antes de asumir la estructura de un documento nuevo, MIRALO
Si estás por auditar/implementar algo sobre una base o tipo de documento que
todavía no conocés (ej. entrar a Antofagasta después de haber trabajado solo
en Lo Barnechea), no asumas que se organiza igual. Renderizá 2-3 páginas
reales a PNG con PyMuPDF y mirálas con el tool `Read` (que sí puede ver
imágenes) antes de escribir ningún prompt o regex:

```python
import fitz
doc = fitz.open(r"ruta\al.pdf")
pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.8, 1.8))
pix.save(r"ruta\salida.png")
```

Esto fue lo que reveló, al pasar de Lo Barnechea a Antofagasta, que:
Contrato/Liquidaciones/Libro ahí son 100% fotocopias escaneadas (cero texto
nativo, a diferencia de Lo Barnechea donde Liquidaciones/Contrato eran
digitales); que el Contrato individual por trabajador en realidad empaqueta
3 documentos con firma propia cada uno (Contrato + Anexo Cargo + Anexo Pacto
HHEE); y que ahí SÍ aparecen ambas firmas (trabajador y empleador) juntas
bajo el mismo encabezado, a diferencia de Lo Barnechea donde había que
inferir por descarte. Nada de esto se ve leyendo el código o el texto
extraído — solo mirando la página real.

### 4. Reproducir el llamado a la IA FUERA del navegador
Usá `scripts/call_ia_page.py` (bundled en este skill) para renderizar
páginas puntuales del PDF y mandarlas al mismo endpoint/modelo/prompt que usa
`va_iaLeerImagen` en index.html:

```
python scripts/call_ia_page.py "ruta\Liquidaciones.pdf" --paginas 15,44,56 --key sk-cp-...
```

Esto muestra EXACTAMENTE qué contesta la IA para esa página, sin depender de
lo que el navegador ya calculó (que puede estar afectado por el bug que
estás buscando). Nota de entorno: en esta máquina `python`/`pip` del PATH no
sirven — usar la ruta completa
`C:\Users\agutierrez\AppData\Local\Programs\Python\Python313\python.exe` (o
`py`). `pymupdf` y `openpyxl` ya están instalados; `requests` puede hacer
falta instalarlo.

Si el prompt real en index.html cambió desde que se escribió este script
(buscar `'Esta es una página de un legajo de RRHH chileno'` en
`va_validarLiquidaciones`, ~línea 11395), actualizar el prompt en el script
también — si no, estarías probando un prompt viejo.

### 5. Clasificar cada caso encontrado
- **La IA leyó bien pero el matching lo rechazó** → bug de código,
  arreglable. Este fue el caso del Libro: la IA leía "Dasnia Arcos Salinas"
  (orden invertido) para la trabajadora "Arcos Salinas Dasnia Andrea", y el
  matching por Levenshtein-de-string-completo lo rechazaba.
- **La IA leyó mal por letra ilegible / mala calidad de imagen** → esperable,
  debe seguir en revisión manual. No es un bug — no hay forma de leer lo que
  no es legible.
- **La página ni siquiera existe en el PDF** → falta de documentación del
  lado del usuario (archivo no subido, foto no tomada), no es un bug de
  código. Avisar al usuario, no "arreglarlo" en el código.

Si aparece un patrón repetido en la muestra (varios casos con el mismo tipo
de falla), correr `--candidatas` en `call_ia_page.py` para escanear TODO el
PDF y tener un número real de cobertura antes de tocar código — un patrón
visto en 3 ejemplos puede no representar el problema real a escala.

### 6. Diseñar y validar el fix con los MISMOS casos reales
Primero replicá el algoritmo en Python (rápido de iterar) — para matching de
nombres, usá/extendé `scripts/match_nombre.py` (réplica exacta de
`va_matchNombreNomina`/`va_tokensNombre`/`va_coberturaTokens`,
~línea 10886+ de index.html). Confirmá el fix contra:
  - Los casos reales encontrados en el paso 4-5 (deben pasar a matchear/
    detectarse correctamente).
  - Un **sanity check anti-falsos-positivos**: cada nombre real de la nómina
    probado contra sí mismo debe matchear siempre consigo mismo y nunca con
    otro trabajador (`python scripts/match_nombre.py "ruta\nomina.xlsx"`
    ya hace esto automáticamente). Sin este check, un fix que "arregla" los
    casos difíciles fácilmente empieza a cruzar identidades — mucho peor que
    dejar el caso sin resolver.

Recién ahí portar el fix a JavaScript en `index.html`. Si tocás
`va_matchNombreNomina`/`va_tokensNombre`/`va_coberturaTokens`, actualizá
también `scripts/match_nombre.py` para que seas fiel a la misma lógica (y
viceversa: si encontrás el bug primero en Python, el fix probablemente nace
ahí y se porta al JS después).

**Si el nombre viene impreso/tipeado (no manuscrito)** en el documento —
como el "TRABAJADOR SR." del Libro de Antofagasta, a diferencia del cuaderno
manuscrito de Lo Barnechea — probá primero con OCR local (Tesseract, ya
integrado vía `ren_ocrWorker`/`cargarOCR()`) antes de gastar una llamada a la
IA visual: extraé el nombre con un regex tolerante a ruido, matchealo con
`va_matchNombreNomina`, y solo si falla recién ahí llamá a la IA. Medido
contra 30 páginas reales del Libro de Antofagasta, el OCR solo resuelve
~15-20% de los casos sin gastar IA (la alineación/calidad de cada foto varía
mucho) — no es una bala de plata, pero al ser gratis siempre vale la pena
intentarlo primero. Cuando el regex de extracción capture texto de más
(ej. arrastra una etiqueta como "MES" pegada al nombre), es más robusto
agregar esa palabra a `VA_STOP_TOKENS` que perseguir cada variante de ruido
con un regex más estricto — el matcher por tokens ya está diseñado para
tolerar basura alrededor del nombre real.

### 7. Chequeo de sintaxis antes de commitear
No hay forma de correr el flujo completo de la app con archivos reales sin
un mecanismo de subida de archivos en el navegador sandbox de Claude Code —
así que el mínimo control es:
1. Levantar un servidor local en la carpeta del proyecto:
   `python -m http.server PUERTO` (usar la ruta completa de python, ver
   paso 4).
2. Abrir `index.html` en el navegador (`preview_start` / `navigate` a
   `http://127.0.0.1:PUERTO/index.html`).
3. Revisar la consola (`read_console_messages` con `onlyErrors: true`) — el
   único error esperable es un 404 de `config.js` (no se generó porque no
   corriste `build.sh`), cualquier otro error de sintaxis JS es un problema
   real.
4. Probar las funciones nuevas/modificadas directo en la consola
   (`javascript_tool`) contra los mismos casos reales del paso 4-6, y
   confirmar que el JS da el mismo resultado que la validación en Python.
5. Cerrar el servidor local (`pkill -f "http.server PUERTO"` o similar)
   cuando termines.

### 8. Commit + push solo después de 5-7, nunca antes
Mensaje de commit largo: qué bug es, qué evidencia real lo confirma (no
"creo que" — números concretos de la auditoría), y cómo se validó el fix.
Esto es lo que le permite a la próxima persona (o a vos, en el próximo
chequeo) confiar en el commit sin tener que re-auditar desde cero.

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

## Alcance

Este proceso aplica a cualquier lectura con IA en este proyecto, no solo
Libro/Contrato — mismo patrón para Licencias Médicas leídas con IA
(`licMedIA` en `va_validarLiquidaciones`), Exención de Cotizar
(`va_validarExenciones`), y el Libro de Asistencia de Antofagasta
(`va_validarLibroAsist`, ver tabla de bases abajo). Vitacura todavía no
tiene lectura con IA de su Libro (`va_validarVitacuraLibroAsist` sigue
siendo solo conteo de páginas) — pendiente si algún día se pide.

Cada lectura con IA debería dejar su rastro en `va_iaAuditLog` (con un
nombre de módulo propio) y renderizarse con `va_renderIAAuditSection(nombreModulo)`
al final del render function de SU PROPIO módulo (Libro dentro de la pestaña
del Libro, Contrato dentro de Liquidaciones, etc.) — pedido explícito del
usuario: no juntar todo en una pestaña aparte, cada módulo muestra su propio
detalle integral.

### Bases conocidas — cómo vienen sus documentos

| Base | Contrato/Liq/Libro | Firma | Libro aplica a | Notas |
|---|---|---|---|---|
| Lo Barnechea / Las Condes / Mejillones | Contrato y Libro intercalados DENTRO del PDF de Liquidaciones (BUK, mayormente digital) | QR/electrónica (texto "Firmado electrónicamente por") | Solo `dias<30` (caso MENOS_30 de `va_clasificar`) | Nombre del Libro a veces manuscrito |
| Antofagasta | Liquidaciones y Libro en archivos SEPARADOS, divididos por letra de apellido (~24 archivos c/u); Contrato en archivo individual por trabajador (bundlea Contrato+Anexo Cargo+Anexo HHEE) | Física (Liq/Libro, requiere OCR) o QR con ambas partes juntas bajo el mismo encabezado (Contrato) | TODOS los activos, sin importar días — NO filtrar por `dias<30` acá | 100% escaneado, cero texto nativo — nómina ~350 trabajadores, volumen de páginas mucho mayor |
| Vitacura | Contrato en slot propio (`va_validarContratosVitacura`); Libro sin IA todavía | — | — | Pendiente de auditar si se pide trabajar acá |

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

## Corriendo una auditoría de prueba completa: usa Python, no el navegador sandbox

Se intentó correr `va_ejecutar()` completo en el navegador sandbox de Claude
Code con los 82 archivos reales de Antofagasta (populando `va_docsData`
directo vía `fetch()`+`File()`, sin pasar por los `<input>` del DOM). El
OCR client-side (Tesseract.js) en ese entorno resultó >30s por página —
a esa velocidad, las ~450 páginas solo de Liquidaciones habrían tardado
horas. No se pudo confirmar si es una limitación del sandbox específicamente
o representativa de hardware real, así que no lo tomes como señal de que el
OCR del navegador esté roto — solo como que ese camino no sirve para probar
rápido acá. Para una auditoría de prueba a escala completa, replicá la
lógica en Python (como en el resto de este proceso) y corré los sweeps en
background con `run_in_background` — MUCHO más rápido (pytesseract nativo)
y permite hacer varios sweeps en paralelo mientras se revisan resultados.
No se pudo probar el fallback a IA visual en este modo porque cargar la
API key real en el navegador está bloqueado por el clasificador de permisos
(manejo de credenciales) — quedó sin ejercitar esa parte del pipeline.

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

## Contexto del proyecto (por si hace falta reconstruirlo)

- Repo: `Proyecto-Acreditable` en GitHub (`HerramientasRRHH/Proyecto-Acreditable`),
  rama `main`. App de una sola página (`index.html`, ~15.000 líneas).
- Deploy: Render (Static Site), auto-deploy al pushear a `main`. URL:
  `https://proyecto-acreditable.onrender.com/`.
- IA: MiniMax, endpoint compatible con Anthropic Messages
  (`https://api.minimax.io/anthropic`, modelo `MiniMax-M3`), configurado vía
  `render.yaml`/`.env` como `MINIMAX_API_KEY`. La key vive en `.env` en la
  raíz del repo (no versionado) — usarla para auditar, nunca commitearla ni
  loguearla en texto plano en ningún archivo que sí se commitee.
- Funciones clave en `index.html`:
  - `va_validarLiquidaciones()` (~línea 11160+) — el loop página-por-página
    que clasifica y lee con IA.
  - `va_iaLeerImagen()` (~línea 10985+) — el llamado genérico a la IA.
  - `va_matchNombreNomina()` / `va_tokensNombre()` / `va_coberturaTokens()`
    (~línea 10886+) — matching de nombres por tokens.
  - `va_clasificar()` (~línea 12082+) — reglas de qué documentos exige cada
    caso (Contrato/CI/Antecedentes/Libro/Licencia Médica).

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
