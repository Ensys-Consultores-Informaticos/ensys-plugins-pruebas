"""Comprueba que el emparejamiento hace lo que tiene que hacer, con un
fixture sintetico -- no hace falta Gesia ni ningun .smn real para ejecutar
esto.

    python probar_cancelacion.py

Ocho cuentas de prueba: una por procedimiento, una que combina dos, y tres
de punteo previo (la columna Indice que traen muchos .smn):

  9999901  2.1 -- toda la cuenta suma 0
  9999902  2.2 -- el total coincide con el ultimo apunte cronologico
  9999903  2.3 -- solo pareo directo, con un apunte suelto sin cancelar
  9999904  2.3 + 2.4 secuencial -- una apertura que solo se cancela
           acumulando tres pagos del mismo dia (como paso de verdad en
           una cuenta de clientes del expediente de calibracion), mas un
           pareo directo aparte y un apunte suelto
  9999905  2.4 combinatorio -- tres apuntes de importes distintos que
           solo cancelan si se combinan SIN ser contiguos en el tiempo
           (nunca hay un tramo cronologico continuo que sume 0), mas dos
           apuntes que quedan sin cancelar
  9999906  punteo previo parcial -- un par ya punteado en contabilidad
           (indice 3) que se respeta tal cual, mas un par sin puntear que
           el skill cancela con un indice NUEVO por encima del previo
  9999907  punteo previo descuadrado -- un grupo previo que NO suma 0:
           se respeta (no se toca), se reporta como descuadre, y la
           verificacion estructural sigue cuadrando
  9999908  punteo previo completo -- todo punteado: el skill no añade
           ningun grupo y no toca nada
  9999910  2.0 por numero de factura -- UNA factura de 2.743,70 muerta por
           TRES pagos de 914,48 / 914,48 / 914,74. Ningun criterio de
           importes llega ahi: los pagos no se parecen a la factura ni entre
           si. Son las cifras reales del caso que lo motivo
  9999911  2.0 con el campo SUCIO -- dos apuntes con el mismo numero de
           factura que NO suman cero: el grupo se rechaza. Es la prueba de
           que el numero PROPONE y la suma DECIDE, no al contrario
  9999912  2.0 y el resto conviven -- una factura que cierra por documento y,
           aparte, un par que solo cierra por importe: los dos pasos suman
  9999913  2.2c la APERTURA por deduccion -- tres pagos con numero de factura
           cuya factura NO esta en el ejercicio (o sea, esta en la apertura),
           mas la regularizacion de centimos que cierra el hueco. Ningun
           subconjunto de los pagos da el importe de la apertura, asi que el
           2.2b no puede con esto
  9999914  2.2c que NO cierra -- lo mismo sin la regularizacion: la apertura se
           queda pendiente y no se fuerza nada
  9999915  SIN CONCEPTO -- el auditor decidio que ese texto no saliera de su
           equipo (rama confidencialidad). Todo funciona igual, el papel no
           lleva la columna, y los hallazgos por fecha de documento salen
           como NO EVALUADOS, no como cero: calcularlos con la fecha contable
           daria una cifra inflada con aspecto de hallazgo
  9999916  DERIVADAS -- el extracto como lo exporta el MCP 1.11.0: sin CONCEPTO,
           con NumeroEnConcepto y FechaEnConcepto. El numero hace de FACTURA
           (con menor prioridad que una columna del diario), la fecha hace de
           FECHA_DOC, los hallazgos por fecha SI se evaluan, y el papel lleva
           FECHA DOC. y FACTURA, dice de donde salen, y el TOTAL cae bajo SALDO
  9999917  DOS CANDIDATAS -- el diario trae NN_Factura y NN_Documento (prueba en
           frio del 10/09/2026). No decide el orden del SELECT: se puntua cada una
           por grupos que suman cero y gana la que mas cierra; la comparacion consta.
           Y ORIGEN dice el paso: documento / apertura / importe / acumulacion.
           Y los pagos anteriores a una factura SIN fecha de documento van a su
           propia fila, no a «con la fecha del documento».

Por que hace falta: en una cuenta sin nada que cancelar, un emparejador
roto y uno correcto pueden dar el mismo resultado (todo en INDICE 0). Que
una cuenta salga limpia no demuestra que esto funcione; hace falta un
caso con respuesta conocida.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_cancelacion import (
    PASO_ACUMULACION,
    PASO_APERTURA,
    PASO_DOCUMENTO,
    PASO_IMPORTE,
    PASO_TOTAL,
    PASOS_ORIGEN,  # noqa: E402
    ORIGEN_AUDITORIA,
    ORIGEN_CONTABLE,
    asignar_indices_cuenta,
    verificar_cuenta,
    analizar_hallazgos,
    cargar_extracto,
    procesar_extracto,
)


def _df(filas, con_punteo=False, con_factura=False):
    cols = ["FECHA", "CUENTA", "NOMBRE", "CONCEPTO", "SALDO"]
    if con_punteo:
        cols.append("INDICE_PREVIO")
    if con_factura:
        cols.append("FACTURA")
    d = pd.DataFrame(filas, columns=cols)
    d["FECHA"] = pd.to_datetime(d["FECHA"])
    d["SALDO"] = d["SALDO"].astype(float)
    return d


FIXTURES = {
    "9999901": _df([
        ("2024-01-05", "9999901", "Cliente Uno", "Fra 1", 100.00),
        ("2024-02-10", "9999901", "Cliente Uno", "Pago 1", -60.00),
        ("2024-03-01", "9999901", "Cliente Uno", "Pago 2", -40.00),
    ]),
    "9999902": _df([
        ("2024-01-01", "9999902", "Cliente Dos", "Apertura", 500.00),
        ("2024-01-10", "9999902", "Cliente Dos", "Pago apertura", -500.00),
        ("2024-06-01", "9999902", "Cliente Dos", "Fra pendiente", 200.00),
    ]),
    "9999903": _df([
        ("2024-01-01", "9999903", "Cliente Tres", "Fra A", 300.00),
        ("2024-01-05", "9999903", "Cliente Tres", "Pago A", -300.00),
        ("2024-01-10", "9999903", "Cliente Tres", "Fra Suelta", 90.00),
        ("2024-02-01", "9999903", "Cliente Tres", "Fra B", 150.00),
        ("2024-02-05", "9999903", "Cliente Tres", "Pago B", -150.00),
    ]),
    "9999904": _df([
        ("2024-01-01", "9999904", "Cliente Cuatro", "Apertura", 1000.00),
        ("2024-01-15", "9999904", "Cliente Cuatro", "Pago 1", -400.00),
        ("2024-01-15", "9999904", "Cliente Cuatro", "Pago 2", -350.00),
        ("2024-01-15", "9999904", "Cliente Cuatro", "Pago 3", -250.00),
        ("2024-03-01", "9999904", "Cliente Cuatro", "Fra Suelta", 75.00),
        ("2024-04-01", "9999904", "Cliente Cuatro", "Fra D", 200.00),
        ("2024-04-10", "9999904", "Cliente Cuatro", "Pago D", -200.00),
    ]),
    "9999905": _df([
        ("2024-01-01", "9999905", "Cliente Cinco", "M1", 200.00),
        ("2024-01-05", "9999905", "Cliente Cinco", "N1 (ruido)", 90.00),
        ("2024-01-10", "9999905", "Cliente Cinco", "M2", 150.00),
        ("2024-01-15", "9999905", "Cliente Cinco", "N2 (ruido)", -60.00),
        ("2024-01-20", "9999905", "Cliente Cinco", "M3", -350.00),
        ("2024-01-25", "9999905", "Cliente Cinco", "Pendiente", 500.00),
    ]),
    # Punteo previo parcial: el par punteado lleva el indice 3 (numeracion
    # del cliente, con huecos: no hay 1 ni 2). El skill tiene que numerar
    # sus grupos nuevos a partir del 4.
    "9999906": _df([
        ("2024-01-05", "9999906", "Cliente Seis", "Fra punteada", 300.00, 3),
        ("2024-01-20", "9999906", "Cliente Seis", "Pago punteado", -300.00, 3),
        ("2024-02-01", "9999906", "Cliente Seis", "Fra nueva", 120.00, 0),
        ("2024-02-15", "9999906", "Cliente Seis", "Pago nuevo", -120.00, 0),
        ("2024-03-01", "9999906", "Cliente Seis", "Fra pendiente", 80.00, 0),
    ], con_punteo=True),
    # Punteo previo descuadrado: el grupo 1 suma +50 (mal punteado en la
    # contabilidad). Se respeta, se reporta, y la conciliacion estructural
    # descuenta ese descuadre.
    "9999907": _df([
        ("2024-01-05", "9999907", "Cliente Siete", "Fra mal punteada", 400.00, 1),
        ("2024-01-20", "9999907", "Cliente Siete", "Pago mal punteado", -350.00, 1),
        ("2024-02-01", "9999907", "Cliente Siete", "Fra C", 90.00, 0),
        ("2024-02-15", "9999907", "Cliente Siete", "Pago C", -90.00, 0),
    ], con_punteo=True),
    # Punteo previo completo: nada que hacer.
    "9999908": _df([
        ("2024-01-05", "9999908", "Cliente Ocho", "Fra 1", 250.00, 1),
        ("2024-01-20", "9999908", "Cliente Ocho", "Cobro 1", -250.00, 1),
        ("2024-02-01", "9999908", "Cliente Ocho", "Fra 2", 130.00, 2),
        ("2024-02-15", "9999908", "Cliente Ocho", "Cobro 2", -130.00, 2),
    ], con_punteo=True),
    # Apertura que NO se puede cancelar: ningun subconjunto de los pagos da
    # exactamente su importe. Tiene que quedarse pendiente, no forzarse.
    # 2.0: el caso que motivo el paso, con las cifras reales de un expediente.
    # Una compra y tres pagos a 30/60/90 dias que solo se atan por el numero de
    # documento. Sin el, el pareo directo no ve nada y la combinatoria tendria
    # que dar con un subconjunto de tres entre los sueltos de toda la cuenta.
    "9999910": _df([
        ("2024-01-10", "9999910", "Proveedor Diez", "Compra", -2743.70, "12"),
        ("2024-02-10", "9999910", "Proveedor Diez", "Pago 1/3", 914.48, "12"),
        ("2024-03-11", "9999910", "Proveedor Diez", "Pago 2/3", 914.48, "12"),
        ("2024-04-10", "9999910", "Proveedor Diez", "Pago 3/3", 914.74, "12"),
        ("2024-05-10", "9999910", "Proveedor Diez", "Fra viva", -500.00, "13"),
    ], con_factura=True),
    # 2.0 con el campo sucio: mismo numero, no suman cero. Se rechaza el grupo.
    # El 77 tampoco cierra por importes, asi que los dos tienen que quedar
    # pendientes: es la garantia de que el numero no manda.
    "9999911": _df([
        ("2024-01-10", "9999911", "Proveedor Once", "Fra A", -1000.00, "77"),
        ("2024-02-10", "9999911", "Proveedor Once", "Pago parcial", 300.00, "77"),
    ], con_factura=True),
    # 2.0 y los pasos de importes conviven: la 88 cierra por documento (tres
    # apuntes) y el par de la 99/sin numero solo cierra por importe.
    "9999912": _df([
        ("2024-01-10", "9999912", "Proveedor Doce", "Fra 88", -600.00, "88"),
        ("2024-02-10", "9999912", "Proveedor Doce", "Pago 88 a", 250.00, "88"),
        ("2024-03-10", "9999912", "Proveedor Doce", "Pago 88 b", 350.00, "88"),
        ("2024-04-10", "9999912", "Proveedor Doce", "Fra 99", -400.00, "99"),
        ("2024-05-10", "9999912", "Proveedor Doce", "Pago sin numero", 400.00, ""),
    ], con_factura=True),
    # 2.2c: la apertura contra pagos de facturas que no estan en el ejercicio.
    # Las facturas 900/901/902 solo aparecen como PAGO: sus facturas son del año
    # anterior y viven dentro de la apertura. 2000+1500+1600 = 5100 contra una
    # apertura de 5000, y el hueco de 100 lo cierra la regularizacion. Ningun
    # subconjunto de los pagos suma 5000, asi que el 2.2b no llega.
    "9999913": _df([
        ("2024-01-01", "9999913", "Proveedor Trece", "Apertura", -5000.00, ""),
        ("2024-02-10", "9999913", "Proveedor Trece", "Pago fra 2023", 2000.00, "900"),
        ("2024-03-10", "9999913", "Proveedor Trece", "Pago fra 2023", 1500.00, "901"),
        ("2024-04-10", "9999913", "Proveedor Trece", "Pago fra 2023", 1600.00, "902"),
        ("2024-12-31", "9999913", "Proveedor Trece", "Regularizacion", -100.00, ""),
        ("2024-06-01", "9999913", "Proveedor Trece", "Fra del año, viva", -800.00, "10"),
    ], con_factura=True),
    # y sin la regularizacion no cierra: la apertura se queda pendiente.
    "9999914": _df([
        ("2024-01-01", "9999914", "Proveedor Catorce", "Apertura", -5000.00, ""),
        ("2024-02-10", "9999914", "Proveedor Catorce", "Pago fra 2023", 2000.00, "900"),
        ("2024-03-10", "9999914", "Proveedor Catorce", "Pago fra 2023", 1500.00, "901"),
        ("2024-04-10", "9999914", "Proveedor Catorce", "Pago fra 2023", 1600.00, "902"),
    ], con_factura=True),
    "9999909": _df([
        ("2024-01-01", "9999909", "Cliente Nueve", "Apertura", 1000.00),
        ("2024-01-15", "9999909", "Cliente Nueve", "Pago 1", -400.00),
        ("2024-02-15", "9999909", "Cliente Nueve", "Pago 2", -350.00),
        ("2024-03-15", "9999909", "Cliente Nueve", "Fra tardia", 120.00),
    ]),
}


def _mismo_indice(res, conceptos):
    idx = res.set_index("CONCEPTO")["INDICE"]
    valores = {idx[c] for c in conceptos}
    return len(valores) == 1 and 0 not in valores


def _es_cero(res, concepto):
    idx = res.set_index("CONCEPTO")["INDICE"]
    return idx[concepto] == 0


def main() -> int:
    fallos = []

    # 9999901 -- 2.1: todo un mismo indice
    res, _ = asignar_indices_cuenta(FIXTURES["9999901"])
    if not _mismo_indice(res, ["Fra 1", "Pago 1", "Pago 2"]):
        fallos.append("9999901 (2.1): se esperaba un unico indice para las 3 filas")
    else:
        print("OK  9999901 (2.1): total=0, un solo grupo")

    # 9999902 -- 2.2: cancela todo menos el ultimo apunte cronologico
    res, _ = asignar_indices_cuenta(FIXTURES["9999902"])
    if not _mismo_indice(res, ["Apertura", "Pago apertura"]):
        fallos.append("9999902 (2.2): Apertura y Pago apertura deberian compartir indice")
    if not _es_cero(res, "Fra pendiente"):
        fallos.append("9999902 (2.2): Fra pendiente deberia quedar en INDICE 0")
    if not fallos or fallos[-1].startswith("9999901"):
        print("OK  9999902 (2.2): el ultimo apunte cronologico queda pendiente")

    # 9999903 -- 2.3: pareo directo, con un suelto
    res, _ = asignar_indices_cuenta(FIXTURES["9999903"])
    ok3 = _mismo_indice(res, ["Fra A", "Pago A"]) and _mismo_indice(res, ["Fra B", "Pago B"])
    if not ok3:
        fallos.append("9999903 (2.3): Fra A/Pago A y Fra B/Pago B deberian cancelar por pares")
    if not _es_cero(res, "Fra Suelta"):
        fallos.append("9999903 (2.3): Fra Suelta deberia quedar en INDICE 0")
    idxA = res.set_index("CONCEPTO")["INDICE"]["Fra A"]
    idxB = res.set_index("CONCEPTO")["INDICE"]["Fra B"]
    if idxA == idxB:
        fallos.append("9999903 (2.3): el par A y el par B no deberian compartir indice")
    if ok3 and _es_cero(res, "Fra Suelta") and idxA != idxB:
        print("OK  9999903 (2.3): dos pares directos, un suelto sin cancelar")

    # 9999904 -- 2.2b: la apertura la resuelve su propio paso, antes que nadie
    res, _ = asignar_indices_cuenta(FIXTURES["9999904"])
    grupo_ap = _mismo_indice(res, ["Apertura", "Pago 1", "Pago 2", "Pago 3"])
    marca_ap = res.set_index("CONCEPTO").loc[
        ["Apertura", "Pago 1", "Pago 2", "Pago 3"], "GRUPO_APERTURA"].all()
    parD = _mismo_indice(res, ["Fra D", "Pago D"])
    suelta_pendiente = _es_cero(res, "Fra Suelta")
    if not grupo_ap:
        fallos.append("9999904 (2.2b): Apertura+Pago1+Pago2+Pago3 deberian compartir indice")
    if not marca_ap:
        fallos.append("9999904 (2.2b): ese grupo deberia venir marcado GRUPO_APERTURA=True")
    if not parD:
        fallos.append("9999904 (2.3): Fra D / Pago D deberian cancelar por pareo directo")
    if not suelta_pendiente:
        fallos.append("9999904: Fra Suelta deberia quedar en INDICE 0")
    if grupo_ap and marca_ap and parD and suelta_pendiente:
        print("OK  9999904 (2.2b): la apertura se cancela en su propio paso, "
              "par directo aparte, un suelto pendiente")

    # 9999905 -- 2.4 combinatorio (no contiguo en el tiempo)
    res, _ = asignar_indices_cuenta(FIXTURES["9999905"])
    grupoM = _mismo_indice(res, ["M1", "M2", "M3"])
    marcaM = res.set_index("CONCEPTO").loc[["M1", "M2", "M3"], "GRUPO_24"].all()
    resto_pendiente = all(_es_cero(res, c) for c in ["N1 (ruido)", "N2 (ruido)", "Pendiente"])
    if not grupoM:
        fallos.append("9999905 (2.4 combinatorio): M1+M2+M3 deberian compartir indice")
    if not marcaM:
        fallos.append("9999905 (2.4 combinatorio): ese grupo deberia venir GRUPO_24=True")
    if not resto_pendiente:
        fallos.append("9999905: N1, N2 y Pendiente deberian quedar en INDICE 0")
    if grupoM and marcaM and resto_pendiente:
        print("OK  9999905 (2.4 combinatorio): M1/M2/M3 cancelan sin ser contiguos "
              "en fecha, el resto queda pendiente")

    # 9999906 -- punteo previo parcial: se respeta y se numera por encima
    res, _ = asignar_indices_cuenta(FIXTURES["9999906"])
    porc = res.set_index("CONCEPTO")
    ok = True
    if not (porc.loc["Fra punteada", "INDICE"] == 3
            and porc.loc["Pago punteado", "INDICE"] == 3):
        fallos.append("9999906 (punteo previo): el par punteado deberia conservar "
                      "su indice 3 tal cual")
        ok = False
    if not (porc.loc[["Fra punteada", "Pago punteado"], "ORIGEN"] == ORIGEN_CONTABLE).all():
        fallos.append("9999906 (punteo previo): el par punteado deberia venir con "
                      "ORIGEN contable")
        ok = False
    if not _mismo_indice(res, ["Fra nueva", "Pago nuevo"]):
        fallos.append("9999906 (punteo previo): Fra nueva / Pago nuevo deberian "
                      "cancelar con un indice nuevo")
        ok = False
    elif porc.loc["Fra nueva", "INDICE"] <= 3:
        fallos.append("9999906 (punteo previo): el indice nuevo deberia ser > 3 "
                      "(el maximo previo), y es "
                      + str(int(porc.loc["Fra nueva", "INDICE"])))
        ok = False
    # el 2.2 («total»: todo menos el ultimo suma cero) llega antes que el 2.3 («importe»)
    if not porc.loc[["Fra nueva", "Pago nuevo"], "ORIGEN"].isin([PASO_IMPORTE, PASO_TOTAL]).all():
        fallos.append("9999906 (punteo previo): el par nuevo deberia venir con "
                      "ORIGEN del paso que lo formo («total» o «importe»), y trae "
                      + str(porc.loc[["Fra nueva", "Pago nuevo"], "ORIGEN"].tolist()))
        ok = False
    if not _es_cero(res, "Fra pendiente"):
        fallos.append("9999906 (punteo previo): Fra pendiente deberia quedar en INDICE 0")
        ok = False
    info = verificar_cuenta(res)
    if info["num_grupos_previos"] != 1 or info["num_grupos_nuevos"] != 1:
        fallos.append("9999906 (punteo previo): se esperaba 1 grupo previo y 1 nuevo, "
                      "y hay " + str(info["num_grupos_previos"]) + " / "
                      + str(info["num_grupos_nuevos"]))
        ok = False
    if ok:
        print("OK  9999906 (punteo previo parcial): el punteo se respeta, el skill "
              "completa con indices nuevos por encima del previo")

    # 9999907 -- punteo previo descuadrado: se respeta, se reporta, y la
    # verificacion estructural sigue cuadrando
    res, _ = asignar_indices_cuenta(FIXTURES["9999907"])
    porc = res.set_index("CONCEPTO")
    info = verificar_cuenta(res)
    ok = True
    if not (porc.loc["Fra mal punteada", "INDICE"] == 1
            and porc.loc["Pago mal punteado", "INDICE"] == 1):
        fallos.append("9999907 (descuadre previo): el grupo descuadrado deberia "
                      "conservar su indice 1 tal cual")
        ok = False
    if info["grupos_previos_descuadrados"] != {1: 50.0}:
        fallos.append("9999907 (descuadre previo): se esperaba reportar {1: 50.0} y "
                      "se reporta " + str(info["grupos_previos_descuadrados"]))
        ok = False
    if not info["coincide_total_con_no_cancelado"]:
        fallos.append("9999907 (descuadre previo): la conciliacion estructural "
                      "deberia cuadrar descontando el descuadre previo")
        ok = False
    if info["grupos_con_error"]:
        fallos.append("9999907 (descuadre previo): el descuadre es del punteo "
                      "previo, no deberia contarse como error del skill")
        ok = False
    if not _mismo_indice(res, ["Fra C", "Pago C"]):
        fallos.append("9999907 (descuadre previo): Fra C / Pago C deberian cancelar "
                      "por pareo directo igualmente")
        ok = False
    if ok:
        print("OK  9999907 (punteo previo descuadrado): se respeta, se reporta como "
              "descuadre, y la verificacion sigue cuadrando")

    # 9999908 -- punteo previo completo: el skill no toca nada
    res, _ = asignar_indices_cuenta(FIXTURES["9999908"])
    info = verificar_cuenta(res)
    ok = True
    if info["num_grupos_nuevos"] != 0:
        fallos.append("9999908 (punteo completo): el skill no deberia añadir grupos, "
                      "y añade " + str(info["num_grupos_nuevos"]))
        ok = False
    if info["num_grupos_previos"] != 2:
        fallos.append("9999908 (punteo completo): se esperaban 2 grupos previos y "
                      "hay " + str(info["num_grupos_previos"]))
        ok = False
    if (res["INDICE"] != res["INDICE_PREVIO"]).any():
        fallos.append("9999908 (punteo completo): los indices previos no deberian "
                      "cambiar")
        ok = False
    if ok:
        print("OK  9999908 (punteo previo completo): nada que añadir, nada tocado")

    # Verificacion estructural sobre todas las cuentas: para cada una, la
    # suma de INDICE=0 tiene que coincidir con el total de la cuenta menos
    # el descuadre de los grupos previos (0 si no hay punteo o esta bien).
    # 9999909 -- la apertura que no cuadra no se fuerza
    res, _ = asignar_indices_cuenta(FIXTURES["9999909"])
    ap_pendiente = _es_cero(res, "Apertura")
    nada_apertura = not res["GRUPO_APERTURA"].any()
    if not ap_pendiente:
        fallos.append("9999909 (2.2b): la apertura no cuadra con ningun subconjunto "
                      "y deberia quedar en INDICE 0, no forzarse")
    if not nada_apertura:
        fallos.append("9999909 (2.2b): no deberia haberse marcado ningun GRUPO_APERTURA")
    if ap_pendiente and nada_apertura:
        print("OK  9999909 (2.2b): una apertura que no cuadra se queda pendiente")

    # 9999910 -- 2.0: una factura y sus tres pagos, atados por el documento
    res, _ = asignar_indices_cuenta(FIXTURES["9999910"])
    grupo = ["Compra", "Pago 1/3", "Pago 2/3", "Pago 3/3"]
    if not _mismo_indice(res, grupo):
        fallos.append("9999910 (2.0): la compra y sus TRES pagos deberian compartir indice")
    elif not _es_cero(res, "Fra viva"):
        fallos.append("9999910 (2.0): la factura sin pagar deberia quedar pendiente")
    elif not res.loc[res["CONCEPTO"].isin(grupo), "GRUPO_FACTURA"].all():
        fallos.append("9999910 (2.0): el grupo deberia venir marcado GRUPO_FACTURA")
    else:
        print("OK  9999910 (2.0): una factura muerta por tres pagos desiguales, por numero de documento")

    # 9999911 -- el numero propone, la suma decide: grupo que no cierra, se rechaza
    res, _ = asignar_indices_cuenta(FIXTURES["9999911"])
    if not (_es_cero(res, "Fra A") and _es_cero(res, "Pago parcial")):
        fallos.append("9999911 (2.0): un grupo por numero que NO suma cero no se puede aceptar")
    elif res["GRUPO_FACTURA"].any():
        fallos.append("9999911 (2.0): no deberia haber ningun GRUPO_FACTURA")
    else:
        print("OK  9999911 (2.0): el numero PROPONE y la suma DECIDE: grupo que no cierra, rechazado")

    # 9999912 -- 2.0 no desplaza a los pasos de importes: los dos suman
    res, _ = asignar_indices_cuenta(FIXTURES["9999912"])
    por_doc = ["Fra 88", "Pago 88 a", "Pago 88 b"]
    por_imp = ["Fra 99", "Pago sin numero"]
    if not _mismo_indice(res, por_doc):
        fallos.append("9999912 (2.0): la 88 deberia cerrarse por documento")
    elif not _mismo_indice(res, por_imp):
        fallos.append("9999912 (2.3): el par que solo cierra por importe deberia seguir cerrandose")
    elif res.loc[res["CONCEPTO"].isin(por_imp), "GRUPO_FACTURA"].any():
        fallos.append("9999912: el par por importe no viene del documento y no debe marcarse")
    else:
        print("OK  9999912 (2.0+2.3): el documento y el importe se complementan, no se estorban")

    # 9999913 -- 2.2c: la apertura se mata deduciendo que esas facturas no estan
    res, _ = asignar_indices_cuenta(FIXTURES["9999913"])
    grupo = ["Apertura", "Pago fra 2023", "Regularizacion"]
    idx_ap = res.loc[res["CONCEPTO"] == "Apertura", "INDICE"].iloc[0]
    del_grupo = res[res["INDICE"] == idx_ap]
    if idx_ap == 0:
        fallos.append("9999913 (2.2c): la apertura deberia haberse cancelado")
    elif len(del_grupo) != 5:
        fallos.append(f"9999913 (2.2c): el grupo de la apertura deberia tener 5 apuntes, tiene {len(del_grupo)}")
    elif not _es_cero(res, "Fra del año, viva"):
        fallos.append("9999913 (2.2c): la factura del año sin pagar deberia quedar pendiente")
    elif not del_grupo["GRUPO_APERTURA"].all():
        fallos.append("9999913 (2.2c): el grupo deberia venir marcado GRUPO_APERTURA")
    else:
        print("OK  9999913 (2.2c): la apertura se cancela con los pagos de facturas ajenas al ejercicio")

    # 9999914 -- sin la regularizacion no cuadra: no se fuerza
    res, _ = asignar_indices_cuenta(FIXTURES["9999914"])
    if not _es_cero(res, "Apertura"):
        fallos.append("9999914 (2.2c): sin el apunte que cierra el hueco, la apertura NO se puede cancelar")
    else:
        print("OK  9999914 (2.2c): si no cuadra al centimo, la apertura se queda pendiente")

    for cuenta, datos in FIXTURES.items():
        res, _ = asignar_indices_cuenta(datos)
        info = verificar_cuenta(res)
        if not info["coincide_total_con_no_cancelado"] or info["grupos_con_error"]:
            fallos.append("verificacion " + cuenta + ": " + str(info))

    if fallos:
        print("\nFALLA:")
        for f in fallos:
            print("  - " + f)
        return 1

    # 9999915 -- sin CONCEPTO: nada se rompe y nada se degrada en silencio
    sin_con = FIXTURES["9999913"].drop(columns=["CONCEPTO"]).copy()
    sin_con["ASIENTO"] = [str(i) for i in range(1, len(sin_con) + 1)]
    try:
        res15, _ = asignar_indices_cuenta(sin_con)
        emparejo = int(res15.loc[res15["CONCEPTO"] == "Apertura", "INDICE"].iloc[0]) if "CONCEPTO" in res15 else None
    except KeyError as exc:
        fallos.append("9999915: sin CONCEPTO el emparejamiento revienta con KeyError " + str(exc))
        res15 = None
    if res15 is not None:
        # el mismo grupo de apertura que en el 9999913: el concepto no pintaba nada
        ap15 = res15.sort_values("FECHA").iloc[0]
        if int(ap15["INDICE"]) == 0 or int((res15["INDICE"] == ap15["INDICE"]).sum()) != 5:
            fallos.append("9999915: sin CONCEPTO la apertura deberia cerrarse igual que en el 9999913")
        else:
            print("OK  9999915 (sin CONCEPTO): el emparejamiento da lo mismo, el concepto no decide")
        h15 = analizar_hallazgos(sin_con, {"9999915": (res15, verificar_cuenta(res15))})
        if h15.get("fecha_doc_disponible") is not False:
            fallos.append("9999915: analizar_hallazgos tiene que decir que el concepto NO esta disponible")
        elif h15["grupos_evaluados"] != 0 or h15["anomalos"] != 0:
            fallos.append("9999915: sin concepto NO se puede evaluar ningun grupo por fecha de documento "
                          "(se estaria usando la fecha contable)")
        else:
            print("OK  9999915 (sin CONCEPTO): los hallazgos por fecha de documento quedan SIN EVALUAR, no a cero")

    # -- el papel: las posiciones de columna se DERIVAN de la cabecera
    # Estaban escritas a mano -j == 5 para el saldo- y al insertar FACTURA el
    # formato de euros y el amarillo se quedaron una columna a la izquierda. Un
    # papel donde el amarillo senala la columna de al lado es peor que no tenerlo.
    import subprocess
    import tempfile

    from openpyxl import load_workbook

    tmp = Path(tempfile.mkdtemp())
    fx = FIXTURES["9999913"].copy()
    fx["ASIENTO"] = [str(i) for i in range(1, len(fx) + 1)]
    fx["FECHA"] = fx["FECHA"].dt.strftime("%Y-%m-%d")
    (tmp / "e.json").write_text(fx.to_json(orient="records"), encoding="utf-8")
    ruta = tmp / "p.xlsx"
    subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "generar_papel.py"),
                    "--entrada", str(tmp / "e.json"), "--salida", str(ruta)],
                   capture_output=True)
    if not ruta.exists():
        fallos.append("el papel no se ha podido generar sobre el fixture 9999913")
    else:
        ws = load_workbook(ruta)["9999913"]
        cab = [ws.cell(row=4, column=j).value for j in range(1, 12)]
        i_saldo, i_idx = cab.index("SALDO") + 1, cab.index("INDICE") + 1
        bien = []
        for f in range(5, ws.max_row + 1):
            if ws.cell(row=f, column=i_idx).value == 0:
                c = ws.cell(row=f, column=i_saldo)
                rgb = (getattr(c.fill.fgColor, "rgb", None)
                       if c.fill and c.fill.patternType else None)
                bien.append(str(rgb).endswith("FFFF00")
                            and c.number_format.startswith("#,##0.00"))
        # y el mismo fixture SIN concepto: el papel no lleva la columna y la hoja de
        # criterios dice NO EVALUADO donde antes contaba pagos anteriores a su factura
        f3 = fx.drop(columns=["CONCEPTO"])
        (tmp / "e2.json").write_text(f3.to_json(orient="records"), encoding="utf-8")
        ruta2 = tmp / "p2.xlsx"
        subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "generar_papel.py"),
                        "--entrada", str(tmp / "e2.json"), "--salida", str(ruta2)],
                       capture_output=True)
        if not ruta2.exists():
            fallos.append("9999915: el papel sin CONCEPTO no se ha podido generar")
        else:
            wb2 = load_workbook(ruta2)
            cab2 = [wb2["9999913"].cell(row=4, column=j).value for j in range(1, 12)]
            crit = " ".join(str(c.value) for row in wb2["Criterios y hallazgos"].iter_rows()
                            for c in row if c.value)
            if "CONCEPTO" in cab2:
                fallos.append("9999915: el papel no debe llevar la columna CONCEPTO si el extracto no la trae")
            elif "NO EVALUADO" not in crit:
                fallos.append("9999915: la hoja de criterios tiene que decir NO EVALUADO, no ensenar ceros")
            else:
                print("OK  9999915 (sin CONCEPTO): el papel sale sin la columna y la hoja de criterios dice NO EVALUADO")
        if not ("ASIENTO" in cab and "FACTURA" in cab):
            fallos.append("el papel deberia traer ASIENTO y FACTURA cuando el extracto las trae")
        elif not (bien and all(bien)):
            fallos.append("el amarillo y el formato de euros tienen que caer en SALDO")
        else:
            print("OK  el papel: ASIENTO y FACTURA presentes, y el amarillo cae en SALDO")

        # 9999916 -- las derivadas del MCP, de punta a punta
        f16 = fx.drop(columns=["CONCEPTO"]).rename(columns={"FACTURA": "NumeroEnConcepto"})
        # la factura viva del año lleva fecha de documento; los pagos y la apertura, no
        f16["FechaEnConcepto"] = [("2024-05-20" if n == "10" else None) for n in f16["NumeroEnConcepto"]]
        (tmp / "e16.json").write_text(f16.to_json(orient="records"), encoding="utf-8")
        df16 = cargar_extracto(tmp / "e16.json")
        if "FACTURA" not in df16.columns or df16.attrs.get("fuente_documento") != "NumeroEnConcepto":
            fallos.append("9999916: NumeroEnConcepto tiene que hacer de FACTURA y decirlo en attrs")
        elif "FECHA_DOC" not in df16.columns or df16.attrs.get("fuente_fecha_doc") != "FechaEnConcepto" \
                or int(df16["FECHA_DOC"].notna().sum()) != 1:
            fallos.append("9999916: FechaEnConcepto tiene que hacer de FECHA_DOC (una fila con fecha)")
        elif "NumeroEnConcepto" in df16.columns or "FechaEnConcepto" in df16.columns:
            fallos.append("9999916: las columnas de origen se normalizan y no se quedan duplicadas")
        else:
            print("OK  9999916 (derivadas): NumeroEnConcepto -> FACTURA y FechaEnConcepto -> FECHA_DOC, con su origen")
            por16 = procesar_extracto(df16)
            res16 = por16["9999913"][0]
            ap16 = res16.sort_values("FECHA").iloc[0]
            if int(ap16["INDICE"]) == 0 or int((res16["INDICE"] == ap16["INDICE"]).sum()) != 5:
                fallos.append("9999916: con el numero derivado la apertura tiene que cerrarse como en el 9999913")
            else:
                print("OK  9999916 (derivadas): el paso 2.0 agrupa por el numero derivado igual que por NN_Factura")
            h16 = analizar_hallazgos(df16, por16)
            if not h16.get("fecha_doc_disponible") or h16.get("fuente_fecha_doc") != "FechaEnConcepto" \
                    or h16.get("fuente_documento") != "NumeroEnConcepto" or h16["grupos_evaluados"] < 1:
                fallos.append("9999916: los hallazgos por fecha SE EVALUAN con la fecha derivada, y dicen su origen: " + str(
                    {k: h16.get(k) for k in ("fecha_doc_disponible", "fuente_fecha_doc", "fuente_documento", "grupos_evaluados")}))
            else:
                print("OK  9999916 (derivadas): los hallazgos por fecha de documento se evaluan sin el texto del concepto")
            ruta16 = tmp / "p16.xlsx"
            subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "generar_papel.py"),
                            "--entrada", str(tmp / "e16.json"), "--salida", str(ruta16)],
                           capture_output=True)
            if not ruta16.exists():
                fallos.append("9999916: el papel con las derivadas no se ha podido generar")
            else:
                wb16 = load_workbook(ruta16)
                ws16 = wb16["9999913"]
                cab16 = [ws16.cell(row=4, column=j).value for j in range(1, 14)]
                crit16 = " ".join(str(c.value) for row in wb16["Criterios y hallazgos"].iter_rows()
                                  for c in row if c.value)
                # la fila de TOTAL es la siguiente a los datos: 6 apuntes desde la fila 5
                j_saldo = cab16.index("SALDO") + 1
                etq = ws16.cell(row=5 + len(f16), column=j_saldo - 1).value
                tot = ws16.cell(row=5 + len(f16), column=j_saldo).value
                if "FECHA DOC." not in cab16 or "FACTURA" not in cab16 or "CONCEPTO" in cab16:
                    fallos.append("9999916: el papel tiene que llevar FECHA DOC. y FACTURA, y no CONCEPTO: " + str(cab16))
                elif "NumeroEnConcepto" not in crit16 or "FechaEnConcepto" not in crit16:
                    fallos.append("9999916: la hoja de criterios tiene que decir que numero y fecha vienen derivados por el MCP")
                elif etq != "TOTAL" or not isinstance(tot, (int, float)):
                    fallos.append("9999916: el TOTAL tiene que caer bajo SALDO, no en una posicion fija: " + str((etq, tot)))
                else:
                    print("OK  9999916 (derivadas): el papel lleva FECHA DOC. y FACTURA, dice su origen, y el TOTAL cae bajo SALDO")

        # 9999917 -- dos candidatas: NN_Factura buena, NN_Documento mala (mismo valor en todo)
        f17 = FIXTURES["9999912"].copy()
        f17["ASIENTO"] = [str(i) for i in range(1, len(f17) + 1)]
        f17["FECHA"] = f17["FECHA"].dt.strftime("%Y-%m-%d")
        f17 = f17.rename(columns={"FACTURA": "NN_Factura"})
        f17["NN_Documento"] = ["ZZZ", "ZZZ", "ZZZ", "ZZZ", ""]   # un grupo de 4 que NO suma cero (-400)
        f17 = f17[["FECHA", "CUENTA", "NOMBRE", "CONCEPTO", "NN_Documento", "NN_Factura", "SALDO", "ASIENTO"]]  # la mala ANTES
        (tmp / "e17.json").write_text(f17.to_json(orient="records"), encoding="utf-8")
        df17 = cargar_extracto(tmp / "e17.json")
        cand17 = df17.attrs.get("candidatas_documento") or []
        if df17.attrs.get("fuente_documento") != "NN_Factura" or len(cand17) != 2 or cand17[0][0] != "NN_Factura" \
                or len(cand17[0]) != 4 or cand17[0][3] != 4 or cand17[1][2] != 0:   # 4 apuntes con valor; la mala no cierra ninguno
            fallos.append("9999917: con dos candidatas tiene que ganar la que mas grupos cierra (NN_Factura), no la primera del SELECT: "
                          + str(df17.attrs.get("fuente_documento")) + " " + str(cand17))
        elif "NN_Documento" in df17.columns or "NN_Factura" in df17.columns:
            fallos.append("9999917: las candidatas se normalizan a FACTURA y no se quedan sueltas")
        else:
            print("OK  9999917 (dos candidatas): gana la que mas grupos cierra, y la comparacion consta en attrs")
        por17 = procesar_extracto(df17)
        res17 = por17["9999912"][0]
        origenes = set(res17.loc[res17["INDICE"] > 0, "ORIGEN"])
        if not origenes <= set(PASOS_ORIGEN):
            fallos.append("9999917: ORIGEN tiene que decir el paso que formo el grupo, y trae " + str(origenes))
        elif PASO_DOCUMENTO not in origenes or len(origenes) < 2:
            # el 88 cierra por documento; lo que queda (Fra 99 / pago sin numero) suma cero
            # y lo cierra el 2.1 («total») antes de llegar al pareo por importe
            fallos.append("9999917: en este fixture hay un grupo por documento y otro por total, y ORIGEN trae " + str(origenes))
        else:
            print("OK  9999917 (ORIGEN): " + ", ".join(sorted(origenes)) + " -- el paso, no solo «auditoria»")
        h17 = analizar_hallazgos(df17, por17)
        if "grupos_por_paso" not in h17 or sum(h17["grupos_por_paso"].values()) != int(res17.loc[res17["INDICE"] > 0, "INDICE"].nunique()):
            fallos.append("9999917: grupos_por_paso tiene que sumar los grupos nuevos: " + str(h17.get("grupos_por_paso")))
        else:
            print("OK  9999917 (hallazgos): grupos_por_paso " + str(h17["grupos_por_paso"]))
        # la tercera fila: pago anterior a factura SIN fecha de documento
        f18 = pd.DataFrame([
            {"FECHA": "2024-03-10", "CUENTA": "9999918", "NOMBRE": "Proveedor Dieciocho", "SALDO": -500.0, "FechaEnConcepto": None, "ASIENTO": "1"},
            {"FECHA": "2024-02-01", "CUENTA": "9999918", "NOMBRE": "Proveedor Dieciocho", "SALDO": 500.0, "FechaEnConcepto": None, "ASIENTO": "2"},
            {"FECHA": "2024-01-01", "CUENTA": "9999918", "NOMBRE": "Proveedor Dieciocho", "SALDO": -100.0, "FechaEnConcepto": None, "ASIENTO": "3"},
            {"FECHA": "2024-01-20", "CUENTA": "9999918", "NOMBRE": "Proveedor Dieciocho", "SALDO": 100.0, "FechaEnConcepto": None, "ASIENTO": "4"},
            # dos facturas vivas al final, para que ni el 2.1 ni el 2.2 junten toda la cuenta
            # en un solo grupo: la apertura cierra por 2.2b y el par de 500 por importe
            {"FECHA": "2024-06-01", "CUENTA": "9999918", "NOMBRE": "Proveedor Dieciocho", "SALDO": -300.0, "FechaEnConcepto": None, "ASIENTO": "5"},
            {"FECHA": "2024-07-01", "CUENTA": "9999918", "NOMBRE": "Proveedor Dieciocho", "SALDO": -250.0, "FechaEnConcepto": None, "ASIENTO": "6"},
        ])
        (tmp / "e18.json").write_text(f18.to_json(orient="records"), encoding="utf-8")
        df18 = cargar_extracto(tmp / "e18.json")
        por18 = procesar_extracto(df18)
        h18 = analizar_hallazgos(df18, por18)
        if h18["anomalos"] != 0 or h18.get("anomalos_sin_fecha_doc", 0) < 1:
            fallos.append("9999918: un pago anterior a una factura SIN fecha de documento va a su propia fila, no a «con la fecha del documento»: "
                          + str({k: h18.get(k) for k in ("anomalos", "anomalos_sin_fecha_doc", "solo_fecha_registro", "grupos_evaluados")}))
        else:
            print("OK  9999918 (sin fecha de documento): el pago anterior cae en su propia fila y no se vende como hallazgo cierto")
        # 9999919 -- una cuenta de UN solo apunte del 1 de enero va aparte de las «no identificables»
        f19 = pd.concat([f18, pd.DataFrame([
            {"FECHA": "2024-01-01", "CUENTA": "9999919", "NOMBRE": "Proveedor Diecinueve", "SALDO": -75.0, "FechaEnConcepto": None, "ASIENTO": "7"},
            {"FECHA": "2024-01-01", "CUENTA": "9999920", "NOMBRE": "Proveedor Veinte", "SALDO": -40.0, "FechaEnConcepto": None, "ASIENTO": "8"},
            {"FECHA": "2024-01-01", "CUENTA": "9999920", "NOMBRE": "Proveedor Veinte", "SALDO": -60.0, "FechaEnConcepto": None, "ASIENTO": "9"},
            {"FECHA": "2024-02-01", "CUENTA": "9999920", "NOMBRE": "Proveedor Veinte", "SALDO": 30.0, "FechaEnConcepto": None, "ASIENTO": "10"},
        ])], ignore_index=True)
        (tmp / "e19.json").write_text(f19.to_json(orient="records"), encoding="utf-8")
        df19 = cargar_extracto(tmp / "e19.json")
        h19 = analizar_hallazgos(df19, procesar_extracto(df19))
        if h19.get("cuentas_un_apunte") != 1 or abs(h19.get("importe_un_apunte", 0) - 75.0) > 0.005 \
                or h19["aperturas_no_identificadas"] != 1 or abs(h19["aperturas_importe_no_identificado"] - 40.0) > 0.005:
            fallos.append("9999919: la cuenta de un solo apunte (75) va aparte de la apertura no identificable (dos el 1 de enero, 40): "
                          + str({k: h19.get(k) for k in ("cuentas_un_apunte", "importe_un_apunte", "aperturas_no_identificadas", "aperturas_importe_no_identificado")}))
        else:
            print("OK  9999919 (un solo apunte): separada de las aperturas no identificables, con su recuento y su importe")
        r19 = subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "generar_papel.py"),
                              "--entrada", str(tmp / "e19.json"), "--salida", str(tmp / "p19.xlsx")],
                             capture_output=True, text=True, encoding="utf-8")
        tot = [l for l in r19.stdout.splitlines() if l.strip().startswith("TOTAL ")]
        if not tot or "3 cuenta(s)" not in tot[0] or "pendiente total" not in tot[0] or "verificacion: todas OK" not in tot[0]:
            fallos.append("9999919: el stdout del papel tiene que acabar con una linea TOTAL con cuentas, apuntes, pendiente y verificacion: " + str(tot))
        else:
            print("OK  9999919 (stdout): linea TOTAL con el agregado, que el corte a 30 cuentas se llevaba")
        ruta18 = tmp / "p18.xlsx"
        subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "generar_papel.py"),
                        "--entrada", str(tmp / "e18.json"), "--salida", str(ruta18)], capture_output=True)
        if ruta18.exists():
            crit18 = " ".join(str(c.value) for row in load_workbook(ruta18)["Criterios y hallazgos"].iter_rows() for c in row if c.value)
            if "Solo con la fecha contable" not in crit18 or "por el paso que los formo" not in crit18:
                fallos.append("9999918: la hoja de criterios tiene que llevar la fila «Solo con la fecha contable» y los grupos por paso")
            else:
                print("OK  9999918 (papel): la hoja de criterios lleva la tercera fila y los grupos por paso")
        else:
            fallos.append("9999918: el papel no se ha podido generar")

    # segunda puerta: los bloques de arriba (9999915 en adelante) tambien llenan `fallos`,
    # y hasta el 10/09/2026 se quedaban sin reportar porque la unica puerta iba antes
    if fallos:
        print("\nFALLA:")
        for f in fallos:
            print("  - " + f)
        return 1
    print("\nTodo detectado. El emparejador ve los diecinueve casos y las verificaciones cuadran.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
