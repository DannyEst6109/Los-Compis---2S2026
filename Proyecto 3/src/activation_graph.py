"""Grafo navegable de las activaciones reales; usa sólo Tkinter.

Conserva la paleta del IDE y separa la disposición de los nodos del dibujo.
Las ramas profundas empiezan plegadas para poder explorar la recursividad.
"""

from dataclasses import dataclass
import tkinter as tk
from tkinter import ttk

from activation_tree import Activation


@dataclass
class GraphNode:
    activation: Activation
    parent: int | None
    depth: int
    x: float = 0


def layout_activations(root: Activation, collapsed: set[int], limit: int = 500):
    """Preorden estable, con padres centrados sobre sus hijos visibles."""
    nodes: list[GraphNode] = []
    pending = [(root, None, 0)]
    children: dict[int, list[int]] = {}
    while pending and len(nodes) < limit:
        activation, parent, depth = pending.pop()
        index = len(nodes)
        nodes.append(GraphNode(activation, parent, depth))
        if parent is not None:
            children.setdefault(parent, []).append(index)
        if id(activation) not in collapsed:
            pending.extend((child, index, depth + 1) for child in reversed(activation.children))
    leaf = 0
    for index in reversed(range(len(nodes))):
        descendants = children.get(index, [])
        if descendants:
            nodes[index].x = (nodes[descendants[0]].x + nodes[descendants[-1]].x) / 2
        else:
            nodes[index].x = leaf
            leaf += 1
    # El postorden anterior recorre las hojas de derecha a izquierda.
    for node in nodes:
        node.x = leaf - 1 - node.x
    return nodes, bool(pending)


class ActivationGraph(ttk.Frame):
    def __init__(self, parent, palette):
        super().__init__(parent, style="Surface.TFrame")
        self.palette = palette
        self.tree = None
        self.collapsed: set[int] = set()
        self.nodes: list[GraphNode] = []
        self.selected = None
        self.zoom = 1.0
        toolbar = ttk.Frame(self, style="Surface.TFrame")
        toolbar.pack(fill="x", pady=(0, 6))
        for text, command in (("Alejar", lambda: self.set_zoom(self.zoom / 1.2)),
                              ("Acercar", lambda: self.set_zoom(self.zoom * 1.2)),
                              ("Ajustar", self.fit)):
            ttk.Button(toolbar, text=text, command=command, style="Secondary.TButton").pack(side="left", padx=(0, 5))
        self.summary = ttk.Label(toolbar, text="", style="Meta.TLabel")
        self.summary.pack(side="right")
        shell = tk.Frame(self, bg=palette.RULE, padx=1, pady=1)
        shell.rowconfigure(0, weight=1)
        shell.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(shell, bg=palette.DETAIL, highlightthickness=0,
                                takefocus=True, width=200, height=180)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(shell, orient="vertical", command=self.canvas.yview)
        horizontal = ttk.Scrollbar(shell, orient="horizontal", command=self.canvas.xview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        self.canvas.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.detail = ttk.Label(self, text="", style="Meta.TLabel", wraplength=480)
        self.detail.pack(side="bottom", fill="x", pady=(5, 0))
        shell.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._resize)
        self.canvas.bind("<ButtonPress-1>", self._pan_start)
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.canvas.bind("<Up>", lambda e: self._navigate(-1))
        self.canvas.bind("<Down>", lambda e: self._navigate(1))
        self.canvas.bind("<Return>", lambda e: self._toggle_selected())
        self.canvas.bind("<space>", lambda e: self._toggle_selected())
        self.clear()

    def _resize(self, event):
        self.detail.configure(wraplength=max(200, event.width - 12))
        if self.tree is None:
            self._draw()

    def clear(self):
        self.tree = None
        self.nodes = []
        self.selected = None
        self.collapsed.clear()
        self.summary.configure(text="Sin ejecución")
        self.detail.configure(text="Ejecute un programa (F6) para ver sus llamadas.")
        self._draw()

    def show_tree(self, tree: Activation):
        self.tree = tree
        self.collapsed.clear()
        pending = [(tree, 0)]
        while pending:
            node, depth = pending.pop()
            if depth >= 3 and node.children:
                self.collapsed.add(id(node))
            else:
                pending.extend((child, depth + 1) for child in node.children)
        self.selected = id(tree)
        self.zoom = 1.0
        self.canvas.xview_moveto(0)
        self.canvas.yview_moveto(0)
        self._draw()
        self.fit()

    @staticmethod
    def _status(node):
        return "Interrumpida por excepción" if node.unwound else "Finalizada" if node.finished else "Sin terminar"

    def _draw(self):
        canvas, p = self.canvas, self.palette
        canvas.delete("all")
        if self.tree is None:
            canvas.create_text(max(canvas.winfo_width(), 250) / 2, max(canvas.winfo_height(), 140) / 2,
                               text="El grafo aparecerá después de ejecutar.\nCada nodo representa una llamada.",
                               fill=p.MUTED, font=("Segoe UI", 10), justify="center", width=300)
            canvas.configure(scrollregion=(0, 0, 0, 0))
            return
        self.nodes, limited = layout_activations(self.tree, self.collapsed)
        z = self.zoom
        width, height, gap, level = 188 * z, 58 * z, 26 * z, 100 * z
        positions = [(24 + node.x * (width + gap), 24 + node.depth * level) for node in self.nodes]
        for index, node in enumerate(self.nodes):
            if node.parent is not None:
                px, py = positions[node.parent]
                x, y = positions[index]
                mid = (py + height + y) / 2
                canvas.create_line(px + width / 2, py + height, px + width / 2, mid,
                                   x + width / 2, mid, x + width / 2, y,
                                   fill=p.MUTED, width=1.2, arrow="last")
        for index, node in enumerate(self.nodes):
            activation = node.activation
            x, y = positions[index]
            tag = f"node_{index}"
            selected = id(activation) == self.selected
            fill = p.RED_PALE if activation.unwound else p.GREEN_PALE if activation.finished else p.SOFT
            color = p.RED if activation.unwound else p.GREEN if activation.finished else p.MUTED
            canvas.create_rectangle(x, y, x + width, y + height, fill=fill,
                                    outline=p.BLUE if selected else p.RULE, width=2 if selected else 1, tags=tag)
            label = activation.label
            label = label if len(label) <= 24 else label[:21] + "…"
            canvas.create_text(x + 10 * z, y + 18 * z, text=label, anchor="w", fill=p.INK,
                               font=("Segoe UI Semibold", max(7, round(10 * z))), tags=tag)
            status = self._status(activation)
            if id(activation) in self.collapsed:
                status = f"{len(activation.children)} llamadas · doble clic para abrir"
            elif activation.children:
                status = f"{len(activation.children)} llamadas · {status.lower()}"
            canvas.create_text(x + 10 * z, y + 39 * z, text=status, anchor="w", fill=color,
                               font=("Segoe UI", max(6, round(8 * z))), width=width - 20 * z, tags=tag)
            canvas.tag_bind(tag, "<Button-1>", lambda e, i=index: self._select(i))
            canvas.tag_bind(tag, "<Double-Button-1>", lambda e, i=index: self._toggle(i))
        canvas.configure(scrollregion=canvas.bbox("all"))
        self.summary.configure(text=f"{len(self.nodes)} nodos visibles" + (" · límite de 500" if limited else ""))
        selected = next((node.activation for node in self.nodes if id(node.activation) == self.selected), self.tree)
        self.detail.configure(text=f"{selected.label} · {self._status(selected)}. Doble clic o Enter: plegar/abrir. Flechas: seleccionar.")

    def _select(self, index):
        self.selected = id(self.nodes[index].activation)
        self.canvas.focus_set()
        self._draw()

    def _toggle(self, index):
        node = self.nodes[index].activation
        if node.children:
            identity = id(node)
            if identity in self.collapsed:
                self.collapsed.remove(identity)
                self.collapsed.update(id(child) for child in node.children if child.children)
            else:
                self.collapsed.add(identity)
            self.selected = identity
            self._draw()

    def _toggle_selected(self):
        for index, node in enumerate(self.nodes):
            if id(node.activation) == self.selected:
                self._toggle(index)
                break
        return "break"

    def _navigate(self, step):
        if self.nodes:
            index = next((i for i, n in enumerate(self.nodes) if id(n.activation) == self.selected), 0)
            self._select(max(0, min(len(self.nodes) - 1, index + step)))
        return "break"

    def _pan_start(self, event):
        self.canvas.scan_mark(event.x, event.y)
        self.canvas.focus_set()

    def set_zoom(self, zoom):
        self.zoom = max(0.5, min(1.75, zoom))
        self._draw()

    def fit(self):
        if self.nodes:
            columns = max(node.x for node in self.nodes) + 1
            depth = max(node.depth for node in self.nodes)
            self.set_zoom(min((self.canvas.winfo_width() - 48) / (214 * columns),
                              (self.canvas.winfo_height() - 48) / (100 * depth + 58)))
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
