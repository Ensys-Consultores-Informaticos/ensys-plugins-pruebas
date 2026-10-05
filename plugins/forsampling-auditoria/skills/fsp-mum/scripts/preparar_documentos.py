# -*- coding: utf-8 -*-
"""Prepara los documentos de una prueba para que el modelo los lea, y lleva la cuenta.

Un escaneo no tiene capa de texto, asi que **leerlo es cosa del modelo**: no hay
OCR en esta cadena y no se quiere (ver docs/lectura-facturas.md). Lo que hace este
script es lo mecanico y repetible:

  - inventaria los PDF de la carpeta y aparta lo que no es una factura
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

Uso:
    python preparar_documentos.py --carpeta <dir> --trabajo <dir>
    python preparar_documentos.py --trabajo <dir> --lotes 10
    python preparar_documentos.py --trabajo <dir> --fusionar
    python preparar_documentos.py --trabajo <dir> --estado
    python preparar_documentos.py --trabajo <dir> --ampliar "18 - X.pdf"        (la ultima pagina)
    python preparar_documentos.py --trabajo <dir> --ampliar "18 - X.pdf" --pagina 3

Codigos de salida: 0 todo bien · 1 hay avisos · 2 no se puede seguir.
"""
from __future__ import annotations

import argparse
import json
import sys
import re
from pathlib import Path

PPP = 100                  # puntos por pulgada del render
ANCHO_A4 = 827             # px de referencia a 100 ppp, solo informativo

# Lo que en una carpeta de documentacion no es la factura de la muestra. No se
# borra ni se esconde: se aparta y se dice, porque el auditor tiene que saber
# que habia. En la calibracion eran 4 justificantes de pago de 22 ficheros.
NO_FACTURA = ("JUSTIFICANTE", "ADEUDO", "RECIBO", "TRANSFERENCIA", "REMESA",
              "PAGO 1", "PAGO 2", "INDICE", "CARATULA", "ULTIMA ESCANEADA")


def _salida_utf8() -> None:
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _marcado(nombre: str) -> bool:
    """El nombre contiene alguna palabra de las que suele llevar un justificante."""
    alto = nombre.upper()
    return any(p in alto for p in NO_FACTURA)


def _grupo(nombre: str) -> str:
    """El número de orden con que el auditor encabeza los ficheros de una misma factura.

    En una carpeta de documentación los ficheros de un mismo elemento van
    numerados: «6 - X FRA F25-002 + JUSTIFICANTE PAGO.pdf» y «6 - X FRA
    F25-002.pdf» serían del mismo grupo.
    """
    cabeza = nombre.split(" - ", 1)[0].strip()
    return cabeza if cabeza.isdigit() else Path(nombre).stem.upper()


def clasificar(pdfs: list[Path]) -> tuple[list[Path], list[Path]]:
    """Reparte los PDF entre facturas y justificantes apartados.

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
    """
    facturas, apartados = [], []
    grupos: dict[str, list[Path]] = {}
    for p in pdfs:
        grupos.setdefault(_grupo(p.name), []).append(p)
    for _, ficheros in grupos.items():
        limpios = [f for f in ficheros if not _marcado(f.name)]
        for f in ficheros:
            if _marcado(f.name) and limpios:
                apartados.append(f)
            else:
                facturas.append(f)
    return sorted(facturas), sorted(apartados)


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


def inventariar(carpeta: Path, trabajo: Path) -> dict:
    todos = sorted(p for p in carpeta.rglob("*") if p.is_file())
    pdfs = [p for p in todos if p.suffix.lower() == ".pdf"]
    if not pdfs:
        raise SystemExit(f"[C] No hay ningún PDF en {carpeta}")
    # Lo que hay en la carpeta y NO es un PDF se lista, no se omite: en una
    # ejecucion real habia un fichero companero sin extension, de pocos KB, junto
    # a una factura, y nadie supo que era porque el inventario solo miraba PDF.
    # Descartar en silencio es como no haberlo visto; decir «esto tambien estaba»
    # deja al auditor decidir. Los renders propios del skill (pag/) no cuentan.
    no_pdf = [p for p in todos if p.suffix.lower() != ".pdf"]
    utiles, fuera = clasificar(pdfs)
    docs = [{"id": f"f{i:02d}", "fichero": p.name, "ruta": str(p),
             "paginas": _paginas_de(p), "imagenes": []}
            for i, p in enumerate(utiles, start=1)]
    man = {"carpeta": str(carpeta), "ppp": PPP, "documentos": docs,
           "apartados": [x.name for x in fuera],
           "no_reconocidos": [f"{x.relative_to(carpeta)} ({max(1, x.stat().st_size // 1024)} KB)" for x in no_pdf]}
    trabajo.mkdir(parents=True, exist_ok=True)
    (trabajo / "manifiesto.json").write_text(
        json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
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


def _transcritos(trabajo: Path) -> set[str]:
    """Lo ya escrito por el modelo en facturas.json: el punto de control."""
    f = trabajo / "facturas.json"
    if not f.exists():
        return set()
    try:
        d = json.loads(f.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    return {x.get("fichero") for x in d.get("facturas", []) if x.get("fichero")}


def _imagenes_abs(trabajo: Path, imagenes: list) -> list[str]:
    """Las imagenes del manifiesto con ruta absoluta. Las que hizo el MCP en el equipo del
    auditor (preparar_facturas) van con el nombre a secas, relativo al manifiesto: asi la
    misma carpeta vale en Windows y, subida, en el contenedor."""
    return [i if Path(i).is_absolute() else str(trabajo / i) for i in imagenes]


def repartir_lotes(trabajo: Path, tamano: int) -> list[dict]:
    """Los documentos pendientes de transcribir, en lotes de `tamano`.

    Es lo que se le da a cada lector: nombre de fichero e imagenes, nada mas. Solo
    los pendientes, para que una segunda pasada tras una compactacion no vuelva a
    leer lo ya transcrito. Se escribe en lotes.json para que quede constancia de
    que se lanzo.
    """
    man = _leer_manifiesto(trabajo)
    base = Path(man.get("_carpeta") or trabajo)
    hechos = _transcritos(trabajo)
    pend = [d for d in man["documentos"] if d["fichero"] not in hechos]
    lotes = []
    for i in range(0, len(pend), max(1, tamano)):
        n = len(lotes) + 1
        lotes.append({"lote": n,
                      "salida": str(trabajo / f"facturas_lote_{n}.json"),
                      "documentos": [{"fichero": d["fichero"], "imagenes": _imagenes_abs(base, d["imagenes"]),
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
    entradas de los lotes se anaden o lo sustituyen por nombre de fichero. Un
    fichero del manifiesto sin entrada es un documento que ningun lector
    transcribio; una entrada cuyo fichero no esta en el manifiesto es un lector
    que se invento un documento, y las dos cosas se dicen.
    """
    man = _leer_manifiesto(trabajo)
    conocidos = {d["fichero"] for d in man["documentos"]}
    por_fichero: dict[str, dict] = {}
    f_out = trabajo / "facturas.json"
    if f_out.exists():
        try:
            for x in json.loads(f_out.read_text(encoding="utf-8")).get("facturas", []):
                if x.get("fichero"):
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
    ap.add_argument("--ampliar", help="fichero del que hace falta otra página")
    ap.add_argument("--pagina", type=int, help="con --ampliar: qué página (por defecto, la última)")
    ap.add_argument("--lotes", type=int, metavar="N",
                    help="reparte los documentos pendientes en lotes de N para los lectores, y escribe lotes.json")
    ap.add_argument("--fusionar", action="store_true",
                    help="junta los facturas_lote_*.json de los lectores en facturas.json")
    a = ap.parse_args()
    trabajo = Path(a.trabajo)
    avisos: list[str] = []

    if a.carpeta:
        carpeta = Path(a.carpeta)
        if not carpeta.is_dir():
            print(f"[C] No existe la carpeta {carpeta}")
            return 2
        man = inventariar(carpeta, trabajo)
        print(f"Inventario: {len(man['documentos'])} documento(s) de factura en {carpeta}")
        if man.get("no_reconocidos"):
            avisos.append(f"{len(man['no_reconocidos'])} fichero(s) en la carpeta que no son PDF y no se han leído: "
                          + ", ".join(man["no_reconocidos"][:6]) + (" …" if len(man["no_reconocidos"]) > 6 else "")
                          + ". Si alguno es un documento de la muestra, conviértelo a PDF o dilo al entregar.")
        if man["apartados"]:
            avisos.append(f"{len(man['apartados'])} fichero(s) apartados por no ser facturas: "
                          + ", ".join(man["apartados"][:6])
                          + (" …" if len(man["apartados"]) > 6 else ""))
        # Primera pagina de cada uno. La ultima se pide con --ampliar cuando el
        # modelo vea que en la primera no estaban los totales.
        pag = trabajo / "pag"
        try:
            for d in man["documentos"]:
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
            json.dumps(man, ensure_ascii=False, indent=1), encoding="utf-8")
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
                  "falta con --ampliar «<fichero>» --pagina N. Obligatorio mirarlas antes de dar por "
                  "buena una diferencia de importe o un total ilegible.")

    if a.ampliar:
        man = _leer_manifiesto(trabajo)
        doc = next((d for d in man["documentos"]
                    if d["fichero"] == a.ampliar or d["id"] == a.ampliar), None)
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
                print(f"      {d['fichero']}  ->  " + ", ".join(d["imagenes"]))
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
        hechos = _transcritos(trabajo)
        pend = [d for d in man["documentos"] if d["fichero"] not in hechos]
        print(f"Transcritos {len(hechos)} de {len(man['documentos'])} documento(s).")
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
