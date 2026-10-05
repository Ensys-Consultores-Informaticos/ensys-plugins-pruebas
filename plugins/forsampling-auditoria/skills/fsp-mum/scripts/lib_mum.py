# -*- coding: utf-8 -*-
"""Lo propio de una prueba MUM: importe según el auditor, error y tasa.

La lectura de los documentos y el cruce con la muestra son iguales que en la
prueba de cumplimiento y viven en `lib_fsp.py`, que es **el mismo fichero** en
los dos skills. Aquí solo está lo que cambia: una MUM no evalúa atributos, mide
**cuánto vale cada elemento según el documento** y de ahí sale el error.

Tres columnas por elemento, con los nombres que usa ForSampling:

    SaldoAuditoria       lo que el documento sostiene para ese apunte
    ErrorAuditoria       Saldo - SaldoAuditoria  (positivo: los libros dicen de más)
    ErrorAuditoriaTasa   el error sobre el saldo, en tanto por ciento

**Lo que este módulo no hace, y no es un olvido:** no proyecta el error a la
población, no lo compara con el error tolerable, no suma los errores entre sí y
no concluye. Eso lo hace ForSampling con la muestra evaluada, y hacerlo aquí
sería sustituir el motor estadístico de la prueba por una cuenta a ojo.

Y sobre todo **no se netean los errores**. Un error de +600 y otro de -600 no se
cancelan: en una MUM son dos incorrecciones que se proyectan cada una por su
lado. Sumarlas y decir «error neto cero» es el fallo más caro que puede cometer
quien lee esta prueba, y ha pasado.
"""
from __future__ import annotations

from lib_fsp import _fmt, _irpf, base_de, parse_importe

TOL = 0.01          # un céntimo, igual que en el cruce
TOL_IVA_PISTA = 0.5  # margen al reconocer una diferencia como cuota de IVA

TERMINOS = ("total", "base", "neto")
NOMBRE_TERMINO = {"total": "el total de la factura",
                  "base": "la base imponible",
                  "neto": "el neto a pagar tras la retención"}


def _valor(fac: dict, termino: str) -> float | None:
    """El importe del documento según con qué se compare.

    `importe_aplicable` manda sobre todo lo demás: es la parte del documento que sostiene ESTE
    elemento, declarada a mano cuando el reparto no se puede deducir (el documento cubre varios
    asientos, hay una entrega parcial, o parte del gasto cae fuera de la población). No falsea
    la lectura: la base y el total siguen siendo los que pone la factura.
    """
    if fac is None:
        return None
    apl = parse_importe(fac.get("importe_aplicable"))
    if apl is not None:
        return apl
    if termino == "total":
        return parse_importe(fac.get("total"))
    if termino == "base":
        return base_de(fac)
    if termino == "neto":
        base, iva, ret = (parse_importe(fac.get("base")), parse_importe(fac.get("iva")), _irpf(fac))
        if base is None or ret is None:
            return None
        return round(base + (iva or 0.0) - ret, 2)
    return None


def termino_mayoritario(evaluados: list[dict]) -> str:
    """Con qué compara esta población: total, base o neto.

    No se decide por el plan contable ni por el nombre de la cuenta, sino por lo
    que hace **la propia muestra**: el término con el que casan los elementos que
    sí casan. Es la regla 8 del proyecto -medir contra la línea base del cliente-
    aplicada al criterio de contabilización.

    Importa porque en los elementos que NO casan hay que restar de algo, y
    equivocarse de término convierte una cuota de IVA en un error de auditoría.
    Con menos de dos elementos casados, o con empate, se devuelve cadena vacía y
    el skill no propone importe: lo decide el auditor.
    """
    votos: dict[str, int] = {}
    for e in evaluados:
        t = (e.get("criterios") or {}).get("importe")
        if t in TERMINOS:
            votos[t] = votos.get(t, 0) + 1
    if not votos:
        return ""
    orden = sorted(votos.items(), key=lambda kv: -kv[1])
    if orden[0][1] < 2:
        return ""
    if len(orden) > 1 and orden[0][1] == orden[1][1]:
        return ""
    return orden[0][0]


def _pista_iva(error: float, fac: dict) -> str:
    """¿La diferencia es justo una cuota de IVA? Entonces es criterio, no error.

    El caso que se da: del documento no se ha podido leer el total -solo la base-,
    los libros llevan el importe con IVA, y el error sale exactamente la cuota.
    Marcarlo como incorrección es un falso positivo que además se proyecta a toda
    la población: un error del tamaño del IVA. Se avisa, se deja el importe
    propuesto, y decide el auditor.
    """
    iva = parse_importe(fac.get("iva"))
    if iva and abs(abs(error) - abs(iva)) <= TOL_IVA_PISTA:
        return (f"coincide con la cuota de IVA del documento ({_fmt(iva)}): puede ser criterio "
                f"de contabilización, no incorrección")
    base = parse_importe(fac.get("base"))
    if base:
        for tipo in (21, 10, 4):
            if abs(abs(error) - round(abs(base) * tipo / 100.0, 2)) <= TOL_IVA_PISTA:
                return (f"coincide con un IVA del {tipo} %: puede ser criterio de "
                        f"contabilización, no incorrección")
    return ""


def evaluar_mum(cruce: dict, cols: dict) -> list[dict]:
    """Un importe según auditor, un error y una tasa por elemento seleccionado."""
    items = cruce["filas"]
    termino = termino_mayoritario(items)
    salida = []
    for it in items:
        fila, fac, c = it["fila"], it["factura"], it["criterios"]
        saldo = parse_importe(fila.get(cols["importe"]))
        reps = parse_importe(fila.get("Repeticiones")) or 1
        saldo_aud = error = tasa = None
        usado, nota = "", ""

        if saldo is None:
            nota = "El elemento no trae importe en la población: no se puede medir el error"
        elif fac is None:
            nota = ("Documento no localizado en la carpeta: sin él no se puede fijar el importe "
                    "según auditoría")
        elif parse_importe(fac.get("importe_aplicable")) is not None:
            # lo declarado a mano manda: se mide contra esa parte, y se dice en la observacion
            usado = termino or "total"
            saldo_aud = _valor(fac, usado)
            saldo_aud = saldo_aud if saldo >= 0 else -saldo_aud
            error = round(saldo - saldo_aud, 2)
            tasa = round(error / saldo * 100.0, 2) if saldo else None
            nota = "importe aplicable declarado a mano en facturas.json"
        elif c["importe"] in TERMINOS:
            # Casa: el documento sostiene el saldo contabilizado, no hay error.
            usado = c["importe"]
            saldo_aud = saldo
            error = 0.0
            tasa = 0.0
        elif c.get("por_asiento") in TERMINOS:
            # El documento sostiene el ASIENTO ENTERO, del que este elemento es una linea. El
            # gasto esta completo: el elemento esta medido y su error es 0.
            usado = c["por_asiento"]
            saldo_aud = saldo
            error = 0.0
            tasa = 0.0
            nota = _nota_asiento(fila, "cuadra")
        elif fila.get("LineasAsiento"):
            # Asiento partido cuyo documento NO sostiene ni la linea ni la suma. Aqui NO se
            # propone nada (David, 18/09/2026): proponer el importe del documento declara un
            # error igual a la otra linea del asiento, y ese error se proyecta a la poblacion
            # entera. La observacion dice donde estan las lineas para que el auditor mire.
            nota = _nota_asiento(fila, "no cuadra")
        elif not termino:
            nota = ("sin criterio de comparación claro (total, base o neto): lo decide "
                    "el auditor")
        else:
            v = _valor(fac, termino)
            if v is None:
                nota = f"no se lee {NOMBRE_TERMINO[termino]} en el documento"
            else:
                usado = termino
                # El signo del saldo manda: en una poblacion de ingresos los
                # importes vienen en negativo y el error tiene que seguirlos.
                saldo_aud = v if saldo >= 0 else -v
                error = round(saldo - saldo_aud, 2)
                tasa = round(error / saldo * 100.0, 2) if saldo else None
                pista = _pista_iva(error, fac) if error else ""
                if pista:
                    nota = pista
        salida.append({**it, "saldo": saldo, "repeticiones": reps, "termino": usado,
                       "saldo_auditoria": saldo_aud, "error": error, "tasa": tasa, "nota": nota})
    return salida


def _nota_asiento(fila: dict, caso: str) -> str:
    """Donde estan las lineas del asiento, para el auditor. Sin cifras que no tenga ya."""
    n = fila.get("LineasAsiento")
    suma = _fmt(parse_importe(fila.get("ImporteAsiento")))
    ids = str(fila.get("IdsAsiento") or "").strip()
    donde = f" (elementos {ids})" if ids else ""
    if caso == "cuadra":
        # la suma no se repite: es la del documento, que ya esta en el papel
        return f"el documento soporta el asiento entero, {n} líneas{donde}"
    # aqui la suma SI se dice: es el dato nuevo, no esta en ninguna columna
    return (f"ATENCIÓN, asiento partido: {n} líneas{donde} suman {suma} y no casan con el "
            f"documento. Sin propuesta")


def _may(t: str) -> str:
    return (t[:1].upper() + t[1:]) if t else t


def observacion_mum(e: dict) -> str:
    """La observación que se copia a ForSampling, firmada y CORTA.

    Sigue el registro telegráfico que usa el propio auditor en estas pruebas
    -«Fra N: <numero> a fecha de <fecha> y con importe correcto», la plantilla que
    apareció igual en los 18 de 18 elementos de un encargo real- y **no repite lo
    que ya está en su columna**. El importe en libros, el valor según auditoría, el error y el
    porcentaje se ven al lado, en el papel y en la rejilla de ForSampling:
    escribirlos otra vez alarga la nota sin añadir nada.

    Aquí va solo lo que no se puede reconstruir de las columnas: qué documento se
    miró, hacia qué lado está la diferencia, la pista de que puede ser criterio de
    contabilización y no incorrección, y los avisos del cruce.

    Dice «Ok» cuando no hay diferencia -decisión de David, 08/09/2026-, y detrás
    «importe correcto», que son las palabras de su propia plantilla. El «Ok»
    delante es lo que permite barrer la columna de un vistazo, igual que en
    fsp-cumplimiento.
    """
    fac = e["factura"]
    if fac is None:
        return "Asistente IA: documento no localizado."
    c = e.get("criterios") or {}
    cola = ""
    if c.get("declarado"):
        cola = " Asignado a mano, no por el cruce."
    elif c.get("ambiguo"):
        cola = " ATENCIÓN: varios candidatos por tercero y fecha, confirma el documento."
    num = fac.get("numero")
    ref = f"Fra {num}" if num else f"factura de {fac.get('proveedor') or '—'}"
    if e["error"] is None:
        return f"Asistente IA: {ref}: {e['nota']}." + cola
    nota = f" {_may(e['nota'])}." if e.get("nota") else ""
    if abs(e["error"]) <= TOL:
        return f"Asistente IA: Ok. {ref}: importe correcto." + nota + cola
    signo = "de más" if abs(e["saldo"]) > abs(e["saldo_auditoria"]) else "de menos"
    return f"Asistente IA: {ref}: {_fmt(abs(e['error']))} {signo} en libros." + nota + cola


def recuento(evaluados: list[dict]) -> dict:
    """Los números que se dicen al entregar. **Nunca un error neto.**

    Las incorrecciones por exceso y por defecto se cuentan por separado a
    propósito: en una MUM cada una se proyecta por su lado, y presentarlas
    sumadas -«error neto 181,32»- esconde justo lo que la prueba busca.
    """
    con_doc = [e for e in evaluados if e["factura"] is not None]
    medidos = [e for e in evaluados if e["error"] is not None]
    exceso = [e for e in medidos if e["error"] > TOL]
    defecto = [e for e in medidos if e["error"] < -TOL]
    return {
        "elementos": len(evaluados),
        "repeticiones": sum(e["repeticiones"] for e in evaluados),
        "con_documento": len(con_doc),
        "sin_documento": len(evaluados) - len(con_doc),
        "medidos": len(medidos),
        "sin_medir": len(evaluados) - len(medidos),
        "sin_error": len([e for e in medidos if abs(e["error"]) <= TOL]),
        "con_error": len(exceso) + len(defecto),
        "n_exceso": len(exceso),
        "n_defecto": len(defecto),
        "suma_exceso": round(sum(e["error"] for e in exceso), 2),
        "suma_defecto": round(sum(e["error"] for e in defecto), 2),
    }


def comparar_con_auditor_mum(evaluados: list[dict], evaluacion: list[dict], cols: dict) -> dict | None:
    """Lo que puso el auditor frente a lo que propone el skill, elemento a elemento.

    La cifra que importa es **«skill dice 0 y el auditor puso error»**:
    incorrecciones que el skill se habría dejado pasar. La contraria hay que
    mirarla, no descartarla: puede ser un error real que el auditor aceptó con
    motivo, y el motivo debería estar en su observación.
    """
    if not evaluacion:
        return None
    idc = cols.get("id")
    por_id = {str(r.get(idc)): r for r in evaluacion if idc and r.get(idc) is not None}
    if not por_id:
        return None
    filas, r = [], {"coinciden": 0, "skill_error_auditor_cero": 0, "skill_cero_auditor_error": 0,
                    "discrepan": 0, "sin_evaluar": 0}
    for e in evaluados:
        ident = str(e["fila"].get(idc))
        ev = por_id.get(ident)
        if ev is None:
            r["sin_evaluar"] += 1
            continue
        err_aud = parse_importe(ev.get("ErrorAuditoria"))
        sa_aud = parse_importe(ev.get("SaldoAuditoria"))
        err_skill = e["error"]
        if err_skill is None:
            estado = "sin medir"
            r["sin_evaluar"] += 1
        elif err_aud is None:
            estado = "el auditor no lo ha evaluado"
            r["sin_evaluar"] += 1
        elif abs(err_skill - err_aud) <= TOL:
            estado = "coinciden"
            r["coinciden"] += 1
        elif abs(err_aud) <= TOL:
            estado = "el skill señala error y el auditor puso 0"
            r["skill_error_auditor_cero"] += 1
        elif abs(err_skill) <= TOL:
            estado = "EL SKILL DA 0 Y EL AUDITOR PUSO ERROR"
            r["skill_cero_auditor_error"] += 1
        else:
            estado = "los dos ven error, de distinto importe"
            r["discrepan"] += 1
        filas.append({"id": ident, "saldo": e["saldo"],
                      "saldo_auditoria_skill": e["saldo_auditoria"], "error_skill": err_skill,
                      "saldo_auditoria_auditor": sa_aud, "error_auditor": err_aud,
                      "estado": estado,
                      "observacion_auditor": next((ev[k] for k in ev if k.endswith("_OBSERV")), None)})
    return {"filas": filas, "recuento": r}
