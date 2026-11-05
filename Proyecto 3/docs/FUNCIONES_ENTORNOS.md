# Persona 3: funciones, entornos de ejecución, tabla de símbolos e integración

Este documento describe la parte del compilador que traduce funciones,
llamadas, clases, objetos, herencia y `try/catch` a TAC; las nuevas
funcionalidades de la tabla de símbolos (direcciones y registros de
activación); y la integración de todas las fases en el IDE. El lenguaje
intermedio común está definido en [TAC.md](TAC.md) y el control de flujo en
[CONTROL_FLUJO.md](CONTROL_FLUJO.md).

| Archivo | Contenido |
| --- | --- |
| `src/symbol_table.py` | Modelo extendido: `StorageKind`, `FrameSlot`, `ActivationRecord`, `ClassLayout` y campos nuevos de `Symbol` y `SymbolTable` |
| `src/memory_layout.py` | Cálculo de direcciones, tamaños, registros de activación, distribución de objetos y vtables |
| `src/tac_functions.py` | `FunctionMixin`: funciones, parámetros, `return`, llamadas y recursión |
| `src/tac_objects.py` | `ObjectMixin`: clases, `new`, atributos, `this`, herencia y despacho dinámico |
| `src/tac_exceptions.py` | `ExceptionMixin`: `try/catch` y su interacción con `break`, `continue` y `return` |
| `src/compiler.py` | Pipeline completo (`compile_source`) usado por el IDE y las pruebas de integración |
| `src/ui.py` | IDE: pestañas «Código intermedio» y «Entornos», direcciones en «Símbolos» |
| `tests/test_memory_layout.py` | Tabla de símbolos, direcciones, entornos y registros de activación |
| `tests/test_tac_functions.py` | Funciones, parámetros, `return`, llamadas y recursión |
| `tests/test_tac_objects.py` | Clases, objetos, herencia y despacho dinámico |
| `tests/test_tac_try_catch.py` | `try/catch` |
| `tests/test_compiler.py` | Integración completa con todos los archivos de `examples/` |

## 1. Nuevas funcionalidades de la tabla de símbolos

La tabla de símbolos del Proyecto 1 sabía *qué* es cada identificador
(nombre, categoría, tipo, ámbito). Para generar código objeto también hace
falta saber dónde vive en tiempo de ejecución y cuánto ocupa. Estos son
los campos agregados:

| Elemento | Campo | Significado |
| --- | --- | --- |
| Variable, constante, parámetro, atributo | `storage` | Clase de almacenamiento: `global`, `parámetro`, `local` o `atributo` |
| | `offset`, `size` | Desplazamiento y tamaño en bytes |
| | `address` | Dirección simbólica: `global+8`, `fp+16` u `obj+4` |
| | `runtime_type` | Tipo declarado o, si falta la anotación, el inferido por el análisis semántico |
| | `owner` | Registro de activación (o clase) que lo aloja |
| Función, método, constructor | `tac_label` | Etiqueta única en el TAC (`factorial`, `Perro.hablar`, `ayuda$1`) |
| | `activation_record` | Su `ActivationRecord` |
| Clase | `class_layout` | Su `ClassLayout`: atributos con desplazamiento, vtable y tamaño de la instancia |
| `SymbolTable` | `global_record` | Área estática: variables globales y temporales del código global |
| | `activation_records` | Registros de todas las funciones, métodos e inicializadores |
| | `class_layouts` | Distribución de cada clase |
| | `record(nombre)` | Busca un registro por su etiqueta TAC |

`memory_layout.assign_memory_layout(table, symbol_types)` llena estos
campos. Se ejecuta después del análisis semántico y sólo si el programa
no tiene errores, por dos razones: una variable sin anotación
(`let x = true;`) ocupa el tamaño de su tipo inferido, y un programa
inválido no debe producir entornos de ejecución. No recorre el AST: todo lo
que necesita está en la jerarquía de `Scope`.

### Tamaños y alineación

| Tipo | Bytes |
| --- | --- |
| `integer` | 4 |
| `boolean` | 1 |
| `string`, arreglos, objetos, `null` | 4 (referencia) |

Cada dato se alinea a su tamaño (como máximo a 4 bytes) y cada registro
termina alineado a 4. Por ejemplo, después de un `boolean` en `+16`, un
`integer` queda en `+20`, no en `+17`.

### Clases de almacenamiento

- **Global**: variables declaradas fuera de toda función, incluidas las de
  bloques, `for`, `foreach` y `catch` del código global. Tienen dirección
  fija `global+k` en el área estática.
- **Parámetro** y **local**: viven en el registro de activación de su
  función, direccionadas desde `fp` (el inicio del registro). Las variables
  de bloques internos de una función se alojan en el registro de esa
  función; una variable sombreada recibe su propia casilla.
- **Atributo**: desplazamiento dentro de cada instancia, `obj+k`.

## 2. Registros de activación

Cada función, método, constructor e inicializador de atributos tiene un
registro con esta forma (desplazamientos en bytes desde `fp`):

```text
 fp+0   ┌───────────────────────────┐
        │ dirección de retorno      │  instrucción a la que vuelve el llamador
 fp+4   ├───────────────────────────┤
        │ enlace de control         │  fp del registro del llamador
 fp+8   ├───────────────────────────┤
        │ enlace de acceso          │  fp del registro que la contiene léxicamente
 fp+12  ├───────────────────────────┤
        │ this                      │  sólo en métodos, constructores e inicializadores
        ├───────────────────────────┤
        │ parámetros, en orden      │  los deja el llamador con «param»
        ├───────────────────────────┤
        │ variables locales         │  incluidas las de bloques internos
        ├───────────────────────────┤
        │ temporales t1 … tn        │  una palabra cada uno
        └───────────────────────────┘
```

El tamaño total es el que aparece en `begin_func f, n`. Ejemplo:

```text
function f(a: integer, b: boolean): integer {     registro «f» (32 bytes)
  let c: integer = a * 2;                          +0  dirección de retorno
  { let d = c; print(d); }                         +4  enlace de control
  return c;                                        +8  enlace de acceso
}                                                  +12 a  (parámetro, 4)
                                                   +16 b  (parámetro, 1)
                                                   +20 c  (local, 4)
                                                   +24 d  (local, 4)
                                                   +28 t1 (temporal, 4)
```

- **Temporales.** El generador traduce cada función con su propio
  `TempAllocator`; al terminar, la cantidad de temporales distintos que usó
  se guarda en `ActivationRecord.temporaries`. Como cada activación tiene
  sus propios temporales, una llamada recursiva no destruye los valores
  pendientes del llamador (en `fib(n - 1) + fib(n - 2)`, `t1` conserva el
  primer resultado mientras se ejecuta la segunda llamada).
- **Funciones anidadas y closures.** `level` es la profundidad léxica
  (global 0, funciones de primer nivel 1, anidadas 2, ...). `parent` nombra
  el registro al que apunta el enlace de acceso. Si `interno` (nivel 2)
  usa una variable de `externo` (nivel 1), la tabla ya sabe en qué registro
  y desplazamiento está (`owner`, `offset`) y cuántos enlaces de acceso hay
  que seguir (diferencia de niveles). `Symbol.captured_names`, del
  Proyecto 1, lista esas variables capturadas.
- **Área global.** `table.global_record` no tiene encabezado: contiene las
  variables globales y los temporales del código global.

## 3. Traducción de funciones

### Definiciones

Cada función es una unidad de generación (`FunctionMixin.generate_unit`):

1. Reserva su lugar en la lista de secciones (así una función externa
   aparece antes que las anidadas en ella).
2. Guarda y reinicia el estado propio de una activación: búfer de
   instrucciones, asignador de temporales, pila de `break`/`continue` y pila
   de manejadores de `try`. Ninguna de esas cosas cruza la frontera de una
   función: un `break` dentro de una función declarada en un ciclo no puede
   saltar al ciclo exterior. El estado se restaura con `finally` aunque la
   traducción falle.
3. Traduce el cuerpo y lo envuelve con `begin_func etiqueta, tamaño` y
   `end_func etiqueta`.

El programa final tiene primero todas las secciones y después el código
global, que es el punto de entrada. Una declaración de función no emite
nada en el lugar donde aparece. Los parámetros tampoco emiten instrucciones:
el llamador ya dejó sus valores con `param` y la tabla guarda su posición.
`return e` emite las instrucciones de `e` y `return p`; `return;` emite
`return`. Llegar a `end_func` equivale a `return` sin valor.

### Llamadas

Se sigue la convención del libro del Dragón: se evalúan todos los
argumentos de izquierda a derecha y después se emiten los `param` seguidos
y la llamada. Así los `param` de una llamada nunca se intercalan con los de
una llamada anidada en sus argumentos:

```text
let x = f(y + 1, g(y * 2));        t1 = y + 1
                                   t2 = y * 2
                                   param t2
                                   t2 = call g, 1
                                   param t1
                                   param t2
                                   t1 = call f, 2
                                   x = t1
```

- Una función con tipo de retorno produce `t = call f, n`; el temporal
  cumple el mismo contrato de propiedad que cualquier otra expresión, por
  lo que una llamada puede aparecer en condiciones, ternarios, argumentos o
  concatenaciones.
- Un procedimiento (sin tipo de retorno) produce `call f, n` sin destino.
- Los argumentos y el destino de la llamada se liberan antes de pedir el
  temporal del resultado, así que el resultado puede reutilizar uno de
  ellos (`t1 = call factorial, 1` después de `param t1`).

### Recursión

No requiere nada especial: la etiqueta de la función ya está en la tabla
antes de traducir su cuerpo (el Proyecto 1 registra las firmas antes que los
cuerpos), y cada activación tiene su propio registro con parámetros,
locales y temporales. La recursión mutua (`esPar` llama a `esImpar`,
declarada después) funciona igual.

## 4. Clases, objetos y herencia

### Distribución de una instancia

```text
class Animal { let nombre: string; let edad: integer = 1; ... }
class Perro : Animal { let vacunado: boolean; let raza: string; ... }

Animal (12 bytes)            Perro (20 bytes)
+0  puntero a vtable         +0  puntero a vtable
+4  nombre                   +4  nombre      ← heredado, mismo desplazamiento
+8  edad                     +8  edad        ← heredado
                             +12 vacunado
                             +16 raza
```

Los atributos heredados conservan su desplazamiento: un `Perro` puede
usarse donde se espera un `Animal` y el código de `Animal` encuentra sus
atributos en el mismo lugar.

### Vtable y despacho dinámico

Cada clase tiene una tabla de métodos virtuales. La de una subclase empieza
como copia de la de su superclase; una redefinición reemplaza la entrada en
la misma posición y un método nuevo se agrega al final:

```text
Animal: [0] hablar → Animal.hablar   [1] comer → Animal.comer
Perro:  [0] hablar → Perro.hablar    [1] comer → Animal.comer   [2] correr → Perro.correr
```

Una llamada a método obtiene la implementación desde el objeto, no desde el
tipo estático de la variable:

```text
let a: Animal = new Perro("Rex");      t1 = method a.hablar     ← busca en la vtable de a
print(a.hablar());                     param a                  ← this
                                       t1 = call t1, 1
                                       print t1
```

`method a.hablar` se traduce en el backend como «leer `vtable[i]` del
objeto», donde `i` es el índice de `hablar` en la vtable del tipo estático
(`ClassLayout.method_index`); como las posiciones se conservan en las
subclases, el índice es válido para cualquier objeto de ese tipo o derivado.
El constructor no está en la vtable: no se hereda por despacho dinámico.

### Instanciación

`new C(args)`:

1. Evalúa los argumentos.
2. `t = new C` reserva `ClassLayout.size` bytes y guarda el puntero a la
   vtable de `C`.
3. Llama a `K.$init` para cada clase `K` de la cadena de herencia, desde la
   raíz, que tenga atributos con valor inicial (`let x: integer = 0;` en el
   cuerpo de la clase). Así los atributos heredados quedan inicializados
   aunque la subclase defina su propio constructor.
4. Llama al constructor vigente con el objeto como primer parámetro: el de
   `C` o, si no tiene, el heredado más cercano.

```text
let p: Perro = new Perro("Toby");      t1 = new Perro
                                       param t1
                                       call Animal.$init, 1
                                       param t1
                                       param "Toby"
                                       call Animal.constructor, 2
                                       p = t1
```

### Atributos y `this`

- `o.f` produce `t = o.f`; `o.f = e` produce `o.f = p`.
- Dentro de un método, `this` es su primer parámetro implícito.
- Un atributo nombrado sin `this.` (lo permite la tabla de símbolos del
  Proyecto 1, que resuelve hacia el ámbito de la clase) se traduce como
  `this.atributo`; un parámetro o local con el mismo nombre tiene prioridad.
  Un método llamado sin `this.` se despacha sobre `this`.

## 5. `try/catch`

Compiscript no tiene `throw`; las excepciones son errores de ejecución
(índice fuera de rango, división entre cero, acceso a `null`). El catch
recibe el mensaje del error, por lo que su variable es de tipo `string`
(este tipo se registra en la tabla de símbolos).

```text
try {                                  try_begin L1
  print(xs[3]);                        t1 = xs[3]
} catch (e) {                          print t1
  print("Error: " + e);                try_end
}                                      goto L2
                                   L1:
                                       e = exception
                                       t1 = concat "Error: ", e
                                       print t1
                                   L2:
```

- Los manejadores forman una pila. Al ocurrir un error, el entorno de
  ejecución retira el manejador más reciente y salta a su etiqueta; si el
  error ocurrió en una función llamada desde el `try`, primero descarta los
  registros de activación hasta el que instaló el manejador.
- `break`, `continue` y `return` que salen de uno o más `try` emiten antes
  un `try_end` por cada manejador abandonado; así la pila nunca conserva un
  manejador de un bloque que ya terminó. `return e` calcula `e` **antes**
  de retirar los manejadores, para que un error al calcularlo todavía sea
  atrapado.
- Una función declarada dentro de un `try` no hereda sus manejadores
  estáticamente: su pila empieza vacía.

## 6. Integración

```text
código .cps
   │
   ▼
compiler.compile_source
   ├─ CompiscriptAnalyzer ─────────► diagnósticos léxicos/sintácticos + AST
   ├─ build_symbol_table ──────────► ámbitos y símbolos + diagnósticos
   ├─ analyze_semantics ───────────► diagnósticos de tipos y flujo
   │
   │  ¿hay algún diagnóstico? ── sí ──► CompilationResult sin TAC
   │            no
   ▼
prepare_generator
   ├─ infer_types ─────────────────► tipos de expresiones y de símbolos
   └─ assign_memory_layout ────────► direcciones y registros en la tabla
   ▼
TACGenerator.generate
   ├─ expresiones y temporales      (Persona 1)
   ├─ ControlFlowMixin              (Persona 2)
   └─ FunctionMixin, ObjectMixin, ExceptionMixin   (Persona 3)
   ▼
CompilationResult: diagnósticos, tabla, TAC, estadísticas de temporales
   ▼
IDE (ui.py)
```

- Si alguna fase reporta errores, no se genera TAC y el IDE limpia el
  resultado anterior.
- Si la generación falla (`TACGenerationError`), el error se muestra como
  diagnóstico de tipo «Generación» y no se entrega TAC parcial.
- `CompilationResult.temp_usage` reporta, por función y para el código
  global, temporales creados, reutilizaciones y máximo de vivos a la vez.

### IDE

El botón **Compilar (F5)** ejecuta `compile_source` y llena cinco pestañas:

| Pestaña | Contenido |
| --- | --- |
| Diagnósticos | Errores léxicos, sintácticos, semánticos y de generación, ordenados por ubicación |
| Código intermedio | El TAC con resaltado de sintaxis. Un clic en una instrucción resalta en el editor la línea que la originó. Botones para copiar y guardar como `.tac` |
| AST | Árbol sintáctico (Proyecto 1) |
| Símbolos | Ámbitos y símbolos con su dirección y tamaño |
| Entornos | Área global, registros de activación (con encabezado, `this`, parámetros, locales y temporales) y distribución de cada clase con su vtable |

Si la compilación es exitosa se abre «Código intermedio»; si hay errores,
«Diagnósticos».

## 7. Pruebas y ejemplos

```powershell
python -m unittest discover -s tests -v
```

| Archivo | Qué valida |
| --- | --- |
| `test_memory_layout.py` | Tamaños y alineación, direcciones globales/parámetros/locales/atributos, sombreado, tipos inferidos, registros de funciones, métodos y anidadas, etiquetas únicas, vtables, inicializadores, recálculo |
| `test_tac_functions.py` | Definiciones, `return`, procedimientos, orden de argumentos, llamadas en condiciones y expresiones, temporales por función, recursión simple, doble y mutua, funciones anidadas, aislamiento del estado; casos fallidos |
| `test_tac_objects.py` | Métodos, `new`, constructor heredado o propio, `$init`, atributos con y sin `this`, cadenas de miembros, despacho dinámico; casos fallidos |
| `test_tac_try_catch.py` | Estructura, anidamiento, `break`/`continue`/`return` dentro de `try` |
| `test_compiler.py` | Todos los ejemplos válidos producen TAC bien formado (secciones balanceadas, saltos válidos, registros y direcciones para todo lo usado); todos los inválidos reportan errores y no producen TAC |

Archivos de ejemplo agregados en `examples/`:

- `tac_funciones.cps`: funciones, recursión simple, doble y mutua, procedimientos y funciones anidadas.
- `tac_clases.cps`: clases, atributos con valor inicial, herencia de tres niveles, redefinición y despacho dinámico.
- `tac_try_catch.cps`: `try/catch` simple, anidado, en funciones y con `break`/`continue`.
- `tac_funciones_errores.cps`: inválido; nueve errores de funciones, clases y llamadas.

## 8. Supuestos y limitaciones

- **Sin optimizaciones.** Puede quedar código inalcanzable (por ejemplo, el
  `try_end` que sigue a un `return` dentro de un `try`).
- **Paso de parámetros por valor.** Los arreglos, `string` y objetos son
  referencias, así que pasar uno permite modificar el arreglo u objeto
  original, como en TypeScript.
- **Sin `super`.** La gramática no lo tiene: si una subclase define
  constructor, el de la superclase no se ejecuta (los valores iniciales de
  los atributos heredados sí, mediante `$init`).
- **Funciones como valores.** La gramática sólo permite llamar a funciones
  por su nombre o a métodos de un objeto; no se generan closures como
  valores de primera clase. Las funciones anidadas acceden a las variables
  de su entorno mediante el enlace de acceso.
- **Bloques locales.** Cada variable de un bloque interno recibe su propia
  casilla; no se reutiliza el espacio de bloques hermanos.
- **Clases declaradas fuera del nivel global.** Se tratan igual que el
  resto de la tabla de símbolos del Proyecto 1: las clases se buscan en el
  ámbito global.
