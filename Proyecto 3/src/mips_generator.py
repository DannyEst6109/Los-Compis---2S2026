"""Integración del generador de MIPS: TAC del Proyecto 2 -> archivo ``.asm``.

Es el único punto que conoce a todos los traductores. Recorre el TAC una
sola vez y manda cada instrucción a quien le corresponde::

            TAC del Proyecto 2 (compiler.compile_source)
                            |
                            v
                     MipsGenerator
                            |
     +-----------+----------+----------+------------+------------+
     |           |          |          |            |            |
     v           v          v          v            v            v
  Funciones   Básicas   Control    Objetos     Excepciones   Registros
  Persona 1   Persona 2 Persona 3  Persona 3   Persona 3     Persona 2
  (llamadas,  (aritm.,  (label,    (new, o.f,  (try_begin,   (getReg,
  marcos)     arreglos, goto, if)  method)     try_end)      spill)
              print)
     |           |          |          |            |
     +-----------+----------+----------+------------+
                            |
                            v
              .data + .text (main primero) + rutinas
                            |
                            v
              Optimización por mirilla (Persona 2 + Persona 3)
                            |
                            v
                     Archivo .asm final

Reglas de integración (``NOTAS.md``):

* Un solo ``MipsRegisters`` por programa, compartido por todos.
* ``begin_func``/``end_func``: el cuerpo se junta aparte y
  ``end_function`` devuelve la función completa (el prólogo depende de los
  ``$s`` que usó el cuerpo).
* Entre los ``param`` y su ``call`` no puede haber otra instrucción.
* ``call t, n`` sobre un método recibe el marco que resolvió
  ``ObjectTranslator`` al traducir ``t = method o.m``.
* Orden del archivo: ``.data`` (área global, clases, manejo de errores y
  cadenas, éstas al final porque se registran durante la traducción),
  ``.text`` con ``main`` primero (MARS empieza en la primera instrucción),
  las funciones y las rutinas de soporte.

``generate_mips`` sólo debe recibir el resultado de una compilación sin
errores; ``compiler.compile_source`` ya lo garantiza.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from mips_basic import HANDLED_OPS as BASIC_OPS
from mips_basic import BasicTranslator
from mips_control import HANDLED_OPS as CONTROL_OPS
from mips_control import ControlFlowTranslator
from mips_exceptions import HANDLED_OPS as EXCEPTION_OPS
from mips_exceptions import ExceptionTranslator
from mips_frames import FrameModel
from mips_functions import FunctionTranslator
from mips_objects import HANDLED_OPS as OBJECT_OPS
from mips_objects import ObjectTranslator
from mips_peephole import optimize_mips
from mips_peephole_control import PeepholeReport, optimize_control_flow
from mips_registers import MipsRegisters
from mips_runtime import LOOKUP_LABEL, THROW_LABEL, MipsGenerationError, RuntimeSupport
from symbol_table import SymbolTable
from tac import TACInstruction, TACOp, TACProgram

HEADER = (
    "# Programa generado por el compilador de Compiscript (Proyecto 3)",
    "# Arquitectura: MIPS32 · simulador: MARS 4.5 (saltos retardados desactivados)",
)

# Instrucciones que ya escriben su propio comentario (Persona 1) o que no
# producen código por sí solas.
_UNCOMMENTED = frozenset({TACOp.BEGIN_FUNC, TACOp.END_FUNC, TACOp.PARAM, TACOp.CALL, TACOp.RETURN, TACOp.LABEL})
_DATA_LABEL = re.compile(r"^[\w.$]+:\s+\.")


def is_instruction(line: str) -> bool:
    """``True`` si la línea es una instrucción (no comentario, etiqueta ni
    directiva)."""
    code = line.split("#", 1)[0].strip()
    return bool(code) and not code.endswith(":") and not code.startswith(".") and not _DATA_LABEL.match(code)


def count_instructions(lines: list[str]) -> int:
    in_text = False
    total = 0
    for line in lines:
        code = line.strip()
        if code in (".data", ".text"):
            in_text = code == ".text"
        elif in_text and is_instruction(code):
            total += 1
    return total


def format_assembly(lines: list[str]) -> str:
    """Texto del ``.asm``: etiquetas y secciones al margen, lo demás con
    sangría de cuatro espacios."""
    out = []
    for line in lines:
        flush = (
            line.endswith(":")
            or line in (".data", ".text")
            or _DATA_LABEL.match(line)
            or line.startswith("# ----")
            or line in HEADER
        )
        out.append(line if flush else f"    {line}")
    return "\n".join(out) + "\n"


@dataclass(slots=True)
class MipsProgram:
    """Resultado de la generación de MIPS."""

    lines: list[str]  # programa final (optimizado si se pidió), sin sangría
    raw_lines: list[str]  # antes de la optimización por mirilla
    optimized: bool
    peephole: PeepholeReport
    stats: dict[str, int] = field(default_factory=dict)

    @property
    def text(self) -> str:
        return format_assembly(self.lines)

    @property
    def raw_text(self) -> str:
        return format_assembly(self.raw_lines)

    @property
    def instruction_count(self) -> int:
        return count_instructions(self.lines)

    @property
    def raw_instruction_count(self) -> int:
        return count_instructions(self.raw_lines)


class MipsGenerator:
    """Traduce un ``TACProgram`` completo a MIPS."""

    def __init__(
        self,
        table: SymbolTable,
        tac: TACProgram,
        *,
        trace: bool = False,
        optimize: bool = True,
        comments: bool = True,
    ) -> None:
        self.tac = tac
        self.optimize = optimize
        self.comments = comments
        self.model = FrameModel(table)
        self.registers = MipsRegisters(self.model)
        self.runtime = RuntimeSupport(self.registers, trace=trace)
        self.functions = FunctionTranslator(self.model, self.registers, trace=trace)
        self.basic = BasicTranslator(self.registers, fault_label=THROW_LABEL)
        self.control = ControlFlowTranslator(self.registers)
        self.objects = ObjectTranslator(self.model, self.registers, self.runtime)
        self.exceptions = ExceptionTranslator(self.registers)
        self.uses_throw = False

    # -- recorrido del TAC ------------------------------------------------------
    def generate(self) -> MipsProgram:
        main: list[str] = []
        definitions: list[str] = []
        body: list[str] | None = None
        for instruction in self.tac:
            out = main if body is None else body
            op = instruction.op
            if op not in (TACOp.PARAM, TACOp.CALL):
                self.functions.ensure_no_pending_params(instruction)
            if self.comments and op not in _UNCOMMENTED:
                out.append(f"# {str(instruction).strip()}")
            if op is TACOp.BEGIN_FUNC:
                # El código global que estuviera antes queda en el área global.
                main += self.registers.spill(None)
                self.registers.forget()
                self.functions.begin_function(instruction)
                body = []
            elif op is TACOp.END_FUNC:
                definitions += self.functions.end_function(instruction, body)
                body = None
            else:
                out += self.translate(instruction)
        main += self.registers.spill(None)
        text = [*self.functions.main_program(main), *definitions]
        text += self._runtime_routines(text)
        data = self._data_lines(text)
        raw = [*HEADER, ".data", *data, ".text", *text]
        return self._finish(raw)

    def translate(self, instruction: TACInstruction) -> list[str]:
        """Traduce una instrucción que no abre ni cierra una función."""
        op = instruction.op
        unit = self.functions.unit
        if op is TACOp.PARAM:
            return self.functions.translate_param(instruction)
        if op is TACOp.CALL:
            frame = self.objects.method_frame(instruction.arg1)
            return self.functions.translate_call(instruction, frame)
        if op is TACOp.RETURN:
            lines = self.functions.translate_return(instruction)
            self.registers.forget()
            return lines
        if op in CONTROL_OPS:
            return self.control.translate(instruction, unit)
        if op in OBJECT_OPS:
            return self.objects.translate(instruction, unit)
        if op in EXCEPTION_OPS:
            return self.exceptions.translate(instruction, unit)
        if op in BASIC_OPS:
            return self.basic.translate(instruction, unit)
        raise MipsGenerationError(f"No hay traducción a MIPS para «{op.value}».", instruction)

    # -- armado del archivo -------------------------------------------------
    @staticmethod
    def _references(lines: list[str], label: str) -> bool:
        pattern = re.compile(rf"\b{re.escape(label)}\b")
        return any(pattern.search(line.split("#", 1)[0]) for line in lines)

    def _runtime_routines(self, text: list[str]) -> list[str]:
        """Rutinas de soporte que el código usa (``p3_lookup`` puede lanzar
        errores, así que se agrega antes de decidir si hace falta
        ``p3_throw``)."""
        routines: list[str] = []
        if self._references(text, LOOKUP_LABEL):
            routines += self.runtime.lookup_routine()
        if self._references([*text, *routines], THROW_LABEL):
            routines += self.runtime.throw_routine()
        self.uses_throw = self._references(routines, THROW_LABEL)
        return routines

    def _data_lines(self, text: list[str]) -> list[str]:
        data = list(self.functions.data_lines())
        data += self.objects.data_lines()
        data += self.runtime.data_lines(self.uses_throw)
        strings = self.registers.data_lines()  # al final: ya se registraron todas
        if strings:
            data += ["# cadenas (longitud + bytes UTF-8, enlazadas para compartir contenido)", *strings]
        return data

    def _finish(self, raw: list[str]) -> MipsProgram:
        report = PeepholeReport()
        lines = raw
        if self.optimize:
            lines, report = peephole_optimize(raw)
        stats = {
            "funciones": len(self.model.frames),
            "clases": len(self.objects.layouts),
            "etiquetas": self.control.labels,
            "saltos": self.control.jumps,
            "saltos condicionales": self.control.branches,
            "condiciones constantes": self.control.folded,
            "accesos a miembros directos": self.objects.static_accesses,
            "accesos a miembros dinámicos": self.objects.dynamic_accesses,
            "objetos creados (new)": self.objects.allocations,
            "bloques try": self.exceptions.handlers,
        }
        return MipsProgram(lines, raw, self.optimize, report, stats)


def peephole_optimize(lines: list[str], max_rounds: int = 10) -> tuple[list[str], PeepholeReport]:
    """Mirilla completa: reglas locales de Persona 2 y reglas de control de
    flujo de Persona 3, repetidas hasta que ninguna cambie el código."""
    report = PeepholeReport()
    current = lines
    for _ in range(max_rounds):
        before = current
        basic = optimize_mips(current)
        report.add("simplificaciones locales (Persona 2)", count_instructions(current) - count_instructions(basic))
        current, round_report = optimize_control_flow(basic)
        report.merge(round_report)
        if current == before:
            break
    return current, report


def generate_mips(
    table: SymbolTable,
    tac: TACProgram,
    *,
    trace: bool = False,
    optimize: bool = True,
    comments: bool = True,
) -> MipsProgram:
    """Punto de integración: TAC + tabla de símbolos con direcciones ->
    programa MIPS completo."""
    return MipsGenerator(table, tac, trace=trace, optimize=optimize, comments=comments).generate()
