"""Regresiones de herencia y retornos, desde fuente hasta el pipeline real."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from compiler import compile_source


class InheritedAttributeTests(unittest.TestCase):
    def test_incompatible_inherited_types_block_code_generation(self):
        cases = [
            ("boolean = true", "integer = 300"),
            ("integer = 300", "boolean = true"),
            ("string = \"a\"", "integer = 1"),
            ("integer[] = [1]", "boolean[] = [true]"),
        ]
        for base, derived in cases:
            with self.subTest(base=base, derived=derived):
                result = compile_source(f"class A {{ let x: {base}; }} class B: A {{ let x: {derived}; }}")
                self.assertEqual(len(result.diagnostics), 1)
                self.assertEqual(result.diagnostics[0].kind, "Semántico")
                self.assertIn("atributo heredado", result.diagnostics[0].description)
                self.assertIsNone(result.tac)
                self.assertIsNone(result.mips)

    def test_inferred_forward_and_indirect_inheritance_are_checked(self):
        for source in (
            "class A { let x = true; } class B: A { let x = 300; }",
            "class B: A { let x = 300; } class A { let x = true; }",
            "class A { let x = true; } class B: A {} class C: B { let x = 300; }",
        ):
            with self.subTest(source=source):
                result = compile_source(source)
                self.assertTrue(any("atributo heredado" in d.description for d in result.diagnostics))
                self.assertIsNone(result.tac)

    def test_same_type_and_new_attributes_remain_valid(self):
        result = compile_source("""
            class A { let x = 1; }
            class B: A { let x = 300; let y: boolean = true; }
            let b: B = new B(); print(b.x);
        """)
        self.assertEqual(result.diagnostics, [])
        self.assertIsNotNone(result.mips)


class CompleteReturnTests(unittest.TestCase):
    def test_paths_without_a_return_block_code_generation(self):
        bodies = [
            "",
            "if (flag) { return 1; }",
            "while (flag) { return 1; }",
            "for (; flag;) { return 1; }",
            "foreach (x in [1, 2]) { return x; }",
            "switch (n) { case 1: return 1; }",
            "switch (n) { case 1: break; default: return 2; }",
            "try { return 1; } catch (e) { print(e); }",
            "try { print(1); } catch (e) { return 2; }",
            "function inner(): integer { return 1; }",
            "while (true) { if (flag) { break; } }",
            "do { if (flag) { continue; } return 1; } while (false);",
        ]
        for body in bodies:
            with self.subTest(body=body):
                result = compile_source(f"function f(flag: boolean, n: integer): integer {{ {body} }}")
                self.assertEqual(len(result.diagnostics), 1, result.diagnostics)
                self.assertIn("puede terminar sin devolver", result.diagnostics[0].description)
                self.assertIsNone(result.tac)
                self.assertIsNone(result.mips)

    def test_complete_returns_and_nonterminating_paths_remain_valid(self):
        bodies = [
            "return 1;",
            "if (flag) { return 1; } else { return 2; }",
            "if (flag) { return 1; } return 2;",
            "if (true) { return 1; }",
            "while (true) { return 1; }",
            "for (;;) { continue; }",
            "while (!(false)) { continue; }",
            "do { return 1; } while (flag);",
            "switch (n) { case 1: print(1); case 2: return 2; default: return 3; }",
            "try { return 1; } catch (e) { return 2; }",
            "while (true) { switch (n) { case 1: break; default: continue; } }",
            "while (true) { while (flag) { break; } }",
            "while (true) { if (flag) { break; } } return 1;",
        ]
        for body in bodies:
            with self.subTest(body=body):
                result = compile_source(f"function f(flag: boolean, n: integer): integer {{ {body} }}")
                self.assertEqual(result.diagnostics, [])
                self.assertIsNotNone(result.mips)

    def test_procedures_can_still_finish_without_returning(self):
        result = compile_source("function f(flag: boolean) { if(flag) { return; } }")
        self.assertEqual(result.diagnostics, [])
        self.assertIsNotNone(result.mips)


if __name__ == "__main__":
    unittest.main()
