"""Pruebas de las secuencias de llamada y retorno (``mips_functions.py``):
prólogo, epílogo, ``return``, paso de parámetros, valor de retorno, enlaces
de acceso, llamadas a métodos, registros ``$s`` y casos fallidos.

La asignación de registros es de Persona 2; aquí se usa el doble de prueba
``MemoryRegisters`` (``mips_doubles.py``), que deja todo en memoria y usa
``$t8`` como registro de paso. Las demás instrucciones del TAC (de Persona 2
y 3) se dejan como comentario."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "tests"))

from mips_doubles import Translation, MemoryRegisters, VALID_EXAMPLES, instructions  # noqa: E402
from mips_functions import FunctionTranslator, MipsFunctionError  # noqa: E402
from tac import Const, Name, TACInstruction, TACOp, Temp  # noqa: E402

FUNCTIONS = """
function suma(a: integer, b: integer): integer { return a + b; }
function f(a: integer, b: boolean): integer {
  let c: integer = a * 2;
  return c;
}
function nada() { print(1); }
function uno(): integer { return 1; }
let resultado: integer = suma(2, 3);
let ok: boolean = true;
print(f(resultado, ok));
nada();
"""

RECURSION = """
function factorial(n: integer): integer {
  if (n <= 1) { return 1; }
  return n * factorial(n - 1);
}
function fib(n: integer): integer {
  if (n < 2) { return n; }
  return fib(n - 1) + fib(n - 2);
}
print(factorial(5) + fib(6));
"""

NESTED = """
function externo(x: integer): integer {
  let y: integer = 1;
  function primero(): integer { return x; }
  function segundo(): integer { return primero() + y; }
  function cuenta(n: integer): integer {
    if (n <= 0) { return 0; }
    return cuenta(n - 1) + 1;
  }
  function medio(): integer {
    function interno(): integer { return segundo() + x; }
    return interno();
  }
  return medio() + cuenta(3) + segundo();
}
print(externo(3));
"""

CLASSES = """
class Animal {
  let nombre: string;
  function constructor(n: string) { this.nombre = n; }
  function hablar(veces: integer, fuerte: boolean): string { return this.nombre; }
  function eco(): string { return hablar(1, false); }
}
let a: Animal = new Animal("Toby");
print(a.hablar(2, true));
"""


class PrologueEpilogueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Translation(FUNCTIONS)

    def test_prologue(self) -> None:
        self.assertEqual(
            self.t.functions["suma"][:6],
            [
                "# begin_func suma, 24",
                "fn_suma:",
                "sw $ra, 16($sp)",
                "sw $fp, 12($sp)",
                "addiu $fp, $sp, 20",
                "addiu $sp, $fp, -24",
            ],
        )

    def test_epilogue(self) -> None:
        self.assertEqual(
            self.t.functions["suma"][-6:],
            ["fn_suma_fin:", "lw $ra, -4($fp)", "move $sp, $fp", "lw $fp, -8($fp)", "jr $ra", "# end_func suma"],
        )

    def test_function_without_parameters(self) -> None:
        self.assertEqual(
            instructions(self.t.functions["nada"])[:5],
            ["fn_nada:", "sw $ra, 8($sp)", "sw $fp, 4($sp)", "addiu $fp, $sp, 12", "addiu $sp, $fp, -12"],
        )

    def test_return_value_goes_to_v0_and_jumps_to_the_epilogue(self) -> None:
        body = self.t.functions["suma"]
        start = body.index("# return t1")
        self.assertEqual(body[start + 1:start + 4], ["# spill", "lw $v0, -24($fp)", "j fn_suma_fin"])

    def test_return_constant(self) -> None:
        body = self.t.functions["uno"]
        start = body.index("# return 1")
        self.assertEqual(body[start + 1:start + 4], ["# spill", "li $v0, 1", "j fn_uno_fin"])

    def test_return_variable_uses_its_slot(self) -> None:
        self.assertIn("lw $v0, -24($fp)", self.t.functions["f"])  # c en +20

    def test_return_without_value(self) -> None:
        translator = Translation(FUNCTIONS).translator
        translator.begin_function(TACInstruction(TACOp.BEGIN_FUNC, None, Name("nada"), Const(12, "integer")))
        lines = translator.translate_return(TACInstruction(TACOp.RETURN))
        self.assertEqual(lines, ["# return", "# spill", "j fn_nada_fin"])

    def test_falling_off_the_end_reaches_the_epilogue(self) -> None:
        body = self.t.functions["nada"]
        self.assertNotIn("j fn_nada_fin", body)
        end = body.index("fn_nada_fin:")
        self.assertEqual(body[end - 2:end], ["# print 1", "# spill"])

    def test_every_return_jumps_to_its_own_epilogue(self) -> None:
        t = Translation(RECURSION)
        for name, lines in t.functions.items():
            jumps = [line for line in lines if line.startswith("j fn_")]
            self.assertEqual(len(jumps), 2, name)  # dos return en cada función
            self.assertEqual(set(jumps), {f"j {t.model.frame(name).epilogue_label}"})

    def test_registers_are_forgotten_at_function_boundaries(self) -> None:
        t = Translation("function g(): integer { return 1; }\nprint(g());")
        events = [event[0] for event in t.registers.events]
        # begin_func: olvida; return: spill; end_func: spill + olvida; llamada: spill + olvida.
        self.assertEqual(events[:4], ["forget", "spill", "spill", "forget"])


class SavedRegisterTests(unittest.TestCase):
    def test_saved_registers_are_stored_and_restored(self) -> None:
        t = Translation(FUNCTIONS, saved={"suma": ["$s1", "$s0"]})
        lines = t.functions["suma"]
        self.assertEqual(
            lines[4:8],
            ["addiu $fp, $sp, 20", "addiu $sp, $fp, -32", "sw $s0, -28($fp)", "sw $s1, -32($fp)"],
        )
        self.assertEqual(
            lines[-8:-4], ["fn_suma_fin:", "lw $s0, -28($fp)", "lw $s1, -32($fp)", "lw $ra, -4($fp)"]
        )
        # El prefijo que reserva el llamador no cambia.
        self.assertIn("addiu $sp, $sp, -20", t.call_to("suma"))

    def test_functions_without_saved_registers_are_unchanged(self) -> None:
        t = Translation(FUNCTIONS, saved={"suma": ["$s0"]})
        self.assertIn("addiu $sp, $fp, -28", t.functions["f"])
        self.assertFalse(any(re.search(r"\$s\d", line) for line in t.functions["f"]))


class CallSequenceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Translation(FUNCTIONS)

    def test_call_with_arguments_and_result(self) -> None:
        self.assertEqual(
            self.t.call_to("suma"),
            [
                "# t1 = call suma, 2",
                "# spill",
                "addiu $sp, $sp, -20",
                "li $t8, 2",
                "sw $t8, 4($sp)",  # a
                "li $t8, 3",
                "sw $t8, 0($sp)",  # b
                "sw $zero, 8($sp)",  # enlace de acceso: suma es de nivel 1
                "jal fn_suma",
                "sw $v0, 8($gp)",  # t1 del código global
            ],
        )

    def test_boolean_argument_uses_a_byte(self) -> None:
        call = self.t.call_to("f")
        self.assertIn("lbu $t8, 4($gp)", call)  # ok
        self.assertIn("sb $t8, 3($sp)", call)  # b: 20 - 16 - 1
        self.assertIn("lw $t8, 0($gp)", call)  # resultado
        self.assertIn("sw $t8, 4($sp)", call)  # a

    def test_procedure_call_has_no_result(self) -> None:
        call = self.t.call_to("nada")
        # nada no tiene parámetros (P = 12): el enlace de acceso va en 0($sp).
        self.assertEqual(instructions(call), ["addiu $sp, $sp, -12", "sw $zero, 0($sp)", "jal fn_nada"])

    def test_registers_are_saved_before_and_forgotten_after_the_call(self) -> None:
        call = self.t.call_to("suma")
        self.assertLess(call.index("# spill"), call.index("addiu $sp, $sp, -20"))
        t = Translation("function g(): integer { return 1; }\nlet x: integer = g();")
        self.assertEqual(t.registers.events[-2:], [("spill", None), ("forget",)])

    def test_reserved_prefix_matches_the_callee(self) -> None:
        for path in VALID_EXAMPLES:
            with self.subTest(example=path.name):
                t = Translation(path.read_text(encoding="utf-8"))
                for _, call in t.calls:
                    target = next(line for line in call if line.startswith(("jal ", "jalr ")))
                    reserve = next(line for line in call if line.startswith("addiu $sp, $sp, -"))
                    if target.startswith("jal "):
                        frame = next(f for f in t.model.frames.values() if f.label == target[4:])
                        self.assertEqual(reserve, f"addiu $sp, $sp, -{frame.prefix_size}")

    def test_sp_only_changes_in_calls_prologues_and_epilogues(self) -> None:
        """Dentro del cuerpo, ``$sp`` sólo cambia al reservar el prefijo de
        una llamada; la función llamada lo restaura al volver."""
        allowed = re.compile(r"^(addiu \$sp, \$sp, -\d+|addiu \$sp, \$fp, -\d+|move \$sp, \$fp)$")
        for path in VALID_EXAMPLES:
            with self.subTest(example=path.name):
                t = Translation(path.read_text(encoding="utf-8"))
                for lines in [*t.functions.values(), t.main]:
                    for line in lines:
                        if re.match(r"^\S+ \$sp,", line):
                            self.assertRegex(line, allowed)
                reserves = sum(1 for line in t.main if line.startswith("addiu $sp, $sp, -"))
                calls = sum(1 for line in t.main if line.startswith(("jal ", "jalr ")))
                self.assertEqual(reserves, calls)


class RecursionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Translation(RECURSION)

    def test_recursive_call_creates_a_new_frame(self) -> None:
        call = self.t.call_to("factorial", caller="factorial")
        self.assertEqual(
            instructions(call),
            [
                "addiu $sp, $sp, -16",
                "lw $t8, -20($fp)",  # t1 = n - 1, en el marco del llamador
                "sw $t8, 0($sp)",  # n de la nueva activación
                "sw $zero, 4($sp)",  # enlace de acceso: P - 12 = 4
                "jal fn_factorial",
                "sw $v0, -20($fp)",  # t1 del llamador
            ],
        )

    def test_caller_values_live_in_its_own_frame(self) -> None:
        """En ``fib(n - 1) + fib(n - 2)`` el primer resultado queda en ``t1``
        del marco del llamador mientras se hace la segunda llamada."""
        calls = self.t.calls_to("fib", caller="fib")
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0][-1], "sw $v0, -20($fp)")  # t1
        self.assertEqual(calls[1][-1], "sw $v0, -24($fp)")  # t2


class AccessLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Translation(NESTED)

    def access_link(self, caller: str | None, callee: str) -> list[str]:
        """Instrucciones que escriben el enlace de acceso: van después del
        último argumento (``sw $t8``) y antes del ``jal``."""
        call = instructions(self.t.call_to(callee, caller))
        jal = call.index(f"jal {self.t.model.frame(callee).label}")
        arguments = [index for index, line in enumerate(call[:jal]) if line.startswith("sw $t8")]
        start = arguments[-1] + 1 if arguments else 1  # 1: después del addiu
        return call[start:jal]

    def test_link_is_the_parent_frame(self) -> None:
        # externo llama a medio (anidada en externo): el enlace es su propio $fp.
        # medio no tiene parámetros: P = 12, así que el enlace va en 0($sp).
        self.assertEqual(self.access_link("externo", "medio"), ["sw $fp, 0($sp)"])
        # medio llama a interno (anidada en medio): también su propio $fp.
        self.assertEqual(self.access_link("medio", "interno"), ["sw $fp, 0($sp)"])

    def test_sibling_call_follows_one_link(self) -> None:
        # segundo llama a primero; las dos están en externo.
        self.assertEqual(self.access_link("segundo", "primero"), ["lw $v1, -12($fp)", "sw $v1, 0($sp)"])

    def test_nested_recursion_follows_one_link(self) -> None:
        # cuenta(n) se llama a sí misma; P = 16, así que el enlace va en 4($sp).
        self.assertEqual(self.access_link("cuenta", "cuenta"), ["lw $v1, -12($fp)", "sw $v1, 4($sp)"])
        # Desde externo, que la contiene, el enlace es el $fp de externo.
        self.assertEqual(self.access_link("externo", "cuenta"), ["sw $fp, 4($sp)"])

    def test_deeper_caller_follows_two_links(self) -> None:
        # interno (nivel 3) llama a segundo (nivel 2, en externo).
        self.assertEqual(
            self.access_link("interno", "segundo"),
            ["lw $v1, -12($fp)", "lw $v1, -12($v1)", "sw $v1, 0($sp)"],
        )

    def test_top_level_functions_get_zero(self) -> None:
        self.assertEqual(self.access_link(None, "externo"), ["sw $zero, 4($sp)"])


class MethodCallTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Translation(CLASSES)

    def test_constructor_receives_this_first(self) -> None:
        call = self.t.call_to("Animal.constructor")
        self.assertEqual(
            instructions(call),
            [
                "addiu $sp, $sp, -20",
                "lw $t8, 4($gp)",  # t1 = new Animal (temporal global)
                "sw $t8, 4($sp)",  # this
                "la $t8, <\"Toby\">",
                "sw $t8, 0($sp)",  # n
                "sw $zero, 8($sp)",
                "jal fn_Animal_constructor",
            ],
        )

    def test_dynamic_dispatch_uses_jalr(self) -> None:
        call = next(lines for lines in self.t.calls_from(None) if "jalr $t8" in lines)
        self.assertEqual(
            instructions(call),
            [
                "addiu $sp, $sp, -24",
                "lw $t8, 0($gp)",  # a -> this
                "sw $t8, 8($sp)",
                "li $t8, 2",
                "sw $t8, 4($sp)",  # veces
                "li $t8, 1",
                "sb $t8, 3($sp)",  # fuerte (boolean)
                "sw $zero, 12($sp)",  # enlace de acceso
                "lw $t8, 4($gp)",  # dirección del método (t1)
                "jalr $t8",
                "sw $v0, 4($gp)",
            ],
        )

    def test_method_called_from_another_method_passes_this(self) -> None:
        call = self.t.calls_from("Animal.eco")[0]
        self.assertIn("jalr $t8", call)
        self.assertEqual(call[3:5], ["lw $t8, -16($fp)", "sw $t8, 8($sp)"])  # this de eco -> this de hablar


class FailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.t = Translation(FUNCTIONS)
        self.tr = FunctionTranslator(self.t.model, MemoryRegisters(self.t.model))

    @staticmethod
    def begin(name: str, size: int | None = None) -> TACInstruction:
        return TACInstruction(TACOp.BEGIN_FUNC, None, Name(name), Const(size, "integer") if size else None)

    @staticmethod
    def call(target, count: int, result=None) -> TACInstruction:
        return TACInstruction(TACOp.CALL, result, target, Const(count, "integer"))

    @staticmethod
    def param(operand) -> TACInstruction:
        return TACInstruction(TACOp.PARAM, None, operand)

    def test_argument_count_does_not_match_the_params(self) -> None:
        self.tr.translate_param(self.param(Const(1, "integer")))
        with self.assertRaises(MipsFunctionError):
            self.tr.translate_call(self.call(Name("suma"), 2))

    def test_argument_count_does_not_match_the_function(self) -> None:
        self.tr.translate_param(self.param(Const(1, "integer")))
        with self.assertRaises(MipsFunctionError) as raised:
            self.tr.translate_call(self.call(Name("suma"), 1))
        self.assertIn("recibe 2 argumentos", str(raised.exception))

    def test_unknown_function(self) -> None:
        with self.assertRaises(MipsFunctionError):
            self.tr.translate_call(self.call(Name("noExiste"), 0))
        with self.assertRaises(MipsFunctionError):
            self.tr.begin_function(self.begin("noExiste"))

    def test_indirect_call_needs_the_method_frame(self) -> None:
        with self.assertRaises(MipsFunctionError):
            self.tr.translate_call(self.call(Temp(1), 0))

    def test_method_frame_must_match_a_named_call(self) -> None:
        with self.assertRaises(MipsFunctionError):
            self.tr.translate_call(self.call(Name("nada"), 0), self.t.model.frame("uno"))

    def test_param_without_call(self) -> None:
        self.tr.begin_function(self.begin("nada"))
        self.tr.translate_param(self.param(Const(1, "integer")))
        with self.assertRaises(MipsFunctionError):
            self.tr.end_function(TACInstruction(TACOp.END_FUNC, None, Name("nada")), [])
        with self.assertRaises(MipsFunctionError):
            self.tr.translate_return(TACInstruction(TACOp.RETURN))
        self.assertEqual(self.tr.pending_params, 1)

    def test_nested_begin_func(self) -> None:
        self.tr.begin_function(self.begin("suma"))
        with self.assertRaises(MipsFunctionError):
            self.tr.begin_function(self.begin("nada"))

    def test_end_func_without_begin_or_for_another_function(self) -> None:
        with self.assertRaises(MipsFunctionError):
            self.tr.end_function(TACInstruction(TACOp.END_FUNC, None, Name("suma")), [])
        self.tr.begin_function(self.begin("suma"))
        with self.assertRaises(MipsFunctionError):
            self.tr.end_function(TACInstruction(TACOp.END_FUNC, None, Name("nada")), [])

    def test_return_outside_a_function(self) -> None:
        with self.assertRaises(MipsFunctionError) as raised:
            self.tr.translate_return(TACInstruction(TACOp.RETURN, None, Const(1, "integer"), line=7))
        self.assertEqual(raised.exception.line, 7)
        self.assertIn("línea 7", str(raised.exception))

    def test_frame_size_must_match_the_tac(self) -> None:
        with self.assertRaises(MipsFunctionError):
            self.tr.begin_function(self.begin("suma", 99))

    def test_nested_function_cannot_be_called_from_global_code(self) -> None:
        t = Translation(NESTED)
        tr = FunctionTranslator(t.model, MemoryRegisters(t.model))
        with self.assertRaises(MipsFunctionError):
            tr.translate_call(self.call(Name("medio"), 0))

    def test_function_not_visible_from_the_caller(self) -> None:
        t = Translation(NESTED + "\nfunction suelta(): integer { return 1; }\nprint(suelta());")
        tr = FunctionTranslator(t.model, MemoryRegisters(t.model))
        tr.begin_function(self.begin("suelta"))
        with self.assertRaises(MipsFunctionError):
            tr.translate_call(self.call(Name("interno"), 0))

    def test_wrong_instruction(self) -> None:
        with self.assertRaises(MipsFunctionError):
            self.tr.translate_param(TACInstruction(TACOp.RETURN))


class ExamplesTests(unittest.TestCase):
    def test_every_example_translates_with_balanced_functions(self) -> None:
        for path in VALID_EXAMPLES:
            with self.subTest(example=path.name):
                t = Translation(path.read_text(encoding="utf-8"))
                self.assertEqual(t.translator.pending_params, 0)
                self.assertIsNone(t.translator.unit)
                self.assertEqual(set(t.functions), set(t.model.frames))
                for name, lines in t.functions.items():
                    frame = t.model.frame(name)
                    self.assertEqual(lines.count(f"{frame.label}:"), 1)
                    self.assertEqual(lines.count(f"{frame.epilogue_label}:"), 1)
                    self.assertEqual(lines[-2], "jr $ra")
                    self.assertEqual(sum(1 for line in lines if line == "jr $ra"), 1)


if __name__ == "__main__":
    unittest.main()
