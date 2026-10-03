# Proyecto 2 - Generación de código intermedio de Compiscript

Compilador de Compiscript con IDE de escritorio. Realiza el análisis léxico y
sintáctico (ANTLR, heredado del Laboratorio 1), construye el AST, la tabla de
símbolos y el análisis semántico (Proyecto 1), y para los programas sin
errores genera código de tres direcciones (TAC) junto con las
direcciones de memoria y los registros de activación de cada función.

| Documento | Contenido |
| --- | --- |
| [docs/TAC.md](docs/TAC.md) | Especificación del lenguaje intermedio, traducción de expresiones y reciclaje de temporales |
| [docs/CONTROL_FLUJO.md](docs/CONTROL_FLUJO.md) | Traducción de condiciones, ciclos, `switch`, `break` y `continue` |
| [docs/FUNCIONES_ENTORNOS.md](docs/FUNCIONES_ENTORNOS.md) | Funciones, recursión, registros de activación, tabla de símbolos extendida, clases, herencia, `try/catch` e integración |
| [docs/ARQUITECTURA.md](docs/ARQUITECTURA.md) | Arquitectura de las fases de análisis |

## Ejecución

Requiere Python 3.11 o superior (incluye Tkinter). El runtime de ANTLR ya
viene en `src/vendor`, así que no hace falta instalar dependencias.

En Windows:

```powershell
.\iniciar.ps1
```

También puede iniciarse directamente desde la carpeta `Proyecto 2`:

```powershell
python src\app.py
```

### Uso del IDE

1. Abra un archivo `.cps` (**Abrir**, `Ctrl+O`) o escriba el programa en el editor.
2. Presione **Compilar** (`F5`).
3. Si hay errores, la pestaña **Diagnósticos** los lista todos (léxicos,
   sintácticos y semánticos) ordenados por ubicación y no se genera código
   intermedio. Doble clic en un diagnóstico lleva a su línea.
4. Si no hay errores, se abre **Código intermedio** con el TAC. Un clic en
   una instrucción resalta la línea de código que la originó; **Copiar** y
   **Guardar .tac** exportan el resultado.
5. **AST**, **Símbolos** (con dirección y tamaño de cada símbolo) y
   **Entornos** (registros de activación, área global y distribución de las
   clases con su vtable) muestran las estructuras internas.

Los archivos de `examples/` sirven para probarlo: los `valido_*` y `tac_*`
(sin «errores» en el nombre) compilan; los `errores_*` y
`tac_*_errores` reportan varios errores sin generar TAC.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

| Archivo | Cubre |
| --- | --- |
| `test_analyzer.py`, `test_ast.py` | Recuperación léxica y sintáctica, construcción del AST, Visitor y visualización |
| `test_symbol_table.py` | Ámbitos, shadowing, duplicados, no declarados, recursión, closures, clases |
| `test_semantic_analyzer.py` | Tipos, control de flujo, funciones, clases, listas, código muerto |
| `test_tac.py`, `test_temporaries.py`, `test_tac_expressions.py` | Instrucciones TAC, reciclaje de temporales y expresiones |
| `test_tac_control_flow.py` | Condiciones, cortocircuito, ciclos, `switch`, `break` y `continue` |
| `test_memory_layout.py` | Tabla de símbolos extendida: direcciones, tamaños, entornos y registros de activación |
| `test_tac_functions.py` | Funciones, parámetros, `return`, llamadas y recursión |
| `test_tac_objects.py` | Clases, objetos, herencia y despacho dinámico |
| `test_tac_try_catch.py` | `try/catch` |
| `test_compiler.py` | Integración completa sobre todos los ejemplos válidos e inválidos |

## Estado actual

| Componente | Estado |
| --- | --- |
| Analizador léxico y sintáctico (heredado del Lab. 1) | Completo |
| AST, tabla de símbolos y análisis semántico (Proyecto 1) | Completo |
| TAC de expresiones y reciclaje de temporales | Completo; `docs/TAC.md` |
| TAC de control de flujo y cortocircuito | Completo; `docs/CONTROL_FLUJO.md` |
| TAC de funciones, parámetros, llamadas y recursión | Completo; `docs/FUNCIONES_ENTORNOS.md` |
| TAC de clases, objetos, herencia y `try/catch` | Completo; `docs/FUNCIONES_ENTORNOS.md` |
| Tabla de símbolos con direcciones y registros de activación | Completo; `docs/FUNCIONES_ENTORNOS.md` |
| IDE con TAC, símbolos y entornos | Completo |

## Estructura

```text
Proyecto 2/
├── docs/                     # TAC, control de flujo, funciones/entornos, arquitectura
├── examples/                 # Archivos .cps válidos e inválidos
├── grammar/                  # Gramática ANTLR
├── src/
│   ├── analyzer.py           # Lexer/parser ANTLR y diagnósticos
│   ├── ast_nodes.py          # Modelo del AST
│   ├── ast_builder.py        # Parse tree -> AST
│   ├── ast_visitor.py        # Visitor base
│   ├── ast_visualization.py  # Modelo visual del árbol
│   ├── symbol_table.py       # Tabla de símbolos, ámbitos y entornos de ejecución
│   ├── semantic_analyzer.py  # Sistema de tipos, control de flujo, listas
│   ├── memory_layout.py      # Direcciones y registros de activación
│   ├── tac.py                # Instrucciones y operandos del TAC
│   ├── temporaries.py        # Asignación y reciclaje de temporales
│   ├── tac_generator.py      # Generador de TAC (expresiones)
│   ├── tac_control_flow.py   # Generador de TAC (control de flujo)
│   ├── tac_functions.py      # Generador de TAC (funciones y llamadas)
│   ├── tac_objects.py        # Generador de TAC (clases y objetos)
│   ├── tac_exceptions.py     # Generador de TAC (try/catch)
│   ├── compiler.py           # Pipeline completo usado por el IDE
│   ├── generated/            # Lexer/parser generados
│   ├── vendor/               # Runtime de ANTLR
│   ├── ui.py                 # IDE
│   └── app.py                # Punto de entrada
├── tests/                    # Batería de pruebas (unittest)
└── README.md
```
