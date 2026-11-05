"""Traducción de funciones, llamadas y ``return`` al TAC compartido.

Cada función (y cada método, constructor o inicializador de atributos) es
una unidad de generación independiente:

* Se traduce en su propio búfer de instrucciones, con su propio
  ``TempAllocator`` (sus temporales viven en su registro de activación, así
  una llamada recursiva no pisa los de la activación anterior) y con las
  pilas de ``break``/``continue`` y de manejadores de excepciones vacías.
* Al terminar se envuelve con ``begin_func <etiqueta>, <tamaño del
  registro>`` y ``end_func <etiqueta>``, y se guarda como una sección.
* ``generate`` coloca todas las secciones antes del código global. Así las
  funciones anidadas no quedan intercaladas con el cuerpo que las contiene.

Primero se evalúan
todos los argumentos de izquierda a derecha, después se emite un ``param``
por argumento y finalmente ``call f, n``. Los métodos reciben el objeto
(``this``) como primer parámetro implícito.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import ast_nodes as ast
from symbol_table import ActivationRecord, ScopeKind, Symbol, SymbolCategory
from tac import Const, Name, Operand, TACInstruction, TACOp, TACProgram


@dataclass(frozen=True)
class FunctionContext:
    """Unidad que se está traduciendo. ``class_symbol`` es la clase dueña de
    ``this`` en métodos, constructores e inicializadores."""

    label: str
    record: ActivationRecord | None
    class_symbol: Symbol | None = None


class FunctionMixin:
    def _init_functions(self) -> None:
        self._sections: list[list[TACInstruction] | None] = []
        self._function: FunctionContext | None = None
        # (etiqueta, asignador) de cada unidad traducida; el IDE muestra
        # estas estadísticas de reciclaje de temporales.
        self.unit_temps: list[tuple[str, object]] = []

    # -- unidades de generación 
    def generate_unit(
        self,
        label: str,
        record: ActivationRecord | None,
        class_symbol: Symbol | None,
        node: ast.AstNode,
        body: Callable[[], None],
    ) -> None:
        """Traduce ``body`` como una función aparte y la agrega como sección.

        Todo el estado propio de una activación se guarda, se reinicia y se
        restaura al salir, incluso si la traducción falla."""
        position = len(self._sections)
        self._sections.append(None)  # reserva el lugar: externas antes que anidadas
        fresh = self._fresh_unit_state()
        saved = {name: getattr(self, name) for name in fresh}
        for name, value in fresh.items():
            setattr(self, name, value)
        self._function = FunctionContext(label, record, class_symbol)
        try:
            body()
            instructions = self.program.instructions
            temps = self.temps
        finally:
            for name, value in saved.items():
                setattr(self, name, value)

        if record is not None:
            record.temporaries = temps.created
        size = Const(record.size, "integer") if record is not None else None
        begin = TACInstruction(TACOp.BEGIN_FUNC, None, Name(label), size, node.span.line)
        end = TACInstruction(TACOp.END_FUNC, None, Name(label), None, node.span.end_line)
        self._sections[position] = [begin, *instructions, end]
        self.unit_temps.append((label, temps))

    def _fresh_unit_state(self) -> dict[str, object]:
        return {"program": TACProgram(), "temps": type(self.temps)(), "_control_stack": [], "_function": None}

    def assemble_sections(self, main: list[TACInstruction]) -> TACProgram:
        program = TACProgram()
        for section in self._sections:
            program.instructions.extend(section or ())
        program.instructions.extend(main)
        return program

    # -- declaraciones ------------------------------------------------------
    def function_symbol(self, node: ast.FunctionDeclaration) -> Symbol:
        scope = self.table.scope_of(node)
        symbol = scope.resolve_local(node.name) if scope is not None else None
        if symbol is None or symbol.category is not SymbolCategory.FUNCTION:
            from tac_generator import TACGenerationError

            raise TACGenerationError(node, f"No se encontró la función «{node.name}» en la tabla de símbolos.")
        return symbol

    @staticmethod
    def function_label(symbol: Symbol) -> str:
        return symbol.tac_label or symbol.name

    def visit_function_declaration(self, node: ast.FunctionDeclaration) -> None:
        # Una función anidada en un método puede usar «this» del método que
        # la contiene (lo alcanza por el enlace de acceso, como cualquier
        # otra variable de su entorno).
        enclosing_class = self._function.class_symbol if self._function is not None else None
        self.generate_function(node, self.function_symbol(node), enclosing_class)

    def generate_function(
        self, node: ast.FunctionDeclaration, symbol: Symbol, class_symbol: Symbol | None = None
    ) -> None:
        # Los parámetros no generan instrucciones: el llamador ya dejó sus
        # valores en el registro (ver «param») y la tabla de símbolos
        # guarda su desplazamiento.
        self.generate_unit(
            self.function_label(symbol),
            symbol.activation_record,
            class_symbol,
            node,
            lambda: self.generate_statements(node.body.statements),
        )

    def visit_return_statement(self, node: ast.ReturnStatement) -> None:
        if self._function is None:
            from tac_generator import TACGenerationError

            raise TACGenerationError(node, "«return» sólo puede usarse dentro de una función.")
        value = self.visit(node.value) if node.value is not None else None
        # Un return dentro de try debe retirar los manejadores que instaló
        # esta función antes de salir de ella.
        self.close_handlers(self._handler_depth)
        self.emit(TACOp.RETURN, arg1=value)
        self.temps.release(value)

    # -- llamadas -------------------------------------------------------------
    def visit_call_expression(self, node: ast.CallExpression) -> Operand:
        callee = node.callee
        if isinstance(callee, ast.MemberExpression):
            return self.method_call(node, callee.object, callee.member)
        if isinstance(callee, ast.IdentifierExpression):
            symbol, owner = self.resolve(callee, callee.name)
            if symbol.category is SymbolCategory.FUNCTION:
                if owner.kind is ScopeKind.CLASS:
                    # Un método invocado sin «this.» dentro de su propia clase.
                    return self.method_call(node, None, callee.name)
                arguments = [self.visit(argument) for argument in node.arguments]
                return self.call(Name(self.function_label(symbol)), arguments, symbol.return_type is not None)
        from tac_generator import TACGenerationError

        raise TACGenerationError(node, "La expresión llamada no es una función ni un método.")

    def call(
        self,
        target: Operand,
        arguments: list[Operand],
        returns_value: bool,
        *,
        release_arguments: bool = True,
    ) -> Operand:
        """Emite ``param`` por cada argumento ya evaluado y la llamada.

        ``target`` es el nombre de la función o un temporal con la dirección
        de un método. Si la función no devuelve valor se emite ``call f, n``
        sin destino y el valor de la expresión es ``null``."""
        for argument in arguments:
            self.emit(TACOp.PARAM, arg1=argument)
        if release_arguments:
            for argument in arguments:
                self.temps.release(argument)
        self.temps.release(target)
        count = Const(len(arguments), "integer")
        if not returns_value:
            self.emit(TACOp.CALL, None, target, count)
            return Const(None, "null")
        result = self.temps.new()
        self.emit(TACOp.CALL, result, target, count)
        return result
