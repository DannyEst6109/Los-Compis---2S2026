"""
THESIS: Una mesa de corrección convierte la salida técnica del parser en marcas claras sobre el archivo y evita el tablero genérico.
OWN-WORLD: Papel marfil, tinta azul noche, reglas finas, rojo de corrección y verde de aprobación; controles planos y tipografía de trabajo.
STORY: El usuario abre un archivo, conserva el código a la vista, ejecuta el análisis y salta desde cada diagnóstico hasta su origen.
FIRST VIEWPORT: Encabezado compacto, acciones a la derecha, código en el panel principal y resultados en una columna de inspección.
FORM: Prueba editorial anotada, quinta dirección; seed c4822037.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
"""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from analyzer import AnalysisResult, CompiscriptAnalyzer, Diagnostic


class CompiscriptApp:
    PAPER = "#F3F0E7"
    SURFACE = "#FFFEFA"
    INK = "#17243A"
    MUTED = "#566277"
    RULE = "#D7D2C6"
    BLUE = "#315AA6"
    BLUE_HOVER = "#274A89"
    RED = "#B62C46"
    RED_PALE = "#F9E8EC"
    GREEN = "#147554"
    GREEN_PALE = "#E4F3EB"
    AMBER = "#986712"

    KEYWORDS = {
        "let", "var", "const", "function", "class", "print", "if", "else", "while",
        "do", "for", "foreach", "in", "break", "continue", "return", "try", "catch",
        "switch", "case", "default", "new", "this", "null", "true", "false", "boolean",
        "integer", "string",
    }

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.analyzer = CompiscriptAnalyzer()
        self.current_file: Path | None = None
        self.dirty = False
        self.last_result: AnalysisResult | None = None
        self._highlight_job: str | None = None

        self._configure_window()
        self._configure_styles()
        self._build_layout()
        self._bind_shortcuts()
        self._set_empty_state()

    def _configure_window(self) -> None:
        self.root.title("Analizador Compiscript")
        self.root.geometry("1280x780")
        self.root.minsize(1040, 650)
        self.root.configure(bg=self.PAPER)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=self.PAPER)
        style.configure("Surface.TFrame", background=self.SURFACE)
        style.configure("Header.TFrame", background=self.INK)
        style.configure("Title.TLabel", background=self.INK, foreground="#FFFFFF", font=("Segoe UI Semibold", 18))
        style.configure("Subtitle.TLabel", background=self.INK, foreground="#C9D2E1", font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=self.SURFACE, foreground=self.INK, font=("Segoe UI Semibold", 11))
        style.configure("Meta.TLabel", background=self.SURFACE, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=self.PAPER, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Primary.TButton", background=self.BLUE, foreground="#FFFFFF", borderwidth=0, padding=(18, 10), font=("Segoe UI Semibold", 9))
        style.map("Primary.TButton", background=[("active", self.BLUE_HOVER), ("disabled", "#9AA8BE")])
        style.configure("Secondary.TButton", background="#FFFFFF", foreground=self.INK, bordercolor="#BCC4D0", borderwidth=1, padding=(14, 9), font=("Segoe UI Semibold", 9))
        style.map("Secondary.TButton", background=[("active", "#EDF0F5")])
        style.configure("Treeview", background=self.SURFACE, fieldbackground=self.SURFACE, foreground=self.INK, rowheight=32, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#E9E5DA", foreground=self.INK, relief="flat", font=("Segoe UI Semibold", 9), padding=(8, 8))
        style.map("Treeview", background=[("selected", "#DCE6F7")], foreground=[("selected", self.INK)])
        style.configure("TPanedwindow", background=self.PAPER, sashwidth=8)

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(24, 16))
        header.pack(fill="x")

        mark = tk.Canvas(header, width=38, height=38, bg=self.INK, highlightthickness=0)
        mark.pack(side="left", padx=(0, 12))
        mark.create_rectangle(3, 3, 35, 35, outline="#8CAAE0", width=1)
        mark.create_line(10, 12, 28, 12, fill="#FFFFFF", width=2)
        mark.create_line(10, 19, 24, 19, fill="#FFFFFF", width=2)
        mark.create_line(10, 26, 28, 26, fill=self.RED, width=2)

        title_block = ttk.Frame(header, style="Header.TFrame")
        title_block.pack(side="left")
        ttk.Label(title_block, text="Analizador Compiscript", style="Title.TLabel").pack(anchor="w")
        ttk.Label(title_block, text="Análisis léxico y sintáctico con ANTLR", style="Subtitle.TLabel").pack(anchor="w")

        ttk.Button(header, text="Analizar  F5", style="Primary.TButton", command=self.analyze).pack(side="right")
        ttk.Button(header, text="Guardar", style="Secondary.TButton", command=self.save_file).pack(side="right", padx=(0, 8))
        ttk.Button(header, text="Abrir archivo", style="Secondary.TButton", command=self.open_file).pack(side="right", padx=(0, 8))

        body = ttk.Frame(self.root, style="App.TFrame", padding=(18, 18, 18, 10))
        body.pack(fill="both", expand=True)
        panes = ttk.Panedwindow(body, orient="horizontal")
        panes.pack(fill="both", expand=True)

        editor_panel = ttk.Frame(panes, style="Surface.TFrame", padding=(16, 14))
        results_panel = ttk.Frame(panes, style="Surface.TFrame", padding=(16, 14))
        panes.add(editor_panel, weight=1)
        panes.add(results_panel, weight=1)

        self.file_name_label = ttk.Label(editor_panel, text="Ningún archivo abierto", style="Section.TLabel")
        self.file_name_label.pack(anchor="w")
        self.file_path_label = ttk.Label(editor_panel, text="Seleccione un archivo .cps para comenzar", style="Meta.TLabel")
        self.file_path_label.pack(anchor="w", pady=(2, 10))

        editor_shell = tk.Frame(editor_panel, bg=self.RULE, bd=0, padx=1, pady=1)
        editor_shell.pack(fill="both", expand=True)
        editor_scroll_x = ttk.Scrollbar(editor_shell, orient="horizontal")
        editor_scroll_x.pack(side="bottom", fill="x")
        text_row = tk.Frame(editor_shell, bg=self.SURFACE)
        text_row.pack(fill="both", expand=True)

        self.line_numbers = tk.Text(
            text_row, width=5, padx=8, pady=12, bd=0, relief="flat", takefocus=0,
            background="#EAE6DB", foreground="#625F69", font=("Cascadia Mono", 10), state="disabled",
        )
        self.line_numbers.pack(side="left", fill="y")

        scroll = ttk.Scrollbar(text_row, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.editor = tk.Text(
            text_row, undo=True, wrap="none", padx=14, pady=12, bd=0, relief="flat",
            background=self.SURFACE, foreground=self.INK, insertbackground=self.BLUE,
            selectbackground="#CBD9F0", selectforeground=self.INK, font=("Cascadia Mono", 10),
            yscrollcommand=lambda first, last: self._sync_scroll(first, last, scroll),
            xscrollcommand=editor_scroll_x.set,
        )
        self.editor.pack(side="left", fill="both", expand=True)
        scroll.configure(command=self._scroll_both)
        editor_scroll_x.configure(command=self.editor.xview)
        self.editor.bind("<<Modified>>", self._on_text_modified)
        self.editor.bind("<KeyRelease>", lambda _: self._schedule_highlight())
        self._configure_editor_tags()

        result_head = ttk.Frame(results_panel, style="Surface.TFrame")
        result_head.pack(fill="x")
        ttk.Label(result_head, text="Resultado del análisis", style="Section.TLabel").pack(side="left")
        self.summary_label = tk.Label(
            result_head, text="SIN ANALIZAR", bg="#E9E5DA", fg=self.MUTED,
            font=("Segoe UI Semibold", 8), padx=9, pady=5,
        )
        self.summary_label.pack(side="right")

        self.result_detail = ttk.Label(
            results_panel, text="Los diagnósticos aparecerán ordenados por ubicación.", style="Meta.TLabel"
        )
        self.result_detail.pack(anchor="w", pady=(5, 10))

        self.navigation_hint = ttk.Label(
            results_panel,
            text="Seleccione un diagnóstico para ver el detalle; doble clic para ir al código.",
            style="Meta.TLabel",
        )
        self.navigation_hint.pack(anchor="w", pady=(0, 8))

        table_shell = tk.Frame(results_panel, bg=self.RULE, bd=0, padx=1, pady=1)
        table_shell.pack(fill="both", expand=True)
        columns = ("kind", "line", "column", "symbol", "description")
        self.results = ttk.Treeview(table_shell, columns=columns, show="headings", selectmode="browse")
        self.results.heading("kind", text="Tipo")
        self.results.heading("line", text="Línea")
        self.results.heading("column", text="Col.")
        self.results.heading("symbol", text="Símbolo")
        self.results.heading("description", text="Descripción")
        self.results.column("kind", width=74, minwidth=70, stretch=False)
        self.results.column("line", width=46, minwidth=44, anchor="center", stretch=False)
        self.results.column("column", width=42, minwidth=40, anchor="center", stretch=False)
        self.results.column("symbol", width=82, minwidth=72, stretch=False)
        self.results.column("description", width=320, minwidth=240, stretch=True)
        self.results.tag_configure("lexical", foreground=self.RED)
        self.results.tag_configure("syntactic", foreground="#8A4D14")
        results_scroll = ttk.Scrollbar(table_shell, orient="vertical", command=self.results.yview)
        results_scroll.pack(side="right", fill="y")
        self.results.pack(side="left", fill="both", expand=True)
        self.results.configure(yscrollcommand=results_scroll.set)
        self.results.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.results.bind("<Double-1>", self._go_to_selected)
        self.results.bind("<Return>", self._go_to_selected)

        self.empty_message = tk.Label(
            table_shell, text="Abra un archivo Compiscript\ny ejecute el análisis.",
            bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI", 11), justify="center",
        )

        detail_shell = tk.Frame(results_panel, bg=self.RULE, bd=0, padx=1, pady=1)
        detail_shell.pack(fill="x", pady=(10, 0))
        detail_body = tk.Frame(detail_shell, bg="#F7F5EF", padx=12, pady=9)
        detail_body.pack(fill="both")
        self.diagnostic_detail = tk.Label(
            detail_body,
            text="Detalle: seleccione una fila de la tabla.",
            bg="#F7F5EF",
            fg=self.INK,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=480,
        )
        self.diagnostic_detail.pack(fill="x")
        results_panel.bind(
            "<Configure>",
            lambda event: self.diagnostic_detail.configure(wraplength=max(event.width - 60, 260)),
        )

        footer = ttk.Frame(self.root, style="App.TFrame", padding=(20, 0, 20, 10))
        footer.pack(fill="x")
        self.position_label = ttk.Label(footer, text="Línea 1, columna 1", style="Status.TLabel")
        self.position_label.pack(side="left")
        self.status_label = ttk.Label(footer, text="Listo", style="Status.TLabel")
        self.status_label.pack(side="right")
        self.editor.bind("<KeyRelease>", self._update_cursor_position, add="+")
        self.editor.bind("<ButtonRelease-1>", self._update_cursor_position, add="+")

    def _configure_editor_tags(self) -> None:
        self.editor.tag_configure("keyword", foreground=self.BLUE, font=("Cascadia Mono", 10, "bold"))
        self.editor.tag_configure("string", foreground="#8B3D64")
        self.editor.tag_configure("number", foreground="#8A4D14")
        self.editor.tag_configure("comment", foreground="#59694F")
        self.editor.tag_configure("error_line", background=self.RED_PALE)
        self.editor.tag_configure("active_error", background="#F4CFD8")

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _: self.open_file())
        self.root.bind("<Control-s>", lambda _: self.save_file())
        self.root.bind("<F5>", lambda _: self.analyze())

    def _sync_scroll(self, first: str, last: str, scrollbar: ttk.Scrollbar) -> None:
        scrollbar.set(first, last)
        self.line_numbers.yview_moveto(first)

    def _scroll_both(self, *args: str) -> None:
        self.editor.yview(*args)
        self.line_numbers.yview(*args)

    def _on_text_modified(self, _event=None) -> None:
        if not self.editor.edit_modified():
            return
        self.editor.edit_modified(False)
        self.dirty = True
        self._update_file_labels()
        self._refresh_line_numbers()

    def _refresh_line_numbers(self) -> None:
        line_count = int(self.editor.index("end-1c").split(".")[0])
        values = "\n".join(str(number) for number in range(1, line_count + 1))
        self.line_numbers.configure(state="normal")
        self.line_numbers.delete("1.0", "end")
        self.line_numbers.insert("1.0", values)
        self.line_numbers.configure(state="disabled")

    def _schedule_highlight(self) -> None:
        if self._highlight_job:
            self.root.after_cancel(self._highlight_job)
        self._highlight_job = self.root.after(120, self._highlight_source)

    def _highlight_source(self) -> None:
        self._highlight_job = None
        source = self.editor.get("1.0", "end-1c")
        for tag in ("keyword", "string", "number", "comment"):
            self.editor.tag_remove(tag, "1.0", "end")

        patterns = (
            ("comment", r"//[^\n]*|/\*[\s\S]*?\*/"),
            ("string", r'"(?:\\.|[^"\\\n])*"'),
            ("keyword", r"\b(?:" + "|".join(sorted(self.KEYWORDS, key=len, reverse=True)) + r")\b"),
            ("number", r"\b\d+\b"),
        )
        for tag, pattern in patterns:
            for match in re.finditer(pattern, source):
                start = f"1.0+{match.start()}c"
                end = f"1.0+{match.end()}c"
                self.editor.tag_add(tag, start, end)

    def open_file(self) -> None:
        if not self._confirm_discard_changes():
            return
        selected = filedialog.askopenfilename(
            title="Abrir archivo Compiscript",
            filetypes=(("Archivos Compiscript", "*.cps"), ("Todos los archivos", "*.*")),
        )
        if not selected:
            return
        path = Path(selected)
        if path.suffix.lower() != ".cps":
            messagebox.showwarning("Extensión no válida", "Seleccione un archivo con extensión .cps.")
            return
        try:
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            source = path.read_text(encoding="latin-1")
        except OSError as exc:
            messagebox.showerror("No se pudo abrir", f"No fue posible leer el archivo:\n{exc}")
            return
        self._load_source(path, source)

    def _load_source(self, path: Path, source: str) -> None:
        self.current_file = path
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", source)
        self.editor.edit_reset()
        self.editor.edit_modified(False)
        self.dirty = False
        self.last_result = None
        self._update_file_labels()
        self._refresh_line_numbers()
        self._highlight_source()
        self._set_empty_state("Archivo cargado. Presione F5 para analizar.")
        self.status_label.configure(text=f"{len(source.encode('utf-8')):,} bytes")

    def save_file(self) -> bool:
        if self.current_file is None:
            selected = filedialog.asksaveasfilename(
                title="Guardar archivo Compiscript", defaultextension=".cps",
                filetypes=(("Archivos Compiscript", "*.cps"),),
            )
            if not selected:
                return False
            self.current_file = Path(selected)
        try:
            self.current_file.write_text(self.editor.get("1.0", "end-1c"), encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("No se pudo guardar", f"No fue posible guardar el archivo:\n{exc}")
            return False
        self.dirty = False
        self._update_file_labels()
        self.status_label.configure(text="Cambios guardados")
        return True

    def analyze(self) -> None:
        source = self.editor.get("1.0", "end-1c")
        if not source.strip():
            messagebox.showinfo("Archivo vacío", "Abra un archivo .cps o escriba código antes de analizar.")
            return
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            result = self.analyzer.analyze(source)
        finally:
            self.root.configure(cursor="")
        self.last_result = result
        self._show_result(result)

    def _show_result(self, result: AnalysisResult) -> None:
        for item in self.results.get_children():
            self.results.delete(item)
        self.editor.tag_remove("error_line", "1.0", "end")
        self.editor.tag_remove("active_error", "1.0", "end")
        self.empty_message.place_forget()

        if result.is_valid:
            self.summary_label.configure(text="SIN ERRORES", bg=self.GREEN_PALE, fg=self.GREEN)
            self.result_detail.configure(
                text=f"{result.line_count} líneas · {result.token_count} tokens · {result.elapsed_ms:.1f} ms"
            )
            self.empty_message.configure(
                text="El archivo fue analizado correctamente.\nNo se encontraron errores léxicos ni sintácticos.",
                fg=self.GREEN,
            )
            self.empty_message.place(relx=0.5, rely=0.45, anchor="center")
            self.diagnostic_detail.configure(
                text="Detalle: el archivo no contiene diagnósticos.", fg=self.GREEN
            )
            self.status_label.configure(text="Análisis completado sin errores")
            return

        total = len(result.diagnostics)
        self.summary_label.configure(text=f"{total} {'ERROR' if total == 1 else 'ERRORES'}", bg=self.RED_PALE, fg=self.RED)
        self.result_detail.configure(
            text=f"{result.lexical_count} léxicos · {result.syntactic_count} sintácticos · {result.elapsed_ms:.1f} ms"
        )
        for index, diagnostic in enumerate(result.diagnostics):
            tag = "lexical" if diagnostic.kind == "Léxico" else "syntactic"
            self.results.insert(
                "", "end", iid=str(index),
                values=(diagnostic.kind, diagnostic.line, diagnostic.column, diagnostic.symbol, diagnostic.description),
                tags=(tag,),
            )
            self.editor.tag_add("error_line", f"{diagnostic.line}.0", f"{diagnostic.line}.end")
        first = self.results.get_children()[0]
        self.results.selection_set(first)
        self._show_selected_detail()
        self.status_label.configure(text=f"Análisis completado: {total} diagnósticos")

    def _show_selected_detail(self, _event=None) -> None:
        selected = self.results.selection()
        if not selected or self.last_result is None:
            return
        diagnostic = self.last_result.diagnostics[int(selected[0])]
        self.diagnostic_detail.configure(
            text=(
                f"{diagnostic.kind} · línea {diagnostic.line}, columna {diagnostic.column} · "
                f"«{diagnostic.symbol}»: {diagnostic.description}"
            ),
            fg=self.RED if diagnostic.kind == "Léxico" else self.AMBER,
        )

    def _go_to_selected(self, _event=None) -> None:
        selected = self.results.selection()
        if not selected or self.last_result is None:
            return
        diagnostic: Diagnostic = self.last_result.diagnostics[int(selected[0])]
        self.editor.tag_remove("active_error", "1.0", "end")
        start = f"{diagnostic.line}.{max(diagnostic.column - 1, 0)}"
        end = f"{diagnostic.line}.{max(diagnostic.column, 1)}"
        self.editor.tag_add("active_error", start, end)
        self.editor.mark_set("insert", start)
        self.editor.see(start)
        self.editor.focus_set()
        self._update_cursor_position()

    def _set_empty_state(self, message: str | None = None) -> None:
        for item in self.results.get_children():
            self.results.delete(item)
        self.summary_label.configure(text="SIN ANALIZAR", bg="#E9E5DA", fg=self.MUTED)
        self.result_detail.configure(text="Los diagnósticos aparecerán ordenados por ubicación.")
        self.diagnostic_detail.configure(text="Detalle: seleccione una fila de la tabla.", fg=self.INK)
        self.empty_message.configure(
            text=message or "Abra un archivo Compiscript\ny ejecute el análisis.", fg=self.MUTED
        )
        self.empty_message.place(relx=0.5, rely=0.45, anchor="center")

    def _update_file_labels(self) -> None:
        if self.current_file is None:
            self.file_name_label.configure(text="Ningún archivo abierto")
            self.file_path_label.configure(text="Seleccione un archivo .cps para comenzar")
            return
        marker = " •" if self.dirty else ""
        self.file_name_label.configure(text=f"{self.current_file.name}{marker}")
        self.file_path_label.configure(text=f"Carpeta: {self.current_file.parent.name}")

    def _update_cursor_position(self, _event=None) -> None:
        line, column = self.editor.index("insert").split(".")
        self.position_label.configure(text=f"Línea {line}, columna {int(column) + 1}")

    def _confirm_discard_changes(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(
            "Cambios sin guardar", "El archivo tiene cambios sin guardar. ¿Desea guardarlos?"
        )
        if answer is None:
            return False
        if answer:
            return self.save_file()
        return True

    def _on_close(self) -> None:
        if self._confirm_discard_changes():
            self.root.destroy()
