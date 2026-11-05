from __future__ import annotations

import sys
import unittest
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

import ast_nodes as ast  # noqa: E402
from analyzer import CompiscriptAnalyzer  # noqa: E402
from ast_visualization import VisualAstNode, build_visual_tree  # noqa: E402
from ast_visitor import AstVisitor  # noqa: E402


def visual_labels(node: VisualAstNode) -> set[str]:
    labels = {node.label}
    for child in node.children:
        labels.update(visual_labels(child))
    return labels


class RecordingVisitor(AstVisitor[None]):
    def __init__(self) -> None:
        self.names: list[str] = []

    def generic_visit(self, node: ast.AstNode) -> None:
        self.names.append(type(node).__name__)
        super().generic_visit(node)


class AstTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.analyzer = CompiscriptAnalyzer()

    def test_operator_precedence_is_preserved(self) -> None:
        result = self.analyzer.analyze("let total: integer = 1 + 2 * 3;")

        self.assertTrue(result.is_valid, result.diagnostics)
        self.assertIsInstance(result.ast, ast.Program)
        declaration = result.ast.statements[0]
        self.assertIsInstance(declaration, ast.VariableDeclaration)
        self.assertIsInstance(declaration.initializer, ast.BinaryExpression)
        self.assertEqual(declaration.initializer.operator, "+")
        self.assertIsInstance(declaration.initializer.right, ast.BinaryExpression)
        self.assertEqual(declaration.initializer.right.operator, "*")

    def test_full_example_contains_required_constructs(self) -> None:
        source = (PROJECT / "examples" / "valido_completo.cps").read_text(encoding="utf-8")
        result = self.analyzer.analyze(source)

        self.assertTrue(result.is_valid, result.diagnostics)
        visitor = RecordingVisitor()
        result.ast.accept(visitor)
        present = set(visitor.names)
        expected = {
            "Program", "ClassDeclaration", "FunctionDeclaration", "VariableDeclaration",
            "ConstantDeclaration", "IfStatement", "ForStatement", "ForeachStatement",
            "DoWhileStatement", "WhileStatement", "SwitchStatement", "TryCatchStatement",
            "ArrayExpression", "CallExpression", "MemberExpression", "IndexExpression",
            "AssignmentExpression", "ConditionalExpression", "ReturnStatement",
        }
        self.assertTrue(expected.issubset(present), expected - present)
        self.assertGreater(result.ast_node_count, 150)

    def test_ast_is_available_after_parser_recovery(self) -> None:
        result = self.analyzer.analyze("let x: integer = ; print(x);")

        self.assertGreaterEqual(result.syntactic_count, 1)
        self.assertIsInstance(result.ast, ast.Program)
        self.assertEqual(len(result.ast.statements), 2)
        self.assertGreater(result.ast_node_count, 2)

    def test_visual_tree_exposes_roles_details_and_locations(self) -> None:
        result = self.analyzer.analyze(
            "function suma(a: integer, b: integer): integer { return a + b; }"
        )
        visual = build_visual_tree(result.ast)
        labels = visual_labels(visual)

        self.assertEqual(visual.label, "Programa")
        self.assertIn("Función", labels)
        self.assertIn("Parámetros", labels)
        self.assertIn("Tipo de retorno", labels)
        self.assertIn("Operación binaria", labels)
        self.assertEqual(visual.location, "1:1")

    def test_base_visitor_can_be_extended_without_antlr(self) -> None:
        result = self.analyzer.analyze("let x = 1; print(x);")
        visitor = RecordingVisitor()

        result.ast.accept(visitor)

        self.assertEqual(visitor.names[0], "Program")
        self.assertIn("VariableDeclaration", visitor.names)
        self.assertIn("PrintStatement", visitor.names)
        self.assertNotIn("ProgramContext", visitor.names)


if __name__ == "__main__":
    unittest.main(verbosity=2)
