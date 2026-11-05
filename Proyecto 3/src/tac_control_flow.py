"""Traducción de condiciones y estructuras de control al TAC compartido.

Las etiquetas pertenecen a una generación completa. Los contextos se apilan
para distinguir el destino de break del destino de continue, incluso cuando
un switch está dentro de un ciclo. No ejecuta el programa fuente.
"""

from contextlib import contextmanager
from dataclasses import dataclass

import ast_nodes as ast
from tac import Const, Label, TACOp, Temp, Var


@dataclass(frozen=True)
class ControlContext:
    break_label: Label
    continue_label: Label | None = None


class ControlFlowMixin:
    def _init_control_flow(self):
        self._next_label = 1
        self._control_stack: list[ControlContext] = []

    def new_label(self) -> Label:
        label = Label(f"L{self._next_label}")
        self._next_label += 1
        return label

    @contextmanager
    def control_context(self, end, advance=None):
        self._control_stack.append(ControlContext(end, advance))
        try:
            yield
        finally:
            self._control_stack.pop()

    def generate_condition(self, node, when_true, when_false):
        """Emite saltos; consume y libera únicamente el valor de condición."""
        if isinstance(node, ast.GroupingExpression):
            return self.generate_condition(node.expression, when_true, when_false)
        if isinstance(node, ast.UnaryExpression) and node.operator == "!":
            return self.generate_condition(node.operand, when_false, when_true)
        if isinstance(node, ast.BinaryExpression) and node.operator in {"&&", "||"}:
            right_label = self.new_label()
            if node.operator == "&&":
                self.generate_condition(node.left, right_label, when_false)
            else:
                self.generate_condition(node.left, when_true, right_label)
            self.emit(TACOp.LABEL, right_label)
            self.generate_condition(node.right, when_true, when_false)
            return
        value = self.visit(node)
        self.emit(TACOp.IF_TRUE, when_true, value)
        self.emit(TACOp.GOTO, when_false)
        self.temps.release(value)

    def generate_logical_value(self, node) -> Temp:
        result = self.temps.new()
        yes, no, end = self.new_label(), self.new_label(), self.new_label()
        self.generate_condition(node, yes, no)
        self.emit(TACOp.LABEL, yes)
        self.emit(TACOp.ASSIGN, result, Const(True, "boolean"))
        self.emit(TACOp.GOTO, end)
        self.emit(TACOp.LABEL, no)
        self.emit(TACOp.ASSIGN, result, Const(False, "boolean"))
        self.emit(TACOp.LABEL, end)
        return result

    def visit_conditional_expression(self, node):
        result = self.temps.new()
        yes, no, end = self.new_label(), self.new_label(), self.new_label()
        self.generate_condition(node.condition, yes, no)
        self.emit(TACOp.LABEL, yes)
        value = self.visit(node.when_true)
        self.emit(TACOp.ASSIGN, result, value)
        self.temps.release(value)
        self.emit(TACOp.GOTO, end)
        self.emit(TACOp.LABEL, no)
        value = self.visit(node.when_false)
        self.emit(TACOp.ASSIGN, result, value)
        self.temps.release(value)
        self.emit(TACOp.LABEL, end)
        return result

    def visit_if_statement(self, node):
        yes, no = self.new_label(), self.new_label()
        end = self.new_label() if node.else_branch is not None else no
        self.generate_condition(node.condition, yes, no)
        self.emit(TACOp.LABEL, yes)
        self.generate_statement(node.then_branch)
        if node.else_branch is not None:
            self.emit(TACOp.GOTO, end)
        self.emit(TACOp.LABEL, no)
        if node.else_branch is not None:
            self.generate_statement(node.else_branch)
            self.emit(TACOp.LABEL, end)

    def visit_while_statement(self, node):
        test, body, end = self.new_label(), self.new_label(), self.new_label()
        self.emit(TACOp.LABEL, test)
        self.generate_condition(node.condition, body, end)
        self.emit(TACOp.LABEL, body)
        with self.control_context(end, test):
            self.generate_statement(node.body)
        self.emit(TACOp.GOTO, test)
        self.emit(TACOp.LABEL, end)

    def visit_do_while_statement(self, node):
        body, test, end = self.new_label(), self.new_label(), self.new_label()
        self.emit(TACOp.LABEL, body)
        with self.control_context(end, test):
            self.generate_statement(node.body)
        self.emit(TACOp.LABEL, test)
        self.generate_condition(node.condition, body, end)
        self.emit(TACOp.LABEL, end)

    def visit_for_statement(self, node):
        if isinstance(node.initializer, ast.VariableDeclaration):
            self.generate_statement(node.initializer)
        elif node.initializer is not None:
            self.temps.release(self.visit(node.initializer))
        test, body, advance, end = (self.new_label() for _ in range(4))
        self.emit(TACOp.LABEL, test)
        if node.condition is not None:
            self.generate_condition(node.condition, body, end)
        self.emit(TACOp.LABEL, body)
        with self.control_context(end, advance):
            self.generate_statement(node.body)
        self.emit(TACOp.LABEL, advance)
        if node.update is not None:
            self.temps.release(self.visit(node.update))
        self.emit(TACOp.GOTO, test)
        self.emit(TACOp.LABEL, end)

    def _snapshot(self, value):
        # Una variable puede reasignarse en el cuerpo o en un case; conservar
        # el valor evaluado antes de entrar en la estructura.
        if isinstance(value, Var):
            snapshot = self.temps.new()
            self.emit(TACOp.ASSIGN, snapshot, value)
            return snapshot
        return value

    def visit_foreach_statement(self, node):
        collection = self._snapshot(self.visit(node.iterable))
        index, length = self.temps.new(), self.temps.new()
        self.emit(TACOp.ASSIGN, index, Const(0, "integer"))
        self.emit(TACOp.LENGTH, length, collection)
        test, advance, end = (self.new_label() for _ in range(3))
        self.emit(TACOp.LABEL, test)
        condition = self.temps.new()
        self.emit(TACOp.LT, condition, index, length)
        self.emit(TACOp.IF_FALSE, end, condition)
        self.temps.release(condition)
        self.emit(TACOp.INDEX_LOAD, self.variable(node.body, node.variable), collection, index)
        with self.control_context(end, advance):
            self.generate_statement(node.body)
        self.emit(TACOp.LABEL, advance)
        self.emit(TACOp.ADD, index, index, Const(1, "integer"))
        self.emit(TACOp.GOTO, test)
        self.emit(TACOp.LABEL, end)
        for value in (collection, index, length):
            self.temps.release(value)

    def visit_switch_statement(self, node):
        selector = self._snapshot(self.visit(node.expression))
        labels = [self.new_label() for _ in node.cases]
        default, end = self.new_label(), self.new_label()
        # Se prueban los casos en orden; el primer acierto salta directamente
        # al cuerpo. Los cuerpos conservan fall-through hasta encontrar break.
        for case, label in zip(node.cases, labels):
            value = self.visit(case.value)
            match = self.temps.new()
            self.emit(TACOp.EQ, match, selector, value)
            self.temps.release(value)
            self.emit(TACOp.IF_TRUE, label, match)
            self.temps.release(match)
        self.emit(TACOp.GOTO, default)
        self.temps.release(selector)
        with self.control_context(end):
            for case, label in zip(node.cases, labels):
                self.emit(TACOp.LABEL, label)
                self.generate_statements(case.statements)
            self.emit(TACOp.LABEL, default)
            self.generate_statements(node.default_statements)
        self.emit(TACOp.LABEL, end)

    def visit_break_statement(self, node):
        if not self._control_stack:
            from tac_generator import TACGenerationError
            raise TACGenerationError(node, "«break» requiere un ciclo o switch.")
        self.emit(TACOp.GOTO, self._control_stack[-1].break_label)

    def visit_continue_statement(self, node):
        for context in reversed(self._control_stack):
            if context.continue_label is not None:
                self.emit(TACOp.GOTO, context.continue_label)
                return
        from tac_generator import TACGenerationError
        raise TACGenerationError(node, "«continue» requiere un ciclo.")
