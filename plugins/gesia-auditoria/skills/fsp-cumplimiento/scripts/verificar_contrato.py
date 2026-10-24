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
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib_fsp import (  # noqa: E402
    ROLES,
    _distintos,
    _tokens_de_cuenta,
    aviso_periodo_poblacion,
    cargar_facturas,
    cargar_json,
    cargar_muestra,
    cargar_parametros,
    columnas_de_muestra,
    detectar_columnas,
    parse_fecha,
    parse_importe,
    salida_utf8,
)


def tercero_del_mcp(muestra: list[dict], cols: dict, avisos_col: list[str]) -> tuple[str, list[str]]:
    """(linea informativa, avisos que quedan) cuando el tercero es la columna que eligio el MCP.

    Al exportar la muestra tokenizada, el MCP decide el mismo cual es la columna del tercero, la
    seudonimiza por la cuenta y dice por que descarta las demas («'NombreCuenta' descartada porque
    tiene un solo valor en todas las filas»). `afinar_columnas` se va a esa misma columna, y hasta
    el registro del 21/10/2026 eso salia como aviso A00, con otro motivo («solo lleva tokens de
    reserva») y entre lo que hay que contar al entregar: para el auditor era ruido, porque el
    cambio es automatico y no afecta al resultado. Ahora es una linea C02, que no se cuenta.

    Solo en ese caso. Un cambio por el numero de valores distintos, sin tokens de cuenta, lo
    decide el skill y sigue siendo A00.
    """
    ini = detectar_columnas(muestra[0])[0].get("tercero")
    fin = cols.get("tercero")
    # la condicion es exactamente la rama del MCP de afinar_columnas: la final lleva tokens de
    # cuenta y la que se habria elegido por el nombre no lleva ninguno
    if not fin or fin == ini or not _tokens_de_cuenta(muestra, fin) or (ini and _tokens_de_cuenta(muestra, ini)):
        return "", avisos_col
    n = len(muestra)
    linea = (f"C02 · tercero = «{fin}»: es la columna que el MCP eligió al exportar la muestra y seudonimizó "
             f"por la cuenta ({_tokens_de_cuenta(muestra, fin)} de {n} filas)")
    if ini:
        d = _distintos(muestra, ini)
        motivo = ("viene vacía" if d == 0 else f"tiene un solo valor en las {n} filas" if d == 1
                  else "solo lleva tokens de reserva, que no atan a ningún tercero")
        linea += f"; «{ini}» no sirve para cruzar el tercero: {motivo}"
    linea += ". Cambio automático: no afecta al resultado y no hay que contarlo."
    # la rama del MCP deja un solo aviso de tercero, y es este
    return linea, [a for a in avisos_col if not a.startswith("la columna de tercero ")]


_RE_ID_DOC = re.compile(r"DOC [0-9a-f]{4}-([fax]\d{2,})|^([fax]\d{2,})$", re.I)


def _id_doc(fichero) -> str:
    m = _RE_ID_DOC.search(str(fichero or "").strip())
    return (m.group(1) or m.group(2)).lower() if m else ""


def _culpa_del_tachado(ruta_facturas, campo: str = "fecha", afectados=None) -> str:
    """¿Lo tapó la seudonimización, o no estaba? Dice lo que se SABE, y nada más.

    Sin esta frase, un dato ilegible por el escaneo se lee como una incidencia del control.
    Medido el 18/09/2026 sobre 30 páginas de una carpeta real: el tachado no tapó ni una fecha ni
    un importe, y dos páginas no traían fecha legible ni antes de tacharlas.

    Pero el MCP solo comprueba fechas e importes (`tachado.datos_tapados`), NO el número de
    factura: decir del número «es del escaneo» era afirmar lo que no se ha medido, y en el
    registro del 21/10/2026 el lector anotaba que lo había tapado el tachado. Para el número se
    dice que no se comprueba, cuántos de esos documentos conservaron un número de la muestra
    (`tachado.numero_conservado`), lo que anota el lector y `numeros_no_encontrados` si viene.
    `afectados` son las entradas de facturas.json sin ese dato.
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
    afectados = list(afectados or [])
    por_clave = {}
    for d in man.get("documentos", []):
        por_clave[str(d.get("fichero"))] = d
        if d.get("id"):
            por_clave[str(d["id"]).lower()] = d
    docs = [por_clave.get(str(f.get("fichero"))) or por_clave.get(_id_doc(f.get("fichero"))) for f in afectados]
    # el lector deja dicho en notas que el tachado le tapo el dato («tapado por el tachado»)
    del_lector = sum(1 for f in afectados if re.search(r"tach|tapad", str(f.get("notas") or ""), re.I))
    nota_lector = (f" {del_lector} lector(es) anotan que se lo tapó el tachado: pide esos documentos «tal "
                   "cual» o dilo en el papel." if del_lector else "")
    if campo == "numero":
        conservado = sum(1 for d in docs if d and (d.get("tachado") or {}).get("numero_conservado"))
        no_hallados = [str(n) for n in (man.get("numeros_no_encontrados") or [])]
        return (" Con las facturas tachadas no se puede descartar el tachado: el MCP comprueba documento a"
                " documento que no tape fechas ni importes, pero el número no."
                + (f" En {conservado} de ellos el tachado conservó un número de la muestra, así que ahí no"
                   " lo tapó." if conservado else "")
                + nota_lector
                + (f" Números de la muestra que no aparecieron en ningún documento (numeros_no_encontrados):"
                   f" {len(no_hallados)}: " + ", ".join(no_hallados[:8]) + ("…" if len(no_hallados) > 8 else "")
                   + "." if no_hallados else "")
                + " NO es una incidencia del control.")
    tapados = sum((d.get("tachado") or {}).get("datos_tapados", 0) for d in man.get("documentos", []))
    if tapados:
        return (f" ATENCIÓN: el tachado ha tapado {tapados} línea(s) con fecha o importe, así que parte de"
                " esto SÍ es de la seudonimización: pide esos documentos «tal cual» o dilo en el papel.")
    if del_lector:
        return (" El MCP no ha medido ninguna fecha ni ningún importe tapados por el tachado, pero" + nota_lector
                + " NO es una incidencia del control.")
    return (" El tachado no ha tapado ninguna fecha ni ningún importe (lo comprueba el MCP documento a"
            " documento), así que no es del tachado: es del escaneo o del propio documento. NO es una"
            " incidencia del control.")


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
    info_tercero, avisos_col = tercero_del_mcp(muestra, cols, avisos_col)
    if info_tercero:
        print(info_tercero)
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
    # A10 · el periodo de la poblacion frente al ejercicio de la prueba (solo si estan las fechas)
    periodo = aviso_periodo_poblacion(params)
    if periodo:
        avisos.append("A10 · " + periodo)

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
        sin_num_f = [f for f in facturas if not str(f.get("numero") or "").strip()]
        sin_fecha_f = [f for f in facturas if parse_fecha(f.get("fecha")) is None]
        sin_num, sin_fecha = len(sin_num_f), len(sin_fecha_f)
        print(f"C06 · {len(facturas)} documento(s) leídos")
        if sin_total:
            avisos.append(f"A06 · {len(sin_total)} documento(s) sin total legible: {', '.join(map(str, sin_total[:5]))}"
                          + ("…" if len(sin_total) > 5 else "") + ". No podrán casar por importe.")
        if sin_num:
            avisos.append(f"A07 · {sin_num} documento(s) sin número de factura legible: casarán solo por importe y fecha."
                          + _culpa_del_tachado(args.facturas, "numero", sin_num_f))
        if sin_fecha:
            avisos.append(f"A08 · {sin_fecha} documento(s) sin fecha legible."
                          + _culpa_del_tachado(args.facturas, "fecha", sin_fecha_f))
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
