"""Escribe el papel de trabajo de cancelacion de saldos en Excel.

    python generar_papel.py --entrada extracto.csv \
        --salida "<expediente>/AsistenteIA/CancelacionSaldos/Cancelacion Saldos <CLIENTE>.xlsx"

Una hoja "Resumen" con una fila por cuenta, y una hoja por cuenta con el
detalle FECHA / CUENTA / NOMBRE / [CONCEPTO, si viene] / SALDO / INDICE / ORIGEN, en
orden cronologico y con autofiltro. Dos colores, y ninguno mas:

  - gris     (fila entera) el apunte venia ya punteado en la contabilidad
             (columna Indice del .smn): se respeta tal cual
  - amarillo (solo la celda del importe) el apunte NO se ha podido parear:
             es lo que compone el saldo vivo de la cuenta, y es donde el
             auditor tiene que mirar

Lo que este papel cancela no se colorea, venga de pareo directo o de
acumulacion de saldo: esa distincion la da la columna ORIGEN. Antes el
amarillo marcaba la acumulacion y se cambio en la revision del
27/08/2026, porque lo que hay que ver de un vistazo es el pendiente.

No usa formulas: los totales se calculan aqui, en Python, y se escriben
como valor. Este papel tiene que leerse igual en Cowork y en la maquina del
auditor sin depender de si hay LibreOffice o Excel instalado para
recalcular -- a diferencia de un artefacto de Cowork, este es un skill que
tambien corre en local.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_cancelacion import (  # noqa: E402
    MAX_GRUPO_COMBOS,
    MAX_LEFTOVER_FOR_COMBOS,
    ORIGEN_CONTABLE,
    analizar_hallazgos,
    cargar_extracto,
    procesar_extracto,
)

FONT = "Arial"
FORMATO_EURO = '#,##0.00 "€";-#,##0.00 "€";"-"'
FORMATO_FECHA = "dd/mm/yyyy"
AMARILLO = PatternFill("solid", fgColor="FFFF00")
GRIS = PatternFill("solid", fgColor="E7E6E6")
CABECERA_FILL = PatternFill("solid", fgColor="1F4E78")
CABECERA_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
TOTAL_FILL = PatternFill("solid", fgColor="D9E1F2")
_BORDE_LADO = Side(style="thin", color="BFBFBF")
BORDE = Border(left=_BORDE_LADO, right=_BORDE_LADO, top=_BORDE_LADO, bottom=_BORDE_LADO)

MAX_LISTA = 30  # cuentas detalladas en consola; por encima, se resume


def _hoja_cuenta(wb: Workbook, cuenta: str, res, info: dict) -> dict:
    ws = wb.create_sheet(str(cuenta)[:31])
    nombre_cliente = res["NOMBRE"].iloc[0] if len(res) else ""

    ws["A1"] = "Cancelacion de saldos — Cuenta " + str(cuenta) + " — " + nombre_cliente
    ws["A1"].font = Font(name=FONT, bold=True, size=13)
    ws["A2"] = ("Emparejamiento de facturas y pagos — gris: punteado ya en la "
                "contabilidad; amarillo: importe sin parear, que compone el "
                "saldo vivo de la cuenta. ORIGEN dice el paso que formo cada grupo: "
                "documento, apertura, total, importe, acumulacion o combinacion")
    ws["A2"].font = Font(name=FONT, italic=True, size=9, color="595959")
    # la banda de titulo llega hasta la ultima columna, que es una mas cuando el
    # extracto trae el numero de documento
    con_fra = "FACTURA" in res.columns
    # La cabecera se ARMA, y los indices de columna se DERIVAN de ella. Estaban
    # escritos a mano -j == 5 para el saldo- y al insertar FACTURA el formato de
    # euros y el amarillo se quedaron una columna a la izquierda. Un papel donde
    # el amarillo senala la columna de al lado no se puede publicar, asi que
    # ninguna posicion vuelve a ir a mano.
    #
    # ASIENTO va si el extracto lo trae: sin el, un apunte del papel no se puede
    # localizar en Gesia ni casar con el papel que el auditor ya tuviera. Se vio
    # al cruzar este papel con uno real: hubo que casar por fecha e importe, y
    # dos apuntes identicos del mismo dia colapsaban en uno.
    con_asi = "ASIENTO" in res.columns
    # FECHA DOC. va si algun apunte la trae: es la fecha del documento que el MCP
    # deriva del concepto en local -o leida del concepto si viajo-, y sin el
    # concepto en el papel es la unica forma de que el auditor la vea
    con_fdoc = "FECHA_DOC" in res.columns and bool(res["FECHA_DOC"].notna().any())
    cab = ["FECHA"] + (["FECHA DOC."] if con_fdoc else [])
    if con_asi:
        cab.append("ASIENTO")
    con_con = "CONCEPTO" in res.columns
    cab += ["CUENTA", "NOMBRE"] + (["CONCEPTO"] if con_con else [])
    if con_fra:
        cab.append("FACTURA")
    cab += ["SALDO", "INDICE", "ORIGEN"]
    col = {h: j for j, h in enumerate(cab, start=1)}
    ultima = get_column_letter(len(cab))
    ws.merge_cells(f"A1:{ultima}1")
    ws.merge_cells(f"A2:{ultima}2")
    fila_cab = 4
    for j, h in enumerate(cab, start=1):
        c = ws.cell(fila_cab, j, h)
        c.font = CABECERA_FONT
        c.fill = CABECERA_FILL
        c.alignment = Alignment(horizontal="center")
        c.border = BORDE

    # Orden cronologico: el mayor se lee en su orden natural (decidido en
    # la revision del 27/08/2026). Los grupos se siguen por la
    # columna INDICE, y el autofiltro permite reordenar al revisar.
    ordenado = res.sort_values("FECHA", kind="stable").reset_index(drop=True)
    fila = fila_cab + 1
    for _, r in ordenado.iterrows():
        valores = [r["FECHA"].to_pydatetime()]
        if con_fdoc:
            valores.append(r["FECHA_DOC"].to_pydatetime() if pd.notna(r["FECHA_DOC"]) else None)
        if con_asi:
            valores.append(str(r.get("ASIENTO", "") or ""))
        valores += [r["CUENTA"], r["NOMBRE"]] + ([r["CONCEPTO"]] if con_con else [])
        if con_fra:
            valores.append(r.get("FACTURA", "") or "")
        valores += [float(r["SALDO"]), int(r["INDICE"]), r["ORIGEN"]]
        # Gris a la fila entera del punteo contable; amarillo SOLO a la celda
        # del importe que queda sin parear, que es lo que compone el saldo
        # vivo de la cuenta (revision del 27/08/2026). Lo cancelado
        # por este papel no se colorea, venga de pareo directo o de
        # acumulacion: esa distincion la da la columna ORIGEN, no el color.
        relleno_fila = GRIS if r["ORIGEN"] == ORIGEN_CONTABLE else None
        sin_parear = int(r["INDICE"]) == 0
        for j, v in enumerate(valores, start=1):
            c = ws.cell(fila, j, v)
            c.font = Font(name=FONT, size=10)
            c.border = BORDE
            if j in (col["FECHA"], col.get("FECHA DOC.", -1)):
                c.number_format = FORMATO_FECHA
            elif j == col["SALDO"]:
                c.number_format = FORMATO_EURO
            elif j in (col["INDICE"], col["ORIGEN"], col.get("ASIENTO", -1)):
                c.alignment = Alignment(horizontal="center")
            if j == col["SALDO"] and sin_parear:
                c.fill = AMARILLO
            elif relleno_fila:
                c.fill = relleno_fila
        fila += 1

    # Las filas de totales tambien van por nombre: la etiqueta en la columna
    # anterior a SALDO y la cifra bajo SALDO. Iban a las posiciones 4 y 5 fijas, y
    # con ASIENTO, CONCEPTO o FACTURA delante el TOTAL caia bajo otra columna.
    j_saldo, j_etq = col["SALDO"], col["SALDO"] - 1
    fila_total = fila
    ws.cell(fila_total, j_etq, "TOTAL").font = Font(name=FONT, bold=True, size=10)
    total = round(float(ordenado["SALDO"].sum()), 2)
    c = ws.cell(fila_total, j_saldo, total)
    c.font = Font(name=FONT, bold=True, size=10)
    c.number_format = FORMATO_EURO
    for j in range(1, len(cab) + 1):
        ws.cell(fila_total, j).fill = TOTAL_FILL

    fila_pend = fila_total + 1
    ws.cell(fila_pend, j_etq, "Pendiente sin cancelar (INDICE = 0)").font = (
        Font(name=FONT, size=9, italic=True))
    pendiente = round(float(info["suma_indice_0"]), 2)
    c = ws.cell(fila_pend, j_saldo, pendiente)
    c.font = Font(name=FONT, bold=True, size=10)
    c.number_format = FORMATO_EURO

    fila_sig = fila_pend + 1
    descuadre = round(float(info["descuadre_punteo_previo"]), 2)
    if abs(descuadre) > 0.005:
        ws.cell(fila_sig, j_etq, "Descuadre del punteo contable (grupos previos "
                                 "que no suman 0)").font = Font(name=FONT, size=9, italic=True)
        c = ws.cell(fila_sig, j_saldo, descuadre)
        c.font = Font(name=FONT, bold=True, size=10, color="C00000")
        c.number_format = FORMATO_EURO
        fila_sig += 1

    ok = info["coincide_total_con_no_cancelado"] and not info["grupos_con_error"]
    ws.cell(fila_sig, j_etq, "Verificacion").font = Font(name=FONT, size=9, italic=True)
    c = ws.cell(fila_sig, j_saldo, "OK" if ok else "REVISAR")
    c.font = Font(name=FONT, bold=True, size=10, color="000000" if ok else "C00000")

    # los anchos, tambien por nombre y no por posicion
    anchos = {"FECHA": 12, "FECHA DOC.": 12, "ASIENTO": 9, "CUENTA": 13, "NOMBRE": 20,
              "CONCEPTO": 34, "FACTURA": 14, "SALDO": 15, "INDICE": 9, "ORIGEN": 11}
    for h, w in anchos.items():
        if h in col:
            ws.column_dimensions[get_column_letter(col[h])].width = w
    ws.freeze_panes = "A" + str(fila_cab + 1)
    # solo las filas de datos: las de totales quedan fuera del filtro
    ws.auto_filter.ref = "A" + str(fila_cab) + ":" + ultima + str(fila - 1)

    return {
        "cuenta": cuenta,
        "nombre": nombre_cliente,
        "apuntes": len(ordenado),
        "grupos_previos": info["num_grupos_previos"],
        "grupos_nuevos": info["num_grupos_nuevos"],
        "sin_cancelar": info["num_registros_sin_cancelar"],
        "total": total,
        "pendiente": pendiente,
        "descuadre_previo": descuadre,
        "ok": ok,
    }


def _hoja_criterios(ws, h: dict) -> None:
    """Bajo que criterios se ha hecho el papel, y que ha salido.

    Va la primera a proposito: quien abra el libro tiene que saber que esta
    leyendo antes de leerlo. Y describe, no dictamina -- los numeros dicen
    donde mirar; concluir es del auditor.
    """
    def titulo(fila, texto):
        c = ws.cell(fila, 1, texto)
        c.font = Font(name=FONT, bold=True, color="FFFFFF", size=10)
        c.fill = CABECERA_FILL
        ws.merge_cells(start_row=fila, start_column=1, end_row=fila, end_column=3)
        return fila + 1

    def linea(fila, etiqueta, valor=None, nota=None):
        c = ws.cell(fila, 1, etiqueta)
        c.font = Font(name=FONT, size=10)
        c.alignment = Alignment(vertical="top", wrap_text=True)
        if valor is not None:
            v = ws.cell(fila, 2, valor)
            v.font = Font(name=FONT, size=10, bold=True)
            v.alignment = Alignment(horizontal="right", vertical="top")
            if isinstance(valor, float):
                v.number_format = FORMATO_EURO
        if nota is not None:
            n = ws.cell(fila, 3, nota)
            n.font = Font(name=FONT, size=9, italic=True, color="595959")
            n.alignment = Alignment(vertical="top", wrap_text=True)
        return fila + 1

    ws["A1"] = "Cancelacion de saldos — criterios y hallazgos"
    ws["A1"].font = Font(name=FONT, bold=True, size=13)
    ws.merge_cells("A1:C1")
    ws.column_dimensions["A"].width = 62
    ws.column_dimensions["B"].width = 16
    ws.column_dimensions["C"].width = 68

    f = 3
    f = titulo(f, "COMO SE HAN FORMADO LOS GRUPOS")
    f = linea(f, "1 · Punteo previo de la contabilidad", None,
              "Si el diario trae la columna Indice, esos grupos se respetan tal cual "
              "y no se rehacen. Un grupo previo que no suma cero se avisa, no se corrige.")
    f = linea(f, "2 · La apertura primero", None,
              "Se acumulan los apuntes de signo contrario hasta dar su importe exacto. "
              "Si ningun conjunto lo da, la apertura queda pendiente: no se fuerza.")
    f = linea(f, "3 · Pareo directo por importe", None,
              "Apuntes de igual importe y signo contrario, uno a uno.")
    f = linea(f, "4 · Acumulacion cronologica y combinaciones", None,
              "Tramos continuos que sumen cero y, sobre lo que quede, subconjuntos de "
              "hasta " + str(MAX_GRUPO_COMBOS) + " apuntes entre un maximo de "
              + str(MAX_LEFTOVER_FOR_COMBOS) + " sin cancelar.")
    f += 1
    f = linea(f, "Fecha que se usa para emparejar", "contable",
              "La del asiento. No se usa el texto del concepto para decidir que apuntes "
              "van juntos.")
    fuente_fd = h.get("fuente_fecha_doc")
    f = linea(f, "Fecha que se usa para informar", "del documento",
              {"FechaEnConcepto": (
                   "La que la factura lleva escrita en el concepto, extraida en local por "
                   "el MCP de Gesia (FechaEnConcepto): el texto del concepto no ha salido "
                   "del equipo. Solo para los recuentos de abajo."),
               "CONCEPTO": (
                   "La que la factura lleva escrita en el concepto, leida aqui del propio "
                   "CONCEPTO, que el auditor autorizo exportar. Solo para los recuentos de "
                   "abajo.")}.get(
                  fuente_fd, "No disponible: el extracto no trae fecha de documento."))
    fuente_doc = h.get("fuente_documento")
    if fuente_doc and str(fuente_doc).lower() == "numeroenconcepto":
        nota_doc = ("Derivado del concepto en local por el MCP de Gesia (NumeroEnConcepto): "
                    "el diario no trae columna de numero de factura. Un grupo por numero "
                    "solo se acepta si suma cero, asi que un numero mal leido no empareja "
                    "nada: el numero propone y la suma decide.")
    elif fuente_doc:
        nota_doc = ("Columna '" + str(fuente_doc) + "' del diario del cliente. Un grupo por "
                    "numero solo se acepta si suma cero.")
    else:
        nota_doc = ("Ninguno: el diario no trae columna de numero de factura y el concepto "
                    "no lleva ninguno reconocible. El paso 0 no ha actuado.")
    cand = h.get("candidatas_documento") or []
    if len(cand) > 1:
        nota_doc += (" Habia " + str(len(cand)) + " columnas candidatas y se eligio la que mas "
                     "grupos cierra a cero EN ESTE EXTRACTO: "
                     + " · ".join((f"{c} vacia" if not t[3] else f"{c} {z}/{g}")
                                  for t in cand for c, g, z in [t[:3]]) + ".")
    f = linea(f, "Numero de documento del paso 0",
              (str(fuente_doc) if fuente_doc else "ninguno"), nota_doc)
    f += 1
    f = linea(f, "LO QUE ESTE PAPEL NO PRUEBA", None,
              "Un grupo es una cancelacion ARITMETICA: sus apuntes suman cero. No es "
              "evidencia documental de que ESE pago liquide ESA factura. Cuando varios "
              "apuntes comparten importe, el emparejamiento concreto es una propuesta.")

    f += 1
    f = titulo(f, "ALCANCE")
    f = linea(f, "Cuentas procesadas", h["cuentas"])
    f = linea(f, "Apuntes", h["apuntes"])
    f = linea(f, "Grupos evaluados", h["grupos_evaluados"])
    por_paso = h.get("grupos_por_paso") or {}
    if por_paso:
        f = linea(f, "Grupos nuevos, por el paso que los formo",
                  " · ".join(f"{k} {v}" for k, v in por_paso.items()),
                  "Los de «acumulación» y «combinación» cierran por aritmetica sobre "
                  "importes que no se parecen: son los que merecen una segunda mirada, "
                  "y mas cuanto mas apuntes tengan. La columna ORIGEN de cada hoja lo "
                  "dice grupo a grupo.")
    if h["grupos_no_evaluables"]:
        f = linea(f, "Grupos no evaluables", h["grupos_no_evaluables"],
                  "No se puede distinguir que lado son documentos y cual pagos: no "
                  "entran en los recuentos de fechas.")

    f += 1
    f = titulo(f, "SALDO DE APERTURA")
    f = linea(f, "Cuentas con apertura detectada", h["aperturas_detectadas"],
              "Se reconoce por estructura: apunte del 1 de enero y el mas antiguo de "
              "la cuenta.")
    f = linea(f, "  cancelada", h["aperturas_canceladas"])
    f = linea(f, "  sigue viva", h["aperturas_vivas"])
    f = linea(f, "  importe vivo", float(h["aperturas_importe_vivo"]))
    f = linea(f, "Aperturas NO identificadas", h["aperturas_no_identificadas"],
              "varios apuntes el 1 de enero: no se sabe cual es la apertura, asi que el "
              "emparejamiento NO la ha intentado. No es que no se haya podido cerrar, es "
              "que no se ha mirado")
    f = linea(f, "  importe", float(h["aperturas_importe_no_identificado"]))
    f = linea(f, "Cuentas de un solo apunte (del 1 de enero)", h.get("cuentas_un_apunte", 0),
              "No hay nada que cancelar: un unico movimiento vivo. Es lo normal en una "
              "cuenta cuyo contrapunto esta en otro ejercicio o que se abrio con saldo y "
              "no se ha movido. No es un frente abierto del emparejamiento.")
    f = linea(f, "  importe", float(h.get("importe_un_apunte", 0.0)))
    f = linea(f, "Cuentas sin apertura detectada", h["cuentas_sin_apertura"],
              "Puede ser una cuenta abierta en el ejercicio, o que el diario no traiga "
              "el asiento de apertura. Si el saldo inicial deberia estar y no aparece, "
              "el extracto no cubre el ejercicio completo.")

    f += 1
    f = titulo(f, "PAGOS ANTERIORES A SU FACTURA")
    if not h.get("fecha_doc_disponible", True):
        # Sin fecha de documento -ni derivada por el MCP ni leida del concepto-
        # calcular esto con la fecha contable daria una cifra inflada con aspecto
        # de hallazgo. Se dice y no se enseña ninguna.
        f = linea(f, "NO EVALUADO", "—",
                  "El extracto no trae fecha de documento: ni FechaEnConcepto -que el MCP "
                  "deriva en local si el SELECT pide CONCEPTO- ni el propio CONCEPTO. Sin "
                  "ella, ni este apartado ni el plazo de pago se han calculado. No significa "
                  "que no haya hallazgos: significa que no se han buscado.")
        return
    if not h["grupos_evaluados"]:
        # Un cero aqui se leeria como "no hay hallazgos" cuando lo que pasa es
        # que no se ha mirado. Se dice, y no se enseña ninguna cifra.
        f = linea(f, "NO SE HA PODIDO EVALUAR", "—",
                  "Para comparar fechas hay que saber que apuntes son documentos y "
                  "cuales pagos, y en estas cuentas no se puede deducir: no hay "
                  "apertura y el saldo es cero. Este apartado NO dice que no haya "
                  "hallazgos: dice que no se han buscado.")
        return
    f = linea(f, "Con la fecha del documento", h["anomalos"],
              "Los que hay que mirar: el pago es anterior a la fecha que la factura "
              "lleva escrita.")
    f = linea(f, "Solo con la fecha contable (la factura no lleva fecha de documento)",
              h.get("anomalos_sin_fecha_doc", 0),
              "El pago es anterior al ASIENTO de una factura que no lleva fecha de "
              "documento: no se puede distinguir un registro a fin de mes de un pago "
              "anticipado. NO son hallazgos confirmados; para saberlo hay que ver el "
              "documento.")
    f = linea(f, "  la pareja venia forzada por el importe", h["anom_forzados"],
              "Ese importe aparece una sola vez a cada lado: no habia emparejamiento "
              "alternativo, asi que no es una eleccion del papel.")
    f = linea(f, "  habia emparejamiento alternativo", h["anom_con_alternativa"],
              "Aqui si se ha elegido entre varios candidatos del mismo importe. Son "
              "los primeros a revisar.")
    f = linea(f, "  grupos de mas de dos apuntes", h["anom_grupos_grandes"])
    f = linea(f, "Lo parecen solo por la fecha de registro", h["solo_fecha_registro"],
              "El pago es anterior al ASIENTO de la factura pero no a su fecha de "
              "documento: es la contabilidad registrando a fin de mes, no una anomalia. "
              "NO se cuentan arriba.")
    if h["facturas_totales"]:
        pct = 100.0 * h["facturas_con_fecha_doc"] / h["facturas_totales"]
        f = linea(f, "Facturas con fecha de documento en el concepto",
                  format(pct, ".0f") + " %",
                  "De esto depende la fiabilidad de los dos recuentos anteriores. Si es "
                  "bajo, la mayoria se comparan contra la fecha del asiento.")

    if h["plazo_mediana"] is not None:
        f += 1
        f = titulo(f, "PLAZO DE PAGO MEDIDO")
        f = linea(f, "Mediana", str(h["plazo_mediana"]) + " dias",
                  "Medido sobre " + str(h["plazo_muestra"]) + " grupos, de la fecha del "
                  "documento a la del pago. Es un hallazgo, no un criterio: no se ha "
                  "usado para emparejar nada.")
        f = linea(f, "Cuartiles", str(h["plazo_p25"]) + " a " + str(h["plazo_p75"]) + " dias")


def _rellenar_resumen(ws, filas: list[dict]) -> None:
    ws["A1"] = "Cancelacion de saldos — resumen por cuenta"
    ws["A1"].font = Font(name=FONT, bold=True, size=13)
    ws.merge_cells("A1:J1")

    cab = ["CUENTA", "NOMBRE", "APUNTES", "GRUPOS PREVIOS (CONTABILIDAD)",
           "GRUPOS NUEVOS (ESTE PAPEL)", "SIN CANCELAR", "TOTAL CUENTA",
           "PENDIENTE (INDICE 0)", "DESCUADRE PUNTEO PREVIO", "VERIFICACION"]
    fila_cab = 3
    for j, h in enumerate(cab, start=1):
        c = ws.cell(fila_cab, j, h)
        c.font = CABECERA_FONT
        c.fill = CABECERA_FILL
        c.alignment = Alignment(horizontal="center", wrap_text=True)
        c.border = BORDE

    fila = fila_cab + 1
    for f in filas:
        valores = [f["cuenta"], f["nombre"], f["apuntes"], f["grupos_previos"],
                   f["grupos_nuevos"], f["sin_cancelar"], f["total"], f["pendiente"],
                   f["descuadre_previo"], "OK" if f["ok"] else "REVISAR"]
        for j, v in enumerate(valores, start=1):
            c = ws.cell(fila, j, v)
            c.font = Font(name=FONT, size=10)
            c.border = BORDE
            if j in (7, 8, 9):
                c.number_format = FORMATO_EURO
            if j == 9 and abs(f["descuadre_previo"]) > 0.005:
                c.font = Font(name=FONT, size=10, bold=True, color="C00000")
            if j == 10 and not f["ok"]:
                c.font = Font(name=FONT, size=10, bold=True, color="C00000")
        fila += 1

    anchos = {1: 13, 2: 22, 3: 10, 4: 15, 5: 15, 6: 12, 7: 16, 8: 18, 9: 15, 10: 13}
    for col, w in anchos.items():
        ws.column_dimensions[get_column_letter(col)].width = w
    ws.freeze_panes = "A" + str(fila_cab + 1)
    ws.auto_filter.ref = "A" + str(fila_cab) + ":J" + str(fila - 1)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--entrada", required=True)
    p.add_argument("--salida", required=True)
    args = p.parse_args()

    df = cargar_extracto(args.entrada)
    por_cuenta = procesar_extracto(df)

    wb = Workbook()
    wb.remove(wb.active)
    # las dos primeras hojas se crean ya para fijar el orden y se rellenan al final
    ws_criterios = wb.create_sheet("Criterios y hallazgos")
    ws_resumen = wb.create_sheet("Resumen")

    filas_resumen = []
    for cuenta, (res, info) in por_cuenta.items():
        filas_resumen.append(_hoja_cuenta(wb, cuenta, res, info))
    _rellenar_resumen(ws_resumen, filas_resumen)
    hallazgos = analizar_hallazgos(df, por_cuenta)
    _hoja_criterios(ws_criterios, hallazgos)

    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    try:
        wb.save(salida)
    except PermissionError:
        # Pasa cuando se regenera el papel con el fichero abierto en Excel.
        print("ERROR: no se puede escribir " + str(salida))
        print("       El fichero esta abierto en Excel. Cierralo y repite.")
        return 2

    print("Escrito: " + str(salida))
    print("  " + str(len(filas_resumen)) + " cuenta(s)")
    for f in filas_resumen[:MAX_LISTA]:
        print("  " + str(f["cuenta"]) + " " + str(f["nombre"])[:30].ljust(30)
              + " " + str(f["apuntes"]).rjust(5) + " apuntes | "
              + str(f["grupos_previos"]).rjust(4) + " previos | "
              + str(f["grupos_nuevos"]).rjust(4) + " nuevos | "
              + str(f["sin_cancelar"]).rjust(4) + " sin cancelar | pendiente "
              + format(f["pendiente"], ",.2f") + " €")
    if len(filas_resumen) > MAX_LISTA:
        print("  ... y " + str(len(filas_resumen) - MAX_LISTA)
              + " cuenta(s) mas: ver hoja Resumen")
    # El agregado va SIEMPRE, y despues del corte: con 69 cuentas el listado se
    # cortaba en la 30 y habia que abrir el Excel para saber el pendiente total y
    # si todas verificaban (dos registros de ejecucion lo pidieron, 10/09/2026).
    no_ok = [f for f in filas_resumen if not f["ok"]]
    print("  TOTAL " + str(len(filas_resumen)) + " cuenta(s) | "
          + str(sum(f["apuntes"] for f in filas_resumen)) + " apuntes | "
          + str(sum(f["grupos_previos"] for f in filas_resumen)) + " grupos previos | "
          + str(sum(f["grupos_nuevos"] for f in filas_resumen)) + " nuevos | "
          + str(sum(f["sin_cancelar"] for f in filas_resumen)) + " sin cancelar | pendiente total "
          + format(sum(f["pendiente"] for f in filas_resumen), ",.2f") + " € | verificacion: "
          + ("todas OK" if not no_ok else str(len(no_ok)) + " REVISAR ("
             + ", ".join(str(f["cuenta"]) for f in no_ok[:8]) + ("..." if len(no_ok) > 8 else "") + ")"))

    con_descuadre = [f for f in filas_resumen if abs(f["descuadre_previo"]) > 0.005]
    if con_descuadre:
        print("  AVISO: " + str(len(con_descuadre)) + " cuenta(s) con punteo "
              "contable que no suma 0 ("
              + ", ".join(str(f["cuenta"]) for f in con_descuadre[:5])
              + ("..." if len(con_descuadre) > 5 else "")
              + "). Se respeta tal cual: lo juzga el auditor.")
    sin_combinatoria = [f for f in filas_resumen
                        if f["sin_cancelar"] > MAX_LEFTOVER_FOR_COMBOS]
    if sin_combinatoria:
        print("  AVISO: en " + str(len(sin_combinatoria)) + " cuenta(s) quedaron "
              "mas de " + str(MAX_LEFTOVER_FOR_COMBOS) + " apuntes sin cancelar ("
              + ", ".join(str(f["cuenta"]) for f in sin_combinatoria[:5])
              + ("..." if len(sin_combinatoria) > 5 else "")
              + "): la busqueda por combinaciones no se intento ahi. Puede ser "
              "una cuenta que no parea por importes (ventas/cobros agregados "
              "por dia, remesas) o que falten periodos en el extracto.")
    if hallazgos["anomalos"]:
        print("  AVISO: " + str(hallazgos["anomalos"]) + " grupo(s) con el pago anterior "
              "a la fecha de la factura (" + str(hallazgos["anom_con_alternativa"])
              + " donde habia emparejamiento alternativo). Otros "
              + str(hallazgos["solo_fecha_registro"]) + " lo parecen solo por la fecha "
              "de registro y no se cuentan. Detalle en la hoja Criterios y hallazgos.")
    if hallazgos["aperturas_vivas"]:
        print("  AVISO: " + str(hallazgos["aperturas_vivas"]) + " apertura(s) sin cancelar, "
              + format(hallazgos["aperturas_importe_vivo"], ",.2f") + " €")
    if hallazgos["aperturas_no_identificadas"]:
        print("  AVISO: " + str(hallazgos["aperturas_no_identificadas"]) + " apertura(s) que NO se "
              "han podido identificar (varios apuntes el 1 de enero, o cuenta de un solo apunte), "
              + format(hallazgos["aperturas_importe_no_identificado"], ",.2f") + " €. El "
              "emparejamiento no las ha intentado: no es que no cuadren, es que no se sabe cual "
              "es la apertura")
    con_error = [f for f in filas_resumen if not f["ok"]]
    if con_error:
        print("  AVISO: " + str(len(con_error)) + " cuenta(s) no verifican -- revisar "
              "hoja Resumen antes de entregar")
    return 0


if __name__ == "__main__":
    sys.exit(main())
