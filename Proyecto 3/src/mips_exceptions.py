"""``try/catch`` en MIPS: ``try_begin L``, ``try_end`` y ``e = exception``.

MIPS no tiene excepciones, así que se implementan con una **pila de
manejadores** en memoria (``docs/MIPS_PERSONA3.md``). Compiscript no tiene
``throw``: los errores son de ejecución (división entre cero, índice fuera
de rango, objeto o cadena nula, ...). Quien los detecta salta a
``p3_throw`` con el mensaje en ``$a0`` (``mips_runtime.py``).

``try_begin L`` instala un manejador en la pila del marco actual::

    addiu $sp, $sp, -12
    lw    $t9, p3_handler          manejador anterior
    sw    $t9, 8($sp)
    la    $t9, L                   dirección del catch
    sw    $t9, 4($sp)
    sw    $fp, 0($sp)              marco que instala el manejador
    sw    $sp, p3_handler          ahora es el manejador activo

``try_end`` lo retira al salir normalmente del bloque::

    lw    $t9, 8($sp)
    sw    $t9, p3_handler
    addiu $sp, $sp, 12

Al ocurrir un error, ``p3_throw`` toma el manejador activo, lo retira,
restaura ``$fp`` y ``$sp`` (``$sp`` = dirección del manejador + 12, el valor
que tenía el marco antes del ``try_begin``) y salta a ``L``. Así se
descartan de una vez todos los marcos de las funciones llamadas desde el
``try`` (NOTAS.md, «Persona 3 necesita»). En ``L``, ``e = exception`` copia
el mensaje del error a la variable del ``catch``.

Por qué la pila del marco: dentro de una función ``$sp`` sólo cambia en
las secuencias de llamada, y cada llamada lo deja como estaba. Así
``try_end`` siempre encuentra su manejador en ``0($sp)``, los ``try``
anidados se apilan solos (también en llamadas recursivas) y un ``return``
libera todo con ``move $sp, $fp``. El TAC ya emite un ``try_end`` por cada
manejador que abandona un ``break``, ``continue`` o ``return``.

Registros: antes de instalar el manejador se guardan en memoria los valores
modificados. Todo salto a ``p3_throw`` también guarda antes los suyos, y la
etiqueta del ``catch`` empieza sin asociaciones (``mips_control.py``), así
que el ``catch`` lee los valores correctos de memoria.
"""

from __future__ import annotations

from mips_registers import STRING_TAG, MipsRegisters
from mips_runtime import EXCEPTION_LABEL, HANDLER_LABEL, HANDLER_SIZE, MipsGenerationError
from tac import Label, TACInstruction, TACOp

HANDLED_OPS = frozenset({TACOp.TRY_BEGIN, TACOp.TRY_END, TACOp.GET_EXCEPTION})


class ExceptionTranslator:
    def __init__(self, registers: MipsRegisters) -> None:
        self.registers = registers
        self.handlers = 0  # cantidad de try (estadística)

    def translate(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        op = instruction.op
        if op is TACOp.TRY_BEGIN:
            return self.try_begin(instruction, unit)
        if op is TACOp.TRY_END:
            return self.try_end()
        if op is TACOp.GET_EXCEPTION:
            return self.get_exception(instruction, unit)
        raise MipsGenerationError(f"Operación de excepciones no admitida: {op.name}.", instruction)

    def try_begin(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        handler = instruction.result
        if not isinstance(handler, Label):
            raise MipsGenerationError(f"«{handler}» no es una etiqueta.", instruction)
        self.handlers += 1
        return [
            *self.registers.spill(unit),
            f"addiu $sp, $sp, -{HANDLER_SIZE}",
            f"lw $t9, {HANDLER_LABEL}",
            "sw $t9, 8($sp)",
            f"la $t9, {handler}",
            "sw $t9, 4($sp)",
            "sw $fp, 0($sp)",
            f"sw $sp, {HANDLER_LABEL}",
        ]

    @staticmethod
    def try_end() -> list[str]:
        return [
            "lw $t9, 8($sp)",
            f"sw $t9, {HANDLER_LABEL}",
            f"addiu $sp, $sp, {HANDLER_SIZE}",
        ]

    def get_exception(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        """``e = exception``: el mensaje es una cadena."""
        return [
            f"lw $t9, {EXCEPTION_LABEL}",
            f"li $a3, {STRING_TAG}",
            *self.registers.assign_from(instruction.result, unit, "$t9", tag="$a3"),
        ]
