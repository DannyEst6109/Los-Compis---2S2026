"""Árboles de activación a partir de la traza de una ejecución.

Cuando el MIPS se genera con traza (``FunctionTranslator(..., trace=True)``),
cada función imprime al entrar ``#>nombre arg1 arg2…`` y al salir
``#<nombre``. Este módulo lee esa salida (de MARS o de cualquier simulador)
y arma el árbol: cada nodo es una activación y sus hijos son las llamadas que
hizo, en orden. La raíz es el programa principal.

Ejemplo para ``print(factorial(3));``::

    main
    └── factorial(3)
        └── factorial(2)
            └── factorial(1)

Cada nodo corresponde a un registro de activación distinto en la pila: dos
llamadas a la misma función son dos nodos, aunque tengan los mismos
argumentos.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

ROOT_NAME = "main"

# «#>nombre a1 a2» o «#<nombre», terminados en salto de línea. Pueden quedar
# pegados a lo que imprimió el programa («5#>f 3»).
_EVENT = re.compile(r"#([<>])([^\s#]+)((?: [^\s#]+)*)\n")


class ActivationTraceError(Exception):
    """La traza no forma un árbol válido."""


@dataclass
class Activation:
    """Un nodo del árbol: una activación de una función."""

    name: str
    arguments: tuple[str, ...] = ()
    children: list["Activation"] = field(default_factory=list)
    finished: bool = False

    @property
    def label(self) -> str:
        if self.name == ROOT_NAME and not self.arguments:
            return self.name
        return f"{self.name}({', '.join(self.arguments)})"

    def walk(self) -> Iterator["Activation"]:
        """Este nodo y todos sus descendientes, en preorden."""
        yield self
        for child in self.children:
            yield from child.walk()

    @property
    def depth(self) -> int:
        """Altura del subárbol: cuántas activaciones anidadas hay como máximo
        debajo de este nodo (0 si no llamó a nadie)."""
        return 1 + max((child.depth for child in self.children), default=-1)

    def count(self, name: str | None = None) -> int:
        """Cantidad de activaciones del subárbol (sin contar la raíz), o
        sólo las de ``name``."""
        return sum(1 for node in self.walk() if node is not self and (name is None or node.name == name))


def build_activation_tree(output: str, strict: bool = True) -> Activation:
    """Arma el árbol a partir de la salida de una ejecución con traza.

    Con ``strict=False``, una ejecución interrumpida (por ejemplo, por un
    error en tiempo de ejecución) deja las activaciones abiertas con
    ``finished=False`` en lugar de lanzar ``ActivationTraceError``."""
    root = Activation(ROOT_NAME)
    stack = [root]
    for match in _EVENT.finditer(output):
        kind, name, arguments = match.group(1), match.group(2), match.group(3).split()
        if kind == ">":
            node = Activation(name, tuple(arguments))
            stack[-1].children.append(node)
            stack.append(node)
            continue
        if len(stack) == 1:
            raise ActivationTraceError(f"«{name}» termina sin haber empezado.")
        if stack[-1].name != name:
            raise ActivationTraceError(
                f"Termina «{name}» pero la activación abierta es «{stack[-1].label}»."
            )
        stack.pop().finished = True
    if len(stack) > 1 and strict:
        raise ActivationTraceError(f"La ejecución terminó dentro de «{stack[-1].label}».")
    root.finished = len(stack) == 1
    return root


def render_activation_tree(root: Activation) -> str:
    """Dibujo del árbol en texto, una activación por línea."""
    lines = [root.label]

    def draw(node: Activation, prefix: str) -> None:
        for index, child in enumerate(node.children):
            last = index == len(node.children) - 1
            mark = "" if child.finished else "  (sin terminar)"
            lines.append(f"{prefix}{'└── ' if last else '├── '}{child.label}{mark}")
            draw(child, prefix + ("    " if last else "│   "))

    draw(root, "")
    return "\n".join(lines)


def strip_trace(output: str) -> str:
    """La salida del programa sin las líneas de la traza."""
    return _EVENT.sub("", output)
