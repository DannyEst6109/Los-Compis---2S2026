"""Pruebas de Persona 2 con el TAC real y el traductor de funciones."""

import unittest

from mips_doubles import TinyMips, compile_source, mars_command, run_mars
from mips_basic import BasicTranslator
from mips_frames import FrameModel
from mips_functions import FunctionTranslator
from mips_peephole import optimize_mips
from mips_registers import MipsRegisters
from tac import Const, TACOp


def assemble(source, fault_label=None):
    """Integra las operaciones básicas con saltos de prueba de Persona 3."""
    result = compile_source(source)
    assert result.succeeded, result.diagnostics
    registers = MipsRegisters(FrameModel(result.symbol_table))
    functions = FunctionTranslator(registers.model, registers)
    basic = BasicTranslator(registers, fault_label)
    main, definitions = [], []
    body = None
    for instruction in result.tac:
        op = instruction.op
        unit = functions.unit
        out = main if body is None else body
        if op is TACOp.BEGIN_FUNC:
            out += registers.spill(unit)
            functions.begin_function(instruction)
            body = []
        elif op is TACOp.END_FUNC:
            definitions += functions.end_function(instruction, body)
            body = None
        elif op is TACOp.PARAM:
            out += functions.translate_param(instruction)
        elif op is TACOp.CALL:
            out += functions.translate_call(instruction)
        elif op is TACOp.RETURN:
            out += functions.translate_return(instruction)
            registers.forget()
        elif op in (TACOp.GOTO, TACOp.LABEL, TACOp.IF_TRUE, TACOp.IF_FALSE):
            out += registers.spill(unit)
            target = instruction.result
            if op is TACOp.LABEL:
                out.append(f"{target}:")
            elif op is TACOp.GOTO:
                out.append(f"j {target}")
            else:
                lines, register = registers.value_register(instruction.arg1, unit)
                branch = "bne" if op is TACOp.IF_TRUE else "beq"
                out += [*lines, f"{branch} {register}, $zero, {target}"]
            registers.forget()
        else:
            out += basic.translate(instruction, unit)
    main += registers.spill(None)
    return [
        ".data", *functions.data_lines(), *registers.data_lines(),
        ".text", *functions.main_program(main), *definitions,
    ]


class RegisterTests(unittest.TestCase):
    def test_reuse_spill_reload_and_forget(self):
        result = compile_source("let x: integer = 11;")
        registers = MipsRegisters(FrameModel(result.symbol_table))
        variable = result.tac[0].result
        self.assertEqual(registers.assign_from(variable, None, "$v0"), ["move $t0, $v0", "sb $zero, 4($gp)"])
        self.assertEqual(registers.value_register(variable, None), ([], "$t0"))
        for value in range(5):
            registers.value_register(Const(value, "integer"), None)
        self.assertEqual(
            registers.value_register(Const(5, "integer"), None),
            (["sw $t0, 0($gp)", "li $t0, 5"], "$t0"),
        )
        self.assertEqual(registers.spill(None), [])
        self.assertEqual(registers.value_register(variable, None), (["lw $t1, 0($gp)"], "$t1"))
        registers.forget()
        self.assertEqual(registers.value_register(variable, None), (["lw $t0, 0($gp)"], "$t0"))

    def test_spill_keeps_values_valid_and_writes_boolean_as_byte(self):
        result = compile_source("let b: boolean = true;")
        registers = MipsRegisters(FrameModel(result.symbol_table))
        variable = result.tac[0].result
        registers.assign_from(variable, None, "$v0")
        self.assertEqual(registers.spill(None), ["sb $t0, 0($gp)"])
        self.assertEqual(registers.spill(None), [])
        self.assertEqual(registers.load_into(variable, None, "$v0"), ["move $v0, $t0"])
        registers.forget()
        self.assertEqual(registers.load_into(variable, None, "$v0"), ["lbu $v0, 0($gp)"])

    def test_branch_merges_and_recursive_calls_use_real_allocator(self):
        program = assemble("""
            let x: integer = 1;
            function sum(n: integer): integer {
                if (n <= 0) { return x; }
                return n + sum(n - 1);
            }
            if (x == 1 && x < 2) { x = 9; } else { x = 100; }
            print(sum(4));
        """)
        self.assertEqual(TinyMips(program).run().output, [19])
        self.assertEqual(TinyMips(optimize_mips(program)).run().output, [19])

    def test_saved_registers_are_preserved_and_pressure_spills(self):
        declarations = "\n".join(f"let x{i}: integer = {i};" for i in range(1, 17))
        total = " + ".join(f"x{i}" for i in range(1, 17))
        program = assemble(f"function total(): integer {{ {declarations} return {total}; }} print(total());")
        self.assertTrue(any(line.startswith("sw $s7,") for line in program))
        self.assertTrue(any(line.startswith("lw $s7,") for line in program))
        self.assertEqual(TinyMips(program).run().output, [136])

    def test_call_invalidates_captured_and_global_values(self):
        program = assemble("""
            let global: integer = 10;
            function outer(): integer {
                let captured: integer = 1;
                function change() {
                    captured = captured + 2;
                    global = global + 4;
                }
                let before: integer = captured + global;
                change();
                return before + captured + global;
            }
            print(outer());
            print(global);
        """)
        self.assertEqual(TinyMips(program).run().output, [28, 14])


class PeepholeTests(unittest.TestCase):
    def test_transformations_individually(self):
        cases = [
            (["move $t0, $t0"], []),
            (["addiu $t0, $t1, 0"], ["move $t0, $t1"]),
            (["sll $t0, $t1, 0"], ["move $t0, $t1"]),
            (["addu $t0, $zero, $t1"], ["move $t0, $t1"]),
            (["subu $t0, $t1, $zero"], ["move $t0, $t1"]),
            (["li $t0, 10", "li $t0, 10"], ["li $t0, 10"]),
            (["j L1", "# comentario", "L1:"], ["# comentario", "L1:"]),
        ]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(optimize_mips(raw), expected)

    def test_keeps_labels_as_barriers_and_real_branches(self):
        raw = ["li $t0, 1", "L0:", "li $t0, 1", "j L1", "L2:", "L1:", "sll $t1, $t0, 2"]
        self.assertEqual(optimize_mips(raw), raw)


@unittest.skipUnless(mars_command(), "MARS requiere Java y un archivo Mars4_5.jar")
class BasicMarsTests(unittest.TestCase):
    def assert_output(self, source, expected):
        raw = assemble(source)
        for lines in (raw, optimize_mips(raw)):
            result = run_mars(lines)
            self.assertEqual(result.returncode, 0, (result.output, result.stderr))
            self.assertEqual(result.output, expected)
            self.assertEqual(result.registers, {"$sp": TinyMips.STACK_TOP, "$fp": TinyMips.STACK_TOP})

    def test_arithmetic_logic_and_variables(self):
        self.assert_output("""
            const base: integer = 13;
            let a: integer = base;
            print(-a / 3); print(-a % 3);
            print((a + 2) * 3 - 1);
            print(a > 1 && !(a <= 3));
            print(a < 1 || a >= 13);
            print(a != 13); print(a == 13);
            print(2147483647 + 1);
            print(a + 0); print(a - 32768); print(a - -32768);
        """, "-4\n-1\n44\n1\n1\n0\n1\n-2147483648\n13\n-32755\n32781")

    def test_peephole_preserves_register_values(self):
        raw = [
            ".text", "main:", "li $t1, -123", "li $t1, -123", "addiu $t2, $t1, 0",
            "sll $t3, $t2, 0", "addu $t4, $zero, $t3", "subu $t5, $t4, $zero",
            "move $t5, $t5", "j L1", "L1:", "li $v0, 10", "syscall",
        ]
        optimized = optimize_mips(raw)
        self.assertLess(len(optimized), len(raw))
        for lines in (raw, optimized):
            result = run_mars(lines, ("$t1", "$t2", "$t3", "$t4", "$t5"))
            self.assertEqual(result.returncode, 0, (result.output, result.stderr))
            self.assertEqual(result.registers, {f"$t{i}": -123 for i in range(1, 6)})

    def test_arrays_aliases_nested_boolean_and_foreach(self):
        self.assert_output("""
            let a: integer[][] = [[1, 2], [3, 4]];
            let b: integer[] = a[0];
            b[1] = 10;
            let sum: integer = 0;
            foreach (x in a[0]) { sum = sum + x; }
            print(sum); print(a[1][0]);
            let empty: integer[] = [];
            foreach (x in empty) { print(x); }
            let flags: boolean[] = [true, false];
            flags[1] = flags[0]; print(flags[1]);
        """, "11\n3\n1")

    def test_strings_and_typed_temporaries(self):
        self.assert_output("""
            function suffix(): string { return "ñ"; }
            let text: string = "a" + suffix();
            print(text); print(text == ("a" + "ñ")); print(text != "a");
            print(text == null); print("" + "ok");
        """, "añ\n1\n1\n0\nok")

    def test_equality_without_parameter_types(self):
        self.assert_output("""
            function iguales(a, b): boolean { return a == b; }
            function distintos(a, b): boolean { return a != b; }
            print(iguales("ab", "a" + "b"));
            print(iguales("ca" + "fé", "c" + "afé"));
            print(distintos("ca" + "fé", "ca" + "fe"));
            print(iguales("" + "", ""));
            print(iguales("ab", null));
            print(iguales(null, null));
            print(iguales(1024, 1024));
            print(distintos(-3, 3));
        """, "1\n1\n1\n1\n0\n1\n1\n1")

    def test_print_type_follows_arguments_returns_and_arrays(self):
        self.assert_output("""
            function mostrar(x) { print(x); }
            function devolver(x): string { return x; }
            function reenviar(x) {
                let copia = x;
                function interna() { mostrar(copia); }
                interna();
            }
            mostrar("hola"); mostrar(42); mostrar(true); mostrar(null);
            reenviar("café"); reenviar(17);
            let palabras: string[] = ["casa", "luz"];
            palabras[1] = devolver("al" + "ba");
            mostrar(palabras[1]);
            function argumentos(a, b, c, d, e, f) { mostrar(a); mostrar(f); }
            argumentos("primero", 2, 3, 4, 5, "último");
        """, "hola\n42\n1\nnull\ncafé\n17\nalba\nprimero\núltimo")

    def test_invalid_runtime_operands(self):
        for source, expected in [
            ("print(5 / 0); print(2);", "División por cero"),
            ("let a: integer[] = []; print(a[0]);", "Índice de arreglo fuera de rango"),
            ("let a: integer[] = [1]; a[-1] = 0;", "Índice de arreglo fuera de rango"),
        ]:
            with self.subTest(source=source):
                self.assert_output(source, expected)

    def test_external_fault_handler_gets_current_memory(self):
        lines = assemble("let x: integer = 42; print(1 / 0);", "handler")
        lines += ["handler:", "lw $a0, 0($gp)", "li $v0, 1", "syscall", "li $v0, 10", "syscall"]
        result = run_mars(lines, ())
        self.assertEqual(result.returncode, 0, (result.output, result.stderr))
        self.assertEqual(result.output, "42")
