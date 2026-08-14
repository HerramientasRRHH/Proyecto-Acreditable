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
