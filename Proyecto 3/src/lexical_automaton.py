"""AFD por regla, derivado de la ATN del lexer generado por ANTLR.

Elimina epsilon y expande llamadas a fragmentos mediante configuraciones
(estado, retornos). Determiniza conjuntos de configuraciones y fusiona
estados equivalentes. Reconoce el lenguaje completo de la regla, sin las
prioridades entre tokens ni el corte anticipado de reglas no codiciosas;
``lexer_description`` informa por separado la decisión del lexer real.
"""

from collections import deque
from dataclasses import dataclass
from functools import lru_cache

from analyzer import CompiscriptLexer, LexerDiagnosticListener
from antlr4 import InputStream
from antlr4.atn.ATNState import ATNState
from antlr4.atn.Transition import Transition

MAX_CHAR = 0x10FFFF


@dataclass(frozen=True)
class Edge:
    source: int
    target: int
    ranges: tuple[tuple[int, int], ...]  # intervalos inclusivos

    @property
    def label(self):
        return ranges_label(self.ranges)


@dataclass(frozen=True)
class Trace:
    states: tuple[int, ...]
    accepted: bool
    failed_at: int | None


@dataclass(frozen=True)
class Automaton:
    rule: str
    state_count: int
    accepting: frozenset[int]
    edges: tuple[Edge, ...]

    def trace(self, text: str) -> Trace:
        state, states = 0, [0]
        outgoing = {}
        for edge in self.edges:
            outgoing.setdefault(edge.source, []).append(edge)
        for index, char in enumerate(text):
            code = ord(char)
            target = next((edge.target for edge in outgoing.get(state, [])
                           if any(low <= code <= high for low, high in edge.ranges)), None)
            if target is None:
                return Trace(tuple(states), False, index)
            state = target
            states.append(state)
        return Trace(tuple(states), state in self.accepting, None)


def token_rules() -> list[str]:
    return [name for index, name in enumerate(CompiscriptLexer.ruleNames)
            if CompiscriptLexer.atn.ruleToTokenType[index] > 0]


def _closure(configurations):
    atn = CompiscriptLexer.atn
    pending, visited, result = list(configurations), set(), set()
    while pending:
        number, stack = pending.pop()
        config = number, stack
        if config in visited:
            continue
        visited.add(config)
        state = atn.states[number]
        if state.stateType == ATNState.RULE_STOP:
            if stack:
                pending.append((stack[-1], stack[:-1]))
            else:
                result.add(config)
            continue
        if any(not transition.isEpsilon for transition in state.transitions):
            result.add(config)
        for transition in state.transitions:
            if transition.serializationType == Transition.RULE:
                if len(stack) >= 32:
                    raise ValueError("No se admiten fragmentos léxicos recursivos en esta vista.")
                pending.append((transition.target.stateNumber, stack + (transition.followState.stateNumber,)))
            elif transition.serializationType in (Transition.PREDICATE, Transition.PRECEDENCE):
                raise ValueError("Esta regla usa predicados; no se puede representar como un AFD puro.")
            elif transition.isEpsilon:
                pending.append((transition.target.stateNumber, stack))
    return frozenset(result)


@lru_cache(maxsize=1)
def _alphabet():
    boundaries = {0, MAX_CHAR + 1}
    for state in CompiscriptLexer.atn.states:
        if state is None:
            continue
        for transition in state.transitions:
            if transition.label is not None:
                for interval in transition.label.intervals or []:
                    boundaries.update((max(0, interval.start), min(MAX_CHAR + 1, interval.stop)))
    points = sorted(boundaries)
    return tuple((low, high - 1) for low, high in zip(points, points[1:]) if low < high)


def _merge_ranges(ranges):
    merged = []
    for low, high in sorted(ranges):
        if merged and merged[-1][1] + 1 == low:
            merged[-1] = merged[-1][0], high
        else:
            merged.append((low, high))
    return tuple(merged)


@lru_cache(maxsize=64)
def build_automaton(rule: str) -> Automaton:
    if rule not in token_rules():
        raise ValueError(f"No existe la regla de token «{rule}».")
    atn = CompiscriptLexer.atn
    start = atn.ruleToStartState[CompiscriptLexer.ruleNames.index(rule)]
    initial = _closure({(start.stateNumber, ())})
    states, indexes, pending = [initial], {initial: 0}, deque([initial])
    alphabet, rows, accepting = _alphabet(), [], set()
    while pending:
        configurations = pending.popleft()
        source = indexes[configurations]
        if any(atn.states[number].stateType == ATNState.RULE_STOP and not stack
               for number, stack in configurations):
            accepting.add(source)
        row = []
        transitions = [(transition, stack) for number, stack in configurations
                       for transition in atn.states[number].transitions if not transition.isEpsilon
                       and atn.states[number].stateType != ATNState.RULE_STOP]
        for low, _high in alphabet:
            destination = _closure({(t.target.stateNumber, stack) for t, stack in transitions
                                    if t.matches(low, 0, MAX_CHAR)})
            if not destination:
                row.append(-1)
                continue
            if destination not in indexes:
                if len(states) >= 256:
                    raise ValueError("La regla supera el límite de 256 estados de esta vista.")
                indexes[destination] = len(states)
                states.append(destination)
                pending.append(destination)
            row.append(indexes[destination])
        rows.append(row)
    # Refinamiento de particiones. -1 representa el rechazo implícito.
    groups = [int(index in accepting) for index in range(len(states))]
    while True:
        signatures, refined = {}, []
        for index, row in enumerate(rows):
            signature = (index in accepting, tuple(groups[target] if target >= 0 else -1 for target in row))
            refined.append(signatures.setdefault(signature, len(signatures)))
        if refined == groups:
            break
        groups = refined
    ordered = list(dict.fromkeys(groups))  # el estado inicial conserva q0
    names = {group: index for index, group in enumerate(ordered)}
    edges = []
    for group in ordered:
        representative = groups.index(group)
        targets = {}
        for interval, target in zip(alphabet, rows[representative]):
            if target >= 0:
                targets.setdefault(names[groups[target]], []).append(interval)
        for target, ranges in sorted(targets.items()):
            edges.append(Edge(names[group], target, _merge_ranges(ranges)))
    return Automaton(rule, len(ordered), frozenset(names[groups[i]] for i in accepting), tuple(edges))


def character_label(code):
    special = {9: r"\t", 10: r"\n", 13: r"\r", 32: "espacio", 92: r"\\"}
    return special.get(code, chr(code) if chr(code).isprintable() else f"U+{code:04X}")


def ranges_label(ranges):
    if ranges == ((0, MAX_CHAR),):
        return "cualquier carácter"
    complement, previous = [], 0
    for low, high in ranges:
        if low > previous:
            complement.append((previous, low - 1))
        previous = high + 1
    if previous <= MAX_CHAR:
        complement.append((previous, MAX_CHAR))
    if sum(high - low + 1 for low, high in complement) <= 8:
        return "excepto " + ", ".join(character_label(code) for low, high in complement for code in range(low, high + 1))
    return ", ".join(character_label(low) if low == high else f"{character_label(low)}–{character_label(high)}"
                     for low, high in ranges)


def lexer_description(text: str) -> str:
    diagnostics = []
    lexer = CompiscriptLexer(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(LexerDiagnosticListener(diagnostics))
    tokens = lexer.getAllTokens()
    if diagnostics:
        return "Lexer real: entrada con errores léxicos."
    if not tokens:
        return "Lexer real: no emite tokens (entrada vacía o texto omitido)."
    if len(tokens) == 1 and tokens[0].start == 0 and tokens[0].stop == len(text) - 1:
        return f"Lexer real: {CompiscriptLexer.symbolicNames[tokens[0].type]}."
    return "Lexer real: la entrada no se consume como un único token completo."
