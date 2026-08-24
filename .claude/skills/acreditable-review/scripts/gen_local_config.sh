#!/usr/bin/env bash
# Genera config.js en la RAIZ del repo (junto a index.html, no en dist/) para
# poder probar la lectura con IA real sirviendo index.html directo con
# `python -m http.server` -- sin esto, el input de la key queda vacio en el
# navegador y hay que pegarla a mano cada vez. Lee las variables desde .env
# (no versionado). config.js tambien esta en .gitignore -- nunca debe
# commitearse, queda la key en texto plano.
set -euo pipefail
cd "$(dirname "$0")/../../../.."

if [ ! -f .env ]; then
  echo "No existe .env en la raiz del repo. Copialo o crealo con MINIMAX_API_KEY=..."
  exit 1
fi
set -a
source .env
set +a

cat > config.js <<EOF
window.NUCLEO_CONFIG = {
  mode: "${IA_MODE:-direct}",
  endpoint: "${IA_ENDPOINT:-https://api.minimax.io/anthropic}",
  model: "${IA_MODEL:-MiniMax-M3}",
  apiKey: "${MINIMAX_API_KEY:-}",
  maxTokens: ${IA_MAX_TOKENS:-8000},
  chunkKB: ${IA_CHUNK_KB:-120},
  ocrSample: ${IA_OCR_SAMPLE:-12}
};
EOF

if [ -z "${MINIMAX_API_KEY:-}" ]; then
  echo "ADVERTENCIA: MINIMAX_API_KEY vacia en .env -- config.js quedo sin key."
else
  echo "config.js generado en la raiz del repo con la key de .env."
fi
