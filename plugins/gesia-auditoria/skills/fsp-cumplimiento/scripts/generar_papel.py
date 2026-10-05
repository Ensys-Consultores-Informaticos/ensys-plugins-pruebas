"""Escribe el papel de trabajo de la prueba de cumplimiento en Excel.

    python generar_papel.py --muestra muestra.json --parametros parametros.json \
        --facturas facturas.json --roles roles.json [--evaluacion evaluacion.json] \
        [--manifiesto manifiesto.json] [--carpeta-documentos C] \
        --salida "<expediente>/AsistenteIA/FspCumplimiento/Cumplimiento <PRUEBA> <CLIENTE> <EJERCICIO>.xlsx" \
        --generado 2026-09-02

Una sola hoja, «Analisis muestra», en cuatro zonas de color con su banda de
titulo: A los datos de la muestra, B el documento localizado y lo leido en el
(numero, fecha, CIF, tercero, concepto, base, IVA, retencion, total), C una
columna por atributo EN BLANCO y la observacion propuesta para ForSampling, y D
la evidencia del cruce. La celda del fichero es un HIPERVINCULO al documento.

Las columnas de atributos van vacias a proposito: el skill no marca Ok ni pone
'auditor', las deja para quien firma y cuenta lo que ha visto en la observacion.

El tinte de cada zona es flojo a proposito: el amarillo de la observacion -que
seña la que ahi hay algo que contar- tiene que seguir cantando por encima. Es el
mismo formato que el papel de la MUM, decidido con el auditor el 17/09/2026.

Lo que no cabe en la hoja se imprime al ejecutar: los recuentos, los elementos
con hallazgo, los documentos que no son de ningun elemento y, si se paso
--evaluacion, la comparacion con lo que puso el auditor. Leelo antes de entregar.

No usa formulas: todo se calcula aqui y se escribe como valor, para que el papel
se lea igual en Cowork y en la maquina del auditor. Y no lee el reloj: la fecha
de generacion entra por --generado, para que el papel se pueda regenerar identico.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_fsp import (  # noqa: E402
    ROL_AUDITOR,
    TOL_IMPORTE,
    TOL_IVA,
    VENTANA_DIAS,
    cargar_evaluacion,
    cargar_facturas,
    cargar_json,
    cargar_muestra,
    cargar_parametros,
    comparar_con_auditor,
    cruzar,
    columnas_de_muestra,
    evaluar,
    parse_fecha,
    parse_importe,
    proponer_roles,
    rutas_documentos,
    salida_utf8,
)

FONT = "Arial"
FORMATO_EURO = '#,##0.00 "€";-#,##0.00 "€";"-"'
FORMATO_FECHA = "DD/MM/YYYY"
AMARILLO = PatternFill("solid", fgColor="FFFF00")
AZUL_ENLACE = "0563C1"

# Una zona por bloque de columnas: (titulo de la banda, color de cabecera, tinte
# de los datos). El mismo esquema que el papel de la MUM, con la zona C cambiada:
# alli es la medida del muestreo y aqui son los atributos, que van en blanco.
ZONAS_DEF = {
    "muestra": ("A · Datos de la muestra", "1F4E78", None),
    "documento": ("B · Datos del documento", "217346", "EAF3EC"),
    "prueba": ("C · Atributos de la prueba", "C55A11", "FDF0E6"),
    "cruce": ("D · Evidencia del cruce", "7F7F7F", "F2F2F2"),
}

# «Proveedor o cliente» lleva lo que el documento diga: la razon social si la factura va en
# claro, y el TOKEN del sello si va tachada -que `rehidratar` convierte en el nombre real al
# entregar-. El CIF, con la factura tachada, se queda vacio: esta en negro y no se restaura,
# porque el diccionario indexa por cuenta y no por CIF.
COL_DOCUMENTO = ["Fichero", "Nº factura", "Fecha doc.", "CIF", "Proveedor o cliente", "Concepto",
                 "Base", "IVA", "IRPF", "Total"]
# «Días libros–doc.» es fecha de libros menos fecha del documento, que es como lo calcula
# lib_fsp y como lo rotula la MUM. Antes ponia «Días doc.–libros», al reves de lo que era.
COL_CRUCE = ["Casa por", "Diferencia importe", "Días libros–doc."]

_BORDE_LADO = Side(style="thin", color="BFBFBF")
BORDE = Border(left=_BORDE_LADO, right=_BORDE_LADO, top=_BORDE_LADO, bottom=_BORDE_LADO)

NOMBRES_ROL = {
    "documento": "el skill comprueba que el documento existe y es el del apunte",
    "calculo": ("el skill comprueba la aritmética del documento: base + IVA = total, "
                "y con retención de IRPF o exención, la que corresponda"),
    "contabilizacion": "el skill compara importe y fecha del documento con los de libros",
    "auditor": "queda al auditor: no se infiere del documento",
}


def _bandas(ws, fila: int, tramos: list[tuple[str, str, int, int]]) -> None:
    """La fila de titulos de zona, cada uno combinado sobre sus columnas."""
    for titulo, color, desde, hasta in tramos:
        for j in range(desde, hasta + 1):
            c = ws.cell(row=fila, column=j)
            c.fill = PatternFill("solid", fgColor=color)
            c.border = BORDE
        if hasta > desde:
            ws.merge_cells(start_row=fila, start_column=desde, end_row=fila, end_column=hasta)
        c = ws.cell(row=fila, column=desde, value=titulo)
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.alignment = Alignment(horizontal="center", vertical="center")


def _cabecera(ws, fila: int, textos: list[str], colores: list[str]) -> None:
    for j, (t, color) in enumerate(zip(textos, colores), start=1):
        c = ws.cell(row=fila, column=j, value=t)
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = PatternFill("solid", fgColor=color)
        c.border = BORDE
        c.alignment = Alignment(vertical="center", wrap_text=True)


def _ficha_muestreo(pr: dict) -> str:
    """Los parametros del muestreo para la linea de contexto, con los nombres que traiga
    DatosMuestreos. Se buscan por patron y no por nombre exacto porque cada tipo de prueba
    de ForSampling los llama a su manera; lo que no este, no se enseña."""
    import re as _re
    trozos = []
    for etiqueta, patron in (("tamaño de muestra", r"tama[nñ]o.*muestra|muestra.*tama[nñ]o"),
                             ("población", r"poblacion.*(num|elementos)|num.*elementos"),
                             ("desviación tolerable", r"(tasa|desviacion).*tolerable|tolerable.*(tasa|desviacion)"),
                             ("desviación esperada", r"(tasa|desviacion).*esperad|esperad.*(tasa|desviacion)"),
                             ("confianza", r"confianza|fiabilidad")):
        k = next((k for k in pr if _re.search(patron, str(k).lower())), None)
        v = pr.get(k) if k else None
        if v not in (None, ""):
            trozos.append(f"{etiqueta} {v}")
    return " · ".join(trozos)


def _anchos(ws, anchos: dict[int, float]) -> None:
    for col, w in anchos.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def _hoja_muestra(wb: Workbook, evaluados: list[dict], cols: dict, atributos: list[dict],
                  roles: dict, params: dict, generado: str,
                  rutas: dict[str, str] | None = None) -> None:
    """La unica hoja del papel: un elemento por fila, en cuatro zonas de color.

    **Las columnas de atributos van en blanco a proposito.** El skill no marca
    Ok ni escribe 'auditor' en ellas: las deja para que las rellene quien firma,
    y dice lo que ha visto en la observacion, que es el texto que se copia a
    ForSampling. Decision del auditor el 03/09/2026, y es el modelo de partida.
    Por eso la zona C es la de los atributos y no la medida del muestreo, que es
    lo que ocupa ese sitio en el papel de la MUM: alli un importe segun el
    documento es una medida, y aqui un atributo es un veredicto.

    Lo que se cuenta y no cabe en la hoja -recuentos, documentos que no son de
    ningun elemento, comparacion con la evaluacion del auditor- se imprime al
    ejecutar. No se pierde: cambia de sitio.
    """
    ws = wb.active
    ws.title = "Análisis muestra"
    if not evaluados:
        ws["A1"] = "La muestra no trae elementos."
        return

    pr = params.get("parametros") or {}

    def _dia(v):
        d = parse_fecha(v)
        return d.strftime("%d/%m/%Y") if d else (str(v) if v else "—")

    col_pob = [c for c in evaluados[0]["fila"].keys() if c.lower() not in ("seleccionado",)]
    col_att = [f"A{a.get('AtributoId')} {a.get('Nombre')}" for a in atributos] + ["Observación propuesta"]
    cab = col_pob + COL_DOCUMENTO + col_att + COL_CRUCE

    # Donde empieza cada zona, para las bandas, las formulas y los formatos
    n_pob, n_doc, n_att, n_cruce = len(col_pob), len(COL_DOCUMENTO), len(col_att), len(COL_CRUCE)
    ini_doc = n_pob + 1
    ini_att = ini_doc + n_doc
    c_obs = ini_att + n_att - 1
    ini_cruce = ini_att + n_att
    c_fecha_doc = ini_doc + 2
    c_casa, c_dif, c_dias = ini_cruce, ini_cruce + 1, ini_cruce + 2
    col_fecha_pob = (col_pob.index(cols["fecha"]) + 1) if cols.get("fecha") in col_pob else None

    colores = ([ZONAS_DEF["muestra"][1]] * n_pob + [ZONAS_DEF["documento"][1]] * n_doc
               + [ZONAS_DEF["prueba"][1]] * n_att + [ZONAS_DEF["cruce"][1]] * n_cruce)
    tintes = ([ZONAS_DEF["muestra"][2]] * n_pob + [ZONAS_DEF["documento"][2]] * n_doc
              + [ZONAS_DEF["prueba"][2]] * n_att + [ZONAS_DEF["cruce"][2]] * n_cruce)

    ficha = _ficha_muestreo(pr)
    ws["A1"] = f"Análisis de la muestra — {params.get('Prueba') or 'prueba de cumplimiento'}"
    ws["A1"].font = Font(name=FONT, bold=True, size=13)
    ws["A2"] = (f"Prueba {params.get('MuestraId')} · {params.get('Tipo')} · área {params.get('Area')} · "
                f"ref. {params.get('Referencia')} · ejercicio "
                f"{_dia(params.get('FechaInicioAuditoria'))} — {_dia(params.get('FechaFinAuditoria'))} · "
                + (ficha + " · " if ficha else "") + f"generado {generado}")
    ws["A2"].font = Font(name=FONT, size=9)
    ws["A3"] = ("Propuesta del asistente: localiza cada documento y comprueba lo que se puede comprobar desde él. "
                "Las columnas de atributos se dejan en blanco para el auditor, que es quien concluye y firma.")
    ws["A3"].font = Font(name=FONT, italic=True, size=9, color="595959")
    ws["A4"] = ("Amarillo: la observación señala algo. Este papel no prueba que el documento sea auténtico, ni que "
                "el gasto estuviera autorizado, ni que el registro fuera oportuno: nada de eso está en la factura.")
    ws["A4"].font = Font(name=FONT, italic=True, size=9, color="595959")

    _bandas(ws, 6, [(ZONAS_DEF["muestra"][0], ZONAS_DEF["muestra"][1], 1, n_pob),
                    (ZONAS_DEF["documento"][0], ZONAS_DEF["documento"][1], ini_doc, ini_doc + n_doc - 1),
                    (ZONAS_DEF["prueba"][0], ZONAS_DEF["prueba"][1], ini_att, ini_att + n_att - 1),
                    (ZONAS_DEF["cruce"][0], ZONAS_DEF["cruce"][1], ini_cruce, len(cab))])
    _cabecera(ws, 7, cab, colores)

    L = get_column_letter
    fila = 8
    for e in evaluados:
        f, fac, c, res = e["fila"], e["factura"], e["criterios"], e["resultados"]
        valores = []
        # Las fechas van como FECHA, no como texto: asi se ordenan y se filtran, y la
        # diferencia de dias es una resta de celdas. Si alguna no se puede interpretar se
        # deja el texto tal cual y esa fila se queda sin formula.
        fecha_libros = fecha_doc = None
        for k in col_pob:
            v = f.get(k)
            if k == cols.get("importe"):
                v = parse_importe(v)
            elif k == cols.get("fecha"):
                fecha_libros = parse_fecha(v)
                v = fecha_libros or v
            valores.append(v)

        if fac:
            fecha_doc = parse_fecha(fac.get("fecha"))
            valores += [fac.get("fichero"), fac.get("numero"), fecha_doc or fac.get("fecha"),
                        fac.get("cif"), fac.get("proveedor") or fac.get("token"), fac.get("concepto"),
                        parse_importe(fac.get("base")), parse_importe(fac.get("iva")),
                        parse_importe(fac.get("irpf")), parse_importe(fac.get("total"))]
        else:
            valores += ["— no localizada"] + [None] * (n_doc - 1)

        valores += [None] * len(atributos)          # en blanco: las rellena el auditor
        valores.append(e["observacion"])

        if fac:
            casa = ", ".join(x for x, b in (("número", c["numero"]), ("tercero", c.get("tercero")),
                                            (f"importe ({c['importe']})", c["importe"]),
                                            ("fecha", c["fecha"])) if b)
            if fecha_libros and fecha_doc and col_fecha_pob:
                dias = f'=IFERROR({L(col_fecha_pob)}{fila}-{L(c_fecha_doc)}{fila},"")'
            else:
                dias = c["dias"]   # sin dos fechas de verdad no hay resta que hacer
            valores += [casa, c["diferencia"], dias]
        else:
            valores += ["", None, None]

        for j, v in enumerate(valores, start=1):
            cell = ws.cell(row=fila, column=j, value=v)
            cell.font = Font(name=FONT, size=9)
            cell.border = BORDE
            cell.alignment = Alignment(vertical="top", wrap_text=j == c_obs)
            if tintes[j - 1]:
                cell.fill = PatternFill("solid", fgColor=tintes[j - 1])
            if isinstance(v, float):
                cell.number_format = FORMATO_EURO
        # el fichero, enlazado al documento. Despues del bucle, que fija la fuente.
        enlace = (rutas or {}).get((fac or {}).get("fichero"))
        if enlace:
            cel = ws.cell(row=fila, column=ini_doc)
            cel.hyperlink = enlace
            cel.font = Font(name=FONT, size=9, color=AZUL_ENLACE, underline="single")
        for col in range(ini_doc + 6, ini_doc + n_doc):
            ws.cell(row=fila, column=col).number_format = FORMATO_EURO
        ws.cell(row=fila, column=c_dif).number_format = FORMATO_EURO
        ws.cell(row=fila, column=c_dias).number_format = "0"
        for col in (col_fecha_pob, c_fecha_doc):
            if col:
                ws.cell(row=fila, column=col).number_format = FORMATO_FECHA
        if any(v != "auditor" and not v.startswith("Ok") for v in res.values()):
            ws.cell(row=fila, column=c_obs).fill = AMARILLO
        fila += 1

    ws.auto_filter.ref = f"A7:{L(len(cab))}{fila - 1}"
    ws.freeze_panes = "A8"
    anchos = {i + 1: 14 for i in range(len(cab))}
    for i, k in enumerate(col_pob, start=1):
        if k in (cols.get("tercero"), "Acreedor"):
            anchos[i] = 30
    anchos[ini_doc] = 34                      # Fichero
    anchos[ini_doc + 4] = 30                  # Proveedor o cliente
    anchos[ini_doc + 5] = 40                  # Concepto
    for k in range(len(atributos)):
        anchos[ini_att + k] = 12
    anchos[c_obs] = 95
    anchos[c_casa] = 26
    _anchos(ws, anchos)

def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--muestra", required=True)
    p.add_argument("--parametros", required=True)
    p.add_argument("--facturas", required=True)
    p.add_argument("--roles", help="{AtributoId: rol} confirmado por el auditor; sin él, la propuesta automática")
    p.add_argument("--evaluacion", help="exportar_consulta(entidad='evaluacion', id=N), para comparar")
    p.add_argument("--manifiesto", help="manifiesto.json de preparar_documentos.py: de ahí sale la "
                                        "ruta de cada documento para el hipervínculo")
    p.add_argument("--carpeta-documentos", dest="carpeta_documentos",
                   help="carpeta de los escaneos EN LA MÁQUINA DEL AUDITOR. Manda sobre el "
                        "manifiesto: en Cowork la ruta del contenedor no le sirve de nada")
    p.add_argument("--salida", required=True)
    p.add_argument("--generado", required=True, help="fecha de generación, AAAA-MM-DD. Nada lee el reloj")
    args = p.parse_args()

    muestra = cargar_muestra(args.muestra)
    params = cargar_parametros(args.parametros)
    facturas = cargar_facturas(args.facturas)
    atributos = params.get("atributos") or []
    roles = cargar_json(args.roles) if args.roles else proponer_roles(atributos)
    roles = {str(k): v for k, v in roles.items()}
    evaluacion = cargar_evaluacion(args.evaluacion)

    cols, _, _ = columnas_de_muestra(muestra)
    cruce = cruzar(muestra, facturas, cols)
    evaluados = evaluar(cruce, cols, atributos, roles)
    comp = comparar_con_auditor(evaluados, evaluacion, cols, atributos)

    rutas = rutas_documentos(args.manifiesto, args.carpeta_documentos)

    wb = Workbook()
    _hoja_muestra(wb, evaluados, cols, atributos, roles, params, args.generado, rutas)

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(salida)
    except PermissionError:
        print(f"ERROR: no se puede escribir {salida}. Si está abierto en Excel, ciérralo y repite.")
        return 2

    con_doc = sum(1 for e in evaluados if e["factura"])
    hall = sum(1 for e in evaluados for v in e["resultados"].values() if v != "auditor" and not v.startswith("Ok"))
    print(f"Papel escrito: {salida}")
    if rutas:
        enlazados = [e for e in evaluados if e["factura"] and rutas.get(e["factura"].get("fichero"))]
        rotos = [e for e in enlazados if not Path(rutas[e["factura"]["fichero"]]).exists()]
        print(f"  documentos enlazados {len(enlazados)} de {con_doc}")
        if rotos:
            print(f"  AVISO: {len(rotos)} vínculo(s) apuntan a rutas que este proceso no ve. Si los "
                  f"scripts corren en un contenedor es lo normal y en la máquina del auditor "
                  f"funcionarán; si no, pásale --carpeta-documentos con la ruta buena y repite")
    else:
        print("  sin hipervínculos: no se ha indicado --manifiesto ni --carpeta-documentos")
    print(f"  elementos {len(evaluados)} · con documento {con_doc} · sin documento {len(evaluados) - con_doc}"
          f" · documentos sin elemento {len(cruce['facturas_sin_fila'])} · celdas con hallazgo {hall}")
    for par in cruce.get("candidatos_sueltos") or []:
        print(f"  · POSIBLE DIFERENCIA, no extravío: el elemento {par['id']} quedó sin documento y "
              f"{par['fichero']} sin elemento"
              + (", mismo tercero" if par["tercero"] else "")
              + (f", {par['dias']} día(s) de diferencia" if par["dias"] is not None else "")
              + (f". En libros {par['importe_libros']}, en el documento base {par['base']} / total "
                 f"{par['total']}: diferencia mínima {par['diferencia_minima']}"
                 if par["diferencia_minima"] is not None else "")
              + ". Revísalo a mano: si son el mismo, hay una diferencia real que declarar con "
                "poblacion_id en facturas.json")
    for fac in cruce["facturas_sin_fila"]:
        print(f"  · documento que no es de ningún elemento de la muestra: {fac.get('fichero')}"
              f" ({fac.get('proveedor') or '—'}, {fac.get('total') or '—'})")
    for e in evaluados:
        if any(v != "auditor" and not v.startswith("Ok") for v in e["resultados"].values()):
            ident = e["fila"].get(cols.get("id"), "?")
            print(f"  · elemento {ident}: " + " | ".join(f"A{k}: {v}" for k, v in e["resultados"].items()
                                                         if v != "auditor" and not v.startswith("Ok")))
    if comp:
        r = comp["recuento"]
        print(f"  frente al auditor: coinciden {r['coinciden']} · skill señala/auditor Sí {r['skill_senala_auditor_si']}"
              f" · skill Ok/auditor No {r['skill_ok_auditor_no']} · al auditor {r['auditor']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
