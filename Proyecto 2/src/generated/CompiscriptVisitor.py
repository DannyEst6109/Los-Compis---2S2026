# Generated from Compiscript.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .CompiscriptParser import CompiscriptParser
else:
    from CompiscriptParser import CompiscriptParser

# This class defines a complete generic visitor for a parse tree produced by CompiscriptParser.

class CompiscriptVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by CompiscriptParser#program.
    def visitProgram(self, ctx:CompiscriptParser.ProgramContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#statement.
    def visitStatement(self, ctx:CompiscriptParser.StatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#block.
    def visitBlock(self, ctx:CompiscriptParser.BlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#variableDeclaration.
    def visitVariableDeclaration(self, ctx:CompiscriptParser.VariableDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#constantDeclaration.
    def visitConstantDeclaration(self, ctx:CompiscriptParser.ConstantDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#typeAnnotation.
    def visitTypeAnnotation(self, ctx:CompiscriptParser.TypeAnnotationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#initializer.
    def visitInitializer(self, ctx:CompiscriptParser.InitializerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#expressionStatement.
    def visitExpressionStatement(self, ctx:CompiscriptParser.ExpressionStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#printStatement.
    def visitPrintStatement(self, ctx:CompiscriptParser.PrintStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#ifStatement.
    def visitIfStatement(self, ctx:CompiscriptParser.IfStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#whileStatement.
    def visitWhileStatement(self, ctx:CompiscriptParser.WhileStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#doWhileStatement.
    def visitDoWhileStatement(self, ctx:CompiscriptParser.DoWhileStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#forStatement.
    def visitForStatement(self, ctx:CompiscriptParser.ForStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#forInitializer.
    def visitForInitializer(self, ctx:CompiscriptParser.ForInitializerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#foreachStatement.
    def visitForeachStatement(self, ctx:CompiscriptParser.ForeachStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#breakStatement.
    def visitBreakStatement(self, ctx:CompiscriptParser.BreakStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#continueStatement.
    def visitContinueStatement(self, ctx:CompiscriptParser.ContinueStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#returnStatement.
    def visitReturnStatement(self, ctx:CompiscriptParser.ReturnStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#tryCatchStatement.
    def visitTryCatchStatement(self, ctx:CompiscriptParser.TryCatchStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#switchStatement.
    def visitSwitchStatement(self, ctx:CompiscriptParser.SwitchStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#switchCase.
    def visitSwitchCase(self, ctx:CompiscriptParser.SwitchCaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#defaultCase.
    def visitDefaultCase(self, ctx:CompiscriptParser.DefaultCaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#functionDeclaration.
    def visitFunctionDeclaration(self, ctx:CompiscriptParser.FunctionDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#parameters.
    def visitParameters(self, ctx:CompiscriptParser.ParametersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#parameter.
    def visitParameter(self, ctx:CompiscriptParser.ParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#classDeclaration.
    def visitClassDeclaration(self, ctx:CompiscriptParser.ClassDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#classMember.
    def visitClassMember(self, ctx:CompiscriptParser.ClassMemberContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#expression.
    def visitExpression(self, ctx:CompiscriptParser.ExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#assignmentExpression.
    def visitAssignmentExpression(self, ctx:CompiscriptParser.AssignmentExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#conditionalExpression.
    def visitConditionalExpression(self, ctx:CompiscriptParser.ConditionalExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#logicalOrExpression.
    def visitLogicalOrExpression(self, ctx:CompiscriptParser.LogicalOrExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#logicalAndExpression.
    def visitLogicalAndExpression(self, ctx:CompiscriptParser.LogicalAndExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#equalityExpression.
    def visitEqualityExpression(self, ctx:CompiscriptParser.EqualityExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#relationalExpression.
    def visitRelationalExpression(self, ctx:CompiscriptParser.RelationalExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#additiveExpression.
    def visitAdditiveExpression(self, ctx:CompiscriptParser.AdditiveExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#multiplicativeExpression.
    def visitMultiplicativeExpression(self, ctx:CompiscriptParser.MultiplicativeExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#unaryExpression.
    def visitUnaryExpression(self, ctx:CompiscriptParser.UnaryExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#primaryExpression.
    def visitPrimaryExpression(self, ctx:CompiscriptParser.PrimaryExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#literalExpression.
    def visitLiteralExpression(self, ctx:CompiscriptParser.LiteralExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#leftHandSide.
    def visitLeftHandSide(self, ctx:CompiscriptParser.LeftHandSideContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#primaryAtom.
    def visitPrimaryAtom(self, ctx:CompiscriptParser.PrimaryAtomContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#suffixOperation.
    def visitSuffixOperation(self, ctx:CompiscriptParser.SuffixOperationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#arguments.
    def visitArguments(self, ctx:CompiscriptParser.ArgumentsContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#arrayLiteral.
    def visitArrayLiteral(self, ctx:CompiscriptParser.ArrayLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#type.
    def visitType(self, ctx:CompiscriptParser.TypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by CompiscriptParser#baseType.
    def visitBaseType(self, ctx:CompiscriptParser.BaseTypeContext):
        return self.visitChildren(ctx)



del CompiscriptParser