"""Modelo de datos, cruce y evaluacion de una prueba de cumplimiento de ForSampling.

No imprime nada: devuelve datos. Imprime el `main` de cada script, y acotado.

Tres entradas, las tres en disco:

  muestra.json      lo que devuelve exportar_consulta(entidad='muestra', id=N): los
                    elementos SELECCIONADOS de la prueba, con las columnas de SU
                    poblacion. Las columnas cambian con lo importado (un registro de
                    facturas, una copia del diario, una tabla de nominas), asi que
                    aqui no se asume ninguna: se detectan por su nombre.
  parametros.json   lo que devuelve obtener_entidad('parametros', id=N): la prueba, sus
                    parametros y los ATRIBUTOS que el auditor definio para ella.
  facturas.json     lo que el modelo escribe despues de leer los documentos escaneados,
                    una entrada por fichero: proveedor, numero, fecha, base, iva, total,
                    albaranes. El modelo es el OCR: es la unica parte del skill donde
                    lee documentos, y es la tarea.

Y una cuarta, opcional:

  evaluacion.json   exportar_consulta(entidad='evaluacion', id=N): la evaluacion que el
                    auditor ya hizo (A1..An, observacion). Solo para calibrar: comparar
                    lo que propone el skill con lo que decidio el auditor.

Lo que sale es una PROPUESTA por elemento y atributo -Ok, un hallazgo con cifras, o
'auditor' cuando el atributo no se puede juzgar desde el documento-, y la observacion
redactada con la formula que fijo el auditor el 02/09/2026:

    Asistente IA: A1: Ok · A2: Importe en factura (4.500,00) no corresponde con
    importe en libros (4.950,00) · A3: auditor · A4: auditor

Describir, no dictaminar: el skill dice que ha encontrado y que no; quien firma decide.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

# ── Umbrales, con su porque ────────────────────────────────────────────────────

# Un centimo. El total de la factura se lee tal cual del documento y el saldo viene
# de la contabilidad: si difieren en mas de un centimo, difieren de verdad (una
# retencion, un descuento, un concepto anadido a mano). Medido en la calibracion:
# 17 de 18 coinciden al centimo y la que no, difiere en 450,00.
TOL_IMPORTE = 0.01

# Dias entre la fecha del documento y la fecha en libros por encima de los cuales
# se informa. No es un hallazgo por si mismo -hay contabilidades que registran a
# fin de mes- pero el auditor tiene que verlo. 45 dias cubre el registro a mes
# vencido con margen; por encima ya no es un desfase administrativo normal.
VENTANA_DIAS = 45

# Diferencia admitida entre base + IVA y el total leido del documento. Un
# centimo de redondeo es normal en facturas con varias lineas; mas no.
TOL_IVA = 0.01

# Los tres papeles que puede hacer el skill con un atributo. El cuarto -'auditor'-
# es el que se pone cuando el control no se puede juzgar desde el documento
# (autorizacion, pedido, anticipo, oportunidad del registro).
ROL_DOCUMENTO = "documento"        # existe la factura y es la que dice el apunte
ROL_CALCULO = "calculo"            # base + IVA = total dentro del documento
ROL_CONTABILIZACION = "contabilizacion"  # importe y fecha del documento vs libros
ROL_AUDITOR = "auditor"            # no se infiere del documento
ROLES = (ROL_DOCUMENTO, ROL_CALCULO, ROL_CONTABILIZACION, ROL_AUDITOR)

# Como se propone el rol de cada atributo a partir de su nombre. Es una PROPUESTA
# que el auditor confirma o cambia en el paso 3 del SKILL.md: los nombres varian
# por firma ('12 DOCUMENTO' en un despacho, 'CI02_07 Albaranes' en otro) y el
# mismo nombre puede significar otra cosa en otra prueba. Nunca se aplica sin
# ensenarselo antes.
PALABRAS_ROL = (
    (ROL_DOCUMENTO, ("documento", "evidencia", "factura", "albar", "soporte", "justific")),
    (ROL_CALCULO, ("calculo", "cálculo", "aritm", "iva", "suma")),
    (ROL_CONTABILIZACION, ("contabiliz", "registro contable", "cuenta correcta", "fecha")),
    (ROL_AUDITOR, ("autoriz", "aprob", "pedido", "anticipo", "pago", "oportun", "registro")),
)


def salida_utf8() -> None:
    """Fuerza UTF-8 en stdout/stderr: la consola de Windows usa cp1252 y muta los acentos."""
    for flujo in (sys.stdout, sys.stderr):
        try:
            flujo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


# ── Lectura ───────────────────────────────────────────────────────────────────

def cargar_json(ruta: str | Path):
    p = Path(ruta)
    if not p.exists():
        raise FileNotFoundError(f"No existe: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def cargar_muestra(ruta: str | Path) -> list[dict]:
    """Las filas seleccionadas. Acepta la lista pelada de exportar_consulta o {'filas': [...]}."""
    datos = cargar_json(ruta)
    filas = datos["filas"] if isinstance(datos, dict) and "filas" in datos else datos
    if not isinstance(filas, list):
        raise ValueError("muestra.json no es una lista de filas ni un objeto con 'filas'.")
    return filas


def cargar_parametros(ruta: str | Path) -> dict:
    datos = cargar_json(ruta)
    if not isinstance(datos, dict):
        raise ValueError("parametros.json tiene que ser el objeto que devuelve obtener_entidad('parametros').")
    return datos


def cargar_evaluacion(ruta: str | Path | None) -> dict | None:
    """La evaluacion del auditor, si se paso. Acepta el objeto entero o solo sus 'filas'."""
    if not ruta:
        return None
    datos = cargar_json(ruta)
    if isinstance(datos, list):
        return {"filas": datos}
    return datos


def cargar_facturas(ruta: str | Path) -> list[dict]:
    datos = cargar_json(ruta)
    filas = datos["facturas"] if isinstance(datos, dict) and "facturas" in datos else datos
    if not isinstance(filas, list):
        raise ValueError("facturas.json no es una lista ni un objeto con 'facturas'.")
    return filas


# ── Columnas de la poblacion: se detectan, no se asumen ───────────────────────

# Cada rol y las palabras que lo delatan en el nombre de la columna, en orden de
# preferencia. Medido en tres poblaciones reales: la copia del diario de Gesia
# (FECHA, CUENTA, NOMBRE, CONCEPTO, SALDO), un registro de facturas 2024 (Fecha,
# Cuenta, NombreCuenta, Concepto, Saldo, Factura) y otro 2025 con los nombres que
# deja Access al importar sin tildes (NmerodeAsiento, CuentaContable,
# DescripcindelaOperacin, DescripcinApunte, Documento).
_ROLES_COLUMNA = {
    "id": (r"_id$",),
    "fecha": (r"^fecha$", r"fecha"),
    "importe": (r"^saldo$", r"^importe$", r"^debe$", r"^haber$"),
    "cuenta": (r"^cuentacontable$", r"^cuenta$", r"^cta\d?$"),
    # `nombrecontrap` es el nombre de la contrapartida del asiento: en una poblacion de gasto es
    # EL proveedor. Va PRIMERO, y tiene que estar aqui aunque ya este en el MCP: si las dos
    # listas no coinciden, el skill elige una columna y el MCP tokeniza otra, y al tachado le
    # llegan tokens que no son de ningun proveedor (18/09/2026, cuatro nombres sin tapar).
    "tercero": (r"^nombrecontrap", r"apunte$", r"^nombrecuenta$", r"^nombre$", r"^tercero$",
                r"^proveedor", r"^acreedor", r"^cliente", r"^descripci", r"^concepto$"),
    "documento": (r"^factura$", r"^documento$", r"^nfactura$", r"^numfactura$",
                  r"^concepto$", r"^descripcinconcepto$"),
    "asiento": (r"asiento", r"^numeroasiento$"),
}


def detectar_columnas(fila: dict) -> tuple[dict, list[str]]:
    """{rol: columna} y los roles que no se han podido asignar.

    Sin 'importe' o sin 'fecha' no hay cruce posible y el contrato aborta. Sin
    'documento' se cruza solo por importe y fecha, y el papel lo dice.
    """
    cols = list(fila.keys())
    bajas = {c: c.lower().replace(" ", "") for c in cols}
    asignadas: dict[str, str] = {}
    usadas: set[str] = set()
    for rol, patrones in _ROLES_COLUMNA.items():
        for patron in patrones:
            for c in cols:
                if c in usadas or c.lower() in ("seleccionado", "repeticiones", "numseleccion"):
                    continue
                if re.search(patron, bajas[c]):
                    asignadas[rol] = c
                    usadas.add(c)
                    break
            if rol in asignadas:
                break
    faltan = [r for r in ("id", "fecha", "importe", "tercero", "documento") if r not in asignadas]
    return asignadas, faltan


def _distintos(muestra: list[dict], col: str) -> int:
    return len({str(f.get(col) or "").strip().upper() for f in muestra if str(f.get(col) or "").strip()})


_RE_TOKEN_CUENTA = re.compile(r"^\s*(?:PROV|CLI|TER) \d{3,}\s*$")


def _tokens_de_cuenta(muestra: list[dict], col: str) -> int:
    """Cuantos valores de la columna son el token de una CUENTA, no uno de reserva.

    Es lo que distingue la columna que el MCP eligio para el tercero -la tokeniza con la cuenta
    de la contrapartida- de las demas columnas de nombres, que tokeniza siempre por reserva.
    """
    return sum(1 for f in muestra if _RE_TOKEN_CUENTA.match(str(f.get(col) or "")))


def afinar_columnas(muestra: list[dict], cols: dict) -> tuple[dict, list[str]]:
    """Reelige 'tercero' y 'documento' mirando TODAS las filas, no solo la primera.

    `detectar_columnas` decide por el nombre de la columna, y el nombre engaña:
    en una poblacion de ventas medida el 03/09/2026, 'Nombre' valia «Ventas» en
    las 42 filas -era el nombre de la cuenta- y el cliente estaba en 'Descripcin'.
    Con el tercero inservible, el unico elemento con diferencia real de importe se
    quedo sin documento, que es el peor sitio donde fallar: el importe es
    precisamente lo que la prueba pone en duda.

    La regla no mira el rotulo, mira el dato: **una columna que vale lo mismo en
    todas las filas no identifica a nadie**. Entre las candidatas se queda la de
    mas valores distintos, y si la elegida no distingue nada se avisa.
    """
    if not muestra:
        return cols, []
    avisos: list[str] = []
    cols = dict(cols)
    ocupadas = {v for k, v in cols.items() if k not in ("tercero", "documento")}
    bajas = {c: c.lower().replace(" ", "") for c in muestra[0]}
    for rol in ("tercero", "documento"):
        candidatas = [c for c in muestra[0]
                      if c not in ocupadas
                      and c.lower() not in ("seleccionado", "repeticiones", "numseleccion")
                      and any(re.search(p, bajas[c]) for p in _ROLES_COLUMNA[rol])]
        if not candidatas:
            continue
        # La de mas valores distintos, y a igualdad la que ya estaba elegida. Pero
        # solo se cambia si la elegida es MALA de verdad -constante, o con menos
        # de la mitad de valores distintos que la mejor-. Cambiar porque otra
        # tenga un valor distinto mas es ruido: en una MUM medida el 03/09/2026,
        # la columna correcta tenia 5 valores en 6 filas y la otra 6.
        elegida = cols.get(rol)
        # El MCP ya decidio cual es el tercero, y lo dice en el DATO: esa columna lleva el token
        # de la cuenta y las demas, tokens de reserva. Si hay una asi y la elegida no lo es, se
        # cambia sin mas: elegir otra manda al tachado tokens que no son de ningun proveedor y
        # el nombre acaba subiendo a la vista (18/09/2026).
        if rol == "tercero":
            con_cuenta = [c for c in candidatas if _tokens_de_cuenta(muestra, c)]
            if con_cuenta and not _tokens_de_cuenta(muestra, elegida or ""):
                mejor_t = max(con_cuenta, key=lambda c: _tokens_de_cuenta(muestra, c))
                if mejor_t != elegida:
                    avisos.append(f"la columna de tercero pasa de «{elegida}» a «{mejor_t}»: es la que el "
                                  f"MCP ha tokenizado por la cuenta de la contrapartida "
                                  f"({_tokens_de_cuenta(muestra, mejor_t)} de {len(muestra)} filas), "
                                  f"y «{elegida}» solo lleva tokens de reserva")
                    cols[rol] = mejor_t
                continue
        mejor = max(candidatas, key=lambda c: (_distintos(muestra, c), c == elegida))
        d_ele, d_mej = _distintos(muestra, elegida) if elegida else 0, _distintos(muestra, mejor)
        if elegida != mejor and (d_ele <= 1 or d_ele * 2 <= d_mej):
            avisos.append(f"la columna de {rol} pasa de «{elegida}» a «{mejor}»: «{elegida}» tiene "
                          f"{d_ele} valor(es) distinto(s) en {len(muestra)} filas y «{mejor}» tiene "
                          f"{d_mej}, así que identifica mucho mejor cada elemento")
            cols[rol] = mejor
        elif _distintos(muestra, cols.get(rol) or "") <= 1 and len(muestra) >= 5:
            # No se descarta la columna: aunque no discrimine -toda la muestra del
            # mismo tercero es posible- sigue siendo la unica pista, y una
            # asignacion que se sostenga sola con ella sale marcada como ambigua.
            # Con menos de cinco filas ni se menciona: un valor unico ahi es normal.
            avisos.append(f"la columna de {rol} («{cols.get(rol)}») vale lo mismo en las "
                          f"{len(muestra)} filas: no distingue entre elementos, y las asignaciones "
                          f"que dependan solo de ella saldrán marcadas")
        ocupadas.add(cols.get(rol) or "")
    return cols, avisos


def columnas_de_muestra(muestra: list[dict]) -> tuple[dict, list[str], list[str]]:
    """Las columnas de la poblacion, decididas con la muestra entera.

    Es lo que hay que usar: `detectar_columnas` sola se queda con el nombre de la
    columna y hay poblaciones donde el nombre miente.
    """
    cols, faltan = detectar_columnas(muestra[0])
    cols, avisos = afinar_columnas(muestra, cols)
    faltan = [r for r in ("id", "fecha", "importe", "tercero", "documento") if r not in cols]
    return cols, faltan, avisos


# ── Normalizacion ─────────────────────────────────────────────────────────────

def parse_importe(x) -> float | None:
    """'6.500,90 €', '6500,9', '1610.4', 4950.47 -> float. None si no hay numero."""
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = str(x).strip().replace("€", "").replace("EUR", "").replace(" ", "")
    if not s:
        return None
    neg = s.startswith("-") or (s.startswith("(") and s.endswith(")"))
    s = s.strip("()-+")
    # Formato espanol si hay coma decimal; si solo hay punto, decide por la posicion.
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3):
        s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    return -v if neg else v


_FORMATOS_FECHA = ("%d/%m/%y %H:%M:%S", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y", "%d/%m/%y",
                   "%d-%m-%Y", "%d-%m-%y", "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")


def parse_fecha(x) -> date | None:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    s = str(x).strip()
    if not s:
        return None
    for f in _FORMATOS_FECHA:
        try:
            return datetime.strptime(s, f).date()
        except ValueError:
            continue
    return None


_RE_NUM = re.compile(r"[0-9]+")
# Lo que precede al numero de factura en los conceptos vistos: 'S/FACTURA Nº 140',
# 'Fra N: CL250099', 'FRA 2500042', 'N. FRA N- 472', 'Factura 367'.
_RE_TRAS_FRA = re.compile(r"(?:fra|factura|fact|invoice|n[ºo°]?)[\s.:\-]*([A-Za-z]{0,3}[\s/\-]?[0-9][0-9A-Za-z/\-]*)", re.I)


def normalizar_numero(valor) -> tuple[str, str]:
    """('FA25/00042') -> ('FA2500042', '2500042'); ('000056') -> ('000056', '56').

    El primero es el alfanumerico sin separadores; el segundo, los digitos sin ceros
    a la izquierda: es el que casa 'A00/00000901' con '901' y 'FA25/00042' con
    '2500042'. Medido: los tres formatos aparecen en el mismo registro de facturas.
    """
    if valor is None:
        return "", ""
    s = str(valor).strip()
    alnum = re.sub(r"[^0-9A-Za-z]", "", s).upper()
    digitos = "".join(_RE_NUM.findall(s)).lstrip("0")
    return alnum, digitos


def numero_en_texto(texto) -> str:
    """El numero de factura que hay en un concepto libre, o '' si no se ve ninguno.

    Primero lo que sigue a 'Fra', 'Factura', 'Nº'...; si no, el ultimo grupo de
    cifras del texto (en 'S/FACTURA Nº             140' es el 140).
    """
    if texto is None:
        return ""
    s = str(texto)
    m = _RE_TRAS_FRA.search(s)
    if m:
        return m.group(1).strip()
    nums = _RE_NUM.findall(s)
    return nums[-1] if nums else ""


def _mismo_numero(a, b) -> str:
    """'exacto', 'sufijo' o ''.

    Exacto: el alfanumerico es igual, o lo son los digitos ('FA25/00042' frente a
    'FA FA25/00042': los dos dan 2500042). Sufijo: los digitos de uno terminan en
    los del otro y el corto tiene AL MENOS CUATRO cifras ('A00/00000901' frente a
    '901' no llega; '2500042' frente a '00133'... tampoco). Medido en la
    calibracion: con dos cifras bastaban, '159' casaba con '59' y le robaba la
    factura al elemento correcto. El numero es la clave DEBIL y se trata como tal.
    """
    aa, ad = normalizar_numero(a)
    ba, bd = normalizar_numero(b)
    if not ad or not bd:
        return ""
    if aa == ba or ad == bd:
        return "exacto"
    corto, largo = sorted((ad, bd), key=len)
    if len(corto) >= 4 and largo.endswith(corto):
        return "sufijo"
    return ""


_PALABRAS_VACIAS = {"sa", "sl", "slu", "lda", "ltda", "spa", "srl", "gmbh", "bv", "sas", "y", "e", "de",
                    "del", "la", "el", "los", "las", "and", "co", "cia", "hnos", "hermanos", "unipessoal"}


_RE_TOKEN_TERCERO = re.compile(r"^\s*(?:PROV|CLI|TER) (?:\d{3,}|h[0-9a-f]{6})\s*$")


def _tokens_tercero(nombre) -> set[str]:
    # Con el perfil del MCP el tercero de la muestra llega como token («PROV 40000012»,
    # «TER h3f9a2c»): no es un nombre y no tiene palabras que casar con el emisor del
    # documento. Vacio: el criterio de tercero queda apagado para esa fila, sin casar
    # nada por casualidad. docs/confidencialidad.md 4.9.
    if _RE_TOKEN_TERCERO.match(str(nombre or "")):
        return set()
    s = re.sub(r"[^a-z0-9 ]", " ", str(nombre or "").lower()
               .replace("á", "a").replace("é", "e").replace("í", "i").replace("ó", "o").replace("ú", "u"))
    return {t for t in s.split() if len(t) >= 3 and t not in _PALABRAS_VACIAS}


def _mismo_tercero_doc(valor_fila, fac: dict) -> bool:
    """El tercero de la fila frente al documento. Si la fila lleva un token (perfil del MCP) y
    el documento trae el sello transcrito en 'token' —el MCP lo estampa al tachar—, comparan
    los tokens, que es lo que devuelve el criterio de tercero al cruce (confidencialidad 4.9).
    Si no, los nombres, como siempre."""
    tok_fila = str(valor_fila or "").strip()
    tok_doc = str((fac or {}).get("token") or "").strip()
    if tok_doc and _RE_TOKEN_TERCERO.match(tok_fila):
        norm = lambda t: re.sub(r"\s+", " ", t).strip().lower()
        return norm(tok_fila) == norm(tok_doc)
    return _mismo_tercero(valor_fila, (fac or {}).get("proveedor"))


def _mismo_tercero(a, b) -> bool:
    """El tercero del apunte y el emisor del documento comparten al menos una palabra
    significativa ('ALFA, Lda.' / 'ALFA, LDA.'; 'PERNOSA' / 'PERFILES NAVARRA, S.L.
    (PERNOSA)'). Es la clave que usa el auditor, y la que faltaba: sin ella una
    factura cuyo importe no cuadra con libros -justo el caso que hay que ver- no se
    podia asignar a su apunte."""
    ta, tb = _tokens_tercero(a), _tokens_tercero(b)
    return bool(ta and tb and (ta & tb))


# ── Cruce muestra <-> documentos ───────────────────────────────────────────────

def _importe_fila(fila: dict, cols: dict) -> float | None:
    v = parse_importe(fila.get(cols["importe"]))
    if v is None and "importe" in cols and cols["importe"].lower() == "saldo":
        # Sin SALDO, se deriva de DEBE - HABER si estan.
        d = parse_importe(fila.get("Debe", fila.get("DEBE")))
        h = parse_importe(fila.get("Haber", fila.get("HABER")))
        if d is not None or h is not None:
            v = (d or 0.0) - (h or 0.0)
    return v


def base_de(fac: dict) -> float | None:
    """La base imponible del documento, derivandola si no viene rotulada.

    Hay facturas -suministros, sobre todo- que desglosan por conceptos y no rotulan ninguna linea
    como «base imponible»: el lector devuelve `base` vacia y el cruce se queda sin con que
    comparar (18/09/2026, un elemento de asiento partido que hubo que atar a mano). Si el
    documento trae total e IVA legibles, la base es la resta. No se inventa nada: si falta
    cualquiera de los dos, sigue vacia.
    """
    base = parse_importe(fac.get("base"))
    if base is not None:
        return base
    total, iva = parse_importe(fac.get("total")), parse_importe(fac.get("iva"))
    if total is None or iva is None:
        return None
    return round(total - iva, 2)


def _irpf(fac: dict) -> float | None:
    """La retencion practicada, si el documento la lleva. Vacio y cero son lo mismo."""
    v = parse_importe(fac.get("irpf"))
    return v if v else None


def _neto_factura(fac: dict) -> float | None:
    """Base + IVA - retencion: lo que se paga al proveedor, no lo que vale la factura.

    Solo existe cuando hay retencion. Se ofrece como tercera clave del cruce
    porque un apunte de tesoreria o un asiento por el neto dejaria el elemento
    sin localizar aunque el documento este en la carpeta.
    """
    ret = _irpf(fac)
    if ret is None:
        return None
    base, iva = parse_importe(fac.get("base")), parse_importe(fac.get("iva"))
    if base is None:
        return None
    return round(base + (iva or 0.0) - ret, 2)


def _cuadra_calculo(fac: dict) -> str:
    """Aritmetica del documento: base, IVA, retencion y total.

    Hay tres formas legitimas de que el total no sea base + IVA, y ninguna es
    hallazgo:

      - **exento o no sujeto** (intracomunitaria, art. 20 LIVA, clases a titulo
        particular): cuota de IVA cero, y base = total
      - **con retencion de IRPF** cuando el documento imprime el NETO a pagar
        (base + IVA - retencion) en vez del importe de la factura, que es lo
        habitual en facturas de profesionales y de arrendamiento
      - **redondeo**, hasta un centimo

    Confundir cualquiera de las tres con un error de calculo fabrica hallazgos
    en serie en pruebas de servicios profesionales, alquileres y nominas. La
    regla y sus porcentajes estan en docs/lectura-facturas.md.
    """
    base, iva, total = (parse_importe(fac.get("base")), parse_importe(fac.get("iva")),
                        parse_importe(fac.get("total")))
    ret = _irpf(fac)
    if base is None or total is None:
        return "Sin base o total legibles en la factura: no se puede comprobar el cálculo"
    pct = parse_importe(fac.get("pct_iva"))
    aviso = ""
    if pct is not None and iva is not None:
        esperado = round(base * pct / 100.0, 2)
        if abs(esperado - iva) > TOL_IVA:
            aviso = (f" · el IVA del documento ({_fmt(iva)}) no es el {pct:g} % de la base "
                     f"({_fmt(esperado)})")
    bruto = round(base + (iva or 0.0), 2)
    if ret is not None:
        if abs(total - bruto) <= TOL_IVA:
            return (f"Ok (con retención de IRPF de {_fmt(ret)}; el importe a pagar sería "
                    f"{_fmt(round(bruto - ret, 2))})" + aviso)
        if abs(total - round(bruto - ret, 2)) <= TOL_IVA:
            return (f"Ok (el total del documento es el neto tras la retención de {_fmt(ret)}; "
                    f"la factura es de {_fmt(bruto)})" + aviso)
        return (f"Cálculo no cuadra: base {_fmt(base)} + IVA {_fmt(iva or 0.0)} − retención "
                f"{_fmt(ret)} no dan el total {_fmt(total)}" + aviso)
    if iva is None:
        if abs(base - total) <= TOL_IVA:
            return "Ok (sin IVA: base = total)"
        return f"Sin IVA legible: base {_fmt(base)} y total {_fmt(total)} no coinciden"
    if abs(bruto - total) <= TOL_IVA:
        if abs(iva) <= TOL_IVA:
            return "Ok (exento o no sujeto: sin cuota de IVA)" + aviso
        return "Ok" + aviso
    return (f"Cálculo no cuadra: base {_fmt(base)} + IVA {_fmt(iva)} = {_fmt(bruto)} "
            f"≠ total {_fmt(total)}" + aviso)


def _numero_fila(fila: dict, cols: dict) -> str:
    if "documento" not in cols:
        return ""
    bruto = fila.get(cols["documento"])
    col = cols["documento"].lower()
    if col in ("concepto", "descripcinconcepto"):
        return numero_en_texto(bruto)
    return "" if bruto is None else str(bruto).strip()


def _puntuar(fila: dict, cols: dict, fac: dict) -> dict:
    """Que criterios casan entre una fila de la muestra y un documento leido."""
    imp = _importe_fila(fila, cols)
    total = parse_importe(fac.get("total"))
    base = base_de(fac)
    num_fila = _numero_fila(fila, cols)
    num_fac = fac.get("numero")
    f_fila = parse_fecha(fila.get(cols.get("fecha")))
    f_fac = parse_fecha(fac.get("fecha"))

    tipo_num = _mismo_numero(num_fila, num_fac) if (num_fila and num_fac) else ""
    numero = tipo_num == "exacto"
    tercero = _mismo_tercero_doc(fila.get(cols.get("tercero")), fac) if cols.get("tercero") else False
    importe = None
    por_asiento = None
    diferencia = None
    # `importe_aplicable`, si el auditor lo declara, es la parte del documento que sostiene
    # ESTE elemento: entra como candidato propio y NO pisa el total ni la base leidos, que se
    # siguen citando tal cual en los mensajes.
    candidatos = (("aplicable", parse_importe(fac.get("importe_aplicable"))),
                  ("total", total), ("base", base), ("neto", _neto_factura(fac)))
    if imp is not None:
        for etiqueta, valor in candidatos:
            if valor is not None and abs(abs(imp) - abs(valor)) <= TOL_IMPORTE:
                importe = etiqueta
                break
        # El elemento puede ser UNA LINEA de un asiento partido: entonces el documento no
        # sostiene la linea, sostiene el asiento. La suma la trae la muestra del MCP
        # (`ImporteAsiento`), sacada de la propia poblacion, no del diario.
        if importe is None:
            suma = parse_importe(fila.get("ImporteAsiento"))
            if suma is not None:
                for etiqueta, valor in candidatos:
                    if valor is not None and abs(abs(suma) - abs(valor)) <= TOL_IMPORTE:
                        por_asiento = etiqueta
                        break
        if importe is None and not por_asiento and total is not None:
            diferencia = round(abs(imp) - abs(total), 2)
    dias = None
    if f_fila and f_fac:
        dias = (f_fila - f_fac).days
    fecha = dias is not None and abs(dias) <= VENTANA_DIAS
    # El importe es la clave FUERTE (3); el tercero y el numero exacto, medias
    # (2); un numero que solo coincide por sufijo y la fecha, debiles (1).
    puntos = ((3 if (importe or por_asiento) else 0) + (2 if tercero else 0)
              + (2 if numero else 1 if tipo_num == "sufijo" else 0) + (1 if fecha else 0))
    # Y con puntos no basta: hace falta una clave que ate el documento al apunte.
    # O el importe, o el numero exacto, o el tercero con la fecha. Sin eso, una
    # fecha y un sufijo de dos cifras 'localizaban' facturas ajenas.
    ancla = bool(importe or por_asiento or numero or (tercero and fecha))
    return {"numero": numero, "tipo_numero": tipo_num, "tercero": tercero, "importe": importe,
            "por_asiento": por_asiento,
            "fecha": fecha, "dias": dias, "diferencia": diferencia, "ambiguo": False,
            "declarado": False,
            "puntos": puntos if ancla else 0, "num_fila": num_fila, "num_factura": num_fac}


def _atadas_a_mano(muestra: list[dict], facturas: list[dict], cols: dict) -> dict:
    """{indice de fila: factura} para los documentos que declaran su elemento.

    Un fichero de facturas.json puede llevar `poblacion_id` con el id del
    elemento al que pertenece, y entonces se le asigna sin pasar por la
    puntuacion. Existe porque el cruce automatico se apoya en el importe, y hay
    un caso en que el importe NO puede casar por definicion: cuando el elemento
    tiene una diferencia real, que es justo lo que la prueba busca. Ahi lo ata el
    auditor y el papel lo hace constar.
    """
    idc = cols.get("id")
    if not idc:
        return {}
    por_id = {str(f.get(idc)).strip(): i for i, f in enumerate(muestra) if f.get(idc) is not None}
    atadas: dict[int, dict] = {}
    for fac in facturas:
        decl = fac.get("poblacion_id") or fac.get("id_elemento")
        if decl is None or str(decl).strip() == "":
            continue
        i = por_id.get(str(decl).strip())
        if i is not None and i not in atadas:
            atadas[i] = fac
    return atadas


def cruzar(muestra: list[dict], facturas: list[dict], cols: dict) -> dict:
    """Asigna a cada fila de la muestra el documento que mejor casa, uno a uno.

    Puntua: importe -total o base- 3, tercero 2, numero exacto 2 (por sufijo de al
    menos cuatro cifras, 1) y fecha dentro de la ventana 1. Se asigna primero lo
    que mas puntua, ningun documento va a dos filas, y solo se asigna con al menos
    3 puntos Y una clave que ate el documento al apunte: importe, numero exacto, o
    tercero con fecha. Asi una factura cuyo importe NO cuadra con libros -el caso
    que hay que ver- se asigna igual por tercero y fecha, y el hallazgo sale en la
    contabilizacion en vez de perderse como 'no localizada'.

    Devuelve {'filas': [...], 'facturas_sin_fila': [...]}. Cada fila lleva la
    factura asignada (o None) y los criterios con que caso.
    """
    # Primero lo que el auditor haya atado a mano: manda sobre la puntuacion.
    atadas = _atadas_a_mano(muestra, facturas, cols)
    asig_fila: dict[int, tuple[int, dict]] = {}
    usadas: set[int] = set()
    for i, fac in atadas.items():
        j = facturas.index(fac)
        p = _puntuar(muestra[i], cols, fac)
        p["declarado"] = True
        asig_fila[i] = (j, p)
        usadas.add(j)

    candidatos = []
    for i, fila in enumerate(muestra):
        for j, fac in enumerate(facturas):
            p = _puntuar(fila, cols, fac)
            if p["puntos"] >= 3:
                candidatos.append((p["puntos"], i, j, p))
    # A igualdad de puntos, la fecha mas cercana. Es como lo resolveria cualquiera:
    # dos facturas del mismo proveedor dentro de la ventana empatan a puntos, y la
    # del mismo dia es la del apunte. Sin este desempate, el reparto iba por el
    # orden de la lista y marcaba como dudosa una pareja que no lo era.
    candidatos.sort(key=lambda c: (-c[0], abs(c[3]["dias"]) if c[3]["dias"] is not None else 10**6,
                                   c[1], c[2]))
    for puntos, i, j, p in candidatos:
        if i in asig_fila or j in usadas:
            continue
        # Una asignacion que no ata ni el importe ni el numero se sostiene sola
        # con tercero y fecha. Si habia mas de un candidato empatado -dos
        # facturas del mismo tercero y fecha, o dos elementos- el reparto voraz
        # elegiria una pareja cualquiera sin decirlo, y un documento mal asignado
        # da un importe equivocado. Se asigna, pero marcada.
        if not p["importe"] and not p["numero"]:
            # Rival de verdad es el que empata en puntos Y en cercania de fecha.
            # Si otro candidato puntua igual pero su fecha esta mas lejos, la
            # eleccion no es dudosa: hay un criterio que la sostiene.
            def _rival(q):
                dq = q[3]["dias"]
                dp = p["dias"]
                return q[0] == puntos and (abs(dq) if dq is not None else None) == (abs(dp) if dp is not None else None)

            rivales_fila = sum(1 for q in candidatos if q[1] == i and _rival(q))
            rivales_doc = sum(1 for q in candidatos if q[2] == j and _rival(q))
            if rivales_fila > 1 or rivales_doc > 1:
                p["ambiguo"] = True
        asig_fila[i] = (j, p)
        usadas.add(j)
    filas = []
    for i, fila in enumerate(muestra):
        if i in asig_fila:
            j, p = asig_fila[i]
            filas.append({"fila": fila, "factura": facturas[j], "criterios": p})
        else:
            filas.append({"fila": fila, "factura": None,
                          "criterios": {"numero": False, "tipo_numero": "", "tercero": False,
                                        "importe": None, "fecha": False, "dias": None,
                                        "diferencia": None, "puntos": 0, "ambiguo": False,
                                        "declarado": False,
                                        "num_fila": _numero_fila(fila, cols), "num_factura": None}})
    sin_fila = [f for j, f in enumerate(facturas) if j not in usadas]
    return {"filas": filas, "facturas_sin_fila": sin_fila,
            "candidatos_sueltos": _parejas_candidatas(filas, sin_fila, cols)}


def _parejas_candidatas(filas: list[dict], sin_fila: list[dict], cols: dict) -> list[dict]:
    """Parejas plausibles entre elementos sin documento y documentos sin elemento.

    Si los dos lados coinciden en tercero, o en fecha cercana, la pareja es
    candidata: **casi siempre significa que ese elemento tiene una diferencia
    real de importe**, no que el documento se haya extraviado. Sin esta pista, un
    caso asi se lee como «falta la factura» y el hallazgo se pierde; y con dos de
    cada lado, no habia forma de saber cual iba con cual.
    """
    if not sin_fila:
        return []
    huerfanas = [it for it in filas if it["factura"] is None]
    if not huerfanas:
        return []
    fuera = []
    for it in huerfanas:
        fila = it["fila"]
        f_fila = parse_fecha(fila.get(cols.get("fecha")))
        for fac in sin_fila:
            mismo = _mismo_tercero_doc(fila.get(cols.get("tercero")), fac) if cols.get("tercero") else False
            f_fac = parse_fecha(fac.get("fecha"))
            dias = (f_fila - f_fac).days if (f_fila and f_fac) else None
            cerca = dias is not None and abs(dias) <= VENTANA_DIAS
            if mismo or cerca:
                imp = _importe_fila(fila, cols)
                base, total = parse_importe(fac.get("base")), parse_importe(fac.get("total"))
                dif = None
                if imp is not None:
                    cands = [abs(abs(imp) - abs(v)) for v in (total, base) if v is not None]
                    dif = round(min(cands), 2) if cands else None
                fuera.append({"id": fila.get(cols.get("id")), "fichero": fac.get("fichero"),
                              "tercero": mismo, "dias": dias, "importe_libros": imp,
                              "base": base, "total": total, "diferencia_minima": dif})
    return fuera


# ── Atributos y evaluacion ────────────────────────────────────────────────────

def proponer_roles(atributos: list[dict]) -> dict[str, str]:
    """{AtributoId: rol} propuesto por el nombre. El auditor lo confirma antes de usarse."""
    roles: dict[str, str] = {}
    for a in atributos:
        texto = ((a.get("Nombre") or "") + " " + (a.get("Descripcion") or "")).lower()
        rol = ROL_AUDITOR
        for candidato, palabras in PALABRAS_ROL:
            if any(p in texto for p in palabras):
                rol = candidato
                break
        # 'registro' a secas es oportunidad del registro, cosa del auditor; pero
        # 'registro contable en fecha y cuenta' es contabilizacion. La segunda
        # pasada resuelve esa ambiguedad a favor del documento cuando lo nombra.
        if rol == ROL_AUDITOR and ("fecha" in texto or "cuenta correcta" in texto):
            rol = ROL_CONTABILIZACION
        roles[str(a.get("AtributoId"))] = rol
    return roles


def _fmt(v: float | None) -> str:
    if v is None:
        return "—"
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def evaluar_fila(item: dict, cols: dict, atributos: list[dict], roles: dict[str, str]) -> dict:
    """Un veredicto propuesto por atributo: 'Ok', un hallazgo con cifras, o 'auditor'."""
    fila, fac, c = item["fila"], item["factura"], item["criterios"]
    imp = _importe_fila(fila, cols)
    resultados: dict[str, str] = {}
    for a in atributos:
        aid = str(a.get("AtributoId"))
        rol = roles.get(aid, ROL_AUDITOR)
        if rol == ROL_AUDITOR:
            resultados[aid] = "auditor"
            continue
        if fac is None:
            resultados[aid] = ("No localizada la factura en la carpeta"
                               + (f" (nº en libros {c['num_fila']})" if c.get("num_fila") else ""))
            continue
        if rol == ROL_DOCUMENTO:
            # El documento existe y es el del apunte si lo ata el importe o el
            # numero exacto. Que el numero de libros no coincida NO es hallazgo:
            # en la calibracion la columna 'Documento' de la poblacion era un
            # numero interno de registro, no el de la factura, y eso fabricaba
            # 17 falsos hallazgos. Se informa, sin marcar.
            if c.get("declarado"):
                resultados[aid] = ("Ok (documento asignado a mano en facturas.json: "
                                   f"{fac.get('fichero')})")
                continue
            if c.get("ambiguo"):
                resultados[aid] = ("Localizada solo por tercero y fecha, y había más de un candidato con la "
                                   f"misma coincidencia: confirma el documento ({fac.get('fichero')})")
                continue
            if c["importe"] or c["numero"] or c.get("por_asiento"):
                via = ("número e importe" if (c["numero"] and c["importe"])
                       else "importe" if c["importe"]
                       else "número" if c["numero"] else "el importe del asiento completo")
                resultados[aid] = f"Ok (localizada por {via}: {fac.get('fichero')})"
            elif c.get("tercero") and c["fecha"]:
                resultados[aid] = (f"Localizada por tercero y fecha, pero el importe no coincide "
                                   f"(ver contabilización): {fac.get('fichero')}")
            else:
                resultados[aid] = f"Documento dudoso: solo coincide la fecha ({fac.get('fichero')})"
        elif rol == ROL_CALCULO:
            resultados[aid] = _cuadra_calculo(fac)
        elif rol == ROL_CONTABILIZACION:
            partes = []
            total = parse_importe(fac.get("total"))
            # Casar por la BASE no es hallazgo: en una cuenta de gasto o de
            # ingreso el apunte lleva la base y el IVA va a la 472/477. Medido en
            # la calibracion: los 18 elementos de compras casan por la base. La
            # hoja Muestra dice 'importe (base)' y con eso basta.
            # El elemento puede ser UNA LINEA de un asiento partido: entonces el documento
            # sostiene el asiento, no la linea, y decir que el importe no corresponde es un
            # hallazgo FALSO. Medido el 17/09/2026: 6 de cada 10 filas de aquella poblacion
            # viven en un asiento partido.
            if c["importe"] is None and not c.get("por_asiento") and fila.get("LineasAsiento"):
                partes.append(f"Asiento partido en {fila.get('LineasAsiento')} líneas "
                              f"(elementos {fila.get('IdsAsiento')}) que suman "
                              f"{_fmt(parse_importe(fila.get('ImporteAsiento')))}, y no casan con el "
                              f"documento: lo decide el auditor")
            elif c["importe"] is None and not c.get("por_asiento") and imp is not None and total is not None:
                partes.append(f"Importe en factura ({_fmt(abs(total))}) no corresponde con importe "
                              f"en libros ({_fmt(abs(imp))}): diferencia {_fmt(c['diferencia'])}")
            if c["dias"] is not None and abs(c["dias"]) > VENTANA_DIAS:
                partes.append(f"Fecha de factura {fac.get('fecha')}, en libros {fila.get(cols.get('fecha'))}"
                              f" ({c['dias']} días)")
            elif c["dias"] is None:
                partes.append("Sin fecha legible en la factura para contrastar")
            if partes:
                resultados[aid] = " · ".join(partes)
            elif c.get("por_asiento"):
                resultados[aid] = (f"Ok (el documento soporta el asiento entero, "
                                   f"{fila.get('LineasAsiento')} líneas: elementos {fila.get('IdsAsiento')})")
            elif c.get("importe") == "neto":
                resultados[aid] = ("Ok (el importe en libros casa con el neto a pagar, "
                                   "tras la retención de IRPF)")
            else:
                resultados[aid] = "Ok"
    return resultados


def observacion(resultados: dict[str, str], atributos: list[dict]) -> str:
    """'Asistente IA: A1: Ok · A2: ... · A3: auditor'. El orden es el de AtributoId."""
    orden = [str(a.get("AtributoId")) for a in atributos]
    return "Asistente IA: " + " · ".join(f"A{aid}: {resultados.get(aid, 'auditor')}" for aid in orden)


def evaluar(cruce: dict, cols: dict, atributos: list[dict], roles: dict[str, str]) -> list[dict]:
    out = []
    for item in cruce["filas"]:
        res = evaluar_fila(item, cols, atributos, roles)
        out.append({**item, "resultados": res, "observacion": observacion(res, atributos)})
    return out


# ── Comparacion con el auditor (calibracion) ──────────────────────────────────

def comparar_con_auditor(evaluados: list[dict], evaluacion: dict | None, cols: dict,
                         atributos: list[dict]) -> dict | None:
    """Por elemento y atributo, lo que puso el auditor (Si/No) frente a lo que propone
    el skill (Ok / hallazgo / auditor). Casa las filas por la columna _ID.

    Cuenta cuatro cosas, y la que importa es la ultima: donde el auditor dijo No y el
    skill dice Ok. Eso es un hallazgo que el skill se habria dejado pasar.
    """
    if not evaluacion or not evaluacion.get("filas"):
        return None
    idcol = cols.get("id")
    if not idcol:
        return None
    por_id = {str(f.get(idcol)): f for f in evaluacion["filas"] if f.get(idcol) is not None}
    filas = []
    n = {"coinciden": 0, "skill_senala_auditor_si": 0, "skill_ok_auditor_no": 0, "auditor": 0, "sin_pareja": 0}
    for e in evaluados:
        clave = str(e["fila"].get(idcol))
        ev = por_id.get(clave)
        if ev is None:
            n["sin_pareja"] += 1
            continue
        for a in atributos:
            aid = str(a.get("AtributoId"))
            auditor = str(ev.get(f"A{aid}", "")).strip()
            skill = e["resultados"].get(aid, "auditor")
            if skill == "auditor":
                n["auditor"] += 1
                estado = "auditor"
            elif skill.startswith("Ok") and auditor.lower().startswith("s"):
                n["coinciden"] += 1
                estado = "coincide"
            elif not skill.startswith("Ok") and auditor.lower().startswith("n"):
                n["coinciden"] += 1
                estado = "coincide"
            elif not skill.startswith("Ok"):
                n["skill_senala_auditor_si"] += 1
                estado = "skill señala, auditor Sí"
            else:
                n["skill_ok_auditor_no"] += 1
                estado = "skill Ok, auditor No"
            filas.append({"id": clave, "atributo": aid, "nombre": a.get("Nombre"),
                          "auditor": auditor, "skill": skill, "estado": estado})
    obs_col = next((k for k in (evaluacion["filas"][0].keys()) if k.upper().endswith("_OBSERV")), None)
    return {"filas": filas, "recuento": n, "columna_observacion": obs_col,
            "observaciones_auditor": {str(f.get(idcol)): f.get(obs_col) for f in evaluacion["filas"]} if obs_col else {}}


# ── El hipervinculo del papel al documento ───────────────────────────────────
#
# Vive aqui, y no en el generador de cada skill, porque los dos papeles enlazan igual.

_RE_RUTA_WINDOWS = re.compile(r"^[A-Za-z]:[\\/]|^\\\\")


def _absoluta(ruta: str) -> str:
    """Una ruta de Windows NO se toca desde el contenedor: Path.resolve() le ponia delante
    /home/claude/ y el vinculo del papel salia roto (registro del 16/09/2026)."""
    ruta = str(ruta)
    if _RE_RUTA_WINDOWS.match(ruta):
        return ruta
    return str(Path(ruta).resolve())


def _bajo(base: str, nombre: str) -> str:
    """base/nombre respetando el separador de la base: una carpeta de Windows lleva '\\'."""
    if _RE_RUTA_WINDOWS.match(base):
        return base.rstrip("\\/") + "\\" + nombre
    return _absoluta(str(Path(base) / nombre))


def rutas_documentos(manifiesto: str | None, carpeta: str | None) -> dict[str, str]:
    """{nombre de fichero: ruta ABSOLUTA} para los hipervinculos del papel.

    `carpeta` manda sobre el manifiesto, y es la salida para Cowork: la ruta que ve
    un script dentro del contenedor no existe en la maquina del auditor, asi que el
    vinculo se rehace sobre la carpeta de Windows que el usuario indique. Sin
    ninguna de las dos se devuelve vacio y las celdas quedan como texto: un vinculo
    roto en un papel de trabajo es peor que ninguno.
    """
    rutas: dict[str, str] = {}
    if manifiesto:
        pm = Path(manifiesto)
        if not pm.exists() and (pm.parent / "facturas" / "manifiesto.json").exists():
            pm = pm.parent / "facturas" / "manifiesto.json"   # la carpeta de preparar_facturas, subida entera
        if pm.exists():
            man = cargar_json(str(pm))
            for d in man.get("documentos") or []:
                nombre, ruta = d.get("fichero"), d.get("ruta")
                if nombre and ruta:
                    rutas[nombre] = _absoluta(ruta)
    if carpeta:
        base = Path(carpeta)
        nombres = set(rutas) or set()
        if not nombres and base.is_dir():
            nombres = {p.name for p in base.iterdir() if p.is_file()}
        rutas = {n: _bajo(str(carpeta), n) for n in nombres}
    return rutas
