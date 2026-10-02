# Persona 2: generación de TAC para control de flujo

## Alcance y arquitectura

`src/tac_control_flow.py` define `ControlFlowMixin`, integrado en `TACGenerator`.
Trabaja sobre el AST existente; no implementa otro lexer/parser, no ejecuta
Compiscript ni interpreta TAC. Usa `TACOp`, `Label`, `Const`, `Temp`, el
`TempAllocator` y las funciones del generador de Persona 1.

Incluye etiquetas, `if/else`, `while`, `do-while`, `for`, `foreach`,
`switch/case/default`, `break`, `continue`, `&&`, `||`, `!` en condiciones,
comparaciones mediante el generador existente y ternarios `?:`.

Funciones, llamadas, registros de activación, objetos, herencia, `try/catch` y
la visualización del TAC en el IDE quedan fuera de esta entrega de Persona 2.
El reparto original no asignó `try/catch`; el equipo debe asignarlo antes de
la entrega completa. Los nodos pendientes siguen generando un error explícito.

## Etiquetas y contextos

`new_label()` genera `L1`, `L2`, etc., sin repetir nombres dentro de una
generación y reiniciándose al crear otro generador. Los nombres reservados ya
están protegidos contra variables del usuario por Persona 1.

Cada `ControlContext` guarda un destino de `break` y, para ciclos, uno de
`continue`. La pila se restaura con `finally`, incluso si falla la traducción
del cuerpo. `break` usa el contexto más cercano; `continue` busca el ciclo
más cercano y omite los contextos de `switch`.

| Estructura | Destino de `continue` | Destino de `break` |
| --- | --- | --- |
| `while` | Evaluación de condición | Final del ciclo |
| `do-while` | Condición, después del cuerpo | Final del ciclo |
| `for` | Actualización | Final del ciclo |
| `foreach` | Incremento del índice | Final del ciclo |
| `switch` | Ciclo exterior, si existe | Final del switch |

La tabla de símbolos permite `break` dentro de ciclos o switch y mantiene
`continue` limitado a ciclos. Ambos contextos se reinician al analizar una
función, para que un salto no escape a una estructura que contiene su declaración.
Al implementar la generación de funciones, Persona 3 también debe guardar,
vaciar y restaurar `_control_stack` alrededor de cada cuerpo de función.

## Condiciones y valores booleanos

`generate_condition(expr, true_label, false_label)` produce dos posibles
destinos. Una condición simple se traduce así:

```text
t1 = x < 3
if t1 goto L1
goto L2
```

Para `a && b`, el destino verdadero de `a` lleva a evaluar `b`; el falso
lleva directamente al destino falso final. Para `a || b`, el verdadero
lleva al destino verdadero final y solo el falso evalúa `b`. `!` intercambia
los destinos. Se conserva la precedencia del AST y se respetan los efectos
secundarios de las expresiones de la derecha.

Cuando se necesita un valor, como en `let b = x > 0 && x < 5`, se reserva
un temporal de resultado y se asigna `true` o `false` en ramas excluyentes.
El ternario reserva igualmente un resultado y copia en él solo el valor de
la rama seleccionada. Ninguna rama puede reciclar ese resultado anticipadamente.

## Condicionales y ciclos

`if` salta a su cuerpo o al final. Con `else`, el cuerpo verdadero termina
con un salto que evita entrar en el cuerpo falso.

```text
// if (x > 0) { print(1); } else { print(2); }
t1 = x > 0
if t1 goto L1
goto L2
L1:
print 1
goto L3
L2:
print 2
L3:
```

`while` ubica la condición en la cabecera y regresa a ella después del cuerpo.
`do-while` comienza con el cuerpo y evalúa después. `for` emite inicialización
una vez, condición en la cabecera, cuerpo, actualización y salto a cabecera.
Las partes opcionales del `for` se omiten; sin condición, solo `break` u otro
salto puede salir del ciclo representado.

## Foreach y temporales persistentes

Se evalúa el iterable una vez. Si es una variable, se copia su referencia a
un temporal para conservar el arreglo original aunque el cuerpo reasigne la
variable. Se reservan un índice y una longitud; los arreglos TAC tienen tamaño
fijo y la longitud se consulta al entrar. En cada iteración se compara el índice,
se carga el elemento en la variable de iteración y se traduce el cuerpo.
Después se incrementa el índice y se vuelve a comparar.

El arreglo, índice y longitud permanecen reservados durante la traducción
del cuerpo, también en ciclos anidados. No se usa `compute` para operar con
ellos porque liberaría valores que todavía se necesitan. Al terminar se
liberan una sola vez. La variable de iteración se resuelve desde el ámbito del
cuerpo, respetando el shadowing.

## Switch

Se evalúa el selector una vez y se conserva su valor. Los casos se comparan en
orden, saltando al primer acierto; si ninguno coincide se pasa a `default` o
al final si no existe. Los cuerpos conservan **fall-through**: sin `break`,
se continúa al siguiente cuerpo sin volver a comparar su caso. `break` sale
solo del switch más cercano. Esta es una decisión de traducción documentada,
pues la gramática describe la sintaxis, pero no define el fall-through.

Los valores de case pueden ser expresiones según la gramática. Se evalúan en
orden hasta el primer acierto. El selector se copia cuando es una variable
para evitar que un case con asignaciones cambie el valor comparado.

## Integración y errores

La entrada `generate_tac(table, program)` conserva su contrato: el llamador
debe comprobar primero los diagnósticos léxicos, sintácticos y semánticos.
Un AST recuperado no constituye autorización para generar TAC. Ante un fallo
de generación, tampoco debe mostrarse el programa parcialmente construido.
El futuro pipeline del IDE debe aplicar ambas reglas y limpiar resultados
anteriores cuando el código actual tenga errores.

`generate_statement` verifica el balance de temporales en cada sentencia.
Los destinos de salto inválidos son rechazados incluso si alguien omite la
validación semántica. La generación de cada rama usa el mismo generador y la
misma tabla de símbolos.

## Verificación

Desde `Proyecto 2`:

```powershell
python -m unittest discover -s tests -v
```

Para correr únicamente los nuevos casos:

```powershell
python -m unittest discover -s tests -p test_tac_control_flow.py -v
```

Las pruebas inspeccionan instrucciones, etiquetas y destinos; no ejecutan el
programa fuente ni implementan un intérprete. Cubren ramas excluyentes,
cortocircuito con asignaciones, ternarios anidados, partes opcionales del for,
destinos de continue, switch con y sin break, ciclos anidados, snapshots,
temporales persistentes, balance, etiquetas deterministas y errores múltiples.

Archivos de calificación:

- `examples/tac_control_flujo.cps`: válido, combina las estructuras implementadas.
- `examples/tac_control_flujo_errores.cps`: inválido, exige varios diagnósticos.

La generación no tiene una opción para ejecutar TAC. La integración gráfica
de estos ejemplos y el resto de los componentes sigue a cargo de Persona 3.

## Entrega a Persona 3

La entrada pública es `generate_tac(table, program)` en `src/tac_generator.py`.
Debe recibir el mismo AST usado para construir la tabla, porque los ámbitos
y tipos están asociados por identidad de nodo. Crear un generador nuevo por
compilación evita conservar instrucciones, temporales o etiquetas anteriores.

Orden de integración en el IDE:

1. Analizar el texto con `CompiscriptAnalyzer`.
2. Construir la tabla con `build_symbol_table` y validar tipos con `analyze_semantics`.
3. Reunir todos los diagnósticos; si existen, borrar el TAC previo y omitir su generación.
4. Si hay un AST válido sin diagnósticos, llamar a `generate_tac`.
5. Capturar `TACGenerationError`, mostrar su mensaje y ubicación, y descartar cualquier TAC parcial.
6. Mostrar `TACProgram.render()` dentro del IDE. Cada instrucción conserva su línea de origen.

Para funciones, agregar `visit_function_declaration`, `visit_call_expression`
y `visit_return_statement`, reutilizando las operaciones ya declaradas en
`TACOp`. Las llamadas usadas dentro de condiciones o ternarios deben devolver
un operando con el mismo contrato de propiedad de temporales de las demás
expresiones. Los temporales de cada función deben pertenecer a su entorno de
activación, especialmente al implementar recursión. No reiniciar el contador
de etiquetas dentro del mismo programa.

Pendientes del proyecto completo: funciones y llamadas, registros de activación
y direcciones, objetos y herencia, visualización de TAC en el IDE y asignar
la implementación de `try/catch`. Los ejemplos de control de flujo se pueden
usar para comprobar que esas integraciones conservan esta parte.
