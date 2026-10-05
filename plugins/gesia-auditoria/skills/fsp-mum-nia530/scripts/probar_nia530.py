# -*- coding: utf-8 -*-
"""Arnes de fsp-mum-nia530. No necesita ForSampling, ni Gesia, ni el API.

Un juego de exportaciones SINTETICAS con la forma exacta que devuelve el MCP 1.23.0 -medida el
30/09/2026 sobre una prueba MUM real-: `pruebas`, `parametros` con su `descodificado`, `resumen` con el
cuadre .smp/.pcu y el desglose por grupo, `muestra` y `evaluacion` tokenizadas. Con eso se pasa
el constructor y el generador de punta a punta y se comprueba lo que no puede romperse:

  * ningun nombre de tercero llega al Word: solo tokens, y una muestra sin tokenizar PARA
  * las unidades MUM son la suma de Repeticiones, y los elementos distintos otra cosa
  * el error tolerable definido por TASA se convierte en importe y SE DICE
  * lo que no esta en ninguna fuente sale como PENDIENTE con quien lo aporta
  * los errores por exceso y por defecto no se netean; la proyeccion se cita, no se calcula

    python probar_nia530.py        ->  0 si todo va bien, 1 si algo falla
"""

from __future__ import annotations

import io
import json
import os
import re
import subprocess
import sys
import tempfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

from generar_nia530 import comprobar, eur, pct, generar  # noqa: E402


def _json(ruta, obj):
    io.open(ruta, "w", encoding="utf-8").write(json.dumps(obj, ensure_ascii=False))


def _run(script, *args):
    r = subprocess.run([sys.executable, os.path.join(AQUI, script), *args],
                       capture_output=True, text=True, encoding="utf-8")
    return r.returncode, (r.stdout or "") + (r.stderr or "")


def fixture(d: str, tokenizada: bool = True, con_ctx: bool = True) -> dict:
    """Las exportaciones de una MUM inventada de 6 elementos (7 unidades)."""
    tok = (lambda i: f"PROV 4000{i:04d}") if tokenizada else (lambda i: f"Proveedor Inventado {i}, S.L.")
    filas = []
    for i, (fecha, saldo, rep) in enumerate([("15/03/2025 0:00:00", "1.200,00", "1"), ("02/01/2025 0:00:00", "195.771,69", "2"),
                                             ("20/07/2025 0:00:00", "800,00", "1"), ("05/05/2025 0:00:00", "50,10", "1"),
                                             ("11/11/2025 0:00:00", "9.999,99", "1"), ("30/12/2025 0:00:00", "12,00", "1")], start=1):
        filas.append({"Diario_25_ID": str(1000 + i), "Seleccionado": "True", "Repeticiones": rep, "FECHA": fecha,
                      "ASIENTO": str(100 + i), "APUNTE": "1", "CTA1": "6", "CTA2": "60", "CUENTA": "60000000" if i != 3 else "60700000",
                      "NOMBRE": tok(i), "CONCEPTO": "Fra. nº 1", "DEBE": saldo, "HABER": "0", "SALDO": saldo})
    _json(f"{d}/muestra.json", filas)
    _json(f"{d}/evaluacion.json", [dict(f, SaldoAuditoria=f["SALDO"], ErrorAuditoria="450,00" if f["Diario_25_ID"] == "1002" else "0",
                                         ErrorAuditoriaTasa="0") for f in filas])
    _json(f"{d}/pruebas.json", [{"MuestraId": "57", "Ejercicio": "2025", "Prueba": "Mum de Compras", "Tipo": "MUM", "Area": "CO",
                                 "Referencia": "CO)1", "PruebaFinalizada": "False", "Realizado": "True", "Verificado": "False",
                                 "FechaInicioAuditoria": "01/01/25 0:00:00", "FechaFinAuditoria": "31/12/25 0:00:00",
                                 "Objetivo": "", "Observaciones": "Comprobar el importe de las compras.", "Poblacion": "SesionesImportacion\\x.smp",
                                 "FicheroPrueba": "C:\\x\\PruebasMuestreo\\PSU_1.pcu", "FicheroExiste": True}])
    _json(f"{d}/parametros.json", {
        "MuestraId": "57", "Prueba": "Mum de Compras", "Tipo": "MUM", "fichero_parametros": "C:\\x\\Cliente.cli",
        "fichero_prueba": "C:\\x\\PruebasMuestreo\\PSU_1.pcu", "tabla_parametros": "DatosPSMum",
        "terceros": "esta entidad no lleva nombres de terceros",
        "parametros": {"MuestraId": "57", "PoblacionDescripcion": "Mayor de la 60", "UnidadMuestreo": "Facturas",
                       "PoblacionNumElementos": "6255", "PoblacionNumErrores": "0", "PoblacionTasaErrores": "0",
                       "RiesgoGeneralId": "10", "ErrorTolerableValor": "0", "ErrorTolerableTasa": "6,5", "ErrorTolerableIndicador": "2",
                       "CriterioSelId": "3", "TamanoMuestraDeseado": "7", "MetodoSelId": "3", "CoefETGesia": ""},
        "descodificado": {"riesgo_general": {"riesgo_general_pct": 10, "confianza_pct": 90, "tipo_trabajo": "Normal",
                                             "factor_confianza": "2,30", "fuente": "TM_Confianza"},
                          "criterio_seleccion": "Proporcional al tamaño (PPT)", "metodo_seleccion": "Aleatorio",
                          "error_tolerable_definido_por": "tasa",
                          "factor_lambda": {"errores_esperados": 0, "error_aceptado_pct": 10, "valor": "2,31", "fuente": "TM_Lambda"},
                          "factor_nota": "ForSampling no guarda qué factor aplica."},
        "atributos": []})
    _json(f"{d}/resumen.json", {
        "MuestraId": "57", "Prueba": "Mum de Compras", "Tipo": "MUM", "fichero_prueba": "C:\\x\\PruebasMuestreo\\PSU_1.pcu",
        "tabla_poblacion": "Diario_25", "elementos": "6255", "seleccionados": "6", "selecciones": "7", "con_repeticion": "1",
        "importe_total": "10784005,52", "importe_seleccionado": "207833,78", "campo_importe": "SALDO", "intervalo_muestreo": 1540572.22,
        "cobertura_pct": 1.93, "importe_maximo": "195771,69",
        "cuadre_importacion": {"fichero_importacion": "C:\\x\\SesionesImportacion\\x.smp", "existe": True,
                               "elementos_importacion": "6255", "importe_importacion": "10784005,5200001",
                               "elementos_prueba": "6255", "importe_prueba": "10784005,52", "cuadra": True},
        "resultados_proyeccion": "ForSampling NO los guarda en ningún fichero.",
        "por_grupo": [{"grupo": "60", "elementos": "6000", "seleccionados": "5", "importe": "10000000,00"},
                      {"grupo": "62", "elementos": "255", "seleccionados": "0", "importe": "784005,52"}]})
    if con_ctx:
        _json(f"{d}/contexto.json", {"RazonSocialCliente": "CLIENTE DE PRUEBA, S.L.", "FechaCierre": "31/12/2025 0:00:00",
                                     "IR_P": "150000", "IR_T": "120000", "IR_I": "60000", "areas": []})
    return {"muestra": f"{d}/muestra.json", "evaluacion": f"{d}/evaluacion.json", "pruebas": f"{d}/pruebas.json",
            "parametros": f"{d}/parametros.json", "resumen": f"{d}/resumen.json", "contexto": f"{d}/contexto.json" if con_ctx else None}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    fallos = 0
    pruebas = []
    with tempfile.TemporaryDirectory() as d:
        fx = fixture(d)
        args = ["--id", "57", "--pruebas", fx["pruebas"], "--parametros", fx["parametros"], "--resumen", fx["resumen"],
                "--muestra", fx["muestra"], "--evaluacion", fx["evaluacion"], "--contexto", fx["contexto"], "--salida", f"{d}/nia530.json"]
        rc, out = _run("construir_nia530.py", *args)
        S = json.load(io.open(f"{d}/nia530.json", encoding="utf-8")) if os.path.exists(f"{d}/nia530.json") else {}
        E = S.get("elementos") or []
        P = S.get("p") or {}
        rc_g, out_g = _run("generar_nia530.py", "--datos", f"{d}/nia530.json", "--generado", "30/09/2026", "--salida", f"{d}/papel.docx")
        txt = ""
        if os.path.exists(f"{d}/papel.docx"):
            from docx import Document
            doc = Document(f"{d}/papel.docx")
            txt = "\n".join(p.text for p in doc.paragraphs) + "\n".join(c.text for t in doc.tables for r in t.rows for c in r.cells)

        pruebas += [
            ("el constructor termina con avisos (1), no con error: falta fsp-mum, y dice que la proyección no se guarda",
             rc == 1 and "sin ejecución de fsp-mum" in out and "no se guarda en ForSampling" in out),
            ("con contexto de Gesia el modo es 'completo', con la razón social, el cierre y la IR",
             S.get("modo") == "completo" and S.get("entidad") == "CLIENTE DE PRUEBA, S.L." and S.get("cierre") == "31/12/2025"
             and (P.get("ir") or {}).get("t") == 120000.0),
            ("LAS UNIDADES MUM son la suma de Repeticiones (7) y los elementos distintos otra cosa (6)",
             sum(e["unidades"] for e in E) == 7 and len(E) == 6 and P["tam"] == {"propuesto": 7, "seleccionado": 7, "unicos": 6}),
            ("el tercero de cada elemento es su TOKEN, leído de la columna tokenizada, y el nombre no aparece",
             all(re.match(r"^PROV \d+$", e["token"]) for e in E) and "Inventado" not in json.dumps(S)),
            ("el error del auditor se casa por el _ID: 450,00 en el 1002 y 0 en los demás",
             next(e for e in E if e["id"] == "1002")["error_auditor"] == 450.0
             and all(e["error_auditor"] == 0.0 for e in E if e["id"] != "1002")),
            ("sin fsp-mum, importe según documento y error van a null, no a cero",
             all(e["doc"] is None and e["error"] is None and not e["sin_documento"] for e in E)),
            ("los elementos van ordenados por FECHA de verdad, no por el texto dd/mm: enero antes que marzo",
             [e["id"] for e in E][:2] == ["1002", "1001"] and E[-1]["fecha"] == "30/12/2025"),
            ("el error tolerable definido por TASA se convierte en importe (6,5 % de 10.784.005,52) y se avisa",
             P["et"] == 700960.36 and "definido por TASA" in out and P["tp"] == 6.5),
            ("la confianza, el método y los DOS factores salen del bloque descodificado; la distribución queda null",
             P["confianza"] == 90 and P["metodo"] == "Aleatorio" and "2,31" in P["factor"] and "2,30" in P["factor"]
             and P["distribucion"] is None),
            ("el cuadre .smp/.pcu se lee del resumen y la frase no rompe el «.smp» al formatear los números",
             S["cuadre"]["ok"] is True and ".smp" in S["cuadre"]["texto"] and "6.255 filas" in S["cuadre"]["texto"]),
            ("las cuentas sin elemento seleccionado salen del desglose por grupo (la 62, 784.005,52)",
             S["sin_elementos"] == [{"cuenta": "62", "importe": 784005.52}]),
            ("el estado de la prueba se lee tal cual: no finalizada, realizada, no verificada",
             S["estado"] == {"finalizada": False, "realizado": True, "verificado": False}),
            ("el generador escribe el Word y cuenta lo que falta",
             rc_g == 0 and os.path.exists(f"{d}/papel.docx") and "datos que faltan" in out_g),
            ("en el Word hay 6 tokens, ningún nombre, y los apartados sin dato salen como PENDIENTE",
             txt.count("PROV 4000") >= 6 and "Inventado" not in txt and "PENDIENTE (AU)" in txt),
            ("EL PDF NO ES FUENTE: el apartado 8 dice que la proyección no se guarda y remite al informe emitido, sin una cifra",
             "no la guarda en ningún fichero" in txt and "se adjunta como anexo" in txt
             and not re.search(r"\d", txt.split("8. Proyección")[1].split("Conclusión del auditor")[0].replace("apartado 7", "").replace("apartados 14 y 15", ""))),
            ("la distribución no se inventa: sale como «no se guarda en los ficheros de ForSampling»",
             "No se guarda en los ficheros de ForSampling" in txt),
        ]

        # sin contexto: modo solo_fs
        fx2 = fixture(d + "/b", con_ctx=False) if os.makedirs(d + "/b", exist_ok=True) is None else None
        rc2, out2 = _run("construir_nia530.py", "--id", "57", "--pruebas", fx2["pruebas"], "--parametros", fx2["parametros"],
                         "--resumen", fx2["resumen"], "--muestra", fx2["muestra"], "--evaluacion", fx2["evaluacion"], "--salida", f"{d}/b/n.json")
        S2 = json.load(io.open(f"{d}/b/n.json", encoding="utf-8")) if os.path.exists(f"{d}/b/n.json") else {}
        pruebas.append(("sin expediente de Gesia el modo es 'solo_fs' y lo de Gesia va a null, no se inventa",
                        S2.get("modo") == "solo_fs" and S2.get("entidad") is None and S2.get("cierre") is None and S2["p"]["ir"] is None))

        # muestra SIN tokenizar: se para
        os.makedirs(d + "/c", exist_ok=True)
        fx3 = fixture(d + "/c", tokenizada=False)
        rc3, out3 = _run("construir_nia530.py", "--id", "57", "--pruebas", fx3["pruebas"], "--parametros", fx3["parametros"],
                         "--resumen", fx3["resumen"], "--muestra", fx3["muestra"], "--evaluacion", fx3["evaluacion"], "--salida", f"{d}/c/n.json")
        pruebas.append(("UNA MUESTRA SIN TOKENIZAR PARA EL SKILL (salida 2) y manda volver a configurar con perfil",
                        rc3 == 2 and "NO está tokenizada" in out3 and not os.path.exists(f"{d}/c/n.json")))

    # puras, del generador
    pruebas += [
        ("eur y pct formatean a la española y devuelven «—» sin dato",
         eur(1234567.891) == "1.234.567,89" and eur(-5) == "−5,00" and eur(None) == "—" and pct(12.7) == "12,70 %" and pct(None) == "—"),
        ("comprobar() caza las unidades que no suman el tamaño y un tercero que no es token, y «Proveedor X» NO pasa por PROV",
         (lambda f: len(f) == 2 and any("unidades" in x for x in f) and any("no es un token" in x for x in f))(
             comprobar({"elementos": [{"id": 1, "unidades": 1, "token": "PROV 1"}, {"id": 2, "unidades": 1, "token": "Proveedor Real, S.A."}],
                        "p": {"tam": {"seleccionado": 3, "unicos": 2}}}))),
        ("comprobar() no protesta cuando todo cuadra",
         comprobar({"elementos": [{"id": 1, "unidades": 2, "token": "TER h1"}, {"id": 2, "unidades": 1, "token": "CLI 43000001"}],
                    "p": {"tam": {"seleccionado": 3, "unicos": 2}}, "cuadre": {"ok": True}}) == []),
        ("los errores por exceso y por defecto se listan separados y NO se netean",
         (lambda t: "por exceso: 1" in t and "por defecto: 2" in t and "No se suman ni se compensan" in t)(
             "\n".join(p.text for p in generar({"elementos": [{"id": 1, "libros": 100, "unidades": 1, "token": "PROV 1", "doc": 90, "error": 10},
                                                              {"id": 2, "libros": 100, "unidades": 1, "token": "PROV 2", "doc": 110, "error": -10}],
                                                "p": {}, "estado": {}}, "30/09/2026").paragraphs))),
    ]

    for descripcion, ok in pruebas:
        print(f"  {'OK   ' if ok else 'FALLA'}  {descripcion}")
        if not ok:
            fallos += 1
    print()
    print("RESULTADO:", "todo correcto" if fallos == 0 else f"{fallos} fallo(s)")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
