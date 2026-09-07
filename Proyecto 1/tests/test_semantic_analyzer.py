from __future__ import annotations

import unittest

import ast_nodes as ast
from symbol_table import SymbolTableBuilder
from semantic_analyzer import SemanticAnalyzer, analyze_semantics

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
    return ast.ConstantDeclaration(span=SPAN, name=name, type_annotation=type_annotation, initializer=initializer)


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


def unary(operator, operand):
    return ast.UnaryExpression(span=SPAN, operator=operator, operand=operand)


def conditional(condition, when_true, when_false):
    return ast.ConditionalExpression(span=SPAN, condition=condition, when_true=when_true, when_false=when_false)


def return_stmt(value=None):
    return ast.ReturnStatement(span=SPAN, value=value)


def if_stmt(condition, then_branch, else_branch=None):
    return ast.IfStatement(span=SPAN, condition=condition, then_branch=then_branch, else_branch=else_branch)


def while_stmt(condition, body):
    return ast.WhileStatement(span=SPAN, condition=condition, body=body)


def do_while_stmt(body, condition):
    return ast.DoWhileStatement(span=SPAN, body=body, condition=condition)


def for_stmt(initializer, condition, update, body):
    return ast.ForStatement(span=SPAN, initializer=initializer, condition=condition, update=update, body=body)


def break_stmt():
    return ast.BreakStatement(span=SPAN)


def this_expr():
    return ast.ThisExpression(span=SPAN)


def member(obj, name):
    return ast.MemberExpression(span=SPAN, object=obj, member=name)


def new_expr(class_name, *arguments):
    return ast.NewExpression(span=SPAN, class_name=class_name, arguments=tuple(arguments))


def array_lit(*elements):
    return ast.ArrayExpression(span=SPAN, elements=tuple(elements))


def index_expr(collection, index):
    return ast.IndexExpression(span=SPAN, collection=collection, index=index)


def analyze(prog):
    """Corre las dos fases (tabla de símbolos + semántico) y regresa
    (ambito_diagnostics, tipo_diagnostics)."""
    table = SymbolTableBuilder().build(prog)
    type_diagnostics = analyze_semantics(table, prog)
    return table, type_diagnostics


class ArithmeticTests(unittest.TestCase):
    def test_integer_plus_integer_is_valid(self):
        _, diags = analyze(program(expr_stmt(binary(lit(10), "+", lit(5)))))
        self.assertEqual(diags, [])

    def test_string_concatenation_is_valid(self):
        _, diags = analyze(program(expr_stmt(binary(lit("a", "string"), "+", lit("b", "string")))))
        self.assertEqual(diags, [])

    def test_boolean_plus_integer_is_invalid(self):
        _, diags = analyze(program(expr_stmt(binary(lit(True, "boolean"), "+", lit(5)))))
        self.assertEqual(len(diags), 1)
        self.assertIn("+", diags[0].symbol)

    def test_subtraction_requires_integers(self):
        _, diags = analyze(program(expr_stmt(binary(lit("a", "string"), "-", lit(1)))))
        self.assertEqual(len(diags), 1)

    def test_function_used_as_operand_is_invalid(self):
        # "foo * 10" donde foo es una función.
        f = func("foo", return_type=type_ref("integer"), body=[return_stmt(lit(1))])
        prog = program(f, expr_stmt(binary(ident("foo"), "*", lit(10))))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)
        self.assertIn("*", diags[0].symbol)


class LogicalTests(unittest.TestCase):
    def test_boolean_and_boolean_is_valid(self):
        _, diags = analyze(program(expr_stmt(binary(lit(True, "boolean"), "&&", lit(False, "boolean")))))
        self.assertEqual(diags, [])

    def test_integer_and_boolean_is_invalid(self):
        _, diags = analyze(program(expr_stmt(binary(lit(10), "&&", lit(False, "boolean")))))
        self.assertEqual(len(diags), 1)

    def test_not_operator_requires_boolean(self):
        _, diags = analyze(program(expr_stmt(unary("!", lit(10)))))
        self.assertEqual(len(diags), 1)


class ComparisonTests(unittest.TestCase):
    def test_integer_relational_comparison_is_valid(self):
        _, diags = analyze(program(expr_stmt(binary(lit(1), "<", lit(2)))))
        self.assertEqual(diags, [])

    def test_string_relational_comparison_is_invalid(self):
        _, diags = analyze(program(expr_stmt(binary(lit("a", "string"), "<", lit("b", "string")))))
        self.assertEqual(len(diags), 1)

    def test_equality_between_incompatible_types_is_invalid(self):
        _, diags = analyze(program(expr_stmt(binary(lit(1), "==", lit("a", "string")))))
        self.assertEqual(len(diags), 1)

    def test_equality_of_same_type_is_valid(self):
        _, diags = analyze(program(expr_stmt(binary(lit(1), "==", lit(2)))))
        self.assertEqual(diags, [])


class AssignmentTests(unittest.TestCase):
    def test_assigning_matching_type_is_valid(self):
        prog = program(var("x", type_annotation=type_ref("integer")), expr_stmt(assign(ident("x"), lit(10))))
        _, diags = analyze(prog)
        self.assertEqual(diags, [])

    def test_assigning_mismatched_type_is_invalid(self):
        prog = program(var("x", type_annotation=type_ref("integer")), expr_stmt(assign(ident("x"), lit(True, "boolean"))))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)
        self.assertIn("asignar", diags[0].description)

    def test_inferred_type_from_initializer_is_checked_on_later_assignment(self):
        # `let x = 10;` sin anotación: el tipo se infiere del inicializador.
        prog = program(var("x", initializer=lit(10)), expr_stmt(assign(ident("x"), lit(True, "boolean"))))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_declared_type_mismatch_with_initializer_is_invalid(self):
        prog = program(var("x", type_annotation=type_ref("integer"), initializer=lit(True, "boolean")))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)


class ListTests(unittest.TestCase):
    def test_homogeneous_array_is_valid(self):
        _, diags = analyze(program(expr_stmt(array_lit(lit(1), lit(2), lit(3)))))
        self.assertEqual(diags, [])

    def test_heterogeneous_array_is_invalid(self):
        _, diags = analyze(program(expr_stmt(array_lit(lit(1), lit("a", "string")))))
        self.assertEqual(len(diags), 1)

    def test_indexing_with_integer_is_valid(self):
        prog = program(
            var("lista", initializer=array_lit(lit(1), lit(2))),
            expr_stmt(index_expr(ident("lista"), lit(0))),
        )
        _, diags = analyze(prog)
        self.assertEqual(diags, [])

    def test_indexing_with_non_integer_is_invalid(self):
        prog = program(
            var("lista", initializer=array_lit(lit(1), lit(2))),
            expr_stmt(index_expr(ident("lista"), lit("a", "string"))),
        )
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_indexing_a_non_array_is_invalid(self):
        prog = program(var("x", initializer=lit(10)), expr_stmt(index_expr(ident("x"), lit(0))))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)


class ControlFlowTests(unittest.TestCase):
    def test_if_with_boolean_condition_is_valid(self):
        prog = program(if_stmt(lit(True, "boolean"), block(print_stmt(lit(1)))))
        _, diags = analyze(prog)
        self.assertEqual(diags, [])

    def test_if_with_non_boolean_condition_is_invalid(self):
        prog = program(if_stmt(lit(1), block(print_stmt(lit(1)))))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_while_with_non_boolean_condition_is_invalid(self):
        prog = program(while_stmt(lit(1), block(break_stmt())))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_do_while_with_non_boolean_condition_is_invalid(self):
        prog = program(do_while_stmt(block(break_stmt()), lit(1)))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_for_with_non_boolean_condition_is_invalid(self):
        prog = program(
            for_stmt(var("i", initializer=lit(0)), lit(1), None, block(break_stmt()))
        )
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_for_with_boolean_condition_is_valid(self):
        prog = program(
            for_stmt(var("i", initializer=lit(0)), binary(ident("i"), "<", lit(10)), None, block(break_stmt()))
        )
        _, diags = analyze(prog)
        self.assertEqual(diags, [])


class FunctionSemanticTests(unittest.TestCase):
    def test_correct_arguments_are_valid(self):
        f = func("foo", parameters=[param("a", type_ref("integer")), param("b", type_ref("boolean"))])
        prog = program(f, expr_stmt(call(ident("foo"), lit(10), lit(True, "boolean"))))
        _, diags = analyze(prog)
        self.assertEqual(diags, [])

    def test_wrong_argument_type_is_invalid(self):
        f = func("foo", parameters=[param("a", type_ref("integer")), param("b", type_ref("integer"))])
        prog = program(f, expr_stmt(call(ident("foo"), lit(10), lit(True, "boolean"))))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_wrong_argument_count_is_invalid(self):
        f = func("foo", parameters=[param("a", type_ref("integer")), param("b", type_ref("integer"))])
        prog = program(f, expr_stmt(call(ident("foo"), lit(10))))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)
        self.assertIn("argumento", diags[0].description)

    def test_wrong_return_type_is_invalid(self):
        f = func("foo", return_type=type_ref("integer"), body=[return_stmt(lit(True, "boolean"))])
        prog = program(f)
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_correct_return_type_is_valid(self):
        f = func("foo", return_type=type_ref("integer"), body=[return_stmt(lit(1))])
        prog = program(f)
        _, diags = analyze(prog)
        self.assertEqual(diags, [])

    def test_returning_value_without_declared_return_type_is_invalid(self):
        f = func("foo", body=[return_stmt(lit(1))])
        prog = program(f)
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_recursive_call_with_correct_types_is_valid(self):
        f = func(
            "factorial",
            parameters=[param("n", type_ref("integer"))],
            return_type=type_ref("integer"),
            body=[return_stmt(binary(ident("n"), "*", call(ident("factorial"), binary(ident("n"), "-", lit(1)))))],
        )
        prog = program(f)
        _, diags = analyze(prog)
        self.assertEqual(diags, [])

    def test_recursive_call_with_wrong_argument_type_is_invalid(self):
        f = func(
            "factorial",
            parameters=[param("n", type_ref("integer"))],
            return_type=type_ref("integer"),
            body=[return_stmt(call(ident("factorial"), lit(True, "boolean")))],
        )
        prog = program(f)
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)


class ClassSemanticTests(unittest.TestCase):
    def _animal_class(self):
        return class_decl(
            "Animal",
            members=[
                var("nombre", type_annotation=type_ref("string")),
                func("constructor", parameters=[param("nombre", type_ref("string"))],
                     body=[expr_stmt(assign(member(this_expr(), "nombre"), ident("nombre")))]),
                func("hablar", return_type=type_ref("string"),
                     body=[return_stmt(member(this_expr(), "nombre"))]),
            ],
        )

    def test_valid_attribute_and_method_access(self):
        prog = program(
            self._animal_class(),
            var("perro", initializer=new_expr("Animal", lit("Firulais", "string"))),
            expr_stmt(call(member(ident("perro"), "hablar"))),
        )
        _, diags = analyze(prog)
        self.assertEqual(diags, [])

    def test_nonexistent_attribute_is_invalid(self):
        prog = program(
            self._animal_class(),
            var("perro", initializer=new_expr("Animal", lit("Firulais", "string"))),
            expr_stmt(member(ident("perro"), "edad")),
        )
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)
        self.assertIn("edad", diags[0].symbol)

    def test_nonexistent_method_call_is_invalid(self):
        prog = program(
            self._animal_class(),
            var("perro", initializer=new_expr("Animal", lit("Firulais", "string"))),
            expr_stmt(call(member(ident("perro"), "volar"))),
        )
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_constructor_argument_type_is_validated(self):
        prog = program(
            self._animal_class(),
            var("perro", initializer=new_expr("Animal", lit(123))),
        )
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_accessing_member_on_non_object_is_invalid(self):
        prog = program(var("x", initializer=lit(10)), expr_stmt(member(ident("x"), "algo")))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_new_on_subclass_uses_inherited_constructor(self):
        animal = self._animal_class()
        perro = class_decl("Perro", superclass="Animal", members=[])
        prog = program(
            animal, perro,
            var("p", initializer=new_expr("Perro", lit("Toby", "string"))),
        )
        _, diags = analyze(prog)
        self.assertEqual(diags, [])

    def test_new_on_subclass_still_validates_inherited_constructor_args(self):
        animal = self._animal_class()
        perro = class_decl("Perro", superclass="Animal", members=[])
        prog = program(
            animal, perro,
            var("p", initializer=new_expr("Perro", lit(123))),
        )
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)


class DeadCodeTests(unittest.TestCase):
    def test_code_after_return_is_dead(self):
        f = func("foo", body=[return_stmt(), expr_stmt(assign(ident("x"), lit(2)))])
        prog = program(var("x", initializer=lit(0)), f)
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)
        self.assertIn("muerto", diags[0].description.lower())

    def test_code_after_break_is_dead(self):
        prog = program(while_stmt(lit(True, "boolean"), block(break_stmt(), print_stmt(lit(1)))))
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)

    def test_no_dead_code_reported_for_normal_sequence(self):
        f = func("foo", return_type=type_ref("integer"),
                  body=[expr_stmt(assign(ident("x"), lit(1))), return_stmt(lit(1))])
        prog = program(var("x", initializer=lit(0)), f)
        _, diags = analyze(prog)
        self.assertEqual(diags, [])

    def test_only_one_diagnostic_for_a_dead_run_of_several_statements(self):
        f = func(
            "foo",
            body=[
                return_stmt(),
                print_stmt(lit(1)),
                print_stmt(lit(2)),
                print_stmt(lit(3)),
            ],
        )
        prog = program(f)
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 1)


class ErrorCascadeTests(unittest.TestCase):
    def test_undeclared_variable_does_not_produce_extra_arithmetic_error(self):
        # symbol_table.py reporta "no declarada"; el analizador semántico NO
        # debe agregar un segundo error de tipos sobre la misma expresión.
        prog = program(expr_stmt(binary(ident("no_existe"), "+", lit(1))))
        table = SymbolTableBuilder().build(prog)
        type_diags = analyze_semantics(table, prog)
        self.assertEqual(len(table.all_symbols()), 0)  # nada se declaró
        self.assertEqual(type_diags, [])  # el semántico no agrega ruido

    def test_analysis_continues_after_multiple_unrelated_errors(self):
        # Varios errores de distinta naturaleza en un solo programa: todos
        # deben reportarse, ninguno debe detener el análisis.
        prog = program(
            expr_stmt(binary(lit(True, "boolean"), "+", lit(1))),   # error aritmético
            if_stmt(lit(1), block(print_stmt(lit(1)))),               # condición no booleana
            expr_stmt(array_lit(lit(1), lit("a", "string"))),        # lista heterogénea
        )
        _, diags = analyze(prog)
        self.assertEqual(len(diags), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
