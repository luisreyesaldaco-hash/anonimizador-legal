---
name: anonimizar
description: Trabajar con documentos que tienen datos personales (demandas, contratos, sentencias, expedientes, actas, correos; Word, PDF o escaneos en español, inglés o checo) SIN ver nunca los datos reales. Los anonimiza en la computadora de la persona, trabaja solo con las etiquetas ([PERSONA_1], [EMPRESA_2]…) y al final devuelve los nombres reales en un Word. Usar SIEMPRE que la persona pida revisar, resumir, contestar, redactar o analizar un documento suyo con datos de clientes o de terceros, o diga "anonimiza", "seudonimiza", "sin que veas los nombres", "protege los datos", "desanonimiza" o "devuélvele los nombres".
---

# Anonimizar, trabajar y devolver

Tú nunca ves los datos reales. El programa `anonimizador` (que corre en esta computadora, sin
internet) los cambia por etiquetas y guarda la equivalencia en una tabla que tú **no abres
jamás**. Trabajas con las etiquetas; al final el programa pone los datos reales en el
resultado, que tampoco abres.

Una guardia (hook de este plugin) bloquea que abras originales, tablas y resultados. Si te
bloquea, **no busques otro camino**: es la regla, no un error. Explícale a la persona qué
querías hacer.

## Reglas

1. **No abras el documento de la persona**: ni con Read, ni con `cat`, `pdftotext`,
   `python-docx`, ni con un script tuyo. Ni para "echar un vistazo". Primero se anonimiza.
   Si no sabes cuál es el archivo, pide la ruta a la persona en vez de listar sus carpetas: el
   nombre del archivo suele ser el del cliente.
2. **No abras nunca** la tabla (`tabla_NO_ABRIR.json`, `*_tabla.json`) ni el resultado final.
3. Trabaja solo con lo que te da `preparar`: `texto_anonimizado.md` y los `*_anonimizado.*`.
4. No adivines ni preguntes quién es `[PERSONA_1]`. No escribas nombres reales en el chat.
5. En tu respuesta, copia las etiquetas **exactas**: con corchetes, en mayúsculas, sin
   traducirlas, declinarlas, renumerarlas ni juntar dos en un corchete. Las etiquetas checas
   no se declinan: «[OSOBA_1]» aunque la gramática pida otra forma (reformula la frase).

## 1. Instalar (una sola vez)

Comprueba con `anonimizador --help`. Si no está:

```bash
uv tool install --python 3.12 "anonimizador[ner] @ git+https://github.com/luisreyesaldaco-hash/anonimizador-legal"
```

(sin `uv`: `pipx install --python python3.12 "anonimizador[ner] @ git+https://github.com/luisreyesaldaco-hash/anonimizador-legal"`).
Para PDF escaneados hace falta además Tesseract (`brew install tesseract tesseract-lang`,
`apt install tesseract-ocr tesseract-ocr-spa tesseract-ocr-ces`); sin él solo avisa.
La primera instalación baja los modelos de idioma (~500 MB): avísale a la persona.

## 2. Preparar

```bash
anonimizador agente preparar "ruta/al/documento.docx" ["otro.pdf" …] [--idioma es|en|cs] [--salida carpeta]
```

Varios archivos del mismo asunto van en **una sola llamada** (una sola tabla: la misma persona
tiene la misma etiqueta en todos). Imprime JSON:

- `estado: "listo"` → lee `texto` (o los `documentos[].archivo`) y trabaja.
- `estado: "revisar"` → la verificación encontró datos reales en la salida. **Detente.** No
  abras nada de esa carpeta. Dile a la persona que lo revise en la app (`anonimizador-app`).
- `etiquetas`: todas las etiquetas válidas. `avisos`: díselos a la persona (imágenes, comentarios
  quitados, páginas escaneadas…).

Si al leer el texto anonimizado ves un dato personal que se escapó (un nombre sin etiqueta),
díselo a la persona y vuelve a preparar con `--manual "ese texto"` (repetible). Para no tapar
una etiqueta que no hacía falta: `--excluir FECHA_2`; para incluir una sugerida: `--incluir`.

## 3. Trabajar

Haz lo que la persona pidió usando solo el texto anonimizado. Guarda tu resultado como
Markdown (`.md`) **en la carpeta de salida** (p. ej. `anonimizado/respuesta.md`); se convierte a
Word con títulos, negritas, listas y tablas. Si la persona quiere algo breve en el chat, puedes
contestarle con etiquetas y ofrecer el Word con los nombres reales.

## 4. Devolver los datos reales

```bash
anonimizador agente devolver "anonimizado/tabla_NO_ABRIR.json" "anonimizado/respuesta.md" -o "Respuesta final.docx"
```

- `estado: "listo"` → dale a la persona la ruta de `salida`. No lo abras tú. Puedes abrírselo
  en su programa con `open "<salida>"` (macOS), `xdg-open` (Linux) o `start "" "<salida>"` (Windows).
- `estado: "revisar"` + `sin_revertir` → alguna etiqueta quedó deformada. Corrígela en TU
  `respuesta.md` (usa la forma exacta de la lista `etiquetas`) y vuelve a correr `devolver`
  con otro nombre de salida.

Lo que ninguna revisión automática detecta: que confundas a `[PERSONA_1]` con `[PERSONA_2]`.
Sé cuidadoso con quién hizo qué, y recuérdale a la persona que revise el resultado.
