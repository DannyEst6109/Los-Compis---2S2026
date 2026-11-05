from __future__ import annotations

import unittest

import ast_nodes as ast
from symbol_table import (
    ScopeKind,
    SymbolCategory,
    SymbolTableBuilder,
)

SPAN = ast.SourceSpan.unknown()


# -- helpers para construir AST a mano (sin depender de ANTLR) -----------------

def ident(name):
    return ast.IdentifierExpression(span=SPAN, name=name)


def lit(value, literal_type="integer"):
    return ast.LiteralExpression(span=SPAN, value=value, literal_type=literal_type)


def type_ref(name, dims=0):
    return ast.TypeRef(span=SPAN, name=name, dimensions=dims)


def var(name, initializer=None, type_annotation=None, kind="let"):
    return ast.VariableDeclaration(
        span=SPAN, declaration_kind=kind, name=name,
        type_annotation=type_annotation, initializer=initializer,
    )


def const(name, initializer, type_annotation=None):
    return ast.ConstantDeclaration(
        span=SPAN, name=name, type_annotation=type_annotation, initializer=initializer,
    )


def param(name, type_annotation=None):
    return ast.Parameter(span=SPAN, name=name, type_annotation=type_annotation)


def block(*statements):
    return ast.Block(span=SPAN, statements=tuple(statements))


def program(*statements):
    return ast.Program(span=SPAN, statements=tuple(statements))


def func(name, parameters=(), return_type=None, body=()):
    return ast.FunctionDeclaration(
        span=SPAN, name=name, parameters=tuple(parameters),
        return_type=return_type, body=block(*body),
    )


def class_decl(name, superclass=None, members=()):
    return ast.ClassDeclaration(span=SPAN, name=name, superclass=superclass, members=tuple(members))


def expr_stmt(expression):
    return ast.ExpressionStatement(span=SPAN, expression=expression)


def print_stmt(expression):
    return ast.PrintStatement(span=SPAN, expression=expression)


def assign(target, value):
    return ast.AssignmentExpression(span=SPAN, target=target, value=value)


def call(callee, *arguments):
    return ast.CallExpression(span=SPAN, callee=callee, arguments=tuple(arguments))


def binary(left, operator, right):
    return ast.BinaryExpression(span=SPAN, left=left, operator=operator, right=right)


def return_stmt(value=None):
    return ast.ReturnStatement(span=SPAN, value=value)


def if_stmt(condition, then_branch, else_branch=None):
    return ast.IfStatement(span=SPAN, condition=condition, then_branch=then_branch, else_branch=else_branch)


def while_stmt(condition, body):
    return ast.WhileStatement(span=SPAN, condition=condition, body=body)


def break_stmt():
    return ast.BreakStatement(span=SPAN)


def continue_stmt():
    return ast.ContinueStatement(span=SPAN)


def this_expr():
    return ast.ThisExpression(span=SPAN)


def member(obj, name):
    return ast.MemberExpression(span=SPAN, object=obj, member=name)


def new_expr(class_name, *arguments):
    return ast.NewExpression(span=SPAN, class_name=class_name, arguments=tuple(arguments))


def build(prog):
    builder = SymbolTableBuilder()
    builder.build(prog)
    return builder


class DeclarationTests(unittest.TestCase):
    def test_declared_variable_has_no_errors(self):
        builder = build(program(var("x", initializer=lit(10)), print_stmt(ident("x"))))
        self.assertEqual(builder.diagnostics, [])

    def test_undeclared_variable_reports_error(self):
        builder = build(program(print_stmt(ident("y"))))
        self.assertEqual(len(builder.diagnostics), 1)
        self.assertIn("y", builder.diagnostics[0].symbol)
        self.assertIn("no ha sido declarada", builder.diagnostics[0].description)

    def test_duplicate_variable_same_scope_reports_error(self):
        builder = build(program(var("x", initializer=lit(1)), var("x", initializer=lit(2))))
        self.assertEqual(len(builder.diagnostics), 1)
        self.assertIn("ya fue declarado", builder.diagnostics[0].description)

    def test_shadowing_in_nested_block_is_allowed(self):
        builder = build(
            program(
                var("x", initializer=lit(1)),
                block(var("x", initializer=lit(2)), print_stmt(ident("x"))),
            )
        )
        self.assertEqual(builder.diagnostics, [])

    def test_reassigning_constant_reports_error(self):
        builder = build(
            program(const("PI", lit(314)), expr_stmt(assign(ident("PI"), lit(1))))
        )
        descriptions = [d.description for d in builder.diagnostics]
        self.assertTrue(any("reasignar la constante" in d for d in descriptions))

    def test_assignment_marks_variable_as_initialized(self):
        builder = build(program(var("x"), expr_stmt(assign(ident("x"), lit(5)))))
        self.assertEqual(builder.diagnostics, [])
        symbol = builder.table.global_scope.resolve_local("x")
        self.assertTrue(symbol.initialized)


class FunctionTests(unittest.TestCase):
    def test_duplicate_parameters_reports_error(self):
        builder = build(program(func("f", parameters=[param("a"), param("a")])))
        self.assertEqual(len(builder.diagnostics), 1)
        self.assertIn("a", builder.diagnostics[0].symbol)

    def test_recursive_function_has_no_errors(self):
        factorial = func(
            "factorial",
            parameters=[param("n", type_ref("integer"))],
            return_type=type_ref("integer"),
            body=[return_stmt(call(ident("factorial"), binary(ident("n"), "-", lit(1))))],
        )
        builder = build(program(factorial))
        self.assertEqual(builder.diagnostics, [])
        symbol = builder.table.global_scope.resolve_local("factorial")
        self.assertEqual(symbol.category, SymbolCategory.FUNCTION)
        self.assertEqual(len(symbol.parameters), 1)
        self.assertEqual(symbol.return_type, "integer")

    def test_mutual_recursion_across_functions_has_no_errors(self):
        is_even = func("isEven", parameters=[param("n")], body=[
            return_stmt(call(ident("isOdd"), ident("n"))),
        ])
        is_odd = func("isOdd", parameters=[param("n")], body=[
            return_stmt(call(ident("isEven"), ident("n"))),
        ])
        builder = build(program(is_even, is_odd))
        self.assertEqual(builder.diagnostics, [])

    def test_forward_reference_to_function_resolves(self):
        # `helper` se usa antes de su declaración textual en el mismo bloque.
        builder = build(program(
            expr_stmt(call(ident("helper"))),
            func("helper", body=[return_stmt(lit(1))]),
        ))
        self.assertEqual(builder.diagnostics, [])

    def test_nested_function_captures_outer_variable(self):
        outer = func(
            "outer",
            body=[
                var("counter", initializer=lit(0)),
                func("increment", body=[
                    expr_stmt(assign(ident("counter"), binary(ident("counter"), "+", lit(1)))),
                ]),
            ],
        )
        builder = build(program(outer))
        self.assertEqual(builder.diagnostics, [])
        outer_scope = builder.table.global_scope.children[0]
        self.assertEqual(outer_scope.kind, ScopeKind.FUNCTION)
        increment_symbol = outer_scope.resolve_local("increment")
        self.assertIn("counter", increment_symbol.captured_names)

    def test_return_outside_function_reports_error(self):
        builder = build(program(return_stmt(lit(1))))
        self.assertEqual(len(builder.diagnostics), 1)
        self.assertIn("return", builder.diagnostics[0].description)

    def test_break_and_continue_outside_loop_report_errors(self):
        builder = build(program(break_stmt(), continue_stmt()))
        self.assertEqual(len(builder.diagnostics), 2)

    def test_break_inside_loop_has_no_errors(self):
        builder = build(program(while_stmt(lit(True, "boolean"), block(break_stmt()))))
        self.assertEqual(builder.diagnostics, [])


class ClassTests(unittest.TestCase):
    def test_class_registers_attributes_methods_and_constructor(self):
        animal = class_decl(
            "Animal",
            members=[
                var("nombre", type_annotation=type_ref("string")),
                func(
                    "constructor",
                    parameters=[param("nombre", type_ref("string"))],
                    body=[expr_stmt(assign(member(this_expr(), "nombre"), ident("nombre")))],
                ),
                func(
                    "hablar",
                    return_type=type_ref("string"),
                    body=[return_stmt(member(this_expr(), "nombre"))],
                ),
            ],
        )
        builder = build(program(animal))
        self.assertEqual(builder.diagnostics, [])
        class_symbol = builder.table.find_class("Animal")
        self.assertIsNotNone(class_symbol)
        self.assertIn("nombre", class_symbol.attributes)
        self.assertIn("constructor", class_symbol.methods)
        self.assertIn("hablar", class_symbol.methods)
        self.assertIs(class_symbol.constructor, class_symbol.methods["constructor"])

    def test_this_outside_class_reports_error(self):
        builder = build(program(print_stmt(member(this_expr(), "x"))))
        self.assertEqual(len(builder.diagnostics), 1)
        self.assertIn("this", builder.diagnostics[0].symbol)

    def test_new_of_undeclared_class_reports_error(self):
        builder = build(program(expr_stmt(new_expr("Fantasma"))))
        self.assertEqual(len(builder.diagnostics), 1)
        self.assertIn("Fantasma", builder.diagnostics[0].symbol)

    def test_class_inheriting_from_undeclared_class_reports_error(self):
        builder = build(program(class_decl("Perro", superclass="Animal")))
        self.assertEqual(len(builder.diagnostics), 1)
        self.assertIn("Animal", builder.diagnostics[0].symbol)

    def test_methods_can_call_each_other_regardless_of_order(self):
        counter = class_decl(
            "Counter",
            members=[
                func("isReady", body=[return_stmt(call(ident("hasStarted")))]),
                func("hasStarted", body=[return_stmt(lit(True, "boolean"))]),
            ],
        )
        builder = build(program(counter))
        self.assertEqual(builder.diagnostics, [])


class RenderTests(unittest.TestCase):
    def test_render_contains_header_and_rows(self):
        builder = build(program(var("x", initializer=lit(1))))
        rendered = builder.table.render()
        self.assertIn("Nombre", rendered)
        self.assertIn("Categoría", rendered)
        self.assertIn("x", rendered)


if __name__ == "__main__":
    unittest.main(verbosity=2)