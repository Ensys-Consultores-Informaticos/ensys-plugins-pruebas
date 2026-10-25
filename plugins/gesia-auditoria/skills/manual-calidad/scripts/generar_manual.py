# -*- coding: utf-8 -*-
"""Genera la pagina del manual de calidad de la firma (AudiQ): un unico HTML que se abre sin internet.

    python generar_manual.py --datos <carpeta> --generado <AAAA-MM-DD> --salida <carpeta de salida>

<carpeta> lleva lo que exporta el MCP (ver SKILL.md):

    manual.json       ControlEnSys x DatosAuditoria: producto, tipo de fichero, nombre, version
    areas.json        Areas
    valores_ria.json  ValoresRIA: la matriz 5x5 de probabilidad x impacto
    ejes.json         los rotulos de los dos ejes (ValoresProbabilidadRIA y ValoresImpactoRIA)
    riesgos.json      RiesgosNIAS
    referencias.json  Referencias
    guias.json        DetalleGuias: el texto de los procedimientos y la lista de plantillas
    vinculos.json     exportar_consulta(entidad='vinculos'): ruta, si existe y el valor original

Tres bloques: el mapa de los riesgos de nivel medio, alto y extremo; las plantillas que cita cada
procedimiento; y el texto de cada procedimiento, legible. Lo no disponible no sale. Diseño y
decisiones en DISENO.md.

Antes de escribir nada se verifica el contrato de datos (verificar): si el fichero no es un manual
de AudiQ, o la matriz no es la que se espera, o un nivel guardado no casa con la matriz, no se
escribe la pagina. Nada lee el reloj: la fecha de generacion la pone quien llama.
Salida 0 = escrito; 2 = falta un fichero, no tiene la forma esperada o no cumple el contrato.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

FICHEROS = ("manual", "areas", "valores_ria", "ejes", "riesgos", "referencias", "guias", "vinculos")

# Las columnas que cada fichero tiene que traer. Faltar una es un contrato roto, no un dato vacio.
COLUMNAS = {
    "manual": {"Proyecto", "TipoMDB", "NombreFichero", "Version", "FechaPublicacion",
               "HipervinculosRelativos", "CodigoTipoFichero"},
    "areas": {"CodigoArea", "Area"},
    "valores_ria": {"CodigoRIA", "CodigoValorRIA", "ValorRIA"},
    "ejes": {"Eje", "CodigoValorRIA", "ValorRIA"},
    "riesgos": {"IdRiesgo", "Riesgo", "CodigoTipoRiesgo", "CodigoArea", "CodigoReferencia",
                "CodigoValorRIA_RCI", "CodigoValorRIA_RI", "CodigoValorRIA_RIM",
                "Descripcion", "Procedimientos", "Recomendacion"},
    "referencias": {"CodigoReferencia", "CodigoArea", "Referencia", "CodigoTipoGuia", "Disponible",
                    "Comentario"},
    "guias": {"CodigoGuia", "CodigoOrden", "Punto", "DesglosePunto", "CodigoReferencia",
              "Descripcion", "FicheroVinculado"},
    # Bruto llega con el MCP 1.27.0: sin el no hay forma de casar cada plantilla con su vinculo
    "vinculos": {"Tabla", "Clave", "Campo", "Tipo", "Ruta", "Existe", "Bruto"},
}

# Solo salen los riesgos desde el nivel medio (decision del 23/10/2026: medio, alto y extremo).
# El umbral se comprueba por la etiqueta de ValoresRIA, no se da por bueno el numero.
NIVEL_MINIMO = 3
ETIQUETAS_NIVEL = {3: "medio", 4: "alto", 5: "extremo"}

# CodigoTipoFichero de DatosAuditoria: 1 = Manual, 2 = Registro de Calidad, 3 = Encargo de Auditoria
TIPO_MANUAL = "1"

# CodigoTipoRiesgo no tiene tabla de codigos en el fichero; los nombres salen de la linea de
# filtros del informe de AudiQ (docs/esquema-audiq.md).
TIPO_RIESGO = {"1": "Riesgo de O.I.", "2": "Riesgo de calidad"}

# La pagina se escribe en <carpeta del manual>\AsistenteIA\ManualCalidad\, dos niveles por debajo
# de la carpeta respecto a la que AudiQ guarda los vinculos relativos. Si la regla 10 del repo
# cambia de profundidad, esto cambia con ella.
PREFIJO_RELATIVO = "../../"

# Lo que el barrido del MCP pone en lugar de un identificador. Se cuenta para decirlo al entregar:
# en un manual suele ser el NIF de la propia firma.
MARCA_BARRIDO = re.compile(r"\[(TBAI|IBAN|VAT-UK|SORT-CODE|CUENTA-BANCARIA|TARJETA|NIE|DNI|CIF|MATRÍCULA|TEL|EMAIL)\]")

# Cuantos casos se nombran en un aviso: el resumen de pantalla es lo que el modelo cuenta al
# entregar, y una lista larga ya no se lee; el resto se resume con «...».
MAX_LISTA = 12

# Un codigo citado en el texto: C)AQ/04, AG)00/01, E)01/05.IT02, D)AQ. Sensible a mayusculas a
# proposito: «aquellos» no es un codigo. La barra en lugar del parentesis (C/AQ/19) esta grabada
# asi en algun manual y se acepta.
CODIGO = re.compile(r"(?<![A-Za-z0-9])([A-Z]{1,2})[)/]((?:AQ|\d{2})(?:/\d{2}(?:\.IT\d{2})?)?)(?![0-9A-Za-z])")


def _salida_utf8() -> None:
    for f in (sys.stdout, sys.stderr):
        try:
            f.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def texto(v) -> str:
    return "" if v is None else str(v).strip()


def entero(v):
    s = texto(v)
    return int(s) if re.fullmatch(r"-?\d+", s) else None


def booleano(v) -> bool:
    return texto(v).lower() in ("true", "1", "-1", "si", "sí")


def normalizar_codigo(c: str) -> str:
    """'C/AQ/19 ' -> 'C)AQ/19'. Los codigos llegan con espacio final y alguno con barra."""
    return re.sub(r"^([A-Z]{1,2})/", r"\1)", texto(c))


def _sin_acentos(s: str) -> str:
    return "".join(ch for ch in unicodedata.normalize("NFD", s) if unicodedata.category(ch) != "Mn").lower()


# ── Carga y contrato ──────────────────────────────────────────────────────────

def cargar(carpeta: Path) -> tuple[dict, list[str]]:
    datos, defectos = {}, []
    for nombre in FICHEROS:
        ruta = carpeta / f"{nombre}.json"
        if not ruta.exists():
            defectos.append(f"falta {ruta.name}")
            continue
        try:
            filas = json.loads(ruta.read_text(encoding="utf-8-sig"))
        except ValueError as exc:
            defectos.append(f"{ruta.name} no es JSON: {exc}")
            continue
        if not isinstance(filas, list) or (filas and not isinstance(filas[0], dict)):
            defectos.append(f"{ruta.name} tiene que ser una lista de filas")
            continue
        faltan = COLUMNAS[nombre] - set(filas[0]) if filas else set()
        if faltan:
            extra = " (hace falta el MCP 1.27.0 o posterior)" if "Bruto" in faltan else ""
            defectos.append(f"{ruta.name} no trae {', '.join(sorted(faltan))}{extra}")
            continue
        datos[nombre] = filas
    return datos, defectos


def verificar(datos: dict) -> list[str]:
    """El contrato de datos, comprobado en ejecucion. Cada linea devuelta es un motivo para NO
    escribir la pagina: un mapa bonito sobre datos mal entendidos es peor que ningun mapa."""
    rotos = []

    m = datos["manual"][0] if datos["manual"] else {}
    if texto(m.get("Proyecto")).lower() != "audiq" or texto(m.get("TipoMDB")).lower() not in ("qat", "qal"):
        rotos.append(f"no es un fichero de AudiQ (ControlEnSys dice {texto(m.get('Proyecto'))!r} / "
                     f"{texto(m.get('TipoMDB'))!r})")
    elif texto(m.get("CodigoTipoFichero")) != TIPO_MANUAL:
        rotos.append(f"no es un manual de calidad: CodigoTipoFichero = {texto(m.get('CodigoTipoFichero'))!r} "
                     "(2 es un registro de calidad, 3 un encargo)")

    # La matriz: 25 casillas, CodigoRIA = probabilidad*10 + impacto, cada nivel con una sola etiqueta
    casillas = {entero(f.get("CodigoRIA")): f for f in datos["valores_ria"]}
    esperadas = {p * 10 + i for p in range(1, 6) for i in range(1, 6)}
    if set(casillas) != esperadas:
        rotos.append(f"la matriz de riesgo no es la 5x5 esperada: casillas {sorted(k for k in casillas if k is not None)}")
    etiquetas = defaultdict(set)
    for f in datos["valores_ria"]:
        etiquetas[entero(f.get("CodigoValorRIA"))].add(texto(f.get("ValorRIA")))
    for nivel, nombre in ETIQUETAS_NIVEL.items():
        if {_sin_acentos(e) for e in etiquetas.get(nivel, set())} != {nombre}:
            rotos.append(f"el nivel {nivel} de la matriz no se llama «{nombre}» sino {sorted(etiquetas.get(nivel, set()))}: "
                         "el umbral de medio, alto y extremo no se puede aplicar a ciegas")

    ejes = defaultdict(set)
    for f in datos["ejes"]:
        ejes[texto(f.get("Eje"))].add(entero(f.get("CodigoValorRIA")))
    if ejes.get("P") != set(range(1, 6)) or ejes.get("I") != set(range(1, 6)):
        rotos.append("los ejes de probabilidad e impacto no traen los cinco valores")

    # AudiQ recalcula el nivel guardado al cambiar la matriz (23/10/2026), asi que tienen que casar
    if not rotos:
        for r in datos["riesgos"]:
            p, i, g = entero(r.get("CodigoValorRIA_RCI")), entero(r.get("CodigoValorRIA_RI")), entero(r.get("CodigoValorRIA_RIM"))
            if p is None and i is None:
                continue
            if p not in range(1, 6) or i not in range(1, 6):
                rotos.append(f"riesgo {texto(r.get('IdRiesgo'))}: probabilidad {p} o impacto {i} fuera de 1-5")
                continue
            calculado = entero(casillas[p * 10 + i].get("CodigoValorRIA"))
            if g != calculado:
                rotos.append(f"riesgo {texto(r.get('IdRiesgo'))}: el nivel guardado ({g}) no es el de la matriz "
                             f"({calculado}); AudiQ lo recalcula solo, asi que el fichero esta dañado o tocado a mano")
    return rotos


# ── El modelo de la pagina ────────────────────────────────────────────────────

def _enlace(bruto: str, relativos: bool) -> str:
    """El href de un vinculo, relativo a la pagina. Una URL se deja tal cual."""
    v = bruto.strip()
    if re.match(r"^(https?|mailto|ftp)://", v, re.I) or v.lower().startswith("mailto:"):
        return v
    if v.lower().startswith("file:"):
        v = v[5:].strip()
    v = v.replace("\\", "/")
    if re.match(r"^[A-Za-z]:/", v) or v.startswith("//"):
        return "file:///" + quote(v.lstrip("/"), safe="/:")
    if not relativos:
        # la casilla de AudiQ dice que no son relativos, pero el valor no lleva unidad: se resuelve
        # igual contra la carpeta del manual, que es lo unico que tiene sentido
        pass
    return PREFIJO_RELATIVO + quote(v, safe="/")


def _relativa(bruto: str) -> str | None:
    """La ruta relativa de un vinculo 'file:', con barras invertidas; None si es absoluta o URL."""
    v = bruto.strip()
    if not v.lower().startswith("file:"):
        return None
    v = v[5:].strip().replace("/", "\\")
    if re.match(r"^[A-Za-z]:\\", v) or v.startswith("\\\\"):
        return None
    return v


def carpeta_manual(vinculos: list, campo: str = "Ruta") -> str | None:
    """La carpeta del manual en el equipo de la firma, deducida de los vinculos: el MCP da la ruta
    absoluta ya resuelta (Ruta) y el valor original relativo (Bruto), y la carpeta es lo que sobra
    por delante. Se queda con la que mas vinculos dan; None si ninguno es relativo.

    Con campo='RutaRed' (MCP 1.27.1) sale la misma carpeta en forma de red, «\\\\servidor\\...»,
    cuando el manual esta en una unidad mapeada: la letra («F:») cambia de un usuario a otro y la
    ruta de red no (David, 25/10/2026)."""
    cuenta: dict = defaultdict(int)
    for v in vinculos:
        if texto(v.get("Tipo")) != "fichero":
            continue
        rel = _relativa(texto(v.get("Bruto")))
        ruta = texto(v.get(campo)).replace("/", "\\")
        if rel and ruta.lower().endswith("\\" + rel.lower()):
            cuenta[ruta[: len(ruta) - len(rel) - 1]] += 1
    return max(cuenta, key=cuenta.get) if cuenta else None


def _enlace_absoluto(base: str, bruto: str) -> str:
    """El mismo vinculo, con la ruta completa: la reserva cuando la pagina no esta en su sitio."""
    rel = _relativa(bruto)
    if not base or not rel:
        return ""
    ruta = (base.rstrip("\\") + "\\" + rel).replace("\\", "/")
    if ruta.startswith("//"):
        return "file:" + quote(ruta, safe="/:")
    return "file:///" + quote(ruta, safe="/:")


def _nombre_fichero(bruto: str) -> str:
    v = re.sub(r"^file:", "", bruto.strip(), flags=re.I).replace("\\", "/")
    return v.rsplit("/", 1)[-1] or v


def _vinculo(bruto: str, vinculos: dict, tabla: str, clave: str, relativos: bool, base: str | None) -> dict | None:
    b = texto(bruto)
    if not b:
        return None
    v = vinculos.get((tabla, clave, b))
    nombre = _nombre_fichero(b)
    ext = nombre.rsplit(".", 1)[-1].lower() if "." in nombre else ""
    if v is None:
        # el MCP no lo ha visto: no se afirma ni que existe ni que no
        return {"href": _enlace(b, relativos), "abs": _enlace_absoluto(base, b), "nombre": nombre, "ext": ext,
                "estado": "sin-comprobar"}
    if v["Tipo"] == "url":
        return {"href": b, "abs": "", "nombre": b, "ext": "web", "estado": "url"}
    if v["Existe"] is True or texto(v["Existe"]).lower() == "true":
        return {"href": _enlace(b, relativos), "abs": _enlace_absoluto(base, b), "nombre": nombre, "ext": ext,
                "estado": "ok"}
    return {"href": "", "abs": "", "nombre": nombre, "ext": ext, "estado": "roto", "ruta": texto(v.get("Ruta"))}


def preparar(datos: dict, generado: str = "") -> tuple[dict, list[str]]:
    """Lo que la pagina necesita, ya convertido. Devuelve (modelo, avisos)."""
    avisos = []
    m = datos["manual"][0]
    relativos = booleano(m.get("HipervinculosRelativos"))
    # la reserva de los enlaces cuando la pagina no esta en su sitio (registro de Cowork, 24/10/2026:
    # se dejo un nivel por encima y ninguna plantilla abria). Mejor en forma de red, que vale para
    # cualquier usuario; si el manual no esta en una unidad mapeada, la ruta tal cual
    base = carpeta_manual(datos["vinculos"], "RutaRed") or carpeta_manual(datos["vinculos"])

    areas = {texto(a["CodigoArea"]): texto(a["Area"]) for a in datos["areas"]}

    vinculos = {}
    for v in datos["vinculos"]:
        vinculos[(texto(v["Tabla"]), texto(v["Clave"]), texto(v["Bruto"]))] = v

    refs = {texto(r["CodigoReferencia"]): r for r in datos["referencias"]}
    disponibles = {c for c, r in refs.items() if booleano(r.get("Disponible"))}
    procs = sorted(c for c in disponibles if texto(refs[c].get("CodigoTipoGuia")) == "PR")
    colecciones = sorted(c for c in disponibles if texto(refs[c].get("CodigoTipoGuia")) == "F")

    por_guia = defaultdict(list)
    for f in datos["guias"]:
        por_guia[texto(f["CodigoGuia"])].append(f)
    for filas in por_guia.values():
        filas.sort(key=lambda f: entero(f.get("CodigoOrden")) or 0)

    # Plantillas: las filas con codigo de las guias de las referencias de formatos (X)AQ). Un punto
    # sin desglose es un titulo de bloque («MANUAL DE PROCEDIMIENTOS»).
    plantillas = {}
    for col in colecciones:
        bloque = ""
        for f in por_guia.get(col, []):
            cod = normalizar_codigo(f.get("CodigoReferencia"))
            if not cod:
                if not texto(f.get("DesglosePunto")):
                    bloque = texto(f.get("Descripcion"))
                continue
            plantillas[cod] = {
                "codigo": cod, "nombre": texto(f.get("Descripcion")), "area": texto(refs[col].get("CodigoArea")),
                "coleccion": col, "bloque": bloque,
                "fichero": _vinculo(f.get("FicheroVinculado"), vinculos, "DetalleGuias", col, relativos, base),
                "citada_por": [],
            }

    # coleccion de plantillas de cada area, para enlazar «ver D)AQ»
    coleccion_area = {texto(refs[c].get("CodigoArea")): c for c in colecciones if c.endswith(")AQ")}

    # citas que parecen de una plantilla y no casan con ninguna: «AQ)03» por «F)AQ/03». El dato se
    # corrige en AudiQ; aqui solo se cuentan (registro de Cowork, 24/10/2026)
    dudosas: list = []

    def enlazar(html: str, propio: str, citas: set) -> str:
        def sustituir(mt):
            cod = f"{mt.group(1)}){mt.group(2)}"
            if "AQ" in cod and cod not in plantillas and cod not in colecciones and (propio, cod) not in dudosas:
                dudosas.append((propio, cod))
            if cod in plantillas:
                citas.add(cod)
                # quien lee el procedimiento quiere la plantilla, no ir a buscarla: si el fichero
                # esta, el codigo lo abre; si no, lleva a su fila, que dice por que no se abre
                f = plantillas[cod]["fichero"]
                if f and f["estado"] in ("ok", "url", "sin-comprobar"):
                    reserva = f' data-abs="{_esc(f["abs"])}"' if f.get("abs") else ""
                    return (f'<a class="cod plt" href="{_esc(f["href"])}"{reserva} target="_blank" rel="noopener" '
                            f'title="{_esc(f["nombre"])}">{mt.group(0)}</a>')
                return f'<a class="cod" href="#plantilla/{quote(cod, safe="")}">{mt.group(0)}</a>'
            if cod in procs and cod != propio:
                return f'<a class="cod prc" href="#p/{quote(cod, safe="")}">{mt.group(0)}</a>'
            if cod in colecciones:
                return f'<a class="cod col" href="#plantillas/{quote(texto(refs[cod].get("CodigoArea")), safe="")}">{mt.group(0)}</a>'
            return mt.group(0)
        return CODIGO.sub(sustituir, html)

    procedimientos = []
    sin_texto = []
    for c in procs:
        r = refs[c]
        citas: set = set()
        filas = por_guia.get(c, [])
        cuerpo = guia_a_html(filas, lambda h: enlazar(h, c, citas))
        resumen_ref = texto_a_html(texto(r.get("Comentario")), lambda h: enlazar(h, c, citas))
        if not filas:
            sin_texto.append(c)
        diagramas = []
        for campo in ("FicheroVinculado1", "FicheroVinculado2", "FicheroVinculado3", "FicheroVinculado4"):
            for v in datos["vinculos"]:
                if texto(v["Tabla"]) == "Referencias" and texto(v["Clave"]) == c and texto(v["Campo"]) == campo:
                    d = _vinculo(v["Bruto"], vinculos, "Referencias", c, relativos, base)
                    if d:
                        diagramas.append(d)
        for cod in citas:
            plantillas[cod]["citada_por"].append(c)
        procedimientos.append({
            "codigo": c, "titulo": texto(r.get("Referencia")), "area": texto(r.get("CodigoArea")),
            "cuerpo": cuerpo, "resumen": resumen_ref, "diagramas": diagramas,
            "plantillas": sorted(citas),
        })
    if sin_texto:
        avisos.append(f"{len(sin_texto)} procedimiento(s) sin texto en su guia, salen solo con el resumen: {', '.join(sin_texto)}")
    if dudosas:
        def pista(propio: str, cod: str) -> str:
            m_ = re.fullmatch(r"AQ\)(\d{2})", cod)
            area = texto(refs[propio].get("CodigoArea"))
            candidata = f"{area})AQ/{m_.group(1)}" if m_ else ""
            return f"{propio} cita «{cod}»" + (f" (¿{candidata}?)" if candidata in plantillas else "")
        avisos.append(f"{len(dudosas)} cita(s) con aspecto de codigo de plantilla que no casan con ninguna, se quedan "
                      "como texto (se corrigen en AudiQ): " + "; ".join(pista(p, c) for p, c in dudosas[:MAX_LISTA])
                      + (" ..." if len(dudosas) > MAX_LISTA else ""))

    # El indice de la pestaña Plantillas: TODOS los procedimientos disponibles de cada area, citen
    # plantillas o no -las plantillas son accesorias: la pestaña es el indice del manual (registro
    # de Cowork, 24/10/2026)-, y al final las plantillas del area que no cita nadie. Una plantilla
    # sale bajo cada procedimiento que la cita, sea del area que sea.
    citadas = {c for p in procedimientos for c in p["plantillas"]}
    indice = []
    for area in sorted({p["area"] for p in procedimientos} | {p["area"] for p in plantillas.values()}):
        indice.append({
            "area": area,
            "procedimientos": [{"codigo": p["codigo"], "titulo": p["titulo"], "plantillas": p["plantillas"]}
                               for p in procedimientos if p["area"] == area],
            "otras": sorted(c for c, p in plantillas.items() if p["area"] == area and c not in citadas),
        })
    sin_plantillas = [p["codigo"] for p in procedimientos if not p["plantillas"]]

    # Riesgos: los valorados de nivel medio o superior. Lo sin valorar no sale, y se cuenta.
    casillas = {entero(f["CodigoRIA"]): f for f in datos["valores_ria"]}
    niveles = {}
    for f in datos["valores_ria"]:
        niveles[entero(f["CodigoValorRIA"])] = texto(f["ValorRIA"])
    ejes = {"P": {}, "I": {}}
    for f in datos["ejes"]:
        ejes[texto(f["Eje"])][entero(f["CodigoValorRIA"])] = texto(f["ValorRIA"])

    riesgos, sin_valorar, por_nivel = [], 0, defaultdict(int)
    enlace_perdido = 0
    for r in datos["riesgos"]:
        p, i = entero(r.get("CodigoValorRIA_RCI")), entero(r.get("CodigoValorRIA_RI"))
        if p is None or i is None:
            sin_valorar += 1
            continue
        nivel = entero(casillas[p * 10 + i]["CodigoValorRIA"])
        por_nivel[nivel] += 1
        if nivel < NIVEL_MINIMO:
            continue
        ref = normalizar_codigo(r.get("CodigoReferencia"))
        destino = None
        if ref in procs:
            destino = {"tipo": "p", "codigo": ref, "titulo": texto(refs[ref].get("Referencia"))}
        elif ref in colecciones:
            destino = {"tipo": "plantillas", "codigo": ref, "area": texto(refs[ref].get("CodigoArea")),
                       "titulo": texto(refs[ref].get("Referencia"))}
        elif ref:
            enlace_perdido += 1
        nada = lambda h: h
        riesgos.append({
            "id": entero(r.get("IdRiesgo")), "riesgo": texto(r.get("Riesgo")),
            "tipo": TIPO_RIESGO.get(texto(r.get("CodigoTipoRiesgo")), ""), "area": texto(r.get("CodigoArea")),
            "p": p, "i": i, "nivel": nivel,
            "descripcion": texto_a_html(texto(r.get("Descripcion")), nada),
            "respuesta": texto_a_html(texto(r.get("Procedimientos")), nada),
            "recomendacion": texto_a_html(texto(r.get("Recomendacion")), nada),
            "destino": destino,
        })
    riesgos.sort(key=lambda x: (-x["nivel"], -x["p"], -x["i"], x["id"] or 0))
    if not riesgos:
        avisos.append("ningun riesgo valorado de nivel medio o superior: el mapa sale vacio")
    if sin_valorar:
        avisos.append(f"{sin_valorar} riesgo(s) sin valorar: no salen en el mapa")
    if enlace_perdido:
        avisos.append(f"{enlace_perdido} riesgo(s) apuntan a una referencia no disponible o que no existe: salen sin enlace")

    lista_plantillas = sorted(plantillas.values(), key=lambda x: (x["area"], x["codigo"]))
    rotas = [p["codigo"] for p in lista_plantillas if p["fichero"] and p["fichero"]["estado"] == "roto"]
    rotos_diag = [p["codigo"] for p in procedimientos for d in p["diagramas"] if d["estado"] == "roto"]
    sin_fichero = [p["codigo"] for p in lista_plantillas if not p["fichero"]]
    if rotas:
        avisos.append(f"{len(rotas)} plantilla(s) con el fichero vinculado que no se encuentra: {', '.join(rotas)}")
    if rotos_diag:
        avisos.append(f"{len(rotos_diag)} diagrama(s) de procedimiento que no se encuentran: {', '.join(rotos_diag)}")

    barridos = sum(len(MARCA_BARRIDO.findall(json.dumps(datos[n], ensure_ascii=False)))
                   for n in ("riesgos", "referencias", "guias"))
    if barridos:
        avisos.append(f"{barridos} identificador(es) tapado(s) en los textos (salen como [CIF], [TEL]...): "
                      "la exportacion los enmascara siempre, y en un manual suele ser el NIF o el telefono de la firma")

    fecha = texto(m.get("FechaPublicacion")).split()[0] if texto(m.get("FechaPublicacion")) else ""
    mt = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2})", fecha)
    if mt:
        fecha = f"{int(mt.group(1)):02d}/{int(mt.group(2)):02d}/20{mt.group(3)}"
    # una fecha de publicacion por delante de hoy puede ser a proposito -se graba con antelacion-,
    # pero el usuario tiene que saberlo (registro de Cowork, 24/10/2026: publicado el 26/10)
    mf, mg = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", fecha), re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", generado)
    if mf and mg and (mf.group(3), mf.group(2), mf.group(1)) > mg.groups():
        avisos.append(f"la fecha de publicacion del manual ({fecha}) es posterior a la de hoy "
                      f"({mg.group(3)}/{mg.group(2)}/{mg.group(1)}): se grabo con antelacion o esta mal en AudiQ")

    # La version sin su «v»: hay manuales que la graban como «V1.2», y el nombre de la pagina y el
    # subtitulo ya la ponen (registro de Cowork, 24/10/2026: salio «… vV1.2.html»). Y si el nombre del
    # manual lleva otra version distinta, se dice: el mismo manual decia «V1.14» en el nombre y
    # «V1.2» en la version.
    version = re.sub(r"^[vV]\s*", "", texto(m.get("Version")))
    en_nombre = re.findall(r"\b[vV]\s*(\d+(?:\.\d+)*)\b", texto(m.get("NombreFichero")))
    if version and en_nombre and version not in en_nombre:
        avisos.append(f"el nombre del manual dice version {en_nombre[-1]} y el campo Version de AudiQ dice {version}: "
                      "se corrige en AudiQ")

    usadas = sorted({x["area"] for x in procedimientos} | {x["area"] for x in riesgos} | {x["area"] for x in lista_plantillas})
    modelo = {
        "manual": texto(m.get("NombreFichero")), "version": version, "publicado": fecha,
        "carpeta_manual": base or "",
        "areas": [{"codigo": a, "area": areas.get(a, a)} for a in usadas],
        "niveles": {str(k): v for k, v in niveles.items()},
        "ejes": {e: {str(k): v for k, v in d.items()} for e, d in ejes.items()},
        "matriz": {str(k): entero(f["CodigoValorRIA"]) for k, f in casillas.items()},
        "riesgos": riesgos,
        "procedimientos": procedimientos,
        "plantillas": lista_plantillas,
        "colecciones": {a: c for a, c in coleccion_area.items()},
        "indice": indice,
        "cuentas": {"por_nivel": {str(k): v for k, v in sorted(por_nivel.items())}, "sin_valorar": sin_valorar,
                    "rotas": len(rotas), "sin_fichero": sin_fichero, "sin_plantillas": sin_plantillas},
    }
    return modelo, avisos


# ── Texto plano de AudiQ a HTML ───────────────────────────────────────────────
# Los campos memo son texto plano: saltos \r\n, tabuladores, listas con guion o con «a)», «1)»,
# y titulillos en mayusculas en una linea sola. Se convierte sin inventar estructura: lo que no
# encaja en una de esas formas queda como parrafo con sus saltos de linea.

VINETA = re.compile(r"^[-•·*]\s*")

# Un punto sin desglose que no va en mayusculas solo se toma por titulo si es una linea corta.
# En el manual de calibracion los titulos de una linea llegan a 144 caracteres («HECHOS
# DESCUBIERTOS DESPUES DE LA FECHA...»), todos en mayusculas; uno en minusculas mas largo que esto
# es un parrafo, y como titulo saldria entero en mayusculas.
LARGO_MAXIMO_TITULO = 150
ORDINAL = re.compile(r"^(\(?[a-zñ]\)|\d{1,2}[.)]|[ivx]{1,4}\))\s+")


def _es_titulillo(s: str) -> bool:
    letras = [ch for ch in s if ch.isalpha()]
    return 4 <= len(s) <= 90 and len(letras) >= 4 and all(ch.isupper() for ch in letras)


def _esc(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def texto_a_html(t: str, enlazar) -> str:
    if not t:
        return ""
    lineas = t.replace("\t", " ").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, parrafo, items, tipo_lista = [], [], [], ""

    def cerrar_parrafo():
        if parrafo:
            out.append("<p>" + "<br>".join(parrafo) + "</p>")
            parrafo.clear()

    def cerrar_lista():
        nonlocal tipo_lista
        if items:
            out.append(f'<ul class="{tipo_lista}">' + "".join(f"<li>{x}</li>" for x in items) + "</ul>")
            items.clear()
        tipo_lista = ""

    for ln in lineas:
        s = re.sub(r"\s+", " ", ln).strip()
        if not s:
            cerrar_parrafo()
            cerrar_lista()
            continue
        h = enlazar(_esc(s))
        mv, mo = VINETA.match(s), ORDINAL.match(s)
        if mv and len(s) > len(mv.group(0)):
            cerrar_parrafo()
            if tipo_lista != "vin":
                cerrar_lista()
                tipo_lista = "vin"
            items.append(enlazar(_esc(s[mv.end():])))
        elif mo:
            cerrar_parrafo()
            if tipo_lista != "ord":
                cerrar_lista()
                tipo_lista = "ord"
            items.append(f'<span class="m">{_esc(mo.group(1))}</span> ' + enlazar(_esc(s[mo.end():])))
        elif _es_titulillo(s) and not parrafo:
            cerrar_lista()
            out.append(f"<h4>{h}</h4>")
        elif items:
            # una linea sin marca justo debajo de un punto de lista lo continua
            items[-1] += "<br>" + h
        else:
            parrafo.append(h)
    cerrar_parrafo()
    cerrar_lista()
    return "".join(out)


def _todo_mayusculas(s: str) -> bool:
    letras = [ch for ch in s if ch.isalpha()]
    return len(letras) >= 3 and all(ch.isupper() for ch in letras)


def guia_a_html(filas: list, enlazar) -> str:
    """La guia de un procedimiento: un punto sin desglose es un titulo; con desglose, su texto.

    Pero un punto sin desglose puede traer el titulo Y el texto en el mismo campo: «RECURSOS
    INTELECTUALES», linea en blanco y 3.700 caracteres de texto. Pasa en el manual real (11 puntos
    en el de calibracion, 24/10/2026), y pintarlo entero como titulo dejaba parrafos enteros en
    mayusculas. Por eso: si la primera linea va en mayusculas, ella es el titulo y lo demas es
    texto; si no, el punto solo es titulo cuando es una linea corta, y si no, es texto.
    """
    out = []
    for f in filas:
        d = texto(f.get("Descripcion"))
        if not d:
            continue
        if texto(f.get("DesglosePunto")):
            out.append(texto_a_html(d, enlazar))
            continue
        primera, _, resto = d.replace("\r\n", "\n").replace("\r", "\n").partition("\n")
        primera = re.sub(r"\s+", " ", primera).strip()
        if _todo_mayusculas(primera):
            out.append(f"<h3>{enlazar(_esc(primera))}</h3>")
            if resto.strip():
                out.append(texto_a_html(resto, enlazar))
        elif not resto.strip() and len(primera) <= LARGO_MAXIMO_TITULO:
            out.append(f"<h3>{enlazar(_esc(primera))}</h3>")
        else:
            out.append(texto_a_html(d, enlazar))
    return "".join(out)


# ── Salida ────────────────────────────────────────────────────────────────────

def resumen(modelo: dict) -> list[str]:
    """Lo que el modelo cuenta al entregar."""
    c = modelo["cuentas"]
    nv = modelo["niveles"]
    altos = [f"{nv.get(k, k)} {c['por_nivel'].get(k, 0)}" for k in ("5", "4", "3")]
    pl = modelo["plantillas"]
    citadas = sum(1 for p in pl if p["citada_por"])
    return [
        f"manual: {modelo['manual']} · version {modelo['version']} · publicado {modelo['publicado']}",
        f"riesgos en el mapa: {len(modelo['riesgos'])} ({', '.join(altos)}) · sin valorar: {c['sin_valorar']}",
        f"procedimientos disponibles: {len(modelo['procedimientos'])} · sin plantillas citadas "
        f"{len(c['sin_plantillas'])} (salen igual en el indice de Plantillas)",
        f"plantillas: {len(pl)} · citadas por algun procedimiento {citadas} · el resto, en «otras del area» · "
        f"sin fichero {len(c['sin_fichero'])} · rotas {c['rotas']}",
    ]


def nombre_pagina(modelo: dict) -> str:
    """El nombre del fichero: el del manual tal como lo pone AudiQ, sin version (David,
    25/10/2026). Asi rehacer la pagina pisa la anterior; un .qat ni siquiera lleva version, solo el
    .qal. Sin los caracteres que Windows no admite: el nombre de un manual real lleva «ISO9001:2015»."""
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "-", modelo["manual"] or "Manual de calidad").strip(" .-") + ".html"


def escribir(modelo: dict, generado: str, salida: Path) -> None:
    datos = json.dumps(modelo, ensure_ascii=False, allow_nan=False).replace("</", "<\\/")
    titulo = f"Manual de calidad · {modelo['manual']}"
    html = (PLANTILLA.replace("{{TITULO}}", _esc(titulo)).replace("{{GENERADO}}", _esc(generado))
            .replace("{{DATOS}}", datos))
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(html, encoding="utf-8")


def main(argv=None) -> int:
    _salida_utf8()
    p = argparse.ArgumentParser(description="Manual de calidad de la firma (AudiQ), en un HTML")
    p.add_argument("--datos", required=True, help="carpeta con los ocho .json exportados")
    p.add_argument("--generado", required=True, help="fecha de hoy, AAAA-MM-DD: la pone quien llama")
    p.add_argument("--salida", required=True,
                   help="la carpeta donde se escribe; el nombre lo pone el script a partir del manual. "
                        "Si termina en .html, se usa tal cual")
    a = p.parse_args(argv)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", a.generado):
        print("ERROR: --generado tiene que ser AAAA-MM-DD")
        return 2
    datos, defectos = cargar(Path(a.datos))
    if not defectos:
        defectos = verificar(datos)
    if defectos:
        print("NO SE ESCRIBE LA PAGINA:")
        for d in defectos[:20]:
            print("   - " + d)
        if len(defectos) > 20:
            print(f"   ... y {len(defectos) - 20} mas")
        return 2
    modelo, avisos = preparar(datos, a.generado)
    salida = Path(a.salida)
    if salida.suffix.lower() != ".html":
        salida = salida / nombre_pagina(modelo)
    try:
        escribir(modelo, a.generado, salida)
    except PermissionError:
        print("ERROR: no se puede escribir " + str(salida))
        print("       O esta abierto (cierralo y repite), o el entorno no tiene permiso para escribir en")
        print("       esa carpeta (pide el permiso y repite).")
        return 2
    print("Pagina escrita: " + str(salida))
    print("  nombre: " + salida.name)
    for linea in resumen(modelo):
        print("  " + linea)
    if avisos:
        print("PARA CONTAR AL ENTREGAR:")
        for av in avisos:
            print("  AVISO · " + av)
    return 0


# ── La pagina ─────────────────────────────────────────────────────────────────
# Una sola, sin recursos externos: se abre desde el disco de la firma y tiene que funcionar sin
# internet. Los colores de nivel son propios, no los de la matriz de AudiQ: su verde y su amarillo
# puros dejan ilegible cualquier texto encima.
PLANTILLA = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{{TITULO}}</title>
<style>
:root {
  --marca: #1d4f73; --marca-2: #2c6a96; --marca-suave: #e6eef5; --marca-tenue: #a9c2d8;
  --bg: #f5f6f8; --panel: #ffffff; --fg: #1b2129; --muted: #5f6873; --line: #e1e5ea; --chip: #eef1f4;
  --n1: #e9ecef; --n2: #e9ecef; --n3: #f6d58a; --n4: #f0a35e; --n5: #d9534f;
  --n3-fg: #4a3500; --n4-fg: #4a2100; --n5-fg: #ffffff; --nbaja-fg: #8a929b;
  --rojo: #b42318; --ambar: #9a5b00;
  --cab-fg: #ffffff; --cab-muted: #c9dbea;
  color-scheme: light;
}
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --marca: #8fbce0; --marca-2: #a9cdea; --marca-suave: #1d2a35; --marca-tenue: #3c5a73;
    --bg: #12161b; --panel: #1a1f26; --fg: #e8ecf0; --muted: #9aa4ae; --line: #2a313a; --chip: #232a33;
    --n1: #252b33; --n2: #252b33; --n3: #8a6a1f; --n4: #9a5326; --n5: #a8332f;
    --n3-fg: #fff3d6; --n4-fg: #ffe6d6; --n5-fg: #ffffff; --nbaja-fg: #6f7882;
    --rojo: #f0857a; --ambar: #e8b25c;
    color-scheme: dark;
  }
}
:root[data-theme="dark"] {
  --marca: #8fbce0; --marca-2: #a9cdea; --marca-suave: #1d2a35; --marca-tenue: #3c5a73;
  --bg: #12161b; --panel: #1a1f26; --fg: #e8ecf0; --muted: #9aa4ae; --line: #2a313a; --chip: #232a33;
  --n1: #252b33; --n2: #252b33; --n3: #8a6a1f; --n4: #9a5326; --n5: #a8332f;
  --n3-fg: #fff3d6; --n4-fg: #ffe6d6; --n5-fg: #ffffff; --nbaja-fg: #6f7882;
  --rojo: #f0857a; --ambar: #e8b25c;
  color-scheme: dark;
}
* { box-sizing: border-box; }
body { margin: 0; background: var(--bg); color: var(--fg);
  font: 14px/1.55 "Segoe UI Variable Text", "Segoe UI", system-ui, -apple-system, Arial, sans-serif; }
header.cab { background: #1d4f73; color: var(--cab-fg); }
.cab .dentro { max-width: 1180px; margin: 0 auto; padding: 18px 24px; display: flex; gap: 16px; align-items: center; flex-wrap: wrap; }
.cab .logo { width: 44px; height: 44px; flex: none; }
.cab .textos { flex: 1 1 320px; min-width: 0; }
.cab .eyebrow { font-size: 11.5px; letter-spacing: .12em; text-transform: uppercase; color: var(--cab-muted); }
.cab h1 { margin: 1px 0 0; font-size: 22px; font-weight: 600; text-wrap: balance; }
.cab .sub { color: var(--cab-muted); font-size: 13px; }
.cab .fecha { font-size: 12.5px; color: var(--cab-muted); text-align: right; }
nav.secciones { position: sticky; top: 0; z-index: 5; background: var(--panel); border-bottom: 1px solid var(--line); }
nav.secciones .dentro { max-width: 1180px; margin: 0 auto; padding: 0 24px; display: flex; gap: 4px; overflow-x: auto; }
nav.secciones a { padding: 11px 14px; color: var(--muted); border-bottom: 2px solid transparent; white-space: nowrap; font-weight: 500; }
nav.secciones a:hover { color: var(--fg); text-decoration: none; }
nav.secciones a.on { color: var(--marca); border-bottom-color: var(--marca); }
select, button, input[type=search] { font: inherit; color: var(--fg); background: var(--panel); border: 1px solid var(--line);
  border-radius: 6px; padding: 6px 10px; }
button, select { cursor: pointer; }
button:hover, select:hover { border-color: var(--marca-tenue); }
button.on { background: var(--marca); border-color: var(--marca); color: var(--panel); }
:focus-visible { outline: 2px solid var(--marca); outline-offset: 2px; }
main { max-width: 1180px; margin: 0 auto; padding: 20px 24px 48px; display: flex; flex-direction: column; gap: 16px; }
section.bloque { background: var(--panel); border: 1px solid var(--line); border-radius: 10px; padding: 18px 20px; min-width: 0; scroll-margin-top: 56px; }
section.bloque > h2 { margin: 0 0 4px; font-size: 16px; font-weight: 600; color: var(--marca); }
.intro { color: var(--muted); font-size: 13px; margin: 0 0 14px; max-width: 75ch; }
a { color: var(--marca); text-decoration: none; }
a:hover { text-decoration: underline; }
.filtros { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.etq { font-size: 11.5px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); }
label.ctl { display: inline-flex; gap: 8px; align-items: center; min-width: 0; max-width: 100%; }
label.ctl select { min-width: 0; max-width: 100%; }
.vacio { color: var(--muted); font-style: italic; padding: 8px 0; }
.chip { display: inline-block; font-size: 11.5px; padding: 1px 8px; border-radius: 10px; background: var(--chip); color: var(--muted); white-space: nowrap; }
.nv { display: inline-block; font-size: 11.5px; font-weight: 600; padding: 1px 8px; border-radius: 10px; white-space: nowrap; }
.nv-3 { background: var(--n3); color: var(--n3-fg); } .nv-4 { background: var(--n4); color: var(--n4-fg); } .nv-5 { background: var(--n5); color: var(--n5-fg); }

/* el mapa */
.mapa { display: grid; grid-template-columns: minmax(0, 470px) minmax(0, 1fr); gap: 22px; align-items: start; }
.matriz { display: grid; grid-template-columns: 26px 92px repeat(5, minmax(0, 1fr)); gap: 3px; font-size: 12px; }
.matriz .eje-v { grid-row: 1 / span 5; writing-mode: vertical-rl; transform: rotate(180deg); text-align: center; color: var(--muted); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.matriz .rot-f { display: flex; align-items: center; justify-content: flex-end; text-align: right; padding-right: 6px; color: var(--muted); line-height: 1.2; }
.matriz .rot-c { text-align: center; color: var(--muted); line-height: 1.2; padding-top: 4px; overflow-wrap: anywhere; hyphens: auto; }
.matriz > *, .mapa > * { min-width: 0; }
.matriz .eje-h { grid-column: 3 / span 5; text-align: center; color: var(--muted); font-size: 11px; letter-spacing: .08em; text-transform: uppercase; }
.celda { aspect-ratio: 1 / .78; border-radius: 6px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; border: 2px solid transparent; padding: 2px; }
.celda.c-1, .celda.c-2 { background: var(--n1); color: var(--nbaja-fg); }
.celda.c-3 { background: var(--n3); color: var(--n3-fg); } .celda.c-4 { background: var(--n4); color: var(--n4-fg); } .celda.c-5 { background: var(--n5); color: var(--n5-fg); }
.celda .num { font-size: 19px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1; }
.celda .lbl { font-size: 10.5px; opacity: .85; }
button.celda { cursor: pointer; font: inherit; }
button.celda:hover { border-color: var(--fg); }
button.celda.sel { border-color: var(--fg); box-shadow: 0 0 0 2px var(--panel) inset; }
.leyenda { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 12px; font-size: 12px; color: var(--muted); }
.leyenda .nv { margin-right: 4px; }
.riesgo { border: 1px solid var(--line); border-radius: 8px; margin-bottom: 8px; }
.riesgo > summary { list-style: none; cursor: pointer; padding: 10px 12px; display: grid; grid-template-columns: auto 1fr auto; gap: 4px 10px; align-items: baseline; }
.riesgo > summary::-webkit-details-marker { display: none; }
.riesgo > summary:hover { background: var(--chip); border-radius: 8px; }
.riesgo .rid { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 12.5px; }
.riesgo .rtit { font-weight: 600; }
.riesgo .rmeta { grid-column: 2 / span 2; font-size: 12px; color: var(--muted); }
.riesgo .rcuerpo { padding: 2px 14px 12px; border-top: 1px solid var(--line); }
.riesgo h4.sec { margin: 12px 0 4px; font-size: 11.5px; text-transform: uppercase; letter-spacing: .07em; color: var(--muted); font-weight: 600; }
.riesgo .rir { margin-top: 12px; }

/* plantillas y procedimientos */
.area-g { margin-bottom: 18px; }
.area-g > h3 { font-size: 14px; margin: 0 0 8px; padding-bottom: 4px; border-bottom: 1px solid var(--line); }
.area-g > h3 .cod { color: var(--muted); font-weight: 400; margin-right: 6px; }
.grupo { margin: 0 0 12px; }
.grupo .gtit { font-size: 13px; font-weight: 600; margin-bottom: 4px; }
.grupo .gtit a { font-weight: 600; }
.grupo .gtit .cod { color: var(--muted); font-weight: 400; margin-right: 6px; font-variant-numeric: tabular-nums; }
ul.plts { list-style: none; margin: 0; padding: 0; }
ul.plts li { display: grid; grid-template-columns: 92px 1fr auto; gap: 10px; padding: 5px 8px; border-radius: 6px; align-items: baseline; }
ul.plts li:hover { background: var(--chip); }
ul.plts li.destacada { background: var(--marca-suave); }
ul.plts .cod { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 12.5px; }
.ext { font-size: 10.5px; font-weight: 700; letter-spacing: .04em; text-transform: uppercase; padding: 1px 6px; border-radius: 4px; background: var(--chip); color: var(--muted); }
.roto { color: var(--rojo); font-size: 12px; font-weight: 600; }
.sinfich { color: var(--muted); font-size: 12px; font-style: italic; }
ul.procs { list-style: none; margin: 0; padding: 0; }
ul.procs li { display: grid; grid-template-columns: 110px 1fr auto; gap: 10px; padding: 6px 8px; border-radius: 6px; align-items: baseline; }
ul.procs li:hover { background: var(--chip); }
ul.procs .cod { color: var(--muted); font-variant-numeric: tabular-nums; font-size: 12.5px; }
ul.procs button.abrir { border: 0; background: none; padding: 0; color: var(--marca); text-align: left; font-weight: 500; }
ul.procs button.abrir:hover { text-decoration: underline; }
ul.procs .info { font-size: 12px; color: var(--muted); white-space: nowrap; }

/* el lector */
dialog.lector { width: min(860px, calc(100vw - 24px)); max-height: calc(100vh - 32px); padding: 0; border: 1px solid var(--line); border-radius: 12px; background: var(--panel); color: var(--fg); }
dialog.lector::backdrop { background: rgba(10, 16, 24, .45); }
.lector .lcab { position: sticky; top: 0; background: var(--panel); border-bottom: 1px solid var(--line); padding: 14px 20px; display: flex; gap: 12px; align-items: flex-start; }
.lector .lcab .t { flex: 1; min-width: 0; }
.lector .lcab .cod { color: var(--muted); font-size: 12.5px; }
.lector .lcab h2 { margin: 2px 0 0; font-size: 18px; color: var(--marca); }
.lector .lcuerpo { padding: 6px 24px 26px; }
.lector .anexos { margin: 14px 0 6px; padding: 10px 14px; background: var(--marca-suave); border-radius: 8px; }
.lector .anexos > summary { cursor: pointer; font-weight: 600; color: var(--marca); font-size: 13px; }
.lector .anexos[open] > summary { margin-bottom: 8px; }
.lector .anexos > div + div { margin-top: 8px; }
.lector .anexos .etq { margin-bottom: 2px; }
.lector .anexos ul.plts li { grid-template-columns: 92px 1fr auto; }
.texto h3 { font-size: 13px; letter-spacing: .08em; text-transform: uppercase; color: var(--marca); margin: 22px 0 6px; padding-bottom: 3px; border-bottom: 1px solid var(--line); }
.texto h4 { font-size: 13px; margin: 14px 0 4px; }
.texto p { margin: 0 0 10px; max-width: 78ch; }
.texto ul { margin: 0 0 10px; padding-left: 22px; max-width: 76ch; }
.texto ul.ord { list-style: none; padding-left: 4px; }
.texto ul.ord .m { font-weight: 600; color: var(--muted); margin-right: 2px; }
.texto li { margin-bottom: 4px; }
.texto a.cod { font-weight: 600; white-space: nowrap; }
.texto a.cod.plt::after { content: " ↗"; font-weight: 400; font-size: 11px; }
details.resref { margin-top: 18px; color: var(--muted); }
details.resref summary { cursor: pointer; font-size: 12.5px; }
.aviso-ubicacion { border: 1px solid var(--ambar); border-left-width: 4px; background: var(--panel); border-radius: 8px; padding: 12px 16px; font-size: 13.5px; }
.aviso-ubicacion strong { color: var(--ambar); }
.aviso-ubicacion code { font-family: Consolas, "Cascadia Mono", monospace; font-size: 12.5px; background: var(--chip); padding: 1px 5px; border-radius: 4px; overflow-wrap: anywhere; }
footer { color: var(--muted); font-size: 12px; text-align: center; padding: 6px 24px 28px; }
@media (max-width: 860px) { .mapa { grid-template-columns: 1fr; } }
@media (max-width: 640px) {
  .cab .dentro, main, nav.secciones .dentro { padding-left: 14px; padding-right: 14px; }
  .cab .fecha { text-align: left; }
  .matriz { grid-template-columns: 16px 54px repeat(5, minmax(0, 1fr)); gap: 2px; font-size: 10.5px; }
  .matriz .rot-f { padding-right: 3px; }
  .celda .lbl { display: none; }
  .celda .num { font-size: 16px; }
  ul.plts li, ul.procs li, .lector .anexos ul.plts li { grid-template-columns: 1fr auto; }
  ul.plts .cod, ul.procs .cod { grid-column: 1 / -1; }
  .lector .lcuerpo { padding: 6px 16px 22px; }
}
@media print { nav.secciones, .filtros, button.cerrar { display: none; } section.bloque { break-inside: avoid-page; } }
</style>
</head>
<body>
<header class="cab">
  <div class="dentro">
    <svg class="logo" viewBox="0 0 44 44" aria-hidden="true"><rect width="44" height="44" rx="10" fill="#ffffff" fill-opacity=".14"/><text x="22" y="30" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="25" font-weight="700" fill="#ffffff">Q</text></svg>
    <div class="textos">
      <div class="eyebrow">Manual de calidad · AudiQ</div>
      <h1 id="manual"></h1>
      <div class="sub" id="subtitulo"></div>
    </div>
    <div class="fecha" id="generado"></div>
  </div>
</header>
<nav class="secciones" aria-label="Secciones">
  <div class="dentro">
    <a href="#riesgos" data-sec="riesgos">Mapa de riesgos</a>
    <a href="#plantillas" data-sec="plantillas">Plantillas</a>
    <a href="#procedimientos" data-sec="procedimientos">Procedimientos</a>
  </div>
</nav>
<main>
  <div class="aviso-ubicacion" id="aviso-ubicacion" role="status" hidden></div>
  <section class="bloque" id="riesgos">
    <h2>Mapa de riesgos</h2>
    <p class="intro">Los riesgos valorados de nivel medio, alto y extremo, en la matriz de probabilidad e impacto del manual. Pulsa una casilla para ver solo sus riesgos.</p>
    <div class="mapa">
      <div>
        <div class="matriz" id="matriz"></div>
        <div class="leyenda" id="leyenda"></div>
      </div>
      <div>
        <div class="filtros">
          <label class="ctl"><span class="etq">Área</span><select id="r-area"></select></label>
          <label class="ctl"><span class="etq">Tipo</span><select id="r-tipo"><option value="">Todos</option></select></label>
          <button id="r-quitar" hidden>Quitar la casilla</button>
        </div>
        <div id="r-lista"></div>
      </div>
    </div>
  </section>

  <section class="bloque" id="plantillas">
    <h2>Plantillas</h2>
    <p class="intro">Todos los procedimientos del manual por área, cada uno con los modelos y formatos que cita. Las plantillas que no cita ningún procedimiento están al final de cada área.</p>
    <div class="filtros">
      <label class="ctl"><span class="etq">Área</span><select id="p-area"></select></label>
      <input type="search" id="p-buscar" placeholder="Buscar procedimiento o plantilla…" aria-label="Buscar procedimiento o plantilla">
    </div>
    <div id="p-lista"></div>
  </section>

  <section class="bloque" id="procedimientos">
    <h2>Procedimientos</h2>
    <p class="intro">Pulsa un procedimiento para leerlo entero, con sus plantillas y sus diagramas.</p>
    <div class="filtros">
      <label class="ctl"><span class="etq">Área</span><select id="t-area"></select></label>
      <input type="search" id="t-buscar" placeholder="Buscar en el texto…" aria-label="Buscar en los procedimientos">
    </div>
    <div id="t-lista"></div>
  </section>
</main>
<dialog class="lector" id="lector" aria-labelledby="l-titulo">
  <div class="lcab"><div class="t"><div class="cod" id="l-cod"></div><h2 id="l-titulo"></h2></div><button class="cerrar" id="l-cerrar" aria-label="Cerrar">✕</button></div>
  <div class="lcuerpo"><div id="l-anexos"></div><div class="texto" id="l-texto"></div><div id="l-resumen"></div></div>
</dialog>
<footer>Generado el <span id="pie"></span> a partir del manual de AudiQ. Es una vista del manual, sin conclusiones: lo que dice el manual es lo que vale.</footer>
<script id="datos" type="application/json">{{DATOS}}</script>
<script>
(function () {
  "use strict";
  var D = JSON.parse(document.getElementById("datos").textContent);
  var GEN = "{{GENERADO}}";
  var $ = function (id) { return document.getElementById(id); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); };
  var nomArea = {}; D.areas.forEach(function (a) { nomArea[a.codigo] = a.area; });
  var procPor = {}; D.procedimientos.forEach(function (p) { procPor[p.codigo] = p; });
  var pltPor = {}; D.plantillas.forEach(function (p) { pltPor[p.codigo] = p; });
  var guardar = function (k, v) { try { localStorage.setItem("manual-calidad:" + k, v); } catch (e) {} };
  var leer = function (k) { try { return localStorage.getItem("manual-calidad:" + k) || ""; } catch (e) { return ""; } };
  var fmtFecha = function (s) { var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(s); return m ? m[3] + "/" + m[2] + "/" + m[1] : s; };

  // Los enlaces a las plantillas son relativos a la carpeta del manual y solo valen con la pagina
  // en <carpeta del manual>\AsistenteIA\ManualCalidad\. Fuera de ahi se avisa y, si se sabe la
  // carpeta, se usa su ruta completa en este equipo.
  var FUERA = !/\/asistenteia\/manualcalidad\/[^\/]*$/i.test(decodeURIComponent(location.pathname));
  if (FUERA) {
    var carpeta = D.carpeta_manual || "<carpeta del manual>";
    $("aviso-ubicacion").innerHTML = "<strong>Esta página no está en su sitio.</strong> Tiene que estar en <code>" +
      esc(carpeta.replace(/\\$/, "") + "\\AsistenteIA\\ManualCalidad\\") + "</code> para que las plantillas abran también desde otro equipo. " +
      (D.carpeta_manual ? "Mientras tanto, los enlaces usan la ruta completa de la carpeta del manual en el equipo donde se generó."
                        : "Fuera de ahí, los enlaces a las plantillas no abren.");
    $("aviso-ubicacion").hidden = false;
  }
  var hrefFichero = function (f) { return FUERA && f.abs ? f.abs : f.href; };

  $("manual").textContent = D.manual;
  // un .qat no lleva version ni fecha de publicacion: solo las tiene el .qal publicado
  $("subtitulo").textContent = [D.version ? "Versión " + D.version : "", D.publicado ? "publicado el " + D.publicado : ""]
    .filter(Boolean).join(" · ") || "Manual en trabajo, sin publicar";
  $("generado").textContent = "Generado el " + fmtFecha(GEN);
  $("pie").textContent = fmtFecha(GEN);

  function opcionesArea(sel, areas, clave) {
    sel.innerHTML = '<option value="">Todas</option>' + areas.map(function (a) {
      return '<option value="' + esc(a) + '">' + esc(a + " · " + (nomArea[a] || a)) + "</option>";
    }).join("");
    var v = leer(clave); if (v && areas.indexOf(v) >= 0) sel.value = v;
    sel.addEventListener("change", function () { guardar(clave, sel.value); });
  }
  function enlaceFichero(f) {
    if (!f) return '<span class="sinfich">sin fichero vinculado</span>';
    if (f.estado === "roto") return '<span class="roto" title="' + esc("No se encuentra: " + (f.ruta || f.nombre)) + '">No se encuentra el fichero</span>';
    var t = f.estado === "url" ? "web" : (f.ext || "fichero");
    return '<a href="' + esc(hrefFichero(f)) + '" target="_blank" rel="noopener" title="' + esc(f.nombre) + '"><span class="ext">' + esc(t) + "</span> Abrir</a>";
  }
  function filaPlantilla(p, destacada) {
    return '<li id="plt-' + esc(p.codigo) + '"' + (destacada ? ' class="destacada"' : "") + '><span class="cod">' + esc(p.codigo) +
      "</span><span>" + esc(p.nombre) + "</span><span>" + enlaceFichero(p.fichero) + "</span></li>";
  }

  // ── Mapa de riesgos ──
  var celdaSel = "";
  function pintarMatriz() {
    var h = '<div class="eje-v">Probabilidad</div>';
    for (var p = 5; p >= 1; p--) {
      h += '<div class="rot-f">' + esc(D.ejes.P[p]) + "</div>";
      for (var i = 1; i <= 5; i++) {
        var nivel = D.matriz[String(p * 10 + i)];
        var n = D.riesgos.filter(function (r) { return r.p === p && r.i === i; }).length;
        var lbl = esc(D.niveles[nivel] || "");
        if (nivel >= 3 && n) {
          h += '<button class="celda c-' + nivel + (celdaSel === p + "-" + i ? " sel" : "") + '" data-c="' + p + "-" + i +
            '" aria-label="' + esc(n + " riesgo(s) de probabilidad " + D.ejes.P[p] + " e impacto " + D.ejes.I[i]) + '"><span class="num">' + n +
            '</span><span class="lbl">' + lbl + "</span></button>";
        } else {
          h += '<div class="celda c-' + nivel + '"><span class="lbl">' + lbl + "</span></div>";
        }
      }
    }
    h += "<div></div><div></div>";
    for (var j = 1; j <= 5; j++) h += '<div class="rot-c">' + esc(D.ejes.I[j]) + "</div>";
    h += '<div></div><div></div><div class="eje-h">Impacto</div>';
    $("matriz").innerHTML = h;
    $("leyenda").innerHTML = ["5", "4", "3"].map(function (k) {
      var n = D.riesgos.filter(function (r) { return String(r.nivel) === k; }).length;
      return '<span><span class="nv nv-' + k + '">' + esc(D.niveles[k]) + "</span>" + n + "</span>";
    }).join("") + (D.cuentas.sin_valorar ? "<span>" + D.cuentas.sin_valorar + " sin valorar</span>" : "");
  }
  function pintarRiesgos() {
    var a = $("r-area").value, t = $("r-tipo").value;
    var lista = D.riesgos.filter(function (r) {
      return (!a || r.area === a) && (!t || r.tipo === t) && (!celdaSel || celdaSel === r.p + "-" + r.i);
    });
    $("r-quitar").hidden = !celdaSel;
    if (!lista.length) { $("r-lista").innerHTML = '<div class="vacio">' + (D.riesgos.length ? "Ningún riesgo con estos filtros." : "El manual no tiene riesgos valorados de nivel medio o superior.") + "</div>"; return; }
    $("r-lista").innerHTML = lista.map(function (r) {
      var dest = "";
      if (r.destino && r.destino.tipo === "p") dest = '<a href="#p/' + encodeURIComponent(r.destino.codigo) + '">Ver el procedimiento ' + esc(r.destino.codigo) + " · " + esc(r.destino.titulo) + "</a>";
      else if (r.destino) dest = '<a href="#plantillas/' + encodeURIComponent(r.destino.area) + '">Ver las plantillas del área ' + esc(r.destino.area) + "</a>";
      var sec = function (t, x) { return x ? '<h4 class="sec">' + t + '</h4><div class="texto">' + x + "</div>" : ""; };
      return '<details class="riesgo"><summary><span class="rid">' + esc(r.id) + '</span><span class="rtit">' + esc(r.riesgo) +
        '</span><span class="nv nv-' + r.nivel + '">' + esc(D.niveles[r.nivel]) + '</span><span class="rmeta">' +
        esc(r.area + " · " + (nomArea[r.area] || "") + (r.tipo ? " · " + r.tipo : "") + " · probabilidad " + D.ejes.P[r.p].toLowerCase() + ", impacto " + D.ejes.I[r.i].toLowerCase()) +
        '</span></summary><div class="rcuerpo">' + sec("Descripción", r.descripcion) + sec("Respuesta prevista", r.respuesta) +
        sec("Recomendación", r.recomendacion) + (dest ? '<div class="rir">' + dest + "</div>" : "") + "</div></details>";
    }).join("");
  }
  var areasR = Array.from(new Set(D.riesgos.map(function (r) { return r.area; }))).sort();
  opcionesArea($("r-area"), areasR, "r-area");
  Array.from(new Set(D.riesgos.map(function (r) { return r.tipo; }).filter(Boolean))).sort().forEach(function (t) {
    var o = document.createElement("option"); o.value = t; o.textContent = t; $("r-tipo").appendChild(o);
  });
  $("matriz").addEventListener("click", function (e) {
    var b = e.target.closest("button.celda"); if (!b) return;
    celdaSel = celdaSel === b.dataset.c ? "" : b.dataset.c; pintarMatriz(); pintarRiesgos();
  });
  $("r-quitar").addEventListener("click", function () { celdaSel = ""; pintarMatriz(); pintarRiesgos(); });
  $("r-area").addEventListener("change", pintarRiesgos);
  $("r-tipo").addEventListener("change", pintarRiesgos);
  pintarMatriz(); pintarRiesgos();

  // ── Plantillas ──
  // El indice lo prepara el script: todos los procedimientos disponibles de cada area, con o sin
  // plantillas, y al final las plantillas del area que no cita nadie.
  var areasP = D.indice.map(function (x) { return x.area; });
  opcionesArea($("p-area"), areasP, "p-area");
  var pltDestacada = "";
  function areaDePlantilla(cod) {
    for (var i = 0; i < D.indice.length; i++) {
      var x = D.indice[i];
      if (x.otras.indexOf(cod) >= 0 || x.procedimientos.some(function (p) { return p.plantillas.indexOf(cod) >= 0; })) return x.area;
    }
    return "";
  }
  function pintarPlantillas() {
    var a = $("p-area").value, q = $("p-buscar").value.trim().toLowerCase();
    var casa = function (t) { return !q || t.toLowerCase().indexOf(q) >= 0; };
    var cumple = function (c) { var p = pltPor[c]; return p && casa(p.codigo + " " + p.nombre); };
    var fila = function (c) { return filaPlantilla(pltPor[c], c === pltDestacada); };
    var h = "";
    D.indice.filter(function (x) { return !a || x.area === a; }).forEach(function (x) {
      var grupos = "";
      x.procedimientos.forEach(function (pr) {
        // buscando, un procedimiento sale si casa el o alguna de sus plantillas
        var propio = casa(pr.codigo + " " + pr.titulo);
        var suyas = propio ? pr.plantillas : pr.plantillas.filter(cumple);
        if (!propio && !suyas.length) return;
        grupos += '<div class="grupo"><div class="gtit"><span class="cod">' + esc(pr.codigo) + '</span><a href="#p/' + encodeURIComponent(pr.codigo) + '">' +
          esc(pr.titulo) + "</a></div>" + (suyas.length ? '<ul class="plts">' + suyas.map(fila).join("") + "</ul>"
          : '<div class="sinfich">sin plantillas citadas</div>') + "</div>";
      });
      var otras = x.otras.filter(cumple);
      if (otras.length) grupos += '<div class="grupo"><div class="gtit">Otras plantillas del área</div><ul class="plts">' +
        otras.map(fila).join("") + "</ul></div>";
      if (grupos) h += '<div class="area-g" id="pa-' + esc(x.area) + '"><h3><span class="cod">' + esc(x.area) + "</span>" + esc(nomArea[x.area] || x.area) + "</h3>" + grupos + "</div>";
    });
    $("p-lista").innerHTML = h || '<div class="vacio">Nada con estos filtros.</div>';
  }
  $("p-area").addEventListener("change", pintarPlantillas);
  $("p-buscar").addEventListener("input", pintarPlantillas);
  pintarPlantillas();

  // ── Procedimientos ──
  var areasT = Array.from(new Set(D.procedimientos.map(function (p) { return p.area; }))).sort();
  opcionesArea($("t-area"), areasT, "t-area");
  var textoPlano = {};
  D.procedimientos.forEach(function (p) {
    var d = document.createElement("div"); d.innerHTML = p.cuerpo + p.resumen;
    textoPlano[p.codigo] = (p.codigo + " " + p.titulo + " " + d.textContent).toLowerCase();
  });
  function pintarProcedimientos() {
    var a = $("t-area").value, q = $("t-buscar").value.trim().toLowerCase();
    var h = "";
    areasT.filter(function (x) { return !a || x === a; }).forEach(function (ar) {
      var deArea = D.procedimientos.filter(function (p) { return p.area === ar && (!q || textoPlano[p.codigo].indexOf(q) >= 0); });
      if (!deArea.length) return;
      h += '<div class="area-g"><h3><span class="cod">' + esc(ar) + "</span>" + esc(nomArea[ar] || ar) + '</h3><ul class="procs">' +
        deArea.map(function (p) {
          var info = [];
          if (p.plantillas.length) info.push(p.plantillas.length + (p.plantillas.length === 1 ? " plantilla" : " plantillas"));
          if (p.diagramas.length) info.push(p.diagramas.length + (p.diagramas.length === 1 ? " diagrama" : " diagramas"));
          return '<li><span class="cod">' + esc(p.codigo) + '</span><button class="abrir" data-p="' + esc(p.codigo) + '">' + esc(p.titulo) +
            '</button><span class="info">' + esc(info.join(" · ")) + "</span></li>";
        }).join("") + "</ul></div>";
    });
    $("t-lista").innerHTML = h || '<div class="vacio">Ningún procedimiento con estos filtros.</div>';
  }
  $("t-area").addEventListener("change", pintarProcedimientos);
  $("t-buscar").addEventListener("input", pintarProcedimientos);
  $("t-lista").addEventListener("click", function (e) {
    var b = e.target.closest("button.abrir"); if (b) location.hash = "#p/" + encodeURIComponent(b.dataset.p);
  });
  pintarProcedimientos();

  // ── El lector ──
  var lector = $("lector");
  function abrir(cod) {
    var p = procPor[cod]; if (!p) return;
    $("l-cod").textContent = p.codigo + " · " + (nomArea[p.area] || p.area);
    $("l-titulo").textContent = p.titulo;
    var an = "", cuenta = [];
    if (p.plantillas.length) {
      cuenta.push(p.plantillas.length + (p.plantillas.length === 1 ? " plantilla" : " plantillas"));
      an += '<div><div class="etq">Plantillas que cita</div><ul class="plts">' +
        p.plantillas.map(function (c) { return pltPor[c] ? filaPlantilla(pltPor[c], false) : ""; }).join("") + "</ul></div>";
    }
    if (p.diagramas.length) {
      cuenta.push(p.diagramas.length + (p.diagramas.length === 1 ? " diagrama o documento" : " diagramas o documentos"));
      an += '<div><div class="etq">Diagramas y documentos</div><ul class="plts">' +
        p.diagramas.map(function (d) { return '<li><span class="cod"></span><span>' + esc(d.nombre) + "</span><span>" + enlaceFichero(d) + "</span></li>"; }).join("") + "</ul></div>";
    }
    // lo que se viene a hacer es leer: con muchos anexos la lista va plegada y el texto arriba
    var plegar = p.plantillas.length + p.diagramas.length > 4;
    $("l-anexos").innerHTML = an ? '<details class="anexos"' + (plegar ? "" : " open") + "><summary>" + esc(cuenta.join(" · ")) +
      "</summary>" + an + "</details>" : "";
    $("l-texto").innerHTML = p.cuerpo || p.resumen || '<div class="vacio">El manual no trae texto para este procedimiento.</div>';
    $("l-resumen").innerHTML = p.cuerpo && p.resumen ? '<details class="resref"><summary>Resumen de la referencia en AudiQ</summary><div class="texto">' + p.resumen + "</div></details>" : "";
    if (FUERA) lector.querySelectorAll("a[data-abs]").forEach(function (a) { a.href = a.dataset.abs; });
    if (!lector.open) { if (lector.showModal) lector.showModal(); else lector.setAttribute("open", ""); }
    lector.querySelector(".lcuerpo").scrollTop = 0; lector.scrollTop = 0;
  }
  function cerrar() { if (lector.open) lector.close ? lector.close() : lector.removeAttribute("open"); }
  $("l-cerrar").addEventListener("click", function () { history.pushState("", "", "#procedimientos"); cerrar(); });
  lector.addEventListener("click", function (e) { if (e.target === lector) { history.pushState("", "", "#procedimientos"); cerrar(); } });
  lector.addEventListener("cancel", function () { history.pushState("", "", "#procedimientos"); });

  // ── Navegacion por la direccion: #p/<cod>, #plantilla/<cod>, #plantillas/<area> ──
  function ir() {
    var h = decodeURIComponent(location.hash.slice(1));
    var m;
    if ((m = /^p\/(.+)$/.exec(h))) { abrir(m[1]); return; }
    cerrar();
    if ((m = /^plantilla\/(.+)$/.exec(h)) && pltPor[m[1]]) {
      pltDestacada = m[1]; $("p-area").value = areaDePlantilla(m[1]); $("p-buscar").value = ""; pintarPlantillas();
      var li = document.getElementById("plt-" + m[1]); if (li) li.scrollIntoView({ block: "center" });
      return;
    }
    if ((m = /^plantillas\/(.+)$/.exec(h))) {
      $("p-area").value = areasP.indexOf(m[1]) >= 0 ? m[1] : ""; $("p-buscar").value = ""; pltDestacada = ""; pintarPlantillas();
      $("plantillas").scrollIntoView(); return;
    }
  }
  window.addEventListener("hashchange", ir);
  ir();

  // la pestaña activa sigue al scroll
  var navs = Array.from(document.querySelectorAll("nav.secciones a"));
  function marcar() {
    var y = window.scrollY + 90, act = "riesgos";
    ["riesgos", "plantillas", "procedimientos"].forEach(function (s) { if ($(s).offsetTop <= y) act = s; });
    navs.forEach(function (a) { a.classList.toggle("on", a.dataset.sec === act); });
  }
  window.addEventListener("scroll", marcar, { passive: true }); marcar();
})();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
