# Proyecto 3 - Generación de código ensamblador MIPS para Compiscript

Compilador completo de Compiscript con IDE de escritorio. Realiza el análisis
léxico y sintáctico (ANTLR, Laboratorio 1), el análisis semántico (Proyecto
1) y la generación de código intermedio TAC (Proyecto 2), y **a partir de ese
TAC** genera código ensamblador **MIPS32** que se ejecuta en el simulador
**MARS 4.5**. El código generado pasa por una optimización por mirilla.

| Documento | Contenido |
| --- | --- |
| [NOTAS.md](NOTAS.md) | Convención de llamadas, uso de registros e interfaz entre las tres partes |
| [docs/REGISTROS_ACTIVACION.md](docs/REGISTROS_ACTIVACION.md) | Registros de activación, secuencias de llamada y retorno, recursividad y árboles de activación |
| [docs/MIPS_PERSONA3.md](docs/MIPS_PERSONA3.md) | Control de flujo, clases, herencia, `try/catch`, integración, mirilla de control de flujo, IDE y simulador |
| [docs/TAC.md](docs/TAC.md), [docs/CONTROL_FLUJO.md](docs/CONTROL_FLUJO.md), [docs/FUNCIONES_ENTORNOS.md](docs/FUNCIONES_ENTORNOS.md) | Lenguaje intermedio (Proyecto 2) |
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Arquitectura de todas las fases |

## Requisitos

- Python 3.11 o superior (incluye Tkinter). El runtime de ANTLR ya viene en
  `src/vendor`; no hay que instalar dependencias.
- Java 8 o superior, sólo para **ejecutar** el ensamblador en MARS desde el
  IDE, la línea de comandos o las pruebas. `tools/Mars4_5.jar` ya está
  incluido (también se puede indicar otro con la variable `MARS_JAR`).

## Ejecución

### IDE

```powershell
.\iniciar.ps1           # o: python src\app.py   (desde la carpeta Proyecto 3)
```

1. **Abrir** (`Ctrl+O`) un archivo `.cps` o escribir el programa en el editor.
2. **Compilar** (`F5`).
3. Si hay errores, **Diagnósticos** los lista todos (léxicos, sintácticos,
   semánticos y de generación) y **no se genera TAC ni ensamblador**. Doble
   clic en un diagnóstico lleva a su línea.
4. Si no hay errores:
   - **TAC**: el código intermedio; un clic en una instrucción resalta la
     línea que la originó. **Guardar .tac** y **Copiar**.
   - **MIPS**: el ensamblador generado (cada bloque lleva como comentario la
     instrucción TAC que traduce), cuántas instrucciones quitó la mirilla y
     con qué reglas, **Ver sin optimizar**, **Copiar** y **Guardar .asm**.
   - **Ejecución** (`F6`): ejecuta el programa en MARS y muestra su salida y
     el **árbol de activación** de esa ejecución.
   - **AST**, **Símbolos** y **Entornos** (registros de activación, área
     global y distribución de cada clase con su vtable).

### Línea de comandos

```powershell
python src\compilar.py examples\mips_herencia.cps                  # crea examples\mips_herencia.asm
python src\compilar.py programa.cps -o salida.asm --tac            # también guarda el .tac
python src\compilar.py programa.cps --ejecutar --arbol             # lo ejecuta en MARS y dibuja el árbol
python src\compilar.py programa.cps --sin-optimizar                # sin mirilla
```

### En MARS, a mano

Abrir el `.asm` en MARS 4.5 (*File → Open*), ensamblar (*Run → Assemble*,
`F3`) y ejecutar (*Run → Go*, `F5`). *Settings → Delayed branching* debe
estar desactivado (valor por defecto). La salida aparece en la consola *Run
I/O*. También por consola: `java -jar tools\Mars4_5.jar nc sm programa.asm`.

## Pruebas

```powershell
python -m unittest discover -s tests -v      # o: .\verificar.bat
```

511 pruebas. Las que ejecutan MARS se omiten automáticamente si no hay Java.
Además de comparar la salida, verifican que `$sp` y `$fp` terminen en el
tope de la pila.

| Archivo | Cubre |
| --- | --- |
| `test_analyzer.py`, `test_ast.py`, `test_symbol_table.py`, `test_semantic_analyzer.py` | Análisis léxico, sintáctico y semántico, recuperación de errores |
| `test_tac*.py`, `test_temporaries.py`, `test_memory_layout.py`, `test_compiler.py`, `test_examples_rubrica.py` | Código intermedio y entornos (Proyecto 2) |
| `test_mips_frames.py`, `test_mips_functions.py`, `test_mips_runtime.py`, `test_mips_program.py`, `test_activation_tree.py`, `test_mips_mars.py` | Registros de activación, llamadas, recursividad y árboles de activación (Persona 1) |
| `test_mips_basic.py` | Asignación de registros, variables, expresiones, arreglos y mirilla local (Persona 2) |
| `test_mips_control.py` | Sentencias de control (Persona 3) |
| `test_mips_objects.py` | Clases, objetos y herencia (Persona 3) |
| `test_mips_exceptions.py` | `try/catch` (Persona 3) |
| `test_mips_peephole_control.py` | Mirilla de control de flujo (Persona 3) |
| `test_mips_integration.py` | Pipeline completo, todos los ejemplos en MARS, línea de comandos e IDE (Persona 3) |

## Ejemplos

Cada archivo válido tiene su salida esperada en `examples/salidas/` (la
prueba `test_every_valid_example_runs_in_mars_with_the_expected_output` los
ejecuta todos en MARS). Los ejemplos `NN_*` y `mips_*` traen al final un caso
de error comentado: al quitarle el `//` el programa debe fallar sin generar
código.

| Archivo | Muestra |
| --- | --- |
| `mips_basicos.cps` | Variables, constantes, expresiones aritméticas y lógicas, arreglos |
| `mips_control_flujo.cps` | `if/else` anidados, `while`, `do-while`, `for`, `foreach`, `switch` con fall-through, `break`, `continue`, ternario, cortocircuito |
| `mips_funciones_recursion.cps` | Parámetros (más de cuatro), recursión simple y doble, funciones anidadas; ver su árbol en «Ejecución» |
| `mips_clases_objetos.cps` | Objetos, atributos, constructores, `this`, objetos dentro de objetos, `null` |
| `mips_herencia.cps` | Tres niveles de herencia, atributos heredados, redefinición, despacho dinámico, búsqueda dinámica |
| `mips_try_catch.cps` | Errores atrapados en el bloque, en funciones recursivas, con objetos nulos, en ciclos, `return` en `try`, `try` anidados |
| `mips_error_no_atrapado.cps` | Error sin `try/catch`: mensaje y fin del programa |
| `mips_programa_completo.cps` | Sistema de calificaciones: todo lo anterior junto |
| `01_…cps` a `13_…cps`, `tac_*.cps`, `valido_*.cps` | Ejemplos de los proyectos anteriores (también se ejecutan en MARS) |
| `errores_*.cps`, `tac_*_errores.cps` | Varios errores léxicos, sintácticos o semánticos por archivo: no se genera código |

## Rúbrica y dónde está cada parte

| Criterio | Puntos | Implementación | Pruebas |
| --- | ---: | --- | --- |
| Selección de registros (`getReg`) | 4 | `mips_registers.py` | `test_mips_basic.py` |
| Registros y árboles de activación | 5 | `mips_frames.py`, `mips_functions.py`, `activation_tree.py` | `test_mips_frames.py`, `test_mips_functions.py`, `test_activation_tree.py`, `test_mips_runtime.py` |
| Variables y constantes | 1 | `mips_basic.py` | `test_mips_basic.py`, `mips_basicos.cps` |
| Expresiones aritméticas | 1 | `mips_basic.py` | `test_mips_basic.py`, `mips_basicos.cps` |
| Expresiones lógicas | 1 | `mips_basic.py` + saltos de `mips_control.py` | `test_mips_basic.py`, `test_mips_control.py` |
| Arreglos | 1 | `mips_basic.py` | `test_mips_basic.py`, `mips_basicos.cps` |
| Sentencias de control | 3 | `mips_control.py` | `test_mips_control.py`, `mips_control_flujo.cps` |
| Funciones y parámetros | 2 | `mips_functions.py` | `test_mips_functions.py`, `mips_funciones_recursion.cps` |
| Recursividad | 2 | `mips_functions.py` | `test_mips_runtime.py`, `test_mips_mars.py` |
| Clases y objetos | 2 | `mips_objects.py` | `test_mips_objects.py`, `mips_clases_objetos.cps` |
| Herencia | 2 | `mips_objects.py` | `test_mips_objects.py`, `mips_herencia.cps` |
| `try/catch` | 2 | `mips_exceptions.py`, `mips_runtime.py` | `test_mips_exceptions.py`, `mips_try_catch.cps` |
| Mirilla (≥ 6 transformaciones) | 3 | `mips_peephole.py` (5 reglas) + `mips_peephole_control.py` (8 reglas) | `test_mips_basic.py`, `test_mips_peephole_control.py` |
| Simulador compatible | 1 | MARS 4.5 (`mars_runner.py`, pestaña «Ejecución», `compilar.py --ejecutar`) | `test_mips_integration.py`, `test_mips_mars.py` |

## Reparto del trabajo

| Integrante | Parte |
| --- | --- |
| Persona 1 | Registros de activación, secuencias de llamada y retorno, recursividad, árboles de activación |
| Persona 2 | Asignación de registros (`getReg`), instrucciones básicas, arreglos, cadenas, mirilla local |
| Persona 3 | Control de flujo, clases, herencia, `try/catch`, integración del generador, mirilla de control de flujo, IDE y simulador |

## Estructura

```text
Proyecto 3/
├── docs/                         # Diseño de cada fase
├── examples/                     # Programas .cps válidos e inválidos
│   └── salidas/                  # Salida esperada de cada programa válido en MARS
├── grammar/                      # Gramática ANTLR
├── src/
│   ├── analyzer.py … semantic_analyzer.py   # Análisis (Lab. 1 y Proyecto 1)
│   ├── tac*.py, memory_layout.py, temporaries.py   # Código intermedio (Proyecto 2)
│   ├── mips_frames.py            # Marcos y direcciones (Persona 1)
│   ├── mips_functions.py         # Llamadas, prólogo/epílogo, main (Persona 1)
│   ├── activation_tree.py        # Árbol de activación (Persona 1)
│   ├── mips_registers.py         # getReg y etiquetas de impresión (Persona 2)
│   ├── mips_basic.py             # Aritmética, lógica, arreglos, cadenas, print (Persona 2)
│   ├── mips_peephole.py          # Mirilla local (Persona 2)
│   ├── mips_control.py           # Saltos y etiquetas (Persona 3)
│   ├── mips_objects.py           # Objetos, herencia, vtables (Persona 3)
│   ├── mips_exceptions.py        # try/catch (Persona 3)
│   ├── mips_runtime.py           # Errores en ejecución y rutinas de soporte (Persona 3)
│   ├── mips_peephole_control.py  # Mirilla de control de flujo (Persona 3)
│   ├── mips_generator.py         # Integración TAC -> .asm (Persona 3)
│   ├── compiler.py               # Pipeline completo
│   ├── mars_runner.py            # Ejecución en MARS
│   ├── compilar.py               # Línea de comandos
│   ├── ui.py, ui_mips.py, app.py # IDE
│   ├── generated/, vendor/       # ANTLR
├── tests/                        # Batería de pruebas (unittest)
└── tools/                        # ANTLR y MARS 4.5
```
