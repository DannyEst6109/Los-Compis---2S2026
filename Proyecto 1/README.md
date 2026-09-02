# Proyecto 1 - Análisis semántico de Compiscript

Esta carpeta contendrá la evolución del analizador del Laboratorio 1 para incorporar un AST, su representación visual, una tabla de símbolos y el análisis semántico, sin ejecutar los programas ni generar código.

## Flujo previsto

```text
Archivo .cps
    ↓
Lexer de ANTLR
    ↓
Parser de ANTLR
    ↓
Parse tree
    ↓
Construcción del AST
    ↓
Visitor del AST
    ↓
Tabla de símbolos y análisis semántico
    ↓
Resultados dentro de la interfaz gráfica
```

## Responsabilidad: AST, visualización e integración

- Integrar el lexer, parser y recuperación de errores del Laboratorio 1.
- Definir los nodos del AST para todas las construcciones de Compiscript.
- Transformar el parse tree de ANTLR en el AST.
- Proporcionar una infraestructura de Visitor independiente de las reglas semánticas.
- Mostrar el árbol dentro de la interfaz gráfica.
- Crear pruebas del AST, su visualización y la integración con entradas válidas e inválidas.
- Mantener la documentación de arquitectura y ejecución.

La implementación de las reglas semánticas y de la tabla de símbolos pertenece a los otros componentes del equipo. El AST y su Visitor deben exponer una API estable para que esos componentes no dependan directamente de las clases generadas por ANTLR.

## Estructura propuesta

```text
Proyecto 1/
├── docs/                   # Arquitectura, AST y guía de ejecución
├── examples/               # Entradas .cps de demostración
├── grammar/                # Gramática de Compiscript
├── src/
│   ├── ast/                # Nodos, constructor y Visitor del AST
│   ├── generated/          # Lexer/parser generados por ANTLR
│   ├── semantic/           # Tabla de símbolos y reglas semánticas
│   ├── ui/                 # IDE y visualización del árbol
│   └── analysis_pipeline.py
├── tests/
│   ├── ast/
│   ├── integration/
│   └── semantic/
└── README.md
```

Esta estructura es una propuesta inicial. Se creará gradualmente al integrar el código del laboratorio, evitando duplicar archivos generados o dependencias innecesarias hasta definir la estrategia final del equipo.
