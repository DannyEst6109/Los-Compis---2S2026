"""Traducción MIPS de las operaciones básicas del TAC."""

from mips_functions import MipsFunctionError
from mips_registers import NULL_TAG, STRING_HEAD, STRING_TAG, MipsRegisters
from tac import BINARY_OPS, UNARY_OPS, Const, TACInstruction, TACOp


HANDLED_OPS = BINARY_OPS | UNARY_OPS | {
    TACOp.ASSIGN, TACOp.NEW_ARRAY, TACOp.INDEX_LOAD, TACOp.INDEX_STORE,
    TACOp.LENGTH, TACOp.CONCAT, TACOp.PRINT,
}

_ARITHMETIC = {TACOp.ADD: "addu", TACOp.SUB: "subu", TACOp.MUL: "mul"}
_MAX_ARRAY_LENGTH = (2**31 - 5) // 5


class BasicTranslator:
    """Emite listas de líneas MIPS para MARS con saltos retardados desactivados."""

    def __init__(self, registers: MipsRegisters, fault_label: str | None = None) -> None:
        self.registers = registers
        self.fault_label = fault_label
        self._next_label = 0

    def _label(self) -> str:
        self._next_label += 1
        return f"p2_local_{self._next_label}"

    def _guard(self, op: str, reg: str, unit: str | None, message: str) -> list[str]:
        """Sigue normalmente si reg cumple la condición contra cero."""
        valid = self._label()
        lines = self.registers.spill(unit) if self.fault_label is not None else []
        lines += [f"{op} {reg}, $zero, {valid}"]
        lines += self.registers.load_into(Const(message, "string"), unit, "$a0")
        if self.fault_label is not None:
            lines.append(f"j {self.fault_label}")
        else:
            lines += self._write_string() + ["li $v0, 10", "syscall"]
        return [*lines, f"{valid}:"]

    def translate(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        op = instruction.op
        if op not in HANDLED_OPS:
            raise MipsFunctionError(f"Operación básica no admitida: {op.name}.", instruction)
        if op is TACOp.PRINT:
            return self._print(instruction, unit)
        if op in (TACOp.NEW_ARRAY, TACOp.INDEX_LOAD, TACOp.INDEX_STORE, TACOp.LENGTH):
            return self._array(instruction, unit)

        regs = self.registers
        a, b, dest = instruction.arg1, instruction.arg2, instruction.result
        if op is TACOp.ASSIGN:
            lines, source = regs.value_register(a, unit)
            return lines + regs.load_type(a, unit, "$a3") + regs.assign_from(dest, unit, source, tag="$a3")

        lines = regs.load_into(a, unit, "$t7")
        if op in (TACOp.ADD, TACOp.SUB) and isinstance(b, Const) and b.type_name == "integer":
            immediate = b.value if op is TACOp.ADD else -b.value
            if -32768 <= immediate <= 32767:
                return lines + [f"addiu $t7, $t7, {immediate}"] + regs.assign_from(dest, unit, "$t7")
        if b is not None:
            lines += regs.load_into(b, unit, "$t8")
        if op is TACOp.CONCAT:
            lines += self._concat(unit) + [f"li $a3, {STRING_TAG}"]
            return lines + regs.assign_from(dest, unit, "$t7", tag="$a3")
        elif op in _ARITHMETIC:
            lines.append(f"{_ARITHMETIC[op]} $t7, $t7, $t8")
        elif op in (TACOp.DIV, TACOp.MOD):
            lines += self._guard("bne", "$t8", unit, "División por cero\n")
            lines += ["div $t7, $t8", "mflo $t7" if op is TACOp.DIV else "mfhi $t7"]
        elif op is TACOp.NEG:
            lines.append("subu $t7, $zero, $t7")
        elif op is TACOp.NOT:
            lines.append("sltiu $t7, $t7, 1")
        elif op in (TACOp.EQ, TACOp.NE):
            # Las cadenas iguales comparten puntero incluso con parámetros sin tipo.
            lines.append("xor $t7, $t7, $t8")
            lines.append("sltiu $t7, $t7, 1" if op is TACOp.EQ else "sltu $t7, $zero, $t7")
        else:
            left, right = ("$t8", "$t7") if op in (TACOp.GT, TACOp.LE) else ("$t7", "$t8")
            lines.append(f"slt $t7, {left}, {right}")
            if op in (TACOp.LE, TACOp.GE):
                lines.append("xori $t7, $t7, 1")
        return lines + regs.assign_from(dest, unit, "$t7")

    def _array(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        """Una palabra de longitud, una palabra por valor y un byte por tipo."""
        op, dest, a, b = instruction.op, instruction.result, instruction.arg1, instruction.arg2
        regs = self.registers
        if op is TACOp.NEW_ARRAY:
            lines = regs.load_into(a, unit, "$t7")
            lines += [f"li $t8, {_MAX_ARRAY_LENGTH + 1}", "sltu $t9, $t7, $t8"]
            lines += self._guard("bne", "$t9", unit, "Longitud de arreglo inválida\n")
            lines += [
                "sll $a0, $t7, 2", "addu $a0, $a0, $t7", "addiu $a0, $a0, 4", "li $v0, 9", "syscall",
                "sw $t7, 0($v0)",
            ]
            return lines + regs.assign_from(dest, unit, "$v0")

        array = dest if op is TACOp.INDEX_STORE else a
        lines = regs.load_into(array, unit, "$t7")
        lines += self._guard("bne", "$t7", unit, "Arreglo nulo\n")
        lines.append("lw $t9, 0($t7)")
        if op is TACOp.LENGTH:
            return lines + regs.assign_from(dest, unit, "$t9")
        index = a if op is TACOp.INDEX_STORE else b
        lines += regs.load_into(index, unit, "$t8")
        lines.append("sltu $t6, $t8, $t9")
        lines += self._guard("bne", "$t6", unit, "Índice de arreglo fuera de rango\n")
        lines += ["sll $t6, $t9, 2", "addu $t6, $t6, $t7", "addu $t6, $t6, $t8"]
        lines += ["sll $t8, $t8, 2", "addu $t7, $t7, $t8"]
        if op is TACOp.INDEX_STORE:
            lines += regs.load_into(b, unit, "$t9") + regs.load_type(b, unit, "$a3")
            return lines + ["sw $t9, 4($t7)", "sb $a3, 4($t6)"]
        return lines + ["lw $t9, 4($t7)", "lbu $a3, 4($t6)"] + regs.assign_from(dest, unit, "$t9", tag="$a3")

    def _concat(self, unit: str | None) -> list[str]:
        """Busca la cadena completa antes de reservar memoria para una nueva."""
        lines = self._guard("bne", "$t7", unit, "Cadena nula\n")
        lines += self._guard("bne", "$t8", unit, "Cadena nula\n")
        search, advance, allocate, done = (self._label() for _ in range(4))
        lines += [
            "lw $t6, 0($t7)", "lw $t9, 0($t8)", "addu $t9, $t6, $t9",
            f"lw $t6, {STRING_HEAD}", f"{search}:", f"beq $t6, $zero, {allocate}",
            "lw $a0, 0($t6)", f"bne $a0, $t9, {advance}", "addiu $a1, $t6, 4",
        ]
        for source in ("$t7", "$t8"):
            loop, end = self._label(), self._label()
            lines += [
                f"lw $a0, 0({source})", f"addiu $a2, {source}, 4", f"{loop}:",
                f"beq $a0, $zero, {end}", "lbu $a3, 0($a2)", "lbu $v0, 0($a1)",
                f"bne $a3, $v0, {advance}", "addiu $a1, $a1, 1", "addiu $a2, $a2, 1",
                "addiu $a0, $a0, -1", f"j {loop}", f"{end}:",
            ]
        lines += [
            "move $t7, $t6", f"j {done}",
            f"{advance}:", "lw $t6, -4($t6)", f"j {search}",
            f"{allocate}:", "addiu $a0, $t9, 9", "li $v0, 9", "syscall",
            f"lw $t6, {STRING_HEAD}", "sw $t6, 0($v0)", "addiu $v0, $v0, 4",
            "sw $t9, 0($v0)", "addiu $t6, $v0, 4",
        ]
        for source in ("$t7", "$t8"):
            loop, end = self._label(), self._label()
            lines += [
                f"lw $t9, 0({source})", f"addiu {source}, {source}, 4",
                f"{loop}:", f"beq $t9, $zero, {end}", f"lbu $a0, 0({source})",
                "sb $a0, 0($t6)", "addiu $t6, $t6, 1", f"addiu {source}, {source}, 1", "addiu $t9, $t9, -1",
                f"j {loop}", f"{end}:",
            ]
        return lines + [
            "sb $zero, 0($t6)", f"sw $v0, {STRING_HEAD}", "move $t7, $v0", f"{done}:",
        ]

    def _print(self, instruction: TACInstruction, unit: str | None) -> list[str]:
        regs = self.registers
        # Los literales numéricos nunca necesitan una bifurcación.
        operand = instruction.arg1
        newline = ["li $a0, 10", "li $v0, 11", "syscall"]
        if isinstance(operand, Const):
            if operand.type_name == "null":
                operand = Const("null", "string")
            lines = regs.load_into(operand, unit, "$a0")
            return lines + (self._write_string() if operand.type_name == "string" else ["li $v0, 1", "syscall"]) + newline
        string, null, end = (self._label() for _ in range(3))
        lines = regs.load_into(operand, unit, "$a0") + regs.load_type(operand, unit, "$t6")
        lines += [
            f"li $t7, {STRING_TAG}", f"beq $t6, $t7, {string}",
            f"li $t7, {NULL_TAG}", f"beq $t6, $t7, {null}",
            "li $v0, 1", "syscall", f"j {end}",
            f"{null}:",
        ]
        lines += regs.load_into(Const("null", "string"), unit, "$a0")
        return lines + [f"{string}:", *self._write_string(), f"{end}:", *newline]

    @staticmethod
    def _write_string() -> list[str]:
        # syscall 15 escribe UTF-8 a stdout. MARS lee un byte extra.
        return ["lw $a2, 0($a0)", "addiu $a1, $a0, 4", "li $a0, 1", "li $v0, 15", "syscall"]
