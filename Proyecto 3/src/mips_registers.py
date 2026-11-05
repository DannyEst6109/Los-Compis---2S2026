"""Asignación de registros MIPS con respaldo en el marco del TAC."""

from collections import OrderedDict
from dataclasses import dataclass

from mips_frames import GP, SAVED_REGISTERS, FrameModel, MemoryLocation
from tac import Const, Operand, Var


# Los traductores pueden usar $t6–$t9 para cálculos de una instrucción.
TEMP_REGISTERS = tuple(f"$t{i}" for i in range(6))
STRING_HEAD = "p2_string_head"
NUMBER_TAG = 0
STRING_TAG = 1
NULL_TAG = 2
RETURN_TAG = "$a3"


@dataclass
class RegisterValue:
    operand: Operand
    dirty: bool = False


class MipsRegisters:
    """Reutiliza valores y desaloja el registro menos recientemente usado.

    El estado representa un solo bloque básico. Al salir de un bloque se
    emite spill(); al entrar por una etiqueta se descartan las asociaciones.
    """

    def __init__(self, model: FrameModel) -> None:
        self.model = model
        for frame in model.frames.values():
            frame.typed_values = True
        self._values: OrderedDict[str, RegisterValue] = OrderedDict()
        self._saved: dict[str, set[str]] = {}
        self._strings: dict[str, str] = {}

    def data_lines(self) -> list[str]:
        if not self._strings:
            return []
        # Cada cadena tiene un enlace a la anterior en -4(puntero).
        previous = "0"
        lines = [".align 2", f"{STRING_HEAD}:", f".word {next(reversed(self._strings.values()))}"]
        for value, label in self._strings.items():
            # .byte evita que MARS interprete escapes o caracteres del host.
            encoded = value.encode("utf-8")
            lines += [".align 2", f".word {previous}", f"{label}:", f".word {len(encoded)}"]
            previous = label
            for offset in range(0, len(encoded), 32):
                chunk = ", ".join(str(byte if byte < 128 else byte - 256) for byte in encoded[offset:offset + 32])
                lines.append(f".byte {chunk}")
            lines.append(".byte 0")  # MARS lee un byte adicional en syscall 15.
        return lines

    def _type_location(self, operand: Operand, unit: str | None) -> MemoryLocation:
        """Ubica la etiqueta paralela, conservando los enlaces de captura."""
        location = self.model.address_of(operand, unit)
        if location.base == GP:
            offset = self.model.global_area.size + location.offset
        else:
            symbol = operand.symbol if isinstance(operand, Var) else None
            frame = self.model.frame(symbol.owner if symbol is not None else unit)
            for index, slot in enumerate(frame.argument_slots):
                if frame.slot_location(slot).offset == location.offset:
                    # El llamador escribe estas etiquetas encima del marco.
                    return MemoryLocation(location.base, 4 * index, 1, location.setup)
            offset = location.offset - frame.record.size
        return MemoryLocation(location.base, offset, 1, location.setup)

    def load_type(self, operand: Operand, unit: str | None, register: str) -> list[str]:
        if isinstance(operand, Const):
            tag = {"string": STRING_TAG, "null": NULL_TAG}.get(operand.type_name, NUMBER_TAG)
            return [f"li {register}, {tag}"]
        if isinstance(operand, Var) and operand.symbol is None and operand.name == "this":
            return [f"li {register}, {NUMBER_TAG}"]
        return self._type_location(operand, unit).load(register)

    def _find(self, operand: Operand) -> str | None:
        for register, entry in self._values.items():
            if entry.operand == operand:
                self._values.move_to_end(register)
                return register
        return None

    def _write_back(self, unit: str | None, register: str) -> list[str]:
        entry = self._values[register]
        if not entry.dirty:
            return []
        lines = self.model.address_of(entry.operand, unit).store(register)
        entry.dirty = False
        return lines

    def _reserve(self, unit: str | None, source: str | None = None) -> tuple[list[str], str]:
        pool = TEMP_REGISTERS if unit is None else TEMP_REGISTERS + SAVED_REGISTERS
        for register in pool:
            if register not in self._values and register != source:
                if register in SAVED_REGISTERS:
                    self._saved.setdefault(unit, set()).add(register)
                return [], register
        register = next(register for register in self._values if register != source)
        return self._write_back(unit, register), register

    def _load(self, operand: Operand, unit: str | None, register: str) -> list[str]:
        if not isinstance(operand, Const):
            return self.model.address_of(operand, unit).load(register)
        if operand.type_name == "string":
            label = self._strings.setdefault(operand.value, f"p2_string_{len(self._strings)}")
            return [f"la {register}, {label}"]
        value = int(operand.value) if operand.value is not None else 0
        # Los valores enteros de la máquina se representan en 32 bits.
        value = (value + 2**31) % 2**32 - 2**31
        return [f"li {register}, {value}"]

    def value_register(self, operand: Operand, unit: str | None) -> tuple[list[str], str]:
        register = self._find(operand)
        if register is not None:
            return [], register
        lines, register = self._reserve(unit)
        lines += self._load(operand, unit, register)
        self._values[register] = RegisterValue(operand)
        self._values.move_to_end(register)
        return lines, register

    def load_into(self, operand: Operand, unit: str | None, register: str) -> list[str]:
        source = self._find(operand)
        if source == register:
            return []
        lines = []
        if register in self._values:
            lines += self._write_back(unit, register)
            del self._values[register]
        if register in SAVED_REGISTERS and unit is not None:
            self._saved.setdefault(unit, set()).add(register)
        if source is None:
            return lines + self._load(operand, unit, register)
        return lines + [f"move {register}, {source}"]

    def assign_from(
        self, operand: Operand, unit: str | None, register: str, *, tag: str = "$zero"
    ) -> list[str]:
        self.model.address_of(operand, unit)
        dest = self._find(operand)
        lines = []
        if dest is None:
            lines, dest = self._reserve(unit, register)
        if dest != register:
            lines.append(f"move {dest}, {register}")
        self._values[dest] = RegisterValue(operand, dirty=True)
        self._values.move_to_end(dest)
        return lines + self._type_location(operand, unit).store(tag)

    def spill(self, unit: str | None) -> list[str]:
        return [line for register in self._values for line in self._write_back(unit, register)]

    def forget(self) -> None:
        self._values.clear()

    def saved_registers(self, unit: str) -> tuple[str, ...]:
        used = self._saved.get(unit, set())
        return tuple(register for register in SAVED_REGISTERS if register in used)
