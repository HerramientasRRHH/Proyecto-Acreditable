# -*- coding: utf-8 -*-
"""
Reproduce el llamado a la IA visual (MiniMax) que hace index.html, pero
FUERA del navegador — para auditar qué contesta la IA sobre una página
puntual de un PDF sin depender de lo que ya calculó una corrida anterior.

Requiere: pip install pymupdf openpyxl requests
(pymupdf y openpyxl normalmente ya están instalados; requests a veces no).

Uso:
  python call_ia_page.py "ruta\al.pdf" --paginas 0,5,12 --key sk-cp-...
  python call_ia_page.py "ruta\al.pdf" --paginas 0-271 --candidatas --key sk-cp-...
  python call_ia_page.py "ruta\al.pdf" --candidatas --key sk-cp-... --out resultados.json

--candidatas: en vez de una lista fija, escanea TODO el PDF y arma la lista
de páginas candidatas automáticamente (texto nativo <40 caracteres y al
menos 1 imagen — el mismo criterio que usa index.html antes de mandar una
página a la IA). Usalo cuando necesites el número real de cobertura, no
solo una muestra.

La key también se puede pasar por variable de entorno MINIMAX_API_KEY en
vez de --key (más seguro que dejarla en el historial de la shell).
"""
import argparse
import base64
import json
import os
import re
import sys
import time

import fitz  # pymupdf
import requests

ENDPOINT = "https://api.minimax.io/anthropic/v1/messages"
MODEL = "MiniMax-M3"

# Mismo prompt que usa index.html (va_validarLiquidaciones, ~línea 11395) para
# clasificar páginas ambiguas del PDF de Liquidaciones. Si el prompt real del
# código cambió, actualizar acá también — buscar "Esta es una página de un
# legajo de RRHH chileno" en index.html.
PROMPT_LIBRO = (
    'Esta es una página de un legajo de RRHH chileno, dentro de un lote de Liquidaciones de Sueldo. '
    'Decime en JSON según el tipo de página: '
    'Si es una foto de un cuaderno rayado con columnas de entrada/salida por día (puede tener '
    'escritura a mano) → {"tipo":"LIBRO_ASISTENCIA","nombre_trabajador":"...","notas":"resumen '
    'breve de qué marca el cuaderno para el mes, mencionando Falta/Permiso/Licencia si aparecen",'
    '"faltas":N,"permisos":N,"licencias_dias":N} donde faltas/permisos/licencias_dias son la '
    'CANTIDAD DE DÍAS del mes marcados en el cuaderno como "Falta"/"F", "Permiso"/"P" y '
    '"Licencia"/"L" respectivamente (contá cada día marcado, no las veces que aparece la palabra '
    'escrita una sola vez para varios días seguidos). Si no hay ninguna marca de un tipo, usá 0. '
    'Si es un formulario de Licencia Médica (Minsal, COMPIN, Mutual, ISAPRE) → '
    '{"tipo":"LICENCIA_MEDICA","nombre_trabajador":"...","fecha_inicio":"DD-MM-AAAA",'
    '"fecha_termino":"DD-MM-AAAA","numero_dias":N}. '
    'Si es otra cosa (cédula de identidad, contrato, certificado, liquidación) → {"tipo":"OTRO"}. '
    '"nombre_trabajador" es el nombre escrito en la página (si hay). Respondé SOLO el JSON.'
)


def render_page_b64(doc, idx, scale=2.0):
    page = doc[idx]
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale))
    return base64.b64encode(pix.tobytes("jpeg", jpg_quality=82)).decode()


def call_ia(api_key, b64, prompt, max_tokens=400, retries=2):
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": prompt},
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
        ]}],
    }
    for attempt in range(retries + 1):
        try:
            resp = requests.post(ENDPOINT, headers=headers, json=body, timeout=60)
            data = resp.json()
            txt = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
            if not txt:
                if attempt < retries:
                    time.sleep(1.5)
                    continue
                return {"_raw": "", "_httpstatus": resp.status_code}
            m = re.search(r"\{[\s\S]*\}", txt)
            if m:
                try:
                    return json.loads(m.group(0))
                except Exception:
                    return {"_raw": txt}
            return {"_raw": txt}
        except Exception as e:
            if attempt == retries:
                return {"_error": str(e)}
            time.sleep(1.5)


def find_candidate_pages(doc, max_native_chars=40):
    """Páginas con texto nativo casi vacío y al menos 1 imagen — el mismo
    criterio (aproximado) que usa index.html para decidir que una página es
    ambigua y necesita IA en vez de resolverse por texto/OCR normal."""
    out = []
    for i in range(doc.page_count):
        page = doc[i]
        txt = page.get_text()
        tlen = len(txt.replace(" ", "").replace("\n", ""))
        imgs = len(page.get_images(full=True))
        if tlen < max_native_chars and imgs >= 1:
            out.append(i)
    return out


def parse_paginas_arg(s, page_count):
    out = []
    for part in s.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), min(int(b) + 1, page_count)))
        elif part:
            out.append(int(part))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf", help="Ruta al PDF (Liquidaciones, Libro, etc.)")
    ap.add_argument("--paginas", help="Lista/rango de páginas 0-indexed, ej. '0,5,12' o '0-271'")
    ap.add_argument("--candidatas", action="store_true", help="Escanear TODO el PDF y usar las páginas candidatas (texto nativo <40 chars + imagen)")
    ap.add_argument("--key", default=os.environ.get("MINIMAX_API_KEY"), help="API key de MiniMax (o variable de entorno MINIMAX_API_KEY)")
    ap.add_argument("--max-tokens", type=int, default=400)
    ap.add_argument("--out", help="Archivo JSON de salida (si no se da, imprime a stdout)")
    args = ap.parse_args()

    if not args.key:
        sys.exit("Falta la API key: pasala con --key o con la variable de entorno MINIMAX_API_KEY")

    doc = fitz.open(args.pdf)

    if args.candidatas:
        paginas = find_candidate_pages(doc)
        print(f"Páginas candidatas encontradas: {len(paginas)} de {doc.page_count} totales", file=sys.stderr)
    elif args.paginas:
        paginas = parse_paginas_arg(args.paginas, doc.page_count)
    else:
        sys.exit("Especificá --paginas o --candidatas")

    results = {}
    for n, idx in enumerate(paginas):
        b64 = render_page_b64(doc, idx)
        results[idx] = call_ia(args.key, b64, PROMPT_LIBRO, max_tokens=args.max_tokens)
        if (n + 1) % 10 == 0:
            print(f"  ... {n + 1}/{len(paginas)}", file=sys.stderr)

    out_json = json.dumps({str(k): v for k, v in results.items()}, ensure_ascii=False, indent=1)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(out_json)
        print(f"Guardado en {args.out}", file=sys.stderr)
    else:
        print(out_json)


if __name__ == "__main__":
    main()
