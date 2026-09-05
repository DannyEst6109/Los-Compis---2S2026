# Proyecto 1 - Análisis semántico de Compiscript

Aplicación de escritorio que integra el lexer y parser de ANTLR del Laboratorio 1 con un árbol sintáctico abstracto (AST) independiente, un Visitor extensible y una representación jerárquica navegable dentro del IDE.

El proyecto realiza análisis léxico y sintáctico y construye el AST y  y a partir de él arma la tabla de símbolos con sus ámbitos (global, bloque, función, clase). Todavía no ejecuta programas ni genera código, y el analizador semántico (sistema de tipos, control de flujo, listas, reglas generales) está en desarrollo.

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

Las pruebas cubren la recuperación léxica y sintáctica heredada, construcción del AST, precedencia de operadores, estructuras de Compiscript, Visitor, visualización, casos de recuperación de errores (incluyendo la aparición explícita de `ErrorExpression` navegable), e integración con entradas válidas e inválidas. `tests/test_symbol_table.py` cubre además la tabla de símbolos: ámbitos anidados y shadowing, declaraciones duplicadas, variables no declaradas, parámetros duplicados, funciones recursivas y con recursión mutua, closures, y registro de clases (atributos, métodos, constructor).

## Estado actual
| Componente | Estado |
| --- | --- |
| Analizador léxico y sintáctico (heredado del Lab. 1) | ✅ Completo |
| AST independiente de ANTLR + recuperación de errores | ✅ Completo |
| Árbol sintáctico con representación visual en el IDE | ✅ Completo |
| Tabla de símbolos, ámbitos, declaraciones, funciones y clases | ✅ Lógica completa y probada (`src/symbol_table.py`, `tests/test_symbol_table.py`) — pendiente conectarla al IDE como una pestaña visible |
| Analizador semántico: sistema de tipos, control de flujo, listas, reglas generales | 🔲 En desarrollo |
| Batería de tests globales de reglas semánticas | 🔲 En desarrollo |
 

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
│   ├── symbol_table.py
│   ├── generated/            # Lexer/parser generados
│   ├── ui.py                 # IDE y vista del AST
│   └── app.py                # Punto de entrada
├── tests/
│   ├── test_analyzer.py
│   └── test_ast.py
│   └── test_symbol_table.py
└── README.md
```

La arquitectura y el contrato para las siguientes fases están documentados en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

