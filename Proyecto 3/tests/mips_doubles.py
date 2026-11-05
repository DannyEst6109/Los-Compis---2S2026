"""Dobles de prueba y mini simulador para las pruebas de Persona 1.

Nada de esto es código del compilador. Sustituye, sólo dentro de las
pruebas, las partes que todavía no existen:

* ``MemoryRegisters``: la asignación de registros (Persona 2). No guarda
  nada en registros: cada valor se lee de memoria cuando se necesita, con
  ``$t8``/``$t9`` como registros de paso.
* ``OtherOperations``: una traducción mínima de las instrucciones TAC de
  Persona 2 y 3 (asignación, aritmética, comparaciones, saltos y ``print``),
  suficiente para ejecutar programas con funciones.
* ``Translation``: el recorrido del TAC que hará la integración (Persona 3).
* ``TinyMips``: un simulador de las pocas instrucciones MIPS que aparecen
  aquí. Es estricto: falla al leer memoria nunca escrita, al acceder a una
  palabra desalineada o al saltar a una etiqueta que no existe. Las pruebas
  finales se harán en MARS.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT / "src"))

from compiler import compile_source  # noqa: E402
from mips_frames import FrameModel  # noqa: E402
from mips_functions import FunctionTranslator  # noqa: E402
from tac import Const, TACInstruction, TACOp, Temp, Var  # noqa: E402

VALID_EXAMPLES = sorted(
    path for path in (PROJECT / "examples").glob("*.cps") if "errores" not in path.name
)


def instructions(lines: list[str]) -> list[str]:
    """Sin comentarios ni marcas del doble de prueba."""
    return [line for line in lines if not line.startswith("#")]


class MemoryRegisters:
    """Doble de la asignación de registros (Persona 2): todo vive en memoria."""

    SCRATCH = "$t8"

    def __init__(self, model: FrameModel, saved: dict[str, list[str]] | None = None) -> None:
        self.model = model
        self.saved = saved or {}
        self.events: list[tuple] = []

    def value_register(self, operand, unit):
        return self.load_into(operand, unit, self.SCRATCH), self.SCRATCH

    def load_into(self, operand, unit, register):
        if isinstance(operand, Const):
            if operand.type_name == "boolean":
                return [f"li {register}, {int(operand.value)}"]
            if operand.type_name == "null":
                return [f"li {register}, 0"]
            if operand.type_name == "integer":
                return [f"li {register}, {operand.value}"]
            return [f"la {register}, <{operand}>"]  # las cadenas son de Persona 2
        return self.model.address_of(operand, unit).load(register)

    def assign_from(self, operand, unit, register):
        return self.model.address_of(operand, unit).store(register)

    def spill(self, unit):
        self.events.append(("spill", unit))
        return ["# spill"]

    def forget(self):
        self.events.append(("forget",))

    def saved_registers(self, unit):
        return self.saved.get(unit, [])


class OtherOperations:
    """Traducción mínima de las instrucciones de Persona 2 y 3, sólo para
    poder ejecutar los programas de prueba en ``TinyMips``."""

    _ARITHMETIC = {TACOp.ADD: "addu", TACOp.SUB: "subu", TACOp.MUL: "mul"}

    def __init__(self, registers: MemoryRegisters) -> None:
        self.registers = registers

    def translate(self, instruction: TACInstruction, unit: str | None) -> list[str] | None:
        op, regs = instruction.op, self.registers
        load = lambda operand, register: regs.load_into(operand, unit, register)  # noqa: E731
        store = lambda register: regs.assign_from(instruction.result, unit, register)  # noqa: E731
        a, b = instruction.arg1, instruction.arg2
        if op is TACOp.ASSIGN:
            return [*load(a, "$t8"), *store("$t8")]
        if op in self._ARITHMETIC:
            return [*load(a, "$t8"), *load(b, "$t9"), f"{self._ARITHMETIC[op]} $t8, $t8, $t9", *store("$t8")]
        if op is TACOp.LT:
            return [*load(a, "$t8"), *load(b, "$t9"), "slt $t8, $t8, $t9", *store("$t8")]
        if op is TACOp.LE:  # a <= b  ==  not (b < a)
            return [*load(a, "$t8"), *load(b, "$t9"), "slt $t8, $t9, $t8", "xori $t8, $t8, 1", *store("$t8")]
        if op is TACOp.EQ:
            return [*load(a, "$t8"), *load(b, "$t9"), "xor $t8, $t8, $t9", "sltiu $t8, $t8, 1", *store("$t8")]
        if op is TACOp.IF_TRUE:
            return [*load(a, "$t8"), f"bne $t8, $zero, {instruction.result}"]
        if op is TACOp.IF_FALSE:
            return [*load(a, "$t8"), f"beq $t8, $zero, {instruction.result}"]
        if op is TACOp.GOTO:
            return [f"j {instruction.result}"]
        if op is TACOp.LABEL:
            return [f"{instruction.result}:"]
        if op is TACOp.PRINT:
            return [*load(a, "$a0"), "li $v0, 1", "syscall"]
        return None


class Translation:
    """Recorre el TAC como lo hará la integración: funciones completas por
    etiqueta TAC, y el código global aparte.

    Con ``run_others=False`` las instrucciones de Persona 2 y 3 se dejan como
    comentario; con ``True`` se traducen con ``OtherOperations``."""

    def __init__(
        self,
        source: str,
        saved: dict[str, list[str]] | None = None,
        run_others: bool = False,
    ) -> None:
        result = compile_source(source)
        assert result.succeeded, result.diagnostics
        self.tac = result.tac
        self.model = FrameModel(result.symbol_table)
        self.registers = MemoryRegisters(self.model, saved)
        self.translator = FunctionTranslator(self.model, self.registers)
        others = OtherOperations(self.registers) if run_others else None
        self.functions: dict[str, list[str]] = {}
        self.main: list[str] = []
        self.calls: list[tuple[str | None, list[str]]] = []  # (función que llama, líneas)
        body: list[str] | None = None
        methods: dict[Temp, object] = {}
        for instruction in self.tac.instructions:
            out = body if body is not None else self.main
            op = instruction.op
            if op is TACOp.BEGIN_FUNC:
                self.translator.begin_function(instruction)
                body = []
            elif op is TACOp.END_FUNC:
                self.functions[instruction.arg1.name] = self.translator.end_function(instruction, body)
                body = None
            elif op is TACOp.PARAM:
                out += self.translator.translate_param(instruction)
            elif op is TACOp.CALL:
                frame = methods.pop(instruction.arg1, None) if isinstance(instruction.arg1, Temp) else None
                lines = self.translator.translate_call(instruction, frame)
                self.calls.append((self.translator.unit, lines))
                out += lines
            elif op is TACOp.RETURN:
                out += self.translator.translate_return(instruction)
            else:
                if op is TACOp.METHOD_LOAD:  # lo que hará Persona 3
                    methods[instruction.result] = self.method_frame(instruction)
                lines = others.translate(instruction, self.translator.unit) if others else None
                out.append(f"# {str(instruction).strip()}")
                if lines is not None:
                    out += lines

    def method_frame(self, instruction: TACInstruction):
        receiver, method = instruction.arg1, instruction.arg2.name
        layouts = self.model.table.class_layouts
        symbol = getattr(receiver, "symbol", None)
        if symbol is not None:
            layout = layouts[symbol.runtime_type or symbol.type_name]
        elif isinstance(receiver, Var):  # this: la clase de la función actual
            layout = layouts[self.translator.unit.split(".")[0]]
        else:  # receptor temporal: cualquier clase con ese método (mismo prefijo)
            layout = next(item for item in layouts.values() if item.method_index(method) is not None)
        label = layout.vtable[layout.method_index(method)][1]
        return self.model.frame(label)

    def calls_from(self, caller: str | None) -> list[list[str]]:
        """Llamadas hechas desde la función ``caller`` (``None``: código global)."""
        return [lines for unit, lines in self.calls if unit == caller]

    def calls_to(self, label: str, caller: str | None | object = ...) -> list[list[str]]:
        mips = self.model.frame(label).label
        calls = self.calls_from(caller) if caller is not ... else [lines for _, lines in self.calls]
        matches = [lines for lines in calls if f"jal {mips}" in lines]
        assert matches, f"no hay llamada a {label}"
        return matches

    def call_to(self, label: str, caller: str | None | object = ...) -> list[str]:
        """Primera llamada a ``label`` (desde ``caller``, si se indica)."""
        return self.calls_to(label, caller)[0]

    def program(self) -> list[str]:
        """Programa completo para ``TinyMips``: código global, salida y
        funciones. (El ``main`` definitivo es la Fase 5.)"""
        lines = [*self.main, "li $v0, 10", "syscall"]
        for function in self.functions.values():
            lines += function
        return lines


class SimulationError(Exception):
    pass


class TinyMips:
    """Simulador mínimo de MIPS para las pruebas (no reemplaza a MARS)."""

    STACK_TOP = 0x7FFFEFFC  # valor inicial de $sp en MARS
    GLOBALS = 0x10010000

    _MEMORY = re.compile(r"^(-?\d+)\((\$\w+)\)$")

    def __init__(self, lines: list[str], max_steps: int = 500_000) -> None:
        self.code: list[tuple[str, list[str]]] = []
        self.labels: dict[str, int] = {}
        for line in lines:
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            if line.endswith(":"):
                self.labels[line[:-1]] = len(self.code)
                continue
            op, _, rest = line.partition(" ")
            self.code.append((op, [arg.strip() for arg in rest.split(",")] if rest else []))
        self.registers: dict[str, int] = {"$sp": self.STACK_TOP, "$fp": self.STACK_TOP, "$gp": self.GLOBALS}
        self.memory: dict[int, int] = {}
        self.output: list[int] = []
        self.lowest_sp = self.STACK_TOP
        self.max_steps = max_steps
        self.calls = 0

    # -- registros y memoria
    def get(self, register: str) -> int:
        return 0 if register == "$zero" else self.registers.get(register, 0)

    def set(self, register: str, value: int) -> None:
        if register == "$zero":
            return
        value &= 0xFFFFFFFF
        self.registers[register] = value - (1 << 32) if value & 0x80000000 else value
        if register == "$sp":
            self.lowest_sp = min(self.lowest_sp, self.get("$sp") & 0xFFFFFFFF)

    def address(self, operand: str) -> int:
        match = self._MEMORY.match(operand)
        if not match:
            raise SimulationError(f"Dirección inválida: {operand}")
        return (self.get(match.group(2)) + int(match.group(1))) & 0xFFFFFFFF

    def read(self, address: int, size: int) -> int:
        if size == 4 and address % 4:
            raise SimulationError(f"Lectura de palabra desalineada en {address:#x}")
        value = 0
        for index in range(size):
            if address + index not in self.memory:
                raise SimulationError(f"Lectura de memoria nunca escrita en {address + index:#x}")
            value |= self.memory[address + index] << (8 * index)
        if size == 4 and value & 0x80000000:
            value -= 1 << 32
        return value

    def write(self, address: int, size: int, value: int) -> None:
        if size == 4 and address % 4:
            raise SimulationError(f"Escritura de palabra desalineada en {address:#x}")
        for index in range(size):
            self.memory[address + index] = (value >> (8 * index)) & 0xFF

    def target(self, label: str) -> int:
        if label not in self.labels:
            raise SimulationError(f"No existe la etiqueta {label}")
        return self.labels[label]

    # -- ejecución
    def run(self) -> "TinyMips":
        pc, steps = 0, 0
        while True:
            if not 0 <= pc < len(self.code):
                raise SimulationError(f"El programa salió del código (pc={pc})")
            steps += 1
            if steps > self.max_steps:
                raise SimulationError("Demasiados pasos: posible ciclo infinito")
            op, args = self.code[pc]
            pc += 1
            get, set_ = self.get, self.set
            if op == "li":
                set_(args[0], int(args[1]))
            elif op == "move":
                set_(args[0], get(args[1]))
            elif op == "addiu":
                set_(args[0], get(args[1]) + int(args[2]))
            elif op == "addu":
                set_(args[0], get(args[1]) + get(args[2]))
            elif op == "subu":
                set_(args[0], get(args[1]) - get(args[2]))
            elif op == "mul":
                set_(args[0], get(args[1]) * get(args[2]))
            elif op == "slt":
                set_(args[0], int(get(args[1]) < get(args[2])))
            elif op == "xor":
                set_(args[0], get(args[1]) ^ get(args[2]))
            elif op == "xori":
                set_(args[0], get(args[1]) ^ int(args[2]))
            elif op == "sltiu":
                set_(args[0], int((get(args[1]) & 0xFFFFFFFF) < int(args[2])))
            elif op in ("lw", "lbu"):
                set_(args[0], self.read(self.address(args[1]), 4 if op == "lw" else 1))
            elif op in ("sw", "sb"):
                self.write(self.address(args[1]), 4 if op == "sw" else 1, get(args[0]))
            elif op == "j":
                pc = self.target(args[0])
            elif op == "beq":
                pc = self.target(args[2]) if get(args[0]) == get(args[1]) else pc
            elif op == "bne":
                pc = self.target(args[2]) if get(args[0]) != get(args[1]) else pc
            elif op == "jal":
                self.calls += 1
                set_("$ra", pc)
                pc = self.target(args[0])
            elif op == "jalr":
                self.calls += 1
                set_("$ra", pc)
                pc = get(args[0])
            elif op == "jr":
                pc = get(args[0])
            elif op == "syscall":
                service = get("$v0")
                if service == 1:
                    self.output.append(get("$a0"))
                elif service == 10:
                    return self
                else:
                    raise SimulationError(f"syscall {service} no soportado")
            else:
                raise SimulationError(f"Instrucción no soportada: {op}")

    @property
    def stack_used(self) -> int:
        """Máximo de bytes de pila usados durante la ejecución."""
        return self.STACK_TOP - self.lowest_sp


def run(source: str) -> tuple[Translation, TinyMips]:
    """Traduce ``source`` y lo ejecuta en ``TinyMips``."""
    translation = Translation(source, run_others=True)
    return translation, TinyMips(translation.program()).run()
