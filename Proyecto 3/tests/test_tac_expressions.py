"""Pruebas de generación de TAC para expresiones, asignaciones y
declaraciones, de punta a punta: código Compiscript -> TAC."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

import ast_nodes as ast  # noqa: E402
from analyzer import CompiscriptAnalyzer  # noqa: E402
from semantic_analyzer import analyze_semantics  # noqa: E402
from symbol_table import SymbolTable, build_symbol_table  # noqa: E402
from tac import TACOp, Temp  # noqa: E402
from tac_generator import (  # noqa: E402
    TACGenerationError,
    TACGenerator,
    generate_tac,
    infer_expression_types,
)

ANALYZER = CompiscriptAnalyzer()
SPAN = ast.SourceSpan.unknown()


def front_end(source: str):
    """Corre las fases anteriores y exige que el programa sea válido."""
    result = ANALYZER.analyze(source)
    table, scope_diagnostics = build_symbol_table(result.ast)
    type_diagnostics = analyze_semantics(table, result.ast)
    diagnostics = [*result.diagnostics, *scope_diagnostics, *type_diagnostics]
    assert not diagnostics, diagnostics
    return table, result.ast


def generator_for(source: str) -> TACGenerator:
    table, program = front_end(source)
    generator = TACGenerator(table, infer_expression_types(table, program))
    generator.generate(program)
    return generator


def tac_lines(source: str) -> list[str]:
    table, program = front_end(source)
    return generate_tac(table, program).lines()


class LeafTests(unittest.TestCase):
    def test_constants_are_used_directly(self) -> None:
        self.assertEqual(
            tac_lines('let a = 10; let s = "hola"; let b = true; let c = false; let n = null;'),
            ["a = 10", 's = "hola"', "b = true", "c = false", "n = null"],
        )

    def test_variable_copy_needs_no_temporary(self) -> None:
        self.assertEqual(tac_lines("let a = 1; let b = a;"), ["a = 1", "b = a"])

    def test_negative_literal_is_a_constant(self) -> None:
        self.assertEqual(tac_lines("let a = -5;"), ["a = -5"])

    def test_declaration_without_initializer_emits_nothing(self) -> None:
        self.assertEqual(tac_lines("let a: integer; a = 3;"), ["a = 3"])

    def test_constant_declaration(self) -> None:
        self.assertEqual(tac_lines("const PI: integer = 314;"), ["PI = 314"])


class ArithmeticTests(unittest.TestCase):
    def test_simple_operation(self) -> None:
        self.assertEqual(
            tac_lines("let a = 1; let b = 2; let x = a + b;"),
            ["a = 1", "b = 2", "t1 = a + b", "x = t1"],
        )

    def test_every_arithmetic_operator(self) -> None:
        lines = tac_lines("let a = 7; let b = 2; let x = 0; x = a - b; x = a * b; x = a / b; x = a % b;")
        self.assertEqual(
            lines[3:],
            ["t1 = a - b", "x = t1", "t1 = a * b", "x = t1", "t1 = a / b", "x = t1", "t1 = a % b", "x = t1"],
        )

    def test_precedence(self) -> None:
        self.assertEqual(
            tac_lines("let a = 1; let b = 2; let x = a + b * 5;")[2:],
            ["t1 = b * 5", "t1 = a + t1", "x = t1"],
        )

    def test_left_associativity(self) -> None:
        self.assertEqual(
            tac_lines("let a = 9; let x = a - 3 - 2;")[1:],
            ["t1 = a - 3", "t1 = t1 - 2", "x = t1"],
        )

    def test_grouping_changes_the_tree(self) -> None:
        self.assertEqual(
            tac_lines("let a = 1; let b = 2; let x = (a + b) * 5;")[2:],
            ["t1 = a + b", "t1 = t1 * 5", "x = t1"],
        )

    def test_nested_expression(self) -> None:
        self.assertEqual(
            tac_lines("let a = 1; let b = 2; let c = 3; let x = (a * b) + (a - c) * (b % 2);")[3:],
            [
                "t1 = a * b",
                "t2 = a - c",
                "t3 = b % 2",
                "t2 = t2 * t3",
                "t1 = t1 + t2",
                "x = t1",
            ],
        )

    def test_constants_only(self) -> None:
        self.assertEqual(tac_lines("let x = 2 + 3 * 4;"), ["t1 = 3 * 4", "t1 = 2 + t1", "x = t1"])

    def test_unary_minus_on_expression(self) -> None:
        self.assertEqual(
            tac_lines("let a = 1; let x = -(a + 2);")[1:],
            ["t1 = a + 2", "t1 = minus t1", "x = t1"],
        )

    def test_double_unary_minus(self) -> None:
        self.assertEqual(tac_lines("let a = 1; let x = - -a;")[1:], ["t1 = minus a", "t1 = minus t1", "x = t1"])


class OtherOperatorTests(unittest.TestCase):
    def test_relational_and_equality_produce_values(self) -> None:
        self.assertEqual(
            tac_lines("let a = 1; let b = a < 10; let c = a == 3; let d = a >= 2; let e = a != a;")[1:],
            ["t1 = a < 10", "b = t1", "t1 = a == 3", "c = t1", "t1 = a >= 2", "d = t1", "t1 = a != a", "e = t1"],
        )

    def test_not(self) -> None:
        self.assertEqual(
            tac_lines("let a = 1; let b = !(a > 2);")[1:],
            ["t1 = a > 2", "t1 = not t1", "b = t1"],
        )

    def test_string_plus_is_concat(self) -> None:
        self.assertEqual(
            tac_lines('let nombre: string = "Ana"; let s = "Hola " + nombre + "!";')[1:],
            ['t1 = concat "Hola ", nombre', 't1 = concat t1, "!"', "s = t1"],
        )

    def test_integer_plus_stays_add_even_next_to_strings(self) -> None:
        lines = tac_lines('let a = 1; let s = "x"; let b = a + 2;')
        self.assertIn("t1 = a + 2", lines)


class AssignmentTests(unittest.TestCase):
    def test_assignment_statement(self) -> None:
        self.assertEqual(
            tac_lines("let x = 0; let a = 4; x = a * 2;")[2:],
            ["t1 = a * 2", "x = t1"],
        )

    def test_chained_assignment(self) -> None:
        self.assertEqual(
            tac_lines("let x = 0; let y = 0; x = y = 3 + 4;")[2:],
            ["t1 = 3 + 4", "y = t1", "x = y"],
        )

    def test_assignment_inside_expression(self) -> None:
        self.assertEqual(
            tac_lines("let x = 0; let y = 0; y = (x = 5) + 1;")[2:],
            ["x = 5", "t1 = x + 1", "y = t1"],
        )

    def test_expression_statement_without_effects(self) -> None:
        self.assertEqual(tac_lines("let a = 1; a + 2;")[1:], ["t1 = a + 2"])

    def test_print(self) -> None:
        self.assertEqual(tac_lines("let a = 1; print(a * 2);")[1:], ["t1 = a * 2", "print t1"])


class ArrayTests(unittest.TestCase):
    def test_array_literal(self) -> None:
        self.assertEqual(
            tac_lines("let a = 1; let lista = [1, a + 1, 3];")[1:],
            [
                "t1 = new_array 3",
                "t1[0] = 1",
                "t2 = a + 1",
                "t1[1] = t2",
                "t1[2] = 3",
                "lista = t1",
            ],
        )

    def test_empty_array(self) -> None:
        self.assertEqual(tac_lines("let lista: integer[] = [];"), ["t1 = new_array 0", "lista = t1"])

    def test_nested_array(self) -> None:
        self.assertEqual(
            tac_lines("let m = [[1], [2]];"),
            [
                "t1 = new_array 2",
                "t2 = new_array 1",
                "t2[0] = 1",
                "t1[0] = t2",
                "t2 = new_array 1",
                "t2[0] = 2",
                "t1[1] = t2",
                "m = t1",
            ],
        )

    def test_index_read(self) -> None:
        self.assertEqual(
            tac_lines("let l = [5, 6]; let i = 0; let x = l[i + 1] * 2;")[5:],
            ["t1 = i + 1", "t1 = l[t1]", "t1 = t1 * 2", "x = t1"],
        )

    def test_matrix_read(self) -> None:
        self.assertEqual(
            tac_lines("let m = [[1, 2]]; let x = m[0][1];")[-3:],
            ["t1 = m[0]", "t1 = t1[1]", "x = t1"],
        )

    def test_index_write(self) -> None:
        self.assertEqual(
            tac_lines("let l = [1, 2]; let i = 0; l[i] = l[1] + 3;")[5:],
            ["t1 = l[1]", "t1 = t1 + 3", "l[i] = t1"],
        )

    def test_index_write_is_an_expression(self) -> None:
        self.assertEqual(
            tac_lines("let l = [1]; let x = 0; x = l[0] = 7;")[4:],
            ["l[0] = 7", "x = 7"],
        )


class NamingTests(unittest.TestCase):
    def test_shadowed_variable_gets_distinct_name(self) -> None:
        self.assertEqual(
            tac_lines("let a = 1; { let a = 2; print(a); } print(a);"),
            ["a = 1", "a$1 = 2", "print a$1", "print a"],
        )

    def test_user_names_never_collide_with_temporaries_or_labels(self) -> None:
        self.assertEqual(
            tac_lines("let t1 = 1; let L2 = 2; let x = t1 + L2;"),
            ["t1$1 = 1", "L2$1 = 2", "t1 = t1$1 + L2$1", "x = t1"],
        )

    def test_variable_operand_carries_its_symbol(self) -> None:
        table, program = front_end("let edad: integer = 3;")
        instruction = generate_tac(table, program)[0]
        self.assertEqual(instruction.result.symbol.type_name, "integer")

    def test_instructions_remember_source_line(self) -> None:
        table, program = front_end("let a = 1;\nlet b = 2;\nlet x = a + b;")
        self.assertEqual([item.line for item in generate_tac(table, program)], [1, 2, 3, 3])


class TemporaryRecyclingTests(unittest.TestCase):
    def test_long_chain_uses_a_single_temporary(self) -> None:
        generator = generator_for("let a = 1; let x = a + a + a + a + a + a;")
        self.assertEqual(generator.temps.max_live, 1)
        self.assertEqual(generator.temps.created, 1)

    def test_balanced_tree_needs_two(self) -> None:
        generator = generator_for("let a = 1; let x = (a * a) + (a * a);")
        self.assertEqual(generator.temps.max_live, 2)

    def test_only_pending_left_results_keep_temporaries_alive(self) -> None:
        # Cada operando izquierdo es una variable: nada queda pendiente.
        generator = generator_for("let a = 1; let x = a * (a + (a * (a - 1)));")
        self.assertEqual(generator.temps.max_live, 1)
        generator = generator_for("let a = 1; let x = (a * a) - ((a * a) - ((a * a) - (a * a)));")
        self.assertEqual(generator.temps.max_live, 4)

    def test_temporaries_are_recycled_between_statements(self) -> None:
        source = "let a = 1; let x = (a + 1) * (a + 2); let y = (a + 3) * (a + 4);"
        generator = generator_for(source)
        lines = generator.program.lines()
        self.assertEqual(lines[1:4], ["t1 = a + 1", "t2 = a + 2", "t1 = t1 * t2"])
        self.assertEqual(lines[5:8], ["t1 = a + 3", "t2 = a + 4", "t1 = t1 * t2"])
        self.assertEqual(generator.temps.created, 2)
        self.assertGreater(generator.temps.reuses, 0)

    def test_no_temporary_is_left_alive(self) -> None:
        generator = generator_for("let l = [1, 2]; let x = l[0] + l[1]; l[0] = x * 2; print(l[1]);")
        self.assertEqual(generator.temps.live_count, 0)

    def test_every_temporary_is_written_before_it_is_read(self) -> None:
        # Si el reciclaje reutilizara un temporal que todavía se necesita,
        # aparecería una lectura de un temporal cuyo valor ya se sobrescribió.
        source = "let a = 1; let b = 2; let x = (a + b) * (a - b) / ((a * b) % (b + 1)) - -a;"
        table, program = front_end(source)
        pending: set[int] = set()
        for instruction in generate_tac(table, program):
            for operand in (instruction.arg1, instruction.arg2):
                if isinstance(operand, Temp):
                    self.assertIn(operand.index, pending, str(instruction))
                    pending.discard(operand.index)
            if isinstance(instruction.result, Temp) and instruction.op is not TACOp.INDEX_STORE:
                self.assertNotIn(instruction.result.index, pending, str(instruction))
                pending.add(instruction.result.index)
        self.assertEqual(pending, set())


class ExampleFileTests(unittest.TestCase):
    def test_expressions_example_generates_with_three_temporaries(self) -> None:
        source = (PROJECT / "examples" / "tac_expresiones.cps").read_text(encoding="utf-8")
        generator = generator_for(source)
        self.assertEqual(generator.temps.created, 3)
        self.assertEqual(generator.temps.live_count, 0)
        self.assertIn('t1 = concat "Hola ", nombre', generator.program.lines())


class _UnsupportedExpression(ast.Expression):
    """Nodo que ningún generador conoce (para probar el caso fallido)."""


class FailureTests(unittest.TestCase):
    """Casos fallidos: el generador se niega a emitir TAC incorrecto."""

    def test_error_expression_is_rejected(self) -> None:
        broken = ast.Program(
            span=SPAN,
            statements=(ast.ExpressionStatement(span=SPAN, expression=ast.ErrorExpression(span=SPAN, description="x")),),
        )
        with self.assertRaisesRegex(TACGenerationError, "errores"):
            TACGenerator(SymbolTable()).generate(broken)

    def test_unknown_node_is_rejected_instead_of_ignored(self) -> None:
        program = ast.Program(
            span=SPAN,
            statements=(ast.ExpressionStatement(span=SPAN, expression=_UnsupportedExpression(span=SPAN)),),
        )
        with self.assertRaisesRegex(TACGenerationError, "_UnsupportedExpression"):
            TACGenerator(SymbolTable()).generate(program)

    def test_identifier_missing_from_symbol_table(self) -> None:
        program = ast.Program(
            span=SPAN,
            statements=(ast.PrintStatement(span=SPAN, expression=ast.IdentifierExpression(span=SPAN, name="fantasma")),),
        )
        with self.assertRaisesRegex(TACGenerationError, "fantasma"):
            TACGenerator(SymbolTable()).generate(program)

    def test_leaked_temporary_is_detected(self) -> None:
        class LeakyGenerator(TACGenerator):
            def visit_print_statement(self, node):
                self.visit(node.expression)  # olvida liberar el temporal

        table, program = front_end("let a = 1; print(a + 1);")
        with self.assertRaisesRegex(TACGenerationError, "temporales vivos"):
            LeakyGenerator(table).generate(program)

    def test_error_reports_source_location(self) -> None:
        span = ast.SourceSpan(4, 7, 4, 9)
        program = ast.Program(
            span=SPAN,
            statements=(ast.ExpressionStatement(span=span, expression=_UnsupportedExpression(span=span)),),
        )
        with self.assertRaises(TACGenerationError) as context:
            TACGenerator(SymbolTable()).generate(program)
        self.assertEqual((context.exception.line, context.exception.column), (4, 7))


if __name__ == "__main__":
    unittest.main()
