"""Reglas reales de ANTLR, determinización, prioridad y recorrido del IDE."""

import itertools
import sys
import tkinter as tk
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analyzer import CompiscriptLexer
from antlr4 import InputStream
from lexical_automaton import MAX_CHAR, build_automaton, lexer_description, token_rules
from ui import CompiscriptApp


class LexicalAutomatonTests(unittest.TestCase):
    def test_all_rules_generate_deterministic_graphs_without_epsilon(self):
        self.assertEqual(len(token_rules()), 61)
        self.assertNotIn("EscapeSequence", token_rules())
        for rule in token_rules():
            with self.subTest(rule=rule):
                automaton = build_automaton(rule)
                self.assertGreater(automaton.state_count, 1)
                self.assertTrue(automaton.accepting)
                self.assertFalse(automaton.trace("").accepted)
                for source in range(automaton.state_count):
                    intervals = sorted((low, high) for edge in automaton.edges if edge.source == source
                                       for low, high in edge.ranges)
                    self.assertTrue(all(0 <= low <= high <= MAX_CHAR for low, high in intervals))
                    self.assertTrue(all(one[1] < two[0] for one, two in zip(intervals, intervals[1:])))

    def test_literal_tokens_match_the_generated_lexer(self):
        for token_type, literal in enumerate(CompiscriptLexer.literalNames[1:], 1):
            with self.subTest(literal=literal):
                text = literal[1:-1]
                automaton = build_automaton(CompiscriptLexer.symbolicNames[token_type])
                self.assertTrue(automaton.trace(text).accepted)
                self.assertFalse(automaton.trace(text + "a").accepted)
                self.assertFalse(automaton.trace(text[:-1]).accepted)

    def test_identifiers_integers_and_failure_position(self):
        identifier = build_automaton("Identifier")
        self.assertEqual(identifier.state_count, 2)  # inicial + aceptación con ciclo
        for text in ("a", "_", "contador_1", "let"):
            self.assertTrue(identifier.trace(text).accepted)
        for text in ("", "1nombre", "café", "a b"):
            self.assertFalse(identifier.trace(text).accepted)
        result = build_automaton("IntegerLiteral").trace("123a")
        self.assertEqual(result.failed_at, 3)
        self.assertEqual(result.states, (0, 1, 1, 1))

    def test_string_fragments_unicode_and_incomplete_inputs(self):
        automaton = build_automaton("StringLiteral")
        for text in ('""', '"café 😀"', '"a\\n\\t\\r\\\\\\\"b"'):
            with self.subTest(text=text):
                self.assertTrue(automaton.trace(text).accepted)
        for text in ('"sin cerrar', '"a\\q"', '"salto\nreal"', '"x" extra'):
            with self.subTest(text=text):
                self.assertFalse(automaton.trace(text).accepted)

    def test_skipped_rules_and_non_greedy_scope_are_explicit(self):
        self.assertTrue(build_automaton("WS").trace(" \t\r\n").accepted)
        self.assertTrue(build_automaton("LINE_COMMENT").trace("// comentario").accepted)
        self.assertFalse(build_automaton("LINE_COMMENT").trace("// comentario\n").accepted)
        self.assertTrue(build_automaton("BLOCK_COMMENT").trace("/* a\nb */").accepted)
        self.assertFalse(build_automaton("BLOCK_COMMENT").trace("/* abierto").accepted)
        self.assertTrue(build_automaton("BLOCK_COMMENT").trace("/* a */ x */").accepted)
        self.assertIn("único token", lexer_description("/* a */ x */"))

    def test_selected_rule_and_real_token_priority_are_distinguished(self):
        self.assertTrue(build_automaton("Identifier").trace("let").accepted)
        self.assertEqual(lexer_description("let"), "Lexer real: LET.")
        self.assertEqual(lexer_description("letra"), "Lexer real: Identifier.")
        self.assertIn("errores léxicos", lexer_description("@"))

    def test_short_accepted_inputs_agree_with_actual_tokenization(self):
        automata = [build_automaton(rule) for rule in token_rules()]
        for size in range(1, 4):
            for letters in itertools.product("a1_+=", repeat=size):
                text = "".join(letters)
                matches = [a.rule for a in automata if a.trace(text).accepted]
                if matches:
                    lexer = CompiscriptLexer(InputStream(text))
                    token = lexer.nextToken()
                    self.assertEqual(token.text, text)
                    self.assertEqual(lexer.symbolicNames[token.type], matches[0])


class AutomatonPanelTests(unittest.TestCase):
    def setUp(self):
        try:
            self.root = tk.Tk()
        except tk.TclError as error:
            self.skipTest(str(error))
        self.root.withdraw()
        self.app = CompiscriptApp(self.root)
        self.panel = self.app.automaton_panel

    def tearDown(self):
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()

    def test_step_accept_reject_and_edit_reset(self):
        panel = self.panel
        panel.input.set("a1")
        panel.step()
        self.assertEqual(panel.badge.cget("text"), "EN RECORRIDO")
        self.assertEqual(panel.trace.states, (0, 1))
        panel.step()
        self.assertEqual(panel.badge.cget("text"), "ACEPTADA")
        panel.input.set("1a")
        self.assertEqual(panel.badge.cget("text"), "LISTO")
        panel.evaluate()
        self.assertEqual(panel.badge.cget("text"), "RECHAZADA")
        self.assertEqual(panel.trace.failed_at, 0)
        self.assertTrue(panel.canvas.find_all())

    def test_change_rule_incomplete_empty_and_oversized_inputs(self):
        panel = self.panel
        panel.rule.set("EQUAL")
        panel.change_rule()
        panel.input.set("=")
        panel.evaluate()
        self.assertEqual(panel.badge.cget("text"), "RECHAZADA")
        self.assertIsNone(panel.trace.failed_at)
        panel.input.set("==")
        panel.evaluate()
        self.assertEqual(panel.badge.cget("text"), "ACEPTADA")
        panel.input.set("")
        panel.evaluate()
        self.assertEqual(panel.badge.cget("text"), "RECHAZADA")
        panel.input.set("a" * 2001)
        panel.evaluate()
        self.assertEqual(panel.badge.cget("text"), "ENTRADA MUY LARGA")


if __name__ == "__main__":
    unittest.main()
