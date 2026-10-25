# -*- coding: utf-8 -*-
"""Prepara los documentos de una prueba para que el modelo los lea, y lleva la cuenta.

Un escaneo no tiene capa de texto, asi que **leerlo es cosa del modelo**: no hay
OCR en esta cadena y no se quiere (ver docs/lectura-facturas.md). Lo que hace este
script es lo mecanico y repetible:

  - inventaria los PDF de la carpeta, y las imagenes sueltas (JPG, JFIF, PNG, TIF,
    BMP: una pagina cada una), y aparta lo que no es una factura
  - renderiza a PNG **solo las paginas que hacen falta**, a 100 ppp
  - dice en cada momento que documentos quedan por transcribir, comparando el
    inventario con el `facturas.json` que el modelo va escribiendo

Esa ultima parte es la que sostiene la lectura sin subagente: el `facturas.json`
es el punto de control, y una compactacion de contexto a mitad de faena no
obliga a releer nada. En la salida de Claude Cowork el trabajo puede ir a un
agente lector, pero el contrato es el mismo fichero y este script no cambia.

**Por que 100 ppp y por que no todas las paginas.** Una pagina A4 a 100 ppp son
827x1170 px, que es legible para un total impreso y cuesta ~1.290 tokens; subir
la resolucion no mejora la lectura de un escaneo de 200 ppp y solo engorda la
factura. Y de una factura de seis paginas interesan dos: la primera, que lleva
la identidad, y la ultima, que suele llevar los totales. Las de en medio son
lineas de detalle que esta prueba no mira. Medido: 37 paginas en vez de 56.

Cuando el entorno tiene subagentes, la lectura se reparte: `--lotes N` escribe
lotes.json con las imagenes de cada lote, cada lector deja su
facturas_lote_N.json, y `--fusionar` los junta en facturas.json comprobando
contra el manifiesto que no falte ni sobre ningun fichero. El contrato no
cambia: facturas.json. Quien lo llena es un detalle del entorno.

**Los nombres de fichero no salen de aqui.** En un despacho los ficheros se llaman
«12 RAZON SOCIAL SL.pdf», y el nombre era la clave de todo el flujo -manifiesto, lotes,
prompts del lector, facturas.json-, asi que la razon social subia a la nube aunque la
imagen fuese tachada (registro del 21/10/2026). Desde el MCP 1.26.0 el manifiesto de
preparar_facturas trae en `fichero` un ALIAS -«12 - DOC 3fa2-f07.pdf»: el numero de
elemento y un codigo por documento- y ya no trae `ruta`. Con `--carpeta` este script hace
lo mismo con la misma regla: lo que imprime y lo que pasa a los lectores es el alias, el id
y las imagenes; el nombre real se queda en el manifiesto local (`reales`) para enlazar el
documento y para que el papel lo recupere al escribirse.

Uso:
    python preparar_documentos.py --carpeta <dir> --trabajo <dir>
    python preparar_documentos.py --carpeta <dir> --trabajo <dir> --incluir "ALBARAN 77.pdf"   (o su alias, o su id)
    python preparar_documentos.py --trabajo <dir> --lotes 10
    python preparar_documentos.py --trabajo <dir> --fusionar
    python preparar_documentos.py --trabajo <dir> --estado
    python preparar_documentos.py --trabajo <dir> --ampliar "18 - DOC 3fa2-f07.pdf"   (la ultima pagina; o el id, f07)
    python preparar_documentos.py --trabajo <dir> --ampliar f07 --pagina 3

Codigos de salida: 0 todo bien · 1 hay avisos · 2 no se puede seguir.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import re
from pathlib import Path

PPP = 100                  # puntos por pulgada del render
ANCHO_A4 = 827             # px de referencia a 100 ppp, solo informativo
# Lado mayor de una imagen suelta tras normalizarla: el alto de un A4 a 100 ppp. Una foto de
# movil trae 4.000 px y no se lee mejor que a esta escala; solo cuesta mas.
LADO_IMAGEN = 1170

# Lo que en una carpeta de documentacion no es la factura de la muestra. No se
# borra ni se esconde: se aparta y se dice, porque el auditor tiene que saber
# que habia. En la calibracion eran 4 justificantes de pago de 22 ficheros.
# «ALBAR» (albaran) desde el 20/10/2026: en una prueba de ventas subieron siete como facturas y
# dieron total vacio. Es la MISMA lista que la del MCP (preparar_facturas, 1.25.1).
# «TODOS»/«TODAS» desde el 21/10/2026 (MCP 1.26.0): un «... TODOS.pdf» que junta las facturas,
# junto a las numeradas, hacia leer cada una dos veces. Sin prefijo de elemento, se aparta.
NO_FACTURA = ("JUSTIFICANTE", "ALBAR", "ADEUDO", "RECIBO", "TRANSFERENCIA", "REMESA",
              "PAGO 1", "PAGO 2", "INDICE", "CARATULA", "ULTIMA ESCANEADA", "TODOS", "TODAS")

# El alias con que un documento sale del equipo, el MISMO que el del MCP 1.26.0
# (_RE_ALIAS_DOC / _alias_doc): «<prefijo> - [MARCA ]DOC <lote>-<id><ext>», donde el prefijo son
# los digitos con que empieza el nombre real (el numero de elemento), <lote> cuatro hex fijos por
# carpeta e <id> f01 (documento), a01 (apartado) o x01 (no reconocido). El separador « - » es el
# que parten _cabecera() y _grupo(), asi que el alias conserva el grupo del elemento.
RE_ALIAS = re.compile(r"(?:\d+ - )?(?:[A-Z0-9_]+ )?DOC ([0-9a-f]{4})-([fax]\d{2,})(?:\.[A-Za-z0-9]{2,5})?")
RE_ID = re.compile(r"[fax]\d{2,}")

# Imagenes sueltas: una pagina por fichero, las mismas extensiones que acepta el MCP 1.25.1. En el
# registro del 20/10/2026 una carpeta de JFIF y JPG dio «no hay ningun PDF».
EXT_IMAGEN = (".jpg", ".jpeg", ".jfif", ".png", ".tif", ".tiff", ".bmp")
EXT_DOCUMENTO = (".pdf",) + EXT_IMAGEN


def _salida_utf8() -> None:
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _marcado(nombre: str) -> bool:
    """El nombre contiene alguna palabra de las que suele llevar un justificante."""
    return bool(_marca_de(nombre))


def _cabecera(nombre: str) -> str:
    return nombre.split(" - ", 1)[0].strip()


def lote_de(carpeta) -> str:
    """Cuatro hex fijos por carpeta, calculados como en el MCP."""
    return hashlib.sha1(os.path.normcase(os.path.abspath(str(carpeta))).encode("utf-8")).hexdigest()[:4]


def alias_doc(lote: str, ident: str, nombre_real: str, marca: str = "") -> str:
    """El nombre con que el documento sale del equipo: numero de elemento, marca y codigo, sin
    una letra del nombre real. Pura, y la misma regla que la del MCP."""
    m = re.match(r"\s*(\d+)(?=\D|$)", nombre_real)
    ext = Path(nombre_real).suffix.lower()
    cuerpo = (marca.replace(" ", "_") + " " if marca else "") + f"DOC {lote}-{ident}{ext}"
    return (m.group(1) + " - " + cuerpo) if m else cuerpo


def _marca_de(nombre: str) -> str:
    """La palabra de NO_FACTURA que lleva el nombre, o "". TODOS/TODAS como palabra entera, como
    en el MCP: por subcadena apartaria a un proveedor «METODOS ...». Las demas, por subcadena."""
    alto = nombre.upper()
    for p in NO_FACTURA:
        if (re.search(r"(?<![A-Z])" + p + r"(?![A-Z])", alto) if p in ("TODOS", "TODAS") else p in alto):
            return p
    return ""


def prefijo_de(fichero: str) -> str:
    """El numero de elemento con que empieza el fichero (o su alias); '' si no lleva."""
    cabeza = _cabecera(str(fichero or ""))
    return cabeza if cabeza.isdigit() else ""


def id_de_clave(clave: str) -> str:
    """El id que lleva una clave de documento: el alias entero, o el id a secas. '' si ninguno."""
    t = str(clave or "").strip()
    m = RE_ALIAS.search(t)
    if m:
        return m.group(2)
    return t.lower() if RE_ID.fullmatch(t.lower()) else ""


def _grupo(nombre: str) -> str:
    """El número de orden con que el auditor encabeza los ficheros de una misma factura.

    En una carpeta de documentación los ficheros de un mismo elemento van
    numerados: «6 - X FRA F25-002 + JUSTIFICANTE PAGO.pdf» y «6 - X FRA
    F25-002.pdf» serían del mismo grupo.
    """
    cabeza = _cabecera(nombre)
    return cabeza if cabeza.isdigit() else Path(nombre).stem.upper()


def clasificar(pdfs: list[Path], incluir=frozenset()) -> tuple[list[Path], list[Path]]:
    """Reparte los documentos entre facturas y justificantes apartados.

    **El nombre por sí solo no basta**, y esto costó una factura en la primera
    prueba. Hay dos casos con la misma palabra en el nombre:

      - «2 - X FRA 367 JUSTIFICANTE PAGO 1.pdf», que es un justificante, y la
        factura está en otro fichero: «2 - X FRA 367.pdf»
      - «6 - X FRA F25-002 + JUSTIFICANTE PAGO.pdf», que **es la factura**, con
        el justificante escaneado detrás, y no hay otro fichero

    Lo que los distingue no es el nombre, es si en el grupo hay otro fichero sin
    marcar. Si no lo hay, el marcado es la única evidencia que existe de ese
    elemento y **no se aparta**: leer una página de más es barato, perder la
    factura de un elemento seleccionado no.

    Pero esa protección la da el PREFIJO NUMÉRICO del elemento. Un fichero marcado sin él
    —«JUSTIFICANTE REMESA 03.pdf», «ALBARAN 1234.pdf»— no tiene grupo que lo proteja y se
    aparta igual (20/10/2026: ocho justificantes y siete albaranes subieron como facturas y
    dieron total vacío). Es la regla del MCP 1.25.1, para que el render local y el del MCP
    aparten lo mismo. Lo que se pida por su nombre en `incluir` no se aparta nunca: es como se
    recupera un falso positivo.
    """
    pedidos = {str(x).strip().lower() for x in incluir}
    facturas, apartados = [], []
    grupos: dict[str, list[Path]] = {}
    for p in pdfs:
        grupos.setdefault(_grupo(p.name), []).append(p)
    for _, ficheros in grupos.items():
        limpios = [f for f in ficheros if not _marcado(f.name)]
        for f in ficheros:
            if (_marcado(f.name) and (limpios or not _cabecera(f.name).isdigit())
                    and f.name.lower() not in pedidos):
                apartados.append(f)
            else:
                facturas.append(f)
    return sorted(facturas), sorted(apartados)


def _es_imagen(ruta: Path) -> bool:
    return ruta.suffix.lower() in EXT_IMAGEN


def _imagen_a_pagina(img: Path, destino: Path, prefijo: str, nombre: str = "") -> tuple[Path, str]:
    """Una imagen suelta como la página 1 de su documento, y un aviso ('' si no hay).

    Con Pillow (o PyMuPDF) se normaliza: RGB, lado mayor LADO_IMAGEN y PNG, como una página de
    PDF renderizada. Sin ninguna de las dos se COPIA tal cual si es un formato que el modelo lee
    (JPEG o PNG; el JFIF es JPEG y se copia como .jpg); un TIF o un BMP sin librería no se puede
    convertir y se dice. `nombre` es como se nombra el documento en los avisos: su alias, nunca
    el nombre real, que iria al chat (registro del 21/10/2026).
    """
    nombre = nombre or prefijo
    destino.mkdir(parents=True, exist_ok=True)
    salida = destino / f"{prefijo}_p1.png"
    if salida.exists():
        return salida, ""
    try:
        from PIL import Image
    except ImportError:
        Image = None
    if Image is not None:
        with Image.open(img) as im:
            marcos = getattr(im, "n_frames", 1)
            im.seek(0)
            pag = im.convert("RGB")
            pag.thumbnail((LADO_IMAGEN, LADO_IMAGEN))
            pag.save(salida)
        aviso = (f"{nombre} tiene {marcos} páginas y solo se ha preparado la primera: una imagen "
                 "suelta es un documento de una página") if marcos > 1 else ""
        return salida, aviso
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None
    if fitz is not None:
        pix = fitz.Pixmap(str(img))
        if pix.n - pix.alpha >= 4:
            pix = fitz.Pixmap(fitz.csRGB, pix)
        if pix.alpha:
            pix = fitz.Pixmap(pix, 0)
        while max(pix.width, pix.height) > 2 * LADO_IMAGEN:
            pix.shrink(1)
        pix.save(str(salida))
        return salida, ""
    import shutil
    ext = img.suffix.lower()
    if ext in (".jpg", ".jpeg", ".jfif"):
        copia = destino / f"{prefijo}_p1.jpg"
    elif ext == ".png":
        copia = salida
    else:
        raise SinRenderizador(f"No hay con qué convertir {nombre} ({ext}): falta Pillow y PyMuPDF. "
                              "Conviértelo a PDF, JPG o PNG, o instala una de las dos.")
    shutil.copyfile(img, copia)
    return copia, ""


class SinRenderizador(RuntimeError):
    pass


def _renderizar(pdf: Path, paginas: list[int], destino: Path, prefijo: str) -> list[Path]:
    """Renderiza las paginas pedidas (1-based) y devuelve los PNG escritos.

    Primero PyMuPDF, que es lo que hay en Windows; si no esta, pdftoppm, que es
    lo que suele haber en un contenedor Linux. Si no hay ninguno, se dice: es un
    fallo del entorno, no del expediente.
    """
    destino.mkdir(parents=True, exist_ok=True)
    escritos = []
    try:
        import fitz  # PyMuPDF
    except ImportError:
        fitz = None

    if fitz is not None:
        doc = fitz.open(pdf)
        try:
            zoom = PPP / 72.0
            for n in paginas:
                if n < 1 or n > doc.page_count:
                    continue
                salida = destino / f"{prefijo}_p{n}.png"
                if not salida.exists():
                    pix = doc.load_page(n - 1).get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                    pix.save(salida)
                escritos.append(salida)
        finally:
            doc.close()
        return escritos

    import shutil
    import subprocess
    if shutil.which("pdftoppm") is None:
        raise SinRenderizador(
            "No hay con qué renderizar los PDF: falta PyMuPDF (pip install pymupdf) y no está "
            "pdftoppm en el PATH. Sin uno de los dos, el modelo tendría que abrir los PDF "
            "directamente, que también vale pero lee todas las páginas que le pidas.")
    for n in paginas:
        salida = destino / f"{prefijo}_p{n}.png"
        if not salida.exists():
            subprocess.run(["pdftoppm", "-r", str(PPP), "-png", "-f", str(n), "-l", str(n),
                            str(pdf), str(destino / f"{prefijo}_tmp")], check=True)
            sueltos = sorted(destino.glob(f"{prefijo}_tmp*.png"))
            if sueltos:
                sueltos[0].rename(salida)
            for extra in destino.glob(f"{prefijo}_tmp*.png"):
                extra.unlink()
        escritos.append(salida)
    return escritos


def _paginas_sin_libreria(datos: bytes) -> int:
    """Numero de paginas leido de los bytes del PDF, sin ninguna libreria.

    Primero el /Count del nodo raiz del arbol de paginas (/Type /Pages): es exacto
    aunque el fichero lleve guardados incrementales, que repiten los objetos. Solo
    si no aparece se cuentan los objetos /Type /Page, que es lo que se hacia antes y
    dio «4 paginas» en un documento de una («Pagina 1/1» en el pie): el escaner habia
    guardado el PDF varias veces y cada guardado repetia la pagina. Medido el
    15/09/2026 en una MUM real, en el contenedor de Cowork, donde no hay PyMuPDF.
    """
    cuentas = []
    for m in re.finditer(rb"<<(.{0,400}?)>>", datos, re.S):
        d = m.group(1)
        if re.search(rb"/Type\s*/Pages\b", d) and not re.search(rb"/Parent\b", d):
            c = re.search(rb"/Count\s+(\d+)", d)
            if c:
                cuentas.append(int(c.group(1)))
    if cuentas:
        return max(max(cuentas), 1)
    n = len(re.findall(rb"/Type\s*/Page\b", datos))
    return max(n, 1)


def _paginas_de(pdf: Path) -> int:
    if _es_imagen(pdf):
        return 1      # una imagen suelta es una pagina, como en el MCP
    try:
        import fitz
        doc = fitz.open(pdf)
        try:
            return doc.page_count
        finally:
            doc.close()
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
        return max(len(PdfReader(str(pdf)).pages), 1)
    except Exception:
        pass
    return _paginas_sin_libreria(pdf.read_bytes())


def inventariar(carpeta: Path, trabajo: Path, incluir=frozenset()) -> dict:
    todos = sorted(p for p in carpeta.rglob("*") if p.is_file())
    # si el directorio de trabajo cuelga de la carpeta, sus renders (pag/*.png) no son documentos:
    # con las imagenes sueltas admitidas, se volverian a inventariar como facturas
    dentro = trabajo.resolve()
    todos = [p for p in todos if dentro not in p.resolve().parents]
    pdfs = [p for p in todos if p.suffix.lower() in EXT_DOCUMENTO]
    if not pdfs:
        raise SystemExit(f"[C] No hay ningún PDF ni ninguna imagen ({', '.join(EXT_IMAGEN)}) en {carpeta}")
    # Lo que hay en la carpeta y NO es un documento se lista, no se omite: en una
    # ejecucion real habia un fichero companero sin extension, de pocos KB, junto
    # a una factura, y nadie supo que era porque el inventario solo miraba PDF.
    # Descartar en silencio es como no haberlo visto; decir «esto tambien estaba»
    # deja al auditor decidir. Los renders propios del skill (pag/) no cuentan.
    no_pdf = [p for p in todos if p.suffix.lower() not in EXT_DOCUMENTO]
    # Los ids son ESTABLES entre pasadas sobre la misma carpeta, como en el MCP: el alias lleva el
    # id, facturas.json se escribe por alias, y un --incluir que corriera la numeracion dejaria lo
    # ya transcrito apuntando a otro documento (y su render, pag/f03_p1.png, al de antes).
    lote = lote_de(carpeta)
    reales: dict[str, str] = {}
    previo = trabajo / "manifiesto.json"
    if previo.exists():
        try:
            p0 = json.loads(previo.read_text(encoding="utf-8"))
            if p0.get("origen") == "local" and p0.get("lote") == lote:
                reales = dict(p0.get("reales") or {})
        except (json.JSONDecodeError, OSError, AttributeError):
            pass
    ids = {rel.lower(): ident for ident, rel in reales.items()}
    conocidos = set(reales)

    def rel(p: Path) -> str:
        return p.relative_to(carpeta).as_posix()

    def id_de(r: str, letra: str) -> str:
        if r.lower() in ids and ids[r.lower()].startswith(letra):
            return ids[r.lower()]
        usados = [int(v[1:]) for v in reales if v.startswith(letra) and v[1:].isdigit()]
        nuevo = f"{letra}{(max(usados) + 1) if usados else 1:02d}"
        ids[r.lower()] = nuevo
        reales[nuevo] = r
        return nuevo

    # --incluir admite el nombre real (lo dice el auditor), el alias o el id que se imprimio
    pedidos, no_vistos = set(), []
    for x in incluir:
        ident = id_de_clave(x)
        pedidos.add(Path(reales[ident]).name.lower() if ident in reales else str(x).strip().lower())
    utiles, fuera = clasificar(pdfs, pedidos)
    docs = []
    for p in utiles:
        r = rel(p)
        ident = ids.get(r.lower(), "")
        if not ident.startswith(("f", "a")):      # un apartado recuperado conserva su id «a»
            ident = id_de(r, "f")
        docs.append({"id": ident, "fichero": alias_doc(lote, ident, p.name,
                                                       _marca_de(p.name) if ident.startswith("a") else ""),
                     "ruta": str(p), "paginas": _paginas_de(p), "imagenes": []})
    nombres_docs = {p.name.lower() for p in utiles}
    for x in incluir:
        ident = id_de_clave(x)
        nombre = Path(reales[ident]).name.lower() if ident in reales else str(x).strip().lower()
        if nombre not in nombres_docs:
            no_vistos.append(str(x))
    man = {"carpeta": str(carpeta), "lote": lote, "origen": "local", "ppp": PPP, "documentos": docs,
           "apartados": [alias_doc(lote, id_de(rel(x), "a"), x.name, _marca_de(x.name)) for x in fuera],
           "no_reconocidos": [f"{alias_doc(lote, id_de(rel(x), 'x'), x.name)} "
                              f"({max(1, x.stat().st_size // 1024)} KB)" for x in no_pdf],
           # el nombre real de cada id: se queda en este manifiesto, que no se imprime ni se sube
           "reales": reales,
           "_nuevos": sorted(set(reales) - conocidos), "_incluir_no_vistos": no_vistos}
    trabajo.mkdir(parents=True, exist_ok=True)
    previo.write_text(json.dumps(_sin_privados(man), ensure_ascii=False, indent=1), encoding="utf-8")
    return man


def _carpeta_manifiesto(trabajo: Path) -> Path | None:
    """Donde esta manifiesto.json: en el directorio de trabajo, o en la subcarpeta que deja
    preparar_facturas cuando se sube entera (`facturas/`). En el registro del 16/09/2026 hubo
    que copiarlo a mano un nivel arriba porque solo se miraba la raiz."""
    if (trabajo / "manifiesto.json").exists():
        return trabajo
    if (trabajo / "facturas" / "manifiesto.json").exists():
        return trabajo / "facturas"
    cands = [p.parent for p in trabajo.glob("*/manifiesto.json")]
    return cands[0] if len(cands) == 1 else None


def _leer_manifiesto(trabajo: Path) -> dict:
    carpeta = _carpeta_manifiesto(trabajo)
    if carpeta is None:
        raise SystemExit("[C] No hay manifiesto: ejecuta primero con --carpeta, o sube la carpeta de "
                         "preparar_facturas (imagenes + manifiesto.json) dentro de --trabajo")
    man = json.loads((carpeta / "manifiesto.json").read_text(encoding="utf-8"))
    man["_carpeta"] = str(carpeta)   # las imagenes relativas se resuelven contra esta
    return man


def _sin_privados(man: dict) -> dict:
    return {k: v for k, v in man.items() if not str(k).startswith("_")}


def _aviso_nombres_reales(man: dict) -> str:
    """Un manifiesto del MCP anterior a la 1.26.0 lleva en `fichero` el nombre real, y saldria tal
    cual en lo impreso y en los lotes del lector. Se dice; el flujo sigue igual."""
    if man.get("origen") != "mcp":
        return ""
    reales = [d for d in man.get("documentos") or [] if not RE_ALIAS.fullmatch(str(d.get("fichero") or ""))]
    if not reales:
        return ""
    return (f"el manifiesto de preparar_facturas lleva en {len(reales)} documento(s) el NOMBRE REAL del "
            "fichero, no su alias: es de un MCP anterior a la 1.26.0, y esos nombres salen en lo que "
            "imprime este script y en los lotes del lector. Dilo al auditor (que actualice el plugin) "
            "y no repitas los nombres en el chat.")


def _claves(man: dict) -> dict[str, str]:
    """{clave con que puede venir un documento: su `fichero` en el manifiesto}. Un lector o el
    modelo pueden escribir el alias entero o solo el id (f07); los dos son el mismo documento."""
    claves: dict[str, str] = {}
    for d in man.get("documentos") or []:
        claves[d["fichero"]] = d["fichero"]
        if d.get("id"):
            claves[str(d["id"]).lower()] = d["fichero"]
    return claves


def _normalizar(clave: str, claves: dict[str, str]) -> str:
    if clave in claves:
        return claves[clave]
    return claves.get(id_de_clave(clave), clave)


def _transcritos(trabajo: Path, man: dict | None = None) -> set[str]:
    """Lo ya escrito por el modelo en facturas.json: el punto de control. Con el manifiesto,
    cada entrada se reconoce por su alias o por su id."""
    f = trabajo / "facturas.json"
    if not f.exists():
        return set()
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    claves = _claves(man) if man else {}
    return {_normalizar(x.get("fichero"), claves) for x in d.get("facturas", []) if x.get("fichero")}


def _imagenes_abs(trabajo: Path, imagenes: list) -> list[str]:
    """Las imagenes del manifiesto con ruta absoluta. Las que hizo el MCP en el equipo del
    auditor (preparar_facturas) van con el nombre a secas, relativo al manifiesto: asi la
    misma carpeta vale en Windows y, subida, en el contenedor."""
    return [i if Path(i).is_absolute() else str(trabajo / i) for i in imagenes]


def repartir_lotes(trabajo: Path, tamano: int) -> list[dict]:
    """Los documentos pendientes de transcribir, en lotes de `tamano`.

    Es lo que se le da a cada lector: el `fichero` del manifiesto -el alias, que es la clave
    que tiene que devolver-, el id, el numero de elemento y las imagenes, nada mas. Ni la
    ruta ni el nombre real: el lote va en el prompt del lector (registro del 21/10/2026).
    Solo los pendientes, para que una segunda pasada tras una compactacion no vuelva a
    leer lo ya transcrito. Se escribe en lotes.json para que quede constancia de
    que se lanzo.
    """
    man = _leer_manifiesto(trabajo)
    base = Path(man.get("_carpeta") or trabajo)
    hechos = _transcritos(trabajo, man)
    pend = [d for d in man["documentos"] if d["fichero"] not in hechos]
    lotes = []
    for i in range(0, len(pend), max(1, tamano)):
        n = len(lotes) + 1
        lotes.append({"lote": n,
                      "salida": str(trabajo / f"facturas_lote_{n}.json"),
                      "documentos": [{"fichero": d["fichero"], "id": d.get("id", ""),
                                      "prefijo": prefijo_de(d["fichero"]),
                                      "imagenes": _imagenes_abs(base, d["imagenes"]),
                                      "paginas": d["paginas"]} for d in pend[i:i + tamano]]})
    (trabajo / "lotes.json").write_text(json.dumps(lotes, ensure_ascii=False, indent=1), encoding="utf-8")
    return lotes


def _json_de_lote(texto: str):
    """El JSON de un lote, aunque venga con adornos alrededor. Un lector devolvio el fichero
    terminado en `]}\n</content>` y se perdio el lote entero -10 documentos- por un cierre de
    etiqueta (registro del 16/09/2026). Se prueba tal cual; si no, desde la primera llave hasta
    el ultimo cierre que parsee. Devuelve None si no hay JSON dentro."""
    t = (texto or "").strip()
    for intento in (t, t.strip("`"), _entre_llaves(t)):
        if not intento:
            continue
        try:
            d = json.loads(intento)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(d, dict):
            return d
        if isinstance(d, list):
            return {"facturas": d}
    return None


def _entre_llaves(t: str):
    """Desde la primera llave hasta el ultimo cierre que parsee, recortando por el final."""
    i = t.find("{")
    if i < 0:
        return None
    cola = t[i:]
    for j in range(len(cola), 0, -1):
        if cola[j - 1] not in "}]":
            continue
        try:
            json.loads(cola[:j])
            return cola[:j]
        except json.JSONDecodeError:
            continue
    return None


def fusionar(trabajo: Path) -> dict:
    """Junta los facturas_lote_*.json en facturas.json y dice que falta y que sobra.

    Lo que ya hubiera en facturas.json se conserva -es el punto de control- y las
    entradas de los lotes se anaden o lo sustituyen por su `fichero` (el alias, o el id). Un
    fichero del manifiesto sin entrada es un documento que ningun lector
    transcribio; una entrada cuyo fichero no esta en el manifiesto es un lector
    que se invento un documento, y las dos cosas se dicen.
    """
    man = _leer_manifiesto(trabajo)
    conocidos = {d["fichero"] for d in man["documentos"]}
    claves = _claves(man)
    por_fichero: dict[str, dict] = {}
    f_out = trabajo / "facturas.json"
    if f_out.exists():
        try:
            for x in json.loads(f_out.read_text(encoding="utf-8")).get("facturas", []):
                if x.get("fichero"):
                    x["fichero"] = _normalizar(x["fichero"], claves)
                    por_fichero[x["fichero"]] = x
        except json.JSONDecodeError:
            pass
    parciales = sorted(trabajo.glob("facturas_lote_*.json"))
    leidas, rescatados = 0, []
    for p in parciales:
        crudo = p.read_text(encoding="utf-8")
        try:
            datos = json.loads(crudo)
        except json.JSONDecodeError:
            datos = _json_de_lote(crudo)
            if datos is None:
                print(f"[A] {p.name}: no es JSON válido ni recortando, se ignora")
                continue
            rescatados.append(p.name)
            print(f"[A] {p.name}: traía texto de más alrededor del JSON; se ha recortado y leído")
        for x in datos.get("facturas", []):
            if x.get("fichero"):
                # el agente no ata documentos a elementos: eso es del auditor
                x.pop("poblacion_id", None)
                # el lector puede devolver el id a secas: la clave es el `fichero` del manifiesto
                x["fichero"] = _normalizar(x["fichero"], claves)
                por_fichero[x["fichero"]] = x
                leidas += 1
    orden = [d["fichero"] for d in man["documentos"]]
    facturas = [por_fichero[f] for f in orden if f in por_fichero]
    sobran = [f for f in por_fichero if f not in conocidos]
    facturas += [por_fichero[f] for f in sobran]
    f_out.write_text(json.dumps({"facturas": facturas}, ensure_ascii=False, indent=1), encoding="utf-8")
    faltan = [f for f in orden if f not in por_fichero]
    return {"parciales": len(parciales), "entradas": leidas, "total": len(facturas),
            "faltan": faltan, "sobran": sobran, "rescatados": rescatados}


def main() -> int:
    _salida_utf8()
    ap = argparse.ArgumentParser(description="Prepara y contabiliza los documentos de la prueba")
    ap.add_argument("--carpeta", help="carpeta con los documentos escaneados (inventaría y renderiza)")
    ap.add_argument("--trabajo", required=True, help="directorio de trabajo del skill")
    ap.add_argument("--estado", action="store_true", help="qué queda por transcribir")
    ap.add_argument("--ampliar", help="documento del que hace falta otra página: su alias o su id")
    ap.add_argument("--pagina", type=int, help="con --ampliar: qué página (por defecto, la última)")
    ap.add_argument("--lotes", type=int, metavar="N",
                    help="reparte los documentos pendientes en lotes de N para los lectores, y escribe lotes.json")
    ap.add_argument("--fusionar", action="store_true",
                    help="junta los facturas_lote_*.json de los lectores en facturas.json")
    ap.add_argument("--incluir", action="append", default=[], metavar="FICHERO",
                    help="con --carpeta: un fichero apartado por su nombre (justificante, albarán…) "
                         "que el auditor dice que SÍ es documento de la muestra: su nombre, su alias "
                         "o su id (a01). Se puede repetir")
    a = ap.parse_args()
    trabajo = Path(a.trabajo)
    avisos: list[str] = []

    if a.carpeta:
        carpeta = Path(a.carpeta)
        if not carpeta.is_dir():
            print(f"[C] No existe la carpeta {carpeta}")
            return 2
        man = inventariar(carpeta, trabajo, a.incluir)
        n_img = sum(1 for d in man["documentos"] if _es_imagen(Path(d["fichero"])))
        print(f"Inventario: {len(man['documentos'])} documento(s) de factura en {carpeta}"
              + (f", {n_img} de ellos imagen suelta (una página cada una)" if n_img else ""))
        no_vistos = man.get("_incluir_no_vistos") or []
        if no_vistos:
            avisos.append("--incluir con valores que no son ningún documento de la carpeta (ni por su "
                          "nombre, ni por su alias o id): " + ", ".join(no_vistos))
        if man.get("no_reconocidos"):
            avisos.append(f"{len(man['no_reconocidos'])} fichero(s) en la carpeta que no son PDF ni imagen y no se han leído: "
                          + ", ".join(man["no_reconocidos"][:6]) + (" …" if len(man["no_reconocidos"]) > 6 else "")
                          + ". Si alguno es un documento de la muestra, conviértelo a PDF o dilo al entregar.")
        if man["apartados"]:
            avisos.append(f"{len(man['apartados'])} fichero(s) apartados por su nombre (justificantes, "
                          "remesas, recibos, transferencias, albaranes…), sin leer: "
                          + ", ".join(man["apartados"][:6])
                          + (" …" if len(man["apartados"]) > 6 else "")
                          + ". Díselo al auditor por el número de elemento y la marca; si alguno SÍ es "
                            "documento de la muestra, repite con --incluir «<alias o id>»")
        # Primera pagina de cada uno. La ultima se pide con --ampliar cuando el
        # modelo vea que en la primera no estaban los totales.
        pag = trabajo / "pag"
        # un id nuevo no hereda el render de otro documento que tuviera ese id antes
        for ident in man.get("_nuevos") or []:
            for viejo in pag.glob(f"{ident}_p*.*") if pag.is_dir() else []:
                viejo.unlink()
        try:
            for d in man["documentos"]:
                if _es_imagen(Path(d["ruta"])):
                    img, aviso = _imagen_a_pagina(Path(d["ruta"]), pag, d["id"], d["fichero"])
                    d["imagenes"] = [str(img)]
                    if aviso:
                        avisos.append(aviso)
                    continue
                imgs = _renderizar(Path(d["ruta"]), [1], pag, d["id"])
                d["imagenes"] = [str(x) for x in imgs]
        except SinRenderizador as e:
            print(f"[C] {e}")
            return 2
        except OSError as e:
            if getattr(e, "errno", None) == 22:
                print("[C] Un PDF no se puede abrir: si el expediente está en OneDrive, los "
                      "ficheros «solo en la nube» dan este error. Pide al usuario que haga clic "
                      "derecho en la carpeta y elija «Mantener siempre en este dispositivo».")
                return 2
            raise
        (trabajo / "manifiesto.json").write_text(
            json.dumps(_sin_privados(man), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Renderizada la página 1 de cada documento a {PPP} ppp ({ANCHO_A4} px de ancho) "
              f"en {pag}")
        varias = [d for d in man["documentos"] if d["paginas"] > len(d.get("imagenes") or [1])]
        if varias:
            print(f"[A] {len(varias)} documento(s) tienen páginas SIN VER "
                  f"({sum(d['paginas'] - len(d.get('imagenes') or [1]) for d in varias)} en total):")
            for d in varias:
                print(f"      {d['id']}  {d['paginas']}p, vistas {len(d.get('imagenes') or [1])}  {d['fichero']}")
            print("    Un escaneo de archivo mete varias facturas, albaranes y guías en el mismo PDF: "
                  "esas páginas pueden traer OTRO documento, no líneas de detalle. Pide las que hagan "
                  "falta con --ampliar «<alias o id>» --pagina N. Obligatorio mirarlas antes de dar por "
                  "buena una diferencia de importe o un total ilegible.")

    if a.ampliar or a.lotes or a.fusionar or a.estado:
        aviso_viejo = _aviso_nombres_reales(_leer_manifiesto(trabajo))
        if aviso_viejo:
            avisos.append(aviso_viejo)

    if a.ampliar:
        man = _leer_manifiesto(trabajo)
        clave = _normalizar(a.ampliar.strip(), _claves(man))
        reales = {Path(r).name.lower(): i for i, r in (man.get("reales") or {}).items()}
        doc = next((d for d in man["documentos"]
                    if d["fichero"] == clave or d["id"] == reales.get(a.ampliar.strip().lower())), None)
        if doc is None:
            print(f"[C] No está en el manifiesto: {a.ampliar}")
            return 2
        if man.get("origen") == "mcp":
            # Las imagenes las hizo el MCP en el equipo del auditor, tachadas: aqui no hay
            # PDF que renderizar, y renderizarlo saltaria el tachado.
            print(f"Las imágenes de este manifiesto las hizo el MCP (preparar_facturas, modo {man.get('modo', '?')}). "
                  f"Pide la página con el MCP: preparar_facturas(carpeta=..., destino=..., modo=\"{man.get('modo', 'tachadas')}\", "
                  f"documentos=[\"{doc['fichero']}\"], paginas=[{a.pagina or -1}]), vuelve a subir la carpeta y sigue.")
            return 0
        if _es_imagen(Path(doc["fichero"])):
            print(f"{doc['fichero']} es una imagen suelta: tiene una sola página y ya está preparada. "
                  "Si el total está en otra imagen, es otro documento del inventario: míralo con "
                  "--estado entre los de su mismo número de elemento, sin listar la carpeta.")
            return 0
        n = a.pagina or doc["paginas"]
        try:
            imgs = _renderizar(Path(doc["ruta"]), [n], trabajo / "pag", doc["id"])
        except SinRenderizador as e:
            print(f"[C] {e}")
            return 2
        doc["imagenes"] = sorted(set(doc["imagenes"]) | {str(x) for x in imgs})
        (Path(man["_carpeta"]) / "manifiesto.json").write_text(
            json.dumps(_sin_privados(man), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"Página {n} de {doc['fichero']}: {', '.join(str(x) for x in imgs)}")

    if a.lotes:
        lotes = repartir_lotes(trabajo, a.lotes)
        print(f"{len(lotes)} lote(s) de hasta {a.lotes} documento(s) en {trabajo / 'lotes.json'}")
        for lt in lotes:
            print(f"  lote {lt['lote']} · {len(lt['documentos'])} documento(s) · salida {lt['salida']}")
            for d in lt["documentos"]:
                print(f"      {d['id']}  {d['fichero']}  ->  " + ", ".join(d["imagenes"]))
        if not lotes:
            print("  no queda ningún documento por transcribir")

    if a.fusionar:
        r = fusionar(trabajo)
        print(f"Fusionados {r['parciales']} lote(s), {r['entradas']} entrada(s): facturas.json tiene "
              f"{r['total']} documento(s)")
        if r["faltan"]:
            avisos.append(f"{len(r['faltan'])} documento(s) del manifiesto sin transcribir: "
                          + ", ".join(r["faltan"][:6]) + (" …" if len(r["faltan"]) > 6 else ""))
        if r["sobran"]:
            avisos.append(f"{len(r['sobran'])} entrada(s) cuyo fichero no está en el manifiesto: "
                          + ", ".join(r["sobran"][:6]))

    if a.estado or not (a.carpeta or a.ampliar or a.lotes or a.fusionar):
        man = _leer_manifiesto(trabajo)
        hechos = _transcritos(trabajo, man)
        pend = [d for d in man["documentos"] if d["fichero"] not in hechos]
        print(f"Transcritos {len(man['documentos']) - len(pend)} de {len(man['documentos'])} documento(s)"
              + (f", y {len(hechos - {d['fichero'] for d in man['documentos']})} entrada(s) de "
                 "facturas.json que no son de este inventario" if hechos - {d["fichero"] for d in man["documentos"]}
                 else "") + ".")
        if pend:
            print("Pendientes:")
            for d in pend:
                print(f"  {d['id']}  {d['paginas']}p  {d['fichero']}")
                for img in d["imagenes"]:
                    print(f"        {img}")
        else:
            print("No queda ninguno: sigue con verificar_contrato.py.")

    for v in avisos:
        print(f"[A] {v}")
    return 1 if avisos else 0


if __name__ == "__main__":
    sys.exit(main())
