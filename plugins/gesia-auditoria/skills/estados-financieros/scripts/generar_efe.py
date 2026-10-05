# -*- coding: utf-8 -*-
"""Escribe el papel de revision del estado de flujos de efectivo (EFE) en Excel.

    python generar_efe.py --cuadro cuadro.json --ajustes ajustes.json
        --estructura estructura.json --ejercicios ejercicios.json
        --cliente "..." --ejercicio 2025
        --salida "<expediente>/AsistenteIA/EstadosFinancieros/Flujos de Efectivo <CLIENTE> <EJERCICIO>.xlsx"

Cuatro hojas:

  FlujosEfectivo  el estado tal como Gesia lo presenta, con lo que calcula el programa y lo
                  que anaden los ajustes aprobados, linea a linea
  Ajustes         los ajustes del expediente, aprobados y no aprobados, con su descuadre
  Apuntes         el detalle de los aprobados: de que linea a que linea va cada cobro y pago
  Comprobaciones  los cuadres, con su semaforo

Este papel NO calcula el estado: lo lee del modulo EFE del expediente y lo cuadra. Gesia hace
la aritmetica -las variaciones de balance las saca solo- y deja el juicio al auditor, que es
quien mete los ajustes. No hay que competir con lo que la aplicacion ya hace bien.

Tres cosas medidas en el expediente con el estado hecho, y las tres son la razon de que este
papel exista:

  * **Solo cuentan los ajustes APROBADOS**, y la casilla «Aprobado» es el campo
    `GeneracionFondos`, que no significa lo que su nombre dice. Comprobado por aritmetica, no
    por fe: los ajustes del cuadro son exactamente la suma de los apuntes aprobados en las 159
    lineas, sin una excepcion.
  * **Cada ajuste es partida doble entre lineas del propio estado**, no entre cuentas
    contables, y sus cobros tienen que igualar a sus pagos. Los diez aprobados cuadran.
  * **El estado tiene que atar con el balance**: los flujos de las actividades suman la
    variacion de la tesoreria, y esa variacion es la del epigrafe de efectivo del balance.
    Medido: 685.252,52 por los tres caminos.

Como en el resto del skill, se escriben VALORES y no formulas.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import date

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from lib_eeff import (
    TOLERANCIA,
    a_float,
    ejercicios,
    es_si,
    hojas,
    leer_json,
    redondear,
    salida_utf8,
    saldo,
    texto,
)

FONT = "Calibri"
CABECERA_FILL = PatternFill("solid", fgColor="1F4E78")
CABECERA_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
TOTAL_FILL = PatternFill("solid", fgColor="D9E1F2")
AMARILLO = PatternFill("solid", fgColor="FFFF00")
GRIS = PatternFill("solid", fgColor="E7E6E6")
VERDE = Font(name=FONT, bold=True, color="006100", size=10)
ROJO = Font(name=FONT, bold=True, color="9C0006", size=10)
AMBAR = Font(name=FONT, bold=True, color="7F6000", size=10)
NORMAL = Font(name=FONT, size=10)
APAGADO = Font(name=FONT, size=10, color="808080")
NEGRITA = Font(name=FONT, bold=True, size=10)
EUROS = "#,##0.00"

# El tipo de linea va en CodigoLinea cuando la linea es estructural; en las de detalle ese
# campo lleva el codigo de la linea (una cuenta del PGC o un concepto propio del estado).
LINEA_FLUJO = "F"      # las actividades: explotacion, inversion, financiacion, tipos de cambio
LINEA_TOTAL = "T"      # los epigrafes numerados del modelo
LINEA_SUBTOTAL = "S"
LINEA_PARCIAL = "P"
ESTRUCTURALES = (LINEA_FLUJO, LINEA_TOTAL, LINEA_SUBTOTAL, LINEA_PARCIAL)


def _orden(fila: dict) -> int:
    o = texto(fila.get("CodigoOrden"))
    return int(o) if o.lstrip("-").isdigit() else 0


def _neto(fila: dict, origen: str, aplicacion: str) -> float:
    """Cobro menos pago. El estado se lee en neto; el desglose se queda al lado."""
    return redondear(a_float(fila.get(origen)) - a_float(fila.get(aplicacion)))


def _cabecera(ws, fila: int, titulos: list, anchos: list) -> None:
    for i, (t, a) in enumerate(zip(titulos, anchos), start=1):
        c = ws.cell(row=fila, column=i, value=t)
        c.fill, c.font = CABECERA_FILL, CABECERA_FONT
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = a
    ws.freeze_panes = ws.cell(row=fila + 1, column=1)


def _titulo(ws, cliente: str, ejercicio: str, subtitulo: str) -> int:
    ws["A1"] = f"{cliente} · ejercicio {ejercicio}"
    ws["A1"].font = Font(name=FONT, bold=True, size=13)
    ws["A2"] = subtitulo
    ws["A2"].font = Font(name=FONT, size=10, italic=True, color="595959")
    ws["A3"] = ("Papel de trabajo preparado por Asistente IA el "
                + date.today().strftime("%d/%m/%Y")
                + ". Revisión: lee el módulo EFE del expediente y lo cuadra, no calcula el estado.")
    ws["A3"].font = Font(name=FONT, size=9, color="808080")
    return 5


def _importe(ws, fila: int, col: int, valor: float, fuente=None, marcar: bool = False):
    c = ws.cell(row=fila, column=col, value=redondear(valor))
    c.number_format, c.font = EUROS, (fuente or NORMAL)
    if marcar and abs(valor) > TOLERANCIA:
        c.fill = AMARILLO
    return c


def _fecha(v) -> str:
    """El API devuelve la fecha con hora pegada: «31/12/2025 0:00:00». Cortar a diez
    caracteres deja «31/12/25 0», que es una fecha que no existe."""
    return texto(v).split(" ")[0]


def _agrupar(ajustes: list) -> dict:
    """{numero de asiento: {descripcion, fecha, aprobado, apuntes}}.

    La exportacion viene de un LEFT JOIN, asi que la cabecera se repite en cada apunte y un
    ajuste sin apuntes llega con la fila de cabecera y el apunte vacio.
    """
    res: dict = {}
    for x in ajustes or []:
        n = texto(x.get("NumeroAsientoOA"))
        if not n:
            continue
        a = res.setdefault(n, {"desc": texto(x.get("Descripcion")), "fecha": texto(x.get("Fecha")),
                               "aprobado": es_si(x.get("Aprobado")), "apuntes": []})
        if texto(x.get("ApunteOA")):
            a["apuntes"].append(x)
    return res


def _totales(apuntes: list) -> tuple:
    cobro = redondear(sum(a_float(p.get("Origen")) for p in apuntes))
    pago = redondear(sum(a_float(p.get("Aplicacion")) for p in apuntes))
    return cobro, pago, redondear(cobro - pago)


def _hoja_estado(wb: Workbook, cuadro: list, cliente: str, ejercicio: str) -> None:
    ws = wb.create_sheet("FlujosEfectivo")
    fila = _titulo(ws, cliente, ejercicio,
                   "El estado de flujos de efectivo del expediente. «Presentado» es lo que sale "
                   "en las cuentas anuales: lo que calcula Gesia más los ajustes aprobados. En "
                   "los totales y subtotales la columna de ajustes va con una raya, porque Gesia "
                   "recalcula el presentado y no la mantiene ahí.")
    _cabecera(ws, fila,
              ["Línea", "Concepto", "Calculado por Gesia", "Ajustes aprobados", "Presentado",
               "Cobro presentado", "Pago presentado"],
              [10, 58, 19, 18, 18, 18, 18])
    fila += 1
    for f in sorted(cuadro, key=_orden):
        tipo = texto(f.get("CodigoLinea"))
        gesia = _neto(f, "Origen", "Aplicacion")
        ajuste = _neto(f, "OrigenAjuste", "AplicacionAjuste")
        presentado = _neto(f, "OrigenAjustado", "AplicacionAjustada")
        estructural = tipo in ESTRUCTURALES
        if not estructural and not any(abs(v) > TOLERANCIA for v in (gesia, ajuste, presentado)):
            continue
        if estructural and not any(abs(v) > TOLERANCIA for v in (gesia, ajuste, presentado)) \
                and tipo in (LINEA_SUBTOTAL, LINEA_PARCIAL):
            continue
        fuente = NEGRITA if tipo in (LINEA_FLUJO, LINEA_TOTAL) else NORMAL
        ws.cell(row=fila, column=1, value=tipo).font = NORMAL
        c = ws.cell(row=fila, column=2, value=texto(f.get("Descripcion")))
        c.font = fuente
        c.alignment = Alignment(indent=0 if tipo in (LINEA_FLUJO, LINEA_TOTAL) else 2)
        _importe(ws, fila, 3, gesia, fuente)
        # En las lineas estructurales Gesia NO mantiene la columna de ajuste: recalcula el
        # ajustado y deja el ajuste a cero. Escribir ese cero diria «aqui no hay ajustes», que
        # es falso -«Movimientos de provisiones a eliminar» va de -9.583,49 a 0 con el ajuste
        # a cero-, y ademas invita a sumar tres columnas que no suman. Se deja en blanco.
        if estructural:
            ws.cell(row=fila, column=4, value="—").font = APAGADO
            ws.cell(row=fila, column=4).alignment = Alignment(horizontal="center")
        else:
            _importe(ws, fila, 4, ajuste, fuente, marcar=True)
        _importe(ws, fila, 5, presentado, fuente)
        _importe(ws, fila, 6, a_float(f.get("OrigenAjustado")), fuente)
        _importe(ws, fila, 7, a_float(f.get("AplicacionAjustada")), fuente)
        if tipo == LINEA_FLUJO:
            for j in range(1, 8):
                ws.cell(row=fila, column=j).fill = TOTAL_FILL
        fila += 1


def _hoja_ajustes(wb: Workbook, grupos: dict, cliente: str, ejercicio: str) -> tuple:
    """Devuelve (n aprobados, descuadrados, no aprobados con importe)."""
    ws = wb.create_sheet("Ajustes")
    fila = _titulo(ws, cliente, ejercicio,
                   "Los ajustes al estado que tiene el expediente. SOLO CUENTAN LOS APROBADOS: "
                   "los demás son propuestas que el auditor no ha aceptado y no suman nada.")
    _cabecera(ws, fila,
              ["Nº", "Fecha", "Descripción", "Aprobado", "Apuntes", "Cobros", "Pagos", "Descuadre"],
              [6, 12, 52, 11, 9, 17, 17, 14])
    fila += 1
    descuadrados, fantasma, aprobados = [], [], 0
    for n, a in sorted(grupos.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        cobro, pago, desc = _totales(a["apuntes"])
        tiene = abs(cobro) > TOLERANCIA or abs(pago) > TOLERANCIA
        if not a["aprobado"] and not tiene:
            continue          # plantilla del catalogo sin usar: no ensucia el papel
        fuente = NORMAL if a["aprobado"] else APAGADO
        ws.cell(row=fila, column=1, value=n).font = fuente
        ws.cell(row=fila, column=2, value=_fecha(a["fecha"])).font = fuente
        ws.cell(row=fila, column=3, value=a["desc"]).font = fuente
        ws.cell(row=fila, column=4, value="SÍ" if a["aprobado"] else "no cuenta").font = fuente
        ws.cell(row=fila, column=5, value=len(a["apuntes"])).font = fuente
        _importe(ws, fila, 6, cobro, fuente)
        _importe(ws, fila, 7, pago, fuente)
        _importe(ws, fila, 8, desc, fuente)
        if not a["aprobado"]:
            for j in range(1, 9):
                ws.cell(row=fila, column=j).fill = GRIS
            if tiene:
                fantasma.append((n, a["desc"], redondear(cobro)))
        else:
            aprobados += 1
            if abs(desc) > TOLERANCIA:
                descuadrados.append((n, a["desc"], desc))
                ws.cell(row=fila, column=8).fill = AMARILLO
        fila += 1
    if not aprobados:
        ws.cell(row=fila, column=1,
                value="El expediente no tiene ningún ajuste aprobado al estado de flujos.").font = NORMAL
    return aprobados, descuadrados, fantasma


def _hoja_apuntes(wb: Workbook, grupos: dict, cuadro: list, cliente: str, ejercicio: str) -> None:
    ws = wb.create_sheet("Apuntes")
    fila = _titulo(ws, cliente, ejercicio,
                   "El detalle de los ajustes aprobados. Cada apunte va de una línea del estado a "
                   "otra: Cuenta y Contrapartida NO son cuentas contables, son líneas del cuadro.")
    _cabecera(ws, fila,
              ["Ajuste", "Descripción del ajuste", "Línea", "Concepto del apunte",
               "Contrapartida", "Cobro", "Pago"],
              [8, 36, 10, 52, 14, 16, 16])
    fila += 1
    nombre = {texto(f.get("CodigoLinea")): texto(f.get("Descripcion")) for f in cuadro
              if texto(f.get("CodigoLinea")) not in ESTRUCTURALES}
    for n, a in sorted(grupos.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        if not a["aprobado"]:
            continue
        for p in a["apuntes"]:
            linea = texto(p.get("Cuenta"))
            ws.cell(row=fila, column=1, value=n).font = NORMAL
            ws.cell(row=fila, column=2, value=a["desc"]).font = NORMAL
            ws.cell(row=fila, column=3, value=linea).font = NORMAL
            ws.cell(row=fila, column=4,
                    value=texto(p.get("Concepto")) or nombre.get(linea, "")).font = NORMAL
            ws.cell(row=fila, column=5, value=texto(p.get("Contrapartida"))).font = NORMAL
            _importe(ws, fila, 6, a_float(p.get("Origen")))
            _importe(ws, fila, 7, a_float(p.get("Aplicacion")))
            fila += 1


def _hoja_comprobaciones(wb: Workbook, comprobaciones: list, cliente: str, ejercicio: str) -> None:
    ws = wb.create_sheet("Comprobaciones")
    fila = _titulo(ws, cliente, ejercicio,
                   "Los cuadres del papel. Si alguno falla, el estado que hay en el expediente no "
                   "se sostiene.")
    todo = all(ok is not False for _, ok, _ in comprobaciones)
    c = ws.cell(row=fila, column=1,
                value="TODO CUADRA" if todo else "HAY DESCUADRES: no entregar sin leerlos")
    c.font = VERDE if todo else ROJO
    fila += 2
    _cabecera(ws, fila, ["Comprobación", "Resultado", "Detalle"], [64, 18, 62])
    fila += 1
    for t, ok, detalle in comprobaciones:
        ws.cell(row=fila, column=1, value=t).font = NORMAL
        etiqueta = "A TENER EN CUENTA" if ok is None else ("CUADRA" if ok else "NO CUADRA")
        r = ws.cell(row=fila, column=2, value=etiqueta)
        r.font = AMBAR if ok is None else (VERDE if ok else ROJO)
        d = ws.cell(row=fila, column=3, value=detalle)
        d.font = NORMAL
        d.alignment = Alignment(wrap_text=True, vertical="top")
        if ok is False:
            ws.cell(row=fila, column=1).fill = AMARILLO
        fila += 1


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("--cuadro", required=True, help="JSON de CuadroFinanciacion del ejercicio")
    p.add_argument("--ajustes", required=True, help="JSON de AsientosOA LEFT JOIN ApuntesOA")
    p.add_argument("--estructura", required=True, help="JSON del balance, para atar con el efectivo")
    p.add_argument("--ejercicios", required=True)
    p.add_argument("--cliente", required=True)
    p.add_argument("--ejercicio", default="")
    p.add_argument("--salida", required=True)
    a = p.parse_args()

    cuadro = leer_json(a.cuadro)
    ajustes = leer_json(a.ajustes)
    estructura = leer_json(a.estructura)
    anios = ejercicios(leer_json(a.ejercicios))

    # ── el primer corte del documento: ¿hay estado? ──────────────────────────
    if not cuadro:
        print("❌ el expediente NO tiene estado de flujos de efectivo: la tabla del cuadro está "
              "vacía. En los modelos de pymes esto es lo correcto, porque el plan no lo exige, "
              "así que no hay nada que revisar ni nada que avisar.")
        return 2
    if not any(abs(_neto(f, "OrigenAjustado", "AplicacionAjustada")) > TOLERANCIA for f in cuadro):
        print("❌ el cuadro existe pero está a cero en todas sus líneas: el estado no se ha hecho.")
        return 2

    ejercicio = a.ejercicio or anios.get("1", "")
    grupos = _agrupar(ajustes)

    wb = Workbook()
    wb.remove(wb.active)
    _hoja_estado(wb, cuadro, a.cliente, ejercicio)
    aprobados, descuadrados, fantasma = _hoja_ajustes(wb, grupos, a.cliente, ejercicio)
    _hoja_apuntes(wb, grupos, cuadro, a.cliente, ejercicio)

    comprobaciones = []
    # LA PRIMERA, y la que mas engaña si falta. Gesia rellena el cuadro solo, comparando
    # saldos de balance, en cuanto hay dos ejercicios cargados. Un cuadro con cifras y sin un
    # solo ajuste aprobado NO es un estado de flujos hecho: es la aritmetica del programa sin
    # el criterio del auditor -sin amortizaciones, sin impuesto, sin intereses-, y cuadra
    # perfectamente consigo mismo. Medido en un expediente terminado de modelo reducido: 159
    # lineas con importe, 29 plantillas en el catalogo y CERO ajustes aprobados.
    comprobaciones.append((
        "El estado está trabajado: tiene ajustes del auditor aprobados",
        True if aprobados else None,
        f"{aprobados} ajustes aprobados" if aprobados else
        f"NINGUNO de los {len(grupos)} del catálogo está aprobado. El cuadro tiene cifras "
        "porque Gesia calcula solo las variaciones de balance, pero sin ajustes esto no es "
        "todavía un estado de flujos: falta el criterio del auditor. Cuadra consigo mismo "
        "igualmente, así que el verde de las demás comprobaciones no dice que esté hecho"))
    comprobaciones.append((
        "Cada ajuste aprobado cuadra: sus cobros suman lo mismo que sus pagos",
        not descuadrados,
        f"cuadran los {aprobados} ajustes aprobados" if not descuadrados
        else f"{len(descuadrados)} descuadran: "
             + "; ".join(f"nº {n} {d} ({v:,.2f} €)" for n, d, v in descuadrados[:3])))

    # LA COMPROBACION QUE JUSTIFICA EL PAPEL: el cuadro suma los aprobados, y solo esos
    porO, porA = {}, {}
    for n, g in grupos.items():
        if not g["aprobado"]:
            continue
        for p_ in g["apuntes"]:
            c = texto(p_.get("Cuenta"))
            porO[c] = redondear(porO.get(c, 0.0) + a_float(p_.get("Origen")))
            porA[c] = redondear(porA.get(c, 0.0) + a_float(p_.get("Aplicacion")))
    rotas = []
    for f in cuadro:
        c = texto(f.get("CodigoLinea"))
        if c in ESTRUCTURALES:
            continue
        dO = redondear(a_float(f.get("OrigenAjuste")) - porO.get(c, 0.0))
        dA = redondear(a_float(f.get("AplicacionAjuste")) - porA.get(c, 0.0))
        if abs(dO) > TOLERANCIA or abs(dA) > TOLERANCIA:
            rotas.append((c, texto(f.get("Descripcion")), redondear(dO - dA)))
    comprobaciones.append((
        "Los ajustes que lleva el estado son exactamente la suma de los apuntes APROBADOS",
        not rotas,
        f"coincide en las {len(cuadro)} líneas del cuadro" if not rotas
        else f"{len(rotas)} líneas no coinciden: "
             + "; ".join(f"{c} {d} ({v:,.2f} €)" for c, d, v in rotas[:3])))

    comprobaciones.append((
        "Ningún ajuste sin aprobar lleva importe que pudiera colarse",
        True if not fantasma else None,
        "ninguno" if not fantasma
        else f"{len(fantasma)} ajuste(s) con importe y SIN aprobar, que por eso no suman: "
             + "; ".join(f"nº {n} {d} ({v:,.2f} €)" for n, d, v in fantasma[:3])
             + ". Si alguno debía entrar, lo aprueba el auditor en Gesia"))

    # el estado contra si mismo: las actividades suman la variacion de la tesoreria
    flujos = [f for f in cuadro if texto(f.get("CodigoLinea")) == LINEA_FLUJO]
    ultima = max(cuadro, key=_orden)
    variacion = -_neto(ultima, "OrigenAjustado", "AplicacionAjustada")
    if not flujos:
        comprobaciones.append((
            "Los flujos de las actividades suman la variación de la tesorería", None,
            "no se han encontrado líneas de actividad en este cuadro: no se ha podido comprobar"))
        suma_flujos = None
    else:
        suma_flujos = redondear(sum(_neto(f, "OrigenAjustado", "AplicacionAjustada") for f in flujos))
        d = redondear(suma_flujos - variacion)
        comprobaciones.append((
            "Los flujos de las actividades suman la variación de la tesorería",
            abs(d) <= TOLERANCIA,
            f"{variacion:,.2f} € por los dos caminos" if abs(d) <= TOLERANCIA
            else f"difieren en {d:,.2f} €"))

    # y contra el balance, que es el cuadre de verdad
    efectivo = [f for f in hojas(estructura)
                if "efectivo" in texto(f.get("Concepto")).lower()
                or "tesorer" in texto(f.get("Concepto")).lower()]
    if not efectivo or len(anios) < 2:
        comprobaciones.append((
            "La variación de la tesorería es la del efectivo en el balance", None,
            "no se ha localizado el epígrafe de efectivo del balance, o no hay ejercicio "
            "anterior cargado: la comprobación no se ha podido hacer"))
    else:
        var_balance = redondear(sum(saldo(f, 1) - saldo(f, 2) for f in efectivo))
        d = redondear(var_balance - variacion)
        comprobaciones.append((
            "La variación de la tesorería es la del efectivo en el balance",
            abs(d) <= TOLERANCIA,
            f"{var_balance:,.2f} €, igual en el estado y en el balance" if abs(d) <= TOLERANCIA
            else f"el estado dice {variacion:,.2f} € y el balance {var_balance:,.2f} €: "
                 f"difieren en {d:,.2f} €"))

    _hoja_comprobaciones(wb, comprobaciones, a.cliente, ejercicio)

    destino = os.path.abspath(a.salida)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    wb.save(destino)
    print(f"✔ papel escrito: {destino}")
    print(f"  hojas: {', '.join(wb.sheetnames)}")
    print(f"  ajustes: {aprobados} aprobados de {len(grupos)} en el catálogo del expediente")
    if suma_flujos is not None:
        print(f"  variación de la tesorería: {variacion:,.2f}")
    malas = [t for t, ok, _ in comprobaciones if ok is False]
    avisos = [t for t, ok, _ in comprobaciones if ok is None]
    if malas or avisos:
        print("\nPARA CONTAR AL ENTREGAR (tal cual, sin resumir):")
        for t, ok, d in comprobaciones:
            # El titulo es la AFIRMACION que se comprueba, y aqui no hay columna de semaforo
            # que lo matice: pegarlo al detalle deja «El estado esta trabajado · NINGUNO esta
            # aprobado», que se lee al reves y un modelo con prisa copia la primera mitad.
            # Cuando la comprobacion no se cumple, la afirmacion no se repite (25/09/2026).
            if ok is False:
                print(f"  - NO CUADRA: {d}")
            elif ok is None:
                print(f"  - A TENER EN CUENTA: {d}")
        return 1
    print("  todas las comprobaciones cuadran")
    return 0


if __name__ == "__main__":
    sys.exit(main())
