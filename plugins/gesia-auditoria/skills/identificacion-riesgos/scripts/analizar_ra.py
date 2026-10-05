"""Señales de la revisión analítica de Gesia, para alimentar los riesgos.

    python analizar_ra.py --ra ra.json --ejercicios "2025,2024,2023,2022,2021" \
        --salida analisis_ra.json

Entra el resultado de consultar ElementosRA + FamiliasRA por el MCP. Sale una
lista de señales medidas sobre los ratios que el auditor tiene activos.

Este script NO interpreta lo que significa cada ratio: no sabe si un
endeudamiento de 0,8 es bueno o malo. Mide comportamientos —tendencias, saltos,
signos— y deja la lectura al modelo, que para eso tiene el campo `Concepto` del
propio Gesia, donde el ratio viene explicado.

Los valores vienen como texto con coma decimal, y `ValorAño1` es el ejercicio
que se audita: el 5 es el más antiguo.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from lib_riesgos import con_resumen, inmaterial, ruta_resumen

# Un ratio que se mueve en la misma direccion este numero de años seguidos, o
# mas, es una tendencia y no ruido. Tres de cinco es lo minimo que permite
# hablar de tendencia sin que una sola oscilacion la dispare.
ANOS_TENDENCIA = 3

# El salto del ultimo ejercicio se compara con lo que ese mismo ratio se movia
# antes. Si es este multiplo del movimiento tipico anterior, es un salto. Se
# hace asi y no con un porcentaje fijo porque cada ratio tiene su escala: un
# 0,2 en un margen es enorme y en un periodo medio de cobro es nada.
FACTOR_SALTO = 3.0

# Por debajo de esto, el movimiento historico se considera plano y no sirve de
# referencia para medir el salto: se usa el valor absoluto del propio ratio.
MOVIMIENTO_PLANO = 1e-9

MAX_LISTA = 20

# Un mismo ratio puede estar repetido por fase: Planificacion, Trabajo e Informe
# (tabla FasesRA: P, T, I). Cuando pasa, manda el de PLANIFICACION, que es la fase
# en la que se identifican los riesgos. La fase vacia significa que el elemento no
# esta asignado a ninguna —el caso normal en los expedientes vistos— y va detras
# de P pero delante de las otras dos.
ORDEN_FASE = {"P": 0, "": 1, "T": 2, "I": 3}


def numero(v):
    """Los valores llegan como texto con coma decimal; vacio es ausencia."""
    t = str(v if v is not None else "").strip()
    if not t:
        return None
    try:
        return float(t.replace(",", "."))
    except ValueError:
        return None


def señales_de(valores: list) -> list:
    """Comportamientos medibles de una serie [actual, ..., mas antiguo]."""
    fuera = []
    serie = [v for v in valores if v is not None]
    if len(serie) < 2:
        return fuera

    actual, anterior = serie[0], serie[1]

    # Tendencia: se recorre del mas antiguo al actual para que "sube" signifique
    # lo que se espera al leerlo.
    cron = list(reversed(serie))
    subidas = bajadas = 0
    for i in range(len(cron) - 1, 0, -1):
        if cron[i] > cron[i - 1]:
            if bajadas:
                break
            subidas += 1
        elif cron[i] < cron[i - 1]:
            if subidas:
                break
            bajadas += 1
        else:
            break
    if subidas + 1 >= ANOS_TENDENCIA:
        fuera.append({"tipo": "tendencia", "sentido": "al alza",
                      "años": subidas + 1})
    elif bajadas + 1 >= ANOS_TENDENCIA:
        fuera.append({"tipo": "tendencia", "sentido": "a la baja",
                      "años": bajadas + 1})

    # Salto: el movimiento del ultimo año contra el movimiento tipico anterior.
    salto = abs(actual - anterior)
    previos = [abs(serie[i] - serie[i + 1]) for i in range(1, len(serie) - 1)]
    referencia = (sum(previos) / len(previos)) if previos else 0.0
    if referencia > MOVIMIENTO_PLANO:
        if salto >= FACTOR_SALTO * referencia:
            fuera.append({"tipo": "salto", "importe": round(salto, 4),
                          "veces_lo_normal": round(salto / referencia, 1)})
    elif salto > abs(anterior) * 0.5 and salto > MOVIMIENTO_PLANO:
        # Sin historial de movimiento, un cambio que es la mitad del propio
        # valor ya es un salto.
        fuera.append({"tipo": "salto", "importe": round(salto, 4),
                      "veces_lo_normal": None})

    if all(v < 0 for v in serie):
        fuera.append({"tipo": "negativo_persistente", "años": len(serie)})

    if (actual < 0) != (anterior < 0):
        fuera.append({"tipo": "cambio_de_signo",
                      "de": round(anterior, 4), "a": round(actual, 4)})

    return fuera


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    resumen = con_resumen()
    p = argparse.ArgumentParser()
    p.add_argument("--ra", required=True, help="JSON de ElementosRA + FamiliasRA")
    p.add_argument("--ejercicios", required=True,
                   help="del actual al mas antiguo, p.ej. 2025,2024,2023,2022,2021")
    p.add_argument("--salida", required=True)
    p.add_argument("--ir-t", type=float, default=0.0,
                   help="importancia relativa de trabajo; por debajo de ella un "
                        "ratio que sea un importe no genera señal. Sin ella no "
                        "se filtra nada.")
    args = p.parse_args()

    ejercicios = [e.strip() for e in args.ejercicios.split(",") if e.strip()]
    filas = json.loads(Path(args.ra).read_text(encoding="utf-8"))
    if isinstance(filas, dict):
        filas = filas.get("filas") or filas.get("elementos") or []
    if not filas:
        print("El JSON de revisión analítica no trae elementos.")
        return 2

    # Deduplicar por fase antes de medir nada: si el mismo CodigoElementoRA viene
    # repetido, se queda el de Planificacion.
    por_codigo: dict = {}
    descartados = 0
    for f in filas:
        codigo = str(f.get("CodigoElementoRA", "")).strip()
        fase = str(f.get("CodigoFaseRA", "")).strip().upper()
        rango = ORDEN_FASE.get(fase, len(ORDEN_FASE))
        previo = por_codigo.get(codigo)
        if previo is None:
            por_codigo[codigo] = (rango, fase, f)
        else:
            descartados += 1
            if rango < previo[0]:
                por_codigo[codigo] = (rango, fase, f)
    filas = [v[2] for v in por_codigo.values()]
    fases_usadas = sorted({v[1] for v in por_codigo.values() if v[1]})

    elementos, con_señal, sin_valor = [], [], 0
    inmateriales: list = []
    for f in filas:
        valores = [numero(f.get("ValorAño" + str(i))) for i in range(1, 6)]
        if valores[0] is None:
            sin_valor += 1
        sen = señales_de(valores)
        # Un importe por debajo de la importancia relativa no es una senal: la
        # tendencia de 130 euros de exigible a largo ocupaba en un informe real
        # el sitio de algo que si importa. El recorte NO es silencioso.
        if sen and valores[0] is not None and inmaterial(f, valores[0], args.ir_t):
            inmateriales.append({
                "codigo": str(f.get("CodigoElementoRA", "")).strip(),
                "elemento": str(f.get("Elemento", "")).strip(),
                "valor": valores[0], "señales": len(sen),
            })
            sen = []
        item = {
            "codigo": str(f.get("CodigoElementoRA", "")).strip(),
            "familia": str(f.get("Familia", "")).strip(),
            "codigo_familia": str(f.get("CodigoFamiliaRA", "")).strip(),
            "elemento": str(f.get("Elemento", "")).strip(),
            # Escala 1-5 del auditor: 1 es lo MAS relevante y 5 lo menos
            # (Confirmado en cliente).
            "relevancia": str(f.get("Relevancia", "")).strip(),
            "fase": str(f.get("CodigoFaseRA", "")).strip().upper(),
            "descripcion": str(f.get("Descripcion", "")).strip(),
            "valores": {ej: valores[i] for i, ej in enumerate(ejercicios)
                        if i < len(valores)},
            "señales": sen,
        }
        elementos.append(item)
        if sen:
            con_señal.append(item)

    # Manda la relevancia que le dio el auditor —1 es lo mas relevante, 5 lo
    # menos— y dentro de cada nivel, lo que mas se ha movido. Al reves, un ratio
    # marginal con tres señales tapaba a uno de relevancia 1 con una sola, y la
    # que sabe cual importa en este encargo es la persona, no el recuento.
    def rango(x):
        r = x["relevancia"]
        return int(r) if r.isdigit() else 99      # sin relevancia, al final
    con_señal.sort(key=lambda x: (rango(x), -len(x["señales"]), x["codigo"]))

    resultado = {
        "ejercicios": ejercicios,
        "n_elementos": len(elementos),
        "duplicados_por_fase_descartados": descartados,
        "fases_presentes": fases_usadas,
        "n_con_señal": len(con_señal),
        "sin_valor_ejercicio_actual": sin_valor,
        # Lo descartado por inmaterial se declara, con nombre e importe: un
        # recorte que no se cuenta se lee como «no habia nada ahi».
        "ir_t_aplicada": args.ir_t,
        "descartados_por_inmateriales": inmateriales,
        "elementos": elementos,
        "con_señal": con_señal,
    }
    Path(args.salida).parent.mkdir(parents=True, exist_ok=True)
    Path(args.salida).write_text(
        json.dumps(resultado, ensure_ascii=False, indent=1, allow_nan=False),
        encoding="utf-8")

    print("Escrito: " + args.salida)
    print("  " + str(len(elementos)) + " ratios activos, "
          + str(len(con_señal)) + " con alguna señal")
    if inmateriales:
        print("  " + str(len(inmateriales)) + " descartado(s) por inmaterial "
              "(importe por debajo de la IR_T de "
              + format(args.ir_t, ",.0f") + " EUR):")
        for x in inmateriales:
            print("      " + x["elemento"][:34].ljust(36)
                  + format(x["valor"], ",.2f").rjust(16)
                  + "   " + str(x["señales"]) + " señal(es) descartada(s)")
    if descartados:
        print("  " + str(descartados) + " repetidos por fase, descartados "
              "(manda Planificación). Fases presentes: "
              + (", ".join(fases_usadas) if fases_usadas else "ninguna"))
    if sin_valor:
        print("  " + str(sin_valor) + " sin valor en el ejercicio auditado")
    print()
    for e in con_señal[:MAX_LISTA]:
        partes = []
        for s in e["señales"]:
            if s["tipo"] == "tendencia":
                partes.append(s["sentido"] + " " + str(s["años"]) + " años")
            elif s["tipo"] == "salto":
                v = s.get("veces_lo_normal")
                partes.append("salto de " + format(s["importe"], ".4f")
                              + (" (x" + str(v) + " lo normal)" if v else ""))
            elif s["tipo"] == "negativo_persistente":
                partes.append("negativo " + str(s["años"]) + " años")
            else:
                partes.append("cambia de signo")
        actual = e["valores"].get(ejercicios[0]) if ejercicios else None
        print("  [" + e["relevancia"] + "] " + e["codigo"] + " "
              + e["elemento"][:42].ljust(42)
              + (format(actual, ">12.4f") if actual is not None else "          — ")
              + "  " + " · ".join(partes))
    if len(con_señal) > MAX_LISTA:
        print("  (" + str(len(con_señal) - MAX_LISTA) + " más en el JSON)")
    resumen.guardar(ruta_resumen(args.salida))
    print("  resumen      " + ruta_resumen(args.salida))
    return 0


if __name__ == "__main__":
    sys.exit(main())
