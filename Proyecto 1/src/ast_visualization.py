"""Modelo presentable y agnóstico de UI para visualizar el AST."""

from __future__ import annotations

from dataclasses import dataclass, fields

import ast_nodes as ast


@dataclass(frozen=True, slots=True)
class VisualAstNode:
    label: str
    detail: str = ""
    ast_node: ast.AstNode | None = None
    children: tuple[VisualAstNode, ...] = ()

    @property
    def location(self) -> str:
        if self.ast_node is None:
            return ""
        return f"{self.ast_node.span.line}:{self.ast_node.span.column}"


NODE_LABELS = {
    "Program": "Programa",
    "Block": "Bloque",
    "VariableDeclaration": "Declaración de variable",
    "ConstantDeclaration": "Declaración de constante",
    "Parameter": "Parámetro",
    "FunctionDeclaration": "Función",
    "ClassDeclaration": "Clase",
    "ExpressionStatement": "Expresión",
    "PrintStatement": "Impresión",
    "IfStatement": "Condicional if",
    "WhileStatement": "Ciclo while",
    "DoWhileStatement": "Ciclo do-while",
    "ForStatement": "Ciclo for",
    "ForeachStatement": "Ciclo foreach",
    "BreakStatement": "break",
    "ContinueStatement": "continue",
    "ReturnStatement": "return",
    "TryCatchStatement": "Manejo try-catch",
    "SwitchStatement": "Selección switch",
    "SwitchCase": "Caso",
    "TypeRef": "Tipo",
    "IdentifierExpression": "Identificador",
    "LiteralExpression": "Literal",
    "ArrayExpression": "Lista",
    "ThisExpression": "Referencia this",
    "NewExpression": "Instanciación",
    "GroupingExpression": "Agrupación",
    "UnaryExpression": "Operación unaria",
    "BinaryExpression": "Operación binaria",
    "ConditionalExpression": "Expresión ternaria",
    "AssignmentExpression": "Asignación",
    "CallExpression": "Llamada",
    "IndexExpression": "Acceso por índice",
    "MemberExpression": "Acceso a miembro",
    "ErrorExpression": "Nodo recuperado",
}

ROLE_LABELS = {
    "statements": "Instrucciones",
    "type_annotation": "Tipo declarado",
    "initializer": "Inicializador",
    "parameters": "Parámetros",
    "return_type": "Tipo de retorno",
    "body": "Cuerpo",
    "condition": "Condición",
    "then_branch": "Rama verdadera",
    "else_branch": "Rama alternativa",
    "update": "Actualización",
    "iterable": "Colección",
    "value": "Valor",
    "try_block": "Bloque try",
    "catch_block": "Bloque catch",
    "expression": "Expresión",
    "cases": "Casos",
    "default_statements": "Caso default",
    "elements": "Elementos",
    "operand": "Operando",
    "left": "Operando izquierdo",
    "right": "Operando derecho",
    "when_true": "Resultado verdadero",
    "when_false": "Resultado falso",
    "target": "Destino",
    "callee": "Invocable",
    "arguments": "Argumentos",
    "collection": "Colección",
    "index": "Índice",
    "object": "Objeto",
    "members": "Miembros",
}


def _detail(node: ast.AstNode) -> str:
    if isinstance(node, ast.Program):
        return f"{len(node.statements)} instrucciones"
    if isinstance(node, ast.Block):
        return f"{len(node.statements)} instrucciones"
    if isinstance(node, ast.TypeRef):
        return str(node)
    if isinstance(node, ast.VariableDeclaration):
        annotation = f": {node.type_annotation}" if node.type_annotation else ""
        return f"{node.declaration_kind} {node.name}{annotation}"
    if isinstance(node, ast.ConstantDeclaration):
        annotation = f": {node.type_annotation}" if node.type_annotation else ""
        return f"const {node.name}{annotation}"
    if isinstance(node, ast.Parameter):
        return f"{node.name}: {node.type_annotation}" if node.type_annotation else node.name
    if isinstance(node, ast.FunctionDeclaration):
        return f"{node.name}({len(node.parameters)} parámetros)"
    if isinstance(node, ast.ClassDeclaration):
        return f"{node.name} : {node.superclass}" if node.superclass else node.name
    if isinstance(node, ast.ForeachStatement):
        return node.variable
    if isinstance(node, ast.TryCatchStatement):
        return f"catch ({node.error_name})"
    if isinstance(node, ast.IdentifierExpression):
        return node.name
    if isinstance(node, ast.LiteralExpression):
        if node.literal_type == "string":
            return repr(node.value)
        if node.value is None:
            return "null"
        if isinstance(node.value, bool):
            return str(node.value).lower()
        return str(node.value)
    if isinstance(node, ast.ArrayExpression):
        return f"{len(node.elements)} elementos"
    if isinstance(node, ast.NewExpression):
        return f"new {node.class_name}({len(node.arguments)} argumentos)"
    if isinstance(node, ast.UnaryExpression):
        return node.operator
    if isinstance(node, ast.BinaryExpression):
        return node.operator
    if isinstance(node, ast.MemberExpression):
        return f".{node.member}"
    if isinstance(node, ast.CallExpression):
        return f"{len(node.arguments)} argumentos"
    if isinstance(node, ast.ErrorExpression):
        return node.description
    return ""


def build_visual_tree(node: ast.AstNode) -> VisualAstNode:
    """Convierte un nodo AST en un árbol etiquetado para cualquier interfaz."""

    children: list[VisualAstNode] = []
    flatten_fields = {"statements", "members"}

    for field_info in fields(node):
        if field_info.name == "span":
            continue
        value = getattr(node, field_info.name)
        role = ROLE_LABELS.get(field_info.name, field_info.name.replace("_", " ").capitalize())

        if isinstance(value, ast.AstNode):
            rendered = build_visual_tree(value)
            children.append(VisualAstNode(role, ast_node=None, children=(rendered,)))
        elif isinstance(value, tuple):
            rendered_items = tuple(build_visual_tree(item) for item in value if isinstance(item, ast.AstNode))
            if not rendered_items:
                continue
            if field_info.name in flatten_fields:
                children.extend(rendered_items)
            else:
                children.append(
                    VisualAstNode(role, f"{len(rendered_items)} elementos", ast_node=None, children=rendered_items)
                )

    return VisualAstNode(
        label=NODE_LABELS.get(type(node).__name__, type(node).__name__),
        detail=_detail(node),
        ast_node=node,
        children=tuple(children),
    )
