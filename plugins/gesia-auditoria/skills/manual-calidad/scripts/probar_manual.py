# -*- coding: utf-8 -*-
"""Comprueba que generar_manual.py escribe la pagina que tiene que escribir, y que para cuando debe.

    python probar_manual.py

Con un manual sintetico, sin AudiQ ni servidor API: tres areas, siete riesgos de todos los niveles
(uno sin valorar), cuatro procedimientos (uno no disponible, uno sin texto) y cinco plantillas
(con fichero, rota, sin fichero, URL y sin citar). Mira:

  1. que la pagina sale con el nombre saneado, sin recursos externos y con «</script>» escapado
  2. el mapa: solo nivel medio o superior, en orden, y adonde lleva cada riesgo
  3. los procedimientos: solo los disponibles, y el texto con titulos, listas y codigos enlazados
  4. las plantillas: quien las cita, su estado y el enlace relativo a la carpeta del manual
  5. los avisos de la degradacion
  6. el contrato: los casos en los que NO se escribe la pagina
  7. que el SKILL.md pide los ocho ficheros, pone el perfil, limpia y borra con ruta literal

Codigos de salida: 0 todo bien, 1 algo ha fallado.
"""
from __future__ import annotations

import io
import json
import re
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

# La carpeta del script, explicita: lanzado con `python -I` no esta en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import generar_manual as g  # noqa: E402

SKILL_MD = Path(__file__).resolve().parent.parent / "SKILL.md"

# La matriz de un manual real: no es simetrica, la probabilidad pesa mas que el impacto
NIVEL = {1: [1, 1, 2, 3, 3], 2: [1, 2, 2, 3, 4], 3: [1, 2, 3, 4, 4], 4: [1, 2, 3, 4, 5], 5: [2, 3, 4, 5, 5]}
NOMBRE_NIVEL = {1: "Muy bajo", 2: "Bajo", 3: "Medio", 4: "Alto", 5: "Extremo"}

MANUAL = [{"Proyecto": "audiQ", "TipoMDB": "qal", "NombreFichero": "Manual de Calidad Ejemplo ISO9001:2015",
           "Version": "2.3", "FechaPublicacion": "05/03/25 0:00:00", "HipervinculosRelativos": "True",
           "CodigoTipoFichero": "1"}]
AREAS = [{"CodigoArea": "A", "Area": "GOBIERNO Y LIDERAZGO"}, {"CodigoArea": "C", "Area": "ACEPTACIÓN"},
         {"CodigoArea": "E", "Area": "EJECUCIÓN"}]
VALORES_RIA = [{"CodigoRIA": str(p * 10 + i), "CodigoValorRIA": str(NIVEL[p][i - 1]),
                "ValorRIA": NOMBRE_NIVEL[NIVEL[p][i - 1]], "Color": "&[CIF]"}
               for p in range(1, 6) for i in range(1, 6)]
EJES = ([{"Eje": "P", "CodigoValorRIA": str(k), "ValorRIA": v}
         for k, v in enumerate(["Muy baja", "Baja", "Media", "Alta", "Muy alta"], start=1)]
        + [{"Eje": "I", "CodigoValorRIA": str(k), "ValorRIA": v}
           for k, v in enumerate(["Insignificante", "Menor", "Medio", "Grave", "Catastrófico"], start=1)])


def riesgo(id_, nombre, p, i, ref, area="A", tipo="2"):
    return {"IdRiesgo": str(id_), "Riesgo": nombre, "CodigoTipoRiesgo": tipo, "CodigoArea": area,
            "CodigoReferencia": ref, "CodigoValorRIA_RCI": str(p) if p else None,
            "CodigoValorRIA_RI": str(i) if i else None,
            "CodigoValorRIA_RIM": str(NIVEL[p][i - 1]) if p and i else None,
            "Descripcion": "Lo que puede pasar.\r\n- una cosa\r\n- otra", "Procedimientos": "Revisarlo.",
            "Recomendacion": ""}


RIESGOS = [
    riesgo(1, "Extremo con procedimiento", 5, 5, "A)01", tipo="1"),
    riesgo(2, "Alto hacia las plantillas", 2, 5, "C)AQ", area="C"),
    riesgo(3, "Medio hacia lo no disponible", 1, 4, "C)05", area="C"),
    riesgo(4, "Muy bajo, no sale", 1, 1, "A)01"),
    # el que delata un umbral mal puesto: nivel bajo, justo debajo del corte
    riesgo(7, "Bajo, no sale", 2, 2, "A)01"),
    riesgo(5, "Sin valorar", None, None, ""),
    riesgo(6, "Medio </script><b>x</b>", 3, 3, ""),
]


def ref(cod, area, nombre, tipo, disp=True, comentario="Resumen de la referencia."):
    return {"CodigoReferencia": cod, "CodigoArea": area, "Referencia": nombre, "CodigoTipoGuia": tipo,
            "CodigoClaseReferencia": "2", "Disponible": "True" if disp else "False", "Comentario": comentario}


REFERENCIAS = [
    ref("A)01", "A", "Política de calidad", "PR"),
    ref("C)01", "C", "Aceptación de clientes", "PR"),
    ref("C)05", "C", "Consideraciones EIP", "PR", disp=False),
    ref("E)01", "E", "Ejecución, solo resumen", "PR", comentario="Solo hay resumen."),
    ref("C)AQ", "C", "Modelos y plantillas", "F"),
]


def linea(guia, orden, punto, desglose, desc, cod="", fichero=""):
    return {"CodigoGuia": guia, "CodigoOrden": str(orden), "Punto": str(punto), "DesglosePunto": desglose,
            "CodigoReferencia": cod, "Descripcion": desc, "FicheroVinculado": fichero}


GUIAS = [
    linea("A)01", 1, 1, "", "OBJETIVO"),
    linea("A)01", 2, 1, "1", "Describir la politica.\r\n\r\nDIRECCIÓN DE LA FIRMA\r\nLa Dirección se asegura de:"
          "\r\n- primero\r\n- segundo\r\n\r\na) letra uno\r\nb) letra dos\r\n\tsigue la b"),
    linea("A)01", 3, 2, "", "DESARROLLO"),
    linea("A)01", 4, 2, "1", "Se usará el modelo C)AQ/01 y, para aquellos casos, C/AQ/03. Ver C)AQ/02, C)01, "
          "C)05, D)AQ y AQ)03. NIF de la firma [CIF]."),
    # titulo y texto en el mismo punto, como en el manual real (registro de Cowork, 24/10/2026)
    linea("A)01", 5, 3, "", "RECURSOS INTELECTUALES\r\n\r\nSon aquellos que se obtienen.\r\n- uno"),
    linea("A)01", 6, 4, "", "Texto largo sin titulo, " + "que sigue y sigue " * 10),
    linea("A)01", 7, 5, "", "Objetivo general"),
    linea("C)01", 1, 1, "", "OBJETIVO"),
    linea("C)01", 2, 1, "1", "Carta segun C)AQ/04 y vuelta a A)01. Registro en AQ)02."),
    linea("C)05", 1, 1, "1", "Texto de algo no disponible, que cita C)AQ/05."),
    linea("C)AQ", 1, 1, "", "MANUAL DE PROCEDIMIENTOS"),
    linea("C)AQ", 2, 1, "1", "Modelo uno", "C)AQ/01", "file:01 Proc\\C)AQ_01 Modelo uno.docx"),
    linea("C)AQ", 3, 1, "2", "Modelo roto", "C)AQ/02", "file:01 Proc\\C)AQ_02 Roto.xlsx"),
    linea("C)AQ", 4, 1, "3", "Sin fichero", "C/AQ/03 ", ""),
    linea("C)AQ", 5, 1, "4", "En la web", "C)AQ/04", "https://ejemplo.invalid/modelo"),
    linea("C)AQ", 6, 1, "5", "Sin citar", "C)AQ/05", "file:01 Proc\\C)AQ_05 Sin citar.docx"),
]


def vinculo(tabla, clave, campo, bruto, existe, tipo="fichero"):
    return {"Tabla": tabla, "Clave": clave, "Descripcion": None, "Campo": campo, "Tipo": tipo,
            "Ruta": "C:\\Firma\\Manual\\" + bruto.replace("file:", ""), "Existe": existe, "Bruto": bruto}


VINCULOS = [
    vinculo("DetalleGuias", "C)AQ", "FicheroVinculado", "file:01 Proc\\C)AQ_01 Modelo uno.docx", True),
    vinculo("DetalleGuias", "C)AQ", "FicheroVinculado", "file:01 Proc\\C)AQ_02 Roto.xlsx", False),
    vinculo("DetalleGuias", "C)AQ", "FicheroVinculado", "https://ejemplo.invalid/modelo", "— (no se comprueba)", "url"),
    vinculo("DetalleGuias", "C)AQ", "FicheroVinculado", "file:01 Proc\\C)AQ_05 Sin citar.docx", True),
    vinculo("Referencias", "A)01", "FicheroVinculado1", "file:00 Calidad\\flujo A)01.pdf", True),
]


def escribir_fixture(carpeta: Path, **cambios) -> None:
    datos = {"manual": MANUAL, "areas": AREAS, "valores_ria": VALORES_RIA, "ejes": EJES, "riesgos": RIESGOS,
             "referencias": REFERENCIAS, "guias": GUIAS, "vinculos": VINCULOS}
    datos.update(cambios)
    for nombre, contenido in datos.items():
        if contenido is not None:
            (carpeta / f"{nombre}.json").write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")


def generar(carpeta: Path, fecha: str = "2026-10-24") -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        codigo = g.main(["--datos", str(carpeta), "--generado", fecha, "--salida", str(carpeta / "salida")])
    return codigo, buf.getvalue()


def datos_de(html: str) -> dict:
    m = re.search(r'<script id="datos" type="application/json">(.*?)</script>', html, re.S)
    if not m:
        raise AssertionError("no encuentro los datos en la pagina")
    return json.loads(m.group(1).replace("<\\/", "</"))


FALLOS: list[str] = []


def comprobar(cond: bool, que: str) -> None:
    print(("  ok   " if cond else "  MAL  ") + que)
    if not cond:
        FALLOS.append(que)


def main() -> int:
    g._salida_utf8()
    with tempfile.TemporaryDirectory(prefix="manual-prueba-") as tmp:
        base = Path(tmp)

        print("1 · la pagina")
        c = base / "completo"; c.mkdir()
        escribir_fixture(c)
        codigo, texto = generar(c)
        paginas = list((c / "salida").glob("*.html"))
        comprobar(codigo == 0 and len(paginas) == 1, "sale una pagina (salida 0)")
        comprobar(bool(paginas) and paginas[0].name == "Manual de Calidad Ejemplo ISO9001-2015.html"
                  and "nombre: Manual de Calidad Ejemplo ISO9001-2015.html" in texto,
                  "el nombre es el del manual, sin los dos puntos y sin la version (asi rehacerla la pisa)")
        html = paginas[0].read_text(encoding="utf-8") if paginas else ""
        externos = re.findall(r"""(?:src|href)\s*=\s*["']?(?:https?:)?//""", html, re.I)
        comprobar(not externos and "@import" not in html, "sin recursos externos")
        comprobar(html.count("</script>") == len(re.findall(r"<script[ >]", html)) and "</script><b>" not in html,
                  "el nombre con </script> va escapado")
        D = datos_de(html)
        comprobar(D["publicado"] == "05/03/2025" and D["version"] == "2.3", "fecha de publicacion con el año entero")

        print("2 · el mapa")
        ids = [r["id"] for r in D["riesgos"]]
        comprobar(ids == [1, 2, 6, 3], "solo nivel medio o superior, del mas alto al mas bajo (y a igual nivel, mas probable)")
        r = {x["id"]: x for x in D["riesgos"]}
        comprobar(r[1]["nivel"] == 5 and r[2]["nivel"] == 4 and r[3]["nivel"] == 3, "el nivel sale de la matriz")
        comprobar(r[1]["destino"] == {"tipo": "p", "codigo": "A)01", "titulo": "Política de calidad"},
                  "un riesgo lleva a su procedimiento")
        comprobar((r[2]["destino"] or {}).get("tipo") == "plantillas" and r[2]["destino"]["area"] == "C",
                  "uno que apunta a la coleccion X)AQ lleva a las plantillas de su area")
        comprobar(r[3]["destino"] is None, "uno que apunta a algo no disponible sale sin enlace")
        comprobar(r[1]["tipo"] == "Riesgo de O.I." and r[2]["tipo"] == "Riesgo de calidad", "tipo de riesgo")
        comprobar("<ul" in r[1]["descripcion"], "la descripcion del riesgo tambien sale con formato")
        comprobar(D["cuentas"]["sin_valorar"] == 1 and D["cuentas"]["por_nivel"].get("1") == 1
                  and D["cuentas"]["por_nivel"].get("2") == 1,
                  "cuenta los sin valorar y los de nivel bajo que no salen")
        comprobar(D["matriz"]["54"] == 5 and D["matriz"]["45"] == 5 and D["matriz"]["15"] == 3 and D["matriz"]["51"] == 2,
                  "la matriz viaja a la pagina tal cual, no simetrica")

        print("3 · los procedimientos")
        P = {p["codigo"]: p for p in D["procedimientos"]}
        comprobar(sorted(P) == ["A)01", "C)01", "E)01"], "solo los disponibles: C)05 no sale")
        a = P["A)01"]["cuerpo"]
        comprobar(a.startswith("<h3>OBJETIVO</h3>") and "<h3>DESARROLLO</h3>" in a, "un punto sin desglose es un titulo")
        comprobar("<h4>DIRECCIÓN DE LA FIRMA</h4>" in a, "el titulillo en mayusculas")
        comprobar('<ul class="vin"><li>primero</li><li>segundo</li></ul>' in a, "la lista con guion")
        comprobar('<span class="m">a)</span> letra uno' in a and "letra dos<br>sigue la b" in a,
                  "la lista con letra, y la linea sin marca continua el punto")
        comprobar('href="../../01%20Proc/C%29AQ_01%20Modelo%20uno.docx"' in a and 'target="_blank"' in a,
                  "un codigo de plantilla abre su fichero, relativo a la carpeta del manual")
        comprobar('href="#plantilla/C%29AQ%2F03">C/AQ/03</a>' in a, "uno sin fichero (y con barra) lleva a su fila")
        comprobar('href="#plantilla/C%29AQ%2F02">C)AQ/02</a>' in a, "uno roto lleva a su fila, que dice por que")
        comprobar('href="#p/C%2901">C)01</a>' in a, "un codigo de procedimiento abre ese procedimiento")
        comprobar("C)05," in a and "#p/C%2905" not in a, "uno no disponible queda como texto")
        comprobar("aquellos" in a and ">aquellos<" not in a and "AQ)03" in a and "D)AQ" in a and "#plantillas/D" not in a,
                  "«aquellos», AQ)03 y una coleccion que no existe no se enlazan")
        comprobar('href="#p/A%2901"' in P["C)01"]["cuerpo"] and "#p/A%2901" not in a, "no se enlaza a si mismo")
        comprobar([d["href"] for d in P["A)01"]["diagramas"]] == ["../../00%20Calidad/flujo%20A%2901.pdf"],
                  "el diagrama del procedimiento")
        comprobar("<h3>RECURSOS INTELECTUALES</h3><p>Son aquellos que se obtienen.</p><ul class=\"vin\"><li>uno</li></ul>" in a,
                  "un punto con titulo y texto juntos se parte: el titulo es titulo y el resto, texto")
        comprobar("<p>Texto largo sin titulo," in a and "<h3>Texto largo" not in a,
                  "un punto largo que no va en mayusculas es texto, no titulo")
        comprobar("<h3>Objetivo general</h3>" in a, "un punto corto de una linea sigue siendo titulo")
        comprobar(max(len(t) for t in re.findall(r"<h3>(.*?)</h3>", a)) <= g.LARGO_MAXIMO_TITULO,
                  "ningun titulo se come un parrafo")
        comprobar(P["E)01"]["cuerpo"] == "" and "Solo hay resumen" in P["E)01"]["resumen"], "sin guia sale el resumen")

        print("4 · las plantillas")
        T = {p["codigo"]: p for p in D["plantillas"]}
        comprobar(sorted(T) == ["C)AQ/01", "C)AQ/02", "C)AQ/03", "C)AQ/04", "C)AQ/05"],
                  "las cinco, con el codigo normalizado (C/AQ/03 con espacio -> C)AQ/03)")
        comprobar(T["C)AQ/01"]["citada_por"] == ["A)01"] and T["C)AQ/04"]["citada_por"] == ["C)01"],
                  "quien cita cada una")
        comprobar(T["C)AQ/05"]["citada_por"] == [], "la que solo cita un procedimiento no disponible queda sin citar")
        comprobar(T["C)AQ/01"]["fichero"]["estado"] == "ok" and T["C)AQ/02"]["fichero"]["estado"] == "roto"
                  and T["C)AQ/02"]["fichero"]["href"] == "" and T["C)AQ/03"]["fichero"] is None
                  and T["C)AQ/04"]["fichero"]["estado"] == "url", "estado de cada fichero: ok, roto, sin fichero, web")
        comprobar(T["C)AQ/01"]["bloque"] == "MANUAL DE PROCEDIMIENTOS", "el bloque de la coleccion")

        print("4a · el indice de la pestaña Plantillas")
        I = {x["area"]: x for x in D["indice"]}
        vacia = {"procedimientos": [], "otras": []}
        ia, ic, ie = I.get("A", vacia), I.get("C", vacia), I.get("E", vacia)
        comprobar(sorted(I) == ["A", "C", "E"], "las areas salen de procedimientos y plantillas: E no tiene plantillas y sale")
        comprobar([p["codigo"] for p in ie["procedimientos"]] == ["E)01"] and ie["procedimientos"][0]["plantillas"] == [],
                  "un procedimiento disponible sin plantillas sale en el indice")
        comprobar(bool(ia["procedimientos"]) and ia["procedimientos"][0]["plantillas"] == ["C)AQ/01", "C)AQ/02", "C)AQ/03"],
                  "un procedimiento lleva sus plantillas aunque sean de otra area")
        comprobar(ic["otras"] == ["C)AQ/05"], "al final del area, solo las que no cita nadie")
        comprobar("pr.plantillas.length; })" not in html and "sin plantillas citadas" in html,
                  "la pagina no descarta los procedimientos sin plantillas")
        comprobar("sin plantillas citadas 1 " in texto, "el resumen cuenta los procedimientos sin plantillas")
        comprobar("3 cita(s) con aspecto de codigo de plantilla" in texto and "C)01 cita «AQ)02» (¿C)AQ/02?)" in texto
                  and "A)01 cita «AQ)03»;" in texto and "A)01 cita «D)AQ»" in texto,
                  "avisa de los codigos mal escritos, y propone la plantilla cuando la ve")
        comprobar("#plantilla/AQ" not in a and ">AQ)03<" not in a, "y no los enlaza: se corrigen en AudiQ")

        print("4b · la pagina fuera de su sitio")
        comprobar(D["carpeta_manual"] == "C:\\Firma\\Manual", "deduce la carpeta del manual de los vinculos")
        absoluto = "file:///C:/Firma/Manual/01%20Proc/C%29AQ_01%20Modelo%20uno.docx"
        comprobar(T["C)AQ/01"]["fichero"]["abs"] == absoluto and T["C)AQ/04"]["fichero"]["abs"] == "",
                  "cada plantilla lleva su ruta completa de reserva (la web no)")
        comprobar(f'data-abs="{absoluto}"' in a, "y tambien el codigo citado en el texto")
        comprobar('id="aviso-ubicacion"' in html and "asistenteia\\/manualcalidad" in html,
                  "la pagina comprueba al abrirse que esta en AsistenteIA\\ManualCalidad")
        unc = g.carpeta_manual([{"Tipo": "fichero", "Bruto": "file:01\\x.docx", "Ruta": "\\\\srv\\datos\\Manual\\01\\x.docx"}])
        comprobar(unc == "\\\\srv\\datos\\Manual" and g._enlace_absoluto(unc, "file:01\\x.docx") == "file://srv/datos/Manual/01/x.docx",
                  "una carpeta en red se enlaza como file://servidor/...")
        comprobar(g.carpeta_manual([{"Tipo": "url", "Bruto": "https://x", "Ruta": "https://x"}]) is None,
                  "sin vinculos relativos no se inventa la carpeta")
        # el manual en una unidad mapeada: la letra cambia de un usuario a otro, la ruta de red no
        d = base / "unidad_mapeada"; d.mkdir()
        mapeados = [dict(v, Ruta=v["Ruta"].replace("C:\\Firma\\", "F:\\"),
                         RutaRed=(v["Ruta"].replace("C:\\Firma\\", "\\\\nas\\audit\\") if v["Tipo"] == "fichero" else ""))
                    for v in VINCULOS]
        escribir_fixture(d, vinculos=mapeados)
        codigo, _ = generar(d)
        Dm = datos_de(next((d / "salida").glob("*.html")).read_text(encoding="utf-8")) if codigo == 0 else {}
        Tm = {p["codigo"]: p for p in Dm.get("plantillas", [])}
        comprobar(Dm.get("carpeta_manual") == "\\\\nas\\audit\\Manual"
                  and Tm.get("C)AQ/01", {}).get("fichero", {}).get("abs") == "file://nas/audit/Manual/01%20Proc/C%29AQ_01%20Modelo%20uno.docx",
                  "con el manual en una unidad mapeada, la reserva usa la ruta de red, que vale para cualquier usuario")

        print("5 · los avisos")
        comprobar("1 riesgo(s) sin valorar" in texto, "avisa de los sin valorar")
        comprobar("1 riesgo(s) apuntan a una referencia no disponible" in texto, "avisa del enlace perdido")
        comprobar("1 procedimiento(s) sin texto en su guia" in texto and "E)01" in texto, "avisa del procedimiento sin texto")
        comprobar("1 plantilla(s) con el fichero vinculado que no se encuentra: C)AQ/02" in texto, "nombra la plantilla rota")
        comprobar("1 identificador(es) tapado(s)" in texto, "cuenta lo tapado por el barrido, no los colores")
        comprobar("riesgos en el mapa: 4 (Extremo 1, Alto 1, Medio 2)" in texto, "el resumen por nivel")
        comprobar("posterior a la de hoy" not in texto, "una publicacion anterior a hoy no avisa")
        d = base / "publicado_despues"; d.mkdir()
        escribir_fixture(d, manual=[dict(MANUAL[0], FechaPublicacion="26/10/26 0:00:00")])
        codigo, texto = generar(d)
        comprobar(codigo == 0 and "la fecha de publicacion del manual (26/10/2026) es posterior a la de hoy (24/10/2026)" in texto,
                  "una publicacion posterior a hoy: sale, y avisa")
        d = base / "version_con_v"; d.mkdir()
        escribir_fixture(d, manual=[dict(MANUAL[0], NombreFichero="Manual Ejemplo V1.14", Version="V1.2")])
        codigo, texto = generar(d)
        comprobar(codigo == 0 and "nombre: Manual Ejemplo V1.14.html" in texto,
                  "la version del campo no entra en el nombre: es el nombre del manual tal cual")
        comprobar("el nombre del manual dice version 1.14 y el campo Version de AudiQ dice 1.2" in texto,
                  "avisa si el nombre y el campo dicen versiones distintas")
        comprobar(datos_de(next((d / "salida").glob("*.html")).read_text(encoding="utf-8"))["version"] == "1.2",
                  "la version va sin su «v»: el subtitulo ya dice «Versión»")
        d = base / "qat"; d.mkdir()
        escribir_fixture(d, manual=[dict(MANUAL[0], TipoMDB="qat", Version="", FechaPublicacion="")])
        codigo, texto = generar(d)
        Dq = datos_de(next((d / "salida").glob("*.html")).read_text(encoding="utf-8")) if codigo == 0 else {}
        comprobar(codigo == 0 and Dq.get("version") == "" and Dq.get("publicado") == ""
                  and "posterior a la de hoy" not in texto and "campo Version" not in texto,
                  "un .qat, sin version ni fecha de publicacion: sale, sin avisos de version ni de fecha")
        comprobar('"Manual en trabajo, sin publicar"' in html, "y el subtitulo no deja «Versión » colgando")
        d = base / "sin_altos"; d.mkdir()
        escribir_fixture(d, riesgos=[riesgo(4, "Muy bajo", 1, 1, "")])
        codigo, texto = generar(d)
        comprobar(codigo == 0 and "ningun riesgo valorado de nivel medio o superior" in texto,
                  "sin riesgos de nivel medio: sale, y avisa")

        print("6 · el contrato")

        def para(nombre: str, motivo: str, **cambios) -> None:
            d = base / nombre; d.mkdir()
            escribir_fixture(d, **cambios)
            codigo, texto = generar(d)
            escrita = list((d / "salida").glob("*.html")) if (d / "salida").exists() else []
            comprobar(codigo == 2 and not escrita and motivo in texto, f"{nombre}: salida 2, sin pagina, y dice «{motivo}»")

        cambiado = [dict(x) for x in RIESGOS]; cambiado[0]["CodigoValorRIA_RIM"] = "4"
        para("nivel_cambiado", "no es el de la matriz", riesgos=cambiado)
        para("encargo", "no es un manual de calidad", manual=[dict(MANUAL[0], CodigoTipoFichero="3")])
        para("gesia", "no es un fichero de AudiQ", manual=[dict(MANUAL[0], Proyecto="Gesia", TipoMDB="Auditoria")])
        para("mcp_antiguo", "hace falta el MCP 1.27.0", vinculos=[{k: v for k, v in x.items() if k != "Bruto"} for x in VINCULOS])
        para("etiqueta", "no se llama «medio»",
             valores_ria=[dict(x, ValorRIA="Moderado") if x["CodigoValorRIA"] == "3" else x for x in VALORES_RIA])
        para("matriz_incompleta", "no es la 5x5", valores_ria=VALORES_RIA[:-1])
        fuera = [dict(x) for x in RIESGOS]; fuera[0]["CodigoValorRIA_RCI"] = "7"
        para("fuera_de_rango", "fuera de 1-5", riesgos=fuera)
        para("falta", "falta guias.json", guias=None)
        d = base / "fecha"; d.mkdir()
        escribir_fixture(d)
        codigo, _ = generar(d, fecha="24/10/2026")
        comprobar(codigo == 2, "fecha de generacion mal escrita: salida 2")

        print("7 · el SKILL.md")
        skill = SKILL_MD.read_text(encoding="utf-8")
        comprobar(all(f"{n}.json" in skill for n in g.FICHEROS), "pide los ocho ficheros que lee el script")
        comprobar('perfil = "manual-calidad"' in skill and 'limpiar_exportaciones(procedimiento = "manual-calidad")' in skill,
                  "perfil y limpieza")
        comprobar('entidad = "vinculos"' in skill, "los vinculos los exporta el MCP, que es quien ve el disco")
        comprobar("Add folder" in skill and "antes de exportar nada" in skill,
                  "en Cowork pide conectar la carpeta del manual al empezar, no al final")
        comprobar("not inside a folder" in skill and "dos carpetas" in skill,
                  "si no se puede, la entrega a mano da la ruta completa y los dos niveles")
        comprobar("**cualquier** fichero `.html`" in skill and "no la borres tú" in skill,
                  "pregunta por cualquier pagina anterior de la carpeta, se llame como se llame, y no la borra")
        comprobar("**por `CodigoGuia`**" in skill and "No por `CodigoReferencia`" in skill,
                  "dice donde buscar el texto de un procedimiento si preguntan despues")
        # del quinto registro de Cowork (25/10/2026)
        desc = " ".join(l.strip() for l in re.search(r"^description: >\n((?:  .*\n)+)", skill, re.M).group(1).splitlines())
        comprobar("cuadro de mando del manual" in desc and "SGCC" in desc and len(desc) <= 1024,
                  "la descripcion recoge «cuadro de mando del manual» y no pasa de 1024 caracteres")
        comprobar("mira antes de preguntar" in skill and "**un solo** `.qat`" in skill,
                  "busca el manual en la carpeta antes de pedir la ruta")
        comprobar("Failed to list" in skill and "no se ha podido comprobar si había una página anterior" in skill,
                  "un destino que no se deja listar ni escribir se entrega a mano, diciendo lo que no se comprobo")
        comprobar("Aparte, y no es de este procedimiento" in skill and "es **el último**" in skill,
                  "lo ajeno de la limpieza va en el mensaje de entrega, que es el ultimo")
        comprobar("Claude outputs" in skill and "no cambia: cambia al republicarlo" in skill,
                  "explica la copia del chat y de donde sale el nombre de la pagina")
        comprobar('rm -rf "$TRABAJO"' not in skill and 'rm -rf "<' in skill, "borra el directorio con ruta literal")
        comprobar("sellar_uso_ia" not in skill and "rehidratar" not in skill, "ni bloque de uso de IA ni nombres que recuperar")
        comprobar("AsistenteIA\\ManualCalidad\\" in skill and "g.PREFIJO_RELATIVO" not in skill and g.PREFIJO_RELATIVO == "../../",
                  "la carpeta de la pagina es la que dan por hecha los enlaces relativos")

    print()
    if FALLOS:
        print(f"FALLAN {len(FALLOS)}:")
        for f in FALLOS:
            print("   - " + f)
        return 1
    print("Todo bien.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
