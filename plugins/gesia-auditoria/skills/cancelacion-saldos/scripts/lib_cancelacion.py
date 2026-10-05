"""Emparejamiento de saldos (facturas vs pagos) para el mayor de una cuenta
de un expediente de auditoria de Gesia.

No imprime: devuelve datos. Quien llama (verificar_contrato.py,
generar_papel.py) decide que hacer con ellos.

PUNTEO PREVIO. Muchos .smn traen la columna `Indice`: el punteo hecho en la
contabilidad o en Gesia, numerado POR CUENTA (la clave es CUENTA+Indice; ver
docs/contrato-datos.md). Cuando el extracto la trae, se respeta: los apuntes
con indice previo > 0 son grupos ya cancelados, no entran al emparejamiento,
y los indices que asigna este modulo arrancan por encima del maximo previo
de la cuenta. Cada grupo previo se verifica igualmente (¿suma 0?): si no
suma, SE AVISA PERO SE RESPETA -- la contabilidad del cliente manda y el
auditor decide. Si la columna no existe (es una opcion de importacion que
falta con normalidad), el emparejamiento parte de cero, como siempre.

Procedimientos (2.1 a 2.4 del encargo original que dio pie a este skill),
aplicados cuenta por cuenta SOBRE LOS APUNTES SIN PUNTEAR:

  2.1  si todo lo pendiente suma 0, un solo INDICE para esos apuntes.
  2.2  si no, pero el total pendiente coincide con el saldo del ULTIMO
       apunte pendiente en orden cronologico, se cancela todo menos ese
       ultimo (que queda como saldo pendiente, INDICE 0).
  2.3  cancelacion directa: apuntes de igual importe absoluto y signo
       contrario se emparejan 1 a 1, sin mirar la fecha.
  2.4  lo que queda se intenta cancelar en orden cronologico, acumulando
       SALDO hasta que de 0 (agrupacion secuencial: cualquier tramo
       contiguo en el tiempo que sume 0 se cierra como grupo). Lo que
       sigue sin cancelar se intenta con combinaciones acotadas (hasta
       MAX_GRUPO_COMBOS apuntes a la vez) buscando subconjuntos --no
       necesariamente contiguos en fecha-- que sumen 0.

Lo que este modulo NO hace: no usa el texto de CONCEPTO para decidir que
apuntes van juntos, aunque el encargo original lo menciona como señal de
apoyo ("por alguna similitud en el campo CONCEPTO"). Se decidio no
implementarlo: es un emparejamiento difuso sin regla objetiva de cuando
aceptar una coincidencia de texto, y el criterio numerico (fecha + importe)
ya resolvio sin ambiguedad el caso real usado para calibrar esto (una
cuenta de clientes del expediente de calibracion: 46 de 46 grupos
correctos).
CONCEPTO se conserva en el informe para que el auditor lo lea, no para que
el algoritmo decida por el. Tampoco usa los campos NN_*: pueden no existir
y su semantica no esta garantizada entre expedientes.

La busqueda combinatoria del 2.4 es un backstop, no magia: sobre cuentas
con muchos apuntes sin cancelar por los pasos anteriores, buscar
subconjuntos que sumen 0 crece muy rapido (es un subset-sum), asi que se
acota a MAX_LEFTOVER_FOR_COMBOS apuntes de entrada y grupos de hasta
MAX_GRUPO_COMBOS. Por encima de eso, sencillamente no se intenta y esos
apuntes quedan en INDICE 0 -- no es un fallo silencioso: verificar_contrato
avisa cuando una cuenta es lo bastante grande para que esto importe.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import pandas as pd

TOL = 0.005                    # tolerancia de redondeo en euros
MAX_LEFTOVER_FOR_COMBOS = 22   # por encima de esto, no se intenta la combinatoria
MAX_GRUPO_COMBOS = 6           # tamaño maximo de grupo que se busca por combinacion
MAX_PAGOS_APERTURA = 14        # candidatos que se prueban por combinacion al cancelar
                               # la apertura. 14 sobre grupos de hasta 6 son 3.003
                               # subconjuntos: instantaneo, y en el caso medido la
                               # apertura se cancela con los pagos de enero, que
                               # siempre caen dentro de esos primeros candidatos

# CONCEPTO ya no es obligatorio (10/09/2026, rama confidencialidad). Es texto
# libre con nombres, matriculas y referencias, y el emparejamiento NO lo usa: lo
# lee el auditor en el papel. Asi que si el auditor decide que no salga de su
# maquina, el extracto viene sin el y todo tiene que seguir funcionando. Lo que
# NO puede pasar es que su ausencia degrade algo en silencio: ver
# analizar_hallazgos, donde sin concepto la fecha del documento no existe y los
# «pagos anteriores a su factura» se dejan SIN EVALUAR en vez de calcularse mal.
COLUMNAS_REQUERIDAS = ("FECHA", "CUENTA", "NOMBRE")

# valores de la columna ORIGEN del resultado. Para los grupos que asigna este
# modulo, ORIGEN dice EL PASO que los formo: un grupo de 26 apuntes por
# «acumulación» merece otra mirada que uno de 3 por «documento», y hasta la prueba
# en frio del 10/09/2026 el papel no lo distinguia (todo decia «auditoría»).
ORIGEN_CONTABLE = "contable"     # el grupo venia punteado en el .smn (Indice)
ORIGEN_AUDITORIA = "auditoría"   # respaldo: grupo de este modulo sin paso anotado
PASO_DOCUMENTO = "documento"     # 2.0  mismo numero de documento, suma cero
PASO_APERTURA = "apertura"       # 2.2b/2.2c la apertura y lo que la cancela
PASO_TOTAL = "total"             # 2.1/2.2 lo pendiente suma cero (o menos el ultimo)
PASO_IMPORTE = "importe"         # 2.3  mismo importe, signo contrario
PASO_ACUMULACION = "acumulación" # 2.4a tramo cronologico que suma cero
PASO_COMBINACION = "combinación" # 2.4b subconjunto acotado que suma cero
PASOS_ORIGEN = (PASO_DOCUMENTO, PASO_APERTURA, PASO_TOTAL, PASO_IMPORTE,
                PASO_ACUMULACION, PASO_COMBINACION)


def _round2(v) -> float:
    return round(float(v), 2)


def _columnas_documento(columnas) -> list:
    """TODAS las columnas candidatas a numero de documento, por orden de prioridad
    de nombre. Un diario puede traer dos -NN_Factura y NN_Documento, medido el
    10/09/2026- y entonces no decide el nombre: decide cuantos grupos cierra cada
    una (ver cargar_extracto). NumeroEnConcepto va la ultima y solo cuenta si no
    hay ninguna del diario."""
    def norm(c):
        return str(c).strip().lower().replace("nn_", "").replace("_", "").replace(" ", "")
    exactas = ("factura", "nfactura", "numfactura", "numerofactura", "nrofactura",
               "documento", "numdocumento", "numerodocumento", "ndocumento")
    # en orden de PRIORIDAD DE NOMBRE (factura antes que documento), no en el orden
    # del SELECT: es el desempate cuando dos candidatas cierran lo mismo
    out = sorted((c for c in columnas if norm(c) in exactas), key=lambda c: exactas.index(norm(c)))
    for c in columnas:
        k = norm(c)
        if c not in out and ("factura" in k or "documento" in k) and not any(
                x in k for x in ("fecha", "importe", "base", "total", "tipo", "clase")):
            out.append(c)
    return out


def _puntuar_documento(df, col) -> tuple:
    """(grupos de 2+ apuntes, cuantos suman cero, apuntes con valor) agrupando por
    CUENTA y por el valor de la columna: la misma prueba que aplica el paso 2.0.
    El tercer numero distingue «columna vacia en este extracto» de «columna llena
    que no cierra nada», que son diagnosticos distintos (registro del 10/09/2026)."""
    k = df[col].fillna("").astype(str).str.strip().replace({"0": "", "nan": "", "None": ""})
    d = df.assign(_K=k)[k != ""]
    if d.empty:
        return 0, 0, 0
    g = d.groupby(["CUENTA", "_K"])["SALDO"].agg(["size", "sum"])
    g = g[g["size"] >= 2]
    return int(len(g)), int((g["sum"].abs() < TOL).sum()), int(len(d))


def _columna_documento(columnas) -> str | None:
    """La columna del numero de factura, se llame como se llame, o None.

    El nombre no esta normalizado: NN_Factura en un .smn, NN_NumFactura o
    Factura o Documento en otro (David, 10/09/2026). Se busca por lo que dice el
    nombre, no por una lista cerrada: contiene «factura» o «documento», y no es
    una fecha ni un importe. Si hay varias candidatas gana la que mas se parece a
    lo conocido, y la eleccion se ve en el papel porque la columna sale con su
    nombre original en el reconocimiento.
    """
    def norm(c):
        return str(c).strip().lower().replace("nn_", "").replace("_", "").replace(" ", "")
    exactas = ("factura", "nfactura", "numfactura", "numerofactura", "nrofactura",
               "documento", "numdocumento", "numerodocumento", "ndocumento")
    for c in columnas:
        if norm(c) in exactas:
            return c
    for c in columnas:
        k = norm(c)
        if ("factura" in k or "documento" in k) and not any(
                x in k for x in ("fecha", "importe", "base", "total", "tipo", "clase")):
            return c
    # Y con MENOR prioridad que cualquier columna del diario: el numero que el MCP
    # deriva en local del concepto (NumeroEnConcepto, docs/confidencialidad.md,
    # ticket 1). Medido el 10/09/2026 en seis diarios: donde hay NN_Factura, el
    # 98% de sus grupos suman cero; el derivado del concepto, el 78-90%. Con los
    # dos, manda la columna; el derivado es para los diarios que no la traen, que
    # son cuatro de siete.
    for c in columnas:
        if norm(c) == "numeroenconcepto":
            return c
    return None


def cargar_extracto(ruta) -> pd.DataFrame:
    """Carga el fichero que exporta Gesia con exportar_consulta: .csv con
    ';' como separador, o .json. Si no trae SALDO pero si DEBE/HABER, lo
    deriva como DEBE-HABER -- que es, comprobado sobre el diario real, el
    mismo importe con signo que Gesia guarda en su columna SALDO/NN_Saldo
    para cada apunte (no es un saldo acumulado, pese al nombre).

    Si trae la columna del punteo previo (`Indice`, en cualquier
    capitalizacion), la normaliza a INDICE_PREVIO: entero, sin negativos,
    0 = sin puntear. Es OPCIONAL: su ausencia no es un error.

    Lanza ValueError si faltan columnas obligatorias -- no adivina nombres
    de campo alternativos: eso lo decide quien llama (o el auditor, si el
    extracto viene de otro sitio).
    """
    ruta = Path(ruta)
    if not ruta.exists():
        raise FileNotFoundError(str(ruta))

    if ruta.suffix.lower() == ".json":
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        df = pd.DataFrame(datos)
    else:
        df = pd.read_csv(ruta, sep=";")

    faltan = [c for c in COLUMNAS_REQUERIDAS if c not in df.columns]
    if faltan:
        raise ValueError("faltan columnas obligatorias: " + str(faltan))

    if "SALDO" not in df.columns:
        if "DEBE" in df.columns and "HABER" in df.columns:
            df["SALDO"] = (
                pd.to_numeric(df["DEBE"], errors="coerce").fillna(0)
                - pd.to_numeric(df["HABER"], errors="coerce").fillna(0)
            )
        else:
            raise ValueError("no hay columna SALDO ni DEBE/HABER para derivarla")

    # El NUMERO DE DOCUMENTO, tambien OPCIONAL. En el diario de Gesia es
    # NN_Factura; el extracto puede traerlo con ese nombre o ya renombrado.
    # "0" y vacio significan «sin factura» y se normalizan a "", que es lo que
    # el paso 2.0 ignora.
    # Si hay VARIAS candidatas en el diario, no decide el orden del SELECT: se
    # puntua cada una por grupos que suman cero -la prueba del paso 2.0- y gana la
    # que mas cierra. La comparacion se guarda para que el reconocimiento y el papel
    # la digan. NumeroEnConcepto solo entra si no hay ninguna del diario (David,
    # 10/09/2026: la columna del diario manda sobre el derivado).
    candidatas = _columnas_documento(df.columns)
    comparacion = []
    if len(candidatas) > 1:
        for c in candidatas:
            grupos, cerrados, con_valor = _puntuar_documento(df, c)
            comparacion.append((c, grupos, cerrados, con_valor))
        # se mide sobre ESTE extracto: la misma columna puede estar llena en un grupo
        # de cuentas y vacia en otro del mismo diario (medido el 10/09/2026)
        comparacion.sort(key=lambda t: (-t[2], -(t[2] / t[1] if t[1] else 0)))
        col_fra = comparacion[0][0]
    else:
        col_fra = _columna_documento(df.columns)
    fuente_documento = col_fra
    if col_fra is not None:
        df["FACTURA"] = (df[col_fra].fillna("").astype(str).str.strip()
                         .replace({"0": "", "nan": "", "None": ""}))
        sobrantes = [c for c in candidatas if c != "FACTURA" and c in df.columns] \
            + ([col_fra] if col_fra != "FACTURA" and col_fra not in candidatas else [])
        if sobrantes:
            df = df.drop(columns=sobrantes)

    col_prev = next(
        (c for c in df.columns
         if str(c).strip().lower() in ("indice", "índice", "indice_previo")),
        None,
    )
    if col_prev is not None:
        df["INDICE_PREVIO"] = (
            pd.to_numeric(df[col_prev], errors="coerce")
            .fillna(0).astype(int).clip(lower=0)
        )
        if col_prev != "INDICE_PREVIO":
            df = df.drop(columns=[col_prev])

    # LA FECHA DEL DOCUMENTO, tambien opcional, y con dos origenes por este orden:
    # la que el MCP deriva en local del concepto (FechaEnConcepto: el texto no sale
    # del equipo, la fecha si), o, si el auditor autorizo que el concepto viajara y
    # el MCP no la derivo -version antigua-, leida aqui del propio CONCEPTO con la
    # misma regla. Se normaliza a FECHA_DOC y el resto del skill no sabe de donde
    # vino; el papel si lo dice.
    fuente_fecha_doc = None
    col_fdoc = next((c for c in df.columns
                     if str(c).strip().lower() == "fechaenconcepto"), None)
    if col_fdoc is not None:
        df["FECHA_DOC"] = pd.to_datetime(df[col_fdoc], errors="coerce")
        if col_fdoc != "FECHA_DOC":
            df = df.drop(columns=[col_fdoc])
        fuente_fecha_doc = "FechaEnConcepto"
    elif "CONCEPTO" in df.columns:
        df["FECHA_DOC"] = pd.to_datetime(df["CONCEPTO"].map(_fecha_desde_concepto),
                                         errors="coerce")
        fuente_fecha_doc = "CONCEPTO"

    df["FECHA"] = pd.to_datetime(df["FECHA"], errors="coerce", dayfirst=False)
    df["SALDO"] = pd.to_numeric(df["SALDO"], errors="coerce")
    df["CUENTA"] = df["CUENTA"].astype(str)
    df["NOMBRE"] = df["NOMBRE"].fillna("").astype(str)
    if "CONCEPTO" in df.columns:
        df["CONCEPTO"] = df["CONCEPTO"].fillna("").astype(str)

    # ORDEN PROPIO, sin fiarse de quien llame. El pareo directo recorre las
    # filas en el orden en que vienen, asi que un ORDER BY distinto en la
    # consulta daba un papel distinto con el MISMO dato. Medido el 31/08/2026
    # sobre un expediente real: por FECHA salian 45 hallazgos, por ASIENTO 49
    # y en orden inverso 53, y hasta el importe de apertura vivo cambiaba.
    #
    # La clave es solo de datos -no incluye el indice de entrada-, asi que dos
    # extractos con las mismas filas dan el mismo papel aunque lleguen en
    # cualquier orden. Es lo que hace que el papel se pueda regenerar.
    clave = [c for c in ("CUENTA", "FECHA", "ASIENTO", "SALDO", "CONCEPTO")
             if c in df.columns]
    df = df.sort_values(clave, kind="mergesort").reset_index(drop=True)
    # de donde salieron el numero y la fecha del documento: lo dicen el papel y
    # el reconocimiento, para que el auditor sepa que se esta fiando de una
    # columna del diario o de un texto leido
    df.attrs["fuente_documento"] = fuente_documento
    df.attrs["fuente_fecha_doc"] = fuente_fecha_doc
    df.attrs["candidatas_documento"] = comparacion   # [(columna, grupos, cerrados, apuntes con valor)], vacio si solo habia una
    return df


def _indice_apertura(df: pd.DataFrame):
    """El apunte de apertura de lo que sigue pendiente, o None.

    Se reconoce POR ESTRUCTURA, no por el texto del concepto: es del 1 de enero
    -no puede haber saldo anterior a eso- y es el apunte mas antiguo de los que
    quedan. Y tiene que ser el UNICO de ese dia, porque si hay varios no se sabe
    cual es la apertura. Lo usan el 2.2c y el 2.2b, y por eso vive aparte: dos
    copias de esta regla acabarian divergiendo.
    """
    pend = df[df["INDICE"] == 0].sort_values("FECHA")
    if len(pend) < 2:
        return None
    primero = pend.index[0]
    del_dia_1 = pend[(pend["FECHA"].dt.month == 1) & (pend["FECHA"].dt.day == 1)]
    if len(del_dia_1) == 1 and del_dia_1.index[0] == primero:
        return primero
    return None


def _indice_apertura_informe(res: pd.DataFrame):
    """La apertura de una cuenta YA emparejada, con la misma regla del algoritmo.

    _indice_apertura mira solo lo que sigue pendiente, porque es lo que necesita el
    emparejamiento. Para informar hace falta verla tambien cuando ya se cancelo, asi
    que la regla se aplica sobre la cuenta entera: 1 de enero, el mas antiguo, y el
    UNICO de ese dia. La regla es la misma; el conjunto sobre el que se aplica, no.
    """
    if len(res) < 2:
        return None
    orden = res.sort_values("FECHA")
    primero = orden.index[0]
    del_dia_1 = orden[(orden["FECHA"].dt.month == 1) & (orden["FECHA"].dt.day == 1)]
    if len(del_dia_1) == 1 and del_dia_1.index[0] == primero:
        return primero
    return None


def _emparejar_pendientes(df: pd.DataFrame, next_idx: int) -> int:
    """Aplica 2.0-2.4 a un df cuyos apuntes vienen TODOS con INDICE 0,
    mutando INDICE, GRUPO_24 y GRUPO_APERTURA sobre sus etiquetas de indice (que no tienen
    por que ser 0..n: puede ser el subconjunto sin puntear de una cuenta).
    Devuelve el primer indice libre tras asignar.
    """
    # --- 2.0: grupos por NUMERO DE FACTURA, aceptados solo si suman cero ---
    # La clave con la que el propio auditor empareja a mano. En su papel de un
    # expediente real la columna «Factura» ata una compra de 2.743,70 con sus
    # TRES pagos a 30, 60 y 90 dias (914,48 + 914,48 + 914,74), y eso no lo
    # alcanza ningun criterio de importes: los pagos no se parecen a la factura
    # ni entre si. La combinatoria de 2.4b tampoco, y no por el tope: buscar
    # subconjuntos de hasta 6 entre los 135 apuntes que quedaban sueltos en esa
    # cuenta son mas de 7.000 millones de combinaciones. Agrupar por documento
    # no busca: particiona.
    #
    # LA REGLA, y es la que hace que esto no sea adivinar: **el numero PROPONE
    # y la suma DECIDE.** Un grupo se acepta solo si sus apuntes suman cero. Si
    # el campo viniera sucio, repetido entre ejercicios o significase otra cosa,
    # ningun grupo cerraria y el resultado seria identico a no haberlo mirado.
    # El numero no es autoridad: solo dice por donde empezar a sumar.
    #
    # Por eso NO contradice la decision de descartar CONCEPTO como senal (ver
    # DISENO.md): aquello era pareo difuso de texto sin regla objetiva de
    # aceptacion. Aqui la regla es exacta y es la misma de siempre, sumar cero.
    if "FACTURA" in df.columns:
        pend_fra = df[(df["INDICE"] == 0) & (df["FACTURA"] != "")]
        for _, grupo in pend_fra.groupby("FACTURA", sort=True):
            if len(grupo) < 2:
                continue
            if abs(_round2(grupo["SALDO"].sum())) < TOL:
                df.loc[grupo.index, "INDICE"] = next_idx
                df.loc[grupo.index, "GRUPO_FACTURA"] = True
                df.loc[grupo.index, "PASO"] = PASO_DOCUMENTO
                next_idx += 1

    # --- 2.2c: la APERTURA contra los pagos de facturas ajenas al ejercicio ---
    # Matar la apertura es lo que mas vale del procedimiento, y el 2.2b no llegaba:
    # busca subconjuntos de hasta 6 pagos entre los 14 primeros, y en la cuenta que
    # motivo esto hacian falta 24. Con el numero de documento no hay que buscar.
    #
    # EL RAZONAMIENTO: despues del 2.0, un apunte que sigue pendiente, que lleva
    # numero de factura, cuyo grupo de ese numero NO cierra, y que va en sentido
    # contrario a la apertura, es un PAGO cuya factura no esta en este ejercicio.
    # Y si no esta en el ejercicio, esta dentro de la apertura: es del anterior.
    # No hay que adivinarlo, se deduce de que falte.
    #
    # Sigue decidiendo la suma: el grupo se acepta solo si apertura + esos pagos da
    # cero. Medido en un expediente real, tres cuentas cerraron al centimo.
    #
    # EL HUECO DE LOS CENTIMOS: cuando no cierra, se admite UN solo apunte mas -sin
    # numero de factura- cuyo importe sea exactamente el hueco que falta. Es la
    # regularizacion de saldos de fin de ejercicio, que en ese expediente valia
    # -2,65 en una cuenta y -136,50 en otra. Uno solo y exacto: nada de buscar
    # combinaciones ni de tolerar diferencias, que eso es materialidad y la decide
    # el auditor.
    if "FACTURA" in df.columns:
        ap = _indice_apertura(df)
        if ap is not None:
            saldo_ap = _round2(df.loc[ap, "SALDO"])
            signo_pago = -1 if saldo_ap > 0 else 1
            pend = df[(df["INDICE"] == 0) & (df.index != ap)]
            # los grupos de numero que NO cierran, y solo por el lado del pago
            huerfanos = []
            con_fra = pend[pend["FACTURA"] != ""]
            for _, g in con_fra.groupby("FACTURA", sort=True):
                if abs(_round2(g["SALDO"].sum())) < TOL:
                    continue          # ese ya lo habria cogido el 2.0
                if all(signo_pago * v > TOL for v in g["SALDO"]):
                    huerfanos += list(g.index)
            if huerfanos:
                suma = _round2(saldo_ap + sum(df.loc[huerfanos, "SALDO"]))
                grupo = list(huerfanos)
                if abs(suma) >= TOL:
                    # el hueco: un unico apunte sin factura que lo cierre exacto
                    resto = pend[(pend["FACTURA"] == "") & (~pend.index.isin(huerfanos))]
                    cierra = [i for i in resto.index
                              if abs(_round2(df.loc[i, "SALDO"] + suma)) < TOL]
                    if len(cierra) >= 1:
                        grupo.append(cierra[0])
                        suma = _round2(suma + df.loc[cierra[0], "SALDO"])
                if abs(suma) < TOL:
                    for x in [ap] + grupo:
                        df.loc[x, "INDICE"] = next_idx
                        df.loc[x, "GRUPO_APERTURA"] = True
                        df.loc[x, "PASO"] = PASO_APERTURA
                    next_idx += 1

    # A partir de aqui, todo va sobre lo que SIGUE pendiente. Cuando el extracto
    # no trae numero de documento -o ningun grupo cerraba-, esto es el df
    # entero y el comportamiento es exactamente el de antes.
    pend_idx = df.index[df["INDICE"] == 0]
    if len(pend_idx) == 0:
        return next_idx
    total = _round2(df.loc[pend_idx, "SALDO"].sum())

    # --- 2.1: si el total pendiente ya es cero, todo un solo indice ---
    if abs(total) < TOL:
        df.loc[pend_idx, "INDICE"] = next_idx
        df.loc[pend_idx, "PASO"] = PASO_TOTAL
        return next_idx + 1

    # --- 2.2: si el total coincide con el saldo del ULTIMO apunte
    #          (orden cronologico), cancelar todos menos ese ---
    orden_fecha = df.loc[pend_idx].sort_values(["FECHA"]).index.tolist()
    ultimo_idx = orden_fecha[-1]
    ultimo_saldo = _round2(df.loc[ultimo_idx, "SALDO"])

    if abs(total - ultimo_saldo) < TOL and len(orden_fecha) > 1:
        resto = [i for i in orden_fecha if i != ultimo_idx]
        df.loc[resto, "INDICE"] = next_idx
        df.loc[resto, "PASO"] = PASO_TOTAL
        return next_idx + 1  # el ultimo se queda con INDICE 0 (pendiente)

    # --- 2.2b: la apertura primero ---------------------------------------
    # Matar el saldo de apertura es el objetivo del procedimiento, y hasta
    # ahora la apertura era un apunte mas: el pareo directo de 2.3 se llevaba
    # sus pagos antes de que nadie mirase si servian para eso, y la apertura
    # se quedaba viva. Medido el 30/08/2026 en las cuentas 40 y 41 de un
    # expediente real: 74 aperturas sin cancelar por 169.332 EUR; con este
    # paso, 67 por 49.637 EUR -un 71% menos-, sin ningun grupo descuadrado.
    #
    # Se reconoce POR ESTRUCTURA, no por el texto del concepto: la apertura
    # es del 1 de enero -no puede haber saldo anterior a eso- y es el apunte
    # mas antiguo de la cuenta. Y no se presupone el signo: en una cuenta
    # acreedora es un abono que cancelan pagos, y en una deudora al reves.
    pend = df[df["INDICE"] == 0].sort_values("FECHA")
    primero = _indice_apertura(df)
    if primero is not None:
        if True:
            objetivo = -_round2(df.loc[primero, "SALDO"])
            signo = 1 if objetivo > 0 else -1
            candidatos = [i for i in pend.index[1:]
                          if signo * df.loc[i, "SALDO"] > TOL]
            grupo = None

            # a) los primeros pagos en orden, acumulando hasta dar el importe
            acc = 0.0
            tramo = []
            for i in candidatos:
                acc = _round2(acc + df.loc[i, "SALDO"])
                tramo.append(i)
                if abs(acc - objetivo) < TOL:
                    grupo = list(tramo)
                    break
                if abs(acc) > abs(objetivo) + TOL:
                    break

            # b) si no cuadra asi, subconjuntos acotados de los primeros
            if grupo is None:
                cand = candidatos[:MAX_PAGOS_APERTURA]
                for n in range(1, min(MAX_GRUPO_COMBOS, len(cand)) + 1):
                    for combo in combinations(cand, n):
                        s = _round2(sum(df.loc[x, "SALDO"] for x in combo))
                        if abs(s - objetivo) < TOL:
                            grupo = list(combo)
                            break
                    if grupo:
                        break

            # si no hay conjunto exacto, no se fuerza nada: la apertura queda
            # pendiente y el auditor la ve en amarillo, que es lo correcto.
            if grupo:
                for x in [primero] + grupo:
                    df.loc[x, "INDICE"] = next_idx
                    df.loc[x, "GRUPO_APERTURA"] = True
                    df.loc[x, "PASO"] = PASO_APERTURA
                next_idx += 1

    # --- 2.3: cancelacion directa (mismo importe absoluto, signo contrario) ---
    buckets = defaultdict(lambda: {"pos": [], "neg": []})
    # SOLO lo que sigue sin asignar: 2.2b ya se ha llevado los apuntes de la
    # apertura. Antes recorria todo el df, que era correcto mientras 2.3 fuese
    # el primer paso que asigna, y deja de serlo en cuanto algo va delante.
    for idx, row in df[df["INDICE"] == 0].iterrows():
        b = buckets[row["SaldoABS"]]
        if row["SALDO"] > TOL:
            b["pos"].append(idx)
        elif row["SALDO"] < -TOL:
            b["neg"].append(idx)

    for _, b in buckets.items():
        pares = min(len(b["pos"]), len(b["neg"]))
        for i in range(pares):
            p, n = b["pos"][i], b["neg"][i]
            df.loc[p, "INDICE"] = next_idx
            df.loc[n, "INDICE"] = next_idx
            df.loc[[p, n], "PASO"] = PASO_IMPORTE
            next_idx += 1

    # apuntes con SALDO 0 exacto se autocancelan (caso raro)
    for idx in df[(df["INDICE"] == 0) & (df["SaldoABS"] < TOL)].index:
        df.loc[idx, "INDICE"] = next_idx
        df.loc[idx, "PASO"] = PASO_IMPORTE
        next_idx += 1

    # --- 2.4a: agrupacion secuencial por SaldoAcumulado, en orden cronologico ---
    pendientes = df[df["INDICE"] == 0].sort_values(["FECHA"]).index.tolist()
    usados = set()
    i = 0
    while i < len(pendientes):
        if pendientes[i] in usados:
            i += 1
            continue
        acc = 0.0
        grupo = []
        j = i
        while j < len(pendientes):
            ridx = pendientes[j]
            if ridx in usados:
                j += 1
                continue
            acc = _round2(acc + df.loc[ridx, "SALDO"])
            grupo.append(ridx)
            if abs(acc) < TOL and len(grupo) > 1:
                for gidx in grupo:
                    df.loc[gidx, "INDICE"] = next_idx
                    df.loc[gidx, "GRUPO_24"] = True
                    df.loc[gidx, "PASO"] = PASO_ACUMULACION
                    usados.add(gidx)
                next_idx += 1
                grupo = []
                acc = 0.0
            j += 1
        i += 1

    # --- 2.4b: combinaciones acotadas sobre lo que quede ---
    leftover = df[df["INDICE"] == 0].index.tolist()
    if 1 < len(leftover) <= MAX_LEFTOVER_FOR_COMBOS:
        encontrado_algo = True
        while encontrado_algo and len(leftover) > 1:
            encontrado_algo = False
            cents = {idx: int(round(df.loc[idx, "SALDO"] * 100)) for idx in leftover}
            grupo_hallado = None
            tope = min(MAX_GRUPO_COMBOS, len(leftover))
            for r in range(2, tope + 1):
                for combo in combinations(leftover, r):
                    if sum(cents[c] for c in combo) == 0:
                        grupo_hallado = combo
                        break
                if grupo_hallado:
                    break
            if grupo_hallado:
                for gidx in grupo_hallado:
                    df.loc[gidx, "INDICE"] = next_idx
                    df.loc[gidx, "GRUPO_24"] = True
                    df.loc[gidx, "PASO"] = PASO_COMBINACION
                next_idx += 1
                leftover = [x for x in leftover if x not in grupo_hallado]
                encontrado_algo = True

    return next_idx


def asignar_indices_cuenta(df_cta: pd.DataFrame):
    """Aplica el emparejamiento a UNA sola cuenta. df_cta: columnas FECHA
    (datetime), CUENTA, NOMBRE, CONCEPTO, SALDO (float, importe con signo
    del apunte) y, opcionalmente, INDICE_PREVIO (punteo del .smn).

    Devuelve (df_resultado, siguiente_indice_libre). df_resultado añade:
      SaldoABS   importe absoluto
      INDICE     int, 0 = sin cancelar. Conserva los previos tal cual y
                 numera los nuevos por encima del maximo previo
      ORIGEN     ORIGEN_CONTABLE si el grupo venia punteado en el .smn; si lo
                 asigno este modulo, EL PASO que lo formo (documento, apertura,
                 total, importe, acumulación, combinación); "" si pendiente
      GRUPO_24   True si el emparejamiento vino del procedimiento 2.4
                 (para resaltar en el informe)
      GRUPO_APERTURA  True si el grupo es el de la apertura y sus pagos
                 (procedimiento 2.2b)
      GRUPO_FACTURA   True si el grupo salio del numero de documento
                 (procedimiento 2.0), verificado por suma cero
    """
    df = df_cta.copy().reset_index(drop=True)
    df["SaldoABS"] = df["SALDO"].abs().round(2)

    if "INDICE_PREVIO" in df.columns:
        prev = (
            pd.to_numeric(df["INDICE_PREVIO"], errors="coerce")
            .fillna(0).astype(int).clip(lower=0)
        )
    else:
        prev = pd.Series(0, index=df.index, dtype=int)

    df["INDICE"] = prev
    df["ORIGEN"] = ""
    df.loc[prev > 0, "ORIGEN"] = ORIGEN_CONTABLE
    df["GRUPO_24"] = False
    df["GRUPO_APERTURA"] = False
    df["GRUPO_FACTURA"] = False
    df["PASO"] = ""

    next_idx = int(prev.max()) + 1
    pendientes = df.index[df["INDICE"] == 0]
    if len(pendientes) == 0:
        return df, next_idx

    cols_sub = ["FECHA", "SALDO", "SaldoABS", "INDICE", "GRUPO_24",
                "GRUPO_APERTURA", "GRUPO_FACTURA", "PASO"]
    if "FACTURA" in df.columns:
        cols_sub.append("FACTURA")
    sub = df.loc[pendientes, cols_sub].copy()
    next_idx = _emparejar_pendientes(sub, next_idx)

    df.loc[sub.index, "INDICE"] = sub["INDICE"]
    df.loc[sub.index, "GRUPO_24"] = sub["GRUPO_24"]
    df.loc[sub.index, "GRUPO_APERTURA"] = sub["GRUPO_APERTURA"]
    df.loc[sub.index, "GRUPO_FACTURA"] = sub["GRUPO_FACTURA"]
    df.loc[sub.index, "PASO"] = sub["PASO"]
    nuevos = sub.index[sub["INDICE"] > 0]
    # el paso que formo el grupo es lo que se ve en el papel; «auditoría» solo
    # si algun camino no lo anoto, para que nunca quede en blanco
    df.loc[nuevos, "ORIGEN"] = sub.loc[nuevos, "PASO"].replace("", ORIGEN_AUDITORIA)
    return df, next_idx


def verificar_cuenta(df_resultado: pd.DataFrame) -> dict:
    """Comprueba las reglas de verificacion.

    Para los grupos asignados por este modulo (ORIGEN auditoria) sumar 0 es
    una propiedad estructural del algoritmo: si no se cumple hay un bug de
    contabilidad interna, no un caso limite de los datos. Para los grupos
    del punteo previo (ORIGEN contable) NO esta garantizado: un grupo
    previo que no suma 0 se reporta en grupos_previos_descuadrados y se
    respeta -- es punteo del cliente y lo juzga el auditor.

    La conciliacion estructural descuenta ese descuadre previo: la suma de
    INDICE=0 tiene que coincidir con el total de la cuenta menos lo que
    sumen (bien o mal) los grupos punteados.
    """
    total = _round2(df_resultado["SALDO"].sum())
    idx0 = _round2(df_resultado.loc[df_resultado["INDICE"] == 0, "SALDO"].sum())
    origen = (df_resultado["ORIGEN"] if "ORIGEN" in df_resultado.columns
              else pd.Series("", index=df_resultado.index))

    grupos_auditoria = {}
    grupos_previos = {}
    for i in sorted(df_resultado["INDICE"].unique()):
        if i == 0:
            continue
        filas = df_resultado[df_resultado["INDICE"] == i]
        s = _round2(filas["SALDO"].sum())
        if (origen.loc[filas.index] == ORIGEN_CONTABLE).any():
            grupos_previos[int(i)] = s
        else:
            grupos_auditoria[int(i)] = s

    grupos_con_error = {k: v for k, v in grupos_auditoria.items() if abs(v) > TOL}
    previos_descuadrados = {k: v for k, v in grupos_previos.items() if abs(v) > TOL}
    descuadre_previo = _round2(sum(previos_descuadrados.values()))

    return {
        "total_cuenta": total,
        "suma_indice_0": idx0,
        "coincide_total_con_no_cancelado": abs(total - descuadre_previo - idx0) < TOL,
        "num_grupos_previos": len(grupos_previos),
        "num_grupos_nuevos": len(grupos_auditoria),
        "num_grupos_cancelados": len(grupos_previos) + len(grupos_auditoria),
        "grupos_con_error": grupos_con_error,
        "grupos_previos_descuadrados": previos_descuadrados,
        "descuadre_punteo_previo": descuadre_previo,
        "num_registros_sin_cancelar": int((df_resultado["INDICE"] == 0).sum()),
    }


# Muchas contabilidades registran la factura a fin de mes y escriben en el
# concepto la fecha del documento ("Fra - PROVEEDOR - 21/01/2025 - FVR2025...").
# Comparar contra la fecha de asiento fabrica entonces "pagos anteriores a su
# factura" que no lo son. Medido en un expediente real: 820 casos con la fecha
# contable y 198 con la del documento -- el 76% eran la fecha de registro.
#
# Esta fecha se usa SOLO PARA INFORMAR. El emparejamiento sigue trabajando con
# la fecha contable: hacerlo depender de un campo de texto libre que el cliente
# rellena como quiere seria fragil, y un 8% de las facturas no lo traen.
#
# Desde la 1.11.0 del MCP la fecha llega ya extraida (FechaEnConcepto) y el
# concepto no viaja. La regex de aqui es la MISMA que aplica el MCP, y solo se
# usa si el extracto trae CONCEPTO y no la derivada: d/m/a con / . o -, año de 2
# o 4 cifras, sin cifras ni separadores pegados a los lados.
_FECHA_CONCEPTO = re.compile(r"(?<![\d/.-])(\d{1,2})[/.-](\d{1,2})[/.-](\d{4}|\d{2})(?![\d/.-])")


def _fecha_desde_concepto(concepto):
    """Fecha del documento escrita en el concepto, como Timestamp, o NaT."""
    for m in _FECHA_CONCEPTO.finditer(str(concepto or "")):
        d, mes, a = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if a < 100:
            a += 2000
        if not 1990 <= a <= 2099:
            continue
        try:
            return pd.Timestamp(a, mes, d)
        except ValueError:
            continue
    return pd.NaT


def fecha_documento(fila):
    """La fecha del documento de un apunte si la tiene (FECHA_DOC); si no, su
    fecha contable."""
    f = fila.get("FECHA_DOC", pd.NaT)
    return f if pd.notna(f) else fila["FECHA"]


def _signo_documento(res) -> int:
    """Que signo tienen los documentos (facturas) en esta cuenta: +1 o -1.

    Por estructura, sin mirar el texto. La APERTURA arrastra los documentos
    que quedaron pendientes del ejercicio anterior, asi que lleva su mismo
    signo: en una cuenta de proveedor es un abono, y en una de cliente un
    cargo. Si no hay apertura, sirve el signo del saldo de la cuenta, que
    apunta en la misma direccion mientras quede algo pendiente.

    Devuelve 0 si no se puede decidir -cuenta sin apertura y con saldo cero-,
    y entonces el grupo no entra en los recuentos de fechas: mejor no evaluar
    que evaluar al reves.
    """
    if len(res):
        primero = res.sort_values("FECHA").iloc[0]
        if primero["FECHA"].month == 1 and primero["FECHA"].day == 1                 and abs(primero["SALDO"]) > TOL:
            return 1 if primero["SALDO"] > 0 else -1
    total = _round2(res["SALDO"].sum())
    if abs(total) > TOL:
        return 1 if total > 0 else -1
    return 0


def _lados(grupo, signo_doc: int):
    """Separa el grupo en (documentos, pagos) segun el signo de la cuenta."""
    if signo_doc == 0:
        return None, None
    docs = grupo[grupo["SALDO"] * signo_doc > TOL]
    pagos = grupo[grupo["SALDO"] * signo_doc < -TOL]
    if docs.empty or pagos.empty:
        return None, None
    return docs, pagos


def _lados_por_texto(grupo):
    """Respaldo cuando el signo no se puede deducir: que lado trae fecha.

    Las lineas de factura suelen llevar fecha de documento (FECHA_DOC) y las de
    pago no. Es una pista de texto, y por eso va SEGUNDA: solo se usa en cuentas
    sin apertura y con saldo cero, donde el criterio estructural no dice nada.
    Si tampoco decide, el grupo no se evalua.
    """
    if "FECHA_DOC" not in grupo.columns:
        return None, None
    pos = grupo[grupo["SALDO"] > TOL]
    neg = grupo[grupo["SALDO"] < -TOL]
    if pos.empty or neg.empty:
        return None, None
    con_pos = int(pos["FECHA_DOC"].notna().sum())
    con_neg = int(neg["FECHA_DOC"].notna().sum())
    if con_neg > con_pos:
        return neg, pos
    if con_pos > con_neg:
        return pos, neg
    return None, None


def analizar_hallazgos(df: pd.DataFrame, por_cuenta: dict) -> dict:
    """Recuentos para la hoja de criterios y hallazgos. No juzga nada.

    Si el extracto no trae fecha de documento -ni FechaEnConcepto derivada por
    el MCP ni CONCEPTO del que leerla-, TODO el bloque de «pagos anteriores a su
    factura» y el plazo de pago se dejan sin evaluar. No se calcula con la fecha
    contable: eso daria una cifra inflada con aspecto de hallazgo. El papel dice
    «no evaluado», que es distinto de «cero».
    """
    con_fecha_doc = "FECHA_DOC" in df.columns
    plazos = []
    facturas = con_fecha = 0
    anom_doc = anom_solo_registro = no_evaluables = 0
    # el pago es anterior a la FECHA CONTABLE de una factura que NO lleva fecha de
    # documento: no se puede saber si es registro tardio o pago anticipado. Hasta
    # el 10/09/2026 caia en «con la fecha del documento» y el modelo lo leyo como
    # hallazgo cierto en un diario con 0 % de facturas con fecha.
    anom_sin_fecha_doc = 0
    forzados = con_alternativa = grandes = 0
    ap_detectadas = ap_canceladas = ap_vivas = 0
    ap_importe_vivo = 0.0
    ctas_sin_apertura = 0
    ap_no_identificadas = 0
    ap_importe_no_ident = 0.0
    # una cuenta de UN solo apunte del 1 de enero no tiene un problema de
    # identificacion: no tiene nada que cancelar. Iba sumada con las anteriores y el
    # auditor recibia un importe unico como si fuera un frente abierto (10/09/2026).
    ctas_un_apunte = 0
    importe_un_apunte = 0.0
    grupos_por_paso = {}

    for cuenta, (res, _info) in por_cuenta.items():
        if "ORIGEN" in res.columns:
            for paso, n in (res[res["INDICE"] > 0].groupby("INDICE")["ORIGEN"].first()
                            .value_counts().items()):
                if paso != ORIGEN_CONTABLE:
                    grupos_por_paso[paso] = grupos_por_paso.get(paso, 0) + int(n)
        # cuantos apuntes de cada importe hay: dice si el pareo tenia eleccion
        cuenta_por_importe = defaultdict(lambda: {"pos": 0, "neg": 0})
        for _, r in res.iterrows():
            if abs(r["SALDO"]) < TOL:
                continue
            lado = "pos" if r["SALDO"] > 0 else "neg"
            cuenta_por_importe[round(abs(r["SALDO"]), 2)][lado] += 1

        # LA MISMA deteccion que usa el emparejamiento (_indice_apertura), no otra.
        # Habia tres definiciones distintas de «apertura» en este fichero y el papel
        # contaba 19 aperturas vivas donde el reconocimiento contaba 10: el papel
        # incluia cuentas con VARIOS apuntes del 1 de enero -donde no se sabe cual es
        # la apertura- y cuentas de un solo apunte. Medido el 08/09/2026 sobre 71
        # cuentas reales.
        #
        # Y esas no desaparecen del informe: se cuentan APARTE, porque el algoritmo
        # NO LAS HA INTENTADO. Meterlas entre las vivas dice «no se ha podido» cuando
        # lo cierto es «no se ha mirado», que es la distincion que este papel cuida en
        # todos los demas recuentos.
        idx_ap = _indice_apertura_informe(res)
        primero = res.sort_values("FECHA").iloc[0] if len(res) else None
        parece_apertura = (primero is not None
                           and primero["FECHA"].month == 1 and primero["FECHA"].day == 1)
        if idx_ap is not None:
            ap_detectadas += 1
            if res.loc[idx_ap, "INDICE"] > 0:
                ap_canceladas += 1
            else:
                ap_vivas += 1
                ap_importe_vivo = _round2(ap_importe_vivo
                                          + abs(res.loc[idx_ap, "SALDO"]))
        elif parece_apertura and len(res) == 1:
            ctas_un_apunte += 1
            importe_un_apunte = _round2(importe_un_apunte + abs(primero["SALDO"]))
        elif parece_apertura:
            ap_no_identificadas += 1
            ap_importe_no_ident = _round2(ap_importe_no_ident
                                          + abs(primero["SALDO"]))
        else:
            ctas_sin_apertura += 1

        if not con_fecha_doc:
            continue      # sin fecha de documento no hay nada que comparar
        signo_doc = _signo_documento(res)
        for ind, g in res[res["INDICE"] > 0].groupby("INDICE"):
            docs, pagos = _lados(g, signo_doc)
            if docs is None:
                docs, pagos = _lados_por_texto(g)
            if docs is None:
                no_evaluables += 1
                continue
            facturas += len(docs)
            con_fecha += int(docs["FECHA_DOC"].notna().sum())
            f_pago = pagos["FECHA"].min()
            f_doc = min(fecha_documento(r) for _, r in docs.iterrows())
            docs_con_fecha = bool(docs["FECHA_DOC"].notna().any())
            if f_pago < f_doc and not docs_con_fecha:
                anom_sin_fecha_doc += 1
            elif f_pago < f_doc:
                anom_doc += 1
                if len(g) > 2:
                    grandes += 1
                else:
                    c = cuenta_por_importe[round(abs(g["SALDO"].iloc[0]), 2)]
                    if c["pos"] == 1 and c["neg"] == 1:
                        forzados += 1
                    else:
                        con_alternativa += 1
            elif f_pago < docs["FECHA"].min():
                anom_solo_registro += 1
            else:
                plazos.append((f_pago - f_doc).days)

    plazos.sort()
    def pct(q):
        return int(plazos[int(q * (len(plazos) - 1))]) if plazos else None

    return {
        "cuentas": len(por_cuenta),
        "apuntes": int(len(df)),
        "fecha_doc_disponible": con_fecha_doc,
        "fuente_fecha_doc": df.attrs.get("fuente_fecha_doc"),
        "fuente_documento": df.attrs.get("fuente_documento"),
        "concepto_disponible": "CONCEPTO" in df.columns,
        "grupos_evaluados": anom_doc + anom_solo_registro + len(plazos),
        "facturas_con_fecha_doc": con_fecha,
        "facturas_totales": facturas,
        "anomalos": anom_doc,
        "anomalos_sin_fecha_doc": anom_sin_fecha_doc,
        "grupos_por_paso": dict(sorted(grupos_por_paso.items(), key=lambda kv: -kv[1])),
        "candidatas_documento": df.attrs.get("candidatas_documento") or [],
        "solo_fecha_registro": anom_solo_registro,
        "grupos_no_evaluables": no_evaluables,
        "anom_forzados": forzados,
        "anom_con_alternativa": con_alternativa,
        "anom_grupos_grandes": grandes,
        "plazo_p25": pct(0.25),
        "plazo_mediana": pct(0.50),
        "plazo_p75": pct(0.75),
        "plazo_muestra": len(plazos),
        "aperturas_detectadas": ap_detectadas,
        "aperturas_canceladas": ap_canceladas,
        "aperturas_vivas": ap_vivas,
        "aperturas_importe_vivo": ap_importe_vivo,
        "cuentas_sin_apertura": ctas_sin_apertura,
        "aperturas_no_identificadas": ap_no_identificadas,
        "aperturas_importe_no_identificado": ap_importe_no_ident,
        "cuentas_un_apunte": ctas_un_apunte,
        "importe_un_apunte": importe_un_apunte,
    }


def procesar_extracto(df: pd.DataFrame) -> dict:
    """Aplica el emparejamiento a CADA cuenta distinta del extracto.
    Devuelve {cuenta: (df_resultado, verificacion)}, en el orden en que
    aparecen las cuentas al ordenar por CUENTA."""
    resultado = {}
    for cuenta, grupo in df.groupby("CUENTA", sort=True):
        res, _ = asignar_indices_cuenta(grupo)
        info = verificar_cuenta(res)
        resultado[cuenta] = (res, info)
    return resultado
