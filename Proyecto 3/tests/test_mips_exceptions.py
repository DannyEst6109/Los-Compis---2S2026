"""Persona 3 · try/catch en MIPS (rúbrica: 2 puntos).

Cubre la pila de manejadores (``try_begin``/``try_end``), cada error en
tiempo de ejecución que puede atraparse, la restauración de ``$fp``/``$sp``
al descartar marcos, ``break``/``continue``/``return`` dentro de un
``try``, ``try`` anidados, errores sin atrapar y el árbol de activación de
una ejecución con excepciones.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mips_helpers import EXAMPLES, EXPECTED, MarsTestCase, compile_mips, instructions, needs_mars  # noqa: E402

from activation_tree import build_activation_tree, render_activation_tree, strip_trace  # noqa: E402
from mars_runner import run_mars  # noqa: E402
from mips_exceptions import ExceptionTranslator  # noqa: E402
from mips_frames import FrameModel  # noqa: E402
from mips_registers import STRING_TAG, MipsRegisters  # noqa: E402
from mips_runtime import EXCEPTION_LABEL, HANDLER_LABEL, THROW_LABEL  # noqa: E402
from tac import Label, TACInstruction, TACOp  # noqa: E402

SIMPLE = "let x: integer = 1; try { x = 10 / x; } catch (e) { print(e); }"


class HandlerTranslationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = compile_mips(SIMPLE)
        self.registers = MipsRegisters(FrameModel(self.result.symbol_table))
        self.exceptions = ExceptionTranslator(self.registers)

    def test_try_begin_pushes_a_handler_on_the_stack(self) -> None:
        lines = self.exceptions.translate(TACInstruction(TACOp.TRY_BEGIN, Label("L1")), None)
        self.assertEqual(lines, [
            "addiu $sp, $sp, -12",
            f"lw $t9, {HANDLER_LABEL}", "sw $t9, 8($sp)",  # manejador anterior
            "la $t9, L1", "sw $t9, 4($sp)",  # dirección del catch
            "sw $fp, 0($sp)",  # marco que lo instala
            f"sw $sp, {HANDLER_LABEL}",
        ])

    def test_try_end_pops_the_handler(self) -> None:
        self.assertEqual(self.exceptions.translate(TACInstruction(TACOp.TRY_END), None), [
            "lw $t9, 8($sp)", f"sw $t9, {HANDLER_LABEL}", "addiu $sp, $sp, 12",
        ])

    def test_catch_variable_receives_the_message_as_a_string(self) -> None:
        get = next(instruction for instruction in self.result.tac if instruction.op is TACOp.GET_EXCEPTION)
        lines = self.exceptions.translate(get, None)
        self.assertEqual(lines[:2], [f"lw $t9, {EXCEPTION_LABEL}", f"li $a3, {STRING_TAG}"])

    def test_runtime_routines_only_when_needed(self) -> None:
        self.assertNotIn(f"{THROW_LABEL}:", compile_mips("let x: integer = 2; print(x * 3);").mips.lines)
        lines = self.result.mips.lines
        self.assertIn(f"{THROW_LABEL}:", lines)
        self.assertIn(f"{HANDLER_LABEL}: .word 0", lines)

    def test_values_are_in_memory_before_installing_the_handler(self) -> None:
        lines = compile_mips("let x: integer = 5; try { print(x); } catch (e) { print(e); }", optimize=False).mips.lines
        start = lines.index("# try_begin L1")
        code = instructions(lines[start:start + 4])
        self.assertTrue(code[0].startswith("sw "), code)  # x se guarda antes de addiu $sp


@needs_mars
class ExceptionExecutionTests(MarsTestCase):
    def test_every_runtime_error_can_be_caught(self) -> None:
        cases = [
            ("let a = 0;", "print(10 / a);", "División por cero"),
            ("let a = 0;", "print(10 % a);", "División por cero"),
            ("let v: integer[] = [1];", "print(v[1]);", "Índice de arreglo fuera de rango"),
            ("let v: integer[] = [1];", "v[-1] = 2;", "Índice de arreglo fuera de rango"),
            ("let v: integer[] = null;", "print(v[0]);", "Arreglo nulo"),
            ('function sufijo(a): string { return a + "x"; }', "print(sufijo(null));", "Cadena nula"),
            ("class C { let x: integer; } let c: C = null;", "print(c.x);", "Acceso a un objeto nulo"),
            ("class C { let x: integer; } let c: C = null;", "c.x = 1;", "Acceso a un objeto nulo"),
            ("class C { function f() { } } let c: C = null;", "c.f();", "Acceso a un objeto nulo"),
            (
                # «x» está en posiciones distintas en C y D, y E no lo tiene.
                "class C { let x: integer; } class D { let y: integer; let x: integer; }"
                " class E { let z: integer; } function leer(o) { print(o.x); }",
                "leer(new E());",
                "El objeto no tiene el miembro solicitado",
            ),
        ]
        for declarations, statement, message in cases:
            with self.subTest(statement=statement):
                self.assert_runs(
                    f'{declarations} try {{ {statement} }} catch (e) {{ print("atrapado: " + e); }} print("sigue");',
                    f"atrapado: {message}\nsigue",
                )

    def test_statements_after_the_error_are_skipped_and_memory_is_current(self) -> None:
        self.assert_runs("""
            let x = 1; let lista: integer[] = [1, 2];
            try {
              x = 5;
              lista[0] = 9;
              print(lista[7]);
              x = 100;
            } catch (e) { print(x); print(lista[0]); }
            print(x);
        """, "5\n9\n5")

    def test_errors_inside_called_functions_discard_their_frames(self) -> None:
        # assert_runs también verifica que $sp y $fp terminen en el tope de la pila.
        self.assert_runs("""
            function baja(n: integer): integer { if (n == 0) { return 1 / n; } return baja(n - 1) + 1; }
            function medio(n: integer): integer { let local = 7; return baja(n) + local; }
            let veces = 0;
            for (let i = 0; i < 200; i = i + 1) {
              try { medio(i % 15); } catch (e) { veces = veces + 1; }
            }
            print(veces);
            function seguro(n: integer): integer {
              try { return baja(n); } catch (e) { print(e); }
              return -1;
            }
            print(seguro(4));
            print(veces + 1);
        """, "200\nDivisión por cero\n-1\n201")

    def test_break_continue_and_return_inside_try(self) -> None:
        self.assert_runs("""
            let v: integer[] = [1, 2, 3];
            let i = 0; let errores = 0;
            while (i < 8) {
              i = i + 1;
              try {
                if (i == 2) { continue; }
                if (i == 6) { break; }
                print(v[i]);
              } catch (e) { errores = errores + 1; }
            }
            print(errores);
            function primero(lista: integer[]): integer {
              foreach (x in lista) { try { return x * 10; } catch (e) { } }
              return 0;
            }
            print(primero(v));
            try { print(v[9]); } catch (e) { print("el manejador del ciclo ya no existe"); }
        """, "2\n3\n10\nel manejador del ciclo ya no existe")

    def test_nested_try_and_errors_inside_catch(self) -> None:
        self.assert_runs("""
            let w: integer[] = [1];
            try {
              try { print(1 / 0); } catch (interno) { print("a: " + interno); print(w[3]); }
              print("no se imprime");
            } catch (externo) { print("b: " + externo); }
            try {
              try { print(2); } catch (e) { print("nunca"); }
              print(1 / 0);
            } catch (e) { print("c: " + e); }
        """, "a: División por cero\nb: Índice de arreglo fuera de rango\n2\nc: División por cero")

    def test_catch_variable_is_a_real_string(self) -> None:
        self.assert_runs("""
            try { print(5 / 0); } catch (e) {
              print(e == "División por cero");
              let mensaje: string = "Error: " + e;
              print(mensaje);
            }
        """, "1\nError: División por cero")

    def test_uncaught_error_stops_the_program_with_a_message(self) -> None:
        result = compile_mips("function f(a: integer): integer { return 9 / a; } print(1); print(f(0)); print(2);")
        run = run_mars(result.mips.text)
        self.assertEqual(run.returncode, 0)
        self.assertEqual(run.output, "1\nError en tiempo de ejecución: División por cero")

    def test_activation_tree_marks_frames_discarded_by_an_exception(self) -> None:
        result = compile_mips("""
            function baja(n: integer): integer { if (n == 0) { return 1 / n; } return baja(n - 1); }
            function intenta(): integer { try { return baja(2); } catch (e) { print(e); } return 0; }
            print(intenta());
        """, trace=True)
        run = run_mars(result.mips.text)
        tree = render_activation_tree(build_activation_tree(run.output + "\n"))
        self.assertEqual(tree, "\n".join([
            "main",
            "└── intenta()",
            "    └── baja(2)  (interrumpida por excepción)",
            "        └── baja(1)  (interrumpida por excepción)",
            "            └── baja(0)  (interrumpida por excepción)",
        ]))
        self.assertEqual(strip_trace(run.output + "\n"), "División por cero\n0\n")

    def test_exception_example_files(self) -> None:
        for name in ("mips_try_catch", "11_try_catch", "tac_try_catch"):
            with self.subTest(example=name):
                source = (EXAMPLES / f"{name}.cps").read_text(encoding="utf-8")
                expected = (EXPECTED / f"{name}.txt").read_text(encoding="utf-8").rstrip("\n")
                self.assert_runs(source, expected)


if __name__ == "__main__":
    unittest.main()
