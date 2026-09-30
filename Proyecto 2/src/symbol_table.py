"""Tabla de símbolos y manejo de ámbitos para Compiscript.

Este módulo recorre el AST producido por ``ast_builder`` (el mismo que
consume ``ast_visualization``) y construye:

* Una jerarquía de ámbitos (global, bloque, función, clase).
* Una tabla de símbolos por ámbito con la información de cada
  identificador declarado: nombre, tipo, categoría, ámbito, parámetros,
  tipo de retorno e inicialización.
* Diagnósticos semánticos relacionados con declaraciones y ámbitos:
  identificadores duplicados, variables no declaradas, parámetros
  duplicados, reasignación de constantes, uso indebido de ``break``,
  ``continue``, ``return`` y ``this``.

Este componente es intencionalmente independiente de ANTLR y del
analizador léxico/sintáctico (``analyzer.py``): sólo depende de
``ast_nodes`` y ``ast_visitor``, igual que ``ast_visualization``. El
analizador semántico (reglas de tipos, existencia de atributos/métodos,
validación de argumentos, etc.) es un Visitor separado que puede
apoyarse en la ``SymbolTable`` construida aquí mediante
``SymbolTable.lookup`` / ``SymbolTable.find_class`` /
``SymbolTable.class_members``.

Uso típico::

    from analyzer import CompiscriptAnalyzer
    from symbol_table import build_symbol_table

    result = CompiscriptAnalyzer().analyze(source)
    table, semantic_diagnostics = build_symbol_table(result.ast)
    print(table.render())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional

import ast_nodes as ast
from ast_visitor import AstVisitor


# ---------------------------------------------------------------------------
# Diagnósticos
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Diagnostic:
    """Mismo formato que ``analyzer.Diagnostic`` (kind/line/column/symbol/
    description) para que ambas listas puedan combinarse y ordenarse juntas
    en la interfaz, sin que este módulo dependa del lexer/parser."""

    kind: str
    line: int
    column: int
    symbol: str
    description: str


# ---------------------------------------------------------------------------
# Modelo de símbolos y ámbitos
# ---------------------------------------------------------------------------


class ScopeKind(Enum):
    GLOBAL = "global"
    BLOCK = "bloque"
    FUNCTION = "función"
    CLASS = "clase"


class SymbolCategory(Enum):
    VARIABLE = "variable"
    CONSTANT = "constante"
    PARAMETER = "parámetro"
    FUNCTION = "función"
    CLASS = "clase"


_CATEGORY_LABEL = {
    SymbolCategory.VARIABLE: "variable",
    SymbolCategory.CONSTANT: "constante",
    SymbolCategory.PARAMETER: "parámetro",
    SymbolCategory.FUNCTION: "función",
    SymbolCategory.CLASS: "clase",
}


@dataclass(frozen=True, slots=True)
class ParameterInfo:
    name: str
    type_name: str | None


@dataclass(slots=True)
class Symbol:
    """Entrada de la tabla de símbolos.

    Los campos ``parameters``/``return_type``/``captured_names`` sólo
    aplican a funciones y métodos; ``superclass``/``attributes``/
    ``methods``/``constructor`` sólo aplican a clases.
    """

    name: str
    category: SymbolCategory
    type_name: str | None = None
    scope_name: str = "global"
    initialized: bool = False
    line: int = 0
    column: int = 0

    # Funciones / métodos.
    parameters: tuple[ParameterInfo, ...] = ()
    return_type: str | None = None
    captured_names: set[str] = field(default_factory=set)

    # Clases.
    superclass: str | None = None
    attributes: dict[str, "Symbol"] = field(default_factory=dict)
    methods: dict[str, "Symbol"] = field(default_factory=dict)
    constructor: Optional["Symbol"] = None


class DuplicateSymbolError(Exception):
    """Se lanza cuando ya existe un identificador con el mismo nombre en
    el mismo ámbito (no aplica entre ámbitos anidados: ahí sí hay
    shadowing)."""

    def __init__(self, existing: Symbol):
        self.existing = existing
        super().__init__(f"'{existing.name}' ya existe en este ámbito")


class Scope:
    """Un ámbito léxico: global, de bloque, de función o de clase."""

    def __init__(self, kind: ScopeKind, name: str, parent: "Scope | None" = None):
        self.kind = kind
        self.name = name
        self.parent = parent
        self.children: list[Scope] = []
        self.symbols: dict[str, Symbol] = {}
        if parent is not None:
            parent.children.append(self)

    # -- insertar ------------------------------------------------------
    def declare(self, symbol: Symbol) -> None:
        if symbol.name in self.symbols:
            raise DuplicateSymbolError(self.symbols[symbol.name])
        symbol.scope_name = self.name
        self.symbols[symbol.name] = symbol

    # -- recuperar información ------------------------------------------
    def resolve_local(self, name: str) -> Symbol | None:
        return self.symbols.get(name)

    def resolve(self, name: str) -> tuple[Symbol, "Scope"] | None:
        """Busca ``name`` en este ámbito y, si no está, en los ámbitos
        superiores. El más cercano gana (shadowing)."""
        scope: Scope | None = self
        while scope is not None:
            symbol = scope.symbols.get(name)
            if symbol is not None:
                return symbol, scope
            scope = scope.parent
        return None

    # -- manejo de alcances ----------------------------------------------
    def enclosing_function(self) -> "Scope | None":
        scope = self
        while scope is not None:
            if scope.kind == ScopeKind.FUNCTION:
                return scope
            scope = scope.parent
        return None

    def enclosing_class(self) -> "Scope | None":
        scope = self
        while scope is not None:
            if scope.kind == ScopeKind.CLASS:
                return scope
            scope = scope.parent
        return None

    def all_symbols(self) -> Iterable[Symbol]:
        yield from self.symbols.values()
        for child in self.children:
            yield from child.all_symbols()


class SymbolTable:
    """Envoltorio de la jerarquía de ámbitos con las operaciones que pide
    la rúbrica: insertar, recuperar información, actualizar información y
    manejo de alcances (este último vía la clase ``Scope``)."""

    def __init__(self) -> None:
        self.global_scope = Scope(ScopeKind.GLOBAL, "global")
        # mapa nodo -> ámbito, para que el analizador
        # semántico (otro Visitor independiente) sepa en qué ámbito vive
        # cada nodo sin tener que reconstruir el recorrido de scopes. Solo
        # es válido junto con el mismo Program a partir del cual se
        # construyó esta tabla (ver build_symbol_table); no reutilizar esta
        # tabla contra un AST distinto.
        self.node_scopes: dict[int, "Scope"] = {}

    def insert(self, scope: Scope, symbol: Symbol) -> bool:
        """Inserta un símbolo en ``scope``. Devuelve ``False`` (sin lanzar
        excepción) si el nombre ya existía en ese mismo ámbito."""
        try:
            scope.declare(symbol)
            return True
        except DuplicateSymbolError:
            return False

    def lookup(self, name: str, scope: Scope) -> Symbol | None:
        """Recupera información de un símbolo buscando desde ``scope``
        hacia los ámbitos superiores."""
        found = scope.resolve(name)
        return found[0] if found else None

    def update(self, scope: Scope, name: str, **changes: object) -> bool:
        """Actualiza campos de un símbolo ya existente (tipo,
        inicialización, tipo de retorno, etc.). Busca igual que
        ``lookup``. Devuelve ``False`` si el símbolo no existe."""
        found = scope.resolve(name)
        if found is None:
            return False
        symbol, _owner_scope = found
        for field_name, value in changes.items():
            if hasattr(symbol, field_name):
                setattr(symbol, field_name, value)
        return True

    # consulta de la "estructura lateral indexada por
    # nodo" mencionada en ARQUITECTURA.md, usada por el analizador
    # semántico para resolver identificadores en el punto exacto del AST
    # donde aparecen.
    def scope_of(self, node: ast.AstNode) -> "Scope | None":
        return self.node_scopes.get(id(node))

    def all_symbols(self) -> list[Symbol]:
        return list(self.global_scope.all_symbols())

    def find_class(self, name: str) -> Symbol | None:
        symbol = self.global_scope.resolve_local(name)
        if symbol is not None and symbol.category == SymbolCategory.CLASS:
            return symbol
        return None

    def class_members(self, class_symbol: Symbol) -> dict[str, Symbol]:
        """Combina atributos y métodos propios con los heredados,
        recorriendo la cadena de superclases."""
        chain: list[Symbol] = []
        current: Symbol | None = class_symbol
        seen: set[str] = set()
        while current is not None and current.name not in seen:
            seen.add(current.name)
            chain.append(current)
            current = self.find_class(current.superclass) if current.superclass else None

        members: dict[str, Symbol] = {}
        for symbol in reversed(chain):
            members.update(symbol.attributes)
            members.update(symbol.methods)
        return members

    def render(self) -> str:
        """Representación tabular simple (para depuración o para una
        pestaña de "Tabla de símbolos" en el IDE)."""
        rows = [("Nombre", "Tipo", "Categoría", "Ámbito", "Inicializada")]
        for symbol in self.all_symbols():
            rows.append(
                (
                    symbol.name,
                    symbol.type_name or "-",
                    symbol.category.value,
                    symbol.scope_name,
                    "sí" if symbol.initialized else "no",
                )
            )
        widths = [max(len(row[i]) for row in rows) for i in range(len(rows[0]))]

        def fmt(row: tuple[str, ...]) -> str:
            return " | ".join(value.ljust(widths[i]) for i, value in enumerate(row))

        separator = "-+-".join("-" * width for width in widths)
        return "\n".join([fmt(rows[0]), separator, *(fmt(row) for row in rows[1:])])


def _type_name(type_ref: ast.TypeRef | None) -> str | None:
    return str(type_ref) if type_ref is not None else None


# ---------------------------------------------------------------------------
# Visitor que construye la tabla
# ---------------------------------------------------------------------------


class SymbolTableBuilder(AstVisitor[None]):
    """Recorre el AST y construye la ``SymbolTable`` junto con los
    diagnósticos semánticos relacionados con ámbitos y declaraciones."""

    def __init__(self) -> None:
        self.table = SymbolTable()
        self.diagnostics: list[Diagnostic] = []
        self._scope_stack: list[Scope] = [self.table.global_scope]
        self._loop_depth = 0
        self._function_depth = 0

    def build(self, program: ast.Program) -> SymbolTable:
        self.visit(program)
        return self.table

    # registra, para cada nodo que pasa por el
    # despacho genérico, cuál era el ámbito activo en ese momento. Cubre la
    # gran mayoría del árbol (todo lo que se visita via self.visit(...),
    # incluida la recursión automática de AstVisitor.generic_visit hacia
    # los hijos). Los pocos sitios que llaman a un visit_xxx directamente
    # (parámetros, firmas de función/clase, el inicializador de un for)
    # registran su propio ámbito de forma explícita más abajo.
    def visit(self, node: ast.AstNode) -> None:
        self._record_scope(node)
        return super().visit(node)

    def _record_scope(self, node: ast.AstNode) -> None:
        self.table.node_scopes[id(node)] = self._current

    # -- utilidades internas ----------------------------------------------
    @property
    def _current(self) -> Scope:
        return self._scope_stack[-1]

    def _push(self, kind: ScopeKind, name: str) -> Scope:
        scope = Scope(kind, name, parent=self._current)
        self._scope_stack.append(scope)
        return scope

    def _pop(self) -> None:
        self._scope_stack.pop()

    def _error(self, node: ast.AstNode, symbol_text: str, description: str) -> None:
        self.diagnostics.append(
            Diagnostic(
                kind="Semántico",
                line=node.span.line,
                column=node.span.column,
                symbol=symbol_text,
                description=description,
            )
        )

    def _declare(self, symbol: Symbol, node: ast.AstNode) -> bool:
        if self.table.insert(self._current, symbol):
            return True
        existing = self._current.resolve_local(symbol.name)
        label = _CATEGORY_LABEL.get(symbol.category, "identificador")
        line = existing.line if existing is not None else "?"
        self._error(
            node,
            symbol.name,
            f"El identificador «{symbol.name}» ({label}) ya fue declarado "
            f"en este ámbito (línea {line}).",
        )
        return False

    def _resolve_identifier(self, name: str, node: ast.AstNode) -> Symbol | None:
        found = self._current.resolve(name)
        if found is None:
            self._error(node, name, f"La variable «{name}» no ha sido declarada.")
            return None
        symbol, owner_scope = found
        self._record_capture(owner_scope, name)
        return symbol

    def _record_capture(self, owner_scope: Scope, name: str) -> None:
        """Si ``name`` vive en una función ancestro distinta de la función
        actual, se marca como variable capturada (closure)."""
        current_function = self._current.enclosing_function()
        if current_function is None or owner_scope is current_function:
            return
        if owner_scope.kind is ScopeKind.FUNCTION:
            owner_of_current = current_function.parent
            if owner_of_current is not None:
                function_symbol = owner_of_current.resolve_local(current_function.name)
                if function_symbol is not None:
                    function_symbol.captured_names.add(name)

    # -- punto de entrada del programa -------------------------------------
    def visit_program(self, node: ast.Program) -> None:
        self._process_statements(node.statements)

    def _process_statements(self, statements: tuple[ast.Statement, ...]) -> None:
        """Dos pasadas: primero se registran las firmas de funciones y
        clases declaradas directamente en este bloque (hoisting parcial),
        lo que permite recursión mutua y referencias hacia adelante dentro
        del mismo ámbito. Luego se procesa todo en el orden original."""
        pending_functions: list[ast.FunctionDeclaration] = []
        pending_classes: list[ast.ClassDeclaration] = []
        for statement in statements:
            if isinstance(statement, ast.FunctionDeclaration):
                self._declare_function_signature(statement)
                pending_functions.append(statement)
            elif isinstance(statement, ast.ClassDeclaration):
                self._declare_class_signature(statement)
                pending_classes.append(statement)

        function_iter = iter(pending_functions)
        class_iter = iter(pending_classes)
        for statement in statements:
            if isinstance(statement, ast.FunctionDeclaration):
                self._process_function_body(next(function_iter))
            elif isinstance(statement, ast.ClassDeclaration):
                self._process_class_body(next(class_iter))
            else:
                self.visit(statement)

    # -- declaraciones simples ----------------------------------------------
    def visit_variable_declaration(self, node: ast.VariableDeclaration) -> None:
        # este método también se llama de forma
        # directa (inicializador de un for), que no pasa por self.visit().
        self._record_scope(node)
        if node.initializer is not None:
            self.visit(node.initializer)
        symbol = Symbol(
            name=node.name,
            category=SymbolCategory.VARIABLE,
            type_name=_type_name(node.type_annotation),
            initialized=node.initializer is not None,
            line=node.span.line,
            column=node.span.column,
        )
        self._declare(symbol, node)

    def visit_constant_declaration(self, node: ast.ConstantDeclaration) -> None:
        self._record_scope(node)  # defensivo, por simetría con variable_declaration
        self.visit(node.initializer)
        symbol = Symbol(
            name=node.name,
            category=SymbolCategory.CONSTANT,
            type_name=_type_name(node.type_annotation),
            initialized=True,
            line=node.span.line,
            column=node.span.column,
        )
        self._declare(symbol, node)

    def visit_parameter(self, node: ast.Parameter) -> None:
        # siempre se llama directamente desde
        # _process_function_body, nunca vía self.visit().
        self._record_scope(node)
        symbol = Symbol(
            name=node.name,
            category=SymbolCategory.PARAMETER,
            type_name=_type_name(node.type_annotation),
            initialized=True,
            line=node.span.line,
            column=node.span.column,
        )
        self._declare(symbol, node)

    # -- funciones ------------------------------------------------------------
    def _declare_function_signature(self, node: ast.FunctionDeclaration) -> None:
        # siempre se llama directamente (nunca vía
        # self.visit()), tanto para funciones de nivel superior como para
        # métodos de clase.
        self._record_scope(node)
        parameters = tuple(
            ParameterInfo(parameter.name, _type_name(parameter.type_annotation))
            for parameter in node.parameters
        )
        symbol = Symbol(
            name=node.name,
            category=SymbolCategory.FUNCTION,
            type_name="function",
            return_type=_type_name(node.return_type),
            parameters=parameters,
            initialized=True,
            line=node.span.line,
            column=node.span.column,
        )
        self._declare(symbol, node)

    def _process_function_body(self, node: ast.FunctionDeclaration) -> None:
        self._push(ScopeKind.FUNCTION, node.name)
        self._function_depth += 1
        for parameter in node.parameters:
            self.visit_parameter(parameter)
        self._process_statements(node.body.statements)
        self._function_depth -= 1
        self._pop()

    def visit_function_declaration(self, node: ast.FunctionDeclaration) -> None:
        """Punto de entrada cuando una función se visita de forma aislada
        (fuera del recorrido de ``_process_statements``, p. ej. en
        pruebas unitarias)."""
        self._declare_function_signature(node)
        self._process_function_body(node)

    # -- clases -----------------------------------------------------------
    def _declare_class_signature(self, node: ast.ClassDeclaration) -> None:
        self._record_scope(node)  # idem, siempre se llama directamente.
        symbol = Symbol(
            name=node.name,
            category=SymbolCategory.CLASS,
            type_name=node.name,
            superclass=node.superclass,
            initialized=True,
            line=node.span.line,
            column=node.span.column,
        )
        self._declare(symbol, node)

    def _process_class_body(self, node: ast.ClassDeclaration) -> None:
        class_symbol = self._current.resolve_local(node.name)
        if node.superclass is not None and self.table.find_class(node.superclass) is None:
            self._error(
                node,
                node.superclass,
                f"La clase base «{node.superclass}» no ha sido declarada.",
            )

        self._push(ScopeKind.CLASS, node.name)

        function_members = [m for m in node.members if isinstance(m, ast.FunctionDeclaration)]
        other_members = [m for m in node.members if not isinstance(m, ast.FunctionDeclaration)]

        for member in function_members:
            self._declare_function_signature(member)

        for member in other_members:
            self.visit(member)
            if class_symbol is not None:
                attribute_symbol = self._current.resolve_local(member.name)
                if attribute_symbol is not None:
                    class_symbol.attributes[member.name] = attribute_symbol

        for member in function_members:
            self._process_function_body(member)
            if class_symbol is not None:
                method_symbol = self._current.resolve_local(member.name)
                if method_symbol is not None:
                    class_symbol.methods[member.name] = method_symbol
                    if member.name == "constructor":
                        class_symbol.constructor = method_symbol

        self._pop()

    def visit_class_declaration(self, node: ast.ClassDeclaration) -> None:
        self._declare_class_signature(node)
        self._process_class_body(node)

    # -- bloques y control de flujo -------------------------------------------
    def visit_block(self, node: ast.Block) -> None:
        self._push(ScopeKind.BLOCK, f"bloque@{node.span.line}:{node.span.column}")
        self._process_statements(node.statements)
        self._pop()

    def visit_for_statement(self, node: ast.ForStatement) -> None:
        self._push(ScopeKind.BLOCK, f"for@{node.span.line}:{node.span.column}")
        if isinstance(node.initializer, ast.VariableDeclaration):
            self.visit_variable_declaration(node.initializer)
        elif node.initializer is not None:
            self.visit(node.initializer)
        if node.condition is not None:
            self.visit(node.condition)
        if node.update is not None:
            self.visit(node.update)
        self._loop_depth += 1
        self.visit(node.body)
        self._loop_depth -= 1
        self._pop()

    def visit_foreach_statement(self, node: ast.ForeachStatement) -> None:
        self.visit(node.iterable)
        self._push(ScopeKind.BLOCK, f"foreach@{node.span.line}:{node.span.column}")
        self._declare(
            Symbol(
                name=node.variable,
                category=SymbolCategory.VARIABLE,
                initialized=True,
                line=node.span.line,
                column=node.span.column,
            ),
            node,
        )
        self._loop_depth += 1
        self.visit(node.body)
        self._loop_depth -= 1
        self._pop()

    def visit_while_statement(self, node: ast.WhileStatement) -> None:
        self.visit(node.condition)
        self._loop_depth += 1
        self.visit(node.body)
        self._loop_depth -= 1

    def visit_do_while_statement(self, node: ast.DoWhileStatement) -> None:
        self._loop_depth += 1
        self.visit(node.body)
        self._loop_depth -= 1
        self.visit(node.condition)

    def visit_break_statement(self, node: ast.BreakStatement) -> None:
        if self._loop_depth == 0:
            self._error(node, "break", "«break» sólo puede usarse dentro de un bucle.")

    def visit_continue_statement(self, node: ast.ContinueStatement) -> None:
        if self._loop_depth == 0:
            self._error(node, "continue", "«continue» sólo puede usarse dentro de un bucle.")

    def visit_return_statement(self, node: ast.ReturnStatement) -> None:
        if self._function_depth == 0:
            self._error(node, "return", "«return» sólo puede usarse dentro de una función.")
        if node.value is not None:
            self.visit(node.value)

    def visit_try_catch_statement(self, node: ast.TryCatchStatement) -> None:
        self.visit(node.try_block)
        self._push(ScopeKind.BLOCK, f"catch@{node.span.line}:{node.span.column}")
        self._declare(
            Symbol(
                name=node.error_name,
                category=SymbolCategory.VARIABLE,
                initialized=True,
                line=node.span.line,
                column=node.span.column,
            ),
            node,
        )
        self._process_statements(node.catch_block.statements)
        self._pop()

    def visit_switch_statement(self, node: ast.SwitchStatement) -> None:
        self.visit(node.expression)
        self._push(ScopeKind.BLOCK, f"switch@{node.span.line}:{node.span.column}")
        for case in node.cases:
            self.visit(case.value)
            for statement in case.statements:
                self.visit(statement)
        for statement in node.default_statements:
            self.visit(statement)
        self._pop()

    # -- expresiones relacionadas con identificadores --------------------------
    def visit_identifier_expression(self, node: ast.IdentifierExpression) -> None:
        self._resolve_identifier(node.name, node)

    def visit_assignment_expression(self, node: ast.AssignmentExpression) -> None:
        if isinstance(node.target, ast.IdentifierExpression):
            # _resolve_identifier no pasa por
            # self.visit(), así que el nodo objetivo nunca quedaba
            # registrado en node_scopes (lo necesita el analizador
            # semántico para resolver "x" en "x = valor;").
            self._record_scope(node.target)
            symbol = self._resolve_identifier(node.target.name, node.target)
            if symbol is not None:
                if symbol.category is SymbolCategory.CONSTANT:
                    self._error(
                        node.target,
                        node.target.name,
                        f"No se puede reasignar la constante «{node.target.name}».",
                    )
                else:
                    self.table.update(self._current, node.target.name, initialized=True)
        else:
            self.visit(node.target)
        self.visit(node.value)

    def visit_this_expression(self, node: ast.ThisExpression) -> None:
        if self._current.enclosing_class() is None:
            self._error(node, "this", "«this» sólo puede usarse dentro de una clase.")

    def visit_new_expression(self, node: ast.NewExpression) -> None:
        if self.table.find_class(node.class_name) is None:
            self._error(
                node,
                node.class_name,
                f"La clase «{node.class_name}» no ha sido declarada.",
            )
        for argument in node.arguments:
            self.visit(argument)


def build_symbol_table(program: ast.Program | None) -> tuple[SymbolTable, list[Diagnostic]]:
    """Punto de integración equivalente a ``build_visual_tree``: recibe el
    AST de ``AnalysisResult.ast`` y devuelve la tabla junto con los
    diagnósticos semánticos de ámbito/declaración."""
    builder = SymbolTableBuilder()
    if program is not None:
        builder.build(program)
    return builder.table, builder.diagnostics