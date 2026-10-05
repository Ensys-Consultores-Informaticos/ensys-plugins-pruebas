"""Catalogo de riesgos, umbrales y deteccion de tipo de entidad.

No imprime: devuelve datos. Imprime el main de cada script.

El catalogo sale de la tabla RiesgosNIAS del MASTER de Gesia, que es otro fichero
distinto del expediente, y se lee EN CADA EJECUCION: el MCP lo vuelca con
`exportar_consulta(entidad='catalogo_riesgos')` y `extraer_catalogo.py` lo
normaliza en el directorio de trabajo.

Hasta el 26/08/2026 viajaba empaquetado en `datos/riesgos.json`: 240 KB con la
metodologia del master, en claro, en cada copia distribuida. Leerlo del master de
cada cliente lo protege de verdad -contraseña del .gs3 y licencia de Gesia- y
ademas propone lo que ESE auditor tiene en su programa, no lo que tenia el master
con el que se construyo el paquete.
"""

from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

# ── Umbrales. Fijados en cliente ─────────────────────────────────
# Son relativos, no importes: no se anclan a la importancia relativa del encargo
# porque miden comportamiento (una variacion, una concentracion), no error.
VARIACION = 0.20            # variacion interanual relevante: mas del 20 %
CONCENTRACION = 0.30        # un epigrafe que pesa mas del 30 % de su masa
EJERCICIOS_PERDIDAS = 3     # perdidas en 3 o mas de los 5 ejercicios
EJERCICIOS = 5              # SaldoAuditoria1..5

# Cuantos riesgos se proponen. Es orientativo: si las cifras no dan para mas, se
# proponen menos y el informe lo dice. Los dos obligatorios cuentan dentro.
MIN_RIESGOS = 5
MAX_RIESGOS = 10

# Van siempre, digan lo que digan las cifras: son los dos riesgos que la NIA-ES
# 240 presume en todo encargo. Se guardan por NOMBRE, y no por numero, a
# proposito.
#
# `IdRiesgo` NO identifica un riesgo: es la numeracion interna del fichero que se
# esta leyendo, y cambia de un master a otro. Medido el 04/09/2026 sobre los dos
# masters de la firma:
#
#     riesgo                            Master 25 (106)   Master 21 (100)
#     Integridad de las ventas                18                97
#     Elusion de controles                    27                28
#
# Y en un expediente la tabla viene renumerada desde 1 con los pocos riesgos que
# el auditor ya eligio para ESE encargo: 6 en un caso real.
#
# Hasta el 04/09/2026 aqui habia `OBLIGATORIOS = (18, 27)`. Acierta contra el
# master 25 y FALLA EN SILENCIO contra cualquier otro: contra el master 21 mete
# "Perdida de la concesion administrativa" y "Obsolescencia del producto en
# catalogo" rotulados como de inclusion obligatoria por la NIA-ES 240, y deja
# fuera los dos que si lo son. La validacion pasaba limpia porque comprobaba que
# los numeros estuvieran en el catalogo, no que riesgo era cada numero. Lo
# descubrio una ejecucion real contra el master 21.
#
# Es el mismo fallo que `CodigoReferencia` (mejora 1 de docs/mejoras-mcp.md): un
# codigo que parece estable entre ficheros y no lo es.
#
# Se busca por un TROZO del nombre y no por el nombre entero, para que un cambio
# de parentesis no rompa la resolucion. Los dos trozos son unicos en los dos
# masters medidos.
CLAVES_OBLIGATORIOS = (
    "integridad de las ventas",
    "elusion de controles por la direccion",
)

# El año del master, para avisar si no es el del ejercicio auditado. Se escriben
# con [0-9] y no con \d a proposito: estos patrones han viajado por heredocs y
# por ficheros de skill, y una barra invertida perdida por el camino convierte el
# patron en literal sin dar error.
ANIO_LARGO = r"(?:19|20)[0-9]{2}"
ANIO_CORTO = r"(?<![0-9])([0-9]{2})(?![0-9])"

# Si casi todo viene a cero, el expediente no tiene cifras cargadas y cualquier
# analisis seria inventado.
UMBRAL_VACIO = 0.90

# ── Codigos del master ──────────────────────────────────────────
#
# LA ESCALA VA AL REVES DE LO QUE PARECE: el 1 es lo PEOR.
#
# Estaba invertida hasta el 31/08/2026 -decia 1=Poco ... 4=Maximo, con una nota
# de "confirmado en cliente"- y eso etiquetaba mal los tres riesgos de cada
# ficha: los dos riesgos del catalogo con RI=1, que son los maximos, salian
# impresos como "Poco". Cualquier informe generado antes de esta fecha lleva las
# valoraciones invertidas.
#
# Lo zanja la ficha del riesgo 1 de un expediente real con la pantalla delante:
# la base guarda CodigoValorRIA_RI = 2 y Gesia muestra "Alto". Con la escala
# ascendente habria mostrado "Moderado". El desplegable enumera Maximo, Alto,
# Moderado, Poco -el orden de filas de ValoresRIA-, y esa tabla esta identica en
# cinco ficheros (dos expedientes reales, master CON RIESGOS, PYME y reducido).
#
# TRAMPA: en el MISMO fichero, ValoresGuias va justo al contrario -1=Bajo,
# 2=Moderado, 3=Alto, 4=Maximo-. Dos escalas de cuatro niveles con la misma
# forma y sentidos opuestos, asi que no se deduce una de la otra.
VALORACION = {1: "Máximo", 2: "Alto", 3: "Moderado", 4: "Poco"}

# Como se califica el riesgo en el master (campo Clasificacion). Confirmado
# en cliente: viene por relevancia, por incorreccion, o por las
# dos. En el catalogo actual: 77 de incorreccion, 17 de relevancia, 10 de
# ambas y 2 sin calificar.
CALIFICACION = {
    "R": "Relevancia",
    "I": "Incorrección",
    "A": "Relevancia e Incorrección",
}

# NIA 315: riesgos a nivel de afirmacion frente a riesgos a nivel de estados
# financieros. Comprobado en el catalogo: los 19 de tipo 2 estan todos en el area
# general, ninguno tiene aserciones y ninguno afecta a saldos ni transacciones.
TIPO_RIESGO = {1: "En las afirmaciones", 2: "General"}

# `Clasificacion` (I / R / A) NO esta confirmada. No se traduce ni se muestra en
# ningun entregable hasta que se sepa que significa.

# ── Entidades sin animo de lucro ──────────────────────────────────────────────
# Se detectan por el vocabulario de sus cuentas anuales, no por el CNAE (que en
# los expedientes suele venir vacio). Si se detecta, el informe habla de "cuenta
# de resultados" y no de "perdidas y ganancias".
TERMINOS_ESAL = (
    "ingresos de la actividad propia",
    "gastos de la actividad propia",
    "fondo social",
    "dotacion fundacional",
    "fondo dotacional",
    "excedente del ejercicio",
    "aportaciones de usuarios",
    "subvenciones imputadas al excedente",
)


class Resumen:
    """Duplica lo que va a consola para poder dejarlo tambien en un fichero.

    El JSON completo de los analisis es la fuente de auditoria, pero es enorme
    —el de la revision analitica son 127 elementos y miles de lineas— y leerlo
    entero para elegir riesgos se trunca y gasta contexto para nada. Lo que hace
    falta es justo el resumen que ya se imprime, asi que se guarda tal cual.

    Se envuelve stdout en vez de tocar los print: los mensajes se escriben una
    sola vez y no hay dos formatos que mantener sincronizados.
    """

    def __init__(self, real):
        self.real = real
        self.trozos: list = []

    def write(self, texto):
        self.real.write(texto)
        self.trozos.append(texto)

    def flush(self):
        self.real.flush()

    def guardar(self, ruta) -> None:
        from pathlib import Path as _P
        _P(ruta).write_text("".join(self.trozos), encoding="utf-8")


def con_resumen():
    """Envuelve sys.stdout y devuelve el Resumen, para guardarlo al final."""
    r = Resumen(sys.stdout)
    sys.stdout = r
    return r


def ruta_resumen(salida) -> str:
    """`analisis_ra.json` -> `analisis_ra_resumen.md`, junto al original."""
    from pathlib import Path as _P
    p = _P(salida)
    return str(p.with_name(p.stem + "_resumen.md"))


def salida_utf8() -> None:
    for flujo in ("stdout", "stderr"):
        f = getattr(sys, flujo)
        if hasattr(f, "reconfigure"):
            f.reconfigure(encoding="utf-8")


def sin_tildes(t: str) -> str:
    """Para comparar terminos: 'dotación' y 'dotacion' son el mismo termino."""
    return "".join(c for c in unicodedata.normalize("NFD", (t or "").lower())
                   if unicodedata.category(c) != "Mn")


def numero(v) -> float:
    """Los importes llegan del API como texto con coma decimal."""
    if v is None:
        return 0.0
    t = str(v).strip().replace(".", "").replace(",", ".") if "," in str(v) else str(v)
    try:
        return float(t)
    except ValueError:
        return 0.0


# ── Catalogo ──────────────────────────────────────────────────────────────────


def cargar_catalogo(ruta=None) -> dict:
    """Devuelve el catalogo con un indice por id, listo para consultar."""
    if ruta is None:
        raise RuntimeError(
            "hay que indicar la ruta del catalogo. Ya no viaja en el skill: se "
            "lee del master con exportar_consulta(entidad='catalogo_riesgos') y "
            "se normaliza con extraer_catalogo.py en el directorio de trabajo.")
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    datos["por_id"] = {r["id"]: r for r in datos["riesgos"]}
    return datos


class SinObligatorios(RuntimeError):
    """El catalogo no permite resolver los dos riesgos obligatorios.

    Se aborta a proposito en vez de seguir con lo que haya: un informe al que le
    falta la elusion de controles es peor que un informe que no se genera.
    """


def resolver_obligatorios(catalogo: dict) -> list:
    """Los dos riesgos obligatorios TAL COMO ESTAN EN ESTE catalogo.

    Devuelve los riesgos enteros, en el orden de CLAVES_OBLIGATORIOS, con el id
    que tienen en el master que se acaba de leer. Nunca un numero fijo: ver el
    comentario de CLAVES_OBLIGATORIOS.
    """
    riesgos = catalogo.get("riesgos") or []
    de_donde = catalogo.get("version") or catalogo.get("origen") or "sin identificar"
    hallados, problemas = [], []
    for clave in CLAVES_OBLIGATORIOS:
        casan = [r for r in riesgos if clave in sin_tildes(r.get("nombre", ""))]
        if len(casan) == 1:
            hallados.append(casan[0])
        elif not casan:
            problemas.append("ningún riesgo del catálogo se llama «" + clave + "»")
        else:
            problemas.append(
                str(len(casan)) + " riesgos se llaman «" + clave + "»: "
                + ", ".join(str(r["id"]) + " " + r["nombre"] for r in casan))
    if problemas:
        raise SinObligatorios(
            "No se pueden resolver los dos riesgos de inclusión obligatoria en el "
            "catálogo leído (" + de_donde + ", " + str(len(riesgos)) + " riesgos): "
            + " · ".join(problemas)
            + ". Comprueba que el máster indicado es el que lleva los riesgos: el "
              "fichero suele llamarse «CON RIESGOS» y trae alrededor de cien. No se "
              "sigue adelante, porque un informe sin estos dos riesgos no vale.")
    return hallados


def ids_obligatorios(catalogo: dict) -> tuple:
    """Solo los ids, para comparar contra la seleccion."""
    return tuple(r["id"] for r in resolver_obligatorios(catalogo))


def anio_master(catalogo: dict):
    """El ejercicio del master, deducido de su nombre. None si no se ve.

    Sirve para avisar de que se esta usando un catalogo de otro año, que es como
    se llego a leer el master de 2021 en un encargo de 2025.
    """
    texto = " ".join(str(catalogo.get(c, "")) for c in ("version", "origen"))
    m = re.search(ANIO_LARGO, texto)
    if m:
        return int(m.group(0))
    m = re.search(ANIO_CORTO, texto)
    return 2000 + int(m.group(1)) if m else None


def aviso_master(catalogo: dict, ejercicio=None):
    """Texto de aviso si el master no parece el del ejercicio auditado."""
    anio = anio_master(catalogo)
    try:
        ejercicio = int(str(ejercicio)[:4])
    except (TypeError, ValueError):
        ejercicio = None
    if not anio or not ejercicio or anio == ejercicio:
        return None
    return ("el catálogo es del máster de " + str(anio) + " y el ejercicio auditado "
            "es " + str(ejercicio) + ". Los riesgos, su numeración y sus "
            "procedimientos cambian de un máster a otro: comprueba que es el máster "
            "que quieres antes de firmar el papel.")


def riesgo_legible(r: dict, con_procedimientos: bool = False) -> dict:
    """Un riesgo con los codigos ya traducidos, para el informe."""
    val = r.get("valoracion_riesgo", {})
    salida = {
        "id": r["id"],
        "area": r["area"],
        "area_nombre": r.get("area_nombre", ""),
        "nombre": r["nombre"],
        "tipo": TIPO_RIESGO.get(r.get("tipo_riesgo"), ""),
        "significativo": r.get("significativo", False),
        "aserciones": [k for k, v in r.get("aserciones", {}).items() if v],
        "riesgo_inherente": VALORACION.get(val.get("inherente"), ""),
        "riesgo_control": VALORACION.get(val.get("control_interno"), ""),
        "riesgo_incorreccion": VALORACION.get(val.get("incorreccion_material"), ""),
        "calificacion": CALIFICACION.get(
            str(r.get("clasificacion", "")).strip().upper(), ""),
        "referencia": r.get("referencia", ""),
        "descripcion": r.get("descripcion", ""),
    }
    if con_procedimientos:
        salida["procedimientos"] = r.get("procedimientos", "")
    return salida


# ── Analisis de las cifras ────────────────────────────────────────────────────


def es_esal(conceptos) -> dict:
    """Decide si la entidad es sin animo de lucro por su vocabulario.

    Devuelve {'esal': bool, 'terminos': [...]}. Se informan los terminos
    encontrados para que la decision se pueda revisar: no es una etiqueta que el
    skill se saque de la manga.
    """
    texto = sin_tildes(" | ".join(c for c in conceptos if c))
    hallados = [t for t in TERMINOS_ESAL if sin_tildes(t) in texto]
    return {"esal": bool(hallados), "terminos": hallados}


def viene_convertido(fila: dict) -> bool:
    """Si el saldo ya trae aplicado el signo de Gesia.

    Se distingue por el nombre de la columna, y no es un detalle cosmetico: la
    entidad `cifras_pyg` del MCP devuelve `Saldo1..5` con el signo YA APLICADO,
    mientras que una consulta cruda a EstructuraPyG devuelve `SaldoAuditoria1..5`
    sin tocar. Aplicar la conversion dos veces deja los beneficios otra vez del
    reves, y el numero resultante es plausible: nadie lo notaria.
    """
    return _prefijo_saldo(fila)[1]


def _prefijo_saldo(fila: dict) -> tuple:
    """(prefijo de las columnas, si ya viene convertido).

    Tres nombres posibles, y el mas especifico se comprueba primero porque
    'SaldoAuditoria1' tambien empieza por 'Saldo':

      SaldoAuditoria1..5  la tabla a pelo          -> hay que convertir
      SaldoAud1..5        consulta oficial de balance -> ya convertido
      Saldo1..5           entidades del MCP        -> ya convertido
    """
    if "SaldoAuditoria1" in fila:
        return ("SaldoAuditoria", False)
    if "SaldoAud1" in fila:
        return ("SaldoAud", True)
    if "Saldo1" in fila:
        return ("Saldo", True)
    return ("SaldoAuditoria", False)


def serie(fila: dict) -> list:
    """Los cinco ejercicios de un epigrafe, del mas reciente al mas antiguo.

    Devuelve el saldo TAL COMO VIENE. Quien necesite el signo de presentacion
    usa convertir_signo(), y para saber si hace falta, viene_convertido().
    """
    prefijo = _prefijo_saldo(fila)[0]
    return [numero(fila.get(prefijo + str(i)))
            for i in range(1, EJERCICIOS + 1)]


# Por debajo de esto la base es despreciable y el porcentaje deja de informar.
# Medido: sin este corte, un epigrafe que pasa de 0,65 a -4.809.750 sale como
# "-739.777 %", que es correcto y no dice nada. Lo que hay que decir es que la
# base era despreciable.
BASE_MINIMA_RELATIVA = 0.01     # el anterior tiene que ser al menos el 1 % del actual
BASE_MINIMA_ABSOLUTA = 1.0      # y al menos un euro


def variacion(actual: float, anterior: float):
    """Variacion relativa, o None si la base no permite calcularla.

    Sin base no hay porcentaje: pasar de 0 a 50.000 no es "infinito por ciento",
    es una partida nueva. Y pasar de 0,65 a 4.800.000 tampoco: es una base
    despreciable. Las dos se informan con palabras, no con un numero absurdo.
    """
    if abs(anterior) < BASE_MINIMA_ABSOLUTA:
        return None
    if abs(actual) > 0 and abs(anterior) / abs(actual) < BASE_MINIMA_RELATIVA:
        return None
    return (actual - anterior) / abs(anterior)


def convertir_signo(saldo: float, clase: str) -> float:
    """El saldo tal como lo presenta Gesia. Son SUS reglas, no unas nuestras.

    Salen de las consultas con las que Gesia hace la revision analitica. Son dos
    reglas distintas, una por tabla, y por suerte las clases no se solapan entre
    las dos tablas, asi que se distinguen solas.

    BALANCE -- IIf(Clase='A', Saldo, -Saldo)

        'A' activo   -> tal cual
        'P' pasivo   -> invertido, porque viene acreedor y se lee en positivo

        OJO: esto NO es el valor absoluto. Un epigrafe de pasivo con saldo
        deudor -un patrimonio neto negativo, tipicamente- queda NEGATIVO despues
        de invertirlo, y tiene que quedarse asi: es la senal que el auditor busca.
        Con abs() desaparecia sin dejar rastro.

    PYG -- IIf(Saldo<0, -Saldo, IIf(Saldo>0 And (Clase="ST" Or Clase="T"), -Saldo, Saldo))

        'I'  epigrafe          -> en magnitud. Su naturaleza ya la dice el
                                  nombre: nadie necesita un signo para saber que
                                  «Gastos de personal» es un gasto.
        'ST' subtotal          -> invertido siempre
        'T'  total             -> invertido siempre, o sea beneficio en positivo
                                  y perdida en negativo. Ahi el signo es justo
                                  lo que se quiere leer.

    Importa seguir estas reglas y no otras parecidas: asi el papel de trabajo da
    los mismos numeros que el programa y el auditor puede cuadrarlos. Contrastado
    fila a fila contra las consultas originales.
    """
    if clase == "A":                    # balance, activo
        return saldo
    if clase == "P":                    # balance, pasivo
        return -saldo
    if clase in ("ST", "T"):            # PyG, subtotal o total
        return -saldo
    if clase == "I":                    # PyG, epigrafe: magnitud
        return -saldo if saldo < 0 else saldo
    # Clase desconocida: no se toca. Inventarse una conversion sobre algo que no
    # se reconoce es peor que dejar el dato como viene.
    return saldo


def comparar(actual: float, anterior: float, cambio_de_signo: bool = False) -> dict:
    """Variación entre dos saldos YA CONVERTIDOS, con la fórmula de Gesia:

        Round(((Actual - Anterior) / Abs(Anterior)) * 100, 4)

    Se divide por el valor absoluto del anterior, así que el signo del resultado
    dice el sentido: positivo mejora o crece, negativo lo contrario. Calcularlo
    sobre los saldos crudos daba el sentido invertido en los subtotales, que es
    como se llegó a informar de un beneficio multiplicado por cinco diciendo que
    la cifra bajaba.
    """
    if abs(anterior) < BASE_MINIMA_ABSOLUTA:
        return {"sentido": "aparece", "variacion_absoluta": None}
    var = (actual - anterior) / abs(anterior)
    if cambio_de_signo:
        # El porcentaje sigue siendo el de Gesia; lo que se cambia es el verbo,
        # porque «aumenta un 141 %» esconde que la partida cambió de lado.
        palabra = "cambia de signo"
    elif var > 0:
        palabra = "aumenta"
    elif var < 0:
        palabra = "disminuye"
    else:
        palabra = "no varía"
    return {"sentido": palabra, "variacion_absoluta": round(var, 4)}


# TipoValor de ElementosRA: 1 = importe en euros, 2 = ratio o porcentaje. Se ve
# en los datos sin lugar a duda: el Fondo de Maniobra y la Cifra de Negocios son
# tipo 1 y valen 1.377.768,68 y 12.413.681,80; el Endeudamiento Total es tipo 2 y
# vale 0,6091.
TIPO_IMPORTE = 1


def es_importe(fila: dict) -> bool:
    """Si el valor del ratio es un importe en euros y no una proporcion."""
    try:
        return int(numero(fila.get("TipoValor"))) == TIPO_IMPORTE
    except (TypeError, ValueError):
        return False


def inmaterial(fila: dict, valor: float, ir_t: float) -> bool:
    """Un importe por debajo de la importancia relativa no es una senal.

    Sale de un informe real: «Exigible a Largo 130,02 - a la baja 5 anos»
    figuraba como hallazgo. Son 130 euros de pasivo no corriente, y que bajen
    cinco anos seguidos no le dice nada a nadie; lo que hace es ocupar el sitio
    de algo que si importa. Un IR_T de 200.000 euros deja fuera ese y deja
    dentro el Fondo de Maniobra, que son 1,4 millones.

    Solo se aplica a los importes: comparar un ratio de 0,6091 con una cifra en
    euros no significa nada, asi que los de tipo 2 pasan siempre.
    """
    if ir_t <= 0 or not es_importe(fila):
        return False
    return abs(valor) < ir_t


def proporcion_ceros(filas: list) -> float:
    """Que parte de los importes viene a cero. Si casi todo, no hay datos."""
    total = vacios = 0
    for f in filas:
        for v in serie(f):
            total += 1
            if abs(v) < 0.005:
                vacios += 1
    return (vacios / total) if total else 1.0
