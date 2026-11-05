# Notas del Proyecto 3: convención de llamadas en MIPS

Acuerdo del grupo sobre cómo se llaman las funciones, cómo se organiza la
pila y qué registros puede usar cada parte del generador MIPS. Todas las
partes deben seguirlo al programar:

- **Persona 1:** registros de activación y llamadas.
- **Persona 2:** asignación de registros, instrucciones básicas, arreglos y
  mirilla.
- **Persona 3:** control de flujo, clases, excepciones e integración.

Recordatorio: el MIPS se genera **a partir del TAC** del Proyecto 2, nunca
directamente desde Compiscript.

## Decisiones tomadas

| Tema | Decisión |
| --- | --- |
| Paso de argumentos | **Todos por la pila.** No se usan `$a0-$a3` para pasar argumentos |
| Frame pointer | **Sí se usa `$fp`**, apuntando al tope del marco |
| Valor de retorno | En `$v0` |
| Registros que guarda el llamador | `$t0-$t9`: se escriben a memoria antes de cada `jal`/`jalr` |
| Registros que guarda la función llamada | `$s0-$s7`: sólo los que use, en su prólogo y epílogo |
| `$v1` | Reservado para Persona 1 (seguir enlaces de acceso). `getReg()` no lo usa |
| `$a0-$a3` | Libres para los `syscall` (`print`, etc.) |
| Área global | Bloque `globales` en `.data`, apuntado por `$gp` |
| Punto de entrada (`main`) | Lo hace Persona 1 |
| Nombres de funciones en MIPS | Prefijo `fn_`, reservado para Persona 1 (sección 7) |
| Simulador | MARS (requiere Java instalado) |

## 1. Punto de partida: lo que ya da el Proyecto 2

No hay que recalcular nada: la tabla de símbolos ya tiene un
`ActivationRecord` por cada función, método, constructor e inicializador
(`Symbol.activation_record`, `SymbolTable.activation_records`):

| Desplazamiento | Casilla |
| --- | --- |
| +0 | dirección de retorno |
| +4 | enlace de control (`$fp` del llamador) |
| +8 | enlace de acceso (`$fp` de la función que la contiene léxicamente) |
| +12 | `this` (sólo métodos, constructores e inicializadores) |
| ... | parámetros, en orden |
| ... | variables locales |
| `temporaries_offset` + 4·(n−1) | temporal `tn` |

- `record.size` es el tamaño total; es el número de `begin_func f, n`.
- Cada `Var` del TAC guarda su `Symbol`, con `offset`, `size`, `storage`
  (`global`, `parámetro`, `local`) y `owner` (registro que lo aloja). `this`
  es `Var("this")` sin símbolo: vive en la casilla `this` del método.
- `record.level` es la profundidad léxica (global 0, funciones de primer nivel
  y métodos 1, anidadas 2, ...).
- `boolean` ocupa 1 byte (`lbu`/`sb`); `integer`, `string`, arreglos y objetos
  ocupan una palabra (`lw`/`sw`).
- En el TAC, todos los `param` de una llamada aparecen seguidos justo antes de
  su `call` (los argumentos se evalúan antes).

## 2. Distribución del marco en la pila

La pila crece hacia abajo. **`$fp` apunta al tope del marco** (la dirección
más alta) y una casilla con desplazamiento `off` y tamaño `size` está en:

```text
-(off + size)($fp)
```

```text
              direcciones altas
   $fp ──►  ┌───────────────────────┐ ◄── $sp del llamador antes de llamar
            │ dirección de retorno  │  -4($fp)   off 0   ┐
            │ enlace de control     │  -8($fp)   off 4   │ prefijo P:
            │ enlace de acceso      │ -12($fp)   off 8   │ lo reserva y llena
            │ this                  │ -16($fp)   off 12  │ el llamador
            │ parámetros            │                    ┘
            ├───────────────────────┤
            │ variables locales     │                    ┐
            │ temporales t1..tn     │                    │ lo reserva el
            │ registros $s guardados│                    │ prólogo de la función
   $sp ──►  └───────────────────────┘                    ┘
              direcciones bajas
```

- **P** (prefijo) = fin de la última casilla de encabezado, `this` o
  parámetros, alineado a 4. Si las redefiniciones de un método conservan su
  firma (ver «A tener en cuenta»), P es igual para todas, así que el llamador
  no necesita saber qué implementación se ejecutará (despacho dinámico con
  `jalr`).
- **SIZE** = `record.size` + 4 por cada registro `$s` que guarde la función.
  Los `$s` guardados van después de los temporales.
- **Invariante:** dentro del cuerpo de una función, fuera de una secuencia de
  llamada, siempre se cumple `$sp == $fp - SIZE`. Al regresar de una llamada,
  `$sp` vuelve exactamente al valor que tenía antes de ella.

### Área global

El registro `global` no tiene encabezado. Es un bloque estático en `.data`:

```mips
        .data
globales: .space N          # N = table.global_record.size
```

Al iniciar, `$gp` apunta a `globales`. Las globales y los temporales del
código global usan desplazamientos **positivos**: `off($gp)`.

## 3. Secuencia de llamada (lado del llamador)

Para `param x1 … param xn` seguido de `[t =] call f, n`:

1. **Guardar registros:** se escriben a memoria los registros modificados
   (`$t` y cualquiera que tenga variables), porque la función llamada puede
   leer globales o variables capturadas. *(Persona 2)*
2. `addiu $sp, $sp, -P`: reserva el prefijo del registro de `f`.
3. Por cada argumento: `sw`/`sb` en `(P - off - size)($sp)`, con el `off` y
   `size` de ese parámetro en el registro de `f`. Los métodos reciben `this`
   como primer argumento.
4. **Enlace de acceso** en `(P - 12)($sp)`:
   - `f` de nivel 1 (funciones globales y métodos): `$zero`.
   - `f` un nivel más adentro que quien llama: `$fp` actual.
   - En otro caso: el resultado de seguir `nivel(llamador) − nivel(f) + 1`
     enlaces de acceso desde `$fp` (`lw $v1, -12($fp)`, `lw $v1, -12($v1)`, …).
5. `jal fn_f`, o `jalr $r` si el destino es un temporal de `method`.
6. Al volver, el valor de retorno está en `$v0`; si hay destino, se asigna a
   `t`. Lo que había en los registros ya no es válido. *(Persona 2)*

## 4. Prólogo, epílogo y `return` (lado de la función)

```mips
fn_f:                               # begin_func f, SIZE
        sw    $ra, P-4($sp)         # dirección de retorno   (-4($fp))
        sw    $fp, P-8($sp)         # enlace de control      (-8($fp))
        addiu $fp, $sp, P           # $fp = tope del marco
        addiu $sp, $fp, -SIZE       # reserva locales y temporales
        sw    $s0, ...($fp)         # sólo los $s que use f
        ...cuerpo...
fn_f_fin:                           # end_func f (y destino de todo return)
        lw    $s0, ...($fp)
        lw    $ra, -4($fp)
        move  $sp, $fp              # libera el marco completo, prefijo incluido
        lw    $fp, -8($fp)          # restaura el $fp del llamador
        jr    $ra
```

- `return x`: carga `x` en `$v0`, guarda en memoria las globales modificadas
  que estén en registros y salta a `fn_f_fin`. `return` sin valor sólo salta.
- Llegar a `end_func` sin `return` equivale a `return` sin valor.
- La función que llama no libera nada: `move $sp, $fp` deja `$sp` como estaba
  antes del `addiu $sp, $sp, -P`.
- El prólogo se emite después de traducir el cuerpo, para saber qué `$s` usó.

## 5. Ejemplo completo

```text
function suma(a: integer, b: integer): integer { return a + b; }
let resultado: integer = suma(2, 3);
```

Registro de `suma` (tabla de símbolos): `a` en +12, `b` en +16, `t1` en +20,
`size` 24, `P` = 20.

```mips
# código global:  param 2 / param 3 / t1 = call suma, 2 / resultado = t1
        addiu $sp, $sp, -20         # prefijo de suma
        li    $t0, 2
        sw    $t0, 4($sp)           # a: 20 - 12 - 4
        li    $t0, 3
        sw    $t0, 0($sp)           # b: 20 - 16 - 4
        sw    $zero, 8($sp)         # enlace de acceso (suma es de nivel 1)
        jal   fn_suma               # al volver, $sp está como antes del addiu
        sw    $v0, 0($gp)           # resultado = t1

fn_suma:                            # begin_func suma, 24
        sw    $ra, 16($sp)
        sw    $fp, 12($sp)
        addiu $fp, $sp, 20
        addiu $sp, $fp, -24
        lw    $t0, -16($fp)         # a
        lw    $t1, -20($fp)         # b
        addu  $t2, $t0, $t1         # t1 = a + b   (Persona 2)
        move  $v0, $t2              # return t1
        j     fn_suma_fin
fn_suma_fin:                        # end_func suma
        lw    $ra, -4($fp)
        move  $sp, $fp
        lw    $fp, -8($fp)
        jr    $ra
```

La recursión no necesita nada especial: cada llamada crea su propio marco con
sus parámetros, locales y temporales, y los valores del llamador quedan en su
propio marco (por eso el paso 1 de la sección 3 los escribe a memoria).

## 6. Uso de registros

| Registro | Uso | Quién lo guarda |
| --- | --- | --- |
| `$zero`, `$at` | Constante 0 y temporal del ensamblador | — |
| `$v0` | Valor de retorno y código de `syscall` | — |
| `$v1` | Auxiliar de Persona 1 para seguir enlaces de acceso | — |
| `$a0-$a3` | Argumentos de `syscall` | — |
| `$t0-$t9` | Libres para `getReg()` | La función que llama (se escriben a memoria antes de `jal`) |
| `$s0-$s7` | Libres para `getReg()` | La función llamada (prólogo y epílogo) |
| `$k0`, `$k1` | Reservados del sistema | — |
| `$gp` | Base del área global | No cambia |
| `$sp`, `$fp`, `$ra` | Pila, marco y dirección de retorno | Secuencia de llamada |

## 7. Interfaz entre las partes

**Persona 1 ofrece** (`src/mips_frames.py`, y luego `src/mips_functions.py`):

- `FrameModel(tabla)`: se construye una vez por programa, con la tabla de
  símbolos ya completada por el Proyecto 2.
- `model.address_of(operando, unidad)`: dirección de un `Var` (incluido
  `this`) o `Temp`. `unidad` es la etiqueta TAC de la función que se está
  traduciendo (la de su `begin_func`), o `None` en el código global. Devuelve
  un `MemoryLocation`:
  - `location.load("$t0")` / `location.store("$t0")` dan las instrucciones
    listas, con `lw`/`sw` o `lbu`/`sb` según el tamaño. Si la variable es de
    una función que contiene a la actual, incluyen antes los `lw $v1, …` que
    siguen los enlaces de acceso.
  - `location.address` (`-16($fp)`, `8($gp)`, `-16($v1)`), `location.size` y
    `location.setup`, por si se necesitan por separado.
  - Constantes, etiquetas, nombres y atributos no tienen dirección: lanzan
    `MipsFrameError`. Los atributos se leen a través del objeto (Persona 3).
- `model.frame(etiqueta TAC)`: el `FrameLayout` de una función, con
  `label` (nombre MIPS), `epilogue_label`, `prefix_size`, `size` y
  `argument_slots`.
- Nombres MIPS: las etiquetas del TAC tienen `.` y `$` (`Perro.hablar`,
  `Animal.$init`, `a$1`), así que cada función recibe un nombre único con
  prefijo `fn_` (`fn_Perro_hablar`, `fn_Animal__init`, `fn_a_1`). **Nadie más
  debe crear etiquetas que empiecen con `fn_`**, ni usar `main` o `globales`.
  Las etiquetas `L1, L2, …` del control de flujo se dejan igual.
- `FunctionTranslator(model, registros)` (`src/mips_functions.py`) traduce
  `begin_func`, `end_func`, `return`, `param` y `call` (`HANDLED_OPS`). Quien
  integra recorre el TAC y:
  - en `begin_func` llama a `begin_function(instr)` y empieza a juntar las
    líneas del cuerpo;
  - manda cada `param`, `call` y `return` a `translate_param`,
    `translate_call` y `translate_return` (también en el código global);
  - en `end_func` llama a `end_function(instr, cuerpo)`, que devuelve la
    función completa: prólogo + cuerpo + epílogo. El prólogo se arma al
    final porque depende de los `$s` que usó el cuerpo;
  - puede llamar a `ensure_no_pending_params(instr)` antes de cualquier otra
    instrucción: entre los `param` y su `call` no debe haber nada más.
  - `translator.unit` dice en qué función se está (la `unit` de
    `address_of`).
- Punto de entrada y área global: `translator.main_program(lineas_globales)`
  envuelve el código global (`main:`, `la $gp, globales`, `move $fp, $sp`
  y la salida con `syscall` 10) y `translator.data_lines()` da lo que va en
  `.data` (el bloque `globales` y, con traza, sus cadenas).
- **Orden del archivo final** (lo arma la integración):

  ```text
  .data
      <data_lines() de Persona 1> <cadenas y datos de Persona 2/3>
  .text
      <main_program(...)>        ← main va primero: MARS empieza en la primera instrucción
      <cada función completa>    ← lo que devuelve end_function
  ```
- Árbol de activación: `FunctionTranslator(model, regs, trace=True)` hace
  que cada función imprima `#>nombre args` al entrar y `#<nombre` al salir;
  `activation_tree.build_activation_tree(salida)` arma el árbol y
  `render_activation_tree(arbol)` lo dibuja en texto (para mostrarlo en el
  IDE). `strip_trace(salida)` deja sólo lo que imprimió el programa. Sin
  `trace` el código no cambia.
- Detalle en [docs/REGISTROS_ACTIVACION.md](docs/REGISTROS_ACTIVACION.md).
- **Formato de las líneas** (para todos): cada parte devuelve listas de
  cadenas sin sangría; una etiqueta termina en `:` y un comentario empieza
  con `#`. La sangría la pone quien escribe el archivo final.

**Persona 2 ofrece** (asignación de registros): un objeto con estos métodos
(el contrato completo está en `RegisterAllocator`, en `src/mips_functions.py`).
`unit` es la etiqueta TAC de la función actual o `None`:

| Método | Qué hace |
| --- | --- |
| `value_register(op, unit) -> (líneas, reg)` | Deja el valor de `op` en algún registro y lo devuelve (argumentos y destino de `jalr`) |
| `load_into(op, unit, reg) -> líneas` | Deja el valor de `op` en `reg` (por ejemplo `$v0` en `return`) |
| `assign_from(op, unit, reg) -> líneas` | `op = reg` (el resultado de una llamada llega en `$v0`) |
| `spill(unit) -> líneas` | Escribe a memoria los registros modificados (antes de `jal` y al salir de la función) |
| `forget()` | Olvida el contenido de todos los registros (después de `jal` y al empezar o terminar una función) |
| `saved_registers(unit)` | Registros `$s` que usó esa función |

- No asignar `$v1`, `$a0-$a3` (salvo para `syscall`), `$gp`, `$sp`, `$fp` ni
  `$ra`. `$v0` y `$a0` no conservan nada a través de una llamada (la traza
  los usa al entrar a cada función).
- En las pruebas de Persona 1 hay un doble de prueba de este contrato
  (`tests/mips_doubles.py`, `MemoryRegisters`) que deja todo en memoria;
  sirve de ejemplo mínimo.

**Persona 3 necesita**:
- Para `t = method o.m` + `call t, n`: pasar a
  `translate_call(instr, method_frame)` el marco del método en el tipo
  estático de `o`: `model.frame(etiqueta)`, con la etiqueta de su vtable
  (`ClassLayout.vtable[ClassLayout.method_index(m)]`). De ahí salen el
  prefijo y la casilla de cada argumento. El destino se carga en un registro
  y se usa `jalr`; `this` es el primer argumento.
- Para `try/catch`: al instalar un manejador, guardar `$fp` **y** `$sp`; al
  atrapar un error, restaurar los dos. Eso descarta todos los marcos
  intermedios (dentro del cuerpo de una función `$sp` no cambia fuera de las
  llamadas). No conviene calcular `$sp` con el tamaño del marco: éste se
  conoce al terminar de traducir la función.

## A tener en cuenta

- **Persona 3:** el análisis semántico no revisa que un método redefinido
  tenga la misma firma. Si cambian los tipos de los parámetros (`boolean`
  ocupa 1 byte e `integer` 4), con `jalr` los argumentos quedarían en
  desplazamientos distintos.
- **Simulador:** MARS es un `.jar`; hay que tener Java instalado y copiar
  `Mars4_5.jar` en `tools/`. Con eso `tests/test_mips_mars.py` deja de
  omitirse. Mientras tanto, las pruebas de ejecución de Persona 1 usan un
  simulador mínimo (`tests/mips_doubles.py`).
- **Dobles de prueba:** `tests/mips_doubles.py` tiene versiones mínimas de la
  asignación de registros y de algunas instrucciones de Persona 2 y 3, sólo
  para que las pruebas de Persona 1 puedan ejecutar programas. No son el
  código real de nadie; cuando estén las implementaciones reales, las pruebas
  pueden pasar a usarlas.
