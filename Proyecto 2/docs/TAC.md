# Lenguaje intermedio: código de tres direcciones (TAC)

Este documento define el código intermedio que genera el compilador de Compiscript: qué instrucciones existen, cómo se escriben, cómo se traducen las expresiones y cómo se asignan y reciclan las variables temporales. Todas las fases que emiten TAC usan esta misma especificación.

| Archivo | Contenido |
| --- | --- |
| `src/tac.py` | Operandos, conjunto de instrucciones (`TACOp`), `TACInstruction`, `TACProgram` |
| `src/temporaries.py` | Algoritmo de asignación y reciclaje de temporales (`TempAllocator`) |
| `src/tac_generator.py` | Visitor que recorre el AST y emite TAC (`TACGenerator`, `generate_tac`) |
| `src/tac_control_flow.py` | Condiciones, cortocircuito, ternario, ciclos y switch (`ControlFlowMixin`) |
| `tests/test_tac.py`, `tests/test_temporaries.py`, `tests/test_tac_expressions.py` | Pruebas |
| `tests/test_tac_control_flow.py` | Pruebas estáticas de traducción del control de flujo, anidamiento y casos fallidos |

## 1. Lugar en el compilador

```text
código .cps ──> lexer/parser ──> AST ──> tabla de símbolos ──> análisis semántico
                                   │            │                      │
                                   │            └── node_scopes        └── tipos de expresiones
                                   ▼                     ▼                      ▼
                                   └──────────────> TACGenerator ──> TACProgram (texto TAC)
```

El generador sólo se ejecuta si el programa no tiene errores léxicos, sintácticos ni semánticos. Así, el TAC puede asumir que los tipos ya son correctos (por ejemplo, un `+` entre `string` siempre es una concatenación válida).

## 2. Forma de una instrucción

Cada instrucción es una **cuádrupla** `(op, result, arg1, arg2)`:

| Campo | Significado |
| --- | --- |
| `op` | Operación (`TACOp`) |
| `result` | Destino: temporal, variable o etiqueta. Vacío en instrucciones que no producen valor |
| `arg1`, `arg2` | Operandos. Como máximo dos, de ahí "tres direcciones" |
| `line` | Línea del código fuente que originó la instrucción. No se imprime; sirve para relacionar TAC y editor |

Se eligieron cuádruplas en lugar de triples porque el resultado tiene nombre propio (`t1`, `x`). Así una instrucción puede moverse o eliminarse sin renumerar las referencias de las demás, y el nombre del resultado es justamente lo que recicla el algoritmo de temporales.

Al crear una instrucción se valida que tenga los campos obligatorios de su operación; si falta alguno se lanza `TACError`. Una cuádrupla incompleta nunca llega al programa.

Al imprimir, las etiquetas y los límites de función (`begin_func`, `end_func`) van al margen y el resto con sangría de cuatro espacios.

## 3. Operandos

| Clase | Se imprime | Qué representa |
| --- | --- | --- |
| `Temp(n)` | `t1`, `t2`, … | Valor intermedio creado por el compilador (sección 6) |
| `Var(name, symbol)` | `x`, `edad`, `a$1` | Variable, constante o parámetro del programa. Guarda su `Symbol` de la tabla de símbolos |
| `Const(value, type)` | `5`, `-3`, `"hola"`, `true`, `null` | Literal. Los `string` van entre comillas con `\"`, `\\`, `\n` y `\t` escapados |
| `Label(name)` | `L1`, `L2`, … | Destino de un salto |
| `Name(name)` | `suma`, `Perro`, `nombre` | Nombre de función, clase o atributo. No es un valor que se pueda almacenar |

### Nombres de variables

- Una variable aparece en el TAC con su nombre original.
- Cada nombre del TAC identifica **un único símbolo en todo el programa**. Si dos símbolos se llaman igual (shadowing en bloques anidados, o locales de funciones distintas), el segundo se escribe `nombre$1`, el tercero `nombre$2`, etc. `$` no es válido en un identificador de Compiscript, así que el nombre nunca choca con otra variable.
- Los nombres con la forma `t<número>` o `L<número>` quedan reservados para temporales y etiquetas. Una variable del usuario llamada `t1` se escribe `t1$1`.
- El operando `Var` conserva la referencia al `Symbol` (tipo, ámbito y la información que agregue la tabla de símbolos, como direcciones) para las fases posteriores.

```text
let a = 1;                a = 1
{ let a = 2; print(a); }  a$1 = 2
                          print a$1
print(a);                 print a
```

## 4. Conjunto de instrucciones

`x`, `y` y `z` son cualquier operando que tenga valor (`Temp`, `Var` o `Const`).

### Copia y operaciones

| Operación | Forma | Significado |
| --- | --- | --- |
| `ASSIGN` | `x = y` | Copia el valor de `y` en `x` |
| `ADD` `SUB` `MUL` `DIV` `MOD` | `x = y + z` (`-` `*` `/` `%`) | Aritmética entera. `/` es división entera |
| `CONCAT` | `x = concat y, z` | Concatenación de `string` |
| `LT` `LE` `GT` `GE` | `x = y < z` (`<=` `>` `>=`) | Comparación de enteros; `x` queda `true` o `false` |
| `EQ` `NE` | `x = y == z` (`!=`) | Igualdad y desigualdad |
| `NEG` | `x = minus y` | Negación aritmética |
| `NOT` | `x = not y` | Negación lógica |

`CONCAT` es una operación aparte (y no `ADD`) porque su código final es muy distinto: reserva memoria y copia caracteres. El generador la elige a partir del tipo que el analizador semántico infiere para la expresión.

### Saltos

| Operación | Forma | Significado |
| --- | --- | --- |
| `LABEL` | `L1:` | Marca una posición del programa |
| `GOTO` | `goto L1` | Salto incondicional |
| `IF_TRUE` | `if x goto L1` | Salta si `x` es `true` |
| `IF_FALSE` | `ifFalse x goto L1` | Salta si `x` es `false` |

En estas instrucciones la etiqueta destino va en `result` y la condición en `arg1`.

### Funciones

| Operación | Forma | Significado |
| --- | --- | --- |
| `BEGIN_FUNC` | `begin_func f` o `begin_func f, n` | Inicio del cuerpo de la función `f`. `n` es opcional (por ejemplo, el tamaño de su registro de activación) |
| `END_FUNC` | `end_func f` | Fin del cuerpo de `f` |
| `PARAM` | `param x` | Apila un argumento para la próxima llamada |
| `CALL` | `x = call f, n` o `call f, n` | Llama a `f` con los últimos `n` argumentos apilados. Con destino, guarda el valor de retorno |
| `RETURN` | `return x` o `return` | Regresa de la función actual, con o sin valor |

### Arreglos

| Operación | Forma | Significado |
| --- | --- | --- |
| `NEW_ARRAY` | `x = new_array n` | Crea un arreglo de `n` elementos |
| `INDEX_LOAD` | `x = y[i]` | Lee el elemento `i` de `y` |
| `INDEX_STORE` | `x[i] = y` | Escribe `y` en el elemento `i` de `x` |
| `LENGTH` | `x = len y` | Cantidad de elementos de `y` |

### Objetos y salida

| Operación | Forma | Significado |
| --- | --- | --- |
| `NEW_OBJECT` | `x = new C` | Crea una instancia de la clase `C` (sin llamar al constructor) |
| `FIELD_LOAD` | `x = y.f` | Lee el atributo `f` de `y` |
| `FIELD_STORE` | `x.f = y` | Escribe `y` en el atributo `f` de `x` |
| `PRINT` | `print x` | Imprime `x` |

## 5. Traducción de expresiones

El generador es un Visitor. Visitar una expresión emite las instrucciones que la calculan y **devuelve el operando** donde queda su valor:

| Expresión | Instrucciones emitidas | Operando devuelto |
| --- | --- | --- |
| Literal `5`, `"hola"`, `true`, `null` | ninguna | `Const` |
| Literal negativo `-5` | ninguna | `Const(-5)` |
| Identificador `x` | ninguna | `Var` |
| `( e )` | las de `e` | el de `e` |
| `e1 op e2` | las de `e1`, las de `e2`, `t = p1 op p2` | `t` |
| `op e` (`-`, `!`) | las de `e`, `t = minus p` / `t = not p` | `t` |
| `x = e` | las de `e`, `x = p` | `x` |
| `a[i] = e` | las de `a`, `i` y `e`, `pa[pi] = pe` | `pe` |
| `[e0, …, en-1]` | `t = new_array n`, y por cada elemento: las de `ek`, `t[k] = pk` | `t` |
| `a[i]` | las de `a` y de `i`, `t = pa[pi]` | `t` |

Las declaraciones `let`, `var` y `const` con inicializador se traducen como una asignación (`x = p`). Sin inicializador no emiten nada: reservar espacio para la variable le corresponde al registro de activación, no al TAC. `print(e)` emite `print p`. Una expresión usada como instrucción (`e;`) emite sus instrucciones y descarta el resultado.

**Ejemplo** (el mismo del enunciado):

```text
let x = a + b * 5;          t1 = b * 5
                            t1 = a + t1
                            x = t1
```

```text
let y = (a * b) + (a - c) * (b % 2);      t1 = a * b
                                          t2 = a - c
                                          t3 = b % 2
                                          t2 = t2 * t3
                                          t1 = t1 + t2
                                          y = t1
```

```text
let s = "Hola " + nombre + "!";          t1 = concat "Hola ", nombre
                                         t1 = concat t1, "!"
                                         s = t1
```

```text
let lista = [1, a + 1];                  t1 = new_array 2
lista[1] = lista[0] * -2;                t1[0] = 1
                                         t2 = a + 1
                                         t1[1] = t2
                                         lista = t1
                                         t1 = lista[0]
                                         t1 = t1 * -2
                                         lista[1] = t1
```

## 6. Asignación y reciclaje de temporales

### Idea

En una expresión, el valor de cada subárbol lo consume **una sola vez** su nodo padre. Por eso un temporal puede liberarse en el momento en que se usa como operando, y quedar disponible para el siguiente resultado.

### Algoritmo (`TempAllocator`)

1. **`new()`**: si hay temporales libres, entrega el de **menor índice**; si no, crea uno nuevo (`t1`, `t2`, …). Elegir el menor hace la salida determinista y mantiene los índices bajos. Los libres se guardan en un montículo (heap), así que la operación cuesta O(log n).
2. **`release(op)`**: si `op` es un temporal, vuelve a quedar libre. Si es una variable o constante no hace nada, así que el generador puede liberar cualquier operando sin revisar de qué clase es.
3. En cada operación, el generador **libera los operandos antes de pedir el temporal del resultado**. Por eso el resultado puede ocupar el lugar de uno de sus operandos (`t1 = t1 + t2`). Esto es seguro porque la instrucción lee sus operandos antes de escribir el resultado.

```python
def compute(op, arg1, arg2):
    temps.release(arg1)
    temps.release(arg2)
    result = temps.new()
    emit(op, result, arg1, arg2)
    return result
```

### Traza de ejemplo

`y = (a * b) + (a - c) * (b % 2)`:

| Instrucción | Libera | Recibe | Vivos después |
| --- | --- | --- | --- |
| `t1 = a * b` | — | `t1` (nuevo) | {t1} |
| `t2 = a - c` | — | `t2` (nuevo) | {t1, t2} |
| `t3 = b % 2` | — | `t3` (nuevo) | {t1, t2, t3} |
| `t2 = t2 * t3` | t2, t3 | `t2` (reciclado) | {t1, t2} |
| `t1 = t1 + t2` | t1, t2 | `t1` (reciclado) | {t1} |
| `y = t1` | t1 | — | {} |

Sin reciclaje, la misma expresión habría necesitado cinco temporales. Con reciclaje:
- Una cadena `a + a + a + a` usa sólo `t1`.
- Cada instrucción nueva vuelve a empezar desde `t1`.
- Un temporal sólo sigue vivo mientras su valor está pendiente de consumirse. Es el mínimo posible si se evalúa de izquierda a derecha.

### Garantías y detección de errores

- **Propiedad del temporal.** Quien recibe un `Temp` al visitar una expresión es su dueño: debe usarlo exactamente una vez y liberarlo.
- **Valores persistentes de control.** `foreach` y `switch` pueden leer el mismo temporal varias veces: lo mantienen reservado durante toda su vida útil y lo liberan una sola vez. No deben pasar un operando persistente a `compute`, porque este lo libera. Los resultados booleanos y ternarios se reservan antes de traducir sus ramas.
- **Balance por instrucción.** `generate_statement` verifica que cada instrucción del programa termine con la misma cantidad de temporales vivos con la que empezó. Si alguna "olvida" liberar un temporal, se lanza `TACGenerationError` en lugar de ir agotando índices en silencio. Se compara contra la cantidad inicial, y no contra cero, para que una construcción pueda mantener vivo un temporal mientras traduce instrucciones internas (por ejemplo, el arreglo que recorre un `foreach`).
- **Mal uso detectado.** Liberar dos veces un temporal, o uno que nunca se entregó, lanza `TempAllocatorError`.
- **Estadísticas.** `created` (nombres distintos), `max_live` (máximo de temporales vivos a la vez), `allocations` y `reuses`.

## 7. Supuestos y decisiones de traducción

- **Orden de evaluación.** Los operandos se evalúan de izquierda a derecha, y las subexpresiones no se reordenan para ahorrar temporales porque pueden tener efectos secundarios (asignaciones y llamadas).
- **Variables leídas en el momento de la operación.** Una variable se usa directamente como operando, sin copiarla antes a un temporal. En casos como `a + (a = 5)`, donde la misma expresión lee y modifica `a`, el TAC lee el valor ya modificado. Compiscript no define otro orden para estos casos.
- **Sin optimizaciones.** No se pliegan constantes (`2 + 3` genera `t1 = 2 + 3`). La excepción es el menos unario sobre un literal entero (`-5`): la gramática no tiene literales negativos y se trata como la constante `-5`.
- **Asignaciones como expresión.** `x = e` devuelve `x`, así que `a = b = e` produce `b = pe` y luego `a = b`. `a[i] = e` devuelve el valor de `e`.
- **Arreglos.** Los índices del TAC cuentan **elementos**, no bytes. Traducirlos a desplazamientos en memoria según el tamaño de cada elemento le corresponde a la generación de código final.
- **Programas con errores.** Si el AST contiene un `ErrorExpression`, el generador lanza `TACGenerationError`: no se genera TAC a partir de un programa inválido.
- **Construcciones todavía sin traducción.** Un nodo sin traducción definida lanza `TACGenerationError` con su nombre y ubicación, en lugar de producir TAC incompleto.

## 8. Cómo extender el generador

Para agregar la traducción de una construcción nueva se define su `visit_<nodo>` en `TACGenerator` (o en un mixin que la clase herede), usando:

| Miembro | Uso |
| --- | --- |
| `self.visit(expr)` | Traduce una subexpresión y devuelve su operando |
| `self.compute(op, a, b)` | Emite `t = a op b`, liberando `a` y `b`, y devuelve `t` |
| `self.emit(op, result, arg1, arg2)` | Emite cualquier instrucción de la sección 4 |
| `self.temps.new()` / `self.temps.release(op)` | Maneja temporales a mano cuando `compute` no aplica |
| `self.variable(node, name)` | Operando `Var` para un identificador, visto desde `node` |
| `self.generate_statement(s)` / `self.generate_statements(ss)` | Traduce instrucciones verificando el balance de temporales |
| `self.type_of(expr)` | Tipo (`semantic_analyzer.Type`) inferido para una expresión |

## 9. Control de flujo

La traducción de Persona 2 está implementada en `ControlFlowMixin`, del que
hereda `TACGenerator`. Usa las mismas operaciones y el mismo asignador de temporales.
Incluye `if/else`, `while`, `do-while`, `for`, `foreach`, `switch`, `break`,
`continue`, cortocircuito `&&` / `||` y el ternario `?:`.

Los algoritmos, ejemplos, supuestos y contrato para integrar funciones están
documentados en [CONTROL_FLUJO.md](CONTROL_FLUJO.md).
