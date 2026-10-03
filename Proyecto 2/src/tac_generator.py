"""Generador de código intermedio (TAC) a partir del AST de Compiscript.

Es un Visitor más sobre el mismo AST que ya consumen ``symbol_table.py`` y
``semantic_analyzer.py``. Recibe la ``SymbolTable`` construida para ese
mismo ``Program`` (la usa, vía ``node_scopes``, para saber a qué símbolo se
refiere cada identificador) y produce un ``tac.TACProgram``.

Sólo debe ejecutarse sobre programas sin diagnósticos léxicos,
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

## Alcance

Esta clase traduce literales, variables, agrupación, operadores
aritméticos, relacionales, de igualdad y unarios, concatenación de
``string``, asignaciones (a variables, elementos de arreglo y atributos),
literales de arreglo, acceso por índice, declaraciones ``let``/``var``/
``const``, instrucciones de expresión y ``print``. El resto está en mixins:

- ``tac_control_flow.ControlFlowMixin``: condiciones, ``&&``, ``||``,
  ``?:``, ciclos, ``switch``, ``break`` y ``continue``.
- ``tac_functions.FunctionMixin``: funciones, llamadas y ``return``.
- ``tac_objects.ObjectMixin``: clases, ``new``, atributos, ``this`` y
  métodos con despacho dinámico.
- ``tac_exceptions.ExceptionMixin``: ``try/catch``.

Un nodo sin traducción llega a ``generic_visit`` y produce
``TACGenerationError``: es preferible fallar de forma explícita a emitir
TAC incompleto.
"""

from __future__ import annotations

import re

import ast_nodes as ast
from ast_visitor import AstVisitor
from memory_layout import assign_memory_layout
from semantic_analyzer import SemanticAnalyzer, Type, TypeKind
from symbol_table import Scope, Symbol, SymbolTable
from tac import (
    SOURCE_BINARY_OPS,
    SOURCE_UNARY_OPS,
    Const,
    Name,
    Operand,
    TACInstruction,
    TACOp,
    TACProgram,
    Temp,
    Var,
)
from temporaries import TempAllocator
from tac_control_flow import ControlFlowMixin
from tac_exceptions import ExceptionMixin
from tac_functions import FunctionMixin
from tac_objects import ObjectMixin


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


    @property
    def symbol_types(self) -> dict[int, Type]:
        """Tipo declarado o inferido de cada variable: ``id(Symbol) -> Type``."""
        return self._symbol_types


def infer_types(table: SymbolTable, program: ast.Program) -> tuple[dict[int, Type], dict[int, Type]]:
    """Tipos de expresiones (``id(expresión)``) y de símbolos (``id(Symbol)``)."""
    recorder = _ExpressionTypeRecorder(table)
    recorder.analyze(program)
    return recorder.types, recorder.symbol_types


def infer_expression_types(table: SymbolTable, program: ast.Program) -> dict[int, Type]:
    """Mapa ``id(expresión) -> Type`` para el mismo ``Program`` de ``table``."""
    return infer_types(table, program)[0]


# ---------------------------------------------------------------------------
# Generador
# ---------------------------------------------------------------------------


# Nombres que el TAC reserva para temporales (t1, t2, ...) y etiquetas
# (L1, L2, ...). Una variable del programa con uno de estos nombres se
# renombra para que nunca se confunda con ellos.
_RESERVED_NAME = re.compile(r"^(t|L)\d+$")


class TACGenerator(FunctionMixin, ObjectMixin, ExceptionMixin, ControlFlowMixin, AstVisitor[Operand | None]):
    def __init__(self, table: SymbolTable, expression_types: dict[int, Type] | None = None) -> None:
        self.table = table
        self.program = TACProgram()
        self.temps = TempAllocator()
        self._types = expression_types if expression_types is not None else {}
        self._names: dict[int, str] = {}  # id(Symbol) -> nombre en el TAC
        self._used_names: set[str] = set()
        self._line: int | None = None
        self._init_control_flow()
        self._init_functions()
        self._init_exceptions()

    def generate(self, program: ast.Program) -> TACProgram:
        """Traduce ``program``. El resultado tiene primero una sección
        ``begin_func``/``end_func`` por cada función, método e inicializador
        y después el código global, que es el punto de entrada."""
        if not self.table.has_layout:
            assign_memory_layout(self.table)
        # Una variable no debe imprimirse igual que una función.
        self._used_names.update(record.name for record in self.table.activation_records)
        self.visit(program)
        if self.table.global_record is not None:
            self.table.global_record.temporaries = self.temps.created
        self.unit_temps.append(("global", self.temps))
        self.program = self.assemble_sections(self.program.instructions)
        return self.program

    def _fresh_unit_state(self) -> dict[str, object]:
        state = super()._fresh_unit_state()
        state.update(_handler_depth=0, _handler_marks=[])
        return state

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
    def resolve(self, node: ast.AstNode, name: str) -> tuple[Symbol, Scope]:
        """Símbolo de ``name`` visto desde ``node`` y el ámbito que lo declara
        (respeta shadowing gracias a ``node_scopes``)."""
        scope = self.table.scope_of(node)
        found = scope.resolve(name) if scope is not None else None
        if found is None:
            raise TACGenerationError(node, f"No se encontró el símbolo «{name}» en la tabla de símbolos.")
        return found

    def variable(self, node: ast.AstNode, name: str) -> Var:
        """Operando para el identificador ``name`` tal como se ve desde ``node``."""
        symbol = self.resolve(node, name)[0]
        return Var(self._tac_name(symbol), symbol)

    def _tac_name(self, symbol: Symbol) -> str:
        """Nombre único en todo el programa para ``symbol``: el original si
        está libre; si no, ``nombre$1``, ``nombre$2``... (``$`` no puede
        aparecer en un identificador de Compiscript, así que no choca).
        Las funciones usan la etiqueta que les asignó la tabla de símbolos."""
        if symbol.tac_label is not None:
            return symbol.tac_label
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

    def visit_identifier_expression(self, node: ast.IdentifierExpression) -> Operand:
        symbol, owner = self.resolve(node, node.name)
        if self.is_attribute(symbol, owner):
            # Atributo nombrado sin «this.» dentro de un método.
            return self.compute(TACOp.FIELD_LOAD, self.this_operand(node), Name(node.name))
        return Var(self._tac_name(symbol), symbol)

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
        if node.operator in {"&&", "||"}:
            return self.generate_logical_value(node)
        op = SOURCE_BINARY_OPS.get(node.operator)
        if op is None:
            return self.generic_visit(node)
        left = self.visit(node.left)
        right = self.visit(node.right)
        if op is TACOp.ADD and self._is_string_concat(node, left, right):
            op = TACOp.CONCAT
        return self.compute(op, left, right)

    def _is_string_concat(self, node: ast.BinaryExpression, left: Operand, right: Operand) -> bool:
        node_type = self.type_of(node)
        if node_type is not None and node_type.kind is not TypeKind.UNKNOWN:
            return node_type.kind is TypeKind.STRING
        # Sin tipo conocido (p. ej. un parámetro sin anotación): basta con
        # que un operando sea string para que «+» sea una concatenación.
        for side, operand in ((node.left, left), (node.right, right)):
            side_type = self.type_of(side)
            if side_type is not None and side_type.kind is TypeKind.STRING:
                return True
            if isinstance(operand, Const) and operand.type_name == "string":
                return True
        return False

    # -- expresiones: asignación ------------------------------------------------
    def visit_assignment_expression(self, node: ast.AssignmentExpression) -> Operand:
        target = node.target
        if isinstance(target, ast.MemberExpression):
            instance = self.visit(target.object)
            return self.store_field(instance, target.member, self.visit(node.value))
        if isinstance(target, ast.IdentifierExpression) and self.is_attribute(*self.resolve(target, target.name)):
            value = self.visit(node.value)
            return self.store_field(self.this_operand(target), target.name, value)
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


def prepare_generator(table: SymbolTable, program: ast.Program) -> TACGenerator:
    """Infiere los tipos, completa la tabla con direcciones y registros de
    activación (``memory_layout``) y devuelve un generador listo."""
    expression_types, symbol_types = infer_types(table, program)
    assign_memory_layout(table, symbol_types)
    return TACGenerator(table, expression_types)


def generate_tac(table: SymbolTable, program: ast.Program) -> TACProgram:
    """Punto de integración: recibe la tabla y el MISMO ``Program`` con el
    que se construyó (igual que ``analyze_semantics``) y devuelve el TAC.
    Como efecto, la tabla queda con las direcciones y registros de
    activación de cada símbolo."""
    return prepare_generator(table, program).generate(program)
