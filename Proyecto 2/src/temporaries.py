"""Asignación y reciclaje de variables temporales.

Algoritmo
---------

Un temporal guarda un resultado intermedio que se usa **exactamente una
vez** como operando de otra instrucción (así se generan las expresiones: el
resultado de un subárbol sólo lo consume su nodo padre). Por eso puede
liberarse en el momento en que se consume:

1. ``new()`` entrega el temporal libre de **menor índice**; si no hay
   ninguno libre, crea uno nuevo (``t1``, ``t2``, ...). Elegir siempre el
   menor hace que la salida sea determinista y mantiene los índices bajos.
2. ``release(op)`` devuelve el temporal al conjunto de libres. Si ``op`` no
   es un temporal (variable o constante) no hace nada, así el generador
   puede liberar cualquier operando sin preguntar su clase.
3. El generador libera los operandos **antes** de pedir el temporal del
   resultado, así que el resultado puede reutilizar el registro de uno de
   sus operandos (``t1 = t1 + t2``). Con esto un temporal sólo está vivo
   mientras su valor todavía no se ha consumido, que es lo mínimo posible
   si el árbol se evalúa de izquierda a derecha (no se reordenan
   subexpresiones, porque pueden tener efectos secundarios).

Liberar dos veces el mismo temporal, o uno que nunca se entregó, indica un
error del generador (un resultado se usó dos veces o se perdió) y lanza
``TempAllocatorError`` en lugar de corromper el TAC en silencio.
"""

from __future__ import annotations

import heapq

from tac import Operand, Temp


class TempAllocatorError(Exception):
    """Uso inválido del asignador (doble liberación o temporal ajeno)."""


class TempAllocator:
    def __init__(self) -> None:
        self._next_index = 1
        self._free: list[int] = []  # min-heap de índices disponibles
        self._live: set[int] = set()
        self._max_live = 0
        self._allocations = 0
        self._reuses = 0

    # -- operaciones -------------------------------------------------------
    def new(self) -> Temp:
        """Entrega un temporal libre (el de menor índice) o crea uno nuevo."""
        if self._free:
            index = heapq.heappop(self._free)
            self._reuses += 1
        else:
            index = self._next_index
            self._next_index += 1
        self._live.add(index)
        self._allocations += 1
        self._max_live = max(self._max_live, len(self._live))
        return Temp(index)

    def release(self, operand: Operand | None) -> None:
        """Marca ``operand`` como libre si es un temporal."""
        if not isinstance(operand, Temp):
            return
        if operand.index not in self._live:
            raise TempAllocatorError(
                f"Se intentó liberar {operand}, que no está en uso "
                "(doble liberación o temporal que no pertenece a este asignador)."
            )
        self._live.remove(operand.index)
        heapq.heappush(self._free, operand.index)

    def reset(self) -> None:
        """Descarta todos los temporales (p. ej. al iniciar otra unidad de
        generación independiente). Las estadísticas también se reinician."""
        self.__init__()

    # -- consultas ---------------------------------------------------------
    def is_live(self, operand: Operand | None) -> bool:
        return isinstance(operand, Temp) and operand.index in self._live

    @property
    def live_count(self) -> int:
        """Temporales entregados y todavía no liberados."""
        return len(self._live)

    @property
    def created(self) -> int:
        """Cantidad de nombres distintos (``t1``..``tN``) creados."""
        return self._next_index - 1

    @property
    def max_live(self) -> int:
        """Máximo de temporales vivos simultáneamente."""
        return self._max_live

    @property
    def allocations(self) -> int:
        """Veces que se pidió un temporal (con o sin reciclaje)."""
        return self._allocations

    @property
    def reuses(self) -> int:
        """Veces que ``new()`` devolvió un temporal reciclado."""
        return self._reuses
