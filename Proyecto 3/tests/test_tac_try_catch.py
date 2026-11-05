"""Pruebas de la traducción de try/catch y de su interacción con break,
continue, return y funciones."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from compiler import compile_source  # noqa: E402
from tac import TACOp  # noqa: E402


def compile_ok(source: str):
    result = compile_source(source)
    assert result.succeeded, result.diagnostics
    return result


def tac_lines(source: str) -> list[str]:
    return compile_ok(source).tac.lines()


def section(lines: list[str], label: str) -> list[str]:
    start = next(i for i, line in enumerate(lines) if line.startswith(f"begin_func {label},"))
    return lines[start + 1:lines.index(f"end_func {label}")]


def last_index(lines: list[str], text: str) -> int:
    return max(i for i, line in enumerate(lines) if line == text)


class TryCatchTests(unittest.TestCase):
    def test_basic_structure(self) -> None:
        self.assertEqual(
            tac_lines('let xs = [1]; try { print(xs[3]); } catch (e) { print("Error: " + e); }'),
            [
                "t1 = new_array 1",
                "t1[0] = 1",
                "xs = t1",
                "try_begin L1",
                "t1 = xs[3]",
                "print t1",
                "try_end",
                "goto L2",
                "L1:",
                "e = exception",
                't1 = concat "Error: ", e',
                "print t1",
                "L2:",
            ],
        )

    def test_handlers_are_balanced_on_every_path(self) -> None:
        result = compile_ok((PROJECT / "examples" / "tac_try_catch.cps").read_text(encoding="utf-8"))
        ops = [instruction.op for instruction in result.tac]
        self.assertGreater(ops.count(TACOp.TRY_BEGIN), 0)
        # Cada try tiene su try_end normal; break/continue/return agregan más.
        self.assertGreaterEqual(ops.count(TACOp.TRY_END), ops.count(TACOp.TRY_BEGIN))
        self.assertEqual(ops.count(TACOp.GET_EXCEPTION), ops.count(TACOp.TRY_BEGIN))

    def test_nested_try(self) -> None:
        lines = tac_lines(
            "try { try { print(1); } catch (a) { print(a); } } catch (b) { print(b); }"
        )
        self.assertEqual(
            lines,
            [
                "try_begin L1",
                "try_begin L3",
                "print 1",
                "try_end",
                "goto L4",
                "L3:",
                "a = exception",
                "print a",
                "L4:",
                "try_end",
                "goto L2",
                "L1:",
                "b = exception",
                "print b",
                "L2:",
            ],
        )

    def test_catch_variables_with_same_name_are_distinct(self) -> None:
        lines = tac_lines("try { print(1); } catch (e) { print(e); } try { print(2); } catch (e) { print(e); }")
        self.assertIn("e = exception", lines)
        self.assertIn("e$1 = exception", lines)

    def test_break_and_continue_inside_try_close_the_handler(self) -> None:
        lines = tac_lines(
            "let i = 0;"
            "while (i < 5) {"
            "  i = i + 1;"
            "  try {"
            "    if (i == 1) { continue; }"
            "    if (i == 3) { break; }"
            "  } catch (e) { print(e); }"
            "}"
        )
        # while: L1 prueba, L2 cuerpo, L3 fin.
        continue_at = lines.index("goto L1")
        break_at = last_index(lines, "goto L3")  # el primero es la salida normal del while
        self.assertEqual(lines[continue_at - 1], "try_end")
        self.assertEqual(lines[break_at - 1], "try_end")

    def test_loop_inside_try_does_not_close_the_handler(self) -> None:
        lines = tac_lines("try { while (true) { break; } } catch (e) { print(e); }")
        break_at = lines.index("goto L5")
        self.assertNotEqual(lines[break_at - 1], "try_end")
        self.assertEqual(lines.count("try_end"), 1)

    def test_break_crossing_two_handlers(self) -> None:
        lines = tac_lines(
            "while (true) { try { try { break; } catch (a) { print(a); } } catch (b) { print(b); } }"
        )
        break_at = last_index(lines, "goto L3")
        self.assertEqual(lines[break_at - 2:break_at], ["try_end", "try_end"])

    def test_return_inside_try_closes_handlers_after_computing_the_value(self) -> None:
        lines = tac_lines(
            "function f(xs: integer[]): integer { try { return xs[1] + 1; } catch (e) { return -1; } }"
        )
        self.assertEqual(
            section(lines, "f"),
            [
                "try_begin L1",
                "t1 = xs[1]",
                "t1 = t1 + 1",
                "try_end",
                "return t1",
                "try_end",
                "goto L2",
                "L1:",
                "e = exception",
                "return -1",
                "L2:",
            ],
        )

    def test_function_declared_inside_try_does_not_inherit_handlers(self) -> None:
        lines = tac_lines("try { function f(): integer { return 1; } print(f()); } catch (e) { print(e); }")
        self.assertEqual(section(lines, "f"), ["return 1"])

    def test_catch_variable_is_a_string(self) -> None:
        self.assertTrue(compile_source("try { print(1); } catch (e) { let n: integer = e; }").diagnostics)
        compile_ok('try { print(1); } catch (e) { let s: string = e + "!"; }')


if __name__ == "__main__":
    unittest.main()
