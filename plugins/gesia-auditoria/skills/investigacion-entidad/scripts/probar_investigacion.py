# -*- coding: utf-8 -*-
"""Arnés de investigacion-entidad. No necesita Gesia, ni red, ni agentes.

    python probar_investigacion.py

Genera informes con contenido y evidencia SINTÉTICOS en una carpeta temporal del
sistema (nunca en el repositorio) y comprueba sobre el .docx que sale:

  - el validador del CIF: control, DNI/NIE y la forma por la letra;
  - que el contenido defectuoso aborta (salida 2) y no deja informe;
  - el apartado «Utilización de herramientas de inteligencia artificial»: existe, la
    cabecera lleva la marca, los huecos de la aplicación son exactamente los seis y
    cada uno en un solo run (sellar_uso_ia reemplaza dentro de document.xml), y los
    11 apartados del equipo salen vacíos;
  - que las comprobaciones de la herramienta dicen la verdad: sin «ATENCIÓN» cuando
    todo encaja, y con ella cuando falta la evidencia de un agente o el registro no
    es el de la letra del CIF;
  - que la copia de cada JSON de los agentes se coteja con su `recuento` (--comprobar y
    al generar): una copia cortada o que pierde fuentes o hechos para; sin recuento, sigue
    con ATENCIÓN;
  - que la sección 8 presenta sin URL las búsquedas web generales, con «—» las fuentes
    sin URL, y recoge los avisos de los agentes, y que el Word ya no remite a evidencia
    archivada (registro del 21/10/2026);
  - que el SKILL.md y los tres agentes dicen lo que el script espera: referencia desde
    `Referencias`, directorio de trabajo con ruta literal, recuento, URL vacía y avisos
    que no valoran;
  - que lib_uso_ia.py es idéntico en todos los skills que lo llevan.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from lib_uso_ia import (  # noqa: E402
    EFECTO, MARCA_DOCX, REVISION, TITULO, VERIFICACION, VERIFICADO)
from validar_cif import FORMAS, LETRAS_CONTROL_CIF, _control_cif, validar  # noqa: E402

HUECOS = ["aplicacion", "entorno", "informacion", "modelo", "plugin", "usuario"]
TMP = Path(tempfile.mkdtemp(prefix="probar-investigacion-"))


def cif_sintetico(letra: str, digitos: str = "1234567") -> str:
    """Un CIF con el control bien calculado: dígito para A/B, letra para G."""
    c = _control_cif(digitos)
    return letra + digitos + (LETRAS_CONTROL_CIF[c] if letra in "PQRSNW" else str(c))


CIF_A = cif_sintetico("A")
REG_A = FORMAS["A"][1]


def contenido_bueno() -> dict:
    return {
        "identificacion": [{"campo": "Forma jurídica", "valor": "Sociedad anónima"}],
        "secciones": {
            "societaria": [{"texto": "Constituida en 2001.", "marca": "✓",
                            "fuente": "BORME-A-2001-1-01"}],
            "actividad": [{"texto": "Sin CNAE en fuente citable.", "marca": "○"}],
            "sector_publico": [{"texto": "Dos contratos adjudicados.", "marca": "✓",
                                "fuente": "PLACE"}],
            "riesgos_legales": [{"texto": "Sin resoluciones localizadas.", "marca": "○"}],
            "analisis": [{"texto": "Actividad y contratos coherentes.", "marca": "⚠",
                          "incertidumbre": "media", "fuente": "hechos 2.1 y 4.1"}],
        },
        "limitaciones_catalogo": ["borme_sin_historico", "place_sin_api"],
        "limitaciones_especificas": ["Ninguna propia de la entidad."],
    }


# El aviso sintetico del societario: describe la busqueda, como pide el contrato.
AVISO = "La consulta gratuita del registro no devuelve el histórico de actos."


def evidencia(nombre: str, avisos=(), *, recuento=True, declaradas=None, hechos=None,
              fuentes_extra=(), crudo=None, sufijo="") -> Path:
    """El JSON de un agente tal como el modelo lo copia al directorio de trabajo. Lleva el
    `recuento` del contrato salvo `recuento=False`; `declaradas` y `hechos` lo descuadran a
    proposito, y `crudo` escribe el texto tal cual (una copia cortada)."""
    ruta = TMP / (nombre + sufijo + ".json")
    if crudo is not None:
        ruta.write_text(crudo, encoding="utf-8")
        return ruta
    fuentes = [
        {"nombre": "Fuente " + nombre, "url": "https://ejemplo.invalid/" + nombre,
         "fecha_consulta": "2026-10-19", "resultado": "con datos"},
        {"nombre": "Otra " + nombre, "url": "", "fecha_consulta": "2026-10-19",
         "resultado": "sin datos"}] + list(fuentes_extra)
    datos = {"fuentes_consultadas": fuentes, "avisos": list(avisos)}
    n_hechos = 0
    if nombre == "societario":
        datos["administradores"] = [{"nombre": "X", "cargo": "Administrador único"}]
        datos["constitucion"] = None
        n_hechos = 1
    if recuento:
        datos = {"recuento": {"fuentes_consultadas": len(fuentes) if declaradas is None
                              else declaradas,
                              "hechos": n_hechos if hechos is None else hechos}, **datos}
    ruta.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    return ruta


OPCIONES = (("--evidencia-societario", "societario"),
            ("--evidencia-sector-publico", "sector-publico"),
            ("--evidencia-riesgos", "riesgos-legales"))


def _args_evidencia(sin=(), retoque=None, sufijo="") -> list:
    """Las tres --evidencia-*; `retoque` = {bloque: kwargs de evidencia()} para estropear una."""
    args = []
    for opcion, bloque in OPCIONES:
        if bloque not in sin:
            kw = {"avisos": [AVISO] if bloque == "societario" else ()}
            kw.update((retoque or {}).get(bloque, {}))
            args += [opcion, str(evidencia(bloque, sufijo=sufijo, **kw))]
    return args


def _lanzar(args: list):
    r = subprocess.run([sys.executable, str(AQUI / "generar_informe.py"), *args],
                       capture_output=True, text=True, encoding="utf-8",
                       env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    return r.returncode, r.stdout + r.stderr


def generar(nombre: str, contenido: dict, *, cif=CIF_A, registro=REG_A,
            sin=(), origen="BORME (enlace), confirmado por el usuario", retoque=None):
    """Lanza generar_informe.py como lo lanza el skill. Devuelve (código, ruta, salida)."""
    ruta_c = TMP / (nombre + "-contenido.json")
    ruta_c.write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")
    salida = TMP / (nombre + ".docx")
    args = ["--contenido", str(ruta_c),
            "--cliente", "ENTIDAD DE PRUEBA, S.A.", "--cif", cif, "--cif-origen", origen,
            "--registro", registro, "--cierre", "31/12/25",
            "--ventana", "31/12/2020 - 19/10/2026", "--generado", "2026-10-19",
            "--ref", "", "--salida", str(salida)]
    codigo, out = _lanzar(args + _args_evidencia(sin, retoque, sufijo="-" + nombre))
    return codigo, salida, out


def comprobar(nombre: str, retoque=None):
    """`generar_informe.py --comprobar`, como va tras copiar los JSON. (código, salida)."""
    return _lanzar(["--comprobar"] + _args_evidencia(retoque=retoque, sufijo="-" + nombre))


def tabla_fuentes(ruta: Path) -> list:
    """Las filas de la tabla de la sección 8: [bloque, fuente, url, fecha, resultado]."""
    for t in _doc(ruta).tables:
        if [c.text for c in t.rows[0].cells] == ["Bloque", "Fuente", "URL", "Fecha consulta",
                                                 "Resultado"]:
            return [[c.text for c in r.cells] for r in t.rows[1:]]
    return []


def parrafos(ruta: Path) -> list:
    return [p.text for p in _doc(ruta).paragraphs]


def _doc(ruta: Path):
    import docx
    return docx.Document(str(ruta))


def runs_de_tablas(d) -> list:
    return [r.text for t in d.tables for row in t.rows for c in row.cells
            for p in c.paragraphs for r in p.runs]


def huecos(ruta: Path) -> list:
    return sorted(m.group(1) for t in runs_de_tablas(_doc(ruta))
                  for m in re.finditer(r"⟦IA:([a-z_]+)[^⟧]*⟧", t))


def apartado_existe(ruta: Path) -> bool:
    d = _doc(ruta)
    titulo = any(p.text == TITULO and p.style.name.startswith("Heading") for p in d.paragraphs)
    marca = any(r.cells[0].text == "Uso de IA" and r.cells[1].text == MARCA_DOCX
                for r in d.tables[0].rows)
    return titulo and marca


def celdas_equipo(ruta: Path):
    etiquetas = {e for e, _ in VERIFICACION + VERIFICADO + EFECTO + REVISION}
    filas = [r for t in _doc(ruta).tables for r in t.rows
             if len(r.cells) == 2 and r.cells[0].text in etiquetas]
    return len(filas), sum(1 for r in filas if r.cells[1].text.strip())


def comprobaciones(ruta: Path) -> list:
    """Las líneas «· …» del apartado 4 del bloque."""
    return [t[2:] for t in runs_de_tablas(_doc(ruta)) if t.startswith("· ")]


def copias_iguales() -> bool:
    propia = AQUI / "lib_uso_ia.py"
    otras = [p for p in propia.parents[2].glob("*/scripts/lib_uso_ia.py")
             if p.resolve() != propia.resolve()]
    return bool(otras) and all(p.read_bytes() == propia.read_bytes() for p in otras)


def casos():
    # El validador del CIF
    yield ("un CIF sintético con el control bien calculado es válido",
           lambda: validar(CIF_A)[:2] == ("cif", True))
    yield ("el mismo CIF con el control cambiado no vale",
           lambda: not validar(CIF_A[:-1] + str((int(CIF_A[-1]) + 1) % 10))[1])
    yield ("un DNI se reconoce como DNI, no como CIF",
           lambda: validar("12345678Z")[0] == "dni")
    yield ("una G (fundación o asociación) no va al BORME",
           lambda: FORMAS["G"][2] is False and "BORME" not in FORMAS["G"][1])

    # El contenido defectuoso aborta y no deja informe
    malo = contenido_bueno()
    malo["secciones"]["societaria"][0]["fuente"] = ""
    yield ("un hecho ✓ sin fuente aborta con salida 2 y no escribe el informe",
           lambda: (lambda r: r[0] == 2 and not r[1].exists())(generar("malo", malo)))
    raro = contenido_bueno()
    raro["limitaciones_catalogo"] = ["inventada"]
    yield ("un id de limitación fuera del catálogo aborta",
           lambda: generar("raro", raro)[0] == 2)

    # El informe bueno y su apartado de uso de IA
    codigo, bueno, salida = generar("bueno", contenido_bueno())
    yield ("el informe bueno se genera (salida 0)", lambda: codigo == 0 and bueno.exists())
    yield ("(a) el apartado de uso de IA existe y la cabecera lleva la marca",
           lambda: apartado_existe(bueno))
    yield ("(b) los huecos de la aplicación son exactamente los seis, cada uno en un solo run",
           lambda: huecos(bueno) == HUECOS)
    yield ("(c) los 11 apartados del equipo salen vacíos: ni una pista dentro",
           lambda: celdas_equipo(bueno) == (11, 0))
    yield ("con todo en orden, ninguna comprobación dice ATENCIÓN",
           lambda: comprobaciones(bueno) and
           not any("ATENCIÓN" in c for c in comprobaciones(bueno)))
    yield ("las comprobaciones cuentan lo que lleva el papel: 2 hechos, 1 indicio, 2 sin información",
           lambda: any("Hechos verificados (✓): 2," in c and "indicios (⚠): 1;" in c
                       and "sin información (○): 2." in c for c in comprobaciones(bueno)))
    yield ("y la sección 8 desde la evidencia: 6 fuentes, 3 con datos; 1 aviso del societario",
           lambda: any("Fuentes: 6; con datos: 3." in c for c in comprobaciones(bueno))
           and any("Avisos de los agentes: 1 (societario 1)" in c for c in comprobaciones(bueno)))
    # La evidencia JSON ya no se archiva (registro del 21/10/2026): lo que acreditaba tiene
    # que estar en el papel, y el papel no puede decir que hay JSON junto a el.
    yield ("el aviso del agente consta tal cual en la sección 8 del Word",
           lambda: "· Societario: " + AVISO in parrafos(bueno))
    yield ("y el Word no remite a una evidencia archivada ni a la subcarpeta «evidencia»",
           lambda: not any("archivad" in t or "«evidencia»" in t
                           for t in parrafos(bueno) + runs_de_tablas(_doc(bueno))))
    yield ("una fuente sin URL que no es búsqueda sale con «—», no con la celda vacía",
           lambda: ["Societario", "Otra societario", "—", "2026-10-19", "sin datos"]
           in tabla_fuentes(bueno))

    # Las copias de los JSON se cotejan con el recuento que declara el agente
    yield ("--comprobar con las tres copias buenas: salida 0 y dice que cuadran",
           lambda: (lambda r: r[0] == 0 and "cuadran" in r[1])(comprobar("cuadra")))
    yield ("una copia que ha perdido una fuente: --comprobar sale con 2 y lo dice",
           lambda: (lambda r: r[0] == 2 and "tiene 2 fuentes y el agente declaró 3" in r[1])(
               comprobar("pierde", {"sector-publico": {"declaradas": 3}})))
    yield ("y el informe tampoco se genera con esa copia",
           lambda: (lambda r: r[0] == 2 and not r[1].exists())(
               generar("pierde", contenido_bueno(), retoque={"sector-publico": {"declaradas": 3}})))
    yield ("una copia con los hechos descuadrados también para",
           lambda: (lambda r: r[0] == 2 and "hechos y el agente declaró 2" in r[1])(
               comprobar("hechos", {"societario": {"hechos": 2}})))
    yield ("una copia cortada que no carga como JSON para, y pide volver a copiarla",
           lambda: (lambda r: r[0] == 2 and "no carga" in r[1] and "vuelve a copiar" in r[1])(
               comprobar("cortada", {"riesgos-legales": {"crudo": '{"fuentes_consultadas": [{"nom'}})))
    _, sin_rec, _ = generar("sin-recuento", contenido_bueno(),
                            retoque={"riesgos-legales": {"recuento": False}})
    yield ("un agente que no declara recuento no aborta, pero el papel lo dice con ATENCIÓN",
           lambda: sin_rec.exists() and any(
               c.startswith("ATENCIÓN: el agente de riesgos legales no declaró recuento")
               for c in comprobaciones(sin_rec)))

    # Una busqueda web general va sin URL (contrato de los agentes, registro del 21/10/2026)
    busquedas = [{"nombre": "Búsqueda web general: «ENTIDAD» sentencia",
                  "url": "https://ejemplo.invalid/ficha-de-otra-cosa",
                  "fecha_consulta": "2026-10-19", "resultado": "sin datos"},
                 {"nombre": "Búsqueda web general: «ENTIDAD» juzgado", "url": "",
                  "fecha_consulta": "2026-10-19", "resultado": "sin datos"}]
    _, con_busq, _ = generar("busquedas", contenido_bueno(),
                             retoque={"riesgos-legales": {"fuentes_extra": busquedas}})
    yield ("una búsqueda web general sale sin URL en la sección 8, aunque el agente pusiera una",
           lambda: [f[2] for f in tabla_fuentes(con_busq) if f[1].startswith("Búsqueda web")]
           == ["— (búsqueda general, sin página concreta)"] * 2
           and not any("ficha-de-otra-cosa" in f[2] for f in tabla_fuentes(con_busq)))
    yield ("y la URL quitada consta con ATENCIÓN en las comprobaciones",
           lambda: any(c.startswith("ATENCIÓN: 1 búsquedas web generales traían la URL")
                       for c in comprobaciones(con_busq)))
    yield ("lo facilitado que el MCP no ve consta: denominación y CIF a internet por los agentes",
           lambda: any("agentes de búsqueda" in t and "denominación y el CIF" in t
                       for t in runs_de_tablas(_doc(bueno))))

    # Las comprobaciones que fallan lo dicen
    _, degradado, _ = generar("degradado", contenido_bueno(), sin=("riesgos-legales",))
    yield ("sin la evidencia de un agente, la comprobación lo dice con ATENCIÓN",
           lambda: any(c.startswith("ATENCIÓN: sin evidencia del agente de riesgos legales")
                       for c in comprobaciones(degradado)))
    _, otro_reg, _ = generar("otro-registro", contenido_bueno(), registro=FORMAS["G"][1])
    yield ("un registro que no es el de la letra del CIF sale con ATENCIÓN",
           lambda: any(c.startswith("ATENCIÓN: el registro citado")
                       for c in comprobaciones(otro_reg)))
    sin_inc = contenido_bueno()
    del sin_inc["secciones"]["analisis"][0]["incertidumbre"]
    _, sin_i, _ = generar("sin-incertidumbre", sin_inc)
    yield ("un indicio sin incertidumbre sale con ATENCIÓN",
           lambda: any(c.startswith("ATENCIÓN: 1 de 1 indicios") for c in comprobaciones(sin_i)))

    yield ("lib_uso_ia.py es idéntico en todos los skills que lo llevan",
           lambda: copias_iguales())

    # El SKILL.md y los agentes (registro del 21/10/2026)
    skill_md = (AQUI.parent / "SKILL.md").read_text(encoding="utf-8")
    yield ("el SKILL.md no archiva la evidencia JSON ni la baja con device_commit_files",
           lambda: "evidencia\\" not in skill_md and "<los tres JSON>" not in skill_md
           and "--comprobar" in skill_md)
    yield ("el SKILL.md busca la referencia en Referencias y comprueba el código que dé el usuario",
           lambda: "FROM Referencias" in skill_md
           and "WHERE CodigoReferencia = '<el código que ha dado>'" in skill_md
           and not re.search(r"\b[A-Z]{1,3}\)\d", skill_md))
    yield ("el SKILL.md imprime la ruta del directorio de trabajo y la borra con la ruta literal",
           lambda: '&& echo "$TRABAJO"' in skill_md
           and 'rm -rf "<la ruta que anotaste>"' in skill_md
           and 'rm -rf "$TRABAJO"' not in skill_md and 'rm -rf "$(cat' not in skill_md)
    for agente in ("investigador-societario", "investigador-sector-publico",
                   "investigador-riesgos-legales"):
        yield ("el contrato de " + agente + " pide recuento, URL vacía en búsquedas y avisos "
               "que no valoran",
               lambda a=agente: (lambda t: '{\n  "recuento": {"fuentes_consultadas"' in t
                                 and "`url` va vacía" in t
                                 and "nunca la valoran ni aconsejan" in t)(
                   (AQUI.parents[2] / "agents" / (a + ".md")).read_text(encoding="utf-8")))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    fallos = 0
    try:
        for nombre, prueba in casos():
            try:
                bien = bool(prueba())
            except Exception as exc:                       # noqa: BLE001
                bien, nombre = False, nombre + "  [" + type(exc).__name__ + ": " + str(exc)[:80] + "]"
            print(("  ok   " if bien else "  FALLA ") + nombre)
            fallos += 0 if bien else 1
    finally:
        shutil.rmtree(TMP, ignore_errors=True)
    print("\n" + ("Todo bien." if not fallos else str(fallos) + " comprobación(es) fallan."))
    return 0 if not fallos else 1


if __name__ == "__main__":
    sys.exit(main())
