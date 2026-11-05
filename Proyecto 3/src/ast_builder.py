"""Transformación del parse tree de ANTLR al AST de Compiscript."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import ast_nodes as ast


SOURCE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SOURCE_DIR / "vendor"))
sys.path.insert(0, str(SOURCE_DIR / "generated"))

from CompiscriptParser import CompiscriptParser  # noqa: E402
from CompiscriptVisitor import CompiscriptVisitor  # noqa: E402


class AstBuilder(CompiscriptVisitor):
    """Construye un AST incluso cuando ANTLR recupera errores parciales."""

    def build(self, parse_tree: CompiscriptParser.ProgramContext) -> ast.Program:
        return self.visit(parse_tree)

    @staticmethod
    def _span(ctx) -> ast.SourceSpan:
        start = getattr(ctx, "start", None)
        stop = getattr(ctx, "stop", None) or start
        if start is None:
            return ast.SourceSpan.unknown()
        start_line = max(getattr(start, "line", 1), 1)
        start_column = max(getattr(start, "column", 0) + 1, 1)
        end_line = max(getattr(stop, "line", start_line), start_line)
        stop_text = getattr(stop, "text", "") or ""
        end_column = max(getattr(stop, "column", start_column - 1) + len(stop_text) + 1, 1)
        return ast.SourceSpan(start_line, start_column, end_line, end_column)

    @staticmethod
    def _text(token, fallback: str = "<faltante>") -> str:
        return token.getText() if token is not None else fallback

    def _expression(self, ctx, owner=None) -> ast.Expression:
        if ctx is None:
            return ast.ErrorExpression(
                description="Expresión incompleta",
                span=self._span(owner) if owner is not None else ast.SourceSpan.unknown(),
            )
        result = self.visit(ctx)
        if isinstance(result, ast.Expression):
            return result
        return ast.ErrorExpression(description="Expresión no recuperable", span=self._span(ctx))

    def _statement(self, ctx, owner=None) -> ast.Statement:
        if ctx is not None:
            result = self.visit(ctx)
            if isinstance(result, ast.Statement):
                return result
        error = ast.ErrorExpression(
            description="Instrucción incompleta",
            span=self._span(owner) if owner is not None else ast.SourceSpan.unknown(),
        )
        return ast.ExpressionStatement(expression=error, span=error.span)

    def _block(self, ctx, owner=None) -> ast.Block:
        if ctx is not None:
            result = self.visit(ctx)
            if isinstance(result, ast.Block):
                return result
        return ast.Block(statements=(), span=self._span(owner) if owner is not None else ast.SourceSpan.unknown())

    def _fold_binary(self, operands, ctx) -> ast.Expression:
        if not operands:
            return self._expression(None, ctx)
        left = self._expression(operands[0], ctx)
        for index, operand_ctx in enumerate(operands[1:], start=1):
            right = self._expression(operand_ctx, ctx)
            operator_child = ctx.getChild(index * 2 - 1)
            operator = operator_child.getText() if operator_child is not None else "?"
            left = ast.BinaryExpression(
                left=left,
                operator=operator,
                right=right,
                span=ast.SourceSpan.merge(left.span, right.span),
            )
        return left

    def visitProgram(self, ctx: CompiscriptParser.ProgramContext) -> ast.Program:
        statements = tuple(self._statement(item, ctx) for item in ctx.statement())
        return ast.Program(statements=statements, span=self._span(ctx))

    def visitStatement(self, ctx: CompiscriptParser.StatementContext) -> ast.Statement:
        child = ctx.getChild(0) if ctx.getChildCount() else None
        return self._statement(child, ctx)

    def visitBlock(self, ctx: CompiscriptParser.BlockContext) -> ast.Block:
        return ast.Block(
            statements=tuple(self._statement(item, ctx) for item in ctx.statement()),
            span=self._span(ctx),
        )

    def visitVariableDeclaration(self, ctx: CompiscriptParser.VariableDeclarationContext) -> ast.VariableDeclaration:
        initializer = ctx.initializer()
        return ast.VariableDeclaration(
            declaration_kind="let" if ctx.LET() is not None else "var",
            name=self._text(ctx.Identifier()),
            type_annotation=self.visit(ctx.typeAnnotation()) if ctx.typeAnnotation() is not None else None,
            initializer=self.visit(initializer) if initializer is not None else None,
            span=self._span(ctx),
        )

    def visitConstantDeclaration(self, ctx: CompiscriptParser.ConstantDeclarationContext) -> ast.ConstantDeclaration:
        return ast.ConstantDeclaration(
            name=self._text(ctx.Identifier()),
            type_annotation=self.visit(ctx.typeAnnotation()) if ctx.typeAnnotation() is not None else None,
            initializer=self._expression(ctx.expression(), ctx),
            span=self._span(ctx),
        )

    def visitTypeAnnotation(self, ctx: CompiscriptParser.TypeAnnotationContext) -> ast.TypeRef:
        return self.visit(ctx.type_())

    def visitInitializer(self, ctx: CompiscriptParser.InitializerContext) -> ast.Expression:
        return self._expression(ctx.expression(), ctx)

    def visitExpressionStatement(self, ctx: CompiscriptParser.ExpressionStatementContext) -> ast.ExpressionStatement:
        return ast.ExpressionStatement(expression=self._expression(ctx.expression(), ctx), span=self._span(ctx))

    def visitPrintStatement(self, ctx: CompiscriptParser.PrintStatementContext) -> ast.PrintStatement:
        return ast.PrintStatement(expression=self._expression(ctx.expression(), ctx), span=self._span(ctx))

    def visitIfStatement(self, ctx: CompiscriptParser.IfStatementContext) -> ast.IfStatement:
        branches = ctx.statement()
        return ast.IfStatement(
            condition=self._expression(ctx.expression(), ctx),
            then_branch=self._statement(branches[0] if branches else None, ctx),
            else_branch=self._statement(branches[1], ctx) if len(branches) > 1 else None,
            span=self._span(ctx),
        )

    def visitWhileStatement(self, ctx: CompiscriptParser.WhileStatementContext) -> ast.WhileStatement:
        return ast.WhileStatement(
            condition=self._expression(ctx.expression(), ctx),
            body=self._statement(ctx.statement(), ctx),
            span=self._span(ctx),
        )

    def visitDoWhileStatement(self, ctx: CompiscriptParser.DoWhileStatementContext) -> ast.DoWhileStatement:
        return ast.DoWhileStatement(
            body=self._statement(ctx.statement(), ctx),
            condition=self._expression(ctx.expression(), ctx),
            span=self._span(ctx),
        )

    def visitForStatement(self, ctx: CompiscriptParser.ForStatementContext) -> ast.ForStatement:
        expressions = ctx.expression()
        return ast.ForStatement(
            initializer=self.visit(ctx.forInitializer()) if ctx.forInitializer() is not None else None,
            condition=self._expression(expressions[0], ctx) if expressions else None,
            update=self._expression(expressions[1], ctx) if len(expressions) > 1 else None,
            body=self._statement(ctx.statement(), ctx),
            span=self._span(ctx),
        )

    def visitForInitializer(self, ctx: CompiscriptParser.ForInitializerContext):
        if ctx.Identifier() is None:
            return self._expression(ctx.expression(), ctx)
        initializer = ctx.initializer()
        return ast.VariableDeclaration(
            declaration_kind="let" if ctx.LET() is not None else "var",
            name=self._text(ctx.Identifier()),
            type_annotation=self.visit(ctx.typeAnnotation()) if ctx.typeAnnotation() is not None else None,
            initializer=self.visit(initializer) if initializer is not None else None,
            span=self._span(ctx),
        )

    def visitForeachStatement(self, ctx: CompiscriptParser.ForeachStatementContext) -> ast.ForeachStatement:
        return ast.ForeachStatement(
            variable=self._text(ctx.Identifier()),
            iterable=self._expression(ctx.expression(), ctx),
            body=self._statement(ctx.statement(), ctx),
            span=self._span(ctx),
        )

    def visitBreakStatement(self, ctx: CompiscriptParser.BreakStatementContext) -> ast.BreakStatement:
        return ast.BreakStatement(span=self._span(ctx))

    def visitContinueStatement(self, ctx: CompiscriptParser.ContinueStatementContext) -> ast.ContinueStatement:
        return ast.ContinueStatement(span=self._span(ctx))

    def visitReturnStatement(self, ctx: CompiscriptParser.ReturnStatementContext) -> ast.ReturnStatement:
        return ast.ReturnStatement(
            value=self._expression(ctx.expression(), ctx) if ctx.expression() is not None else None,
            span=self._span(ctx),
        )

    def visitTryCatchStatement(self, ctx: CompiscriptParser.TryCatchStatementContext) -> ast.TryCatchStatement:
        blocks = ctx.block()
        return ast.TryCatchStatement(
            try_block=self._block(blocks[0] if blocks else None, ctx),
            error_name=self._text(ctx.Identifier()),
            catch_block=self._block(blocks[1] if len(blocks) > 1 else None, ctx),
            span=self._span(ctx),
        )

    def visitSwitchStatement(self, ctx: CompiscriptParser.SwitchStatementContext) -> ast.SwitchStatement:
        default_context = ctx.defaultCase()
        default_statements = (
            tuple(self._statement(item, default_context) for item in default_context.statement())
            if default_context is not None
            else ()
        )
        return ast.SwitchStatement(
            expression=self._expression(ctx.expression(), ctx),
            cases=tuple(self.visit(item) for item in ctx.switchCase()),
            default_statements=default_statements,
            span=self._span(ctx),
        )

    def visitSwitchCase(self, ctx: CompiscriptParser.SwitchCaseContext) -> ast.SwitchCase:
        return ast.SwitchCase(
            value=self._expression(ctx.expression(), ctx),
            statements=tuple(self._statement(item, ctx) for item in ctx.statement()),
            span=self._span(ctx),
        )

    def visitDefaultCase(self, ctx: CompiscriptParser.DefaultCaseContext) -> tuple[ast.Statement, ...]:
        return tuple(self._statement(item, ctx) for item in ctx.statement())

    def visitFunctionDeclaration(self, ctx: CompiscriptParser.FunctionDeclarationContext) -> ast.FunctionDeclaration:
        parameters = self.visit(ctx.parameters()) if ctx.parameters() is not None else ()
        return ast.FunctionDeclaration(
            name=self._text(ctx.Identifier()),
            parameters=parameters,
            return_type=self.visit(ctx.type_()) if ctx.type_() is not None else None,
            body=self._block(ctx.block(), ctx),
            span=self._span(ctx),
        )

    def visitParameters(self, ctx: CompiscriptParser.ParametersContext) -> tuple[ast.Parameter, ...]:
        return tuple(self.visit(item) for item in ctx.parameter())

    def visitParameter(self, ctx: CompiscriptParser.ParameterContext) -> ast.Parameter:
        return ast.Parameter(
            name=self._text(ctx.Identifier()),
            type_annotation=self.visit(ctx.typeAnnotation()) if ctx.typeAnnotation() is not None else None,
            span=self._span(ctx),
        )

    def visitClassDeclaration(self, ctx: CompiscriptParser.ClassDeclarationContext) -> ast.ClassDeclaration:
        identifiers = ctx.Identifier()
        return ast.ClassDeclaration(
            name=self._text(identifiers[0] if identifiers else None),
            superclass=self._text(identifiers[1]) if len(identifiers) > 1 else None,
            members=tuple(self._statement(item, ctx) for item in ctx.classMember()),
            span=self._span(ctx),
        )

    def visitClassMember(self, ctx: CompiscriptParser.ClassMemberContext) -> ast.Statement:
        child = ctx.getChild(0) if ctx.getChildCount() else None
        return self._statement(child, ctx)

    def visitExpression(self, ctx: CompiscriptParser.ExpressionContext) -> ast.Expression:
        return self._expression(ctx.assignmentExpression(), ctx)

    def visitAssignmentExpression(self, ctx: CompiscriptParser.AssignmentExpressionContext) -> ast.Expression:
        if ctx.ASSIGN() is None:
            return self._expression(ctx.conditionalExpression(), ctx)
        return ast.AssignmentExpression(
            target=self._expression(ctx.leftHandSide(), ctx),
            value=self._expression(ctx.assignmentExpression(), ctx),
            span=self._span(ctx),
        )

    def visitConditionalExpression(self, ctx: CompiscriptParser.ConditionalExpressionContext) -> ast.Expression:
        condition = self._expression(ctx.logicalOrExpression(), ctx)
        alternatives = ctx.expression()
        if not alternatives:
            return condition
        return ast.ConditionalExpression(
            condition=condition,
            when_true=self._expression(alternatives[0], ctx),
            when_false=self._expression(alternatives[1] if len(alternatives) > 1 else None, ctx),
            span=self._span(ctx),
        )

    def visitLogicalOrExpression(self, ctx: CompiscriptParser.LogicalOrExpressionContext) -> ast.Expression:
        return self._fold_binary(ctx.logicalAndExpression(), ctx)

    def visitLogicalAndExpression(self, ctx: CompiscriptParser.LogicalAndExpressionContext) -> ast.Expression:
        return self._fold_binary(ctx.equalityExpression(), ctx)

    def visitEqualityExpression(self, ctx: CompiscriptParser.EqualityExpressionContext) -> ast.Expression:
        return self._fold_binary(ctx.relationalExpression(), ctx)

    def visitRelationalExpression(self, ctx: CompiscriptParser.RelationalExpressionContext) -> ast.Expression:
        return self._fold_binary(ctx.additiveExpression(), ctx)

    def visitAdditiveExpression(self, ctx: CompiscriptParser.AdditiveExpressionContext) -> ast.Expression:
        return self._fold_binary(ctx.multiplicativeExpression(), ctx)

    def visitMultiplicativeExpression(self, ctx: CompiscriptParser.MultiplicativeExpressionContext) -> ast.Expression:
        return self._fold_binary(ctx.unaryExpression(), ctx)

    def visitUnaryExpression(self, ctx: CompiscriptParser.UnaryExpressionContext) -> ast.Expression:
        nested = ctx.unaryExpression()
        if nested is None:
            return self._expression(ctx.primaryExpression(), ctx)
        return ast.UnaryExpression(
            operator=self._text(ctx.getChild(0)),
            operand=self._expression(nested, ctx),
            span=self._span(ctx),
        )

    def visitPrimaryExpression(self, ctx: CompiscriptParser.PrimaryExpressionContext) -> ast.Expression:
        if ctx.literalExpression() is not None:
            return self._expression(ctx.literalExpression(), ctx)
        if ctx.leftHandSide() is not None:
            return self._expression(ctx.leftHandSide(), ctx)
        return ast.GroupingExpression(
            expression=self._expression(ctx.expression(), ctx),
            span=self._span(ctx),
        )

    def visitLiteralExpression(self, ctx: CompiscriptParser.LiteralExpressionContext) -> ast.Expression:
        if ctx.arrayLiteral() is not None:
            return self._expression(ctx.arrayLiteral(), ctx)
        if ctx.IntegerLiteral() is not None:
            return ast.LiteralExpression(
                value=int(ctx.IntegerLiteral().getText()), literal_type="integer", span=self._span(ctx)
            )
        if ctx.StringLiteral() is not None:
            raw = ctx.StringLiteral().getText()
            try:
                value = json.loads(raw)
            except (json.JSONDecodeError, TypeError):
                value = raw[1:-1] if len(raw) >= 2 else raw
            return ast.LiteralExpression(value=value, literal_type="string", span=self._span(ctx))
        if ctx.TRUE() is not None or ctx.FALSE() is not None:
            return ast.LiteralExpression(
                value=ctx.TRUE() is not None, literal_type="boolean", span=self._span(ctx)
            )
        return ast.LiteralExpression(value=None, literal_type="null", span=self._span(ctx))

    def visitArrayLiteral(self, ctx: CompiscriptParser.ArrayLiteralContext) -> ast.ArrayExpression:
        return ast.ArrayExpression(
            elements=tuple(self._expression(item, ctx) for item in ctx.expression()),
            span=self._span(ctx),
        )

    def visitLeftHandSide(self, ctx: CompiscriptParser.LeftHandSideContext) -> ast.Expression:
        expression = self._expression(ctx.primaryAtom(), ctx)
        for suffix in ctx.suffixOperation():
            if suffix.LPAREN() is not None:
                arguments = self.visit(suffix.arguments()) if suffix.arguments() is not None else ()
                expression = ast.CallExpression(
                    callee=expression,
                    arguments=arguments,
                    span=ast.SourceSpan.merge(expression.span, self._span(suffix)),
                )
            elif suffix.LBRACK() is not None:
                expression = ast.IndexExpression(
                    collection=expression,
                    index=self._expression(suffix.expression(), suffix),
                    span=ast.SourceSpan.merge(expression.span, self._span(suffix)),
                )
            else:
                expression = ast.MemberExpression(
                    object=expression,
                    member=self._text(suffix.Identifier()),
                    span=ast.SourceSpan.merge(expression.span, self._span(suffix)),
                )
        return expression

    def visitPrimaryAtom(self, ctx: CompiscriptParser.PrimaryAtomContext) -> ast.Expression:
        if ctx.NEW() is not None:
            arguments = self.visit(ctx.arguments()) if ctx.arguments() is not None else ()
            return ast.NewExpression(
                class_name=self._text(ctx.Identifier()), arguments=arguments, span=self._span(ctx)
            )
        if ctx.THIS() is not None:
            return ast.ThisExpression(span=self._span(ctx))
        return ast.IdentifierExpression(name=self._text(ctx.Identifier()), span=self._span(ctx))

    def visitArguments(self, ctx: CompiscriptParser.ArgumentsContext) -> tuple[ast.Expression, ...]:
        return tuple(self._expression(item, ctx) for item in ctx.expression())

    def visitType(self, ctx: CompiscriptParser.TypeContext) -> ast.TypeRef:
        base_type = ctx.baseType()
        return ast.TypeRef(
            name=base_type.getText() if base_type is not None else "<faltante>",
            dimensions=len(ctx.LBRACK()),
            span=self._span(ctx),
        )
