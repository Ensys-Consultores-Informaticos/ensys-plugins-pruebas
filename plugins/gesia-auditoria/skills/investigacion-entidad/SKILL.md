---
name: investigacion-entidad-gesia
description: >
  Investiga en fuentes públicas de internet a la entidad auditada de un
  expediente de Gesia: información societaria (BORME), contratos públicos
  (PLACE), subvenciones (BDNS), jurisprudencia (CENDOJ), sanciones y prensa.
  Lanza tres agentes en paralelo y deja el papel en Word con cada hecho citado
  a su fuente y las fuentes consultadas con su fecha.
  Usa este skill cuando el usuario pida investigar al cliente, buscar
  información pública o externa de la entidad, una due diligence, el
  conocimiento de la entidad y su entorno por fuentes externas, o diga cosas
  como "investiga a este cliente", "qué se sabe de esta empresa", "busca al
  cliente en internet", "mira el BORME", "tiene contratos públicos o
  subvenciones", "busca noticias o sentencias del cliente".
  NO es la identificación de riesgos del expediente (eso usa las cifras de
  Gesia), ni el cuadro de mando del diario, ni la revisión de la memoria.
  Requiere acceso a internet. El nombre sale de Gesia; el CIF, si no está, se
  busca en internet y lo confirma el usuario.
---

# Investigación de la entidad auditada en fuentes públicas

Convierte el nombre del cliente —y su CIF, confirmado— en un informe de due diligence:
hechos societarios, vínculos con el sector público, riesgos legales y
reputacionales — **cada uno con su fuente, y los huecos declarados**.

Es el primer skill del plugin que usa **agentes**: tres investigadores en
paralelo (<!-- solo-cowork:alt=sus instrucciones están en `agentes/`, dentro de este skill -->`agents/` del plugin<!-- /solo-cowork -->), cada uno con su contrato JSON. El análisis y la
redacción NO se delegan: son tuyos, en el contexto principal, donde el usuario
puede corregirlos.

El informe va a `<expediente>\AsistenteIA\InvestigacionEntidad\` —solo el Word— y
**nunca se publica** en ninguna URL, ni como Artifact: forma parte del archivo de un
encargo.

---

## Reglas que gobiernan todo

**1. Hacia internet solo viajan la denominación y el CIF.** Ninguna cifra, saldo
ni dato interno del expediente entra jamás en una búsqueda web ni en el prompt de
un agente. Los agentes no tienen acceso al MCP de Gesia, y así debe seguir.

**2. Cero hechos sin fuente.** Todo lo que llega de los agentes trae fuente, URL
y fecha de consulta; lo que no la traiga no entra en el informe. Tú tampoco
añades hechos: tu papel en el análisis es cruzar los que hay.

**3. La ausencia de información es un resultado, no un fallo.** La parte
gratuita del Registro Mercantil es escasa y muchas pymes no dejan rastro en
PLACE ni en CENDOJ. Un informe lleno de ○ con las fuentes documentadas es un
papel de trabajo válido; un informe que rellena esos huecos por plausibilidad es
un papel falso.

**4. Describir, no dictaminar.** Los cruces del análisis se presentan como
elementos a contrastar, con su incertidumbre, nunca como conclusiones. Concluir
es del auditor, que es quien firma. Y sobre las personas (administradores,
apoderados): cargo y fechas publicados, ni una valoración.

**5. La evidencia es el propio papel.** Las fuentes web cambian y la búsqueda de
hoy no es reproducible mañana: lo que hace defendible el informe es que **cada hecho
lleva su fuente** y que **la sección 8 recoge cada fuente consultada con su URL y su
fecha de consulta**, junto con los avisos de los agentes sobre su búsqueda. Los JSON
de los agentes son la entrada de `generar_informe.py`, que construye desde ellos esa
sección: viven en el directorio de trabajo y se borran con él. **No se archivan**<!-- solo-cowork -->: en
Cowork los agentes no escriben ficheros y su JSON llega como mensaje, así que guardarlo
era retranscribirlo a mano, y una copia retranscrita no acredita más que el papel<!-- /solo-cowork -->.

---

## Dónde están los scripts

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(mktemp -d "${TMPDIR:-/tmp}/investigacion-XXXX")" && echo "$TRABAJO"
```

Un directorio de trabajo **nuevo en cada ejecución**, en la carpeta temporal del sistema y
**nunca en `AsistenteIA`**. Créalo al empezar: los JSON de los agentes van a él (paso 5).

**Anota la ruta que imprime**; si el entorno no conserva variables entre llamadas, vuelve a
escribir `SKILL="…"` y `TRABAJO="<esa ruta>"` al principio de cada orden, sin crear otro
directorio. No la guardes en un fichero para leerla luego con `$(cat …)`: al final se borra
con la ruta escrita tal cual (paso 8). **No hagas `cd` a él**; trabaja con rutas completas:
al final se borra desde fuera, y el entorno no deja borrar el directorio en el que estás.

---

## Secuencia

### Paso 1 — El nombre, del expediente

Con expediente de Gesia (el caso normal):

```
configurar(perfil = "investigacion-entidad")
contexto_expediente()
```

**El perfil va lo primero**: marca el comienzo del procedimiento, y desde ahí el MCP lleva
la cuenta de lo que se facilita a la herramienta, que es lo que el informe dirá en su apartado
de uso de IA. Este perfil no seudonimiza nada: la búsqueda necesita el nombre de la entidad
tal cual, y lo que se lee del expediente —razón social y cierre— no lleva terceros.

**`contexto_expediente()` va siempre, después del perfil, aunque ya lo tengas en la
conversación.** Lo que se leyó antes con otro perfil cuenta para aquel procedimiento, no para
este: si no lo vuelves a pedir, el apartado de uso de IA no lo lista como facilitado y el
informe dice menos de lo que se usó.

**Si `configurar` —o cualquier otra llamada del MCP— avisa de que otra conversación está
trabajando con otro expediente o con otro perfil en el mismo servidor**, díselo al auditor tal
cual y **no sigas hasta que confirme**. Las conversaciones abiertas a la vez comparten el MCP:
cada `configurar` cambia el expediente y el perfil de todas, y lo que una lee o sella puede
acabar en el papel de la otra sin que nada lo avise.

De ahí salen la razón social (`RazonSocialCliente`) y la fecha de cierre. **No le
pidas el nombre al usuario si el expediente lo trae.** Solo si no hay expediente, o
la razón social viene vacía, pregúntale cómo se llama la entidad.

### Paso 2 — El CIF: se busca en internet por el nombre y lo confirma el usuario

**El CIF no está en Gesia: no lo busques en el expediente.** `DatosAuditoria` tiene una
columna `NIF`, pero Gesia la usa desde hace varias versiones para el **sector** del cliente
—en pantalla se llama así; por dentro conserva el nombre—, así que lo que trae no es un CIF.
Lo que sale del expediente es solo el nombre (paso 1).

**Búscalo en internet, solo con el nombre.** Es la regla 1:
hacia fuera viaja la denominación y nada más. Busca la razón social en BORME y en
las fichas públicas de empresa (Infocif, Empresite, eInforma, LibreBORME), y apunta
cada **candidata**: denominación tal como aparece, CIF, provincia o domicilio, y la
fuente con su enlace. Hay homónimos y nombres parecidos —«X, S.A.» y «X Ibérica,
S.L.»—, y quedarte con el primero que salga es investigar a otra empresa.

**Valida cada CIF candidato antes de enseñarlo:**

```bash
python "$SKILL/scripts/validar_cif.py" --cif "<CIF>"
```

Salida `2` → ese CIF no vale (control erróneo): descártalo y dilo. Si
`es_persona_juridica` es `false` (DNI/NIE), también se descarta: la investigación
mercantil no aplica a personas físicas.

Con un CIF válido, el script devuelve además la **`forma`** de la entidad y el
**`registro`** que le corresponde, por la letra inicial (G, fundación o asociación;
F, cooperativa; A y B, sociedades…), y **`borme_aplica`**. Úsalos en la tabla de
candidatas y guárdalos: van a los agentes (paso 4) y al informe (paso 7). Si la
entidad no es mercantil, no la busques en el BORME como si lo fuera.

**Y pide confirmación SIEMPRE, aunque haya una sola candidata.** Enséñale al usuario
la tabla de candidatas válidas —denominación, CIF, provincia, fuente— y pregúntale
cuál es su cliente. Es la pregunta central de la investigación, y no se salta: un CIF
mal elegido produce un informe entero sobre otra entidad, que es el peor resultado
posible.

- **Confirma una** → esa es la entidad. Origen: «<fuente>, confirmado por el usuario».
- **No es ninguna, o no aparece ninguna** → pídele el CIF. Si lo da, se valida igual
  y el origen es «indicado por el usuario».
- **No lo tiene** → **para.** Sin una entidad identificada no se investiga: dilo así
  y no lances los agentes.

Guarda el origen del CIF: va al informe (paso 7).

### Paso 3 — Avisar de lo que va a pasar

Antes de lanzar nada, dile al usuario: que vas a lanzar **tres investigadores en
paralelo** sobre fuentes públicas de internet (BORME, PLACE, BDNS, CENDOJ, BOE,
prensa), que hacia fuera solo viajan denominación y CIF, que la ventana de
búsqueda es la que le digas, y que puede tardar varios minutos.

**La ventana temporal por defecto son los 5 años anteriores al cierre auditado,
hasta hoy.** Es la misma profundidad plurianual que maneja el expediente. Si el
usuario quiere otra, se usa la suya y el informe la declara.

Antes de lanzar nada, busca también **la referencia del papel** en `Referencias` (paso 7)
y, si no sale una y solo una, pregúntala ahora, enseñando las candidatas: así no se le
interrumpe otra vez al final.

### Paso 4 — Lanzar los tres agentes en paralelo

<!-- solo-cowork:agentes -->
Los tres subagentes del plugin, **en una sola tanda** (una llamada por agente,
las tres en el mismo mensaje para que corran a la vez):

| Subagente | Cubre |
|---|---|
| `investigador-societario` | BORME, Registro Mercantil, actividad, CNAE |
| `investigador-sector-publico` | PLACE, BDNS |
| `investigador-riesgos-legales` | CENDOJ, sanciones BOE, prensa |

(Instalados desde el plugin aparecen con su prefijo, p. ej.
`gesia-auditoria:investigador-societario`.)
<!-- /solo-cowork -->

El prompt de cada uno lleva exactamente esto, y nada más del expediente:

```
Denominación confirmada: <razón social>
CIF: <CIF>
Forma jurídica: <forma> — registro: <registro>
Cierre del ejercicio auditado: <fecha>
Ventana temporal: desde <cierre − 5 años> hasta <hoy>
Fecha de consulta a registrar: <hoy>
```

<!-- solo-cowork:agentes-salida -->
Cada agente devuelve **solo un JSON** (su contrato está en su propio fichero de
`agents/`), que empieza por su `recuento`: cuántas fuentes consultadas y cuántos
hechos lleva. Si uno devuelve otra cosa o falla, **un reintento y se sigue**: su
sección del informe queda en ○ con la limitación explícita. No se bloquea la
investigación entera por una pata.
<!-- /solo-cowork -->

### Paso 5 — Los JSON, en el directorio de trabajo, y comprobados

<!-- solo-cowork:agentes-copia -->
Copia el JSON de cada agente, **entero y tal cual llegó en su mensaje**, sin retocar ni
resumir, a `$TRABAJO/societario.json`, `$TRABAJO/sector-publico.json` y
`$TRABAJO/riesgos-legales.json` —con la herramienta de escribir ficheros si el entorno la
tiene, o con un heredoc entre comillas simples, que no toca el texto:
`cat > "$TRABAJO/societario.json" <<'FIN_JSON'` … `FIN_JSON`—. Son la entrada del
informe, **no se archivan** (regla 5): no van a `AsistenteIA`.
<!-- /solo-cowork -->

Y **comprueba los JSON antes de seguir**, que es barato y caza lo que se pierde por el
camino:

```bash
python "$SKILL/scripts/generar_informe.py" --comprobar \
    --evidencia-societario "$TRABAJO/societario.json" \
    --evidencia-sector-publico "$TRABAJO/sector-publico.json" \
    --evidencia-riesgos "$TRABAJO/riesgos-legales.json"
```

Carga cada JSON y cuenta sus fuentes y sus hechos contra el `recuento` que declaró el
agente. Salida `2` → un JSON no carga o no cuadra: <!-- solo-cowork:alt=**vuelve a lanzar ese subagente**, con las mismas instrucciones, -->**vuelve a copiar ese JSON del mensaje
del agente**, entero,<!-- /solo-cowork --> y repite la comprobación. Si un agente no declaró recuento, lo dice y
no para: compáralo tú con su mensaje, y el informe hará constar que esa respuesta no se
pudo cotejar. Si un agente se degradó, omite su `--evidencia-*`.

### Paso 6 — El análisis (este es tuyo)

Con los tres JSON delante, cruza. No generas hechos nuevos: añades relación
entre los que hay.

1. **Actividad declarada vs contratos públicos**: ¿el objeto social y lo
   adjudicado son coherentes?
2. **Cambios societarios vs procedimientos y sanciones**: ¿coincidencias
   temporales (cambio de administrador y litigio en fechas próximas)?
3. **Dependencia del sector público**: si los importes de contratos y
   subvenciones son relevantes, dilo con la cifra — sin cruzarla con las del
   expediente dentro del informe, que es de fuentes públicas.
4. **Huecos**: cuáles de los `huecos_informacion` importan para el encargo
   (p. ej. sin depósito de cuentas constatable).

Cada elemento del análisis cita los hechos concretos en que se basa y lleva
incertidumbre: `baja` = respaldado por dos o más fuentes; `alta` = hipótesis a
partir de una coincidencia. **La ausencia de información nunca genera un
indicio**: va a huecos. Y recuerda la regla 4: elementos a contrastar, no
conclusiones.

### Paso 7 — El informe, en Word (puede abortar)

El entregable es un `.docx` con la **cabecera común de los papeles del
expediente** (cliente, «AUDITORIA A <cierre>», título, fuente, bloque
`REF. P.T.` / `Realizado` / `Verificado`), como continuidad de saldos e
identificación de riesgos. La genera `generar_informe.py`; tú escribes el
contenido en un JSON y el script maqueta.

**La referencia del papel (`--ref`) sale de la tabla `Referencias` de ESTE expediente,
y de ningún otro sitio.** Ni de memoria, ni de un ejemplo, ni de otro expediente: no se
elige ni se **propone** un código que no hayas visto en una fila de estas consultas.
`CodigoReferencia` no es estable entre encargos —el mismo código apunta a papeles
distintos en expedientes distintos—: el 21/10/2026, en un expediente real, un código
propuesto de memoria era allí el de la normativa aplicable, el usuario lo aceptó y el papel
quedó archivado bajo la referencia de otro.

1. **Búscala por el texto** del papel, que es el conocimiento de la entidad y su entorno:

   ```sql
   SELECT CodigoReferencia, Referencia FROM Referencias
   WHERE Referencia LIKE '%conocimiento%entidad%' OR Referencia LIKE '%entidad y su entorno%'
   ```

   **Una fila** → úsala, y dile al usuario cuál has cogido, con su código y su nombre.
   **Ninguna, o más de una** → no elijas: punto 2.

2. **Una segunda búsqueda más amplia, y se pregunta:**

   ```sql
   SELECT TOP 30 CodigoReferencia, Referencia FROM Referencias
   WHERE Referencia LIKE '%conocimiento%' OR Referencia LIKE '%entorno%'
      OR Referencia LIKE '%planificaci%n%'
   ORDER BY CodigoReferencia
   ```

   En JET el comodín es `%`; con `*` sale vacía sin dar error. **Enséñale las candidatas,
   cada una con su código y su nombre tal como vienen, y pregúntale cuál es.** Aunque salga
   una sola, se pregunta; si no sale ninguna, díselo así y pregúntale igual.

3. **Si el usuario da un código, compruébalo antes de usarlo** —también si lo dice de
   entrada—:

   ```sql
   SELECT CodigoReferencia, Referencia FROM Referencias
   WHERE CodigoReferencia = '<el código que ha dado>'
   ```

   Enséñale el nombre que tiene en este expediente y espera a que lo confirme. Sin fila,
   ese código no existe aquí: díselo y no lo uses.

Si no tiene referencia para este papel, se pasa vacía (`--ref ""`) y la celda queda en
blanco: mejor un hueco que el código de otro papel. Para no interrumpir dos veces, haz
esta búsqueda **antes de lanzar los agentes** (paso 3) y, si hay que preguntar, pregúntalo
entonces.

Escribe `$TRABAJO/informe.json`:

```json
{
  "identificacion": [{"campo": "Forma jurídica", "valor": "..."}],
  "secciones": {
    "societaria":     [{"texto": "...", "marca": "✓", "fuente": "BORME-A-..."}],
    "actividad":      [...],
    "sector_publico": [...],
    "riesgos_legales":[...],
    "analisis":       [{"texto": "...", "marca": "⚠", "incertidumbre": "media",
                        "fuente": "hechos que cruza"}]
  },
  "limitaciones_catalogo": ["borme_sin_historico", "place_sin_api"],
  "limitaciones_especificas": ["..."]
}
```

Las marcas, afirmación a afirmación: **✓** hecho verificado (exige `fuente`),
**⚠** indicio del análisis del paso 6 (con su incertidumbre), **○** sin
información (consta que se buscó). Los datos de fiabilidad `media`
(agregadores) se dicen como tales en el propio texto.

**Las limitaciones estructurales de las fuentes gratuitas no se redactan: se
marcan.** El catálogo vive en `generar_informe.py` con texto fijo
(`borme_sin_historico`, `registro_mercantil_pago`, `aeat_censal`,
`place_sin_api`, `cendoj_no_fetchable`, `boletines_no_fetchable`,
`prensa_no_indexada`, `cnae_no_oficial`): elige por id las que los `avisos` de
los agentes confirmen. En `limitaciones_especificas` va solo lo propio de esta
entidad. Un id fuera del catálogo aborta.

**La sección 8 (fuentes consultadas) no la escribes tú**: el script la
construye desde los `fuentes_consultadas` de los JSON de los agentes, con las
que aportaron datos primero, y añade debajo sus `avisos` tal cual. Así el informe
no puede citar una fuente que los agentes no registraran. Una búsqueda web general,
que no es una página, sale sin URL.

**Si el informe ya existe, pregunta antes de generarlo.** Mira si en
`<expediente>\AsistenteIA\InvestigacionEntidad\` ya hay un fichero con ese nombre<!-- solo-cowork:alt=. --> —en
Cowork, listando la carpeta conectada con `device_list_dir`; en local, en el disco—.<!-- /solo-cowork -->
Si lo hay, **pregunta al auditor** si lo sobrescribe o si guarda el nuevo con « (rehecho
AAAA-MM-DD)» antes de la extensión, con la fecha de hoy. Ni lo sobrescribas sin preguntar ni
inventes otro sufijo: al repetir un procedimiento el mismo día, una ejecución pisó el papel y otra
improvisó el nombre (registro del 21/10/2026). El nombre elegido es el de todo lo que sigue
—<!-- solo-cowork -->la bajada al expediente y <!-- /solo-cowork -->el sello—.<!-- solo-cowork --> En
Cowork, `device_commit_files` va **sin `force`**; solo si el auditor eligió sobrescribir y el
commit lo rechaza porque el fichero existe, repítelo con `force` y díselo.<!-- /solo-cowork -->

```bash
python "$SKILL/scripts/generar_informe.py" \
    --contenido "$TRABAJO/informe.json" \
    --evidencia-societario "$TRABAJO/societario.json" \
    --evidencia-sector-publico "$TRABAJO/sector-publico.json" \
    --evidencia-riesgos "$TRABAJO/riesgos-legales.json" \
    --cliente "<razón social>" --cif "<CIF>" --cif-origen "<origen del paso 2>" \
    --registro "<registro del paso 2>" \
    --cierre "<dd/mm/aa>" \
    --ventana "<desde> - <hasta>" --generado "<AAAA-MM-DD>" --ref "<ref o vacía>" \
    --salida "<expediente>/AsistenteIA/InvestigacionEntidad/Investigacion <CLIENTE> <AAAA>.docx"
```

(AAAA = ejercicio auditado.) Si un agente se degradó, omite su `--evidencia-*`:
el script lo hace constar en la tabla de fuentes. Salida `2` → defectos en el
contenido (marca inválida, hecho ✓ sin fuente, id de limitación inexistente) o en
una copia de los agentes (la misma comprobación del paso 5): **se corrige el JSON,
nunca el script**, y se relanza.

**Y termina con el apartado «Utilización de herramientas de inteligencia artificial»**,
con una marca en la cabecera, junto a Realizado y Verificado: la evidencia de que el informe
se hizo con una herramienta de IA, de qué se le facilitó y de cómo debe verificarse. Dice que
el informe lo ha compuesto la herramienta a partir de lo que devolvieron los agentes, con cada
hecho citado a su fuente, y que la denominación y el CIF salieron a búsquedas en fuentes
públicas de internet por los agentes (eso el MCP no lo ve, así que lo declara el script). Las
comprobaciones que lista —el CIF y su registro, hechos con fuente, incertidumbre de los
indicios, fuentes desde las respuestas de los agentes, el cotejo de cada copia con su
recuento, agentes sin evidencia, avisos— las calcula el script
sobre el propio informe. Los apartados de la herramienta quedan con huecos que se rellenan al
archivar (paso 8); los de verificación, verificado por, efecto en la conclusión y revisión
**son del equipo y salen en blanco**. No escribas nada en ellos ni propongas texto para ellos.

<!-- solo-cowork:entrega -->
**En Cowork el script escribe en el sandbox, no en el expediente**, así que la ruta de destino
no se cumple sola: hay que bajar el Word. Se envía con `SendUserFile`, que devuelve un
`file_uuid`, y con `device_commit_files` se escribe en el disco del auditor:

```
device_commit_files → "<expediente>/AsistenteIA/InvestigacionEntidad/<informe>.docx"
```

**Solo el Word, por su nombre exacto, nunca con un comodín**: en el directorio de trabajo
están también `informe.json` y los tres JSON de los agentes, que no van al expediente.
<!-- /solo-cowork -->

### Paso 8 — Entregar

**Con el informe ya en el disco del auditor**, en
`<expediente>\AsistenteIA\InvestigacionEntidad\`, séllalo:

```
sellar_uso_ia(ruta = "<expediente>/AsistenteIA/InvestigacionEntidad/<fichero>.docx",
              modelo = "<el modelo con el que trabajas>",
              procedimiento = "investigacion-entidad")
```

Rellena en el apartado de uso de IA lo que solo sabe la aplicación: herramienta y versiones,
quién lo ejecutó, dónde corrieron los scripts y **qué información se facilitó y cómo**, según
lo que el MCP ha servido desde el paso 1. `procedimiento` es el mismo perfil del paso 1, y es
lo que le dice al MCP de qué procedimiento tiene que listar lo facilitado. En `modelo` pon el
nombre y la versión que te da tu propio contexto; si no lo sabes, déjalo vacío. **Sin esta
llamada el informe queda con huecos que dicen «pendiente»**: no se da por entregado.

**Si en algún momento el MCP avisó de otra conversación con otro expediente o perfil en el
mismo servidor** (paso 1) y el auditor decidió seguir, recuérdaselo al entregar: es lo primero
que tiene que mirar si el apartado de uso de IA lista algo que este procedimiento no usó.

Di dónde ha quedado el informe, resume en tres líneas lo más
relevante de cada bloque, y recuerda que el informe recopila y cruza información
pública: la evaluación del efecto en el encargo es del auditor. Recuérdale también
que el apartado de uso de IA deja la verificación, quién la hace, su efecto en la
conclusión y la revisión en blanco para el equipo: mientras lo estén, el informe no
es evidencia de auditoría. Si algún agente se degradó (paso 4), dilo aquí también,
no solo dentro del informe.

**Los temporales.** Borra el directorio de trabajo —con los tres JSON de los agentes y
`informe.json`— **desde fuera**, sin haber hecho `cd` a él (si lo hiciste, sal antes), y
**con la ruta literal que anotaste al crearlo**, al empezar, escrita entera:

```bash
rm -rf "<la ruta que anotaste>"
```

<!-- solo-cowork -->Ni `"$TRABAJO"` —en un entorno que no conserva variables llega vacía— ni
`"$(cat <fichero>)"`: un borrado recursivo cuya ruta se calcula en el momento no se puede
revisar antes de lanzarlo, y en Cowork la seguridad lo bloquea (registro del 21/10/2026).<!-- /solo-cowork -->

Si el entorno no deja borrar, di la ruta exacta de lo que queda. En
`AsistenteIA\InvestigacionEntidad\` solo debe quedar el Word. Este procedimiento no exporta
nada con `exportar_consulta`, así que no hay volcados del MCP que limpiar.

---

## Lo que este skill no hace

- **No consulta fuentes de pago ni con certificado**: ni el Registro Mercantil
  de pago, ni el censo de la AEAT, ni informes comerciales (eInforma, Axesor de
  pago). Sus fichas públicas gratuitas sí, marcadas como fiabilidad media.
- **No resuelve CAPTCHAs ni crea cuentas** en ningún servicio.
- **No mezcla las cifras del expediente con el informe.** La comparación entre
  lo público y lo contabilizado (p. ej. subvenciones BDNS vs ingresos) es un
  procedimiento de auditoría posterior, del auditor.
- **No identifica riesgos NIA 315**: eso es `identificacion-riesgos`, con las
  cifras del expediente. Este skill le da contexto externo, no lo sustituye.
- **No escribe en el expediente de Gesia.**
- **No verifica su propio resultado por el equipo.** Propone qué contrastar; la verificación,
  quién la hace y su efecto en la conclusión los escribe el equipo en el apartado de uso de IA.

## Degradación

| Situación | Qué sale |
|---|---|
| Servidor API de Gesia caído o sin expediente | se pregunta el nombre al usuario y se sigue igual |
| El MCP avisa de otra conversación con otro expediente o perfil en el mismo servidor | se le dice al auditor tal cual y **no se sigue hasta que confirme** |
| El expediente no trae el CIF (siempre: la columna `NIF` es el sector) | se busca el CIF en internet por el nombre y el usuario confirma la candidata |
| Varias candidatas con nombres parecidos | se enseñan todas y elige el usuario |
| Ninguna candidata, o el usuario no reconoce ninguna | se le pide el CIF; si no lo tiene, **para** |
| CIF con control inválido | se descarta esa candidata; si era el indicado por el usuario, **para** |
| DNI/NIE en vez de CIF | **para.** Fuera del alcance |
| Un agente falla o devuelve JSON inválido | un reintento; después, sección en ○ con limitación explícita |
| Un JSON no carga o no cuadra con su `recuento` (`--comprobar`, salida 2) | <!-- solo-cowork:alt=se vuelve a lanzar ese subagente -->se vuelve a copiar del mensaje del agente, entero,<!-- /solo-cowork --> y se repite la comprobación |
| Un agente no declara `recuento` | se sigue; el informe dice con ATENCIÓN que esa respuesta no se pudo cotejar |
| Una búsqueda web general trae la URL de una página | la sección 8 la presenta sin URL y lo dice con ATENCIÓN |
| La búsqueda de la referencia no da una sola fila | segunda búsqueda más amplia y se pregunta enseñando las candidatas; nunca un código que no salga de `Referencias` de este expediente |
| El usuario da un código de referencia | se comprueba en `Referencias` y se le enseña su nombre antes de usarlo; si no existe, no se usa |
| Homonimia señalada por un agente | se traslada al usuario antes del informe; su decisión consta en Limitaciones |
| Sin hallazgos en todas las fuentes | informe igualmente, con las fuentes y fechas consultadas |
| `sellar_uso_ia` dice que no hay huecos | el informe ya estaba sellado o no es el que escribió el script: no lo repitas, dilo |
| `sellar_uso_ia` dice que no tiene constancia de lo facilitado | o no se sirvió nada por el plugin, o el MCP se reinició a mitad: el informe lo dice y remite a `RegistroEmision.jsonl`; cuéntaselo al auditor tal cual |
