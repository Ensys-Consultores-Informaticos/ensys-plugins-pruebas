"""Compara la apertura del diario con el cierre auditado del ejercicio anterior.

    python comparar.py --filtro filtro.json --apertura apertura.json \
        --cierre cierre.json --salida resultado.json

El modelo no lee filas del diario: las lee este script y devuelve el resultado
ya agregado al nivel de auditoria: el modelo no cuenta filas de un diario,
las cuenta un script.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# La carpeta del script, explicita: lanzado con `python -I` no esta en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_continuidad import (  # noqa: E402
    DECIMALES,
    GRUPOS_BALANCE,
    cargar_apertura,
    leer_cierre,
    leer_filtro,
    mapear_a_maximo_nivel,
    saldos_apertura,
    salida_utf8,
)

# Por debajo de esto una diferencia es redondeo, no un hallazgo. Es el centimo:
# los dos lados vienen ya redondeados a 2 decimales, asi que cualquier resto es
# ruido de coma flotante y no un descuadre contable.
UMBRAL = 0.005

MAX_LISTA = 15

# Rotulo de las diferencias que se compensan entre si. Es una MARCA, no una
# explicacion: siguen siendo diferencias y cuentan como tales (decidido por el
# auditor tras el registro del 21/10/2026).
ROTULO_COMPENSA = "posible reclasificación al abrir"


def emparejar_compensadas(hallazgos: list) -> list:
    """Agrupa las diferencias que se compensan: mismo importe absoluto, signo contrario.

    Salio en un expediente real (registro del 21/10/2026): cuatro diferencias que eran dos
    parejas -una 40 contra una 57, y dos 43 entre si- y que el auditor tuvo que emparejar a
    mano. Es lo que deja una partida abierta en otra cuenta de la que se cerro.

    Solo las de tipo `diferencia`: una `sin_apertura` o una `cuenta_nueva` dicen otra cosa
    -falta la cuenta o sobra- y mezclarlas seria ya interpretar. El importe se compara al
    centimo, que es la misma tolerancia que UMBRAL: los dos lados llegan redondeados a 2
    decimales, asi que dos importes que difieren en un centimo no son el mismo.

    La pareja solo se forma cuando es UNICA: exactamente una diferencia positiva y una
    negativa con ese importe. Con mas de una en algun lado (dos +X y una -X, o dos y dos)
    hay varias formas de emparejar y elegir una seria inventarla, asi que el grupo sale
    como `ambigua`, con todas sus cuentas y sin pareja asignada.

    Anota en cada hallazgo afectado `compensacion` (pareja | ambigua), `compensa_con` (las
    cuentas de signo contrario) y `compite_con` (las de su mismo signo e importe, vacio en una
    pareja), y devuelve la lista de grupos para el resumen.
    """
    por_importe: dict = {}
    for h in hallazgos:
        if h["tipo"] != "diferencia":
            continue
        centimos = int(round(abs(h["importe"]) * 100))
        if centimos:
            por_importe.setdefault(centimos, []).append(h)

    grupos: list = []
    for centimos in sorted(por_importe, reverse=True):
        de_ese = por_importe[centimos]
        positivas = sorted((h for h in de_ese if h["importe"] > 0), key=lambda h: h["cuenta"])
        negativas = sorted((h for h in de_ese if h["importe"] < 0), key=lambda h: h["cuenta"])
        if not positivas or not negativas:
            continue
        clase = "pareja" if len(positivas) == 1 and len(negativas) == 1 else "ambigua"
        for lado, contrario in ((positivas, negativas), (negativas, positivas)):
            for h in lado:
                h["compensacion"] = clase
                h["compensa_con"] = [c["cuenta"] for c in contrario]
                # en la ambigua, las de su mismo signo: son las que se disputan la pareja
                h["compite_con"] = [c["cuenta"] for c in lado if c is not h]
        grupos.append({
            "clase": clase,
            "importe": round(centimos / 100, DECIMALES),
            "positivas": [h["cuenta"] for h in positivas],
            "negativas": [h["cuenta"] for h in negativas],
        })
    return grupos


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser()
    p.add_argument("--filtro", required=True, help="JSON exportado con SQL_FILTRO")
    p.add_argument("--apertura", required=True, help="JSON del asiento de apertura")
    p.add_argument("--cierre", required=True)
    p.add_argument("--salida", required=True)
    p.add_argument("--ejercicio", default="",
                   help="ejercicio auditado; obligatorio si el cierre son filas crudas")
    p.add_argument("--ejercicio-anterior", default="",
                   help="ejercicio del cierre con el que se compara")
    p.add_argument("--cliente", default="", help="razón social, para el papel")
    args = p.parse_args()

    filtro = leer_filtro(args.filtro)
    if filtro.get("ausente"):
        print("No se puede identificar la apertura: " + filtro["motivo"])
        return 2

    df = cargar_apertura(args.apertura)
    mascara = df["POR_FILTRO"]
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

    compensaciones = emparejar_compensadas(hallazgos)

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
            "parejas_compensadas": sum(1 for g in compensaciones if g["clase"] == "pareja"),
            "grupos_compensacion_ambigua": sum(1 for g in compensaciones
                                               if g["clase"] == "ambigua"),
        },
        "cuadre": cuadre,
        "filas": filas,
        "hallazgos": hallazgos,
        "compensaciones": compensaciones,
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
    # que importe lleva cada tipo. Sin decirlo, un «-341.42» en pantalla no se sabia hacia que
    # lado iba (registro del 28/10/2026). La diferencia es la del papel: APERTURA menos CIERRE.
    que_importe = {"sin_apertura": "importe = saldo al cierre auditado",
                   "cuenta_nueva": "importe = saldo abierto",
                   "diferencia": "importe = apertura − cierre"}
    print("  hallazgos  " + str(len(hallazgos)))
    for tipo in ("sin_apertura", "cuenta_nueva", "diferencia"):
        de_ese = [h for h in hallazgos if h["tipo"] == tipo]
        if de_ese:
            print("    " + tipo + ": " + str(len(de_ese)) + "  (" + que_importe[tipo] + ")")
            for h in de_ese[:MAX_LISTA]:
                marca = ""
                if h.get("compensacion") == "pareja":
                    marca = "  [se compensa con " + h["compensa_con"][0] + "]"
                elif h.get("compensacion") == "ambigua":
                    marca = ("  [ambigua: con " + " o ".join(h["compensa_con"])
                             + (", igual que " + ", ".join(h["compite_con"])
                                if h["compite_con"] else "") + "]")
                print("      " + h["cuenta"] + " " + format(h["importe"], ".2f")
                      + "  " + h["nombre"][:40] + marca)
            if len(de_ese) > MAX_LISTA:
                print("      (" + str(len(de_ese) - MAX_LISTA) + " mas en el JSON)")
    # Las que se compensan, aparte y enteras: el auditor las emparejaba a mano
    # (registro del 21/10/2026). Se dicen como marca, no como explicacion.
    if compensaciones:
        print("  COMPENSAN  " + str(m["parejas_compensadas"]) + " pareja(s) y "
              + str(m["grupos_compensacion_ambigua"]) + " grupo(s) ambiguo(s) de "
              "diferencias de igual importe y signo contrario: " + ROTULO_COMPENSA
              + ". Siguen siendo diferencias.")
        for g in compensaciones[:MAX_LISTA]:
            lados = (", ".join(g["positivas"]) + " (+) / " + ", ".join(g["negativas"])
                     + " (-)")
            if g["clase"] == "pareja":
                print("      pareja   " + format(g["importe"], ".2f") + "  " + lados)
            else:
                print("      AMBIGUA  " + format(g["importe"], ".2f") + "  " + lados
                      + "  -> no se sabe cual con cual: no se emparejan")
        if len(compensaciones) > MAX_LISTA:
            print("      (" + str(len(compensaciones) - MAX_LISTA) + " mas en el JSON)")
    if resultados:
        print("  ATENCION: " + str(len(resultados)) + " cuentas de los grupos 6 y 7 "
              "con saldo de apertura (fuera de la prueba)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
