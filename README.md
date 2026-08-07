# Proyecto Acreditable

Herramienta de validación de acreditable laboral (asistencia, liquidaciones, firmas) con un módulo opcional de validación asistida por IA (MiniMax, API compatible con Anthropic Messages).

## Despliegue en Render (Static Site)

1. Conectar este repositorio en Render como **Static Site**.
2. Build Command: `chmod +x build.sh && ./build.sh`
3. Publish Directory: `dist`
4. Variables de entorno (ver `render.yaml`):

| Variable | Valor |
|---|---|
| `IA_MODE` | `direct` |
| `IA_ENDPOINT` | `https://api.minimax.io/anthropic` |
| `IA_MODEL` | `MiniMax-M3` |
| `MINIMAX_API_KEY` | tu key del plan de tokens |
| `IA_MAX_TOKENS` | `8000` |
| `IA_CHUNK_KB` | `120` |
| `IA_OCR_SAMPLE` | `12` |

`build.sh` genera `dist/config.js` con esos valores inyectados como `window.NUCLEO_CONFIG`.

### Advertencia de seguridad

Este despliegue usa **Static Site simple**: `MINIMAX_API_KEY` queda visible en texto plano en `/config.js` para cualquiera que tenga la URL del sitio publicado. Usa una key dedicada a este sitio y no la reutilices en otros servicios. Si en algún momento se necesita ocultar la key, hay que mover el modo IA a `proxy` con un servicio backend intermedio (no incluido en este despliegue).

El HTML incluye direcciones de correo corporativas embebidas en la pestaña de envío; el repositorio es privado, pero el sitio publicado en Render es accesible por URL directa salvo que se configure control de acceso en Render.
