"""Pipeline completo del compilador: código fuente -> diagnósticos o TAC y MIPS.

Es el único punto de integración que necesita el IDE (y las pruebas de
integración)::

    from compiler import compile_source

    result = compile_source(source)
    if result.succeeded:
        print(result.tac.render())
        print(result.mips.text)
    else:
        for diagnostic in result.diagnostics:
            print(diagnostic)

Orden de las fases:

1. ``CompiscriptAnalyzer``: análisis léxico, sintáctico y construcción del AST.
2. ``build_symbol_table``: ámbitos y declaraciones.
3. ``analyze_semantics``: tipos y flujo.
4. Sólo si las tres fases terminaron **sin ningún diagnóstico**:
   ``prepare_generator`` (tipos inferidos + direcciones y registros de
   activación en la tabla de símbolos) y ``TACGenerator.generate``.

5. Sólo si el TAC se generó sin errores: ``mips_generator.generate_mips``
   traduce **ese mismo TAC** a MIPS (Proyecto 3) y aplica la optimización
   por mirilla.

Si alguna fase reporta errores no se genera código intermedio ni
ensamblador. Si la generación falla, el error se reporta como diagnóstico
de «Generación» y tampoco se entrega código parcial: un error al generar
MIPS deja el TAC (que sí es correcto) pero no el ensamblador.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from analyzer import AnalysisResult, CompiscriptAnalyzer
from mips_frames import MipsFrameError
from mips_generator import MipsProgram, generate_mips
from semantic_analyzer import analyze_semantics
from symbol_table import Diagnostic, SymbolTable, build_symbol_table
from tac import TACProgram
from tac_generator import TACGenerationError, prepare_generator
from temporaries import TempAllocatorError

GENERATION_KIND = "Generación"
_KIND_ORDER = {"Léxico": 0, "Sintáctico": 1, "Semántico": 2, GENERATION_KIND: 3}


@dataclass(frozen=True, slots=True)
class TempUsage:
    """Estadísticas del reciclaje de temporales de una unidad (función,
    método o código global)."""

    unit: str
    created: int
    allocations: int
    reuses: int
    max_live: int


@dataclass(slots=True)
class CompilationResult:
    analysis: AnalysisResult
    symbol_table: SymbolTable | None
    diagnostics: list = field(default_factory=list)
    tac: TACProgram | None = None
    temp_usage: list[TempUsage] = field(default_factory=list)
    mips: MipsProgram | None = None

    @property
    def succeeded(self) -> bool:
        return self.tac is not None and not self.diagnostics

    def count(self, kind: str) -> int:
        return sum(1 for diagnostic in self.diagnostics if diagnostic.kind == kind)


def merge_diagnostics(*groups) -> list:
    combined = [diagnostic for group in groups for diagnostic in group]
    combined.sort(key=lambda item: (item.line, item.column, _KIND_ORDER.get(item.kind, 4)))
    return combined


def compile_source(
    source: str,
    analyzer: CompiscriptAnalyzer | None = None,
    *,
    assembly: bool = True,
    trace: bool = False,
    optimize: bool = True,
) -> CompilationResult:
    """Compila ``source``. ``assembly=False`` se detiene en el TAC;
    ``trace`` agrega al MIPS la traza del árbol de activación y
    ``optimize`` aplica la optimización por mirilla."""
    analysis = (analyzer or CompiscriptAnalyzer()).analyze(source)
    table, scope_diagnostics = build_symbol_table(analysis.ast)
    type_diagnostics = analyze_semantics(table, analysis.ast)
    result = CompilationResult(
        analysis=analysis,
        symbol_table=table if analysis.ast is not None else None,
        diagnostics=merge_diagnostics(analysis.diagnostics, scope_diagnostics, type_diagnostics),
    )
    if result.diagnostics or analysis.ast is None:
        return result

    try:
        generator = prepare_generator(table, analysis.ast)
        tac = generator.generate(analysis.ast)
    except TACGenerationError as error:
        message = str(error).split(": ", 1)[-1]
        result.diagnostics = [Diagnostic(GENERATION_KIND, error.line, error.column, "TAC", message)]
        return result
    except TempAllocatorError as error:
        result.diagnostics = [Diagnostic(GENERATION_KIND, 1, 1, "TAC", str(error))]
        return result

    result.tac = tac
    result.temp_usage = [
        TempUsage(unit, temps.created, temps.allocations, temps.reuses, temps.max_live)
        for unit, temps in generator.unit_temps
    ]
    if assembly:
        result.mips, error = assemble(table, tac, trace=trace, optimize=optimize)
        if error is not None:
            result.diagnostics = [error]
    return result


def assemble(
    table: SymbolTable, tac: TACProgram, *, trace: bool = False, optimize: bool = True
) -> tuple[MipsProgram | None, Diagnostic | None]:
    """Genera el MIPS a partir del TAC. Devuelve el programa o el
    diagnóstico de «Generación» que explica por qué no se pudo."""
    try:
        return generate_mips(table, tac, trace=trace, optimize=optimize), None
    except MipsFrameError as error:
        line = getattr(error, "line", None) or 1
        return None, Diagnostic(GENERATION_KIND, line, 1, "MIPS", str(error))
    except Exception as error:  # noqa: BLE001 - un fallo interno no debe cerrar el IDE
        message = f"Error interno al generar MIPS ({type(error).__name__}): {error}"
        return None, Diagnostic(GENERATION_KIND, 1, 1, "MIPS", message)
