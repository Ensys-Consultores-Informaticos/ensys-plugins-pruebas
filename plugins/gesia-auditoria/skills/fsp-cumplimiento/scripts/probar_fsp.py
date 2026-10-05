"""Comprueba el cruce y la evaluacion con un fixture sintetico: no hace falta
ForSampling, ni Gesia, ni ningun documento real.

    python probar_fsp.py

Seis elementos de muestra y seis documentos, cada uno con una respuesta conocida:

  E1  factura exacta: numero, importe y fecha casan -> todo Ok
  E2  numero con formato distinto ('FA25/00042' en libros, '2500042' en el
      documento) e importe en libros SUPERIOR al total del documento
      (4.950,00 frente a 4.500,00, como paso de verdad): documento Ok por
      numero, contabilizacion con hallazgo de importe
  E3  sin documento en la carpeta -> 'No localizada'
  E4  el concepto lleva el numero dentro de texto ('S/FACTURA Nº    140') y
      el documento lo trae limpio; base + IVA no cuadran con el total -> calculo
      con hallazgo
  E5  contabilizada por la BASE imponible, no por el total, y registrada 70
      dias despues de la fecha del documento -> dos avisos de contabilizacion
  E6  importe 0 y sin numero: no puede casar con nada

Y un documento de mas -una factura que no esta en la muestra- que tiene que salir
en 'facturas_sin_fila' y no colarse en ninguna fila.

Por que hace falta: un cruce que asigne documentos al azar y uno correcto dan el
mismo recuento de 'localizadas'. Solo un caso con respuesta conocida distingue
los dos.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_fsp import (
    _cuadra_calculo,  # noqa: E402
    ROL_AUDITOR,
    ROL_CALCULO,
    ROL_CONTABILIZACION,
    ROL_DOCUMENTO,
    comparar_con_auditor,
    cruzar,
    detectar_columnas,
    evaluar,
    evaluar_fila,
    normalizar_numero,
    numero_en_texto,
    observacion,
    proponer_roles,
    salida_utf8,
)

MUESTRA = [
    {"60_ID": "1", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "10/05/25 0:00:00",
     "CuentaContable": "60260000", "DescripcinApunte": "CARTONAJES DEL SUR, S.A.", "Saldo": "6500,9", "Documento": "CL250099"},
    {"60_ID": "2", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "26/02/25 0:00:00",
     "CuentaContable": "60000300", "DescripcinApunte": "ALFA, Lda.", "Saldo": "4950,00", "Documento": "FA25/00042"},
    {"60_ID": "3", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "12/03/25 0:00:00",
     "CuentaContable": "60000302", "DescripcinApunte": "BETA S.p.a.", "Saldo": "16704", "Documento": "FTE/16"},
    {"60_ID": "4", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "13/01/25 0:00:00",
     "CuentaContable": "60000000", "DescripcinApunte": "COMPRAS", "Saldo": "2884", "Documento": "S/FACTURA Nº             140"},
    {"60_ID": "5", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "20/09/25 0:00:00",
     "CuentaContable": "60000000", "DescripcinApunte": "PERNOSA", "Saldo": "1000", "Documento": "777"},
    {"60_ID": "6", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "01/06/25 0:00:00",
     "CuentaContable": "60000000", "DescripcinApunte": "NADIE", "Saldo": "0", "Documento": ""},
    # Honorarios de un profesional: el gasto lleva la base y la factura imprime el bruto
    {"60_ID": "7", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "15/04/25 0:00:00",
     "CuentaContable": "62300000", "DescripcinApunte": "ASESORES ARGOS", "Saldo": "1000", "Documento": "A-125"},
    # Alquiler de local: la factura imprime el NETO a pagar, tras el 19 %
    {"60_ID": "8", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "05/05/25 0:00:00",
     "CuentaContable": "62100000", "DescripcinApunte": "PATRIMONIAL DELTA", "Saldo": "800", "Documento": "ALQ-05"},
    # Formacion exenta y contabilizada por el neto: solo el neto localiza el documento
    {"60_ID": "9", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "10/06/25 0:00:00",
     "CuentaContable": "62900000", "DescripcinApunte": "FORMACION SIGMA", "Saldo": "2125", "Documento": "FS-31"},
]

FACTURAS = [
    {"fichero": "1 - CARTONAJES FRA 251221.pdf", "proveedor": "CARTONAJES DEL SUR, S.A.", "numero": "CL250099",
     "fecha": "10/05/2025", "base": "5372,64", "iva": "1128,26", "total": "6500,90"},
    {"fichero": "18 - ALFA FRA 2500042.pdf", "proveedor": "ALFA, LDA.", "numero": "FA FA25/00042",
     "fecha": "25/02/2025", "base": "4500,00", "iva": "0", "total": "4500,00"},
    {"fichero": "4 - X FRA 140.pdf", "proveedor": "PROVEEDOR X", "numero": "140",
     "fecha": "10/01/2025", "base": "2400,00", "iva": "500,00", "total": "2884,00"},
    {"fichero": "5 - PERNOSA FRA 777.pdf", "proveedor": "PERNOSA", "numero": "777",
     "fecha": "10/07/2025", "base": "1000,00", "iva": "210,00", "total": "1210,00"},
    {"fichero": "99 - INTRUSA FRA 9.pdf", "proveedor": "INTRUSA", "numero": "9",
     "fecha": "01/04/2025", "base": "100,00", "iva": "21,00", "total": "121,00"},
    {"fichero": "7 - ARGOS FRA A-125.pdf", "proveedor": "ASESORES ARGOS, S.L.P.", "numero": "A-125",
     "fecha": "14/04/2025", "base": "1000,00", "iva": "210,00", "irpf": "150,00", "pct_iva": "21",
     "total": "1210,00"},
    {"fichero": "8 - DELTA ALQ-05.pdf", "proveedor": "PATRIMONIAL DELTA, S.L.", "numero": "ALQ-05",
     "fecha": "01/05/2025", "base": "800,00", "iva": "168,00", "irpf": "152,00", "total": "816,00"},
    {"fichero": "9 - SIGMA FS-31.pdf", "proveedor": "FORMACION SIGMA", "numero": "FS-31",
     "fecha": "09/06/2025", "base": "2500,00", "iva": "0,00", "irpf": "375,00", "total": "2500,00"},
]

ATRIBUTOS = [
    {"AtributoId": "1", "Nombre": "05 REGISTRO", "Descripcion": "Se ha registrado correcta y oportunamente"},
    {"AtributoId": "2", "Nombre": "11 CONTABILIZACIÓN", "Descripcion": "Se ha contabilizado en fecha y en la cuenta correcta"},
    {"AtributoId": "3", "Nombre": "12 DOCUMENTO", "Descripcion": "Verificada evidencia documental"},
    {"AtributoId": "4", "Nombre": "02 AUTORIZACIÓN", "Descripcion": "Ha sido debidamente autorizado por persona responsable"},
    {"AtributoId": "5", "Nombre": "03 CALCULO", "Descripcion": "Los cálculos se han realizado correctamente"},
]


def main() -> int:
    salida_utf8()
    fallos = 0

    def ok(cond: bool, texto: str) -> None:
        nonlocal fallos
        print(("OK   " if cond else "FALLA") + "  " + texto)
        if not cond:
            fallos += 1

    # -- normalizacion
    ok(normalizar_numero("FA25/00042") == ("FA2500042", "2500042"), "normaliza 'FA25/00042' -> digitos 2500042")
    ok(normalizar_numero("A00/00000901")[1] == "901", "normaliza 'A00/00000901' -> 901")
    ok(numero_en_texto("S/FACTURA Nº             140") == "140", "saca el 140 de 'S/FACTURA Nº    140'")
    ok(numero_en_texto("Fra N: CL250099 a fecha de") == "CL250099", "saca CL250099 de la nota del auditor")
    from lib_fsp import _mismo_numero, _mismo_tercero  # noqa: E402  (privadas, pero son la regla)
    ok(_mismo_numero("FA25/00042", "FA FA25/00042") == "exacto", "FA25/00042 y 'FA FA25/00042' son el mismo numero (digitos iguales)")
    ok(_mismo_numero("159", "59") == "", "159 NO casa con 59: el sufijo exige cuatro cifras (le robaba la factura a otro elemento)")
    ok(_mismo_numero("2025000133", "0133") == "", "tampoco casa un sufijo de tres cifras")
    ok(_mismo_numero("XX2500042", "2500042") == "exacto", "los digitos iguales bastan aunque el prefijo cambie")
    ok(_mismo_tercero("ALFA, Lda.", "ALFA, LDA.") and _mismo_tercero("PERNOSA", "PERFILES DEL NORTE, S.L. (PERNOSA)"),
       "el tercero casa por una palabra significativa comun, sin las formas juridicas")
    ok(not _mismo_tercero("COMPRAS", "PERNOSA") and not _mismo_tercero("S.L.", "LDA."),
       "y no casa por las formas juridicas ni por palabras genericas")

    # -- columnas
    cols, faltan = detectar_columnas(MUESTRA[0])
    ok(cols.get("importe") == "Saldo" and cols.get("fecha") == "Fecha", "detecta importe=Saldo y fecha=Fecha")
    ok(cols.get("documento") == "Documento" and cols.get("id") == "60_ID", "detecta documento=Documento e id=60_ID")
    ok(cols.get("tercero") == "DescripcinApunte", "detecta el tercero en DescripcinApunte")
    ok(not faltan, "no falta ningun rol en esta poblacion")

    # -- roles propuestos por el nombre
    roles = proponer_roles(ATRIBUTOS)
    ok(roles["3"] == ROL_DOCUMENTO, "12 DOCUMENTO -> documento")
    ok(roles["5"] == ROL_CALCULO, "03 CALCULO -> calculo")
    ok(roles["2"] == ROL_CONTABILIZACION, "11 CONTABILIZACION -> contabilizacion")
    ok(roles["4"] == ROL_AUDITOR, "02 AUTORIZACION -> auditor")
    ok(roles["1"] == ROL_AUDITOR, "05 REGISTRO (oportunidad) -> auditor")

    # -- el aviso de dato ilegible dice de quien es la culpa (18/09/2026)
    import json as _json, tempfile as _tmpf
    from verificar_contrato import _culpa_del_tachado
    _d = Path(_tmpf.gettempdir()) / "probar_culpa"
    (_d / "facturas").mkdir(parents=True, exist_ok=True)
    _fj = _d / "facturas.json"
    _fj.write_text("[]", encoding="utf-8")
    _mj = _d / "facturas" / "manifiesto.json"
    _mj.write_text(_json.dumps({"origen": "mcp", "documentos": [
        {"id": "f01", "tachado": {"cabecera": 1, "datos_tapados": 0}},
        {"id": "f02", "tachado": {"cabecera": 1, "datos_tapados": 0}}]}), encoding="utf-8")
    _t0 = _culpa_del_tachado(str(_fj))
    _mj.write_text(_json.dumps({"origen": "mcp", "documentos": [
        {"id": "f01", "tachado": {"cabecera": 1, "datos_tapados": 2}}]}), encoding="utf-8")
    _t1 = _culpa_del_tachado(str(_fj))
    _mj.write_text(_json.dumps({"origen": "script", "documentos": []}), encoding="utf-8")
    _t2 = _culpa_del_tachado(str(_fj))
    ok("NO es una incidencia" in _t0 and "escaneo" in _t0,
       "con el tachado sin tapar datos, el aviso dice que NO es del tachado ni del control")
    ok("ATENCION" in _t1.replace("Ó", "O") and "2 línea" in _t1,
       "y si el tachado SI tapo datos, lo dice con la cuenta")
    ok(_t2 == "",
       "con imagenes que no hizo el MCP no se afirma nada: no hay con que medirlo")
    for _f in sorted((_d / "facturas").iterdir()):
        _f.unlink()
    (_d / "facturas").rmdir(); _fj.unlink(); _d.rmdir()

    # -- el asiento partido: el elemento es UNA LINEA y el documento sostiene el asiento
    # (lo adjunta el MCP a la muestra desde la propia poblacion, no del diario)
    _part = [
        {"60_ID": "20", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "04/12/25 0:00:00",
         "CuentaContable": "60000001", "DescripcinApunte": "EPSILON", "Saldo": "8000", "Documento": "E-55",
         "LineasAsiento": 2, "ImporteAsiento": 12100.0, "IdsAsiento": "20, 21"},
        {"60_ID": "22", "Seleccionado": "True", "Repeticiones": "1", "Fecha": "09/12/25 0:00:00",
         "CuentaContable": "60000001", "DescripcinApunte": "ZETA", "Saldo": "8400", "Documento": "Z-90",
         "LineasAsiento": 2, "ImporteAsiento": 10500.0, "IdsAsiento": "22, 23"},
    ]
    _fac_part = [
        {"fichero": "20 - EPSILON E-55.pdf", "proveedor": "EPSILON", "numero": "E-55",
         "fecha": "04/12/2025", "base": "10000,00", "iva": "2100,00", "total": "12100,00"},
        {"fichero": "22 - ZETA Z-90.pdf", "proveedor": "ZETA", "numero": "Z-90",
         "fecha": "09/12/2025", "base": "9800,00", "iva": "2058,00", "total": "11858,00"},
    ]
    _cols_p = detectar_columnas(_part[0])[0]
    _cp = cruzar(_part, _fac_part, _cols_p)
    _ep = {e["fila"]["60_ID"]: evaluar_fila(e, _cols_p, ATRIBUTOS, roles) for e in _cp["filas"]}
    ok("asiento entero" in _ep["20"]["2"] and _ep["20"]["2"].startswith("Ok"),
       "asiento partido cuya SUMA sostiene el documento: la contabilizacion es Ok, no un hallazgo de importe")
    ok("no corresponde" not in _ep["22"]["2"] and "lo decide el auditor" in _ep["22"]["2"]
       and "22, 23" in _ep["22"]["2"],
       "y si no cuadra, no se afirma que el importe no corresponde: se dice donde estan las lineas y decide el auditor")

    # -- cruce
    cruce = cruzar(MUESTRA, FACTURAS, cols)
    f = {e["fila"]["60_ID"]: e for e in cruce["filas"]}
    ok(f["1"]["factura"] and f["1"]["factura"]["numero"] == "CL250099" and f["1"]["criterios"]["numero"]
       and f["1"]["criterios"]["importe"] == "total", "E1 casa por numero, importe (total) y fecha")
    ok(f["2"]["factura"] and f["2"]["criterios"]["numero"] and f["2"]["criterios"]["importe"] is None
       and f["2"]["criterios"]["diferencia"] == 450.0, "E2 casa por numero con formato distinto; diferencia de importe 450,00")
    ok(f["3"]["factura"] is None, "E3 sin documento -> None")
    ok(f["4"]["factura"] and f["4"]["factura"]["numero"] == "140" and f["4"]["criterios"]["numero"],
       "E4 el numero dentro del concepto casa con el del documento")
    ok(f["5"]["factura"] and f["5"]["criterios"]["importe"] == "base" and f["5"]["criterios"]["dias"] == 72,
       "E5 casa por la BASE y con 72 dias de desfase")
    ok(f["6"]["factura"] is None, "E6 importe 0 y sin numero -> None")
    ok([x["fichero"] for x in cruce["facturas_sin_fila"]] == ["99 - INTRUSA FRA 9.pdf"],
       "la factura intrusa queda en 'facturas_sin_fila' y no se cuela en ninguna fila")

    # -- evaluacion
    ev = {e["fila"]["60_ID"]: e for e in evaluar(cruce, cols, ATRIBUTOS, roles)}
    r1, r2, r3, r4, r5 = (ev[k]["resultados"] for k in ("1", "2", "3", "4", "5"))
    r7, r8, r9 = (ev[k]["resultados"] for k in ("7", "8", "9"))
    ok(r1["3"].startswith("Ok") and r1["5"] == "Ok" and r1["2"] == "Ok" and r1["4"] == "auditor" and r1["1"] == "auditor",
       "E1: documento Ok, calculo Ok, contabilizacion Ok, autorizacion y registro al auditor")
    ok(r2["3"].startswith("Ok") and r2["2"].startswith("Importe en factura (4.500,00) no corresponde con importe en libros (4.950,00)"),
       "E2: documento Ok (por numero) y contabilizacion con el hallazgo de importe redactado con las dos cifras")
    ok(r3["3"].startswith("No localizada la factura") and r3["2"].startswith("No localizada") and r3["4"] == "auditor",
       "E3: 'No localizada' en lo que evalua el skill; 'auditor' en lo que no")
    ok(r4["5"].startswith("Cálculo no cuadra") and "2.900,00" in r4["5"], "E4: base + IVA no cuadra, con las cifras")
    ok("72 días" in r5["2"] and "base imponible" not in r5["2"],
       "E5: casar por la base NO es hallazgo (el IVA va a otra cuenta); solo se informa el desfase de 72 dias")
    # -- reparto entre facturas y justificantes (el nombre solo no basta)
    from pathlib import PurePath as _PP
    from preparar_documentos import clasificar
    nombres = ["2 - X FRA 367.pdf", "2 - X FRA 367 JUSTIFICANTE PAGO 1.pdf",
               "6 - Y FRA F25-002 + JUSTIFICANTE PAGO.pdf", "13 - JUSTIFICANTE Z FACTURAS 611 612.pdf",
               "13 - Z FRA 2500612.pdf"]
    fac, ap = clasificar([_PP(n) for n in nombres])
    fac, ap = [x.name for x in fac], [x.name for x in ap]
    ok("6 - Y FRA F25-002 + JUSTIFICANTE PAGO.pdf" in fac,
       "la factura que lleva el justificante escaneado detras NO se aparta: es la unica evidencia del elemento")
    ok("2 - X FRA 367 JUSTIFICANTE PAGO 1.pdf" in ap and "2 - X FRA 367.pdf" in fac,
       "y el justificante suelto si se aparta, porque su factura esta en otro fichero del mismo grupo")
    ok("13 - JUSTIFICANTE Z FACTURAS 611 612.pdf" in ap and len(fac) == 3,
       "el reparto sale 3 facturas y 2 justificantes en el caso medido")


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
    _r = fusionar(_t)
    _f = _json.loads((_t / "facturas.json").read_text(encoding="utf-8"))["facturas"]
    ok([x["fichero"] for x in _f] == ["a.pdf", "b.pdf", "c.pdf", "z.pdf"],
       "la fusion conserva lo que ya habia, anade los lotes en el orden del manifiesto y deja al final lo desconocido")
    ok(_r["faltan"] == [] and _r["sobran"] == ["z.pdf"],
       "y dice que sobra z.pdf, que ningun documento del inventario respalda")
    ok("poblacion_id" not in _f[1], "un lector no puede atar documentos a elementos: la fusion le quita poblacion_id")
    ok(_r["parciales"] == 3 and _r["entradas"] == 3, "un lote con JSON invalido se ignora avisando, sin tumbar la fusion")

    # -- retencion de IRPF y exencion: las tres formas legitimas de que el total no sea base + IVA
    ok(r7["5"].startswith("Ok (con retención de IRPF de 150,00") and "1.060,00" in r7["5"] and r7["2"] == "Ok",
       "E7: honorarios con retencion, factura por el bruto -> calculo Ok, y dice el importe a pagar")
    ok(r8["5"].startswith("Ok (el total del documento es el neto") and "968,00" in r8["5"],
       "E8: alquiler cuyo documento imprime el neto tras el IRPF -> calculo Ok, y dice el importe de la factura")
    ok(ev["9"]["criterios"]["importe"] == "neto" and r9["3"].startswith("Ok"),
       "E9: contabilizado por el neto -> el documento se localiza igual (tercera clave del cruce)")
    ok(r9["2"].startswith("Ok (el importe en libros casa con el neto"),
       "E9: y casar por el neto se informa sin marcarlo como hallazgo")
    ok(_cuadra_calculo({"base": "2500", "iva": "0", "total": "2500"}).startswith("Ok (exento o no sujeto"),
       "una operacion exenta (IVA cero, base = total) no es un error de calculo")
    ok(_cuadra_calculo({"base": "100", "iva": "21", "irpf": "15", "total": "200"}).startswith("Cálculo no cuadra"),
       "y con retencion, un total que no sale ni en bruto ni en neto si es hallazgo")
    ok("no es el 10 %" in _cuadra_calculo({"base": "1000", "iva": "210", "pct_iva": "10", "total": "1210"}),
       "si el documento declara un tipo que no cuadra con su cuota, se avisa")
    ok(ev["1"]["observacion"].startswith("Asistente IA: A1: auditor · A2: Ok · A3: Ok")
       and ev["1"]["observacion"].endswith("· A4: auditor · A5: Ok"),
       "la observacion sigue la formula 'Asistente IA: A1: ... · A2: ...' en el orden de los atributos")
    ok(observacion({"1": "Ok"}, ATRIBUTOS[:1]) == "Asistente IA: A1: Ok", "observacion minima")

    # -- comparacion con el auditor: un caso donde el auditor puso Si en todo
    evaluacion = {"filas": [{"60_ID": k, "A1": "Sí", "A2": "Sí", "A3": "Sí", "A4": "Sí", "A5": "Sí", "60_OBSERV": "x"}
                            for k in ("1", "2", "3", "4", "5", "6")]}
    comp = comparar_con_auditor(list(ev.values()), evaluacion, cols, ATRIBUTOS)
    n = comp["recuento"]
    ok(n["skill_ok_auditor_no"] == 0, "ningun 'skill Ok, auditor No' (el peligroso) en este fixture")
    ok(n["skill_senala_auditor_si"] >= 3, "el skill senala donde el auditor puso Si (E2 importe, E3, E4, E5): a revisar, no a callar")
    ok(n["auditor"] == 12, "12 celdas quedan al auditor (2 atributos x 6 elementos)")

    # -- el papel: el formato de la MUM traido a cumplimiento (17/09/2026)
    import tempfile as _tf
    from pathlib import Path as _P
    from openpyxl import Workbook as _WB, load_workbook as _LW
    import generar_papel as _gp
    _params = {"MuestraId": 99, "Tipo": "Cumplimiento", "Area": "CG", "Referencia": "CG)1/0",
               "Prueba": "Compras 25", "FechaInicioAuditoria": "01/01/2025", "FechaFinAuditoria": "31/12/2025",
               "parametros": {"TamanoMuestraDeseado": 22, "PoblacionNumElementos": 332, "TasaErrorTolerable": 5}}
    _ruta_doc = r"C:\Exp\Docs\1 - CARTONAJES FRA 251221.pdf"
    _wb = _WB()
    _gp._hoja_muestra(_wb, list(ev.values()), cols, ATRIBUTOS, roles, _params, "2026-09-17",
                      {"1 - CARTONAJES FRA 251221.pdf": _ruta_doc})
    _x = _P(_tf.mkdtemp()) / "papel.xlsx"
    _wb.save(_x)
    _ws = _LW(_x).active
    _cab = [c.value for c in _ws[7]]
    _i = {v: j + 1 for j, v in enumerate(_cab) if v}
    _bandas = [(c.value, c.fill.fgColor.rgb[-6:]) for c in _ws[6] if c.value]
    ok([t for t, _ in _bandas] == ["A · Datos de la muestra", "B · Datos del documento",
                                   "C · Atributos de la prueba", "D · Evidencia del cruce"]
       and [col for _, col in _bandas] == ["1F4E78", "217346", "C55A11", "7F7F7F"],
       "el papel va en cuatro zonas con su banda de titulo y el color de cada una")
    ok(_cab[len(_cab) - 3:] == ["Casa por", "Diferencia importe", "Días libros–doc."]
       and "CIF" in _i and "Proveedor o cliente" in _i and "Concepto" in _i,
       "la zona del documento trae CIF, tercero y concepto, y la del cruce va al final")
    ok(_ws.cell(row=8, column=_i["Fichero"]).hyperlink is not None
       and _ws.cell(row=8, column=_i["Fichero"]).hyperlink.target == _ruta_doc
       and _ws.cell(row=10, column=_i["Fichero"]).hyperlink is None,
       "la celda del fichero enlaza al documento con su ruta de Windows, y un elemento sin documento no enlaza")
    from datetime import datetime as _dt
    ok(isinstance(_ws.cell(row=8, column=_i["Fecha"]).value, _dt)
       and isinstance(_ws.cell(row=8, column=_i["Fecha doc."]).value, _dt)
       and _ws.cell(row=8, column=_i["Fecha"]).number_format == "DD/MM/YYYY",
       "las fechas son FECHA, no texto, y se ven como dd/mm/aaaa: asi se ordenan y se restan")
    ok(str(_ws.cell(row=8, column=_i["Días libros–doc."]).value).startswith("=IFERROR(")
       and _ws.cell(row=10, column=_i["Días libros–doc."]).value is None,
       "los dias son una resta de celdas, y sin documento la celda se queda vacia")
    ok(all(_ws.cell(row=8, column=_i[f"A{a['AtributoId']} {a['Nombre']}"]).value is None for a in ATRIBUTOS),
       "las columnas de atributos siguen EN BLANCO: el veredicto lo firma el auditor")
    ok(_ws.cell(row=9, column=_i["Observación propuesta"]).fill.fgColor.rgb[-6:] == "FFFF00"
       and _ws.cell(row=8, column=_i["Observación propuesta"]).fill.fgColor.rgb[-6:] == "FDF0E6",
       "el amarillo marca la observacion que señala algo, y donde no hay nada queda el tinte de la zona")
    ok("tamaño de muestra 22" in _ws["A2"].value and "población 332" in _ws["A2"].value,
       "la linea de contexto trae los parametros del muestreo que haya en DatosMuestreos")
    _wb2 = _WB()
    _gp._hoja_muestra(_wb2, list(ev.values()), cols, ATRIBUTOS, roles,
                      dict(_params, parametros={}), "2026-09-17", None)
    ok("generado 2026-09-17" in _wb2.active["A2"].value and "·  ·" not in _wb2.active["A2"].value,
       "y sin parametros la linea no deja separadores huerfanos")

    print()
    print("RESULTADO:", "todo correcto" if fallos == 0 else f"{fallos} fallo(s)")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
