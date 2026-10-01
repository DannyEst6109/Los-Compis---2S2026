"""Representación interna del código intermedio (TAC) de Compiscript.

Este módulo define *qué* es el lenguaje intermedio: los operandos, el
conjunto de instrucciones y cómo se imprime cada una. No sabe nada del AST
ni de la tabla de símbolos; el generador (``tac_generator.py``) es quien
recorre el AST y produce instancias de las clases de aquí.

Cada instrucción es una **cuádrupla** ``(op, result, arg1, arg2)``. La
especificación completa del lenguaje (con ejemplos y supuestos) está en
``docs/TAC.md``; cualquier fase que emita TAC debe usar exclusivamente las
operaciones de ``TACOp`` para que todo el programa comparta una sola
sintaxis.

Uso típico::

    from tac import Const, TACOp, TACProgram, Temp, Var

    program = TACProgram()
    program.emit(TACOp.MUL, Temp(1), Var("b"), Const(5))
    program.emit(TACOp.ADD, Temp(1), Var("a"), Temp(1))
    program.emit(TACOp.ASSIGN, Var("x"), Temp(1))
    print(program.render())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterator, Union


# ---------------------------------------------------------------------------
# Operandos
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Temp:
    """Variable temporal generada por el compilador: ``t1``, ``t2``, ...

    Los índices los administra ``temporaries.TempAllocator``; un mismo
    índice puede reaparecer varias veces en el programa porque los
    temporales se reciclan cuando dejan de necesitarse.
    """

    index: int

    def __str__(self) -> str:
        return f"t{self.index}"


@dataclass(frozen=True, slots=True)
class Var:
    """Variable, constante o parámetro declarado en el programa fuente.

    ``name`` es el nombre con el que aparece en el TAC (puede diferir del
    nombre original si hubo shadowing, ver ``docs/TAC.md``). ``symbol`` es
    la entrada de ``symbol_table.Symbol`` correspondiente, para que las
    fases siguientes puedan consultar su tipo, ámbito o dirección. No
    participa en la igualdad ni en la impresión.
    """

    name: str
    symbol: Any = field(default=None, compare=False, repr=False)

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class Const:
    """Valor literal: ``integer``, ``string``, ``boolean`` o ``null``."""

    value: int | str | bool | None
    type_name: str

    def __str__(self) -> str:
        if self.type_name == "string":
            escaped = (
                str(self.value)
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\t", "\\t")
            )
            return f'"{escaped}"'
        if self.value is None:
            return "null"
        if isinstance(self.value, bool):
            return "true" if self.value else "false"
        return str(self.value)


@dataclass(frozen=True, slots=True)
class Label:
    """Etiqueta destino de un salto: ``L1``, ``L2``, ..."""

    name: str

    def __str__(self) -> str:
        return self.name


@dataclass(frozen=True, slots=True)
class Name:
    """Identificador que no es un valor almacenable: nombre de función,
    de clase o de atributo (en ``call``, ``new``, ``o.f``, ``begin_func``)."""

    name: str

    def __str__(self) -> str:
        return self.name


Operand = Union[Temp, Var, Const, Label, Name]


# ---------------------------------------------------------------------------
# Conjunto de instrucciones
# ---------------------------------------------------------------------------


class TACOp(Enum):
    """Operaciones del lenguaje intermedio.

    El valor de cada miembro es el símbolo o palabra clave con la que se
    imprime. La forma exacta de cada instrucción (qué campos usa) está en
    ``_FORMATS`` y documentada en ``docs/TAC.md``.
    """

    # Copia.
    ASSIGN = "="

    # Aritméticas (integer).
    ADD = "+"
    SUB = "-"
    MUL = "*"
    DIV = "/"
    MOD = "%"

    # Concatenación de string (el backend la traduce distinto a ADD).
    CONCAT = "concat"

    # Relacionales y de igualdad (producen boolean).
    LT = "<"
    LE = "<="
    GT = ">"
    GE = ">="
    EQ = "=="
    NE = "!="

    # Unarias.
    NEG = "minus"
    NOT = "not"

    # Saltos y etiquetas.
    LABEL = "label"
    GOTO = "goto"
    IF_TRUE = "if"
    IF_FALSE = "ifFalse"

    # Funciones.
    BEGIN_FUNC = "begin_func"
    END_FUNC = "end_func"
    PARAM = "param"
    CALL = "call"
    RETURN = "return"

    # Arreglos.
    NEW_ARRAY = "new_array"
    INDEX_LOAD = "index_load"
    INDEX_STORE = "index_store"
    LENGTH = "len"

    # Objetos.
    NEW_OBJECT = "new"
    FIELD_LOAD = "field_load"
    FIELD_STORE = "field_store"

    # Salida.
    PRINT = "print"


BINARY_OPS = frozenset(
    {
        TACOp.ADD, TACOp.SUB, TACOp.MUL, TACOp.DIV, TACOp.MOD,
        TACOp.LT, TACOp.LE, TACOp.GT, TACOp.GE, TACOp.EQ, TACOp.NE,
    }
)
UNARY_OPS = frozenset({TACOp.NEG, TACOp.NOT})

# Operadores de Compiscript -> operación TAC (sólo los que son
# directamente una cuádrupla; ``&&``, ``||`` y ``?:`` se traducen con saltos).
SOURCE_BINARY_OPS = {
    "+": TACOp.ADD,
    "-": TACOp.SUB,
    "*": TACOp.MUL,
    "/": TACOp.DIV,
    "%": TACOp.MOD,
    "<": TACOp.LT,
    "<=": TACOp.LE,
    ">": TACOp.GT,
    ">=": TACOp.GE,
    "==": TACOp.EQ,
    "!=": TACOp.NE,
}
SOURCE_UNARY_OPS = {"-": TACOp.NEG, "!": TACOp.NOT}


# ---------------------------------------------------------------------------
# Instrucción y programa
# ---------------------------------------------------------------------------


class TACError(Exception):
    """Instrucción mal formada (faltan operandos obligatorios)."""


# Formato de impresión por operación. ``r`` = result, ``a`` = arg1,
# ``b`` = arg2. Las operaciones con variantes (``call``, ``return``,
# ``begin_func``) se resuelven en ``TACInstruction.__str__``.
_FORMATS: dict[TACOp, str] = {
    TACOp.ASSIGN: "{r} = {a}",
    TACOp.CONCAT: "{r} = concat {a}, {b}",
    TACOp.NEG: "{r} = minus {a}",
    TACOp.NOT: "{r} = not {a}",
    TACOp.LABEL: "{r}:",
    TACOp.GOTO: "goto {r}",
    TACOp.IF_TRUE: "if {a} goto {r}",
    TACOp.IF_FALSE: "ifFalse {a} goto {r}",
    TACOp.END_FUNC: "end_func {a}",
    TACOp.PARAM: "param {a}",
    TACOp.NEW_ARRAY: "{r} = new_array {a}",
    TACOp.INDEX_LOAD: "{r} = {a}[{b}]",
    TACOp.INDEX_STORE: "{r}[{a}] = {b}",
    TACOp.LENGTH: "{r} = len {a}",
    TACOp.NEW_OBJECT: "{r} = new {a}",
    TACOp.FIELD_LOAD: "{r} = {a}.{b}",
    TACOp.FIELD_STORE: "{r}.{a} = {b}",
    TACOp.PRINT: "print {a}",
}

# Campos obligatorios por operación (los opcionales no se listan).
_REQUIRED: dict[TACOp, str] = {
    TACOp.ASSIGN: "ra",
    TACOp.CONCAT: "rab",
    TACOp.LABEL: "r",
    TACOp.GOTO: "r",
    TACOp.IF_TRUE: "ra",
    TACOp.IF_FALSE: "ra",
    TACOp.BEGIN_FUNC: "a",
    TACOp.END_FUNC: "a",
    TACOp.PARAM: "a",
    TACOp.CALL: "ab",
    TACOp.RETURN: "",
    TACOp.NEW_ARRAY: "ra",
    TACOp.INDEX_LOAD: "rab",
    TACOp.INDEX_STORE: "rab",
    TACOp.LENGTH: "ra",
    TACOp.NEW_OBJECT: "ra",
    TACOp.FIELD_LOAD: "rab",
    TACOp.FIELD_STORE: "rab",
    TACOp.PRINT: "a",
    **{op: "rab" for op in BINARY_OPS},
    **{op: "ra" for op in UNARY_OPS},
}

# Operaciones que se imprimen sin sangría (delimitan secciones del programa).
_UNINDENTED = frozenset({TACOp.LABEL, TACOp.BEGIN_FUNC, TACOp.END_FUNC})


@dataclass(frozen=True, slots=True)
class TACInstruction:
    """Cuádrupla ``(op, result, arg1, arg2)``.

    ``line`` es la línea del código fuente que originó la instrucción; no
    se imprime, pero permite relacionar el TAC con el editor.
    """

    op: TACOp
    result: Operand | None = None
    arg1: Operand | None = None
    arg2: Operand | None = None
    line: int | None = None

    def __post_init__(self) -> None:
        values = {"r": self.result, "a": self.arg1, "b": self.arg2}
        missing = [key for key in _REQUIRED[self.op] if values[key] is None]
        if missing:
            names = {"r": "result", "a": "arg1", "b": "arg2"}
            raise TACError(
                f"La instrucción {self.op.name} requiere {', '.join(names[key] for key in missing)}."
            )

    def __str__(self) -> str:
        op = self.op
        if op in BINARY_OPS:
            return f"{self.result} = {self.arg1} {op.value} {self.arg2}"
        if op is TACOp.CALL:
            call = f"call {self.arg1}, {self.arg2}"
            return f"{self.result} = {call}" if self.result is not None else call
        if op is TACOp.RETURN:
            return f"return {self.arg1}" if self.arg1 is not None else "return"
        if op is TACOp.BEGIN_FUNC:
            if self.arg2 is not None:
                return f"begin_func {self.arg1}, {self.arg2}"
            return f"begin_func {self.arg1}"
        return _FORMATS[op].format(r=self.result, a=self.arg1, b=self.arg2)

    @property
    def indented(self) -> bool:
        return self.op not in _UNINDENTED


class TACProgram:
    """Secuencia ordenada de instrucciones TAC."""

    INDENT = "    "

    def __init__(self) -> None:
        self.instructions: list[TACInstruction] = []

    def emit(
        self,
        op: TACOp,
        result: Operand | None = None,
        arg1: Operand | None = None,
        arg2: Operand | None = None,
        *,
        line: int | None = None,
    ) -> TACInstruction:
        instruction = TACInstruction(op, result, arg1, arg2, line)
        self.instructions.append(instruction)
        return instruction

    def __iter__(self) -> Iterator[TACInstruction]:
        return iter(self.instructions)

    def __len__(self) -> int:
        return len(self.instructions)

    def __getitem__(self, index: int) -> TACInstruction:
        return self.instructions[index]

    def lines(self) -> list[str]:
        """Instrucciones impresas, sin sangría (útil en pruebas)."""
        return [str(instruction) for instruction in self.instructions]

    def render(self) -> str:
        """Texto final del programa: etiquetas y límites de función al
        margen, el resto con sangría."""
        return "\n".join(
            (self.INDENT if instruction.indented else "") + str(instruction)
            for instruction in self.instructions
        )

    def __str__(self) -> str:
        return self.render()
