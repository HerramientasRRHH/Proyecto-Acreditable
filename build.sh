#!/usr/bin/env bash
set -euo pipefail

mkdir -p dist
cp index.html dist/index.html

cat > dist/config.js <<EOF
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
  echo "ADVERTENCIA: MINIMAX_API_KEY no esta definida en Render. El validador IA no funcionara hasta configurarla."
else
  echo "ADVERTENCIA: modo Static Site -> MINIMAX_API_KEY queda visible en texto plano en dist/config.js para cualquiera con la URL del sitio."
fi

echo "Build completo: dist/"
