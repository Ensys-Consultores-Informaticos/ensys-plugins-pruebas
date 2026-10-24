"""Lectura y modelo de datos de los cuestionarios de Gesia (`DetalleGuias`).

No imprime nada: devuelve datos. Imprime el `main` de cada script, y acotado.

NO habla con el API de Gesia. Lo hizo hasta el 23/08/2026 —leia el
`http://localhost:{puerto}/gs3` directamente para no meter 94.455 caracteres en el
contexto del modelo— y eso hacia el skill INUTILIZABLE desde Cowork: ni el bash
del contenedor ni el `device_bash` del puente alcanzan el localhost del Windows
del auditor (comprobado con curl, exit 7, en cliente).

Ahora el dato entra por el MCP: el modelo lanza `consultar_gesia` troceado por
una sola consulta con `exportar_consulta`, que lo deja en `cuestionario.json`, y
el resto del flujo lee de disco. Se paga el texto en contexto, y se paga dos veces
(al leerlo y al escribirlo) hasta que el MCP tenga `exportar_consulta` — mejora 3
de `docs/mejoras-mcp.md`. Es el precio de que funcione donde tiene que funcionar.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


def salida_utf8() -> None:
    """Fuerza UTF-8 en stdout/stderr.

    La consola de Windows usa cp1252 por defecto y convierte cada acento en un
    interrogante. Lo que lee el modelo son estos mensajes: si salen mutilados,
    los titulos de las secciones dejan de ser utilizables.
    """
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass

# ── Columnas ──────────────────────────────────────────────────────────────────

# Orden EXACTO del fichero que exporta Gesia. No reordenar: el importador lo
# espera asi, y la comprobacion de fidelidad compara columna a columna.
COLUMNAS = [
    "Prioritaria",
    "CodigoArea",
    "CodigoGuia",
    "CodigoOrden",
    "Punto",
    "DesglosePunto",
    "Descripcion",
    "CodigoClaseReferencia",
    "CodigoReferencia",
    "CodigoRealizado",
    "Respuesta",
    "Comentario",
]

# Tipo con el que cada columna vuelve a escribirse en el .xlsx. Medido sobre el
# export real de AG)20/01 de un expediente el 22/08/2026.
BOOLEANAS = {"Prioritaria"}
ENTERAS = {"CodigoOrden", "Punto", "DesglosePunto", "CodigoRealizado", "Respuesta"}
TEXTO = {"CodigoGuia", "Descripcion", "Comentario"}
# Vacias en las 154 filas de AG)20/01: su tipo no se puede observar. Se deduce
# del valor (vacio -> celda vacia, digitos -> entero, resto -> texto). Si algun
# cuestionario las trae con contenido, esta es la linea que hay que revisar.
AUTO = {"CodigoArea", "CodigoClaseReferencia", "CodigoReferencia"}

# ── Codigos de respuesta ──────────────────────────────────────────────────────

# Confirmado en cliente. No estan en ninguna tabla del .gs3: la
# semantica vive en la aplicacion, asi que esta constante es la unica fuente.
RESPUESTAS = {1: "Si", 2: "No", 3: "No aplica", 4: "Pendiente"}

# El codigo que se pone cuando la memoria no permite responder. La regla es
# deliberadamente conservadora: un 4 de mas cuesta un minuto de revision al
# auditor; un 1 de mas es un desglose que ya no vuelve a mirar nadie.
RESPUESTA_ANTE_LA_DUDA = 4

# ── Consultas, para que el modelo las lance por el MCP ────────────────────────


SQL_REFERENCIAS_CCC = (
    "SELECT CodigoArea, CodigoReferencia, Referencia, CodigoTipoGuia, "
    "Disponible, Realizado, Verificado "
    "FROM Referencias WHERE CodigoTipoGuia = 'CCC' ORDER BY CodigoReferencia"
)


def sql_detalle(guia: str) -> str:
    """Filas de un cuestionario, en el orden del export.

    Se filtra SOLO por `CodigoGuia`, que es texto. Ni una comparacion mas en la
    consulta: `CodigoRealizado` y `DesglosePunto` son numericos y compararlos
    contra una cadena aborta la consulta entera, incluidas las columnas que no
    tenian nada que ver. Todo lo demas se filtra en Python.
    """
    guia_escapado = guia.replace("'", "''")
    return (
        "SELECT " + ", ".join(COLUMNAS) + " FROM DetalleGuias "
        f"WHERE CodigoGuia = '{guia_escapado}' ORDER BY CodigoOrden"
    )


def es_cabecera(fila: dict) -> bool:
    """Una fila con `Punto` pero sin `DesglosePunto` es el titulo del apartado.

    No es una pregunta: no se responde y su `Respuesta` queda vacia, igual que
    en el export de Gesia. Son 17 de las 154 filas de AG)20/01.
    """
    return not str(fila.get("DesglosePunto", "")).strip()


def partir_en_secciones(filas: list[dict]) -> list[dict]:
    """Agrupa las filas por `Punto`, con su titulo y sus preguntas.

    El modelo contesta seccion a seccion, no las 137 preguntas de golpe: cada
    `Punto` es un tema coherente que mapea contra una parte de la memoria.
    """
    secciones: dict[str, dict] = {}
    for fila in filas:
        punto = str(fila.get("Punto", "")).strip()
        seccion = secciones.setdefault(
            punto, {"punto": punto, "titulo": "", "preguntas": []}
        )
        if es_cabecera(fila):
            seccion["titulo"] = str(fila.get("Descripcion", "")).strip()
        else:
            seccion["preguntas"].append(fila)

    return [secciones[p] for p in sorted(secciones, key=lambda x: int(x) if x.isdigit() else 0)]


def orden_de(fila: dict) -> int:
    """El CodigoOrden como numero. -1 si no se puede leer."""
    try:
        return int(str(fila.get("CodigoOrden", "")).strip() or -1)
    except ValueError:
        return -1


def leer_cuestionario(ruta, guia: str = "") -> dict:
    """El cuestionario, venga como venga, con las cuentas ya hechas.

    Acepta dos formas y por una razon concreta: `exportar_consulta` deja en el
    fichero la LISTA de filas tal cual, mientras que antes habia un paso de
    fusion que escribia un objeto con metadatos. Aceptar las dos evita romper lo
    que ya funcionaba y ahorra una vuelta si el fichero se genero de otro modo.

    Las derivadas -secciones, recuento de preguntas, cuantas estan ya
    contestadas- se calculan aqui y no se leen del fichero: si se leyeran,
    bastaria un fichero mal escrito para que el papel dijera que hay 154
    preguntas cuando trae 120.
    """
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    if isinstance(datos, dict):
        filas = None
        for clave in ("filas", "rows", "resultado", "data"):
            if isinstance(datos.get(clave), list):
                filas = datos[clave]
                break
        if filas is None:
            raise RuntimeError(
                str(ruta) + ": es un objeto y no encuentro la lista de filas "
                "dentro (pruebo 'filas', 'rows', 'resultado', 'data')")
        guia = guia or str(datos.get("guia", "") or "")
    elif isinstance(datos, list):
        filas = datos
    else:
        raise RuntimeError(str(ruta) + ": se esperaba una lista de filas")

    if not filas:
        raise RuntimeError(str(ruta) + ": no trae ni una fila. Si la consulta "
                           "salio vacia, comprueba el CodigoGuia: en LIKE el "
                           "comodin es el porcentaje, no el asterisco.")

    filas = sorted(filas, key=orden_de)
    secciones = partir_en_secciones(filas)
    preguntas = [f for f in filas if not es_cabecera(f)]
    contestadas = [f for f in preguntas if str(f.get("Respuesta", "")).strip()]
    return {
        "guia": guia or str(filas[0].get("CodigoGuia", "") or ""),
        "n_filas": len(filas),
        "n_cabeceras": len(filas) - len(preguntas),
        "n_preguntas": len(preguntas),
        "n_contestadas": len(contestadas),
        "indice_secciones": [
            {"punto": s["punto"], "titulo": s["titulo"],
             "n_preguntas": len(s["preguntas"])}
            for s in secciones
        ],
        "secciones": secciones,
        "filas": filas,
    }


def huecos_de_orden(filas: list) -> list:
    """CodigoOrden que faltan entre el primero y el ultimo.

    Un hueco significa que el cuestionario llego incompleto, y eso no se nota al
    leerlo: un cuestionario al que le faltan doce preguntas se rellena igual de
    bien y el papel sale con la misma pinta. Cuando la consulta iba por tramos,
    el motivo tipico era un tramo cortado por el limite de caracteres; ahora
    viene de una sola consulta, pero la comprobacion sigue valiendo para
    cualquier otra causa de perdida.
    """
    claves = sorted({orden_de(f) for f in filas if orden_de(f) >= 0})
    if not claves:
        return []
    return [n for n in range(claves[0], claves[-1] + 1) if n not in set(claves)]


def entero_o_none(bruto) -> int | None:
    texto = str(bruto if bruto is not None else "").strip()
    if not texto:
        return None
    try:
        return int(float(texto.replace(",", ".")))
    except ValueError:
        return None


def valor_celda(columna: str, bruto) -> object:
    """Convierte el valor que devuelve el API al tipo que lleva el .xlsx.

    El vacio siempre es celda vacia (`None`), nunca cadena vacia: el export de
    Gesia lo hace asi y es lo que probablemente espere el importador.
    """
    texto = str(bruto if bruto is not None else "").strip()
    if not texto:
        return None

    if columna in BOOLEANAS:
        return texto.lower() in ("true", "1", "-1", "si", "sí", "verdadero")
    if columna in ENTERAS:
        return entero_o_none(texto)
    if columna in TEXTO:
        return str(bruto)
    # AUTO
    return int(texto) if texto.lstrip("-").isdigit() else str(bruto)
