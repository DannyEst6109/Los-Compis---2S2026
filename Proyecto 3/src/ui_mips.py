"""Pestañas del IDE para el Proyecto 3: ensamblador MIPS y ejecución en MARS.

``CompiscriptApp`` (``ui.py``) hereda de ``MipsPanelsMixin``. Aquí está todo
lo nuevo de la interfaz:

* **MIPS**: el ensamblador generado con resaltado, cuántas instrucciones
  quitó la optimización por mirilla (y cuáles reglas se aplicaron), la
  opción de verlo sin optimizar, **Copiar** y **Guardar .asm**.
* **Ejecución**: ejecuta el programa en MARS (``F6``) en segundo plano y
  muestra lo que imprimió y el árbol de activación de esa ejecución. No es
  obligatorio (el ``.asm`` se puede abrir en MARS a mano), pero sirve para
  validar el programa sin salir del IDE.
"""

from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from activation_tree import build_activation_tree, render_activation_tree, strip_trace
from compiler import CompilationResult, compile_source
from mars_runner import mars_available, mars_jar, run_mars, unavailable_reason


class MipsPanelsMixin:
    MIPS_FONT = ("Cascadia Mono", 10)

    def _init_mips_state(self) -> None:
        self.last_source: str | None = None
        self.show_raw_mips = tk.BooleanVar(value=False)
        self._run_queue: queue.Queue = queue.Queue()
        self._running = False

    # -- construcción -----------------------------------------------------------
    def _text_area(self, parent: tk.Widget, height: int | None = None) -> tk.Text:
        shell = tk.Frame(parent, bg=self.RULE, bd=0, padx=1, pady=1)
        shell.pack(fill="both", expand=True)
        scroll_y = ttk.Scrollbar(shell, orient="vertical")
        scroll_x = ttk.Scrollbar(shell, orient="horizontal")
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        options = {"height": height} if height else {}
        text = tk.Text(
            shell, wrap="none", padx=14, pady=12, bd=0, relief="flat",
            background=self.SURFACE, foreground=self.INK, selectbackground="#CBD9F0",
            selectforeground=self.INK, font=self.MIPS_FONT, spacing1=1, spacing3=1,
            yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set, state="disabled", **options,
        )
        text.pack(side="left", fill="both", expand=True)
        scroll_y.configure(command=text.yview)
        scroll_x.configure(command=text.xview)
        text.shell = shell  # para colocar mensajes de estado vacío encima
        return text

    def _empty_label(self, text_widget: tk.Text, message: str) -> tk.Label:
        label = tk.Label(
            text_widget.shell, text=message, bg=self.SURFACE, fg=self.MUTED,
            font=("Segoe UI Semibold", 11), justify="center",
        )
        label.place(relx=0.5, rely=0.45, anchor="center")
        return label

    def _build_mips_tab(self, tab: ttk.Frame) -> None:
        head = ttk.Frame(tab, style="Surface.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Ensamblador MIPS (MARS)", style="Section.TLabel").pack(side="left")
        self.mips_summary_label = tk.Label(
            head, text="SIN GENERAR", bg=self.SOFT, fg=self.MUTED,
            font=("Segoe UI Semibold", 8), padx=9, pady=5,
        )
        self.mips_summary_label.pack(side="right")

        self.mips_detail_label = ttk.Label(
            tab, text="Compile el archivo (F5) para generar el ensamblador.", style="Meta.TLabel"
        )
        self.mips_detail_label.pack(anchor="w", pady=(4, 0))
        toolbar = ttk.Frame(tab, style="Surface.TFrame")
        toolbar.pack(fill="x", pady=(6, 8))
        self.mips_save_button = ttk.Button(
            toolbar, text="Guardar .asm", style="Secondary.TButton", command=self.save_mips
        )
        self.mips_save_button.pack(side="right")
        self.mips_copy_button = ttk.Button(
            toolbar, text="Copiar", style="Secondary.TButton", command=self.copy_mips
        )
        self.mips_copy_button.pack(side="right", padx=(0, 6))
        self.mips_raw_check = ttk.Checkbutton(
            toolbar, text="Ver sin optimizar (antes de la mirilla)", style="Surface.TCheckbutton",
            variable=self.show_raw_mips, command=self._refresh_mips_text,
        )
        self.mips_raw_check.pack(side="left")

        self.peephole_label = ttk.Label(tab, text="", style="Meta.TLabel", wraplength=520, justify="left")
        self.peephole_label.pack(side="bottom", anchor="w", pady=(8, 0))
        tab.bind("<Configure>", lambda event: self.peephole_label.configure(wraplength=max(event.width - 20, 260)))

        self.mips_text = self._text_area(tab)
        self.mips_text.tag_configure("mips_comment", foreground="#6A7368")
        self.mips_text.tag_configure("mips_label", foreground=self.BLUE, font=(*self.MIPS_FONT, "bold"))
        self.mips_text.tag_configure("mips_function", foreground=self.VIOLET, font=(*self.MIPS_FONT, "bold"))
        self.mips_text.tag_configure("mips_directive", foreground=self.VIOLET)
        self.mips_text.tag_configure("mips_op", foreground=self.BLUE)
        self.mips_text.tag_configure("mips_register", foreground="#8A4D14")
        self.mips_text.tag_configure("mips_tac", foreground=self.GREEN)
        self.mips_empty_message = self._empty_label(
            self.mips_text, "El ensamblador aparecerá aquí después de compilar."
        )

    def _build_run_tab(self, tab: ttk.Frame) -> None:
        head = ttk.Frame(tab, style="Surface.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Ejecución en el simulador MARS", style="Section.TLabel").pack(side="left")
        self.run_summary_label = tk.Label(
            head, text="SIN EJECUTAR", bg=self.SOFT, fg=self.MUTED,
            font=("Segoe UI Semibold", 8), padx=9, pady=5,
        )
        self.run_summary_label.pack(side="right")

        self.run_detail_label = ttk.Label(tab, text=self._mars_description(), style="Meta.TLabel")
        self.run_detail_label.pack(anchor="w", pady=(4, 0))
        toolbar = ttk.Frame(tab, style="Surface.TFrame")
        toolbar.pack(fill="x", pady=(6, 8))
        self.run_button = ttk.Button(
            toolbar, text="Ejecutar en MARS  F6", style="Primary.TButton", command=self.run_in_mars
        )
        self.run_button.pack(side="left")
        ttk.Label(
            toolbar, text="Se ejecuta el ensamblador de la pestaña «MIPS», con traza para el árbol.",
            style="Meta.TLabel",
        ).pack(side="left", padx=(10, 0))

        sections = ttk.Panedwindow(tab, orient="vertical")
        sections.pack(fill="both", expand=True)
        output_frame = ttk.Frame(sections, style="Surface.TFrame")
        tree_frame = ttk.Frame(sections, style="Surface.TFrame")
        sections.add(output_frame, weight=1)
        sections.add(tree_frame, weight=1)
        ttk.Label(output_frame, text="Salida del programa", style="Meta.TLabel").pack(anchor="w", pady=(0, 4))
        self.run_output_text = self._text_area(output_frame, height=8)
        self.run_output_text.tag_configure("run_error", foreground=self.RED)
        ttk.Label(tree_frame, text="Árbol de activación de esta ejecución", style="Meta.TLabel").pack(
            anchor="w", pady=(8, 4)
        )
        self.run_tree_text = self._text_area(tree_frame, height=8)
        self.run_tree_text.tag_configure("tree_unwound", foreground=self.RED)
        self.run_empty_message = self._empty_label(
            self.run_output_text, "Compile (F5) y luego ejecute (F6)\npara ver la salida del programa."
        )

    @staticmethod
    def _mars_description() -> str:
        if not mars_available():
            return unavailable_reason()
        return f"Simulador: {mars_jar().name} · saltos retardados desactivados"

    # -- pestaña MIPS ----------------------------------------------------------
    def _set_text(self, widget: tk.Text, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _clear_mips(self) -> None:
        self._set_text(self.mips_text, "")
        self.mips_save_button.state(["disabled"])
        self.mips_copy_button.state(["disabled"])
        self.mips_raw_check.state(["disabled"])
        self._set_badge(self.mips_summary_label, "SIN GENERAR")
        self.mips_detail_label.configure(text="Compile el archivo (F5) para generar el ensamblador.")
        self.peephole_label.configure(text="")
        self.mips_empty_message.configure(
            text="El ensamblador aparecerá aquí después de compilar.", fg=self.MUTED
        )
        self.mips_empty_message.place(relx=0.5, rely=0.45, anchor="center")

    def _show_mips(self, compilation: CompilationResult | None) -> None:
        self._clear_mips()
        self._clear_run()
        if compilation is None:
            return
        mips = compilation.mips
        if mips is None:
            self._set_badge(self.mips_summary_label, "NO GENERADO", "error")
            reason = (
                "No se pudo traducir el TAC a MIPS: vea el error de «Generación» en Diagnósticos."
                if compilation.tac is not None
                else "El programa tiene errores; no se genera TAC ni ensamblador."
            )
            self.mips_detail_label.configure(text=reason)
            self.mips_empty_message.configure(
                text="No se generó código ensamblador.\nRevise la pestaña «Diagnósticos».", fg=self.RED
            )
            return
        self.mips_empty_message.place_forget()
        for button in (self.mips_save_button, self.mips_copy_button, self.mips_raw_check):
            button.state(["!disabled"])
        removed = mips.raw_instruction_count - mips.instruction_count
        self._set_badge(self.mips_summary_label, f"{mips.instruction_count} INSTRUCCIONES", "success")
        stats = mips.stats
        self.mips_detail_label.configure(
            text=(
                f"{stats['funciones']} funciones · {stats['clases']} clases · "
                f"{removed} instrucciones menos por mirilla"
            )
        )
        rules = " · ".join(f"{rule} ({amount})" for rule, amount in mips.peephole.counts.most_common())
        self.peephole_label.configure(
            text=f"Optimización por mirilla: {rules}." if rules else "Optimización por mirilla: sin cambios."
        )
        self._refresh_mips_text()

    def _current_mips_text(self) -> str | None:
        compilation = self.last_compilation
        if compilation is None or compilation.mips is None:
            return None
        return compilation.mips.raw_text if self.show_raw_mips.get() else compilation.mips.text

    def _refresh_mips_text(self) -> None:
        text = self._current_mips_text()
        if text is None:
            return
        self._set_text(self.mips_text, text)
        self._highlight_mips()

    def _highlight_mips(self) -> None:
        widget = self.mips_text
        text = widget.get("1.0", "end-1c")
        patterns = (
            ("mips_register", r"\$\w+"),
            ("mips_directive", r"(?m)^\s*\.\w+|(?<=: )\.\w+"),
            ("mips_op", r"(?m)^ {4}[a-z]+\b"),
            ("mips_label", r"(?m)^[A-Za-z_][\w.$]*:"),
            ("mips_function", r"(?m)^(?:fn_\w+|main):$"),
            ("mips_comment", r"#[^\n]*"),
            ("mips_tac", r"(?m)^ {4}# (?![-á])(?:t\d+ = |if|ifFalse|goto|print|try_|[\w.$]+ = )[^\n]*"),
        )
        widget.configure(state="normal")
        for tag, pattern in patterns:
            for match in re.finditer(pattern, text):
                widget.tag_add(tag, f"1.0+{match.start()}c", f"1.0+{match.end()}c")
        widget.configure(state="disabled")

    def copy_mips(self) -> None:
        text = self._current_mips_text()
        if text is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.configure(text="Ensamblador copiado al portapapeles")

    def save_mips(self) -> None:
        text = self._current_mips_text()
        if text is None:
            return
        initial = f"{self.current_file.stem}.asm" if self.current_file is not None else "programa.asm"
        selected = filedialog.asksaveasfilename(
            title="Guardar ensamblador MIPS", defaultextension=".asm", initialfile=initial,
            filetypes=(("Ensamblador MIPS", "*.asm *.s"), ("Texto", "*.txt")),
        )
        if not selected:
            return
        try:
            Path(selected).write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("No se pudo guardar", f"No fue posible guardar el ensamblador:\n{exc}")
            return
        self.status_label.configure(text=f"Ensamblador guardado en {Path(selected).name} (ábralo en MARS para ejecutarlo)")

    # -- pestaña Ejecución ----------------------------------------------------
    def _clear_run(self) -> None:
        self._set_text(self.run_output_text, "")
        self._set_text(self.run_tree_text, "")
        self._set_badge(self.run_summary_label, "SIN EJECUTAR")
        self.run_detail_label.configure(text=self._mars_description())
        self.run_empty_message.configure(
            text="Compile (F5) y luego ejecute (F6)\npara ver la salida del programa.", fg=self.MUTED
        )
        self.run_empty_message.place(relx=0.5, rely=0.45, anchor="center")
        if not self._running:
            self.run_button.state(["!disabled"] if mars_available() else ["disabled"])

    def run_in_mars(self) -> None:
        if self._running:
            return
        if not mars_available():
            messagebox.showinfo("MARS no disponible", unavailable_reason())
            return
        compilation = self.last_compilation
        if compilation is None or compilation.mips is None or self.last_source is None:
            messagebox.showinfo(
                "Nada que ejecutar", "Compile primero (F5) un programa sin errores para generar el ensamblador."
            )
            return
        self.inspector_tabs.select(self.run_tab)
        self._running = True
        self.run_button.state(["disabled"])
        self._set_badge(self.run_summary_label, "EJECUTANDO…")
        self.run_detail_label.configure(text="MARS está ejecutando el programa…")
        self.status_label.configure(text="Ejecutando en MARS…")
        source, optimized = self.last_source, not self.show_raw_mips.get()
        threading.Thread(target=self._run_worker, args=(source, optimized), daemon=True).start()
        self.root.after(100, self._poll_run)

    def _run_worker(self, source: str, optimized: bool) -> None:
        """En segundo plano: genera la versión con traza (para el árbol de
        activación) y la ejecuta. Nunca toca la interfaz directamente."""
        try:
            traced = compile_source(source, trace=True, optimize=optimized)
            if traced.mips is None:
                raise RuntimeError("No se pudo generar el programa con traza.")
            self._run_queue.put(("ok", run_mars(traced.mips.text)))
        except Exception as error:  # noqa: BLE001 - se informa en la interfaz
            self._run_queue.put(("error", error))

    def _poll_run(self) -> None:
        try:
            kind, payload = self._run_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self._poll_run)
            return
        self._running = False
        self.run_button.state(["!disabled"])
        self.run_empty_message.place_forget()
        if kind == "error":
            self._set_badge(self.run_summary_label, "ERROR", "error")
            self._set_text(self.run_output_text, str(payload))
            self.run_detail_label.configure(text="No se pudo ejecutar MARS.")
            self.status_label.configure(text="No se pudo ejecutar MARS")
            return
        run = payload
        output = strip_trace(run.output + "\n").rstrip("\n")
        problem = run.problem
        self._set_text(self.run_output_text, output + (f"\n\n{problem}" if problem else ""))
        if problem:
            self.run_output_text.configure(state="normal")
            self.run_output_text.tag_add("run_error", f"1.0+{len(output)}c", "end")
            self.run_output_text.configure(state="disabled")
        try:
            tree = build_activation_tree(run.output + "\n", strict=False)
            drawing = render_activation_tree(tree)
            calls = tree.count()
            depth = tree.depth
        except Exception as error:  # noqa: BLE001
            drawing, calls, depth = f"No se pudo construir el árbol: {error}", 0, 0
        self._set_text(self.run_tree_text, drawing)
        self.run_tree_text.configure(state="normal")
        for match in re.finditer(r"[^\n]*\(interrumpida por excepción\)", drawing):
            self.run_tree_text.tag_add("tree_unwound", f"1.0+{match.start()}c", f"1.0+{match.end()}c")
        self.run_tree_text.configure(state="disabled")
        lines = output.count("\n") + 1 if output else 0
        if problem:
            self._set_badge(self.run_summary_label, "CON ERRORES", "error")
        else:
            self._set_badge(self.run_summary_label, "EJECUTADO", "success")
        self.run_detail_label.configure(
            text=f"{lines} líneas de salida · {calls} activaciones · profundidad máxima {depth}"
        )
        self.status_label.configure(text="Ejecución en MARS terminada" + (" con errores" if problem else ""))
