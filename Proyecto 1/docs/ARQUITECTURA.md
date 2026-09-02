# Arquitectura del Proyecto 1

## Objetivo y límites

Esta fase toma el analizador léxico y sintáctico del Laboratorio 1 y agrega una representación estructurada que puedan consumir la tabla de símbolos y el analizador semántico. El programa fuente nunca se ejecuta.

## Flujo del análisis

```text
Archivo o editor .cps
        |
        v
CompiscriptLexer (ANTLR)
        |
        v
CommonTokenStream
        |
        v
CompiscriptParser (ANTLR) ------> diagnósticos léxicos/sintácticos
        |
        v
Parse tree recuperado
        |
        v
AstBuilder
        |
        v
AST independiente de ANTLR
        |
        +----------> AstVisitor ----------> tabla de símbolos / semántica
        |
        +----------> build_visual_tree ---> pestaña "Árbol sintáctico"
```

`CompiscriptAnalyzer.analyze` es el punto de integración. Su resultado contiene los diagnósticos, métricas y un `Program` en `AnalysisResult.ast`.

## Módulos

### `analyzer.py`

- Configura el lexer y el parser generados por ANTLR.
- Instala listeners que traducen y acumulan diagnósticos.
- Mantiene la recuperación estándar de ANTLR.
- Elimina diagnósticos duplicados y los ordena por ubicación.
- Conserva el parse tree y lo entrega a `AstBuilder`.
- Expone la cantidad de nodos mediante `AnalysisResult.ast_node_count`.

### `ast_nodes.py`

Define dataclasses inmutables y con `slots`. Todos los nodos incluyen un `SourceSpan` con ubicación inicial y final. Las familias principales son:

- Estructura: `Program`, `Block`, `TypeRef` y `Parameter`.
- Declaraciones: variables, constantes, funciones y clases.
- Control: `if`, ciclos, `switch`, `try-catch`, `break`, `continue` y `return`.
- Expresiones: literales, listas, identificadores, operadores, asignación, ternario, llamadas, miembros, índices, `new` y `this`.
- Recuperación: `ErrorExpression` representa una porción incompleta sin detener el resto del análisis.

Las siguientes fases deben importar estos nodos, no las clases `*Context` generadas por ANTLR.

### `ast_builder.py`

Implementa un Visitor del parse tree. Reduce las reglas de precedencia de ANTLR a nodos `BinaryExpression`, conserva asociatividad, transforma sufijos encadenados en llamadas/accesos y crea nodos parciales cuando el parser recupera una entrada inválida.

El parse tree contiene detalles de puntuación necesarios para reconocer la gramática. El AST elimina llaves, paréntesis, comas y puntos y conserva solamente la estructura relevante para las siguientes fases.

### `ast_visitor.py`

Proporciona despacho por tipo y recorrido genérico. Un componente puede implementar solamente los nodos que le interesan:

```python
from ast_visitor import AstVisitor


class SymbolCollector(AstVisitor[None]):
    def visit_variable_declaration(self, node):
        # Insertar node.name y node.type_annotation en el alcance actual.
        if node.initializer is not None:
            self.visit(node.initializer)


result.ast.accept(SymbolCollector())
```

La tabla de símbolos y el verificador semántico deben ser Visitors separados para mantener responsabilidades claras.

### `ast_visualization.py`

Convierte el AST en `VisualAstNode`, una estructura independiente de Tkinter con etiquetas en español, detalles, roles y ubicaciones. Esta separación permite probar la visualización sin abrir una ventana.

### `ui.py`

Mantiene el editor y la tabla de diagnósticos del Laboratorio 1. El inspector derecho contiene dos pestañas:

- **Diagnósticos:** errores ordenados y navegación al código.
- **Árbol sintáctico:** jerarquía del AST, resumen, ubicación y controles para expandir o contraer.

Un doble clic o la tecla `Enter` sobre un nodo selecciona su intervalo en el editor.

## Recuperación de errores

El lexer continúa después de un carácter desconocido. El parser utiliza su estrategia de recuperación y construye un parse tree parcial. `AstBuilder` trata los hijos ausentes de forma defensiva y usa `ErrorExpression` cuando no hay una expresión completa.

Si una entrada está demasiado dañada para formar una estructura navegable, `AnalysisResult.ast` puede ser `None`; los diagnósticos ya acumulados siguen mostrándose y el IDE no termina abruptamente.

## Extensión para el trabajo del equipo

1. La tabla de símbolos recibe `AnalysisResult.ast` y lo recorre con un `AstVisitor`.
2. El analizador semántico utiliza otro Visitor y consulta la tabla de símbolos.
3. Los diagnósticos semánticos deben agregarse al modelo de resultados sin modificar los nodos del AST.
4. Los nodos son inmutables; cualquier información inferida debe vivir en la tabla de símbolos o en una estructura lateral indexada por nodo.

## Regeneración y verificación

Para regenerar los analizadores se requiere Java 11 o superior:

```powershell
.\generar_analizadores.ps1
```

Para ejecutar toda la batería:

```powershell
python -m unittest discover -s tests -v
```

Las pruebas deben ejecutarse desde la carpeta `Proyecto 1`.
