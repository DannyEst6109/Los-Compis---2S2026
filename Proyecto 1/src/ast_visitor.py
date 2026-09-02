"""Visitor extensible para el AST de Compiscript."""

from __future__ import annotations

import re
from typing import Generic, TypeVar

from ast_nodes import AstNode, iter_child_nodes


ResultT = TypeVar("ResultT")


def _snake_case(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


class AstVisitor(Generic[ResultT]):
    """Despacho por nombre con recorrido genérico como comportamiento base.

    Una fase puede implementar, por ejemplo, ``visit_variable_declaration`` y
    heredar el recorrido del resto de los nodos. Esto permite que la tabla de
    símbolos y el analizador semántico sean Visitors separados.
    """

    def visit(self, node: AstNode) -> ResultT:
        for node_type in type(node).__mro__:
            if not issubclass(node_type, AstNode):
                continue
            method = getattr(self, f"visit_{_snake_case(node_type.__name__)}", None)
            if method is not None:
                return method(node)
        return self.generic_visit(node)

    def generic_visit(self, node: AstNode) -> ResultT:
        result = None
        for child in iter_child_nodes(node):
            result = self.visit(child)
        return result  # type: ignore[return-value]
