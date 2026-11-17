"""Interfaz en checo. Clave = texto en español tal como está en el código (ver textos.py)."""

TEXTOS = {
    # --- categorías de la tabla (flujo.CATEGORIAS) ---
    "Personas": "Osoby",
    "Empresas": "Firmy",
    "Identificaciones": "Identifikační čísla",
    "Datos bancarios": "Bankovní údaje",
    "Contacto": "Kontaktní údaje",
    "Domicilios": "Adresy",
    "Expedientes, folios y placas": "Spisové značky, čísla jednací a SPZ",
    "Fechas y montos": "Data a částky",
    "Agregados a mano": "Přidáno ručně",
    "Otros": "Ostatní",

    # --- ventana principal ---
    "Arrastra aquí tus documentos": "Přetáhněte sem dokumenty",
    "Elige tus documentos": "Vyberte dokumenty",
    "PDF, Word, texto o fotos · uno o varios: comparten revisión y tabla":
        "PDF, Word, text nebo fotky · jeden i více: mají společnou kontrolu i tabulku",
    "Elegir archivos…": "Vybrat soubory…",
    "Elige los documentos": "Vyberte dokumenty",
    "Documentos": "Dokumenty",
    "Texto": "Text",
    "Imágenes": "Obrázky",
    "Imagen": "Obrázek",
    "Leyendo {que}…": "Načítám {que}…",
    "{n} documentos": "Dokumentů: {n}",
    "Revertir respuesta de la IA…": "Vrátit údaje do odpovědi AI…",
    "Idioma": "Jazyk",
    "Espera a que termine lo que está haciendo y vuelve a elegir el idioma.":
        "Počkejte, až se dokončí rozpracovaná činnost, a pak jazyk vyberte znovu.",
    "Agregar archivo…": "Přidat soubor…",
    "Agregar al proyecto": "Přidat do projektu",
    "Cambiar archivo": "Změnit soubor",
    "Cambiar archivos": "Změnit soubory",
    "Hallazgos": "Nálezy",
    "Renombrar": "Přejmenovat",
    "Unir con…": "Sloučit s…",
    "Separar variante…": "Oddělit variantu…",
    "Dato": "Údaj",
    "Se cambia por": "Nahradí se",
    "Veces": "Počet",
    "Palabra, nombre o frase que no se detectó": "Slovo, jméno nebo fráze, které se nenašly",
    "Añadir a la lista": "Přidat do seznamu",
    "Contexto": "Kontext",
    "Documento": "Dokument",
    "Revisé los hallazgos": "Nálezy jsem zkontroloval(a)",
    "Anonimizar y guardar": "Anonymizovat a uložit",
    "Salida:": "Výstup:",
    "Igual al original": "Stejný jako originál",
    "Elige un hallazgo para ver dónde aparece": "Vyberte nález a uvidíte, kde se vyskytuje",
    "Elige un hallazgo para verlo aquí": "Vyberte nález a zobrazí se zde",
    "{categoria}  ({marcadas} de {total})": "{categoria}  ({marcadas} z {total})",
    "se ocultará": "bude skryto",
    "NO se ocultará": "NEBUDE skryto",
    "{marcador} — {estado}": "{marcador} — {estado}",
    "Variantes: ": "Varianty: ",
    "No aparece en el texto de los documentos.": "V textu dokumentů se nevyskytuje.",
    "{documento} · 1 vez\n": "{documento} · 1×\n",
    "{documento} · {veces} veces\n": "{documento} · {veces}×\n",
    "aparición {actual} de {n}": "výskyt {actual} z {n}",

    # --- diálogos de revisión ---
    "No se agregó": "Nepřidáno",
    "¿Quitar del proyecto?": "Odebrat z projektu?",
    "«{nombre}» sale del proyecto. Lo que solo aparecía ahí deja la lista; lo demás conserva tu revisión.":
        "„{nombre}“ bude odebrán z projektu. Co se vyskytovalo jen v něm, zmizí ze seznamu; zbytek si zachová vaši kontrolu.",
    "Quitar": "Odebrat",
    "¿Cambiar de archivo?": "Změnit soubor?",
    "Se pierden los cambios que hiciste en la revisión.": "Změny provedené při kontrole se ztratí.",
    "Cambiar de archivo": "Změnit soubor",
    "No se añadió": "Nepřidáno",
    "No se pudo renombrar": "Nelze přejmenovat",
    "Unir hallazgos": "Sloučit nálezy",
    "¿Con cuál se une {marcador} ({canonico})?\nQuedará todo bajo la etiqueta que elijas.":
        "S čím sloučit {marcador} ({canonico})?\nVše bude pod označením, které vyberete.",
    "Separar variante": "Oddělit variantu",
    "¿Qué variante es otra persona o dato distinto?": "Která varianta je jiná osoba nebo jiný údaj?",
    "Aceptar": "OK",
    "Cancelar": "Zrušit",

    # --- guardar y resultado ---
    "Sin permiso para escribir ahí: elige otra carpeta": "Do této složky nelze zapisovat: vyberte jinou",
    "No se pudo guardar": "Nelze uložit",
    "Resultado": "Výsledek",
    "Listo": "Hotovo",
    "Atención: quedaron datos en el archivo": "Pozor: v souboru zůstaly osobní údaje",
    "Atención: {sucios} de {total} con datos por revisar": "Pozor: {sucios} z {total} obsahuje údaje ke kontrole",
    "   {sustituciones} sustituciones, sin datos marcados\n": "   náhrad: {sustituciones}, žádné označené údaje nezůstaly\n",
    "   quedaron datos originales; se nombró así para que no se comparta por error\n":
        "   zůstaly původní údaje; soubor je tak pojmenován, aby se omylem nesdílel\n",
    "\nTabla: {tabla}  ": "\nTabulka: {tabla}  ",
    "(privada: tiene los datos reales; sirve para revertir)\n": "(soukromá: obsahuje skutečné údaje; slouží k jejich vrácení)\n",
    "Carpeta: {carpeta}\n": "Složka: {carpeta}\n",
    "Copiar texto limpio": "Kopírovat anonymizovaný text",
    "Abrir carpeta": "Otevřít složku",
    "Cerrar": "Zavřít",
    "Copiado": "Zkopírováno",
    "Texto limpio copiado.": "Anonymizovaný text zkopírován.",

    # --- revertir ---
    "Revertir respuesta de la IA": "Vrátit údaje do odpovědi AI",
    "1. Elige la tabla de equivalencias (_tabla.json) del documento.":
        "1. Vyberte tabulku náhrad dokumentu (_tabla.json).",
    "1. Tabla: {ruta}": "1. Tabulka: {ruta}",
    "Elegir tabla…": "Vybrat tabulku…",
    "Tabla de equivalencias": "Tabulka náhrad",
    "Tabla": "Tabulka",
    "No es una tabla": "Není to tabulka",
    "2. Pega la respuesta de la IA, o arrastra su archivo (.docx, .md, .txt):":
        "2. Vložte odpověď AI nebo sem přetáhněte její soubor (.docx, .md, .txt):",
    "2. Pega la respuesta de la IA, o abre su archivo (.docx, .md, .txt):":
        "2. Vložte odpověď AI nebo otevřete její soubor (.docx, .md, .txt):",
    "2. Archivo de Word: {ruta} (conserva su formato)": "2. Soubor Word: {ruta} (formátování zůstane)",
    "Abrir archivo…": "Otevřít soubor…",
    "Quitar archivo": "Odebrat soubor",
    "Respuesta de la IA": "Odpověď AI",
    "Respuesta": "Odpověď",
    "No se pudo abrir": "Nelze otevřít",
    "3. Vista previa con los datos reales:": "3. Náhled se skutečnými údaji:",
    "Sin revertir (la tabla no las conoce): {desconocidas}": "Nevráceno (tabulka je nezná): {desconocidas}",
    "Guardar .docx": "Uložit .docx",
    "Copiar texto": "Kopírovat text",
    "Falta la tabla": "Chybí tabulka",
    "Elige primero el archivo _tabla.json del documento.": "Nejdřív vyberte soubor _tabla.json k dokumentu.",
    "Guardar respuesta con los datos reales": "Uložit odpověď se skutečnými údaji",
    "Texto con los datos reales copiado.": "Text se skutečnými údaji zkopírován.",

    # --- visor ---
    "Sin documento": "Žádný dokument",
    "Ajustar": "Přizpůsobit",
    "El documento está protegido con contraseña": "Dokument je chráněn heslem",
    "No se pudo abrir el documento": "Dokument nelze otevřít",

    # --- flujo, procesadores, verificación y tabla ---
    "===== Documento {i} de {n}: {nombre} =====\n\n{texto_limpio}": "===== Dokument {i} z {n}: {nombre} =====\n\n{texto_limpio}",
    "No se encontró texto en el documento.": "V dokumentu nebyl nalezen žádný text.",
    "Elige al menos un documento.": "Vyberte alespoň jeden dokument.",
    "El proyecto necesita al menos un documento.": "Projekt musí mít alespoň jeden dokument.",
    "{r} ya está en el proyecto.": "{r} už v projektu je.",
    "El detector de nombres avanzado no está disponible; revisa con más cuidado los nombres.":
        "Pokročilé rozpoznávání jmen není k dispozici; jména kontrolujte pečlivěji.",
    "El modelo checo de nombres no está instalado; solo se usan reglas. Revisa los nombres con cuidado.":
        "Český model pro jména není nainstalován; používají se jen pravidla. Jména pečlivě zkontrolujte.",
    "El modelo inglés de nombres no está instalado; solo se usan reglas. Revisa los nombres con cuidado.":
        "Anglický model pro jména není nainstalován; používají se jen pravidla. Jména pečlivě zkontrolujte.",
    "El detector de nombres avanzado no estaba disponible; revisa con más cuidado los nombres.":
        "Pokročilé rozpoznávání jmen nebylo k dispozici; jména kontrolujte pečlivěji.",
    "Primero revisa los hallazgos y confirma la revisión.": "Nejdřív zkontrolujte nálezy a kontrolu potvrďte.",
    "No se puede sobrescribir el documento original. Elige otro nombre.":
        "Původní dokument nelze přepsat. Zvolte jiný název.",
    "Formato de salida desconocido: {formato}": "Neznámý výstupní formát: {formato}",
    "No hay documentos cargados.": "Nejsou načteny žádné dokumenty.",
    "La tabla no puede ocupar el lugar de un documento.": "Tabulka nemůže nahradit dokument.",
    "{ruta}: se aceptan PDF, Word (.docx, .doc), .odt, .rtf, .txt, .md e imágenes (.jpg, .png, .tif).":
        "{ruta}: podporované formáty jsou PDF, Word (.docx, .doc), .odt, .rtf, .txt, .md a obrázky (.jpg, .png, .tif).",
    "No encuentro el archivo {ruta}.": "Soubor nenalezen: {ruta}.",
    "No pude abrir {ruta} como imagen: {e}": "{ruta} nelze otevřít jako obrázek: {e}",
    "El archivo {doc} se convirtió a .docx; la salida es un .docx.": "Soubor {doc} byl převeden do .docx; výstup je .docx.",
    "Para abrir archivos {doc} se necesita Microsoft Word o LibreOffice instalado. También puedes abrirlo en Word y guardarlo como .docx.":
        "K otevření souborů {doc} je potřeba Microsoft Word nebo LibreOffice. Můžete ho také otevřít ve Wordu a uložit jako .docx.",
    "La salida no puede ser el archivo original; elige otro nombre.": "Výstupem nemůže být původní soubor; zvolte jiný název.",
    "No pude abrir {ruta} como documento de Word: {e}": "{ruta} nelze otevřít jako dokument Word: {e}",
    "No pude abrir {entrada} como documento de Word: {e}": "{entrada} nelze otevřít jako dokument Word: {e}",
    "El documento contiene un objeto incrustado ({partname}) que no se revisa. Ábrelo y revísalo a mano, o elimínalo antes de compartir.":
        "Dokument obsahuje vložený objekt ({partname}), který se nekontroluje. Otevřete ho a zkontrolujte ručně, nebo ho před sdílením odstraňte.",
    "{ruta} está protegido con contraseña. Quita la protección y vuelve a intentarlo.":
        "{ruta} je chráněn heslem. Odstraňte ochranu a zkuste to znovu.",
    "{ruta} no es un PDF.": "{ruta} není PDF.",
    "No pude abrir {ruta} como PDF: {e}": "{ruta} nelze otevřít jako PDF: {e}",
    "Las páginas {paginas} parecen escaneadas y no se pudieron leer (falta el OCR). Sus datos NO se anonimizaron.":
        "Stránky {paginas} jsou zřejmě naskenované a nepodařilo se je přečíst (chybí OCR). Jejich údaje NEBYLY anonymizovány.",
    "Página(s) {paginas} escaneada(s): se leyeron con OCR. Las firmas, sellos y lo escrito a mano siguen visibles; revísalas antes de compartir.":
        "Naskenované stránky {paginas}: přečteny pomocí OCR. Podpisy, razítka a rukopis zůstávají viditelné; před sdílením je zkontrolujte.",
    "Salida en Word: se conserva el texto, no el diseño del PDF; las firmas, sellos e imágenes no se copian.":
        "Výstup ve Wordu: zachová se text, ne vzhled PDF; podpisy, razítka a obrázky se nekopírují.",
    "página {number}": "stránka {number}",
    "anotación p. {number}": "poznámka s. {number}",
    "imagen de la página {number}": "obrázek na stránce {number}",
    "Página {number}: imagen sin texto, no se puede verificar.": "Stránka {number}: obrázek bez textu, nelze zkontrolovat.",
    "archivos adjuntos": "přílohy",
    "el PDF todavía tiene archivos incrustados": "PDF stále obsahuje vložené soubory",
    "No pude leer {ruta}: {e}": "{ruta} nelze přečíst: {e}",
    "Guarda el resultado con otro nombre: el archivo de la IA se conserva.":
        "Uložte výsledek pod jiným názvem: soubor od AI zůstane zachován.",
    "El documento contiene imágenes; revisa que no muestren datos (firmas, credenciales, sellos).":
        "Dokument obsahuje obrázky; zkontrolujte, že neukazují osobní údaje (podpisy, průkazy, razítka).",
    "miniatura de la primera página": "náhled první stránky",
    "{nombre}: objeto incrustado que no se puede verificar automáticamente.":
        "{nombre}: vložený objekt, který nelze automaticky zkontrolovat.",
    "Contiene los datos reales del documento. No la compartas ni la subas a ninguna IA.":
        "Obsahuje skutečné údaje z dokumentu. Nesdílejte ji a nenahrávejte ji do žádné AI.",
    "El archivo no es una tabla de equivalencias del anonimizador.": "Soubor není tabulkou náhrad Anonymizéru.",
    "La etiqueta no puede quedar vacía.": "Označení nesmí být prázdné.",
    "Ya existe la etiqueta {nueva}.": "Označení {nueva} už existuje.",
    "Solo se puede separar una variante de una entidad que tenga varias.":
        "Variantu lze oddělit jen od položky, která jich má víc.",
    "Escribe el texto que quieres ocultar.": "Napište text, který chcete skrýt.",
    "«{valor}» no aparece en el documento. Revisa cómo está escrito.":
        "„{valor}“ se v dokumentu nevyskytuje. Zkontrolujte, jak je napsáno.",
    # IA local (Ollama)
    "Revisar con IA local": "Zkontrolovat místní AI",
    "IA local": "Místní AI",
    "La IA local ({modelo}) no encontró nada más que tapar.": "Místní AI ({modelo}) nenašla nic dalšího ke skrytí.",
    "La IA local ({modelo}) sugirió {n} datos más. Ya están marcados y llevan una ✦: revísalos y desmarca los que no haga falta tapar.":
        "Místní AI ({modelo}) navrhla dalších {n} údajů. Jsou už označené a mají ✦: zkontrolujte je a odznačte ty, které skrývat netřeba.",
    "La IA solo puede estar en esta computadora o en tu red privada ({host} no lo es).":
        "AI smí běžet jen na tomto počítači nebo ve vaší soukromé síti ({host} mezi ně nepatří).",
    "No encontré Ollama en esta computadora. Instálalo desde ollama.com y luego, en una terminal: ollama pull {modelo}":
        "Na tomto počítači není Ollama. Nainstalujte ji z ollama.com a pak v terminálu spusťte: ollama pull {modelo}",
    "Ollama está instalado, pero falta el modelo. En una terminal: ollama pull {modelo}":
        "Ollama je nainstalovaná, ale chybí model. V terminálu spusťte: ollama pull {modelo}",
    "■ Detener la IA": "■ Zastavit AI",
    "Revisión con IA local": "Kontrola místní AI",
    "Es una segunda revisión, después del detector. Una IA lee el documento ya tapado y busca lo que se escapó: fechas en letra, folios, números de escritura o de notaría, colonias, sellos. Lo que sugiere entra a la lista marcado y con una ✦: tú decides qué se queda.":
        "Jde o druhou kontrolu po automatickém rozpoznání. AI přečte už zakrytý dokument a hledá, co uniklo: data psaná slovy, čísla jednací, čísla notářských zápisů, části obcí, razítka. Co navrhne, přidá se do seznamu označené a s ✦: o tom, co zůstane, rozhodujete vy.",
    "Corre completa en esta computadora, con Ollama: el documento no sale de aquí. Solo funciona con gemma3 de 27b (más precisa; pide 32 GB de memoria) o de 12b (cabe en una laptop de 16 GB). Es lenta: cerca de un minuto por cada parte del documento.":
        "Běží celá na tomto počítači přes Ollamu: dokument ho neopustí. Funguje jen s gemma3 27b (přesnější; potřebuje 32 GB paměti) nebo 12b (stačí notebook s 16 GB). Je pomalá: asi minuta na každou část dokumentu.",
    "En esta computadora: {modelo} ✓": "Na tomto počítači: {modelo} ✓",
    "En esta computadora falta instalarla:": "Na tomto počítači ji ještě musíte nainstalovat:",
    "Abrir ollama.com": "Otevřít ollama.com",
    "Copiar": "Kopírovat",
    "{n}. Instala Ollama (gratis).": "{n}. Nainstalujte Ollamu (zdarma).",
    "{n}. En la Terminal, una de dos:": "{n}. V Terminálu spusťte jeden z příkazů:",
    "Cuando termine la descarga, vuelve a presionar «Revisar con IA local».":
        "Po dokončení stahování znovu klikněte na „Zkontrolovat místní AI“.",
    "Preparando la IA local ({modelo})…": "Spouštím místní AI ({modelo})…",
    "IA local ({modelo}): parte {parte} de {total} · cerca de un minuto cada una":
        "Místní AI ({modelo}): část {parte} z {total} · asi minuta na každou",
    "La IA local no respondió ({error}).": "Místní AI neodpověděla ({error}).",
    "Se quitaron {n} comentario(s) del Word: pueden traer datos y el nombre de quien los escribió. El original los conserva.":
        "Z Wordu byly odstraněny komentáře ({n}): mohou obsahovat osobní údaje a jméno autora. Originál je zachovává.",
    "Se aceptaron los cambios controlados del Word: el texto borrado podía traer datos. El original los conserva.":
        "Sledované změny ve Wordu byly přijaty: smazaný text mohl obsahovat osobní údaje. Originál je zachovává.",
    "Algo falló": "Něco se pokazilo",
    "La app tuvo un error y no pudo seguir: {error}\n\nEl detalle (sin datos del documento) quedó en:\n{ruta}":
        "Aplikace narazila na chybu a nemohla pokračovat: {error}\n\nPodrobnosti (bez údajů z dokumentu) jsou uloženy v:\n{ruta}",
    "{nombre}: página {pagina} de {total} escaneada, leyéndola con OCR (unos segundos por página)…":
        "{nombre}: stránka {pagina} z {total} je naskenovaná, čtu ji pomocí OCR (několik sekund na stránku)…",
    "Cambiar el idioma del documento": "Změnit jazyk dokumentu",
    "Se vuelve a leer el documento con las reglas de ese idioma y se pierde la revisión hecha. ¿Seguir?":
        "Dokument se znovu načte s pravidly tohoto jazyka a provedená kontrola se ztratí. Pokračovat?",
    "Cambiar idioma": "Změnit jazyk",
    "Documento en:": "Dokument v jazyce:",
}
