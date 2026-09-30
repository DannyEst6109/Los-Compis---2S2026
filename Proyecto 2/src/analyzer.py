from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

SOURCE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE_DIR / "vendor"))
sys.path.insert(0, str(SOURCE_DIR / "generated"))

from antlr4 import CommonTokenStream, InputStream, Token  # noqa: E402
from antlr4.error.ErrorListener import ErrorListener  # noqa: E402

from CompiscriptLexer import CompiscriptLexer  # noqa: E402
from CompiscriptParser import CompiscriptParser  # noqa: E402
from ast_builder import AstBuilder  # noqa: E402
from ast_nodes import AstNode, Program, iter_child_nodes  # noqa: E402


@dataclass(frozen=True, slots=True)
class Diagnostic:
    kind: str
    line: int
    column: int
    symbol: str
    description: str


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    diagnostics: tuple[Diagnostic, ...]
    token_count: int
    line_count: int
    elapsed_ms: float
    ast: Program | None

    @property
    def is_valid(self) -> bool:
        return not self.diagnostics

    @property
    def lexical_count(self) -> int:
        return sum(item.kind == "Léxico" for item in self.diagnostics)

    @property
    def syntactic_count(self) -> int:
        return sum(item.kind == "Sintáctico" for item in self.diagnostics)

    @property
    def ast_node_count(self) -> int:
        def count(node: AstNode) -> int:
            return 1 + sum(count(child) for child in iter_child_nodes(node))

        return count(self.ast) if self.ast is not None else 0


def _clean_symbol(value: str | None) -> str:
    if not value or value == "<EOF>":
        return "fin del archivo"
    value = value.rstrip().replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    if len(value) > 32:
        return f"{value[:29]}..."
    return value


def _clean_expected(value: str) -> str:
    value = value.strip()
    expression_starters = ("'new'", "'this'", "'null'", "'true'", "'false'", "'-'", "'!'", "'('", "'['")
    if value.startswith("{") and all(item in value for item in expression_starters):
        return "una expresión válida"
    value = value.replace("<EOF>", "fin del archivo")
    value = value.replace("Identifier", "un identificador")
    value = value.replace("IntegerLiteral", "un número entero")
    value = value.replace("StringLiteral", "una cadena de texto")
    if value.startswith("{") and value.endswith("}"):
        items = [item.strip() for item in value[1:-1].split(",")]
        rendered = [f"«{item[1:-1]}»" if item.startswith("'") and item.endswith("'") else item for item in items]
        if len(rendered) == 1:
            return rendered[0]
        return ", ".join(rendered[:-1]) + f" o {rendered[-1]}"
    if value.startswith("'") and value.endswith("'"):
        return f"«{value[1:-1]}»"
    return value


class LexerDiagnosticListener(ErrorListener):
    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        super().__init__()
        self.diagnostics = diagnostics

    def syntaxError(
        self,
        recognizer,
        offendingSymbol,
        line: int,
        column: int,
        msg: str,
        exc,
    ) -> None:
        start = getattr(recognizer, "_tokenStartCharIndex", -1)
        current = getattr(getattr(recognizer, "_input", None), "index", start)
        symbol = ""
        if start >= 0 and current >= start:
            try:
                symbol = recognizer._input.getText(start, current)
            except Exception:
                symbol = ""

        match = re.search(r"token recognition error at: '(.+)'", msg, re.DOTALL)
        if not symbol and match:
            symbol = match.group(1)

        if symbol.startswith('"') and not symbol.endswith('"'):
            description = "La cadena de texto no tiene comillas de cierre."
        elif symbol.startswith("/*"):
            description = "El comentario de bloque no tiene cierre."
        else:
            description = "Carácter o lexema no reconocido por Compiscript."

        self.diagnostics.append(
            Diagnostic("Léxico", max(line, 1), max(column + 1, 1), _clean_symbol(symbol), description)
        )


class ParserDiagnosticListener(ErrorListener):
    def __init__(self, diagnostics: list[Diagnostic]) -> None:
        super().__init__()
        self.diagnostics = diagnostics

    def syntaxError(
        self,
        recognizer,
        offendingSymbol,
        line: int,
        column: int,
        msg: str,
        exc,
    ) -> None:
        symbol = _clean_symbol(getattr(offendingSymbol, "text", None))
        description = self._translate(recognizer, msg, symbol)
        self.diagnostics.append(
            Diagnostic("Sintáctico", max(line, 1), max(column + 1, 1), symbol, description)
        )

    @staticmethod
    def _expected(recognizer) -> str:
        try:
            tokens = recognizer.getExpectedTokens()
            rendered = tokens.toString(recognizer.literalNames, recognizer.symbolicNames)
            return _clean_expected(rendered)
        except Exception:
            return "otro símbolo"

    def _translate(self, recognizer, message: str, symbol: str) -> str:
        expected = self._expected(recognizer)

        missing = re.match(r"missing (.+) at ", message)
        if missing:
            return f"Falta {_clean_expected(missing.group(1))} antes de «{symbol}»."

        if message.startswith("extraneous input"):
            return f"«{symbol}» no corresponde aquí; se esperaba {expected}."

        if message.startswith("mismatched input"):
            return f"Se encontró «{symbol}»; se esperaba {expected}."

        if message.startswith("no viable alternative"):
            return f"La secuencia cercana a «{symbol}» no forma una construcción válida."

        if message.startswith("failed predicate"):
            return f"La construcción cercana a «{symbol}» no cumple la forma requerida."

        return f"«{symbol}» no es válido aquí; se esperaba {expected}."


class CompiscriptAnalyzer:
    """Integra lexer, parser y AST sin ejecutar el programa."""

    def analyze(self, source: str) -> AnalysisResult:
        started = perf_counter()
        diagnostics: list[Diagnostic] = []

        lexer = CompiscriptLexer(InputStream(source))
        lexer.removeErrorListeners()
        lexer.addErrorListener(LexerDiagnosticListener(diagnostics))

        token_stream = CommonTokenStream(lexer)
        token_stream.fill()
        token_count = sum(token.type != Token.EOF for token in token_stream.tokens)
        token_stream.seek(0)

        parser = CompiscriptParser(token_stream)
        parser.removeErrorListeners()
        parser.addErrorListener(ParserDiagnosticListener(diagnostics))
        parser.buildParseTrees = True
        parse_tree = parser.program()

        program_ast: Program | None
        try:
            program_ast = AstBuilder().build(parse_tree)
        except (AttributeError, IndexError, TypeError, ValueError):
            # Una entrada muy dañada puede no dejar suficiente estructura para
            # formar un AST. Los diagnósticos de ANTLR siguen disponibles y el
            # analizador no termina abruptamente.
            program_ast = None

        unique: dict[tuple[object, ...], Diagnostic] = {}
        for item in diagnostics:
            key = (item.kind, item.line, item.column, item.symbol, item.description)
            unique.setdefault(key, item)

        ordered = tuple(
            sorted(
                unique.values(),
                key=lambda item: (item.line, item.column, 0 if item.kind == "Léxico" else 1),
            )
        )
        elapsed_ms = (perf_counter() - started) * 1000
        return AnalysisResult(
            diagnostics=ordered,
            token_count=token_count,
            line_count=max(source.count("\n") + 1, 1),
            elapsed_ms=elapsed_ms,
            ast=program_ast,
        )
