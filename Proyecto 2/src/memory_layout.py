"""Entornos de ejecución: direcciones, tamaños y registros de activación.

Recorre la jerarquía de ``Scope`` de una ``SymbolTable`` ya validada y
completa la información que necesitará la generación de código objeto:

* Cada variable, constante y parámetro recibe una clase de
  almacenamiento (global, parámetro, local), un desplazamiento y un
  tamaño. Su dirección simbólica queda en ``Symbol.address``
  (``global+8``, ``fp+16``).
* Cada función y método recibe una **etiqueta TAC** única
  (``Symbol.tac_label``) y un **registro de activación**
  (``Symbol.activation_record``) con el encabezado, ``this``, parámetros y
  locales. El generador de TAC agrega después la cantidad de temporales.
* Cada clase recibe una **distribución de sus instancias**
  (``Symbol.class_layout``): puntero a la vtable, atributos heredados y
  propios con su desplazamiento, y la vtable con la implementación vigente
  de cada método.

No recorre el AST: todo lo que necesita ya está en los ámbitos. Se ejecuta
sólo sobre programas sin errores (lo invoca ``generate_tac``), después del
análisis semántico, porque una variable sin anotación ocupa el tamaño de su
tipo inferido.

Tamaños: ``integer`` 4 bytes, ``boolean`` 1 byte; ``string``, arreglos,
objetos y ``null`` son referencias de una palabra (4 bytes). Cada dato se
alinea a su tamaño y cada registro termina alineado a una palabra.
"""

from __future__ import annotations

import re
from typing import Any

from symbol_table import (
    WORD_SIZE,
    ActivationRecord,
    ClassLayout,
    Scope,
    ScopeKind,
    StorageKind,
    Symbol,
    SymbolCategory,
    SymbolTable,
)

GLOBAL_RECORD = "global"
INIT_SUFFIX = "$init"
_DATA_CATEGORIES = (SymbolCategory.VARIABLE, SymbolCategory.CONSTANT, SymbolCategory.PARAMETER)
_HEADER = ("dirección de retorno", "enlace de control", "enlace de acceso")
_RESERVED_NAME = re.compile(r"^(t|L)\d+$")


def size_of(type_name: str | None) -> int:
    """Bytes que ocupa un valor del tipo ``type_name`` en un registro."""
    return 1 if type_name == "boolean" else WORD_SIZE


def method_label(class_name: str, method_name: str) -> str:
    return f"{class_name}.{method_name}"


class MemoryLayoutBuilder:
    def __init__(self, table: SymbolTable, symbol_types: dict[int, Any] | None = None) -> None:
        self.table = table
        self._symbol_types = symbol_types or {}
        self._labels: set[str] = set()
        self._class_scopes = {
            scope.name: scope for scope in table.global_scope.children if scope.kind is ScopeKind.CLASS
        }
        self._classes_in_progress: set[str] = set()

    def build(self) -> SymbolTable:
        table = self.table
        for symbol in table.all_symbols():  # permite recalcular sobre la misma tabla
            symbol.storage = symbol.offset = symbol.runtime_type = symbol.owner = None
            symbol.size = 0
            symbol.tac_label = symbol.activation_record = symbol.class_layout = None
        table.activation_records = []
        table.class_layouts = {}
        table.global_record = ActivationRecord(name=GLOBAL_RECORD, kind="programa", level=0)
        self._walk(table.global_scope, table.global_record, level=0)
        return table

    # -- recorrido de ámbitos 
    def _walk(self, scope: Scope, record: ActivationRecord, level: int) -> None:
        """Aloja los datos de ``scope`` en ``record``. Los bloques internos
        comparten el registro de su función; las funciones y clases
        anidadas crean el suyo."""
        for symbol in scope.symbols.values():
            if symbol.category in _DATA_CATEGORIES and symbol.storage is None:
                self._allocate(record, symbol)
        for child in scope.children:
            if child.kind is ScopeKind.BLOCK:
                self._walk(child, record, level)
            elif child.kind is ScopeKind.FUNCTION:
                symbol = scope.resolve_local(child.name)
                if symbol is not None and symbol.category is SymbolCategory.FUNCTION:
                    self._function(symbol, child, parent=record, level=level + 1)
            elif child.kind is ScopeKind.CLASS:
                symbol = scope.resolve_local(child.name)
                if symbol is not None and symbol.category is SymbolCategory.CLASS:
                    self._class_scopes.setdefault(child.name, child)
                    self._class(symbol)

    def _allocate(self, record: ActivationRecord, symbol: Symbol) -> None:
        runtime_type = self._runtime_type(symbol)
        if record.name == GLOBAL_RECORD:
            storage, role = StorageKind.GLOBAL, "global"
        elif symbol.category is SymbolCategory.PARAMETER:
            storage, role = StorageKind.PARAMETER, "parámetro"
        else:
            storage, role = StorageKind.LOCAL, "local"
        slot = record.allocate(symbol.name, role, size_of(runtime_type), runtime_type, symbol)
        symbol.storage = storage
        symbol.offset = slot.offset
        symbol.size = slot.size
        symbol.runtime_type = runtime_type
        symbol.owner = record.name

    def _runtime_type(self, symbol: Symbol) -> str | None:
        inferred = self._symbol_types.get(id(symbol))
        kind = getattr(getattr(inferred, "kind", None), "name", None)
        if inferred is not None and kind not in ("UNKNOWN", "ERROR", "NULL", "VOID"):
            return str(inferred)
        return symbol.type_name

    # -- funciones 
    def _unique_label(self, name: str) -> str:
        # Igual que con las variables: «$» no aparece en Compiscript, y los
        # nombres t<n>/L<n> quedan para temporales y etiquetas.
        label, suffix = name, 1
        if _RESERVED_NAME.match(label):
            label = f"{name}${suffix}"
            suffix += 1
        while label in self._labels:
            label = f"{name}${suffix}"
            suffix += 1
        self._labels.add(label)
        return label

    def _new_record(self, label: str, kind: str, level: int, parent: str | None, this_type: str | None) -> ActivationRecord:
        record = ActivationRecord(name=label, kind=kind, level=level, parent=parent)
        for role in _HEADER:
            record.allocate(role, role, WORD_SIZE)
        if this_type is not None:
            record.allocate("this", "this", WORD_SIZE, this_type)
        self.table.activation_records.append(record)
        return record

    def _function(
        self,
        symbol: Symbol,
        scope: Scope,
        parent: ActivationRecord,
        level: int,
        owner_class: Symbol | None = None,
    ) -> None:
        if symbol.activation_record is not None:
            return  # declaración duplicada: ya se procesó la primera
        if owner_class is None:
            label, kind, this_type = self._unique_label(symbol.name), "función", None
        else:
            label = self._unique_label(method_label(owner_class.name, symbol.name))
            kind = "constructor" if symbol.name == "constructor" else "método"
            this_type = owner_class.name
        record = self._new_record(label, kind, level, parent.name, this_type)
        symbol.tac_label = label
        symbol.activation_record = record
        symbol.owner = parent.name
        self._walk(scope, record, level)

    # -- clases 
    def _class(self, symbol: Symbol) -> ClassLayout | None:
        existing = self.table.class_layouts.get(symbol.name)
        if existing is not None:
            return existing
        if symbol.name in self._classes_in_progress:
            return None  # herencia circular: el análisis semántico ya la reportó
        self._classes_in_progress.add(symbol.name)
        try:
            return self._build_class(symbol)
        finally:
            self._classes_in_progress.discard(symbol.name)

    def _build_class(self, symbol: Symbol) -> ClassLayout:
        parent_layout = None
        if symbol.superclass:
            parent_symbol = self.table.find_class(symbol.superclass)
            if parent_symbol is not None:
                parent_layout = self._class(parent_symbol)

        layout = ClassLayout(name=symbol.name, superclass=symbol.superclass)
        if parent_layout is None:
            layout.allocate("vtable", "puntero a vtable", WORD_SIZE)
        else:
            layout.slots = list(parent_layout.slots)
            layout.data_size = parent_layout.data_size
            layout.vtable = list(parent_layout.vtable)

        for attribute in symbol.attributes.values():
            runtime_type = self._runtime_type(attribute)
            inherited = layout.field_offset(attribute.name)
            if inherited is None:
                slot = layout.allocate(attribute.name, "atributo", size_of(runtime_type), runtime_type, attribute)
                offset, size = slot.offset, slot.size
            else:
                offset, size = inherited, size_of(runtime_type)
            attribute.storage = StorageKind.FIELD
            attribute.offset = offset
            attribute.size = size
            attribute.runtime_type = runtime_type
            attribute.owner = symbol.name

        for name in symbol.methods:
            if name == "constructor":
                continue  # el constructor no se hereda por despacho dinámico
            entry = (name, method_label(symbol.name, name))
            index = layout.method_index(name)
            if index is None:
                layout.vtable.append(entry)
            else:
                layout.vtable[index] = entry

        symbol.class_layout = layout
        self.table.class_layouts[symbol.name] = layout

        global_record = self.table.global_record
        if global_record is None:
            return layout
        # Atributos con valor inicial: se asignan en «Clase.$init», que
        # «new» invoca antes del constructor.
        if any(attribute.initialized for attribute in symbol.attributes.values()):
            label = self._unique_label(method_label(symbol.name, INIT_SUFFIX))
            layout.init_record = self._new_record(label, "inicializador", 1, global_record.name, symbol.name)
        scope = self._class_scopes.get(symbol.name)
        if scope is not None:
            for child in scope.children:
                method = scope.resolve_local(child.name)
                if child.kind is ScopeKind.FUNCTION and method is not None:
                    self._function(method, child, parent=global_record, level=1, owner_class=symbol)
        return layout


def assign_memory_layout(table: SymbolTable, symbol_types: dict[int, Any] | None = None) -> SymbolTable:
    """Completa la tabla con direcciones y registros de activación.

    ``symbol_types`` es el mapa ``id(Symbol) -> Type`` que infiere el
    analizador semántico (opcional: sin él se usa el tipo declarado)."""
    return MemoryLayoutBuilder(table, symbol_types).build()
