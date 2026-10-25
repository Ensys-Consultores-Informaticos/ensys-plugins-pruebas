---
name: continuidad-saldos-gesia
description: >
  Prueba de continuidad de saldos de apertura de un expediente de auditoría de
  Gesia. Compara cuenta por cuenta la apertura del diario normalizado (.smn) con
  los saldos finales auditados del ejercicio anterior (.gs3), al nivel de
  auditoría del expediente, y produce el papel de trabajo en Excel.
  Usa este skill cuando el usuario pida comprobar o cuadrar los saldos de
  apertura, la continuidad de saldos, la prueba de apertura, el AG)02, o diga
  cosas como "cuadra la apertura", "comprueba los saldos de apertura", "prueba
  de continuidad", "revisa que la apertura casa con el cierre auditado" o
  "saldos iniciales del ejercicio".
  NO es el cuadro de mando del diario ni el cuestionario de la memoria.
  Requiere Gesia abierto con el servidor API arrancado, un expediente con al
  menos dos ejercicios y diario importado.
---

# Continuidad de saldos de apertura (Gesia)

Compara lo que el cliente ha abierto con lo que quedó auditado al cierre
anterior. La diferencia es el hallazgo; cero en todas las cuentas es el
resultado esperado.

Los ficheros se escriben en `<expediente>\AsistenteIA\ContinuidadSaldos\` y
**nunca se publican** en ninguna URL: son la contabilidad de un cliente
auditado.

---

## Cinco reglas que gobiernan todo

**1. El asiento de apertura no se adivina.** Se fija al normalizar el diario y no
tiene que ser el número 1 —en el expediente de calibración era el 3495—. Vive en la tabla
`CfgNormalizacion` del `.smn`, en el registro `FiltroDeApertura`. Si ese filtro
no se puede leer o trae un operador desconocido, **el skill para**. Elegir el
asiento por intuición da un resultado plausible y falso.

**2. La comparación va al nivel de auditoría del expediente que se audita,** no
al del papel del año pasado ni al desglose del cliente. Y ese nivel **no es un
número fijo de dígitos**: en el expediente de calibración hay 204 cuentas de
máximo nivel a 3 dígitos y 234 a 4. Cada cuenta del diario se asigna a la cuenta de máximo nivel
cuyo código sea **el prefijo más largo** que exista.

**3. Solo grupos 1 a 5.** Los grupos 6 y 7 se regularizan contra resultados y no
tienen saldo de apertura; el 0, el 8 y el 9 quedan fuera. En el expediente eso es
`CodigoTipo = 'B'`, que es más fiable que mirar el primer dígito.

**4. Una cuenta a cero en los dos lados no sale en el papel.** Son cuentas del
plan que el cliente no usa —389 de 438 en el expediente de calibración— y solo
estorban. El
recuento de omitidas se dice en pantalla: el recorte no es silencioso.

**5. A la herramienta solo va lo que la prueba necesita.** El diario **no se sube
nunca entero**: se exportan el filtro de apertura y el asiento de apertura —unas
cientos de líneas, con seis columnas y los terceros seudonimizados— y nada más. Y
el papel deja constancia de qué se facilitó y cómo en su hoja «Uso de IA».

---

## Dónde están los scripts

Al cargarse, el runtime indica el **directorio base del skill**. Las rutas
`scripts/…` son relativas a él, no al directorio de trabajo:

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(mktemp -d "${TMPDIR:-/tmp}/continuidad-XXXX")" && echo "$TRABAJO"
```

**Un directorio de trabajo nuevo en cada ejecución**, con el nombre del skill: nunca el de
otra ejecución ni el de otro skill, que pueden traer ficheros de otro expediente con el
mismo nombre. **No hagas `cd` dentro**: todas las rutas van como `"$TRABAJO/<fichero>"`, y así
se puede borrar al final desde fuera. **Anota la ruta que imprime**: si el entorno no conserva
variables entre llamadas, vuelve a escribir `TRABAJO="<esa ruta>"` al principio de cada orden
—y lo mismo `SKILL`—, sin crear otro. Esa ruta anotada es también la que se borra al final,
escrita literal (paso 6).

`consulta_apertura.py` (la consulta del asiento de apertura), `verificar_contrato.py`,
`comparar.py` y `generar_papel.py`. Más `probar_hallazgos.py`, el arnés.

---

## Secuencia

### Paso 1 — Expediente

```
configurar(perfil = "continuidad-saldos")   # primero: lista blanca y terceros seudonimizados
contexto_expediente()                       # siempre, aunque ya lo tengas de antes
```

**Lo primero, antes de leer nada: `configurar(perfil = "continuidad-saldos")`.** Con el perfil, el
MCP retira de lo que exporta las columnas que este skill no necesita y **seudonimiza los nombres
de terceros** en todo lo que devuelve: verás `PROV 40000012` o `CLI 43000007` donde iría la razón
social. El nombre no sale del equipo del auditor —ni al contenedor ni a este chat—; el papel lo
recupera al final con `rehidratar`. Trabaja y habla **por cuenta y por token**: «la apertura de
PROV 40001013 no cierra». **Nunca preguntes al auditor a quién corresponde un token ni lo
adivines** por el concepto o por los importes: él lo lee en el papel. Si `configurar()` dice
`nombres_terceros: en claro — forzado por el auditor`, es que lo ha apagado él; no lo
vuelvas a encender tú.

El perfil marca también **el comienzo del procedimiento**: desde ahí el MCP lleva la cuenta de
lo que facilita a la herramienta, que es lo que el papel dirá en su hoja «Uso de IA».

**Y después de `configurar`, llama SIEMPRE a `contexto_expediente()`**, aunque ya lo tengas de
antes en la conversación: lo que se leyó con otro perfil no cuenta como facilitado para este
papel, y la hoja «Uso de IA» lo listaría mal.

Luego, los ejercicios del expediente:

```
consultar_gesia(sql = "SELECT CodigoAuditoria, [Año], FechaAuditoria FROM Auditorias
                       ORDER BY [Año] DESC")
```

**De estas dos lecturas salen los huecos de los ejemplos de abajo, y ninguno se escribe de
memoria ni se copia de un ejemplo**: el ejercicio auditado no es siempre el del año pasado.

| Hueco | Qué es | De dónde sale |
|---|---|---|
| `<ejercicio>` | el ejercicio que se audita | `Año` de la fila de `Auditorias` cuya `FechaAuditoria` es la `FechaCierre` de `contexto_expediente` —la más reciente— |
| `<ejercicio anterior>` | el del cierre auditado con el que se compara | `Año` de la fila inmediatamente anterior en esa lista |
| `<anterior>` | el `CodigoAuditoria` de ese ejercicio anterior | la misma fila. Es un orden interno, **no un año**: no lo calcules sumando uno |
| `<FechaCierre>` | la fecha de la cabecera del papel | `FechaCierre` de `contexto_expediente`, sin la hora (`dd/mm/aa`) |
| `<razón social>` | el cliente | `RazonSocialCliente` de `contexto_expediente` |

Si `Auditorias` no tiene una fila anterior a la del ejercicio, **para**: no hay cierre auditado
con el que comparar.

**Si `configurar` avisa de que otra conversación está trabajando con otro expediente o perfil**
en el mismo servidor, **para**: díselo al auditor tal cual y no sigas hasta que confirme que esa
otra conversación ha terminado. Las dos comparten el MCP y se pisan el expediente, el perfil y
la cuenta de lo facilitado.

Si falta `gs3_file`, **pide la ruta**. Si el servidor API no responde, llama a
`arrancar_api`. Si el expediente no tiene diario importado, **para**: sin diario no
hay apertura que comparar, y eso no se arregla indicando otra ruta.

### Paso 2 — Exportar lo que la prueba necesita, y solo eso

Son tres ficheros, y **ninguno se abre**: los leen los scripts. Tú solo ves cuántas filas
ha escrito cada uno.

**El único diario válido es el que el expediente tiene vinculado**, el que declara
`configurar`. En la carpeta puede haber otros `.smn` —dos o cuarenta, es normal— y **no se
miran**: ni se listan, ni se comparan fechas, ni se ofrecen como alternativa. Medido en
cliente el 23/08/2026: un expediente tenía dos `.smn` que daban resultados contradictorios,
uno perfecto y otro con un hallazgo de 4,78 M€. Si el resultado sorprende, la pregunta es si
lo que Gesia tiene vinculado es lo que el auditor cree, y eso se arregla en Gesia
reimportando. Solo si **el usuario dice que el vinculado no vale** y señala otro se usa el
suyo, y el papel lo hace constar.

<!-- solo-cowork:export -->
#### En Cowork: dónde se exporta y cómo llega a los scripts (en local no aplica)

El MCP corre en el equipo del auditor y los scripts en el contenedor de la nube, así que
**no comparten disco**. La receta es fija: exportar dentro de la carpeta conectada, en una
subcarpeta de trabajo de su raíz, `_tmp_cowork` —**nunca en `AsistenteIA`**, donde van los
papeles que se archivan—; subirla con `device_stage_files`; y copiar lo subido a `$TRABAJO`,
porque `/mnt/user-data/uploads` es de solo lectura. El staging cuelga los ficheros de una
subcarpeta con el nombre de la carpeta conectada:

```bash
# tras device_stage_files de <raíz conectada>/_tmp_cowork/<fichero>
cp "/mnt/user-data/uploads/<carpeta conectada>/_tmp_cowork/filtro.json" "$TRABAJO/filtro.json"
```

**Uno a uno y por su nombre exacto** —`filtro.json`, `cierre.json`, `apertura.json`—, nunca
con un comodín: en `_tmp_cowork` puede haber lo exportado por otro procedimiento.

**Si `device_stage_files` falla por permisos** («can't be read without a grant…»), llama a
`device_request_folder_access` con la raíz de la carpeta conectada y repite la subida **una
vez**. Si vuelve a fallar, **para** y díselo al auditor con el mensaje tal cual: sin la subida
los scripts no tienen nada que leer.

Si la carpeta conectada **es** el expediente, `_tmp_cowork\` queda en su raíz, fuera de
`AsistenteIA`, y `limpiar_exportaciones(procedimiento = "continuidad-saldos")` lo borra al final. Dile al auditor que ahí ha habido
datos del cliente hasta el borrado, por si el expediente se sincroniza a la nube.

En los ejemplos de abajo, `<EXPORT>` es `<raíz conectada>/_tmp_cowork` para el MCP, y los
scripts leen la copia de `$TRABAJO`. **El filtro se sube antes que lo demás**, porque
`consulta_apertura.py` lo necesita para dar la consulta del asiento.
<!-- /solo-cowork -->

**2a · El cierre auditado del ejercicio anterior**, del expediente:

```
exportar_consulta(
  sql = "SELECT ca.Cuenta, c.Nombre, ca.SaldoAuditoria
         FROM CuentasAuditorias AS ca LEFT JOIN Cuentas AS c ON ca.Cuenta = c.Cuenta
         WHERE ca.CodigoAuditoria = '<anterior>'
           AND ca.MaximoNivel = True AND ca.CodigoTipo = 'B'",
  ruta = "<EXPORT>/cierre.json")
```

`<anterior>` es el `CodigoAuditoria` del ejercicio anterior, de la tabla del paso 1: un
orden interno, **no un año**, así que no lo calcules sumando uno.

**2b · El filtro de apertura**, del diario. Esta consulta, **tal cual**:

```
exportar_consulta(
  fuente = "diario",
  sql = "SELECT Datos FROM CfgNormalizacion WHERE Trim(Concepto) = 'FiltroDeApertura'",
  ruta = "<EXPORT>/filtro.json")
```

**2c · La consulta del asiento de apertura**, que no se escribe a mano: la da el script a
partir del filtro. Mira antes si el diario trae el campo `APERTURA`, que es una opción de
importación:

```
columnas(fuente = "diario", tabla = "Diario")
```

```bash
python "$SKILL/scripts/consulta_apertura.py" --filtro "$TRABAJO/filtro.json"
# y si columnas() no lista APERTURA:
python "$SKILL/scripts/consulta_apertura.py" --filtro "$TRABAJO/filtro.json" --sin-campo-apertura
```

Salida `2` → **para**: el filtro no se puede leer o trae un operador desconocido, y el asiento
de apertura no se adivina. Salida `0` → imprime una línea `SQL: …`.

**2d · El asiento de apertura**, con **esa consulta copiada exactamente**, sin quitarle ni
añadirle nada:

```
exportar_consulta(fuente = "diario", sql = "<la línea SQL: de consulta_apertura.py>",
                  ruta = "<EXPORT>/apertura.json")
```

Trae seis columnas, el campo `APERTURA` si existe y `POR_FILTRO`, que es el filtro de apertura
ya evaluado en el equipo del auditor. Son las líneas del asiento de apertura y nada más: si
`exportar_consulta` dice que ha escrito decenas de miles de filas, algo va mal y **paras**.

Cuando el MCP y los scripts comparten disco —en la máquina del auditor—, `<EXPORT>` es
`$TRABAJO` mismo: se exporta ahí y los scripts leen de ahí, sin subir ni copiar nada.

### Paso 3 — Verificar el contrato (puede abortar)

```bash
python "$SKILL/scripts/verificar_contrato.py" --filtro "$TRABAJO/filtro.json" \
    --apertura "$TRABAJO/apertura.json" --cierre "$TRABAJO/cierre.json" \
    --ejercicio "<ejercicio>" --ejercicio-anterior "<ejercicio anterior>" --cliente "<razón social>"
```

Salida `2` → **para**, no se genera nada. Salida `1` son avisos: léelos y
**cuéntalos al entregar**, porque cambian lo que el papel puede concluir. Los dos
que más importan: que el campo `APERTURA` no coincida con el filtro (suele
significar que el filtro se cambió después de importar) y que la apertura traiga
cuentas de los grupos 6 y 7.

### Paso 4 — Comparar

```bash
python "$SKILL/scripts/comparar.py" --filtro "$TRABAJO/filtro.json" \
    --apertura "$TRABAJO/apertura.json" --cierre "$TRABAJO/cierre.json" \
    --ejercicio "<ejercicio>" --ejercicio-anterior "<ejercicio anterior>" --cliente "<razón social>" \
    --salida "$TRABAJO/resultado.json"
```

Imprime el resumen y los hallazgos. **No leas `resultado.json` entero**: el
resumen de pantalla ya trae lo que hay que contar.

Tres clases de hallazgo, y no son lo mismo:

| Tipo | Qué pasa |
|---|---|
| `diferencia` | la cuenta está en los dos lados y el importe no cuadra |
| `sin_apertura` | tenía saldo al cierre y el cliente no la ha abierto |
| `cuenta_nueva` | se ha abierto con saldo y el expediente no la reconoce a ningún nivel |

**Las diferencias que se compensan entre sí salen agrupadas** en el bloque `COMPENSAN`: dos
`diferencia` del mismo importe al céntimo y signo contrario —una 40 contra una 57, dos 43 entre
sí— son una **posible reclasificación al abrir**, y en el papel llevan la pareja en la columna G.
Es una marca, no una explicación: **siguen siendo diferencias**, cuentan como tales y no digas
que «se anulan» ni que «está bien». Solo se empareja cuando la pareja es **única**; si hay más
de una cuenta con ese importe en algún lado (dos +X y una −X), el grupo sale como `AMBIGUA`,
sin emparejar, y así se cuenta: no elijas tú la pareja. Las `sin_apertura` y las `cuenta_nueva`
no se emparejan nunca.

**Y mira el cuadre de control, que es la línea más importante de la salida.** La
apertura de balance tiene que sumar cero. Si no suma cero, lo que falta es
exactamente lo que se ha quedado fuera de la comparación —patas en cuentas de
resultados y cuentas no reconocidas— y el script lo desglosa. Si queda algo
**sin explicar**, no entregues el papel: hay algo que el skill no está
entendiendo.

Medido en el fixture de pruebas: descuadre de 383.333, que son 333.333 de una
cuenta 710 metida en el asiento de apertura más 50.000 de una cuenta nueva. Sin
esta comprobación el papel salía diciendo que la caja no cuadraba, sin mencionar
que había un ingreso dentro de la apertura.

### Paso 5 — El papel de trabajo

**Si el papel ya existe, pregunta antes de generarlo.** Mira si en
`<expediente>\AsistenteIA\ContinuidadSaldos\` ya hay un fichero con ese nombre<!-- solo-cowork:alt=. --> —en
Cowork, listando la carpeta conectada con `device_list_dir`; en local, en el disco—.<!-- /solo-cowork -->
Si lo hay, **pregunta al auditor** si lo sobrescribe o si guarda el nuevo con « (rehecho
AAAA-MM-DD)» antes de la extensión, con la fecha de hoy. Ni lo sobrescribas sin preguntar ni
inventes otro sufijo: al repetir un procedimiento el mismo día, una ejecución pisó el papel y otra
improvisó el nombre (registro del 21/10/2026). El nombre elegido es el de todo lo que sigue
—<!-- solo-cowork -->la bajada al expediente, <!-- /solo-cowork -->el sello y la recuperación de nombres—.<!-- solo-cowork --> En
Cowork, `device_commit_files` va **sin `force`**; solo si el auditor eligió sobrescribir y el
commit lo rechaza porque el fichero existe, repítelo con `force` y díselo.<!-- /solo-cowork -->

```bash
python "$SKILL/scripts/generar_papel.py" --resultado "$TRABAJO/resultado.json" \
    --fecha-cierre "<FechaCierre>" --generado "<fecha de hoy, dd/mm/aaaa>" \
    --salida "$TRABAJO/AG)02 Saldos de Apertura <CLIENTE> <ejercicio>.xlsx"
```

`--fecha-cierre` es como se escribe en la cabecera del papel: la `FechaCierre` de
`contexto_expediente` sin la hora, la del paso 1. `<CLIENTE>` es la razón social y
`<ejercicio>` el mismo del paso 3. `--generado` es la fecha de hoy, que conoces por tu
contexto. **Las pones tú**: nada en este skill lee el reloj.

La referencia es `AG)02` («ESTIMACIONES Y SALDOS APERTURA CONTABLES»), que es la
que tiene el expediente. `REF`, `Realizado` y `Verificado` van en blanco a
propósito: los rellena el auditor.

**El libro empieza por la hoja «Uso de IA»**: la evidencia de que el papel se hizo con una
herramienta de inteligencia artificial, de qué se le facilitó y de cómo debe verificarse. Los
apartados de la herramienta quedan con huecos que se rellenan al archivar (paso 6); los de
verificación, verificado por, efecto en la conclusión y revisión **son del equipo y salen en
blanco**. No escribas nada en ellos ni propongas texto para ellos.

<!-- solo-cowork:entrega -->
**En Cowork el script escribe en el directorio de trabajo del sandbox, no en el expediente**, así
que la ruta de destino no se cumple sola: hay que bajar el fichero. `--salida` va **siempre** a
`"$TRABAJO/<PAPEL>"`, como en el ejemplo: ni a la carpeta de salidas de la sesión
(`/mnt/user-data/outputs`) ni a otra ruta del contenedor (registro del 21/10/2026: se escribió
ahí directamente). Desde el directorio de trabajo se envía con `SendUserFile` **por su nombre
exacto** —el que pasaste a `--salida`, con la ruta anotada escrita literal, nunca
`"$TRABAJO"/*.xlsx`—, que devuelve un `fileUuid`, y `device_commit_files` con ese `fileUuid` lo
escribe en el disco del auditor:

```
device_commit_files → "<expediente>/AsistenteIA/ContinuidadSaldos/<PAPEL>"
```

**El papel bueno es el del expediente.** La copia que queda en el chat lleva los terceros en
código —seudonimizada— y sin sellar: no es la que se archiva.
<!-- /solo-cowork -->

**Si el expediente está en OneDrive, el entorno puede rechazar la escritura antes de ejecutar
nada** y pedir autorización expresa para escribir datos contables ahí. No es un fallo del skill:
pídesela al usuario y repite.

### Paso 6 — Archivar y entregar

Con el papel **ya en el disco del auditor**, en `<expediente>\AsistenteIA\ContinuidadSaldos\`,
dos llamadas sobre esa ruta de Windows, en este orden o en el contrario:

1. **`sellar_uso_ia(ruta = "<expediente>/AsistenteIA/ContinuidadSaldos/<fichero>", modelo =
   "<el modelo con el que trabajas>", procedimiento = "continuidad-saldos")`.** Rellena en la hoja «Uso de IA» lo que solo sabe la
   aplicación: herramienta y versiones, quién lo ejecutó, dónde corrieron los scripts y **qué
   información se facilitó y cómo**, según lo que el MCP ha servido desde el paso 1. En `modelo`
   pon el nombre y la versión que te da tu propio contexto; si no lo sabes, déjalo vacío. **Sin
   esta llamada el papel queda con huecos que dicen «pendiente»**: no se da por entregado.
2. **`rehidratar(ruta = …, leyenda = true)`.** Sustituye cada token por el nombre real, en
   local, y devuelve recuentos —ni un nombre vuelve aquí—. Con `leyenda = true` añade la hoja
   «Tokens» con la equivalencia. **Cuéntale al auditor los dos números que devuelve**
   (sustituciones y tokens distintos) y, si hay `tokens_sin_nombre`, dilos tal cual: son
   cuentas que el diccionario no conoce, no las completes tú.

Luego di dónde ha quedado el fichero, **cuántas cuentas lleva y cuántos hallazgos de cada
clase**. **Si `comparar.py` sacó el bloque `COMPENSAN`, dilo también**: cuántas parejas, cuáles
—cuenta contra cuenta, con el importe— como **posible reclasificación al abrir**, y los grupos
ambiguos tal cual, sin emparejarlos; todas siguen contando en las diferencias. Si no hay ningún
hallazgo, dilo así: la continuidad está comprobada y no hay diferencias. Con
este párrafo, y sin llamar «rehidratar» ni «sellar» a nada delante del auditor:

> *Papel generado y archivado en el expediente: `AsistenteIA\…\<fichero>`. Nombres de terceros
> recuperados en tu equipo: N sustituciones, M terceros distintos, ninguno sin nombre, y hoja
> «Tokens» con la leyenda. La hoja «Uso de IA» deja constancia de la herramienta y de lo que se
> le facilitó; la verificación, quién la hace, su efecto en la conclusión y la revisión están en
> blanco para el equipo, y mientras lo estén el papel no es evidencia de auditoría. Los
> extractos temporales están borrados.*

Si hubo tokens sin nombre, en vez de «ninguno sin nombre» van listados. <!-- solo-cowork:papel-unico -->La copia del chat
**siempre** está seudonimizada y sin sellar —viajó por el contenedor—: dilo, para que no la
confunda con el papel bueno.<!-- /solo-cowork -->

En `sellar_uso_ia`, `procedimiento` es el mismo nombre del perfil de `configurar`: con él el
sello lista lo que se facilitó **para este papel**, no lo de otra conversación que comparta el
servidor.

**Los temporales.** Lo que haya escrito `exportar_consulta` lo borra
`limpiar_exportaciones(procedimiento = "continuidad-saldos")`, y esa es la vía: funciona igual
en local y en Cowork —lo borra el MCP, que corre en la máquina del usuario— y no hay que decirle
qué fichero, porque borra lo que él escribió **para este procedimiento**. Lo exportado por otros
lo deja y lo resume en unas líneas: no lo borres tú, dilo tal cual. Si algo no se deja borrar
(un `.csv` abierto en Excel, típicamente), lo dice con su ruta: trasládala al usuario.

El directorio de trabajo va aparte, y se borra **desde fuera**, sin estar dentro de él:

```bash
rm -rf "<!-- solo-cowork:alt=<TRABAJO> --><la ruta que anotaste al crearlo, literal><!-- /solo-cowork -->"
```

<!-- solo-cowork -->**Con la ruta escrita tal cual, nunca con una variable ni con `$(cat …)`**: si el
entorno no conserva variables, `"$TRABAJO"` llega vacío, y el control de seguridad del entorno
bloquea un `rm -rf` sobre una expansión como `"$(cat …)"` (registro del 21/10/2026).

<!-- /solo-cowork -->Si no se deja borrar, **di la ruta exacta** de `$TRABAJO` y qué contiene —los extractos del
cliente y, si se escribió ahí, la copia del papel— para que el usuario lo quite. Nada de dejarlo caer: son datos
de su cliente.

---

## Lo que este skill no hace

- **No escribe en el expediente.** El MCP solo lee.
- **No sube el diario.** Solo el filtro y el asiento de apertura, con las columnas que la
  prueba usa.
- **No explica la diferencia**, solo la localiza. Si una cuenta no cuadra, por qué
  no cuadra lo averigua el auditor. Tampoco las que se compensan entre sí: las marca como
  posible reclasificación al abrir y siguen siendo diferencias.
- **No verifica su propio resultado por el equipo.** Propone qué contrastar; la verificación,
  quién la hace y su efecto en la conclusión los escribe el equipo en la hoja «Uso de IA».
- **No comprueba que el cierre anterior esté bien auditado.** Toma
  `SaldoAuditoria` del ejercicio anterior tal como está en el expediente, con sus
  ajustes ya incorporados.
- **No mira los grupos 6 y 7**, ni el 0, ni el 8, ni el 9.
- **No vale para un encargo inicial** tal cual: la NIA-ES 510 se aplica cuando el
  cierre anterior **no** lo auditamos nosotros, y entonces este cruce no es
  evidencia suficiente. El cálculo sirve igual; lo que cambia es qué puede
  concluir el papel.

## Degradación

| Situación | Qué sale |
|---|---|
| Sin diario importado | **para.** No hay apertura que comparar |
| Sin `CfgNormalizacion` o sin `FiltroDeApertura` | **para.** El asiento de apertura no se adivina |
| Operador de filtro desconocido | **para**, y dice cuál era |
| La apertura no cuadra | **para.** Con la apertura descuadrada la prueba no significa nada |
| Campo `APERTURA` inexistente | `consulta_apertura.py --sin-campo-apertura`; sigue con el filtro y avisa de que pierde la comprobación cruzada |
| Expediente con un solo ejercicio | **para.** No hay cierre anterior |
| Cuentas abiertas sin destino en el expediente | sigue, y las emite como hallazgo `cuenta_nueva` |
| La apertura de balance no cuadra | sigue, y el papel lo avisa arriba con el desglose |
| `sellar_uso_ia` dice que no hay huecos | el papel ya estaba sellado o no es el que escribió el script: no lo repitas, dilo |
| `sellar_uso_ia` dice que no tiene constancia de lo facilitado | o no se sirvió nada por el plugin, o el MCP se reinició a mitad: el papel lo dice y remite a `RegistroEmision.jsonl`; cuéntaselo al auditor tal cual |
