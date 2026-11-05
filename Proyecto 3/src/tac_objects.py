"""Traducción de clases, objetos y herencia al TAC compartido.

* Una clase no genera código en el punto donde se declara: genera una
  sección por método (``Clase.metodo``) y, si algún atributo tiene valor
  inicial, un inicializador ``Clase.$init`` que los asigna.
* ``new C(args)`` reserva la instancia (``t = new C``, que también deja en
  ella el puntero a la vtable de ``C``), llama a los inicializadores de la
  cadena de herencia desde la raíz y después al constructor vigente (el
  propio o el heredado más cercano).
* Los atributos se leen y escriben por nombre (``t = o.f`` y ``o.f = x``);
  su desplazamiento está en la distribución de la clase en la tabla de
  símbolos.
* Las llamadas a métodos usan **despacho dinámico**: ``t = method o.m``
  obtiene de la vtable del objeto la implementación vigente, y luego
  ``call t, n`` la invoca con ``o`` como primer parámetro. Así una variable
  de tipo ``Animal`` que guarda un ``Perro`` ejecuta ``Perro.hablar``.
* Dentro de un método, ``this`` es el parámetro implícito ``this`` y un
  atributo o método nombrado sin ``this.`` se traduce como si lo tuviera.
"""

from __future__ import annotations

import ast_nodes as ast
from memory_layout import method_label
from semantic_analyzer import TypeKind
from symbol_table import Scope, ScopeKind, Symbol, SymbolCategory
from tac import Name, Operand, TACOp, Var

THIS = Var("this")


def _error(node: ast.AstNode, message: str) -> Exception:
    from tac_generator import TACGenerationError

    return TACGenerationError(node, message)


class ObjectMixin:
    # -- this y atributos 
    def this_operand(self, node: ast.AstNode) -> Var:
        if self._function is None or self._function.class_symbol is None:
            raise _error(node, "«this» sólo puede usarse dentro de un método de una clase.")
        return THIS

    def visit_this_expression(self, node: ast.ThisExpression) -> Var:
        return self.this_operand(node)

    @staticmethod
    def is_attribute(symbol: Symbol, owner: Scope) -> bool:
        return owner.kind is ScopeKind.CLASS and symbol.category in (
            SymbolCategory.VARIABLE,
            SymbolCategory.CONSTANT,
        )

    def visit_member_expression(self, node: ast.MemberExpression) -> Operand:
        target = self.visit(node.object)
        member = self._member_symbol(node.object, node.member)
        op = TACOp.METHOD_LOAD if member is not None and member.category is SymbolCategory.FUNCTION else TACOp.FIELD_LOAD
        return self.compute(op, target, Name(node.member))

    def store_field(self, target: Operand, member: str, value: Operand) -> Operand:
        """``target.member = value``; libera ``target`` y devuelve ``value``
        (el valor de una asignación es el valor asignado)."""
        self.emit(TACOp.FIELD_STORE, target, Name(member), value)
        self.temps.release(target)
        return value

    def _member_symbol(self, object_node: ast.Expression, member: str) -> Symbol | None:
        object_type = self.type_of(object_node)
        if object_type is None or object_type.kind is not TypeKind.CLASS or object_type.class_name is None:
            return None
        class_symbol = self.table.find_class(object_type.class_name)
        if class_symbol is None:
            return None
        return self.table.class_members(class_symbol).get(member)

    # -- declaración de clases 
    def visit_class_declaration(self, node: ast.ClassDeclaration) -> None:
        class_symbol = self.table.find_class(node.name)
        if class_symbol is None:
            raise _error(node, f"No se encontró la clase «{node.name}» en la tabla de símbolos.")
        layout = class_symbol.class_layout
        initialized = [
            member
            for member in node.members
            if isinstance(member, (ast.VariableDeclaration, ast.ConstantDeclaration))
            and member.initializer is not None
        ]
        if initialized:
            record = layout.init_record if layout is not None else None
            label = record.name if record is not None else method_label(node.name, "$init")
            self.generate_unit(label, record, class_symbol, node, lambda: self._initialize_fields(initialized))
        for member in node.members:
            if isinstance(member, ast.FunctionDeclaration):
                self.generate_function(member, self.function_symbol(member), class_symbol)

    def _initialize_fields(self, members: list[ast.Statement]) -> None:
        for member in members:
            live_before = self.temps.live_count
            value = self.visit(member.initializer)
            self.temps.release(self.store_field(THIS, member.name, value))
            if self.temps.live_count != live_before:
                raise _error(member, f"El valor inicial de «{member.name}» dejó temporales vivos.")

    # -- instanciación 
    def _inheritance_chain(self, class_symbol: Symbol) -> list[Symbol]:
        """Clases desde la raíz de la jerarquía hasta ``class_symbol``."""
        chain: list[Symbol] = []
        current: Symbol | None = class_symbol
        while current is not None and all(current is not known for known in chain):
            chain.append(current)
            current = self.table.find_class(current.superclass) if current.superclass else None
        return list(reversed(chain))

    def visit_new_expression(self, node: ast.NewExpression) -> Operand:
        class_symbol = self.table.find_class(node.class_name)
        if class_symbol is None:
            raise _error(node, f"No se encontró la clase «{node.class_name}» en la tabla de símbolos.")
        arguments = [self.visit(argument) for argument in node.arguments]
        instance = self.temps.new()
        self.emit(TACOp.NEW_OBJECT, instance, Name(node.class_name))
        for ancestor in self._inheritance_chain(class_symbol):
            layout = ancestor.class_layout
            if layout is not None and layout.init_record is not None:
                self.call(Name(layout.init_record.name), [instance], False, release_arguments=False)
        constructor = self.table.class_members(class_symbol).get("constructor")
        if constructor is not None and constructor.category is SymbolCategory.FUNCTION:
            self.call(Name(self.function_label(constructor)), [instance, *arguments], False, release_arguments=False)
        for argument in arguments:
            self.temps.release(argument)
        return instance

    # -- llamadas a métodos 
    def method_call(
        self, node: ast.CallExpression, receiver_node: ast.Expression | None, method: str
    ) -> Operand:
        """``receiver.method(args)`` con despacho dinámico. Sin
        ``receiver_node`` el receptor es ``this``."""
        if receiver_node is None:
            receiver = self.this_operand(node)
            member = self.table.class_members(self._function.class_symbol).get(method)
        else:
            receiver = self.visit(receiver_node)
            member = self._member_symbol(receiver_node, method)
        arguments = [self.visit(argument) for argument in node.arguments]
        address = self.temps.new()
        self.emit(TACOp.METHOD_LOAD, address, receiver, Name(method))
        returns_value = member is None or member.return_type is not None
        return self.call(address, [receiver, *arguments], returns_value)
