"""Sentencias de control en MIPS: ``label``, ``goto``, ``if`` e ``ifFalse``.

El TAC del Proyecto 2 ya reduce ``if/else``, ``while``, ``do-while``,
``for``, ``foreach``, ``switch/case``, ``break``, ``continue``, ``&&``,
``||`` y ``?:`` a etiquetas y saltos (``docs/CONTROL_FLUJO.md``). Aquí se
traduce cada uno de esos saltos a MIPS, respetando el contrato de la
asignación de registros de Persona 2 (``NOTAS.md``, «Integración de
Persona 2»):

========================  ==================================================
TAC                       MIPS
========================  ==================================================
``L:``                    guardar registros modificados (camino que llega
                          por continuación), ``L:`` y olvidar asociaciones
``goto L``                guardar registros, ``j L`` y olvidar asociaciones
``if c goto L``           ``c`` en un registro, guardar, ``bne c, $zero, L``
``ifFalse c goto L``      ``c`` en un registro, guardar, ``beq c, $zero, L``
========================  ==================================================

Por qué así:

* En una etiqueta pueden confluir varios caminos y cada uno deja valores
  distintos en los registros. Antes de cualquier salto se escriben a memoria
  los valores modificados, así en la etiqueta la memoria siempre está al
  día y se puede empezar «en limpio».
* Después de un salto condicional **no** se olvidan las asociaciones: el
  camino que sigue de largo tiene exactamente los mismos registros, y
  después de guardar ya están todos limpios. Así el cuerpo de un ``if`` o de
  un ciclo puede reutilizar, por ejemplo, la variable que se comparó.
* Una condición constante (``if false goto L``, que el TAC produce en
  ``do { } while (false)``) se resuelve al compilar: se vuelve un salto
  incondicional o no genera nada.

Ejemplo real (``if (x > 10) { y = 1; } else { y = 2; }`` con ``x`` y ``y``
globales; el comentario ``#`` es la instrucción TAC que se traduce)::

    # t1 = x > 10                 Persona 2 (getReg eligió $t4 para t1)
    move $t7, $t1
    li   $t8, 10
    slt  $t7, $t8, $t7
    move $t4, $t7
    # if t1 goto L1
    sw   $t3, 4($gp)              guardar y, x y t1 antes de saltar
    sw   $t1, 0($gp)
    sw   $t4, 8($gp)
    bne  $t4, $zero, L1
    # goto L2
    j    L2
    L1:                           y = 1
    ...
    # goto L3
    sw   $t1, 4($gp)
    j    L3
    L2:                           y = 2
    ...
    L3:

La mirilla (``mips_peephole_control.py``) convierte después
``bne $t4, $zero, L1`` / ``j L2`` / ``L1:`` en ``beq $t4, $zero, L2``.
"""

from __future__ import annotations

from mips_registers import MipsRegisters
from tac import Const, Label, TACInstruction, TACOp

HANDLED_OPS = frozenset({TACOp.LABEL, TACOp.GOTO, TACOp.IF_TRUE, TACOp.IF_FALSE})


def is_true_constant(constant: Const) -> bool:
    """Valor de verdad de una condición constante."""
    return constant.value not in (None, False, 0, "")


class ControlFlowTranslator:
    """Traduce las instrucciones de salto del TAC."""

    def __init__(self, registers: MipsRegisters) -> None:
        self.registers = registers
        # Estadísticas (las muestra el IDE).
        self.labels = 0
        self.jumps = 0
        self.branches = 0
        self.folded = 0

    def translate(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        op = instruction.op
        target = instruction.result
        if not isinstance(target, Label):
            from mips_runtime import MipsGenerationError

            raise MipsGenerationError(f"«{target}» no es una etiqueta.", instruction)
        if op is TACOp.LABEL:
            return self.label(target, unit)
        if op is TACOp.GOTO:
            return self.goto(target, unit)
        return self.branch(instruction.arg1, target, unit, jump_if=op is TACOp.IF_TRUE)

    def label(self, target: Label, unit: str | None) -> list[str]:
        self.labels += 1
        lines = [*self.registers.spill(unit), f"{target}:"]
        self.registers.forget()
        return lines

    def goto(self, target: Label, unit: str | None) -> list[str]:
        self.jumps += 1
        lines = [*self.registers.spill(unit), f"j {target}"]
        self.registers.forget()
        return lines

    def branch(self, condition, target: Label, unit: str | None, jump_if: bool) -> list[str]:
        """``if c goto L`` (``jump_if=True``) o ``ifFalse c goto L``."""
        if isinstance(condition, Const):
            self.folded += 1
            if is_true_constant(condition) == jump_if:
                return ["# condición constante: el salto siempre se toma", *self.goto(target, unit)]
            return ["# condición constante: el salto nunca se toma"]
        self.branches += 1
        lines, register = self.registers.value_register(condition, unit)
        lines += self.registers.spill(unit)
        mnemonic = "bne" if jump_if else "beq"
        lines.append(f"{mnemonic} {register}, $zero, {target}")
        return lines
