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
_Versión del skill: 21/10/2026 · plugin interno 1.53.0 · pide MCP ≥ 1.26.0._


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
redactó. Y el papel deja constancia de qué se facilitó a la herramienta y cómo en su hoja
«Uso de IA».

---

## Lo que mide, y lo que no hace por ti

Tres columnas por elemento, con los nombres que usa ForSampling:

| Columna | Qué es |
|---|---|
| `SaldoAuditoria` | lo que el documento sostiene para ese apunte |
| `ErrorAuditoria` | `|Saldo| − |SaldoAuditoria|`, en valor absoluto como lo guarda ForSampling. Positivo: los libros dicen de más, también en una población de saldo acreedor (ventas): −5.403,96 en libros con factura de 5.200 es +203,96 |
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
- **No verifica su propio resultado por el equipo.** Propone qué contrastar; la verificación,
  quién la hace y su efecto en la conclusión los escribe el equipo en la hoja «Uso de IA».

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
TRABAJO="$(mktemp -d "${TMPDIR:-/tmp}/fsp-mum-XXXX")" && echo "$TRABAJO"
```

**Un directorio de trabajo nuevo por ejecución, y sin entrar en él.** Nada de `cd "$TRABAJO"`:
todas las órdenes llevan la ruta entera (`"$TRABAJO/…"`), y así al final se borra desde fuera.
Reutilizar el de otra ejecución mezcla lo de las dos: `--fusionar` junta todos los
`facturas_lote_*.json` que encuentre y `--estado` da por transcritos documentos de otra prueba.
**Anota la ruta que imprime**: si el entorno no conserva variables entre llamadas, vuelve a
escribir `TRABAJO="<esa ruta>"` al principio de cada orden —y lo mismo `SKILL`, `DATOS` y
`PAPEL`—, sin crear otro. Esa ruta anotada es también la que se borra al final, escrita literal
(paso 5).

Son cuatro: `preparar_documentos.py` (inventaría y renderiza las páginas que hacen falta,
y lleva la cuenta de lo transcrito), `verificar_contrato.py`, `generar_papel.py` y
`ejecutar_mum.py`, que encadena los dos últimos. Más `probar_mum.py`, el arnés.

---

## Secuencia

### Paso 1 — Expediente, cliente de muestreo y prueba

```
configurar(perfil = "fsp-mum")   # primero: el tercero de la muestra, seudonimizado
contexto_expediente()            # SIEMPRE, aunque ya lo tengas de antes
```

**`contexto_expediente()` va siempre justo después de `configurar(perfil = …)`**, si el fichero
activo es un `.gs3` (con un `.cli` suelto no hay expediente que resumir), **aunque ya lo tengas
en la conversación**. Lo leído antes, con otro perfil o con ninguno, no consta como facilitado a
este papel —la hoja «Uso de IA» lista lo que el MCP ha servido desde que se puso este perfil— y
el nombre de la entidad que necesitan los lectores en el paso 3 tiene que salir de aquí.

**Si `configurar` avisa de que otra conversación está trabajando en el mismo servidor** con otro
expediente o con otro perfil (`aviso_otra_conversacion`), **díselo al auditor tal cual y no sigas
hasta que confirme que la otra ha terminado**. Las conversaciones comparten el MCP —expediente
activo, perfil, lista de lo facilitado y ficheros de trabajo—: lo que una configure, exporte o
limpie le puede tocar a la otra (el 20/10/2026 la limpieza de una borró la muestra y las facturas
de una prueba en curso en otra).

Si la primera llamada al MCP falla con **«Connection closed»**, **«Server … unavailable»** o
**«did not respond within 60s»**, **reintenta hasta tres veces, esperando entre intentos**: el
conector tarda unos segundos en arrancar y la primera petición puede llegar antes. Reintentar
seguido no basta —medido el 18/09/2026: los tres intentos fallaron y lo que funcionó fue esperar
alrededor de un minuto—. Si después sigue igual, pídele que reinicie Claude del todo.

**Y en cuanto vuelva, antes de cualquier otra cosa, repite `configurar()` con el expediente Y el
perfil.** Un reinicio del servidor borra el estado, y el MCP vuelve sin expediente y **sin
perfil**: si sigues sin reconfigurar, la muestra sale con **los nombres de los terceros en claro**.
El MCP lo avisa en la propia respuesta cuando detecta que hay columnas de nombre sin seudonimizar
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

El perfil marca también **el comienzo del procedimiento**: desde ahí el MCP lleva la cuenta de
lo que facilita a la herramienta, que es lo que el papel dirá en su hoja «Uso de IA».

**Las facturas escaneadas las decide el auditor, en el paso 3**: tachadas en su equipo antes
de subir, o tal cual. Con el perfil puesto, las prepara el MCP en cualquiera de los dos casos y
en las dos va estampado el token del emisor, así que el cruce conserva el tercero. Si el auditor
prefiere que la muestra viaje con los nombres en claro, el interruptor es suyo:
`configurar(nombres = "claro")`.

**El diario: no lo pidas antes de saber si hace falta.** El MCP necesita la contrapartida de
cada elemento para seudonimizar al tercero, pero **muchas poblaciones ya la traen** en una columna
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

Sin propuesta, la frase: *«Necesito la contrapartida de cada elemento para seudonimizar al
tercero; la saco del diario si me indicas dónde está el .smn del ejercicio completo»*. Si el
diario solo existe fuera de ForSampling —también en Excel—, puede importarlo en ForSampling,
que lo guarda como `.smn` en esa carpeta.

**Para identificar el diario no instales nada** —ni `access-parser` ni otro lector de Access, ni
`pip install` de ningún tipo—: el diario lo mide el MCP en el equipo del auditor, y en el
contenedor no hay nada que abrir. El 28/10/2026 una sesión instaló un lector en la máquina
virtual para mirar un `.smn` y lo dejó instalado. Si la propuesta del MCP no basta, pregunta al
auditor.

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
exportar_consulta(entidad = "parametros", id = <MuestraId>, ruta = "<DATOS>/parametros.json")
```

**`parametros.json` se exporta, no se escribe a mano**: `exportar_consulta(entidad =
"parametros")` (MCP ≥ 1.26.0) deja en el fichero lo mismo que devuelve
`obtener_entidad('parametros', id = …)`, y viaja con la muestra y la evaluación. Reescribirlo tú
desde la respuesta es copiar a mano un JSON que el script valida, y lo borra
`limpiar_exportaciones` con lo demás. Si el MCP es anterior y no admite `parametros`, entonces
sí: guarda tal cual la respuesta de `obtener_entidad` en `<DATOS>/parametros.json`.

Y **la evaluación del auditor, siempre: inténtalo aunque creas que no la hay**:

```
exportar_consulta(entidad = "evaluacion", id = <MuestraId>, ruta = "<DATOS>/evaluacion.json")
```

Con ella, al ejecutar se imprime la comparación elemento a elemento: su importe frente al
propuesto. Es la calibración del skill sobre ese encargo, y donde se ve si se dejaría pasar
una incorrección. **No te la saltes suponiendo que el auditor no ha evaluado**: una sesión lo dio
por hecho y se perdió la única comparación que calibra el skill. Si la respuesta dice que todavía
no hay tabla de evaluación (`_AN`) o trae cero filas, **díselo al auditor en una línea** —«la
prueba no tiene evaluación del auditor: no hay comparación con lo que él puso»— y sigue sin
`--evaluacion`.

`parametros.json` trae, además del tipo de prueba, el contexto que va al encabezado del
papel: unidad de muestreo, número de elementos de la población, **error tolerable** y
tamaño de muestra deseado. No lo recortes ni lo retoques.

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
#   /mnt/user-data/uploads/<carpeta conectada>/_tmp_cowork/fsp-mum/muestra.json
# Receta: exportar a _tmp_cowork\fsp-mum en la carpeta conectada, subirla, y copiar de ahi a $DATOS.
DATOS="$TRABAJO/datos"; mkdir -p "$DATOS"   # dentro del de ESTA ejecución; ahi se copia lo subido
```
Si `device_stage_files` falla por permisos, pide acceso con `device_request_folder_access` sobre
la **raíz de la carpeta conectada** y repite la subida **una sola vez**; si vuelve a fallar, para
y díselo al auditor.
**El escenario habitual en Cowork**, para no volver a razonarlo cada sesión: el MCP corre en
el equipo del usuario y los scripts en el contenedor de la nube, así que **no comparten
disco**. Ahí la receta es fija: exportar dentro de la carpeta conectada del expediente, subir,
y trabajar con la copia del sandbox. Exporta siempre a **`_tmp_cowork\fsp-mum`**, la carpeta de este procedimiento, y no a
`_tmp_cowork` a secas: fsp-mum y fsp-cumplimiento exportan los mismos nombres —`muestra.json`,
`parametros.json`, `evaluacion.json`— y el 28/10/2026, con los dos a la vez, uno pisó los
ficheros del otro y la limpieza dejó `_tmp_cowork` con datos del cliente. No crees una por
ejecución: `limpiar_exportaciones` borra los ficheros y las carpetas que quedan vacías dentro.

### Paso 3 — Preparar y leer los documentos

Pide la carpeta con los documentos escaneados de la prueba (suele estar en
`Documentacion\<ejercicio>\<área>` del expediente, y a veces en una subcarpeta
`Facturas` dentro de ella; se busca en profundidad).

**La carpeta se inspecciona por recuentos y por el número de elemento, nunca listando
nombres.** En un despacho los ficheros se llaman «12 RAZÓN SOCIAL SL.pdf»: un `ls`, un `find` o un
`dir` de exploración saca las razones sociales al chat, y pasó así el 21/10/2026, aunque las
facturas fueran tachadas y la muestra seudonimizada. Si necesitas saber qué hay, cuéntalo
(cuántos ficheros, cuántos con prefijo numérico, de qué extensiones) o deja que lo diga
`preparar_facturas`. Desde el MCP 1.26.0 **cada documento sale del equipo con un alias**
—`«12 - DOC 3fa2-f07.pdf»`: el número de elemento, que es lo que cruza con la muestra, y un
código por documento (`f07`; `a01` los apartados, `x01` lo que no es documento)—, y el nombre
real y la ruta se quedan en el equipo del auditor. **Ese alias es el nombre del documento en todo
el flujo**: en el manifiesto, en los lotes, en `facturas.json`, en el chat y en el papel, hasta
que al archivar se recuperan los nombres (paso 5).

**Antes de preparar las facturas, mira en el resumen de la exportación cuántos elementos llevan
token de reserva** (`TER h…` en `muestra_tokenizada`): son apuntes sin contrapartida de tercero
—comisiones y servicios bancarios de las 626 y 629, cargos domiciliados—, y su documento casi
seguro es **de un emisor que no está en el plan de cuentas como tercero, típicamente un banco**.
Ese documento no casará con ningún token, el tachado no reconocerá al emisor, y **su nombre
subirá a la vista** aunque elija «tachadas». Díselo al auditor con la cuenta antes de la pregunta
de abajo —«N elementos llevan token de reserva: sus documentos, probablemente cargos de un banco,
subirán con el nombre del emisor visible»—, para que decida sabiéndolo; si prefiere, puede
excluirlos (`excluir`, más abajo) y documentarlos a mano.

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
                  destino = "<raíz de la carpeta conectada>\\_tmp_cowork\\fsp-mum\\facturas",
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
sin nombres, que no los hay. **Los recuentos de una llamada con `pendientes > 0` son
provisionales**: los da por buenos solo la última, la de `pendientes: 0`.

**Si la respuesta trae `numeros_no_encontrados`** —números de la muestra que pasaste en
`numeros` y que no aparecen en ningún documento del lote—, dilo al auditor con la cuenta: es la
pista de un documento que falta en la carpeta o de un número que el tachado o el escaneo no deja
leer.

**Si el auditor dice que un documento no es de la prueba** —va en la carpeta pero no lo quiere
leído ni en el papel—, sácalo en su equipo: `preparar_facturas(..., excluir = ["<alias o id>"])`.
Lo quita del manifiesto, borra sus imágenes y se recuerda en las llamadas siguientes sobre esa
carpeta. **No filtres el manifiesto a mano en el contenedor**: el 21/10/2026 se hizo así con dos
documentos que el auditor había excluido, y esa copia deja de ser la del equipo: la siguiente
llamada a `preparar_facturas` rehace el manifiesto y los vuelve a traer.

La respuesta trae **`ficheros`**, la lista de las imágenes generadas: úsala para subirlas, sin
listar la carpeta ni escribir las rutas a mano.

**Si la carpeta trae solo imágenes** —JPG, JFIF, PNG, TIF o BMP, escaneos sueltos o fotos—, no es
un error: `preparar_facturas` las acepta igual que los PDF, **una página por imagen y con el mismo
tachado**. No montes un manifiesto a mano ni subas las imágenes originales: eso se salta el
tachado. Si el MCP es anterior a la 1.25.1 y responde «no hay ningún PDF», para y díselo al
auditor (que actualice el plugin, o que pase las imágenes a PDF); con «tal cual» puede servir
`preparar_documentos.py --carpeta`, que también las acepta, pero **nunca con «tachadas»**, porque
el script no tacha.

**Lo apartado por el nombre se dice siempre.** `preparar_facturas` deja fuera, y lista en
`apartados`, los ficheros cuyo nombre dice justificante, remesa, recibo, transferencia, albarán
o «todos»/«todas» (el recopilatorio que junta las facturas), **también cuando no van numerados**
con el elemento («JUSTIFICANTE REMESA 03.pdf», «ALBARAN 1234.jpg», «FACTURAS TODOS.pdf»). Solo se
queda dentro el marcado que es el único fichero de su elemento numerado («6 - X FRA F25-002 +
JUSTIFICANTE PAGO.pdf»), porque es la factura con el justificante detrás. Los apartados no se leen
ni suben, y vienen **por su alias**, con la palabra que los marcó —«6 - JUSTIFICANTE DOC 3fa2-a01.pdf»,
«TODOS DOC 3fa2-a02.pdf»—: **dile al auditor cuántos y cuáles por su número de elemento y esa
palabra**, que él los reconoce en su carpeta. Si alguno SÍ es el documento de un elemento, se
recupera pidiéndolo por su alias o su id —`preparar_facturas(..., documentos = ["<alias o id>"])`,
o `--incluir "<alias o id>"` con `preparar_documentos.py --carpeta`, que admite también el nombre
que te diga el auditor—. Un albarán no es una factura y no sostiene un importe
según auditoría: no se transcribe a `facturas.json`.

Deja en `destino` un JPEG por página a 100 ppp y un `manifiesto.json` que
`preparar_documentos.py` lee tal cual: **sube esa carpeta dentro del mismo `$DATOS` del paso 2**<!-- solo-cowork -->
(en Cowork, `device_stage_files` sobre `_tmp_cowork\fsp-mum\facturas`; queda como `$DATOS/facturas/`. Si
falla por permisos, `device_request_folder_access` sobre la raíz de la carpeta conectada y se
repite **una vez**; si vuelve a fallar, para y díselo al auditor)<!-- /solo-cowork -->.
**No es otro `$DATOS`**: `muestra.json`, `parametros.json` y `facturas/` conviven en el mismo
directorio, y el script encuentra el manifiesto en esa subcarpeta solo (con scripts anteriores
al 16/09/2026 había que copiarlo a la raíz a mano: ya no). Los pasos siguientes —`--lotes`,
`--fusionar`, `--estado`— son los mismos. **`--ampliar` no**: con
imágenes del MCP, la página que falte se pide otra vez al MCP con `documentos=["<alias o id>"]`
y `paginas=[-1]`, y se vuelve a subir.

**Sin perfil** —o si `preparar_facturas` no existe porque el MCP es anterior a la 1.14.0—, el
script del skill renderiza él, en claro:

```bash
python "$SKILL/scripts/preparar_documentos.py" --carpeta "<la carpeta>" --trabajo "$DATOS"
```

Inventaría los PDF y las imágenes sueltas, aparta con la misma regla que el MCP los
justificantes y albaranes (y los recupera con `--incluir "<alias o id>"`) y **renderiza la
primera página de cada documento**, a 100 puntos por pulgada; una imagen suelta es su única
página. Aquí los nombres son los reales, así que **el script hace lo mismo que el MCP**: todo lo
que imprime y lo que pasa a los lectores va por alias, id y número de elemento, y el nombre real
se queda en su `manifiesto.json` —no lo leas ni lo imprimas— para el vínculo del papel, que lo
recupera al escribirse. No renderiza el resto a propósito: de una
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
tiene que dejar su resultado (`facturas_lote_N.json`). Cada documento del lote va por su
**alias** (`fichero`), su id y su número de elemento, nunca por el nombre real: pásaselo así al
lector, que devuelve el `fichero` tal cual se lo das.

**Si el modo es «tachadas», `proveedor` y `cif` van vacíos.** Es una regla de la prueba, no
un encargo al lector: vale igual si delegas la lectura y si la haces tú. Aunque el nombre se lea
en la imagen —pasa con los documentos que no casaron con ningún tercero, y con los membretes que
el tachado no reconoció—, **no lo transcribas**: déjalo vacío y hazlo constar en `notas`. El
tercero ya va en el papel por su token en las columnas de la muestra, y en esa columna se
recuperan los nombres al final; **en la columna del documento no se recuperan nunca**, así que
lo que escribas ahí se queda escrito. En modo «tal cual» sí se transcriben, que para eso lo eligió el
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
Sale solo en la llamada que acaba el lote (`pendientes: 0`), con la cuenta definitiva: no lo
busques en las intermedias. El tachado tapa la cabecera y los identificadores siempre, y desde el MCP 1.20.0 tapa además
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
`preparar_facturas(..., documentos=["<alias o id>"], paginas=[2,3])`.

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
python "$SKILL/scripts/preparar_documentos.py" --trabajo "$DATOS" --ampliar "<alias o id>"
```

De cada factura anota lo siguiente, y **escribe `<DATOS>/facturas.json` cada cinco o seis
documentos**, no al final:

```json
{"facturas": [
  {"fichero": "DOC 3fa2-f03.pdf", "proveedor": "Inmobiliaria X, S.L.", "cif": "B00000000",
   "numero": "A-2025-118", "fecha": "13/03/2025", "concepto": "Arrendamiento local, marzo",
   "base": "12500,00", "pct_iva": "21",
   "iva": "2625,00", "irpf": "", "total": "15125,00", "paginas": 1, "notas": ""}
]}
```

`fichero` **tal cual lo imprime `--estado` o el lote: el alias**, nunca el nombre real del
fichero —esa columna va al papel y al chat—. `concepto` es de qué es la factura, en una línea y
con las palabras del documento: no entra en el cruce, solo describe la fila del papel.

**En una MUM la base y el total pesan igual**: el término de comparación se decide después,
así que hay que leer los dos siempre que estén. Si uno no se lee, déjalo vacío y dilo en
`notas`: nunca lo calcules aplicando un tipo de IVA, porque entonces el error que salga
será el de tu cálculo y no el del documento.

**La base es el importe sin IVA, se rotule como se rotule** (decidido con el auditor el
21/10/2026). Si la factura no dice «base imponible» pero imprime el importe sin IVA («Importe»,
«Neto», «Subtotal»), ese es `base`. Si lo trae por líneas —«Importe s. IVA» en cada una— y no hay
un total de base impreso, `base` es **la suma de esas líneas impresas**, y lo dices en `notas`
(«base = suma de N líneas»). Lo que sigue prohibido es deducirla aplicando un tipo de IVA al
total. Y un **cargo bancario o una liquidación sin IVA** que imprime el importe del cargo: ese
importe va en `total`, con una nota («cargo bancario, sin IVA»).

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
{"fichero": "DOC 3fa2-f12.pdf", "poblacion_id": "301", "proveedor": "…", "base": "1234,56", "…": ""}
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

**Y si dice «ATENCIÓN, asignación dudosa»**, el elemento queda **sin medir**: sin valor según
auditoría, sin error y sin tasa. Al elemento le ha caído un documento que solo sostienen el
tercero y la fecha, sin número que lo ate, y que además **se aparta más de la mitad del importe de
libros, o tiene la fecha más lejos que cualquier documento atado por importe o número en esta
muestra** (nunca menos de 22 días). Lo más probable es que sea otro documento del mismo tercero y
que el del elemento no esté en la carpeta; proponer su importe declararía un error ajeno, y ese
error se proyectaría a toda la población. Se cuenta aparte —en la cabecera de la hoja, en la
salida y en la hoja «Uso de IA»—, igual que el «sin criterio de comparación». **No lo presentes
como diferencia**: dilo aparte y pregunta. Si el auditor confirma que es ese documento, átalo con
`poblacion_id` y vuelve a ejecutar: entonces se mide.

**Cuatro trampas de la lectura**, todas medidas:

- **El número del ángulo superior derecho suele ser el sello de registro del cliente**, no
  el número del proveedor, que está en el cuerpo junto a «Factura nº».
- **El CIF que se pide es el del proveedor**, no el del cliente.
- **Hay tres formas legítimas de que el total no sea base + IVA**: exención o no sujeción
  (intracomunitaria, inversión del sujeto pasivo, art. 20 LIVA), retención de IRPF cuando
  el documento imprime el neto a pagar, y el redondeo. Transcribe la retención en `irpf`.
- **Las rectificativas llevan importes negativos**, que son correctos.

### Paso 4 — Verificar y generar el papel (puede abortar)

**Si el papel ya existe, pregunta antes de generarlo.** Mira si en
`<expediente>\AsistenteIA\FspMum\` ya hay un fichero con ese nombre<!-- solo-cowork:alt=. --> —en
Cowork, listando la carpeta conectada con `device_list_dir`; en local, en el disco—.<!-- /solo-cowork -->
Si lo hay, **pregunta al auditor** si lo sobrescribe o si guarda el nuevo con « (rehecho
AAAA-MM-DD)» antes de la extensión, con la fecha de hoy. Ni lo sobrescribas sin preguntar ni
inventes otro sufijo: al repetir un procedimiento el mismo día, una ejecución pisó el papel y otra
improvisó el nombre (registro del 21/10/2026). El nombre elegido es el de todo lo que sigue
—<!-- solo-cowork -->la bajada al expediente, <!-- /solo-cowork -->el sello y la recuperación de nombres—.<!-- solo-cowork --> En
Cowork, `device_commit_files` va **sin `force`**; solo si el auditor eligió sobrescribir y el
commit lo rechaza porque el fichero existe, repítelo con `force` y díselo.<!-- /solo-cowork -->

```bash
PAPEL="MUM <PRUEBA> <CLIENTE> <EJERCICIO>.xlsx"
# Si el nombre de la prueba ya empieza por «MUM», no lo repitas: «MUM Ventas 25», no
# «MUM MUM Ventas 25». Medido en el primer uso real.
python "$SKILL/scripts/ejecutar_mum.py" \
    --muestra "$DATOS/muestra.json" --parametros "$DATOS/parametros.json" \
    --facturas "$DATOS/facturas.json" --evaluacion "$DATOS/evaluacion.json" \
    --manifiesto "$DATOS/manifiesto.json" \
    --carpeta-documentos "<la carpeta de los documentos, la misma que pasaste a preparar_facturas>" \
    --salida "$TRABAJO/$PAPEL" --generado "<AAAA-MM-DD, la fecha que te dé el usuario>"
# si las imágenes las hizo el MCP, el manifiesto está en $DATOS/facturas/: el script lo encuentra igual
```

`--evaluacion` solo si existe. `--generado` es la fecha de generación, que se pasa porque
**nada lee el reloj**: el papel tiene que poder regenerarse idéntico. `--manifiesto` pásalo
siempre que lo haya: además del vínculo, es lo que deja dicho en la hoja «Uso de IA» si las
imágenes las preparó el MCP o el script del skill.

**El libro empieza por la hoja «Uso de IA»**: la evidencia de que el papel se hizo con una
herramienta de inteligencia artificial, de qué se le facilitó y de cómo debe verificarse. Los
apartados de la herramienta quedan con huecos que se rellenan al archivar (paso 5); los de
verificación, verificado por, efecto en la conclusión y revisión **son del equipo y salen en
blanco**. No escribas nada en ellos ni propongas texto para ellos.

`--manifiesto` es lo que convierte la celda del fichero en **hipervínculo al documento**,
con ruta absoluta. Con el manifiesto del MCP la celda lleva el alias y el vínculo va a
`<carpeta-documentos>\<alias>`, que no existe en ningún disco **hasta que se recuperan los
nombres** (paso 5): `rehidratar` cambia el alias por el nombre real en el texto y por la ruta real
en el vínculo. Por eso **`--carpeta-documentos` va siempre**, con la carpeta de los escaneos tal
como la ve el auditor —la misma que te dio en el paso 3 y que pasaste a `preparar_facturas`—; sin
ella el script usa la que trae el manifiesto. Con el manifiesto de `preparar_documentos.py
--carpeta` el papel sale ya con el nombre real y el vínculo al fichero real. El script dice
cuántos vínculos van por alias, y solo avisa de «rutas que este proceso no ve» si no le has pasado
`--carpeta-documentos`. Sin manifiesto ni carpeta, la celda queda como texto y el script lo dice:
es mejor sin vínculo que con un vínculo que no abre nada.

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

<!-- solo-cowork:entrega -->
**En Cowork el script escribe en el sandbox, no en el expediente**, así que la ruta de destino
no se cumple sola: hay que bajar el fichero. Se envía con `SendUserFile` **por su nombre
exacto** —`"$TRABAJO/$PAPEL"`, nunca `"$TRABAJO"/*.xlsx`—, que devuelve un `file_uuid`, y con
`device_commit_files` y ese `fileUuid` se escribe en el disco del auditor:

```
device_commit_files → "<expediente>/AsistenteIA/FspMum/<PAPEL>"
```

**No lo copies a `/mnt/user-data/outputs` ni lo pases como `stagedPath`**: el 21/10/2026 se hizo
así y `device_commit_files` devolvió 404. En la máquina del auditor esto no hace falta: pásale
directamente a `--salida` la ruta del expediente y el script escribe ahí, creando el árbol si no
existe.
<!-- /solo-cowork -->

**Si el expediente está en OneDrive, el entorno puede rechazar la escritura antes de ejecutar
nada** y pedir autorización expresa. No es un fallo: pídesela al usuario y repite la orden.

### Paso 5 — Entregar

Di dónde ha quedado el fichero y, **antes que nada**:

1. **El término de comparación** que ha usado la muestra (base, total o neto). Todo lo
   demás depende de eso.
2. **Los elementos con diferencia**, uno por uno y con sus cifras.
3. Los errores **por exceso y por defecto, por separado**, tal como los imprime el script.
   Nunca sumados entre sí.
4. Cuántos elementos quedaron sin documento o sin medir, qué documentos de la carpeta no
   son de ningún elemento, y cuántos ficheros se apartaron por el nombre (justificantes,
   albaranes…), con la lista.

Si había evaluación del auditor, traslada las cifras de la comparación. La que importa es
**«el skill da 0 y el auditor puso error»**: incorrecciones que se habrían dejado pasar.

**Archivar: sello y nombres.** El papel se ha escrito con tokens en las columnas de la muestra (la
columna del documento leído, `Proveedores`, lleva lo que decía la factura), con el alias de cada
documento en la celda del fichero y en su vínculo, y con huecos en la hoja «Uso de IA». Cuando ya esté en el disco del auditor, en `<expediente>\AsistenteIA\FspMum\`<!-- solo-cowork --> —en
Cowork, después de bajarlo al expediente con `device_commit_files`; en local, directamente—<!-- /solo-cowork -->,
dos llamadas sobre esa ruta de Windows, en este orden o en el contrario:

1. **`sellar_uso_ia(ruta = "<expediente>/AsistenteIA/FspMum/<fichero>", modelo = "<el modelo con
   el que trabajas>", procedimiento = "fsp-mum")`.** El `procedimiento` es el perfil del paso 1:
   con él el sello toma lo facilitado a ESTE procedimiento y no lo de otra conversación que
   comparta el servidor. Rellena en la hoja «Uso de IA» lo que solo sabe la aplicación:
   herramienta y versiones, quién lo ejecutó, dónde corrieron los scripts y **qué información se
   facilitó y cómo**, según lo que el MCP ha servido desde el paso 1 (la muestra, la evaluación,
   los parámetros y las facturas preparadas, tachadas o no). En `modelo` pon el nombre y la
   versión que te da tu propio contexto; si no lo sabes, déjalo vacío. **Sin esta llamada el papel
   queda con huecos que dicen «pendiente»**: no se da por entregado.
2. **`rehidratar(ruta = …, leyenda = true)`.** Sustituye cada token por el nombre real, en local,
   y devuelve recuentos —ni un nombre vuelve aquí—. Desde el MCP 1.26.0 cambia también **cada
   alias de documento por el nombre real del fichero**, en el texto de las celdas y en el destino
   de los vínculos, que pasan a abrir el documento en su carpeta. Con `leyenda = true` añade la hoja «Tokens»
   con la equivalencia, para que lo que has dicho en el chat con tokens se pueda leer en el papel.
   **Cuéntale al auditor los números que devuelve** (sustituciones y tokens distintos) y, si
   hay `tokens_sin_nombre`, dilos tal cual: no los completes tú. Los tokens de reserva `TER h…`
   rehidratan igual: su nombre es el texto del apunte, que el diccionario guardó al seudonimizar.

Sin llamar «rehidratar» ni «sellar» a nada delante del auditor —para él es **recuperar los
nombres** y dejar constancia del uso de IA—:

> *Papel generado y archivado en el expediente: `AsistenteIA\FspMum\<fichero>`<!-- solo-cowork --> (también lo
> tienes en el chat, aunque esa copia está seudonimizada y sin sellar)<!-- /solo-cowork -->. Nombres de
> terceros y de los ficheros de los documentos recuperados en tu equipo: N sustituciones, M terceros distintos, ninguno sin nombre, y
> hoja «Tokens» con la leyenda. La hoja «Uso de IA» deja constancia de la herramienta y de lo que
> se le facilitó; la verificación, quién la hace, su efecto en la conclusión y la revisión están
> en blanco para el equipo, y mientras lo estén el papel no es evidencia de auditoría. Los
> temporales están borrados.*

<!-- solo-cowork:papel-unico -->La copia del chat **siempre** está seudonimizada y sin sellar —viajó por el contenedor—: dilo, para que no la
confunda con el papel bueno.<!-- /solo-cowork --> **El diccionario de nombres no se borra**: vive con el encargo,
cifrado, y es lo que permite recuperar los nombres de un papel de hace días.

**Lo que no digas**: el error proyectado, el error neto, si se supera el error tolerable, o
si la prueba pasa. Nada de eso sale de este papel.

**Los temporales.** **`limpiar_exportaciones(procedimiento = "fsp-mum")`**, siempre con el
`procedimiento`: así borra solo lo que exportó este procedimiento (y lo abandonado hace más de 12
horas), no lo de otra conversación que use el mismo servidor con otro perfil. Sin él toma el
perfil activo, que puede haberlo cambiado la otra. `limpiar_exportaciones` borra la muestra, los parámetros y la evaluación exportados (si con un MCP anterior escribiste tú `parametros.json` desde `obtener_entidad`, ese no lo borra: bórralo aparte, y en una carpeta conectada puede pedir permiso de borrado) y, desde el MCP 1.14.3, **también las imágenes y el `manifiesto.json` que `preparar_facturas` dejó en `_tmp_cowork\fsp-mum\facturas`** (con un MCP anterior quedan ahí: dilo al auditor con la ruta<!-- solo-cowork:alt=, y en este canal bórralas tú, que compartes disco con el auditor) -->, que en Cowork no tienes shell en su equipo)<!-- /solo-cowork -->.
`facturas.json`<!-- solo-cowork --> y las copias del sandbox<!-- /solo-cowork --> los escribiste
tú: van con el directorio de trabajo. Los PDF no se copian a ningún sitio.

**El directorio de trabajo es de esta ejecución y se borra entero desde fuera**, sin haber entrado
en él. Lleva `facturas.json`, la copia de la muestra y las imágenes de las facturas.

```bash
rm -rf "<!-- solo-cowork:alt=<TRABAJO> --><la ruta que anotaste al crearlo, literal><!-- /solo-cowork -->"
```

<!-- solo-cowork -->**Con la ruta escrita tal cual, nunca con una variable ni con `$(cat …)`**: si el
entorno no conserva variables, `"$TRABAJO"` llega vacío, y el control de seguridad del entorno
bloquea un `rm -rf` sobre una expansión como `"$(cat …)"` (registro del 21/10/2026).

<!-- /solo-cowork -->Si no se deja borrar, di al auditor **la ruta exacta** y **si dentro quedan
imágenes de facturas sin tachar**: las hay si eligió «tal cual» o si las renderizó
`preparar_documentos.py`, que nunca tacha; con «tachadas» del MCP, las que quedan van
tachadas.<!-- solo-cowork --> En Cowork ese directorio está en el contenedor de la nube, no en su
equipo: es justo lo que tiene que saber.<!-- /solo-cowork -->

Si en el paso 1 `configurar` avisó de otra conversación en el mismo servidor, dilo también al
entregar: los temporales de esta se han borrado y los de la otra no se han tocado.

**No te fíes del recuento.** La respuesta de `limpiar_exportaciones` puede traer dos cosas que
no borra, y las dos se dicen:

- **`de_otros_procedimientos`**: ficheros recientes exportados con otro perfil, que pueden ser
  de otra conversación en marcha. No se tocan: se borran cuando ese procedimiento limpie, o solos
  pasadas 12 horas. Díselo al auditor en una línea.
- **`no_escritos_por_mi`** con su **`aviso`**: ficheros que la herramienta **no** ha escrito,
  en carpetas donde alguna vez exportó, con cuántos son, en qué carpetas y de qué fechas. Si
  alguno es una exportación de esta sesión —una muestra, una evaluación— lleva contabilidad del
  cliente, y esas carpetas suelen estar sincronizadas con la nube. **Enséñale al auditor las
  carpetas y las fechas y pídele que los mire**; no lo escondas porque el recuento diga que se han
  borrado muchos. El 18/09/2026 la herramienta
dijo «45 borrados» y quedaron dos exportaciones con datos del cliente dentro de OneDrive.

---

## Cómo se lee el papel

**Dos hojas.** La primera, **«Uso de IA»**, es la evidencia del uso de inteligencia
artificial: herramienta, qué se le pidió, qué información se le facilitó y cómo, qué
devolvió —las tres columnas de la MUM y la observación son **propuestas** suyas— y qué
comprobó ella misma (documentos localizados, término de comparación deducido, fórmulas,
diferencias sin netear y, si la había, la comparación con la evaluación del auditor). Debajo,
una propuesta orientativa de qué verificar y, **en blanco**, la verificación del equipo, quién
la hizo, su efecto en la conclusión y la revisión. Mientras eso esté en blanco el papel no es
evidencia de auditoría, y la hoja de la muestra lo recuerda junto al encabezado.

La segunda, **«Análisis muestra»**: una fila por elemento seleccionado, con sus columnas de
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
| Asignación solo por tercero y fecha, sin número que la ate, con importe que se aparta más de la mitad o fecha lejana | sigue: «asignación dudosa», **sin medir** y contada aparte; se confirma con `poblacion_id` |
| La muestra no fija un término de comparación claro | sigue: los elementos que no casan quedan sin importe propuesto, con el motivo |
| Una columna de tercero que vale lo mismo en todas las filas | el skill cambia de columna solo, y lo avisa (A00). Fue el fallo de la MUM de ventas: «Nombre» valía «Ventas» en las 42 filas. Si se va a la que el MCP ya eligió y seudonimizó por la cuenta, es una línea `C02 · tercero = …` informativa: no se cuenta al entregar |
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
| `sellar_uso_ia` dice que no hay huecos | el papel ya estaba sellado o no es el que escribió el script: no lo repitas, dilo |
| `sellar_uso_ia` dice que no tiene constancia de lo facilitado | o no se sirvió nada por el plugin, o el MCP se reinició a mitad: el papel lo dice y remite a `RegistroEmision.jsonl`; cuéntaselo al auditor tal cual |
| Fichero de salida abierto en Excel | **para** al guardar, y dice que hay que cerrarlo |
| `configurar` avisa de otra conversación con otro expediente o perfil en el mismo servidor | **para** hasta que el auditor confirme que la otra ha terminado |
| El sello dice que el servidor se usó con otro contexto durante el procedimiento | sigue: el papel lo hace constar y remite a `RegistroEmision.jsonl`; díselo al auditor tal cual |
| La carpeta trae solo imágenes (JPG, JFIF, PNG, TIF, BMP) | sigue: `preparar_facturas` (MCP ≥ 1.25.1) y `preparar_documentos.py` las aceptan, una página por imagen |
| Ficheros cuyo nombre dice justificante, remesa, recibo, transferencia, albarán o todos/todas, numerados o no | sigue: se apartan y se listan al auditor por su alias; el que sí sea documento se recupera pidiéndolo por su alias o su id |
| Elementos con token de reserva `TER h…` (cargos bancarios, 626/629) | sigue: se avisa antes de preparar las facturas de que su documento subirá con el emisor visible; el auditor decide si los excluye |
| `preparar_facturas` devuelve `numeros_no_encontrados` | sigue: se dice al auditor con la cuenta; es la pista de un documento que falta o de un número ilegible |
| El auditor excluye un documento de la carpeta | sigue: `preparar_facturas(..., excluir = ["<alias o id>"])`, nunca filtrando el manifiesto a mano |
| El manifiesto del MCP trae nombres reales en `fichero` (MCP anterior a la 1.26.0) | sigue, y `preparar_documentos.py` lo avisa: esos nombres salen en lo impreso; que actualice el plugin |

## Comprobar que el skill funciona

```bash
python "$SKILL/scripts/probar_mum.py"
```

No hace falta ForSampling ni un solo PDF: 102 comprobaciones sobre un fixture sintético de
ocho elementos elegidos por lo que puede salir mal en una MUM —gasto por la base, diferencia
real con su tasa, sin documento, contabilizado por el total, ingreso con saldo negativo,
ingreso negativo con diferencia, documento sin total legible cuya diferencia es justo la
cuota de IVA, y un elemento sin importe—. Comprueba además que el término de comparación sale
de la muestra, que **los errores no se netean nunca**, que se detecta el caso en que el skill
da 0 donde el auditor puso error, que **un tercero tokenizado apaga el criterio de tercero
sin casar nada por casualidad** y el cruce sigue atando por importe, que el papel lleva la hoja
«Uso de IA» con sus huecos y con lo del equipo en blanco, y que `lib_fsp.py` y
`preparar_documentos.py` son byte a byte los mismos ficheros que en `fsp-cumplimiento` y
`lib_uso_ia.py` el mismo que en los demás skills. Y desde el 20/10/2026, que los albaranes y
justificantes sin prefijo numérico se apartan y se recuperan con `--incluir`, que una imagen
suelta es un documento de una página, y que todos los scripts arrancan con `python -I`. Y desde
el 21/10/2026, que con el manifiesto del MCP (alias, sin ruta) el papel enlaza
`<carpeta-documentos>\<alias>` y no avisa de vínculos que no ve cuando se le da la carpeta, que
con el manifiesto local recupera el nombre real sin imprimirlo, y que el «… TODOS.pdf» sin
prefijo se aparta.
