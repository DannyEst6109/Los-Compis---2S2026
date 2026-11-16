"""Pestaña Autómata: AFD de una regla, aceptación y recorrido interactivo.

Extiende los colores, tipografía y controles del IDE; no altera la compilación.
"""

import math
import tkinter as tk
from tkinter import ttk

from lexical_automaton import build_automaton, character_label, lexer_description, token_rules


class AutomatonPanel(ttk.Frame):
    def __init__(self, parent, palette):
        super().__init__(parent, style="Surface.TFrame", padding=(2, 4))
        self.palette = palette
        self.rule = tk.StringVar(self, "Identifier")
        self.input = tk.StringVar(self, "contador_1")
        self.position = 0
        self.zoom = 1.0
        self.trace = None
        self.started = False
        header = ttk.Frame(self, style="Surface.TFrame")
        header.pack(fill="x")
        ttk.Label(header, text="Autómata léxico por regla", style="Section.TLabel").pack(side="left")
        self.badge = tk.Label(header, text="LISTO", bg=palette.SOFT, fg=palette.MUTED,
                              font=("Segoe UI Semibold", 8), padx=9, pady=5)
        self.badge.pack(side="right")
        self.note = ttk.Label(self, text="Generado desde la ATN del lexer ANTLR. Doble círculo: estado de aceptación.",
                              style="Meta.TLabel", wraplength=530)
        self.note.pack(fill="x", pady=(4, 10))
        rule_row = ttk.Frame(self, style="Surface.TFrame")
        rule_row.pack(fill="x")
        ttk.Label(rule_row, text="Regla", style="Meta.TLabel").pack(side="left", padx=(0, 8))
        self.rule_picker = ttk.Combobox(rule_row, textvariable=self.rule, values=token_rules(),
                                        state="readonly", width=22, font=("Segoe UI", 10))
        self.rule_picker.pack(side="left")
        self.rule_picker.bind("<<ComboboxSelected>>", self.change_rule)
        self.stats = ttk.Label(rule_row, text="", style="Meta.TLabel")
        self.stats.pack(side="right")
        ttk.Label(self, text="Entrada literal para la regla seleccionada", style="Meta.TLabel").pack(
            anchor="w", pady=(10, 4))
        self.entry = ttk.Entry(self, textvariable=self.input, font=("Cascadia Mono", 11))
        self.entry.pack(fill="x")
        self.entry.bind("<Return>", lambda e: self.evaluate())
        controls = ttk.Frame(self, style="Surface.TFrame")
        controls.pack(fill="x", pady=(8, 8))
        for text, command, style in (("Evaluar", self.evaluate, "Primary.TButton"),
                                     ("Paso", self.step, "Secondary.TButton"),
                                     ("Reiniciar", self.reset, "Secondary.TButton")):
            ttk.Button(controls, text=text, command=command, style=style).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="Ajustar", command=self.fit, style="Secondary.TButton").pack(side="right")
        ttk.Button(controls, text="Alejar", command=lambda: self.set_zoom(self.zoom / 1.2),
                   style="Secondary.TButton").pack(side="right", padx=(0, 6))
        ttk.Button(controls, text="Acercar", command=lambda: self.set_zoom(self.zoom * 1.2),
                   style="Secondary.TButton").pack(side="right", padx=(0, 6))
        self.result = ttk.Label(self, text="", style="Meta.TLabel", wraplength=530)
        self.result.pack(fill="x", pady=(0, 5))
        self.lexer_result = ttk.Label(self, text="", style="Meta.TLabel", wraplength=530)
        self.lexer_result.pack(fill="x", pady=(0, 8))
        footer = ttk.Label(self, text="La aceptación corresponde a esta regla, sin prioridad entre tokens ni corte "
                           "no codicioso. El lexer real aplica ambos. No valida un programa completo.",
                           style="Meta.TLabel", wraplength=530)
        footer.pack(side="bottom", fill="x", pady=(8, 0))
        self.route = ttk.Label(self, text="", style="Meta.TLabel", wraplength=530)
        self.route.pack(side="bottom", fill="x", pady=(6, 0))
        shell = tk.Frame(self, bg=palette.RULE, padx=1, pady=1)
        shell.pack(fill="both", expand=True)
        shell.columnconfigure(0, weight=1)
        shell.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(shell, bg=palette.DETAIL, height=240, width=200,
                                highlightthickness=0, takefocus=True)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        xscroll = ttk.Scrollbar(shell, orient="horizontal", command=self.canvas.xview)
        yscroll = ttk.Scrollbar(shell, orient="vertical", command=self.canvas.yview)
        xscroll.grid(row=1, column=0, sticky="ew")
        yscroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=xscroll.set, yscrollcommand=yscroll.set)
        self.canvas.bind("<ButtonPress-1>", lambda e: self.canvas.scan_mark(e.x, e.y))
        self.canvas.bind("<B1-Motion>", lambda e: self.canvas.scan_dragto(e.x, e.y, gain=1))
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 if e.delta > 0 else 1, "units"))
        self.canvas.bind("<Map>", lambda e: self.fit())
        self.bind("<Configure>", lambda e: self._resize(e, footer))
        self.input.trace_add("write", lambda *_: self.reset())
        self.change_rule()

    def _resize(self, event, footer):
        if event.widget is self:
            width = max(220, event.width - 12)
            for label in (self.note, self.result, self.lexer_result, self.route, footer):
                label.configure(wraplength=width)

    def change_rule(self, _event=None):
        self.automaton = build_automaton(self.rule.get())
        self.stats.configure(text=f"{self.automaton.state_count} estados · {len(self.automaton.edges)} transiciones")
        self.reset()
        if self.canvas.winfo_width() > 1:
            self.fit()

    def reset(self):
        self.position = 0
        self.started = False
        self._update()

    def evaluate(self):
        self.position = len(self.input.get())
        self.started = True
        self._update()

    def step(self):
        if self.trace and self.trace.failed_at is not None:
            return
        self.position = min(self.position + 1, len(self.input.get()))
        self.started = True
        self._update()

    def _update(self):
        text = self.input.get()
        if len(text) > 2000:
            self.palette._set_badge(self.badge, "ENTRADA MUY LARGA", "error")
            self.result.configure(text="Use como máximo 2000 caracteres para explorar un token.")
            self.lexer_result.configure(text="")
            self.trace = self.automaton.trace("")
            self.route.configure(text="q0")
            self.draw()
            return
        self.trace = self.automaton.trace(text[:self.position])
        current = self.trace.states[-1]
        if not self.started:
            badge, kind = "LISTO", "neutral"
            message = "Evaluar recorre toda la entrada; Paso consume un carácter. Las transiciones ausentes rechazan."
        elif self.trace.failed_at is not None:
            badge, kind = "RECHAZADA", "error"
            index = self.trace.failed_at
            message = f"Sin transición desde q{current} para «{character_label(ord(text[index]))}» " \
                      f"en el carácter {index + 1}."
        elif self.position < len(text):
            badge, kind = "EN RECORRIDO", "neutral"
            message = f"Paso {self.position}/{len(text)} · estado q{current}."
        elif self.trace.accepted:
            badge, kind = "ACEPTADA", "success"
            message = f"Entrada completa aceptada por {self.automaton.rule} en q{current}."
        else:
            badge, kind = "RECHAZADA", "error"
            message = f"La entrada terminó en q{current}, que no es un estado de aceptación."
        self.palette._set_badge(self.badge, badge, kind)
        self.result.configure(text=message)
        self.lexer_result.configure(text=lexer_description(text) if self.started else "")
        states = self.trace.states
        route = " → ".join(f"q{state}" for state in states[:20])
        if len(states) > 20:
            route += f" → … → q{states[-1]} ({len(states) - 1} caracteres consumidos)"
        self.route.configure(text=route)
        self.draw()

    def _positions(self):
        count = self.automaton.state_count
        if count == 2:
            return [(120, 160), (410, 160)], (265, 160)
        radius = max(125, count * 24)
        center = radius + 130, radius + 110
        return [(center[0] + radius * math.cos(math.pi + 2 * math.pi * i / count),
                 center[1] + radius * math.sin(math.pi + 2 * math.pi * i / count))
                for i in range(count)], center

    def draw(self):
        canvas, p, z = self.canvas, self.palette, self.zoom
        canvas.delete("all")
        positions, center = self._positions()
        points = [(x * z, y * z) for x, y in positions]
        r = 29 * z
        visited = set(self.trace.states) if self.trace else {0}
        active = set(zip(self.trace.states, self.trace.states[1:])) if self.trace else set()
        labels = []
        pairs = {(e.source, e.target) for e in self.automaton.edges}
        for edge in self.automaton.edges:
            x, y = points[edge.source]
            tx, ty = points[edge.target]
            color = p.BLUE if (edge.source, edge.target) in active else p.MUTED
            width = 2.5 if (edge.source, edge.target) in active else 1.2
            if edge.source == edge.target:
                dx, dy = positions[edge.source][0] - center[0], positions[edge.source][1] - center[1]
                length = math.hypot(dx, dy) or 1
                nx, ny = dx / length, dy / length
                ux, uy = -ny, nx
                coords = [x + nx * r * .7 + ux * r * .7, y + ny * r * .7 + uy * r * .7,
                          x + nx * r * 3 + ux * r, y + ny * r * 3 + uy * r,
                          x + nx * r * 3 - ux * r, y + ny * r * 3 - uy * r,
                          x + nx * r * .7 - ux * r * .7, y + ny * r * .7 - uy * r * .7]
                canvas.create_line(*coords, smooth=True, arrow="last", fill=color, width=width)
                labels.append((x + nx * r * 3.8, y + ny * r * 3.8, edge.label, color))
            else:
                length = math.hypot(tx - x, ty - y)
                nx, ny = (tx - x) / length, (ty - y) / length
                offset = 38 * z if (edge.target, edge.source) in pairs else 0
                mx, my = (x + tx) / 2 - ny * offset, (y + ty) / 2 + nx * offset
                canvas.create_line(x + nx * r, y + ny * r, mx, my, tx - nx * r, ty - ny * r,
                                   smooth=bool(offset), arrow="last", fill=color, width=width)
                labels.append((mx - ny * 17 * z, my + nx * 17 * z, edge.label, color))
        for x, y, text, color in labels:
            item = canvas.create_text(x, y, text=text, fill=color, font=("Segoe UI", max(8, round(10 * z))),
                                      width=170 * z, justify="center")
            box = canvas.bbox(item)
            background = canvas.create_rectangle(box[0] - 3, box[1] - 2, box[2] + 3, box[3] + 2,
                                                   fill=p.DETAIL, outline="")
            canvas.tag_lower(background, item)
        initial_x, initial_y = points[0]
        canvas.create_line(initial_x - 75 * z, initial_y, initial_x - r - 2, initial_y,
                           arrow="last", fill=p.INK, width=1.5)
        for index, (x, y) in enumerate(points):
            current = self.trace and index == self.trace.states[-1]
            failed = current and self.started and (self.trace.failed_at is not None or
                         self.position == len(self.input.get()) and not self.trace.accepted)
            fill = p.RED_PALE if failed else "#DCE6F7" if index in visited else p.SURFACE
            outline = p.RED if failed else p.BLUE if current else p.GREEN if index in self.automaton.accepting else p.INK
            canvas.create_oval(x - r, y - r, x + r, y + r, fill=fill, outline=outline, width=2)
            if index in self.automaton.accepting:
                inset = 5 * z
                canvas.create_oval(x - r + inset, y - r + inset, x + r - inset, y + r - inset,
                                   outline=outline, width=1.5)
            canvas.create_text(x, y, text=f"q{index}", fill=p.INK,
                               font=("Segoe UI Semibold", max(9, round(11 * z))))
        canvas.configure(scrollregion=canvas.bbox("all"))

    def set_zoom(self, zoom):
        self.zoom = min(1.8, max(.45, zoom))
        self.draw()

    def fit(self):
        self.zoom = 1.0
        self.draw()
        box = self.canvas.bbox("all")
        if box:
            self.set_zoom(min((self.canvas.winfo_width() - 32) / max(1, box[2] - box[0]),
                              (self.canvas.winfo_height() - 32) / max(1, box[3] - box[1]), 1.2))
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)
