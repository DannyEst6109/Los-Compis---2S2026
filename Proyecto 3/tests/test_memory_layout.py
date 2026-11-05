"""Pruebas de las nuevas funcionalidades de la tabla de símbolos:
direcciones, tamaños, registros de activación y distribución de objetos."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from compiler import compile_source  # noqa: E402
from memory_layout import assign_memory_layout, size_of  # noqa: E402
from symbol_table import StorageKind, SymbolTable, align, build_symbol_table  # noqa: E402
from analyzer import CompiscriptAnalyzer  # noqa: E402
from tac_generator import generate_tac  # noqa: E402


def compiled_table(source: str) -> SymbolTable:
    result = compile_source(source)
    assert result.succeeded, result.diagnostics
    return result.symbol_table


def symbol(table: SymbolTable, name: str, scope_name: str | None = None):
    matches = [
        item for item in table.all_symbols()
        if item.name == name and (scope_name is None or item.scope_name == scope_name)
    ]
    assert len(matches) == 1, matches
    return matches[0]


def slot_names(record) -> list[str]:
    return [slot.name for slot in record.all_slots()]


class SizeAndAlignmentTests(unittest.TestCase):
    def test_sizes_by_type(self) -> None:
        self.assertEqual(size_of("integer"), 4)
        self.assertEqual(size_of("boolean"), 1)
        for reference in ("string", "integer[]", "Perro", None):
            self.assertEqual(size_of(reference), 4)

    def test_alignment(self) -> None:
        self.assertEqual(align(0, 4), 0)
        self.assertEqual(align(1, 4), 4)
        self.assertEqual(align(5, 1), 5)
        self.assertEqual(align(6, 4), 8)


class GlobalStorageTests(unittest.TestCase):
    def test_globals_receive_consecutive_static_addresses(self) -> None:
        table = compiled_table("let a: integer = 1; const B: string = \"x\"; let c: integer[] = [1];")
        self.assertEqual(
            [(s.name, s.storage, s.address, s.size) for s in (symbol(table, n) for n in ("a", "B", "c"))],
            [
                ("a", StorageKind.GLOBAL, "global+0", 4),
                ("B", StorageKind.GLOBAL, "global+4", 4),
                ("c", StorageKind.GLOBAL, "global+8", 4),
            ],
        )

    def test_boolean_uses_one_byte_and_next_integer_is_aligned(self) -> None:
        table = compiled_table("let ok: boolean = true; let n: integer = 1;")
        self.assertEqual((symbol(table, "ok").address, symbol(table, "ok").size), ("global+0", 1))
        self.assertEqual(symbol(table, "n").address, "global+4")

    def test_untyped_variable_uses_inferred_type(self) -> None:
        table = compiled_table("let flag = 1 < 2; let texto = \"hola\";")
        self.assertEqual((symbol(table, "flag").runtime_type, symbol(table, "flag").size), ("boolean", 1))
        self.assertEqual(symbol(table, "texto").runtime_type, "string")

    def test_block_variables_at_global_level_are_static(self) -> None:
        table = compiled_table("let a = 1; { let b = 2; print(b); } for (let i = 0; i < 2; i = i + 1) { print(i); }")
        self.assertEqual(symbol(table, "b").storage, StorageKind.GLOBAL)
        self.assertEqual(symbol(table, "i").address, "global+8")

    def test_shadowed_variables_get_different_addresses(self) -> None:
        table = compiled_table("let x = 1; { let x = 2; print(x); }")
        addresses = sorted(item.address for item in table.all_symbols() if item.name == "x")
        self.assertEqual(addresses, ["global+0", "global+4"])

    def test_global_record_counts_temporaries_of_global_code(self) -> None:
        table = compiled_table("let a = 1; let b = (a + 2) * (a + 3);")
        record = table.global_record
        self.assertEqual(record.temporaries, 2)
        self.assertEqual(slot_names(record), ["a", "b", "t1", "t2"])
        self.assertEqual(record.size, 16)


class ActivationRecordTests(unittest.TestCase):
    def test_function_record_layout(self) -> None:
        table = compiled_table(
            "function f(a: integer, b: boolean): integer { let c: integer = a; { let d = c; print(d); } return c; }"
        )
        record = symbol(table, "f").activation_record
        self.assertEqual(record.name, "f")
        self.assertEqual((record.kind, record.level, record.parent), ("función", 1, "global"))
        self.assertEqual(
            [(slot.name, slot.role, slot.offset, slot.size) for slot in record.slots],
            [
                ("dirección de retorno", "dirección de retorno", 0, 4),
                ("enlace de control", "enlace de control", 4, 4),
                ("enlace de acceso", "enlace de acceso", 8, 4),
                ("a", "parámetro", 12, 4),
                ("b", "parámetro", 16, 1),
                ("c", "local", 20, 4),
                ("d", "local", 24, 4),
            ],
        )
        self.assertEqual(symbol(table, "a").address, "fp+12")
        self.assertEqual(symbol(table, "a").storage, StorageKind.PARAMETER)
        self.assertEqual(symbol(table, "c").storage, StorageKind.LOCAL)
        self.assertEqual(symbol(table, "d").owner, "f")

    def test_record_size_includes_temporaries(self) -> None:
        table = compiled_table(
            "function factorial(n: integer): integer { if (n <= 1) { return 1; } return n * factorial(n - 1); }"
        )
        record = symbol(table, "factorial").activation_record
        self.assertEqual(record.temporaries, 1)
        self.assertEqual(record.temporary_slots()[0].offset, 16)
        self.assertEqual(record.size, 20)

    def test_begin_func_announces_record_size(self) -> None:
        result = compile_source("function f(a: integer): integer { let b = a * 2; return b + 1; }")
        self.assertEqual(result.tac.lines()[0], f"begin_func f, {symbol(result.symbol_table, 'f').activation_record.size}")

    def test_nested_function_has_its_own_record_and_access_link(self) -> None:
        table = compiled_table(
            "function externo(n: integer): integer {"
            "  let base = 10;"
            "  function interno(k: integer): integer { return base + k + n; }"
            "  return interno(n);"
            "}"
        )
        inner = symbol(table, "interno").activation_record
        outer = symbol(table, "externo").activation_record
        self.assertEqual((inner.level, inner.parent), (2, "externo"))
        self.assertNotIn("k", slot_names(outer))
        self.assertIn("base", slot_names(outer))
        self.assertEqual(symbol(table, "interno").captured_names, {"base", "n"})

    def test_functions_with_same_name_get_unique_labels(self) -> None:
        table = compiled_table(
            "function a(): integer { function ayuda(): integer { return 1; } return ayuda(); }"
            "function b(): integer { function ayuda(): integer { return 2; } return ayuda(); }"
        )
        labels = sorted(item.tac_label for item in table.all_symbols() if item.name == "ayuda")
        self.assertEqual(labels, ["ayuda", "ayuda$1"])

    def test_function_named_like_a_temporary_is_renamed(self) -> None:
        result = compile_source("function t1(): integer { return 1; } print(t1());")
        self.assertTrue(result.succeeded, result.diagnostics)
        self.assertIn("t1 = call t1$1, 0", result.tac.lines())

    def test_catch_variable_is_a_string_local(self) -> None:
        table = compiled_table("function f() { try { print(1); } catch (e) { print(e); } }")
        error = symbol(table, "e")
        self.assertEqual((error.runtime_type, error.storage, error.owner), ("string", StorageKind.LOCAL, "f"))

    def test_records_are_listed_outer_before_inner(self) -> None:
        table = compiled_table(
            "function a() { function b() { function c() { print(1); } c(); } b(); } a();"
        )
        self.assertEqual([record.name for record in table.activation_records], ["a", "b", "c"])
        self.assertIs(table.record("b"), symbol(table, "b").activation_record)
        self.assertIs(table.record("global"), table.global_record)


class ClassLayoutTests(unittest.TestCase):
    SOURCE = """
        class Animal {
          let nombre: string;
          let edad: integer = 1;
          function constructor(nombre: string) { this.nombre = nombre; }
          function hablar(): string { return "..."; }
          function comer(): string { return "comiendo"; }
        }
        class Perro : Animal {
          let vacunado: boolean;
          let raza: string;
          function hablar(): string { return "guau"; }
          function correr(): string { return "corriendo"; }
        }
    """

    def test_fields_vtable_pointer_and_inherited_offsets(self) -> None:
        table = compiled_table(self.SOURCE)
        animal, perro = table.class_layouts["Animal"], table.class_layouts["Perro"]
        self.assertEqual([(s.name, s.offset) for s in animal.slots], [("vtable", 0), ("nombre", 4), ("edad", 8)])
        self.assertEqual(
            [(s.name, s.offset, s.size) for s in perro.slots],
            [("vtable", 0, 4), ("nombre", 4, 4), ("edad", 8, 4), ("vacunado", 12, 1), ("raza", 16, 4)],
        )
        self.assertEqual((animal.size, perro.size), (12, 20))
        self.assertEqual(symbol(table, "raza").address, "obj+16")
        self.assertEqual(symbol(table, "nombre", "Animal").storage, StorageKind.FIELD)

    def test_vtable_keeps_positions_and_replaces_overrides(self) -> None:
        table = compiled_table(self.SOURCE)
        self.assertEqual(table.class_layouts["Animal"].vtable, [("hablar", "Animal.hablar"), ("comer", "Animal.comer")])
        self.assertEqual(
            table.class_layouts["Perro"].vtable,
            [("hablar", "Perro.hablar"), ("comer", "Animal.comer"), ("correr", "Perro.correr")],
        )
        self.assertEqual(table.class_layouts["Perro"].method_index("comer"), 1)

    def test_method_records_have_this_before_parameters(self) -> None:
        table = compiled_table(self.SOURCE)
        constructor = symbol(table, "constructor", "Animal").activation_record
        self.assertEqual((constructor.name, constructor.kind), ("Animal.constructor", "constructor"))
        self.assertEqual(slot_names(constructor)[3:5], ["this", "nombre"])
        self.assertEqual(constructor.slot("this").offset, 12)
        self.assertEqual(symbol(table, "nombre", "constructor").address, "fp+16")
        self.assertEqual(symbol(table, "hablar", "Perro").activation_record.kind, "método")

    def test_initializer_record_only_when_attributes_have_initial_values(self) -> None:
        table = compiled_table(self.SOURCE)
        self.assertEqual(table.class_layouts["Animal"].init_record.name, "Animal.$init")
        self.assertIsNone(table.class_layouts["Perro"].init_record)

    def test_class_symbol_points_to_its_layout(self) -> None:
        table = compiled_table(self.SOURCE)
        self.assertIs(table.find_class("Perro").class_layout, table.class_layouts["Perro"])


class TableIntegrationTests(unittest.TestCase):
    def test_render_includes_address_and_size(self) -> None:
        rendered = compiled_table("let x: integer = 1;").render()
        self.assertIn("Dirección", rendered)
        self.assertIn("global+0", rendered)

    def test_layout_can_be_recomputed_without_duplicates(self) -> None:
        result = CompiscriptAnalyzer().analyze("function f(a: integer): integer { return a; } let x = f(1);")
        table, _ = build_symbol_table(result.ast)
        generate_tac(table, result.ast)
        generate_tac(table, result.ast)
        self.assertEqual([record.name for record in table.activation_records], ["f"])
        self.assertEqual(table.global_record.slots[0].name, "x")

    def test_layout_without_inferred_types_uses_declared_types(self) -> None:
        result = CompiscriptAnalyzer().analyze("let ok: boolean = true; let n = 1;")
        table, _ = build_symbol_table(result.ast)
        assign_memory_layout(table)
        self.assertEqual(symbol(table, "ok").size, 1)
        self.assertEqual((symbol(table, "n").runtime_type, symbol(table, "n").size), (None, 4))

    def test_layout_is_not_computed_for_invalid_programs(self) -> None:
        result = compile_source("let x: integer = \"texto\";")
        self.assertFalse(result.succeeded)
        self.assertFalse(result.symbol_table.has_layout)


if __name__ == "__main__":
    unittest.main()
