"""Pruebas de la representación del TAC (operandos, instrucciones, programa)."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from tac import (  # noqa: E402
    Const,
    Label,
    Name,
    TACError,
    TACInstruction,
    TACOp,
    TACProgram,
    Temp,
    Var,
)


class OperandTests(unittest.TestCase):
    def test_temporaries_and_labels(self) -> None:
        self.assertEqual(str(Temp(3)), "t3")
        self.assertEqual(str(Label("L7")), "L7")
        self.assertEqual(str(Name("Perro")), "Perro")

    def test_variable_ignores_symbol_for_equality_and_printing(self) -> None:
        self.assertEqual(Var("x", symbol=object()), Var("x", symbol=object()))
        self.assertEqual(str(Var("x$1")), "x$1")

    def test_constants_of_every_type(self) -> None:
        self.assertEqual(str(Const(42, "integer")), "42")
        self.assertEqual(str(Const(-3, "integer")), "-3")
        self.assertEqual(str(Const(True, "boolean")), "true")
        self.assertEqual(str(Const(False, "boolean")), "false")
        self.assertEqual(str(Const(None, "null")), "null")
        self.assertEqual(str(Const("hola", "string")), '"hola"')

    def test_string_constants_are_escaped(self) -> None:
        self.assertEqual(str(Const('di "hola"\n', "string")), r'"di \"hola\"\n"')
        self.assertEqual(str(Const("a\\b", "string")), r'"a\\b"')


class InstructionFormatTests(unittest.TestCase):
    def check(self, expected: str, *args) -> None:
        self.assertEqual(str(TACInstruction(*args)), expected)

    def test_copy_and_arithmetic(self) -> None:
        a, b, t1 = Var("a"), Var("b"), Temp(1)
        self.check("x = t1", TACOp.ASSIGN, Var("x"), t1)
        self.check("t1 = a + b", TACOp.ADD, t1, a, b)
        self.check("t1 = a - b", TACOp.SUB, t1, a, b)
        self.check("t1 = a * b", TACOp.MUL, t1, a, b)
        self.check("t1 = a / b", TACOp.DIV, t1, a, b)
        self.check("t1 = a % b", TACOp.MOD, t1, a, b)
        self.check('t1 = concat a, "!"', TACOp.CONCAT, t1, a, Const("!", "string"))

    def test_relational_and_unary(self) -> None:
        a, b, t1 = Var("a"), Var("b"), Temp(1)
        for op, symbol in [
            (TACOp.LT, "<"), (TACOp.LE, "<="), (TACOp.GT, ">"),
            (TACOp.GE, ">="), (TACOp.EQ, "=="), (TACOp.NE, "!="),
        ]:
            self.check(f"t1 = a {symbol} b", op, t1, a, b)
        self.check("t1 = minus a", TACOp.NEG, t1, a)
        self.check("t1 = not a", TACOp.NOT, t1, a)

    def test_jumps(self) -> None:
        self.check("L1:", TACOp.LABEL, Label("L1"))
        self.check("goto L1", TACOp.GOTO, Label("L1"))
        self.check("if t1 goto L2", TACOp.IF_TRUE, Label("L2"), Temp(1))
        self.check("ifFalse t1 goto L2", TACOp.IF_FALSE, Label("L2"), Temp(1))

    def test_functions(self) -> None:
        self.check("begin_func suma", TACOp.BEGIN_FUNC, None, Name("suma"))
        self.check("begin_func suma, 8", TACOp.BEGIN_FUNC, None, Name("suma"), Const(8, "integer"))
        self.check("end_func suma", TACOp.END_FUNC, None, Name("suma"))
        self.check("param a", TACOp.PARAM, None, Var("a"))
        self.check("t1 = call suma, 2", TACOp.CALL, Temp(1), Name("suma"), Const(2, "integer"))
        self.check("call saludar, 0", TACOp.CALL, None, Name("saludar"), Const(0, "integer"))
        self.check("return t1", TACOp.RETURN, None, Temp(1))
        self.check("return", TACOp.RETURN)

    def test_arrays_objects_and_print(self) -> None:
        t1, t2 = Temp(1), Temp(2)
        self.check("t1 = new_array 3", TACOp.NEW_ARRAY, t1, Const(3, "integer"))
        self.check("t2 = t1[0]", TACOp.INDEX_LOAD, t2, t1, Const(0, "integer"))
        self.check("t1[0] = 5", TACOp.INDEX_STORE, t1, Const(0, "integer"), Const(5, "integer"))
        self.check("t1 = len lista", TACOp.LENGTH, t1, Var("lista"))
        self.check("t1 = new Perro", TACOp.NEW_OBJECT, t1, Name("Perro"))
        self.check("t2 = t1.nombre", TACOp.FIELD_LOAD, t2, t1, Name("nombre"))
        self.check('t1.nombre = "Toby"', TACOp.FIELD_STORE, t1, Name("nombre"), Const("Toby", "string"))
        self.check("print t1", TACOp.PRINT, None, t1)

    def test_line_is_not_printed(self) -> None:
        instruction = TACInstruction(TACOp.ASSIGN, Var("x"), Const(1, "integer"), line=12)
        self.assertEqual(instruction.line, 12)
        self.assertEqual(str(instruction), "x = 1")


class InvalidInstructionTests(unittest.TestCase):
    """Casos fallidos: una instrucción incompleta se rechaza al crearla."""

    def test_binary_without_second_operand(self) -> None:
        with self.assertRaisesRegex(TACError, "arg2"):
            TACInstruction(TACOp.ADD, Temp(1), Var("a"))

    def test_assignment_without_destination(self) -> None:
        with self.assertRaisesRegex(TACError, "result"):
            TACInstruction(TACOp.ASSIGN, None, Var("a"))

    def test_conditional_jump_without_label(self) -> None:
        with self.assertRaises(TACError):
            TACInstruction(TACOp.IF_FALSE, None, Temp(1))

    def test_call_without_argument_count(self) -> None:
        with self.assertRaises(TACError):
            TACInstruction(TACOp.CALL, Temp(1), Name("f"))

    def test_program_emit_validates_too(self) -> None:
        program = TACProgram()
        with self.assertRaises(TACError):
            program.emit(TACOp.MUL, Temp(1), Var("a"))
        self.assertEqual(len(program), 0)


class ProgramTests(unittest.TestCase):
    def test_emit_keeps_order_and_line(self) -> None:
        program = TACProgram()
        program.emit(TACOp.MUL, Temp(1), Var("b"), Const(5, "integer"), line=3)
        program.emit(TACOp.ADD, Temp(1), Var("a"), Temp(1), line=3)
        program.emit(TACOp.ASSIGN, Var("x"), Temp(1), line=3)
        self.assertEqual(program.lines(), ["t1 = b * 5", "t1 = a + t1", "x = t1"])
        self.assertEqual([item.line for item in program], [3, 3, 3])
        self.assertIs(program[2].op, TACOp.ASSIGN)

    def test_render_indents_everything_except_labels_and_function_limits(self) -> None:
        program = TACProgram()
        program.emit(TACOp.BEGIN_FUNC, arg1=Name("f"))
        program.emit(TACOp.LABEL, Label("L1"))
        program.emit(TACOp.ASSIGN, Var("x"), Const(1, "integer"))
        program.emit(TACOp.GOTO, Label("L1"))
        program.emit(TACOp.END_FUNC, arg1=Name("f"))
        self.assertEqual(
            program.render(),
            "begin_func f\nL1:\n    x = 1\n    goto L1\nend_func f",
        )


if __name__ == "__main__":
    unittest.main()
