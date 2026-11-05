"""Ejemplos cortos por criterio de la rúbrica (examples/NN_*.cps).

Cada archivo debe compilar sin errores y traer al final un caso de error
comentado: la línea que sigue a «// Esperado:» (y a sus líneas de
continuación). Al quitarle el «//», el programa debe fallar con un
diagnóstico y no generar código intermedio.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from compiler import compile_source  # noqa: E402

RUBRIC_EXAMPLES = sorted((PROJECT / "examples").glob("[0-9][0-9]_*.cps"))


def with_error_uncommented(source: str) -> str:
    """Devuelve ``source`` con la línea de error descomentada (la última
    línea comentada del archivo, que viene después de «// Esperado:»)."""
    lines = source.splitlines()
    expected = next(index for index, line in enumerate(lines) if line.startswith("// Esperado:"))
    error_line = max(index for index, line in enumerate(lines) if line.startswith("// "))
    if error_line <= expected:
        raise AssertionError("No hay una línea de error comentada después de «// Esperado:».")
    lines[error_line] = lines[error_line][3:]
    return "\n".join(lines)


class RubricExampleTests(unittest.TestCase):
    def test_one_example_per_rubric_criterion(self) -> None:
        self.assertEqual([path.name[:2] for path in RUBRIC_EXAMPLES], [f"{n:02d}" for n in range(1, 14)])

    def test_every_example_compiles_without_errors(self) -> None:
        for path in RUBRIC_EXAMPLES:
            with self.subTest(example=path.name):
                result = compile_source(path.read_text(encoding="utf-8"))
                self.assertEqual(result.diagnostics, [])
                self.assertTrue(result.succeeded)

    def test_every_commented_error_fails_without_generating_tac(self) -> None:
        for path in RUBRIC_EXAMPLES:
            with self.subTest(example=path.name):
                result = compile_source(with_error_uncommented(path.read_text(encoding="utf-8")))
                self.assertGreater(len(result.diagnostics), 0)
                self.assertIsNone(result.tac)
                self.assertFalse(result.succeeded)


if __name__ == "__main__":
    unittest.main()
