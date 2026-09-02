# Proyecto 1 - Análisis semántico de Compiscript

Aplicación de escritorio que integra el lexer y parser de ANTLR del Laboratorio 1 con un árbol sintáctico abstracto (AST) independiente, un Visitor extensible y una representación jerárquica navegable dentro del IDE.

El proyecto realiza análisis léxico y sintáctico y construye el AST. No ejecuta programas, no genera código y todavía no implementa las reglas semánticas ni la tabla de símbolos.

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

Las pruebas cubren la recuperación léxica y sintáctica heredada, construcción del AST, precedencia de operadores, estructuras de Compiscript, Visitor, visualización e integración con entradas válidas e inválidas.

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
│   ├── generated/            # Lexer/parser generados
│   ├── ui.py                 # IDE y vista del AST
│   └── app.py                # Punto de entrada
├── tests/
│   ├── test_analyzer.py
│   └── test_ast.py
└── README.md
```

La arquitectura y el contrato para las siguientes fases están documentados en [`docs/ARQUITECTURA.md`](docs/ARQUITECTURA.md).

