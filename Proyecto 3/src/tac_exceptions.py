"""Traducción de ``try/catch`` al TAC compartido.

Compiscript no tiene ``throw``: las excepciones son errores de ejecución
(índice fuera de rango, división entre cero, acceso a ``null``...). Se
modelan con una pila de manejadores::

    try_begin L1        instala un manejador que salta a L1
    ...                 cuerpo del try
    try_end             retira el manejador (salida normal)
    goto L2
    L1:                 al ocurrir un error, el entorno de ejecución retira
    err = exception     el manejador, salta aquí y entrega el mensaje
    ...                 cuerpo del catch
    L2:

Si el error ocurre dentro de una función llamada desde el ``try``, se
descartan los registros de activación hasta llegar al que instaló el
manejador. Un ``break``, ``continue`` o ``return`` que sale de uno o más
``try`` emite antes un ``try_end`` por cada manejador que abandona, para que
la pila de manejadores nunca quede con entradas de un bloque ya cerrado.
"""

from __future__ import annotations

from contextlib import contextmanager

import ast_nodes as ast
from tac import TACOp


class ExceptionMixin:
    def _init_exceptions(self) -> None:
        self._handler_depth = 0
        # Profundidad de manejadores al abrir cada contexto de break/continue
        # (paralela a _control_stack de ControlFlowMixin).
        self._handler_marks: list[int] = []

    @contextmanager
    def control_context(self, end, advance=None):
        self._handler_marks.append(self._handler_depth)
        try:
            with super().control_context(end, advance):
                yield
        finally:
            self._handler_marks.pop()

    def close_handlers(self, count: int) -> None:
        for _ in range(count):
            self.emit(TACOp.TRY_END)

    def visit_break_statement(self, node: ast.BreakStatement) -> None:
        if self._control_stack:
            self.close_handlers(self._handler_depth - self._handler_marks[-1])
        super().visit_break_statement(node)

    def visit_continue_statement(self, node: ast.ContinueStatement) -> None:
        for position in range(len(self._control_stack) - 1, -1, -1):
            if self._control_stack[position].continue_label is not None:
                self.close_handlers(self._handler_depth - self._handler_marks[position])
                break
        super().visit_continue_statement(node)

    def visit_try_catch_statement(self, node: ast.TryCatchStatement) -> None:
        handler, end = self.new_label(), self.new_label()
        self.emit(TACOp.TRY_BEGIN, handler)
        self._handler_depth += 1
        try:
            self.generate_statement(node.try_block)
        finally:
            self._handler_depth -= 1
        self.emit(TACOp.TRY_END)
        self.emit(TACOp.GOTO, end)
        self.emit(TACOp.LABEL, handler)
        self.emit(TACOp.GET_EXCEPTION, self.variable(node.catch_block, node.error_name))
        self.generate_statements(node.catch_block.statements)
        self.emit(TACOp.LABEL, end)
