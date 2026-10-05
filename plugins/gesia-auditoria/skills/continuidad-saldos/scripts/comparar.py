"""Compara la apertura del diario con el cierre auditado del ejercicio anterior.

    python comparar.py --diario diario.mdb --cierre cierre.json \
        --salida resultado.json

El modelo no lee filas del diario: las lee este script y devuelve el resultado
ya agregado al nivel de auditoria: el modelo no cuenta filas de un diario,
las cuenta un script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib_continuidad import (
    DECIMALES,
    GRUPOS_BALANCE,
    aplicar_filtro,
    cargar_diario,
    leer_cierre,
    leer_filtro_apertura,
    mapear_a_maximo_nivel,
    saldos_apertura,
    salida_utf8,
)

# Por debajo de esto una diferencia es redondeo, no un hallazgo. Es el centimo:
# los dos lados vienen ya redondeados a 2 decimales, asi que cualquier resto es
# ruido de coma flotante y no un descuadre contable.
UMBRAL = 0.005

MAX_LISTA = 15


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("--diario", required=True)
    p.add_argument("--cierre", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--ejercicio", default="",
                   help="ejercicio auditado; obligatorio si el cierre son filas crudas")
    p.add_argument("--ejercicio-anterior", default="",
                   help="ejercicio del cierre con el que se compara")
    p.add_argument("--cliente", default="", help="razón social, para el papel")
    args = p.parse_args()

    filtro = leer_filtro_apertura(args.diario)
    if filtro.get("ausente"):
        print("No se puede identificar la apertura: " + filtro["motivo"])
        return 2

    df = cargar_diario(args.diario)
    mascara = aplicar_filtro(df, filtro)
    if not mascara.any():
        print("El filtro de apertura no selecciona ningun apunte.")
        return 2

    cierre = leer_cierre(args.cierre, args.ejercicio, args.ejercicio_anterior,
                             args.cliente)
    saldo_cierre = {c["cuenta"]: c["saldo"] for c in cierre["cuentas"]}
    nombre = {c["cuenta"]: c["nombre"] for c in cierre["cuentas"]}
    nivel = set(saldo_cierre)

    # Apertura por cuenta del cliente, y de ahi al nivel de auditoria.
    apertura_cliente = saldos_apertura(df, mascara)
    mapa = mapear_a_maximo_nivel(apertura_cliente["CUENTA"].tolist(), nivel)

    saldo_apertura: dict = {}
    detalle: dict = {}          # cuenta de nivel -> cuentas del cliente que agrega
    sin_mapeo: list = []
    resultados: list = []

    for fila in apertura_cliente.itertuples(index=False):
        cta, saldo = fila.CUENTA, float(fila.SALDO_AP)
        if cta[:1] not in GRUPOS_BALANCE:
            # Grupos 6, 7, 0, 8 y 9: fuera de la prueba. Los de resultados se
            # informan porque no deberian tener apertura.
            if cta[:1] in ("6", "7") and abs(saldo) >= UMBRAL:
                resultados.append({"cuenta": cta, "saldo": round(saldo, DECIMALES)})
            continue
        destino = mapa.get(cta)
        if destino is None:
            if abs(saldo) >= UMBRAL:
                sin_mapeo.append({"cuenta": cta, "saldo": round(saldo, DECIMALES)})
            continue
        saldo_apertura[destino] = round(
            saldo_apertura.get(destino, 0.0) + saldo, DECIMALES
        )
        detalle.setdefault(destino, []).append(cta)

    # Una cuenta abierta con saldo que el expediente no reconoce ES el hallazgo
    # "cuenta nueva", no una incidencia menor: es lo que se pidio detectar.
    # Se emite aqui, con la cuenta del cliente, porque no tiene equivalente al
    # nivel de auditoria y por eso no puede salir del bucle de abajo.
    hallazgos: list = []
    for s in sin_mapeo:
        hallazgos.append({
            "tipo": "cuenta_nueva", "cuenta": s["cuenta"], "nombre": "",
            "importe": s["saldo"],
            "que_pasa": "se ha abierto con saldo y el expediente no la reconoce "
                        "a ningun nivel: no existia al cierre anterior",
        })

    # El papel recorre las cuentas del cierre, que son TODOS los destinos posibles
    # del mapeo: si una cuenta de apertura encontro destino, ese destino esta aqui
    # por construccion. Las que estan a cero en los dos lados no salen (decidido
    # 23/08/2026): son cuentas del plan que el cliente no usa, y en el expediente de calibracion
    # son 389 de 438 filas que no acreditan nada y estorban para leer las que si.
    codigos = sorted(nivel)

    filas: list = []
    omitidas = 0
    for cta in codigos:
        en_apertura = cta in saldo_apertura
        sc = saldo_cierre[cta]
        sa = saldo_apertura.get(cta, 0.0)
        dif = round(sa - sc, DECIMALES)

        if abs(sa) < UMBRAL and abs(sc) < UMBRAL:
            omitidas += 1
            continue

        filas.append({
            "cuenta": cta,
            "nombre": nombre.get(cta, ""),
            # Sin apertura es celda VACIA, no cero: el hueco dice "la cuenta no
            # se ha abierto" y el cero dice "se ha abierto y vale cero".
            "apertura": sa if en_apertura else None,
            "cierre": sc,
            "diferencia": dif,
            "cuentas_cliente": len(detalle.get(cta, [])),
        })

        if not en_apertura and abs(sc) >= UMBRAL:
            hallazgos.append({
                "tipo": "sin_apertura", "cuenta": cta, "nombre": nombre.get(cta, ""),
                "importe": sc,
                "que_pasa": "tenia saldo al cierre y no se ha abierto",
            })
        elif abs(dif) >= UMBRAL:
            hallazgos.append({
                "tipo": "diferencia", "cuenta": cta, "nombre": nombre.get(cta, ""),
                "importe": dif,
                "que_pasa": "la apertura no coincide con el cierre auditado",
            })

    # Cuadre de control. El asiento de apertura cuadra a cero por construccion, y
    # la parte que entra en la prueba es solo la de balance. Asi que si la
    # apertura de balance NO suma cero, lo que falta es exactamente lo que se ha
    # quedado fuera: las patas en cuentas de resultados y las cuentas que el
    # expediente no reconoce. Medido en el fixture: 383.333 = 333.333 de una 710
    # metida en la apertura + 50.000 de una cuenta nueva sin correspondencia.
    #
    # Sin esta comprobacion el papel puede salir con una diferencia en una cuenta
    # y sin decir que hay un importe sin explicar en ningun sitio.
    suma_apertura = round(sum(saldo_apertura.values()), DECIMALES)
    fuera_resultados = round(-sum(r["saldo"] for r in resultados), DECIMALES)
    fuera_sin_mapeo = round(-sum(s["saldo"] for s in sin_mapeo), DECIMALES)
    descuadre_explicado = round(fuera_resultados + fuera_sin_mapeo, DECIMALES)
    cuadre = {
        "descuadre_apertura_balance": suma_apertura,
        "por_cuentas_de_resultados": fuera_resultados,
        "por_cuentas_no_reconocidas": fuera_sin_mapeo,
        "explicado": descuadre_explicado,
        # Si esto no es cero, el descuadre no se explica con lo excluido y hay
        # algo que este skill no esta entendiendo. Es la senal de alarma.
        "sin_explicar": round(suma_apertura - descuadre_explicado, DECIMALES),
    }

    resultado = {
        "meta": {
            "cliente": cierre.get("cliente", ""),
            "ejercicio": cierre["ejercicio"],
            "ejercicio_anterior": cierre["ejercicio_anterior"],
            "filtro_apertura": filtro["crudo"],
            "apuntes_apertura": int(mascara.sum()),
            "asientos_apertura": sorted(
                df.loc[mascara, "ASIENTO"].drop_duplicates().tolist()
            ),
            "cuentas_cierre": len(saldo_cierre),
            "cuentas_apertura": len(saldo_apertura),
            "cuentas_papel": len(filas),
            "cuentas_sin_saldo_omitidas": omitidas,
            "suma_cierre": round(sum(saldo_cierre.values()), DECIMALES),
            "suma_apertura": suma_apertura,
            "umbral": UMBRAL,
        },
        "cuadre": cuadre,
        "filas": filas,
        "hallazgos": hallazgos,
        "sin_mapeo": sin_mapeo,
        "resultados_en_apertura": resultados,
    }

    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=1, allow_nan=False),
        encoding="utf-8",
    )

    m = resultado["meta"]
    print("Escrito: " + args.salida)
    print("  apertura   " + str(m["apuntes_apertura"]) + " apuntes, asiento(s) "
          + str(m["asientos_apertura"][:5]))
    print("  cuentas    " + str(m["cuentas_papel"]) + " en el papel ("
          + str(m["cuentas_cierre"]) + " del cierre, " + str(m["cuentas_apertura"])
          + " con apertura)")
    print("             " + str(m["cuentas_sin_saldo_omitidas"]) + " cuentas "
          "omitidas por estar a cero en los dos lados")
    print("  suma       cierre " + format(m["suma_cierre"], ".2f")
          + " | apertura " + format(m["suma_apertura"], ".2f"))
    c = resultado["cuadre"]
    if abs(c["descuadre_apertura_balance"]) >= UMBRAL:
        print("  CUADRE     la apertura de balance no suma cero: "
              + format(c["descuadre_apertura_balance"], ".2f"))
        print("             " + format(c["por_cuentas_de_resultados"], ".2f")
              + " en cuentas de resultados, "
              + format(c["por_cuentas_no_reconocidas"], ".2f")
              + " en cuentas no reconocidas")
        if abs(c["sin_explicar"]) >= UMBRAL:
            print("             ATENCION: quedan "
                  + format(c["sin_explicar"], ".2f")
                  + " sin explicar. No entregues el papel: hay algo que este "
                    "skill no esta entendiendo.")
    else:
        print("  CUADRE     la apertura de balance cuadra a cero")
    print("  hallazgos  " + str(len(hallazgos)))
    for tipo in ("sin_apertura", "cuenta_nueva", "diferencia"):
        de_ese = [h for h in hallazgos if h["tipo"] == tipo]
        if de_ese:
            print("    " + tipo + ": " + str(len(de_ese)))
            for h in de_ese[:MAX_LISTA]:
                print("      " + h["cuenta"] + " " + format(h["importe"], ".2f")
                      + "  " + h["nombre"][:40])
            if len(de_ese) > MAX_LISTA:
                print("      (" + str(len(de_ese) - MAX_LISTA) + " mas en el JSON)")
    if resultados:
        print("  ATENCION: " + str(len(resultados)) + " cuentas de los grupos 6 y 7 "
              "con saldo de apertura (fuera de la prueba)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
