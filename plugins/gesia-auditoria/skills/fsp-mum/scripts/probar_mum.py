# -*- coding: utf-8 -*-
"""Arnes de fsp-mum. No necesita ForSampling ni un solo PDF.

Un fixture sintetico de ocho elementos de respuesta conocida, elegidos por lo
que puede salir mal en una MUM, que no es lo mismo que en una de cumplimiento:

  E1  gasto contabilizado por la BASE, documento que la sostiene  -> error 0
  E2  gasto por la base con diferencia real de 450,00             -> error y tasa
  E3  sin documento en la carpeta                                 -> sin medir
  E4  contabilizado por el TOTAL, documento que lo sostiene       -> error 0
  E5  INGRESO con saldo negativo y documento que lo sostiene      -> error 0
  E6  ingreso negativo con diferencia                             -> error negativo
  E7  documento sin total legible y libros con IVA                -> pista de IVA
  E8  sin importe en la poblacion                                 -> sin medir

Y las reglas que no se pueden romper: el termino de comparacion sale de la
propia muestra, los errores NO se netean, y lib_fsp.py es el mismo fichero que
en fsp-cumplimiento.

    python probar_mum.py        ->  0 si todo va bien, 1 si algo falla
"""
from __future__ import annotations

import copy
import hashlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_fsp import base_de, columnas_de_muestra, cruzar, detectar_columnas, salida_utf8  # noqa: E402
from lib_mum import (  # noqa: E402
    comparar_con_auditor_mum,
    evaluar_mum,
    observacion_mum,
    recuento,
    termino_mayoritario,
)

MUESTRA = [
    {"GA1Poblacion_ID": "1", "Seleccionado": "True", "Repeticiones": "2", "Fecha": "13/03/25 0:00:00",
     "CuentaContable": "62300011", "DescripcinApunte": "OMICRON", "Saldo": "12500", "Acreedor": "OMICRON"},
    {"GA1Poblacion_ID": "2", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "26/02/25 0:00:00",
     "CuentaContable": "62300004", "DescripcinApunte": "ALFA", "Saldo": "4950,00", "Acreedor": "ALFA, Lda."},
    {"GA1Poblacion_ID": "3", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "03/04/25 0:00:00",
     "CuentaContable": "62900200", "DescripcinApunte": "SIN PAPELES", "Saldo": "3344,83", "Acreedor": "SIN PAPELES"},
    {"GA1Poblacion_ID": "4", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "06/05/25 0:00:00",
     "CuentaContable": "62700000", "DescripcinApunte": "GAMMA", "Saldo": "1210", "Acreedor": "GAMMA, S.L."},
    {"GA1Poblacion_ID": "5", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "30/07/25 0:00:00",
     "CuentaContable": "70000000", "DescripcinApunte": "CLIENTE UNO", "Saldo": "-5000", "Acreedor": "CLIENTE UNO, S.A."},
    {"GA1Poblacion_ID": "6", "Seleccionado": "True", "Repeticiones": "2", "Fecha": "01/09/25 0:00:00",
     "CuentaContable": "70000000", "DescripcinApunte": "CLIENTE DOS", "Saldo": "-8000", "Acreedor": "CLIENTE DOS, S.L."},
    {"GA1Poblacion_ID": "7", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "06/10/25 0:00:00",
     "CuentaContable": "62900000", "DescripcinApunte": "DELTA", "Saldo": "12100", "Acreedor": "DELTA SERVICIOS"},
    {"GA1Poblacion_ID": "8", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "10/11/25 0:00:00",
     "CuentaContable": "62900000", "DescripcinApunte": "OMEGA", "Saldo": "", "Acreedor": "OMEGA"},
    # E9 y E10: el asiento esta PARTIDO en dos lineas de la poblacion y la muestra cogio una.
    # Las tres columnas ultimas las adjunta el MCP desde la propia poblacion (no del diario).
    {"GA1Poblacion_ID": "9", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "04/12/25 0:00:00",
     "CuentaContable": "60000001", "DescripcinApunte": "EPSILON", "Saldo": "8000", "Acreedor": "EPSILON",
     "LineasAsiento": 2, "ImporteAsiento": 10000.0, "IdsAsiento": "9, 11"},
    {"GA1Poblacion_ID": "10", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "09/12/25 0:00:00",
     "CuentaContable": "60000001", "DescripcinApunte": "ZETA", "Saldo": "8400", "Acreedor": "ZETA, S.L.",
     "LineasAsiento": 2, "ImporteAsiento": 10500.0, "IdsAsiento": "10, 12"},
]

FACTURAS = [
    # E1: base 17.000 = saldo -> casa por base
    {"fichero": "1 - OMICRON 25-114.pdf", "proveedor": "OMICRON CONSULTORES", "numero": "25-114",
     "fecha": "13/03/2025", "concepto": "Honorarios de consultoria", "base": "12500,00",
     "iva": "2625,00", "total": "15125,00"},
    # E2: la factura dice 4.500,00 y los libros 4.950,00
    {"fichero": "2 - ALFA FK25-00133.pdf", "proveedor": "ALFA, LDA.", "numero": "FA25/00042",
     "fecha": "25/02/2025", "base": "4500,00", "iva": "0,00", "total": "4500,00"},
    # E4: contabilizado por el total
    {"fichero": "4 - GAMMA 900.pdf", "proveedor": "GAMMA, S.L.", "numero": "900",
     "fecha": "05/05/2025", "base": "1000,00", "iva": "210,00", "total": "1210,00"},
    # E5: ingreso, el documento sostiene los 5.000
    {"fichero": "5 - CLIENTE UNO FV-31.pdf", "proveedor": "CLIENTE UNO, S.A.", "numero": "FV-31",
     "fecha": "30/07/2025", "base": "5000,00", "iva": "1050,00", "total": "6050,00"},
    # E6: ingreso, el documento dice 7.900 y los libros 8.000
    {"fichero": "6 - CLIENTE DOS FV-77.pdf", "proveedor": "CLIENTE DOS, S.L.", "numero": "FV-77",
     "fecha": "01/09/2025", "base": "7900,00", "iva": "1659,00", "total": "9559,00"},
    # E9: el documento sostiene la SUMA del asiento (10.000), no esta linea (8.000)
    {"fichero": "9 - EPSILON E-55.pdf", "proveedor": "EPSILON", "numero": "E-55",
     "fecha": "04/12/2025", "base": "10000,00", "iva": "2100,00", "total": "12100,00"},
    # E10: no sostiene ni la linea (8.400) ni la suma del asiento (10.500)
    {"fichero": "10 - ZETA Z-90.pdf", "proveedor": "ZETA, S.L.", "numero": "Z-90",
     "fecha": "09/12/2025", "base": "9800,00", "iva": "2058,00", "total": "11858,00"},
    # E7: sin total legible; los libros llevan 12.100 = base + 21 %
    {"fichero": "7 - DELTA 5512.pdf", "proveedor": "DELTA SERVICIOS", "numero": "5512",
     "fecha": "06/10/2025", "base": "10000,00", "iva": "", "total": "", "notas": "total ilegible"},
]

EVALUACION_AUDITOR = [
    {"GA1Poblacion_ID": "1", "Saldo": "12500", "SaldoAuditoria": "12500", "ErrorAuditoria": "0",
     "GA1Poblacion_OBSERV": "Ok. Revisada factura de honorarios"},
    # el auditor SI vio el error de 450,00
    {"GA1Poblacion_ID": "2", "Saldo": "4950,00", "SaldoAuditoria": "4500,00", "ErrorAuditoria": "450",
     "GA1Poblacion_OBSERV": "Diferencia de 450,00 con la factura"},
    # y aqui puso un error que el skill no ve: es la cifra que importa
    {"GA1Poblacion_ID": "4", "Saldo": "1210", "SaldoAuditoria": "1000", "ErrorAuditoria": "210",
     "GA1Poblacion_OBSERV": "El apunte lleva el IVA, que no es gasto"},
]


def main() -> int:
    salida_utf8()
    fallos = 0

    def ok(cond: bool, texto: str) -> None:
        nonlocal fallos
        print(("OK   " if cond else "FALLA") + "  " + texto)
        if not cond:
            fallos += 1

    cols, _ = detectar_columnas(MUESTRA[0])
    ok(cols.get("importe") == "Saldo" and cols.get("id") == "GA1Poblacion_ID",
       "reconoce el importe y el id de una poblacion de MUM (GA1Poblacion_ID, Saldo)")
    ok(cols.get("tercero") in ("DescripcinApunte", "Acreedor"),
       "reconoce una columna de tercero aunque la poblacion no traiga numero de documento")

    cruce = cruzar(MUESTRA, FACTURAS, cols)
    ev = evaluar_mum(cruce, cols)
    for e in ev:
        e["observacion"] = observacion_mum(e)
    por_id = {e["fila"]["GA1Poblacion_ID"]: e for e in ev}
    e1, e2, e3, e4, e5, e6, e7, e8, e9, e10 = (por_id[str(i)] for i in range(1, 11))

    # -- el termino de comparacion sale de la muestra, no del plan contable
    ok(termino_mayoritario(cruce["filas"]) == "base",
       "el termino mayoritario de la muestra es la base: lo votan los elementos que casan")
    ok(termino_mayoritario([{"criterios": {"importe": "total"}}]) == "",
       "con un solo elemento casado no hay criterio: no se propone termino")
    ok(termino_mayoritario([{"criterios": {"importe": "total"}}, {"criterios": {"importe": "total"}},
                            {"criterios": {"importe": "base"}}, {"criterios": {"importe": "base"}}]) == "",
       "y con empate tampoco: lo decide el auditor")

    # -- los elementos
    ok(e1["error"] == 0.0 and e1["termino"] == "base"
       and e1["observacion"] == "Asistente IA: Ok. Fra 25-114: importe correcto.",
       "E1: gasto por la base que el documento sostiene -> error 0 y observacion de una linea")
    ok(e2["saldo_auditoria"] == 4500.0 and e2["error"] == 450.0 and e2["tasa"] == 9.09,
       "E2: diferencia real -> saldo auditoria 4.500,00, error 450,00 y tasa 9,09 %")
    ok("450,00" in e2["observacion"] and "de mas en libros" in e2["observacion"].replace("á", "a"),
       "E2: la observacion dice la diferencia y hacia que lado esta")
    ok("4.950,00" not in e2["observacion"] and "4.500,00" not in e2["observacion"]
       and "9,09" not in e2["observacion"],
       "E2: y NO repite el saldo, el valor de auditoria ni el %: cada uno esta en su columna")
    ok(e9["error"] == 0.0 and e9["saldo_auditoria"] == 8000.0,
       "E9: linea de un asiento partido cuya SUMA sostiene el documento -> medido, error 0")
    ok("asiento entero" in e9["observacion"] and "9, 11" in e9["observacion"],
       "E9: y la observacion dice que el documento cubre el asiento, y donde estan sus lineas")
    ok(e10["error"] is None and e10["saldo_auditoria"] is None,
       "E10: si no casa ni la linea ni la suma, NO se propone importe (el error falso seria la otra linea)")
    ok("10, 12" in e10["observacion"] and "10.500,00" in e10["observacion"]
       and "Sin propuesta" in e10["observacion"],
       "E10: y la observacion lleva al auditor a las lineas y dice cuanto suman")
    ok(e1["error"] == 0.0 and e2["error"] == 450.0,
       "un elemento que NO esta partido no cambia en nada")
    # la columna del tercero: la del MCP y la del skill tienen que ser LA MISMA (18/09/2026)
    _mc = [{"Hoja1_ID": str(i), "FECHA": "01/03/25 0:00:00", "CUENTA": "60000000%d" % (i % 3),
            "ASIENTO": 1000 + i, "SALDO": "100,00", "NOMBRE": "TER h%06x" % (i % 6),
            "NOMBRECONTRAP": "PROV 4000000%02d" % (i % 9)} for i in range(14)]
    ok(columnas_de_muestra(_mc)[0].get("tercero") == "NOMBRECONTRAP",
       "el tercero es la columna con tokens de CUENTA, no la que solo lleva tokens de reserva")
    _sc = [{k: v for k, v in f.items() if k != "NOMBRECONTRAP"} for f in _mc]
    ok(columnas_de_muestra(_sc)[0].get("tercero") == "NOMBRE",
       "y sin columna de contrapartida se sigue eligiendo como siempre")
    ok(base_de({"base": "1000,00", "iva": "210,00", "total": "1210,00"}) == 1000.0
       and base_de({"base": "", "iva": "404,55", "total": "2330,96"}) == 1926.41
       and base_de({"base": "", "iva": "", "total": "2330,96"}) is None,
       "la base se deriva de total - iva cuando el documento no la rotula, y no se inventa sin IVA")

    # importe_aplicable: la anulacion a mano para lo que el reparto automatico no ve
    _m2 = copy.deepcopy(MUESTRA); _f2 = copy.deepcopy(FACTURAS)
    for _x in _f2:
        if _x["fichero"].startswith("10 - ZETA"):
            _x["poblacion_id"] = "10"; _x["importe_aplicable"] = "8400,00"
    _e = {str(x["fila"]["GA1Poblacion_ID"]): x
          for x in evaluar_mum(cruzar(_m2, _f2, columnas_de_muestra(_m2)[0]), columnas_de_muestra(_m2)[0])}
    ok(_e["10"]["error"] == 0.0 and _e["10"]["saldo_auditoria"] == 8400.0,
       "importe_aplicable declarado a mano manda: el elemento se mide contra esa parte del documento")
    ok("a mano" in observacion_mum(_e["10"]),
       "y la observacion dice que va declarado a mano, no deducido")
    ok(max(len(x["observacion"]) for x in ev) <= 150,
       f"ninguna observacion pasa de 150 caracteres (la mas larga: {max(len(x['observacion']) for x in ev)})")
    ok(e3["error"] is None and e3["saldo_auditoria"] is None and "no localizado" in e3["observacion"],
       "E3: sin documento no se inventa importe segun auditoria")
    ok(e4["error"] == 0.0 and e4["termino"] == "total",
       "E4: un elemento contabilizado por el total casa por el total aunque la muestra vaya por base")
    ok(e5["error"] == 0.0 and e5["saldo_auditoria"] == -5000.0,
       "E5: ingreso negativo -> el importe segun auditoria conserva el signo del saldo")
    ok(e6["saldo_auditoria"] == -7900.0 and e6["error"] == -100.0,
       "E6: ingreso con diferencia -> error = Saldo - SaldoAuditoria, con su signo")
    ok("de mas en libros" in e6["observacion"].replace("á", "a"),
       "E6: y la redaccion no se lia con el signo: compara magnitudes")
    ok(e7["error"] == 2100.0 and "IVA del 21 %" in e7["nota"],
       "E7: sin total legible, la diferencia es la cuota de IVA y se avisa de que puede ser criterio")
    ok(e8["error"] is None and "no trae importe" in e8["nota"],
       "E8: sin importe en la poblacion no hay nada que medir")

    # -- el recuento no netea NUNCA
    r = recuento(ev)
    ok(r["elementos"] == 10 and r["repeticiones"] == 12,
       "el recuento cuenta 10 elementos y 12 unidades de muestreo con las repeticiones")
    ok(r["n_exceso"] == 2 and r["suma_exceso"] == 2550.0 and r["n_defecto"] == 1 and r["suma_defecto"] == -100.0,
       "exceso y defecto van POR SEPARADO: 2 por exceso suman 2.550,00 y 1 por defecto -100,00")
    ok("neto" not in r and not any("neto" in k for k in r),
       "y no existe ninguna cifra de error neto: netear una MUM esconde las incorrecciones")
    ok(r["sin_medir"] == 3 and r["con_documento"] == 8,
       "tres quedan sin medir -sin documento, sin importe, y el asiento partido que no cuadra- y ocho tienen documento")

    # -- comparacion con el auditor
    comp = comparar_con_auditor_mum(ev, EVALUACION_AUDITOR, cols)
    c = comp["recuento"]
    ok(c["coinciden"] == 2, "coincide con el auditor en los dos elementos que los dos midieron igual")
    ok(c["skill_cero_auditor_error"] == 1,
       "y detecta el caso peligroso: el skill da 0 donde el auditor puso un error de 210,00")
    ok(any(f["estado"].startswith("EL SKILL DA 0") and f["observacion_auditor"] for f in comp["filas"]),
       "arrastrando la observacion del auditor, que es donde esta el motivo")

    # -- el rotulo de la columna miente: se elige por el dato (caso medido 03/09/2026)
    VENTAS = [
        {"POBLACION_ID": "1", "Repeticiones": "1", "Fecha": "02/01/25 0:00:00", "Cuenta": "70000000",
         "Nombre": "Ventas", "Descripcin": "CLIENTE UNO, S.A.", "Saldo": "-5709", "Proveedores": "CLIENTE UNO, S.A."},
        {"POBLACION_ID": "2", "Repeticiones": "1", "Fecha": "28/03/25 0:00:00", "Cuenta": "70000000",
         "Nombre": "Ventas", "Descripcin": "ZETAFER CARIBE, S.L.", "Saldo": "-1500,00", "Proveedores": "ZETAFER CARIBE, S.L."},
        {"POBLACION_ID": "3", "Repeticiones": "1", "Fecha": "15/05/25 0:00:00", "Cuenta": "70000000",
         "Nombre": "Ventas", "Descripcin": "TERCERO TRES, S.A.", "Saldo": "-3200", "Proveedores": "TERCERO TRES, S.A."},
    ]
    F_VENTAS = [
        {"fichero": "2025000008 CLIENTE UNO.pdf", "proveedor": "CLIENTE UNO, S.A.", "numero": "2025000008",
         "fecha": "02/01/2025", "base": "5709,00", "iva": "1198,89", "total": "6907,89"},
        # el importe NO casa: la factura dice 1234,56 y los libros 1500,00
        {"fichero": "2025000042 ZETAFER CARIBE.pdf", "proveedor": "ZETAFER CARIBE, S.L.", "numero": "2025000042",
         "fecha": "28/03/2025", "base": "1234,56", "iva": "49,68", "total": "286,25"},
        {"fichero": "2025000900 TERCERO TRES.pdf", "proveedor": "TERCERO TRES, S.A.", "numero": "2025000900",
         "fecha": "15/05/2025", "base": "3200,00", "iva": "672,00", "total": "3872,00"},
    ]
    colv, _, avisos_col = columnas_de_muestra(VENTAS)
    ok(colv.get("tercero") == "Descripcin",
       "el tercero se elige por el dato: 'Nombre' vale 'Ventas' en todas las filas y no identifica a nadie")
    ok(any("identifica mucho mejor" in a for a in avisos_col),
       "y el cambio de columna se avisa, no se hace a escondidas")
    ok(detectar_columnas(VENTAS[0])[0].get("tercero") == "Nombre",
       "mirando solo la primera fila se elegiria 'Nombre': por eso hace falta la muestra entera")
    crv = cruzar(VENTAS, F_VENTAS, colv)
    evv = evaluar_mum(crv, colv)
    e_dif = next(e for e in evv if e["fila"]["POBLACION_ID"] == "2")
    ok(e_dif["factura"] is not None and e_dif["error"] == -265.44,
       "el elemento con diferencia real se localiza por tercero y fecha, y sale como error de 265,44")
    ok(not crv["facturas_sin_fila"] and not crv["candidatos_sueltos"],
       "no quedan ni elementos sin documento ni documentos sobrantes")

    # -- dos elementos del mismo tercero y fecha: el reparto no puede elegir a ciegas
    GEMELOS = [
        {"POBLACION_ID": "1", "Repeticiones": "1", "Fecha": "02/01/25 0:00:00", "Cuenta": "70000000",
         "Descripcin": "ZETAFER CARIBE, S.L.", "Saldo": "-1000"},
        {"POBLACION_ID": "2", "Repeticiones": "1", "Fecha": "02/01/25 0:00:00", "Cuenta": "70000000",
         "Descripcin": "ZETAFER CARIBE, S.L.", "Saldo": "-2000"},
    ]
    F_GEMELOS = [
        {"fichero": "A.pdf", "proveedor": "ZETAFER CARIBE, S.L.", "numero": "", "fecha": "02/01/2025",
         "base": "900,00", "iva": "189,00", "total": "1089,00"},
        {"fichero": "B.pdf", "proveedor": "ZETAFER CARIBE, S.L.", "numero": "", "fecha": "02/01/2025",
         "base": "1800,00", "iva": "378,00", "total": "2178,00"},
    ]
    colg, _, _ = columnas_de_muestra(GEMELOS)
    crg = cruzar(GEMELOS, F_GEMELOS, colg)
    ok(all(it["criterios"].get("ambiguo") for it in crg["filas"] if it["factura"]),
       "con dos candidatos empatados por tercero y fecha, la asignacion se marca AMBIGUA en vez de elegir en silencio")
    evg = evaluar_mum(crg, colg)
    for e in evg:
        e["observacion"] = observacion_mum(e)
    ok(all("ATENCIÓN" in e["observacion"] for e in evg),
       "y la observacion lo dice, que es lo que el auditor va a leer")

    # -- la salida de emergencia: atar el documento a mano
    F_ATADA = [dict(F_GEMELOS[1], poblacion_id="1")]
    cra = cruzar(GEMELOS, F_ATADA, colg)
    at = next(it for it in cra["filas"] if it["fila"]["POBLACION_ID"] == "1")
    ok(at["factura"] is not None and at["criterios"].get("declarado"),
       "un documento con poblacion_id se ata a ese elemento sin pasar por la puntuacion")
    eva = evaluar_mum(cra, colg)
    for e in eva:
        e["observacion"] = observacion_mum(e)
    ok("a mano" in next(e for e in eva if e["fila"]["POBLACION_ID"] == "1")["observacion"],
       "y el papel hace constar que el vinculo lo puso el auditor, no el cruce")

    # -- cuando de verdad no hay documento, se proponen las parejas candidatas
    SOLOS = [GEMELOS[0]]
    F_SOLOS = [{"fichero": "otro.pdf", "proveedor": "ZETAFER CARIBE, S.L.", "numero": "",
                "fecha": "20/06/2025", "base": "50,00", "iva": "10,50", "total": "60,50"}]
    crs = cruzar(SOLOS, F_SOLOS, columnas_de_muestra(SOLOS)[0])
    ok(len(crs["candidatos_sueltos"]) == 1 and crs["candidatos_sueltos"][0]["tercero"],
       "un elemento sin documento y un documento sobrante del mismo tercero salen como pareja candidata")


    # -- lotes para los lectores, y la fusion de lo que devuelven (agente lector)
    import json as _json, tempfile as _tf
    from pathlib import Path as _P
    from preparar_documentos import fusionar, repartir_lotes
    _t = _P(_tf.mkdtemp())
    (_t / "manifiesto.json").write_text(_json.dumps({"carpeta": "x", "ppp": 100, "apartados": [], "documentos": [
        {"id": "f01", "fichero": "a.pdf", "ruta": "x/a.pdf", "paginas": 1, "imagenes": ["x/f01_p1.png"]},
        {"id": "f02", "fichero": "b.pdf", "ruta": "x/b.pdf", "paginas": 2, "imagenes": ["x/f02_p1.png"]},
        {"id": "f03", "fichero": "c.pdf", "ruta": "x/c.pdf", "paginas": 1, "imagenes": ["x/f03_p1.png"]}]}), encoding="utf-8")
    (_t / "facturas.json").write_text(_json.dumps({"facturas": [{"fichero": "a.pdf", "total": "1,00"}]}), encoding="utf-8")
    _lotes = repartir_lotes(_t, 1)
    ok(len(_lotes) == 2 and [d["fichero"] for l in _lotes for d in l["documentos"]] == ["b.pdf", "c.pdf"],
       "los lotes solo llevan los documentos PENDIENTES: lo ya transcrito no se relee")
    ok(all(l["salida"].endswith(f"facturas_lote_{l['lote']}.json") for l in _lotes) and (_t / "lotes.json").exists(),
       "cada lote sabe donde tiene que dejar su resultado, y lotes.json queda escrito")
    (_t / "facturas_lote_1.json").write_text(_json.dumps({"facturas": [{"fichero": "b.pdf", "total": "2,00", "poblacion_id": "9"}]}), encoding="utf-8")
    (_t / "facturas_lote_2.json").write_text(_json.dumps({"facturas": [{"fichero": "c.pdf", "total": "3,00"},
                                                                       {"fichero": "z.pdf", "total": "9,00"}]}), encoding="utf-8")
    (_t / "facturas_lote_3.json").write_text("{esto no es json", encoding="utf-8")
    # un lector devolvio el fichero con una etiqueta de cierre pegada detras del JSON y se
    # perdio el lote entero, 10 documentos (registro del 16/09/2026): ahora se recorta
    (_t / "facturas_lote_4.json").write_text(
        '{"facturas": [{"fichero": "d.pdf", "total": "4,00"}]}\n</content>', encoding="utf-8")
    _r = fusionar(_t)
    _f = _json.loads((_t / "facturas.json").read_text(encoding="utf-8"))["facturas"]
    ok([x["fichero"] for x in _f] == ["a.pdf", "b.pdf", "c.pdf", "z.pdf", "d.pdf"],
       "la fusion conserva lo que ya habia, anade los lotes en el orden del manifiesto y deja al final lo desconocido")
    ok(_r["faltan"] == [] and _r["sobran"] == ["z.pdf", "d.pdf"],
       "y dice que sobra z.pdf, que ningun documento del inventario respalda")
    ok("poblacion_id" not in _f[1], "un lector no puede atar documentos a elementos: la fusion le quita poblacion_id")
    ok(_r["parciales"] == 4 and _r["entradas"] == 4, "un lote con JSON invalido se ignora avisando, sin tumbar la fusion")
    from preparar_documentos import _json_de_lote
    ok(_r["rescatados"] == ["facturas_lote_4.json"] and any(x["fichero"] == "d.pdf" for x in _f),
       "un lote con una etiqueta de cierre pegada al JSON se recorta y se lee, y la fusion dice cual")
    ok(all(len((_json_de_lote(_c) or {}).get("facturas", [])) == 1 for _c in (
            '{"facturas": [{"fichero": "a.pdf"}]}\n</content>',
            '```json\n{"facturas": [{"fichero": "a.pdf"}]}\n```',
            'Aqui tienes:\n{"facturas": [{"fichero": "a.pdf"}]}\nListo.',
            '[{"fichero": "a.pdf"}]'))
       and _json_de_lote('{"facturas": [{"fichero": "a.p') is None,
       "el recorte salva valla de codigo, prosa alrededor y lista pelada, pero NO se inventa nada con un fichero truncado")

    # -- el papel: cuatro zonas de color, el campo principal repetido y el error como
    # formula. Se comprueba la HOJA, no solo los numeros: el layout es lo que el auditor
    # ve, y una formula mal puesta en un elemento sin medir pintaria el saldo entero
    # como error.
    try:
        from openpyxl import Workbook as _WB
        from openpyxl.utils import get_column_letter as _L
        import generar_papel as _gp
    except ImportError:
        print("-      el papel: sin openpyxl al lado no se comprueba la hoja")
    else:
        _params = {"Prueba": "PRUEBA SINTETICA", "MuestraId": 7, "Area": "GA",
                   "Referencia": "GA)1", "parametros": {"UnidadMuestreo": "1000",
                   "PoblacionNumElementos": "500", "ErrorTolerableValor": "5000"}}
        _wb = _WB()
        _gp._hoja(_wb, ev, cols, _params, "2026-09-08")
        _ws = _wb.active
        _banda = [c.value for c in _ws[6] if c.value]
        ok([str(x)[:1] for x in _banda] == ["A", "B", "C", "D"],
           "el papel lleva las cuatro bandas de zona: muestra, documento, prueba y cruce")
        _i = {v: n + 1 for n, v in enumerate(c.value for c in _ws[7]) if v}
        ok(all(k in _i for k in ("CIF", "Proveedor o cliente", "Concepto", "Fecha doc.")),
           "la zona del documento trae CIF, tercero, concepto y su propia fecha")
        ok(_i["Fecha doc."] != _i.get("Fecha"),
           "y la fecha del documento no se confunde con la del apunte en el filtro")
        ok(_ws.cell(row=8, column=_i["Concepto"]).value == "Honorarios de consultoria",
           "y el concepto leido en el documento llega al papel")
        ok("VRL (muestra)" in _i and "Valor Auditoría (doc)" in _i and "Error" in _i,
           "la zona de la prueba va en el lenguaje del muestreo: VRL, Valor Auditoria y Error")
        _fs = _ws.cell(row=8, column=_i["VRL (muestra)"]).value
        ok(_fs == f"={_L(_i['Saldo'])}8",
           "el campo principal de la zona C REFERENCIA el de la zona A: el saldo tiene un solo origen")
        _fe = _ws.cell(row=8, column=_i["Error"]).value
        _cs, _cv = _L(_i["VRL (muestra)"]), _L(_i["Valor Auditoría (doc)"])
        ok(_fe == f'=IFERROR({_cs}8-{_cv}8,"")',
           "el error es formula Saldo - Valor auditoria, y envuelta en IFERROR")
        _fp = _ws.cell(row=8, column=_i["% error"]).value
        ok(isinstance(_fp, str) and _fp.startswith("=IFERROR(") and "ABS(" in _fp
           and _fp.endswith('*100,"")'),
           "el % de error es formula sobre magnitudes: con IFERROR, un saldo 0 deja la celda en blanco")
        ok("SI.ERROR" not in _fe and "SI.ERROR" not in _fp,
           "la funcion se guarda en INGLES: SI.ERROR en el fichero rompe la formula")
        ok(_ws.cell(row=10, column=_i["Error"]).value is None
           and _ws.cell(row=10, column=_i["% error"]).value is None,
           "E3, sin documento: SIN formula en error ni en %, para no restar de una celda vacia")
        ok(_ws.cell(row=8, column=_i["Fichero"]).hyperlink is None,
           "sin manifiesto ni carpeta no hay hipervinculo: mejor texto que un vinculo que miente")
        # y con las rutas, enlace absoluto en la celda del fichero
        _rt = _gp.rutas_documentos(None, str(_t))
        _wb2 = _WB()
        _gp._hoja(_wb2, ev, cols, _params, "2026-09-08",
                  {"1 - OMICRON 25-114.pdf": str(_t / "1 - OMICRON 25-114.pdf")})
        _h = _wb2.active.cell(row=8, column=_i["Fichero"]).hyperlink
        ok(_h is not None and Path(_h.target or _h.location or "").is_absolute(),
           "con la ruta del documento, la celda del fichero enlaza y la ruta es ABSOLUTA")
        ok(_wb2.active.cell(row=10, column=_i["Fichero"]).hyperlink is None,
           "y un elemento sin documento no enlaza a ninguna parte")
        # -- las rutas de Windows no pasan por resolve(): el vinculo salia /home/claude/C:\... (16/09/2026)
        _tm = _P(_tf.mkdtemp())
        (_tm / "facturas").mkdir()
        (_tm / "facturas" / "manifiesto.json").write_text(_json.dumps({"carpeta": r"C:\Exp\Facturas", "origen": "mcp", "documentos": [
            {"id": "f01", "fichero": "a.pdf", "ruta": r"C:\Exp\Facturas\a.pdf", "paginas": 1, "imagenes": ["f01_p1.jpg"]}]}), encoding="utf-8")
        _rw = _gp.rutas_documentos(str(_tm / "manifiesto.json"), None)
        ok(_rw.get("a.pdf") == r"C:\Exp\Facturas\a.pdf",
           "una ruta de Windows del manifiesto se enlaza tal cual, sin /home/… delante, y el manifiesto se encuentra en facturas/")
        _rc = _gp.rutas_documentos(None, r"C:\Otra Carpeta\Docs")
        ok(_rc == {}, "sin manifiesto y con una carpeta de Windows que aqui no existe, no se inventa ningun vinculo")
        _rc2 = _gp.rutas_documentos(str(_tm / "manifiesto.json"), r"C:\Otra Carpeta\Docs")
        ok(_rc2.get("a.pdf") == r"C:\Otra Carpeta\Docs\a.pdf",
           "--carpeta-documentos de Windows rehace el vinculo con su propio separador, sin mezclar barras")
        from preparar_documentos import _leer_manifiesto as _lm
        ok(_lm(_tm).get("_carpeta") == str(_tm / "facturas") and "imagenes" in _lm(_tm)["documentos"][0],
           "preparar_documentos lee el manifiesto de la subcarpeta facturas/ y las imagenes se resuelven contra ella")
        # -- las fechas son fechas, y los dias una resta
        from datetime import date as _date, datetime as _dt
        _fl = _ws.cell(row=8, column=_i["Fecha"]).value
        _fd = _ws.cell(row=8, column=_i["Fecha doc."]).value
        ok(isinstance(_fl, (_date, _dt)) and isinstance(_fd, (_date, _dt)),
           "las dos fechas se escriben como FECHA, no como texto: si no, no hay resta posible")
        _fdias = _ws.cell(row=8, column=_i["Días libros–doc."]).value
        ok(_fdias == f'=IFERROR({_L(_i["Fecha"])}8-{_L(_i["Fecha doc."])}8,"")',
           "los dias son la resta de las dos fechas, en el sentido que calcula el cruce")
        ok((_fl - _fd).days == e1["criterios"]["dias"],
           "y la resta de las celdas da lo MISMO que el cruce en Python: el papel no se desvia")

    # -- el tercero llega tokenizado por el MCP (perfil fsp-mum): PROV/CLI + cuenta, o TER h...
    import lib_fsp as _lf
    ok(_lf._tokens_tercero("PROV 40000012") == set() and _lf._tokens_tercero("TER h3f9a2c") == set()
       and not _lf._mismo_tercero("PROV 40000012", "PROVEEDORES DEL NORTE, S.L.")
       and _lf._mismo_tercero("Alfa Lda", "ALFA, LDA."),
       "un tercero tokenizado no tiene palabras que casar: el criterio se apaga sin casar nada por casualidad")
    _tok = [dict(f, **{cols["tercero"]: "PROV 4000" + str(i).zfill(4)}) for i, f in enumerate(MUESTRA)]
    _cr_tok = cruzar(_tok, FACTURAS, cols)
    _por_importe = {i for i, f in enumerate(cruce["filas"]) if f["factura"] and f["criterios"]["importe"]}
    ok(all(_cr_tok["filas"][i]["factura"] is not None
           and _cr_tok["filas"][i]["factura"]["fichero"] == cruce["filas"][i]["factura"]["fichero"] for i in _por_importe)
       and not any(f["criterios"]["tercero"] for f in _cr_tok["filas"]),
       "con la muestra tokenizada el cruce ata por importe lo mismo que antes, y ninguna fila casa por tercero")

    # -- el conteo de paginas sin libreria: el /Count del arbol manda sobre los objetos repetidos
    import preparar_documentos as _pd
    _pdf_inc = (b"%PDF-1.4\n1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
                b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
                b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
                b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"      # guardado incremental: la misma pagina otra vez
                b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
                b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n%%EOF")
    _pdf_tres = (b"%PDF-1.4\n2 0 obj << /Type /Pages /Kids [3 0 R 4 0 R 5 0 R] /Count 3 >> endobj\n"
                 b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n4 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
                 b"5 0 obj << /Type /Page /Parent 2 0 R >> endobj\n%%EOF")
    _pdf_sin = b"%PDF-1.4\n3 0 obj << /Type /Page >> endobj\n4 0 obj << /Type /Page >> endobj\n%%EOF"
    ok(_pd._paginas_sin_libreria(_pdf_inc) == 1 and _pd._paginas_sin_libreria(_pdf_tres) == 3
       and _pd._paginas_sin_libreria(_pdf_sin) == 2 and _pd._paginas_sin_libreria(b"") == 1,
       "sin libreria, las paginas salen del /Count del arbol: un PDF con la pagina repetida por guardados incrementales es 1, no 4")

    # -- la libreria compartida no puede derivar entre skills
    propia = Path(__file__).resolve().parent / "lib_fsp.py"
    hermana = Path(__file__).resolve().parents[2] / "fsp-cumplimiento" / "scripts" / "lib_fsp.py"
    if hermana.exists():
        h1 = hashlib.sha256(propia.read_bytes()).hexdigest()
        h2 = hashlib.sha256(hermana.read_bytes()).hexdigest()
        ok(h1 == h2, "lib_fsp.py es byte a byte el mismo que en fsp-cumplimiento (una sola fuente del cruce)")
    else:
        print("-      lib_fsp.py: sin la copia hermana al lado, no se comprueba la deriva (normal ya instalado)")

    print("\n" + ("RESULTADO: todo correcto" if not fallos else f"RESULTADO: {fallos} fallo(s)"))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
