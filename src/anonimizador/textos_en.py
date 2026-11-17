"""Interfaz en inglés. Clave = texto en español tal como está en el código (ver textos.py)."""

TEXTOS = {
    # --- categorías de la tabla (flujo.CATEGORIAS) ---
    "Personas": "People",
    "Empresas": "Companies",
    "Identificaciones": "ID numbers",
    "Datos bancarios": "Bank details",
    "Contacto": "Contact details",
    "Domicilios": "Addresses",
    "Expedientes, folios y placas": "Case, reference and plate numbers",
    "Fechas y montos": "Dates and amounts",
    "Agregados a mano": "Added by hand",
    "Otros": "Other",

    # --- ventana principal ---
    "Arrastra aquí tus documentos": "Drop your documents here",
    "Elige tus documentos": "Choose your documents",
    "PDF, Word, texto o fotos · uno o varios: comparten revisión y tabla":
        "PDF, Word, text or photos · one or several: they share one review and one table",
    "Elegir archivos…": "Choose files…",
    "Elige los documentos": "Choose the documents",
    "Documentos": "Documents",
    "Texto": "Text",
    "Imágenes": "Images",
    "Imagen": "Image",
    "Leyendo {que}…": "Reading {que}…",
    "{n} documentos": "{n} documents",
    "Revertir respuesta de la IA…": "Restore the AI's reply…",
    "Idioma": "Language",
    "Espera a que termine lo que está haciendo y vuelve a elegir el idioma.":
        "Wait until the current task finishes, then choose the language again.",
    "Agregar archivo…": "Add file…",
    "Agregar al proyecto": "Add to the project",
    "Cambiar archivo": "Change file",
    "Cambiar archivos": "Change files",
    "Hallazgos": "Findings",
    "Renombrar": "Rename",
    "Unir con…": "Merge with…",
    "Separar variante…": "Split variant…",
    "Dato": "Data",
    "Se cambia por": "Replaced with",
    "Veces": "Times",
    "Palabra, nombre o frase que no se detectó": "Word, name or phrase that was not detected",
    "Añadir a la lista": "Add to the list",
    "Contexto": "Context",
    "Documento": "Document",
    "Revisé los hallazgos": "I have reviewed the findings",
    "Anonimizar y guardar": "Anonymize and save",
    "Salida:": "Output:",
    "Igual al original": "Same as original",
    "Elige un hallazgo para ver dónde aparece": "Choose a finding to see where it appears",
    "Elige un hallazgo para verlo aquí": "Choose a finding to see it here",
    "{categoria}  ({marcadas} de {total})": "{categoria}  ({marcadas} of {total})",
    "se ocultará": "will be hidden",
    "NO se ocultará": "will NOT be hidden",
    "{marcador} — {estado}": "{marcador} — {estado}",
    "Variantes: ": "Variants: ",
    "No aparece en el texto de los documentos.": "It does not appear in the text of the documents.",
    "{documento} · 1 vez\n": "{documento} · once\n",
    "{documento} · {veces} veces\n": "{documento} · {veces} times\n",
    "aparición {actual} de {n}": "occurrence {actual} of {n}",

    # --- diálogos de revisión ---
    "No se agregó": "Not added",
    "¿Quitar del proyecto?": "Remove from the project?",
    "«{nombre}» sale del proyecto. Lo que solo aparecía ahí deja la lista; lo demás conserva tu revisión.":
        "“{nombre}” leaves the project. What appeared only there leaves the list; everything else keeps your review.",
    "Quitar": "Remove",
    "¿Cambiar de archivo?": "Change file?",
    "Se pierden los cambios que hiciste en la revisión.": "The changes you made in the review will be lost.",
    "Cambiar de archivo": "Change file",
    "No se añadió": "Not added",
    "No se pudo renombrar": "Could not rename",
    "Unir hallazgos": "Merge findings",
    "¿Con cuál se une {marcador} ({canonico})?\nQuedará todo bajo la etiqueta que elijas.":
        "Merge {marcador} ({canonico}) with which one?\nEverything will go under the label you choose.",
    "Separar variante": "Split variant",
    "¿Qué variante es otra persona o dato distinto?": "Which variant is a different person or item?",
    "Aceptar": "OK",
    "Cancelar": "Cancel",

    # --- guardar y resultado ---
    "Sin permiso para escribir ahí: elige otra carpeta": "No permission to write there: choose another folder",
    "No se pudo guardar": "Could not save",
    "Resultado": "Result",
    "Listo": "Done",
    "Atención: quedaron datos en el archivo": "Warning: personal data remained in the file",
    "Atención: {sucios} de {total} con datos por revisar": "Warning: {sucios} of {total} have data to check",
    "   {sustituciones} sustituciones, sin datos marcados\n": "   {sustituciones} replacements, no marked data left\n",
    "   quedaron datos originales; se nombró así para que no se comparta por error\n":
        "   original data remained; it was named this way so it is not shared by mistake\n",
    "\nTabla: {tabla}  ": "\nTable: {tabla}  ",
    "(privada: tiene los datos reales; sirve para revertir)\n": "(private: it holds the real data; used to restore)\n",
    "Carpeta: {carpeta}\n": "Folder: {carpeta}\n",
    "Copiar texto limpio": "Copy clean text",
    "Abrir carpeta": "Open folder",
    "Cerrar": "Close",
    "Copiado": "Copied",
    "Texto limpio copiado.": "Clean text copied.",

    # --- revertir ---
    "Revertir respuesta de la IA": "Restore the AI's reply",
    "1. Elige la tabla de equivalencias (_tabla.json) del documento.":
        "1. Choose the document's substitution table (_tabla.json).",
    "1. Tabla: {ruta}": "1. Table: {ruta}",
    "Elegir tabla…": "Choose table…",
    "Tabla de equivalencias": "Substitution table",
    "Tabla": "Table",
    "No es una tabla": "Not a table",
    "2. Pega la respuesta de la IA, o arrastra su archivo (.docx, .md, .txt):":
        "2. Paste the AI's reply, or drop its file (.docx, .md, .txt):",
    "2. Pega la respuesta de la IA, o abre su archivo (.docx, .md, .txt):":
        "2. Paste the AI's reply, or open its file (.docx, .md, .txt):",
    "2. Archivo de Word: {ruta} (conserva su formato)": "2. Word file: {ruta} (keeps its formatting)",
    "Abrir archivo…": "Open file…",
    "Quitar archivo": "Remove file",
    "Respuesta de la IA": "AI reply",
    "Respuesta": "Reply",
    "No se pudo abrir": "Could not open",
    "3. Vista previa con los datos reales:": "3. Preview with the real data:",
    "Sin revertir (la tabla no las conoce): {desconocidas}": "Not restored (not in the table): {desconocidas}",
    "Guardar .docx": "Save .docx",
    "Copiar texto": "Copy text",
    "Falta la tabla": "Table missing",
    "Elige primero el archivo _tabla.json del documento.": "First choose the document's _tabla.json file.",
    "Guardar respuesta con los datos reales": "Save the reply with the real data",
    "Texto con los datos reales copiado.": "Text with the real data copied.",

    # --- visor ---
    "Sin documento": "No document",
    "Ajustar": "Fit",
    "El documento está protegido con contraseña": "The document is password-protected",
    "No se pudo abrir el documento": "The document could not be opened",

    # --- flujo, procesadores, verificación y tabla ---
    "===== Documento {i} de {n}: {nombre} =====\n\n{texto_limpio}": "===== Document {i} of {n}: {nombre} =====\n\n{texto_limpio}",
    "No se encontró texto en el documento.": "No text was found in the document.",
    "Elige al menos un documento.": "Choose at least one document.",
    "El proyecto necesita al menos un documento.": "The project needs at least one document.",
    "{r} ya está en el proyecto.": "{r} is already in the project.",
    "El detector de nombres avanzado no está disponible; revisa con más cuidado los nombres.":
        "The advanced name detector is not available; check names more carefully.",
    "El modelo checo de nombres no está instalado; solo se usan reglas. Revisa los nombres con cuidado.":
        "The Czech name model is not installed; only rules are used. Check names carefully.",
    "El modelo inglés de nombres no está instalado; solo se usan reglas. Revisa los nombres con cuidado.":
        "The English name model is not installed; only rules are used. Check names carefully.",
    "El detector de nombres avanzado no estaba disponible; revisa con más cuidado los nombres.":
        "The advanced name detector was not available; check names more carefully.",
    "Primero revisa los hallazgos y confirma la revisión.": "First review the findings and confirm the review.",
    "No se puede sobrescribir el documento original. Elige otro nombre.":
        "The original document cannot be overwritten. Choose another name.",
    "Formato de salida desconocido: {formato}": "Unknown output format: {formato}",
    "No hay documentos cargados.": "No documents loaded.",
    "La tabla no puede ocupar el lugar de un documento.": "The table cannot take the place of a document.",
    "{ruta}: se aceptan PDF, Word (.docx, .doc), .odt, .rtf, .txt, .md e imágenes (.jpg, .png, .tif).":
        "{ruta}: accepted formats are PDF, Word (.docx, .doc), .odt, .rtf, .txt, .md and images (.jpg, .png, .tif).",
    "No encuentro el archivo {ruta}.": "File not found: {ruta}.",
    "No pude abrir {ruta} como imagen: {e}": "Could not open {ruta} as an image: {e}",
    "El archivo {doc} se convirtió a .docx; la salida es un .docx.": "The {doc} file was converted to .docx; the output is a .docx.",
    "Para abrir archivos {doc} se necesita Microsoft Word o LibreOffice instalado. También puedes abrirlo en Word y guardarlo como .docx.":
        "Opening {doc} files requires Microsoft Word or LibreOffice. You can also open it in Word and save it as .docx.",
    "La salida no puede ser el archivo original; elige otro nombre.": "The output cannot be the original file; choose another name.",
    "No pude abrir {ruta} como documento de Word: {e}": "Could not open {ruta} as a Word document: {e}",
    "No pude abrir {entrada} como documento de Word: {e}": "Could not open {entrada} as a Word document: {e}",
    "El documento contiene un objeto incrustado ({partname}) que no se revisa. Ábrelo y revísalo a mano, o elimínalo antes de compartir.":
        "The document contains an embedded object ({partname}) that is not checked. Open and check it by hand, or delete it before sharing.",
    "{ruta} está protegido con contraseña. Quita la protección y vuelve a intentarlo.":
        "{ruta} is password-protected. Remove the protection and try again.",
    "{ruta} no es un PDF.": "{ruta} is not a PDF.",
    "No pude abrir {ruta} como PDF: {e}": "Could not open {ruta} as a PDF: {e}",
    "Las páginas {paginas} parecen escaneadas y no se pudieron leer (falta el OCR). Sus datos NO se anonimizaron.":
        "Pages {paginas} look scanned and could not be read (OCR is missing). Their data was NOT anonymized.",
    "Página(s) {paginas} escaneada(s): se leyeron con OCR. Las firmas, sellos y lo escrito a mano siguen visibles; revísalas antes de compartir.":
        "Scanned page(s) {paginas}: read with OCR. Signatures, stamps and handwriting are still visible; check them before sharing.",
    "Salida en Word: se conserva el texto, no el diseño del PDF; las firmas, sellos e imágenes no se copian.":
        "Word output: the text is kept, not the PDF layout; signatures, stamps and images are not copied.",
    "página {number}": "page {number}",
    "anotación p. {number}": "annotation p. {number}",
    "imagen de la página {number}": "image on page {number}",
    "Página {number}: imagen sin texto, no se puede verificar.": "Page {number}: image without text, cannot be checked.",
    "archivos adjuntos": "attachments",
    "el PDF todavía tiene archivos incrustados": "the PDF still has embedded files",
    "No pude leer {ruta}: {e}": "Could not read {ruta}: {e}",
    "Guarda el resultado con otro nombre: el archivo de la IA se conserva.":
        "Save the result under another name: the AI's file is kept.",
    "El documento contiene imágenes; revisa que no muestren datos (firmas, credenciales, sellos).":
        "The document contains images; check that they show no personal data (signatures, ID cards, stamps).",
    "miniatura de la primera página": "first-page thumbnail",
    "{nombre}: objeto incrustado que no se puede verificar automáticamente.":
        "{nombre}: embedded object that cannot be checked automatically.",
    "Contiene los datos reales del documento. No la compartas ni la subas a ninguna IA.":
        "Contains the document's real data. Do not share it or upload it to any AI.",
    "El archivo no es una tabla de equivalencias del anonimizador.": "The file is not an Anonymizer substitution table.",
    "La etiqueta no puede quedar vacía.": "The label cannot be empty.",
    "Ya existe la etiqueta {nueva}.": "The label {nueva} already exists.",
    "Solo se puede separar una variante de una entidad que tenga varias.":
        "A variant can only be split from an item that has several.",
    "Escribe el texto que quieres ocultar.": "Type the text you want to hide.",
    "«{valor}» no aparece en el documento. Revisa cómo está escrito.":
        "“{valor}” does not appear in the document. Check how it is spelled.",
    # IA local (Ollama)
    "Revisar con IA local": "Check with local AI",
    "IA local": "Local AI",
    "La IA local ({modelo}) no encontró nada más que tapar.": "The local AI ({modelo}) found nothing else to cover.",
    "La IA local ({modelo}) sugirió {n} datos más. Ya están marcados y llevan una ✦: revísalos y desmarca los que no haga falta tapar.":
        "The local AI ({modelo}) suggested {n} more items. They are already checked and carry a ✦: review them and uncheck the ones that don't need covering.",
    "La IA solo puede estar en esta computadora o en tu red privada ({host} no lo es).":
        "The AI can only run on this computer or your private network ({host} is not).",
    "No encontré Ollama en esta computadora. Instálalo desde ollama.com y luego, en una terminal: ollama pull {modelo}":
        "Ollama was not found on this computer. Install it from ollama.com, then run in a terminal: ollama pull {modelo}",
    "Ollama está instalado, pero falta el modelo. En una terminal: ollama pull {modelo}":
        "Ollama is installed but the model is missing. In a terminal: ollama pull {modelo}",
    "■ Detener la IA": "■ Stop the AI",
    "Revisión con IA local": "Local AI check",
    "Es una segunda revisión, después del detector. Una IA lee el documento ya tapado y busca lo que se escapó: fechas en letra, folios, números de escritura o de notaría, colonias, sellos. Lo que sugiere entra a la lista marcado y con una ✦: tú decides qué se queda.":
        "It is a second pass, after the detector. An AI reads the already-covered document and looks for what slipped through: dates written out in words, reference numbers, deed or notary numbers, neighborhoods, seals. What it suggests goes into the list, checked and marked with a ✦: you decide what stays.",
    "Corre completa en esta computadora, con Ollama: el documento no sale de aquí. Solo funciona con gemma3 de 27b (más precisa; pide 32 GB de memoria) o de 12b (cabe en una laptop de 16 GB). Es lenta: cerca de un minuto por cada parte del documento.":
        "It runs entirely on this computer, with Ollama: the document never leaves it. It only works with gemma3 27b (more accurate; needs 32 GB of memory) or 12b (fits a 16 GB laptop). It is slow: about a minute for each part of the document.",
    "En esta computadora: {modelo} ✓": "On this computer: {modelo} ✓",
    "En esta computadora falta instalarla:": "It still needs to be installed on this computer:",
    "Abrir ollama.com": "Open ollama.com",
    "Copiar": "Copy",
    "{n}. Instala Ollama (gratis).": "{n}. Install Ollama (free).",
    "{n}. En la Terminal, una de dos:": "{n}. In Terminal, one of these:",
    "Cuando termine la descarga, vuelve a presionar «Revisar con IA local».":
        "When the download finishes, press “Check with local AI” again.",
    "Preparando la IA local ({modelo})…": "Starting the local AI ({modelo})…",
    "IA local ({modelo}): parte {parte} de {total} · cerca de un minuto cada una":
        "Local AI ({modelo}): part {parte} of {total} · about a minute each",
    "La IA local no respondió ({error}).": "The local AI did not respond ({error}).",
    "Se quitaron {n} comentario(s) del Word: pueden traer datos y el nombre de quien los escribió. El original los conserva.":
        "Removed {n} comment(s) from the Word file: they may contain personal data and the name of whoever wrote them. The original keeps them.",
    "Se aceptaron los cambios controlados del Word: el texto borrado podía traer datos. El original los conserva.":
        "Accepted the tracked changes in the Word file: deleted text could contain personal data. The original keeps them.",
    "Algo falló": "Something went wrong",
    "La app tuvo un error y no pudo seguir: {error}\n\nEl detalle (sin datos del documento) quedó en:\n{ruta}":
        "The app hit an error and could not continue: {error}\n\nThe details (without document data) were saved to:\n{ruta}",
    "{nombre}: página {pagina} de {total} escaneada, leyéndola con OCR (unos segundos por página)…":
        "{nombre}: page {pagina} of {total} is scanned, reading it with OCR (a few seconds per page)…",
    "Cambiar el idioma del documento": "Change the document language",
    "Se vuelve a leer el documento con las reglas de ese idioma y se pierde la revisión hecha. ¿Seguir?":
        "The document is read again with that language's rules and your review is lost. Continue?",
    "Cambiar idioma": "Change language",
    "Documento en:": "Document in:",
}
