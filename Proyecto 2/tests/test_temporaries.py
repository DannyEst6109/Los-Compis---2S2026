"""Pruebas del algoritmo de asignación y reciclaje de temporales."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from tac import Const, Temp, Var  # noqa: E402
from temporaries import TempAllocator, TempAllocatorError  # noqa: E402


class AllocationTests(unittest.TestCase):
    def test_creates_consecutive_temporaries(self) -> None:
        temps = TempAllocator()
        self.assertEqual([temps.new() for _ in range(3)], [Temp(1), Temp(2), Temp(3)])
        self.assertEqual(temps.live_count, 3)
        self.assertEqual(temps.created, 3)

    def test_released_temporary_is_reused(self) -> None:
        temps = TempAllocator()
        t1 = temps.new()
        temps.release(t1)
        self.assertEqual(temps.new(), Temp(1))
        self.assertEqual(temps.created, 1)
        self.assertEqual(temps.reuses, 1)

    def test_lowest_free_index_is_reused_first(self) -> None:
        temps = TempAllocator()
        t1, t2, t3 = temps.new(), temps.new(), temps.new()
        temps.release(t3)
        temps.release(t1)
        self.assertEqual(temps.new(), Temp(1))
        self.assertEqual(temps.new(), Temp(3))
        self.assertEqual(temps.new(), Temp(4))
        self.assertTrue(temps.is_live(t2))

    def test_max_live_tracks_peak_not_total(self) -> None:
        temps = TempAllocator()
        for _ in range(5):
            temps.release(temps.new())
        self.assertEqual(temps.max_live, 1)
        self.assertEqual(temps.allocations, 5)
        self.assertEqual(temps.created, 1)

    def test_releasing_non_temporaries_is_a_no_op(self) -> None:
        temps = TempAllocator()
        t1 = temps.new()
        temps.release(Var("x"))
        temps.release(Const(1, "integer"))
        temps.release(None)
        self.assertEqual(temps.live_count, 1)
        self.assertTrue(temps.is_live(t1))
        self.assertFalse(temps.is_live(Var("t1")))

    def test_reset_starts_over(self) -> None:
        temps = TempAllocator()
        temps.new()
        temps.new()
        temps.reset()
        self.assertEqual(temps.live_count, 0)
        self.assertEqual(temps.new(), Temp(1))


class MisuseTests(unittest.TestCase):
    """Casos fallidos: errores del generador que el asignador detecta."""

    def test_double_release(self) -> None:
        temps = TempAllocator()
        t1 = temps.new()
        temps.release(t1)
        with self.assertRaises(TempAllocatorError):
            temps.release(t1)

    def test_release_of_unknown_temporary(self) -> None:
        temps = TempAllocator()
        with self.assertRaises(TempAllocatorError):
            temps.release(Temp(9))

    def test_failed_release_does_not_corrupt_state(self) -> None:
        temps = TempAllocator()
        t1 = temps.new()
        with self.assertRaises(TempAllocatorError):
            temps.release(Temp(2))
        self.assertTrue(temps.is_live(t1))
        self.assertEqual(temps.new(), Temp(2))


if __name__ == "__main__":
    unittest.main()
