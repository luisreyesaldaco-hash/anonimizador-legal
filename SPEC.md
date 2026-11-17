# Anonimizador — Especificación v1

> Sustituye a la spec inicial (generada con Gemini). Decisiones tomadas por Luis el
> 10-nov-2026; el número entre corchetes remite a la pregunta del cuestionario.

## 1. Qué es

Aplicación de escritorio para Windows, **gratuita y de código abierto**, publicada por
LegalAtlas [2, 3]. Sirve para que un abogado **seudonimice** un documento **en su propia
PC** antes de pegarlo en un modelo de IA, y después **revierta** la respuesta de la IA
para recuperar los nombres reales.

El documento nunca sale del equipo: la app no hace ninguna conexión de red salvo cuando
el usuario pide expresamente buscar actualizaciones [11].

## 2. Flujo del usuario

1. **Cargar** un `.pdf`, `.docx` o `.doc` (arrastrar o abrir).
2. **Escanear**: la app detecta datos sensibles y los agrupa por persona o entidad.
3. **Revisar** (obligatorio [12]): lista de hallazgos con su contexto
   ("…el C. **Juan Pérez** promovió…"). El abogado:
   - marca o desmarca cada hallazgo,
   - junta o separa grupos de variantes [10],
   - renombra un seudónimo (`[PERSONA_1]` → `[ACTOR]`) [9],
   - añade a mano términos que no se detectaron.
4. **Generar** [5b]:
   - el archivo seudonimizado, en el mismo formato que entró (`*_anonimizado.*`),
   - un botón «Copiar texto limpio» para pegar directo en la IA,
   - la **tabla de equivalencias** local (`*_tabla.json`), que nunca se manda a nadie.
5. **Revertir**: el abogado pega la respuesta de la IA y la app la regresa con los
   nombres reales, usando la tabla [1].

## 3. Seudonimización [1, 9, 10]

- Sustitución **consistente**: la misma entidad recibe siempre la misma etiqueta en todo
  el documento: `[PERSONA_1]`, `[RFC_1]`, `[DOMICILIO_2]`, etc.
- **Variantes agrupadas**: "Juan Pérez López", "Pérez López", "JUAN PÉREZ" y
  "el C. Pérez" → `PERSONA_1`. La comparación ignora mayúsculas, acentos y espacios
  dobles. El abogado puede corregir la agrupación.
- **Duplicados**: cada entidad aparece una sola vez en la lista de revisión, pero se
  sustituye en todas sus apariciones.
- **Tabla local**: JSON con `etiqueta → valores originales`, más el nombre y hash del
  documento fuente. Se guarda junto a la salida; la UI advierte que contiene los datos
  reales y no debe compartirse.
- Fuera de la v1: el modo destructivo de tapar en negro.

## 4. Qué se detecta [6, 7, 8]

Todo encendido por defecto en la v1:

| Tipo | Motor |
|---|---|
| Nombres de personas | reglas de contexto + nombres de pila frecuentes (firmas, tablas) + spaCy local en español |
| CURP, RFC, NSS | regex con validación de estructura (y dígito verificador cuando aplique) |
| CLABE, cuentas, tarjetas | regex + validación (CLABE: dígito de control; tarjetas: Luhn) |
| Correo, teléfono | regex (el correo tolera la arroba mal leída por el OCR) |
| Sitios web privados | regex; los de gobierno y universidades (.gob, .gov, .edu) se conservan |
| Domicilio | reglas ("calle", "col.", "C.P.", "número exterior"…) + spaCy |
| Clave de elector (INE) | regex |
| Número de expediente | regex de formatos comunes ("expediente 123/2024", "juicio …") |
| Folios | con contexto: no. de empleado, registro patronal IMSS, cédula profesional, folio, clave interna |
| Placas vehiculares | regex |
| Fechas, montos | regex |

- **Empresas (personas morales)**: llegan **marcadas** las que son parte del asunto (contexto
  de parte: "demandada", "en contra de", "patrón", "persona citada"…; o la que domina el
  documento) y los despachos o razones sociales con apellidos de personas detectadas. Las
  demás (bancos, proveedores mencionados de paso) llegan desmarcadas como sugerencia.
  Marcadas, también se cubren su nombre sin "S.A. de C.V." y su sigla ("IMV").
- **Autoridades** (juzgados, tribunales, dependencias): nunca se seudonimizan; la IA
  necesita saberlas.

## 5. Formatos [5a]

### Entrada
- **`.docx`**: nativo.
- **`.doc`**: se convierte a `.docx` en una carpeta temporal (que se borra) antes de
  procesar: vía Word (COM) si está instalado y, si no, vía LibreOffice. Si no hay ninguno,
  mensaje claro. La salida es `.docx`.
- El tipo se decide por el contenido del archivo, no por la extensión.
- **PDF con texto**: nativo.
- **PDF escaneado**: OCR local con Tesseract (español) incluido en el instalador.

### Word
- La búsqueda se hace a nivel **párrafo** y se mapea a los *runs*, para encontrar texto
  partido en varios fragmentos de formato sin perder negritas ni estilos.
- Recorre: cuerpo, tablas, encabezados, pies, notas al pie y al final, cuadros de texto
  (incluida su copia de respaldo para Word antiguo), hipervínculos (también su destino
  `mailto:`), códigos de campo, textos alternativos de imágenes y XML personalizado.
- **Comentarios**: se eliminan completos (con sus autores), no se seudonimizan.
- **Miniatura**: se elimina la vista previa de la primera página que Word guarda como imagen.
- También se quitan el glosario de bloques de creación, las propiedades personalizadas,
  las variables del documento y la ruta de la plantilla.
- **Control de cambios**: el texto borrado (`w:del`) y el insertado se limpian; la salida
  no conserva el historial de revisiones.
- **Metadatos**: se vacían autor, último en modificar, empresa y comentarios del archivo.

### PDF
- Antes de leer, se "hornean" formularios y anotaciones en la página: los valores de los
  campos se tratan como texto normal.
- Sustitución mediante redacción real de PyMuPDF (`add_redact_annot` + `apply_redactions`);
  el texto original desaparece del flujo de contenido. La etiqueta se escribe después,
  sobre la línea base original y al tamaño del texto.
- PDF con contraseña: se rechaza con un mensaje claro.
- Limpieza: metadatos y XMP (`scrub()`), anotaciones, marcadores, campos de formulario y
  adjuntos. Guardado con `garbage=4, deflate=True`.
- En escaneados, la redacción también borra los píxeles de la imagen.
- Limitación conocida: el seudónimo dentro de la página puede no calzar exacto con la
  tipografía original. El texto limpio (botón «Copiar») no tiene este problema.

### Verificación (obligatoria, todos los formatos)
Después de guardar se vuelve a abrir la salida, se extrae todo el texto (en Word: todas las
partes del paquete, texto, atributos y relaciones) y se confirma que **ningún valor original
marcado** aparece. Si aparece alguno, la app no da el archivo por bueno, dice dónde quedó y
lo renombra a `*_CON_DATOS_REVISAR` para que no se comparta por error.

## 6. Reglas de negocio

- **Nunca** se sobrescribe el original; la salida siempre es una copia nueva.
- No se puede generar la salida sin pasar por la pantalla de revisión [12].
- La app no promete anonimato perfecto. Texto de producto y de `privacy.html`:
  «Herramienta de apoyo que corre en tu equipo; tú revisas antes de compartir» [13].
- Mientras procesa, la UI bloquea los botones y muestra progreso.
- Cero telemetría. La búsqueda de actualizaciones solo corre cuando el usuario la pide [11].

## 7. Arquitectura

- **Python 3.12**.
- **Motores** (sin dependencia de la UI, usables desde CLI y tests):
  - `detector/`: regex + validadores + reglas de contexto + spaCy (`es_core_news_md`).
  - `seudonimos/`: agrupación de variantes, asignación de etiquetas, tabla y reversión.
  - `procesadores/`: `docx`, `doc` (conversión), `pdf`, `ocr`.
  - `verificacion/`: re-extracción y comprobación de la salida.
- **CLI** (`anonimizador escanear|generar|revertir`): para probar con documentos reales
  antes de la UI.
- **UI**: CustomTkinter + `tkinterdnd2` para arrastrar y soltar [15].
- **Empaquetado**: PyInstaller en modo carpeta (`onedir`) + instalador Inno Setup, con el
  build en un runner de Windows de GitHub Actions [16].
- **Firma de código** [14]: el piloto va sin firma. Para el lanzamiento público, publicar en
  la Microsoft Store como MSIX (registro gratuito y Microsoft firma sin costo). Plan B:
  SignPath Foundation (firma gratis para OSS). Plan C: certificado pagado (~USD 120–450/año).
  Costo objetivo del proyecto: USD 0.

### Estructura

```text
anonimizador/
├── src/anonimizador/
│   ├── detector/        # patrones.py, validadores.py, contexto.py, ner.py
│   ├── seudonimos/      # agrupacion.py, tabla.py, revertir.py
│   ├── procesadores/    # docx.py, doc.py, pdf.py, ocr.py
│   ├── verificacion.py
│   ├── cli.py
│   └── ui/              # ventana_principal.py
├── tests/               # con documentos de prueba (runs partidos, control de cambios, escaneados)
├── packaging/           # build.spec, instalador.iss
└── pyproject.toml
```

## 8. Licencia y publicación

- Código abierto (AGPL-3.0, compatible con PyMuPDF) en un repo público de GitHub.
- Argumento de confianza: «código auditable, corre en tu PC, no se conecta a internet».

## 9. Orden de construcción [17]

1. Detector con tests (regex + validadores primero, luego spaCy).
2. Seudónimos: agrupación, tabla y reversión.
3. Procesador `.docx` + verificación.
4. Procesador PDF + verificación; luego OCR.
5. Conversión `.doc`.
6. CLI y prueba con documentos reales.
7. UI.
8. Empaquetado: instalador Inno Setup (piloto) y MSIX para la Microsoft Store (público).

## 10. Fuera de la v1

Mac y Linux [4], modo negro destructivo, `.xlsx`/`.pptx`, actualizaciones automáticas.
