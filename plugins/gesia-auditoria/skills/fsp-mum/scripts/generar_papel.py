"""Escribe el papel de trabajo de la prueba MUM en Excel.

    python generar_papel.py --muestra muestra.json --parametros parametros.json \
        --facturas facturas.json [--evaluacion evaluacion.json] \
        --salida "<expediente>/AsistenteIA/FspMum/MUM <PRUEBA> <CLIENTE> <EJERCICIO>.xlsx" \
        --generado 2026-09-03

Dos hojas. La primera, «Uso de IA», es la evidencia del uso de inteligencia
artificial (lib_uso_ia.py, la misma en todos los skills): que hizo la herramienta,
que se le facilito, que comprobo ella misma y que debe verificar el equipo, con lo
del equipo EN BLANCO. Los huecos de la aplicacion los rellena sellar_uso_ia del MCP
sobre el papel ya archivado.

La segunda, «Analisis muestra»: una fila por elemento seleccionado, con las
columnas repartidas en cuatro ZONAS de color, cada una con su banda de titulo:

  A · Datos de la muestra   lo que ForSampling tiene guardado del elemento
  B · Datos del documento   lo leido en la factura: fecha, CIF, tercero,
                            concepto, base, IVA, IRPF y total
  C · Prueba de muestreo    el campo principal repetido, el valor segun
                            auditoria, el error, el % de error, con que se
                            compara y la observacion
  D · Evidencia del cruce   por que se atribuyo ese documento a ese elemento

El campo principal se repite en la zona C a proposito: la comparacion se lee de
izquierda a derecha aunque la poblacion traiga veinte columnas. Se repite como
REFERENCIA a la celda de la zona A, no como copia, para que el saldo siga
teniendo un solo origen.

El error y el % de error SI van como formula de Excel -lo demas, como valor-.
El motivo es del auditor: cuando cambia el valor segun auditoria, el error y su
porcentaje se recalculan solos, que es justo lo que va a hacer al revisar el
papel. La misma cifra se calcula ademas en Python para lo que se imprime al
ejecutar y para comparar con lo que el auditor ya tenga evaluado.

  Error = Saldo - SaldoAuditoria, la definicion de ForSampling, medida en el
  esquema y respetada tal cual. Positivo = de mas en libros. El % es
  |Error| / |Saldo| x 100, tambien como lo guarda ForSampling, asi que siempre
  sale positivo.

Las dos van envueltas en IFERROR: si el auditor deja la celda con texto, o el
campo principal se queda a cero, la celda se ve EN BLANCO en vez de con un
#!DIV/0! o un #!VALOR! en un papel de trabajo. Y se escribe IFERROR, en ingles,
porque es como el fichero guarda las funciones; Excel la ensena como SI.ERROR
segun el idioma. Escribir SI.ERROR aqui rompe la formula.

La diferencia de dias tambien es formula, la resta de las dos fechas. Para eso
las fechas se escriben como FECHA y no como texto, que de paso deja ordenar y
filtrar por fecha. El sentido es (fecha en libros - fecha del documento), que es
el que calcula el cruce: negativo = el documento es posterior al apunte.

Un elemento sin medir -sin documento, o con el importe ilegible- se queda con
las dos celdas VACIAS y sin formula. Una formula ahi restaria de una celda vacia
y pintaria el saldo entero como error.

La celda del fichero es un HIPERVINCULO al documento, con RUTA ABSOLUTA: el
papel vive en AsistenteIA y los escaneos en otra carpeta, asi que una ruta
relativa se rompe en cuanto el fichero se mueve o se abre desde otro sitio.

La ruta sale del manifiesto de preparar_documentos.py (--manifiesto), que ya
guarda la de cada documento. Y hay un --carpeta-documentos para el caso de
Cowork: alli los scripts corren en un contenedor y la ruta que ven no existe en
la maquina del auditor, asi que el vinculo se rehace sobre la carpeta de Windows
que indique el usuario. Sin ninguna de las dos, la celda queda como texto: mas
vale sin vinculo que con un vinculo que miente.

Un solo color con significado: amarillo en la observacion cuando hay error o
cuando el elemento no se ha podido medir. Los tonos de zona son estructura, y el
azul subrayado del fichero es la convencion de enlace de toda la vida.

**No hay fila de totales, y es a proposito.** Sumar los errores de una MUM es
proyectar a ojo, y sumarlos con su signo esconde las incorrecciones al
cancelarse. La proyeccion la hace ForSampling con la muestra evaluada. Lo que se
imprime al ejecutar son los errores por exceso y por defecto POR SEPARADO.

Y no lee el reloj: la fecha de generacion entra por --generado, para que el
papel se pueda regenerar identico dentro de dos años.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_fsp import (  # noqa: E402
    es_alias,
    nombres_locales,
    rehidratar_local,
    rutas_documentos,
    TOL_IMPORTE,
    cargar_evaluacion,
    cargar_json,
    cargar_facturas,
    cargar_muestra,
    cargar_parametros,
    cruzar,
    columnas_de_muestra,
    parse_fecha,
    parse_importe,
    salida_utf8,
)
from lib_mum import (  # noqa: E402
    NOMBRE_TERMINO,
    TERMINOS,
    comparar_con_auditor_mum,
    evaluar_mum,
    observacion_mum,
    recuento,
    termino_mayoritario,
)
from lib_uso_ia import hoja_uso_ia, marcar_papel  # noqa: E402

FONT = "Arial"
FORMATO_EURO = '#,##0.00 "€";-#,##0.00 "€";"-"'
FORMATO_PCT = '0.00 "%";-0.00 "%";"-"'
FORMATO_FECHA = "DD/MM/YYYY"
AMARILLO = PatternFill("solid", fgColor="FFFF00")
AZUL_ENLACE = "0563C1"

# Una zona por bloque de columnas: (titulo de la banda, color de cabecera, tinte
# de los datos). El tinte es flojo a proposito, para que el amarillo de la
# observacion -que es el unico color con significado- siga cantando encima.
ZONAS_DEF = {
    "muestra": ("A · Datos de la muestra", "1F4E78", None),
    "documento": ("B · Datos del documento", "217346", "EAF3EC"),
    "prueba": ("C · Prueba de muestreo", "C55A11", "FDF0E6"),
    "cruce": ("D · Evidencia del cruce", "7F7F7F", "F2F2F2"),
}

# «Proveedor o cliente» lleva lo que el documento diga: la razon social si la factura va en
# claro, y el TOKEN del sello si va tachada -que `rehidratar` convierte en el nombre real al
# entregar-. El CIF, con la factura tachada, se queda vacio: esta en negro y no se restaura,
# porque el diccionario indexa por cuenta y no por CIF.
COL_DOCUMENTO = ["Fichero", "Nº factura", "Fecha doc.", "CIF", "Proveedor o cliente", "Concepto",
                 "Base", "IVA", "IRPF", "Total"]
COL_CRUCE = ["Casa por", "Días libros–doc."]

# Lo que el equipo deberia contrastar. Describe, no dictamina: el alcance es suyo. El hueco
# {termino} lleva el termino deducido, o la frase de que la muestra no lo fija.
PROPUESTA = (
    "Cotejar con el documento original los elementos con diferencia y una selección de los que no "
    "la tienen: que el documento es el del apunte y que el importe transcrito es el que figura en "
    "él. En los elementos sin medir, obtener el documento o el motivo. {termino}"
)
PROPUESTA_TERMINO = ("Confirmar que el término de comparación tomado ({nombre}) es el criterio con "
                     "el que la entidad contabiliza esta población.")
PROPUESTA_SIN_TERMINO = ("Fijar el término de comparación (base, total o neto), que la muestra no "
                         "ha permitido deducir.")

_BORDE_LADO = Side(style="thin", color="BFBFBF")
BORDE = Border(left=_BORDE_LADO, right=_BORDE_LADO, top=_BORDE_LADO, bottom=_BORDE_LADO)


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


def _anchos(ws, anchos: dict[int, float]) -> None:
    for col, w in anchos.items():
        ws.column_dimensions[get_column_letter(col)].width = w


def _eur(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _dia(v) -> str:
    d = parse_fecha(v)
    return d.strftime("%d/%m/%Y") if d else (str(v) if v else "—")


def _hoja(wb: Workbook, evaluados: list[dict], cols: dict, params: dict, generado: str,
          rutas: dict[str, str] | None = None) -> None:
    """La unica hoja: un elemento por fila, en cuatro zonas de color.

    Las tres columnas de la MUM SI se rellenan, al contrario que los atributos de
    la prueba de cumplimiento, y la diferencia no es un descuido. Un atributo es
    un veredicto -Ok o no Ok- y rellenarlo es concluir, que no es del skill. Un
    importe segun el documento es una medida: decir que la factura pone 16.962,50
    es describir. De quien es la propuesta lo dice la linea de arriba de la hoja
    -«Propuesta del asistente... el auditor adopta o cambia cada importe»- y el
    propio rotulo «Valor Auditoria (doc)», que dice de donde sale el importe.
    """
    ws = wb.active
    ws.title = "Análisis muestra"
    if not evaluados:
        ws["A1"] = "La muestra no trae elementos."
        return

    pr = params.get("parametros") or {}
    et = parse_importe(pr.get("ErrorTolerableValor"))

    col_pob = [c for c in evaluados[0]["fila"].keys() if c.lower() not in ("seleccionado",)]
    col_principal = cols.get("importe")
    # «VRL» es el valor registrado en libros, el termino de la MUM. Se rotula asi y no
    # con el nombre de la columna de ForSampling -que cambia de prueba en prueba- porque
    # el auditor lee la zona C en el lenguaje del muestreo, no en el del fichero.
    col_mum = ["VRL (muestra)", "Valor Auditoría (doc)", "Error",
               "% error", "Comparado con", "Observación propuesta"]
    cab = col_pob + COL_DOCUMENTO + col_mum + COL_CRUCE

    # Donde empieza cada zona, para las bandas y para las formulas
    n_pob, n_doc, n_mum = len(col_pob), len(COL_DOCUMENTO), len(col_mum)
    ini_doc = n_pob + 1
    ini_mum = n_pob + n_doc + 1
    ini_cruce = ini_mum + n_mum
    c_saldo, c_valor, c_error, c_pct = ini_mum, ini_mum + 1, ini_mum + 2, ini_mum + 3
    c_obs = ini_mum + n_mum - 1
    # el campo principal de la zona A, para referenciarlo desde la C
    col_saldo_pob = (col_pob.index(col_principal) + 1) if col_principal in col_pob else None
    col_fecha_pob = ((col_pob.index(cols['fecha']) + 1)
                     if cols.get('fecha') in col_pob else None)
    c_fecha_doc, c_dias = ini_doc + 2, len(cab)

    colores = ([ZONAS_DEF["muestra"][1]] * n_pob + [ZONAS_DEF["documento"][1]] * n_doc
               + [ZONAS_DEF["prueba"][1]] * n_mum + [ZONAS_DEF["cruce"][1]] * len(COL_CRUCE))
    tintes = ([ZONAS_DEF["muestra"][2]] * n_pob + [ZONAS_DEF["documento"][2]] * n_doc
              + [ZONAS_DEF["prueba"][2]] * n_mum + [ZONAS_DEF["cruce"][2]] * len(COL_CRUCE))

    ws["A1"] = f"Análisis de la muestra — {params.get('Prueba') or 'prueba MUM'}"
    ws["A1"].font = Font(name=FONT, bold=True, size=13)
    ws["A2"] = (f"Prueba {params.get('MuestraId')} · MUM · área {params.get('Area')} · "
                f"ref. {params.get('Referencia')} · ejercicio "
                f"{_dia(params.get('FechaInicioAuditoria'))} — {_dia(params.get('FechaFinAuditoria'))} · "
                f"unidad de muestreo {pr.get('UnidadMuestreo') or '—'} · población "
                f"{pr.get('PoblacionNumElementos') or '—'} elementos · error tolerable de la prueba "
                f"{_eur(et)} · generado {generado}")
    ws["A2"].font = Font(name=FONT, size=9)
    ws["A3"] = ("Propuesta del asistente: localiza el documento de cada elemento y mide lo que sostiene, "
                "en el término con el que contabiliza esta población. El auditor adopta o cambia cada importe. "
                "El error y el % son fórmulas: al cambiar el valor según auditoría se recalculan.")
    ws["A3"].font = Font(name=FONT, italic=True, size=9, color="595959")
    ws["A4"] = ("Error = campo principal − valor según auditoría, como lo define ForSampling: positivo es de "
                "más en libros. Amarillo: hay diferencia, o el elemento no se ha podido medir. Este papel NO "
                "proyecta el error a la población, no lo compara con el error tolerable y no suma los errores "
                "entre sí: eso lo hace ForSampling, y los errores por exceso y por defecto no se cancelan."
                + _frase_dudosas(evaluados, cols))
    ws["A4"].font = Font(name=FONT, italic=True, size=9, color="595959")

    _bandas(ws, 6, [(ZONAS_DEF["muestra"][0], ZONAS_DEF["muestra"][1], 1, n_pob),
                    (ZONAS_DEF["documento"][0], ZONAS_DEF["documento"][1], ini_doc, ini_doc + n_doc - 1),
                    (ZONAS_DEF["prueba"][0], ZONAS_DEF["prueba"][1], ini_mum, ini_mum + n_mum - 1),
                    (ZONAS_DEF["cruce"][0], ZONAS_DEF["cruce"][1], ini_cruce, len(cab))])
    _cabecera(ws, 7, cab, colores)

    L = get_column_letter
    fila = 8
    for e in evaluados:
        f, fac, c = e["fila"], e["factura"], e["criterios"]
        valores = []
        # Las fechas van como FECHA, no como texto: es lo que permite que la
        # diferencia de dias sea una resta de celdas, y de paso que se puedan
        # ordenar y filtrar por fecha. Si alguna no se puede interpretar se deja
        # el texto tal cual y esa fila se queda sin formula.
        fecha_libros = fecha_doc = None
        for k in col_pob:
            v = f.get(k)
            if k == col_principal:
                v = parse_importe(v)
            elif k == cols.get("fecha"):
                fecha_libros = parse_fecha(v)
                v = fecha_libros or v
            valores.append(v)

        if fac:
            fecha_doc = parse_fecha(fac.get("fecha"))
            valores += [fac.get("fichero"), fac.get("numero"),
                        fecha_doc or fac.get("fecha"), fac.get("cif"),
                        fac.get("proveedor") or fac.get("token"), fac.get("concepto"),
                        parse_importe(fac.get("base")), parse_importe(fac.get("iva")),
                        parse_importe(fac.get("irpf")), parse_importe(fac.get("total"))]
        else:
            valores += ["— no localizada", None, None, None, None, None, None, None, None, None]

        # Zona C. El campo principal se referencia, no se copia.
        valores.append(f"={L(col_saldo_pob)}{fila}" if col_saldo_pob else None)
        valores.append(e["saldo_auditoria"])
        if e["saldo_auditoria"] is not None and col_saldo_pob:
            valores.append(f'=IFERROR({L(c_saldo)}{fila}-{L(c_valor)}{fila},"")')
            valores.append(f'=IFERROR(ABS({L(c_error)}{fila})'
                           f'/ABS({L(c_saldo)}{fila})*100,"")')
        else:
            # sin medir: las dos celdas se quedan vacias. Una formula aqui restaria
            # de una celda vacia y pintaria el saldo entero como error.
            valores += [None, None]
        valores.append(NOMBRE_TERMINO.get(e["termino"], "—"))
        valores.append(e["observacion"])

        if fac:
            casa = ", ".join(x for x, b in (("número", c["numero"]), ("tercero", c.get("tercero")),
                                            (f"importe ({c['importe']})", c["importe"]),
                                            ("fecha", c["fecha"])) if b)
            if fecha_libros and fecha_doc:
                dias = f'=IFERROR({L(col_fecha_pob)}{fila}-{L(c_fecha_doc)}{fila},"")'
            else:
                dias = c["dias"]   # sin dos fechas de verdad no hay resta que hacer
            valores += [casa, dias]
        else:
            valores += ["", None]

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
        for col in (c_saldo, c_valor, c_error):
            ws.cell(row=fila, column=col).number_format = FORMATO_EURO
        ws.cell(row=fila, column=c_pct).number_format = FORMATO_PCT
        ws.cell(row=fila, column=c_dias).number_format = "0"
        for col in (col_fecha_pob, c_fecha_doc):
            if col:
                ws.cell(row=fila, column=col).number_format = FORMATO_FECHA
        if e["error"] is None or abs(e["error"]) > TOL_IMPORTE:
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
    for k in range(n_mum - 1):
        anchos[ini_mum + k] = 20
    anchos[c_obs] = 95
    anchos[ini_cruce] = 26                    # Casa por
    _anchos(ws, anchos)


def _ids_dudosas(evaluados: list[dict], cols: dict) -> list[str]:
    return [str(e["fila"].get(cols.get("id"), "?")) for e in evaluados if e.get("dudosa")]


def _frase_dudosas(evaluados: list[dict], cols: dict) -> str:
    """Las asignaciones dudosas, contadas aparte: quedan sin medir porque el documento puede ser
    otro del mismo tercero, y proponer su importe proyectaria un error ajeno (20/10/2026)."""
    ids = _ids_dudosas(evaluados, cols)
    if not ids:
        return ""
    return (f" Asignaciones dudosas, contadas aparte y sin medir: {len(ids)} ({', '.join(ids[:15])}"
            f"{'…' if len(ids) > 15 else ''}). El documento puede ser otro del mismo tercero: se "
            "confirma con poblacion_id antes de proponer importe.")


def _manifiesto(ruta: str | None) -> dict | None:
    """El manifiesto de los documentos, buscado como en rutas_documentos (tambien en facturas/)."""
    if not ruta:
        return None
    pm = Path(ruta)
    if not pm.exists() and (pm.parent / "facturas" / "manifiesto.json").exists():
        pm = pm.parent / "facturas" / "manifiesto.json"
    try:
        return cargar_json(str(pm)) if pm.exists() else None
    except (OSError, ValueError):
        return None


def _comprobaciones(ws, evaluados: list[dict], cruce: dict, cols: dict, comp: dict | None,
                    r: dict, termino: str) -> list[str]:
    """Lo que comprobo la propia herramienta, calculado sobre lo que lleva la hoja.

    Cada frase tiene que ser VERDAD sobre este papel: si una comprobacion no se cumple, la
    frase lo dice con «ATENCIÓN» en vez de afirmar lo contrario. Van en el resultado, nunca en
    la verificacion, que es del equipo.
    """
    n = r["elementos"]
    ids = [str(e["fila"].get(cols.get("id"), "?")) for e in evaluados]
    out = []

    sin_doc = [i for i, e in zip(ids, evaluados) if e["factura"] is None]
    out.append(f"Documento localizado para los {n} elementos de la muestra." if not sin_doc else
               f"ATENCIÓN: sin documento localizado para {len(sin_doc)} de {n} elementos "
               f"({', '.join(sin_doc[:15])}{'…' if len(sin_doc) > 15 else ''}).")

    con_doc = [e for e in evaluados if e["factura"] is not None]
    declarados = sum(1 for e in con_doc if (e.get("criterios") or {}).get("declarado"))
    ambiguos = [i for i, e in zip(ids, evaluados)
                if e["factura"] is not None and (e.get("criterios") or {}).get("ambiguo")]
    out.append(f"Vínculo entre documento y elemento: {len(con_doc) - declarados} por el cruce "
               f"automático (número, tercero, importe o fecha) y {declarados} declarados a mano.")
    if ambiguos:
        out.append(f"ATENCIÓN: {len(ambiguos)} elementos asignados solo por tercero y fecha, con más "
                   f"de un documento candidato ({', '.join(ambiguos[:15])}).")
    dudosas = _ids_dudosas(evaluados, cols)
    if dudosas:
        out.append(f"ATENCIÓN: {len(dudosas)} asignación(es) dudosa(s), contadas aparte ({', '.join(dudosas[:15])}): "
                   "solo las sostienen el tercero y la fecha, sin número que las ate, y el importe se "
                   "aparta más de la mitad o la fecha está más lejos que la de los documentos atados por "
                   "importe o número. Quedan sin medir, sin valor según auditoría ni error propuestos.")
    sueltos = cruce.get("candidatos_sueltos") or []
    if sueltos:
        out.append(f"ATENCIÓN: {len(sueltos)} elementos sin documento con un documento sobrante del "
                   f"mismo tercero: posible diferencia de importe, no extravío.")

    votos = sum(1 for e in evaluados if (e.get("criterios") or {}).get("importe") == termino)
    casan = sum(1 for e in evaluados if (e.get("criterios") or {}).get("importe") in TERMINOS)
    out.append(f"Término de comparación deducido de la propia muestra, no supuesto: "
               f"{NOMBRE_TERMINO[termino]} ({votos} de los {casan} elementos que casan con su "
               f"documento lo hacen por ese término)." if termino else
               "ATENCIÓN: la muestra no permite deducir un término de comparación (base, total o "
               "neto): los elementos que no casan quedan sin importe propuesto.")

    # las formulas, leidas de la hoja: una por elemento medido y ninguna en los sin medir
    cab = {c.value: c.column for c in ws[7] if c.value} if ws.max_row >= 7 else {}
    c_err, c_pct, c_val, c_obs = (cab.get("Error"), cab.get("% error"),
                                  cab.get("Valor Auditoría (doc)"), cab.get("Observación propuesta"))
    con_formula = sin_medir_bien = sin_medir = 0
    hay_suma = False
    for fila in ws.iter_rows(min_row=8):
        for c in fila:
            if isinstance(c.value, str) and c.value.startswith("=") and "SUM" in c.value.upper():
                hay_suma = True
    if c_err and c_pct and c_val and c_obs:
        for f in range(8, ws.max_row + 1):
            ve, vp = ws.cell(f, c_err).value, ws.cell(f, c_pct).value
            if isinstance(ve, str) and ve.startswith("=IFERROR(") and isinstance(vp, str):
                con_formula += 1
            elif ws.cell(f, c_val).value is None:
                sin_medir += 1
                sin_medir_bien += 1 if (ve is None and vp is None and ws.cell(f, c_obs).value) else 0
    if con_formula == r["medidos"] and sin_medir_bien == sin_medir == r["sin_medir"]:
        out.append(f"Error y % de error escritos como fórmula (libros − valor según auditoría) en "
                   f"los {con_formula} elementos medidos; los {sin_medir} sin medir quedan sin "
                   f"fórmula y con el motivo en la observación.")
    else:
        out.append(f"ATENCIÓN: la hoja lleva fórmula de error en {con_formula} elementos y hay "
                   f"{r['medidos']} medidos; {sin_medir} filas sin medir, {sin_medir_bien} con su motivo.")

    out.append((f"Diferencias contadas por separado, sin netear: {r['n_exceso']} por exceso y "
                f"{r['n_defecto']} por defecto." if r["con_error"] else
                "Ningún elemento medido con diferencia.")
               + (" La hoja no suma importes ni lleva fila de totales." if not hay_suma else
                  " ATENCIÓN: la hoja lleva una fórmula de suma."))

    if comp:
        c = comp["recuento"]
        out.append(("ATENCIÓN: " if c["skill_cero_auditor_error"] else "")
                   + f"Frente a la evaluación ya registrada en ForSampling: coinciden "
                   f"{c['coinciden']}; la herramienta propone 0 donde la evaluación registra error "
                   f"en {c['skill_cero_auditor_error']}; señala diferencia donde la evaluación "
                   f"registra 0 en {c['skill_error_auditor_cero']}; importes distintos en "
                   f"{c['discrepan']}; sin comparar {c['sin_evaluar']}.")
    return out


def _uso_ia(wb: Workbook, args, params: dict, evaluados: list[dict], cruce: dict, cols: dict,
            comp: dict | None, r: dict, n_facturas: int) -> None:
    """La hoja de evidencia del uso de IA, la primera del libro (lib_uso_ia)."""
    termino = termino_mayoritario(evaluados)
    ws = wb["Análisis muestra"]
    ejercicio = (_dia(params.get("FechaInicioAuditoria")) + " — "
                 + _dia(params.get("FechaFinAuditoria")))

    # Lo facilitado que el MCP NO ve: la lectura de las imagenes la hace la herramienta. Si las
    # preparo el MCP, el sello ya las lista; si las renderizo el script, no pasan por el MCP.
    adicional = [f"Las imágenes de los documentos de la muestra las lee la propia herramienta (el "
                 f"modelo o sus agentes lectores), que transcribe lo que figura en la zona «B · "
                 f"Datos del documento»: {n_facturas} documentos transcritos."]
    man = _manifiesto(args.manifiesto)
    if man and man.get("origen") == "mcp":
        adicional.append("Las imágenes las preparó la aplicación en el equipo del auditor, "
                         + ("tachadas antes de facilitarlas." if man.get("modo") == "tachadas"
                            else "sin tachar."))
    elif man:
        adicional.append("Las imágenes las renderizó el script del procedimiento a partir de los "
                         "PDF, sin tachar: no pasan por la aplicación y no constan en la lista "
                         "anterior.")
    else:
        adicional.append("Sin manifiesto de los documentos: no consta si las imágenes las preparó la "
                         "aplicación (entonces figuran en la lista anterior) o se leyeron sin pasar "
                         "por ella, sin tachar.")

    hoja_uso_ia(
        wb,
        papel=(f"Prueba MUM {params.get('Prueba') or ''} · ref. {params.get('Referencia') or '—'} · "
               f"ejercicio {ejercicio} · Análisis muestra"),
        procedimiento="fsp-mum",
        descripcion=("Validación de la muestra de una prueba MUM (muestreo por unidades monetarias) de "
                     "ForSampling contra los documentos escaneados: localiza el documento de cada "
                     "elemento, lee el importe que sostiene y propone el valor según auditoría, el "
                     "error y la tasa de error por elemento."),
        alcance=(f"Prueba {params.get('Prueba') or '—'} (id {params.get('MuestraId')}), área "
                 f"{params.get('Area') or '—'}, ejercicio {ejercicio}: los {r['elementos']} "
                 f"elementos seleccionados ({r['repeticiones']:g} unidades de muestreo con "
                 f"repeticiones) y {n_facturas} documentos transcritos de la carpeta indicada por "
                 f"el auditor."),
        resultado=(f"Este libro: hoja «Análisis muestra», {r['elementos']} elementos ({r['con_error']} "
                   f"con diferencia, {r['sin_medir']} sin medir"
                   + (f", de ellos {r['dudosas']} por asignación dudosa" if r.get("dudosas") else "")
                   + f"). Redactado por la herramienta: lo "
                   f"transcrito de cada documento y, como PROPUESTAS que el auditor adopta o cambia, "
                   f"el valor según auditoría (SaldoAuditoria), el error y la tasa de error de cada "
                   f"elemento, el término con el que se compara y la observación para ForSampling. "
                   f"No proyecta el error a la población, no lo compara con el error tolerable ni "
                   f"concluye si la prueba se supera: eso corresponde a ForSampling y al auditor."),
        comprobaciones=_comprobaciones(ws, evaluados, cruce, cols, comp, r, termino),
        propuesta=PROPUESTA.format(termino=PROPUESTA_TERMINO.format(nombre=NOMBRE_TERMINO[termino])
                                   if termino else PROPUESTA_SIN_TERMINO),
        generado=args.generado,
        informacion_adicional=adicional,
    )


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--muestra", required=True)
    p.add_argument("--parametros", required=True)
    p.add_argument("--facturas", required=True)
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
    evaluacion = cargar_evaluacion(args.evaluacion)

    cols, _, _ = columnas_de_muestra(muestra)
    cruce = cruzar(muestra, facturas, cols)
    evaluados = evaluar_mum(cruce, cols)
    for e in evaluados:
        e["observacion"] = observacion_mum(e)
    comp = comparar_con_auditor_mum(evaluados, (evaluacion or {}).get("filas") or [], cols)
    r = recuento(evaluados)

    rutas = rutas_documentos(args.manifiesto, args.carpeta_documentos)

    wb = Workbook()
    _hoja(wb, evaluados, cols, params, args.generado, rutas)
    # la marca junto al encabezado, en la fila libre antes de las bandas: que se vea al abrirlo
    marcar_papel(wb["Análisis muestra"], "A5", "B5")
    _uso_ia(wb, args, params, evaluados, cruce, cols, comp, r, len(facturas))
    # con un manifiesto local (--carpeta, sin MCP) el papel recupera aqui el nombre real de cada
    # alias; lo impreso al chat sigue por alias (registro del 21/10/2026)
    rehidratar_local(wb, nombres_locales(_manifiesto(args.manifiesto)))

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(salida)
    except PermissionError:
        print(f"ERROR: no se puede escribir {salida}. Si está abierto en Excel, ciérralo y repite.")
        return 2

    term = termino_mayoritario(evaluados)
    print(f"Papel escrito: {salida}")
    print("  hoja «Uso de IA» con huecos de la aplicación: sellar_uso_ia sobre el papel archivado")
    if rutas:
        enlazados = [e for e in evaluados if e["factura"] and rutas.get(e["factura"].get("fichero"))]
        rotos = [e for e in enlazados if not Path(rutas[e["factura"]["fichero"]]).exists()]
        print(f"  documentos enlazados {len(enlazados)} de {r['con_documento']}")
        # Con --carpeta-documentos la ruta la ha dado el auditor, y desde el contenedor nunca se
        # ve: el aviso solo hacia ruido (registro del 21/10/2026). Y un vinculo por alias
        # (<carpeta>\<alias>, MCP 1.26.0) no existe en ningun disco hasta que `rehidratar` lo
        # cambia por el nombre real: tampoco es un vinculo roto.
        por_alias = [e for e in enlazados
                     if es_alias(str(rutas[e["factura"]["fichero"]]).replace("\\", "/").rsplit("/", 1)[-1])]
        rotos = [e for e in rotos if e not in por_alias]
        if por_alias:
            print(f"  {len(por_alias)} vínculo(s) van por el alias del documento: los deja buenos "
                  f"«rehidratar» en el equipo del auditor, que cambia el alias por el fichero real")
        if rotos and not args.carpeta_documentos:
            print(f"  AVISO: {len(rotos)} vínculo(s) apuntan a rutas que este proceso no ve. Si los "
                  f"scripts corren en un contenedor es lo normal y en la máquina del auditor "
                  f"funcionarán; si no, pásale --carpeta-documentos con la ruta buena y repite")
    else:
        print("  sin hipervínculos: no se ha indicado --manifiesto ni --carpeta-documentos")
    print(f"  elementos {r['elementos']} · unidades de muestreo con repeticiones {r['repeticiones']:g}"
          f" · con documento {r['con_documento']} · sin documento {r['sin_documento']}"
          f" · medidos {r['medidos']} · sin medir {r['sin_medir']}"
          f" (asignaciones dudosas {r['dudosas']})")
    print(f"  esta población contabiliza por: {NOMBRE_TERMINO.get(term, 'sin criterio claro (lo decide el auditor)')}")
    print(f"  sin diferencia {r['sin_error']} · con diferencia {r['con_error']}")
    if r["con_error"]:
        print(f"  incorrecciones POR SEPARADO, sin netear: {r['n_exceso']} por exceso suman "
              f"{_eur(r['suma_exceso'])} · {r['n_defecto']} por defecto suman {_eur(r['suma_defecto'])}")
        print("  NO son la proyección ni el error neto: la proyección la hace ForSampling con la muestra evaluada")
    for e in evaluados:
        ident = e["fila"].get(cols.get("id"), "?")
        if e.get("dudosa"):
            print(f"  · ASIGNACIÓN DUDOSA, elemento {ident}, sin medir: {e['observacion']}")
        elif e["error"] is None or abs(e["error"]) > TOL_IMPORTE:
            print(f"  · elemento {ident}: {e['observacion']}")
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
    if comp:
        c = comp["recuento"]
        print(f"  frente al auditor: coinciden {c['coinciden']} · skill señala error/auditor 0 "
              f"{c['skill_error_auditor_cero']} · SKILL 0/AUDITOR ERROR {c['skill_cero_auditor_error']}"
              f" · los dos con error distinto {c['discrepan']} · sin comparar {c['sin_evaluar']}")
        for f in comp["filas"]:
            if f["estado"].startswith("EL SKILL DA 0") or f["estado"].startswith("los dos"):
                print(f"    · elemento {f['id']}: skill {_eur(f['error_skill'])} / auditor "
                      f"{_eur(f['error_auditor'])} — {f['observacion_auditor'] or ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
