# Registros de activación, llamadas y recursividad en MIPS

Este documento describe la parte del generador de MIPS que maneja la memoria
de las funciones: los registros de activación en la pila, el manejo de `$sp`
y `$fp`, la secuencia de llamada y de retorno, el paso de parámetros, el
valor de retorno, la recursividad, las funciones anidadas, el punto de
entrada del programa y los árboles de activación.

El MIPS se genera **a partir del TAC** del Proyecto 2: cada instrucción
`begin_func`, `end_func`, `param`, `call` y `return` del TAC se traduce a una
secuencia fija de instrucciones MIPS, usando los registros de activación que
la tabla de símbolos del Proyecto 2 ya tiene calculados. La convención
acordada entre las tres partes del generador está en [NOTAS.md](../NOTAS.md).

| Archivo | Contenido |
| --- | --- |
| `src/mips_frames.py` | Marcos en MIPS: `FrameModel`, `FrameLayout`, `GlobalArea`, `MemoryLocation`, direcciones (`address_of`), enlaces de acceso y nombres de etiquetas |
| `src/mips_functions.py` | `FunctionTranslator`: prólogo, epílogo, `return`, `param`, `call`, punto de entrada `main`, área global y traza de activaciones |
| `src/activation_tree.py` | Árbol de activación a partir de la traza de una ejecución |
| `tests/test_mips_frames.py` | Marcos y direcciones |
| `tests/test_mips_functions.py` | Secuencias de llamada y retorno (código generado) |
| `tests/test_mips_runtime.py` | Ejecución de funciones, parámetros y recursividad |
| `tests/test_mips_program.py` | Punto de entrada y área global |
| `tests/test_activation_tree.py` | Traza y árboles de activación |
| `tests/test_mips_mars.py` | Los mismos programas en MARS (si hay Java) |
| `tests/mips_doubles.py` | Dobles de prueba y simulador mínimo usados por las pruebas |

## 1. Registro de activación en la pila

Cada llamada a una función crea su propio registro de activación (marco) en
la pila. La distribución es la del `ActivationRecord` del Proyecto 2; la
pila crece hacia abajo y **`$fp` apunta al tope del marco**:

```text
              direcciones altas
   $fp ──►  ┌───────────────────────┐ ◄── $sp del llamador antes de llamar
            │ dirección de retorno  │  -4($fp)                    ┐
            │ enlace de control     │  -8($fp)   $fp del llamador │ prefijo P:
            │ enlace de acceso      │ -12($fp)   $fp del padre    │ lo reserva
            │ this                  │ -16($fp)   (sólo métodos)   │ el llamador
            │ parámetros            │                             ┘
            ├───────────────────────┤
            │ variables locales     │                             ┐ lo reserva
            │ temporales t1..tn     │                             │ el prólogo
            │ registros $s guardados│                             ┘
   $sp ──►  └───────────────────────┘
              direcciones bajas
```

- Una casilla con desplazamiento `off` y tamaño `size` en el registro del
  Proyecto 2 está en `-(off + size)($fp)`. Así no se recalcula nada: los
  desplazamientos de parámetros, locales y temporales salen de la tabla de
  símbolos.
- `boolean` ocupa 1 byte (`lbu`/`sb`); los demás tipos, una palabra
  (`lw`/`sw`).
- **P** (prefijo) es el tamaño del encabezado, `this` y los parámetros,
  alineado a 4. **SIZE** es el tamaño del registro (`begin_func f, SIZE`) más
  4 bytes por cada registro `$s` que guarde la función.
- **Invariante:** dentro del cuerpo de una función, fuera de una llamada,
  siempre `$sp == $fp - SIZE`.

`FrameModel(tabla)` construye un `FrameLayout` por función y
`address_of(operando, función)` devuelve dónde vive cada variable, parámetro,
temporal o `this`, visto desde la función que se está traduciendo.

### Área global

Las variables globales y los temporales del código global no están en la
pila: viven en el bloque estático `globales` de `.data`, apuntado por `$gp`,
con desplazamientos positivos (`off($gp)`).

## 2. Secuencia de llamada y de retorno

### Lado del llamador

El TAC deja todos los `param` de una llamada seguidos, justo antes de su
`call` (los argumentos se evalúan antes). `translate_param` sólo los guarda;
`translate_call` genera:

```mips
# t = call f, n
<escribir a memoria los registros modificados>   (asignación de registros)
addiu $sp, $sp, -P                  # 1. reserva el prefijo del registro de f
sw    <x1>, (P - off1 - size1)($sp) # 2. cada argumento en su casilla (sb si es boolean)
...
sw    <enlace>, (P - 12)($sp)       # 3. enlace de acceso
jal   fn_f                          # 4. salto (jalr $r si es un método)
<t = $v0>                           # 5. valor de retorno
```

- Lo que el llamador escribe en `k($sp)` es exactamente la casilla
  `k - P` respecto al `$fp` de la función llamada, porque el prólogo hace
  `$fp = $sp + P`.
- No hay límite de parámetros: todos van por la pila. `$a0-$a3` quedan para
  los `syscall`.
- Los registros `$t` no sobreviven a una llamada: se escriben a memoria
  antes del `jal` (cada temporal y variable tiene su casilla en el registro
  de activación) y se olvidan al volver.

### Lado de la función

```mips
fn_f:                           # begin_func f, SIZE
    sw    $ra, P-4($sp)         # dirección de retorno
    sw    $fp, P-8($sp)         # enlace de control (el $fp del llamador)
    addiu $fp, $sp, P           # $fp = tope del nuevo marco
    addiu $sp, $fp, -SIZE       # reserva locales y temporales
    sw    $s0, ...($fp)         # sólo los $s que use f
    ...cuerpo...
    # return x
    <$v0 = x>
    j     fn_f_fin
fn_f_fin:                       # end_func f: único punto de salida
    lw    $s0, ...($fp)
    lw    $ra, -4($fp)
    move  $sp, $fp              # libera el marco completo, prefijo incluido
    lw    $fp, -8($fp)          # restaura el marco del llamador
    jr    $ra
```

- Todos los `return` saltan al epílogo; llegar a `end_func` sin `return`
  equivale a `return` sin valor.
- `move $sp, $fp` deja `$sp` con el valor que tenía antes del
  `addiu $sp, $sp, -P` del llamador: **la llamada completa no cambia `$sp`**.
- El prólogo se genera después de traducir el cuerpo, para saber qué
  registros `$s` usó.

### Ejemplo

```text
function suma(a: integer, b: integer): integer { return a + b; }
print(suma(2, 3));
```

Registro de `suma`: `a` en +12, `b` en +16, `t1` en +20; SIZE = 24, P = 20.

```mips
# t1 = call suma, 2                      fn_suma:
addiu $sp, $sp, -20                          sw    $ra, 16($sp)
li    $t8, 2                                 sw    $fp, 12($sp)
sw    $t8, 4($sp)        # a                 addiu $fp, $sp, 20
li    $t8, 3                                 addiu $sp, $fp, -24
sw    $t8, 0($sp)        # b                 lw    $t8, -16($fp)   # a
sw    $zero, 8($sp)      # enlace            lw    $t9, -20($fp)   # b
jal   fn_suma                                addu  $t8, $t8, $t9
sw    $v0, 0($gp)        # t1                sw    $t8, -24($fp)   # t1
                                             lw    $v0, -24($fp)   # return t1
                                             j     fn_suma_fin
                                         fn_suma_fin:
                                             lw    $ra, -4($fp)
                                             move  $sp, $fp
                                             lw    $fp, -8($fp)
                                             jr    $ra
```

(Las instrucciones de la suma y de los temporales son de la asignación de
registros; aquí se muestran con la versión más simple, todo en memoria.)

## 3. Recursividad

No necesita nada especial: cada llamada ejecuta el prólogo y crea un marco
nuevo con sus propios parámetros, locales y temporales. Los valores
pendientes del llamador quedan en **su** marco, así que una llamada recursiva
no los pisa.

Pila en el punto más profundo de `print(factorial(3));`
(`factorial`: SIZE = 20, P = 16; direcciones reales de una ejecución):

```text
dirección     contenido                     marco
0x7fffeffc    ─── $fp de factorial(3) ───   ┐
0x7fffeff8    dirección de retorno → main   │
0x7fffeff4    enlace de control 0x7fffeffc  │ factorial(3)
0x7fffeff0    enlace de acceso  0           │
0x7fffefec    n = 3                         │
0x7fffefe8    t1 = 2   (n - 1)              ┘
              ─── $fp de factorial(2) = 0x7fffefe8 ───
0x7fffefe4    dirección de retorno → factorial
0x7fffefe0    enlace de control 0x7fffeffc  │ factorial(2)
0x7fffefdc    enlace de acceso  0           │
0x7fffefd8    n = 2                         │
0x7fffefd4    t1 = 1                        ┘
              ─── $fp de factorial(1) = 0x7fffefd4 ───
0x7fffefd0    dirección de retorno → factorial
0x7fffefcc    enlace de control 0x7fffefe8  │ factorial(1)
0x7fffefc8    enlace de acceso  0           │
0x7fffefc4    n = 1                         │
0x7fffefc0    t1                            ┘ ◄── $sp
```

Los enlaces de control forman la cadena de marcos de las llamadas activas:
desde `factorial(1)` se llega a `factorial(2)` y de ahí a `factorial(3)`.
Al terminar, cada epílogo restaura el `$fp` y el `$sp` de su llamador, y al
final del programa los dos vuelven a `0x7fffeffc`.

## 4. Funciones anidadas: enlace de acceso

Una función declarada dentro de otra puede usar las variables de la que la
contiene. El enlace de acceso (`-12($fp)`) guarda el `$fp` del marco de la
función que la contiene léxicamente; `record.level` es la profundidad
(funciones globales y métodos 1, anidadas 2, …).

- **Al llamar**, el llamador escribe el enlace de acceso de la función
  llamada:
  - función global o método: `$zero` (no lo usa);
  - función declarada directamente en el llamador: su propio `$fp`;
  - en otro caso (hermana, recursión de una anidada, o una más externa):
    sigue `k` enlaces desde su `$fp` hasta el marco de la función que
    contiene a la llamada, con `k = nivel(llamador) − nivel(llamada) + 1`.
- **Al usar una variable** de `k` niveles más afuera, `address_of` antepone
  `k` lecturas de enlaces, usando `$v1` (reservado para esto):

```mips
lw  $v1, -12($fp)       # marco de la función que contiene a la actual
lw  $v1, -12($v1)       # y el de la que contiene a ésa
lw  $t0, -16($v1)       # la variable
```

## 5. Punto de entrada y área global

```mips
        .data
        .align 2
globales: .space N              # N = tamaño del registro global (mínimo 4)
        .text
        .globl main
main:                           # va antes que las funciones
        la    $gp, globales
        move  $fp, $sp          # base de la cadena de marcos
        ...código global...
        li    $v0, 10           # fin del programa
        syscall
fn_…:                           # funciones
```

`data_lines()` da el área global y `main_program(cuerpo)` envuelve el código
global. `main` va primero porque MARS empieza a ejecutar en la primera
instrucción de `.text`.

## 6. Árboles de activación

Un árbol de activación muestra las llamadas de **una ejecución**: cada nodo
es una activación (un registro de activación en la pila) y sus hijos son las
llamadas que hizo, en orden.

Con `FunctionTranslator(..., trace=True)` cada función imprime al entrar
`#>nombre arg1 arg2…` (los parámetros `integer` y `boolean`; los demás como
`?`) y al salir `#<nombre`. El epílogo guarda `$v0` en `$v1` mientras
imprime, así la traza no cambia el valor de retorno.
`activation_tree.build_activation_tree(salida)` arma el árbol y
`render_activation_tree` lo dibuja; `strip_trace` devuelve la salida del
programa sin la traza.

```text
print(fib(4));

main
└── fib(4)
    ├── fib(3)
    │   ├── fib(2)
    │   │   ├── fib(1)
    │   │   └── fib(0)
    │   └── fib(1)
    └── fib(2)
        ├── fib(1)
        └── fib(0)
```

Si la ejecución se interrumpe, `build_activation_tree(salida, strict=False)`
deja las activaciones abiertas marcadas como «sin terminar».

## 7. Pruebas

```powershell
python -m unittest discover -s tests -v
```

| Archivo | Qué valida |
| --- | --- |
| `test_mips_frames.py` | Prefijo y tamaño de cada marco, direcciones de parámetros, locales, temporales, globales y `this`, `boolean` de 1 byte, enlaces de acceso de 1 y 2 niveles, registros `$s`, nombres de etiquetas únicos, casos fallidos y que todo operando de todos los ejemplos tenga dirección |
| `test_mips_functions.py` | Prólogo, epílogo y `return` exactos; paso de argumentos, `boolean`, procedimientos, valor de retorno; enlaces de acceso; métodos con `jalr`; recursión; que `$sp` sólo cambie al llamar; casos fallidos (`param` sin `call`, cantidad de argumentos, función inexistente o no visible, `begin_func`/`end_func` desbalanceados) |
| `test_mips_runtime.py` | Ejecución: funciones simples, con parámetros (más de cuatro, `boolean`, por valor), con retorno, anidadas, consecutivas, recursión (`factorial`, `fib`, `ackermann`, mutua, profunda), variables de funciones externas, globales; cada activación ocupa su marco; `$sp` y `$fp` terminan como empezaron |
| `test_mips_program.py` | `main`, `$gp`, área global y su contenido al terminar |
| `test_activation_tree.py` | Árboles de recursión simple, doble, anidada y consecutiva; la traza no cambia la salida ni el valor de retorno; errores de una traza mal formada |
| `test_mips_mars.py` | Los mismos programas en MARS, revisando la salida y el valor final de `$sp` y `$fp` |

Las pruebas de ejecución usan `TinyMips` (`tests/mips_doubles.py`), un
simulador mínimo y estricto: falla si se lee de la pila memoria que nadie
escribió, si una palabra está desalineada o si se salta a una etiqueta que no
existe. Las instrucciones que no son de esta parte (aritmética, comparaciones,
saltos, `print`) las traduce un doble de prueba hasta integrar las reales.

### MARS

1. Instalar Java y copiar `Mars4_5.jar` en `tools/`.
2. `python -m unittest tests.test_mips_mars -v` ejecuta las pruebas en MARS.
3. Para abrir un programa en la interfaz de MARS:
   `python tests/mips_doubles.py examples/08_recursividad.cps salida.asm`
   (agregar `--traza` para imprimir la traza de activaciones).

## 8. Supuestos y limitaciones

- **Paso por valor.** Los arreglos, cadenas y objetos son referencias de una
  palabra: pasarlos permite modificar el original.
- **Registros y llamadas.** Antes de cada llamada se escriben a memoria los
  registros modificados y al volver se olvidan. Es correcto con recursión y
  con funciones anidadas (la función llamada puede leer variables del
  llamador); una asignación de registros más fina podría guardar sólo los
  necesarios.
- **Redefinición de métodos.** El despacho dinámico supone que un método
  redefinido conserva la firma; si cambiara el tipo de un parámetro
  (`boolean` de 1 byte vs. `integer` de 4), los argumentos quedarían en
  desplazamientos distintos.
- **Sin desbordamiento de pila.** No se verifica que la pila tenga espacio;
  una recursión sin fin termina con un error del simulador.
- **Traza.** Imprime sólo parámetros `integer` y `boolean` (`true` = 1); la
  traza es opcional y no se incluye en el programa normal.
- **Funciones como valores.** La gramática no permite guardar funciones en
  variables, así que no hay closures que sobrevivan a la función que las
  contiene; el enlace de acceso siempre apunta a un marco vivo.
