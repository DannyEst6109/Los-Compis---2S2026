# Persona 3: control de flujo, clases, herencia, excepciones e integración

Este documento describe cómo se traducen a MIPS las estructuras que cambian
el flujo de ejecución (saltos, ciclos, `switch`, `try/catch`) y las de
objetos (clases, atributos, métodos, herencia), y cómo se integran todas las
partes del generador para producir el archivo `.asm` final. La convención de
llamadas y registros que se respeta aquí está en [NOTAS.md](../NOTAS.md) y
[REGISTROS_ACTIVACION.md](REGISTROS_ACTIVACION.md).

> **Regla principal:** el MIPS se genera **sólo a partir del TAC** del
> Proyecto 2. `mips_generator.py` recibe el `TACProgram` y la tabla de
> símbolos con direcciones; nunca vuelve a mirar el código fuente ni el AST.

| Módulo | Contenido |
| --- | --- |
| `src/mips_control.py` | `label`, `goto`, `if`, `ifFalse` |
| `src/mips_objects.py` | `new`, `o.f`, `o.f = x`, `method o.m`, vtables y tablas de miembros |
| `src/mips_exceptions.py` | `try_begin`, `try_end`, `e = exception` |
| `src/mips_runtime.py` | Errores en tiempo de ejecución, `p3_throw`, `p3_lookup`, etiquetas locales |
| `src/mips_generator.py` | Integración: recorre el TAC, arma el archivo y aplica la mirilla |
| `src/mips_peephole_control.py` | Reglas de mirilla de control de flujo |
| `src/mars_runner.py` | Ejecución en MARS por línea de comandos |
| `src/compilar.py` | Compilador por línea de comandos |
| `src/ui_mips.py` | Pestañas «MIPS» y «Ejecución» del IDE |

## 1. Integración del generador

```text
              Código Compiscript (IDE o compilar.py)
                              |
                              v
      Análisis léxico, sintáctico y semántico (Lab. 1 y Proyecto 1)
                              |   ¿hay errores? -> se muestran todos; no hay TAC ni MIPS
                              v
                 TAC + tabla de símbolos con direcciones (Proyecto 2)
                              |
                              v
                        MipsGenerator
                              |
   +-----------+----------+---+-------+------------+-------------+
   v           v          v           v            v             v
Funciones   Básicas    Control     Objetos     Excepciones   Registros
Persona 1   Persona 2  Persona 3   Persona 3   Persona 3     Persona 2
   |           |          |           |            |             |
   +-----------+----------+-----------+------------+-------------+
                              |
                              v
        .data (área global, clases, manejadores, cadenas)
        .text (main primero, funciones, rutinas de soporte)
                              |
                              v
         Optimización por mirilla (Persona 2 + Persona 3, hasta punto fijo)
                              |
                              v
               Archivo .asm  ->  MARS (IDE, compilar.py o a mano)
```

`compiler.compile_source` ejecuta todo el pipeline. Garantías:

- **No se genera MIPS si hay errores anteriores.** Si alguna fase reporta
  diagnósticos, `result.tac` y `result.mips` quedan en `None`.
- **Se usa el TAC correcto.** `generate_mips(tabla, tac)` recibe exactamente
  el `TACProgram` que se muestra en la pestaña «TAC». La prueba
  `test_assembly_is_generated_from_the_tac` cambia una constante del TAC y
  verifica que el MIPS cambie.
- **Archivo completo.** `.data` con el área global, las vtables y tablas de
  miembros, el estado de los manejadores y las cadenas (éstas al final,
  porque se registran mientras se traduce); `.text` con `main` primero
  (MARS empieza en la primera instrucción), cada función completa y las
  rutinas de soporte que se usaron.
- **Compatibilidad entre componentes.** Un único `MipsRegisters` por
  programa, compartido por todos los traductores; las líneas de cada parte
  se devuelven sin sangría y la sangría la pone `format_assembly`.
- **Errores de generación reportados.** Cualquier `MipsFrameError` (de
  Persona 1, 2 o 3) se convierte en un diagnóstico de tipo «Generación» con
  la línea de la instrucción TAC que lo produjo; un fallo interno inesperado
  también se reporta en lugar de cerrar el IDE. No se entrega MIPS parcial.

Recorrido del TAC (`MipsGenerator.generate`):

| Instrucción TAC | Quién la traduce |
| --- | --- |
| `begin_func`, `end_func`, `param`, `call`, `return` | `FunctionTranslator` (Persona 1) |
| `=`, aritméticas, relacionales, `not`, `minus`, `concat`, arreglos, `print` | `BasicTranslator` (Persona 2) |
| `label`, `goto`, `if`, `ifFalse` | `ControlFlowTranslator` |
| `new`, `o.f`, `o.f = x`, `method o.m` | `ObjectTranslator` |
| `try_begin`, `try_end`, `exception` | `ExceptionTranslator` |

Antes de cada instrucción se escribe su texto TAC como comentario
(`# t1 = x > 10`), así el `.asm` se puede leer junto con la pestaña «TAC».

## 2. Sentencias de control

El TAC ya reduce `if/else`, `while`, `do-while`, `for`, `foreach`,
`switch/case`, `break`, `continue`, `&&`, `||` y `?:` a etiquetas y saltos
([CONTROL_FLUJO.md](CONTROL_FLUJO.md)). Cada salto se traduce así:

| TAC | MIPS |
| --- | --- |
| `L:` | guardar registros modificados, `L:`, olvidar asociaciones |
| `goto L` | guardar registros, `j L`, olvidar asociaciones |
| `if c goto L` | `c` en un registro (`getReg`), guardar, `bne c, $zero, L` |
| `ifFalse c goto L` | `c` en un registro, guardar, `beq c, $zero, L` |

- **Por qué guardar antes de saltar.** A una etiqueta pueden llegar varios
  caminos, cada uno con valores distintos en los registros. Si todo salto
  deja la memoria al día, en la etiqueta se puede empezar sin asociaciones.
- **Después de un salto condicional no se olvidan las asociaciones**: el
  camino que sigue de largo tiene los mismos registros, ya limpios.
- **Condiciones constantes** (`if false goto L`, que aparece en
  `do { } while (false)`) se resuelven al compilar.
- **Anidamiento, `break` y `continue`**: las etiquetas TAC son únicas en todo
  el programa, así que los ciclos y condiciones anidados no necesitan nada
  especial; `break` y `continue` ya son `goto` a la etiqueta de salida o de
  continuación del ciclo correcto.

Ejemplo real de `if (x > 10) { y = 1; } else { y = 2; }`:

```mips
    # t1 = x > 10
    move $t7, $t1
    li   $t8, 10
    slt  $t7, $t8, $t7
    move $t4, $t7
    # if t1 goto L1
    sw   $t3, 4($gp)
    sw   $t1, 0($gp)
    sw   $t4, 8($gp)
    beq  $t4, $zero, L2        # mirilla: era «bne $t4, $zero, L1» + «j L2» + «L1:»
    # y = 1
    ...
    j    L3
L2:
    # y = 2
    ...
L3:
```

## 3. Clases y objetos

### Representación en memoria

La distribución de cada clase viene del Proyecto 2 (`ClassLayout`): el
desplazamiento 0 guarda el puntero a la vtable y cada atributo tiene un
desplazamiento fijo. `new C` reserva el objeto en el heap con `sbrk`
(`syscall` 9):

```text
  o - S  ┌────────────────────────┐
         │ etiquetas de impresión │  1 byte por atributo, en -(off + 1)(o)
  o ───► ├────────────────────────┤
         │ puntero a la vtable    │  0(o)
         │ atributos              │  off(o)   lw/sw (lbu/sb si es boolean)
  o + S  └────────────────────────┘           S = ClassLayout.size
```

- Las **etiquetas de impresión** (número, texto o nulo) son las mismas que
  usa Persona 2 para que `print` sepa mostrar un valor. Se guardan en bytes
  aparte, en una posición que sólo depende del desplazamiento del atributo:
  así un atributo heredado tiene su etiqueta en el mismo lugar en todas las
  subclases.
- `new` marca como `null` los atributos de tipo referencia (cadenas,
  arreglos, objetos); los numéricos empiezan en 0.
- `new C(args)` en el TAC es: `t = new C`, una llamada a cada inicializador
  de atributos (`C.$init`) desde la raíz de la jerarquía y la llamada al
  constructor vigente. Las llamadas usan la secuencia de Persona 1, con el
  objeto como primer argumento (`this`).

```mips
    # t1 = new Contador
    li   $a0, 16             # etiquetas + datos (2 × 8 bytes)
    li   $v0, 9
    syscall
    addiu $v0, $v0, 8        # el objeto empieza después de las etiquetas
    la   $t9, p3_vt_Contador
    sw   $t9, 0($v0)         # puntero a la vtable
    move $t0, $v0            # t1 = objeto (getReg)
```

### Atributos y métodos

| TAC | MIPS (clase estática conocida) |
| --- | --- |
| `t = o.f` | verificar `o ≠ null`; `lw $t9, off(o)`; `lbu $a3, -(off+1)(o)`; `t = $t9` con etiqueta `$a3` |
| `o.f = x` | verificar `o ≠ null`; `x` en `$t9` y su etiqueta en `$a3`; `sw $t9, off(o)`; `sb $a3, -(off+1)(o)` |
| `t = method o.m` | verificar `o ≠ null`; `lw $t9, 0(o)`; `lw $t9, 4·i($t9)`; `t = $t9` |

- **`this`** es el parámetro implícito de cada método (casilla `this` del
  marco, Persona 1). Nunca es nulo, así que con `this` no se verifica.
- **Objeto nulo**: cualquier otro acceso verifica el puntero y, si es 0,
  lanza «Acceso a un objeto nulo», que un `try/catch` puede atrapar.
- **Llamada a un método**: `call t, n` lo traduce Persona 1 con `jalr`. Para
  saber dónde van los argumentos, `ObjectTranslator.method_frame(t)` le
  entrega el marco del método que resolvió `method o.m`.

## 4. Herencia y despacho dinámico

- **Atributos heredados**: conservan el desplazamiento que tienen en la
  superclase (lo garantiza la distribución del Proyecto 2), por lo que
  `o.nombre` es la misma instrucción para un `Animal` y para un `Perro`.
- **vtable**: la de una subclase empieza con los métodos de la superclase en
  las mismas posiciones; una redefinición reemplaza la entrada heredada y los
  métodos nuevos se agregan al final.

```mips
    .word p3_members_Perro          # tabla de miembros (vtable - 4)
p3_vt_Perro:
    .word fn_Perro_hablar           # 0: hablar   (redefinido)
    .word fn_Animal_presentarse     # 1: presentarse (heredado)
```

- **Despacho dinámico**: `method o.m` lee la vtable *del objeto* (su clase
  real) en la posición de `m` en la clase estática. Una variable `Animal` que
  guarda un `Perro` ejecuta `Perro.hablar`, incluso cuando la llamada está
  dentro de un método heredado (`this.sonido()` en `Animal.hablar`).
- **Firmas**: con `jalr` el llamador no sabe qué implementación se ejecutará,
  así que todas deben esperar los argumentos en las mismas casillas. Se
  verifica para la clase estática y todas sus subclases; si una redefinición
  cambia la firma se reporta un error de generación (el análisis semántico
  no lo revisa; ver «A tener en cuenta» en NOTAS.md).

### Clase estática y búsqueda dinámica

El generador de TAC anota en `Name.owner` la clase estática del objeto
(como `Var.symbol`, no se imprime ni participa en la igualdad). Con eso:

1. **Clase estática conocida** → desplazamiento y posición fijos.
2. **Clase desconocida** (por ejemplo `function etiqueta(x) { return x.nombre; }`,
   un parámetro sin anotación): si todas las clases que tienen ese miembro
   lo ponen en el mismo lugar, se usa ese lugar.
3. **Si no**, se busca en tiempo de ejecución: `p3_lookup` recorre la tabla
   de miembros de la clase real del objeto (en `vtable - 4`), con entradas
   `clave, valor, tamaño` (desplazamiento del atributo o dirección del
   método). Si el objeto no tiene el miembro, lanza «El objeto no tiene el
   miembro solicitado».

## 5. try/catch

Compiscript no tiene `throw`: los errores son de ejecución. Quien detecta uno
(Persona 2: división entre cero, arreglos, cadenas nulas; Persona 3: objetos
nulos y miembros inexistentes) guarda los registros modificados y salta a
`p3_throw` con el mensaje en `$a0`.

### Pila de manejadores

Cada `try_begin L` reserva 12 bytes **en la pila del marco actual**:

```text
            ┌──────────────────────┐
 $sp + 8    │ manejador anterior   │ ──► lista enlazada hasta 0
 $sp + 4    │ dirección del catch L│
 $sp + 0    │ $fp del marco        │
            └──────────────────────┘   p3_handler apunta aquí
```

```mips
    # try_begin L1                      # try_end
    addiu $sp, $sp, -12                  lw    $t9, 8($sp)
    lw    $t9, p3_handler                sw    $t9, p3_handler
    sw    $t9, 8($sp)                    addiu $sp, $sp, 12
    la    $t9, L1
    sw    $t9, 4($sp)
    sw    $fp, 0($sp)
    sw    $sp, p3_handler
```

`p3_throw`:

1. Guarda el mensaje en `p3_exception` (sin el salto de línea final de los
   mensajes de Persona 2).
2. Si no hay manejador: imprime `Error en tiempo de ejecución: <mensaje>` y
   termina el programa.
3. Si hay: lo retira, restaura `$fp` del marco que lo instaló y
   `$sp = manejador + 12` (el `$sp` de ese marco antes del `try`), y salta a
   `L`. Así se descartan de una vez todos los marcos de las funciones
   llamadas desde el `try` (también en recursión).

En `L`, `e = exception` copia el mensaje (una cadena real: `e == "División
por cero"` funciona) a la variable del `catch`.

Por qué funciona:

- Dentro de una función `$sp` sólo cambia en las secuencias de llamada y
  cada llamada lo deja como estaba (NOTAS.md, sección 2), así que `try_end`
  siempre encuentra su manejador en `0($sp)` y los `try` anidados se apilan
  solos.
- El TAC emite un `try_end` por cada manejador que abandona un `break`,
  `continue` o `return`; además el epílogo de una función hace
  `move $sp, $fp`, que libera cualquier manejador de su marco.
- No se calcula `$sp` con el tamaño del marco: se usa el valor guardado
  (NOTAS.md, «Persona 3 necesita»).
- Todo salto a `p3_throw` guarda antes los registros modificados y la
  etiqueta del `catch` empieza sin asociaciones, así que el `catch` lee de
  memoria los valores correctos (por ejemplo, una variable asignada dentro
  del `try` antes del error).
- **Árbol de activación**: con traza, `p3_throw` imprime `#<*` por cada
  marco descartado (siguiendo los enlaces de control) y
  `activation_tree.py` los marca como «interrumpida por excepción».

## 6. Optimización por mirilla

`mips_generator.peephole_optimize` repite, hasta que el código deja de
cambiar, las reglas locales de Persona 2 (`mips_peephole.py`) y estas reglas
de control de flujo (`mips_peephole_control.py`). Sólo se aplican en
`.text`; una etiqueta corta las ventanas porque se puede llegar a ella por
otro camino.

| # | Regla | Ejemplo |
| --- | --- | --- |
| 1 | Salto a salto | `j L1` … `L1: j L2` → `j L2` (también `beq`/`bne`) |
| 2 | Salto condicional sobre un salto | `bne c, $zero, L1` / `j L2` / `L1:` → `beq c, $zero, L2` / `L1:` |
| 3 | Código inalcanzable | instrucciones entre `j`/`jr` y la siguiente etiqueta |
| 4 | Etiqueta sin uso | `L7:` que nadie menciona (sólo etiquetas generadas) |
| 5 | Carga de lo recién guardado | `sw $t0, X` / `lw $t1, X` → `sw $t0, X` / `move $t1, $t0` |
| 6 | Carga repetida | `lw $t0, X` / `lw $t0, X` → una sola |
| 7 | Movimiento de ida y vuelta | `move $t0, $t1` / `move $t1, $t0` → sólo el primero |
| 8 | Salto condicional a la siguiente instrucción | `beq c, $zero, L4` / `L4:` → `L4:` |

Persona 2 aporta: `addiu`/`sll` con 0, suma y resta con `$zero` → `move`;
`move` a sí mismo; `li` repetido; `j` a la etiqueta siguiente. El IDE muestra
cuántas veces se aplicó cada regla y permite ver el código sin optimizar.
Las pruebas ejecutan cada ejemplo con y sin mirilla y comparan la salida.

## 7. Interfaz y simulador

- Pestaña **MIPS**: ensamblador con resaltado, total de instrucciones,
  cuántas quitó la mirilla y cuáles reglas se aplicaron, casilla «Ver sin
  optimizar», **Copiar** y **Guardar .asm**.
- Pestaña **Ejecución** (`F6`): ejecuta el programa en MARS en segundo plano
  (no congela el IDE) y muestra lo que imprimió y su **árbol de activación**.
  Tiene un límite de instrucciones para no colgarse con un ciclo infinito.
- No es obligatorio ejecutar desde el IDE: el `.asm` guardado se abre en
  MARS 4.5 (*File → Open*, *Run → Assemble*, *Run → Go*). En *Settings*
  debe estar desactivado *Delayed branching* (es el valor por defecto).
- `python src/compilar.py programa.cps --ejecutar --arbol` hace lo mismo por
  línea de comandos.

## 8. Pruebas

| Archivo | Cubre |
| --- | --- |
| `tests/test_mips_control.py` | Etiquetas, saltos, condiciones constantes; `if/else`, anidados, cortocircuito, `while`, `do-while`, `for`, `foreach`, `switch`, `break`/`continue` en MARS |
| `tests/test_mips_objects.py` | Distribución, vtables, tablas de miembros, `new`, atributos, `this`, objetos anidados, herencia, despacho dinámico, búsqueda dinámica, firmas incompatibles |
| `tests/test_mips_exceptions.py` | Manejadores, cada error atrapable, marcos descartados, `$sp`/`$fp` restaurados, `break`/`continue`/`return` en `try`, anidados, error sin atrapar, árbol con excepciones |
| `tests/test_mips_peephole_control.py` | Cada regla y sus límites; mismas salidas con y sin mirilla |
| `tests/test_mips_integration.py` | Sin MIPS si hay errores, MIPS desde el TAC, estructura del archivo, errores de generación, **todos los ejemplos en MARS** contra `examples/salidas`, CLI e IDE |

Las pruebas que ejecutan MARS comprueban además que `$sp` y `$fp` terminen
en el tope de la pila (ningún marco ni manejador quedó sin liberar).
