---
name: estados-financieros-gesia
description: >
  Revisión de los estados financieros de un expediente de Gesia, con las cifras ya
  cargadas: papeles en Excel con el balance y la cuenta de resultados comparados, la
  conciliación de lo presentado por el cliente a lo auditado, epígrafe a epígrafe y cuenta
  a cuenta, el movimiento del patrimonio neto, y el estado de flujos de efectivo del
  módulo EFE con sus ajustes; si no hay ajustes de flujos aprobados, propone sus importes.
  Úsalo si piden revisar o cuadrar el balance, la PyG, los ajustes por epígrafe, el ECPN,
  el EFE o el cash flow, o dicen "saca el balance comparado", "cómo ha variado el
  patrimonio neto" o "qué ajustes faltan en el estado de flujos". NO formula cuentas
  anuales, y no es el cuestionario de la memoria, ni el cuadro de mando del diario, ni la
  continuidad de saldos. SI SOLO DICEN «CUENTAS ANUALES», NO LANCES NADA: este revisa LAS
  CIFRAS del expediente, sin PDF; el cuestionario revisa EL CONTENIDO DE LA MEMORIA con el
  PDF del cliente. Pregunta cuál quieren.
---

# Revisión de estados financieros (Gesia)

Enseña de dónde sale cada epígrafe de las cuentas anuales: qué presentó el cliente, qué
ajustes y reclasificaciones se le hicieron, y qué quedó auditado. Y lo cuadra.

Los ficheros se escriben en `<expediente>\AsistenteIA\EstadosFinancieros\` y **nunca se
publican** en ninguna URL: son la contabilidad de un cliente auditado.

---

## Antes de empezar: ¿te han pedido esto, o la memoria?

**«Cuentas anuales» no es este skill, ni es el otro: son las dos cosas.** El conjunto lo
forman el balance, la cuenta de resultados, el estado de cambios en el patrimonio neto, el de
flujos de efectivo y la memoria. Aquí se revisan **las cifras** que el expediente ya tiene
cargadas; el contenido de la memoria lo revisa `cuestionario-cuentas-anuales`, que necesita el
PDF del cliente y produce otro papel distinto.

Si la petición no distingue —«revisa las cuentas anuales», «mira las cuentas del cliente»—,
**pregunta antes de exportar nada** y ofrece las dos. Cuesta una línea, y equivocarse cuesta
un papel que no era el que hacía falta. La pista más fiable: **si el auditor te ha dado o
mencionado un PDF, casi seguro quiere la memoria**.

---

## Cuatro reglas que gobiernan todo

**1. Esto revisa, no formula.** El auditor no formula las cuentas de su cliente. El papel
contrasta lo que hay en el expediente y señala; no propone cifras ni «completa» estados. Si
el usuario pide formular las cuentas anuales, dilo y para.

**2. Solo suman las cuentas asignadas a un epígrafe.** El plan repite la misma cuenta a uno,
dos, tres y cuatro dígitos. Sumarlas todas cuenta el dinero dos o tres veces. La marca es
`AsignadaCCAA`, y en un expediente real son 535 de 4.569 cuentas. El cuadro de mando en Excel
que ya usa la firma hace exactamente lo mismo y la llama `NivelEEFF`.

**3. Solo suman las líneas que admiten cuentas.** `CuentasAsignables` distingue las líneas de
detalle de los totales y subtotales del modelo oficial. Sumar los subtotales duplica igual.

**4. El signo de presentación no es el del dato crudo.** En el balance el pasivo viene con el
signo cambiado; en pérdidas y ganancias la regla de Gesia es epígrafes en magnitud y
subtotales invertidos. El script la replica **tal cual**, sin «mejorarla», para que las cifras
coincidan con las que el auditor ve en la revisión analítica del programa. Si algún día no
coinciden, es un fallo del skill, no del programa.

---

## Dónde están los scripts

Al cargarse, el runtime indica el **directorio base del skill**. Las rutas `scripts/…` son
relativas a él, no al directorio de trabajo:

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(mktemp -d "${TMPDIR:-/tmp}/eeff-XXXX")" && echo "$TRABAJO"
```

`$TRABAJO` es **nuevo en cada ejecución**: no reutilices el de otra vez ni el de otro skill, y no
hagas `cd` dentro; las rutas van siempre completas. **Anota la ruta que imprime**: si el entorno
no conserva las variables entre llamadas, vuelve a escribir `TRABAJO="<esa ruta>"` al principio
de cada orden, sin crear otro.

Los scripts no tocan el `.gs3`: leen lo que `exportar_consulta` haya dejado en disco. El
expediente lleva contraseña y **solo lo abre el servidor API**.

**`cuentas.json` lleva el nombre de todas las cuentas del plan**, y las de los grupos 40, 41 y
43 se llaman como el proveedor o el cliente. Por eso el paso 1 pone el perfil
`estados-financieros`, que los exporta como token, y por eso **los scripts se niegan a
trabajar con un plan que los traiga en claro** (paran con «NOMBRE EN CLARO»).

En la máquina del auditor —Claude Code, ChatGPT— el MCP y los scripts comparten disco: los
pasos exportan a `<TEMP>/gesia-eeff/`, los scripts leen de ahí y escriben el papel
directamente en el expediente.
<!-- solo-cowork -->

#### En Cowork: quien exporta y quien calcula no son la misma máquina

El MCP corre en el equipo del auditor y escribe ahí; los scripts corren en el entorno de la
sesión y **no ven el `<TEMP>` de ese equipo**. Medido el 05/10/2026: la sesión no tenía shell en
el equipo, exportó el plan sin perfil a una carpeta del expediente en OneDrive y solo entonces
se paró. Así se hace bien, y en este orden:

1. **El perfil, antes de la primera exportación** (paso 1). Lo que viaja a la sesión son los
   ficheros exportados: con el perfil, viajan seudonimizados.
2. **Exporta dentro de la carpeta conectada**, en `<raíz de la carpeta conectada>/_tmp_cowork/gesia-eeff/`:
   donde los pasos dicen `<TEMP>/gesia-eeff/`, usa esa ruta. `device_stage_files` no puede
   subir un fichero que esté fuera de las carpetas conectadas. **Nunca en `AsistenteIA`**: ahí
   van los papeles que el auditor archiva. Si la carpeta conectada es el propio expediente,
   `_tmp_cowork\` va en su raíz, fuera de `AsistenteIA`.
3. **Todas las exportaciones antes de subir nada, y una sola tanda.** Son cinco ficheros:
   `ejercicios.json` (paso 1), `estructura.json` (paso 2), `cuentas.json` (paso 3), y
   `cuadro.json` y `catalogo.json` (paso 5 ter). Exporta los cinco, **súbelos juntos** con
   `device_stage_files`, nombrándolos uno a uno, y trabaja con la copia de la sesión, bajo
   `/mnt/user-data/uploads/_tmp_cowork/gesia-eeff/`. Comprueba que están los cinco con
   `ls -la`, sin abrir ninguno. Un fichero exportado después de la tanda no está en la sesión:
   el script para con `FileNotFoundError`.

   Si `device_stage_files` falla por permisos, pide acceso con `device_request_folder_access`
   sobre la raíz de la carpeta conectada y repite la subida **una vez**. Si vuelve a fallar,
   para y díselo al auditor: no busques otra forma de llevar los ficheros a la sesión.
4. **Los scripts escriben en la sesión**: pásales `--salida "$TRABAJO/<fichero>.xlsx"` y baja
   cada papel al expediente con `SendUserFile`, que devuelve un `file_uuid`, y
   `device_commit_files` → `<expediente>/AsistenteIA/EstadosFinancieros/<fichero>`.
   **Cada papel por su nombre exacto, uno a uno, nunca con un comodín**: un `*.xlsx` arrastra
   lo que haya en la carpeta, y en una sesión real se llevó el papel de otro skill al expediente.
   El nombre es el que quedó elegido en el paso 5 si alguno ya existía, y sin `force` (paso 5).
5. **Sella y recupera los nombres en el equipo** de cada papel ya bajado, en la entrega
   (paso 6): `sellar_uso_ia` y `rehidratar`, sobre la ruta de Windows del expediente.
6. **Al terminar, `limpiar_exportaciones(procedimiento = "estados-financieros")`**: borra lo
   exportado por este procedimiento —y solo eso— y la carpeta `_tmp_cowork` si queda vacía. Si
   la carpeta conectada se sincroniza a la nube, dile al auditor que ahí ha habido datos del
   plan, seudonimizados, hasta el borrado. Y borra el directorio de trabajo desde fuera, con
   **la ruta literal que anotaste**: `rm -rf "<la ruta que anotaste>"`. Ni con la variable, que
   en Cowork no pasa de una llamada a otra y deja la orden en `rm -rf ""`, ni con
   `rm -rf "$(cat …)"`, que la seguridad del entorno bloquea (registro del 21/10/2026). Si no se
   puede borrar, di su ruta.

**Si no hay ni shell en el equipo ni entorno de sesión donde ejecutar los scripts, para y
díselo antes de exportar nada.**
<!-- /solo-cowork -->

---

## Secuencia

### Paso 1 — Expediente

```
configurar(perfil = "estados-financieros")   # primero: nombres de terceros seudonimizados
contexto_expediente()                        # siempre, después del perfil
```

**Lo primero, antes de exportar nada: el perfil.** Con él, el MCP **seudonimiza los nombres de
terceros** en todo lo que exporta: en `cuentas.json` las cuentas de proveedores y clientes
salen como `PROV 40000012` o `CLI 43000007` en vez de su razón social, y el papel los recupera
al final con `rehidratar`. Trabaja y habla por cuenta y por token; **nunca preguntes al auditor
a quién corresponde un token ni lo adivines**. Si un script para con «NOMBRE EN CLARO», faltó
el perfil: ponlo, borra lo exportado con `limpiar_exportaciones(procedimiento =
"estados-financieros")` y repite la exportación. Solo
si `configurar()` dice `nombres_terceros: en claro — forzado por el auditor`, lo ha apagado él:
entonces pasa `--nombres-en-claro` a los scripts, y no lo vuelvas a encender tú.

El perfil marca también **el comienzo del procedimiento**: desde ahí el MCP lleva la cuenta de
lo que facilita a la herramienta, que es lo que cada papel dirá en su hoja «Uso de IA». Por eso,
**justo después del perfil, llama siempre a `contexto_expediente()`, aunque ya lo tengas** de
antes en la conversación: lo que se leyó con otro perfil, o sin ninguno, no cuenta como
facilitado para estos papeles.

`configurar()` te devuelve además el estado. Si no hay expediente, pide la ruta del
`.gs3`. Si responde que el servidor API no contesta, **llama a `arrancar_api`**: lo levanta en
el equipo del auditor y sigues. No le pidas a él que lo arranque a mano.

**Si `configurar()` avisa de que otra conversación está trabajando con otro expediente o con
otro perfil en el mismo servidor**, díselo al auditor tal cual y **no sigas hasta que
confirme**. Las dos conversaciones comparten el MCP y se pisan: lo que configura una cambia el
expediente o el perfil con que trabaja la otra.

Quédate con el nombre del cliente y con la correspondencia de ejercicios:

```
exportar_consulta(sql = "SELECT CodigoAuditoria, Año FROM Auditorias",
                  ruta = "<TEMP>/gesia-eeff/ejercicios.json")
```

**`CodigoAuditoria` es un orden interno, no un año.** El 1 es el ejercicio más reciente. Nunca
etiquetes una columna con un año sin haber leído esta tabla.

### Paso 2 — La estructura de los dos estados

Una sola exportación con las dos tablas unidas. La columna `Estado` es la que luego las
separa en el papel:

```
exportar_consulta(
  sql = "SELECT CodigoCCAA, 'Balance' AS Estado,
                IIf(CodigoClase='A','ACTIVO','PASIVO') AS Activo_Pasivo, CodigoClase,
                CodigoAMostrar, Concepto, CuentasAsignables, CodigoSeccion, CodigoEpigrafe,
                CodigoDesglose, CodigoSubDesglose, Null AS CodigoOrdenI,
                SaldoAuditoria1, SaldoAuditoria2, SaldoAuditoria3, SaldoAuditoria4,
                SaldoAuditoria5
         FROM EstructuraBalance
         UNION ALL
         SELECT CodigoCCAA, 'PyG', '', CodigoClase, CodigoAMostrar, ConceptoIngresos,
                CuentasAsignables, CodigoSeccion, CodigoEpigrafe, CodigoDesglose,
                CodigoSubDesglose, CodigoOrdenI, SaldoAuditoria1, SaldoAuditoria2,
                SaldoAuditoria3, SaldoAuditoria4, SaldoAuditoria5
         FROM EstructuraPyG WHERE CodigoClase IN ('I','T','ST')",
  ruta = "<TEMP>/gesia-eeff/estructura.json")
```

Son del orden de 175 filas. **No las abras**: el script las lee tal cual.

`CodigoOrdenI` es el orden oficial de la cuenta de resultados, y es el mismo por el que ordena
el cuadro de mando en Excel de la firma. El balance no tiene columna de orden —va por sección,
epígrafe y desglose—, por eso ahí se pide `Null`. Sin `CodigoOrdenI` la PyG sale desordenada:
las cifras son correctas y las líneas están cambiadas de sitio, que es la peor de las dos
formas de estar mal.

### Paso 3 — El plan de cuentas con su epígrafe y su saldo

Aquí está la cadena de la revisión: lo del cliente, los ajustes, las reclasificaciones y lo
auditado, por cuenta.

```
exportar_consulta(
  sql = "SELECT ca.Cuenta, c.Nombre, ca.Digitos, ca.CodigoCCAA, ca.AsignadaCCAA,
                ca.SaldoAuditoria, c.SaldoAnterior, c.SaldoCliente, c.SaldoAj, c.SaldoRec
         FROM CuentasAuditorias AS ca INNER JOIN Cuentas AS c ON ca.Cuenta = c.Cuenta
         WHERE ca.CodigoAuditoria = '1'",
  ruta = "<TEMP>/gesia-eeff/cuentas.json")
```

El `'1'` es el ejercicio corriente y va **entrecomillado**: el campo es texto, y sin comillas
Access responde que no coinciden los tipos de datos.

Son varios miles de filas y pesa poco, porque va a fichero y no a tu contexto.

`SaldoAnterior` es **la apertura del ejercicio, y es la auditada**: medido en un expediente
real, coincide con el `SaldoAuditoria` del ejercicio anterior en las 535 cuentas asignadas, sin
una excepción. Sin esa columna no hay papel de patrimonio neto.

### Paso 4 — Verificar el contrato (puede abortar)

```bash
python "$SKILL/scripts/verificar_contrato.py" \
  --estructura "<TEMP>/gesia-eeff/estructura.json" \
  --cuentas    "<TEMP>/gesia-eeff/cuentas.json" \
  --ejercicios "<TEMP>/gesia-eeff/ejercicios.json"
```

Salida `2` → **no se genera nada**. Lee el motivo y trasládalo. Aborta si el balance
descuadra, si no se sabe qué ejercicio es cada columna, si ninguna cuenta está asignada a un
epígrafe o si los epígrafes de las cuentas no existen en la estructura.

Salida `1` → se puede seguir, pero **los avisos van al auditor en la entrega**.

Salida `0` → todo encaja.

### Paso 5 — El papel de trabajo

**Si algún papel ya existe, una sola pregunta para todos, antes del primero.** Mira si en
`<expediente>\AsistenteIA\EstadosFinancieros\` ya está alguno de los cuatro de este skill
—«Estados Financieros», «Patrimonio Neto», «Flujos de Efectivo» y «Propuesta EFE», con el
cliente y el ejercicio—<!-- solo-cowork:alt=. --> —en Cowork, listando la carpeta conectada con
`device_list_dir`; en local, en el disco—.<!-- /solo-cowork --> Si hay alguno, **pregunta al auditor una vez**,
diciendo cuáles: sobrescribirlos, o guardar los de esta ejecución con « (rehecho AAAA-MM-DD)»
antes de la extensión, con la fecha de hoy; lo que elija vale para todos los que salgan, y con
el sufijo lo llevan todos, para que se vea que van juntos. Ni los sobrescribas sin preguntar ni
inventes otro sufijo: al repetir un procedimiento el mismo día, una ejecución pisó el papel y otra
improvisó el nombre (registro del 21/10/2026). Los nombres elegidos son los de todo lo que sigue
—los `--salida` de los pasos 5 a 5 quater,<!-- solo-cowork --> la bajada al expediente,<!-- /solo-cowork --> el
sello y la recuperación de nombres—.<!-- solo-cowork --> En Cowork, `device_commit_files` va **sin `force`**;
solo si el auditor eligió sobrescribir y el commit lo rechaza porque el fichero existe, repítelo
con `force` y díselo.<!-- /solo-cowork -->

```bash
python "$SKILL/scripts/generar_papel.py" \
  --estructura "<TEMP>/gesia-eeff/estructura.json" \
  --cuentas    "<TEMP>/gesia-eeff/cuentas.json" \
  --ejercicios "<TEMP>/gesia-eeff/ejercicios.json" \
  --cliente    "<razón social del expediente>" \
  --ejercicio  "<año del ejercicio corriente>" \
  --generado   "<fecha de hoy, dd/mm/aaaa>" \
  --salida     "<expediente>/AsistenteIA/EstadosFinancieros/Estados Financieros <CLIENTE> <EJERCICIO>.xlsx"
```

`--generado` es la fecha de hoy, que conoces por tu contexto, y la llevan los cuatro scripts de
este skill. **La pones tú**: nada en este skill lee el reloj.

Seis hojas: **Uso de IA**, **Balance**, **PyG**, **Conciliacion**, **Ajustes** y
**Comprobaciones**.

**Cada papel de este skill empieza por la hoja «Uso de IA»**, la suya: la evidencia de que se
hizo con una herramienta de inteligencia artificial, de qué se le facilitó, de lo que comprobó
el propio script y de cómo podría verificarse, y cada hoja del papel lleva la marca «Uso de IA:
pendiente de verificación». Los apartados de la herramienta quedan con huecos que se rellenan al
archivar (paso 6); los de verificación, verificado por, efecto en la conclusión y revisión **son
del equipo y salen en blanco**. No escribas nada en ellos ni propongas texto para ellos.

Si el script termina con salida `1`, imprime una sección **«PARA CONTAR AL ENTREGAR (tal cual,
sin resumir)»**. Esas líneas van al auditor **literales, todas**, no resumidas con tus
palabras.

En las hojas Comprobaciones de los cuatro papeles, **«NO CUADRA» es siempre un fallo
aritmético**. Lo que está a medias por diseño lleva su propia etiqueta y no es un descuadre:
**«SIN HACER»** el estado de flujos sin ajustes aprobados, y **«BORRADOR»** la propuesta de
ajustes. No los cuentes como descuadres, ni los des por buenos porque el resto salga en verde.

### Paso 5 bis — El papel de patrimonio neto

**Siempre.** Usa **los mismos tres ficheros** del paso 3: no cuesta ni una exportación más, así
que no hay motivo para dejarlo a que al auditor se le ocurra pedirlo.

```bash
python "$SKILL/scripts/generar_ecpn.py"   --estructura "<TEMP>/gesia-eeff/estructura.json"   --cuentas    "<TEMP>/gesia-eeff/cuentas.json"   --ejercicios "<TEMP>/gesia-eeff/ejercicios.json"   --cliente    "<razón social del expediente>"   --ejercicio  "<año del ejercicio corriente>"   --generado   "<fecha de hoy, dd/mm/aaaa>"   --salida     "<expediente>/AsistenteIA/EstadosFinancieros/Patrimonio Neto <CLIENTE> <EJERCICIO>.xlsx"
```

Cinco hojas: **Uso de IA**, **PatrimonioNeto**, **Movimiento**, **Detalle** y **Comprobaciones**.

**Gesia no tiene módulo de ECPN.** Está comprobado sobre el ejecutable: los nombres de tabla
que aparecen en su propio SQL son los del balance, la PyG, la PyG analítica, las cuentas
anuales antiguas y las tres del estado de flujos. De patrimonio neto no hay tabla ni menú. Por
eso este papel **reconcilia** cada componente —de la apertura auditada al cierre auditado,
pasando por el movimiento del cliente, los ajustes y las reclasificaciones— y **no reparte** la
variación entre resultado, operaciones con socios y otras variaciones. Ese reparto lo hace
quien firma.

La clasificación por componentes tampoco se inventa: es la del propio Gesia, la del epígrafe
del balance al que está asignada cada cuenta.

El semáforo de este papel tiene **tres** estados, no dos. «A TENER EN CUENTA» no es un
descuadre: es algo que el auditor necesita saber, y sale igualmente en la sección de
«PARA CONTAR AL ENTREGAR». El caso típico: el cliente no usa los grupos 8 y 9, así que el
estado de ingresos y gastos reconocidos no se puede sacar de la contabilidad y hay que
construirlo con él. Pasa en los dos expedientes de calibración.

### Paso 5 ter — El papel de flujos de efectivo

**Mira siempre si hay estado que revisar; otra cosa es que lo haya.** No esperes a que te lo
pidan: lo que decide es el dato, y comprobarlo cuesta una exportación.

**La señal son los ajustes APROBADOS, no que el cuadro tenga cifras.** Gesia rellena las
variaciones de balance él solo en cuanto hay dos ejercicios cargados, así que un cuadro con
importes no significa que nadie haya trabajado el estado. Medido en un expediente terminado de
modelo reducido: 159 líneas con importe y cero ajustes aprobados, porque formulando abreviado
no está obligado a presentarlo y el auditor ni lo empezó. Ahí el papel sale igual, pero dice
que el estado está **SIN HACER** (más abajo).

Así que primero el cuadro y el catálogo de ajustes, que son las exportaciones que responden a la
pregunta. Son las dos únicas del estado de flujos: el catálogo sirve también para la propuesta
del paso 5 quater.<!-- solo-cowork --> En Cowork van en la tanda inicial, con las de los pasos 1
a 3, antes de subir nada.<!-- /solo-cowork -->

```
exportar_consulta(
  sql = "SELECT CodigoAuditoria, CodigoOrden, CodigoLinea, Descripcion, Origen,
                Aplicacion, OrigenAjuste, AplicacionAjuste, OrigenAjustado,
                AplicacionAjustada, SaldoAuditoriaAnterior, SaldoAuditoria
         FROM CuadroFinanciacion WHERE CodigoAuditoria = '1'",
  ruta = "<TEMP>/gesia-eeff/cuadro.json")

exportar_consulta(
  sql = "SELECT a.NumeroAsientoOA, a.Fecha, a.Descripcion,
                a.GeneracionFondos AS Aprobado, a.Observaciones, p.ApunteOA, p.Cuenta,
                p.Concepto, p.Contrapartida, p.Origen, p.Aplicacion
         FROM AsientosOA AS a
         LEFT JOIN ApuntesOA AS p ON a.NumeroAsientoOA = p.NumeroAsientoOA
         ORDER BY a.NumeroAsientoOA, p.ApunteOA",
  ruta = "<TEMP>/gesia-eeff/catalogo.json")
```

El `LEFT JOIN` es a propósito: así vienen también las plantillas del catálogo que nadie ha
usado, y el papel puede decir cuántas hay frente a cuántas están aprobadas.

`Observaciones` es el criterio de cada plantilla, escrito por quien montó el máster: dice de
qué cuentas sale el importe y qué mirar. Es doctrina de la casa y la propuesta lo reproduce tal
cual, sin resumirlo.

**Cuenta los aprobados —`Aprobado` a `True`— antes de seguir**, porque es lo que decide qué
estás entregando. Si no hay ninguno, el expediente **no tiene el estado de flujos hecho**:
Gesia rellena el cuadro solo, comparando saldos de balance, y cuadra perfectamente consigo
mismo sin un solo ajuste del auditor.

**Genera el papel igual** —enseña precisamente eso, que está sin hacer— y al entregar **lleva
el aviso por delante**, antes que ninguna cifra: sin ajustes aprobados, eso no es un estado de
flujos, y el verde de las demás comprobaciones no dice que lo esté. El papel lo marca como
**«SIN HACER»** —no como «NO CUADRA»: no es un descuadre, es trabajo por hacer—, el script
imprime `estado de flujos: SIN HACER` y lo repite en «PARA CONTAR AL ENTREGAR»: cópialo tal
cual y **no lo resumas en «cuadra»**.

**Y sigue con la propuesta, sin esperar a que te la pidan** (paso 5 quater). Es el caso
normal, no la excepción: de nueve expedientes medidos el 25/09/2026, **ocho** tienen el
catálogo del máster sin tocar y cero ajustes aprobados. Un papel que solo diga «esto no está
hecho» no le sirve de nada al auditor; cuatro ajustes calculados son cuatro que no tiene que
calcular él.

```bash
python "$SKILL/scripts/generar_efe.py" \
  --cuadro     "<TEMP>/gesia-eeff/cuadro.json" \
  --ajustes    "<TEMP>/gesia-eeff/catalogo.json" \
  --estructura "<TEMP>/gesia-eeff/estructura.json" \
  --ejercicios "<TEMP>/gesia-eeff/ejercicios.json" \
  --cliente    "<razón social del expediente>" \
  --ejercicio  "<año del ejercicio corriente>" \
  --generado   "<fecha de hoy, dd/mm/aaaa>" \
  --salida     "<expediente>/AsistenteIA/EstadosFinancieros/Flujos de Efectivo <CLIENTE> <EJERCICIO>.xlsx"
```

Cinco hojas: **Uso de IA**, **FlujosEfectivo**, **Ajustes**, **Apuntes** y **Comprobaciones**.

**Cuatro cosas de este módulo que no se adivinan**, todas medidas y todas vigiladas por el
papel:

1. **La casilla «Aprobado» es el campo `GeneracionFondos`**, que no significa lo que su nombre
   dice. Solo cuentan los aprobados, igual que en los ajustes de auditoría. Comprobado por
   aritmética: los ajustes del cuadro son exactamente la suma de los apuntes aprobados en las
   159 líneas, sin una excepción.
2. **Un cuadro con cifras no quiere decir que el estado esté hecho.** Gesia rellena las
   variaciones de balance él solo en cuanto hay dos ejercicios cargados. Sin ajustes aprobados
   eso no es un estado de flujos: es la aritmética del programa sin el criterio del auditor, y
   cuadra consigo mismo perfectamente. Pasa en uno de los dos expedientes de calibración, con
   159 líneas con importe y cero ajustes aprobados. El papel lo dice en ámbar, arriba del todo,
   como «SIN HACER».
3. **`Cuenta` y `Contrapartida` de un apunte NO son cuentas contables**: son líneas del propio
   estado. El ajuste es partida doble entre líneas del cuadro, y sus cobros tienen que igualar
   a sus pagos.
4. **Si la tabla está vacía, no es un error.** Los modelos de pymes no llevan estado de flujos
   porque el plan no se lo exige: se dice y se para, sin ofrecer nada.

Y el cuadre que vale por todos: la suma de los flujos de las actividades es la variación de la
tesorería, y esa variación es la del epígrafe de efectivo del balance. Medido en el expediente
con el estado hecho: 685.252,52 € por los tres caminos.

### Paso 5 quater — Proponer los ajustes del estado de flujos

**Automáticamente cuando el expediente no tiene ningún ajuste aprobado**, sin esperar a que te
la pidan; con ajustes aprobados, solo si el auditor la pide. Siempre **después** del papel de
flujos, porque ahí se ve qué falta. Si el cuadro está vacío —modelo de pymes— no hay nada que
proponer.

**Lo que sale es un BORRADOR, y así hay que entregarlo.** La hoja Comprobaciones lo marca como
«BORRADOR», no como «NO CUADRA»: no es un error de nadie. Medido contra el único expediente
que tiene el estado terminado: de los diez ajustes que aprobó el auditor, estas reglas
aciertan **cuatro** —y no fallan ninguna— pero cubren el **32 %** del importe movido. Los seis
que faltan son los grandes: impuesto de sociedades, ventas de inmovilizado, provisiones,
reclasificación de créditos y las dos amortizaciones de deuda; solo la de créditos movía más
del doble que todo lo propuesto junto.

Así que al entregar, **por delante de cualquier cifra**, tres cosas:

1. **Qué se propone y con qué regla**, cada una con su importe.
2. **Qué falta, por nombre**: las plantillas del catálogo sin propuesta salen en la hoja
   `Catalogo` con el criterio que escribió quien montó el máster. Eso es lo que el auditor
   tiene que calcular, y decírselo es la mitad del valor del papel.
3. **Que no va a cuadrar, y que no cuadra porque está a medias**, no porque haya un error en
   las cuentas del cliente. Si esto no se dice, el descuadre se atribuye al cliente.

Usa el `catalogo.json` del paso 5 ter, que ya trae el criterio de cada plantilla
(`Observaciones`): **no hace falta otra exportación**.

```bash
python "$SKILL/scripts/proponer_efe.py" \
  --catalogo "<TEMP>/gesia-eeff/catalogo.json" \
  --cuentas  "<TEMP>/gesia-eeff/cuentas.json" \
  --cuadro   "<TEMP>/gesia-eeff/cuadro.json" \
  --cliente  "<razón social del expediente>" \
  --ejercicio "<año del ejercicio corriente>" \
  --generado "<fecha de hoy, dd/mm/aaaa>" \
  --salida   "<expediente>/AsistenteIA/EstadosFinancieros/Propuesta EFE <CLIENTE> <EJERCICIO>.xlsx"
```

Cuatro hojas: **Uso de IA**, **Propuestas**, **Catalogo** y **Comprobaciones**. Aquí la hoja
«Uso de IA» dice, con número e importe, **qué importes ha calculado la herramienta** y que es un
borrador: es el único papel del skill con cifras que no salen tal cual del expediente.

**Esto no escribe nada en Gesia**, que el MCP solo lee. Es una propuesta en papel, y al
teclearla va **siempre como ajuste NO APROBADO y con «Asistente IA:» al principio de la
descripción**, para que no se confunda nunca con el trabajo del auditor. El papel ya la
escribe así.

**Solo hay cuatro reglas, y no salen de leer el criterio: salen de reproducir lo que un
auditor puso de verdad.** En el expediente que tiene el estado hecho, las cuatro dan el
importe exacto, y la de amortización acierta apunte por apunte:

| Regla | De dónde sale | Comprobado |
|---|---|---|
| Distribución del resultado (beneficio) | apertura de la 129, repartida por el movimiento de reservas, remanente y pérdidas anteriores; el resto, dividendo | 848.404,89 |
| Amortización del ejercicio | 680, 681 y 682, cada una con su amortización acumulada | 140.498,55 |
| Gastos financieros | saldo de la 66 | 220.875,62 |
| Ingresos financieros | saldo de la 76 | 496.068,23 |

**Lo que NO se propone importa tanto como lo que sí**, y el papel lo dice: el impuesto de
sociedades (el auditor puso 315.413,38 y el gasto de la 630 son 240.077,05, porque la línea es
de cobros y pagos y no del gasto devengado), las provisiones (fueron por la 529, no por la 14)
y la distribución de pérdidas, que se escribió por simetría y al probarla colaba el movimiento
de las subvenciones como si fuera reparto del resultado. Cuadraba, y habría pasado por buena.

**Cada una de las cuatro reglas dice si se ha aplicado o por qué no.** El script las imprime
bajo «reglas verificadas», una línea por regla: aplicada a qué plantilla y por cuánto, o el
motivo concreto de que no —la 66 o la 76 sin saldo o fuera del plan, las dotaciones 68 a cero,
la 129 abriendo a cero o deudora (pérdida del ejercicio anterior, variante sin calibrar), o que
ninguna plantilla del catálogo tiene la forma de la regla—. **Cuéntalas las cuatro, tal cual.**
Una plantilla con regla verificada que se queda sin importe no es lo mismo que una sin regla:
en la hoja `Catalogo`, la columna «Regla y motivo» las separa —aplicada, «NO aplicada, porque…»
en amarillo, o sin regla—, y en `Comprobaciones` van en filas distintas.

Al entregar, di siempre estas dos cosas: **cuántas plantillas del catálogo llevan propuesta,
cuántas tienen regla y no se aplicó —con el motivo— y cuántas no tienen regla**, y que **donde
el auditor ya puso el ajuste manda lo suyo**; si la propuesta no coincide con lo que hay en
Gesia, eso es algo que entender, no algo que corregir.

### Paso 6 — Entregar

**Enumera los cuatro papeles, los hechos y los no hechos, con el motivo.** Es la parte que más
fácil se queda a medias: si solo cuentas el primero, el auditor da por terminado el trabajo y
no sabe que faltan tres.

| Papel | Cuándo sale | Si no sale, qué decir |
|---|---|---|
| Estados financieros | siempre | — |
| Patrimonio neto | siempre | — |
| Flujos de efectivo | siempre que el módulo EFE tenga cuadro con cifras, con ajustes aprobados o sin ellos | que es un modelo de pymes y no lleva estado de flujos, o que el cuadro está a cero |
| Propuesta de ajustes del EFE | sin ajustes aprobados, siempre (paso 5 quater); con ajustes aprobados, solo si el auditor la pide | con ajustes aprobados y sin pedirla, nada: no se ofrece sola. Sin estado de flujos, lo mismo que el papel de flujos |

**Si el expediente tiene 0 ajustes aprobados, una línea propia, antes que las cifras de los
papeles: «El estado de flujos NO está hecho: el expediente no tiene ningún ajuste aprobado; lo
que cuadra es el cálculo de Gesia consigo mismo».** Sin ella, el verde de las demás
comprobaciones se lee como «hecho».

Y de cada papel que salga, en pocas líneas:

- dónde está el fichero, con la ruta completa
- qué ejercicios lleva el comparativo
- cuántas cuentas tienen ajuste o reclasificación y cuántos epígrafes mueven
- si todas las comprobaciones cuadran, o cuáles no; lo que salga «SIN HACER» o «BORRADOR» se
  dice como lo que es, trabajo a medias, no como descuadre

Y una advertencia que va siempre: **el papel es una lectura del expediente, no una opinión.**
Que los epígrafes cuadren no dice que las cuentas sean correctas, dice que el expediente es
internamente consistente.

**Archivar cada papel.** Con cada papel **ya en el disco del auditor**, en
`<expediente>\AsistenteIA\EstadosFinancieros\`, dos llamadas sobre esa ruta de Windows, en este
orden o en el contrario, y con **todos** los papeles que hayan salido:

1. **`sellar_uso_ia(ruta = "<expediente>/AsistenteIA/EstadosFinancieros/<fichero>", modelo =
   "<el modelo con el que trabajas>", procedimiento = "estados-financieros")`**, una vez por
   papel, cada uno por su nombre. Rellena en la hoja «Uso de IA» de ese papel lo que solo
   sabe la aplicación: herramienta y versiones, quién lo ejecutó, dónde corrieron los scripts y
   **qué información se facilitó y cómo**, según lo que el MCP ha servido desde el paso 1. En
   `modelo` pon el nombre y la versión que te da tu propio contexto; si no lo sabes, déjalo
   vacío. **Sin esta llamada el papel queda con huecos que dicen «pendiente»**: no se da por
   entregado.
2. **`rehidratar(ruta = "<expediente>/AsistenteIA/EstadosFinancieros/<fichero>", leyenda =
   true)`.** Los papeles se han escrito con tokens: sustituye cada token por el nombre real, en
   local, y devuelve recuentos —ni un nombre vuelve aquí—. El de flujos puede no llevar ninguno,
   y eso no es un fallo. Cuéntale al auditor las sustituciones y los terceros distintos de cada
   papel y, si hay `tokens_sin_nombre`, dilos tal cual: son cuentas que el diccionario no
   conoce, no las completes tú.

Delante del auditor no llames «rehidratar» ni «sellar» a nada: para él es **recuperar los
nombres** y **dejar constancia del uso de IA**. Y dile siempre, de cada papel, que su hoja «Uso
de IA» deja constancia de la herramienta y de lo que se le facilitó, y que **la verificación,
quién la hace, su efecto en la conclusión y la revisión están en blanco para el equipo: mientras
lo estén, el papel no es evidencia de auditoría**. <!-- solo-cowork:papel-unico -->La copia del
chat **siempre** está seudonimizada y sin sellar —viajó por el contenedor—: dilo, para que no la
confunda con el papel bueno.<!-- /solo-cowork -->

**Si en el paso 1 `configurar()` avisó de otra conversación** trabajando en el mismo servidor,
recuérdaselo al auditor al entregar: lo que la hoja «Uso de IA» dice que se facilitó es lo que
el MCP sirvió, y con dos conversaciones a la vez puede no ser solo lo de esta.

**Los temporales.** Lo que haya escrito `exportar_consulta` lo borra
`limpiar_exportaciones(procedimiento = "estados-financieros")`, que solo toca lo de este
procedimiento y deja lo de otros skills: funciona igual en local y en Cowork, porque lo borra el
MCP en el equipo del auditor.

---

## Lo que este skill no hace

- **No formula las cuentas anuales.** Revisa las que hay en el expediente.
- **No hace el estado de flujos de efectivo.** Gesia tiene su propio módulo, con su catálogo
  de ajustes y su casilla de aprobado; está documentado en `docs/esquema-efe.md` y es una fase
  posterior.
- **No formula el ECPN oficial.** Reconcilia el patrimonio neto componente a componente;
  repartir la variación entre resultado, operaciones con socios y otras variaciones es una
  clasificación del auditor.
- **No hace el estado de ingresos y gastos reconocidos** cuando el cliente no usa los grupos 8
  y 9, que es lo normal en una pyme: sin esas cuentas el desglose no está en la contabilidad.
- **No calcula el estado de flujos de efectivo.** Lo lee del módulo EFE del expediente y lo
  cuadra. Gesia hace la aritmética y deja el juicio al auditor; ese reparto es del producto y
  no hay que competir con lo que ya hace bien.
- **No decide los ajustes del estado de flujos: propone el importe de cuatro**, y solo de
  aquellas cuya regla se pudo contrastar contra un expediente real. Las demás las rellena el
  auditor con el criterio que trae cada plantilla.
- **No escribe la propuesta en Gesia.** El MCP solo lee.
- **No hace la memoria.**
- **No compara con el ejercicio anterior más allá de lo que el expediente guarda.** El saldo
  del cliente solo existe del ejercicio corriente. Si el auditor quiere la conciliación de un
  año anterior, hace falta el `.gs3` de ese año: se le pide y se pasa con
  `configurar(gs3_anterior=…)`.
- **No escribe nada en Gesia.** El MCP solo lee.
- **No proyecta, no valora y no opina sobre la empresa.**
- **No verifica su propio resultado por el equipo.** Propone qué contrastar; la verificación,
  quién la hace y su efecto en la conclusión los escribe el equipo en la hoja «Uso de IA» de
  cada papel.

---

## Degradación

| Situación | Qué hace |
|---|---|
| El servidor API no responde | llama a `arrancar_api` y repite; solo si eso falla, se lo dice al auditor |
| `configurar` avisa de otra conversación con otro expediente o perfil en el mismo servidor | se lo dice al auditor y **no sigue** hasta que confirme |
| Un script para con «NOMBRE EN CLARO» | faltó el perfil: `configurar(perfil = "estados-financieros")`, `limpiar_exportaciones(procedimiento = "estados-financieros")` y exportar de nuevo |
| El expediente no tiene cifras cargadas en ningún ejercicio | **para**: no hay nada que revisar |
| El balance descuadra en algún ejercicio | **para**: con un balance descuadrado no se emite papel, y se dice en qué ejercicio y por cuánto |
| Los epígrafes de las cuentas no existen en la estructura | **para**: el mapeo no es de este modelo de cuentas |
| El expediente no trae saldo de cliente | sigue: el papel compara ejercicios pero no lo presentado frente a lo auditado, y se avisa |
| Solo hay un ejercicio con cifras | sigue: sin columna de variación |
| No hay líneas de pérdidas y ganancias | sigue: el papel sale solo con el balance, y se dice |
| El expediente no tiene ajustes ni reclasificaciones | sigue: la hoja de ajustes lo dice expresamente, que es un resultado, no un fallo |
| Un epígrafe no cuadra con la suma de sus cuentas | sigue y lo marca en Comprobaciones: esa línea no se desglosa por cuenta |
| El plan exportado no trae `SaldoAnterior` | **para el papel de patrimonio neto**: sin la apertura no hay estado de cambios. El de estados financieros sale igual |
| La apertura no es el patrimonio neto que cerró el ejercicio anterior | sigue y lo marca en rojo: el ejercicio abre con un patrimonio distinto del que cerró, y eso se explica o se investiga |
| El cliente no usa los grupos 8 y 9 | sigue: lo dice en Comprobaciones como «A tener en cuenta», y avisa de que el estado de ingresos y gastos reconocidos hay que construirlo con el auditor |
| `CuadroFinanciacion` viene vacía | **para el papel de flujos**: es un modelo de pymes y no lleva estado de flujos. Se dice y no se ofrece nada más |
| El cuadro está a cero en todas sus líneas | **para**: el estado no se ha hecho |
| El cuadro tiene cifras pero ningún ajuste aprobado | sigue y lo marca como «SIN HACER», en ámbar arriba del todo: es la aritmética de Gesia sin el criterio del auditor, y cuadra igual. Al entregar, la línea de que el estado no está hecho; y la propuesta sale sola |
| Un ajuste aprobado descuadra (cobros ≠ pagos) | sigue y lo marca en rojo: el módulo tiene un «Descuadre» que debería estar a cero |
| Ninguna plantilla del catálogo encaja con una regla verificada | sigue: el papel sale con la hoja Catalogo, que ya es útil, y lo dice |
| La propuesta no coincide con un ajuste que el auditor ya aprobó | sigue y lo marca en rojo: manda lo del auditor, y la diferencia se entiende antes de tocar nada |
| El resultado del ejercicio anterior fue pérdida | no se propone la distribución: esa variante no está calibrada contra ningún expediente. La regla sale como «NO aplicada» con ese motivo |
| Una plantilla tiene la forma de una regla pero la cuenta de la que sale el importe está a cero o no está en el plan | no se propone, y la regla lo dice con el motivo en la consola, en «Regla y motivo» del `Catalogo` y en `Comprobaciones`, aparte de las plantillas sin regla |
| `sellar_uso_ia` dice que no hay huecos | el papel ya estaba sellado o no es el que escribió el script: no lo repitas, dilo |
| `sellar_uso_ia` dice que no tiene constancia de lo facilitado | o no se sirvió nada por el plugin, o el MCP se reinició a mitad: el papel lo dice y remite a `RegistroEmision.jsonl`; cuéntaselo al auditor tal cual |

---

## Comprobar que el skill funciona

```bash
python "$SKILL/scripts/probar_eeff.py"
```

Comprobaciones puras sobre los cuadres, los signos de presentación y la agregación por
epígrafe, sin tocar ningún expediente. Calibrado contra dos expedientes reales terminados, uno
de modelo normal y otro de reducido: en ambos el balance cuadra en los cinco ejercicios y la
cadena del saldo cuadra en todas las cuentas.
