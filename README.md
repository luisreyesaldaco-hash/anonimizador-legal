# anonimizador

App de escritorio (Windows `.exe`) para que los abogados seudonimicen documentos
**en su propia PC** antes de mandarlos a un modelo de IA, de modo que los datos de
sus clientes no salgan de su equipo.

## Estado

Spec v1: [`SPEC.md`](SPEC.md). Motores (detector, seudónimos, Word, PDF, `.doc`), verificación,
línea de comandos e interfaz escritos y con pruebas. Pendiente: probar la interfaz en pantalla,
OCR con Tesseract y el instalador de Windows.

## Con Claude Code: Claude trabaja sin ver los datos reales

```
/plugin marketplace add luisreyesaldaco-hash/anonimizador-legal
/plugin install anonimizador@anonimizador
```

Luego basta con pedirle a Claude algo sobre un documento («contesta esta demanda», «resume el
contrato»). El plugin trae:

- **Una skill** (`claude-plugin/skills/anonimizar`) que le dice a Claude cómo trabajar: instala el
  paquete si falta, corre `anonimizador agente preparar` (anonimiza en tu computadora y deja
  `texto_anonimizado.md`), trabaja **solo** con las etiquetas `[PERSONA_1]`, escribe su respuesta en
  Markdown y corre `anonimizador agente devolver … -o final.docx`, que pone los datos reales.
- **Una guardia** (`claude-plugin/hooks/guardia.py`, hook `PreToolUse`) que bloquea a Claude si
  intenta abrir el original, la tabla de equivalencias o el resultado final, con Read, Grep,
  Glob, la terminal, WebFetch o un script propio. No depende de que Claude obedezca: lo frena antes de que el dato
  llegue a la conversación.
- **El modo `anonimizador agente`**, que nunca imprime un dato real: solo JSON con rutas,
  etiquetas y conteos; las salidas llevan nombres neutros (`documento_1_anonimizado.docx`) porque
  el nombre del archivo suele ser el del cliente; y si la verificación encuentra datos en la
  salida, no entrega texto y pide revisión humana en la app.

### Qué protege y qué no

Un dato que entra a la conversación se manda a la API en cada mensaje siguiente de esa sesión, y
ningún plugin puede borrarlo después. Lo único que se puede hacer es impedir que entre.

| Por dónde podría entrar un dato real | ¿Lo frena? |
|---|---|
| Abrir el original, la tabla o el resultado (Read, NotebookRead, WebFetch con `file://`) | ✅ Sí |
| Buscar o listar en una carpeta con originales o tablas (Grep, Glob) | ✅ Sí, aunque no se indique carpeta |
| Cualquier Word, PDF, RTF u ODT sin anonimizar, aunque nunca se haya registrado | ✅ Sí, sin configurar nada |
| `cat`, `pdftotext`, `python-docx` o un script propio que mencione esos archivos | ⚠️ Los casos evidentes; un comando ofuscado a propósito no |
| `anonimizador escanear/generar/revertir` (imprimen datos reales) | ✅ Sí; solo pasa `anonimizador agente` |
| Avisos de `preparar` y `devolver` | ✅ Nunca traen un dato real (se tapan con la tabla) |
| Lo que tú pegues o escribas en el chat, incluido el nombre del archivo | ❌ No: ningún hook ve tus mensajes |
| `ls` o `dir` en una carpeta de documentos sin preparar | ❌ Claude ve los nombres de archivo |
| Lo que el detector no encuentre (un nombre raro, un apodo) | ❌ Claude lo verá en el texto anonimizado; `--ia` agrega una segunda revisión local |
| Respuestas de servidores MCP, subagentes o páginas web | ❌ No pasan por la guardia |
| Que la IA confunda a `[PERSONA_1]` con `[PERSONA_2]` | ❌ Ninguna revisión automática lo detecta: el resultado hay que leerlo |

La guardia es un cinturón de seguridad contra descuidos, no una caja fuerte contra alguien que
quiera saltársela. Si un dato real ya entró a la conversación, empieza una sesión nueva para el
trabajo confidencial.

## Desarrollo

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev,ner,ui]"
.venv/bin/pytest -q
```

Línea de comandos (para probar con documentos reales):

```bash
anonimizador escanear demanda.docx
anonimizador generar demanda.docx --texto limpio.txt      # → demanda_anonimizado.docx + demanda_tabla.json
anonimizador revertir demanda_tabla.json respuesta_ia.txt
```

App de escritorio: `anonimizador-app` (requiere Tk; en Debian, `python3-tk`).

Instalador de Windows: `.github/workflows/windows.yml` (PyInstaller + Inno Setup + Tesseract).

## Licencia

AGPL-3.0-or-later (ver `LICENSE`).
