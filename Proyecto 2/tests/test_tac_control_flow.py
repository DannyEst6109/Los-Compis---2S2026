"""Verifica la traducción estática a TAC; no ejecuta Compiscript ni el TAC."""
import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

import ast_nodes as ast
from analyzer import CompiscriptAnalyzer
from semantic_analyzer import analyze_semantics
from symbol_table import SymbolTable, build_symbol_table
from tac import Const, Label, TACOp, Temp
from tac_generator import TACGenerationError, TACGenerator, infer_expression_types


def diagnostics(source):
    result = CompiscriptAnalyzer().analyze(source)
    table, scope_errors = build_symbol_table(result.ast)
    errors = [*result.diagnostics, *scope_errors, *analyze_semantics(table, result.ast)]
    return result.ast, table, errors


def generate(source):
    program, table, errors = diagnostics(source)
    if errors:
        raise AssertionError(errors)
    generator = TACGenerator(table, infer_expression_types(table, program))
    generator.generate(program)
    return generator


class ControlFlowTests(unittest.TestCase):
    def checked(self, source):
        generator = generate(source)
        self.assertEqual(generator.temps.live_count, 0)
        self.assertEqual(generator._control_stack, [])
        instructions = generator.program.instructions
        labels = [i.result for i in instructions if i.op is TACOp.LABEL]
        self.assertEqual(len(labels), len(set(labels)))
        for instruction in instructions:
            if instruction.op in {TACOp.GOTO, TACOp.IF_TRUE, TACOp.IF_FALSE}:
                self.assertIn(instruction.result, labels)
        return generator

    def test_if_else_has_exclusive_branches(self):
        lines = self.checked('let x = 0; if (true) { x = 1; } else { x = 2; }').program.lines()
        self.assertEqual(lines, ['x = 0', 'if true goto L1', 'goto L2', 'L1:',
                                 'x = 1', 'goto L3', 'L2:', 'x = 2', 'L3:'])

    def test_if_without_else(self):
        lines = self.checked('if (false) { print(1); } print(2);').program.lines()
        self.assertEqual(lines[-3:], ['print 1', 'L2:', 'print 2'])

    def test_while_recomputes_condition_at_header(self):
        lines = self.checked('let x = 0; while (x < 3) { x = x + 1; }').program.lines()
        self.assertEqual(lines[1:4], ['L1:', 't1 = x < 3', 'if t1 goto L2'])
        self.assertEqual(lines[-2:], ['goto L1', 'L3:'])

    def test_while_continue_and_break(self):
        lines = self.checked('while (true) { if (true) { continue; } else { break; } }').program.lines()
        self.assertIn('goto L1', lines[5:])
        self.assertIn('goto L3', lines[5:])

    def test_do_while_continue_targets_test_after_body(self):
        lines = self.checked('do { print(1); continue; } while (false);').program.lines()
        self.assertEqual(lines[:4], ['L1:', 'print 1', 'goto L2', 'L2:'])
        self.assertEqual(lines[4:], ['if false goto L1', 'goto L3', 'L3:'])

    def test_for_continue_targets_update(self):
        lines = self.checked('for (let i = 0; i < 3; i = i + 1) { continue; }').program.lines()
        self.assertIn('L2:', lines)
        self.assertEqual(lines[lines.index('L2:')+1:lines.index('L3:')+3],
                         ['goto L3', 'L3:', 't1 = i + 1', 'i = t1'])

    def test_for_optional_parts(self):
        lines = self.checked('for (;;) { break; }').program.lines()
        self.assertEqual(lines, ['L1:', 'L2:', 'goto L4', 'L3:', 'goto L1', 'L4:'])

    def test_for_expression_initializer(self):
        lines = self.checked('let i = 9; for (i = 0; i < 1;) { break; }').program.lines()
        self.assertEqual(lines[:2], ['i = 9', 'i = 0'])

    def test_nested_loops_break_targets_nearest_loop(self):
        lines = self.checked('while (true) { while (true) { break; } break; }').program.lines()
        self.assertEqual(lines[lines.index('L5:')+1], 'goto L6')
        self.assertEqual(lines[lines.index('L6:')+1], 'goto L3')

    def test_foreach_persistent_temporaries_and_continue(self):
        generator = self.checked('let a = [1,2]; foreach (x in a) { print(x + 1); continue; }')
        instructions = generator.program.instructions
        load = next(i for i in instructions if i.op is TACOp.INDEX_LOAD)
        length = next(i for i in instructions if i.op is TACOp.LENGTH)
        self.assertEqual(load.arg1, length.arg1)
        update = next(i for i in instructions if i.op is TACOp.ADD and i.result == load.arg2)
        self.assertEqual(update.arg1, load.arg2)
        body_add = next(i for i in instructions if i.op is TACOp.ADD and i is not update)
        self.assertNotIn(body_add.result, (load.arg1, load.arg2, length.result))
        lines = generator.program.lines()
        self.assertIn('goto L2', lines)

    def test_foreach_literal_and_empty_arrays(self):
        self.checked('foreach (x in [1, 2]) { print(x); }')
        self.checked('let a: integer[] = []; foreach (x in a) { print(x); }')

    def test_foreach_snapshot_survives_source_reassignment(self):
        generator = self.checked('let a = [1]; foreach (x in a) { a = [2]; print(x); }')
        load = next(i for i in generator.program if i.op is TACOp.INDEX_LOAD)
        self.assertIsInstance(load.arg1, Temp)

    def test_nested_foreach_has_distinct_iteration_temporaries(self):
        generator = self.checked('foreach (x in [1]) { foreach (y in [2]) { print(x+y); } }')
        loads = [i for i in generator.program if i.op is TACOp.INDEX_LOAD]
        self.assertNotEqual(loads[0].arg1, loads[1].arg1)
        self.assertNotEqual(loads[0].arg2, loads[1].arg2)

    def test_switch_break_and_default(self):
        lines = self.checked('switch (2) { case 1: print(1); break; case 2: print(2); break; default: print(3); }').program.lines()
        self.assertEqual(lines[:5], ['t1 = 2 == 1', 'if t1 goto L1',
                                     't1 = 2 == 2', 'if t1 goto L2', 'goto L3'])
        self.assertEqual(lines[-3:], ['L3:', 'print 3', 'L4:'])
        self.assertEqual(lines.count('goto L4'), 2)

    def test_switch_fallthrough_has_no_implicit_jump(self):
        lines = self.checked('switch (1) { case 1: print(1); case 2: print(2); }').program.lines()
        self.assertEqual(lines[lines.index('L1:'):lines.index('L2:')+2],
                         ['L1:', 'print 1', 'L2:', 'print 2'])

    def test_switch_selector_evaluated_once_and_snapshotted(self):
        generator = self.checked('let x = 1; switch (x = x + 1) { case 2: print(x); case 3: print(x); }')
        self.assertEqual(sum(i.op is TACOp.ADD for i in generator.program), 1)
        comparisons = [i for i in generator.program if i.op is TACOp.EQ]
        self.assertIsInstance(comparisons[0].arg1, Temp)
        self.assertEqual(comparisons[0].arg1, comparisons[1].arg1)

    def test_switch_continue_targets_surrounding_loop(self):
        lines = self.checked('for (;;) { switch (1) { case 1: continue; default: break; } break; }').program.lines()
        self.assertEqual(lines[lines.index('L5:')+1], 'goto L3')
        self.assertEqual(lines[lines.index('L6:')+1], 'goto L7')
        self.assertEqual(lines[lines.index('L7:')+1], 'goto L4')

    def test_empty_switch_and_default_only(self):
        self.checked('switch (1) {}')
        self.checked('switch (1) { default: print(0); }')

    def test_and_skips_right_hand_assignment(self):
        lines = self.checked('let b = false; let x = false && (b = true);').program.lines()
        rhs_label = lines[1].split()[-1] + ':'
        self.assertEqual(lines[2], 'goto L2')
        self.assertLess(lines.index(rhs_label), lines.index('b = true'))
        self.assertLess(lines.index('b = true'), lines.index('L1:'))

    def test_or_skips_right_hand_assignment(self):
        lines = self.checked('let b = false; let x = true || (b = true);').program.lines()
        self.assertEqual(lines[1], 'if true goto L1')
        rhs_label = lines[2].split()[-1] + ':'
        self.assertLess(lines.index(rhs_label), lines.index('b = true'))

    def test_nested_boolean_negation_and_precedence(self):
        self.checked('let a = 1; if (!(a < 2 && a != 0) || false) { print(1); }')
        self.checked('let b = (true || false) && !false; print(b);')

    def test_ternary_branches_are_separated_and_share_result(self):
        generator = self.checked('let x = true ? 1 + 2 : 3 + 4;')
        assignments = [i for i in generator.program if i.op is TACOp.ASSIGN and isinstance(i.result, Temp)]
        self.assertEqual(len(assignments), 2)
        self.assertEqual(assignments[0].result, assignments[1].result)
        lines = generator.program.lines()
        self.assertLess(lines.index('goto L3'), lines.index('t2 = 3 + 4'))

    def test_nested_ternary_and_boolean_value(self):
        self.checked('let x = true ? (false ? 1 : 2) : 3; print(x);')
        self.checked('let b = true && (false || true); print(b);')

    def test_labels_deterministic_per_generation(self):
        source = 'while (true) { if (true) { break; } }'
        self.assertEqual(self.checked(source).program.lines(), self.checked(source).program.lines())

    def test_example_file(self):
        self.checked((PROJECT / 'examples' / 'tac_control_flujo.cps').read_text(encoding='utf-8'))


class InvalidControlFlowTests(unittest.TestCase):
    def test_invalid_programs_report_errors_before_generation(self):
        for source in ['break;', 'continue;', 'if (1) {}', 'while ("x") {}',
                       'for (;1;) {}', 'foreach (x in 1) {}',
                       'switch (1) { case true: break; }',
                       'switch (1) { case 1: continue; }',
                       'let x = true && 1;', 'let x = true ? 1 : "x";',
                       'while (true) { function f() { break; } }',
                       'switch (1) { case 1: function f() { break; } }']:
            with self.subTest(source=source):
                self.assertTrue(diagnostics(source)[2])

    def test_multiple_control_errors_are_collected(self):
        errors = diagnostics('{ break; } { continue; } if (1) {} foreach (x in 1) {}')[2]
        self.assertGreaterEqual(len(errors), 4)

    def test_invalid_jump_rejected_even_when_semantic_phase_is_bypassed(self):
        span = ast.SourceSpan.unknown()
        for node in [ast.BreakStatement(span=span), ast.ContinueStatement(span=span)]:
            generator = TACGenerator(SymbolTable())
            with self.assertRaises(TACGenerationError):
                generator.visit(node)
            self.assertEqual(len(generator.program), 0)

    def test_context_is_restored_when_body_translation_fails(self):
        program, table, _ = diagnostics('while (true) { print(missing); }')
        generator = TACGenerator(table)
        with self.assertRaises(TACGenerationError):
            generator.generate(program)
        self.assertEqual(generator._control_stack, [])

    def test_error_example_reports_multiple_errors(self):
        source = (PROJECT / 'examples' / 'tac_control_flujo_errores.cps').read_text(encoding='utf-8')
        self.assertGreaterEqual(len(diagnostics(source)[2]), 3)


if __name__ == '__main__':
    unittest.main()
