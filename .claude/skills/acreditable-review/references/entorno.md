# Entorno de trabajo y trampas de la herramienta

> Parte del skill `acreditable-review`. Leer **antes de la primera medición** de una sesión: casi
> todas estas trampas ya costaron tiempo real al menos una vez, y varias produjeron conclusiones
> falsas (no solo demoras).

## Rutas de esta máquina

| Qué | Ruta |
|---|---|
| Python | `C:\Users\agutierrez\AppData\Local\Programs\Python\Python313\python.exe` (el `python` del PATH **no** sirve) |
| Tesseract (para `pytesseract`) | `C:\Users\agutierrez\AppData\Local\Programs\Tesseract-OCR\tesseract.exe` — **no está en el PATH**, hay que setear `pytesseract.pytesseract.tesseract_cmd` en cada script |
| Proyecto | `C:\Users\agutierrez\Desktop\Proyectos\Proyecto Acreditable` |
| Documentos reales | `Documentos Antofagasta\` y `Documentos Lo Barnechea\` dentro del proyecto |
| Key de MiniMax | `.env` en la raíz del proyecto (`MINIMAX_API_KEY`), no versionado — leerla desde el script, **nunca** imprimirla ni commitearla |

`pymupdf` (`fitz`), `openpyxl`, `pytesseract`, `Pillow` y `requests` ya están instalados.

## La trampa más cara: pytesseract ≠ Tesseract.js

**Una prueba con pytesseract demuestra que el REGEX / la LÓGICA es correcta. No demuestra que el
OCR real del navegador vaya a producir un texto lo bastante limpio para alcanzarla.** Son
implementaciones distintas del mismo algoritmo base y leen la misma imagen distinto.

Esto ya produjo un "49/49 resuelto" que resultó falso: 4 páginas confirmadas "perfectamente
legibles" con pytesseract seguían sin dar ninguna fecha en la corrida real del usuario.

Consecuencias prácticas:
- Frasear los hallazgos como *"el regex ya soporta este formato, validado con texto real"*, nunca
  como *"esto va a funcionar en tu navegador"*.
- Lo que **sí** transfiere directo es la medición de píxeles sobre el canvas (densidad de tinta,
  geometría): no depende del motor OCR. Lo que **no** transfiere es cualquier cosa anclada a que
  una palabra se reconozca.
- Una prueba aislada con un `ren_ocrWorker` recién cargado tampoco predice el comportamiento dentro
  de una corrida larga, donde ese worker ya procesó cientos de páginas (ver el caso de PSM 4, que
  daba 46/46 aislado y 0 en producción).

## Texto OCR con tildes: guardar a archivo UTF-8, no imprimir por consola

La consola de este entorno muestra `�` en lugar de tildes/ñ y hace pensar que el OCR corrompió el
texto cuando no es así. Guardá siempre a archivo con `encoding='utf-8'` y leelo con el tool `Read`.
Esto ya costó tiempo persiguiendo una corrupción que no existía.

Mismo problema al revés: `print()` de un dict con acentos revienta con `UnicodeEncodeError`
(`cp1252`). Escribí a archivo y listo.

## El servidor local sirve copias viejas

`python -m http.server 8080` no manda cabeceras `no-cache`, así que el navegador puede seguir
ejecutando la versión anterior de `index.html` incluso con `navigate force:true`. Un fix que ya
estaba en el archivo puede parecer que "no funciona".

1. Navegá siempre con un query string distinto: `http://127.0.0.1:8080/index.html?v=<algo-nuevo>`.
2. Confirmá que corre lo que creés antes de sacar cualquier conclusión:
   `va_validarLiquidaciones.toString().includes('<texto que acabás de agregar>')`.

## Auditorías a escala: Python en background, no el navegador

Correr `va_ejecutar()` completo en el navegador sandbox con los archivos reales no es viable: el
OCR client-side ahí da >30s por página (y el render de PDF solo, sin OCR, también). Para una
auditoría a escala completa, replicá la lógica en Python y corré los sweeps con
`run_in_background` — mucho más rápido y podés lanzar varios en paralelo mientras revisás
resultados.

No lo tomes como señal de que el OCR del navegador esté roto: es una limitación de este sandbox, no
necesariamente del hardware real del usuario.

## Auditá a la MISMA escala que usa el código real

`va_getPdfTextOCR` usa escala 2.5 por defecto, pero `va_validarLiquidaciones` hace su **propio** OCR
inline a escala **3.0**. Auditar a la escala equivocada reproduce bugs que el código real no tiene y
da un resultado sistemáticamente peor: un audit corrido a 2.5 reportó "no resuelto" un caso que ya
se había verificado a mano que sí funcionaba.

Antes de medir nada, confirmá a qué escala hace su OCR la función exacta que estás probando.

## `pdfjsLib.getDocument` no se puede mockear acá

`pdfjsLib.getDocument = miStub` no tira error pero tampoco cambia nada (`pdfjsLib.getDocument !==
miStub` después de asignar). No se puede armar un test rápido con PDFs falsos; hay que usar
archivos reales o probar la lógica aislada.

## Verdad de terreno: mirá la IMAGEN, no solo el texto OCR

Para calibrar cualquier detector visual (firma, sellos, casillas marcadas) hace falta saber la
respuesta correcta de cada página. La forma que funciona: renderizar la zona relevante de N páginas
con PyMuPDF, pegarlas en una tira vertical con el número de página escrito encima, y mirarla con el
tool `Read` (que sí ve imágenes). Con 3 tiras de ~18 recortes se etiquetan 52 páginas rápido.

Esto también sirve para diagnosticar: cuando un valor mal leído coincide **exacto** con otro dato
real de la página (no es ruido, es un número válido), es señal de que la IA/OCR agarró el CAMPO
equivocado — y eso solo se ve mirando la página entera.
