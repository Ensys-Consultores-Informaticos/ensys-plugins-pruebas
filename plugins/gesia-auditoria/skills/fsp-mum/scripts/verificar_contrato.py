"""Comprueba en ejecucion lo que la prueba MUM asume.

No fiarse de la documentacion: lo que se asume, se comprueba. Un papel de trabajo
bonito sobre datos mal entendidos es peor que no tener papel.

    python verificar_contrato.py --muestra muestra.json --parametros parametros.json \
        --facturas facturas.json [--evaluacion evaluacion.json]

Codigos de salida:
  0  todo encaja
  1  avisos: se puede seguir, pero hay que leerlos y contarlos al entregar
  2  no se puede hacer la prueba. No se genera nada.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_fsp import (  # noqa: E402
    cargar_evaluacion,
    cargar_facturas,
    cargar_muestra,
    cargar_parametros,
    columnas_de_muestra,
    parse_fecha,
    parse_importe,
    salida_utf8,
)


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--muestra", required=True, help="exportar_consulta(entidad='muestra', id=N)")
    p.add_argument("--parametros", required=True, help="obtener_entidad('parametros', id=N), guardado tal cual")
    p.add_argument("--facturas", required=True, help="lo leido de los documentos, una entrada por fichero")
    p.add_argument("--evaluacion", help="exportar_consulta(entidad='evaluacion', id=N), para comparar")
    args = p.parse_args()

    errores: list[str] = []
    avisos: list[str] = []

    # C01 · la muestra se lee y trae filas
    try:
        muestra = cargar_muestra(args.muestra)
    except (ValueError, FileNotFoundError) as exc:
        print("C01 ERROR: " + str(exc))
        return 2
    if not muestra:
        print("C01 ERROR: la muestra no trae ninguna fila. ¿Se exportó la entidad 'muestra' con el id correcto?")
        return 2
    reps = sum(parse_importe(f.get("Repeticiones")) or 1 for f in muestra)
    print(f"C01 · {len(muestra)} elemento(s) seleccionados, {reps:g} unidad(es) de muestreo con las repeticiones")

    # C02 · las columnas de la poblacion se reconocen. En una MUM el importe es
    # lo que se mide, asi que sin el no hay prueba; la fecha solo ayuda a cruzar.
    cols, faltan, avisos_col = columnas_de_muestra(muestra)
    print("C02 · columnas: " + ", ".join(f"{r}={c}" for r, c in cols.items()))
    for a in avisos_col:
        avisos.append("A00 · " + a)
    if "importe" not in cols:
        errores.append("C02 · no reconozco la columna de importe en la población: "
                       + ", ".join(muestra[0].keys())
                       + ". En una MUM el importe es lo que se mide: sin él no hay prueba.")
    if "fecha" not in cols:
        avisos.append("A01 · la población no trae fecha: el cruce con los documentos pierde una clave.")
    if "documento" not in cols:
        avisos.append("A02 · la población no trae número de factura ni concepto: el cruce va por "
                      "importe, tercero y fecha, y el papel lo dice.")
    if "id" not in cols:
        avisos.append("A03 · la población no trae columna <Tabla>_ID: no se podrá comparar con la "
                      "evaluación del auditor si la hay.")

    # C03 · los importes se interpretan, que es lo que se va a restar
    if not errores:
        malos = [f for f in muestra if parse_importe(f.get(cols["importe"])) is None]
        if malos:
            errores.append(f"C03 · {len(malos)} elemento(s) con importe no interpretable en {cols['importe']}. "
                           "Son los que se comparan con el documento: no se puede seguir.")
        else:
            imp = [parse_importe(f.get(cols["importe"])) or 0.0 for f in muestra]
            pos, neg = sum(1 for v in imp if v > 0), sum(1 for v in imp if v < 0)
            print(f"C03 · importes interpretados: {pos} positivo(s), {neg} negativo(s)")
            if pos and neg:
                avisos.append("A04 · la muestra mezcla importes positivos y negativos. El error sigue el signo "
                              "del saldo, pero conviene mirar si la población debía filtrarse por signo.")
        ceros = sum(1 for f in muestra if (parse_importe(f.get(cols["importe"])) or 0) == 0)
        if ceros:
            avisos.append(f"A05 · {ceros} elemento(s) con importe 0: ni casan por importe ni admiten tasa de error.")

    # C04 · la prueba es MUM
    try:
        params = cargar_parametros(args.parametros)
    except (ValueError, FileNotFoundError) as exc:
        print("C04 ERROR: " + str(exc))
        return 2
    tipo = str(params.get("Tipo") or "").strip()
    if tipo and tipo.lower() != "mum":
        errores.append(f"C04 · la prueba {params.get('MuestraId')} es de tipo '{tipo}', no MUM. "
                       "Este skill mide importes y errores; una de cumplimiento evalúa atributos Sí/No "
                       "y va por fsp-cumplimiento.")
    else:
        pr = params.get("parametros") or {}
        et = parse_importe(pr.get("ErrorTolerableValor"))
        print(f"C04 · prueba {params.get('MuestraId')} «{params.get('Prueba')}» (MUM) · "
              f"unidad {pr.get('UnidadMuestreo') or '—'} · población {pr.get('PoblacionNumElementos') or '—'} "
              f"elementos · error tolerable {('—' if et is None else f'{et:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.'))}")
        deseado = parse_importe(pr.get("TamanoMuestraDeseado"))
        if deseado is not None and abs(deseado - reps) > 0.01:
            avisos.append(f"A06 · el tamaño de muestra deseado es {deseado:g} y las repeticiones suman {reps:g}. "
                          "No es un error del skill: puede que la selección se ampliara o se recortara.")

    # C05 · los documentos leidos se interpretan
    try:
        facturas = cargar_facturas(args.facturas)
    except (ValueError, FileNotFoundError) as exc:
        print("C05 ERROR: " + str(exc))
        return 2
    if not facturas:
        errores.append("C05 · facturas.json no trae ningún documento leído.")
    else:
        sin_imp = [f.get("fichero") for f in facturas
                   if parse_importe(f.get("total")) is None and parse_importe(f.get("base")) is None]
        sin_base = sum(1 for f in facturas if parse_importe(f.get("base")) is None)
        sin_fecha = sum(1 for f in facturas if parse_fecha(f.get("fecha")) is None)
        print(f"C05 · {len(facturas)} documento(s) leídos")
        if sin_imp:
            avisos.append(f"A07 · {len(sin_imp)} documento(s) sin base ni total legibles: "
                          f"{', '.join(map(str, sin_imp[:5]))}" + ("…" if len(sin_imp) > 5 else "")
                          + ". No pueden sostener ningún importe.")
        if sin_base:
            avisos.append(f"A08 · {sin_base} documento(s) sin base imponible legible. Si esta población "
                          "contabiliza por la base, esos elementos no se podrán medir.")
        if sin_fecha:
            avisos.append(f"A09 · {sin_fecha} documento(s) sin fecha legible.")
        if len(facturas) < len(muestra):
            avisos.append(f"A10 · hay {len(muestra)} elementos y {len(facturas)} documentos: al menos "
                          f"{len(muestra) - len(facturas)} elemento(s) quedarán sin importe según auditoría.")

    # C06 · si hay evaluacion del auditor, tiene la forma de una MUM
    if args.evaluacion:
        try:
            evaluacion = cargar_evaluacion(args.evaluacion)
        except (ValueError, FileNotFoundError) as exc:
            print("C06 ERROR: " + str(exc))
            return 2
        filas_ev = (evaluacion or {}).get("filas") or []
        if filas_ev:
            faltan_col = [c for c in ("SaldoAuditoria", "ErrorAuditoria") if c not in filas_ev[0]]
            if faltan_col:
                errores.append("C06 · la evaluación no tiene la forma de una MUM: faltan "
                               + ", ".join(faltan_col)
                               + ". Una evaluación con A1..An es de una prueba de cumplimiento.")
            else:
                print(f"C06 · evaluación del auditor: {len(filas_ev)} fila(s) con SaldoAuditoria y ErrorAuditoria")

    if errores:
        for e in errores:
            print("\n" + e)
        print("\nNo se puede hacer la prueba.")
        return 2
    for a in avisos:
        print("\n" + a)
    return 1 if avisos else 0


if __name__ == "__main__":
    sys.exit(main())
