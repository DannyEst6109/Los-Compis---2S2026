"""Soporte en tiempo de ejecución que comparten los traductores de Persona 3.

Contiene lo que no corresponde a una sola instrucción TAC:

* **Etiquetas locales** ``p3_local_N`` para los saltos internos de una
  instrucción (por ejemplo, la verificación de un objeto nulo).
* **Errores en tiempo de ejecución.** ``guard`` emite la verificación
  «si el registro es cero, lanzar un error»: guarda los registros
  modificados y salta a ``p3_throw`` con el mensaje en ``$a0``. Persona 2
  usa el mismo punto de entrada (``BasicTranslator(..., fault_label)``) para
  la división entre cero, los arreglos y las cadenas nulas.
* **Rutinas compartidas** que se agregan al final de ``.text`` sólo si el
  programa las usa:

  - ``p3_throw``: busca el manejador activo de ``try/catch``. Si existe,
    lo retira, restaura ``$fp`` y ``$sp`` (descarta los marcos intermedios)
    y salta al ``catch``; si no, imprime el error y termina el programa.
  - ``p3_lookup``: búsqueda dinámica de un atributo o método por su clave
    en la tabla de miembros de la clase del objeto (sólo cuando la clase
    estática del objeto no se conoce y el miembro está en posiciones
    distintas según la clase).

Pila de manejadores (la usa ``mips_exceptions.py``). Cada ``try_begin``
reserva 12 bytes en la pila del marco actual::

    0($sp)   $fp del marco que instaló el manejador
    4($sp)   dirección del catch (etiqueta TAC)
    8($sp)   manejador anterior (lista enlazada)

``p3_handler`` apunta al manejador activo (0 si no hay) y ``p3_exception``
guarda el mensaje del último error, que ``e = exception`` asigna a la
variable del ``catch``.

Registros: estas rutinas sólo usan ``$t6-$t9`` y ``$a0-$a3``, que no
conservan valores entre instrucciones TAC (``NOTAS.md``, sección 6).
"""

from __future__ import annotations

from mips_functions import SYSCALL_EXIT, SYSCALL_PRINT_CHAR, SYSCALL_PRINT_STRING, MipsFunctionError
from mips_registers import MipsRegisters
from tac import Const, TACInstruction

THROW_LABEL = "p3_throw"
UNCAUGHT_LABEL = "p3_uncaught"
LOOKUP_LABEL = "p3_lookup"
HANDLER_LABEL = "p3_handler"
EXCEPTION_LABEL = "p3_exception"
UNWIND_TRACE_LABEL = "p3_trace_unwind"
LOCAL_PREFIX = "p3_local_"

HANDLER_SIZE = 12  # $fp, catch, manejador anterior
SYSCALL_SBRK = 9
SYSCALL_WRITE = 15

# Mensajes de los errores que detecta Persona 3.
NULL_OBJECT_MESSAGE = "Acceso a un objeto nulo"
MISSING_MEMBER_MESSAGE = "El objeto no tiene el miembro solicitado"
UNCAUGHT_PREFIX = "Error en tiempo de ejecución: "

# Los mensajes de Persona 2 terminan en salto de línea (los imprime ella
# misma cuando no hay manejador). La variable del catch recibe el texto sin
# ese salto, y la salida sin manejador lo agrega una sola vez.
BASIC_FAULT_MESSAGES = (
    "División por cero",
    "Longitud de arreglo inválida",
    "Arreglo nulo",
    "Índice de arreglo fuera de rango",
    "Cadena nula",
)


class MipsGenerationError(MipsFunctionError):
    """Instrucción TAC que Persona 3 no puede traducir a MIPS."""

    def __init__(self, message: str, instruction: TACInstruction | None = None) -> None:
        super().__init__(message, instruction)


class RuntimeSupport:
    """Etiquetas locales, errores en tiempo de ejecución y rutinas comunes."""

    def __init__(self, registers: MipsRegisters, trace: bool = False) -> None:
        self.registers = registers
        self.trace = trace
        self._next_label = 0

    # -- etiquetas ------------------------------------------------------------
    def label(self) -> str:
        self._next_label += 1
        return f"{LOCAL_PREFIX}{self._next_label}"

    # -- errores --------------------------------------------------------------
    def guard(self, register: str, unit: str | None, message: str) -> list[str]:
        """Continúa si ``register`` no es cero; si lo es, lanza ``message``.

        Antes de saltar se guardan los registros modificados, para que el
        ``catch`` (o el resto del programa) vea la memoria actualizada. Las
        asociaciones de registros siguen siendo válidas después de la
        etiqueta de continuación: sólo se llega a ella desde el ``bne``."""
        valid = self.label()
        lines = self.registers.spill(unit)
        lines.append(f"bne {register}, $zero, {valid}")
        lines += self.registers.load_into(Const(message, "string"), unit, "$a0")
        lines += [f"j {THROW_LABEL}", f"{valid}:"]
        return lines

    # -- rutinas --------------------------------------------------------------
    def _string(self, text: str, register: str) -> list[str]:
        """``la register, <cadena>``. Fuera de una instrucción TAC no hay
        valores vivos en registros, así que se olvidan las asociaciones antes
        de pedir la cadena (si no, podría reutilizarse un registro)."""
        self.registers.forget()
        return self.registers.load_into(Const(text, "string"), None, register)

    @staticmethod
    def _write_string() -> list[str]:
        """Imprime la cadena de ``$a0`` (mismo formato que Persona 2:
        longitud en la primera palabra y bytes UTF-8 después)."""
        return ["lw $a2, 0($a0)", "addiu $a1, $a0, 4", "li $a0, 1", f"li $v0, {SYSCALL_WRITE}", "syscall"]

    def throw_routine(self) -> list[str]:
        lines = [
            "# ---- p3_throw: lanza el error cuyo mensaje está en $a0 ----",
            f"{THROW_LABEL}:",
        ]
        # Sólo los mensajes que el programa puede producir (los que Persona 2
        # ya agregó a su tabla de cadenas).
        interned = getattr(self.registers, "_strings", None)
        for message in BASIC_FAULT_MESSAGES:
            if interned is not None and message + "\n" not in interned:
                continue
            skip = self.label()
            lines += self._string(message + "\n", "$t9")
            lines.append(f"bne $a0, $t9, {skip}")
            lines += self._string(message, "$a0")
            lines.append(f"{skip}:")
        lines += [
            f"sw $a0, {EXCEPTION_LABEL}",
            f"lw $t6, {HANDLER_LABEL}",
            f"beq $t6, $zero, {UNCAUGHT_LABEL}",
        ]
        if self.trace:
            # Cada marco que se descarta cierra su activación en la traza.
            loop, done = self.label(), self.label()
            lines += [
                "lw $t8, 0($t6)",
                "move $t9, $fp",
                f"{loop}:",
                f"beq $t9, $t8, {done}",
                f"la $a0, {UNWIND_TRACE_LABEL}",
                f"li $v0, {SYSCALL_PRINT_STRING}",
                "syscall",
                "lw $t9, -8($t9)",
                f"j {loop}",
                f"{done}:",
            ]
        lines += [
            "lw $t7, 8($t6)",
            f"sw $t7, {HANDLER_LABEL}",  # retira el manejador
            "lw $fp, 0($t6)",  # marco que instaló el manejador
            "lw $t7, 4($t6)",  # dirección del catch
            f"addiu $sp, $t6, {HANDLER_SIZE}",  # $sp que tenía ese marco
            "jr $t7",
            f"{UNCAUGHT_LABEL}:",
            *self._string(UNCAUGHT_PREFIX, "$a0"),
            *self._write_string(),
            f"lw $a0, {EXCEPTION_LABEL}",
            *self._write_string(),
            "li $a0, 10",
            f"li $v0, {SYSCALL_PRINT_CHAR}",
            "syscall",
            f"li $v0, {SYSCALL_EXIT}",
            "syscall",
        ]
        return lines

    def lookup_routine(self) -> list[str]:
        """``$t6`` = objeto (no nulo), ``$t7`` = clave del miembro.
        Devuelve en ``$t9`` el valor (desplazamiento del atributo o dirección
        del método) y en ``$t8`` el tamaño del atributo (0 en métodos)."""
        loop, found, fail = self.label(), self.label(), self.label()
        return [
            "# ---- p3_lookup: busca un miembro en la tabla de la clase del objeto ----",
            f"{LOOKUP_LABEL}:",
            "lw $t8, 0($t6)",  # vtable de la clase dinámica
            "lw $t8, -4($t8)",  # tabla de miembros (justo antes de la vtable)
            "lw $t9, 0($t8)",  # cantidad de entradas
            "addiu $t8, $t8, 4",
            f"{loop}:",
            f"beq $t9, $zero, {fail}",
            "lw $a0, 0($t8)",
            f"beq $a0, $t7, {found}",
            "addiu $t8, $t8, 12",
            "addiu $t9, $t9, -1",
            f"j {loop}",
            f"{found}:",
            "lw $t9, 4($t8)",
            "lw $t8, 8($t8)",
            "jr $ra",
            f"{fail}:",
            *self._string(MISSING_MEMBER_MESSAGE, "$a0"),
            f"j {THROW_LABEL}",
        ]

    def data_lines(self, uses_throw: bool) -> list[str]:
        if not uses_throw:
            return []
        lines = [
            "# manejo de errores: manejador activo y último mensaje",
            ".align 2",
            f"{HANDLER_LABEL}: .word 0",
            f"{EXCEPTION_LABEL}: .word 0",
        ]
        if self.trace:
            lines.append(f'{UNWIND_TRACE_LABEL}: .asciiz "#<*\\n"')
        return lines
