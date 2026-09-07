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
        +----------> SymbolTableBuilder ---------> SymbolTable (ámbitos, símbolos, node_scopes)
                                                         |
                                                         v
                                          SemanticAnalyzer (sistema de tipos,
                                          control de flujo, listas, código muerto)
```

`CompiscriptAnalyzer.analyze` es el punto de integración léxico/sintáctico. Su resultado contiene los diagnósticos, métricas y un `Program` en `AnalysisResult.ast`. `symbol_table.build_symbol_table(result.ast)` es el punto de integración para símbolos/ámbitos, y `semantic_analyzer.analyze_semantics(table, result.ast)` es el punto de integración para tipos/flujo, y siempre se llama con la misma tabla y el mismo `Program` que produjo esa tabla (ver advertencia en la sección de `symbol_table.py` sobre `node_scopes`).

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

La tabla de símbolos y el verificador semántico son Visitors separados para mantener responsabilidades claras.

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

**`node_scopes` (nodo → ámbito).** Además de la jerarquía de `Scope`, `SymbolTable` guarda `node_scopes: dict[id(nodo), Scope]`, poblado por `SymbolTableBuilder` mientras recorre el AST. Es la "estructura lateral indexada por nodo" que ya preveía este documento. `SymbolTable.scope_of(node)` la consulta. Esto le permite a `semantic_analyzer.py` (otro Visitor completamente independiente) saber en qué ámbito vive cualquier nodo del AST y resolver identificadores (`scope.resolve(nombre)`) sin reconstruir el recorrido de ámbitos ni repetir las validaciones de declaración que ya hizo `SymbolTableBuilder`.

*Advertencia de uso*: `node_scopes` usa `id(nodo)` como llave, así que sólo es válida junto con el mismo objeto `Program` a partir del cual se construyó esa `SymbolTable` (y mientras ese `Program` siga vivo en memoria — nunca se debe dejar salir de alcance entre `build_symbol_table` y `analyze_semantics`). No reutilizar una `SymbolTable` contra un AST distinto (por ejemplo, de un segundo análisis).

La cobertura de `node_scopes` no depende sólo del override de `visit()`: varios métodos de `SymbolTableBuilder` se llaman de forma directa (no vía `self.visit()`) por razones de diseño — `visit_parameter`, `_declare_function_signature`, `_declare_class_signature`, el inicializador de un `for`, y el identificador objetivo de una asignación. Cada uno de esos métodos registra su propio ámbito explícitamente (buscar `_record_scope` en el archivo) para no depender de cómo se llegó a ellos.

Punto de integración:

```python
from symbol_table import build_symbol_table

table, scope_diagnostics = build_symbol_table(result.ast)
```

### `semantic_analyzer.py`

Tercer Visitor sobre el mismo AST (`SemanticAnalyzer(AstVisitor[Type])`), independiente de `symbol_table.py` en el sentido de que no repite sus validaciones — las reutiliza vía `SymbolTable.scope_of(node)` y `SymbolTable.class_members(...)`.

Modelo de tipos. `Type` es un dataclass inmutable (`TypeKind` + `element_type` para arreglos + `class_name` para instancias de clase). Constantes: `INTEGER`, `STRING`, `BOOLEAN`, `NULL`, `VOID`, `FUNCTION`, `ERROR`, `UNKNOWN`. `ERROR` se propaga silenciosamente por los operadores/llamadas para no duplicar un diagnóstico ya emitido más abajo en el árbol; `UNKNOWN` se propaga igual pero representa "no se pudo inferir" (p. ej. un parámetro sin anotación) en vez de "ya hubo un error".

Inferencia de tipo de variables sin anotación. `symbol_table.py` sólo guarda el tipo declarado (texto) o `None`. `SemanticAnalyzer` mantiene su propio `dict[id(symbol), Type]` (`_symbol_types`) donde cachea, al visitar cada `VariableDeclaration`/`ConstantDeclaration`/`Parameter`/variable de `foreach`, el tipo declarado o, si falta la anotación, el tipo inferido del inicializador. Usos posteriores de ese símbolo (`visit_identifier_expression`) consultan ese caché antes de caer al tipo declarado en el `Symbol`.

Responsabilidades:
- Sistema de tipos: aritmética (`+ - * /  %`), lógica (`&& || !`), comparaciones (`== != < <= > >=`), compatibilidad en asignaciones, inicialización de constantes (ya la exige la gramática), tipos de elementos de listas.
- Control de flujo: condición booleana en `if`/`while`/`do-while`/`for` (ver desviación sobre `switch` más abajo).
- Funciones: cantidad y tipo de argumentos (posicional) contra `Symbol.parameters`, tipo de retorno contra `Symbol.return_type`/lo declarado en el `FunctionDeclaration` que se está visitando, recursión (se resuelve gratis: una llamada recursiva es sólo una llamada a un símbolo que ya tiene su firma completa gracias al hoisting de `symbol_table.py`).
- Clases y objetos: existencia de atributos/métodos accedidos con `.` (vía `SymbolTable.class_members`, que ya incluye herencia), validación de argumentos del constructor en `new`, tipo de `this` dentro de un método.
- Listas: tipo de los elementos de un literal de lista, tipo del índice (`integer`), que sólo se pueda indexar algo de tipo lista.
- Generales: código muerto (instrucción después de un `return`/`break`/`continue` incondicional dentro del mismo bloque — un solo diagnóstico por tramo muerto, sin visitar lo que sigue), expresiones sin sentido semántico (p. ej. usar una función como operando aritmético, que cae naturalmente en la validación de tipos de operadores).
- Manejo de errores: un único recorrido descendente sobre un árbol finito (no hay riesgo de ciclos infinitos); cada nodo se tipa incluso tras un error (como `ERROR`/`UNKNOWN`) para que el resto del análisis continúe y no se repitan diagnósticos derivados de uno anterior.

Desviaciones deliberadas (documentadas también como docstring del módulo): no existe el tipo `float` porque la gramática no lo define (sólo aplica a `+` la variante de concatenación de `string`, que el propio lenguaje usa); `switch` no exige condición booleana (se valida que cada `case` sea comparable con el tipo de la expresión); el código muerto se detecta a nivel de instrucción-siguiente-en-el-mismo-bloque, no con un análisis de alcanzabilidad completo con ramas.

Punto de integración:

```python
from symbol_table import build_symbol_table
from semantic_analyzer import analyze_semantics

table, scope_diagnostics = build_symbol_table(result.ast)
type_diagnostics = analyze_semantics(table, result.ast)  # mismo result.ast
```

### `ui.py`

Mantiene el editor y la tabla de diagnósticos del Laboratorio 1. El inspector derecho tiene tres pestañas:

- **Diagnósticos:** léxicos, sintácticos y semánticos combinados y ordenados por ubicación, con color distinto por tipo.
- **Árbol sintáctico:** jerarquía del AST, resumen, ubicación y controles para expandir o contraer.
- **Tabla de símbolos:** jerarquía real de `Scope` (global → función/bloque/clase → símbolos), con salto a la declaración en el editor.

Un doble clic o la tecla `Enter` sobre un nodo o símbolo selecciona su intervalo en el editor. `analyze()` llama en secuencia a `CompiscriptAnalyzer.analyze`, `build_symbol_table` y `analyze_semantics`, y combina las tres listas de diagnósticos.

## Recuperación de errores

El lexer continúa después de un carácter desconocido. El parser utiliza su estrategia de recuperación y construye un parse tree parcial. `AstBuilder` trata los hijos ausentes de forma defensiva y usa `ErrorExpression` cuando no hay una expresión completa.

Si una entrada está demasiado dañada para formar una estructura navegable, `AnalysisResult.ast` puede ser `None`; los diagnósticos ya acumulados siguen mostrándose y el IDE no termina abruptamente. `SymbolTableBuilder` no se ejecuta en ese caso (no hay `Program` que recorrer); si `AnalysisResult.ast` no es `None` pero contiene nodos `ErrorExpression` parciales, el recorrido continúa con normalidad porque esos nodos no tienen hijos que visitar.

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
