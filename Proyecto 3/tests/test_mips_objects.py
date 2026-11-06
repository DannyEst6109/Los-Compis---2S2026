"""Persona 3 · Clases, objetos y herencia en MIPS (rúbrica: 2 + 2 puntos).

Cubre la representación de los objetos en memoria, la creación con
``new``, lectura y escritura de atributos, atributos heredados, vtables,
redefinición de métodos, despacho dinámico y la búsqueda dinámica de
miembros cuando la clase del objeto no se conoce al compilar.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mips_helpers import EXAMPLES, EXPECTED, MarsTestCase, compile_mips, instructions, needs_mars  # noqa: E402

from compiler import GENERATION_KIND, compile_source  # noqa: E402
from mips_frames import FrameModel  # noqa: E402
from mips_objects import ObjectTranslator, members_label, tag_offset, vtable_label  # noqa: E402
from mips_registers import MipsRegisters  # noqa: E402
from mips_runtime import RuntimeSupport  # noqa: E402
from tac import Name, TACInstruction, TACOp  # noqa: E402

ANIMALES = """
class Animal {
  let nombre: string;
  let edad: integer = 1;
  function constructor(nombre: string) { this.nombre = nombre; }
  function hablar(): string { return "..."; }
  function presentarse(): string { return "Soy " + this.nombre; }
}
class Perro : Animal {
  let raza: string = "criollo";
  let vacunado: boolean;
  function hablar(): string { return this.nombre + " ladra"; }
}
let animal: Animal = new Perro("Toby");
print(animal.hablar());
"""


def objects_for(source: str) -> tuple[ObjectTranslator, object]:
    result = compile_mips(source)
    registers = MipsRegisters(FrameModel(result.symbol_table))
    return ObjectTranslator(registers.model, registers, RuntimeSupport(registers)), result


class ObjectRepresentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.objects, self.result = objects_for(ANIMALES)
        self.layouts = self.result.symbol_table.class_layouts

    def test_inherited_attributes_keep_the_superclass_offset(self) -> None:
        animal, perro = self.layouts["Animal"], self.layouts["Perro"]
        for name in ("nombre", "edad"):
            self.assertEqual(animal.field_offset(name), perro.field_offset(name))
        self.assertEqual(perro.field_offset("vtable"), 0)
        self.assertGreater(perro.field_offset("raza"), animal.field_offset("edad"))

    def test_vtable_override_replaces_the_inherited_entry(self) -> None:
        data = "\n".join(self.objects.data_lines())
        self.assertIn(f".word {members_label('Perro')}\n{vtable_label('Perro')}:", data)
        perro = data.split(f"{vtable_label('Perro')}:")[1].splitlines()
        self.assertTrue(perro[1].startswith(".word fn_Perro_hablar"))  # posición 0: redefinido
        self.assertTrue(perro[2].startswith(".word fn_Animal_presentarse"))  # posición 1: heredado

    def test_member_table_lists_fields_and_methods(self) -> None:
        data = self.objects.data_lines()
        start = data.index(f"{members_label('Perro')}:")
        self.assertEqual(data[start + 1], ".word 6")  # 4 atributos + 2 métodos
        rows = data[start + 2:start + 8]
        self.assertTrue(any(row.endswith("# atributo vacunado") and ", 1  #" in row for row in rows))

    def test_new_reserves_tags_and_data_and_sets_the_vtable(self) -> None:
        size = self.layouts["Perro"].size
        lines = self.objects.translate(TACInstruction(TACOp.NEW_OBJECT, self._temp(), Name("Perro")), None)
        self.assertEqual(lines[:6], [
            f"li $a0, {2 * size}", "li $v0, 9", "syscall", f"addiu $v0, $v0, {size}",
            f"la $t9, {vtable_label('Perro')}", "sw $t9, 0($v0)",
        ])
        # Los atributos de referencia (cadenas) empiezan como null; los numéricos no.
        raza = self.layouts["Perro"].field_offset("raza")
        edad = self.layouts["Perro"].field_offset("edad")
        self.assertTrue(any(line.startswith(f"sb $t9, {tag_offset(raza)}($v0)") for line in lines))
        self.assertFalse(any(line.startswith(f"sb $t9, {tag_offset(edad)}($v0)") for line in lines))

    def _temp(self):
        return next(instruction.result for instruction in self.result.tac if instruction.op is TACOp.NEW_OBJECT)

    def test_tac_carries_the_static_class_of_each_member(self) -> None:
        members = {
            (str(instruction), instruction.arg2.owner)
            for instruction in self.result.tac
            if instruction.op in (TACOp.METHOD_LOAD, TACOp.FIELD_LOAD)
        }
        self.assertIn(("t1 = method animal.hablar", "Animal"), members)
        self.assertIn(("t1 = this.nombre", "Perro"), members)
        self.assertIn(("t1 = this.nombre", "Animal"), members)

    def test_static_access_uses_fixed_offsets_and_vtable_positions(self) -> None:
        lines = self.result.mips.lines
        method = lines.index("# t1 = method animal.hablar")
        code = instructions(lines[method:method + 12])
        self.assertIn("lw $t9, 0($t9)", code)  # vtable[0] = hablar
        self.assertNotIn("jal p3_lookup", "\n".join(lines))

    def test_this_is_never_checked_for_null(self) -> None:
        lines = self.result.mips.lines
        start = lines.index("fn_Animal_constructor:")  # sólo usa this.nombre = nombre
        end = lines.index("fn_Animal_constructor_fin:")
        self.assertNotIn("j p3_throw", lines[start:end])

    def test_untyped_receivers_use_dynamic_lookup_only_when_needed(self) -> None:
        objects, _ = objects_for("""
            class A { let x: integer; let solo: integer; function f(): integer { return 1; } }
            class B { let y: integer; let x: integer; function g(): integer { return 2; } function f(): integer { return 3; } }
            function usar(o) { print(o.x); print(o.solo); print(o.f()); }
            usar(new A());
        """)
        instruction = None  # sólo se usa en los mensajes de error
        self.assertTrue(objects.field_access(Name("x"), instruction).dynamic)  # 4 en A, 8 en B
        self.assertEqual(objects.field_access(Name("solo"), instruction).offset, 8)  # sólo existe en A
        self.assertEqual(objects.field_access(Name("x", "B"), instruction).offset, 8)  # clase estática
        self.assertTrue(objects.method_access(Name("f"), instruction).dynamic)  # posición 0 en A, 1 en B
        self.assertEqual(objects.method_access(Name("f", "B"), instruction).index, 1)

    def test_incompatible_overrides_are_reported_as_generation_errors(self) -> None:
        result = compile_source("""
            class A { function f(x: integer): integer { return x; } }
            class B { function f(x: boolean, y: integer): integer { return y; } }
            function usar(o): integer { return o.f(1); }
            print(usar(new A()));
        """)
        self.assertIsNotNone(result.tac)  # el TAC es correcto
        self.assertIsNone(result.mips)  # pero no se entrega MIPS parcial
        self.assertEqual([item.kind for item in result.diagnostics], [GENERATION_KIND])
        self.assertIn("argumentos distintos", result.diagnostics[0].description)


@needs_mars
class ObjectExecutionTests(MarsTestCase):
    def test_creation_and_attribute_reads_and_writes(self) -> None:
        self.assert_runs("""
            class Persona {
              let nombre: string;
              let edad: integer = 18;
              let activo: boolean = true;
              let apodo: string;
            }
            let p: Persona = new Persona();
            print(p.edad); print(p.activo); print(p.apodo);
            p.nombre = "Ana"; p.edad = p.edad + 2; p.activo = false;
            print(p.nombre); print(p.edad); print(p.activo);
            let otra: Persona = new Persona();
            print(otra.edad);
        """, "18\n1\nnull\nAna\n20\n0\n18")

    def test_methods_constructor_this_and_attributes_without_this(self) -> None:
        self.assert_runs("""
            class Contador {
              let valor: integer = 0;
              let paso: integer;
              function constructor(paso: integer) { this.paso = paso; }
              function avanzar(): integer { valor = valor + paso; return this.valor; }
              function avanzarVeces(n: integer): integer {
                for (let i = 0; i < n; i = i + 1) { this.avanzar(); }
                return valor;
              }
            }
            let c = new Contador(3);
            print(c.avanzar());
            print(c.avanzarVeces(4));
            print(new Contador(5).avanzarVeces(2));
        """, "3\n15\n10")

    def test_objects_inside_objects_and_returned_objects(self) -> None:
        self.assert_runs("""
            class Nodo {
              let valor: integer; let siguiente: Nodo;
              function constructor(v: integer, s: Nodo) { this.valor = v; this.siguiente = s; }
              function ultimo(): Nodo { if (this.siguiente == null) { return this; } return this.siguiente.ultimo(); }
            }
            function crear(n: integer): Nodo {
              let lista: Nodo = null;
              while (n > 0) { lista = new Nodo(n, lista); n = n - 1; }
              return lista;
            }
            let l: Nodo = crear(5);
            print(l.valor); print(l.siguiente.siguiente.valor); print(l.ultimo().valor);
            l.siguiente.valor = 20;
            let suma = 0; let p: Nodo = l;
            while (p != null) { suma = suma + p.valor; p = p.siguiente; }
            print(suma);
        """, "1\n3\n5\n33")

    def test_methods_with_nested_functions_reach_this(self) -> None:
        self.assert_runs("""
            class Caja {
              let total: integer = 1;
              function multiplicar(k: integer): integer {
                function ayuda(): integer { return this.total * k; }
                this.total = ayuda();
                return total;
              }
            }
            let c = new Caja();
            c.multiplicar(3); c.multiplicar(4);
            print(c.total);
        """, "12")

    def test_inheritance_inherited_attributes_and_dynamic_dispatch(self) -> None:
        self.assert_runs("""
            class Animal {
              let nombre: string; let patas: integer = 4;
              function constructor(n: string) { this.nombre = n; }
              function sonido(): string { return "..."; }
              function hablar(): string { return this.nombre + ": " + this.sonido(); }
            }
            class Perro : Animal { function sonido(): string { return "guau"; } }
            class Cachorro : Perro { let edad: integer = 1; function sonido(): string { return "guau guau"; } }
            class Ave : Animal {
              function constructor(n: string) { this.nombre = n; this.patas = 2; }
              function sonido(): string { return "pío"; }
            }
            let zoo: Animal[] = [new Animal("Pez"), new Perro("Rex"), new Cachorro("Bolt"), new Ave("Kiwi")];
            foreach (a in zoo) { print(a.hablar()); print(a.patas); }
            let c: Cachorro = new Cachorro("Max");
            print(c.nombre); print(c.edad);
            let comoAnimal: Animal = c;
            print(comoAnimal.sonido());
        """, "Pez: ...\n4\nRex: guau\n4\nBolt: guau guau\n4\nKiwi: pío\n2\nMax\n1\nguau guau")

    def test_dynamic_member_lookup_for_untyped_parameters(self) -> None:
        self.assert_runs("""
            class A {
              let x: integer; let marca: boolean;
              function constructor() { this.x = 10; this.marca = true; }
              function f(): integer { return 1; }
            }
            class B {
              let y: integer; let marca: integer; let x: integer;
              function constructor() { this.x = 20; this.marca = 7; }
              function g(): integer { return 2; }
              function f(): integer { return 3; }
            }
            function mostrar(o) {
              print(o.x); print(o.f()); print(o.marca);
              o.x = o.x + 1; o.marca = o.marca;
              print(o.x);
            }
            mostrar(new A());
            mostrar(new B());
        """, "10\n1\n1\n11\n20\n3\n7\n21")

    def test_class_examples(self) -> None:
        for name in ("mips_clases_objetos", "mips_herencia", "09_clases_objetos", "10_herencia", "tac_clases"):
            with self.subTest(example=name):
                source = (EXAMPLES / f"{name}.cps").read_text(encoding="utf-8")
                expected = (EXPECTED / f"{name}.txt").read_text(encoding="utf-8").rstrip("\n")
                self.assert_runs(source, expected)


if __name__ == "__main__":
    unittest.main()
