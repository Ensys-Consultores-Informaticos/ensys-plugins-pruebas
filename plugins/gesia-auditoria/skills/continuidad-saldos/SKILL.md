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

## Cuatro reglas que gobiernan todo

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

---

## Dónde están los scripts

Al cargarse, el runtime indica el **directorio base del skill**. Las rutas
`scripts/…` son relativas a él, no al directorio de trabajo:

```bash
SKILL="<directorio base indicado al cargar el skill>"
TRABAJO="$(pwd)/trabajo" && mkdir -p "$TRABAJO"
```

El diario se lee con `mdbtools` cuando existe —el caso de Cowork— y por el driver
ODBC de Access cuando no, que es el caso de la máquina del auditor. El script lo
decide solo y no hay que indicarle nada.

---

## Secuencia

### Paso 1 — Expediente

```
configurar(perfil = "continuidad-saldos")   # primero: lista blanca y nombres tokenizados
contexto_expediente()
```

**Lo primero, antes de leer nada: `configurar(perfil = "continuidad-saldos")`.** Con el perfil, el
MCP retira del extracto las columnas que este skill no necesita y **tokeniza los nombres de
terceros** en todo lo que devuelve: verás `PROV 40000012` o `CLI 43000007` donde iría la razón
social. El nombre no sale del equipo del auditor —ni al contenedor ni a este chat—; el papel lo
recupera al final con `rehidratar`. Trabaja y habla **por cuenta y por token**: «la apertura de
PROV 40001013 no cierra». **Nunca preguntes al auditor a quién corresponde un token ni lo
adivines** por el concepto o por los importes: él lo lee en el papel. Si `configurar()` dice
`nombres_terceros: en claro — forzado por el auditor`, es que lo ha apagado él; no lo
vuelvas a encender tú.

Si falta `gs3_file`, **pide la ruta**. Si el servidor API no responde, dile que lo
arranque en *Herramientas > Gesia - Cuadro de mando > Arrancar servidor API*. Si
el expediente no tiene diario importado, **para**: sin diario no hay apertura que
comparar, y eso no se arregla indicando otra ruta.

### Paso 2 — El cierre auditado del ejercicio anterior

El `.gs3` es un `.mdb` con contraseña y **solo se lee por el API**, así que este
dato no se puede leer desde el contenedor.

**Se exporta a fichero, no se trae al contexto.** `exportar_consulta` ejecuta la
consulta y deja el resultado en disco; tú solo ves cuántas filas ha escrito. Son
unas 440 y antes costaban del orden de 7.000 tokens al traerlas y otros tantos al
volver a escribirlas.

```
exportar_consulta(
  sql = "SELECT ca.Cuenta, c.Nombre, ca.SaldoAuditoria
         FROM CuentasAuditorias AS ca LEFT JOIN Cuentas AS c ON ca.Cuenta = c.Cuenta
         WHERE ca.CodigoAuditoria = '<anterior>'
           AND ca.MaximoNivel = True AND ca.CodigoTipo = 'B'",
  ruta = "<TEMP>/gesia-continuidad/cierre.json")
```

El `CodigoAuditoria` es un orden interno, **no un año**: sácalo de `Auditorias`
por el campo `Año` y no lo calcules sumando uno.

**No abras ese fichero.** Los scripts lo leen tal cual: aceptan las filas crudas
del export y solo necesitan que les digas los ejercicios, que la consulta no trae.

### Paso 3 — El diario

**El único diario válido es el que el expediente tiene vinculado**, el que declara
`configurar` / `DatosAuditoria`. No hay nada que decidir: se usa ese.

En la carpeta puede haber otros `.smn` —dos o cuarenta, es normal— y **no se
miran**. Ni se listan, ni se comparan fechas, ni se ofrecen como alternativa. Que
uno parezca más nuevo o tenga mejor pinta no lo convierte en el diario del
encargo.

Dos excepciones, y solo dos:

- **No hay diario vinculado** → **para**. Sin diario no hay apertura que comparar,
  y no se arregla cogiendo un `.smn` parecido de la carpeta. La única salida es que
  el usuario aporte el diario en ese momento: pídeselo.
- **El usuario dice que el vinculado no vale** y señala otro → se usa el que él
  diga, y el papel de trabajo deja constancia de que no es el vinculado.

Por qué se insiste tanto: medido en cliente el 23/08/2026, un expediente tenía dos
`.smn` que **daban resultados contradictorios** — con uno la apertura salía
perfecta y con el otro aparecía un hallazgo de 4,78 M€. Si el resultado sorprende,
la pregunta no es «¿habrá otro fichero mejor?», es si lo que Gesia tiene vinculado
es lo que el auditor cree. Y eso se arregla en Gesia reimportando, no eligiendo
otro fichero aquí.

En la máquina del auditor no hay nada más que hacer: los scripts abren el `.smn`
donde está, por ODBC.

<!-- solo-cowork:alt=Los ficheros que dejes con `exportar_consulta` escríbelos en `<TEMP>/gesia-continuidad` o en el directorio de trabajo, **nunca en la carpeta del expediente**, y bórralos al terminar. -->En Cowork hay que subirlo, y **comprimido, porque directo no pasa**: el
presupuesto de transferencia de `device_stage_files` es de unos 50 segundos y un
diario de un ejercicio completo no cabe. Medido: 6,98 MB no pasan, y comprimidos
son 1,17 MB, que sí.

**Y tiene que quedar dentro de una carpeta conectada a la sesión**, porque
`device_stage_files` no puede subir un fichero que esté fuera de ellas — el
`$TEMP` de Windows no lo está. Corregido el 27/08/2026: antes este bloque
comprimía a `$TEMP` y así no se puede subir. Ver `docs/arquitectura.md`.

```bash
# en la maquina del usuario, dentro de la carpeta conectada pero FUERA del
# expediente: una subcarpeta de trabajo en su raiz
mkdir -p "<raíz conectada>/_tmp_cowork"
gzip -c "<smn_file>" > "<raíz conectada>/_tmp_cowork/diario.smn.gz"
```

**Y no en `AsistenteIA`.** Ahí van los papeles de trabajo, y un `.gz` con el
diario del cliente al lado del papel firmado no es un descuido estético: es
contabilidad ajena en la carpeta que el auditor archiva. De ahí la subcarpeta de
trabajo en la raíz de lo conectado, que **se borra al terminar** — la carpeta
temporal del sistema se limpiaba sola, y esta no.

Luego `device_stage_files` con esa ruta y, en el sandbox:

```bash
which mdb-export || apt-get install -y mdbtools
gunzip -c "<staged>/diario.smn.gz" > "$TRABAJO/diario.mdb"
```

**Y al terminar se borran**, en el paso de entrega. Lo mismo vale para cualquier
fichero que dejes con `exportar_consulta`: escríbelo en `$TEMP/gesia-continuidad`
o en el directorio de trabajo, nunca en la carpeta del expediente.<!-- /solo-cowork -->

### Paso 4 — Verificar el contrato (puede abortar)

```bash
python "$SKILL/scripts/verificar_contrato.py" --diario "<diario>" \
    --cierre "<TEMP>/gesia-continuidad/cierre.json" \
    --ejercicio 2025 --ejercicio-anterior 2024 --cliente "<razón social>"
```

Salida `2` → **para**, no se genera nada. Salida `1` son avisos: léelos y
**cuéntalos al entregar**, porque cambian lo que el papel puede concluir. Los dos
que más importan: que el campo `APERTURA` no coincida con el filtro (suele
significar que el filtro se cambió después de importar) y que la apertura traiga
cuentas de los grupos 6 y 7.

### Paso 5 — Comparar

```bash
python "$SKILL/scripts/comparar.py" --diario "<diario>" \
    --cierre "<TEMP>/gesia-continuidad/cierre.json" \
    --ejercicio 2025 --ejercicio-anterior 2024 --cliente "<razón social>" \
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

### Paso 6 — El papel de trabajo

```bash
python "$SKILL/scripts/generar_papel.py" --resultado "$TRABAJO/resultado.json" \
    --fecha-cierre "31/12/25" \
    --salida "<expediente>/AsistenteIA/ContinuidadSaldos/AG)02 Saldos de Apertura <CLIENTE> <EJERCICIO>.xlsx"
```

`--fecha-cierre` es como se escribe en la cabecera del papel y **lo pones tú**:
nada en este skill lee el reloj. Sale de `FechaCierre` de `contexto_expediente`.

La referencia es `AG)02` («ESTIMACIONES Y SALDOS APERTURA CONTABLES»), que es la
que tiene el expediente. `REF`, `Realizado` y `Verificado` van en blanco a
propósito: los rellena el auditor.

### Paso 7 — Entregar

Di dónde ha quedado el fichero, **cuántas cuentas lleva y cuántos hallazgos de
cada clase**. Si no hay ninguno, dilo así: la continuidad está comprobada y no
hay diferencias. Y recuérdale que:

- el papel es una propuesta y la revisión y la firma son suyas;

**Los nombres.** El fichero se ha escrito con tokens. Cuando ya esté en el disco del auditor
—en Cowork, después de bajarlo al expediente; en local, directamente—, llama a
`rehidratar(ruta = "<expediente>/AsistenteIA/…/<fichero>", leyenda = true)`: sustituye cada
token por el nombre real, en local, y devuelve recuentos —ni un nombre vuelve aquí—. Con
`leyenda = true` añade la tabla token → nombre (hoja «Tokens» en el Excel), para que lo que
has dicho en el chat con tokens se pueda leer en el papel. **Cuéntale al auditor los dos
números que devuelve** (sustituciones y tokens distintos) y, si hay `tokens_sin_nombre`,
dilos tal cual: son cuentas que el diccionario no conoce, no las completes tú.

Con este párrafo, y sin llamar «rehidratar» a nada delante del auditor —para él es
**desanonimizar**—:

> *Papel generado y archivado en el expediente: `AsistenteIA\…\<fichero>` (también lo tienes
> en el chat, aunque esa copia está anonimizada). Nombres ya desanonimizados: N sustituciones,
> M terceros distintos, ninguno sin nombre, y hoja «Tokens» con la leyenda. El extracto
> temporal está borrado.*

Si hubo tokens sin nombre, en vez de «ninguno sin nombre» van listados. <!-- solo-cowork:papel-unico -->La copia del chat
**siempre** está anonimizada —viajó por el contenedor—: dilo, para que no la confunda con el
papel bueno.<!-- /solo-cowork -->

**Los temporales.** Lo que haya escrito `exportar_consulta` lo borra
`limpiar_exportaciones()`, y esa es la vía: funciona igual en local y en Cowork
—lo borra el MCP, que corre en la máquina del usuario— y no hay que decirle qué
fichero, porque borra lo que él escribió. Si algo no se deja borrar (un `.csv`
abierto en Excel, típicamente), lo dice con su ruta: trasládala al usuario.

El directorio de trabajo va aparte, y ahí sí puede fallar el borrado en Cowork
—el puente no tiene permiso en el equipo del usuario, comprobado el 25/08/2026—:

```bash
rm -rf "$TRABAJO"
```

Si falla, **di las rutas exactas** de lo que queda para que el usuario lo quite.
Nada de dejarlo caer: son datos de su cliente. Por eso, además, los temporales
van a la carpeta temporal del sistema y no al expediente — ahí los limpia
Windows y no estorban entre los papeles de trabajo.

---

## Lo que este skill no hace

- **No escribe en el expediente.** El MCP solo lee.
- **No explica la diferencia**, solo la localiza. Si una cuenta no cuadra, por qué
  no cuadra lo averigua el auditor.
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
| Campo `APERTURA` vacío | sigue con el filtro, y avisa de que pierde la comprobación cruzada |
| Expediente con un solo ejercicio | **para.** No hay cierre anterior |
| Cuentas abiertas sin destino en el expediente | sigue, y las emite como hallazgo `cuenta_nueva` |
| La apertura de balance no cuadra | sigue, y el papel lo avisa arriba con el desglose |
