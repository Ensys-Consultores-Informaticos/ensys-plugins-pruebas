# -*- coding: utf-8 -*-
"""Propone importes para los ajustes del estado de flujos, desde el catalogo del expediente.

    python proponer_efe.py --catalogo catalogo.json --cuentas cuentas.json
        --cuadro cuadro.json --cliente "..." --ejercicio 2025 --generado 19/10/2026
        --salida "<expediente>/AsistenteIA/EstadosFinancieros/Propuesta EFE <CLIENTE> <EJERCICIO>.xlsx"

La primera hoja es «Uso de IA» (lib_uso_ia): la evidencia del uso de IA, que dice que los
importes propuestos los ha calculado la herramienta, con lo del equipo en blanco. Nada lee el
reloj: la fecha de generacion llega con --generado (regla 4).

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
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# Los modulos de la carpeta se encuentran aunque se ejecute con `python -I`, que no pone la
# carpeta del script en sys.path (prueba en Cowork, 20/10/2026).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib_eeff import (  # noqa: E402
    BORRADOR,
    INCOMPLETO,
    exigir_tokens,
    TOLERANCIA,
    a_float,
    es_si,
    etiqueta,
    frase_terceros,
    frases_comprobacion,
    leer_json,
    lineas_entrega,
    redondear,
    salida_utf8,
    texto,
)
from lib_uso_ia import hoja_uso_ia, marcar_papel  # noqa: E402

# La fecha de generacion, la que pasa el modelo con --generado. Se fija en main().
GENERADO = ""

# Lo que el equipo podria contrastar. Describe, no dictamina: el alcance es suyo.
PROPUESTA = (
    "Contrastar cada importe propuesto con los movimientos de las cuentas de las que sale "
    "(columna «De dónde sale» de la hoja Propuestas) y con la documentación del expediente. "
    "Revisar que cada ajuste propuesto se sostiene en esos movimientos antes de teclearlo en "
    "Gesia, y completar las plantillas sin propuesta según el criterio que trae cada una (hoja "
    "Catalogo)."
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
# La funcion devuelve {par: (cobro, pago)} y una linea de texto diciendo de donde sale. Si no
# da importe devuelve None y, en el texto, EL MOTIVO: hasta la tanda 3 devolvia None y una
# cadena vacia, y proponer() descartaba la plantilla en silencio. En un expediente real
# quedaron sin importe la distribucion del resultado y los gastos financieros, con regla
# verificada, y la hoja Comprobaciones las conto entre las que no tienen regla (registro del
# 21/10/2026).


def _sin_saldo(s: Saldos, cuenta: str) -> str:
    """Por que una cuenta no da importe. No estar en el plan no es lo mismo que estar a cero."""
    if not s.existe(cuenta):
        return f"la {cuenta} no está en el plan del expediente"
    return f"la {cuenta} no tiene saldo en el ejercicio (0,00)"


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
        return None, ("ninguna dotación a la amortización da importe: "
                      + "; ".join(_sin_saldo(s, d) for _, d in tramos))
    return imp, "dotación del ejercicio, cada tramo con su amortización acumulada: " + "; ".join(fuentes)


def _r_gastos_financieros(apuntes: list, s: Saldos):
    v = s.importe("66")
    if not v:
        return None, _sin_saldo(s, "66")
    return {("C66", "G66"): (v, 0.0), ("G66", "C66"): (0.0, v)}, f"saldo de la 66 del ejercicio = {v:,.2f}"


def _r_ingresos_financieros(apuntes: list, s: Saldos):
    v = s.importe("76")
    if not v:
        return None, _sin_saldo(s, "76")
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
    if apertura is None:
        return None, ("la 129 no está en el plan del expediente: sin su apertura no se sabe qué "
                      "resultado se distribuye")
    if abs(apertura) < TOLERANCIA:
        return None, ("la apertura de la 129 es cero: no hay resultado del ejercicio anterior que "
                      "distribuir")
    if beneficio != (apertura < 0):
        if beneficio:
            return None, (f"la apertura de la 129 es deudora ({apertura:,.2f}): el ejercicio "
                          "anterior cerró con pérdida, y la distribución de pérdidas no se propone "
                          "porque no está contrastada contra ningún expediente")
        return None, (f"la apertura de la 129 es acreedora ({apertura:,.2f}): el ejercicio "
                      "anterior cerró con beneficio, no con pérdida")
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


def _orden_plantillas(grupos: dict) -> list:
    return sorted(grupos.items(), key=lambda kv: int(kv[0]) if kv[0].isdigit() else 0)


def _pares(pares) -> str:
    return ", ".join(f"{a} → {b}" for a, b in sorted(pares))


def proponer(grupos: dict, s: Saldos) -> list:
    """[{numero, desc, regla, fuente, lineas: [(par, concepto, cobro, pago)], puesto}]"""
    return evaluar(grupos, s)[0]


def evaluar(grupos: dict, s: Saldos) -> tuple:
    """(propuestas, no_aplicadas, reglas).

    no_aplicadas es {numero: (regla, motivo)}: las plantillas que tienen regla verificada y no
    llevan propuesta, con el motivo concreto. reglas es [(regla, aplicada, frase)], una por cada
    una de las cuatro, con una frase que se entiende leida sola: a que plantilla se aplico, o
    por que no. Las dos cosas faltaban, y una regla que no se aplica sin decirlo se confunde con
    una plantilla sin regla (registro del 21/10/2026).
    """
    salida, no_aplicadas = [], {}
    for n, a in _orden_plantillas(grupos):
        nombre, fn = regla_de(a)
        if not fn:
            continue
        imp, fuente = fn(a["apuntes"], s)
        if not imp:
            no_aplicadas[n] = (nombre, fuente)
            continue
        lineas = []
        for p in a["apuntes"]:
            cobro, pago = imp.get(_par(p), (0.0, 0.0))
            lineas.append((_par(p), texto(p.get("Concepto")), cobro, pago))
        puesto = redondear(sum(a_float(p.get("Origen")) for p in a["apuntes"]))
        salida.append({"numero": n, "desc": a["desc"], "regla": nombre, "fuente": fuente,
                       "criterio": a["criterio"], "lineas": lineas,
                       "aprobado": a["aprobado"], "puesto": puesto})

    reglas = []
    for nombre, firma, _ in REGLAS:
        hechas = [p for p in salida if p["regla"] == nombre]
        sin = [(n, m) for n, (r, m) in no_aplicadas.items() if r == nombre]
        partes = [f"aplicada a la nº {p['numero']} ({total_propuesto(p):,.2f} €)" for p in hechas]
        partes += [f"NO aplicada a la nº {n}, porque {m}" for n, m in sin]
        if partes:
            reglas.append((nombre, bool(hechas), f"regla «{nombre}»: " + "; ".join(partes)))
            continue
        # NINGUNA plantilla tiene su forma. Si hay una parecida -comparte algun apunte con la
        # firma y no tiene ya otra regla- se nombra con lo que le falta: es la que el auditor
        # habra tocado o la que viene de otro master, y el motivo va tambien a su fila del
        # Catalogo. La parecida NO se propone: la forma es lo que hace fiable la regla.
        frase = (f"regla «{nombre}»: NO aplicada, porque ninguna plantilla del catálogo tiene su "
                 f"forma (los apuntes {_pares(firma)})")
        parecidas = [(len(firma & {_par(x) for x in a["apuntes"]}), n) for n, a in _orden_plantillas(grupos)
                     if n not in no_aplicadas and not regla_de(a)[1]]
        parecidas = [x for x in parecidas if x[0]]
        if parecidas:
            n = max(parecidas, key=lambda x: x[0])[1]
            falta = firma - {_par(x) for x in grupos[n]["apuntes"]}
            motivo = (f"no tiene la forma de la regla: le falta{'n' if len(falta) > 1 else ''} "
                      f"{'los apuntes' if len(falta) > 1 else 'el apunte'} {_pares(falta)}")
            no_aplicadas[n] = (nombre, motivo)
            frase += f"; la más parecida es la nº {n}, que {motivo}"
        reglas.append((nombre, False, frase))
    return salida, no_aplicadas, reglas


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
    ws["A3"] = ("Preparado por Asistente IA" + (" el " + GENERADO if GENERADO else "")
                + ". PROPUESTA: no está en Gesia, no está aprobada, y quien decide es el auditor.")
    ws["A3"].font = Font(name=FONT, size=9, color="808080")
    # en todas las hojas, no solo en la primera: una hoja impresa suelta tambien la lleva
    marcar_papel(ws, "A4", "B4")
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
                value="Ninguna regla verificada ha dado importe a una plantilla del catálogo. "
                      "Mira la hoja Catalogo: están todas, con su criterio, y en «Regla y motivo» "
                      "por qué no se ha aplicado cada regla.").font = NORMAL
    return descuadres, ya_puestos


def total_propuesto(p: dict) -> float:
    """Lo que suma la propuesta de una plantilla.

    Redondeando apunte a apunte, igual que la hoja Propuestas, para que las dos hojas
    digan el mismo numero y no se separen por un centimo."""
    t = 0.0
    for _, _, cobro, _ in p["lineas"]:
        t = redondear(t + cobro)
    return t


SIN_REGLA = "sin regla verificada: la rellena el auditor con el criterio de la plantilla"


def motivo_catalogo(n: str, plantilla: dict, propuesto: dict, no_aplicadas: dict) -> str:
    """La columna «Regla y motivo» del Catalogo: con que regla se propone, o por que no.

    Separa las tres cosas que la columna «¿Propuesta?» mezclaba con un «—» (registro del
    21/10/2026): propuesta, con regla verificada y NO aplicada -con el motivo-, y sin regla."""
    if n in propuesto:
        return f"«{regla_de(plantilla)[0]}»: aplicada"
    if n in no_aplicadas:
        regla, motivo = no_aplicadas[n]
        return f"«{regla}»: NO aplicada, porque {motivo}"
    return SIN_REGLA


def _hoja_catalogo(wb: Workbook, grupos: dict, propuesto: dict, cliente: str, ejercicio: str,
                   no_aplicadas: dict | None = None) -> None:
    no_aplicadas = no_aplicadas or {}
    ws = wb.create_sheet("Catalogo")
    fila = _titulo(ws, cliente, ejercicio,
                   "TODAS las plantillas de ajuste que tiene este expediente, con el criterio "
                   "que trae cada una. Las que no llevan propuesta las rellena el auditor, y "
                   "«Regla y motivo» dice si tienen regla verificada y por qué no se aplicó. "
                   "Son DOS importes distintos: «ya aprobado en Gesia» es lo que está registrado "
                   "hoy en el expediente —0,00 mientras no se apruebe nada—, y «propuesto» es lo "
                   "que propone este papel, desglosado en la hoja Propuestas.")
    _cabecera(ws, fila,
              ["Nº", "Descripción", "Aprobado", "Apuntes", "Importe ya aprobado en Gesia",
               "Importe propuesto", "¿Propuesta?", "Regla y motivo", "Criterio de la plantilla"],
              [6, 44, 11, 9, 20, 17, 13, 60, 96])
    fila += 1
    for n, a in _orden_plantillas(grupos):
        puesto = redondear(sum(a_float(p.get("Origen")) for p in a["apuntes"]))
        usada = a["aprobado"] or abs(puesto) > TOLERANCIA
        fuente = NORMAL if usada or n in propuesto or n in no_aplicadas else APAGADO
        ws.cell(row=fila, column=1, value=n).font = fuente
        ws.cell(row=fila, column=2, value=a["desc"]).font = fuente
        ws.cell(row=fila, column=3, value="SÍ" if a["aprobado"] else "no").font = fuente
        ws.cell(row=fila, column=4, value=len(a["apuntes"])).font = fuente
        _importe(ws, fila, 5, puesto, fuente)
        # En blanco, no 0,00, cuando no hay propuesta: un cero en esta columna es justo la
        # lectura que hizo perder el tiempo al auditor el 26/09/2026.
        if n in propuesto:
            _importe(ws, fila, 6, propuesto[n], fuente)
        ws.cell(row=fila, column=7,
                value="sí" if n in propuesto else ("no" if n in no_aplicadas else "—")).font = fuente
        m = ws.cell(row=fila, column=8, value=motivo_catalogo(n, a, propuesto, no_aplicadas))
        m.font = fuente
        m.alignment = Alignment(wrap_text=True, vertical="top")
        c = ws.cell(row=fila, column=9, value=a["criterio"])
        c.font = fuente
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if n in propuesto:
            ws.cell(row=fila, column=7).fill = TOTAL_FILL
        elif n in no_aplicadas:
            # tiene regla y no se aplico: es lo primero que el auditor tiene que mirar
            for j in (7, 8):
                ws.cell(row=fila, column=j).fill = AMARILLO
        elif not usada:
            for j in range(1, 10):
                ws.cell(row=fila, column=j).fill = GRIS
        fila += 1


def _hoja_comprobaciones(wb: Workbook, comprobaciones: list, cliente: str, ejercicio: str) -> None:
    ws = wb.create_sheet("Comprobaciones")
    fila = _titulo(ws, cliente, ejercicio, "Los cuadres de la propuesta.")
    todo = all(ok is not False for _, ok, _ in comprobaciones)
    borrador = any(ok in INCOMPLETO for _, ok, _ in comprobaciones)
    # La propuesta es un borrador SIEMPRE: si sus cuadres salen bien, la cabecera lo dice en
    # ambar, no en verde, y no lo llama descuadre, que es como se leyo el 20/10/2026.
    c = ws.cell(row=fila, column=1,
                value=("HAY DESCUADRES: no llevar esto a Gesia sin leerlos" if not todo else
                       "LA PROPUESTA CUADRA, PERO ES UN BORRADOR: no es un estado de flujos "
                       "terminado" if borrador else "TODO CUADRA"))
    c.font = ROJO if not todo else (AMBAR if borrador else VERDE)
    fila += 2
    _cabecera(ws, fila, ["Comprobación", "Resultado", "Detalle"], [62, 18, 68])
    fila += 1
    for t, ok, detalle in comprobaciones:
        ws.cell(row=fila, column=1, value=t).font = NORMAL
        r = ws.cell(row=fila, column=2, value=etiqueta(ok))
        r.font = VERDE if ok is True else (ROJO if ok is False else AMBAR)
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
    p.add_argument("--generado", required=True,
                   help="fecha de generacion, dd/mm/aaaa: nada aqui lee el reloj")
    p.add_argument("--nombres-en-claro", action="store_true",
                   help="solo si el auditor ha apagado la seudonimizacion: configurar dice «forzado por el auditor»")
    a = p.parse_args()
    global GENERADO
    GENERADO = a.generado

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
    props, no_aplicadas, reglas = evaluar(grupos, s)
    propuesto = {p["numero"]: total_propuesto(p) for p in props}

    wb = Workbook()
    wb.remove(wb.active)
    descuadres, ya_puestos = _hoja_propuestas(wb, props, a.cliente, a.ejercicio)
    _hoja_catalogo(wb, grupos, propuesto, a.cliente, a.ejercicio, no_aplicadas)

    # Cada detalle lleva su sujeto: en «PARA CONTAR AL ENTREGAR» sale sin el titulo, y
    # «2 no coinciden» leido solo no dice que (registro del 21/10/2026).
    comprobaciones = []
    comprobaciones.append((
        "Cada propuesta cuadra: sus cobros suman lo mismo que sus pagos",
        not descuadres,
        f"cuadran las {len(props)} propuestas" if not descuadres
        else f"{len(descuadres)} propuestas de ajuste del estado de flujos descuadran, sus cobros "
             "no suman lo mismo que sus pagos: "
             + "; ".join(f"nº {n} {d} ({v:,.2f} €)" for n, d, v in descuadres[:3])))

    distintas = [x for x in ya_puestos if abs(x[4]) > TOLERANCIA]
    if ya_puestos:
        comprobaciones.append((
            "Donde el auditor ya puso el ajuste, la propuesta coincide con lo suyo",
            not distintas,
            f"coinciden las {len(ya_puestos)} que ya estaban puestas" if not distintas
            else f"{len(distintas)} propuestas no coinciden con el ajuste que el auditor ya "
                 "aprobó en Gesia: "
                 + "; ".join(f"nº {n} {d}: Gesia {g:,.2f} y la propuesta {pr:,.2f}"
                             for n, d, g, pr, _ in distintas[:3])
                 + ". Manda lo del auditor; la diferencia hay que entenderla antes de tocar nada"))
    # hasta aqui, los CUADRES de la propuesta: lo que el script comprueba. Lo que sigue son
    # avisos sobre lo que es el papel, y en el bloque de uso de IA van en el resultado
    cuadres = list(comprobaciones)

    # LAS REGLAS QUE NO SE APLICARON, aparte de las plantillas sin regla. Hasta la tanda 3
    # iban juntas en «las N que no se proponen porque no hay contra que contrastar», y en
    # un expediente real dos de ellas SI tenian regla verificada (registro del 21/10/2026).
    fallidas = [frase for _, aplicada, frase in reglas if not aplicada]
    comprobaciones.append((
        f"Las {len(REGLAS)} reglas verificadas se han aplicado", True if not fallidas else None,
        f"las {len(REGLAS)} llevan propuesta: " + "; ".join(f for _, _, f in reglas)
        if not fallidas else
        f"{len(fallidas)} de las {len(REGLAS)} reglas verificadas de la propuesta de ajustes del "
        "estado de flujos no se han aplicado: " + "; ".join(fallidas)
        + ". Esas plantillas las rellena el auditor; el motivo está en la hoja Catalogo"))

    sin_regla = len(grupos) - len(propuesto) - len(no_aplicadas)
    comprobaciones.append((
        "Todas las plantillas del catálogo tienen regla verificada", True if not sin_regla else None,
        f"de las {len(grupos)} plantillas de ajuste del catálogo del estado de flujos, "
        f"{len(propuesto)} llevan propuesta"
        + ((f", {len(no_aplicadas)} tiene" if len(no_aplicadas) == 1 else f", {len(no_aplicadas)} tienen")
           + " regla verificada y no se ha aplicado (el motivo está en la hoja Catalogo)" if no_aplicadas else "")
        + (" y ninguna se queda sin regla" if not sin_regla else
           (f" y {sin_regla} no tiene regla: sale en la hoja Catalogo con su criterio, para que la "
            if sin_regla == 1 else
            f" y {sin_regla} no tienen regla: salen en la hoja Catalogo con su criterio, para que las ")
           + "rellene el auditor. No se proponen porque no hay contra qué contrastar una regla, y "
           "una regla sin verificar que acierte por casualidad es peor que no tener regla")))

    # LA QUE MAS IMPORTA cuando el expediente no tiene el estado hecho, que es justo cuando
    # esta propuesta se lanza sola. Medido contra el unico expediente terminado: de los 10
    # ajustes que aprobo el auditor, estas reglas aciertan 4 y cubren el 32 % del importe
    # movido. Los seis que faltan son los grandes -solo la amortizacion de creditos movia mas
    # del doble que todo lo propuesto junto-. Sin decirlo, el descuadre de un borrador parece
    # un error del cliente en vez de un trabajo a medias. Por eso va como BORRADOR y no como
    # NO CUADRA, que queda para los fallos aritmeticos (20/10/2026).
    comprobaciones.append((
        "Esto es un estado de flujos terminado", BORRADOR,
        "la propuesta de ajustes del estado de flujos es un BORRADOR, no un estado de flujos "
        "terminado. Estas reglas, medidas contra el único expediente que tiene el estado hecho, acertaron 4 de los 10 ajustes que aprobó el auditor y cubrían el "
        "32 % del importe movido. Lo que falta son los grandes: impuesto de sociedades, ventas "
        "de inmovilizado, provisiones, reclasificaciones y amortización de deuda. Con esto el "
        "estado NO va a cuadrar, y no cuadra porque está a medias, no porque haya un error en "
        "las cuentas del cliente. Dilo así al entregar, antes que ninguna cifra"))

    comprobaciones.append((
        "Esto no está en Gesia", None,
        "la propuesta de ajustes del estado de flujos no está en Gesia: es una propuesta en "
        "papel. Cuando se teclee, va como ajuste NO APROBADO y con "
        "«Asistente IA:» al principio de la descripción, para que no se confunda nunca con el "
        "trabajo del auditor"))

    _hoja_comprobaciones(wb, comprobaciones, a.cliente, a.ejercicio)
    _uso_ia(wb, a, cuentas, cuadres, props, len(grupos), no_aplicadas)

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
    # Las cuatro reglas, una linea cada una, aplicada o con el motivo: es lo que el modelo
    # cuenta al entregar, y sin esto solo veia las que salian (registro del 21/10/2026).
    print(f"  reglas verificadas ({len(REGLAS)}; cuéntalas todas al entregar, tal cual):")
    for _, _, frase in reglas:
        print(f"    - {frase}")
    entrega = lineas_entrega(comprobaciones)
    if entrega:
        # el titulo es la AFIRMACION que se comprueba; si no se cumple, no se repite en
        # afirmativo pegada a su negacion (ver lineas_entrega en lib_eeff, 25/09/2026)
        print("\nPARA CONTAR AL ENTREGAR (tal cual, sin resumir):")
        for linea in entrega:
            print(f"  - {linea}")
        return 1
    print("  todas las comprobaciones cuadran")
    return 0


def _uso_ia(wb: Workbook, a, cuentas: list, cuadres: list, props: list, plantillas: int,
            no_aplicadas: dict | None = None) -> None:
    """La hoja de evidencia del uso de IA, la primera del libro (lib_uso_ia).

    Este es el papel en que la herramienta CALCULA cifras, y el resultado lo dice con nombre y
    numero: que importes ha propuesto, con que reglas, y que es un borrador. Las comprobaciones
    son los cuadres de la hoja Comprobaciones -no sus avisos, que no son comprobaciones y van al
    resultado- mas la de los nombres de terceros.
    """
    hojas_papel = list(wb.sheetnames)      # antes de añadir la de uso de IA
    reglas = sorted({p["regla"] for p in props})
    propuestas = "; ".join(f"nº {p['numero']} {p['desc']} ({total_propuesto(p):,.2f} €)" for p in props)
    if props:
        calculado = (f"La herramienta ha calculado los importes propuestos para {len(props)} de las "
                     f"{plantillas} plantillas de ajuste del catálogo del expediente ({propuestas}), "
                     "con reglas contrastadas contra un expediente con el estado terminado ("
                     + ", ".join(reglas).lower() + "), y ha escrito el texto de «De dónde sale» de "
                     "cada una y el prefijo «Asistente IA:» de sus descripciones. ")
    else:
        calculado = (f"Ninguna de las {plantillas} plantillas del catálogo encaja con una regla "
                     "contrastada: la herramienta no ha calculado ningún importe. ")
    sin = plantillas - len(props)
    resto = ("" if not sin else
             "La otra plantilla queda sin propuesta, con su criterio, para el auditor. " if sin == 1 else
             f"Las otras {sin} plantillas quedan sin propuesta, con su criterio, para el auditor. ")
    if no_aplicadas:
        # las que tienen regla y no se aplico, con su numero: no son «sin regla» (21/10/2026)
        resto += ("De ellas, " + ("la nº " if len(no_aplicadas) == 1 else "las nº ")
                  + ", ".join(sorted(no_aplicadas, key=lambda n: int(n) if n.isdigit() else 0))
                  + (" tiene" if len(no_aplicadas) == 1 else " tienen")
                  + " regla verificada que no se ha aplicado; el motivo está en la hoja Catalogo. ")
    hoja_uso_ia(
        wb,
        papel=a.cliente + " · Ejercicio " + a.ejercicio + " · Propuesta de ajustes del estado de flujos",
        procedimiento="estados-financieros",
        descripcion=("Propuesta de importes para las plantillas de ajuste del estado de flujos de "
                     "efectivo del expediente, calculados desde los saldos de sus cuentas."),
        alcance=("Ejercicio " + a.ejercicio + ". Las " + str(plantillas) + " plantillas de ajuste del "
                 "catálogo del módulo EFE del expediente y los saldos de su plan de cuentas."),
        resultado=("Este libro: hojas " + ", ".join(hojas_papel) + ". " + calculado + resto
                   + "Es un BORRADOR: no está en Gesia ni aprobado, y con él solo el estado de "
                     "flujos no queda terminado."),
        comprobaciones=[frase_terceros(cuentas, a.nombres_en_claro)] + frases_comprobacion(cuadres),
        propuesta=PROPUESTA,
        generado=a.generado,
    )


if __name__ == "__main__":
    sys.exit(main())
