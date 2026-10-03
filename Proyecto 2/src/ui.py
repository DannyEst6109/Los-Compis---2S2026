"""IDE de escritorio para escribir, analizar y compilar archivos Compiscript
a código intermedio (TAC)."""

from __future__ import annotations

import re
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from analyzer import AnalysisResult, CompiscriptAnalyzer, Diagnostic
from ast_visualization import VisualAstNode, build_visual_tree
from compiler import GENERATION_KIND, CompilationResult, compile_source
from symbol_table import (
    ActivationRecord,
    ClassLayout,
    FrameSlot,
    Scope,
    ScopeKind,
    Symbol,
    SymbolCategory,
    SymbolTable,
)
from tac import TACInstruction


class CompiscriptApp:
    PAPER = "#F3F0E7"
    SURFACE = "#FFFEFA"
    INK = "#17243A"
    MUTED = "#4E5B70"
    RULE = "#C9C5BA"
    SOFT = "#ECE9E0"
    DETAIL = "#F7F5EF"
    FOCUS = "#5F86C9"
    BLUE = "#315AA6"
    BLUE_HOVER = "#274A89"
    RED = "#B62C46"
    RED_PALE = "#F9E8EC"
    GREEN = "#147554"
    GREEN_PALE = "#E4F3EB"
    AMBER = "#986712"
    VIOLET = "#6B3FA0"

    KEYWORDS = {
        "let", "var", "const", "function", "class", "print", "if", "else", "while",
        "do", "for", "foreach", "in", "break", "continue", "return", "try", "catch",
        "switch", "case", "default", "new", "this", "null", "true", "false", "boolean",
        "integer", "string",
    }
    TAC_KEYWORDS = (
        "goto", "ifFalse", "if", "call", "param", "return", "new_array", "new", "len", "concat",
        "minus", "not", "method", "print", "try_begin", "try_end", "exception",
    )

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.analyzer = CompiscriptAnalyzer()
        self.current_file: Path | None = None
        self.dirty = False
        self.last_result: AnalysisResult | None = None
        self.last_compilation: CompilationResult | None = None
        self._highlight_job: str | None = None
        self.ast_visual_by_item: dict[str, VisualAstNode] = {}
        self.last_symbol_table: SymbolTable | None = None
        self.last_diagnostics: list[Diagnostic] = []
        self.symbol_by_item: dict[str, Symbol] = {}
        self.scope_by_item: dict[str, Scope] = {}
        self.tac_line_instructions: list[TACInstruction | None] = []
        self.environment_by_item: dict[str, object] = {}

        self._configure_window()
        self._configure_styles()
        self._build_layout()
        self._bind_shortcuts()
        self._set_empty_state()

    def _configure_window(self) -> None:
        self.root.title("Compilador Compiscript")
        self.root.geometry("1320x800")
        self.root.minsize(1040, 650)
        self.root.configure(bg=self.PAPER)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _configure_styles(self) -> None:
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=self.PAPER)
        style.configure("Surface.TFrame", background=self.SURFACE)
        style.configure("Header.TFrame", background=self.INK)
        style.configure("Title.TLabel", background=self.INK, foreground="#FFFFFF", font=("Segoe UI Semibold", 19))
        style.configure("Subtitle.TLabel", background=self.INK, foreground="#D6DEEA", font=("Segoe UI", 9))
        style.configure("Section.TLabel", background=self.SURFACE, foreground=self.INK, font=("Segoe UI Semibold", 12))
        style.configure("Meta.TLabel", background=self.SURFACE, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure("Status.TLabel", background=self.PAPER, foreground=self.MUTED, font=("Segoe UI", 9))
        style.configure(
            "Primary.TButton", background=self.BLUE, foreground="#FFFFFF", borderwidth=1,
            bordercolor=self.BLUE, focuscolor="#AFC6EC", focusthickness=2,
            padding=(17, 10), font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Primary.TButton",
            background=[("active", self.BLUE_HOVER), ("pressed", "#193C74"), ("disabled", "#8F9DB3")],
            bordercolor=[("focus", "#FFFFFF"), ("active", self.BLUE_HOVER)],
        )
        style.configure(
            "Secondary.TButton", background="#FFFFFF", foreground=self.INK,
            bordercolor="#AEB7C5", borderwidth=1, focuscolor=self.FOCUS, focusthickness=2,
            padding=(14, 9), font=("Segoe UI Semibold", 9),
        )
        style.map(
            "Secondary.TButton",
            background=[("active", "#EEF1F5"), ("pressed", "#E1E6ED")],
            bordercolor=[("focus", self.BLUE), ("active", "#8F9BAC")],
        )
        style.configure(
            "Treeview", background=self.SURFACE, fieldbackground=self.SURFACE,
            foreground=self.INK, rowheight=30, borderwidth=0, font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading", background=self.SOFT, foreground=self.INK, relief="flat",
            font=("Segoe UI Semibold", 9), padding=(8, 8),
        )
        style.map(
            "Treeview", background=[("selected", "#DCE6F7")],
            foreground=[("selected", self.INK)],
        )
        style.configure("TPanedwindow", background=self.PAPER, sashwidth=8)
        style.configure("TNotebook", background=self.SURFACE, borderwidth=0, tabmargins=(0, 0, 0, 8))
        style.configure(
            "TNotebook.Tab", background=self.SOFT, foreground=self.MUTED,
            padding=(14, 9), font=("Segoe UI Semibold", 9), borderwidth=0,
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", self.INK), ("active", "#DCE2EC"), ("focus", "#DCE6F7")],
            foreground=[("selected", "#FFFFFF"), ("active", self.INK)],
        )

    def _build_layout(self) -> None:
        header = ttk.Frame(self.root, style="Header.TFrame", padding=(24, 14))
        header.pack(fill="x")

        mark = tk.Canvas(header, width=38, height=38, bg=self.INK, highlightthickness=0)
        mark.pack(side="left", padx=(0, 12))
        mark.create_rectangle(3, 3, 35, 35, outline="#8CAAE0", width=1)
        mark.create_line(10, 12, 28, 12, fill="#FFFFFF", width=2)
        mark.create_line(10, 19, 24, 19, fill="#FFFFFF", width=2)
        mark.create_line(10, 26, 28, 26, fill=self.RED, width=2)

        title_block = ttk.Frame(header, style="Header.TFrame")
        title_block.pack(side="left")
        ttk.Label(title_block, text="Compilador Compiscript", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_block,
            text="Análisis léxico, sintáctico y semántico · código intermedio (TAC) · entornos de ejecución",
            style="Subtitle.TLabel",
        ).pack(anchor="w")

        actions = ttk.Frame(header, style="Header.TFrame")
        actions.pack(side="right")
        self.open_button = ttk.Button(
            actions, text="Abrir  Ctrl+O", style="Secondary.TButton", command=self.open_file, takefocus=True
        )
        self.open_button.grid(row=0, column=0, padx=(0, 8))
        self.save_button = ttk.Button(
            actions, text="Guardar  Ctrl+S", style="Secondary.TButton", command=self.save_file, takefocus=True
        )
        self.save_button.grid(row=0, column=1, padx=(0, 8))
        self.analyze_button = ttk.Button(
            actions, text="Compilar  F5", style="Primary.TButton", command=self.analyze, takefocus=True
        )
        self.analyze_button.grid(row=0, column=2)

        body = ttk.Frame(self.root, style="App.TFrame", padding=(18, 18, 18, 12))
        body.pack(fill="both", expand=True)
        self.panes = ttk.Panedwindow(body, orient="horizontal")
        self.panes.pack(fill="both", expand=True)

        editor_border = tk.Frame(self.panes, bg=self.RULE, bd=0, padx=1, pady=1)
        results_border = tk.Frame(self.panes, bg=self.RULE, bd=0, padx=1, pady=1)
        editor_panel = ttk.Frame(editor_border, style="Surface.TFrame", padding=(16, 14))
        results_panel = ttk.Frame(results_border, style="Surface.TFrame", padding=(16, 14))
        editor_panel.pack(fill="both", expand=True)
        results_panel.pack(fill="both", expand=True)
        self.panes.add(editor_border, weight=3)
        self.panes.add(results_border, weight=2)
        self.root.after_idle(self._set_initial_split)

        self.file_name_label = ttk.Label(editor_panel, text="Ningún archivo abierto", style="Section.TLabel")
        self.file_name_label.pack(anchor="w")
        self.file_path_label = ttk.Label(editor_panel, text="Seleccione un archivo .cps para comenzar", style="Meta.TLabel")
        self.file_path_label.pack(anchor="w", pady=(2, 10))

        self.editor_shell = tk.Frame(editor_panel, bg=self.RULE, bd=0, padx=1, pady=1)
        self.editor_shell.pack(fill="both", expand=True)
        editor_scroll_x = ttk.Scrollbar(self.editor_shell, orient="horizontal")
        editor_scroll_x.pack(side="bottom", fill="x")
        text_row = tk.Frame(self.editor_shell, bg=self.SURFACE)
        text_row.pack(fill="both", expand=True)

        self.line_numbers = tk.Text(
            text_row, width=5, padx=8, pady=12, bd=0, relief="flat", takefocus=0,
            background=self.SOFT, foreground="#5A6170", font=("Cascadia Mono", 10), state="disabled",
        )
        self.line_numbers.pack(side="left", fill="y")

        scroll = ttk.Scrollbar(text_row, orient="vertical")
        scroll.pack(side="right", fill="y")
        self.editor = tk.Text(
            text_row, undo=True, wrap="none", padx=14, pady=12, bd=0, relief="flat",
            background=self.SURFACE, foreground=self.INK, insertbackground=self.BLUE, insertwidth=2,
            selectbackground="#CBD9F0", selectforeground=self.INK, font=("Cascadia Mono", 10),
            spacing1=1, spacing3=1,
            yscrollcommand=lambda first, last: self._sync_scroll(first, last, scroll),
            xscrollcommand=editor_scroll_x.set,
        )
        self.editor.pack(side="left", fill="both", expand=True)
        scroll.configure(command=self._scroll_both)
        editor_scroll_x.configure(command=self.editor.xview)
        self.editor.bind("<<Modified>>", self._on_text_modified)
        self.editor.bind("<KeyRelease>", lambda _: self._schedule_highlight())
        self.editor.bind("<FocusIn>", lambda _: self.editor_shell.configure(bg=self.FOCUS))
        self.editor.bind("<FocusOut>", lambda _: self.editor_shell.configure(bg=self.RULE))
        self._configure_editor_tags()

        self.inspector_tabs = ttk.Notebook(results_panel, takefocus=True)
        self.inspector_tabs.pack(fill="both", expand=True)
        diagnostics_tab = ttk.Frame(self.inspector_tabs, style="Surface.TFrame", padding=(2, 4))
        self.tac_tab = ttk.Frame(self.inspector_tabs, style="Surface.TFrame", padding=(2, 4))
        ast_tab = ttk.Frame(self.inspector_tabs, style="Surface.TFrame", padding=(2, 4))
        symbols_tab = ttk.Frame(self.inspector_tabs, style="Surface.TFrame", padding=(2, 4))
        environments_tab = ttk.Frame(self.inspector_tabs, style="Surface.TFrame", padding=(2, 4))
        self.diagnostics_tab = diagnostics_tab
        self.inspector_tabs.add(diagnostics_tab, text="Diagnósticos")
        self.inspector_tabs.add(self.tac_tab, text="Código intermedio")
        self.inspector_tabs.add(ast_tab, text="AST")
        self.inspector_tabs.add(symbols_tab, text="Símbolos")
        self.inspector_tabs.add(environments_tab, text="Entornos")
        self._build_tac_tab(self.tac_tab)
        self._build_environments_tab(environments_tab)

        result_head = ttk.Frame(diagnostics_tab, style="Surface.TFrame")
        result_head.pack(fill="x")
        ttk.Label(result_head, text="Resultado del análisis", style="Section.TLabel").pack(side="left")
        self.summary_label = tk.Label(
            result_head, text="SIN ANALIZAR", bg=self.SOFT, fg=self.MUTED,
            font=("Segoe UI Semibold", 8), padx=9, pady=5,
        )
        self.summary_label.pack(side="right")

        self.result_detail = ttk.Label(
            diagnostics_tab, text="Los diagnósticos aparecerán ordenados por ubicación.", style="Meta.TLabel"
        )
        self.result_detail.pack(anchor="w", pady=(5, 10))

        self.navigation_hint = ttk.Label(
            diagnostics_tab,
            text="Seleccione un diagnóstico para ver el detalle; doble clic para ir al código.",
            style="Meta.TLabel",
        )
        self.navigation_hint.pack(anchor="w", pady=(0, 8))

        table_shell = tk.Frame(diagnostics_tab, bg=self.RULE, bd=0, padx=1, pady=1)
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
        self.results.tag_configure("semantic", foreground=self.VIOLET)
        self.results.tag_configure("odd", background="#F7F5EF")
        results_scroll = ttk.Scrollbar(table_shell, orient="vertical", command=self.results.yview)
        results_scroll.pack(side="right", fill="y")
        self.results.pack(side="left", fill="both", expand=True)
        self.results.configure(yscrollcommand=results_scroll.set)
        self.results.bind("<<TreeviewSelect>>", self._show_selected_detail)
        self.results.bind("<Double-1>", self._go_to_selected)
        self.results.bind("<Return>", self._go_to_selected)

        self.empty_message = tk.Label(
            table_shell, text="Abra un archivo Compiscript\ny ejecute el análisis.",
            bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI Semibold", 11), justify="center",
        )

        detail_shell = tk.Frame(diagnostics_tab, bg=self.RULE, bd=0, padx=1, pady=1)
        detail_shell.pack(fill="x", pady=(10, 0))
        detail_body = tk.Frame(detail_shell, bg=self.DETAIL, padx=12, pady=9)
        detail_body.pack(fill="both")
        self.diagnostic_detail = tk.Label(
            detail_body,
            text="Detalle: seleccione una fila de la tabla.",
            bg=self.DETAIL,
            fg=self.INK,
            font=("Segoe UI", 9),
            justify="left",
            anchor="w",
            wraplength=480,
        )
        self.diagnostic_detail.pack(fill="x")
        diagnostics_tab.bind(
            "<Configure>",
            lambda event: self.diagnostic_detail.configure(wraplength=max(event.width - 60, 260)),
        )

        ast_head = ttk.Frame(ast_tab, style="Surface.TFrame")
        ast_head.pack(fill="x")
        ttk.Label(ast_head, text="Árbol sintáctico abstracto", style="Section.TLabel").pack(side="left")
        self.ast_summary_label = tk.Label(
            ast_head, text="SIN GENERAR", bg=self.SOFT, fg=self.MUTED,
            font=("Segoe UI Semibold", 8), padx=9, pady=5,
        )
        self.ast_summary_label.pack(side="right")

        ast_toolbar = ttk.Frame(ast_tab, style="Surface.TFrame")
        ast_toolbar.pack(fill="x", pady=(6, 8))
        self.ast_detail_label = ttk.Label(
            ast_toolbar, text="Analice el archivo para construir el AST.", style="Meta.TLabel"
        )
        self.ast_detail_label.pack(side="left")
        ttk.Button(ast_toolbar, text="Contraer", style="Secondary.TButton", command=self._collapse_ast).pack(side="right")
        ttk.Button(ast_toolbar, text="Expandir", style="Secondary.TButton", command=self._expand_ast).pack(side="right", padx=(0, 6))

        ast_shell = tk.Frame(ast_tab, bg=self.RULE, bd=0, padx=1, pady=1)
        ast_shell.pack(fill="both", expand=True)
        ast_columns = ("detail", "location")
        self.ast_tree = ttk.Treeview(ast_shell, columns=ast_columns, show="tree headings", selectmode="browse")
        self.ast_tree.heading("#0", text="Nodo")
        self.ast_tree.heading("detail", text="Detalle")
        self.ast_tree.heading("location", text="Línea:col.")
        self.ast_tree.column("#0", width=210, minwidth=150, stretch=True)
        self.ast_tree.column("detail", width=185, minwidth=120, stretch=True)
        self.ast_tree.column("location", width=72, minwidth=68, anchor="center", stretch=False)
        ast_scroll_y = ttk.Scrollbar(ast_shell, orient="vertical", command=self.ast_tree.yview)
        ast_scroll_x = ttk.Scrollbar(ast_shell, orient="horizontal", command=self.ast_tree.xview)
        ast_scroll_y.pack(side="right", fill="y")
        ast_scroll_x.pack(side="bottom", fill="x")
        self.ast_tree.pack(side="left", fill="both", expand=True)
        self.ast_tree.configure(yscrollcommand=ast_scroll_y.set, xscrollcommand=ast_scroll_x.set)
        self.ast_tree.bind("<<TreeviewSelect>>", self._show_selected_ast_detail)
        self.ast_tree.bind("<Double-1>", self._go_to_selected_ast)
        self.ast_tree.bind("<Return>", self._go_to_selected_ast)

        self.ast_empty_message = tk.Label(
            ast_shell,
            text="El AST aparecerá aquí después del análisis.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI Semibold", 11),
            justify="center",
        )
        self.ast_empty_message.place(relx=0.5, rely=0.45, anchor="center")

        symbols_head = ttk.Frame(symbols_tab, style="Surface.TFrame")
        symbols_head.pack(fill="x")
        ttk.Label(symbols_head, text="Tabla de símbolos", style="Section.TLabel").pack(side="left")
        self.symbols_summary_label = tk.Label(
            symbols_head, text="SIN GENERAR", bg=self.SOFT, fg=self.MUTED,
            font=("Segoe UI Semibold", 8), padx=9, pady=5,
        )
        self.symbols_summary_label.pack(side="right")

        symbols_toolbar = ttk.Frame(symbols_tab, style="Surface.TFrame")
        symbols_toolbar.pack(fill="x", pady=(6, 8))
        self.symbols_detail_label = ttk.Label(
            symbols_toolbar,
            text="Analice el archivo para construir la tabla de símbolos.",
            style="Meta.TLabel",
        )
        self.symbols_detail_label.pack(side="left")
        ttk.Button(
            symbols_toolbar, text="Contraer", style="Secondary.TButton", command=self._collapse_symbols
        ).pack(side="right")
        ttk.Button(
            symbols_toolbar, text="Expandir", style="Secondary.TButton", command=self._expand_symbols
        ).pack(side="right", padx=(0, 6))

        symbols_shell = tk.Frame(symbols_tab, bg=self.RULE, bd=0, padx=1, pady=1)
        symbols_shell.pack(fill="both", expand=True)
        symbols_columns = ("category", "type", "initialized", "address", "size")
        self.symbols_tree = ttk.Treeview(
            symbols_shell, columns=symbols_columns, show="tree headings", selectmode="browse"
        )
        self.symbols_tree.heading("#0", text="Ámbito / símbolo")
        self.symbols_tree.heading("category", text="Categoría")
        self.symbols_tree.heading("type", text="Tipo")
        self.symbols_tree.heading("initialized", text="Inic.")
        self.symbols_tree.heading("address", text="Dirección")
        self.symbols_tree.heading("size", text="Bytes")
        self.symbols_tree.column("#0", width=190, minwidth=150, stretch=True)
        self.symbols_tree.column("category", width=84, minwidth=76, stretch=False)
        self.symbols_tree.column("type", width=96, minwidth=80, stretch=True)
        self.symbols_tree.column("initialized", width=44, minwidth=40, anchor="center", stretch=False)
        self.symbols_tree.column("address", width=82, minwidth=72, anchor="center", stretch=False)
        self.symbols_tree.column("size", width=48, minwidth=44, anchor="center", stretch=False)
        self.symbols_tree.tag_configure("scope", foreground=self.MUTED, font=("Segoe UI Semibold", 9))
        symbols_scroll_y = ttk.Scrollbar(symbols_shell, orient="vertical", command=self.symbols_tree.yview)
        symbols_scroll_x = ttk.Scrollbar(symbols_shell, orient="horizontal", command=self.symbols_tree.xview)
        symbols_scroll_y.pack(side="right", fill="y")
        symbols_scroll_x.pack(side="bottom", fill="x")
        self.symbols_tree.pack(side="left", fill="both", expand=True)
        self.symbols_tree.configure(yscrollcommand=symbols_scroll_y.set, xscrollcommand=symbols_scroll_x.set)
        self.symbols_tree.bind("<<TreeviewSelect>>", self._show_selected_symbol_detail)
        self.symbols_tree.bind("<Double-1>", self._go_to_selected_symbol)
        self.symbols_tree.bind("<Return>", self._go_to_selected_symbol)

        self.symbols_empty_message = tk.Label(
            symbols_shell,
            text="La tabla de símbolos aparecerá aquí después del análisis.",
            bg=self.SURFACE,
            fg=self.MUTED,
            font=("Segoe UI Semibold", 11),
            justify="center",
        )
        self.symbols_empty_message.place(relx=0.5, rely=0.45, anchor="center")

        ttk.Separator(self.root, orient="horizontal").pack(fill="x", padx=18)
        footer = ttk.Frame(self.root, style="App.TFrame", padding=(20, 8, 20, 10))
        footer.pack(fill="x")
        self.position_label = ttk.Label(footer, text="Línea 1, columna 1", style="Status.TLabel")
        self.position_label.pack(side="left")
        self.status_label = ttk.Label(footer, text="Listo", style="Status.TLabel")
        self.status_label.pack(side="right")
        self.editor.bind("<KeyRelease>", self._update_cursor_position, add="+")
        self.editor.bind("<ButtonRelease-1>", self._update_cursor_position, add="+")

    def _build_tac_tab(self, tab: ttk.Frame) -> None:
        head = ttk.Frame(tab, style="Surface.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Código intermedio (TAC)", style="Section.TLabel").pack(side="left")
        self.tac_summary_label = tk.Label(
            head, text="SIN GENERAR", bg=self.SOFT, fg=self.MUTED,
            font=("Segoe UI Semibold", 8), padx=9, pady=5,
        )
        self.tac_summary_label.pack(side="right")

        # Los botones se empaquetan antes que el texto para que nunca se
        # compriman cuando el panel es angosto.
        toolbar = ttk.Frame(tab, style="Surface.TFrame")
        toolbar.pack(fill="x", pady=(6, 8))
        self.tac_save_button = ttk.Button(
            toolbar, text="Guardar .tac", style="Secondary.TButton", command=self.save_tac
        )
        self.tac_save_button.pack(side="right")
        self.tac_copy_button = ttk.Button(
            toolbar, text="Copiar", style="Secondary.TButton", command=self.copy_tac
        )
        self.tac_copy_button.pack(side="right", padx=(0, 6))
        self.tac_detail_label = ttk.Label(
            toolbar, text="Compile el archivo (F5) para generar el TAC.", style="Meta.TLabel"
        )
        self.tac_detail_label.pack(side="left")
        ttk.Label(
            tab, text="Clic en una instrucción para resaltar la línea de código que la originó.",
            style="Meta.TLabel",
        ).pack(side="bottom", anchor="w", pady=(8, 0))

        shell = tk.Frame(tab, bg=self.RULE, bd=0, padx=1, pady=1)
        shell.pack(fill="both", expand=True)
        scroll_y = ttk.Scrollbar(shell, orient="vertical")
        scroll_x = ttk.Scrollbar(shell, orient="horizontal")
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        self.tac_text = tk.Text(
            shell, wrap="none", padx=14, pady=12, bd=0, relief="flat", cursor="arrow",
            background=self.SURFACE, foreground=self.INK, selectbackground="#CBD9F0",
            selectforeground=self.INK, font=("Cascadia Mono", 10), spacing1=1, spacing3=1,
            yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set, state="disabled",
        )
        self.tac_text.pack(side="left", fill="both", expand=True)
        scroll_y.configure(command=self.tac_text.yview)
        scroll_x.configure(command=self.tac_text.xview)
        self.tac_text.tag_configure("tac_label", foreground=self.BLUE, font=("Cascadia Mono", 10, "bold"))
        self.tac_text.tag_configure("tac_function", foreground=self.VIOLET, font=("Cascadia Mono", 10, "bold"))
        self.tac_text.tag_configure("tac_keyword", foreground=self.BLUE)
        self.tac_text.tag_configure("tac_temp", foreground="#8A4D14")
        self.tac_text.tag_configure("tac_string", foreground="#8B3D64")
        self.tac_text.tag_configure("tac_current", background="#DCE6F7")
        self.tac_text.bind("<ButtonRelease-1>", self._go_to_tac_source)

        self.tac_empty_message = tk.Label(
            shell, text="El código intermedio aparecerá aquí después de compilar.",
            bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI Semibold", 11), justify="center",
        )
        self.tac_empty_message.place(relx=0.5, rely=0.45, anchor="center")

    def _build_environments_tab(self, tab: ttk.Frame) -> None:
        head = ttk.Frame(tab, style="Surface.TFrame")
        head.pack(fill="x")
        ttk.Label(head, text="Registros de activación y objetos", style="Section.TLabel").pack(side="left")
        self.environments_summary_label = tk.Label(
            head, text="SIN GENERAR", bg=self.SOFT, fg=self.MUTED,
            font=("Segoe UI Semibold", 8), padx=9, pady=5,
        )
        self.environments_summary_label.pack(side="right")

        toolbar = ttk.Frame(tab, style="Surface.TFrame")
        toolbar.pack(fill="x", pady=(6, 8))
        ttk.Button(
            toolbar, text="Contraer", style="Secondary.TButton", command=self._collapse_environments
        ).pack(side="right")
        ttk.Button(
            toolbar, text="Expandir", style="Secondary.TButton", command=self._expand_environments
        ).pack(side="right", padx=(0, 6))
        self.environments_detail_label = ttk.Label(
            toolbar, text="Compile el archivo para calcular los entornos.", style="Meta.TLabel"
        )
        self.environments_detail_label.pack(side="left")

        shell = tk.Frame(tab, bg=self.RULE, bd=0, padx=1, pady=1)
        shell.pack(fill="both", expand=True)
        self.environments_tree = ttk.Treeview(
            shell, columns=("offset", "size", "detail"), show="tree headings", selectmode="browse"
        )
        self.environments_tree.heading("#0", text="Registro / casilla")
        self.environments_tree.heading("offset", text="Despl.")
        self.environments_tree.heading("size", text="Bytes")
        self.environments_tree.heading("detail", text="Detalle")
        self.environments_tree.column("#0", width=190, minwidth=150, stretch=True)
        self.environments_tree.column("offset", width=60, minwidth=54, anchor="center", stretch=False)
        self.environments_tree.column("size", width=52, minwidth=48, anchor="center", stretch=False)
        self.environments_tree.column("detail", width=220, minwidth=150, stretch=True)
        self.environments_tree.tag_configure("scope", foreground=self.MUTED, font=("Segoe UI Semibold", 9))
        self.environments_tree.tag_configure("temporary", foreground="#8A4D14")
        self.environments_tree.tag_configure("header", foreground=self.MUTED)
        scroll_y = ttk.Scrollbar(shell, orient="vertical", command=self.environments_tree.yview)
        scroll_x = ttk.Scrollbar(shell, orient="horizontal", command=self.environments_tree.xview)
        scroll_y.pack(side="right", fill="y")
        scroll_x.pack(side="bottom", fill="x")
        self.environments_tree.pack(side="left", fill="both", expand=True)
        self.environments_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)
        self.environments_tree.bind("<<TreeviewSelect>>", self._show_selected_environment_detail)
        self.environments_tree.bind("<Double-1>", self._go_to_selected_environment)
        self.environments_tree.bind("<Return>", self._go_to_selected_environment)

        self.environments_empty_message = tk.Label(
            shell, text="Los registros de activación aparecerán aquí después de compilar.",
            bg=self.SURFACE, fg=self.MUTED, font=("Segoe UI Semibold", 11), justify="center",
        )
        self.environments_empty_message.place(relx=0.5, rely=0.45, anchor="center")

    def _set_initial_split(self) -> None:
        width = self.panes.winfo_width()
        if width > 1:
            self.panes.sashpos(0, int(width * 0.52))

    def _configure_editor_tags(self) -> None:
        self.editor.tag_configure("keyword", foreground=self.BLUE, font=("Cascadia Mono", 10, "bold"))
        self.editor.tag_configure("string", foreground="#8B3D64")
        self.editor.tag_configure("number", foreground="#8A4D14")
        self.editor.tag_configure("comment", foreground="#59694F")
        self.editor.tag_configure("error_line", background=self.RED_PALE)
        self.editor.tag_configure("active_error", background="#F4CFD8")
        self.editor.tag_configure("tac_source", background="#DCE6F7")

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-o>", lambda _: self.open_file())
        self.root.bind("<Control-s>", lambda _: self.save_file())
        self.root.bind("<F5>", lambda _: self.analyze())
        self.root.bind("<Escape>", lambda _: self.editor.focus_set())

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
        self.last_compilation = None
        self.last_symbol_table = None
        self.last_diagnostics = []
        self._update_file_labels()
        self._refresh_line_numbers()
        self._highlight_source()
        self._set_empty_state("Archivo cargado. Presione F5 para compilar.")
        self.status_label.configure(text=f"{len(source.encode('utf-8')):,} bytes")
        self.editor.focus_set()

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
        self.analyze_button.state(["disabled"])
        self.status_label.configure(text="Compilando…")
        self.root.configure(cursor="watch")
        self.root.update_idletasks()
        try:
            compilation = compile_source(source, self.analyzer)
        finally:
            self.root.configure(cursor="")
            self.analyze_button.state(["!disabled"])
        self.last_compilation = compilation
        self.last_result = compilation.analysis
        self.last_symbol_table = compilation.symbol_table
        self.last_diagnostics = compilation.diagnostics
        self._show_result(compilation.analysis)

    def _show_result(self, result: AnalysisResult) -> None:
        for item in self.results.get_children():
            self.results.delete(item)
        self.editor.tag_remove("error_line", "1.0", "end")
        self.editor.tag_remove("active_error", "1.0", "end")
        self.editor.tag_remove("tac_source", "1.0", "end")
        self.empty_message.place_forget()
        self._show_ast(result)
        self._show_symbol_table(result, self.last_symbol_table)
        self._show_tac(self.last_compilation)
        self._show_environments(self.last_compilation)

        diagnostics = self.last_diagnostics
        semantic_count = sum(1 for item in diagnostics if item.kind == "Semántico")

        if not diagnostics:
            tac = self.last_compilation.tac if self.last_compilation is not None else None
            instructions = len(tac) if tac is not None else 0
            self._set_badge(self.summary_label, "SIN ERRORES", "success")
            self.result_detail.configure(
                text=(
                    f"{result.line_count} líneas · {result.token_count} tokens · "
                    f"{instructions} instrucciones TAC · {result.elapsed_ms:.1f} ms"
                )
            )
            self.empty_message.configure(
                text=(
                    "El archivo fue compilado correctamente.\nNo se encontraron errores léxicos, "
                    "sintácticos ni semánticos.\nEl código intermedio está en la pestaña «Código intermedio»."
                ),
                fg=self.GREEN,
            )
            self.empty_message.place(relx=0.5, rely=0.45, anchor="center")
            self.diagnostic_detail.configure(
                text="Detalle: el archivo no contiene diagnósticos.", fg=self.GREEN
            )
            self.status_label.configure(text=f"Compilación exitosa: {instructions} instrucciones TAC")
            self.inspector_tabs.select(self.tac_tab)
            return

        total = len(diagnostics)
        self._set_badge(
            self.summary_label,
            f"{total} {'ERROR' if total == 1 else 'ERRORES'}",
            "error",
        )
        generation_count = sum(1 for item in diagnostics if item.kind == GENERATION_KIND)
        generation_text = f" · {generation_count} de generación" if generation_count else ""
        self.result_detail.configure(
            text=(
                f"{result.lexical_count} léxicos · {result.syntactic_count} sintácticos · "
                f"{semantic_count} semánticos{generation_text} · {result.elapsed_ms:.1f} ms"
            )
        )
        self.inspector_tabs.select(self.diagnostics_tab)
        for index, diagnostic in enumerate(diagnostics):
            tag = self._diagnostic_tag(diagnostic.kind)
            tags = (tag, "odd") if index % 2 else (tag,)
            self.results.insert(
                "", "end", iid=str(index),
                values=(diagnostic.kind, diagnostic.line, diagnostic.column, diagnostic.symbol, diagnostic.description),
                tags=tags,
            )
            self.editor.tag_add("error_line", f"{diagnostic.line}.0", f"{diagnostic.line}.end")
        first = self.results.get_children()[0]
        self.results.selection_set(first)
        self._show_selected_detail()
        self.status_label.configure(text=f"Compilación detenida: {total} diagnósticos, no se generó TAC")

    @staticmethod
    def _diagnostic_tag(kind: str) -> str:
        return {"Léxico": "lexical", "Sintáctico": "syntactic", GENERATION_KIND: "lexical"}.get(kind, "semantic")

    def _diagnostic_color(self, kind: str) -> str:
        return {"Léxico": self.RED, "Sintáctico": self.AMBER, GENERATION_KIND: self.RED}.get(kind, self.VIOLET)

    def _set_badge(self, label: tk.Label, text: str, tone: str = "neutral") -> None:
        colors = {
            "neutral": (self.SOFT, self.MUTED),
            "success": (self.GREEN_PALE, self.GREEN),
            "error": (self.RED_PALE, self.RED),
        }
        background, foreground = colors[tone]
        label.configure(text=text, bg=background, fg=foreground)

    def _show_ast(self, result: AnalysisResult) -> None:
        self._clear_ast()
        if result.ast is None:
            self._set_badge(self.ast_summary_label, "NO DISPONIBLE", "error")
            self.ast_detail_label.configure(
                text="La recuperación sintáctica no produjo una estructura navegable."
            )
            self.ast_empty_message.configure(
                text="No fue posible construir el AST.\nRevise primero los errores sintácticos.", fg=self.RED
            )
            self.ast_empty_message.place(relx=0.5, rely=0.45, anchor="center")
            return

        visual_root = build_visual_tree(result.ast)
        self._insert_ast_node("", visual_root, depth=0)
        self.ast_empty_message.place_forget()
        self._set_badge(self.ast_summary_label, f"{result.ast_node_count} NODOS", "success")
        self.ast_detail_label.configure(
            text="Seleccione un nodo; doble clic para ir a su ubicación en el código."
        )

    def _insert_ast_node(self, parent: str, visual: VisualAstNode, depth: int) -> str:
        item = self.ast_tree.insert(
            parent,
            "end",
            text=visual.label,
            values=(visual.detail, visual.location),
            open=depth < 2,
        )
        self.ast_visual_by_item[item] = visual
        for child in visual.children:
            self._insert_ast_node(item, child, depth + 1)
        return item

    def _clear_ast(self, message: str | None = None) -> None:
        for item in self.ast_tree.get_children():
            self.ast_tree.delete(item)
        self.ast_visual_by_item.clear()
        self._set_badge(self.ast_summary_label, "SIN GENERAR")
        self.ast_detail_label.configure(text=message or "Analice el archivo para construir el AST.")
        self.ast_empty_message.configure(
            text="El AST aparecerá aquí después del análisis.", fg=self.MUTED
        )
        self.ast_empty_message.place(relx=0.5, rely=0.45, anchor="center")

    def _show_selected_ast_detail(self, _event=None) -> None:
        selected = self.ast_tree.selection()
        if not selected:
            return
        visual = self.ast_visual_by_item.get(selected[0])
        if visual is None:
            return
        if visual.ast_node is None:
            self.ast_detail_label.configure(text=f"{visual.label}: {visual.detail}".rstrip(": "))
            return
        span = visual.ast_node.span
        detail = f" · {visual.detail}" if visual.detail else ""
        self.ast_detail_label.configure(
            text=f"{visual.label}{detail} · línea {span.line}, columna {span.column}"
        )

    def _go_to_selected_ast(self, _event=None) -> None:
        selected = self.ast_tree.selection()
        if not selected:
            return
        visual = self.ast_visual_by_item.get(selected[0])
        if visual is None or visual.ast_node is None:
            return
        span = visual.ast_node.span
        self.editor.tag_remove("active_error", "1.0", "end")
        start = f"{span.line}.{max(span.column - 1, 0)}"
        end = f"{span.end_line}.{max(span.end_column - 1, 1)}"
        self.editor.tag_add("active_error", start, end)
        self.editor.mark_set("insert", start)
        self.editor.see(start)
        self.editor.focus_set()
        self._update_cursor_position()

    def _set_ast_open(self, item: str, is_open: bool) -> None:
        self.ast_tree.item(item, open=is_open)
        for child in self.ast_tree.get_children(item):
            self._set_ast_open(child, is_open)

    def _expand_ast(self) -> None:
        for item in self.ast_tree.get_children():
            self._set_ast_open(item, True)

    def _collapse_ast(self) -> None:
        for item in self.ast_tree.get_children():
            self._set_ast_open(item, False)
            self.ast_tree.item(item, open=True)

    def _show_symbol_table(self, result: AnalysisResult, table: SymbolTable | None) -> None:
        self._clear_symbols()
        if result.ast is None or table is None:
            self._set_badge(self.symbols_summary_label, "NO DISPONIBLE", "error")
            self.symbols_detail_label.configure(
                text="La recuperación sintáctica no produjo un AST navegable."
            )
            self.symbols_empty_message.configure(
                text="No fue posible construir la tabla de símbolos.\nRevise primero los errores sintácticos.",
                fg=self.RED,
            )
            self.symbols_empty_message.place(relx=0.5, rely=0.45, anchor="center")
            return

        self._insert_scope_node("", table.global_scope, depth=0)
        self.symbols_empty_message.place_forget()
        total = len(table.all_symbols())
        self._set_badge(self.symbols_summary_label, f"{total} SÍMBOLOS", "success")
        self.symbols_detail_label.configure(
            text="Seleccione un símbolo; doble clic para ir a su declaración en el código."
        )

    def _insert_scope_node(self, parent: str, scope: Scope, depth: int) -> str:
        label = "Global" if scope.kind is ScopeKind.GLOBAL else f"{scope.kind.value} · {scope.name}"
        item = self.symbols_tree.insert(
            parent, "end", text=label, values=("", "", "", "", ""), open=depth < 2, tags=("scope",),
        )
        self.scope_by_item[item] = scope
        for symbol in scope.symbols.values():
            self._insert_symbol_node(item, symbol)
        for child in scope.children:
            self._insert_scope_node(item, child, depth + 1)
        return item

    def _insert_symbol_node(self, parent: str, symbol: Symbol) -> str:
        item = self.symbols_tree.insert(
            parent,
            "end",
            text=symbol.name,
            values=(
                symbol.category.value,
                symbol.type_name or symbol.runtime_type or "-",
                "sí" if symbol.initialized else "no",
                self._symbol_address(symbol),
                self._symbol_size(symbol),
            ),
            open=False,
        )
        self.symbol_by_item[item] = symbol
        return item

    def _clear_symbols(self, message: str | None = None) -> None:
        for item in self.symbols_tree.get_children():
            self.symbols_tree.delete(item)
        self.symbol_by_item.clear()
        self.scope_by_item.clear()
        self._set_badge(self.symbols_summary_label, "SIN GENERAR")
        self.symbols_detail_label.configure(
            text=message or "Analice el archivo para construir la tabla de símbolos."
        )
        self.symbols_empty_message.configure(
            text="La tabla de símbolos aparecerá aquí después del análisis.", fg=self.MUTED
        )
        self.symbols_empty_message.place(relx=0.5, rely=0.45, anchor="center")

    def _show_selected_symbol_detail(self, _event=None) -> None:
        selected = self.symbols_tree.selection()
        if not selected:
            return
        symbol = self.symbol_by_item.get(selected[0])
        if symbol is None:
            scope = self.scope_by_item.get(selected[0])
            if scope is not None:
                label = "global" if scope.kind is ScopeKind.GLOBAL else f"{scope.kind.value} · {scope.name}"
                self.symbols_detail_label.configure(text=f"Ámbito: {label}")
            return

        parts = [f"{symbol.category.value} «{symbol.name}»"]
        if symbol.type_name or symbol.runtime_type:
            parts.append(f"tipo {symbol.type_name or symbol.runtime_type}")
        if symbol.address:
            parts.append(f"dirección {symbol.address} ({symbol.size} B, {symbol.storage.value} en {symbol.owner})")
        if symbol.category is SymbolCategory.FUNCTION:
            params = ", ".join(f"{p.name}: {p.type_name or '?'}" for p in symbol.parameters)
            parts.append(f"({params}) -> {symbol.return_type or 'void'}")
            if symbol.activation_record is not None:
                record = symbol.activation_record
                parts.append(f"etiqueta {record.name}, registro de {record.size} B")
            if symbol.captured_names:
                parts.append(f"captura: {', '.join(sorted(symbol.captured_names))}")
        if symbol.category is SymbolCategory.CLASS:
            if symbol.superclass:
                parts.append(f"extiende {symbol.superclass}")
            if symbol.attributes:
                parts.append(f"atributos: {', '.join(sorted(symbol.attributes))}")
            if symbol.methods:
                parts.append(f"métodos: {', '.join(sorted(symbol.methods))}")
            if symbol.class_layout is not None:
                parts.append(f"instancia de {symbol.class_layout.size} B")
        parts.append(f"línea {symbol.line}, columna {symbol.column}")
        self.symbols_detail_label.configure(text=" · ".join(parts))

    @staticmethod
    def _symbol_address(symbol: Symbol) -> str:
        if symbol.address:
            return symbol.address
        if symbol.activation_record is not None:
            return symbol.activation_record.name
        return "-"

    @staticmethod
    def _symbol_size(symbol: Symbol) -> str:
        if symbol.size:
            return str(symbol.size)
        if symbol.activation_record is not None:
            return str(symbol.activation_record.size)
        if symbol.class_layout is not None:
            return str(symbol.class_layout.size)
        return "-"

    def _go_to_selected_symbol(self, _event=None) -> None:
        selected = self.symbols_tree.selection()
        if not selected:
            return
        symbol = self.symbol_by_item.get(selected[0])
        if symbol is None:
            return
        self.editor.tag_remove("active_error", "1.0", "end")
        start = f"{symbol.line}.{max(symbol.column - 1, 0)}"
        self.editor.tag_add("active_error", start, f"{symbol.line}.end")
        self.editor.mark_set("insert", start)
        self.editor.see(start)
        self.editor.focus_set()
        self._update_cursor_position()

    def _set_symbols_open(self, item: str, is_open: bool) -> None:
        self.symbols_tree.item(item, open=is_open)
        for child in self.symbols_tree.get_children(item):
            self._set_symbols_open(child, is_open)

    def _expand_symbols(self) -> None:
        for item in self.symbols_tree.get_children():
            self._set_symbols_open(item, True)

    def _collapse_symbols(self) -> None:
        for item in self.symbols_tree.get_children():
            self._set_symbols_open(item, False)
            self.symbols_tree.item(item, open=True)

    # -- código intermedio -----------------------------------------------------
    def _show_tac(self, compilation: CompilationResult | None) -> None:
        self._clear_tac()
        if compilation is None:
            return
        if compilation.tac is None:
            total = len(compilation.diagnostics)
            self._set_badge(self.tac_summary_label, "NO GENERADO", "error")
            self.tac_detail_label.configure(text="El programa tiene errores; no se genera código intermedio.")
            self.tac_empty_message.configure(
                text=(
                    f"No se generó código intermedio.\nCorrija {'el error' if total == 1 else f'los {total} errores'} "
                    "de la pestaña «Diagnósticos»."
                ),
                fg=self.RED,
            )
            return

        lines = compilation.tac.rendered_lines()
        self.tac_line_instructions = [instruction for _text, instruction in lines]
        self.tac_text.configure(state="normal")
        self.tac_text.insert("1.0", "\n".join(text for text, _instruction in lines))
        self._highlight_tac()
        self.tac_text.configure(state="disabled")
        self.tac_empty_message.place_forget()
        self.tac_save_button.state(["!disabled"])
        self.tac_copy_button.state(["!disabled"])

        functions = sum(1 for instruction in compilation.tac if instruction.op.name == "BEGIN_FUNC")
        self._set_badge(self.tac_summary_label, f"{len(compilation.tac)} INSTRUCCIONES", "success")
        usage = compilation.temp_usage
        created = sum(item.created for item in usage)
        reuses = sum(item.reuses for item in usage)
        peak = max((item.max_live for item in usage), default=0)
        self.tac_detail_label.configure(
            text=f"{functions} funciones · {created} temporales · {reuses} reciclados · máx. {peak} vivos"
        )

    def _highlight_tac(self) -> None:
        text = self.tac_text.get("1.0", "end-1c")
        keyword_pattern = r"\b(?:" + "|".join(self.TAC_KEYWORDS) + r")\b"
        patterns = (
            ("tac_function", r"^(?:begin_func|end_func)\b[^\n]*"),
            ("tac_label", r"^[^\s\n][^\n]*:$"),
            ("tac_string", r'"(?:\\.|[^"\\\n])*"'),
            ("tac_keyword", keyword_pattern),
            ("tac_temp", r"\bt\d+\b"),
        )
        for tag, pattern in patterns:
            for match in re.finditer(pattern, text, re.MULTILINE):
                self.tac_text.tag_add(tag, f"1.0+{match.start()}c", f"1.0+{match.end()}c")

    def _clear_tac(self) -> None:
        self.tac_line_instructions = []
        self.tac_text.configure(state="normal")
        self.tac_text.delete("1.0", "end")
        self.tac_text.configure(state="disabled")
        self.tac_save_button.state(["disabled"])
        self.tac_copy_button.state(["disabled"])
        self._set_badge(self.tac_summary_label, "SIN GENERAR")
        self.tac_detail_label.configure(text="Compile el archivo (F5) para generar el código intermedio.")
        self.tac_empty_message.configure(
            text="El código intermedio aparecerá aquí después de compilar.", fg=self.MUTED
        )
        self.tac_empty_message.place(relx=0.5, rely=0.45, anchor="center")

    def _go_to_tac_source(self, _event=None) -> None:
        if not self.tac_line_instructions:
            return
        line_number = int(self.tac_text.index("insert").split(".")[0])
        self.tac_text.tag_remove("tac_current", "1.0", "end")
        self.tac_text.tag_add("tac_current", f"{line_number}.0", f"{line_number}.end+1c")
        if line_number > len(self.tac_line_instructions):
            return
        instruction = self.tac_line_instructions[line_number - 1]
        if instruction is None or instruction.line is None:
            return
        self.editor.tag_remove("tac_source", "1.0", "end")
        self.editor.tag_add("tac_source", f"{instruction.line}.0", f"{instruction.line}.end")
        self.editor.see(f"{instruction.line}.0")
        self.status_label.configure(text=f"Instrucción TAC generada por la línea {instruction.line}")

    def _tac_text(self) -> str | None:
        compilation = self.last_compilation
        if compilation is None or compilation.tac is None:
            return None
        return compilation.tac.render() + "\n"

    def copy_tac(self) -> None:
        text = self._tac_text()
        if text is None:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.status_label.configure(text="Código intermedio copiado al portapapeles")

    def save_tac(self) -> None:
        text = self._tac_text()
        if text is None:
            return
        initial = f"{self.current_file.stem}.tac" if self.current_file is not None else "programa.tac"
        selected = filedialog.asksaveasfilename(
            title="Guardar código intermedio", defaultextension=".tac", initialfile=initial,
            filetypes=(("Código de tres direcciones", "*.tac"), ("Texto", "*.txt")),
        )
        if not selected:
            return
        try:
            Path(selected).write_text(text, encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("No se pudo guardar", f"No fue posible guardar el TAC:\n{exc}")
            return
        self.status_label.configure(text=f"Código intermedio guardado en {Path(selected).name}")

    # -- entornos de ejecución -----------------------------------------------
    def _show_environments(self, compilation: CompilationResult | None) -> None:
        self._clear_environments()
        if compilation is None:
            return
        table = compilation.symbol_table
        if compilation.tac is None or table is None or not table.has_layout:
            self._set_badge(self.environments_summary_label, "NO DISPONIBLE", "error")
            self.environments_detail_label.configure(text="Los entornos se calculan sólo para programas sin errores.")
            self.environments_empty_message.configure(
                text="No hay entornos de ejecución.\nEl programa tiene errores.", fg=self.RED
            )
            return

        for record in [table.global_record, *table.activation_records]:
            self._insert_record(record)
        for layout in table.class_layouts.values():
            self._insert_class_layout(layout)
        self.environments_empty_message.place_forget()
        records = len(table.activation_records) + 1
        classes = len(table.class_layouts)
        self._set_badge(
            self.environments_summary_label,
            f"{records} REGISTROS · {classes} {'CLASE' if classes == 1 else 'CLASES'}",
            "success",
        )
        self.environments_detail_label.configure(text="Desplazamientos en bytes desde fp, global u obj.")

    def _insert_record(self, record: ActivationRecord) -> None:
        if record.kind == "programa":
            title = "Área global (programa)"
            detail = "variables globales y temporales del código global"
        else:
            title = f"{record.kind} {record.name}"
            detail = f"nivel {record.level} · enlace de acceso → {record.parent or '-'}"
        item = self.environments_tree.insert(
            "", "end", text=title, values=("", record.size, detail), open=record.kind == "programa",
            tags=("scope",),
        )
        self.environment_by_item[item] = record
        for slot in record.all_slots():
            self._insert_slot(item, slot, record)

    _HEADER_DETAILS = {
        "dirección de retorno": "instrucción a la que vuelve el llamador",
        "enlace de control": "fp del registro del llamador",
        "puntero a vtable": "tabla de métodos de la clase real",
    }

    def _insert_slot(self, parent: str, slot: FrameSlot, record: ActivationRecord | None = None) -> None:
        if slot.role == "enlace de acceso":
            detail = f"fp del entorno léxico ({record.parent if record is not None else '-'})"
        else:
            detail = self._HEADER_DETAILS.get(slot.role) or (
                slot.role + (f" · {slot.type_name}" if slot.type_name else "")
            )
        tags = {"temporal": ("temporary",), "dirección de retorno": ("header",),
                "enlace de control": ("header",), "enlace de acceso": ("header",),
                "puntero a vtable": ("header",)}.get(slot.role, ())
        item = self.environments_tree.insert(
            parent, "end", text=slot.name, values=(f"+{slot.offset}", slot.size, detail), tags=tags
        )
        self.environment_by_item[item] = slot

    def _insert_class_layout(self, layout: ClassLayout) -> None:
        detail = f"instancia · extiende {layout.superclass}" if layout.superclass else "instancia"
        item = self.environments_tree.insert(
            "", "end", text=f"clase {layout.name}", values=("", layout.size, detail), open=False,
            tags=("scope",),
        )
        self.environment_by_item[item] = layout
        for slot in layout.slots:
            self._insert_slot(item, slot)
        vtable = self.environments_tree.insert(
            item, "end", text="vtable", values=("", len(layout.vtable) * 4, "métodos con despacho dinámico"),
            open=True, tags=("scope",),
        )
        for index, (method, label) in enumerate(layout.vtable):
            self.environments_tree.insert(
                vtable, "end", text=f"[{index}] {method}", values=(f"+{index * 4}", 4, f"→ {label}")
            )

    def _clear_environments(self) -> None:
        for item in self.environments_tree.get_children():
            self.environments_tree.delete(item)
        self.environment_by_item.clear()
        self._set_badge(self.environments_summary_label, "SIN GENERAR")
        self.environments_detail_label.configure(text="Compile el archivo para calcular los entornos de ejecución.")
        self.environments_empty_message.configure(
            text="Los registros de activación aparecerán aquí después de compilar.", fg=self.MUTED
        )
        self.environments_empty_message.place(relx=0.5, rely=0.45, anchor="center")

    def _show_selected_environment_detail(self, _event=None) -> None:
        selected = self.environments_tree.selection()
        if not selected:
            return
        value = self.environment_by_item.get(selected[0])
        if isinstance(value, ActivationRecord):
            text = (
                f"{value.kind} {value.name} · {value.size} B · {len(value.slots)} casillas de datos · "
                f"{value.temporaries} temporales"
            )
        elif isinstance(value, ClassLayout):
            text = f"clase {value.name} · instancias de {value.size} B · {len(value.vtable)} métodos en la vtable"
        elif isinstance(value, FrameSlot):
            text = f"{value.name}: {value.role} en +{value.offset} ({value.size} B)"
            if value.symbol is not None:
                text += f" · declarado en la línea {value.symbol.line}; doble clic para ir"
        else:
            return
        self.environments_detail_label.configure(text=text)

    def _go_to_selected_environment(self, _event=None) -> None:
        selected = self.environments_tree.selection()
        if not selected:
            return
        value = self.environment_by_item.get(selected[0])
        symbol = value.symbol if isinstance(value, FrameSlot) else None
        if symbol is None:
            return
        self.editor.tag_remove("active_error", "1.0", "end")
        start = f"{symbol.line}.{max(symbol.column - 1, 0)}"
        self.editor.tag_add("active_error", start, f"{symbol.line}.end")
        self.editor.mark_set("insert", start)
        self.editor.see(start)
        self.editor.focus_set()
        self._update_cursor_position()

    def _set_environments_open(self, item: str, is_open: bool) -> None:
        self.environments_tree.item(item, open=is_open)
        for child in self.environments_tree.get_children(item):
            self._set_environments_open(child, is_open)

    def _expand_environments(self) -> None:
        for item in self.environments_tree.get_children():
            self._set_environments_open(item, True)

    def _collapse_environments(self) -> None:
        for item in self.environments_tree.get_children():
            self._set_environments_open(item, False)

    def _show_selected_detail(self, _event=None) -> None:
        selected = self.results.selection()
        if not selected or not self.last_diagnostics:
            return
        diagnostic = self.last_diagnostics[int(selected[0])]
        self.diagnostic_detail.configure(
            text=(
                f"{diagnostic.kind} · línea {diagnostic.line}, columna {diagnostic.column} · "
                f"«{diagnostic.symbol}»: {diagnostic.description}"
            ),
            fg=self._diagnostic_color(diagnostic.kind),
        )

    def _go_to_selected(self, _event=None) -> None:
        selected = self.results.selection()
        if not selected or not self.last_diagnostics:
            return
        diagnostic = self.last_diagnostics[int(selected[0])]
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
        self._set_badge(self.summary_label, "SIN ANALIZAR")
        self.result_detail.configure(text="Los diagnósticos aparecerán ordenados por ubicación.")
        self.diagnostic_detail.configure(text="Detalle: seleccione una fila de la tabla.", fg=self.INK)
        self.empty_message.configure(
            text=message or "Abra un archivo Compiscript\ny ejecute el análisis.", fg=self.MUTED
        )
        self.empty_message.place(relx=0.5, rely=0.45, anchor="center")
        self._clear_ast(message or "Analice el archivo para construir el AST.")
        self._clear_symbols(message or "Analice el archivo para construir la tabla de símbolos.")
        self._clear_tac()
        self._clear_environments()
        self.editor.tag_remove("tac_source", "1.0", "end")


    def _update_file_labels(self) -> None:
        if self.current_file is None:
            self.file_name_label.configure(text="Ningún archivo abierto")
            self.file_path_label.configure(text="Seleccione un archivo .cps para comenzar")
            self.root.title("Compilador Compiscript")
            return
        marker = " •" if self.dirty else ""
        self.file_name_label.configure(text=f"{self.current_file.name}{marker}")
        self.file_path_label.configure(text=str(self.current_file.parent))
        dirty_title = " *" if self.dirty else ""
        self.root.title(f"{self.current_file.name}{dirty_title} — Compilador Compiscript")

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
