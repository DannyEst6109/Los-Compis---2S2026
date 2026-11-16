"""Salidas posibles de una instrucción, para validar retornos completos.

Los saltos se consumen en su ciclo o switch, sin confundir un return de
una función anidada con el de la función que la declara. El análisis es
conservador con condiciones no constantes y posibles excepciones.
"""

import ast_nodes as ast

NEXT = "siguiente"
RETURN = "return"
BREAK = "break"
CONTINUE = "continue"


def sequence_exits(statements) -> set[str]:
    exits = {NEXT}
    for statement in statements:
        if NEXT not in exits:
            break
        exits = (exits - {NEXT}) | statement_exits(statement)
    return exits


def boolean_constant(expression) -> bool | None:
    if isinstance(expression, ast.GroupingExpression):
        return boolean_constant(expression.expression)
    if isinstance(expression, ast.LiteralExpression) and expression.literal_type == "boolean":
        return expression.value
    if isinstance(expression, ast.UnaryExpression) and expression.operator == "!":
        value = boolean_constant(expression.operand)
        return None if value is None else not value
    return None


def _loop_exits(body, condition, *, executes_once=False) -> set[str]:
    truth = boolean_constant(condition) if condition is not None else True
    if truth is False and not executes_once:
        return {NEXT}
    exits = statement_exits(body)
    result = exits & {RETURN}
    if BREAK in exits or (not executes_once and truth is not True):
        result.add(NEXT)
    if truth is not True and exits & {NEXT, CONTINUE}:
        result.add(NEXT)
    return result


def statement_exits(statement) -> set[str]:
    if isinstance(statement, ast.ReturnStatement):
        return {RETURN}
    if isinstance(statement, ast.BreakStatement):
        return {BREAK}
    if isinstance(statement, ast.ContinueStatement):
        return {CONTINUE}
    if isinstance(statement, ast.Block):
        return sequence_exits(statement.statements)
    if isinstance(statement, ast.IfStatement):
        truth = boolean_constant(statement.condition)
        yes = statement_exits(statement.then_branch)
        no = statement_exits(statement.else_branch) if statement.else_branch is not None else {NEXT}
        return yes if truth is True else no if truth is False else yes | no
    if isinstance(statement, ast.WhileStatement):
        return _loop_exits(statement.body, statement.condition)
    if isinstance(statement, ast.DoWhileStatement):
        return _loop_exits(statement.body, statement.condition, executes_once=True)
    if isinstance(statement, ast.ForStatement):
        return _loop_exits(statement.body, statement.condition)
    if isinstance(statement, ast.ForeachStatement):
        # El arreglo podría estar vacío.
        return {NEXT} | (statement_exits(statement.body) & {RETURN})
    if isinstance(statement, ast.TryCatchStatement):
        return statement_exits(statement.try_block) | statement_exits(statement.catch_block)
    if isinstance(statement, ast.SwitchStatement):
        # Cada case es un punto de entrada y puede caer al siguiente.
        suffix = sequence_exits(statement.default_statements)
        exits = set(suffix)
        for case in reversed(statement.cases):
            current = sequence_exits(case.statements)
            suffix = (current - {NEXT}) | (suffix if NEXT in current else set())
            exits |= suffix
        return (exits - {BREAK}) | ({NEXT} if BREAK in exits else set())
    return {NEXT}
