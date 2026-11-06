"""Clases, objetos y herencia en MIPS: ``new``, ``o.f``, ``o.f = x`` y
``method o.m``.

Representación de un objeto
---------------------------

La distribución de cada clase la calculó el Proyecto 2
(``ClassLayout`` en la tabla de símbolos): el desplazamiento 0 guarda el
puntero a la vtable y cada atributo tiene un desplazamiento fijo. Los
atributos heredados **conservan el desplazamiento de la superclase**, así un
``Perro`` puede usarse donde se espera un ``Animal``. ``new C`` reserva el
objeto en el heap (``syscall`` 9, ``sbrk``)::

    o - S  ┌──────────────────────┐
           │ etiquetas de impresión│  1 byte por atributo, en -(off + 1)(o)
    o ───► ├──────────────────────┤
           │ puntero a la vtable  │  0(o)
           │ atributos            │  off(o)   (lw/sw, o lbu/sb si es boolean)
    o + S  └──────────────────────┘           S = ClassLayout.size

Las etiquetas (número, texto o nulo) son las mismas que usa Persona 2 para
que ``print`` sepa cómo mostrar un valor. Se guardan en bytes aparte, en
posiciones que sólo dependen del desplazamiento del atributo, para que un
atributo heredado tenga su etiqueta en el mismo lugar en todas las
subclases. ``new`` marca como nulos los atributos de tipo referencia.

Vtables y tablas de miembros (en ``.data``)
-------------------------------------------

::

    .word p3_members_Perro       ← tabla de miembros, en vtable - 4
    p3_vt_Perro:                 ← lo que guarda 0(o)
    .word fn_Perro_hablar        método 0 (redefinido)
    .word fn_Animal_presentarse  método 1 (heredado)
    p3_members_Perro:
    .word 3                      cantidad de entradas
    .word <clave>, <valor>, <tamaño>

La vtable de una subclase empieza con los mismos métodos, en la misma
posición, que la de su superclase; una redefinición reemplaza la entrada
heredada. Por eso ``method o.m`` es::

    lw   $t9, 0(o)               vtable de la clase dinámica de o
    lw   $t9, 4*i($t9)           i = posición de m en la clase estática

y ``call t, n`` (Persona 1) hace ``jalr``: **despacho dinámico**. Un
``Animal`` que guarda un ``Perro`` ejecuta ``Perro.hablar``.

Resolución de miembros
----------------------

El generador de TAC anota en ``Name.owner`` la clase estática del objeto.

1. Clase estática conocida: desplazamiento y posición en la vtable fijos.
2. Clase desconocida (por ejemplo, un parámetro sin anotación): si todas
   las clases que tienen ese miembro lo ponen en el mismo lugar, se usa ese
   lugar.
3. Si no, se busca en tiempo de ejecución (``p3_lookup``) en la tabla de
   miembros de la clase dinámica del objeto.

Todo acceso verifica antes que el objeto no sea ``null`` (salvo ``this``, que
nunca lo es); si lo es, lanza el error «Acceso a un objeto nulo», que puede
atrapar un ``try/catch``.

Las llamadas usan la secuencia de Persona 1. Para ``call t, n`` sobre un
método, ``method_frame(t)`` entrega el marco del método (de ahí salen el
prefijo y la casilla de cada argumento); se verifica que todas las
implementaciones que podrían ejecutarse tengan la misma distribución de
argumentos.
"""

from __future__ import annotations

from dataclasses import dataclass

from mips_frames import FrameLayout, FrameModel, MipsFrameError
from mips_registers import NULL_TAG, MipsRegisters
from mips_runtime import (
    LOOKUP_LABEL,
    NULL_OBJECT_MESSAGE,
    SYSCALL_SBRK,
    MipsGenerationError,
    RuntimeSupport,
)
from symbol_table import WORD_SIZE, ClassLayout, FrameSlot
from tac import Name, Operand, TACInstruction, TACOp, Temp, Var

HANDLED_OPS = frozenset({TACOp.NEW_OBJECT, TACOp.FIELD_LOAD, TACOp.FIELD_STORE, TACOp.METHOD_LOAD})

VTABLE_PREFIX = "p3_vt_"
MEMBERS_PREFIX = "p3_members_"
FIELD_ROLE = "atributo"
_VALUE_TYPES = ("integer", "boolean")  # los demás atributos son referencias


def vtable_label(class_name: str) -> str:
    return VTABLE_PREFIX + class_name


def members_label(class_name: str) -> str:
    return MEMBERS_PREFIX + class_name


def is_this(operand: Operand) -> bool:
    """``this`` es el parámetro implícito de un método: nunca es nulo."""
    return isinstance(operand, Var) and operand.symbol is None and operand.name == "this"


def tag_offset(offset: int) -> int:
    """Desplazamiento de la etiqueta de impresión del atributo en ``offset``."""
    return -(offset + 1)


@dataclass(frozen=True, slots=True)
class FieldAccess:
    """Cómo llegar a un atributo: desplazamiento fijo o búsqueda dinámica."""

    name: str
    offset: int | None  # None: se busca en tiempo de ejecución
    sizes: frozenset[int]
    key: int

    @property
    def dynamic(self) -> bool:
        return self.offset is None


@dataclass(frozen=True, slots=True)
class MethodAccess:
    name: str
    index: int | None  # None: se busca en tiempo de ejecución
    frame: FrameLayout
    key: int

    @property
    def dynamic(self) -> bool:
        return self.index is None


class ObjectTranslator:
    """Traduce las instrucciones de objetos y arma las tablas de las clases."""

    def __init__(self, model: FrameModel, registers: MipsRegisters, runtime: RuntimeSupport) -> None:
        self.model = model
        self.registers = registers
        self.runtime = runtime
        self.layouts: dict[str, ClassLayout] = dict(model.table.class_layouts)
        # Clave única por miembro, para la búsqueda dinámica.
        self.keys: dict[tuple[str, str], int] = {}
        for layout in self.layouts.values():
            for slot in self.fields(layout):
                self._key("atributo", slot.name)
            for method, _label in layout.vtable:
                self._key("método", method)
        self._method_frames: dict[Operand, FrameLayout] = {}
        # Estadísticas (las muestra el IDE).
        self.static_accesses = 0
        self.dynamic_accesses = 0
        self.allocations = 0

    # -- consultas sobre las clases -------------------------------------------
    @staticmethod
    def fields(layout: ClassLayout) -> list[FrameSlot]:
        return [slot for slot in layout.slots if slot.role == FIELD_ROLE]

    def _key(self, kind: str, name: str) -> int:
        return self.keys.setdefault((kind, name), len(self.keys))

    def layout(self, class_name: str, instruction: TACInstruction) -> ClassLayout:
        layout = self.layouts.get(class_name)
        if layout is None:
            raise MipsGenerationError(f"No existe la distribución de la clase «{class_name}».", instruction)
        return layout

    def is_subclass(self, layout: ClassLayout, ancestor: str) -> bool:
        seen: set[str] = set()
        current: ClassLayout | None = layout
        while current is not None and current.name not in seen:
            if current.name == ancestor:
                return True
            seen.add(current.name)
            current = self.layouts.get(current.superclass) if current.superclass else None
        return False

    def null_check(self, target: Operand, register: str, unit: str | None) -> list[str]:
        """Lanza «Acceso a un objeto nulo» si ``register`` es 0 (no hace
        falta con ``this``)."""
        if is_this(target):
            return []
        return self.runtime.guard(register, unit, NULL_OBJECT_MESSAGE)

    def field_access(self, member: Name, instruction: TACInstruction) -> FieldAccess:
        name = member.name
        if ("atributo", name) not in self.keys:
            raise MipsGenerationError(f"Ninguna clase tiene el atributo «{name}».", instruction)
        key = self.keys[("atributo", name)]
        if member.owner is not None and member.owner in self.layouts:
            slot = self._field_slot(self.layouts[member.owner], name)
            if slot is None:
                raise MipsGenerationError(f"La clase «{member.owner}» no tiene el atributo «{name}».", instruction)
            return FieldAccess(name, slot.offset, frozenset({slot.size}), key)
        places = {
            (slot.offset, slot.size)
            for layout in self.layouts.values()
            if (slot := self._field_slot(layout, name)) is not None
        }
        sizes = frozenset(size for _offset, size in places)
        offsets = {offset for offset, _size in places}
        if len(offsets) == 1 and len(sizes) == 1:
            return FieldAccess(name, offsets.pop(), sizes, key)
        return FieldAccess(name, None, sizes, key)

    @staticmethod
    def _field_slot(layout: ClassLayout, name: str) -> FrameSlot | None:
        return next((slot for slot in layout.slots if slot.role == FIELD_ROLE and slot.name == name), None)

    def method_access(self, member: Name, instruction: TACInstruction) -> MethodAccess:
        name = member.name
        if ("método", name) not in self.keys:
            raise MipsGenerationError(f"Ninguna clase tiene el método «{name}».", instruction)
        key = self.keys[("método", name)]
        if member.owner is not None and member.owner in self.layouts:
            index = self.layouts[member.owner].method_index(name)
            if index is None:
                raise MipsGenerationError(f"La clase «{member.owner}» no tiene el método «{name}».", instruction)
            # Pueden ejecutarse la implementación de la clase estática o la de
            # cualquier subclase que la redefina.
            candidates = [
                (layout, index) for layout in self.layouts.values() if self.is_subclass(layout, member.owner)
            ]
        else:
            candidates = [
                (layout, layout.method_index(name))
                for layout in self.layouts.values()
                if layout.method_index(name) is not None
            ]
            indexes = {index for _layout, index in candidates}
            index = indexes.pop() if len(indexes) == 1 else None
        frames = [self._frame(layout.vtable[position][1], instruction) for layout, position in candidates]
        self._check_signatures(name, frames, instruction)
        return MethodAccess(name, index, frames[0], key)

    def _frame(self, label: str, instruction: TACInstruction) -> FrameLayout:
        try:
            return self.model.frame(label)
        except MipsFrameError as error:
            raise MipsGenerationError(str(error), instruction) from None

    @staticmethod
    def _check_signatures(name: str, frames: list[FrameLayout], instruction: TACInstruction) -> None:
        """Con ``jalr`` el llamador no sabe qué implementación se ejecutará:
        todas deben esperar los argumentos en las mismas casillas."""

        def shape(frame: FrameLayout):
            return frame.prefix_size, [(slot.offset, slot.size) for slot in frame.argument_slots]

        first = shape(frames[0])
        for frame in frames[1:]:
            if shape(frame) != first:
                raise MipsGenerationError(
                    f"«{frames[0].name}» y «{frame.name}» reciben argumentos distintos; no se puede "
                    f"llamar a «{name}» con despacho dinámico.",
                    instruction,
                )

    # -- traducción -------------------------------------------------------------
    def translate(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        op = instruction.op
        if op is TACOp.NEW_OBJECT:
            return self.new_object(instruction, unit)
        member = instruction.arg1 if op is TACOp.FIELD_STORE else instruction.arg2
        if not isinstance(member, Name):
            raise MipsGenerationError("Se esperaba el nombre de un atributo o método.", instruction)
        if op is TACOp.FIELD_LOAD:
            return self.field_load(instruction, unit)
        if op is TACOp.FIELD_STORE:
            return self.field_store(instruction, unit)
        if op is TACOp.METHOD_LOAD:
            return self.method_load(instruction, unit)
        raise MipsGenerationError(f"Operación de objetos no admitida: {op.name}.", instruction)

    def new_object(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        """``t = new C``: reserva etiquetas + datos y apunta a la vtable."""
        class_name = instruction.arg1.name
        layout = self.layout(class_name, instruction)
        size = layout.size
        self.allocations += 1
        lines = [
            f"li $a0, {2 * size}",  # etiquetas + datos
            f"li $v0, {SYSCALL_SBRK}",
            "syscall",
            f"addiu $v0, $v0, {size}",  # el objeto empieza después de las etiquetas
            f"la $t9, {vtable_label(class_name)}",
            "sw $t9, 0($v0)",
        ]
        references = [slot for slot in self.fields(layout) if slot.type_name not in _VALUE_TYPES]
        if references:
            lines.append(f"li $t9, {NULL_TAG}")
            lines += [f"sb $t9, {tag_offset(slot.offset)}($v0)  # {slot.name} = null" for slot in references]
        return lines + self.registers.assign_from(instruction.result, unit, "$v0")

    def field_load(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        """``t = o.f``"""
        access = self.field_access(instruction.arg2, instruction)
        dest, target = instruction.result, instruction.arg1
        if not access.dynamic:
            self.static_accesses += 1
            lines, register = self.registers.value_register(target, unit)
            lines += self.null_check(target, register, unit)
            load = "lbu" if access.sizes == {1} else "lw"
            lines += [
                f"{load} $t9, {access.offset}({register})",
                f"lbu $a3, {tag_offset(access.offset)}({register})",
            ]
            return lines + self.registers.assign_from(dest, unit, "$t9", tag="$a3")
        self.dynamic_accesses += 1
        lines = self._lookup(target, access.key, unit, f"atributo «{access.name}»")
        lines += ["addu $t7, $t6, $t9", "subu $t6, $t6, $t9", "lbu $a3, -1($t6)"]
        lines += self._sized("$t9", "0($t7)", access.sizes, load=True)
        return lines + self.registers.assign_from(dest, unit, "$t9", tag="$a3")

    def field_store(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        """``o.f = x``"""
        target, value = instruction.result, instruction.arg2
        access = self.field_access(instruction.arg1, instruction)
        if not access.dynamic:
            self.static_accesses += 1
            lines, register = self.registers.value_register(target, unit)
            lines += self.null_check(target, register, unit)
            # El valor va a registros auxiliares: así no puede desalojar al
            # registro que tiene el objeto.
            lines += self.registers.load_into(value, unit, "$t9")
            lines += self.registers.load_type(value, unit, "$a3")
            store = "sb" if access.sizes == {1} else "sw"
            return lines + [
                f"{store} $t9, {access.offset}({register})",
                f"sb $a3, {tag_offset(access.offset)}({register})",
            ]
        self.dynamic_accesses += 1
        lines = self._lookup(target, access.key, unit, f"atributo «{access.name}»")
        lines += ["addu $t7, $t6, $t9", "subu $t6, $t6, $t9"]
        lines += self.registers.load_into(value, unit, "$t9")
        lines += self.registers.load_type(value, unit, "$a3")
        lines += self._sized("$t9", "0($t7)", access.sizes, load=False)
        return lines + ["sb $a3, -1($t6)"]

    def method_load(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        """``t = method o.m``: dirección de la implementación vigente."""
        access = self.method_access(instruction.arg2, instruction)
        dest, target = instruction.result, instruction.arg1
        self._method_frames[dest] = access.frame
        if not access.dynamic:
            self.static_accesses += 1
            lines, register = self.registers.value_register(target, unit)
            lines += self.null_check(target, register, unit)
            lines += [f"lw $t9, 0({register})", f"lw $t9, {WORD_SIZE * access.index}($t9)  # {access.name}"]
            return lines + self.registers.assign_from(dest, unit, "$t9")
        self.dynamic_accesses += 1
        lines = self._lookup(target, access.key, unit, f"método «{access.name}»")
        return lines + self.registers.assign_from(dest, unit, "$t9")

    def method_frame(self, target: Operand) -> FrameLayout | None:
        """Marco del método cuya dirección quedó en ``target`` (lo necesita
        ``FunctionTranslator.translate_call``)."""
        return self._method_frames.pop(target, None) if isinstance(target, Temp) else None

    # -- auxiliares -----------------------------------------------------------
    def _lookup(self, target: Operand, key: int, unit: str | None, description: str) -> list[str]:
        """Objeto en ``$t6``; deja en ``$t9`` el valor del miembro ``key``."""
        lines = self.registers.load_into(target, unit, "$t6")
        lines += self.null_check(target, "$t6", unit)
        return lines + [f"li $t7, {key}  # {description}: búsqueda dinámica", f"jal {LOOKUP_LABEL}"]

    def _sized(self, register: str, address: str, sizes: frozenset[int], load: bool) -> list[str]:
        """Lee o escribe una palabra o un byte; si el tamaño depende de la
        clase dinámica, lo decide en tiempo de ejecución con ``$t8``."""
        word, byte = ("lw", "lbu") if load else ("sw", "sb")
        if sizes == {1}:
            return [f"{byte} {register}, {address}"]
        if sizes == {WORD_SIZE}:
            return [f"{word} {register}, {address}"]
        small, done = self.runtime.label(), self.runtime.label()
        return [
            "li $a0, 1",
            f"beq $t8, $a0, {small}",
            f"{word} {register}, {address}",
            f"j {done}",
            f"{small}:",
            f"{byte} {register}, {address}",
            f"{done}:",
        ]

    # -- datos ---------------------------------------------------------------
    def data_lines(self) -> list[str]:
        """Vtable y tabla de miembros de cada clase."""
        if not self.layouts:
            return []
        lines = ["# clases: tabla de miembros (en vtable - 4) y vtable de cada clase"]
        for name, layout in self.layouts.items():
            parent = f" (extiende {layout.superclass})" if layout.superclass else ""
            lines += [
                f"# clase {name}{parent}: {layout.size} bytes por instancia",
                ".align 2",
                f".word {members_label(name)}",
                f"{vtable_label(name)}:",
            ]
            for index, (method, label) in enumerate(layout.vtable):
                lines.append(f".word {self.model.frame(label).label}  # {index}: {method} ({label})")
            fields = self.fields(layout)
            lines += [f"{members_label(name)}:", f".word {len(fields) + len(layout.vtable)}"]
            for slot in fields:
                key = self.keys[("atributo", slot.name)]
                lines.append(f".word {key}, {slot.offset}, {slot.size}  # atributo {slot.name}")
            for method, label in layout.vtable:
                key = self.keys[("método", method)]
                lines.append(f".word {key}, {self.model.frame(label).label}, 0  # método {method}")
        return lines
