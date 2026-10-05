# -*- coding: utf-8 -*-
"""Lo comun de estados-financieros: cargar lo exportado del expediente y cuadrar.

Nada de esto inventa cifras. Lee lo que el MCP ha exportado del .gs3 y comprueba que
encaja; cuando no encaja, lo dice con nombres y numeros, nunca lo arregla por su cuenta.

El modelo de datos sale medido del expediente y del codigo Power Query del cuadro de mando
que la firma ya usa (`docs/esquema-efe.md` para el modulo hermano, y la fase 1 del contrato
de este skill). Dos reglas que no son evidentes y que aqui se respetan:

  * **Solo suman las cuentas con `AsignadaCCAA`.** El plan tiene la misma cuenta a varios
    niveles de digitos; sumar todas cuenta el dinero dos o tres veces. El cuadro de mando de
    Excel llama a esa marca `NivelEEFF` y hace lo mismo.
  * **Solo suman las lineas con `CuentasAsignables`.** Las demas son totales y subtotales del
    modelo oficial; incluirlas duplica igual.
"""

from __future__ import annotations

import io
import json
import re
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# Dos decimales, que es el redondeo del euro. La tolerancia se da por linea, no en
# porcentaje: un descuadre de verdad en unas cuentas anuales no es proporcional al tamaño.
DECIMALES = 2
TOLERANCIA = 0.01

# Las columnas de importe de la estructura son posicionales, NO años: SaldoAuditoria1 es el
# ejercicio mas reciente. Quien las lea sin cruzar con Auditorias atribuye cifras al año que
# no es, y nada avisa porque el numero es valido. Se cruza siempre.
COLUMNAS_SALDO = tuple(f"SaldoAuditoria{i}" for i in range(1, 6))

ESTADO_BALANCE = "Balance"
ESTADO_PYG = "PyG"


def salida_utf8() -> None:
    """La consola de Windows es cp1252 y se atraganta con los iconos de estado."""
    for flujo in ("stdout", "stderr"):
        f = getattr(sys, flujo, None)
        if f is not None and hasattr(f, "reconfigure"):
            try:
                f.reconfigure(encoding="utf-8")
            except Exception:
                pass


def leer_json(ruta: str) -> list | dict:
    with io.open(ruta, encoding="utf-8-sig") as fh:
        return json.load(fh)


def redondear(v: float) -> float:
    """Redondeo contable: el medio centimo sube (HALF_UP), como en cualquier libro.

    `round()` de Python redondea AL PAR y ademas arrastra el error del binario: round(1000.555, 2)
    da 1000.55, no 1000.56. Sobre un saldo suelto son ocho centimos al año; sobre un balance que
    tiene que cuadrar al centimo, es una discusion con el auditor que no toca tener.
    """
    try:
        return float(Decimal(str(v)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return 0.0


def a_float(v) -> float:
    """Los importes llegan del API como texto con coma decimal y punto de millar."""
    if v is None or v == "":
        return 0.0
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
        return 0.0


def es_si(v) -> bool:
    """True/False del API vienen como texto."""
    return str(v).strip().lower() in ("true", "sí", "si", "-1", "1", "yes")


def texto(v) -> str:
    return "" if v is None else str(v).strip()


# ── los nombres de terceros tienen que venir tokenizados ─────────────────────
# Misma regla que el MCP (_es_cuenta_tercero): cuenta de tercero a maximo detalle. El
# 05/10/2026, en Cowork, la sesion exporto el plan sin perfil -los nombres de proveedores y
# clientes en claro- a una carpeta del expediente en OneDrive. Desde la 2.0.7 el skill pone el
# perfil `estados-financieros`, que los tokeniza, y estos scripts se niegan a trabajar con un
# plan que los traiga en claro: si alguien se salta el perfil, no sale ningun papel.
GRUPOS_TERCERO = ("40", "41", "43", "44", "46", "47", "55", "64")
_RE_TOKEN = re.compile(r"^(?:PROV|CLI|TER) \S+$")


def nombres_en_claro(cuentas) -> list:
    """Las cuentas de tercero cuyo nombre NO viene como token (PROV/CLI/TER + cuenta)."""
    malas = []
    for c in cuentas or []:
        cuenta, nombre = texto(c.get("Cuenta")), texto(c.get("Nombre"))
        if (len(cuenta) > 3 and cuenta.isdigit() and cuenta[:2] in GRUPOS_TERCERO
                and nombre and not _RE_TOKEN.match(nombre)):
            malas.append(cuenta)
    return malas


def exigir_tokens(cuentas, en_claro_por_el_auditor: bool = False) -> bool:
    """True si se puede seguir. Si no, lo dice -con el numero de cuenta, nunca el nombre-."""
    malas = nombres_en_claro(cuentas)
    if not malas or en_claro_por_el_auditor:
        return True
    print(f"❌ {len(malas)} cuentas de tercero traen el NOMBRE EN CLARO (la primera, la {malas[0]}). "
          "Falta configurar(perfil = \"estados-financieros\") ANTES de exportar: el perfil los "
          "tokeniza y el papel los recupera al final con rehidratar. Vuelve a exportar el plan con el "
          "perfil puesto y repite; no muevas este fichero a ningun sitio, y borralo con "
          "limpiar_exportaciones(). Solo si el auditor ha apagado él la tokenización "
          "(configurar dice «forzado por el auditor») se sigue, con --nombres-en-claro. No se genera nada.")
    return False


def ejercicios(filas_auditorias: list) -> dict:
    """{'1': '2025', '2': '2024', ...}. Sin esto no se puede etiquetar ninguna columna."""
    res = {}
    for f in filas_auditorias or []:
        cod, anio = texto(f.get("CodigoAuditoria")), texto(f.get("Año") or f.get("Anio"))
        if cod and anio:
            res[cod] = anio
    return res


# Dentro de un mismo numero de orden de la PyG, primero el detalle y despues los subtotales:
# «20. Impuestos sobre beneficios» va antes de «A.4) RESULTADO DEL EJERCICIO...», no al reves.
RANGO_CLASE = {"I": 0, "ST": 1, "T": 2}


def _tramo(v) -> tuple:
    """Un tramo del codigo de linea, ordenado como en el modelo oficial.

    Vacio primero, que la cabecera del bloque va antes que sus lineas; luego los numeros por
    su valor, que es lo que evita el 1, 10, 11, 2; y al final las letras de los desgloses.
    """
    t = texto(v)
    if not t:
        return (0, 0, "")
    if re.fullmatch(r"-?\d+", t):
        return (1, int(t), "")
    return (2, 0, t.lower())


def _clave_orden(fila: dict) -> tuple:
    """El orden del modelo oficial, no el alfabetico.

    La PyG trae el suyo ya hecho en `CodigoOrdenI`, que es por el que ordena el cuadro de
    mando de la firma. El balance no tiene columna de orden y hay que reconstruirlo con sus
    tramos, donde `CodigoSeccion` es LA LETRA del bloque (A, B, C, TG) y no un numero: leerla
    como numero colapsa las secciones y mezcla el activo corriente con el no corriente, que es
    un balance con pinta correcta y las lineas cambiadas de sitio.
    """
    return (texto(fila.get("Estado")),
            texto(fila.get("Activo_Pasivo")),
            _tramo(fila.get("CodigoOrdenI")),
            RANGO_CLASE.get(texto(fila.get("CodigoClase")).upper(), 0),
            _tramo(fila.get("CodigoSeccion")),
            _tramo(fila.get("CodigoEpigrafe")),
            _tramo(fila.get("CodigoDesglose")),
            _tramo(fila.get("CodigoSubDesglose")),
            texto(fila.get("CodigoCCAA")))


def estructura_ordenada(filas: list) -> list:
    return sorted(filas or [], key=_clave_orden)


def hojas(filas: list) -> list:
    """Las lineas que admiten cuentas: las unicas que suman. El resto son subtotales."""
    return [f for f in filas or [] if es_si(f.get("CuentasAsignables"))]


def saldo(fila: dict, indice: int) -> float:
    return redondear(a_float(fila.get(f"SaldoAuditoria{indice}")))


def cuadre_balance(filas: list, indice: int) -> float:
    """Activo + Pasivo sobre las lineas que admiten cuentas.

    En la tabla cruda el pasivo viene con el signo contrario al activo, asi que un balance
    cuadrado suma CERO. Medido en un expediente real: cero en los cinco ejercicios.
    """
    total = 0.0
    for f in hojas(filas):
        if texto(f.get("Estado")) == ESTADO_BALANCE:
            total += saldo(f, indice)
    return round(total, DECIMALES)


def suma_por_epigrafe(filas: list, indice: int) -> dict:
    """{CodigoCCAA del epigrafe: suma de sus desgloses}, para contrastar con el subtotal."""
    res: dict = {}
    for f in hojas(filas):
        padre = texto(f.get("CodigoCCAA"))
        if not padre:
            continue
        # el epigrafe padre es el codigo sin su ultimo tramo: «Activo A)I.1.» -> «Activo A)I.»
        tramos = [t for t in padre.split(".") if t]
        if len(tramos) > 1:
            clave = ".".join(tramos[:-1]) + "."
            res[clave] = round(res.get(clave, 0.0) + saldo(f, indice), DECIMALES)
    return res


def cuentas_por_epigrafe(cuentas: list, campo_saldo: str = "SaldoAuditoria") -> dict:
    """{CodigoCCAA: suma de las cuentas ASIGNADAS a ese epigrafe}.

    Solo las asignadas, por lo que dice la cabecera del modulo: el plan repite la misma
    cuenta a 1, 2, 3 y 4 digitos, y sumarlas todas multiplica el saldo.
    """
    res: dict = {}
    for c in cuentas or []:
        if not es_si(c.get("AsignadaCCAA")):
            continue
        cod = texto(c.get("CodigoCCAA"))
        if cod:
            res[cod] = round(res.get(cod, 0.0) + a_float(c.get(campo_saldo)), DECIMALES)
    return res


def cadena_del_saldo(cuenta: dict) -> tuple:
    """(cliente, ajustes, reclasificaciones, auditoria) de una cuenta del ejercicio en curso.

    Medido en un expediente real: cliente + ajustes + reclasificaciones = auditoria en las
    4.569 cuentas, sin una sola excepcion. Es la columna vertebral del papel de revision.
    """
    return (a_float(cuenta.get("SaldoCliente")), a_float(cuenta.get("SaldoAj")),
            a_float(cuenta.get("SaldoRec")), a_float(cuenta.get("SaldoAuditoria")))


# Gesia mantiene un grupo 0 «Explotacion y Cambios en el Patrimonio Neto» que NO es del PGC:
# es el contraasiento interno con el que cuadra los ajustes. No esta asignado a ningun epigrafe
# y no debe estarlo. Medido en dos expedientes: su ajuste es el de las cuentas asignadas
# cambiado de signo.
GRUPO_CUADRE = "0"


def ajustes_sin_epigrafe(cuentas: list) -> list:
    """Cuentas con ajuste cuyo importe no llega a ningun epigrafe del modelo.

    Una cuenta llega si esta asignada, si lo esta alguna de sus agregadas -el ajuste de 4100
    se ve en 410- o si lo esta alguna de sus desglosadas. Si no llega por ninguna via, el
    ajuste existe en el expediente y NO aparece en las cuentas anuales: hay que decirlo, no
    descartarlo en silencio.
    """
    asignadas = {texto(c.get("Cuenta")) for c in cuentas or [] if es_si(c.get("AsignadaCCAA"))}
    fuera = []
    for c in cuentas or []:
        cod = texto(c.get("Cuenta"))
        if not cod or cod.startswith(GRUPO_CUADRE):
            continue
        aj, rec = a_float(c.get("SaldoAj")), a_float(c.get("SaldoRec"))
        if abs(aj) <= TOLERANCIA and abs(rec) <= TOLERANCIA:
            continue
        if cod in asignadas:
            continue
        if any(a.startswith(cod) or cod.startswith(a) for a in asignadas if a != cod):
            continue
        fuera.append((cod, texto(c.get("Nombre")), redondear(aj + rec)))
    return fuera


# ── patrimonio neto ────────────────────────────────────────────────────────────
# El patrimonio neto es la seccion A del pasivo. Se reconoce por ahi y no por el texto del
# CodigoCCAA: «Pasivo A)...» es como lo escribe el modelo normal, pero el rotulo cambia entre
# modelos y una fundacion no lo llama igual que una sociedad.
SECCION_PN = "A"


def lineas_pn(estructura: list) -> list:
    return [f for f in estructura or []
            if texto(f.get("Estado")) == ESTADO_BALANCE
            and texto(f.get("Activo_Pasivo")) == "PASIVO"
            and texto(f.get("CodigoSeccion")) == SECCION_PN]


def movimiento_cuenta(cuenta: dict) -> tuple:
    """(apertura, movimiento del cliente, ajustes, reclasificaciones, cierre auditado).

    El movimiento del ejercicio es SaldoCliente menos SaldoAnterior, NO DebeCliente menos
    HaberCliente: esos dos acumulados llevan dentro la apertura. Medido en los dos
    expedientes: DebeCliente - HaberCliente = SaldoCliente en las 403 cuentas de grupo 1, 8 y
    9, apertura incluida. Tomar el Debe por movimiento del año se comeria el saldo inicial.
    """
    ant = a_float(cuenta.get("SaldoAnterior"))
    cli = a_float(cuenta.get("SaldoCliente"))
    return (ant, redondear(cli - ant), a_float(cuenta.get("SaldoAj")),
            a_float(cuenta.get("SaldoRec")), a_float(cuenta.get("SaldoAuditoria")))


def movimiento_por_epigrafe(cuentas: list, codigos: set) -> dict:
    """{CodigoCCAA: [apertura, movimiento, ajustes, reclasificaciones, cierre]}.

    Solo cuentas ASIGNADAS, por lo de siempre: el plan repite la cuenta a varios niveles.
    """
    res: dict = {}
    for c in cuentas or []:
        cod = texto(c.get("CodigoCCAA"))
        if cod not in codigos or not es_si(c.get("AsignadaCCAA")):
            continue
        fila = res.setdefault(cod, [0.0] * 5)
        for i, v in enumerate(movimiento_cuenta(c)):
            fila[i] = redondear(fila[i] + v)
    return res
