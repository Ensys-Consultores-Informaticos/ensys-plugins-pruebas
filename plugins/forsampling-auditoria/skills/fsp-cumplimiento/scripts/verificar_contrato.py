"""Comprueba en ejecucion lo que la prueba de cumplimiento asume.

No fiarse de la documentacion: lo que se asume, se comprueba. Un papel de trabajo
bonito sobre datos mal entendidos es peor que no tener papel.

    python verificar_contrato.py --muestra muestra.json --parametros parametros.json \
        --facturas facturas.json [--roles roles.json]

Codigos de salida:
  0  todo encaja
  1  avisos: se puede seguir, pero hay que leerlos y contarlos en el papel
  2  no se puede hacer la prueba. No se genera nada.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_fsp import (  # noqa: E402
    ROLES,
    cargar_facturas,
    cargar_json,
    cargar_muestra,
    cargar_parametros,
    columnas_de_muestra,
    parse_fecha,
    parse_importe,
    salida_utf8,
)


def _culpa_del_tachado(ruta_facturas) -> str:
    """¿Lo tapó la anonimización, o no estaba? El MCP lo cuenta por documento en el manifiesto.

    Sin esta frase, un dato ilegible por el escaneo se lee como una incidencia del control.
    Medido el 18/09/2026 sobre 30 páginas de una carpeta real: el tachado no tapó ni una fecha ni
    un importe, y dos páginas no traían fecha legible ni antes de tacharlas.
    """
    base = Path(ruta_facturas).resolve().parent
    man = None
    for cand in (base / "manifiesto.json", base / "facturas" / "manifiesto.json"):
        try:
            if cand.exists():
                man = cargar_json(str(cand)); break
        except Exception:
            pass
    if not isinstance(man, dict) or man.get("origen") != "mcp":
        return ""
    tapados = sum((d.get("tachado") or {}).get("datos_tapados", 0) for d in man.get("documentos", []))
    if tapados:
        return (f" ATENCIÓN: el tachado ha tapado {tapados} línea(s) con fecha o importe, así que parte de"
                " esto SÍ es de la anonimización: pide esos documentos «tal cual» o dilo en el papel.")
    return (" El tachado no ha tapado ninguna fecha ni ningún importe (lo comprueba el MCP documento a"
            " documento), así que es del escaneo o del propio documento: NO es una incidencia del control.")


def main() -> int:
    salida_utf8()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--muestra", required=True, help="exportar_consulta(entidad='muestra', id=N)")
    p.add_argument("--parametros", required=True, help="obtener_entidad('parametros', id=N), guardado tal cual")
    p.add_argument("--facturas", required=True, help="lo leido de los documentos, una entrada por fichero")
    p.add_argument("--roles", help="{AtributoId: rol} confirmado por el auditor")
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
    print(f"C01 · {len(muestra)} elemento(s) seleccionados")

    # C02 · las columnas de la poblacion se reconocen. Sin importe o sin fecha no hay cruce.
    cols, faltan, avisos_col = columnas_de_muestra(muestra)
    print("C02 · columnas: " + ", ".join(f"{r}={c}" for r, c in cols.items()))
    for a in avisos_col:
        avisos.append("A00 · " + a)
    if "importe" not in cols or "fecha" not in cols:
        errores.append("C02 · no reconozco la columna de importe o la de fecha en la población: "
                       + ", ".join(muestra[0].keys()) + ". Sin ellas no se puede cruzar con los documentos.")
    if "documento" not in cols:
        avisos.append("A01 · la población no trae número de factura ni concepto: el cruce va solo por "
                      "importe y fecha, y el papel lo dice.")
    if "id" not in cols:
        avisos.append("A02 · la población no trae columna <Tabla>_ID: no se podrá comparar con la "
                      "evaluación del auditor si la hay.")

    # C03 · importes y fechas de la muestra se interpretan
    if not errores:
        malos_imp = sum(1 for f in muestra if parse_importe(f.get(cols["importe"])) is None)
        malas_fec = sum(1 for f in muestra if parse_fecha(f.get(cols["fecha"])) is None)
        if malos_imp:
            errores.append(f"C03 · {malos_imp} elemento(s) con importe no interpretable en {cols['importe']}.")
        if malas_fec:
            errores.append(f"C03 · {malas_fec} elemento(s) con fecha no interpretable en {cols['fecha']}.")
        if not malos_imp and not malas_fec:
            print("C03 · importes y fechas de la muestra se interpretan")
        ceros = sum(1 for f in muestra if (parse_importe(f.get(cols["importe"])) or 0) == 0)
        if ceros:
            avisos.append(f"A03 · {ceros} elemento(s) con importe 0: no se pueden casar por importe.")

    # C04 · la prueba es de cumplimiento y tiene atributos
    try:
        params = cargar_parametros(args.parametros)
    except (ValueError, FileNotFoundError) as exc:
        print("C04 ERROR: " + str(exc))
        return 2
    tipo = str(params.get("Tipo") or "").strip()
    atributos = params.get("atributos") or []
    if tipo and tipo.lower() != "cumplimiento":
        errores.append(f"C04 · la prueba {params.get('MuestraId')} es de tipo '{tipo}', no de cumplimiento. "
                       "Este skill evalúa atributos Sí/No; una MUM o una circularización van por otro.")
    if not atributos:
        errores.append("C04 · la prueba no tiene atributos definidos en el .cli: no hay controles que evaluar.")
    else:
        print(f"C04 · prueba {params.get('MuestraId')} «{params.get('Prueba')}» ({tipo}), "
              f"{len(atributos)} atributo(s): " + " · ".join(f"A{a.get('AtributoId')} {a.get('Nombre')}" for a in atributos))

    # C05 · los roles confirmados cubren todos los atributos y son roles conocidos
    if args.roles:
        try:
            roles = cargar_json(args.roles)
        except (ValueError, FileNotFoundError) as exc:
            print("C05 ERROR: " + str(exc))
            return 2
        sin_rol = [str(a.get("AtributoId")) for a in atributos if str(a.get("AtributoId")) not in roles]
        raros = [f"A{k}={v}" for k, v in roles.items() if v not in ROLES]
        if sin_rol:
            errores.append("C05 · atributos sin rol confirmado: A" + ", A".join(sin_rol)
                           + ". Cada atributo lleva documento / calculo / contabilizacion / auditor.")
        if raros:
            errores.append("C05 · roles desconocidos: " + ", ".join(raros) + ". Los válidos son "
                           + ", ".join(ROLES) + ".")
        if not sin_rol and not raros:
            n_aud = sum(1 for v in roles.values() if v == "auditor")
            print(f"C05 · roles confirmados: {len(roles) - n_aud} atributo(s) los evalúa el skill, "
                  f"{n_aud} quedan al auditor")
            if len(roles) - n_aud == 0:
                avisos.append("A04 · todos los atributos quedan al auditor: el papel solo localizará documentos.")
    else:
        avisos.append("A05 · sin --roles: se usa la propuesta automática por el nombre del atributo. "
                      "El SKILL.md manda confirmarla con el auditor antes.")

    # C06 · los documentos leidos se interpretan
    try:
        facturas = cargar_facturas(args.facturas)
    except (ValueError, FileNotFoundError) as exc:
        print("C06 ERROR: " + str(exc))
        return 2
    if not facturas:
        errores.append("C06 · facturas.json no trae ningún documento leído.")
    else:
        sin_total = [f.get("fichero") for f in facturas if parse_importe(f.get("total")) is None]
        sin_num = sum(1 for f in facturas if not str(f.get("numero") or "").strip())
        sin_fecha = sum(1 for f in facturas if parse_fecha(f.get("fecha")) is None)
        print(f"C06 · {len(facturas)} documento(s) leídos")
        if sin_total:
            avisos.append(f"A06 · {len(sin_total)} documento(s) sin total legible: {', '.join(map(str, sin_total[:5]))}"
                          + ("…" if len(sin_total) > 5 else "") + ". No podrán casar por importe.")
        if sin_num:
            avisos.append(f"A07 · {sin_num} documento(s) sin número de factura legible: casarán solo por importe y fecha."
                          + _culpa_del_tachado(args.facturas))
        if sin_fecha:
            avisos.append(f"A08 · {sin_fecha} documento(s) sin fecha legible." + _culpa_del_tachado(args.facturas))
        if len(facturas) < len(muestra):
            avisos.append(f"A09 · hay {len(muestra)} elementos y {len(facturas)} documentos: al menos "
                          f"{len(muestra) - len(facturas)} elemento(s) quedarán sin factura.")

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
