"""Persona 3 · Integración del generador MIPS (TAC -> archivo .asm), uso del
simulador MARS (rúbrica: 1 punto) y la interfaz.

Verifica que:

* no se genere MIPS si hay errores léxicos, sintácticos o semánticos;
* el MIPS salga del TAC que generó el Proyecto 2 (y de ningún otro lado);
* el archivo ensamblador esté completo y bien formado;
* los errores de generación se reporten como diagnósticos;
* **todos** los ejemplos válidos se ensamblen y ejecuten en MARS con la
  salida esperada (``examples/salidas``), con y sin optimización;
* la línea de comandos y el IDE usen el mismo pipeline.
"""

from __future__ import annotations

import io
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mips_helpers import EXAMPLES, EXPECTED, MarsTestCase, compile_mips, needs_mars  # noqa: E402
from test_examples_rubrica import with_error_uncommented  # noqa: E402

import compilar  # noqa: E402
from activation_tree import build_activation_tree  # noqa: E402
from compiler import GENERATION_KIND, compile_source  # noqa: E402
from mars_runner import mars_available, run_mars  # noqa: E402
from mips_generator import MipsGenerator, generate_mips  # noqa: E402
from mips_runtime import MipsGenerationError  # noqa: E402
from tac import Const, TACInstruction, TACOp  # noqa: E402

VALID = sorted(path for path in EXAMPLES.glob("*.cps") if "errores" not in path.name)
INVALID = sorted(path for path in EXAMPLES.glob("*.cps") if "errores" in path.name)
P3_EXAMPLES = sorted(EXAMPLES.glob("mips_*.cps"))
_LABEL = re.compile(r"^([A-Za-z_][\w.$]*):")


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


class PipelineTests(unittest.TestCase):
    def test_no_assembly_when_there_are_previous_errors(self) -> None:
        self.assertGreaterEqual(len(INVALID), 10)
        for path in INVALID:
            with self.subTest(example=path.name):
                result = compile_source(read(path))
                self.assertGreater(len(result.diagnostics), 1)  # reporta varios errores
                self.assertIsNone(result.tac)
                self.assertIsNone(result.mips)

    def test_commented_error_of_each_persona3_example_blocks_generation(self) -> None:
        self.assertGreaterEqual(len(P3_EXAMPLES), 8)
        for path in P3_EXAMPLES:
            with self.subTest(example=path.name):
                result = compile_source(with_error_uncommented(read(path)))
                self.assertGreater(len(result.diagnostics), 0)
                self.assertIsNone(result.mips)

    def test_every_valid_example_generates_assembly(self) -> None:
        for path in VALID:
            with self.subTest(example=path.name):
                result = compile_source(read(path))
                self.assertEqual(result.diagnostics, [])
                self.assertTrue(result.succeeded)
                self.assertGreater(result.mips.instruction_count, 0)

    def test_assembly_is_generated_from_the_tac(self) -> None:
        """Si se cambia el TAC, cambia el MIPS: el ensamblador no se genera
        desde el código fuente ni desde el AST."""
        result = compile_mips("let x: integer = 41; print(x);")
        self.assertIn("# x = 41", result.mips.lines)
        tac = result.tac
        position = next(index for index, item in enumerate(tac.instructions) if item.op is TACOp.ASSIGN)
        original = tac.instructions[position]
        tac.instructions[position] = TACInstruction(TACOp.ASSIGN, original.result, Const(99, "integer"))
        changed = generate_mips(result.symbol_table, tac)
        self.assertIn("# x = 99", changed.lines)
        self.assertIn("li $t0, 99", changed.lines)
        # Cada instrucción TAC deja su comentario, en el mismo orden.
        comments = [line[2:] for line in changed.raw_lines if line.startswith("# ")]
        expected = [str(item).strip() for item in tac if item.op not in (TACOp.LABEL, TACOp.BEGIN_FUNC,
                                                                          TACOp.END_FUNC, TACOp.PARAM)]
        tac_comments = [comment for comment in comments if comment in expected]
        self.assertEqual(tac_comments, expected)

    def test_generation_errors_are_reported_as_diagnostics(self) -> None:
        error = MipsGenerationError("instrucción imposible", TACInstruction(TACOp.TRY_END, line=3))
        with mock.patch("compiler.generate_mips", side_effect=error):
            result = compile_source("let x: integer = 1;\n\nprint(x);")
        self.assertIsNotNone(result.tac)
        self.assertIsNone(result.mips)
        self.assertFalse(result.succeeded)
        self.assertEqual(len(result.diagnostics), 1)
        diagnostic = result.diagnostics[0]
        self.assertEqual((diagnostic.kind, diagnostic.line, diagnostic.symbol), (GENERATION_KIND, 3, "MIPS"))
        self.assertIn("instrucción imposible", diagnostic.description)

    def test_internal_errors_do_not_crash_the_compiler(self) -> None:
        with mock.patch("compiler.generate_mips", side_effect=KeyError("x")):
            result = compile_source("print(1);")
        self.assertIsNone(result.mips)
        self.assertIn("Error interno", result.diagnostics[0].description)

    def test_unknown_tac_instruction_is_rejected(self) -> None:
        result = compile_mips("print(1);")
        generator = MipsGenerator(result.symbol_table, result.tac)
        with self.assertRaises(MipsGenerationError):
            generator.translate(TACInstruction(TACOp.BEGIN_FUNC, arg1=Const(1, "integer")))

    def test_assembly_only_on_request(self) -> None:
        self.assertIsNone(compile_source("print(1);", assembly=False).mips)


class AssemblyFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.program = compile_mips(read(EXAMPLES / "mips_programa_completo.cps")).mips
        self.lines = self.program.lines

    def test_sections_and_entry_point(self) -> None:
        lines = self.lines
        self.assertLess(lines.index(".data"), lines.index(".text"))
        text = lines[lines.index(".text") + 1:]
        first = next(line for line in text if not line.startswith(("#", ".")))
        self.assertEqual(first, "main:")  # MARS empieza en la primera instrucción
        self.assertIn(".globl main", text)
        self.assertEqual(lines.count("main:"), 1)
        self.assertEqual(lines[-2:], ["li $v0, 10", "syscall"])  # salida de p3_uncaught

    def test_labels_are_unique_and_every_reference_is_defined(self) -> None:
        defined = [match.group(1) for line in self.lines if (match := _LABEL.match(line))]
        self.assertEqual(len(defined), len(set(defined)))
        references = set()
        for line in self.lines:
            code = line.split("#", 1)[0].strip()
            if _LABEL.match(code) and not re.match(r"^[\w.$]+:\s+\.", code):
                continue
            match = re.match(r"^(?:j|jal|beq|bne|la)\s.*?([A-Za-z_][\w.$]*)$", code)
            if match:
                references.add(match.group(1))
            references.update(re.findall(r"\b(?:fn_\w+|p[23]_\w+|L\d+)\b", code.split(":", 1)[-1]))
        self.assertTrue(references <= set(defined), references - set(defined))

    def test_every_class_has_its_tables_and_every_function_its_code(self) -> None:
        for label in ("p3_vt_Estudiante:", "p3_vt_Becado:", "p3_members_Becado:",
                      "fn_Becado_promedio:", "fn_ordenar:", "fn_mcd:", "p3_throw:"):
            self.assertIn(label, self.lines)

    def test_formatted_text_is_indented(self) -> None:
        text = self.program.text.splitlines()
        self.assertIn("main:", text)
        self.assertIn("    la $gp, globales", text)
        self.assertTrue(text[0].startswith("# Programa generado"))

    def test_optimization_report(self) -> None:
        self.assertLess(self.program.instruction_count, self.program.raw_instruction_count)
        self.assertGreater(self.program.peephole.total, 0)
        self.assertEqual(compile_mips("print(1);", optimize=False).mips.peephole.total, 0)


@needs_mars
class MarsSimulatorTests(MarsTestCase):
    def test_every_valid_example_runs_in_mars_with_the_expected_output(self) -> None:
        missing = [path.name for path in VALID if not (EXPECTED / f"{path.stem}.txt").is_file()]
        self.assertEqual(missing, [])
        for path in VALID:
            with self.subTest(example=path.name):
                expected = read(EXPECTED / f"{path.stem}.txt").rstrip("\n")
                # Un error sin atrapar termina el programa dentro de una función.
                balanced = path.stem != "mips_error_no_atrapado"
                self.assert_runs(read(path), expected, balanced=balanced)

    def test_activation_tree_of_a_complete_program(self) -> None:
        result = compile_mips(read(EXAMPLES / "mips_funciones_recursion.cps"), trace=True)
        run = run_mars(result.mips.text)
        tree = build_activation_tree(run.output + "\n")
        self.assertEqual(tree.count("hanoi"), 2 ** 6 - 1)  # hanoi(5) hace 63 activaciones
        self.assertEqual(tree.count("potencia"), 11 + 5 + 11)
        self.assertEqual(tree.count("siguiente"), 3)

    def test_infinite_loops_are_stopped(self) -> None:
        run = run_mars(compile_mips("let i = 0; while (true) { i = i + 1; }").mips.text, steps=20000)
        self.assertFalse(run.ok)
        self.assertIn("máximo de instrucciones", run.problem)


class CommandLineTests(unittest.TestCase):
    def run_cli(self, *args: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = compilar.main(list(args))
        return code, out.getvalue(), err.getvalue()

    def test_writes_the_asm_and_tac_files(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "programa.asm"
            code, out, _ = self.run_cli(str(EXAMPLES / "mips_basicos.cps"), "-o", str(output), "--tac")
            self.assertEqual(code, 0)
            self.assertIn(".text", output.read_text(encoding="utf-8"))
            self.assertIn("print", output.with_suffix(".tac").read_text(encoding="utf-8"))
            self.assertIn("MIPS guardado", out)

    def test_reports_all_errors_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "malo.asm"
            code, _, err = self.run_cli(str(EXAMPLES / "errores_semanticos_medio.cps"), "-o", str(output))
            self.assertEqual(code, 1)
            self.assertFalse(output.exists())
            self.assertGreater(err.count("[Semántico]"), 1)

    @unittest.skipUnless(mars_available(), "MARS no disponible")
    def test_runs_in_mars_and_draws_the_activation_tree(self) -> None:
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "recursion.asm"
            code, out, _ = self.run_cli(
                str(EXAMPLES / "08_recursividad.cps"), "-o", str(output), "--ejecutar", "--arbol"
            )
        self.assertEqual(code, 0)
        self.assertIn("---- salida de MARS ----\n120\n8\n1\n", out)
        self.assertIn("└── factorial(4)", out)


class InterfaceTests(unittest.TestCase):
    """El IDE muestra el MIPS y lo ejecuta en MARS (sin abrir diálogos)."""

    def setUp(self) -> None:
        try:
            import tkinter as tk

            self.root = tk.Tk()
        except Exception as error:  # noqa: BLE001 - sin pantalla no se puede probar el IDE
            self.skipTest(f"Tkinter no disponible: {error}")
        self.root.withdraw()
        from ui import CompiscriptApp

        self.app = CompiscriptApp(self.root)

    def tearDown(self) -> None:
        self.root.destroy()

    def load(self, name: str) -> None:
        path = EXAMPLES / name
        self.app._load_source(path, read(path))
        self.app.analyze()

    def test_shows_mips_after_compiling(self) -> None:
        self.load("mips_herencia.cps")
        self.assertIn("INSTRUCCIONES", self.app.mips_summary_label.cget("text"))
        self.assertIn("p3_vt_Director:", self.app.mips_text.get("1.0", "end"))
        self.app.show_raw_mips.set(True)
        self.app._refresh_mips_text()
        raw = self.app.mips_text.get("1.0", "end")
        self.assertEqual(raw.strip(), self.app.last_compilation.mips.raw_text.strip())

    def test_errors_clear_the_mips_tab(self) -> None:
        self.load("errores_semanticos_bajo.cps")
        self.assertEqual(self.app.mips_summary_label.cget("text"), "NO GENERADO")
        self.assertEqual(self.app.mips_text.get("1.0", "end").strip(), "")

    @unittest.skipUnless(mars_available(), "MARS no disponible")
    def test_runs_in_mars_and_shows_the_activation_tree(self) -> None:
        self.load("mips_try_catch.cps")
        self.app._run_worker(self.app.last_source, True)  # mismo trabajo que el hilo, sin esperar
        self.app._running = True
        self.app._poll_run()
        output = self.app.run_output_text.get("1.0", "end")
        self.assertIn("1: Índice de arreglo fuera de rango", output)
        self.assertIn("3628800", output)
        self.assertIn("(interrumpida por excepción)", self.app.run_tree_text.get("1.0", "end"))
        self.assertEqual(self.app.run_summary_label.cget("text"), "EJECUTADO")


if __name__ == "__main__":
    unittest.main()
