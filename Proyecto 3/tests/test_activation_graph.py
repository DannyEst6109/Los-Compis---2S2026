"""Disposición del grafo y navegación de las activaciones del IDE."""

import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from activation_graph import ActivationGraph, layout_activations
from activation_tree import Activation, build_activation_tree
from ui import CompiscriptApp


class ActivationLayoutTests(unittest.TestCase):
    def test_siblings_keep_execution_order_and_distinct_activations(self):
        root = build_activation_tree("#>f 1\n#<f\n#>f 1\n#<f\n")
        nodes, limited = layout_activations(root, set())
        self.assertFalse(limited)
        self.assertEqual([node.parent for node in nodes], [None, 0, 0])
        self.assertLess(nodes[1].x, nodes[2].x)
        self.assertEqual(nodes[0].x, (nodes[1].x + nodes[2].x) / 2)
        self.assertIsNot(nodes[1].activation, nodes[2].activation)

    def test_collapsing_preserves_the_source_tree(self):
        root = build_activation_tree("#>f 2\n#>f 1\n#<f\n#<f\n")
        nodes, _ = layout_activations(root, {id(root.children[0])})
        self.assertEqual(len(nodes), 2)
        self.assertEqual(root.count(), 2)

    def test_deep_and_wide_trees_have_bounded_iterative_layout(self):
        root = Activation("main")
        node = root
        for _ in range(1200):
            child = Activation("f")
            node.children.append(child)
            node = child
        nodes, limited = layout_activations(root, set())
        self.assertEqual(len(nodes), 500)
        self.assertTrue(limited)
        self.assertEqual(nodes[-1].depth, 499)
        root = Activation("main", children=[Activation("f") for _ in range(700)])
        nodes, limited = layout_activations(root, set())
        self.assertEqual(len(nodes), 500)
        self.assertTrue(limited)


class ActivationGraphWidgetTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.root.withdraw()
        self.graph = ActivationGraph(self.root, CompiscriptApp)
        self.graph.pack(fill="both", expand=True)

    def tearDown(self):
        self.root.destroy()

    def test_empty_and_new_execution_clear_previous_nodes(self):
        self.assertEqual(self.graph.nodes, [])
        tree = build_activation_tree("#>f 1\n#<f\n")
        self.graph.show_tree(tree)
        self.assertEqual(len(self.graph.nodes), 2)
        self.graph.clear()
        self.assertEqual(self.graph.nodes, [])
        self.assertIsNone(self.graph.tree)
        self.graph.show_tree(build_activation_tree(""))
        self.assertEqual(len(self.graph.nodes), 1)

    def test_keyboard_collapse_zoom_and_exception_state(self):
        tree = build_activation_tree("#>f 2\n#>f 1\n#<*\n#<f\n")
        self.graph.show_tree(tree)
        self.graph._navigate(1)
        self.graph._toggle_selected()
        self.assertEqual(len(self.graph.nodes), 2)
        self.graph._toggle_selected()
        self.assertEqual(len(self.graph.nodes), 3)
        self.assertEqual(self.graph._status(tree.children[0].children[0]), "Interrumpida por excepción")
        self.graph.set_zoom(20)
        self.assertEqual(self.graph.zoom, 1.75)
        self.graph.set_zoom(0)
        self.assertEqual(self.graph.zoom, 0.5)


if __name__ == "__main__":
    unittest.main()
