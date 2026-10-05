"""Comprueba en ejecucion lo que la prueba de continuidad asume. Puede abortar.

No fiarse de la documentacion: lo que se asume, se comprueba. Un papel de trabajo
bonito sobre datos mal entendidos es peor que no tener papel.

    python verificar_contrato.py --diario diario.mdb --cierre cierre.json

Codigos de salida:
  0  todo encaja
  1  avisos: se puede seguir, pero hay que leerlos y contarlos en el papel
  2  no se puede hacer la prueba. No se genera nada.
"""

from __future__ import annotations

import argparse
import sys

from lib_continuidad import (
    DECIMALES,
    GRUPOS_BALANCE,
    aplicar_filtro,
    cargar_diario,
    leer_cierre,
    hay_diario,
    leer_filtro_apertura,
    saldos_apertura,
    salida_utf8,
    tablas,
)

# Tolerancia para dar por cuadrado un asiento. Dos decimales es el redondeo del
# euro fijado en cliente; se deja un margen de un centimo por cuenta agregada, no
# un porcentaje: un descuadre real en un asiento de apertura no es proporcional.
TOLERANCIA = 0.01

COLUMNAS_MINIMAS = ("CUENTA", "DEBE", "HABER")


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("--diario", required=True, help="el .mdb/.smn ya en el contenedor")
    p.add_argument("--cierre", required=True, help="JSON con el cierre auditado")
    p.add_argument("--ejercicio", default="",
                   help="ejercicio auditado; obligatorio si el cierre son filas crudas")
    p.add_argument("--ejercicio-anterior", default="",
                   help="ejercicio del cierre con el que se compara")
    p.add_argument("--cliente", default="", help="razón social, para el papel")
    args = p.parse_args()

    errores: list = []
    avisos: list = []

    # C01 · el diario es legible y trae lo imprescindible
    try:
        tabs = tablas(args.diario)
    except RuntimeError as exc:
        print("C01 ERROR: " + str(exc))
        return 2
    if not hay_diario(args.diario):
        print("C01 ERROR: el fichero no tiene tabla Diario. Tablas: " + str(tabs))
        return 2

    df = cargar_diario(args.diario)
    faltan = [c for c in COLUMNAS_MINIMAS if c not in df.columns]
    if faltan:
        errores.append("C01 · al diario le faltan columnas obligatorias: " + str(faltan))

    # C02 · el filtro de apertura se lee y se entiende
    filtro = leer_filtro_apertura(args.diario)
    if filtro.get("ausente"):
        errores.append(
            "C02 · no se puede identificar el asiento de apertura: "
            + filtro["motivo"]
            + ". El asiento de apertura se fija al normalizar y no tiene que ser "
            "el 1, asi que no se puede suponer."
        )

    if errores:
        for e in errores:
            print(e)
        print("\nNo se puede hacer la prueba.")
        return 2

    print("C02 · filtro de apertura: " + filtro["campo"] + " " + filtro["operador"]
          + " " + repr(filtro["valor"]))

    # C03 · el filtro selecciona algo
    mascara = aplicar_filtro(df, filtro)
    n = int(mascara.sum())
    if n == 0:
        print("C03 ERROR: el filtro de apertura no selecciona ningun apunte.")
        return 2
    asientos = sorted(df.loc[mascara, "ASIENTO"].drop_duplicates().tolist())
    print("C03 · " + str(n) + " apuntes de apertura, asiento(s) " + str(asientos[:5])
          + (" y " + str(len(asientos) - 5) + " mas" if len(asientos) > 5 else ""))

    # C04 · la apertura cuadra
    ap = df[mascara]
    neto = round(float((ap["DEBE"] - ap["HABER"]).sum()), DECIMALES)
    if abs(neto) > TOLERANCIA:
        errores.append(
            "C04 · el asiento de apertura no cuadra: descuadre de "
            + format(neto, ".2f") + " EUR. Con la apertura descuadrada la prueba "
            "no significa nada."
        )
    else:
        print("C04 · la apertura cuadra (" + format(neto, ".2f") + ")")

    # C05 · la apertura no deberia traer cuentas de resultados
    g1 = ap["CUENTA"].str[:1]
    resultados = ap[g1.isin(["6", "7"])]
    if len(resultados):
        avisos.append(
            "C05 · la apertura trae " + str(len(resultados)) + " apuntes de los "
            "grupos 6 y 7, que no deberian tener saldo inicial. Quedan fuera de la "
            "comparacion y se informan aparte: es un error del cliente, no una "
            "diferencia que cuantificar."
        )

    # C06 · si el campo APERTURA viene relleno, tiene que decir lo mismo que el filtro
    if "APERTURA" in df.columns and (df["APERTURA"] != 0).any():
        por_campo = set(df.index[df["APERTURA"] != 0])
        por_filtro = set(df.index[mascara])
        if por_campo != por_filtro:
            avisos.append(
                "C06 · el campo APERTURA y el FiltroDeApertura NO seleccionan lo "
                "mismo (" + str(len(por_campo)) + " frente a " + str(len(por_filtro))
                + " apuntes). Manda el filtro, pero esto suele significar que se "
                "cambio despues de importar: revisalo antes de firmar."
            )
        else:
            print("C06 · el campo APERTURA coincide con el filtro")
    else:
        avisos.append(
            "C06 · el campo APERTURA viene vacio o no existe (es una opcion de "
            "importacion). Se usa el filtro, que es la fuente buena, pero se "
            "pierde la comprobacion cruzada."
        )

    # C07 · el cierre que trajo el modelo tiene la pinta que debe
    try:
        cierre = leer_cierre(args.cierre, args.ejercicio, args.ejercicio_anterior,
                             args.cliente)
    except (RuntimeError, ValueError) as exc:
        print("C07 ERROR: " + str(exc))
        return 2

    ctas = cierre["cuentas"]
    fuera = [c["cuenta"] for c in ctas if c["cuenta"][:1] not in GRUPOS_BALANCE]
    if fuera:
        errores.append(
            "C07 · el cierre trae " + str(len(fuera)) + " cuentas que no son de los "
            "grupos 1 a 5 (" + str(fuera[:5]) + "). La consulta al expediente tiene "
            "que filtrar CodigoTipo = 'B'."
        )
    suma = round(sum(c["saldo"] for c in ctas), DECIMALES)
    if abs(suma) > TOLERANCIA:
        avisos.append(
            "C07 · los saldos del cierre suman " + format(suma, ".2f") + " y deberian "
            "sumar cero: un balance completo cuadra. Puede que la consulta no haya "
            "filtrado MaximoNivel, o que falten cuentas."
        )
    else:
        print("C07 · el cierre trae " + str(len(ctas)) + " cuentas y cuadra a cero")

    # C08 · las cuentas de maximo nivel no se pueden solapar entre si
    codigos = set(c["cuenta"] for c in ctas)
    solapes = [c for c in codigos if any(o != c and o.startswith(c) for o in codigos)]
    if solapes:
        errores.append(
            "C08 · hay " + str(len(solapes)) + " cuentas del cierre que son prefijo "
            "de otra del mismo cierre (" + str(sorted(solapes)[:5]) + "). Eso duplica "
            "saldos y rompe el mapeo por prefijo mas largo."
        )
    else:
        print("C08 · las cuentas del cierre no se solapan")

    # C09 · cuanto de la apertura encuentra destino
    agr = saldos_apertura(df, mascara)
    del agr  # el recuento real lo hace comparar.py; aqui solo interesa que haya algo

    for e in errores:
        print("\n" + e)
    for a in avisos:
        print("\n" + a)

    if errores:
        print("\nNo se puede hacer la prueba.")
        return 2
    if avisos:
        print("\nSe puede seguir, pero hay " + str(len(avisos)) + " aviso(s) que "
              "tienen que constar en el papel.")
        return 1
    print("\nContrato verificado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
