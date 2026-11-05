"""Secuencias de llamada y retorno en MIPS: traducción de ``begin_func``,
``end_func``, ``return``, ``param`` y ``call``.

Sigue la convención de ``NOTAS.md``: todos los argumentos van por la pila,
``$fp`` apunta al tope del marco, el valor de retorno queda en ``$v0``, los
``$t`` los guarda quien llama y los ``$s`` la función llamada.

Secuencia de llamada (``param x1 … param xn`` + ``[t =] call f, n``)::

    # call f, n
    <guardar registros modificados>       Persona 2
    addiu $sp, $sp, -P                     reserva encabezado + this + parámetros de f
    sw    <x_i>, (P - off_i - size_i)($sp) un argumento por casilla (sb si es boolean)
    sw    <enlace de acceso>, (P - 12)($sp)
    jal   fn_f                             o jalr $r para métodos
    <t = $v0>                              Persona 2

Prólogo y epílogo de ``f``::

    fn_f:
        sw    $ra, P-4($sp)
        sw    $fp, P-8($sp)
        addiu $fp, $sp, P
        addiu $sp, $fp, -SIZE
        sw    $s_i, ...($fp)               sólo los $s que usó f
        ...cuerpo...                       cada return: $v0 = valor; j fn_f_fin
    fn_f_fin:
        lw    $s_i, ...($fp)
        lw    $ra, -4($fp)
        move  $sp, $fp                     libera el marco: $sp vuelve al valor anterior a la llamada
        lw    $fp, -8($fp)
        jr    $ra

Las instrucciones se devuelven como listas de cadenas sin sangría; una
etiqueta termina en ``:`` y un comentario empieza con ``#``. Este módulo no
decide en qué registro vive cada valor: eso lo hace la asignación de
registros (``RegisterAllocator``, Persona 2).
"""

from __future__ import annotations

from typing import Iterable, Protocol

from mips_frames import (
    CONTROL_LINK_OFFSET,
    FP,
    RA,
    RETURN_ADDRESS_OFFSET,
    RETURN_VALUE,
    SP,
    ZERO,
    FrameLayout,
    FrameModel,
    MipsFrameError,
)
from symbol_table import WORD_SIZE
from tac import Name, Operand, TACInstruction, TACOp

# Operaciones del TAC que traduce este módulo.
HANDLED_OPS = frozenset({TACOp.BEGIN_FUNC, TACOp.END_FUNC, TACOp.PARAM, TACOp.CALL, TACOp.RETURN})


class MipsFunctionError(MipsFrameError):
    """TAC de funciones o llamadas que no puede traducirse."""

    def __init__(self, message: str, instruction: TACInstruction | None = None) -> None:
        self.instruction = instruction
        self.line = instruction.line if instruction is not None else None
        if instruction is not None:
            where = f"«{str(instruction).strip()}»"
            if self.line is not None:
                where += f", línea {self.line}"
            message = f"{message} ({where})"
        super().__init__(message)


class RegisterAllocator(Protocol):
    """Lo que necesitan las llamadas de la asignación de registros (Persona 2).

    ``unit`` es la etiqueta TAC de la función actual o ``None`` en el código
    global. Todos los métodos que emiten código devuelven las instrucciones
    como lista de cadenas. Ninguno puede usar ``$v1``, ``$sp``, ``$fp`` ni
    ``$ra``."""

    def value_register(self, operand: Operand, unit: str | None) -> tuple[list[str], str]:
        """Deja el valor de ``operand`` en algún registro y lo devuelve."""

    def load_into(self, operand: Operand, unit: str | None, register: str) -> list[str]:
        """Deja el valor de ``operand`` en ``register`` (por ejemplo ``$v0``)."""

    def assign_from(self, operand: Operand, unit: str | None, register: str) -> list[str]:
        """``operand = register`` (el resultado de una llamada está en ``$v0``)."""

    def spill(self, unit: str | None) -> list[str]:
        """Escribe a memoria los registros modificados (antes de llamar o
        de salir de la función)."""

    def forget(self) -> None:
        """Olvida el contenido de todos los registros (después de una
        llamada y al empezar o terminar una función)."""

    def saved_registers(self, unit: str) -> Iterable[str]:
        """Registros ``$s`` que usó la función ``unit``."""


class FunctionTranslator:
    """Traduce las instrucciones de funciones y llamadas de un programa.

    Quien integra el generador recorre el TAC y:

    * llama a ``begin_function`` en cada ``begin_func`` y empieza a juntar
      las líneas del cuerpo;
    * manda cada ``param``, ``call`` y ``return`` del cuerpo a
      ``translate_param``, ``translate_call`` y ``translate_return``;
    * en ``end_func`` llama a ``end_function`` con las líneas del cuerpo, y
      recibe la función completa (prólogo + cuerpo + epílogo).

    En el código global (fuera de toda función) también se usan
    ``translate_param`` y ``translate_call``."""

    def __init__(self, model: FrameModel, registers: RegisterAllocator) -> None:
        self.model = model
        self.registers = registers
        self._frame: FrameLayout | None = None
        self._params: list[tuple[Operand, TACInstruction]] = []

    # -- estado ---------------------------------------------------------------
    @property
    def unit(self) -> str | None:
        """Etiqueta TAC de la función que se está traduciendo (``None`` en
        el código global)."""
        return self._frame.name if self._frame is not None else None

    @property
    def frame(self) -> FrameLayout | None:
        return self._frame

    @property
    def pending_params(self) -> int:
        return len(self._params)

    def ensure_no_pending_params(self, instruction: TACInstruction | None = None) -> None:
        """Error si hay ``param`` sin su ``call``. Quien integra puede
        llamarlo antes de traducir cualquier otra instrucción."""
        if self._params:
            first = self._params[0][1]
            raise MipsFunctionError(
                f"Hay {len(self._params)} «param» sin su «call» (el primero es «{str(first).strip()}»).",
                instruction,
            )

    # -- funciones: prólogo, epílogo y return --------------------------------
    def begin_function(self, instruction: TACInstruction) -> list[str]:
        """``begin_func f, n``. No emite nada todavía: el prólogo depende de
        los ``$s`` que use el cuerpo, así que lo arma ``end_function``."""
        self._expect(instruction, TACOp.BEGIN_FUNC)
        if self._frame is not None:
            raise MipsFunctionError(f"«begin_func» dentro de la función «{self._frame.name}».", instruction)
        self.ensure_no_pending_params(instruction)
        frame = self._callee(instruction.arg1, instruction)
        size = instruction.arg2.value if instruction.arg2 is not None else None
        if size is not None and size != frame.record.size:
            raise MipsFunctionError(
                f"El TAC dice que «{frame.name}» ocupa {size} bytes, pero su registro ocupa {frame.record.size}.",
                instruction,
            )
        self._frame = frame
        self.registers.forget()
        return []

    def end_function(self, instruction: TACInstruction, body: list[str]) -> list[str]:
        """``end_func f``: devuelve la función completa. Llegar al final sin
        ``return`` equivale a ``return`` sin valor."""
        self._expect(instruction, TACOp.END_FUNC)
        frame = self._require_frame(instruction)
        if instruction.arg1.name != frame.name:
            raise MipsFunctionError(f"«end_func» no corresponde a la función abierta «{frame.name}».", instruction)
        self.ensure_no_pending_params(instruction)
        fall_through = list(self.registers.spill(frame.name))
        frame.use_saved_registers(self.registers.saved_registers(frame.name))
        lines = [*self.prologue(frame), *body, *fall_through, *self.epilogue(frame)]
        self.registers.forget()
        self._frame = None
        return lines

    def prologue(self, frame: FrameLayout) -> list[str]:
        prefix = frame.prefix_size
        lines = [
            f"# begin_func {frame.name}, {frame.record.size}",
            f"{frame.label}:",
            f"sw {RA}, {prefix - RETURN_ADDRESS_OFFSET - WORD_SIZE}({SP})",
            f"sw {FP}, {prefix - CONTROL_LINK_OFFSET - WORD_SIZE}({SP})",
            f"addiu {FP}, {SP}, {prefix}",
            f"addiu {SP}, {FP}, -{frame.size}",
        ]
        for register in frame.saved_registers:
            lines += frame.saved_register_location(register).store(register)
        return lines

    def epilogue(self, frame: FrameLayout) -> list[str]:
        lines = [f"{frame.epilogue_label}:"]
        for register in frame.saved_registers:
            lines += frame.saved_register_location(register).load(register)
        lines += [
            f"lw {RA}, {frame.return_address.address}",
            f"move {SP}, {FP}",
            f"lw {FP}, {frame.control_link.address}",
            f"jr {RA}",
            f"# end_func {frame.name}",
        ]
        return lines

    def translate_return(self, instruction: TACInstruction) -> list[str]:
        """``return x`` / ``return``: deja el valor en ``$v0`` y salta al
        epílogo, que es el único punto de salida de la función."""
        self._expect(instruction, TACOp.RETURN)
        frame = self._require_frame(instruction)
        self.ensure_no_pending_params(instruction)
        lines = [f"# {str(instruction).strip()}", *self.registers.spill(frame.name)]
        if instruction.arg1 is not None:
            lines += self.registers.load_into(instruction.arg1, frame.name, RETURN_VALUE)
        lines.append(f"j {frame.epilogue_label}")
        return lines

    # -- llamadas -------------------------------------------------------------
    def translate_param(self, instruction: TACInstruction) -> list[str]:
        """``param x``: se guarda hasta su ``call``, que conoce el marco de
        la función llamada y por lo tanto dónde va cada argumento."""
        self._expect(instruction, TACOp.PARAM)
        self._params.append((instruction.arg1, instruction))
        return []

    def translate_call(self, instruction: TACInstruction, method_frame: FrameLayout | None = None) -> list[str]:
        """``[t =] call f, n``.

        Si ``f`` es un temporal con la dirección de un método (``t = method
        o.m``), quien traduce ``method`` (Persona 3) debe pasar en
        ``method_frame`` el marco de ``m`` en el tipo estático de ``o``: de
        ahí salen el tamaño del prefijo y la casilla de cada argumento."""
        self._expect(instruction, TACOp.CALL)
        arguments, self._params = self._params, []
        target = instruction.arg1
        count = instruction.arg2.value
        if count != len(arguments):
            raise MipsFunctionError(f"«call» espera {count} argumentos y hay {len(arguments)} «param».", instruction)

        if isinstance(target, Name):
            callee = self._callee(target, instruction)
            if method_frame is not None and method_frame is not callee:
                raise MipsFunctionError(
                    f"La llamada es a «{callee.name}», no al método «{method_frame.name}».", instruction
                )
        elif method_frame is None:
            raise MipsFunctionError(
                f"La llamada indirecta a «{target}» necesita el marco del método (method_frame).", instruction
            )
        else:
            callee = method_frame

        slots = callee.argument_locations()
        if len(slots) != count:
            raise MipsFunctionError(f"«{callee.name}» recibe {len(slots)} argumentos, no {count}.", instruction)

        unit = self.unit
        lines = [f"# {str(instruction).strip()}", *self.registers.spill(unit)]
        lines.append(f"addiu {SP}, {SP}, -{callee.prefix_size}")
        for (operand, _), location in zip(arguments, slots):
            code, register = self.registers.value_register(operand, unit)
            lines += code
            lines.append(f"{location.store_op} {register}, {location.address}")
        lines += self.access_link(callee, instruction)
        if isinstance(target, Name):
            lines.append(f"jal {callee.label}")
        else:
            code, register = self.registers.value_register(target, unit)
            lines += code
            lines.append(f"jalr {register}")
        # Al volver, $sp ya está como antes del addiu y los registros
        # pudieron cambiar dentro de la función llamada.
        self.registers.forget()
        if instruction.result is not None:
            lines += self.registers.assign_from(instruction.result, unit, RETURN_VALUE)
        return lines

    def access_link(self, callee: FrameLayout, instruction: TACInstruction | None = None) -> list[str]:
        """Escribe el enlace de acceso de ``callee``: el ``$fp`` del registro
        que la contiene léxicamente, visto desde la función actual."""
        location = callee.caller_access_link
        parent = callee.record.parent
        if parent is None or parent == self.model.global_area.record.name:
            return [f"sw {ZERO}, {location.address}"]
        if self._frame is None:
            raise MipsFunctionError(
                f"«{callee.name}» está declarada dentro de «{parent}» y no puede llamarse desde el código global.",
                instruction,
            )
        try:
            hops = self.model.hops_to(self._frame, parent, callee.name)
        except MipsFrameError as error:
            raise MipsFunctionError(str(error), instruction) from None
        setup, base = self.model.follow_access_links(hops)
        return [*setup, f"sw {base}, {location.address}"]

    # -- auxiliares -----------------------------------------------------------
    def _callee(self, target: object, instruction: TACInstruction) -> FrameLayout:
        if not isinstance(target, Name):
            raise MipsFunctionError(f"«{target}» no es el nombre de una función.", instruction)
        try:
            return self.model.frame(target.name)
        except MipsFrameError as error:
            raise MipsFunctionError(str(error), instruction) from None

    def _require_frame(self, instruction: TACInstruction) -> FrameLayout:
        if self._frame is None:
            raise MipsFunctionError(f"«{instruction.op.value}» fuera de una función.", instruction)
        return self._frame

    @staticmethod
    def _expect(instruction: TACInstruction, op: TACOp) -> None:
        if instruction.op is not op:
            raise MipsFunctionError(f"Se esperaba «{op.value}».", instruction)
