"""Marcos de pila en MIPS: registros de activación, área global y direcciones.

Traduce los ``ActivationRecord`` que el Proyecto 2 dejó en la tabla de
símbolos a posiciones concretas de memoria en MIPS. No recalcula
desplazamientos: usa los de la tabla tal cual. La convención completa está
en ``NOTAS.md``.

Distribución de un marco (la pila crece hacia abajo)::

    $fp ──► ┌──────────────────────┐  tope del marco
            │ dirección de retorno │  -4($fp)    off 0  ┐
            │ enlace de control    │  -8($fp)    off 4  │ prefijo: lo reserva
            │ enlace de acceso     │  -12($fp)   off 8  │ y llena el llamador
            │ this, parámetros     │                    ┘
            │ locales, temporales  │                    ┐ lo reserva el
            │ registros $s         │                    ┘ prólogo
    $sp ──► └──────────────────────┘

Una casilla del registro con desplazamiento ``off`` y tamaño ``size`` está
en ``-(off + size)($fp)``. El área global no tiene encabezado: es el bloque
``globales`` de ``.data``, apuntado por ``$gp``, con desplazamientos
positivos.

Uso típico (desde la traducción de una instrucción TAC)::

    model = FrameModel(table)
    location = model.address_of(Var("x", symbol), unit="factorial")
    lines = location.load("$t0")      # ["lw $t0, -16($fp)"]
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from symbol_table import WORD_SIZE, ActivationRecord, FrameSlot, StorageKind, SymbolTable, align
from tac import Temp, Var

# Registros con un papel fijo en la convención de llamadas.
FP = "$fp"
SP = "$sp"
GP = "$gp"
RA = "$ra"
ZERO = "$zero"
RETURN_VALUE = "$v0"
LINK_REGISTER = "$v1"  # sólo para seguir enlaces de acceso
SAVED_REGISTERS = tuple(f"$s{index}" for index in range(8))

# Encabezado de todo registro de activación (desplazamientos del Proyecto 2).
RETURN_ADDRESS_OFFSET = 0
CONTROL_LINK_OFFSET = 4
ACCESS_LINK_OFFSET = 8
HEADER_SIZE = 3 * WORD_SIZE

# Etiquetas que genera Persona 1. Nadie más usa el prefijo ``fn_``.
MAIN_LABEL = "main"
GLOBAL_AREA_LABEL = "globales"
FUNCTION_PREFIX = "fn_"
EPILOGUE_SUFFIX = "_fin"

_ARGUMENT_ROLES = ("this", "parámetro")
_INVALID_LABEL_CHARS = re.compile(r"[^A-Za-z0-9_]")


class MipsFrameError(Exception):
    """Error de traducción relacionado con marcos o direcciones."""


def frame_offset(offset: int, size: int) -> int:
    """Desplazamiento respecto a ``$fp`` de una casilla del registro."""
    return -(offset + size)


# ---------------------------------------------------------------------------
# Posiciones de memoria
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class MemoryLocation:
    """Dónde vive un valor: ``offset(base)`` con ``size`` bytes.

    ``setup`` son las instrucciones que dejan ``base`` lista cuando hay que
    seguir enlaces de acceso (``base`` es entonces ``$v1``); va vacío si la
    base es ``$fp`` o ``$gp``.
    """

    base: str
    offset: int
    size: int
    setup: tuple[str, ...] = ()

    @property
    def address(self) -> str:
        return f"{self.offset}({self.base})"

    @property
    def load_op(self) -> str:
        return "lbu" if self.size == 1 else "lw"

    @property
    def store_op(self) -> str:
        return "sb" if self.size == 1 else "sw"

    def load(self, register: str) -> list[str]:
        """Instrucciones que cargan el valor en ``register``."""
        return [*self.setup, f"{self.load_op} {register}, {self.address}"]

    def store(self, register: str) -> list[str]:
        """Instrucciones que guardan ``register`` en esta posición."""
        if self.setup and register == LINK_REGISTER:
            raise MipsFrameError(
                f"No se puede guardar {LINK_REGISTER} en {self.address}: ese registro "
                "se usa para calcular la dirección."
            )
        return [*self.setup, f"{self.store_op} {register}, {self.address}"]


# ---------------------------------------------------------------------------
# Marcos de funciones y área global
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class FrameLayout:
    """Marco en MIPS de una función, método, constructor o inicializador."""

    record: ActivationRecord
    label: str
    epilogue_label: str
    saved_registers: tuple[str, ...] = ()
    typed_values: bool = False

    @property
    def name(self) -> str:
        """Etiqueta TAC de la función (``begin_func <name>``)."""
        return self.record.name

    @property
    def level(self) -> int:
        return self.record.level

    @property
    def argument_slots(self) -> list[FrameSlot]:
        """``this`` (si existe) y los parámetros, en el orden de los ``param``."""
        slots = [slot for slot in self.record.slots if slot.role in _ARGUMENT_ROLES]
        return sorted(slots, key=lambda slot: slot.offset)

    @property
    def prefix_size(self) -> int:
        """Bytes que reserva el llamador: encabezado, ``this`` y parámetros."""
        end = max([HEADER_SIZE, *(slot.offset + slot.size for slot in self.argument_slots)])
        return align(end, WORD_SIZE)

    @property
    def size(self) -> int:
        """Tamaño total del marco: el registro más los ``$s`` guardados."""
        return self.local_size + WORD_SIZE * len(self.saved_registers)

    @property
    def local_size(self) -> int:
        return self.record.size * (2 if self.typed_values else 1)

    def use_saved_registers(self, registers) -> None:
        """Registra qué ``$s`` usa la función (los guarda su prólogo)."""
        registers = list(registers)
        unknown = [register for register in registers if register not in SAVED_REGISTERS]
        if unknown:
            raise MipsFrameError(f"{', '.join(unknown)} no es un registro $s0-$s7.")
        if len(set(registers)) != len(registers):
            raise MipsFrameError("Un registro $s aparece repetido.")
        self.saved_registers = tuple(sorted(registers, key=SAVED_REGISTERS.index))

    # -- casillas del marco
    def slot_location(self, slot: FrameSlot) -> MemoryLocation:
        return MemoryLocation(FP, frame_offset(slot.offset, slot.size), slot.size)

    def temp_location(self, index: int) -> MemoryLocation:
        return MemoryLocation(FP, frame_offset(_temp_offset(self.record, index), WORD_SIZE), WORD_SIZE)

    def saved_register_location(self, register: str) -> MemoryLocation:
        if register not in self.saved_registers:
            raise MipsFrameError(f"{self.name} no guarda {register}.")
        offset = self.local_size + WORD_SIZE * self.saved_registers.index(register)
        return MemoryLocation(FP, frame_offset(offset, WORD_SIZE), WORD_SIZE)

    @property
    def return_address(self) -> MemoryLocation:
        return MemoryLocation(FP, frame_offset(RETURN_ADDRESS_OFFSET, WORD_SIZE), WORD_SIZE)

    @property
    def control_link(self) -> MemoryLocation:
        return MemoryLocation(FP, frame_offset(CONTROL_LINK_OFFSET, WORD_SIZE), WORD_SIZE)

    @property
    def access_link(self) -> MemoryLocation:
        return MemoryLocation(FP, frame_offset(ACCESS_LINK_OFFSET, WORD_SIZE), WORD_SIZE)

    # -- vista del llamador
    def caller_offset(self, slot: FrameSlot) -> int:
        """Desplazamiento respecto a ``$sp`` después de que el llamador
        reserva el prefijo (``addiu $sp, $sp, -prefix_size``)."""
        return self.prefix_size - slot.offset - slot.size

    def argument_locations(self) -> list[MemoryLocation]:
        """Dónde escribe el llamador cada argumento, en orden."""
        return [MemoryLocation(SP, self.caller_offset(slot), slot.size) for slot in self.argument_slots]

    @property
    def caller_access_link(self) -> MemoryLocation:
        return MemoryLocation(SP, self.prefix_size - ACCESS_LINK_OFFSET - WORD_SIZE, WORD_SIZE)


@dataclass(slots=True)
class GlobalArea:
    """Área estática del código global: variables globales y sus temporales."""

    record: ActivationRecord
    label: str = GLOBAL_AREA_LABEL

    @property
    def size(self) -> int:
        return self.record.size

    def slot_location(self, slot: FrameSlot) -> MemoryLocation:
        return MemoryLocation(GP, slot.offset, slot.size)

    def temp_location(self, index: int) -> MemoryLocation:
        return MemoryLocation(GP, _temp_offset(self.record, index), WORD_SIZE)


def _temp_offset(record: ActivationRecord, index: int) -> int:
    if not 1 <= index <= record.temporaries:
        raise MipsFrameError(
            f"El temporal t{index} no existe en «{record.name}» (tiene {record.temporaries})."
        )
    return record.temporaries_offset + (index - 1) * WORD_SIZE


# ---------------------------------------------------------------------------
# Etiquetas
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class LabelRegistry:
    """Nombres MIPS únicos para las funciones y sus epílogos.

    Las etiquetas del TAC pueden tener ``.`` y ``$`` (``Perro.hablar``,
    ``Animal.$init``, ``a$1``); en MIPS se reemplazan por ``_`` y se agrega
    el prefijo ``fn_``. Si dos nombres coinciden, el segundo recibe ``_2``,
    ``_3``, ..."""

    used: set[str] = field(default_factory=lambda: {MAIN_LABEL, GLOBAL_AREA_LABEL})

    def unique(self, base: str) -> str:
        label, suffix = base, 2
        while label in self.used:
            label = f"{base}_{suffix}"
            suffix += 1
        self.used.add(label)
        return label

    def function(self, tac_label: str) -> str:
        return self.unique(FUNCTION_PREFIX + _INVALID_LABEL_CHARS.sub("_", tac_label))


# ---------------------------------------------------------------------------
# Modelo de memoria del programa
# ---------------------------------------------------------------------------


class FrameModel:
    """Marcos de todas las funciones y el área global de un programa.

    Se construye una vez, a partir de una tabla de símbolos que ya pasó por
    ``memory_layout.assign_memory_layout`` (lo hace ``compile_source``)."""

    def __init__(self, table: SymbolTable) -> None:
        if table.global_record is None:
            raise MipsFrameError(
                "La tabla de símbolos no tiene registros de activación: debe generarse el TAC antes."
            )
        self.table = table
        self.global_area = GlobalArea(table.global_record)
        self.labels = LabelRegistry()
        records = list(table.activation_records)
        names = [record.name for record in records]
        if len(set(names)) != len(names):
            raise MipsFrameError("Hay dos registros de activación con la misma etiqueta.")
        # Primero los nombres de todas las funciones y después los epílogos,
        # así el nombre de una función nunca depende de un epílogo.
        function_labels = {record.name: self.labels.function(record.name) for record in records}
        self.frames: dict[str, FrameLayout] = {
            record.name: FrameLayout(
                record,
                function_labels[record.name],
                self.labels.unique(function_labels[record.name] + EPILOGUE_SUFFIX),
            )
            for record in records
        }

    # -- consultas
    def frame(self, tac_label: str) -> FrameLayout:
        frame = self.frames.get(tac_label)
        if frame is None:
            raise MipsFrameError(f"No existe la función «{tac_label}».")
        return frame

    def unit(self, tac_label: str | None) -> FrameLayout | None:
        """Marco de la unidad actual; ``None`` es el código global."""
        if tac_label is None or tac_label == self.global_area.record.name:
            return None
        return self.frame(tac_label)

    def mips_label(self, tac_label: str) -> str:
        return self.frame(tac_label).label

    # -- direcciones
    def address_of(self, operand: object, unit: str | None = None) -> MemoryLocation:
        """Dirección de un ``Var`` o ``Temp`` visto desde ``unit``.

        ``unit`` es la etiqueta TAC de la función que se está traduciendo
        (la de su ``begin_func``) o ``None`` para el código global."""
        frame = self.unit(unit)
        if isinstance(operand, Temp):
            if frame is None:
                return self.global_area.temp_location(operand.index)
            return frame.temp_location(operand.index)
        if isinstance(operand, Var):
            return self._variable_location(operand, frame)
        raise MipsFrameError(
            f"«{operand}» no tiene dirección de memoria: sólo las variables y los temporales la tienen."
        )

    def _variable_location(self, var: Var, frame: FrameLayout | None) -> MemoryLocation:
        symbol = var.symbol
        if symbol is None:
            if var.name == "this":
                return self._this_location(frame)
            raise MipsFrameError(f"La variable «{var.name}» no tiene símbolo en la tabla.")
        storage = symbol.storage
        if storage is StorageKind.GLOBAL:
            return MemoryLocation(GP, symbol.offset, symbol.size)
        if storage in (StorageKind.PARAMETER, StorageKind.LOCAL):
            if frame is None:
                raise MipsFrameError(
                    f"«{var.name}» pertenece a «{symbol.owner}» y no es accesible desde el código global."
                )
            hops = self.hops_to(frame, symbol.owner, var.name)
            setup, base = self.follow_access_links(hops)
            return MemoryLocation(base, frame_offset(symbol.offset, symbol.size), symbol.size, setup)
        if storage is StorageKind.FIELD:
            raise MipsFrameError(
                f"«{var.name}» es un atributo: se lee y escribe a través del objeto, no tiene dirección propia."
            )
        raise MipsFrameError(f"La variable «{var.name}» no tiene dirección asignada.")

    def _this_location(self, frame: FrameLayout | None) -> MemoryLocation:
        hops, record = 0, frame.record if frame is not None else None
        while record is not None and record is not self.global_area.record:
            slot = next((item for item in record.slots if item.role == "this"), None)
            if slot is not None:
                setup, base = self.follow_access_links(hops)
                return MemoryLocation(base, frame_offset(slot.offset, slot.size), slot.size, setup)
            record = self.table.record(record.parent) if record.parent else None
            hops += 1
        raise MipsFrameError("«this» sólo existe dentro de un método, constructor o inicializador.")

    def hops_to(self, frame: FrameLayout, owner: str | None, name: str) -> int:
        """Cuántos enlaces de acceso hay que seguir desde ``frame`` para
        llegar al registro ``owner``. ``name`` (la variable o función que se
        busca) sólo aparece en el mensaje de error."""
        hops, record = 0, frame.record
        while record is not None and record is not self.global_area.record:
            if record.name == owner:
                return hops
            record = self.table.record(record.parent) if record.parent else None
            hops += 1
        raise MipsFrameError(
            f"«{name}» está en «{owner}», que no contiene a «{frame.name}»: no es accesible desde ahí."
        )

    @staticmethod
    def follow_access_links(hops: int) -> tuple[tuple[str, ...], str]:
        """Instrucciones que dejan en ``$v1`` el ``$fp`` del registro que está
        ``hops`` niveles léxicos hacia afuera, y la base resultante."""
        if hops < 0:
            raise MipsFrameError("La cantidad de enlaces de acceso no puede ser negativa.")
        if hops == 0:
            return (), FP
        link = frame_offset(ACCESS_LINK_OFFSET, WORD_SIZE)
        setup = [f"lw {LINK_REGISTER}, {link}({FP})"]
        setup += [f"lw {LINK_REGISTER}, {link}({LINK_REGISTER})"] * (hops - 1)
        return tuple(setup), LINK_REGISTER
