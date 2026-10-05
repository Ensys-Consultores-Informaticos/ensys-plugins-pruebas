# -*- coding: utf-8 -*-
"""Construye `nia530.json` a partir de lo que el MCP exporta de una prueba MUM. Puede abortar.

    python construir_nia530.py --id 57 \
        --pruebas    "$DATOS/pruebas.json" \
        --parametros "$DATOS/parametros.json" \
        --resumen    "$DATOS/resumen.json" \
        --muestra    "$DATOS/muestra.json" \
        --evaluacion "$DATOS/evaluacion.json" \
        [--contexto  "$DATOS/contexto.json"] \
        [--excel     "<papel de fsp-mum>.xlsx"] \
        --salida     "$DATOS/nia530.json"

Cada dato del papel sale de UNA fuente y aqui se dice cual. Lo que no esta en ninguna va a
null, y el generador lo pinta como PENDIENTE con quien lo aporta. No se infiere, no se estima,
no se rellena con ejercicios anteriores.

De donde sale cada cosa (medido el 30/09/2026 sobre el MCP 1.23.0):

  pruebas.json      obtener_entidad('pruebas')            la prueba, su estado y sus fechas
  parametros.json   obtener_entidad('parametros', id)     DatosPSMum y su bloque `descodificado`
  resumen.json      obtener_entidad('resumen', id)        la poblacion en cifras y el cuadre .smp/.pcu
  muestra.json      exportar_consulta(entidad='muestra')  los elementos seleccionados, TOKENIZADOS
  evaluacion.json   exportar_consulta(entidad='evaluacion') la evaluacion del auditor, TOKENIZADA
  contexto.json     contexto_expediente()                 cliente, cierre e importancia relativa (solo con .gs3)
  excel             el papel de fsp-mum de esta sesion    importe segun documento y error por elemento

El informe PDF de ForSampling NO es fuente (David, 30/09/2026): sirvio para saber QUE hay que
documentar, y todo sale de los ficheros. Lo que ForSampling no guarda -la proyeccion del error,
la distribucion- no se transcribe de ningun PDF ni se recalcula: se dice que se calcula al
emitir el informe y se deja el hueco.

Codigos de salida: 0 todo encaja · 1 hay avisos que van al auditor · 2 falta algo sin lo que no hay papel.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import sys

RE_TOKEN = re.compile(r"^(PROV|CLI|TER)\b\s*\S+$", re.I)


def salida_utf8() -> None:
    for flujo in ("stdout", "stderr"):
        f = getattr(sys, flujo, None)
        if f is not None and hasattr(f, "reconfigure"):
            try:
                f.reconfigure(encoding="utf-8")
            except Exception:
                pass


def leer(ruta):
    if not ruta:
        return None
    with io.open(ruta, encoding="utf-8-sig") as fh:
        return json.load(fh)


def texto(v) -> str:
    return "" if v is None else str(v).strip()


def a_float(v):
    """Los importes del API vienen como texto con coma decimal y punto de millar."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace(" ", "").replace("€", "")
    if "," in t and "." in t:
        t = t.replace(".", "").replace(",", ".")
    elif "," in t:
        t = t.replace(",", ".")
    try:
        return float(t)
    except ValueError:
        return None


def a_int(v):
    f = a_float(v)
    return None if f is None else int(round(f))


def es_si(v) -> bool:
    return texto(v).lower() in ("true", "sí", "si", "-1", "1", "yes")


def solo_fecha(v) -> str | None:
    """«31/12/2025 0:00:00» -> «31/12/2025»; «31/12/25 0:00:00» -> «31/12/2025»."""
    t = texto(v).split(" ")[0]
    if not t:
        return None
    m = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", t)
    if not m:
        return t
    d, mth, y = m.groups()
    if len(y) == 2:
        y = "20" + y
    return f"{int(d):02d}/{int(mth):02d}/{y}"


def columna(fila: dict, *candidatas) -> str | None:
    """La primera columna de la fila cuyo nombre en minusculas coincide con alguna candidata."""
    bajas = {k.lower(): k for k in fila}
    for c in candidatas:
        if c.lower() in bajas:
            return bajas[c.lower()]
    return None


def columna_id(fila: dict) -> str | None:
    return next((k for k in fila if k.lower().endswith("_id")), None)


def columna_token(filas: list) -> str | None:
    """La columna cuyos valores son tokens PROV/CLI/TER. Si no hay ninguna, None: los nombres
    han salido en claro y el papel NO los puede llevar."""
    if not filas:
        return None
    for k in filas[0]:
        vals = [texto(f.get(k)) for f in filas if texto(f.get(k))]
        if vals and all(RE_TOKEN.match(v) for v in vals):
            return k
    return None


def leer_excel_fsp_mum(ruta: str) -> dict:
    """{id: {doc, error, fichero}} del papel de fsp-mum. La fila de cabecera se busca, no se supone."""
    from openpyxl import load_workbook
    wb = load_workbook(ruta, data_only=True)
    ws = wb["Análisis muestra"] if "Análisis muestra" in wb.sheetnames else wb.active
    cab_fila, cab = None, None
    for fila in ws.iter_rows(min_row=1, max_row=15, values_only=True):
        vals = [texto(v) for v in fila]
        if "Error" in vals and any(v.startswith("Valor Auditor") for v in vals):
            cab_fila, cab = ws.min_row, vals
            break
    if cab is None:
        raise ValueError("el Excel no tiene la cabecera de fsp-mum (columnas «Valor Auditoría (doc)» y «Error»)")
    # la fila de cabecera real: la primera que casa
    for i, fila in enumerate(ws.iter_rows(min_row=1, max_row=15, values_only=True), start=1):
        if [texto(v) for v in fila] == cab:
            cab_fila = i
            break
    i_id = next(i for i, v in enumerate(cab) if v.lower().endswith("_id"))
    i_doc = next(i for i, v in enumerate(cab) if v.startswith("Valor Auditor"))
    i_err = cab.index("Error")
    i_fic = cab.index("Fichero") if "Fichero" in cab else None
    res = {}
    for fila in ws.iter_rows(min_row=cab_fila + 1, values_only=True):
        if fila[i_id] is None:
            continue
        res[texto(fila[i_id])] = {"doc": a_float(fila[i_doc]), "error": a_float(fila[i_err]),
                                  "fichero": texto(fila[i_fic]) if i_fic is not None else ""}
    return res


def main() -> int:
    salida_utf8()
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--pruebas", required=True)
    ap.add_argument("--parametros", required=True)
    ap.add_argument("--resumen", required=True)
    ap.add_argument("--muestra", required=True)
    ap.add_argument("--evaluacion", required=True)
    ap.add_argument("--contexto")
    ap.add_argument("--excel")
    ap.add_argument("--salida", required=True)
    a = ap.parse_args()

    errores, avisos, fuentes = [], [], []
    mid = texto(a.id)

    try:
        pruebas = leer(a.pruebas); par = leer(a.parametros); res = leer(a.resumen)
        muestra = leer(a.muestra); evaluacion = leer(a.evaluacion)
        ctx = leer(a.contexto)
    except Exception as exc:
        print("❌ no se han podido leer los ficheros exportados: " + str(exc))
        return 2

    # ── 1 · la prueba ────────────────────────────────────────────────────────
    lista = pruebas.get("pruebas") if isinstance(pruebas, dict) else pruebas
    prueba = next((p for p in (lista or []) if texto(p.get("MuestraId")) == mid), None)
    if prueba is None:
        print(f"❌ la prueba {mid} no está en pruebas.json: obtener_entidad('pruebas') las lista")
        return 2
    if texto(prueba.get("Tipo")).upper() != "MUM":
        print(f"❌ la prueba {mid} es de tipo «{prueba.get('Tipo')}», no MUM: este papel es de la NIA-ES 530 para MUM")
        return 2
    fuentes.append(["FS · .cli · Muestreos", "prueba, área, referencia, tipo, periodo, estado, objetivo"])

    # ── 2 · parametros, descodificados ───────────────────────────────────────
    if not isinstance(par, dict) or "parametros" not in par:
        print("❌ parametros.json no es lo que devuelve obtener_entidad('parametros', id)")
        return 2
    dp = par.get("parametros") or {}
    desc = par.get("descodificado") or {}
    if not desc:
        avisos.append("el MCP no ha devuelto 'descodificado' en parametros: es anterior a la 1.23.0. Confianza, "
                      "factor, criterio y método quedan PENDIENTES")
    fuentes.append(["FS · .cli · DatosPSMum", "descripción y unidad de la población, errores esperados, error tolerable, tamaño deseado"])
    if desc:
        fuentes.append(["FS · .cli · TM_Confianza, TM_Riesgos, TM_Lambda", "confianza, riesgo, tipo de trabajo y factores, vía el MCP"])

    # ── 3 · resumen: la poblacion en cifras ──────────────────────────────────
    if not isinstance(res, dict) or "elementos" not in res:
        print("❌ resumen.json no es lo que devuelve obtener_entidad('resumen', id) del MCP 1.23.0")
        return 2
    VP = a_float(res.get("importe_total"))
    cuadre_res = res.get("cuadre_importacion") or {}
    fuentes.append(["FS · fichero de la prueba · " + texto(res.get("tabla_poblacion")),
                    "número de elementos, valor de la población, seleccionados, selecciones, cuadre con el .smp"])

    # ── 4 · muestra: los elementos, tokenizados ──────────────────────────────
    filas_m = muestra if isinstance(muestra, list) else (muestra or {}).get("filas") or []
    if not filas_m:
        print("❌ muestra.json viene vacío")
        return 2
    k_id = columna_id(filas_m[0])
    k_rep = columna(filas_m[0], "Repeticiones")
    k_fecha = columna(filas_m[0], "FECHA", "Fecha")
    k_cta = columna(filas_m[0], "CUENTA", "CTA4", "CuentaContable", "CodigoCuenta")
    k_imp = texto(res.get("campo_importe")) or columna(filas_m[0], "SALDO", "IMPORTE", "DEBE", "HABER")
    k_tok = columna_token(filas_m)
    if not k_id or not k_imp or k_imp not in filas_m[0]:
        print("❌ la muestra no trae la columna _ID o la del importe (" + texto(k_imp) + ")")
        return 2
    if not k_tok:
        # se PARA: un papel con nombres de terceros no puede salir de aqui
        print("❌ la muestra NO está tokenizada: ninguna columna lleva tokens PROV/CLI/TER. Vuelve a "
              "configurar(gs3_file=…, perfil='fsp-mum') y exporta otra vez. El papel no puede llevar nombres.")
        return 2

    # ── 5 · evaluacion: el error segun el auditor, por id ────────────────────
    filas_e = evaluacion if isinstance(evaluacion, list) else (evaluacion or {}).get("filas") or []
    err_auditor = {}
    if filas_e:
        k_id_e = columna_id(filas_e[0]) or k_id
        k_err = columna(filas_e[0], "ErrorAuditoria")
        if k_err:
            for f in filas_e:
                err_auditor[texto(f.get(k_id_e))] = a_float(f.get(k_err))
            fuentes.append(["FS · fichero de la prueba · " + texto(res.get("tabla_poblacion")) + "_AN", "evaluación del auditor por elemento"])
        else:
            avisos.append("la evaluación no trae ErrorAuditoria: el error según el auditor queda PENDIENTE")
    else:
        avisos.append("la prueba no tiene evaluación del auditor todavía (tabla _AN vacía)")

    # ── 6 · el Excel de fsp-mum, si lo hay ───────────────────────────────────
    excel = {}
    if a.excel:
        try:
            excel = leer_excel_fsp_mum(a.excel)
            fuentes.append(["DOC · papel de fsp-mum", "importe según documento y error por elemento"])
        except Exception as exc:
            avisos.append("no se ha podido leer el papel de fsp-mum: " + str(exc) + ". Los apartados 6 y 7 salen PENDIENTES")
    else:
        avisos.append("sin ejecución de fsp-mum: importe según documento y error quedan PENDIENTES (apartados 6 y 7)")

    elementos = []
    for f in filas_m:
        eid = texto(f.get(k_id))
        ex = excel.get(eid, {})
        sin_doc = bool(excel) and not texto(ex.get("fichero")) and ex.get("doc") is None
        elementos.append({
            "id": eid, "fecha": solo_fecha(f.get(k_fecha)) if k_fecha else None,
            "cuenta": texto(f.get(k_cta)) if k_cta else None,
            "libros": a_float(f.get(k_imp)), "unidades": a_int(f.get(k_rep)) or 1 if k_rep else 1,
            "token": texto(f.get(k_tok)) or None,
            "doc": ex.get("doc") if excel and not sin_doc else None,
            "error": ex.get("error") if excel and not sin_doc else None,
            "error_auditor": err_auditor.get(eid),
            "nota": "", "sin_documento": sin_doc,
            "sin_doc_texto": "No localizado en la carpeta de documentación del área." if sin_doc else None,
        })
    # por fecha DE VERDAD: «dd/mm/aaaa» como texto ordena por el dia y mezcla los meses
    def _clave_fecha(e):
        f = e["fecha"] or ""
        m = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", f)
        return ((m.group(3), m.group(2), m.group(1)) if m else ("", "", "")), e["id"]
    elementos.sort(key=_clave_fecha)

    # ── 7 · contexto de Gesia, solo si hay .gs3 ──────────────────────────────
    modo = "completo" if ctx else "solo_fs"
    ir = None
    if ctx:
        if a_float(ctx.get("IR_T")) is not None:
            ir = {"p": a_float(ctx.get("IR_P")), "t": a_float(ctx.get("IR_T")), "i": a_float(ctx.get("IR_I"))}
            fuentes.append(["GS · .gs3 · CalculosIRElecciones", "importancia relativa"])
        fuentes.append(["GS · .gs3 · DatosAuditoria, Auditorias", "razón social y fecha de cierre"])

    # ── 8 · los parametros del diseño ────────────────────────────────────────
    rg = desc.get("riesgo_general") if isinstance(desc.get("riesgo_general"), dict) else {}
    definido_por = texto(desc.get("error_tolerable_definido_por"))
    et_valor, et_tasa = a_float(dp.get("ErrorTolerableValor")), a_float(dp.get("ErrorTolerableTasa"))
    et = None
    if definido_por == "valor" and et_valor:
        et = et_valor
    elif definido_por == "tasa" and et_tasa and VP:
        et = round(et_tasa / 100.0 * VP, 2)
        avisos.append(f"el error tolerable está definido por TASA ({et_tasa:g} %): el importe {et:,.2f} es tasa × valor "
                      "de la población, aritmética y no juicio")
    elif et_valor:
        et = et_valor
    tie = a_float(dp.get("PoblacionTasaErrores"))
    tp = round(et / VP * 100 - (tie or 0), 4) if (et and VP) else None
    metodo = desc.get("metodo_seleccion")
    metodo = None if (not metodo or str(metodo).startswith("sin confirmar")) else metodo
    # la distribucion (binomial / Poisson) NO se guarda en ningun fichero de ForSampling: medido en
    # DatosPSMum y en Parametrizacion. Se queda a null y el papel lo dice; no se transcribe de nada.
    criterio = desc.get("criterio_seleccion")
    fl = desc.get("factor_lambda") if isinstance(desc.get("factor_lambda"), dict) else None
    factor = None
    if fl or rg.get("factor_confianza"):
        partes = []
        if fl:
            partes.append(f"{fl.get('valor')} (TM_Lambda, {fl.get('errores_esperados')} errores esperados)")
        if rg.get("factor_confianza"):
            partes.append(f"{rg.get('factor_confianza')} (TM_Confianza)")
        factor = " / ".join(partes)
    p = {
        "confianza": rg.get("confianza_pct"), "tipo_trabajo": rg.get("tipo_trabajo"),
        "distribucion": None,
        "err_esp_n": a_int(dp.get("PoblacionNumErrores")), "err_esp_pct": tie, "tie": tie,
        "et": et, "tp": tp, "ir": ir, "ir_nota": None,
        "tam": {"propuesto": a_int(dp.get("TamanoMuestraDeseado")), "seleccionado": a_int(res.get("selecciones")),
                "unicos": a_int(res.get("seleccionados"))},
        "metodo": metodo,
        "metodo_nota": ((f"criterio «{criterio}»; " if criterio and not str(criterio).startswith("sin confirmar") else "")
                        + ("código descodificado por el MCP, medido sobre los ficheros" if metodo
                           else "código sin confirmar en los ficheros de ForSampling")),
        "factor": factor, "factor_nota": desc.get("factor_nota"), "motivacion": None,
    }

    # ── 9 · la proyeccion NO se guarda: no hay fuente, y se dice ────────────
    # Medido el 30/09/2026 en las 40 tablas del .cli y en las del fichero de la prueba: la
    # estimacion del error, IMS/IMI, el porcentaje y el limite superior no estan en ningun sitio.
    # ForSampling los calcula al emitir el informe. El PDF no es fuente y no se recalcula nada.
    resultados, informe_fecha = None, None
    avisos.append("la proyección (estimación del error, IMS/IMI, límite superior) no se guarda en ForSampling: se "
                  "calcula al emitir el informe. El apartado 8 lo dice y deja el hueco; no se transcribe ni se recalcula")

    # ── 10 · cuentas sin elemento, del desglose por grupo ────────────────────
    sin_elementos = []
    for g in res.get("por_grupo") or []:
        if a_int(g.get("seleccionados")) == 0 and a_float(g.get("importe")):
            sin_elementos.append({"cuenta": texto(g.get("grupo")), "importe": a_float(g.get("importe"))})

    cuadre = {"ok": None, "texto": None}
    if cuadre_res:
        if cuadre_res.get("cuadra") is True:
            # los numeros se formatean APARTE y luego se componen: aplicar el cambio de separadores
            # a la frase entera convertia «.smp» en «,smp»
            def _es(n, dec):
                return f"{n:,.{dec}f}".replace(",", "X").replace(".", ",").replace("X", ".")
            cuadre = {"ok": True, "texto": f"{_es(a_int(cuadre_res.get('elementos_importacion')), 0)} filas y "
                                            f"{_es(a_float(cuadre_res.get('importe_importacion')), 2)} € en el .smp y en el fichero de la prueba"}
        elif cuadre_res.get("cuadra") is False:
            cuadre = {"ok": False, "texto": f"NO cuadran: .smp {cuadre_res.get('elementos_importacion')} filas / "
                                             f"{cuadre_res.get('importe_importacion')}; prueba {cuadre_res.get('elementos_prueba')} / "
                                             f"{cuadre_res.get('importe_prueba')}"}
            avisos.append("la población importada (.smp) y la del fichero de la prueba NO cuadran: hay que entenderlo antes de seguir")
        elif cuadre_res.get("existe") is False:
            cuadre = {"ok": None, "texto": "el .smp de importación no está donde el .cli dice"}

    objetivo = texto(prueba.get("Objetivo")) or texto(prueba.get("Observaciones")) or None

    S = {
        "modo": modo,
        "entidad": texto(ctx.get("RazonSocialCliente")) or None if ctx else None,
        "ejercicio_ini": solo_fecha(prueba.get("FechaInicioAuditoria")),
        "ejercicio_fin": solo_fecha(prueba.get("FechaFinAuditoria")),
        "cierre": solo_fecha(ctx.get("FechaCierre")) if ctx else None,
        "area": texto(prueba.get("Area")) or None, "referencia": texto(prueba.get("Referencia")) or None,
        "prueba": texto(prueba.get("Prueba")), "tipo": texto(prueba.get("Tipo")) or "MUM", "muestra_id": a_int(mid),
        "cli": os.path.basename(texto(par.get("fichero_parametros"))) or None,
        "informe_fecha": informe_fecha,
        "estado": {"finalizada": es_si(prueba.get("PruebaFinalizada")), "realizado": es_si(prueba.get("Realizado")),
                   "verificado": es_si(prueba.get("Verificado"))},
        "objetivo": objetivo, "afirmacion": None, "riesgo_area": None,
        "descripcion_poblacion": texto(dp.get("PoblacionDescripcion")) or None,
        "unidad": texto(dp.get("UnidadMuestreo")) or None,
        "n_elementos": a_int(res.get("elementos")), "valor_poblacion": VP, "poblacion_nota": None,
        "fichero_smp": os.path.basename(texto(cuadre_res.get("fichero_importacion"))) or None,
        "fichero_pcu": os.path.basename(texto(res.get("fichero_prueba"))) or None,
        "cuadre": cuadre, "diario": {"ok": None, "texto": None},
        "por_cuenta": [], "conciliacion_nota": None, "conciliacion_detalle": None,
        "p": p, "seleccion_fecha": None,
        "elementos": elementos, "sin_elementos": sin_elementos,
        "n_documentos": len({texto(x.get("fichero")) for x in excel.values() if texto(x.get("fichero"))}) or None,
        "modo_facturas": None, "procedimientos_extra": [], "avisos": [], "observaciones_ajenas": [],
        "causa_errores": None, "anomalias": None,
        "resultados": resultados, "resultados_nota": None, "fuentes": fuentes,
    }
    if a_int(dp.get("PoblacionNumElementos")) not in (None, S["n_elementos"]):
        avisos.append(f"DatosPSMum dice {dp.get('PoblacionNumElementos')} elementos y el fichero de la prueba tiene "
                      f"{S['n_elementos']}: la población declarada y la real no coinciden")

    os.makedirs(os.path.dirname(os.path.abspath(a.salida)), exist_ok=True)
    with io.open(a.salida, "w", encoding="utf-8") as fh:
        json.dump(S, fh, ensure_ascii=False, indent=1)

    print(f"✔ nia530.json escrito: {a.salida}")
    print(f"  modo {modo} · prueba {mid} «{S['prueba']}» · {len(elementos)} elementos, "
          f"{sum(e['unidades'] for e in elementos)} unidades · población {VP:,.2f} en {S['n_elementos']} elementos"
          if VP else f"  modo {modo} · prueba {mid} · {len(elementos)} elementos")
    print(f"  tercero tokenizado en «{k_tok}» · error del auditor en {len(err_auditor)} elementos · "
          f"documento en {sum(1 for e in elementos if e['doc'] is not None)}")
    if avisos:
        print("\nPARA CONTAR AL ENTREGAR (tal cual, sin resumir):")
        for v in avisos:
            print("  - " + v)
        return 1
    print("  todo encaja")
    return 0


if __name__ == "__main__":
    sys.exit(main())
