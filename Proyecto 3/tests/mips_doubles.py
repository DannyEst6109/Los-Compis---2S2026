"""Dobles de prueba y simuladores para las pruebas de Persona 1.

Nada de esto es código del compilador. Sustituye, sólo dentro de las
pruebas, las partes que todavía no existen:

* ``MemoryRegisters``: la asignación de registros (Persona 2). No guarda
  nada en registros: cada valor se lee de memoria cuando se necesita, con
  ``$t8``/``$t9`` como registros de paso.
* ``OtherOperations``: una traducción mínima de las instrucciones TAC de
  Persona 2 y 3 (asignación, aritmética, comparaciones, saltos y ``print``),
  suficiente para ejecutar programas con funciones.
* ``Translation``: el recorrido del TAC y el armado del archivo que hará la
  integración (Persona 3).
* ``TinyMips``: un simulador de las pocas instrucciones MIPS que aparecen
  aquí. Es estricto: falla al leer de la pila memoria nunca escrita, al
  acceder a una palabra desalineada o al saltar a una etiqueta que no existe.
* ``run_mars``: ejecuta un programa en MARS por línea de comandos, si hay
  Java y un ``tools/Mars*.jar``.

También sirve para generar un ``.asm`` y abrirlo en MARS a mano::

    python tests/mips_doubles.py examples/08_recursividad.cps salida.asm
    python tests/mips_doubles.py programa.cps salida.asm --traza
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT / "src"))

from compiler import compile_source  # noqa: E402
from mips_frames import FrameModel  # noqa: E402
from mips_functions import FunctionTranslator  # noqa: E402
from tac import Const, TACInstruction, TACOp, Temp  # noqa: E402

VALID_EXAMPLES = sorted(
    path for path in (PROJECT / "examples").glob("*.cps") if "errores" not in path.name
)


def instructions(lines: list[str]) -> list[str]:
    """Sin comentarios ni marcas del doble de prueba."""
    return [line for line in lines if not line.startswith("#")]


# ---------------------------------------------------------------------------
# Dobles de las otras partes
# ---------------------------------------------------------------------------


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


class UnsupportedByDouble(NotImplementedError):
    """Instrucción de Persona 2 o 3 que el doble de prueba no traduce."""


class OtherOperations:
    """Traducción mínima de las instrucciones de Persona 2 y 3, sólo para
    poder ejecutar los programas de prueba."""

    _ARITHMETIC = {TACOp.ADD: "addu", TACOp.SUB: "subu", TACOp.MUL: "mul"}
    _IGNORED = {TACOp.METHOD_LOAD}  # sólo se usa en pruebas de estructura

    def __init__(self, registers: MemoryRegisters) -> None:
        self.registers = registers

    def translate(self, instruction: TACInstruction, unit: str | None) -> list[str]:
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
            return [*load(a, "$a0"), "li $v0, 1", "syscall", "li $a0, 10", "li $v0, 11", "syscall"]
        if op in self._IGNORED:
            return []
        raise UnsupportedByDouble(
            f"«{str(instruction).strip()}» es de Persona 2 o 3 y el doble de prueba no la traduce."
        )


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
        trace: bool = False,
    ) -> None:
        result = compile_source(source)
        assert result.succeeded, result.diagnostics
        self.tac = result.tac
        self.model = FrameModel(result.symbol_table)
        self.registers = MemoryRegisters(self.model, saved)
        self.translator = FunctionTranslator(self.model, self.registers, trace=trace)
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
                out.append(f"# {str(instruction).strip()}")
                if others is not None:
                    out += others.translate(instruction, self.translator.unit)

    def method_frame(self, instruction: TACInstruction):
        """Marco del método de ``t = method o.m``. Usa la resolución real de
        Persona 3 (``mips_objects``): clase estática anotada en el TAC o, si
        no se conoce, la firma común de todas las implementaciones."""
        from mips_objects import ObjectTranslator

        return ObjectTranslator(self.model, None, None).method_access(instruction.arg2, instruction).frame

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
        """Programa completo, en el orden que debe tener el archivo: datos,
        ``main`` y después las funciones."""
        lines = [".data", *self.translator.data_lines(), ".text", *self.translator.main_program(self.main)]
        for function in self.functions.values():
            lines += function
        return lines


def format_assembly(lines: list[str]) -> str:
    """Texto del archivo ``.asm``: etiquetas y directivas de sección al
    margen, el resto con sangría."""
    out = []
    for line in lines:
        flush = line.endswith(":") or line in (".data", ".text") or re.match(r"^[\w.$]+: \.", line)
        out.append(line if flush else f"    {line}")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Simulador mínimo
# ---------------------------------------------------------------------------


class SimulationError(Exception):
    pass


class TinyMips:
    """Simulador mínimo de MIPS para las pruebas (no reemplaza a MARS)."""

    STACK_TOP = 0x7FFFEFFC  # valor inicial de $sp en MARS
    DATA = 0x10010000  # inicio de .data en MARS

    _MEMORY = re.compile(r"^(-?\d+)\((\$\w+)\)$")
    _LABEL = re.compile(r"^([A-Za-z_][\w.$]*):\s*(.*)$")
    _ESCAPES = {"n": "\n", "t": "\t", "\\": "\\", '"': '"', "0": "\0"}

    def __init__(self, lines: list[str], max_steps: int = 2_000_000) -> None:
        self.code: list[tuple[str, list[str]]] = []
        self.labels: dict[str, int] = {}
        self.data_labels: dict[str, int] = {}
        self.memory: dict[int, int] = {}
        self._load(lines)
        self.registers: dict[str, int] = {"$sp": self.STACK_TOP, "$fp": self.STACK_TOP}
        self.output: list[int] = []  # enteros impresos con syscall 1
        self.text = ""  # todo lo impreso
        self.lowest_sp = self.STACK_TOP
        self.max_steps = max_steps
        self.calls = 0

    def _load(self, lines: list[str]) -> None:
        mode, pointer = ".text", self.DATA
        words = []
        for raw in lines:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line in (".data", ".text"):
                mode = line
                continue
            if line.startswith(".globl"):
                continue
            label, directive = None, line
            match = self._LABEL.match(line)
            if match:
                label, directive = match.group(1), match.group(2)
            if mode == ".data":
                if directive.startswith(".align"):
                    pointer = (pointer + 3) & ~3
                if label:
                    self.data_labels[label] = pointer
                if directive.startswith(".space"):
                    size = int(directive.split()[1])
                    for offset in range(size):
                        self.memory[pointer + offset] = 0
                    pointer += size
                elif directive.startswith(".asciiz"):
                    for char in self._string(directive) + "\0":
                        self.memory[pointer] = ord(char)
                        pointer += 1
                elif directive.startswith(".word "):
                    words.append((pointer, directive.split()[1]))
                    pointer += 4
                elif directive.startswith(".byte "):
                    for value in directive[6:].split(","):
                        self.memory[pointer] = int(value) & 255
                        pointer += 1
                elif directive and not directive.startswith(".align"):
                    raise SimulationError(f"Directiva no soportada: {line}")
                continue
            if directive.startswith(".align"):
                continue
            if label:
                self.labels[label] = len(self.code)
            if directive:
                op, _, rest = directive.partition(" ")
                self.code.append((op, [arg.strip() for arg in rest.split(",")] if rest else []))
        for address, value in words:
            self.write(address, 4, self.data_labels[value] if value in self.data_labels else int(value))

    def _string(self, directive: str) -> str:
        literal = directive[directive.index('"') + 1:directive.rindex('"')]
        return re.sub(r"\\(.)", lambda m: self._ESCAPES.get(m.group(1), m.group(1)), literal)

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

    def string_at(self, address: int) -> str:
        chars = []
        while self.memory.get(address, 0) != 0:
            chars.append(chr(self.memory[address]))
            address += 1
        return "".join(chars)

    # -- ejecución
    def run(self) -> "TinyMips":
        pc, steps = self.labels.get("main", 0), 0
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
            elif op == "la":
                if args[1] in self.data_labels:
                    set_(args[0], self.data_labels[args[1]])
                else:
                    set_(args[0], self.target(args[1]))
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
                    self.text += str(get("$a0"))
                elif service == 4:
                    self.text += self.string_at(get("$a0") & 0xFFFFFFFF)
                elif service == 11:
                    self.text += chr(get("$a0") & 0xFF)
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


def run(source: str, trace: bool = False) -> tuple[Translation, TinyMips]:
    """Traduce ``source`` y lo ejecuta en ``TinyMips``."""
    translation = Translation(source, run_others=True, trace=trace)
    return translation, TinyMips(translation.program()).run()


# ---------------------------------------------------------------------------
# MARS
# ---------------------------------------------------------------------------


def mars_command() -> list[str] | None:
    """Usa MARS_JAR o tools/Mars*.jar si Java está en PATH."""
    java = shutil.which("java")
    override = os.environ.get("MARS_JAR")
    if override:
        return [java, "-jar", override] if java and Path(override).is_file() else None
    jars = sorted((PROJECT / "tools").glob("[Mm]ars*.jar"))
    return [java, "-jar", str(jars[-1])] if java and jars else None


@dataclass
class MarsResult:
    output: str  # lo que imprimió el programa
    registers: dict[str, int]  # valor final de los registros pedidos
    returncode: int
    stderr: str


def run_mars(lines: list[str], registers: tuple[str, ...] = ("$sp", "$fp"), timeout: int = 60) -> MarsResult:
    """Ensambla y ejecuta el programa en MARS (modo línea de comandos).

    Opciones de MARS: ``nc`` sin aviso de copyright, ``sm`` empieza en
    ``main``, ``dec`` registros en decimal, ``ae2``/``se1`` código de salida
    distinto de 0 si falla el ensamblado o la simulación; los nombres de
    registro se imprimen con su valor al terminar."""
    command = mars_command()
    if command is None:
        raise RuntimeError("Se necesita Java y un tools/Mars*.jar para ejecutar MARS.")
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "programa.asm"
        path.write_text(format_assembly(lines), encoding="utf-8")
        process = subprocess.run(
            [*command, "nc", "sm", "dec", "we", "ae2", "se1", *registers, str(path)],
            capture_output=True, encoding="utf-8", timeout=timeout,
        )
    values: dict[str, int] = {}
    output_lines = []
    for line in process.stdout.splitlines():
        match = re.match(r"^\s*(\$\w+)\s+(-?(?:0x)?[0-9a-fA-F]+)\s*$", line)
        if match and match.group(1) in registers:
            values[match.group(1)] = int(match.group(2), 0)
        else:
            output_lines.append(line)
    return MarsResult("\n".join(output_lines).strip("\n"), values, process.returncode, process.stderr)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    source = Path(argv[1]).read_text(encoding="utf-8")
    translation = Translation(source, run_others=True, trace="--traza" in argv)
    text = format_assembly(translation.program())
    outputs = [arg for arg in argv[2:] if not arg.startswith("--")]
    if outputs:
        Path(outputs[0]).write_text(text, encoding="utf-8")
        print(f"MIPS guardado en {outputs[0]}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
