---
name: fsp-mum-gesia
description: >
  Valida contra las facturas escaneadas la muestra de una PRUEBA MUM (muestreo por
  unidades monetarias) de ForSampling: localiza el documento de cada elemento, mide el
  importe que sostiene y propone las columnas que espera ForSampling —saldo según
  auditoría, error y tasa de error— con la observación para copiar. Deja el papel en
  Excel, un elemento por fila. Úsalo si piden validar o revisar la muestra de una MUM,
  comprobar los importes contra las facturas, calcular el error por elemento o rellenar el
  saldo de auditoría, o dicen "revisa la MUM de servicios exteriores" o "qué diferencias
  hay entre libros y las facturas de la muestra". NO es la prueba de cumplimiento (fsp-
  cumplimiento) ni el papel de la NIA 530 (fsp-mum-nia530), ni la circularización, ni la
  cancelación de saldos. NO proyecta el error ni concluye si la prueba pasa: eso lo hace
  ForSampling. Requiere el servidor API arrancado, el .cli o el expediente que lo vincula,
  y la carpeta de los documentos escaneados.
---
_Versión del skill: 18/09/2026 · plugin interno 1.51.0 · pide MCP ≥ 1.19.1._


# Prueba MUM de ForSampling (fsp-mum)

Una MUM selecciona elementos de una población con probabilidad proporcional a su
importe, y el auditor comprueba en cada uno **cuánto vale de verdad**. De la diferencia
entre lo contabilizado y lo que sostiene el documento sale el error, y ForSampling lo
proyecta a la población. Este skill hace la parte de mirar el documento y medir.

Los ficheros se escriben en `<expediente>\AsistenteIA\FspMum\` y **nunca se publican**
en ninguna URL: llevan la contabilidad de un cliente auditado. `<expediente>` es **la carpeta
del fichero configurado**: la del `.gs3`, o la del `.cli` cuando se trabaja solo con
ForSampling, sin expediente de Gesia. Es la misma que usa el MCP para su registro.

**Este skill no escribe en ForSampling.** El MCP solo lee. Los importes propuestos y la
observación se copian a mano, y la firma «Asistente IA» deja constancia de quién los
redactó.

---

## Lo que mide, y lo que no hace por ti

Tres columnas por elemento, con los nombres que usa ForSampling:

| Columna | Qué es |
|---|---|
| `SaldoAuditoria` | lo que el documento sostiene para ese apunte |
| `ErrorAuditoria` | `Saldo − SaldoAuditoria`. Positivo: los libros dicen de más |
| `ErrorAuditoriaTasa` | el error sobre el saldo, en tanto por ciento |

**Lo que no hace, y no es un olvido:**

- **No proyecta el error a la población.** La proyección, el límite superior del error y
  la conclusión los calcula ForSampling con la muestra evaluada. Hacerlos aquí sería
  sustituir el motor estadístico de la prueba por una cuenta a ojo.
- **No compara con el error tolerable.** El papel lo enseña como contexto de la prueba,
  y ahí se queda.
- **No suma los errores, y sobre todo no los netea.** Un error de +600 y otro de −600 no
  se cancelan: son dos incorrecciones que se proyectan cada una por su lado. Decir «error
  neto cero» es el fallo más caro que puede cometer quien lee esta prueba, y ha pasado. Al
  ejecutar, los errores por exceso y por defecto se imprimen **por separado**.
- **No dice si la prueba pasa.** Eso es del auditor.

**El término de comparación lo fija la propia muestra.** Un apunte de gasto suele llevar
la base imponible y el IVA va a otra cuenta; otro puede llevar el total. En vez de
suponerlo por el plan contable, el skill mira **con qué casan los elementos que casan** y
usa ese término —base, total o neto tras retención— para medir los que no casan. Si la
muestra no da un criterio claro, no propone importe: lo decide el auditor. Equivocarse de
término convierte una cuota de IVA en un error de auditoría, y ese error se proyectaría a
toda la población.

---

## Dónde están los scripts

Al cargarse, el runtime indica el **directorio base del skill**. Las rutas `scripts/…`
son relativas a él, no al directorio de trabajo.

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(pwd)/trabajo" && mkdir -p "$TRABAJO"
```

Son cuatro: `preparar_documentos.py` (inventaría y renderiza las páginas que hacen falta,
y lleva la cuenta de lo transcrito), `verificar_contrato.py`, `generar_papel.py` y
`ejecutar_mum.py`, que encadena los dos últimos. Más `probar_mum.py`, el arnés.

---

## Secuencia

### Paso 1 — Expediente, cliente de muestreo y prueba

```
configurar(perfil = "fsp-mum")   # primero: el tercero de la muestra, tokenizado
contexto_expediente()
```

Si la primera llamada al MCP falla con **«Connection closed»**, **«Server … unavailable»** o
**«did not respond within 60s»**, **reintenta hasta tres veces, esperando entre intentos**: el
conector tarda unos segundos en arrancar y la primera petición puede llegar antes. Reintentar
seguido no basta —medido el 18/09/2026: los tres intentos fallaron y lo que funcionó fue esperar
alrededor de un minuto—. Si después sigue igual, pídele que reinicie Claude del todo.

**Y en cuanto vuelva, antes de cualquier otra cosa, repite `configurar()` con el expediente Y el
perfil.** Un reinicio del servidor borra el estado, y el MCP vuelve sin expediente y **sin
perfil**: si sigues sin reconfigurar, la muestra sale con **los nombres de los terceros en claro**.
El MCP lo avisa en la propia respuesta cuando detecta que hay columnas de nombre sin tokenizar
—«⚠ NOMBRES EN CLARO»—; si ves ese aviso, no sigas con esas filas: reconfigura y vuelve a
exportar.

**Lo primero, antes de leer nada: `configurar(perfil = "fsp-mum")`.** Con el perfil, la muestra
que exporta el MCP lleva el tercero de cada elemento como **token** —`PROV 40000012`,
`CLI 43000007`— en vez de la razón social, y cualquier otra columna de texto de la fila pierde
las palabras del nombre. El token es la cuenta del tercero, que en una población de compras no
es la de la fila (esa es la de gasto) sino **la contrapartida del asiento en el diario**; el MCP
la busca solo. El nombre no sale del equipo del auditor —ni al contenedor ni a este chat—; el
papel lo recupera al final con `rehidratar`. Trabaja y habla **por token**: «el elemento 301,
PROV 40000012, sale 116,00 por debajo». **Nunca preguntes al auditor a quién corresponde un
token ni lo adivines** por el documento: él lo lee en el papel. Si `configurar()` dice
`nombres_terceros: en claro — forzado por el auditor`, es que lo ha apagado él; no lo vuelvas a
encender tú.

**Las facturas escaneadas las decide el auditor, en el paso 3**: tachadas en su equipo antes
de subir, o tal cual. Con el perfil puesto, las prepara el MCP en cualquiera de los dos casos y
en las dos va estampado el token del emisor, así que el cruce conserva el tercero. Si el auditor
prefiere que tampoco la muestra viaje anonimizada, el interruptor es suyo:
`configurar(nombres = "claro")`.

**El diario: no lo pidas antes de saber si hace falta.** El MCP necesita la contrapartida de
cada elemento para tokenizar al tercero, pero **muchas poblaciones ya la traen** en una columna
propia (`CONTRAPFINAL` junto a `NOMBRECONTRAP`), y entonces el diario sobra. Así que **exporta
primero** y mira lo que dice `muestra_tokenizada`:

- «*N por la contrapartida que trae la propia población*» → **no preguntes nada**, ya está.
- «*N con token de reserva (TER h…)*» o `SIN DIARIO` → ahí sí falta, y entonces preguntas.

**Si `diario_comprobado` trae una `PROPUESTA`**, el MCP ya ha buscado entre los diarios
importados en ForSampling (`Muestreo\SesionesImportacion`) y ha encontrado uno con todos los
asientos de la muestra que además casa en importe. **No lo ha usado**: enséñale al auditor el
fichero y sus cifras y pregúntale si es el diario del que salió la población. Si dice que sí,
`configurar(smn_file = "<la ruta de la propuesta>")` y vuelve a exportar la muestra. Si la
propuesta dice que en esta prueba no cambiaría nada, díselo así y sigue.

**No elijas tú ningún otro `.smn` de esa carpeta**: hay decenas —medido: 55, 121 y 121 en tres
expedientes—, se llaman parecido, y la numeración de asientos se repite cada año, así que
tener los mismos números no prueba nada. Solo vale el que el MCP ha medido o el que diga el
auditor.

Sin propuesta, la frase: *«Necesito la contrapartida de cada elemento para tokenizar al
tercero; la saco del diario si me indicas dónde está el .smn del ejercicio completo»*. Si el
diario solo existe fuera de ForSampling —también en Excel—, puede importarlo en ForSampling,
que lo guarda como `.smn` en esa carpeta.

Pásalo con `configurar(smn_file = "<ruta>")`. Si no lo tiene o no lo sabe, **sigue**: la muestra
saldrá con tokens de reserva —los nombres no salen del equipo igual— y el papel lo hace constar.
Y si ofrece algo que no es un `.smn` —un Excel de la contabilidad—, el MCP lo rechaza sin tocar
el estado: no insistas ni intentes convertirlo.

Si el fichero activo es un `.gs3`, `configurar` deduce solo el `.cli` del cliente de
muestreo (`cli_file`). Si dice «sin cliente de muestreo vinculado», pregunta al usuario si
existe el `.cli` —suele estar en la carpeta `Muestreo` del expediente— y pásaselo a
`configurar` como fichero activo. Si tampoco existe, **para**.

```
obtener_entidad('pruebas')
```

**Pregunta qué prueba quiere validar** si hay más de una MUM, enseñando nombre, ejercicio,
área y referencia. No adivines por el nombre: «Servicios exteriores 24» y «Servicios
exteriores 25» son dos pruebas distintas con dos carpetas de facturas distintas. Si el
usuario nombra la prueba y el ejercicio, no preguntes.

Una prueba de tipo `Cumplimiento` **no es de este skill** —va por `fsp-cumplimiento`— y
una de `Confirmación Terceros` tampoco. Dilo y para.

### Paso 2 — Traer la muestra, los parámetros y la evaluación

```
exportar_consulta(entidad = "muestra", id = <MuestraId>, ruta = "<DATOS>/muestra.json")
obtener_entidad('parametros', id = <MuestraId>)      → guárdalo tal cual en <DATOS>/parametros.json
```

Y si el auditor ya evaluó la prueba, también:

```
exportar_consulta(entidad = "evaluacion", id = <MuestraId>, ruta = "<DATOS>/evaluacion.json")
```

Con ella, al ejecutar se imprime la comparación elemento a elemento: su importe frente al
propuesto. Es la calibración del skill sobre ese encargo, y donde se ve si se dejaría pasar
una incorrección.

`parametros.json` trae, además del tipo de prueba, el contexto que va al encabezado del
papel: unidad de muestreo, número de elementos de la población, **error tolerable** y
tamaño de muestra deseado. Guárdalo tal cual, sin recortarlo.

**Lee el resumen de la exportación de la muestra.** Trae dos líneas nuevas con el perfil:
`muestra_tokenizada` —cuántos terceros llevan token por su cuenta, cuántos por la contrapartida
del diario y cuántos de reserva— y `diario_comprobado` —cuántos asientos de la muestra están en
el diario y casan en importe—. Trasládalas al auditor en una línea. Si los asientos están en el
diario pero los importes no coinciden —una población ajustada por exclusiones o periodificaciones—,
el MCP lo dice como `POBLACIÓN AJUSTADA`, toma la contrapartida del asiento igual, y **no hay que
buscar otro diario**; en la MUM del segundo registro la contrapartida salió 24 de 24. Solo si
viene el error **«ese diario no es el de esta población»** —los asientos no existen en él, o
existen pero no casan ni importes ni cuentas: es otro ejercicio— la ruta es otra: si el error
trae una `PROPUESTA`, es lo del paso 1; si no, pídesela **una vez** al auditor, y **no busques
otro `.smn` por tu cuenta** aunque haya varios en la carpeta; si tampoco, sigue sin diario. Si
dice `SIN DIARIO`, es lo del paso 1: la propuesta si la hay, o tokens de reserva y adelante.

**Dónde es `<DATOS>` no depende del producto, depende de una propiedad**: si los scripts y
el MCP comparten disco. Compruébalo por la ruta que te devuelve `configurar`, no por dónde
creas que estás corriendo.

```bash
# Comparten disco (los scripts ven las rutas de Windows del MCP): directo.
DATOS="$TRABAJO"

# No lo comparten (los scripts corren en un contenedor): $DATOS es un directorio ESCRIBIBLE
# del contenedor, y ahi se copia lo que se sube. `/mnt/user-data/uploads` NO vale como
# $DATOS: es de solo lectura, y el skill escribe ahi facturas.json (y roles.json).
# Ademas, el staging cuelga los ficheros de una subcarpeta con el NOMBRE de la carpeta
# conectada, asi que la ruta subida NO es la que uno anticipa:
#   /mnt/user-data/uploads/<carpeta conectada>/_tmp_cowork/muestra.json
# Receta: exportar a _tmp_cowork en la carpeta conectada, subirla, y copiar de ahi a $DATOS.
DATOS="$HOME/trabajo"; mkdir -p "$DATOS"   # y se copia ahi lo subido
```
**El escenario habitual en Cowork**, para no volver a razonarlo cada sesión: el MCP corre en
el equipo del usuario y los scripts en el contenedor de la nube, así que **no comparten
disco**. Ahí la receta es fija: exportar dentro de la carpeta conectada del expediente, subir,
y trabajar con la copia del sandbox. Reutiliza siempre la **misma** carpeta temporal
(`_tmp_cowork`) en vez de crear una por ejecución: `limpiar_exportaciones()` borra los
ficheros pero no la carpeta, y quedan directorios vacíos por ahí.

### Paso 3 — Preparar y leer los documentos

Pide la carpeta con los documentos escaneados de la prueba (suele estar en
`Documentacion\<ejercicio>\<área>` del expediente, y a veces en una subcarpeta
`Facturas` dentro de ella; se busca en profundidad).

**Y pregunta cómo quiere las facturas, con las dos opciones y su consecuencia**, como una
pregunta con opciones y no como texto:

> *¿Cómo subo las facturas escaneadas para leerlas?*
> *Opciones: **(1) Tachadas** — el nombre del emisor, la cabecera, los identificadores (CIF,
> IBAN, teléfono, correo, web), el pie y los márgenes salen en negro en tu equipo antes de
> subir; el modelo lee importes, fechas y número, y en vez del nombre ve el mismo código que en
> la muestra. **(2) Tal cual** — la factura sube completa, con el nombre del emisor, y puedes
> pedirme que revise su contenido; el código del emisor va en una esquina.*
>
> *Con «tachadas», en algunos documentos el número o la fecha pueden quedar ilegibles —van
> pegados a la cabecera, o el escaneo es pobre—. Eso sale como aviso del contrato, no como
> incidencia de la prueba, y te lo diré distinguiéndolo.*

Es su decisión y hay que hacerla sabiendo lo que implica; no la tomes tú ni la des por hecha de
una sesión a otra. **Con el perfil puesto, en los dos casos las imágenes las hace el MCP** en el
equipo del auditor, y a la nube solo suben esas imágenes, nunca los PDF:

```
preparar_facturas(carpeta = "<la carpeta>",
                  destino = "<raíz de la carpeta conectada>\\_tmp_cowork\\facturas",
                  modo = "tachadas" | "claras",
                  terceros = [<los tokens de tercero de la muestra exportada, sin repetir>],
                  numeros = [<los números de documento de la muestra, sin repetir>])
```

`terceros` son los candidatos a emisor: pásalos siempre —salen de `muestra.json`—, porque sin
ellos el casado va contra el diccionario entero y es menos fiable. **`numeros` son los números de
documento de esa misma muestra** (la columna de documento): con ellos, el tachado **conserva ese
número dondequiera que esté** en la factura, en vez de intentar adivinar qué parece un número. No
expone nada —el auditor ya los tiene en libros— y es lo que evita que el número se vaya en negro
cuando comparte sitio con un identificador. Si la población no trae número, no pases nada. **La llamada es incremental y
se para sola a los 45 segundos** —unos 2 a 4 por documento—: si la respuesta trae `pendientes > 0`,
**vuelve a llamar con los mismos parámetros** hasta que sea 0; lo hecho no se rehace. La regla de
dedo para avisar al auditor con una cifra: **unos 8 a 10 documentos por llamada**, así que 24
documentos son tres llamadas y unos dos minutos. Va en dos fases
(`fase` en la respuesta): primero **lee** todo el lote y luego **tacha**; una llamada puede acabar en
`lectura` con `imagenes: 0` y no es un fallo, es que hace falta el lote entero para casar bien al emisor.
Si una factura no lleva el total en la primera página —las que paginan con «Suma y sigue»—, el MCP
**añade su última página él solo** y lo cuenta en `ultimas_paginas`: por eso a veces salen más
imágenes que documentos, y por eso `--ampliar` hace falta menos que antes. Y si
Cowork corta la llamada («did not respond within 60s»), no es un fallo: el MCP siguió trabajando
en el equipo, llama otra vez y verás lo hecho como `ya_hechos`. Con más de diez facturas, avisa al
auditor de que va a tardar. La respuesta trae recuentos: cuántos documentos, cuántos con token
estampado, cuántos ambiguos y sin casar (esos irán por importe, número y fecha: un sello equivocado
es peor que ninguno, y el MCP prefiere no estampar cuando duda), qué se ha tapado y cuántos
ficheros se han apartado como justificantes. Trasládale al auditor los recuentos en una línea,
sin nombres, que no los hay.

La respuesta trae **`ficheros`**, la lista de las imágenes generadas: úsala para subirlas, sin
listar la carpeta ni escribir las rutas a mano.

Deja en `destino` un JPEG por página a 100 ppp y un `manifiesto.json` que
`preparar_documentos.py` lee tal cual: **sube esa carpeta dentro del mismo `$DATOS` del paso 2**<!-- solo-cowork -->
(en Cowork, `device_stage_files` sobre `_tmp_cowork\facturas`; queda como `$DATOS/facturas/`)<!-- /solo-cowork -->.
**No es otro `$DATOS`**: `muestra.json`, `parametros.json` y `facturas/` conviven en el mismo
directorio, y el script encuentra el manifiesto en esa subcarpeta solo (con scripts anteriores
al 16/09/2026 había que copiarlo a la raíz a mano: ya no). Los pasos siguientes —`--lotes`,
`--fusionar`, `--estado`— son los mismos. **`--ampliar` no**: con
imágenes del MCP, la página que falte se pide otra vez al MCP con `documentos=["<fichero>"]`
y `paginas=[-1]`, y se vuelve a subir.

**Sin perfil** —o si `preparar_facturas` no existe porque el MCP es anterior a la 1.14.0—, el
script del skill renderiza él, en claro:

```bash
python "$SKILL/scripts/preparar_documentos.py" --carpeta "<la carpeta>" --trabajo "$DATOS"
```

Inventaría los PDF, aparta los justificantes de pago y **renderiza la primera página
de cada documento**, a 100 puntos por pulgada. No renderiza el resto a propósito: de una
factura interesan la primera página, que lleva la identidad, y la última, que suele llevar
los totales. Una página cuesta unos 1.290 tokens.

**Si el entorno tiene subagentes** (Claude Cowork y Claude Code los tienen; ChatGPT Cowork
no), **no leas tú las imágenes: reparte la lectura en lotes y lanza el agente lector**, que
es del plugin y se llama `lector-facturas`. El coste total de mirar las páginas es el mismo,
pero sale de tu contexto y los lotes van en paralelo: la MUM de 42 elementos pasó de diez
minutos leyendo en línea a leer cuatro lotes a la vez.

```bash
python "$SKILL/scripts/preparar_documentos.py" --trabajo "$DATOS" --lotes 10
```

Escribe `lotes.json` y te imprime cada lote con sus imágenes y la ruta donde ese lector
tiene que dejar su resultado (`facturas_lote_N.json`).

**Si el modo es «tachadas», `proveedor` y `cif` van vacíos.** Es una regla de la prueba, no
un encargo al lector: vale igual si delegas la lectura y si la haces tú. Aunque el nombre se lea
en la imagen —pasa con los documentos que no casaron con ningún tercero, y con los membretes que
el tachado no reconoció—, **no lo transcribas**: déjalo vacío y hazlo constar en `notas`. El
tercero ya va en el papel por su token en las columnas de la muestra, y esa columna se
desanonimiza al final; **la columna del documento no se desanonimiza nunca**, así que lo que
escribas ahí se queda escrito. En modo «tal cual» sí se transcriben, que para eso lo eligió el
auditor.

Al lector hay que **decírselo con esas palabras: «el lote va tachado»**, porque es lo único que
él no puede saber mirando las imágenes. Si lees tú, ya lo sabes: lo dice `modo` en la respuesta
de `preparar_facturas`. El 19/09/2026 se leyeron seis documentos en línea, en modo «tachadas», y
los cinco nombres legibles acabaron en el papel: la regla estaba escrita solo para el lector. **Los lotes son los que imprime el
script, no los partas tú**: con diez documentos o menos es un solo lote, y ese lote va igual a
**un** lector aunque sean seis —lo que gana no es velocidad, es sacar las imágenes de tu
contexto—; el paralelismo paga a partir de dos o tres lotes, y tres agentes para seis documentos
es más coordinación que lectura (observado el 15/09/2026). Lees tú solo si tu entorno no tiene
subagentes, y entonces con la regla de arriba delante. Lanza **un agente por lote, todos en
la misma tanda**, hasta cuatro a la vez; a cada uno le pasas en el prompt **el nombre de la entidad
auditada** (el de `contexto_expediente`), la lista de sus documentos con las imágenes y la
ruta de salida, y nada más: ni la muestra, ni los importes de libros. El nombre de la entidad
va para que el lector sepa qué lado del documento NO es el tercero: en una prueba de ventas
las facturas las emite la propia entidad y el tercero es el destinatario. Al lanzarlos, recuérdales que **el fichero del lote es JSON y nada más**: empieza en `{` y
acaba en `}`, sin vallas de código ni etiquetas detrás. Si aun así llega con texto alrededor,
`--fusionar` lo recorta y lo dice en una línea (`rescatados`), pero no siempre se puede.
Cada lector devuelve una línea de resumen; si uno devuelve el JSON entero en vez
de escribir el fichero, escríbelo tú en su ruta. Si uno falla, **un reintento** con el mismo
lote; si vuelve a fallar, lee tú ese lote en línea. Después:

```bash
python "$SKILL/scripts/preparar_documentos.py" --trabajo "$DATOS" --fusionar
```

junta los lotes en `facturas.json` y te dice si falta algún documento del inventario o si
algún lector se inventó uno. Con todo transcrito, sigue en el paso siguiente. **Solo si tu
entorno no tiene subagentes**, lee las imágenes tú, como sigue.

**Si la respuesta trae `aviso_sin_casar`, para y cuéntaselo al auditor antes de subir nada.**
El tachado tapa la cabecera y los identificadores siempre, y desde el MCP 1.20.0 tapa además
**cualquier razón social del plan de cuentas del encargo que el documento nombre**, no solo la
del emisor casado —eso cerró una página de anexo que soltaba nueve terceros de golpe—. Pero el
emisor de estos documentos **no se ha reconocido**, así que si su razón social tampoco está en
el plan de cuentas, sube a la vista. Y sigue sin cubrirse, en cualquier documento, el tercero
que no está en el plan de cuentas —un banco, un transportista— y el nombre que el OCR parte en
dos renglones. Pasa con lo que no es una factura —un pedido, un
certificado, un comprobante de pago— y con logotipos sin texto. El 18/09/2026 subieron así cuatro
documentos, uno con el DNI de una persona física en una página adjunta. Comprueba además que
`terceros` lleva los tokens de la **columna que el MCP ha tokenizado**: si el papel muestra tokens
distintos de los que pasaste, el tachado está casando contra la columna equivocada.

**Antes de dar por buena ninguna lectura, mira el aviso de páginas sin ver.** `preparar_facturas`
devuelve `paginas_sin_ver` —por id de documento— y el inventario lo imprime con `[A]`. Sólo se
renderiza la primera página de cada documento (y la última cuando la primera no sostiene un
total), y eso da por supuesto que lo de en medio es detalle. **En un escaneo de archivo es falso**:
en el mismo PDF conviven la factura, su albarán, la guía de transporte y a veces **otra factura**.
El 18/09/2026 el hallazgo que daba sentido a la prueba estaba en la página 2 de un PDF de 5 —otra
factura del mismo emisor, cuyo importe explicaba la diferencia— y la lectura por defecto concluyó
que no existía.

Regla dura: **importe que no casa con libros + documento con páginas sin ver ⇒ pide esas páginas
antes de declarar ninguna diferencia.** Se piden con
`preparar_facturas(..., documentos=["<fichero>"], paginas=[2,3])`.

**Antes de la primera imagen, mira `modo`.** Si es «tachadas», `proveedor` y `cif` se quedan
vacíos en todas las filas, se lea el nombre o no. Se repite aquí porque es aquí donde se
incumple: la regla de arriba se escribió para el lector y quien leía era el skill.

**Lee las imágenes que te ha dejado**, no los PDF. Si en la primera página no están los totales,
pide la que falte y no des ningún total por leído hasta verlo escrito como total. Son **dos**
casos distintos y los dos cuentan:

- la página lo anuncia —«SEGUE», «Suma y sigue», «continúa»— y el total está en la siguiente;
- **las casillas de totales están, pero vacías.** No es un escaneo malo ni un tachado: es una
  factura cuyos totales van en la página 2. Si ves las casillas y no ves cifra dentro, deja base
  y total vacíos y **pide la página siguiente** antes de concluir nada (medido el 18/09/2026:
  pasó y hubo que resolverlo mirando las imágenes a mano).

```bash
python "$SKILL/scripts/preparar_documentos.py" --trabajo "$DATOS" --ampliar "<fichero>"
```

De cada factura anota lo siguiente, y **escribe `<DATOS>/facturas.json` cada cinco o seis
documentos**, no al final:

```json
{"facturas": [
  {"fichero": "20260226142827850.pdf", "proveedor": "Inmobiliaria X, S.L.", "cif": "B00000000",
   "numero": "A-2025-118", "fecha": "13/03/2025", "concepto": "Arrendamiento local, marzo",
   "base": "12500,00", "pct_iva": "21",
   "iva": "2625,00", "irpf": "", "total": "15125,00", "paginas": 1, "notas": ""}
]}
```

`concepto` es de qué es la factura, en una línea y con las palabras del documento: no entra
en el cruce, solo describe la fila del papel.

**En una MUM la base y el total pesan igual**: el término de comparación se decide después,
así que hay que leer los dos siempre que estén. Si uno no se lee, déjalo vacío y dilo en
`notas`: nunca lo calcules aplicando un tipo de IVA, porque entonces el error que salga
será el de tu cálculo y no el del documento.

Si algo no se lee, **déjalo vacío**. Nunca lo completes por deducción ni lo copies de otra
factura del mismo proveedor.

Si el contexto se compacta a mitad, **no preguntes al usuario por dónde ibas**:

```bash
python "$SKILL/scripts/preparar_documentos.py" --trabajo "$DATOS" --estado
```

compara el inventario con lo ya transcrito y dice qué queda.

**Si un elemento sale «sin documento» y a la vez sobra un documento del mismo tercero**, casi
siempre no es un extravío: **es una diferencia real de importe**. El cruce se apoya en el
importe, que es justo lo que la prueba pone en duda, así que cuando no cuadra puede quedarse
sin atar. El script lo detecta y lo dice como «POSIBLE DIFERENCIA, no extravío» con las dos
cifras. No lo resuelvas reintentando: mira los dos, y si son el mismo documento, **átalo a
mano** añadiendo `poblacion_id` a esa entrada de `facturas.json` con el id del elemento:

```json
{"fichero": "2025000042 X.pdf", "poblacion_id": "301", "proveedor": "…", "base": "1234,56", "…": ""}
```

Con eso el documento se asigna a ese elemento sin pasar por la puntuación, y el papel hace
constar que el vínculo lo puso el auditor.

**El elemento puede ser UNA LÍNEA de un asiento partido.** ForSampling selecciona líneas; la
factura sostiene el asiento. Cuando el asiento reparte la base en varias líneas, la muestra coge
una y la factura no casa con ella. **No es raro**: medido en una población de compras el
17/09/2026, el 60 % de las filas vivía en un asiento de más de una línea.

No hay que hacer nada para que funcione: cuando el asiento del elemento está partido, la muestra
trae `LineasAsiento`, `ImporteAsiento` e `IdsAsiento` —los calcula el MCP sobre la propia
población, no sobre el diario— y el cruce prueba también esa suma. Lo que sí hay que saber al leer
el resultado:

| Lo que sale | Qué significa |
|---|---|
| Casa la suma del asiento | el gasto está entero, repartido en varias líneas: el elemento está **medido y su error es 0**, y la observación dice cuáles son las otras líneas |
| No casa ni la línea ni la suma | **no se propone importe ni error**, a propósito: proponer el del documento declararía un error igual a la otra línea del asiento, y ese error se proyectaría a toda la población. La observación dice dónde están las líneas y cuánto suman, para que el auditor investigue por qué no cuadran |

Si la población está acotada por cuenta y parte del gasto del asiento cae fuera, la suma se queda
corta y cae en el segundo caso. Es correcto, y la pista está en la observación.

**Cuando el reparto no se puede deducir** —un documento que cubre varios asientos, una entrega
parcial, un gasto que en parte cae fuera de la población—, añade `importe_aplicable` junto a
`poblacion_id` con la parte del documento que sostiene ese elemento:

```json
{"fichero": "…", "poblacion_id": "301", "importe_aplicable": "8400,00", "base": "10000,00", "…": ""}
```

No falsea la lectura —`base` y `total` siguen siendo los que pone la factura— y la observación hace
constar que va declarado a mano. Es la excepción: el caso corriente lo resuelve solo la suma.

**Y si la observación dice «ATENCIÓN: asignado solo por tercero y fecha, y había más de un
candidato»**, confírmalo antes de entregar: hay dos documentos del mismo tercero que encajan
igual de bien y el skill no puede saber cuál va con cuál. Se resuelve igual, con
`poblacion_id`.

**Cuatro trampas de la lectura**, todas medidas:

- **El número del ángulo superior derecho suele ser el sello de registro del cliente**, no
  el número del proveedor, que está en el cuerpo junto a «Factura nº».
- **El CIF que se pide es el del proveedor**, no el del cliente.
- **Hay tres formas legítimas de que el total no sea base + IVA**: exención o no sujeción
  (intracomunitaria, inversión del sujeto pasivo, art. 20 LIVA), retención de IRPF cuando
  el documento imprime el neto a pagar, y el redondeo. Transcribe la retención en `irpf`.
- **Las rectificativas llevan importes negativos**, que son correctos.

### Paso 4 — Verificar y generar el papel (puede abortar)

```bash
PAPEL="MUM <PRUEBA> <CLIENTE> <EJERCICIO>.xlsx"
# Si el nombre de la prueba ya empieza por «MUM», no lo repitas: «MUM Ventas 25», no
# «MUM MUM Ventas 25». Medido en el primer uso real.
python "$SKILL/scripts/ejecutar_mum.py" \
    --muestra "$DATOS/muestra.json" --parametros "$DATOS/parametros.json" \
    --facturas "$DATOS/facturas.json" --evaluacion "$DATOS/evaluacion.json" \
    --manifiesto "$DATOS/manifiesto.json" \
    # (si las imágenes las hizo el MCP, el manifiesto está en $DATOS/facturas/: el script lo encuentra igual)
    --salida "$TRABAJO/$PAPEL" --generado "<AAAA-MM-DD, la fecha que te dé el usuario>"
```

`--evaluacion` solo si existe. `--generado` es la fecha de generación, que se pasa porque
**nada lee el reloj**: el papel tiene que poder regenerarse idéntico.

`--manifiesto` es lo que convierte la celda del fichero en **hipervínculo al documento**,
con ruta absoluta. **Y si los scripts no ven la carpeta del auditor —porque corren en un
contenedor—, la ruta que ellos manejan no le sirve de nada**: pásale además
`--carpeta-documentos` con la carpeta de los escaneos tal como la ve él, la misma que te dio
en el paso 3, y el vínculo se rehace sobre ella. Donde los scripts y el auditor comparten
disco, no hace falta. Sin ninguno de los dos, la celda queda como texto y el script lo dice: es
mejor sin vínculo que con un vínculo que no abre nada.

Salida `2` → **para**: el contrato no se cumple —la población no tiene columna de importe,
la prueba no es MUM, la evaluación tiene forma de prueba de cumplimiento— y **no se ha
escrito nada**.

Salida `1` → el papel **sí está escrito**, pero hay avisos. **Léelos y cuéntalos al
entregar.** El script imprime una sección **«PARA CONTAR AL ENTREGAR (tal cual, sin resumir)»**:
esas líneas —A02, A07, A08, A09…— van al auditor **literales, todas**, no un resumen con tus
cifras. En la prueba en frío del 16/09 se trasladaron dos de cuatro y las otras dos (documentos
sin base imponible legible, documentos sin fecha legible) se perdieron por el camino.

Imprime, además, el término con el que compara esta población, los elementos con diferencia
y, si había evaluación, el recuento frente al auditor. **Lee esa salida antes de entregar.**

En un entorno donde los scripts no comparten disco con el expediente, el papel se escribe
en el sandbox y se envía; donde sí lo comparten, pásale a `--salida` la ruta del expediente
directamente y el script crea el árbol. Si el expediente está en OneDrive, el entorno puede
pedir autorización antes de escribir: pídesela al usuario y repite.

### Paso 5 — Entregar

Di dónde ha quedado el fichero y, **antes que nada**:

1. **El término de comparación** que ha usado la muestra (base, total o neto). Todo lo
   demás depende de eso.
2. **Los elementos con diferencia**, uno por uno y con sus cifras.
3. Los errores **por exceso y por defecto, por separado**, tal como los imprime el script.
   Nunca sumados entre sí.
4. Cuántos elementos quedaron sin documento o sin medir, y qué documentos de la carpeta no
   son de ningún elemento.

Si había evaluación del auditor, traslada las cifras de la comparación. La que importa es
**«el skill da 0 y el auditor puso error»**: incorrecciones que se habrían dejado pasar.

**Los nombres.** El papel se ha escrito con tokens en las columnas de la muestra (la columna del
documento leído, `Proveedores`, lleva lo que decía la factura). Cuando ya esté en el disco del
auditor<!-- solo-cowork --> —en Cowork, después de bajarlo al expediente con
`device_commit_files`; en local, directamente—<!-- /solo-cowork -->, llama a `rehidratar(ruta = "<expediente>/AsistenteIA/FspMum/<fichero>",
leyenda = true)`: sustituye cada token por el nombre real, en local, y devuelve recuentos —ni un
nombre vuelve aquí—. Con `leyenda = true` añade la hoja «Tokens» con la equivalencia, para que
lo que has dicho en el chat con tokens se pueda leer en el papel. **Cuéntale al auditor los dos
números que devuelve** (sustituciones y tokens distintos) y, si hay `tokens_sin_nombre`, dilos tal
cual: no los completes tú. Los tokens de reserva `TER h…` rehidratan igual: su nombre es el texto
del apunte, que el diccionario guardó al tokenizar.

Sin llamar «rehidratar» a nada delante del auditor —para él es **desanonimizar**—:

> *Papel generado y archivado en el expediente: `AsistenteIA\FspMum\<fichero>`<!-- solo-cowork --> (también lo
> tienes en el chat, aunque esa copia está anonimizada)<!-- /solo-cowork -->. Nombres ya desanonimizados: N
> sustituciones, M terceros distintos, ninguno sin nombre, y hoja «Tokens» con la leyenda. Los
> temporales están borrados.*

<!-- solo-cowork:papel-unico -->La copia del chat **siempre** está anonimizada —viajó por el contenedor—: dilo, para que no la
confunda con el papel bueno.<!-- /solo-cowork --> **El diccionario de nombres no se borra**: vive con el encargo,
cifrado, y es lo que permite rehidratar un papel de hace días.

**Lo que no digas**: el error proyectado, el error neto, si se supera el error tolerable, o
si la prueba pasa. Nada de eso sale de este papel.

**Los temporales.** `parametros.json` lo escribiste tú desde la respuesta de `obtener_entidad`, así que `limpiar_exportaciones()` **no lo borra**: bórralo aparte, y en una carpeta conectada puede pedir permiso de borrado. `limpiar_exportaciones()` borra la muestra y la evaluación exportadas y, desde el MCP 1.14.3, **también las imágenes y el `manifiesto.json` que `preparar_facturas` dejó en `_tmp_cowork\facturas`** (con un MCP anterior quedan ahí: dilo al auditor con la ruta<!-- solo-cowork:alt=, y en este canal bórralas tú, que compartes disco con el auditor) -->, que en Cowork no tienes shell en su equipo)<!-- /solo-cowork -->.
`facturas.json`<!-- solo-cowork --> y las copias del sandbox<!-- /solo-cowork --> los escribiste
tú: bórralos con el directorio de trabajo. Los PDF no se copian a ningún sitio.

**No te fíes del recuento.** Desde el MCP 1.17.0 la respuesta puede traer `revisa_estos_ficheros`
y un `aviso`: son ficheros que quedan en las carpetas donde el MCP ha exportado y que la
herramienta **no** ha escrito, así que no los borra. Si alguno es una exportación de esta sesión
—una muestra, una evaluación— lleva contabilidad del cliente, y esas carpetas suelen estar
sincronizadas con la nube. **Enséñale la lista al auditor con la ruta y pídele que los borre**;
no la escondas porque el recuento diga que se han borrado muchos. El 18/09/2026 la herramienta
dijo «45 borrados» y quedaron dos exportaciones con datos del cliente dentro de OneDrive.

---

## Cómo se lee el papel

**Una sola hoja, «Análisis muestra».** Una fila por elemento seleccionado: sus columnas de
población tal como vienen —incluidas `Repeticiones`, que es cuántas unidades de muestreo
representa—, el documento localizado y lo leído en él, las tres columnas de la MUM —**VRL
(muestra)**, **Valor Auditoría (doc)** y **Error**, más el % —, con qué término se
comparó, la **observación propuesta** lista para copiar a ForSampling y, al final, por
qué clave casó el documento.

Las columnas van en **cuatro zonas de color**, cada una con su banda de título: A los
datos de la muestra tal como los guarda ForSampling, B lo leído en el documento, C la
prueba de muestreo y D la evidencia del cruce. El **Error y el % son fórmulas**: al
cambiar el valor según auditoría se recalculan solos.

Las tres columnas **sí** se rellenan, al contrario que los atributos de la prueba de
cumplimiento, y la diferencia no es un descuido: un atributo es un veredicto, y rellenarlo
es concluir; un importe leído en un documento es una medida, y decirlo es describir.

Un solo color, **amarillo en la observación** cuando hay diferencia o cuando el elemento no
se ha podido medir. Arriba, la hoja se identifica: prueba, área, referencia, ejercicio,
unidad de muestreo, tamaño de la población, error tolerable y fecha de generación.

**No hay fila de totales, a propósito.** Sumar los errores de una MUM es proyectar a ojo.

## Degradación

| Situación | Qué sale |
|---|---|
| Sin `.cli` vinculado ni indicado | **para** en el paso 1 |
| La prueba no es MUM | **para** (C04): las de cumplimiento van por `fsp-cumplimiento` |
| La población no tiene columna de importe | **para** (C02): en una MUM el importe es lo que se mide |
| La evaluación tiene forma de prueba de cumplimiento (A1..An) | **para** (C06): se ha exportado la prueba equivocada |
| La población no trae fecha o número de documento | sigue: el cruce va por importe y tercero, y el papel lo dice (A01, A02) |
| La muestra mezcla importes positivos y negativos | sigue, y avisa (A04): el error sigue el signo del saldo |
| Un documento sin base ni total legibles | sigue: ese elemento queda sin medir, y se dice (A07) |
| La muestra no fija un término de comparación claro | sigue: los elementos que no casan quedan sin importe propuesto, con el motivo |
| Una columna de tercero que vale lo mismo en todas las filas | el skill cambia de columna solo, y lo avisa (A00). Fue el fallo de la MUM de ventas: «Nombre» valía «Ventas» en las 42 filas |
| Dos documentos del mismo tercero encajan igual en un elemento | sigue: se asigna el de fecha más cercana, y si empatan también en fecha se marca la observación como dudosa |
| Los documentos sobrantes son justo los ficheros de la carpeta SIN prefijo numérico | sigue: la carpeta tiene más documentos de los que pide la muestra. No es extravío ni diferencia |
| Un elemento cuyo asiento está partido y cuya suma no casa con el documento | sigue: queda **sin propuesta** y la observación lleva a las líneas del asiento |
| Un elemento sin documento y un documento sobrante del mismo tercero | sigue, y el script lo señala como POSIBLE DIFERENCIA con las cifras: se ata con `poblacion_id` |
| Sin PyMuPDF ni `pdftoppm` | `preparar_documentos.py` **para** y lo dice; camino alterno, abrir los PDF directamente |
| Sin evaluación del auditor | sigue: no hay comparación que imprimir |
| Fichero activo `.cli` y el auditor no sabe dónde está el diario | sigue: la muestra sale con tokens de reserva `TER h…`, el cruce va sin tercero, y el papel lo dice |
| Una factura tachada sin token (el emisor no casó con ningún tercero: logo sin texto, nombre distinto al del diario) | sigue: ese documento se cruza por importe, número y fecha, y si queda «sin documento» se ata con `poblacion_id` |
| El MCP no tiene `preparar_facturas` (anterior a la 1.14.0) | sigue en claro con `preparar_documentos.py --carpeta`, y se dice que las facturas no van tachadas |
| El `.smn` indicado no es el de la población (sus asientos no existen en él) | **para** en el paso 2 con «ese diario no es el de esta población»: se pide una vez, no se busca otro |
| Población ajustada: los asientos existen pero los importes no coinciden con el diario | sigue: el MCP toma la contrapartida del asiento y lo dice como `POBLACIÓN AJUSTADA`; no es otro diario |
| `preparar_facturas` devuelve `pendientes > 0`, o Cowork corta la llamada a los 60 s | sigue: se vuelve a llamar con los mismos parámetros; lo hecho no se rehace |
| `rehidratar` devuelve `tokens_sin_nombre` | sigue: el papel se entrega con esos tokens tal cual y se dicen al auditor; no se completan a mano |
| Fichero de salida abierto en Excel | **para** al guardar, y dice que hay que cerrarlo |

## Comprobar que el skill funciona

```bash
python "$SKILL/scripts/probar_mum.py"
```

No hace falta ForSampling ni un solo PDF: 60 comprobaciones sobre un fixture sintético de
ocho elementos elegidos por lo que puede salir mal en una MUM —gasto por la base, diferencia
real con su tasa, sin documento, contabilizado por el total, ingreso con saldo negativo,
ingreso negativo con diferencia, documento sin total legible cuya diferencia es justo la
cuota de IVA, y un elemento sin importe—. Comprueba además que el término de comparación sale
de la muestra, que **los errores no se netean nunca**, que se detecta el caso en que el skill
da 0 donde el auditor puso error, que **un tercero tokenizado apaga el criterio de tercero
sin casar nada por casualidad** y el cruce sigue atando por importe, y que `lib_fsp.py` es byte
a byte el mismo fichero que en `fsp-cumplimiento`.
