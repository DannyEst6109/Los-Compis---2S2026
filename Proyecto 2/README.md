# Proyecto 2 - Generación de código intermedio de Compiscript

La generación de TAC incluye expresiones y control de flujo. El contrato del
lenguaje intermedio está en [docs/TAC.md](docs/TAC.md); la implementación de
Persona 2 y sus decisiones están en [docs/CONTROL_FLUJO.md](docs/CONTROL_FLUJO.md).
La integración de TAC en el IDE, funciones, registros de activación, objetos y
`try/catch` sigue pendiente. El IDE heredado muestra los análisis, AST y símbolos.

Aplicación de escritorio que integra el lexer y parser de ANTLR del Laboratorio 1 con un árbol sintáctico abstracto (AST) independiente, un Visitor extensible, una representación jerárquica navegable dentro del IDE y una tabla de símbolos con manejo de ámbitos.

El proyecto realiza análisis léxico y sintáctico, construye el AST, arma la tabla de símbolos con sus ámbitos (global, bloque, función, clase) y ejecuta el análisis semántico (sistema de tipos, control de flujo, funciones/clases, listas, código muerto). 

## Ejecución

En Windows:

```powershell
.\iniciar.ps1
```

También puede iniciarse directamente:

```powershell
python src\app.py
```

La interfaz permite abrir o editar un archivo `.cps`, analizarlo con `F5`, consultar diagnósticos y explorar el AST. Un doble clic en un diagnóstico o nodo del árbol lleva el cursor a su ubicación en el código.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```


Las pruebas cubren la recuperación léxica y sintáctica heredada, construcción del AST, precedencia de operadores, estructuras de Compiscript, Visitor, visualización, casos de recuperación de errores (incluyendo la aparición explícita de `ErrorExpression` navegable), e integración con entradas válidas e inválidas. `tests/test_symbol_table.py` cubre además la tabla de símbolos: ámbitos anidados y shadowing, declaraciones duplicadas, variables no declaradas, parámetros duplicados, funciones recursivas y con recursión mutua, closures, y registro de clases (atributos, métodos, constructor). `tests/test_semantic_analyzer.py` cubre el analizador semántico - aritmética, lógica, comparaciones, asignaciones, listas, condiciones de control de flujo, argumentos/tipo de retorno de funciones (incluida recursión), atributos/métodos/constructor de clases, código muerto, y que los errores no se dupliquen en cascada.

## Estado actual

| Componente | Estado |
| --- | --- |
| Analizador léxico y sintáctico (heredado del Lab. 1) | Completo |
| AST independiente de ANTLR + recuperación de errores | Completo |
| Árbol sintáctico con representación visual en el IDE | Completo |
| Tabla de símbolos, ámbitos, declaraciones, funciones y clases | Completo, con pestaña propia en el IDE (`src/symbol_table.py`, `tests/test_symbol_table.py`) |
| Analizador semántico: sistema de tipos, control de flujo, listas, reglas generales | Lógica completa y probada (`src/semantic_analyzer.py`, `tests/test_semantic_analyzer.py`) |
| Batería de tests globales de reglas semánticas | `tests/test_semantic_analyzer.py` (46 casos) |
| IDE: documentación de arquitectura y de ejecución | Este README y `docs/ARQUITECTURA.md` |
| TAC de expresiones y reciclaje de temporales | Implementado y probado; contrato en `docs/TAC.md` |
| TAC de control de flujo y expresiones con cortocircuito | Implementado y probado; decisiones en `docs/CONTROL_FLUJO.md` |
| Visualización de TAC, funciones, entornos y objetos | Pendiente de integración de Persona 3 |

## Estructura

```text
Proyecto 1/
├── docs/
│   └── ARQUITECTURA.md
├── examples/                 # Archivos .cps de prueba
├── grammar/                  # Gramática ANTLR
├── src/
│   ├── analyzer.py           # Pipeline y diagnósticos
│   ├── ast_nodes.py          # Modelo del AST
│   ├── ast_builder.py        # Parse tree -> AST
│   ├── ast_visitor.py        # Visitor base
│   ├── ast_visualization.py  # Modelo visual del árbol
│   ├── symbol_table.py       # Tabla de símbolos y ámbitos (incluye node_scopes)
│   ├── semantic_analyzer.py  # sistema de tipos, control de flujo, listas
│   ├── generated/            # Lexer/parser generados
│   ├── ui.py                 # IDE, AST y tabla de símbolos
│   └── app.py                # Punto de entrada
├── tests/
│   ├── test_analyzer.py
│   ├── test_ast.py
│   ├── test_symbol_table.py
│   └── test_semantic_analyzer.py  # pruebas del analizador semántico
└── README.md
```

La arquitectura y el contrato para las siguientes fases están documentados en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).
