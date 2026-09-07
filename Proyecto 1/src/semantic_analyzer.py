"""Analizador semántico de Compiscript: sistema de tipos, control de flujo,
validaciones de funciones/clases desde el punto de vista de tipos, listas y
reglas generales (código muerto, expresiones inválidas).

Este módulo es un segundo Visitor independiente de ``symbol_table.py``: no
vuelve a resolver ámbitos ni a detectar declaraciones duplicadas (eso ya lo
hace ``SymbolTableBuilder``). En cambio, usa ``SymbolTable.scope_of(node)``
para saber en qué ámbito vive cada nodo del AST y así resolver
identificadores a su ``Symbol`` (con tipo, parámetros, atributos, etc.) sin
reimplementar el manejo de ámbitos.

Uso típico::

    from analyzer import CompiscriptAnalyzer
    from symbol_table import build_symbol_table
    from semantic_analyzer import analyze_semantics

    result = CompiscriptAnalyzer().analyze(source)
    table, scope_diagnostics = build_symbol_table(result.ast)
    type_diagnostics = analyze_semantics(table, result.ast)

``scope_diagnostics`` y ``type_diagnostics`` comparten el mismo formato
(``symbol_table.Diagnostic`` = mismos campos que ``analyzer.Diagnostic``), así
que se pueden combinar y ordenar junto con los diagnósticos léxicos y
sintácticos sin conversiones adicionales.

## División de responsabilidades con symbol_table.py

Ya cubierto por ``SymbolTableBuilder`` y por lo tanto no se repite aquí:

- Identificador no declarado / identificador duplicado en el mismo ámbito.
- Parámetros duplicados.
- Reasignación de una constante.
- ``break``/``continue`` fuera de un bucle.
- ``return`` fuera de una función.
- ``this`` fuera de una clase.
- ``new`` de una clase no declarada / herencia de una clase no declarada.

Este módulo se concentra en todo lo que depende de **tipos** y de **flujo
de ejecución dentro de una secuencia de instrucciones**: aritmética, lógica,
comparaciones, compatibilidad de asignaciones, condiciones booleanas,
argumentos/retorno de funciones y métodos, atributos/métodos de clases,
listas, y código muerto.

## Manejo de errores (no fatal, sin duplicados en cascada)
Cada nodo de expresión se tipa como un ``Type``. Cuando algo ya fue
reportado como erróneo (identificador no declarado, clase inexistente,
etc.) el nodo se tipa como ``ERROR`` en lugar de lanzar una excepción; los
operadores y llamadas propagan ``ERROR`` sin emitir un segundo diagnóstico
("evitar mensajes derivados de un error anterior"). El recorrido es un
único paso descendente sobre un árbol finito e inmutable, así que no hay
riesgo de ciclos infinitos.

## Desviaciones deliberadas respecto al enunciado genérico
- No existe el tipo ``float``: la gramática de Compiscript (`grammar/Compiscript.g4`)
  no define ni un token ``FLOAT`` ni un literal de punto flotante, sólo
  ``integer``, ``string``, ``boolean`` y clases. Las operaciones aritméticas
  se validan sólo contra ``integer`` (más el caso especial de ``+`` para
  concatenar ``string``, que el propio README del lenguaje usa como
  ejemplo: ``"Hola " + nombre``). 
- ``switch`` no exige una condición booleana: obligarlo sería casi
  inútil (un `switch` sólo tendría sentido con dos casos). En su lugar se
  valida que cada valor de ``case`` sea comparable con el tipo de la
  expresión del ``switch``.
- Código muerto se detecta a nivel de "instrucción siguiente dentro del
  mismo bloque" (lo que pide literalmente el enunciado: algo después de un
  ``return``/``break``/``continue``), no mediante un análisis de
  alcanzabilidad completo con ramas (p. ej. un `if/else` donde ambas ramas
  retornan no marca como muerto lo que sigue del `if`). 
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

import ast_nodes as ast
from ast_visitor import AstVisitor
from symbol_table import (
    Diagnostic,
    ParameterInfo,
    Symbol,
    SymbolCategory,
    SymbolTable,
)



# Modelo de tipos
class TypeKind(Enum):
    INTEGER = "integer"
    STRING = "string"
    BOOLEAN = "boolean"
    NULL = "null"
    VOID = "void"
    ARRAY = "array"
    CLASS = "class"
    FUNCTION = "función"
    ERROR = "<error>"
    UNKNOWN = "<desconocido>"


@dataclass(frozen=True, slots=True)
class Type:
    kind: TypeKind
    element_type: Optional["Type"] = None
    class_name: str | None = None

    def __str__(self) -> str:
        if self.kind is TypeKind.ARRAY:
            return f"{self.element_type}[]"
        if self.kind is TypeKind.CLASS:
            return self.class_name or "clase"
        return self.kind.value


INTEGER = Type(TypeKind.INTEGER)
STRING = Type(TypeKind.STRING)
BOOLEAN = Type(TypeKind.BOOLEAN)
NULL = Type(TypeKind.NULL)
VOID = Type(TypeKind.VOID)
FUNCTION = Type(TypeKind.FUNCTION)
ERROR = Type(TypeKind.ERROR)
UNKNOWN = Type(TypeKind.UNKNOWN)


def array_of(element: Type) -> Type:
    return Type(TypeKind.ARRAY, element_type=element)


def class_type(name: str) -> Type:
    return Type(TypeKind.CLASS, class_name=name)


# Analizador semántico
class SemanticAnalyzer(AstVisitor[Type]):
    """Segundo Visitor sobre el mismo AST. Infiere el tipo de cada
    expresión (de abajo hacia arriba) y valida las reglas semánticas que
    dependen de tipos y de flujo de ejecución."""

    _ARITHMETIC_OPERATORS = {"-", "*", "/", "%"}
    _LOGICAL_OPERATORS = {"&&", "||"}
    _EQUALITY_OPERATORS = {"==", "!="}
    _RELATIONAL_OPERATORS = {"<", "<=", ">", ">="}
    _TERMINATORS = (ast.ReturnStatement, ast.BreakStatement, ast.ContinueStatement)

    def __init__(self, table: SymbolTable) -> None:
        self.table = table
        self.diagnostics: list[Diagnostic] = []
        self._return_type_stack: list[Type] = []
        self._symbol_types: dict[int, Type] = {}

    def analyze(self, program: ast.Program) -> list[Diagnostic]:
        self.visit(program)
        return self.diagnostics

    # utilidades internas 
    def _error(self, node: ast.AstNode, symbol_text: object, description: str) -> None:
        self.diagnostics.append(
            Diagnostic(
                kind="Semántico",
                line=node.span.line,
                column=node.span.column,
                symbol=str(symbol_text),
                description=description,
            )
        )

    def _describe(self, node: ast.AstNode) -> str:
        if isinstance(node, ast.IdentifierExpression):
            return node.name
        if isinstance(node, ast.MemberExpression):
            return f".{node.member}"
        return type(node).__name__

    def _symbol_for_name(self, node: ast.AstNode, name: str) -> Symbol | None:
        scope = self.table.scope_of(node)
        if scope is None:
            return None
        return scope.resolve_local(name)

    # resolución de anotaciones de tipo 
    def _build_type(self, base_name: str, dimensions: int, error_node: ast.AstNode) -> Type:
        if base_name == "integer":
            result = INTEGER
        elif base_name == "string":
            result = STRING
        elif base_name == "boolean":
            result = BOOLEAN
        elif self.table.find_class(base_name) is not None:
            result = class_type(base_name)
        else:
            self._error(error_node, base_name, f"El tipo «{base_name}» no ha sido declarado.")
            return ERROR
        for _ in range(dimensions):
            result = array_of(result)
        return result

    def _resolve_type_ref(self, type_ref: ast.TypeRef | None) -> Type:
        """Para anotaciones donde la ausencia significa "sin anotar,
        infiera del valor" (variables, constantes, parámetros)."""
        if type_ref is None:
            return UNKNOWN
        return self._build_type(type_ref.name, type_ref.dimensions, type_ref)

    def _resolve_return_type(self, type_ref: ast.TypeRef | None) -> Type:
        """Para el tipo de retorno de una función, donde la ausencia
        significa "no devuelve valor" (procedimiento)."""
        if type_ref is None:
            return VOID
        return self._build_type(type_ref.name, type_ref.dimensions, type_ref)

    def _type_from_name(self, name: str | None, *, none_means_void: bool = False) -> Type:
        """Convierte el ``type_name``/``return_type`` (texto) que guarda un
        ``Symbol`` de symbol_table.py de vuelta a un ``Type`` estructurado."""
        if name is None:
            return VOID if none_means_void else UNKNOWN
        if name == "function":
            return FUNCTION
        base = name
        dims = 0
        while base.endswith("[]"):
            base = base[:-2]
            dims += 1
        if base == "integer":
            result = INTEGER
        elif base == "string":
            result = STRING
        elif base == "boolean":
            result = BOOLEAN
        elif self.table.find_class(base) is not None:
            result = class_type(base)
        else:
            return UNKNOWN
        for _ in range(dims):
            result = array_of(result)
        return result

    def _type_of_symbol(self, symbol: Symbol) -> Type:
        if symbol.category is SymbolCategory.FUNCTION:
            return FUNCTION
        if symbol.category is SymbolCategory.CLASS:
            return class_type(symbol.name)
        cached = self._symbol_types.get(id(symbol))
        if cached is not None:
            return cached
        return self._type_from_name(symbol.type_name)

    #  compatibilidad de tipos 
    def is_assignable(self, target: Type, value: Type) -> bool:
        if target.kind is TypeKind.ERROR or value.kind is TypeKind.ERROR:
            return True
        if target.kind is TypeKind.UNKNOWN or value.kind is TypeKind.UNKNOWN:
            return True
        if value.kind is TypeKind.NULL:
            return target.kind in (TypeKind.CLASS, TypeKind.ARRAY, TypeKind.NULL)
        if target.kind is TypeKind.ARRAY and value.kind is TypeKind.ARRAY:
            if target.element_type is None or value.element_type is None:
                return True
            if UNKNOWN in (target.element_type, value.element_type):
                return True
            return self.is_assignable(target.element_type, value.element_type)
        if target.kind is TypeKind.CLASS and value.kind is TypeKind.CLASS:
            return self._is_subclass(value.class_name, target.class_name)
        return target.kind is value.kind

    def _is_subclass(self, sub_name: str | None, super_name: str | None) -> bool:
        if sub_name is None or super_name is None:
            return False
        if sub_name == super_name:
            return True
        current = self.table.find_class(sub_name)
        seen: set[str] = set()
        while current is not None and current.superclass and current.name not in seen:
            seen.add(current.name)
            if current.superclass == super_name:
                return True
            current = self.table.find_class(current.superclass)
        return False

    def _comparable(self, a: Type, b: Type) -> bool:
        if a.kind is TypeKind.ERROR or b.kind is TypeKind.ERROR:
            return True
        if a.kind is TypeKind.UNKNOWN or b.kind is TypeKind.UNKNOWN:
            return True
        if a.kind is TypeKind.NULL or b.kind is TypeKind.NULL:
            return True
        if a.kind is TypeKind.CLASS and b.kind is TypeKind.CLASS:
            return self._is_subclass(a.class_name, b.class_name) or self._is_subclass(b.class_name, a.class_name)
        return a.kind is b.kind

    def _expect_boolean(self, node: ast.AstNode, type_: Type, context: str) -> None:
        if type_.kind in (TypeKind.BOOLEAN, TypeKind.ERROR, TypeKind.UNKNOWN):
            return
        self._error(node, context, f"Se esperaba una expresión de tipo boolean en {context}; se encontró {type_}.")

    # código muerto: secuencias de instrucciones 
    def _visit_statement_sequence(self, statements: tuple[ast.Statement, ...]) -> None:
        terminated = False
        for statement in statements:
            if terminated:
                self._error(
                    statement,
                    self._describe(statement),
                    "Código muerto: esta instrucción nunca se ejecuta porque la anterior "
                    "siempre termina el bloque (return/break/continue).",
                )
                break
            self.visit(statement)
            if isinstance(statement, self._TERMINATORS):
                terminated = True

    #  estructura 
    def visit_program(self, node: ast.Program) -> None:
        self._visit_statement_sequence(node.statements)

    def visit_block(self, node: ast.Block) -> None:
        self._visit_statement_sequence(node.statements)

    def visit_class_declaration(self, node: ast.ClassDeclaration) -> None:
        for member in node.members:
            self.visit(member)

    def visit_parameter(self, node: ast.Parameter) -> None:
        symbol = self._symbol_for_name(node, node.name)
        param_type = self._resolve_type_ref(node.type_annotation)
        if symbol is not None:
            self._symbol_types[id(symbol)] = param_type

    def visit_function_declaration(self, node: ast.FunctionDeclaration) -> None:
        for parameter in node.parameters:
            self.visit_parameter(parameter)
        return_type = self._resolve_return_type(node.return_type)
        self._return_type_stack.append(return_type)
        self._visit_statement_sequence(node.body.statements)
        self._return_type_stack.pop()

    #  declaraciones con tipo 
    def visit_variable_declaration(self, node: ast.VariableDeclaration) -> None:
        declared_type = self._resolve_type_ref(node.type_annotation)
        initializer_type = self.visit(node.initializer) if node.initializer is not None else None
        if node.type_annotation is not None:
            effective_type = declared_type
            if initializer_type is not None and not self.is_assignable(declared_type, initializer_type):
                self._error(
                    node, node.name,
                    (
                        f"El valor asignado a «{node.name}» es de tipo {initializer_type} y no es "
                        f"compatible con el tipo declarado {declared_type}."
                    ),
                )
        else:
            effective_type = initializer_type if initializer_type is not None else UNKNOWN
        symbol = self._symbol_for_name(node, node.name)
        if symbol is not None:
            self._symbol_types[id(symbol)] = effective_type

    def visit_constant_declaration(self, node: ast.ConstantDeclaration) -> None:
        declared_type = self._resolve_type_ref(node.type_annotation)
        initializer_type = self.visit(node.initializer)
        if node.type_annotation is not None:
            effective_type = declared_type
            if not self.is_assignable(declared_type, initializer_type):
                self._error(
                    node, node.name,
                    (
                        f"El valor asignado a la constante «{node.name}» es de tipo {initializer_type} y "
                        f"no es compatible con el tipo declarado {declared_type}."
                    ),
                )
        else:
            effective_type = initializer_type
        symbol = self._symbol_for_name(node, node.name)
        if symbol is not None:
            self._symbol_types[id(symbol)] = effective_type

    # control de flujo: condiciones booleanas 
    def visit_if_statement(self, node: ast.IfStatement) -> None:
        self._expect_boolean(node.condition, self.visit(node.condition), "la condición del if")
        self.visit(node.then_branch)
        if node.else_branch is not None:
            self.visit(node.else_branch)

    def visit_while_statement(self, node: ast.WhileStatement) -> None:
        self._expect_boolean(node.condition, self.visit(node.condition), "la condición del while")
        self.visit(node.body)

    def visit_do_while_statement(self, node: ast.DoWhileStatement) -> None:
        self.visit(node.body)
        self._expect_boolean(node.condition, self.visit(node.condition), "la condición del do-while")

    def visit_for_statement(self, node: ast.ForStatement) -> None:
        if isinstance(node.initializer, ast.VariableDeclaration):
            self.visit_variable_declaration(node.initializer)
        elif node.initializer is not None:
            self.visit(node.initializer)
        if node.condition is not None:
            self._expect_boolean(node.condition, self.visit(node.condition), "la condición del for")
        if node.update is not None:
            self.visit(node.update)
        self.visit(node.body)

    def visit_foreach_statement(self, node: ast.ForeachStatement) -> None:
        iterable_type = self.visit(node.iterable)
        if iterable_type.kind is TypeKind.ARRAY:
            element_type = iterable_type.element_type or UNKNOWN
        elif iterable_type.kind in (TypeKind.ERROR, TypeKind.UNKNOWN):
            element_type = UNKNOWN
        else:
            self._error(node, node.variable, f"«foreach» requiere una lista; se recibió {iterable_type}.")
            element_type = UNKNOWN
        symbol = self._symbol_for_name(node.body, node.variable)
        if symbol is not None:
            self._symbol_types[id(symbol)] = element_type
        self.visit(node.body)

    def visit_switch_statement(self, node: ast.SwitchStatement) -> None:
        switch_type = self.visit(node.expression)
        for case in node.cases:
            case_type = self.visit(case.value)
            if not self._comparable(switch_type, case_type):
                self._error(
                    case.value, "case",
                    f"El valor del case es de tipo {case_type} y no es comparable con {switch_type}.",
                )
            self._visit_statement_sequence(case.statements)
        self._visit_statement_sequence(node.default_statements)

    def visit_try_catch_statement(self, node: ast.TryCatchStatement) -> None:
        self.visit(node.try_block)
        self.visit(node.catch_block)

    def visit_return_statement(self, node: ast.ReturnStatement) -> None:
        if not self._return_type_stack:
            # symbol_table.py ya reportó "return fuera de una función".
            if node.value is not None:
                self.visit(node.value)
            return
        expected = self._return_type_stack[-1]
        if node.value is None:
            if expected.kind not in (TypeKind.VOID, TypeKind.UNKNOWN, TypeKind.ERROR):
                self._error(node, "return", f"La función debe devolver un valor de tipo {expected}.")
            return
        value_type = self.visit(node.value)
        if expected.kind is TypeKind.VOID:
            self._error(
                node, "return",
                "La función no declara tipo de retorno (se interpreta como procedimiento) "
                "y no debería devolver un valor.",
            )
            return
        if value_type.kind is TypeKind.ERROR or expected.kind in (TypeKind.UNKNOWN, TypeKind.ERROR):
            return
        if not self.is_assignable(expected, value_type):
            self._error(
                node, "return",
                f"El valor de retorno es de tipo {value_type} y no coincide con el tipo declarado {expected}.",
            )

    # print / expresión suelta 
    def visit_print_statement(self, node: ast.PrintStatement) -> None:
        self.visit(node.expression)

    def visit_expression_statement(self, node: ast.ExpressionStatement) -> None:
        self.visit(node.expression)

    #  expresiones: literales e identificadores 
    def visit_literal_expression(self, node: ast.LiteralExpression) -> Type:
        if node.literal_type == "string":
            return STRING
        if node.value is None:
            return NULL
        if isinstance(node.value, bool):
            return BOOLEAN
        if isinstance(node.value, int):
            return INTEGER
        return UNKNOWN

    def visit_identifier_expression(self, node: ast.IdentifierExpression) -> Type:
        scope = self.table.scope_of(node)
        found = scope.resolve(node.name) if scope is not None else None
        if found is None:
            return ERROR  # symbol_table.py ya reportó "no declarada"
        return self._type_of_symbol(found[0])

    def visit_this_expression(self, node: ast.ThisExpression) -> Type:
        scope = self.table.scope_of(node)
        class_scope = scope.enclosing_class() if scope is not None else None
        if class_scope is None:
            return ERROR  # symbol_table.py ya reportó "this fuera de una clase"
        return class_type(class_scope.name)

    def visit_grouping_expression(self, node: ast.GroupingExpression) -> Type:
        return self.visit(node.expression)

    def visit_error_expression(self, node: ast.ErrorExpression) -> Type:
        return ERROR

    #  listas 
    def visit_array_expression(self, node: ast.ArrayExpression) -> Type:
        element_types = [self.visit(element) for element in node.elements]
        if not element_types:
            return array_of(UNKNOWN)
        first = element_types[0]
        for position, element_type in enumerate(element_types[1:], start=2):
            if not self._comparable(first, element_type):
                self._error(
                    node, f"elemento {position}",
                    f"Los elementos de la lista deben ser del mismo tipo ({first}); se encontró {element_type}.",
                )
        return array_of(first)

    def visit_index_expression(self, node: ast.IndexExpression) -> Type:
        collection_type = self.visit(node.collection)
        index_type = self.visit(node.index)
        if index_type.kind not in (TypeKind.INTEGER, TypeKind.ERROR, TypeKind.UNKNOWN):
            self._error(node, "índice", f"El índice de una lista debe ser de tipo integer, no {index_type}.")
        if collection_type.kind is TypeKind.ERROR:
            return ERROR
        if collection_type.kind in (TypeKind.UNKNOWN,):
            return UNKNOWN
        if collection_type.kind is not TypeKind.ARRAY:
            self._error(node, "[]", f"No se puede indexar un valor de tipo {collection_type} porque no es una lista.")
            return ERROR
        return collection_type.element_type or UNKNOWN

    # clases: atributos y métodos 
    def _find_class_member(self, class_name: str, member_name: str) -> Symbol | None:
        class_symbol = self.table.find_class(class_name)
        if class_symbol is None:
            return None
        return self.table.class_members(class_symbol).get(member_name)

    def visit_member_expression(self, node: ast.MemberExpression) -> Type:
        object_type = self.visit(node.object)
        if object_type.kind is TypeKind.ERROR:
            return ERROR
        if object_type.kind in (TypeKind.UNKNOWN,):
            return UNKNOWN
        if object_type.kind is not TypeKind.CLASS or object_type.class_name is None:
            self._error(
                node, node.member,
                f"No se puede acceder a «.{node.member}» porque el valor no es una instancia de una "
                f"clase (tipo actual: {object_type}).",
            )
            return ERROR
        member_symbol = self._find_class_member(object_type.class_name, node.member)
        if member_symbol is None:
            self._error(
                node, node.member,
                f"La clase «{object_type.class_name}» no tiene un atributo o método llamado «{node.member}».",
            )
            return ERROR
        return self._type_of_symbol(member_symbol)

    def visit_new_expression(self, node: ast.NewExpression) -> Type:
        argument_types = [self.visit(argument) for argument in node.arguments]
        class_symbol = self.table.find_class(node.class_name)
        if class_symbol is None:
            return ERROR  # symbol_table.py ya reportó "clase no declarada"
        constructor = self._find_class_member(node.class_name, "constructor")
        if constructor is not None:
            self._check_call(node, constructor, argument_types)
        elif argument_types:
            self._error(
                node, node.class_name,
                f"La clase «{node.class_name}» no define un constructor pero se le pasaron argumentos.",
            )
        return class_type(node.class_name)

    # llamadas y argumentos 
    def _check_call(self, node: ast.AstNode, symbol: Symbol, argument_types: list[Type]) -> Type:
        expected: tuple[ParameterInfo, ...] = symbol.parameters
        if len(argument_types) != len(expected):
            self._error(
                node, symbol.name,
                f"«{symbol.name}» espera {len(expected)} argumento(s) pero recibió {len(argument_types)}.",
            )
        else:
            for index, (parameter, argument_type) in enumerate(zip(expected, argument_types), start=1):
                expected_type = self._type_from_name(parameter.type_name)
                if expected_type.kind is TypeKind.UNKNOWN:
                    continue  # parámetro sin anotación: no se valida el tipo
                if not self.is_assignable(expected_type, argument_type):
                    self._error(
                        node, symbol.name,
                        (
                            f"El argumento {index} de «{symbol.name}» debe ser de tipo {expected_type}, "
                            f"pero se recibió {argument_type}."
                        ),
                    )
        return self._type_from_name(symbol.return_type, none_means_void=True)

    def _resolve_callee(self, callee: ast.Expression) -> tuple[Symbol | None, Type]:
        if isinstance(callee, ast.IdentifierExpression):
            scope = self.table.scope_of(callee)
            found = scope.resolve(callee.name) if scope is not None else None
            if found is None:
                return None, ERROR  # symbol_table.py ya reportó "no declarada"
            symbol, _owner = found
            if symbol.category is not SymbolCategory.FUNCTION:
                return None, self._type_of_symbol(symbol)
            return symbol, FUNCTION
        if isinstance(callee, ast.MemberExpression):
            object_type = self.visit(callee.object)
            if object_type.kind in (TypeKind.ERROR, TypeKind.UNKNOWN):
                return None, object_type
            if object_type.kind is not TypeKind.CLASS or object_type.class_name is None:
                self._error(
                    callee, callee.member,
                    f"No se puede acceder a «.{callee.member}» porque el valor no es una instancia de "
                    f"una clase (tipo actual: {object_type}).",
                )
                return None, ERROR
            member_symbol = self._find_class_member(object_type.class_name, callee.member)
            if member_symbol is None:
                self._error(
                    callee, callee.member,
                    f"La clase «{object_type.class_name}» no tiene un método llamado «{callee.member}».",
                )
                return None, ERROR
            if member_symbol.category is not SymbolCategory.FUNCTION:
                return None, self._type_of_symbol(member_symbol)
            return member_symbol, FUNCTION
        return None, self.visit(callee)

    def visit_call_expression(self, node: ast.CallExpression) -> Type:
        argument_types = [self.visit(argument) for argument in node.arguments]
        callee_symbol, callee_type = self._resolve_callee(node.callee)
        if callee_symbol is None:
            if callee_type.kind not in (TypeKind.ERROR, TypeKind.UNKNOWN):
                self._error(
                    node, self._describe(node.callee),
                    f"El valor no es invocable (tipo {callee_type}); no es una función ni un método.",
                )
            return ERROR
        return self._check_call(node, callee_symbol, argument_types)

    #  asignaciones 
    def _resolve_assignment_target_type(self, target: ast.Expression) -> Type | None:
        if isinstance(target, ast.IdentifierExpression):
            scope = self.table.scope_of(target)
            found = scope.resolve(target.name) if scope is not None else None
            if found is None:
                return None
            return self._type_of_symbol(found[0])
        return self.visit(target)

    def visit_assignment_expression(self, node: ast.AssignmentExpression) -> Type:
        value_type = self.visit(node.value)
        target_type = self._resolve_assignment_target_type(node.target)
        if target_type is not None and target_type.kind is not TypeKind.ERROR and value_type.kind is not TypeKind.ERROR:
            if not self.is_assignable(target_type, value_type):
                self._error(
                    node.target, self._describe(node.target),
                    f"No se puede asignar un valor de tipo {value_type} a algo de tipo {target_type}.",
                )
        return target_type or value_type

    #  operadores 
    def visit_conditional_expression(self, node: ast.ConditionalExpression) -> Type:
        condition_type = self.visit(node.condition)
        self._expect_boolean(node.condition, condition_type, "la condición del operador ternario")
        when_true = self.visit(node.when_true)
        when_false = self.visit(node.when_false)
        if when_true.kind is TypeKind.ERROR or when_false.kind is TypeKind.ERROR:
            return ERROR
        if self._comparable(when_true, when_false):
            return when_true if when_true.kind is not TypeKind.UNKNOWN else when_false
        self._error(
            node, "?:",
            f"Las dos ramas del operador ternario deben ser del mismo tipo ({when_true} vs {when_false}).",
        )
        return ERROR

    def visit_unary_expression(self, node: ast.UnaryExpression) -> Type:
        operand = self.visit(node.operand)
        if operand.kind is TypeKind.ERROR:
            return ERROR
        if node.operator == "!":
            if operand.kind in (TypeKind.BOOLEAN, TypeKind.UNKNOWN):
                return BOOLEAN
            self._error(node, "!", f"El operador «!» requiere un operando boolean; se recibió {operand}.")
            return ERROR
        if node.operator == "-":
            if operand.kind in (TypeKind.INTEGER, TypeKind.UNKNOWN):
                return INTEGER
            self._error(node, "-", f"El operador unario «-» requiere un operando integer; se recibió {operand}.")
            return ERROR
        return UNKNOWN

    def visit_binary_expression(self, node: ast.BinaryExpression) -> Type:
        left = self.visit(node.left)
        right = self.visit(node.right)
        operator = node.operator

        if left.kind is TypeKind.ERROR or right.kind is TypeKind.ERROR:
            return ERROR
        if left.kind is TypeKind.UNKNOWN or right.kind is TypeKind.UNKNOWN:
            return UNKNOWN

        if operator == "+":
            if left.kind is TypeKind.STRING and right.kind is TypeKind.STRING:
                return STRING
            if left.kind is TypeKind.INTEGER and right.kind is TypeKind.INTEGER:
                return INTEGER
            self._error(
                node, operator,
                f"El operador «+» requiere dos operandos integer o dos operandos string; "
                f"se recibió {left} y {right}.",
            )
            return ERROR

        if operator in self._ARITHMETIC_OPERATORS:
            if left.kind is TypeKind.INTEGER and right.kind is TypeKind.INTEGER:
                return INTEGER
            self._error(
                node, operator,
                f"El operador «{operator}» requiere dos operandos integer; se recibió {left} y {right}.",
            )
            return ERROR

        if operator in self._LOGICAL_OPERATORS:
            if left.kind is TypeKind.BOOLEAN and right.kind is TypeKind.BOOLEAN:
                return BOOLEAN
            self._error(
                node, operator,
                f"El operador «{operator}» requiere dos operandos boolean; se recibió {left} y {right}.",
            )
            return ERROR

        if operator in self._EQUALITY_OPERATORS:
            if self._comparable(left, right):
                return BOOLEAN
            self._error(node, operator, f"No se puede comparar {left} con {right} usando «{operator}».")
            return ERROR

        if operator in self._RELATIONAL_OPERATORS:
            if left.kind is TypeKind.INTEGER and right.kind is TypeKind.INTEGER:
                return BOOLEAN
            self._error(
                node, operator,
                f"El operador «{operator}» requiere dos operandos integer; se recibió {left} y {right}.",
            )
            return ERROR

        return UNKNOWN


def analyze_semantics(table: SymbolTable, program: ast.Program | None) -> list[Diagnostic]:
    """Punto de integración equivalente a ``build_symbol_table``: recibe la
    tabla ya construida y el MISMO ``Program`` a partir del cual se
    construyó, y devuelve los diagnósticos semánticos de tipos/flujo."""
    if program is None:
        return []
    return SemanticAnalyzer(table).analyze(program)
