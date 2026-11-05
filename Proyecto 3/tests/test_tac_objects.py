"""Pruebas de la traducción de clases, objetos, this, herencia y despacho
dinámico de métodos."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

import ast_nodes as ast  # noqa: E402
from compiler import compile_source  # noqa: E402
from symbol_table import SymbolTable  # noqa: E402
from tac_generator import TACGenerationError, TACGenerator  # noqa: E402

SPAN = ast.SourceSpan.unknown()


def tac_lines(source: str) -> list[str]:
    result = compile_source(source)
    assert result.succeeded, result.diagnostics
    return result.tac.lines()


def section(lines: list[str], label: str) -> list[str]:
    start = next(i for i, line in enumerate(lines) if line.startswith(f"begin_func {label},"))
    return lines[start + 1:lines.index(f"end_func {label}")]


def global_code(lines: list[str]) -> list[str]:
    last_end = max((i for i, line in enumerate(lines) if line.startswith("end_func")), default=-1)
    return lines[last_end + 1:]


PERSONA = """
class Persona {
  let nombre: string;
  let edad: integer;
  function constructor(nombre: string, edad: integer) {
    this.nombre = nombre;
    this.edad = edad;
  }
  function cumplir() { this.edad = this.edad + 1; }
  function saludo(): string { return "Hola " + this.nombre; }
}
"""


class ClassTranslationTests(unittest.TestCase):
    def test_methods_become_sections_with_class_prefix(self) -> None:
        lines = tac_lines(PERSONA)
        self.assertEqual(
            [line for line in lines if line.startswith("begin_func")],
            ["begin_func Persona.constructor, 24", "begin_func Persona.cumplir, 20", "begin_func Persona.saludo, 20"],
        )
        self.assertEqual(section(lines, "Persona.constructor"), ["this.nombre = nombre", "this.edad = edad"])
        self.assertEqual(section(lines, "Persona.cumplir"), ["t1 = this.edad", "t1 = t1 + 1", "this.edad = t1"])
        self.assertEqual(section(lines, "Persona.saludo"), ["t1 = this.nombre", 't1 = concat "Hola ", t1', "return t1"])
        self.assertEqual(global_code(lines), [])

    def test_new_allocates_and_calls_constructor_with_this_first(self) -> None:
        lines = tac_lines(PERSONA + 'let ana: Persona = new Persona("Ana", 20);')
        self.assertEqual(
            global_code(lines),
            ["t1 = new Persona", "param t1", 'param "Ana"', "param 20", "call Persona.constructor, 3", "ana = t1"],
        )

    def test_new_without_constructor(self) -> None:
        lines = tac_lines("class Vacia { let x: integer; } let v: Vacia = new Vacia();")
        self.assertEqual(global_code(lines), ["t1 = new Vacia", "v = t1"])

    def test_method_call_uses_dynamic_dispatch(self) -> None:
        lines = tac_lines(PERSONA + 'let ana: Persona = new Persona("Ana", 20); print(ana.saludo()); ana.cumplir();')
        self.assertEqual(
            global_code(lines)[6:],
            [
                "t1 = method ana.saludo",
                "param ana",
                "t1 = call t1, 1",
                "print t1",
                "t1 = method ana.cumplir",
                "param ana",
                "call t1, 1",
            ],
        )

    def test_field_access_and_assignment_from_outside(self) -> None:
        lines = tac_lines(PERSONA + 'let ana: Persona = new Persona("Ana", 20); ana.edad = ana.edad * 2; print(ana.nombre);')
        self.assertEqual(
            global_code(lines)[6:],
            ["t1 = ana.edad", "t1 = t1 * 2", "ana.edad = t1", "t1 = ana.nombre", "print t1"],
        )

    def test_attribute_and_method_without_this_inside_class(self) -> None:
        lines = tac_lines(
            "class Contador {"
            "  let valor: integer;"
            "  function incrementar() { valor = valor + 1; }"
            "  function doble(): integer { incrementar(); return valor * 2; }"
            "}"
        )
        self.assertEqual(section(lines, "Contador.incrementar"), ["t1 = this.valor", "t1 = t1 + 1", "this.valor = t1"])
        self.assertEqual(
            section(lines, "Contador.doble"),
            ["t1 = method this.incrementar", "param this", "call t1, 1", "t1 = this.valor", "t1 = t1 * 2", "return t1"],
        )

    def test_function_nested_in_method_can_use_this(self) -> None:
        lines = tac_lines(
            "class C { let v: integer;"
            "  function m(): integer { function ayuda(): integer { return this.v; } return ayuda(); } }"
        )
        self.assertEqual(section(lines, "C.m"), ["t1 = call ayuda, 0", "return t1"])
        self.assertEqual(section(lines, "ayuda"), ["t1 = this.v", "return t1"])

    def test_parameter_shadows_attribute(self) -> None:
        lines = tac_lines("class P { let x: integer; function poner(x: integer) { this.x = x; } }")
        self.assertEqual(section(lines, "P.poner"), ["this.x = x"])

    def test_method_on_new_expression_and_chained_members(self) -> None:
        lines = tac_lines(
            "class Nodo { let siguiente: Nodo; let valor: integer;"
            "  function constructor(v: integer) { this.valor = v; }"
            "  function leer(): integer { return this.valor; } }"
            "let a: Nodo = new Nodo(1);"
            "a.siguiente = new Nodo(2);"
            "print(a.siguiente.valor);"
            "print(new Nodo(3).leer());"
        )
        self.assertEqual(
            global_code(lines)[5:],
            [
                "t1 = new Nodo", "param t1", "param 2", "call Nodo.constructor, 2", "a.siguiente = t1",
                "t1 = a.siguiente", "t1 = t1.valor", "print t1",
                "t1 = new Nodo", "param t1", "param 3", "call Nodo.constructor, 2",
                "t2 = method t1.leer", "param t1", "t1 = call t2, 1", "print t1",
            ],
        )

    def test_attribute_initializers_go_to_init_routine(self) -> None:
        lines = tac_lines(
            "class Config { let limite: integer = 10 * 2; let activo: boolean = true; let nombre: string; }"
            "let c: Config = new Config();"
        )
        self.assertEqual(
            section(lines, "Config.$init"),
            ["t1 = 10 * 2", "this.limite = t1", "this.activo = true"],
        )
        self.assertEqual(global_code(lines), ["t1 = new Config", "param t1", "call Config.$init, 1", "c = t1"])


class InheritanceTests(unittest.TestCase):
    SOURCE = """
    class Animal {
      let nombre: string = "animal";
      function constructor(nombre: string) { this.nombre = nombre; }
      function hablar(): string { return "..."; }
    }
    class Perro : Animal {
      let ladridos: integer = 0;
      function hablar(): string { return this.nombre + " ladra"; }
    }
    class Cachorro : Perro {
      function constructor(nombre: string) { this.nombre = "cachorro " + nombre; }
    }
    """

    def test_inherited_constructor_and_initializers_from_the_root(self) -> None:
        lines = tac_lines(self.SOURCE + 'let p: Perro = new Perro("Toby");')
        self.assertEqual(
            global_code(lines),
            [
                "t1 = new Perro",
                "param t1", "call Animal.$init, 1",
                "param t1", "call Perro.$init, 1",
                "param t1", 'param "Toby"', "call Animal.constructor, 2",
                "p = t1",
            ],
        )

    def test_subclass_constructor_replaces_inherited_one(self) -> None:
        lines = tac_lines(self.SOURCE + 'let c: Cachorro = new Cachorro("Max");')
        self.assertIn("call Cachorro.constructor, 2", global_code(lines))
        self.assertNotIn("call Animal.constructor, 2", global_code(lines))

    def test_inherited_attribute_is_accessible_in_subclass(self) -> None:
        lines = tac_lines(self.SOURCE)
        self.assertEqual(
            section(lines, "Perro.hablar"), ["t1 = this.nombre", 't1 = concat t1, " ladra"', "return t1"]
        )

    def test_polymorphic_call_goes_through_vtable(self) -> None:
        result = compile_source(self.SOURCE + 'let a: Animal = new Perro("Rex"); print(a.hablar());')
        self.assertTrue(result.succeeded, result.diagnostics)
        lines = global_code(result.tac.lines())
        # No se elige Animal.hablar en compilación: se busca en la vtable
        # del objeto, que para un Perro apunta a Perro.hablar.
        self.assertIn("t1 = method a.hablar", lines)
        self.assertNotIn("call Animal.hablar", " ".join(lines))
        layouts = result.symbol_table.class_layouts
        index = layouts["Animal"].method_index("hablar")
        self.assertEqual(layouts["Perro"].vtable[index], ("hablar", "Perro.hablar"))
        self.assertEqual(layouts["Cachorro"].vtable[index], ("hablar", "Perro.hablar"))

    def test_inherited_method_called_on_subclass(self) -> None:
        lines = tac_lines(
            "class A { function saludar(): string { return \"hola\"; } }"
            "class B : A { }"
            "let b: B = new B(); print(b.saludar());"
        )
        self.assertEqual(global_code(lines)[2:5], ["t1 = method b.saludar", "param b", "t1 = call t1, 1"])

    def test_class_example(self) -> None:
        source = (PROJECT / "examples" / "tac_clases.cps").read_text(encoding="utf-8")
        lines = tac_lines(source)
        self.assertIn("begin_func Cuadrado.area, 24", lines)
        self.assertIn("call Rectangulo.constructor, 3", global_code(lines))


class InvalidObjectTests(unittest.TestCase):
    def test_semantic_errors_prevent_generation(self) -> None:
        for source in [
            "let x = new NoExiste();",
            "class A { } let a: A = new A(); a.volar();",
            "class A { let x: integer; } let a: A = new A(); print(a.y);",
            "class A { function constructor(n: integer) { } } let a: A = new A();",
            "class B : Fantasma { }",
            "print(this);",
            "class A { let x: integer; } let a: A = new A(); a.x = \"texto\";",
        ]:
            with self.subTest(source=source):
                result = compile_source(source)
                self.assertTrue(result.diagnostics)
                self.assertIsNone(result.tac)

    def test_this_outside_method_rejected_when_semantics_is_bypassed(self) -> None:
        program = ast.Program(
            span=SPAN,
            statements=(ast.PrintStatement(span=SPAN, expression=ast.ThisExpression(span=SPAN)),),
        )
        with self.assertRaisesRegex(TACGenerationError, "this"):
            TACGenerator(SymbolTable()).generate(program)

    def test_unknown_class_rejected_when_semantics_is_bypassed(self) -> None:
        program = ast.Program(
            span=SPAN,
            statements=(
                ast.ExpressionStatement(
                    span=SPAN, expression=ast.NewExpression(span=SPAN, class_name="Fantasma", arguments=())
                ),
            ),
        )
        with self.assertRaisesRegex(TACGenerationError, "Fantasma"):
            TACGenerator(SymbolTable()).generate(program)


if __name__ == "__main__":
    unittest.main()
