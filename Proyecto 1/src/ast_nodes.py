"""Nodos inmutables del AST de Compiscript.

El AST es deliberadamente independiente de ANTLR. Las siguientes fases pueden
trabajar con estas clases aunque la gramática o el generador del parser cambien.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from ast_visitor import AstVisitor


@dataclass(frozen=True, slots=True)
class SourceSpan:
    line: int
    column: int
    end_line: int
    end_column: int

    @classmethod
    def unknown(cls) -> SourceSpan:
        return cls(1, 1, 1, 1)

    @classmethod
    def merge(cls, first: SourceSpan, last: SourceSpan) -> SourceSpan:
        return cls(first.line, first.column, last.end_line, last.end_column)


@dataclass(frozen=True, slots=True, kw_only=True)
class AstNode:
    span: SourceSpan

    def accept(self, visitor: AstVisitor):
        return visitor.visit(self)


@dataclass(frozen=True, slots=True, kw_only=True)
class TypeRef(AstNode):
    name: str
    dimensions: int = 0

    def __str__(self) -> str:
        return self.name + "[]" * self.dimensions


@dataclass(frozen=True, slots=True, kw_only=True)
class Statement(AstNode):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class Expression(AstNode):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class Program(AstNode):
    statements: tuple[Statement, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Block(Statement):
    statements: tuple[Statement, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class VariableDeclaration(Statement):
    declaration_kind: str
    name: str
    type_annotation: TypeRef | None
    initializer: Expression | None


@dataclass(frozen=True, slots=True, kw_only=True)
class ConstantDeclaration(Statement):
    name: str
    type_annotation: TypeRef | None
    initializer: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class Parameter(AstNode):
    name: str
    type_annotation: TypeRef | None


@dataclass(frozen=True, slots=True, kw_only=True)
class FunctionDeclaration(Statement):
    name: str
    parameters: tuple[Parameter, ...]
    return_type: TypeRef | None
    body: Block


@dataclass(frozen=True, slots=True, kw_only=True)
class ClassDeclaration(Statement):
    name: str
    superclass: str | None
    members: tuple[Statement, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpressionStatement(Statement):
    expression: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class PrintStatement(Statement):
    expression: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class IfStatement(Statement):
    condition: Expression
    then_branch: Statement
    else_branch: Statement | None


@dataclass(frozen=True, slots=True, kw_only=True)
class WhileStatement(Statement):
    condition: Expression
    body: Statement


@dataclass(frozen=True, slots=True, kw_only=True)
class DoWhileStatement(Statement):
    body: Statement
    condition: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class ForStatement(Statement):
    initializer: VariableDeclaration | Expression | None
    condition: Expression | None
    update: Expression | None
    body: Statement


@dataclass(frozen=True, slots=True, kw_only=True)
class ForeachStatement(Statement):
    variable: str
    iterable: Expression
    body: Statement


@dataclass(frozen=True, slots=True, kw_only=True)
class BreakStatement(Statement):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ContinueStatement(Statement):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class ReturnStatement(Statement):
    value: Expression | None


@dataclass(frozen=True, slots=True, kw_only=True)
class TryCatchStatement(Statement):
    try_block: Block
    error_name: str
    catch_block: Block


@dataclass(frozen=True, slots=True, kw_only=True)
class SwitchCase(AstNode):
    value: Expression
    statements: tuple[Statement, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class SwitchStatement(Statement):
    expression: Expression
    cases: tuple[SwitchCase, ...]
    default_statements: tuple[Statement, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class IdentifierExpression(Expression):
    name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class LiteralExpression(Expression):
    value: int | str | bool | None
    literal_type: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ArrayExpression(Expression):
    elements: tuple[Expression, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ThisExpression(Expression):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class NewExpression(Expression):
    class_name: str
    arguments: tuple[Expression, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class GroupingExpression(Expression):
    expression: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class UnaryExpression(Expression):
    operator: str
    operand: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class BinaryExpression(Expression):
    left: Expression
    operator: str
    right: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class ConditionalExpression(Expression):
    condition: Expression
    when_true: Expression
    when_false: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class AssignmentExpression(Expression):
    target: Expression
    value: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class CallExpression(Expression):
    callee: Expression
    arguments: tuple[Expression, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class IndexExpression(Expression):
    collection: Expression
    index: Expression


@dataclass(frozen=True, slots=True, kw_only=True)
class MemberExpression(Expression):
    object: Expression
    member: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ErrorExpression(Expression):
    """Marcador recuperable para una expresión sintácticamente incompleta."""

    description: str


def iter_child_nodes(node: AstNode) -> Iterator[AstNode]:
    """Recorre hijos directos sin acoplar Visitors a cada dataclass."""

    for field_info in fields(node):
        if field_info.name == "span":
            continue
        value = getattr(node, field_info.name)
        if isinstance(value, AstNode):
            yield value
        elif isinstance(value, tuple):
            yield from (item for item in value if isinstance(item, AstNode))

