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
        +----------> build_visual_tree ---------> pestaña "Árbol sintáctico"
        |
        +----------> SymbolTableBuilder ---------> SymbolTable (ámbitos, símbolos)
        |                                                |
        |                                                v
        +----------> AstVisitor (semántico) ----> usa SymbolTable, agrega diagnósticos
```

`CompiscriptAnalyzer.analyze` es el punto de integración. Su resultado contiene los diagnósticos, métricas y un `Program` en `AnalysisResult.ast`. `symbol_table.build_symbol_table(result.ast)` es el punto de integración equivalente para la fase de símbolos/ámbitos.
 

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

> Nota sobre `forInitializer`: la gramática nunca le asigna el `SEMI` a esta subregla (`forStatement: FOR LPAREN forInitializer? SEMI ...`); el `SEMI` lo consume `forStatement`. `visitForInitializer` no lo toca, así que no hay doble consumo ni un `SEMI` perdido.

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

### `symbol_table.py`
 
Segundo Visitor sobre el mismo AST (`SymbolTableBuilder(AstVisitor[None])`), independiente de ANTLR y de `analyzer.py`: solo depende de `ast_nodes` y `ast_visitor`, igual que `ast_visualization.py`.
 
**Modelo:**
 
- `Scope`: ámbito léxico (`ScopeKind.GLOBAL | BLOCK | FUNCTION | CLASS`), con `parent`/`children` y un diccionario propio de símbolos. `resolve(name)` busca en el ámbito actual y sube por `parent` hasta encontrar el símbolo más cercano (shadowing: el ámbito más interno gana). `declare(symbol)` sólo compara contra el propio ámbito, por lo que declarar el mismo nombre en un ámbito anidado es válido.
- `Symbol`: nombre, categoría (`variable`, `constante`, `parámetro`, `función`, `clase`), tipo, ámbito, si está inicializado, y — según la categoría — parámetros/tipo de retorno/nombres capturados (funciones) o superclase/atributos/métodos/constructor (clases).
- `SymbolTable`: envoltorio con las operaciones que pide la rúbrica de forma explícita: `insert`, `lookup`, `update` (además de `find_class`, `class_members` con herencia, y `render()` para una vista tabular).
- `Diagnostic`: mismo formato (`kind`, `line`, `column`, `symbol`, `description`) que `analyzer.Diagnostic`, para poder combinarse y ordenarse junto a los diagnósticos léxicos/sintácticos en el IDE sin que este módulo dependa del lexer/parser.
**Decisiones de diseño relevantes:**
 
- **Hoisting parcial por bloque.** Antes de procesar las instrucciones de un `Program`, `Block` o cuerpo de función, se registran primero las *firmas* de las funciones y clases declaradas directamente ahí (nombre, parámetros, tipo de retorno / superclase), y luego se procesan los cuerpos en el orden original. Esto permite recursión mutua entre funciones (o métodos) y referencias hacia adelante dentro del mismo ámbito, sin necesitar un pase de resolución de nombres separado.
- **Captura de closures.** Al resolver un identificador, si el símbolo vive en un ámbito de función ancestro distinto del ámbito de función actual, se agrega su nombre a `captured_names` de la función que lo usa. Es una aproximación práctica (no un análisis de flujo completo) suficiente para el alcance del curso.
- **Clases.** Los miembros se dividen en métodos (incluyendo `constructor`, si existe) y atributos; ambos quedan indexados en el `Symbol` de la clase (`methods`, `attributes`, `constructor`) además de vivir en el ámbito de la clase. `class_members()` combina lo propio con lo heredado siguiendo `superclass` hasta la raíz.
- **Validaciones que sí caen aquí** (por depender directamente de ámbitos/símbolos, no de tipos): identificador duplicado en el mismo ámbito, variable no declarada, parámetro duplicado, reasignación de una constante, `break`/`continue` fuera de un bucle, `return` fuera de una función, `this` fuera de una clase, `new` de una clase no declarada, herencia de una clase no declarada.
- **Validaciones que NO caen aquí** (le corresponden al analizador semántico, que puede apoyarse en la `SymbolTable` ya construida): compatibilidad de tipos, existencia de un atributo/método accedido con `.`, conteo y tipo de argumentos en llamadas y constructores, tipo del valor de `return` contra el tipo declarado, condiciones `boolean` en `if`/`while`/`for`/`switch`, código muerto.
Punto de integración:
 
```python
from symbol_table import build_symbol_table
 
table, semantic_diagnostics = build_symbol_table(result.ast)
```
 

### `ui.py`

Mantiene el editor y la tabla de diagnósticos del Laboratorio 1. El inspector derecho contiene dos pestañas:

- **Diagnósticos:** errores ordenados y navegación al código.
- **Árbol sintáctico:** jerarquía del AST, resumen, ubicación y controles para expandir o contraer.

Un doble clic o la tecla `Enter` sobre un nodo selecciona su intervalo en el editor.

## Recuperación de errores

El lexer continúa después de un carácter desconocido. El parser utiliza su estrategia de recuperación y construye un parse tree parcial. `AstBuilder` trata los hijos ausentes de forma defensiva y usa `ErrorExpression` cuando no hay una expresión completa.

Si una entrada está demasiado dañada para formar una estructura navegable, `AnalysisResult.ast` puede ser `None`; los diagnósticos ya acumulados siguen mostrándose y el IDE no termina abruptamente. `SymbolTableBuilder` no se ejecuta en ese caso (no hay `Program` que recorrer); si `AnalysisResult.ast` no es `None` pero contiene nodos `ErrorExpression` parciales, el recorrido continúa con normalidad porque esos nodos no tienen hijos que visitar.
 

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
