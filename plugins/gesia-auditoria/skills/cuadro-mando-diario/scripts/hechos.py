#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Hechos relevantes del ejercicio, deducidos de forma determinista.

Cada regla mira los cuatro paquetes de datos y, si se cumple, devuelve una
tarjeta con su severidad, su narrativa y las cifras que la sostienen. La
severidad se ancla a la importancia relativa del encargo, no al criterio de
quien mira.

Dos reglas de redaccion que importan tanto como el calculo:

  * Describir, no dictaminar. El panel no decide si un patron es normal: dice
    cuanto vale y deja el juicio al auditor. Un diario con el 12 % de los
    apuntes en fin de semana puede ser una empresa que abre los sabados o un
    diario amanado, y el fichero no lo sabe.

  * Nada que salga del punteo se presenta como medida contable: es una lista
    de revision.
"""

from __future__ import annotations

CRITICO, ALTO, MEDIO, BAJO, CORRECTO = "critico", "alto", "medio", "bajo", "correcto"
ORDEN = {CRITICO: 0, ALTO: 1, MEDIO: 2, BAJO: 3, CORRECTO: 4}


def eur(v: float) -> str:
    return f"{v:,.0f}".replace(",", ".") + " €"


def eur2(v: float) -> str:
    e = f"{v:,.2f}"
    return e.replace(",", "@").replace(".", ",").replace("@", ".") + " €"


def n(v) -> str:
    return f"{int(v):,}".replace(",", ".")


def pct(v, d=1) -> str:
    return f"{v:.{d}f}".replace(".", ",") + " %"


class Hechos:
    def __init__(self) -> None:
        self.lista: list[dict] = []

    def add(self, sev, cat, titulo, parrafos, cifras=None, ancla=None):
        self.lista.append({
            "severidad": sev, "categoria": cat, "titulo": titulo,
            "parrafos": [p for p in parrafos if p],
            "cifras": cifras or [], "ancla": ancla or "",
        })

    def ordenados(self) -> list[dict]:
        return sorted(self.lista, key=lambda h: ORDEN[h["severidad"]])


def _grupo(conc, cuenta):
    if not conc:
        return None
    for g in conc.get("grupos", []):
        if g.get("cuenta") == cuenta:
            return g
    return None


def construir(meta, resultado, contrato, conc, punt, diario) -> list[dict]:
    H = Hechos()
    ir_t = meta.get("ir_t")

    # ---------------------------------------------------- 1. conciliacion ---
    if conc:
        R = conc["resumen"]
        if R.get("materiales"):
            H.add(CRITICO, "conciliación",
                  "El diario no cuadra con los saldos del expediente",
                  [f"{R['materiales']} grupos de cuenta descuadran por encima del "
                   f"umbral de materialidad ({eur(conc['umbral_trivial'])}). Mientras "
                   "no se resuelvan, cualquier cifra de este panel puede contradecir "
                   "a los papeles de trabajo."],
                  [f"{R['materiales']} descuadres materiales",
                   f"{pct(conc['pct_volumen_conciliado'])} del volumen conciliado"],
                  "conciliacion")
        else:
            H.add(CORRECTO, "conciliación",
                  "El diario analizado es el que sostiene los saldos del expediente",
                  [f"{R.get('conformes', 0)} grupos de cuenta coinciden al céntimo y "
                   f"{R.get('conformes_saldo_cero', 0)} más tienen movimiento con saldo "
                   "cero al cierre. Ningún descuadre, ni material ni trivial.",
                   "Se excluyen del cuadre las cuentas que Gesia calcula y el diario no "
                   "lleva ("
                   + ", ".join(conc.get("calculadas_excluidas", [])) + ")."],
                  [f"{pct(conc['pct_volumen_conciliado'])} del volumen conciliado",
                   f"{R.get('triviales', 0)} descuadres triviales"],
                  "conciliacion")

    # ------------------------------------------------------- 2. resultado ---
    r = resultado
    if r.get("gesia_08") is not None and r.get("cuadra") is False:
        H.add(CRITICO, "resultado",
              "El resultado del diario no coincide con la cuenta 08",
              [f"El diario da {eur2(r['diario'])} y el expediente "
               f"{eur2(r['gesia_08'])}. El panel contradice al expediente."],
              [f"Desfase {eur2(r['diario'] - r['gesia_08'])}"], "conciliacion")

    if r.get("anterior") not in (None, 0):
        var = (r["diario"] / r["anterior"] - 1) * 100
        if abs(var) >= 50:
            sube = var > 0
            H.add(MEDIO, "tendencia",
                  f"El resultado {'se multiplica' if sube else 'se desploma'} "
                  f"respecto al ejercicio anterior",
                  [f"De {eur(r['anterior'])} a {eur(r['diario'])}, "
                   f"{'+' if sube else ''}{pct(var, 0)}. Una variación de este tamaño "
                   "es el primer hecho del ejercicio que hay que explicar: conviene "
                   "identificar qué cuentas la producen antes de dar el resultado por "
                   "bueno."],
                  [f"{'+' if sube else ''}{pct(var, 0)} interanual",
                   f"Anterior {eur(r['anterior'])}"], "conciliacion")

    # --------------------------------------------- 3. ajustes de auditoria ---
    if r.get("ajustes") is not None and conc:
        aj = [g for g in conc["grupos"] if abs(g.get("ajuste", 0)) > 0.01]
        movido = sum(abs(g["ajuste"]) for g in aj) / 2
        if movido > 0:
            rel = (movido / ir_t * 100) if ir_t else None
            sev = ALTO if (rel is None or rel >= 100) else (MEDIO if rel >= 25 else BAJO)
            H.add(sev, "ajustes",
                  "Los ajustes propuestos por auditoría son materiales",
                  [f"{len(aj)} cuentas llevan ajuste, por un importe de {eur(movido)}"
                   + (f", el {pct(rel, 0)} de la importancia relativa" if rel else "")
                   + f". El resultado pasaría de {eur(r['diario'])} a "
                   + (eur(r['auditoria']) if r.get("auditoria") is not None else "—")
                   + ".",
                   "El neto de los ajustes es cero porque cada asiento cuadra por sí "
                   "mismo; la cifra que mide su tamaño es el importe movido."],
                  [f"{eur(movido)} de ajustes"]
                  + ([f"{pct(rel, 0)} de IR_T"] if rel else [])
                  + [f"{len(aj)} cuentas"], "conciliacion")

        imp = _grupo(conc, "630")
        if imp and abs(imp.get("ajuste", 0)) > (ir_t or 0) * 0.25:
            H.add(ALTO, "impuesto",
                  "El impuesto sobre beneficios lo pone la auditoría, no el cliente",
                  [f"La cuenta 630 tiene un saldo de cliente de "
                   f"{eur2(imp['gesia'])} y un ajuste propuesto de "
                   f"{eur2(imp['ajuste'])}. Es decir, el gasto por impuesto "
                   "practicamente no está contabilizado y sale del trabajo de "
                   "auditoría."],
                  [f"Saldo cliente {eur2(imp['gesia'])}",
                   f"Ajuste {eur2(imp['ajuste'])}"], "conciliacion")

    # --------------------------------------------------------- 4. punteo ----
    if punt and punt.get("punteo"):
        R = punt["resumen"]
        insuf = R.get("grupos_cobertura_insuficiente", [])
        if insuf:
            saldos = []
            for g in insuf:
                gg = _grupo(conc, g) if conc else None
                if gg and abs(gg.get("gesia", 0)) > (ir_t or 0):
                    saldos.append((g, gg))
            if saldos:
                detalle = "; ".join(
                    f"{g} {gg.get('nombre', '')} ({eur(gg['gesia'])})"
                    for g, gg in saldos[:4])
                H.add(MEDIO, "punteo",
                      "Hay saldos materiales sobre los que el punteo no permite concluir",
                      [f"En {detalle}, la cobertura del punteo no llega al "
                       f"{pct(punt['umbral_cobertura'], 0)}. Ahí «no punteado» no "
                       "equivale a «pendiente»: puede significar simplemente que nadie "
                       "lo punteó. El panel muestra la distribución por antigüedad pero "
                       "no publica el saldo como cifra.",
                       "Si esas cuentas importan para el encargo, la vía es reimportar "
                       "el diario con el punteo completo o revisarlas por otro "
                       "procedimiento."],
                      [f"{len(insuf)} grupos por debajo del umbral"]
                      + [f"{g}: {eur(gg['gesia'])}" for g, gg in saldos[:2]],
                      "punteo")

        lentos = [p for p in punt.get("plazos", [])
                  if p.get("muestra_suficiente") and p.get("maximo", 0) > 180]
        if lentos:
            peor = max(lentos, key=lambda p: p["maximo"])
            H.add(BAJO, "punteo",
                  "Hay partidas que tardan más de medio año en cancelarse",
                  [f"En el grupo {peor['grupo']} la mediana es de "
                   f"{n(peor['mediana'])} días, pero el máximo llega a "
                   f"{n(peor['maximo'])}. Son, según el punteo automático de Gesia, "
                   "una lista de revisión y no una medida contable."],
                  [f"Mediana {n(peor['mediana'])} d",
                   f"Máximo {n(peor['maximo'])} d",
                   f"{n(peor['grupos'])} partidas"], "punteo")

        if R.get("punteos_masivos"):
            H.add(BAJO, "punteo",
                  "Una parte del punteo es la cuenta neteándose consigo misma",
                  [f"{R['punteos_masivos']} grupos absorben más de la mitad de las "
                   "líneas de su cuenta. No son emparejamientos de partidas y su "
                   "«plazo» es solo la duración del ejercicio, así que quedan fuera de "
                   "los plazos de liquidación. Sus líneas sí cuentan como canceladas."],
                  [f"{R['punteos_masivos']} grupos excluidos"], "punteo")
    elif punt is not None:
        H.add(ALTO, "punteo",
              "El diario se importó sin punteo, y eso recorta el panel",
              ["Sin punteo no hay plazos reales de liquidación ni antigüedad de "
               "partidas abiertas. Reimportar el diario en Gesia con la opción de "
               "punteo activada —y también la de apertura, de la que depende— añade "
               "esas dos secciones."], [], "punteo")

    if meta["opciones"]["punteo"] and not meta["opciones"]["aging_publicable"]:
        H.add(ALTO, "punteo",
              "La antigüedad de partidas abiertas está suprimida",
              ["Hay punteo pero no hay apertura verificada. Los pagos que cancelan "
               "facturas del ejercicio anterior se quedan sin contrapartida y "
               "aparecerían como abiertos, de modo que la antigüedad estaría "
               "sobreestimada de forma sistemática. Se prefiere no publicarla."],
              [], "punteo")

    # ------------------------------------------------------ 5. atipicos ----
    if diario:
        A = diario.get("atipicos", {})
        tot = (A.get("marcados") or {}).get("totales", {})

        if A.get("materiales"):
            H.add(MEDIO, "importes",
                  "Hay apuntes que por sí solos superan la importancia relativa",
                  [f"{n(A['materiales'])} apuntes individuales por encima de "
                   + (eur(ir_t) if ir_t else "IR_T")
                   + ". Cada uno merece soporte documental propio."],
                  [f"{n(A['materiales'])} apuntes"], "atipicos")

        cr = [c for c in A.get("contrapartidas_raras", [])
              if ir_t and c.get("importe_mayor_asiento", 0) >= ir_t]
        if cr:
            c0 = cr[0]
            H.add(MEDIO, "operaciones singulares",
                  "Aparecen operaciones que no se repiten en todo el ejercicio",
                  [f"La combinación de cuentas {c0['debe']} → {c0['haber']} aparece "
                   f"{c0['veces']} vez/veces, con un asiento de "
                   f"{eur(c0['importe_mayor_asiento'])} (asiento {c0['ejemplo']}). "
                   "Las contrapartidas que no se repiten suelen ser el préstamo, el "
                   "ajuste de existencias o la operación singular del año — "
                   "exactamente lo que hay que mirar a mano."],
                  [f"{len(cr)} combinaciones materiales",
                   f"Mayor {eur(c0['importe_mayor_asiento'])}"], "atipicos")

        fds = tot.get("fin de semana", {}).get("apuntes", 0)
        if fds:
            share = fds / meta["apuntes"] * 100
            H.add(MEDIO if share >= 2 else BAJO, "calendario",
                  "Parte del diario se registra en fin de semana",
                  [f"{n(fds)} apuntes ({pct(share)}) caen en sábado o domingo, por "
                   + eur(tot['fin de semana']['importe']) + ". "
                   "El panel no juzga si eso es normal: en un negocio que abre el fin "
                   "de semana lo es, y en una oficina no. **Si no encaja con la "
                   "actividad del cliente, esta cifra es en sí misma el hallazgo.**",
                   "Lo que sí se marca por separado son los días que se salen de la "
                   "distribución del propio cliente, en la sección de actividad."],
                  [f"{n(fds)} apuntes", pct(share),
                   eur(tot["fin de semana"]["importe"])], "atipicos")

        da = [d for d in diario.get("dias_atipicos", []) if not d.get("fin_de_mes")]
        if da:
            H.add(BAJO, "calendario",
                  "Hay días de actividad anómala que no son cierre de mes",
                  [f"De los {len(diario.get('dias_atipicos', []))} días que se salen "
                   f"de la distribución de su propio día de la semana, {len(da)} no "
                   "coinciden con el último día natural del mes. El resto se explica "
                   "por el cierre mensual."],
                  [f"{len(da)} días a revisar"], "actividad")

        neg = next((h for h in contrato.get("hallazgos", [])
                    if h.get("codigo") == "C05"), None)
        if neg:
            d = neg.get("datos", {})
            H.add(MEDIO, "medición",
                  "Hay abonos anotados en la columna contraria",
                  [f"{n(d.get('apuntes', 0))} apuntes con Debe o Haber negativo. "
                   "Medir el volumen como Debe+Haber los resta y deja el total "
                   + eur(abs(d.get("desfase_bruto_vs_neto", 0)))
                   + " por debajo de la realidad, así que todo este panel mide en "
                   "neto (Debe − Haber)."],
                  [f"{n(d.get('apuntes', 0))} apuntes",
                   f"Desfase {eur(abs(d.get('desfase_bruto_vs_neto', 0)))}"],
                  "contrato")

        bf = A.get("benford", {})
        if bf.get("aplicable") and bf.get("ajuste") in ("dudoso", "NO CONFORME"):
            d0 = bf["digitos_mas_desviados"][0]
            H.add(BAJO, "distribución de importes",
                  "La distribución del primer dígito no se ajusta a Benford",
                  [f"Desviación media absoluta de {bf['mad']:.5f}".replace(".", ",")
                   + f" sobre {n(bf['importes'])} importes: ajuste {bf['ajuste']}. "
                   f"El dígito {d0['digito']} aparece en el {pct(d0['observado_pct'])} "
                   f"de los casos frente al {pct(d0['esperado_pct'])} esperado.",
                   "La no conformidad no es por sí misma un indicio de manipulación: "
                   "en un negocio con importes repetidos —cobros diarios, cuotas "
                   "fijas— es frecuente. Es una pregunta que hacer, no una "
                   "conclusión."],
                  [f"MAD {bf['mad']:.5f}".replace(".", ","), bf["ajuste"]], "atipicos")

        if A.get("duplicados"):
            H.add(ALTO, "duplicidad",
                  "Hay apuntes duplicados por encima del umbral de interés",
                  [f"{n(A['duplicados'])} grupos de apuntes idénticos —misma fecha, "
                   "cuenta, importe y concepto— en asientos distintos."],
                  [f"{n(A['duplicados'])} grupos"], "atipicos")
        else:
            H.add(CORRECTO, "duplicidad", "No hay apuntes duplicados relevantes",
                  ["Ningún grupo de apuntes idénticos por encima del umbral de "
                   "interés en asientos distintos."], [], "atipicos")

    # ------------------------------------------------- 6. contrato del diario ---
    if contrato:
        codigos = {h["codigo"]: h for h in contrato.get("hallazgos", [])}
        buenos = [c for c in ("C10", "C11", "C12", "C13", "C16")
                  if codigos.get(c, {}).get("nivel") == "OK"]
        if len(buenos) >= 4:
            H.add(CORRECTO, "integridad",
                  "La integridad formal del diario es correcta",
                  ["Cuadre global exacto, todos los asientos cuadran individualmente, "
                   "numeración numérica, grabación en orden cronológico estricto y el "
                   "campo SALDO coherente con Debe − Haber en todos los apuntes.",
                   "Estas cinco comprobaciones se ejecutan antes de calcular un solo "
                   "indicador; si alguna hubiera fallado, este panel no existiría."],
                  [f"{len(buenos)} de 5 comprobaciones conformes",
                   f"{n(meta['asientos'])} asientos"], "contrato")

    return H.ordenados()
