# -*- coding: utf-8 -*-
"""Propone importes para los ajustes del estado de flujos, desde el catalogo del expediente.

    python proponer_efe.py --catalogo catalogo.json --cuentas cuentas.json
        --cuadro cuadro.json --cliente "..." --ejercicio 2025
        --salida "<expediente>/AsistenteIA/EstadosFinancieros/Propuesta EFE <CLIENTE> <EJERCICIO>.xlsx"

Gesia deja el importe de cada ajuste en blanco: la plantilla dice QUE lineas se mueven y en
que sentido, y el auditor pone CUANTO. Este papel propone ese cuanto donde se puede sacar de
la contabilidad del propio expediente, y donde no se puede lo dice y deja la plantilla con su
criterio para que la rellene quien firma.

**Nada de esto se escribe en Gesia.** El MCP solo lee. Es una propuesta en papel, y cuando el
API tenga escritura entrara igual: como ajuste NO APROBADO y con «Asistente IA:» al principio
de la descripcion, para que nunca se confunda con el trabajo del auditor.

**El catalogo se lee del expediente, nunca del master ni cableado aqui.** El master trae 29
plantillas y el auditor las amplia -35 en uno de los medidos-; cablearlas ignoraria en
silencio las que anada.

## De donde sale cada regla, y por que solo hay cuatro

Las reglas NO salen de leer el criterio y deducir: salen de reproducir lo que un auditor puso
de verdad. En el expediente que tiene el estado hecho se compararon las diez propuestas de
estas reglas contra los diez ajustes aprobados. Cuatro dan el importe exacto, y una de ellas
-la amortizacion- acierta APUNTE POR APUNTE, no solo en el total:

    distribucion del resultado   848.404,89  =  apertura de la 129
    amortizacion                 140.498,55  =  680 + 681 + 682, cada una con su par
    gastos financieros           220.875,62  =  saldo de la 66
    ingresos financieros         496.068,23  =  saldo de la 76

Las que NO se proponen, y el motivo, que es igual de util:

  * **impuesto de sociedades**: el auditor puso 315.413,38 y el gasto de la 630 son
    240.077,05. La diferencia es la variacion del saldo con Hacienda, porque la linea es de
    COBROS Y PAGOS por impuesto y no del gasto devengado. Con un solo caso no se sabe que
    cuentas entran, asi que no se propone.
  * **provisiones**: el auditor lo llevo por la 529 y no por la 14, que es la que nombraria
    cualquier lectura del criterio.
  * **distribucion de PERDIDAS**: la plantilla existe, pero no hay ningun expediente medido en
    que se haya usado. Se escribio por simetria con la de beneficios y al probarla colaba el
    movimiento de la cuenta 13 -subvenciones traspasadas a resultados- como si fuera una
    aplicacion del resultado. Cuadraba, y habria pasado por buena.
  * las demas, porque en el unico expediente medido nadie las uso y no hay contra que
    contrastar.

Una regla sin verificar que acierte por casualidad es peor que no tener regla: el auditor la
daria por buena.

## La cuenta de la que sale el importe se lee distinto segun el grupo

Para las de resultados -grupos 6 y 7- vale el SALDO del ejercicio, que es el gasto o el
ingreso del año. Para las de balance vale el MOVIMIENTO, cierre menos apertura. Medido: la 66
tiene saldo 220.875,62 y movimiento 74.629,14, y el ajuste lleva el saldo.
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
    exigir_tokens,
    TOLERANCIA,
    a_float,
    es_si,
    leer_json,
    redondear,
    salida_utf8,
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

# Lo que el ajuste llevara en Gesia cuando el API sepa escribir. Va aqui, en el papel, para
# que el auditor que lo teclee a mano ponga ya la misma marca.
PREFIJO_IA = "Asistente IA: "

GRUPOS_RESULTADO = ("6", "7")


class Saldos:
    """Los saldos del expediente, leidos como toca segun el grupo de la cuenta."""

    def __init__(self, cuentas: list):
        self._por = {texto(c.get("Cuenta")): c for c in cuentas or []}

    def existe(self, cuenta: str) -> bool:
        return cuenta in self._por

    def importe(self, cuenta: str):
        """El saldo del año para las de resultados, el movimiento para las de balance.

        Devuelve None si la cuenta no esta en el plan del expediente, que no es lo mismo que
        cero: una cuenta que no existe no da importe, y proponer cero seria inventarse que el
        concepto no se ha movido.
        """
        c = self._por.get(cuenta)
        if c is None:
            return None
        if cuenta[:1] in GRUPOS_RESULTADO:
            return abs(redondear(a_float(c.get("SaldoAuditoria"))))
        return abs(redondear(a_float(c.get("SaldoCliente")) - a_float(c.get("SaldoAnterior"))))

    def apertura(self, cuenta: str):
        c = self._por.get(cuenta)
        return None if c is None else redondear(a_float(c.get("SaldoAnterior")))

    def movimiento(self, cuenta: str):
        c = self._por.get(cuenta)
        if c is None:
            return None
        return redondear(a_float(c.get("SaldoCliente")) - a_float(c.get("SaldoAnterior")))


def _par(apunte: dict) -> tuple:
    return (texto(apunte.get("Cuenta")).upper(), texto(apunte.get("Contrapartida")).upper())


# ── LAS REGLAS ────────────────────────────────────────────────────────────────
# Cada una: los pares de linea y contrapartida que tiene que tener la plantilla para que la
# regla le aplique -se reconoce por LA FORMA, no por el texto de la descripcion, que el
# auditor puede cambiar-, y una funcion que reparte importes por par.
# La funcion devuelve {par: (cobro, pago)} y una linea de texto diciendo de donde sale.

def _r_amortizacion(apuntes: list, s: Saldos):
    tramos = [("280", "680"), ("281", "681"), ("282", "682")]
    imp, fuentes = {}, []
    for acumulada, dotacion in tramos:
        v = s.importe(dotacion)
        if not v:
            continue
        imp[("C68", acumulada)] = (v, 0.0)
        imp[(acumulada, "C68")] = (0.0, v)
        fuentes.append(f"{dotacion} = {v:,.2f}")
    if not imp:
        return None, ""
    return imp, "dotación del ejercicio, cada tramo con su amortización acumulada: " + "; ".join(fuentes)


def _r_gastos_financieros(apuntes: list, s: Saldos):
    v = s.importe("66")
    if not v:
        return None, ""
    return {("C66", "G66"): (v, 0.0), ("G66", "C66"): (0.0, v)}, f"saldo de la 66 del ejercicio = {v:,.2f}"


def _r_ingresos_financieros(apuntes: list, s: Saldos):
    v = s.importe("76")
    if not v:
        return None, ""
    return {("C76", "C76"): (v, 0.0), ("G76", "C76"): (0.0, v)}, f"saldo de la 76 del ejercicio = {v:,.2f}"


def _distribucion(s: Saldos, beneficio: bool, contra129: str, destinos: tuple, resto_a: str):
    """La distribucion del resultado del ejercicio ANTERIOR, que es la apertura de la 129.

    EL SIGNO ELIGE LA PLANTILLA, y hay dos. Con la apertura acreedora hubo beneficio y el
    resultado sale de la 129 hacia reservas, remanente o dividendo; con la apertura deudora
    hubo perdida y va al reves. Las dos plantillas tienen una forma parecida, asi que sin
    mirar el signo se rellena la que no es: medido en un expediente con perdidas de 5,1
    millones, que habria salido propuesto como reparto de beneficios.
    """
    apertura = s.apertura("129")
    if apertura is None or abs(apertura) < TOLERANCIA:
        return None, ""
    if beneficio != (apertura < 0):
        return None, ""
    total = abs(apertura)
    que = "beneficio" if beneficio else "pérdida"
    # con beneficio la 129 es el cobro y los destinos son pagos; con perdida, al reves.
    # La contrapartida de la pata de la 129 es LA QUE TRAE LA PLANTILLA, no el primer destino:
    # emparejarla con el destino deja esa pata sin importe y la propuesta descuadra entera.
    imp = {("129", contra129): ((total, 0.0) if beneficio else (0.0, total))}
    repartido, fuentes = 0.0, [f"apertura de la 129 = {total:,.2f} ({que} del ejercicio anterior)"]
    for destino in destinos:
        m = s.movimiento(destino)
        if m is None or abs(m) < TOLERANCIA:
            continue
        v = abs(m)
        imp[(destino, "129")] = ((0.0, v) if beneficio else (v, 0.0))
        repartido = redondear(repartido + v)
        fuentes.append(f"a la {destino}, {v:,.2f} (su movimiento del año)")
    resto = redondear(total - repartido)
    if abs(resto) > TOLERANCIA:
        imp[(resto_a, "129")] = ((0.0, resto) if beneficio else (resto, 0.0))
        fuentes.append(f"y el resto, {resto:,.2f}, a la {resto_a}: CONFÍRMALO con el acuerdo de "
                       "la Junta, que es quien decide el destino del resultado")
    return imp, "; ".join(fuentes)


def _r_distribucion_beneficio(apuntes: list, s: Saldos):
    return _distribucion(s, True, "120", ("11", "120", "121"), "526")


# La variante de PERDIDAS no se propone. Existe en el catalogo y se escribio aqui por
# simetria con la de beneficios, pero NO hay ningun expediente medido en que el auditor la
# haya usado, asi que no hay contra que contrastarla. Y al probarla se vio por que importa:
# repartia la perdida entre los destinos de la plantilla y colaba el movimiento de la cuenta
# 13 -subvenciones traspasadas a resultados, que no tiene nada que ver con el reparto- como
# si fuera una aplicacion del resultado. Cuadraba, porque el resto iba a la 121, y habria
# pasado por buena. Cuando haya un expediente con perdidas repartidas, se mide y se vuelve.


REGLAS = (
    ("Amortización del ejercicio", {("C68", "280"), ("C68", "281"), ("C68", "282")}, _r_amortizacion),
    ("Gastos financieros", {("C66", "G66"), ("G66", "C66")}, _r_gastos_financieros),
    ("Ingresos financieros", {("G76", "C76")}, _r_ingresos_financieros),
    # solo la de beneficios, y con el signo comprobado: con la apertura deudora hubo perdida
    # y esta regla NO propone nada, que es lo correcto mientras la de perdidas no se mida
    ("Distribución del resultado (beneficio)",
     {("129", "120"), ("11", "129"), ("526", "129")}, _r_distribucion_beneficio),
)


def agrupar(catalogo: list) -> dict:
    res: dict = {}
    for x in catalogo or []:
        n = texto(x.get("NumeroAsientoOA"))
        if not n:
            continue
        a = res.setdefault(n, {"desc": texto(x.get("Descripcion")),
                               "criterio": " ".join(texto(x.get("Observaciones")).split()),
                               "aprobado": es_si(x.get("Aprobado")), "apuntes": []})
        if texto(x.get("ApunteOA")):
            a["apuntes"].append(x)
    return res


def regla_de(plantilla: dict):
    """La regla que le toca a una plantilla, por LA FORMA de sus apuntes."""
    pares = {_par(p) for p in plantilla["apuntes"]}
    for nombre, firma, fn in REGLAS:
        if firma <= pares:
            return nombre, fn
    return None, None


def proponer(grupos: dict, s: Saldos) -> list:
    """[{numero, desc, regla, fuente, lineas: [(par, concepto, cobro, pago)], puesto}]"""
    salida = []
    for n, a in sorted(grupos.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        nombre, fn = regla_de(a)
        if not fn:
            continue
        imp, fuente = fn(a["apuntes"], s)
        if not imp:
            continue
        lineas = []
        for p in a["apuntes"]:
            cobro, pago = imp.get(_par(p), (0.0, 0.0))
            lineas.append((_par(p), texto(p.get("Concepto")), cobro, pago))
        puesto = redondear(sum(a_float(p.get("Origen")) for p in a["apuntes"]))
        salida.append({"numero": n, "desc": a["desc"], "regla": nombre, "fuente": fuente,
                       "criterio": a["criterio"], "lineas": lineas,
                       "aprobado": a["aprobado"], "puesto": puesto})
    return salida


# ── el papel ──────────────────────────────────────────────────────────────────

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
    ws["A3"] = ("Preparado por Asistente IA el " + date.today().strftime("%d/%m/%Y")
                + ". PROPUESTA: no está en Gesia, no está aprobada, y quien decide es el auditor.")
    ws["A3"].font = Font(name=FONT, size=9, color="808080")
    return 5


def _importe(ws, fila, col, valor, fuente=None):
    c = ws.cell(row=fila, column=col, value=redondear(valor))
    c.number_format, c.font = EUROS, (fuente or NORMAL)
    return c


def _hoja_propuestas(wb: Workbook, props: list, cliente: str, ejercicio: str) -> tuple:
    ws = wb.create_sheet("Propuestas")
    fila = _titulo(ws, cliente, ejercicio,
                   "Importes propuestos para las plantillas de ajuste del expediente. En Gesia "
                   "entran SIEMPRE como no aprobados y con «Asistente IA:» delante.")
    _cabecera(ws, fila,
              ["Ajuste", "Línea", "Contrapartida", "Concepto del apunte", "Cobro", "Pago", "De dónde sale"],
              [9, 10, 13, 50, 16, 16, 66])
    fila += 1
    descuadres, ya_puestos = [], []
    for p in props:
        c = ws.cell(row=fila, column=1, value=f"nº {p['numero']}")
        c.font = NEGRITA
        t = ws.cell(row=fila, column=2, value=PREFIJO_IA + p["desc"])
        t.font = NEGRITA
        ws.cell(row=fila, column=7, value=p["fuente"]).font = APAGADO
        ws.cell(row=fila, column=7).alignment = Alignment(wrap_text=True, vertical="top")
        for j in range(1, 8):
            ws.cell(row=fila, column=j).fill = TOTAL_FILL
        fila += 1
        cobros = pagos = 0.0
        for (linea, contra), concepto, cobro, pago in p["lineas"]:
            ws.cell(row=fila, column=2, value=linea).font = NORMAL
            ws.cell(row=fila, column=3, value=contra).font = NORMAL
            ws.cell(row=fila, column=4, value=concepto).font = NORMAL
            _importe(ws, fila, 5, cobro)
            _importe(ws, fila, 6, pago)
            cobros, pagos = redondear(cobros + cobro), redondear(pagos + pago)
            fila += 1
        d = redondear(cobros - pagos)
        ws.cell(row=fila, column=4, value="suma de la propuesta").font = NEGRITA
        _importe(ws, fila, 5, cobros, NEGRITA)
        _importe(ws, fila, 6, pagos, NEGRITA)
        if abs(d) > TOLERANCIA:
            descuadres.append((p["numero"], p["desc"], d))
            ws.cell(row=fila, column=6).fill = AMARILLO
        if p["aprobado"]:
            dif = redondear(p["puesto"] - cobros)
            ya_puestos.append((p["numero"], p["desc"], p["puesto"], cobros, dif))
            ws.cell(row=fila + 1, column=4,
                    value=("YA ESTÁ PUESTO Y APROBADO en Gesia por "
                           + f"{p['puesto']:,.2f} €. "
                           + ("Coincide con la propuesta." if abs(dif) < TOLERANCIA
                              else f"NO coincide: difiere en {dif:,.2f} €."))).font = (
                NORMAL if abs(dif) < TOLERANCIA else ROJO)
            fila += 1
        fila += 2
    if not props:
        ws.cell(row=fila, column=1,
                value="No hay ninguna plantilla del catálogo a la que aplique una regla "
                      "verificada. Mira la hoja Catalogo: están todas, con su criterio.").font = NORMAL
    return descuadres, ya_puestos


def total_propuesto(p: dict) -> float:
    """Lo que suma la propuesta de una plantilla.

    Redondeando apunte a apunte, igual que la hoja Propuestas, para que las dos hojas
    digan el mismo numero y no se separen por un centimo."""
    t = 0.0
    for _, _, cobro, _ in p["lineas"]:
        t = redondear(t + cobro)
    return t


def _hoja_catalogo(wb: Workbook, grupos: dict, propuesto: dict, cliente: str, ejercicio: str) -> None:
    ws = wb.create_sheet("Catalogo")
    fila = _titulo(ws, cliente, ejercicio,
                   "TODAS las plantillas de ajuste que tiene este expediente, con el criterio "
                   "que trae cada una. Las que no llevan propuesta las rellena el auditor. "
                   "Son DOS importes distintos: «ya aprobado en Gesia» es lo que está registrado "
                   "hoy en el expediente —0,00 mientras no se apruebe nada—, y «propuesto» es lo "
                   "que propone este papel, desglosado en la hoja Propuestas.")
    _cabecera(ws, fila,
              ["Nº", "Descripción", "Aprobado", "Apuntes", "Importe ya aprobado en Gesia",
               "Importe propuesto", "¿Propuesta?", "Criterio de la plantilla"],
              [6, 44, 11, 9, 20, 17, 13, 96])
    fila += 1
    for n, a in sorted(grupos.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0):
        puesto = redondear(sum(a_float(p.get("Origen")) for p in a["apuntes"]))
        usada = a["aprobado"] or abs(puesto) > TOLERANCIA
        fuente = NORMAL if usada or n in propuesto else APAGADO
        ws.cell(row=fila, column=1, value=n).font = fuente
        ws.cell(row=fila, column=2, value=a["desc"]).font = fuente
        ws.cell(row=fila, column=3, value="SÍ" if a["aprobado"] else "no").font = fuente
        ws.cell(row=fila, column=4, value=len(a["apuntes"])).font = fuente
        _importe(ws, fila, 5, puesto, fuente)
        # En blanco, no 0,00, cuando no hay propuesta: un cero en esta columna es justo la
        # lectura que hizo perder el tiempo al auditor el 26/09/2026.
        if n in propuesto:
            _importe(ws, fila, 6, propuesto[n], fuente)
        ws.cell(row=fila, column=7, value="sí" if n in propuesto else "—").font = fuente
        c = ws.cell(row=fila, column=8, value=a["criterio"])
        c.font = fuente
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if n in propuesto:
            ws.cell(row=fila, column=7).fill = TOTAL_FILL
        elif not usada:
            for j in range(1, 9):
                ws.cell(row=fila, column=j).fill = GRIS
        fila += 1


def _hoja_comprobaciones(wb: Workbook, comprobaciones: list, cliente: str, ejercicio: str) -> None:
    ws = wb.create_sheet("Comprobaciones")
    fila = _titulo(ws, cliente, ejercicio, "Los cuadres de la propuesta.")
    todo = all(ok is not False for _, ok, _ in comprobaciones)
    c = ws.cell(row=fila, column=1,
                value="TODO CUADRA" if todo else "HAY DESCUADRES: no llevar esto a Gesia sin leerlos")
    c.font = VERDE if todo else ROJO
    fila += 2
    _cabecera(ws, fila, ["Comprobación", "Resultado", "Detalle"], [62, 18, 68])
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
    p.add_argument("--catalogo", required=True, help="JSON de AsientosOA LEFT JOIN ApuntesOA con Observaciones")
    p.add_argument("--cuentas", required=True, help="JSON del plan con SaldoAnterior y SaldoAuditoria")
    p.add_argument("--cuadro", required=True, help="JSON de CuadroFinanciacion, para saber si hay estado")
    p.add_argument("--cliente", required=True)
    p.add_argument("--ejercicio", default="")
    p.add_argument("--salida", required=True)
    p.add_argument("--nombres-en-claro", action="store_true",
                   help="solo si el auditor ha apagado la tokenizacion: configurar dice «forzado por el auditor»")
    a = p.parse_args()

    catalogo = leer_json(a.catalogo)
    cuentas = leer_json(a.cuentas)
    if not exigir_tokens(cuentas, a.nombres_en_claro):
        return 2
    cuadro = leer_json(a.cuadro)

    if not cuadro:
        print("❌ el expediente no tiene estado de flujos: no hay nada que ajustar. En los "
              "modelos de pymes es lo correcto.")
        return 2
    if not catalogo:
        print("❌ el expediente no tiene ninguna plantilla de ajuste en su catálogo.")
        return 2
    if not cuentas or "SaldoAnterior" not in cuentas[0]:
        print("❌ el plan exportado no trae SaldoAnterior: sin la apertura no se puede sacar "
              "el importe de casi ninguna regla.")
        return 2

    grupos = agrupar(catalogo)
    s = Saldos(cuentas)
    props = proponer(grupos, s)
    propuesto = {p["numero"]: total_propuesto(p) for p in props}
    con_regla = set(propuesto)

    wb = Workbook()
    wb.remove(wb.active)
    descuadres, ya_puestos = _hoja_propuestas(wb, props, a.cliente, a.ejercicio)
    _hoja_catalogo(wb, grupos, propuesto, a.cliente, a.ejercicio)

    comprobaciones = []
    comprobaciones.append((
        "Cada propuesta cuadra: sus cobros suman lo mismo que sus pagos",
        not descuadres,
        f"cuadran las {len(props)} propuestas" if not descuadres
        else f"{len(descuadres)} descuadran: "
             + "; ".join(f"nº {n} {d} ({v:,.2f} €)" for n, d, v in descuadres[:3])))

    distintas = [x for x in ya_puestos if abs(x[4]) > TOLERANCIA]
    if ya_puestos:
        comprobaciones.append((
            "Donde el auditor ya puso el ajuste, la propuesta coincide con lo suyo",
            not distintas,
            f"coinciden las {len(ya_puestos)} que ya estaban puestas" if not distintas
            else f"{len(distintas)} no coinciden: "
                 + "; ".join(f"nº {n} {d}: Gesia {g:,.2f} y la propuesta {pr:,.2f}"
                             for n, d, g, pr, _ in distintas[:3])
                 + ". Manda lo del auditor; la diferencia hay que entenderla antes de tocar nada"))

    sin_regla = len(grupos) - len(con_regla)
    comprobaciones.append((
        "Hay regla verificada para las plantillas que se proponen", None,
        f"{len(con_regla)} de las {len(grupos)} del catálogo llevan propuesta. Las otras "
        f"{sin_regla} salen en la hoja Catalogo con su criterio, para que las rellene el "
        "auditor: no se proponen porque no hay contra qué contrastar la regla, y una regla sin "
        "verificar que acierte por casualidad es peor que no tener regla"))

    # LA QUE MAS IMPORTA cuando el expediente no tiene el estado hecho, que es justo cuando
    # esta propuesta se lanza sola. Medido contra el unico expediente terminado: de los 10
    # ajustes que aprobo el auditor, estas reglas aciertan 4 y cubren el 32 % del importe
    # movido. Los seis que faltan son los grandes -solo la amortizacion de creditos movia mas
    # del doble que todo lo propuesto junto-. Sin decirlo, el descuadre de un borrador parece
    # un error del cliente en vez de un trabajo a medias.
    comprobaciones.append((
        "Esto es un estado de flujos terminado", False,
        "Es un BORRADOR, no un estado de flujos. Estas reglas, medidas contra el único expediente que tiene "
        "el estado hecho, acertaron 4 de los 10 ajustes que aprobó el auditor y cubrían el "
        "32 % del importe movido. Lo que falta son los grandes: impuesto de sociedades, ventas "
        "de inmovilizado, provisiones, reclasificaciones y amortización de deuda. Con esto el "
        "estado NO va a cuadrar, y no cuadra porque está a medias, no porque haya un error en "
        "las cuentas del cliente. Dilo así al entregar, antes que ninguna cifra"))

    comprobaciones.append((
        "Esto no está en Gesia", None,
        "es una propuesta en papel. Cuando se teclee, va como ajuste NO APROBADO y con "
        "«Asistente IA:» al principio de la descripción, para que no se confunda nunca con el "
        "trabajo del auditor"))

    _hoja_comprobaciones(wb, comprobaciones, a.cliente, a.ejercicio)

    destino = os.path.abspath(a.salida)
    os.makedirs(os.path.dirname(destino), exist_ok=True)
    wb.save(destino)
    print(f"✔ propuesta escrita: {destino}")
    print(f"  hojas: {', '.join(wb.sheetnames)}")
    print(f"  plantillas en el catálogo del expediente: {len(grupos)}")
    print(f"  propuestas: {len(props)}"
          + (f", de las que {len(ya_puestos)} ya están puestas y aprobadas" if ya_puestos else ""))
    for p in props:
        total = redondear(sum(c for _, _, c, _ in p["lineas"]))
        print(f"    nº {p['numero']:>3} {p['desc'][:38]:38} {total:>14,.2f}")
    malas = [t for t, ok, _ in comprobaciones if ok is False]
    avisos = [t for t, ok, _ in comprobaciones if ok is None]
    if malas or avisos:
        print("\nPARA CONTAR AL ENTREGAR (tal cual, sin resumir):")
        for t, ok, d in comprobaciones:
            # el titulo es la AFIRMACION que se comprueba; si no se cumple, no se repite en
            # afirmativo pegada a su negacion (ver generar_efe.py, 25/09/2026)
            if ok is False:
                print(f"  - NO CUADRA: {d}")
            elif ok is None:
                print(f"  - A TENER EN CUENTA: {d}")
        return 1
    print("  todas las comprobaciones cuadran")
    return 0


if __name__ == "__main__":
    sys.exit(main())
