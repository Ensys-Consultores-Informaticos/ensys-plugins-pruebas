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

    # -- el bloque de uso de IA (docs/evidencia-uso-ia.md, 19/10/2026): el papel entero, por main()
    import shutil as _sh
    import subprocess as _sp
    from lib_uso_ia import EFECTO, HOJA, REVISION, VERIFICACION, VERIFICADO
    _d = _P(_tf.mkdtemp())
    for _n, _v in (("muestra.json", MUESTRA), ("facturas.json", {"facturas": FACTURAS}),
                   ("parametros.json", dict(_params, atributos=ATRIBUTOS)), ("roles.json", roles)):
        (_d / _n).write_text(_json.dumps(_v, ensure_ascii=False), encoding="utf-8")
    _papel = _d / "papel.xlsx"
    _r = _sp.run([sys.executable, str(_P(__file__).resolve().parent / "generar_papel.py"),
                  "--muestra", str(_d / "muestra.json"), "--parametros", str(_d / "parametros.json"),
                  "--facturas", str(_d / "facturas.json"), "--roles", str(_d / "roles.json"),
                  "--salida", str(_papel), "--generado", "2026-10-19"],
                 capture_output=True, text=True, encoding="utf-8")
    ok(_r.returncode == 0 and _papel.exists(), "generar_papel escribe el papel con el bloque de uso de IA")
    if _papel.exists():
        _wb = _LW(_papel)
        _wi = _wb[HOJA] if HOJA in _wb.sheetnames else None
        ok(_wi is not None and _wb.sheetnames[0] == HOJA, f"el papel lleva la hoja «{HOJA}», la primera")
        if _wi is not None:
            _txt = [str(c.value) for f in _wi.iter_rows() for c in f if c.value is not None]
            _huecos = sorted({t.split("⟦IA:")[1].split(" ")[0] for t in _txt if "⟦IA:" in t})
            ok(_huecos == ["aplicacion", "entorno", "informacion", "modelo", "plugin", "usuario"],
               "con los huecos que rellena la aplicacion: " + ", ".join(_huecos))
            _etq = {e for e, _ in VERIFICACION + VERIFICADO + EFECTO + REVISION}
            _filas = [f for f in range(1, _wi.max_row + 1) if _wi.cell(f, 1).value in _etq]
            _llenas = [f for f in _filas if any(_wi.cell(f, c).value for c in (2, 3, 4))]
            ok(len(_filas) == 11 and not _llenas, f"los {len(_filas)} apartados del equipo salen en blanco")
            _todo = "\n".join(_txt)
            # las comprobaciones son VERDAD sobre el fixture: 7 de 9 localizados (E3 y E6 no),
            # E4 no cuadra, E2 no casa en importe, E5 fuera de la ventana
            ok("Documento localizado para 7 de 9 elementos" in _todo
               and "ATENCIÓN: 2 elemento(s) sin documento (elementos 3, 6)" in _todo
               and "Ningún documento está asignado a dos elementos" in _todo,
               "la comprobacion de localizacion dice 7 de 9 y nombra los dos sin documento con ATENCIÓN")
            ok("cuadra en 6." in _todo and "ATENCIÓN: no cuadra en 1 (elemento 4)" in _todo,
               "la aritmetica: cuadra en 6 de 7 y señala el E4 con ATENCIÓN")
            ok("casa en 6 de 7" in _todo and "ATENCIÓN: no casa en 1 (elemento 2)" in _todo,
               "el importe frente a libros: casa en 6 de 7 y señala el E2")
            ok("ATENCIÓN: fuera de ese margen en 1 (elemento 5)" in _todo,
               "la fecha: el E5 fuera de la ventana, con ATENCIÓN")
            ok("PROPUESTAS de la herramienta" in _todo and "(A1, A4)" in _todo,
               "el resultado dice que los veredictos son propuestas y que A1 y A4 quedan al auditor")
        ok("Pendiente de verificación" in str(_wb["Análisis muestra"]["B5"].value or ""),
           "y la hoja del papel dice que esta pendiente de verificacion")
    _sh.rmtree(_d, ignore_errors=True)
    _propia = _P(__file__).resolve().parent / "lib_uso_ia.py"
    _otras = [p for p in _propia.parents[2].glob("*/scripts/lib_uso_ia.py") if p.resolve() != _propia]
    ok(bool(_otras) and all(p.read_bytes() == _propia.read_bytes() for p in _otras),
       f"lib_uso_ia.py es identico en los {len(_otras) + 1} skills que lo llevan")

    _probar_dudosa(ok)
    _probar_periodo(ok)
    _probar_apartados_e_imagenes(ok)
    _probar_aislado(ok)
    _probar_alias(ok)
    _probar_culpa_numero(ok)
    _probar_tercero_del_mcp(ok)
    for _lib in ("lib_fsp.py", "preparar_documentos.py"):
        _mia = _P(__file__).resolve().parent / _lib
        _her = _P(__file__).resolve().parents[2] / "fsp-mum" / "scripts" / _lib
        if _her.exists():
            ok(_mia.read_bytes() == _her.read_bytes(), f"{_lib} es byte a byte el mismo que en fsp-mum")
        else:
            print(f"-      {_lib}: sin la copia hermana al lado, no se comprueba la deriva (normal ya instalado)")

    print()
    print("RESULTADO:", "todo correcto" if fallos == 0 else f"{fallos} fallo(s)")
    return 1 if fallos else 0


# ── Asignacion dudosa (registro del 20/10/2026) ──────────────────────────────
#
#   D1, D2  atados por numero e importe: la linea base de desfases de la muestra (1 y 0 dias)
#   D3      EL CASO DEL REGISTRO: su factura no esta; hay otra del mismo tercero, sin numero,
#           de 900 frente a 3.000 y fechada 30 dias antes -> DUDOSA, no diferencia firme
#   D4      diferencia real: mismo tercero, sin numero, 1.000 frente a 1.100 el mismo dia -> firme
#   D5      importe parecido (5 %) pero 28 dias antes, cuando lo atado no pasa de 1 -> DUDOSA por fecha
#   D6      como D3, pero atada a mano con poblacion_id -> manda el auditor, firme
MUESTRA_D = [
    {"60_ID": "10", "Fecha": "15/03/25 0:00:00", "DescripcinApunte": "OMEGA", "Saldo": "1210", "Documento": "OM-1"},
    {"60_ID": "11", "Fecha": "02/04/25 0:00:00", "DescripcinApunte": "KAPPA", "Saldo": "500", "Documento": "K-9"},
    {"60_ID": "12", "Fecha": "20/06/25 0:00:00", "DescripcinApunte": "LAMBDA", "Saldo": "3000", "Documento": "L-200"},
    {"60_ID": "13", "Fecha": "10/07/25 0:00:00", "DescripcinApunte": "MURCIA", "Saldo": "1100", "Documento": "M-7"},
    {"60_ID": "14", "Fecha": "29/08/25 0:00:00", "DescripcinApunte": "NUBIA", "Saldo": "2000", "Documento": "N-3"},
    {"60_ID": "15", "Fecha": "30/09/25 0:00:00", "DescripcinApunte": "XILO", "Saldo": "5000", "Documento": "X-1"},
]
FACTURAS_D = [
    {"fichero": "10 - OMEGA.pdf", "proveedor": "OMEGA", "numero": "OM-1", "fecha": "14/03/2025",
     "base": "1000,00", "iva": "210,00", "total": "1210,00"},
    {"fichero": "11 - KAPPA.pdf", "proveedor": "KAPPA", "numero": "K-9", "fecha": "02/04/2025",
     "base": "500,00", "iva": "0,00", "total": "500,00"},
    {"fichero": "LAMBDA otra.pdf", "proveedor": "LAMBDA", "numero": "", "fecha": "21/05/2025",
     "base": "900,00", "iva": "0,00", "total": "900,00"},
    {"fichero": "13 - MURCIA.pdf", "proveedor": "MURCIA", "numero": "", "fecha": "10/07/2025",
     "base": "1000,00", "iva": "0,00", "total": "1000,00"},
    {"fichero": "14 - NUBIA.pdf", "proveedor": "NUBIA", "numero": "", "fecha": "01/08/2025",
     "base": "2100,00", "iva": "0,00", "total": "2100,00"},
    {"fichero": "15 - XILO.pdf", "proveedor": "XILO", "numero": "", "fecha": "31/08/2025", "poblacion_id": "15",
     "base": "1000,00", "iva": "0,00", "total": "1000,00"},
]


def _probar_dudosa(ok) -> None:
    import json as _json
    import shutil as _sh
    import subprocess as _sp
    import tempfile as _tf
    from openpyxl import load_workbook as _LW
    from lib_fsp import PREFIJO_DUDOSA
    roles = proponer_roles(ATRIBUTOS)
    cols = detectar_columnas(MUESTRA_D[0])[0]
    cruce = cruzar(MUESTRA_D, FACTURAS_D, cols)
    ev = {e["fila"]["60_ID"]: e for e in evaluar(cruce, cols, ATRIBUTOS, roles)}
    d = {k: ev[k]["criterios"].get("dudosa") for k in ev}
    ok(ev["12"]["factura"]["fichero"] == "LAMBDA otra.pdf" and d["12"] and d["12"]["muy_distinto"]
       and d["12"]["lejos"],
       "D3 (el caso del registro): otra factura del mismo tercero, sin número, 900 frente a 3.000 y 30 días "
       "antes -> se asigna, pero DUDOSA por importe y por fecha")
    r12 = ev["12"]["resultados"]
    ok(all(r12[a] == "auditor" or r12[a].startswith(PREFIJO_DUDOSA) for a in r12)
       and not any("no corresponde" in v for v in r12.values()),
       "D3: ninguna celda afirma la diferencia de importe; todas dicen «Asignación dudosa» o «auditor»")
    ok("no trae número legible" in r12["2"] and "70 % distinto" in r12["2"] and "30 días antes" in r12["2"]
       and "poblacion_id" in r12["2"] and r12["3"] == f"{PREFIJO_DUDOSA} (ver A2)",
       "D3: la observación explica el porqué una vez (número, 70 %, 30 días, cómo atarlo) y el resto remite a ella")
    ok(not d["13"] and ev["13"]["resultados"]["2"].startswith("Importe en factura (1.000,00) no corresponde"),
       "D4: una diferencia real del 9 % el mismo día sigue siendo un hallazgo firme, no una duda")
    ok(d["14"] and d["14"]["lejos"] and not d["14"]["muy_distinto"] and "28 días antes" in ev["14"]["resultados"]["2"]
       and "% distinto" not in ev["14"]["resultados"]["2"],
       "D5: importe parecido pero 28 días antes, cuando lo atado no pasa de 1 -> dudosa solo por la fecha")
    ok(d["14"]["umbral_dias"] == 22, "el umbral de fecha es la media ventana (22) si lo atado por importe o número está más cerca")
    ok(not d["15"] and ev["15"]["criterios"]["declarado"] and "no corresponde" in ev["15"]["resultados"]["2"],
       "D6: atada a mano con poblacion_id no es dudosa: manda el auditor y la diferencia es firme")
    ok(not d["10"] and not d["11"], "D1, D2: lo atado por número e importe nunca es dudoso")

    # el papel: contadas aparte en la hoja, en la salida y en las comprobaciones del uso de IA
    t = Path(_tf.mkdtemp())
    params = {"MuestraId": 7, "Tipo": "Cumplimiento", "Area": "CG", "Referencia": "CG)1/0", "Prueba": "Compras 25",
              "FechaInicioAuditoria": "01/01/2025", "FechaFinAuditoria": "31/12/2025", "atributos": ATRIBUTOS,
              "parametros": {"PoblacionFechaIni": "01/01/24 0:00:00", "PoblacionFechaFin": "31/12/24 0:00:00"}}
    for n, v in (("muestra.json", MUESTRA_D), ("facturas.json", {"facturas": FACTURAS_D}),
                 ("parametros.json", params), ("roles.json", roles)):
        (t / n).write_text(_json.dumps(v, ensure_ascii=False), encoding="utf-8")
    papel = t / "papel.xlsx"
    r = _sp.run([sys.executable, str(Path(__file__).resolve().parent / "ejecutar_fsp.py"),
                 "--muestra", str(t / "muestra.json"), "--parametros", str(t / "parametros.json"),
                 "--facturas", str(t / "facturas.json"), "--roles", str(t / "roles.json"),
                 "--salida", str(papel), "--generado", "2026-10-20"],
                capture_output=True, text=True, encoding="utf-8")
    sal = r.stdout
    ok(r.returncode == 1 and "celdas con hallazgo 3 · asignaciones dudosas 2" in sal,
       "la salida cuenta aparte: 3 celdas con hallazgo (D4 dos, D6 una) y 2 asignaciones dudosas (D3, D5)")
    cuenta = sal.split("PARA CONTAR AL ENTREGAR")[-1]
    ok("ASIGNACIÓN DUDOSA, elemento 12" in cuenta and "ASIGNACIÓN DUDOSA, elemento 14" in cuenta
       and "elemento 12: A2" not in sal,
       "y las dudosas van en «PARA CONTAR AL ENTREGAR» con su rótulo, no mezcladas con los hallazgos")
    ok("A10 · " in cuenta and "NO se solapan" in cuenta,
       "E3: la población de 2024 para una prueba de 2025 sale como aviso A10, también al entregar")
    if papel.exists():
        wb = _LW(papel)
        ws = wb["Análisis muestra"]
        cab = {c.value: c.column for c in ws[7] if c.value}
        fila12 = next(f for f in range(8, ws.max_row + 1) if str(ws.cell(f, cab["60_ID"]).value) == "12")
        ok("ASIGNACIÓN DUDOSA" in str(ws.cell(fila12, cab["Casa por"]).value)
           and ws.cell(fila12, cab["Diferencia importe"]).value is None,
           "en la hoja, «Casa por» la rotula como dudosa y no se escribe diferencia de importe")
        ok("Asignaciones dudosas, contadas aparte: 2 (elementos 12, 14)" in str(ws["A4"].value),
           "y la cabecera de la hoja las cuenta aparte")
        txt = "\n".join(str(c.value) for f in wb[wb.sheetnames[0]].iter_rows() for c in f if c.value is not None)
        ok("ATENCIÓN: 2 asignación(es) dudosa(s), contadas aparte (elementos 12, 14)" in txt
           and "con asignación dudosa (elementos 12, 14) no se compara" in txt
           and "ATENCIÓN: no casa en 2 (elementos 13, 15)" in txt,
           "las comprobaciones del uso de IA las cuentan aparte, y el importe no casa solo en D4 y D6")
        ok("Aparte, 2 asignación(es) dudosa(s)" in txt, "y el resultado del uso de IA también")
    else:
        ok(False, "ejecutar_fsp no ha escrito el papel: " + (r.stdout + r.stderr)[-300:])
    _sh.rmtree(t, ignore_errors=True)


def _probar_periodo(ok) -> None:
    from lib_fsp import aviso_periodo_poblacion as _av
    base = {"FechaInicioAuditoria": "01/01/25 0:00:00", "FechaFinAuditoria": "31/12/25 0:00:00"}
    p = lambda i, f: dict(base, parametros={"PoblacionFechaIni": i, "PoblacionFechaFin": f})  # noqa: E731
    ok("NO se solapan" in _av(p("01/01/24 0:00:00", "31/12/24 0:00:00")),
       "E3: población de 2024 y prueba de 2025 -> no se solapan")
    ok("solo una parte" in _av(p("01/07/25 0:00:00", "31/12/25 0:00:00")),
       "E3: población del segundo semestre -> cubre solo una parte, y se dice")
    ok(_av(p("01/01/25 0:00:00", "31/01/26 0:00:00")) == "" and _av(base) == "",
       "E3: si la contiene, o si faltan las fechas, no hay aviso (es opcional)")


def _probar_apartados_e_imagenes(ok) -> None:
    import json as _json
    import shutil as _sh
    import subprocess as _sp
    import tempfile as _tf
    from pathlib import PurePath as _PP
    from preparar_documentos import clasificar
    nombres = ["JUSTIFICANTE REMESA 03.pdf", "ALBARAN 1234.pdf", "4 - ALBARAN 77.pdf",
               "5 - Y FRA 9.pdf", "5 - Y ALBARAN 9.pdf", "Z FRA 1.pdf"]
    fac, ap = clasificar([_PP(n) for n in nombres])
    fac, ap = [x.name for x in fac], [x.name for x in ap]
    ok(sorted(ap) == ["5 - Y ALBARAN 9.pdf", "ALBARAN 1234.pdf", "JUSTIFICANTE REMESA 03.pdf"],
       "C7: se aparta lo marcado SIN prefijo numérico (justificante, albarán) y el albarán con factura en su grupo")
    ok("4 - ALBARAN 77.pdf" in fac and "Z FRA 1.pdf" in fac,
       "C7: y no se aparta el marcado que es el único de su elemento numerado, ni lo que no lleva marca")
    fac2, ap2 = clasificar([_PP(n) for n in nombres], {"ALBARAN 1234.pdf"})
    ok("ALBARAN 1234.pdf" in [x.name for x in fac2] and len(ap2) == 2,
       "C7: lo pedido por su nombre (--incluir) se recupera: es la salida de un falso positivo")
    try:
        from PIL import Image
    except ImportError:
        print("-      imágenes sueltas: sin Pillow no se fabrica el fixture (no se comprueba)")
        return
    car, tra = Path(_tf.mkdtemp()), Path(_tf.mkdtemp())
    Image.new("RGB", (2000, 2800), "white").save(car / "1 - A FRA.jpg")
    Image.new("RGB", (900, 1200), "white").save(car / "2 - B FRA.jfif", format="JPEG")
    Image.new("RGBA", (800, 1100), "white").save(car / "3 - C FRA.png")
    Image.new("RGB", (800, 1100), "white").save(car / "4 - D FRA.tif", save_all=True,
                                                append_images=[Image.new("RGB", (800, 1100), "white")])
    Image.new("RGB", (800, 1100), "white").save(car / "ALBARAN 5.jpg")
    (car / "nota.txt").write_text("x", encoding="utf-8")
    script = str(Path(__file__).resolve().parent / "preparar_documentos.py")
    r = _sp.run([sys.executable, script, "--carpeta", str(car), "--trabajo", str(tra)],
                capture_output=True, text=True, encoding="utf-8")
    man = _json.loads((tra / "manifiesto.json").read_text(encoding="utf-8")) if (tra / "manifiesto.json").exists() else {}
    docs = man.get("documentos") or []
    ok(r.returncode == 1 and len(docs) == 4 and all(d["paginas"] == 1 for d in docs),
       "C7: una carpeta SOLO de imágenes (JPG, JFIF, PNG, TIF) se inventaría: cuatro documentos de una página")
    _ap = man.get("apartados") or []
    ok(len(_ap) == 1 and _ap[0].startswith("ALBAR DOC ") and _ap[0].endswith("-a01.jpg")
       and any(x.startswith("DOC ") and ".txt" in x and "nota" not in x for x in man.get("no_reconocidos") or []),
       "C7: la imagen marcada como albarán se aparta y el .txt se lista como no reconocido, los dos por su alias")
    imgs = [Path(i) for d in docs for i in d["imagenes"]]
    tams = [Image.open(i).size for i in imgs if i.exists()]
    ok(len(tams) == 4 and all(max(t) <= 1170 for t in tams),
       "C7: cada imagen queda como su página 1, con el lado mayor a escala de un A4 a 100 ppp")
    ok("solo se ha preparado la primera" in r.stdout and "--incluir" in r.stdout,
       "C7: el TIF de dos páginas se avisa, y el apartado dice cómo recuperarlo")
    tra2 = Path(_tf.mkdtemp())
    r2 = _sp.run([sys.executable, script, "--carpeta", str(car), "--trabajo", str(tra2), "--incluir", "ALBARAN 5.jpg"],
                 capture_output=True, text=True, encoding="utf-8")
    man2 = _json.loads((tra2 / "manifiesto.json").read_text(encoding="utf-8")) if (tra2 / "manifiesto.json").exists() else {}
    ok(len(man2.get("documentos") or []) == 5 and not man2.get("apartados"),
       "C7: con --incluir el albarán vuelve a la lista de documentos")
    for x in (car, tra, tra2):
        _sh.rmtree(x, ignore_errors=True)


def _probar_alias(ok) -> None:
    """Los nombres de fichero no salen del equipo (registro del 21/10/2026, MCP 1.26.0).

    Con --carpeta los nombres son reales: lo impreso y los lotes del lector llevan el alias, el id
    y el numero de elemento, nunca el nombre; los ids son estables entre pasadas; --incluir y
    --ampliar admiten alias o id; la fusion acepta el id a secas; y el papel recupera el nombre
    real (texto y vinculo) del manifiesto local, mientras que con el del MCP enlaza
    <carpeta>/<alias> y lo deja a rehidratar.
    """
    import json as _json
    import shutil as _sh
    import subprocess as _sp
    import tempfile as _tf
    from pathlib import PurePath as _PP
    import preparar_documentos as _pd
    import lib_fsp as _lf
    ok(_pd.alias_doc("3fa2", "f07", "12 RAZON SOCIAL SL.pdf") == "12 - DOC 3fa2-f07.pdf"
       and _pd.alias_doc("3fa2", "f01", "RAZON SOCIAL SL.PDF") == "DOC 3fa2-f01.pdf"
       and _pd.alias_doc("3fa2", "a01", "4 - X JUSTIFICANTE.pdf", "JUSTIFICANTE") == "4 - JUSTIFICANTE DOC 3fa2-a01.pdf"
       and _pd.alias_doc("3fa2", "a02", "PAGO 1.pdf", "PAGO 1") == "PAGO_1 DOC 3fa2-a02.pdf",
       "A1: el alias es el del MCP 1.26.0: «<prefijo> - [MARCA ]DOC <lote>-<id><ext>», sin una letra del nombre")
    ok(_pd._grupo("12 - DOC 3fa2-f07.pdf") == "12" and _pd.prefijo_de("12 - DOC 3fa2-f07.pdf") == "12"
       and _pd.prefijo_de("DOC 3fa2-f01.pdf") == "" and _pd.id_de_clave("12 - DOC 3fa2-f07.pdf") == "f07"
       and _pd.id_de_clave("F07") == "f07" and _pd.id_de_clave("12 X.pdf") == "",
       "A1: el alias conserva el grupo del elemento (_grupo, prefijo) y de él sale el id")
    _fac, _ap = _pd.clasificar([_PP(n) for n in ("TODOS.pdf", "FACTURAS TODAS 2025.pdf", "1 - A.pdf",
                                                  "3 - B TODOS.pdf")])
    ok(sorted(x.name for x in _ap) == ["FACTURAS TODAS 2025.pdf", "TODOS.pdf"]
       and "3 - B TODOS.pdf" in [x.name for x in _fac],
       "A2: un «… TODOS.pdf» recopilatorio sin prefijo se aparta; numerado y único de su elemento, no")
    try:
        from PIL import Image
    except ImportError:
        print("-      alias con --carpeta: sin Pillow no se fabrica el fixture (no se comprueba)")
        return
    car, tra = Path(_tf.mkdtemp()), Path(_tf.mkdtemp())
    (car / "sub").mkdir()
    for n in ("12 RAZON ALFA SL.jpg", "7 RAZON BETA SA.png", "sub/RAZON GAMMA.jpg", "JUSTIFICANTE RAZON DELTA.jpg"):
        Image.new("RGB", (800, 1100), "white").save(car / n)
    (car / "RAZON EPSILON.docx").write_bytes(b"x")
    script = str(Path(__file__).resolve().parent / "preparar_documentos.py")

    def corre(*a):
        return _sp.run([sys.executable, script, "--trabajo", str(tra)] + list(a),
                       capture_output=True, text=True, encoding="utf-8")
    r = corre("--carpeta", str(car))
    man = _json.loads((tra / "manifiesto.json").read_text(encoding="utf-8"))
    docs = {d["id"]: d for d in man["documentos"]}
    ok("RAZON" not in r.stdout and len(docs) == 3
       and all(_pd.RE_ALIAS.fullmatch(d["fichero"]) for d in docs.values())
       and sorted(_pd.prefijo_de(d["fichero"]) for d in docs.values()) == ["", "12", "7"],
       "A3: con --carpeta lo impreso no lleva ningún nombre real y cada documento va por su alias, con su prefijo")
    ok(man.get("origen") == "local" and "sub/RAZON GAMMA.jpg" in man["reales"].values()
       and all("RAZON" not in x for x in man["apartados"] + man["no_reconocidos"]),
       "A3: el nombre real se queda en el manifiesto local (reales); apartados y no reconocidos van por alias")
    r = corre("--lotes", "10")
    lotes = _json.loads((tra / "lotes.json").read_text(encoding="utf-8"))
    claves = {k for lt in lotes for d in lt["documentos"] for k in d}
    ok("RAZON" not in r.stdout and "RAZON" not in (tra / "lotes.json").read_text(encoding="utf-8")
       and claves == {"fichero", "id", "prefijo", "imagenes", "paginas"},
       "A4: los lotes del lector (lotes.json y lo impreso) llevan alias, id, prefijo e imágenes; ni ruta ni nombre")
    ap_id = _pd.id_de_clave(man["apartados"][0])
    ids_antes = {d["fichero"]: d["id"] for d in docs.values()}
    r = corre("--carpeta", str(car), "--incluir", ap_id)
    man2 = _json.loads((tra / "manifiesto.json").read_text(encoding="utf-8"))
    ok(len(man2["documentos"]) == 4 and not man2["apartados"] and ap_id in {d["id"] for d in man2["documentos"]}
       and all(ids_antes.get(d["fichero"], d["id"]) == d["id"] for d in man2["documentos"])
       and "RAZON" not in r.stdout,
       "A5: --incluir por id recupera el apartado con su id «a», y los demás conservan el suyo (ids estables)")
    f1, f2 = sorted(docs)[:2]
    (tra / "facturas_lote_1.json").write_text(_json.dumps({"facturas": [
        {"fichero": f1, "total": "1,00"}, {"fichero": docs[f2]["fichero"], "total": "2,00"}]}), encoding="utf-8")
    r = corre("--fusionar")
    fac = _json.loads((tra / "facturas.json").read_text(encoding="utf-8"))["facturas"]
    ok(sorted(x["fichero"] for x in fac) == sorted([docs[f1]["fichero"], docs[f2]["fichero"]])
       and "RAZON" not in r.stdout,
       "A6: la fusión acepta el id a secas y lo deja por su alias; nada de lo impreso lleva el nombre")
    r = corre("--estado")
    ok("Transcritos 2 de 4" in r.stdout and "RAZON" not in r.stdout, "A6: --estado cuenta por alias o id")
    r = corre("--ampliar", f1)
    ok(r.returncode == 0 and "imagen suelta" in r.stdout and "RAZON" not in r.stdout,
       "A7: --ampliar admite el id, y no nombra el fichero real")
    # el papel: con el manifiesto local, el texto recupera el nombre real y el vinculo va al fichero real
    rutas = _lf.rutas_documentos(str(tra / "manifiesto.json"), None)
    ok(rutas.get(docs[f1]["fichero"]) == docs[f1]["ruta"] and Path(docs[f1]["ruta"]).name == Path(man["reales"][f1]).name,
       "A8: manifiesto local: el vínculo va a la ruta real del documento")
    rc = _lf.rutas_documentos(str(tra / "manifiesto.json"), "C:\\Docs")
    gam = next(i for i, x in man["reales"].items() if x == "sub/RAZON GAMMA.jpg")
    ok(rc.get(docs[gam]["fichero"]) == "C:\\Docs\\sub\\RAZON GAMMA.jpg",
       "A8: y con --carpeta-documentos, a la ruta real relativa dentro de esa carpeta, con su separador")
    from openpyxl import Workbook as _WB
    wb = _WB()
    wb.active["A1"] = f"Ok (localizada por importe: {docs[f1]['fichero']})"
    n = _lf.rehidratar_local(wb, _lf.nombres_locales(_json.loads((tra / "manifiesto.json").read_text(encoding="utf-8"))))
    ok(n == 1 and wb.active["A1"].value == f"Ok (localizada por importe: {Path(man['reales'][f1]).name})",
       "A8: el papel escrito con un manifiesto local recupera el nombre real en el texto")
    # con el manifiesto del MCP (sin ruta), el vinculo es <carpeta>\<alias> y lo arregla rehidratar
    tm = Path(_tf.mkdtemp())
    (tm / "manifiesto.json").write_text(_json.dumps({"carpeta": "C:\\Exp\\Docs", "lote": "3fa2", "origen": "mcp",
        "documentos": [{"id": "f07", "fichero": "12 - DOC 3fa2-f07.pdf", "paginas": 1, "imagenes": ["f07_p1.jpg"]}]}),
        encoding="utf-8")
    ok(_lf.rutas_documentos(str(tm / "manifiesto.json"), None) == {"12 - DOC 3fa2-f07.pdf": "C:\\Exp\\Docs\\12 - DOC 3fa2-f07.pdf"}
       and _lf.rutas_documentos(str(tm / "manifiesto.json"), "D:\\Otra") == {"12 - DOC 3fa2-f07.pdf": "D:\\Otra\\12 - DOC 3fa2-f07.pdf"}
       and _lf.nombres_locales(_json.loads((tm / "manifiesto.json").read_text(encoding="utf-8"))) == {},
       "A9: manifiesto del MCP sin ruta: el vínculo es <carpeta>\\<alias> (lo arregla rehidratar) y el texto no se toca")
    (tm / "manifiesto.json").write_text(_json.dumps({"origen": "mcp", "documentos": [
        {"id": "f01", "fichero": "12 RAZON ALFA SL.pdf", "imagenes": []}]}), encoding="utf-8")
    ok("anterior a la 1.26.0" in _pd._aviso_nombres_reales(_pd._leer_manifiesto(tm)),
       "A10: un manifiesto del MCP con nombres reales (anterior a la 1.26.0) se avisa")
    # c): el papel entero con el manifiesto del MCP y --carpeta-documentos: sin el aviso de
    # «rutas que este proceso no ve» (la carpeta la ha dado el auditor) y con el vinculo por alias
    al = {f["fichero"]: _pd.alias_doc("3fa2", f"f{i:02d}", f["fichero"]) for i, f in enumerate(FACTURAS, 1)}
    (tm / "facturas").mkdir()
    (tm / "manifiesto.json").unlink()
    (tm / "facturas" / "manifiesto.json").write_text(_json.dumps({"carpeta": "C:\\Exp\\Docs", "lote": "3fa2",
        "origen": "mcp", "modo": "tachadas", "documentos": [{"id": f"f{i:02d}", "fichero": a, "paginas": 1,
                                                              "imagenes": []} for i, a in enumerate(al.values(), 1)]}),
        encoding="utf-8")
    for n, v in (("muestra.json", MUESTRA), ("facturas.json", {"facturas": [dict(f, fichero=al[f["fichero"]]) for f in FACTURAS]}),
                 ("parametros.json", {"MuestraId": 9, "Tipo": "Cumplimiento", "Prueba": "Compras 25", "atributos": ATRIBUTOS}),
                 ("roles.json", proponer_roles(ATRIBUTOS))):
        (tm / n).write_text(_json.dumps(v, ensure_ascii=False), encoding="utf-8")
    r = _sp.run([sys.executable, str(Path(__file__).resolve().parent / "generar_papel.py"),
                 "--muestra", str(tm / "muestra.json"), "--parametros", str(tm / "parametros.json"),
                 "--facturas", str(tm / "facturas.json"), "--roles", str(tm / "roles.json"),
                 "--manifiesto", str(tm / "manifiesto.json"), "--carpeta-documentos", "D:\\Docs",
                 "--salida", str(tm / "papel.xlsx"), "--generado", "2026-10-21"],
                capture_output=True, text=True, encoding="utf-8")
    ok(r.returncode == 0 and "AVISO" not in r.stdout and "por el alias" in r.stdout,
       "c): con --carpeta-documentos no sale el aviso de «rutas que este proceso no ve»; el vínculo va por alias")
    for x in (car, tra, tm):
        _sh.rmtree(x, ignore_errors=True)


def _probar_culpa_numero(ok) -> None:
    """A07: el numero ilegible no se atribuye al escaneo (registro del 21/10/2026). El MCP mide
    que el tachado no tape fechas ni importes, pero el numero no; y si el lector anota que lo
    tapo el tachado, se dice."""
    import json as _json
    import shutil as _sh
    import tempfile as _tf
    from verificar_contrato import _culpa_del_tachado
    d = Path(_tf.mkdtemp())
    (d / "facturas").mkdir()
    fj = d / "facturas.json"
    fj.write_text("[]", encoding="utf-8")
    man = {"origen": "mcp", "documentos": [
        {"id": "f01", "fichero": "1 - DOC 3fa2-f01.pdf", "tachado": {"datos_tapados": 0, "numero_conservado": 0}},
        {"id": "f02", "fichero": "2 - DOC 3fa2-f02.pdf", "tachado": {"datos_tapados": 0, "numero_conservado": 1}}],
        "numeros_no_encontrados": ["A-1"]}
    (d / "facturas" / "manifiesto.json").write_text(_json.dumps(man), encoding="utf-8")
    sin_num = [{"fichero": "1 - DOC 3fa2-f01.pdf", "notas": "número tapado por el tachado"},
               {"fichero": "f02", "notas": ""}]
    t = _culpa_del_tachado(str(fj), "numero", sin_num)
    ok("escaneo" not in t and "el número no" in t and "1 de ellos" in t and "lector" in t and "A-1" in t,
       "A07: sin número legible no se culpa al escaneo: el número no se comprueba, se dice la nota del "
       "lector, el número conservado y numeros_no_encontrados")
    t2 = _culpa_del_tachado(str(fj), "fecha", [{"fichero": "f02", "notas": ""}])
    ok("escaneo" in t2 and "NO es una incidencia" in t2,
       "A08: sin fecha legible y sin datos tapados, sí se dice que no es del tachado")
    t3 = _culpa_del_tachado(str(fj), "fecha", [{"fichero": "f01", "notas": "fecha tapada por el tachado"}])
    ok("lector" in t3 and "es del escaneo" not in t3,
       "A08: pero si el lector anota que el tachado la tapó, no se afirma que sea del escaneo")
    _sh.rmtree(d, ignore_errors=True)


def _probar_tercero_del_mcp(ok) -> None:
    """A00: el cambio a la columna de tercero que eligio el MCP es informativo (registro del
    21/10/2026). El MCP descarto 'NombreCuenta' por tener un solo valor, y el contrato lo contaba
    como aviso con otro motivo. Ahora es una linea C02, no llega a «PARA CONTAR» y, si era el unico
    aviso, el contrato sale con 0. Un cambio que decide el skill, sin tokens de cuenta, sigue en A00."""
    import contextlib as _cl
    import io as _io
    import json as _json
    import shutil as _sh
    import tempfile as _tf
    import verificar_contrato as _vc
    from ejecutar_fsp import _para_el_usuario
    # muestra tokenizada como la exporta el MCP: el tercero en 'Proveedor' con token de cuenta y
    # 'NombreCuenta' con un solo token de reserva en todas las filas
    muestra = [{"60_ID": str(i), "Fecha": f"0{i}/03/25 0:00:00", "Cuenta": "62300000",
                "NombreCuenta": "TER h1a2b3c", "Proveedor": f"PROV 40000000{i}",
                "Saldo": f"{i}00,00", "Factura": f"F-{i}"} for i in range(1, 6)]
    facturas = [{"fichero": f"{i} - F-{i}.pdf", "proveedor": f"PROV 40000000{i}", "numero": f"F-{i}",
                 "fecha": f"0{i}/03/2025", "base": f"{i}00,00", "iva": "0,00", "total": f"{i}00,00"}
                for i in range(1, 6)]
    params = {"MuestraId": "1", "Prueba": "Servicios", "Tipo": "Cumplimiento", "atributos": ATRIBUTOS}
    d = Path(_tf.mkdtemp())

    def correr(filas):
        for n, v in (("muestra.json", filas), ("facturas.json", facturas), ("parametros.json", params),
                     ("roles.json", proponer_roles(ATRIBUTOS))):
            (d / n).write_text(_json.dumps(v, ensure_ascii=False), encoding="utf-8")
        sys.argv = ["verificar_contrato.py"] + [x for n in ("muestra", "parametros", "facturas", "roles")
                                                for x in ("--" + n, str(d / f"{n}.json"))]
        buf = _io.StringIO()
        with _cl.redirect_stdout(buf):
            cod = _vc.main()
        out = buf.getvalue()
        buf2 = _io.StringIO()
        with _cl.redirect_stdout(buf2):
            _para_el_usuario(out, "")
        return cod, out, buf2.getvalue()

    argv = list(sys.argv)
    try:
        cod, out, contar = correr(muestra)
        ok(cod == 0 and "A00" not in out and "C02 · tercero = «Proveedor»" in out
           and "«NombreCuenta» no sirve para cruzar el tercero: tiene un solo valor en las 5 filas" in out,
           "A00: el cambio a la columna del MCP sale como línea C02 con el motivo real (un solo valor), "
           "no como aviso, y el contrato sale con 0")
        ok("NombreCuenta" not in contar and "sin avisos ni hallazgos" in contar,
           "y no llega a «PARA CONTAR AL ENTREGAR»")
        # 'NombreCuenta' con varios tokens de reserva distintos: el motivo es otro
        varios = [dict(f, NombreCuenta=f"TER h00000{f['60_ID']}") for f in muestra]
        cod, out, _ = correr(varios)
        ok(cod == 0 and "A00" not in out and "solo lleva tokens de reserva" in out,
           "y con varios tokens de reserva en 'NombreCuenta' el motivo es que no atan a ningún tercero")
        # sin tokens de cuenta el cambio lo decide el skill: sigue siendo aviso
        en_claro = [dict(f, NombreCuenta="SERVICIOS", Proveedor=f"PROVEEDOR {f['60_ID']}") for f in muestra]
        cod, out, contar = correr(en_claro)
        ok(cod == 1 and "A00 · la columna de tercero pasa de «NombreCuenta» a «Proveedor»" in out
           and "C02 · tercero =" not in out and "A00" in contar,
           "un cambio de columna sin tokens de cuenta lo decide el skill: sigue siendo A00 y se cuenta")
    finally:
        sys.argv = argv
        _sh.rmtree(d, ignore_errors=True)


def _probar_aislado(ok) -> None:
    """C1: cada script arranca con `python -I` desde otra carpeta (sin la suya en la ruta)."""
    import subprocess as _sp
    import tempfile as _tf
    aqui = Path(__file__).resolve().parent
    fuera = _tf.mkdtemp()
    malos = []
    for s in sorted(aqui.glob("*.py")):
        if s.name.startswith("probar_"):
            continue
        r = _sp.run([sys.executable, "-I", str(s), "--help"], cwd=fuera, capture_output=True,
                    text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            malos.append(f"{s.name}: {(r.stderr or r.stdout).strip().splitlines()[-1:]}")
    ok(not malos, "C1: todos los scripts arrancan con python -I desde otra carpeta"
       + (" — fallan: " + "; ".join(malos) if malos else ""))
    Path(fuera).rmdir()


if __name__ == "__main__":
    sys.exit(main())
