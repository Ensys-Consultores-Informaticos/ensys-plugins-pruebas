---
name: cuestionario-cuentas-anuales-gesia
description: >
  Rellena el cuestionario de revisión del contenido de la memoria de un expediente de
  Gesia a partir de las cuentas anuales del cliente en PDF: un Excel con el formato de
  exportación de Gesia, listo para importar, y un papel en Word que justifica cada
  respuesta. Úsalo si piden revisar la memoria, contestar el cuestionario de cuentas
  anuales o comprobar qué desgloses faltan, o dicen "revisa la memoria", "rellena el
  AG)20" o "checklist de la memoria". NO es para el diario contable, ni para ratios o
  revisión analítica. SI SOLO DICEN «CUENTAS ANUALES», NO LANCES NADA: este revisa EL
  CONTENIDO DE LA MEMORIA y necesita el PDF; estados-financieros revisa LAS CIFRAS del
  expediente, sin PDF. Pregunta cuál quieren. Requiere el servidor API de Gesia arrancado
  y las cuentas anuales en PDF.
---

# Revisión del contenido de la memoria (Gesia)

Produce un papel de trabajo, no una publicación. Los dos ficheros se escriben **siempre**
en `<expediente>\AsistenteIA\CuestionarioCuentasAnuales\` —la regla del proyecto de una
subcarpeta por skill, para que el auditor sepa dónde buscar sin preguntar— y **nunca se
publican** en ninguna URL: contienen las cuentas anuales de un cliente auditado.

Los dos scripts de generación crean esa carpeta si no existe. No hace falta `mkdir`.

---

## Antes de empezar: ¿te han pedido la memoria, o las cifras?

**«Cuentas anuales» no es este skill, ni es el otro: son las dos cosas.** Aquí se revisa **el
contenido de la memoria** contra el PDF del cliente; las cifras del expediente —balance,
resultados, patrimonio neto y flujos— las revisa `estados-financieros`, que no necesita PDF.

Si la petición no distingue, **pregunta antes de tocar nada** y ofrece las dos. La pista más
fiable: **sin PDF del cliente este skill no puede trabajar**, y el otro no lo necesita. Esa pista
sirve para distinguir los dos skills, **no para ir a buscar el PDF**: si es este, el PDF lo da el
auditor (paso 1).

---

## Cuatro reglas que gobiernan todo

**1. Ante la duda, `4`.** Un `4` (Pendiente) de más le cuesta al auditor un minuto de
revisión. Un `1` (Sí) de más es un desglose que ya no vuelve a mirar nadie. **No se
responde `1` sin poder citar dónde está el desglose en la memoria.**

**2. Esto propone, no concluye.** El auditor revisa el Excel antes de importarlo y es
quien firma. El papel de trabajo lo dice explícitamente, y esa frase no se quita.

**3. `Disponible = False` no se toca.** Es una decisión del auditor sobre qué aplica al
encargo. Un skill que la ignora está deshaciendo trabajo hecho.

**4. La importancia relativa no filtra los hallazgos.** Si el desglose falta, va un `2`
aunque el importe sea ridículo. Se revisa si el desglose **está**, no si la cifra mueve la
opinión. Medido: de los cuatro hallazgos que en el expediente de calibración el modelo
marcó y el auditor
no, el auditor confirmó los cuatro — y dos eran de 4.875 € y 239 €. Un umbral de importe habría
borrado la mitad de lo que este skill aporta.

---

## Dónde están los scripts

Al cargarse, el runtime indica el **directorio base de este skill**. Todas las rutas
`scripts/…` son relativas a ese directorio, no al directorio de trabajo. Guárdalo al
empezar:

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(mktemp -d "${TMPDIR:-/tmp}/cuestionario-XXXX")" && echo "$TRABAJO"
```

**Un directorio de trabajo nuevo en cada ejecución**, en la carpeta temporal del sistema y
nunca en `AsistenteIA`: así no se mezcla con lo que dejó una ejecución anterior. **No hagas
`cd` a él**; trabaja con rutas completas. Al final se borra desde fuera, y el entorno no deja
borrar el directorio en el que estás.

**Anota la ruta que imprime**: si el entorno no conserva variables entre llamadas, vuelve a
escribir `TRABAJO="<esa ruta>"` al principio de cada orden —y lo mismo `SKILL` y `DATOS`—, sin
crear otro. Esa ruta anotada es también la que se borra al final, escrita literal (paso 9).

**El dato entra por el MCP, siempre.** Los scripts no hablan con el API de Gesia: lo
hicieron hasta el 23/08/2026 y eso hacía el skill inservible en Cowork, porque ni el
sandbox ni el `device_bash` alcanzan el `localhost` del auditor. El cuestionario entra
en una sola llamada a `exportar_consulta`, que lo deja en disco: son 154 filas y ~94.000
caracteres —`consultar_gesia` cortaría en 60.000—, y tú lees de ese fichero solo la
sección que estás contestando.

**Dónde se exporta depende del entorno**, porque quien exporta y quien calcula no
siempre son la misma máquina (ver `docs/arquitectura.md`):

```bash
# En la máquina del auditor: MCP y scripts comparten disco.
DATOS="$TRABAJO"

# En Cowork: exportar DENTRO de una carpeta conectada -una ruta del sandbox o
# del $TEMP de Windows no sirve-, subirla con device_stage_files, y leer la
# copia que aparece en el sandbox.
#   exportar_consulta(..., ruta = "<raíz conectada>/_tmp_cowork/cuestionario.json")
# Lo subido cuelga de una subcarpeta con el nombre de la carpeta conectada, como en
# los demás skills del plugin.
DATOS="/mnt/user-data/uploads/<carpeta conectada>/_tmp_cowork"
```

---

## Secuencia

### Paso 1 — Expediente, y pedir las cuentas anuales

```
configurar(perfil = "cuestionario-cuentas-anuales")
contexto_expediente()
```

**Pide ya el PDF de las cuentas anuales**, en este paso, junto al expediente: puede subirlo o
decirte dónde está. Mientras lo localiza, sigues con el paso 2. **No lo busques tú**: ni en las
tablas de Gesia ni recorriendo la carpeta del expediente. El PDF lo tiene el auditor, y buscarlo
tarda y no aporta nada (medido: el modelo se ponía a buscarlo en Gesia antes de pedirlo). Se pide
y se espera; en el paso 3 se confirma.

**El perfil va lo primero**: marca el comienzo del procedimiento, y desde ahí el MCP lleva
la cuenta de lo que se facilita a la herramienta, que es lo que el papel de trabajo dirá en su
apartado de uso de IA. Este perfil no seudonimiza nada: el cuestionario es texto del máster y no
lleva terceros. Las cuentas anuales en PDF no pasan por el MCP —las lees tú directamente, en
claro— y por eso el papel las declara aparte (paso 8).

**`contexto_expediente()` va siempre, después del perfil, aunque ya lo tengas en la
conversación.** Lo que se leyó antes con otro perfil cuenta para aquel procedimiento, no para
este: si no lo vuelves a pedir, el apartado de uso de IA no lo lista como facilitado y el papel
dice menos de lo que se usó.

Si falta `gs3_file`, **pide la ruta al usuario**. No la adivines. Si `configurar` dice que el
servidor API no responde, **llama a `arrancar_api`**: lo levanta en el equipo del auditor y
sigues. Solo si eso falla, díselo al auditor.

**Si `configurar` —o cualquier otra llamada del MCP— avisa de que otra conversación está
trabajando con otro expediente o con otro perfil en el mismo servidor**, díselo al auditor tal
cual y **no sigas hasta que confirme**. Las conversaciones abiertas a la vez comparten el MCP:
cada `configurar` cambia el expediente y el perfil de todas, y lo que una exporta o sella puede
acabar en el papel de la otra sin que nada lo avise.

<!-- solo-cowork -->**En Cowork, mira ya qué carpetas tiene conectadas la sesión** (`device_list_dir`).
Este skill necesita dos: **la que contiene el expediente** —la carpeta del `gs3_file` que devuelve
`configurar`, donde se escriben los dos ficheros y suele estar el PDF— y **la de la exportación
temporal**, la raíz conectada de la que cuelga `_tmp_cowork` (paso 4). Si la del expediente no
está conectada, pide acceso con `device_request_folder_access` sobre esa carpeta, y si
`_tmp_cowork` va a ir en otra, pídelo también para esa. **Pídelo ahora, no al entregar**:
sin acceso ni se sube el cuestionario ni se escribe el papel, y descubrirlo después de contestar
ciento y pico preguntas es perder la sesión. Si el auditor no lo concede, **para** y dilo.

<!-- /solo-cowork -->
### Paso 2 — Localizar el cuestionario

Es el `Referencias` con `CodigoTipoGuia = 'CCC'`, `CodigoReferencia LIKE 'AG)20/%'` y
`Disponible = True`.

```sql
SELECT CodigoReferencia, Referencia, Disponible
FROM Referencias
WHERE CodigoTipoGuia = 'CCC' AND CodigoReferencia LIKE 'AG)20/%'
ORDER BY CodigoReferencia
```

Las cuatro modalidades —PYME, abreviada, normal y consolidada— **existen siempre las
cuatro**; el auditor activa la que aplica. Si hay **ninguna disponible o más de una,
pídele la referencia al usuario**. No elijas tú.

> **Ojo, dos cosas, y las dos muerden** (medido el 01/09/2026 en dos expedientes):
>
> 1. `AG)20` es solo el nodo del índice y **tiene cero filas**. El contenido cuelga de
>    sus hijos. Ni su título ni la numeración de los hijos son fijos: se llama
>    «ESTADOS FINANCIEROS (CUENTAS ANUALES)» en un expediente y «MEMORIA Y CUENTAS
>    ANUALES» en otro, y la memoria PYME es `AG)20/01` en uno y `AG)20/05` en otro.
>    **Nunca fijes el código**: localiza por tipo, título y `Disponible`.
> 2. **Puede haber más de un `CCC` con `Disponible = True`.** En un expediente real
>    salían dos: la revisión de la memoria (154 filas) y una «Revisión de las cuentas
>    anuales» de 23. Si la consulta devuelve varias, **pregunta cuál**, o dilo y
>    quédate con la de más filas; lo que no vale es coger la primera en silencio.

### Paso 3 — Confirmar y preparar las cuentas anuales

**Sin el PDF no se responde nada, y el PDF lo indica el usuario.** Si todavía no te ha dicho
cuál es, vuelve a pedírselo —puede subirlo o indicarte dónde está— **aunque veas un candidato obvio en la
carpeta del expediente**: un borrador sin firmar, las cuentas del ejercicio anterior o una
versión reformulada tienen el mismo aspecto, y contestar contra el documento equivocado da un
cuestionario entero que parece bueno.

**Si hay más de una copia** —o más de un PDF que pueda serlo—, lístalas con su nombre, su
carpeta, su tamaño y su fecha de modificación, y pide que confirme cuál. No elijas tú por la
fecha ni por el tamaño. El que confirme es el que pasas a `--pdf` en el paso 8, y el papel lo
dice en su ficha.

**Lee el PDF directamente, sin convertirlo con ningún script.** La herramienta de lectura
abre PDFs, y los abre igual de bien cuando son un escaneo — que es el caso normal, no la
excepción: las cuentas anuales que el auditor archiva son el ejemplar **firmado**, y en
el expediente de calibración eran 31 páginas con **cero** caracteres extraíbles.

Van en tramos de 20 páginas como máximo por lectura, así que unas cuentas anuales normales
son dos lecturas.

**Que el PDF es de esta sociedad se comprueba en la imagen de la página, no en el texto
extraído.** La cabecera con el nombre de la sociedad va a menudo como **logotipo**, que es una
imagen y no sale en la extracción de texto: buscar la razón social de `contexto_expediente` en
el texto da cero coincidencias aunque el nombre esté impreso en todas las hojas (registro del
21/10/2026). Mira la portada y la cabecera de las páginas como imagen; solo si tampoco ahí
aparece el nombre, o aparece otro, pregúntale al auditor.

Léelas **todas** antes de contestar la primera pregunta.

**Y en cuanto acabes de leerlas, escribe tus notas en disco**, en
`$TRABAJO/memoria_notas.md`: qué notas tiene la memoria, en qué página del PDF empieza cada
una, y los datos que ya sepas que vas a necesitar —importes del balance, criterios de la
nota 4, lo que aparezca y lo que no—.

**Las páginas se citan siempre por la numeración del fichero PDF**: la primera página del
fichero es la 1, aunque sea la portada y el documento imprima otro número. Es la que usa la
lectura por tramos, la única que existe también en un escaneo sin numerar, y la que encuentra
el auditor al abrir el fichero. La numeración impresa no suele coincidir —portada, índice y
hojas de firmas no la llevan—: en las notas puedes apuntarla para orientarte, pero en
`evidencia` va siempre la del PDF (`"Nota 9, p. 14"`). El papel declara esta numeración en
una línea de su ficha.

No es burocracia: **contestar 137 preguntas es una sesión larga y el contexto se compacta a
mitad.** Cuando pasa, sin esas notas hay que releer el PDF entero otra vez. Medido en
cliente el 23/08/2026: la segunda lectura de 33 páginas costó unos cinco minutos de sesión,
y era evitable. Con las notas en disco, tras una compactación relees el fichero y sigues;
solo vuelves al PDF para lo que las notas no resuelvan.

> Aquí había un `preparar_memoria.py` que rendería las páginas con PyMuPDF. Se quitó el
> 22/08/2026: obligaba al cliente a instalar Python y `pymupdf` para hacer algo que el
> modelo ya hace solo. Ver `DISENO.md`, «Lo que se ejecuta y dónde».

### Paso 4 — Traer el cuestionario

**El dato entra por el MCP, siempre.** Los scripts de este skill no hablan con el API de
Gesia<!-- solo-cowork:alt=. -->: lo hicieron hasta el 23/08/2026 y eso lo hacía inservible en Cowork, porque ni el
contenedor ni el `device_bash` alcanzan el `localhost` del auditor.<!-- /solo-cowork -->

**Primero, el código del cuestionario**: el `CodigoGuia` de `DetalleGuias`, que es lo que
filtra la exportación. Se saca de la propia `DetalleGuias`, agrupando por la referencia del
paso 2:

```
consultar_gesia(sql =
  "SELECT CodigoGuia, Count(*) AS Filas
   FROM DetalleGuias
   WHERE CodigoGuia LIKE '<la referencia del paso 2>%'
   GROUP BY CodigoGuia")
```

Sale una fila por cuestionario cuyo código empiece así, con su número de filas: pocas por
construcción. Quédate con la que **coincide con la referencia**; si ninguna coincide, o hay
más de una que podría ser, enséñaselas al usuario y que diga cuál. Si no sale ninguna, el
cuestionario no tiene contenido en este expediente: **para** y dilo.

**No lo busques por otro camino**, que ya se ha intentado: `Referencias` no tiene columna
`CodigoGuia`, y `Guias` no tiene `CodigoReferencia`. JET no responde «columna desconocida»
sino **«No se han especificado valores para algunos parámetros»**, que no dice qué falla. En el
único expediente donde se ha medido, el código coincidía con la referencia (`AG)20/01` →
`AG)20/01`); es una sola medida, así que compruébalo con la consulta y no lo des por hecho.

**Después, el cuestionario: una sola consulta, y a fichero.** El cuestionario no cabe en una
respuesta —el PYME son unos 129.000 bytes y `consultar_gesia` corta en 60.000—, pero eso da igual porque
`exportar_consulta` escribe en disco y a ti solo te devuelve el recuento:

```
exportar_consulta(
  sql = "SELECT Prioritaria, CodigoArea, CodigoGuia, CodigoOrden, Punto,
                DesglosePunto, Descripcion, CodigoClaseReferencia,
                CodigoReferencia, CodigoRealizado, Respuesta, Comentario
         FROM DetalleGuias
         WHERE CodigoGuia = '<el CodigoGuia de la consulta anterior>'
         ORDER BY Val(CodigoOrden)",
  ruta = "<en local: $TRABAJO/cuestionario.json — en Cowork: <raíz conectada>/_tmp_cowork/cuestionario.json>")
```

<!-- solo-cowork -->**En Cowork, súbelo después con `device_stage_files`** y trabaja con la copia
del sandbox. Si exportas a una ruta que no esté bajo una carpeta conectada, no
se puede subir y el fichero no le sirve al script: hay que reexportarlo.

Si `device_stage_files` falla por permisos, pide acceso con `device_request_folder_access`
sobre la raíz conectada y repite la subida **una sola vez**. Si vuelve a fallar, **para** y
díselo al auditor con la ruta del fichero: sin él en el sandbox no hay cuestionario que
contestar, y reintentar en bucle no lo arregla.<!-- /solo-cowork -->

Las doce columnas y en ese orden: son las del export de Gesia y `generar_xlsx.py` las copia
literales.

Dos detalles que cuestan una vuelta si se olvidan:

- **`ORDER BY Val(CodigoOrden)`, no `ORDER BY CodigoOrden`.** El campo es texto, así que sin
  `Val()` ordena 1, 10, 100, 101… y las secciones salen entrelazadas.
- **`Punto` es numérico** y va sin comillas si alguna vez lo filtras.

**Comprueba el recuento que te devuelve** y quédatelo: es con lo que se compara luego si el
contrato avisa de que faltan preguntas. El PYME son 154 filas.

**No abras `cuestionario.json`.** Lo leen los scripts, y es justo el fichero que no tiene
que pasar por tu contexto: son 129 KB de texto del máster que no aportan nada hasta que hay
que contestar una sección concreta, y para eso está `mostrar_seccion.py`.

### Paso 5 — Verificar el contrato (puede abortar)

```bash
python "$SKILL/scripts/verificar_contrato.py" \
    --cuestionario "$DATOS/cuestionario.json" --guia "<el CodigoGuia del paso 4>"
```

Salida `2` → **para**. No se genera nada. Salida `1` son avisos: léelos, sobre todo el
**C12**, que dice si el cuestionario ya tenía respuestas. Si las tenía, **pregunta al
usuario** si se rellenan solo los huecos o se rehace entero, antes de seguir.

### Paso 6 — Responder, sección a sección

Recorre las secciones de una en una. Para cada una:

```bash
python "$SKILL/scripts/mostrar_seccion.py" --cuestionario "$DATOS/cuestionario.json" --punto 3
```

Con las preguntas de esa sección y la memoria delante, decide para cada pregunta:

| Código | Cuándo |
|---|---|
| `1` Sí | el desglose **está** en la memoria y puedes decir dónde |
| `2` No | el desglose **debería estar y no está** |
| `3` No aplica | lo que la pregunta nombra **no existe** en esta empresa |
| `4` Pendiente | **la memoria no permite decidirlo.** Es la respuesta por defecto |

**`1` y `3` significan lo mismo para el trabajo: esta pregunta no arroja hallazgo.** Cuál
de los dos se pone es convención del auditor que contesta, no criterio de auditoría, y por
eso `probar_calibracion.py` los colapsa: el número que mide el skill es el del eje
hallazgo/no hallazgo. **No gastes esfuerzo en afinar esa frontera.**

Se intentó dar una regla y no funciona. En la segunda calibración fueron 23 de 42 discrepancias —18 en
un sentido y 5 en el otro—, y no se deduce de la memoria: de las 55 respuestas `3` con
motivo negativo el auditor dio por buenas 39, así que voltearlas en bloque arreglaba 16 y
rompía 39.

La única pauta que ayuda: **si la memoria dice algo sobre la pregunta —aunque sea que la
circunstancia no se da—, pon `1`**; reserva `3` para cuando lo que la pregunta nombra no
existe en esta empresa y la memoria calla. Y si el expediente ya trae secciones
contestadas, copia la convención que siga de hecho.

**Y responde `4` siempre que contestar exija saber algo que no está en las cuentas
anuales.** Ejemplo real: «si hay proveedores con vencimiento superior a un año, la partida
se desglosa» no se puede responder leyendo el balance —donde no aparecen— porque la
pregunta es si *existen*, y eso lo sabe el auditor, no la memoria. Contestar `3` ahí borra
un hallazgo: es como se perdieron 4 de los 12 que había en el expediente de calibración.

**Antes de firmar un `2`, pasa estos cuatro filtros.** Salen de la tercera calibración
(19/09/2026), en la que el auditor revisó **13 respuestas `2` y las trece se cayeron**: doce
estaban mal y la decimotercera es cierta pero inmaterial. No es que el modelo marcara de más
por valiente: es que dio por incumplimiento cuatro cosas que no lo eran.

**(a) ¿Tu motivo empieza por «no se menciona», «no existe nota sobre» o «no informa de»?**
Entonces pregúntate si eso que falta **existiría en esta empresa**. Ocho de los trece eran
desgloses cuya circunstancia de fondo no se da: no hay capitalización de gastos financieros,
no hay costes de desmantelamiento, no hay deterioro de las inversiones en el grupo, la deuda
no tiene garantía real, no hay compromisos fuera de balance. La memoria no lo cuenta porque
no hay nada que contar. **Si no puedes saber desde las cuentas anuales si la circunstancia se
da, es `4`, no `2`.** Es la regla 1 de arriba, aplicada donde más se incumple.

**(b) ¿La pregunta es de presentación o de desglose?** Si versa sobre **cómo se presenta una
partida** en el balance o en la cuenta de pérdidas y ganancias —si el capital está inscrito,
si Aprovisionamientos separa los trabajos de otras empresas— no es una obligación de
información de la memoria y no se responde leyéndola: va `3`. Dos de los trece.

**(c) ¿Has mirado la memoria entera, o solo la nota que sugiere el cuestionario?** Dos de los
trece estaban informados **en otra nota**: el salto de Mobiliario lo explicaba la 8.1 cuando
el motivo decía que faltaba en la 6. Busca el dato por toda la memoria antes de decir que no
está.

**(d) ¿Estás dando por hecho algo del encargo que la memoria no dice?** Quién administra la
sociedad, quién es apoderado, quién debe firmar. El modelo dedujo de una nota que una persona
era administradora, montó dos hallazgos sobre su firma ausente, y resultó ser el director
general. **Los hechos del encargo no se deducen de la memoria: si hacen falta, es `4`.**

Y cuando el `2` pase los cuatro filtros, **ponle el importe en el motivo**. La regla 4 de
arriba sigue en pie —la importancia relativa no filtra hallazgos, y está medida: el auditor
confirmó hallazgos de 4.875 € y de 239 €—, pero con la cifra delante descartar uno inmaterial
le cuesta un vistazo en vez de una búsqueda.

**Dicho todo eso, no te vuelvas tímido.** En las dos primeras calibraciones los `2` fueron
buenos —nueve de nueve válidos en la primera, cero peligrosos en la segunda— y cuatro eran
desgloses que el auditor no había detectado. El coste de este skill sigue estando en los
hallazgos que **no** ve. Los filtros de arriba no dicen «marca menos»: dicen **«lo que no
puedas decidir leyendo las cuentas, déjalo en `4` y que se vea en el Word»**, que es para lo
que está el papel de trabajo. Este skill contesta de una pasada y deja escritas las dudas; no
se convierte en un interrogatorio al auditor.

Ve acumulando en `$TRABAJO/respuestas.json`:

```json
{"respuestas": [
  {"orden": 2, "respuesta": 1,
   "motivo": "La memoria incluye balance, PyG y memoria PYME",
   "evidencia": "Índice, p. 1"}
]}
```

`orden` es el `CodigoOrden` de la fila. **Toda pregunta lleva una entrada** — si no se
puede contestar, va un `4` con el motivo. Las **cabeceras de sección no se responden**:
`mostrar_seccion.py` ya no te las enseña.

`evidencia` es obligatoria para un `1`. Sin ella, la respuesta es `4`. Y la página que cite
es la del fichero PDF (paso 3), nunca la impresa.

**Da noticias al usuario al terminar cada bloque de secciones** —cada tres o cuatro secciones,
o unas treinta preguntas—, en una línea: «Secciones 1 a 4 contestadas: 38 de 137 preguntas, 2
en `2` y 6 en `4`. Sigo con la 5.» Y guarda `respuestas.json` en ese momento, no solo al final.
Contestar el cuestionario entero es la parte más larga del skill y no hay otra forma de que el
auditor sepa que avanza: en el registro del 21/10/2026 el entorno avisó cuatro veces de que el
usuario no tenía noticias, y la conversación acabó resumida a mitad. Con el avance en disco y
dicho en el chat, tras un resumen se sigue desde el último bloque.

### Paso 7 — Generar el Excel

**Si los ficheros ya existen, una sola pregunta, antes de generar el Excel.** Mira si en
`<expediente>\AsistenteIA\CuestionarioCuentasAnuales\` ya están el Excel de este paso o el Word
del siguiente<!-- solo-cowork:alt=. --> —en Cowork, listando la carpeta conectada con `device_list_dir`; en
local, en el disco—.<!-- /solo-cowork --> Si hay alguno, **pregunta al auditor una vez, para los dos**:
sobrescribirlos, o guardar los nuevos con « (rehecho AAAA-MM-DD)» antes de la extensión, con la
fecha de hoy. Ni los sobrescribas sin preguntar ni inventes otro sufijo: al repetir un
procedimiento el mismo día, una ejecución pisó el papel y otra improvisó el nombre (registro del
21/10/2026). Los nombres elegidos son los de todo lo que sigue —el `--xlsx` del paso 8<!-- solo-cowork -->, la
bajada al expediente<!-- /solo-cowork --> y el sello—.<!-- solo-cowork --> En Cowork, `device_commit_files` va **sin
`force`**; solo si el auditor eligió sobrescribir y el commit lo rechaza porque el fichero existe,
repítelo con `force` y díselo.<!-- /solo-cowork -->

```bash
python "$SKILL/scripts/generar_xlsx.py" \
    --cuestionario "$DATOS/cuestionario.json" \
    --respuestas "$TRABAJO/respuestas.json" \
    --salida "<destino>/AG20-01_<CLIENTE>_<EJERCICIO>.xlsx"
```

Aborta si falta alguna pregunta por responder o si hay respuestas fuera de 1-4.

<!-- solo-cowork:alt=**El destino es la carpeta del expediente**, directamente: `<expediente>/AsistenteIA/CuestionarioCuentasAnuales/`. Vale igual para el papel de trabajo del paso siguiente. -->**El destino depende del entorno.** En la máquina del auditor, directamente
`<expediente>/AsistenteIA/CuestionarioCuentasAnuales/`. En Cowork el script escribe
en el sandbox, así que va a `$TRABAJO` y luego se baja: `SendUserFile` devuelve un
`file_uuid` y `device_commit_files` lo escribe en esa carpeta del expediente. Vale
igual para el papel de trabajo del paso siguiente. **Cada fichero por su nombre exacto,
nunca con un comodín**: en `$TRABAJO` están también las notas, las respuestas y el
cuestionario exportado, y nada de eso va al expediente.<!-- /solo-cowork -->

Copia once columnas literales del expediente y calcula una, `Respuesta`. En particular
**`CodigoRealizado` no se deduce**: hay expedientes con preguntas contestadas y esa
columna vacía, así que rellenarla sería inventar dato.

### Paso 8 — Generar el papel de trabajo

```bash
python "$SKILL/scripts/generar_papel.py" \
    --cuestionario "$DATOS/cuestionario.json" \
    --respuestas "$TRABAJO/respuestas.json" \
    --generado "<AAAA-MM-DD>" \
    --cliente "<razón social>" --cierre "<fecha de cierre>" \
    --xlsx "<el Excel que acaba de escribir el paso 7>" \
    --pdf "<el PDF confirmado en el paso 3, con su ruta en el equipo del auditor>" \
    --salida "<expediente>/AsistenteIA/CuestionarioCuentasAnuales/revision_memoria_<CLIENTE>_<EJERCICIO>.docx"
```

`--generado` es obligatorio y lo pones tú: **nada en este skill lee el reloj**. Un papel de
trabajo tiene que poder regenerarse idéntico dentro de dos años.

**`--cliente` y `--cierre` salen de `contexto_expediente`** y hay que pasarlos. Si los
omites, la cabecera del papel sale en blanco: antes se leían del API y, cuando el API no
respondía, quedaba vacía sin decir nada. Ahora al menos el hueco se ve en el comando.

**El papel termina con el apartado «Utilización de herramientas de inteligencia artificial»**,
con una marca en la ficha de cabecera: la evidencia de que las respuestas se propusieron con una
herramienta de IA, de qué se le facilitó y de cómo debe verificarse. Dice que las respuestas, sus
motivos y las referencias a la memoria los ha redactado la herramienta, y que las mismas
respuestas van en el Excel de importación. **El apartado va solo en el Word**: el Excel no se
toca, porque lo lee el importador de Gesia y una hoja de más podría romper la importación.

- **`--xlsx`** es el Excel del paso 7: el script lo coteja con sus propias respuestas —una sola
  hoja, las columnas del expediente sin cambios y la misma `Respuesta` en cada pregunta— y deja
  el resultado entre sus comprobaciones. Sin él, el papel dice que no se ha cotejado.
- **`--pdf`** es obligatorio: el PDF de las cuentas anuales que confirmó el usuario en el paso
  3, con su ruta en el equipo del auditor (si lo subió a la conversación, su nombre). Sale tal
  cual en la ficha de cabecera, junto a la línea que dice cómo se numeran las páginas citadas,
  y sin él el script para con salida `2`. El MCP no lo ve, así que el apartado de uso de IA lo
  declara además como información facilitada en claro.

Las comprobaciones de la herramienta se calculan sobre lo que lleva el papel y, si algo no
cuadra —un «Sí» sin evidencia, una pregunta sin respuesta, un Excel que dice otra cosa—, lo
dicen con «ATENCIÓN» y el script lo imprime: corrígelo y vuelve a generar. Los apartados de la
herramienta quedan con huecos que se rellenan al archivar (paso 9); los de verificación,
verificado por, efecto en la conclusión y revisión **son del equipo y salen en blanco**. No
escribas nada en ellos ni propongas texto para ellos.

### Paso 9 — Entregar

**Con el papel de trabajo ya en el disco del auditor**, en
`<expediente>\AsistenteIA\CuestionarioCuentasAnuales\`<!-- solo-cowork --> —en Cowork, después
de `device_commit_files`: la ruta del contenedor no vale—<!-- /solo-cowork -->, sella el Word:

```
sellar_uso_ia(ruta = "<expediente>/AsistenteIA/CuestionarioCuentasAnuales/<papel>.docx",
              modelo = "<el modelo con el que trabajas>",
              procedimiento = "cuestionario-cuentas-anuales")
```

Rellena en el apartado de uso de IA lo que solo sabe la aplicación: herramienta y versiones,
quién lo ejecutó, dónde corrieron los scripts y **qué información se facilitó y cómo**, según
lo que el MCP ha servido desde el paso 1. `procedimiento` es el mismo perfil del paso 1, y es
lo que le dice al MCP de qué procedimiento tiene que listar lo facilitado. En `modelo` pon el
nombre y la versión que te da tu propio contexto; si no lo sabes, déjalo vacío. **Solo sobre el
Word**: el Excel de importación no lleva el apartado y no se sella. **Sin esta llamada el papel
queda con huecos que dicen «pendiente»**: no se da por entregado.

**Si en algún momento el MCP avisó de otra conversación con otro expediente o perfil en el
mismo servidor** (paso 1) y el auditor decidió seguir, recuérdaselo al entregar: es lo primero
que tiene que mirar si el apartado de uso de IA lista algo que este procedimiento no usó.

Di la ruta completa de los dos ficheros —siempre
`<expediente>\AsistenteIA\CuestionarioCuentasAnuales\`— y **cuántas preguntas
quedaron en `2` y en `4`**, que es el trabajo que le queda al auditor. Recuérdale que:

- el Excel se importa **desde Gesia**, y conviene revisarlo antes. El formato está
  comprobado contra el importador real (22/08/2026), así que si algo falla al importar es
  el contenido, no la estructura;
- las respuestas son una propuesta, y la revisión y la firma son suyas;
- el apartado de uso de IA del papel deja la verificación, quién la hace, su efecto en la
  conclusión y la revisión en blanco para el equipo: mientras lo estén, el papel no es
  evidencia de auditoría.

**Los temporales.** Los volcados de `exportar_consulta` los borra
`limpiar_exportaciones(procedimiento = "cuestionario-cuentas-anuales")`, y esa es la vía:
funciona igual en local y en Cowork —lo borra el MCP, que corre en la máquina del usuario— y
borra lo que él escribió sin que haya que decirle cuál. **Con `procedimiento` borra solo lo de
este procedimiento**: lo que haya exportado otra conversación con el mismo servidor se queda
donde está. Si alguno no se deja, lo dice con su ruta.

El directorio de trabajo va aparte, **borrado desde fuera** —sin haber hecho `cd` a él: si lo
hiciste, sal antes—:

```bash
rm -rf "<!-- solo-cowork:alt=<TRABAJO> --><la ruta que anotaste al crearlo, literal><!-- /solo-cowork -->"
```

<!-- solo-cowork -->**Con la ruta escrita tal cual, nunca con una variable ni con `$(cat …)`**: si el
entorno no conserva variables, `"$TRABAJO"` llega vacío, y el control de seguridad del entorno
bloquea un `rm -rf` sobre una expansión como `"$(cat …)"` (registro del 21/10/2026).

<!-- /solo-cowork -->**Y cuenta con que en Cowork no te dejen**: el puente no tiene permiso de borrado
en el equipo del usuario (comprobado el 25/08/2026). Por eso los volcados van a la
carpeta temporal del sistema y **nunca a `AsistenteIA`**, donde solo debe quedar
el entregable. Si el borrado falla, di las rutas exactas de lo que queda.


---

## Lo que este skill no hace

Decirlo importa: callar una limitación es peor que tenerla, y la conversación no va al
archivo del encargo. El papel de trabajo ya lo recoge, pero tenlo presente al explicarlo:

- **No escribe en el expediente.** El MCP solo lee; el auditor importa el `.xlsx` a mano.
- **No juzga si la memoria es correcta**, solo si el desglose **está**.
- **No contrasta las respuestas contra los saldos** del expediente. Una pregunta
  respondida «no aplica» sobre un epígrafe con saldo no se detecta hoy.
- **No cuadra el balance ni la PyG** contra el PDF.
- **No cubre los demás cuestionarios `CCC`** (continuidad, independencia, control interno).
- **No verifica su propio resultado por el equipo.** Propone qué contrastar; la verificación,
  quién la hace y su efecto en la conclusión los escribe el equipo en el apartado de uso de IA.

## Degradación

| Situación | Qué sale |
|---|---|
| `configurar` dice que el servidor API no responde | `arrancar_api` y se repite; solo si eso falla, se le dice al auditor |
| El MCP avisa de otra conversación con otro expediente o perfil en el mismo servidor | se le dice al auditor tal cual y **no se sigue hasta que confirme** |
| El usuario no ha dicho qué PDF leer, o hay varias copias | se le pregunta, con la lista de copias (nombre, carpeta, tamaño, fecha); no se elige por él |
| La razón social no sale en el texto extraído del PDF | se mira en la imagen de la portada y las cabeceras (suele ser un logotipo); solo si tampoco está ahí, se pregunta |
| No sale ningún `CodigoGuia` para la referencia | **para**: el cuestionario no tiene contenido en el expediente |
| `sellar_uso_ia` dice que no hay huecos | el papel ya estaba sellado o no es el que escribió el script: no lo repitas, dilo |
| `sellar_uso_ia` dice que no tiene constancia de lo facilitado | o no se sirvió nada por el plugin, o el MCP se reinició a mitad: el papel lo dice y remite a `RegistroEmision.jsonl`; cuéntaselo al auditor tal cual |<!-- solo-cowork -->
| La carpeta del expediente no está conectada a la sesión (Cowork) | `device_request_folder_access` sobre la carpeta que contiene el `.gs3`, y sobre la de `_tmp_cowork` si es otra, **antes del paso 3**; si no se concede, **para** y se dice |
| `device_stage_files` falla por permisos (Cowork) | `device_request_folder_access` sobre la raíz conectada y un reintento; si vuelve a fallar, **para** y se dice |<!-- /solo-cowork -->
