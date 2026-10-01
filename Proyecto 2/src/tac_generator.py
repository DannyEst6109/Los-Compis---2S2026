"""Generador de código intermedio (TAC) a partir del AST de Compiscript.

Es un Visitor más sobre el mismo AST que ya consumen ``symbol_table.py`` y
``semantic_analyzer.py``. Recibe la ``SymbolTable`` construida para ese
mismo ``Program`` (la usa, vía ``node_scopes``, para saber a qué símbolo se
refiere cada identificador) y produce un ``tac.TACProgram``.

Sólo debe ejecutarse sobre programas **sin** diagnósticos léxicos,
sintácticos ni semánticos: la especificación del lenguaje intermedio asume
que los tipos ya fueron validados.

Uso típico::

    from analyzer import CompiscriptAnalyzer
    from symbol_table import build_symbol_table
    from semantic_analyzer import analyze_semantics
    from tac_generator import generate_tac

    result = CompiscriptAnalyzer().analyze(source)
    table, scope_diagnostics = build_symbol_table(result.ast)
    type_diagnostics = analyze_semantics(table, result.ast)
    if result.is_valid and not scope_diagnostics and not type_diagnostics:
        tac = generate_tac(table, result.ast)
        print(tac.render())

## Contrato para expresiones (lo que debe respetar cualquier ``visit_*``)

- Visitar una expresión emite las instrucciones que la calculan y devuelve
  el **operando** donde quedó su valor: ``Const`` (literal), ``Var``
  (variable) o ``Temp`` (resultado intermedio).
- Quien recibe un ``Temp`` es su **dueño**: debe usarlo exactamente una vez
  como operando y liberarlo con ``self.temps.release(...)`` (``release``
  ignora operandos que no son temporales). ``compute`` ya hace esto.
- Cada instrucción debe terminar con la misma cantidad de temporales vivos
  con la que empezó; ``generate_statement`` lo verifica.

## Alcance actual

Implementado: literales, variables, agrupación, operadores aritméticos,
relacionales, de igualdad y unarios, concatenación de ``string``,
asignaciones (a variables y a elementos de arreglo), literales de arreglo,
acceso por índice, declaraciones ``let``/``var``/``const``, instrucciones
de expresión y ``print``.

Los nodos que todavía no tienen traducción (control de flujo, ``&&``,
``||``, ``?:``, funciones, llamadas, clases y objetos) llegan a
``generic_visit`` y producen ``TACGenerationError``: es preferible fallar
de forma explícita a emitir TAC incompleto. Para agregarlos basta con
definir el ``visit_<nodo>`` correspondiente (en esta clase o en un mixin)
usando ``emit``, ``compute``, ``temps`` y ``variable``.
"""

from __future__ import annotations

import re

import ast_nodes as ast
from ast_visitor import AstVisitor
from semantic_analyzer import SemanticAnalyzer, Type, TypeKind
from symbol_table import Symbol, SymbolTable
from tac import (
    SOURCE_BINARY_OPS,
    SOURCE_UNARY_OPS,
    Const,
    Operand,
    TACInstruction,
    TACOp,
    TACProgram,
    Temp,
    Var,
)
from temporaries import TempAllocator


class TACGenerationError(Exception):
    """El AST contiene algo que no puede (o todavía no puede) traducirse."""

    def __init__(self, node: ast.AstNode, message: str) -> None:
        self.node = node
        self.line = node.span.line
        self.column = node.span.column
        super().__init__(f"Línea {self.line}:{self.column}: {message}")


# ---------------------------------------------------------------------------
# Tipos de las expresiones
# ---------------------------------------------------------------------------


class _ExpressionTypeRecorder(SemanticAnalyzer):
    """Reutiliza la inferencia de tipos del analizador semántico y guarda el
    tipo de cada expresión (``SemanticAnalyzer`` los calcula pero no los
    conserva). Se necesita, por ejemplo, para distinguir ``+`` entre
    enteros (ADD) de ``+`` entre strings (CONCAT)."""

    def __init__(self, table: SymbolTable) -> None:
        super().__init__(table)
        self.types: dict[int, Type] = {}

    def visit(self, node: ast.AstNode):
        result = super().visit(node)
        if isinstance(node, ast.Expression) and isinstance(result, Type):
            self.types[id(node)] = result
        return result


def infer_expression_types(table: SymbolTable, program: ast.Program) -> dict[int, Type]:
    """Mapa ``id(expresión) -> Type`` para el mismo ``Program`` de ``table``."""
    recorder = _ExpressionTypeRecorder(table)
    recorder.analyze(program)
    return recorder.types


# ---------------------------------------------------------------------------
# Generador
# ---------------------------------------------------------------------------


# Nombres que el TAC reserva para temporales (t1, t2, ...) y etiquetas
# (L1, L2, ...). Una variable del programa con uno de estos nombres se
# renombra para que nunca se confunda con ellos.
_RESERVED_NAME = re.compile(r"^(t|L)\d+$")


class TACGenerator(AstVisitor[Operand | None]):
    def __init__(self, table: SymbolTable, expression_types: dict[int, Type] | None = None) -> None:
        self.table = table
        self.program = TACProgram()
        self.temps = TempAllocator()
        self._types = expression_types if expression_types is not None else {}
        self._names: dict[int, str] = {}  # id(Symbol) -> nombre en el TAC
        self._used_names: set[str] = set()
        self._line: int | None = None

    def generate(self, program: ast.Program) -> TACProgram:
        self.visit(program)
        return self.program

    # -- infraestructura ------------------------------------------------------
    def visit(self, node: ast.AstNode) -> Operand | None:
        # Cada instrucción emitida recuerda la línea del nodo más interno
        # que se estaba traduciendo.
        previous = self._line
        self._line = node.span.line
        try:
            return super().visit(node)
        finally:
            self._line = previous

    def generic_visit(self, node: ast.AstNode) -> Operand | None:
        raise TACGenerationError(
            node, f"La generación de TAC para «{type(node).__name__}» todavía no está implementada."
        )

    def emit(
        self,
        op: TACOp,
        result: Operand | None = None,
        arg1: Operand | None = None,
        arg2: Operand | None = None,
    ) -> TACInstruction:
        return self.program.emit(op, result, arg1, arg2, line=self._line)

    def compute(self, op: TACOp, arg1: Operand, arg2: Operand | None = None) -> Temp:
        """Emite ``t = arg1 op arg2`` (o ``t = op arg1``) y devuelve ``t``.

        Los operandos se liberan *antes* de pedir el temporal del
        resultado, para que éste pueda reutilizar uno de ellos."""
        self.temps.release(arg1)
        self.temps.release(arg2)
        result = self.temps.new()
        self.emit(op, result, arg1, arg2)
        return result

    def type_of(self, node: ast.Expression) -> Type | None:
        return self._types.get(id(node))

    # -- nombres de variables --------------------------------------------------
    def variable(self, node: ast.AstNode, name: str) -> Var:
        """Operando para el identificador ``name`` tal como se ve desde
        ``node`` (respeta shadowing gracias a ``node_scopes``)."""
        scope = self.table.scope_of(node)
        found = scope.resolve(name) if scope is not None else None
        if found is None:
            raise TACGenerationError(node, f"No se encontró el símbolo «{name}» en la tabla de símbolos.")
        symbol = found[0]
        return Var(self._tac_name(symbol), symbol)

    def _tac_name(self, symbol: Symbol) -> str:
        """Nombre único en todo el programa para ``symbol``: el original si
        está libre; si no, ``nombre$1``, ``nombre$2``... (``$`` no puede
        aparecer en un identificador de Compiscript, así que no choca)."""
        key = id(symbol)
        cached = self._names.get(key)
        if cached is not None:
            return cached
        name = symbol.name
        if name in self._used_names or _RESERVED_NAME.match(name):
            suffix = 1
            while f"{symbol.name}${suffix}" in self._used_names:
                suffix += 1
            name = f"{symbol.name}${suffix}"
        self._used_names.add(name)
        self._names[key] = name
        return name

    # -- secuencias de instrucciones ------------------------------------------
    def generate_statements(self, statements: tuple[ast.Statement, ...]) -> None:
        for statement in statements:
            self.generate_statement(statement)

    def generate_statement(self, statement: ast.Statement) -> None:
        live_before = self.temps.live_count
        self.visit(statement)
        if self.temps.live_count != live_before:
            raise TACGenerationError(
                statement,
                f"«{type(statement).__name__}» terminó con {self.temps.live_count} temporales vivos "
                f"(se esperaban {live_before}).",
            )

    def visit_program(self, node: ast.Program) -> None:
        self.generate_statements(node.statements)

    def visit_block(self, node: ast.Block) -> None:
        self.generate_statements(node.statements)

    # -- instrucciones simples ----------------------------------------------
    def visit_variable_declaration(self, node: ast.VariableDeclaration) -> None:
        # Sin inicializador no hay nada que calcular: reservar espacio para
        # la variable es trabajo del registro de activación, no del TAC.
        if node.initializer is None:
            return
        self._store(node, node.name, node.initializer)

    def visit_constant_declaration(self, node: ast.ConstantDeclaration) -> None:
        self._store(node, node.name, node.initializer)

    def _store(self, node: ast.AstNode, name: str, initializer: ast.Expression) -> None:
        value = self.visit(initializer)
        self.emit(TACOp.ASSIGN, self.variable(node, name), value)
        self.temps.release(value)

    def visit_expression_statement(self, node: ast.ExpressionStatement) -> None:
        self.temps.release(self.visit(node.expression))

    def visit_print_statement(self, node: ast.PrintStatement) -> None:
        value = self.visit(node.expression)
        self.emit(TACOp.PRINT, arg1=value)
        self.temps.release(value)

    # -- expresiones: hojas ----------------------------------------------------
    def visit_literal_expression(self, node: ast.LiteralExpression) -> Const:
        return Const(node.value, node.literal_type)

    def visit_identifier_expression(self, node: ast.IdentifierExpression) -> Var:
        return self.variable(node, node.name)

    def visit_grouping_expression(self, node: ast.GroupingExpression) -> Operand:
        # Los paréntesis ya quedaron reflejados en la forma del árbol.
        return self.visit(node.expression)

    def visit_error_expression(self, node: ast.ErrorExpression) -> Operand:
        raise TACGenerationError(
            node, "El programa contiene errores; no se genera código intermedio."
        )

    # -- expresiones: operadores ------------------------------------------------
    def visit_unary_expression(self, node: ast.UnaryExpression) -> Operand:
        operand_node = node.operand
        # La gramática no tiene literales negativos: «-5» es un menos unario
        # sobre 5. Se trata como la constante -5 en vez de «t = minus 5».
        if (
            node.operator == "-"
            and isinstance(operand_node, ast.LiteralExpression)
            and operand_node.literal_type == "integer"
        ):
            return Const(-operand_node.value, "integer")
        op = SOURCE_UNARY_OPS.get(node.operator)
        if op is None:
            return self.generic_visit(node)
        return self.compute(op, self.visit(operand_node))

    def visit_binary_expression(self, node: ast.BinaryExpression) -> Operand:
        op = SOURCE_BINARY_OPS.get(node.operator)
        if op is None:
            # «&&» y «||» se evalúan en cortocircuito, con saltos.
            return self.generic_visit(node)
        left = self.visit(node.left)
        right = self.visit(node.right)
        if op is TACOp.ADD and self._is_string_concat(node, left, right):
            op = TACOp.CONCAT
        return self.compute(op, left, right)

    def _is_string_concat(self, node: ast.BinaryExpression, left: Operand, right: Operand) -> bool:
        node_type = self.type_of(node)
        if node_type is not None:
            return node_type.kind is TypeKind.STRING
        return any(isinstance(item, Const) and item.type_name == "string" for item in (left, right))

    # -- expresiones: asignación ------------------------------------------------
    def visit_assignment_expression(self, node: ast.AssignmentExpression) -> Operand:
        target = node.target
        if isinstance(target, ast.IdentifierExpression):
            value = self.visit(node.value)
            variable = self.variable(target, target.name)
            self.emit(TACOp.ASSIGN, variable, value)
            self.temps.release(value)
            # El valor de «x = e» es x, así «a = b = e» encadena sin
            # mantener vivo el temporal de e.
            return variable
        if isinstance(target, ast.IndexExpression):
            collection = self.visit(target.collection)
            index = self.visit(target.index)
            value = self.visit(node.value)
            self.emit(TACOp.INDEX_STORE, collection, index, value)
            self.temps.release(collection)
            self.temps.release(index)
            # El valor de «a[i] = e» es e; si es un temporal, sigue vivo y
            # ahora pertenece a quien pidió esta expresión.
            return value
        return self.generic_visit(node)

    # -- expresiones: arreglos --------------------------------------------------
    def visit_array_expression(self, node: ast.ArrayExpression) -> Temp:
        array = self.temps.new()
        self.emit(TACOp.NEW_ARRAY, array, Const(len(node.elements), "integer"))
        for position, element in enumerate(node.elements):
            value = self.visit(element)
            self.emit(TACOp.INDEX_STORE, array, Const(position, "integer"), value)
            self.temps.release(value)
        return array

    def visit_index_expression(self, node: ast.IndexExpression) -> Temp:
        collection = self.visit(node.collection)
        index = self.visit(node.index)
        return self.compute(TACOp.INDEX_LOAD, collection, index)


def generate_tac(table: SymbolTable, program: ast.Program) -> TACProgram:
    """Punto de integración: recibe la tabla y el MISMO ``Program`` con el
    que se construyó (igual que ``analyze_semantics``) y devuelve el TAC."""
    types = infer_expression_types(table, program)
    return TACGenerator(table, types).generate(program)
