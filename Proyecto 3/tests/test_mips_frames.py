"""Pruebas del modelo de marcos en MIPS (``mips_frames.py``): prefijo y
tamaño de cada marco, direcciones de parámetros, locales, temporales,
globales y ``this``, enlaces de acceso, registros ``$s`` guardados, nombres
de etiquetas y casos fallidos."""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from analyzer import CompiscriptAnalyzer  # noqa: E402
from compiler import compile_source  # noqa: E402
from mips_frames import (  # noqa: E402
    FP,
    GP,
    LINK_REGISTER,
    SP,
    FrameModel,
    LabelRegistry,
    MemoryLocation,
    MipsFrameError,
)
from symbol_table import build_symbol_table  # noqa: E402
from tac import Const, Label, Name, Temp, Var  # noqa: E402

VALID_EXAMPLES = sorted(
    path for path in (PROJECT / "examples").glob("*.cps") if "errores" not in path.name
)

FUNCTIONS = """
function suma(a: integer, b: integer): integer { return a + b; }
function f(a: integer, b: boolean): integer {
  let c: integer = a * 2;
  return c;
}
function nada() { print(1); }
let resultado: integer = suma(2, 3);
let ok: boolean = true;
print(f(resultado, ok));
"""

NESTED = """
function externo(x: integer): integer {
  let y: integer = 1;
  function medio(): integer {
    function interno(): integer { return x + y; }
    return interno();
  }
  return medio();
}
function otra(z: integer): integer { return z; }
let r: integer = externo(3) + otra(4);
"""

CLASSES = """
class Animal {
  let nombre: string;
  let edad: integer = 1;
  function constructor(n: string) { this.nombre = n; }
  function hablar(veces: integer, fuerte: boolean): string {
    function ayuda(): string { return this.nombre; }
    return ayuda();
  }
}
let a: Animal = new Animal("Toby");
print(a.hablar(2, true));
"""


def model_of(source: str) -> FrameModel:
    result = compile_source(source)
    assert result.succeeded, result.diagnostics
    return FrameModel(result.symbol_table)


def var(model: FrameModel, record_name: str, name: str) -> Var:
    """``Var`` del TAC para la casilla ``name`` del registro ``record_name``."""
    slot = model.table.record(record_name).slot(name)
    assert slot is not None and slot.symbol is not None, (record_name, name)
    return Var(name, slot.symbol)


class FrameSizeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = model_of(FUNCTIONS)

    def test_prefix_covers_header_and_parameters(self) -> None:
        self.assertEqual(self.model.frame("suma").prefix_size, 20)  # 12 + a + b
        # b es boolean (1 byte en +16): el prefijo se alinea a 20.
        self.assertEqual(self.model.frame("f").prefix_size, 20)

    def test_function_without_parameters_reserves_only_the_header(self) -> None:
        self.assertEqual(self.model.frame("nada").prefix_size, 12)

    def test_frame_size_is_the_record_size(self) -> None:
        for name in ("suma", "f", "nada"):
            frame = self.model.frame(name)
            self.assertEqual(frame.size, frame.record.size)
        self.assertEqual(self.model.frame("suma").size, 24)
        self.assertEqual(self.model.frame("f").size, 28)

    def test_prefix_never_exceeds_the_frame(self) -> None:
        for frame in self.model.frames.values():
            self.assertLessEqual(frame.prefix_size, frame.size)
            self.assertEqual(frame.prefix_size % 4, 0)
            self.assertEqual(frame.size % 4, 0)

    def test_method_prefix_includes_this(self) -> None:
        model = model_of(CLASSES)
        hablar = model.frame("Animal.hablar")
        self.assertEqual([slot.name for slot in hablar.argument_slots], ["this", "veces", "fuerte"])
        self.assertEqual(hablar.prefix_size, 24)  # 12 + this + veces + fuerte(1) alineado


class FrameAddressTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = model_of(FUNCTIONS)

    def test_header_slots(self) -> None:
        frame = self.model.frame("suma")
        self.assertEqual(frame.return_address.address, "-4($fp)")
        self.assertEqual(frame.control_link.address, "-8($fp)")
        self.assertEqual(frame.access_link.address, "-12($fp)")

    def test_parameters_and_locals_are_below_fp(self) -> None:
        a = self.model.address_of(var(self.model, "suma", "a"), "suma")
        b = self.model.address_of(var(self.model, "suma", "b"), "suma")
        c = self.model.address_of(var(self.model, "f", "c"), "f")
        self.assertEqual((a.address, b.address, c.address), ("-16($fp)", "-20($fp)", "-24($fp)"))
        self.assertEqual(a.load("$t0"), ["lw $t0, -16($fp)"])
        self.assertEqual(c.store("$t1"), ["sw $t1, -24($fp)"])

    def test_boolean_parameter_uses_byte_instructions(self) -> None:
        b = self.model.address_of(var(self.model, "f", "b"), "f")
        self.assertEqual((b.address, b.size), ("-17($fp)", 1))
        self.assertEqual(b.load("$t0"), ["lbu $t0, -17($fp)"])
        self.assertEqual(b.store("$t0"), ["sb $t0, -17($fp)"])

    def test_temporaries_follow_the_variables(self) -> None:
        # suma: temporales a partir de +20 -> t1 en -24($fp).
        self.assertEqual(self.model.address_of(Temp(1), "suma").address, "-24($fp)")
        # f: c en +20, temporales a partir de +24 -> t1 en -28($fp).
        self.assertEqual(self.model.address_of(Temp(1), "f").address, "-28($fp)")

    def test_globals_and_global_temporaries_use_gp(self) -> None:
        table = self.model.table
        resultado = Var("resultado", table.global_record.slot("resultado").symbol)
        ok = Var("ok", table.global_record.slot("ok").symbol)
        self.assertEqual(self.model.address_of(resultado).address, "0($gp)")
        self.assertEqual(self.model.address_of(ok).load("$t0"), ["lbu $t0, 4($gp)"])
        # Una global se ve igual desde cualquier función.
        self.assertEqual(self.model.address_of(resultado, "suma").address, "0($gp)")
        # Temporales del código global: después de las globales (+8).
        self.assertEqual(self.model.address_of(Temp(1)).address, "8($gp)")
        self.assertEqual(self.model.global_area.size, table.global_record.size)

    def test_global_unit_by_name(self) -> None:
        self.assertIsNone(self.model.unit(None))
        self.assertIsNone(self.model.unit("global"))
        self.assertEqual(self.model.address_of(Temp(1), "global").address, "8($gp)")


class CallerViewTests(unittest.TestCase):
    def test_argument_offsets_relative_to_sp(self) -> None:
        model = model_of(FUNCTIONS)
        suma = model.frame("suma")
        self.assertEqual([loc.address for loc in suma.argument_locations()], ["4($sp)", "0($sp)"])
        f = model.frame("f")
        self.assertEqual([(loc.address, loc.store_op) for loc in f.argument_locations()],
                         [("4($sp)", "sw"), ("3($sp)", "sb")])
        self.assertEqual(suma.caller_access_link.address, "8($sp)")

    def test_caller_and_callee_see_the_same_slot(self) -> None:
        """Lo que el llamador escribe en ``k($sp)`` es ``k - P`` respecto al
        nuevo ``$fp`` (``$fp = $sp + P``)."""
        for source in (FUNCTIONS, NESTED, CLASSES):
            for frame in model_of(source).frames.values():
                with self.subTest(frame=frame.name):
                    for slot, caller in zip(frame.argument_slots, frame.argument_locations()):
                        callee = frame.slot_location(slot)
                        self.assertEqual(caller.base, SP)
                        self.assertEqual(caller.offset - frame.prefix_size, callee.offset)
                    self.assertEqual(
                        frame.caller_access_link.offset - frame.prefix_size, frame.access_link.offset
                    )


class SavedRegisterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.frame = model_of(FUNCTIONS).frame("suma")

    def test_saved_registers_go_after_the_temporaries(self) -> None:
        self.frame.use_saved_registers(["$s1", "$s0"])
        self.assertEqual(self.frame.saved_registers, ("$s0", "$s1"))
        self.assertEqual(self.frame.size, 32)
        self.assertEqual(self.frame.saved_register_location("$s0").address, "-28($fp)")
        self.assertEqual(self.frame.saved_register_location("$s1").address, "-32($fp)")
        # El prefijo del llamador no cambia.
        self.assertEqual(self.frame.prefix_size, 20)

    def test_only_s_registers_can_be_saved(self) -> None:
        with self.assertRaises(MipsFrameError):
            self.frame.use_saved_registers(["$t0"])
        with self.assertRaises(MipsFrameError):
            self.frame.use_saved_registers(["$s0", "$s0"])

    def test_register_not_saved(self) -> None:
        with self.assertRaises(MipsFrameError):
            self.frame.saved_register_location("$s3")


class AccessLinkTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = model_of(NESTED)
        self.x = var(self.model, "externo", "x")
        self.y = var(self.model, "externo", "y")

    def test_levels(self) -> None:
        self.assertEqual([self.model.frame(name).level for name in ("externo", "medio", "interno")], [1, 2, 3])

    def test_own_variable_has_no_setup(self) -> None:
        location = self.model.address_of(self.x, "externo")
        self.assertEqual((location.base, location.setup), (FP, ()))

    def test_one_level_out(self) -> None:
        location = self.model.address_of(self.y, "medio")
        self.assertEqual(location.load("$t0"), ["lw $v1, -12($fp)", "lw $t0, -20($v1)"])

    def test_two_levels_out(self) -> None:
        location = self.model.address_of(self.x, "interno")
        self.assertEqual(
            location.load("$t0"),
            ["lw $v1, -12($fp)", "lw $v1, -12($v1)", "lw $t0, -16($v1)"],
        )
        self.assertEqual(location.base, LINK_REGISTER)

    def test_v1_cannot_be_stored_through_itself(self) -> None:
        location = self.model.address_of(self.x, "interno")
        with self.assertRaises(MipsFrameError):
            location.store(LINK_REGISTER)
        self.assertEqual(location.store("$t2")[-1], "sw $t2, -16($v1)")

    def test_follow_access_links(self) -> None:
        self.assertEqual(FrameModel.follow_access_links(0), ((), FP))
        setup, base = FrameModel.follow_access_links(3)
        self.assertEqual(len(setup), 3)
        self.assertEqual(base, LINK_REGISTER)
        with self.assertRaises(MipsFrameError):
            FrameModel.follow_access_links(-1)


class ThisTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = model_of(CLASSES)

    def test_this_in_methods_constructors_and_initializers(self) -> None:
        for name in ("Animal.hablar", "Animal.constructor", "Animal.$init"):
            location = self.model.address_of(Var("this"), name)
            self.assertEqual((location.address, location.setup), ("-16($fp)", ()))

    def test_this_from_a_function_nested_in_a_method(self) -> None:
        location = self.model.address_of(Var("this"), "ayuda")
        self.assertEqual(location.load("$t0"), ["lw $v1, -12($fp)", "lw $t0, -16($v1)"])

    def test_this_outside_a_method(self) -> None:
        with self.assertRaises(MipsFrameError):
            self.model.address_of(Var("this"))
        with self.assertRaises(MipsFrameError):
            model_of(FUNCTIONS).address_of(Var("this"), "suma")


class LabelTests(unittest.TestCase):
    def test_tac_characters_are_replaced(self) -> None:
        model = model_of(CLASSES)
        self.assertEqual(model.mips_label("Animal.hablar"), "fn_Animal_hablar")
        self.assertEqual(model.mips_label("Animal.$init"), "fn_Animal__init")
        self.assertEqual(model.frame("Animal.hablar").epilogue_label, "fn_Animal_hablar_fin")

    def test_collisions_get_a_suffix(self) -> None:
        source = CLASSES + """
function Animal_hablar(): integer { return 1; }
function suma_fin(): integer { return 2; }
function suma(): integer { return 3; }
print(Animal_hablar() + suma_fin() + suma());
"""
        model = model_of(source)
        self.assertEqual(model.mips_label("Animal.hablar"), "fn_Animal_hablar")
        self.assertEqual(model.mips_label("Animal_hablar"), "fn_Animal_hablar_2")
        self.assertEqual(model.mips_label("suma_fin"), "fn_suma_fin")
        self.assertEqual(model.frame("suma").epilogue_label, "fn_suma_fin_2")

    def test_shadowed_function_labels(self) -> None:
        registry = LabelRegistry()
        self.assertEqual(registry.function("ayuda$1"), "fn_ayuda_1")
        self.assertEqual(registry.unique("main"), "main_2")  # main y globales están reservados
        self.assertEqual(registry.unique("globales"), "globales_2")

    def test_every_label_is_unique_and_valid_in_all_examples(self) -> None:
        valid = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
        for path in VALID_EXAMPLES:
            with self.subTest(example=path.name):
                model = model_of(path.read_text(encoding="utf-8"))
                labels = [label for frame in model.frames.values() for label in (frame.label, frame.epilogue_label)]
                self.assertEqual(len(labels), len(set(labels)))
                for label in labels:
                    self.assertRegex(label, valid)
                    self.assertTrue(label.startswith("fn_"))


class FailureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.model = model_of(NESTED)

    def test_operands_without_address(self) -> None:
        for operand in (Const(5, "integer"), Const("hola", "string"), Label("L1"), Name("externo"), None):
            with self.subTest(operand=operand), self.assertRaises(MipsFrameError):
                self.model.address_of(operand, "externo")

    def test_temporary_out_of_range(self) -> None:
        with self.assertRaises(MipsFrameError):
            self.model.address_of(Temp(0), "externo")
        with self.assertRaises(MipsFrameError):
            self.model.address_of(Temp(self.model.frame("externo").record.temporaries + 1), "externo")

    def test_unknown_function(self) -> None:
        with self.assertRaises(MipsFrameError):
            self.model.frame("noExiste")
        with self.assertRaises(MipsFrameError):
            self.model.address_of(Temp(1), "noExiste")

    def test_local_from_global_code(self) -> None:
        with self.assertRaises(MipsFrameError):
            self.model.address_of(var(self.model, "externo", "x"))

    def test_local_of_a_function_that_does_not_contain_the_unit(self) -> None:
        # «z» es de «otra», que no contiene a «interno».
        with self.assertRaises(MipsFrameError):
            self.model.address_of(var(self.model, "otra", "z"), "interno")
        # Una función interna no expone sus variables a la externa.
        with self.assertRaises(MipsFrameError):
            self.model.address_of(var(model_of(FUNCTIONS), "f", "c"), "suma")

    def test_variable_without_symbol(self) -> None:
        with self.assertRaises(MipsFrameError):
            self.model.address_of(Var("x"), "externo")

    def test_attribute_has_no_own_address(self) -> None:
        model = model_of(CLASSES)
        attribute = model.table.find_class("Animal").attributes["nombre"]
        with self.assertRaises(MipsFrameError):
            model.address_of(Var("nombre", attribute), "Animal.hablar")

    def test_table_without_activation_records(self) -> None:
        analysis = CompiscriptAnalyzer().analyze(FUNCTIONS)
        table, _ = build_symbol_table(analysis.ast)
        with self.assertRaises(MipsFrameError):
            FrameModel(table)


class ExamplesIntegrationTests(unittest.TestCase):
    def test_every_operand_of_every_example_has_an_address(self) -> None:
        """Cada ``Var`` y ``Temp`` del TAC de los ejemplos válidos tiene
        dirección dentro de la función donde aparece."""
        for path in VALID_EXAMPLES:
            with self.subTest(example=path.name):
                result = compile_source(path.read_text(encoding="utf-8"))
                self.assertTrue(result.succeeded, result.diagnostics)
                model = FrameModel(result.symbol_table)
                unit = None
                for instruction in result.tac.instructions:
                    if instruction.op.name == "BEGIN_FUNC":
                        unit = instruction.arg1.name
                        continue
                    if instruction.op.name == "END_FUNC":
                        unit = None
                        continue
                    for operand in (instruction.result, instruction.arg1, instruction.arg2):
                        if isinstance(operand, (Var, Temp)):
                            location = model.address_of(operand, unit)
                            self.assertIsInstance(location, MemoryLocation)
                            self.assertIn(location.base, (FP, GP, LINK_REGISTER))
                            self.assertIn(location.size, (1, 4))


if __name__ == "__main__":
    unittest.main()
