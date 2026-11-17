"""Los tests corren con la interfaz en español y sin leer las preferencias de quien los corre."""

import os
import tempfile

os.environ["ANONIMIZADOR_IDIOMA_UI"] = "es"
os.environ.setdefault("ANONIMIZADOR_PREFERENCIAS", os.path.join(tempfile.mkdtemp(), "preferencias.json"))
