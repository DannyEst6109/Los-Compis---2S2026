"""Optimización por mirilla orientada al control de flujo (Persona 3).

Complementa las reglas locales de ``mips_peephole.py`` (Persona 2). Trabaja
sobre el programa completo, sólo en la sección ``.text``, con MARS sin
saltos retardados. Cada regla mira una ventana pequeña de instrucciones
(la «mirilla"); los comentarios no cuentan como instrucciones y una
etiqueta corta las ventanas, porque a ella se puede llegar por otro camino.

=====================================  ==========================================
Regla                                  Ejemplo
=====================================  ==========================================
1. Salto a salto                       ``j L1`` … ``L1: j L2``  →  ``j L2``
   (también ``beq``/``bne``)
2. Salto condicional sobre un salto    ``bne $t0, $zero, L1`` / ``j L2`` / ``L1:``
                                       →  ``beq $t0, $zero, L2`` / ``L1:``
3. Código inalcanzable                 instrucciones después de ``j``/``jr`` y
                                       antes de la siguiente etiqueta
4. Etiqueta sin uso                    ``L7:`` que ningún salto menciona
5. Carga de lo recién guardado         ``sw $t0, -8($fp)`` / ``lw $t1, -8($fp)``
                                       →  ``sw …`` / ``move $t1, $t0``
6. Carga repetida                      ``lw $t0, X`` / ``lw $t0, X``  →  una
7. Movimiento de ida y vuelta          ``move $t0, $t1`` / ``move $t1, $t0``
                                       →  sólo el primero
8. Salto condicional a la siguiente    ``beq $t0, $zero, L4`` / ``L4:``  →  ``L4:``
   instrucción                         (los dos caminos llegan al mismo lugar)
=====================================  ==========================================

Las reglas 1 a 4 limpian sobre todo lo que produce la traducción de
``if``/``while``/``for``/``switch``: el TAC salta a etiquetas que sólo
tienen otro salto, o pone ``if c goto L1; goto L2; L1:``. La regla 4 sólo
borra etiquetas generadas (``L5``, ``p2_local_3``, ``p3_local_8``): nunca las
de funciones, ``main`` ni las de datos.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field

_BRANCH = re.compile(r"^(beq|bne)\s+(\$\w+),\s*(\$\w+),\s*([A-Za-z_]\w*)$")
_JUMP = re.compile(r"^j\s+([A-Za-z_]\w*)$")
_JR = re.compile(r"^jr\s+\$\w+$")
_LABEL = re.compile(r"^([A-Za-z_][\w.$]*):$")
_MEMORY = re.compile(r"^(lw|sw)\s+(\$\w+),\s*(.+)$")
_MOVE = re.compile(r"^move\s+(\$\w+),\s*(\$\w+)$")
_BASE = re.compile(r"\((\$\w+)\)$")
_GENERATED_LABEL = re.compile(r"^(?:L\d+|p2_local_\d+|p3_local_\d+)$")
_WORD = re.compile(r"[A-Za-z_][\w.$]*")
_INVERSE = {"beq": "bne", "bne": "beq"}

THREADING = "salto a salto"
BRANCH_OVER_JUMP = "salto condicional sobre salto"
UNREACHABLE = "código inalcanzable"
UNUSED_LABEL = "etiqueta sin uso"
STORE_LOAD = "carga de lo recién guardado"
REPEATED_LOAD = "carga repetida"
MOVE_BACK = "movimiento de ida y vuelta"
BRANCH_TO_NEXT = "salto condicional a la siguiente instrucción"


@dataclass
class PeepholeReport:
    """Cuántas veces se aplicó cada transformación."""

    counts: Counter = field(default_factory=Counter)

    def add(self, rule: str, amount: int = 1) -> None:
        if amount > 0:
            self.counts[rule] += amount

    def merge(self, other: "PeepholeReport") -> None:
        for rule, amount in other.counts.items():
            self.add(rule, amount)

    @property
    def total(self) -> int:
        return sum(self.counts.values())

    def lines(self) -> list[str]:
        return [f"{rule}: {amount}" for rule, amount in self.counts.most_common()]


def _code(line: str) -> str:
    """La línea sin comentario ni espacios."""
    return line.split("#", 1)[0].strip()


def _is_label(code: str) -> bool:
    return bool(_LABEL.match(code))


def _is_instruction(code: str) -> bool:
    return bool(code) and not _is_label(code) and not code.startswith(".")


def _indent(line: str) -> str:
    return line[: len(line) - len(line.lstrip())]


class _Text:
    """Vista de la sección ``.text`` (las directivas y ``.data`` quedan
    intactas)."""

    def __init__(self, lines: list[str]) -> None:
        self.lines = list(lines)
        self.start = self.lines.index(".text") + 1 if ".text" in self.lines else 0

    def indices(self):
        return range(self.start, len(self.lines))

    def next_instruction(self, index: int, cross_labels: bool) -> int | None:
        """Índice de la siguiente instrucción después de ``index``."""
        for position in range(index + 1, len(self.lines)):
            code = _code(self.lines[position])
            if _is_label(code):
                if not cross_labels:
                    return None
                continue
            if _is_instruction(code):
                return position
        return None

    def labels(self) -> dict[str, int]:
        found = {}
        for index in self.indices():
            match = _LABEL.match(_code(self.lines[index]))
            if match:
                found[match.group(1)] = index
        return found


def _thread_jumps(text: _Text, report: PeepholeReport) -> None:
    """Regla 1: un salto a una etiqueta cuya primera instrucción es ``j B``
    puede ir directo a ``B``."""
    labels = text.labels()

    def final_target(label: str) -> str:
        seen = {label}
        while label in labels:
            position = text.next_instruction(labels[label], cross_labels=True)
            jump = _JUMP.match(_code(text.lines[position])) if position is not None else None
            if jump is None or jump.group(1) in seen:
                break
            label = jump.group(1)
            seen.add(label)
        return label

    for index in text.indices():
        line = text.lines[index]
        code = _code(line)
        if jump := _JUMP.match(code):
            target = final_target(jump.group(1))
            if target != jump.group(1):
                text.lines[index] = f"{_indent(line)}j {target}"
                report.add(THREADING)
        elif branch := _BRANCH.match(code):
            target = final_target(branch.group(4))
            if target != branch.group(4):
                op, left, right = branch.group(1, 2, 3)
                text.lines[index] = f"{_indent(line)}{op} {left}, {right}, {target}"
                report.add(THREADING)


def _branch_over_jump(text: _Text, report: PeepholeReport) -> None:
    """Regla 2: ``bxx a, b, L1`` / ``j L2`` / ``L1:`` se vuelve
    ``b!xx a, b, L2`` / ``L1:``."""
    index = text.start
    while index < len(text.lines):
        branch = _BRANCH.match(_code(text.lines[index]))
        following = text.next_instruction(index, cross_labels=False) if branch else None
        jump = _JUMP.match(_code(text.lines[following])) if following is not None else None
        if branch and jump:
            # Después del j sólo puede haber comentarios y luego L1.
            position = following + 1
            while position < len(text.lines) and not _code(text.lines[position]):
                position += 1
            label = _LABEL.match(_code(text.lines[position])) if position < len(text.lines) else None
            if label and label.group(1) == branch.group(4):
                op, left, right = branch.group(1, 2, 3)
                text.lines[index] = f"{_indent(text.lines[index])}{_INVERSE[op]} {left}, {right}, {jump.group(1)}"
                del text.lines[following]
                # El comentario TAC del salto eliminado ya no describe nada.
                if text.lines[following - 1].strip() == f"# goto {jump.group(1)}":
                    del text.lines[following - 1]
                report.add(BRANCH_OVER_JUMP)
        index += 1


def _branch_to_next(text: _Text, report: PeepholeReport) -> None:
    """Regla 8: ``beq``/``bne`` a la etiqueta que viene justo después (sólo
    con comentarios u otras etiquetas en medio). ``beq``/``bne`` no tienen
    efectos además del salto, así que se pueden quitar."""
    index = text.start
    while index < len(text.lines):
        branch = _BRANCH.match(_code(text.lines[index]))
        if branch:
            position, labels = index + 1, set()
            while position < len(text.lines):
                code = _code(text.lines[position])
                if match := _LABEL.match(code):
                    labels.add(match.group(1))
                elif code:
                    break
                position += 1
            if branch.group(4) in labels:
                del text.lines[index]
                report.add(BRANCH_TO_NEXT)
                continue
        index += 1


def _remove_unreachable(text: _Text, report: PeepholeReport) -> None:
    """Regla 3: nada se ejecuta entre un salto incondicional y la siguiente
    etiqueta. Los comentarios de esas instrucciones también se van; se
    conservan los que marcan secciones (``# ----``, ``# end_func``)."""
    result = text.lines[: text.start]
    dead = False
    for line in text.lines[text.start:]:
        code = _code(line)
        if _is_label(code):
            dead = False
        elif dead:
            stripped = line.strip()
            if _is_instruction(code):
                report.add(UNREACHABLE)
                continue
            if stripped.startswith("#") and not stripped.startswith(("# ----", "# end_func", "# begin_func")):
                continue
        elif _JUMP.match(code) or _JR.match(code):
            dead = True
        result.append(line)
    text.lines = result


def _remove_unused_labels(text: _Text, report: PeepholeReport) -> None:
    """Regla 4: etiquetas generadas que nadie menciona."""
    used: Counter = Counter()
    for index, line in enumerate(text.lines):
        code = _code(line)
        if index >= text.start and _is_label(code):
            continue
        used.update(_WORD.findall(code))
    result = text.lines[: text.start]
    for line in text.lines[text.start:]:
        match = _LABEL.match(_code(line))
        if match and _GENERATED_LABEL.match(match.group(1)) and not used[match.group(1)]:
            report.add(UNUSED_LABEL)
            continue
        result.append(line)
    text.lines = result


def _adjacent_rules(text: _Text, report: PeepholeReport) -> None:
    """Reglas 5 a 7: pares de instrucciones consecutivas (sin etiqueta entre
    ellas)."""
    index = text.start
    while index < len(text.lines):
        first = _code(text.lines[index])
        if not _is_instruction(first):
            index += 1
            continue
        following = text.next_instruction(index, cross_labels=False)
        if following is None:
            index += 1
            continue
        second = _code(text.lines[following])
        replacement = _pair(first, second, report)
        if replacement is not None:
            if replacement:
                text.lines[following] = f"{_indent(text.lines[following])}{replacement}"
            else:
                del text.lines[following]
            continue  # vuelve a mirar la misma instrucción con la siguiente
        index += 1


def _pair(first: str, second: str, report: PeepholeReport) -> str | None:
    """Devuelve la nueva segunda instrucción, ``""`` para borrarla o
    ``None`` si ninguna regla aplica."""
    one, two = _MEMORY.match(first), _MEMORY.match(second)
    if one and two and two.group(1) == "lw" and one.group(3) == two.group(3):
        source, dest = one.group(2), two.group(2)
        if one.group(1) == "sw":
            report.add(STORE_LOAD)
            return "" if source == dest else f"move {dest}, {source}"
        base = _BASE.search(one.group(3))
        # lw $t0, X / lw $t1, X: X no puede depender del registro cargado.
        if base is None or base.group(1) != source:
            report.add(REPEATED_LOAD)
            return "" if source == dest else f"move {dest}, {source}"
    move_one, move_two = _MOVE.match(first), _MOVE.match(second)
    if move_one and move_two and move_one.groups() == move_two.groups()[::-1]:
        report.add(MOVE_BACK)
        return ""
    return None


def optimize_control_flow(lines: list[str]) -> tuple[list[str], PeepholeReport]:
    """Aplica una ronda de las ocho reglas. ``mips_generator`` repite las
    rondas (junto con las de Persona 2) hasta que el código no cambia."""
    report = PeepholeReport()
    text = _Text(lines)
    _thread_jumps(text, report)
    _branch_over_jump(text, report)
    _branch_to_next(text, report)
    _remove_unreachable(text, report)
    _remove_unused_labels(text, report)
    _adjacent_rules(text, report)
    return text.lines, report
