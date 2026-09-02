grammar Compiscript;

program
    : statement* EOF
    ;

statement
    : variableDeclaration
    | constantDeclaration
    | functionDeclaration
    | classDeclaration
    | expressionStatement
    | printStatement
    | block
    | ifStatement
    | whileStatement
    | doWhileStatement
    | forStatement
    | foreachStatement
    | tryCatchStatement
    | switchStatement
    | breakStatement
    | continueStatement
    | returnStatement
    ;

block
    : LBRACE statement* RBRACE
    ;

variableDeclaration
    : (LET | VAR) Identifier typeAnnotation? initializer? SEMI
    ;

constantDeclaration
    : CONST Identifier typeAnnotation? ASSIGN expression SEMI
    ;

typeAnnotation
    : COLON type
    ;

initializer
    : ASSIGN expression
    ;

expressionStatement
    : expression SEMI
    ;

printStatement
    : PRINT LPAREN expression RPAREN SEMI
    ;

ifStatement
    : IF LPAREN expression RPAREN statement (ELSE statement)?
    ;

whileStatement
    : WHILE LPAREN expression RPAREN statement
    ;

doWhileStatement
    : DO statement WHILE LPAREN expression RPAREN SEMI
    ;

forStatement
    : FOR LPAREN forInitializer? SEMI expression? SEMI expression? RPAREN statement
    ;

forInitializer
    : (LET | VAR) Identifier typeAnnotation? initializer?
    | expression
    ;

foreachStatement
    : FOREACH LPAREN Identifier IN expression RPAREN statement
    ;

breakStatement
    : BREAK SEMI
    ;

continueStatement
    : CONTINUE SEMI
    ;

returnStatement
    : RETURN expression? SEMI
    ;

tryCatchStatement
    : TRY block CATCH LPAREN Identifier RPAREN block
    ;

switchStatement
    : SWITCH LPAREN expression RPAREN LBRACE switchCase* defaultCase? RBRACE
    ;

switchCase
    : CASE expression COLON statement*
    ;

defaultCase
    : DEFAULT COLON statement*
    ;

functionDeclaration
    : FUNCTION Identifier LPAREN parameters? RPAREN (COLON type)? block
    ;

parameters
    : parameter (COMMA parameter)*
    ;

parameter
    : Identifier typeAnnotation?
    ;

classDeclaration
    : CLASS Identifier (COLON Identifier)? LBRACE classMember* RBRACE
    ;

classMember
    : functionDeclaration
    | variableDeclaration
    | constantDeclaration
    ;

expression
    : assignmentExpression
    ;

assignmentExpression
    : leftHandSide ASSIGN assignmentExpression
    | conditionalExpression
    ;

conditionalExpression
    : logicalOrExpression (QUESTION expression COLON expression)?
    ;

logicalOrExpression
    : logicalAndExpression (OR logicalAndExpression)*
    ;

logicalAndExpression
    : equalityExpression (AND equalityExpression)*
    ;

equalityExpression
    : relationalExpression ((EQUAL | NOT_EQUAL) relationalExpression)*
    ;

relationalExpression
    : additiveExpression ((LT | LE | GT | GE) additiveExpression)*
    ;

additiveExpression
    : multiplicativeExpression ((PLUS | MINUS) multiplicativeExpression)*
    ;

multiplicativeExpression
    : unaryExpression ((STAR | SLASH | PERCENT) unaryExpression)*
    ;

unaryExpression
    : (MINUS | NOT) unaryExpression
    | primaryExpression
    ;

primaryExpression
    : literalExpression
    | leftHandSide
    | LPAREN expression RPAREN
    ;

literalExpression
    : IntegerLiteral
    | StringLiteral
    | arrayLiteral
    | NULL
    | TRUE
    | FALSE
    ;

leftHandSide
    : primaryAtom suffixOperation*
    ;

primaryAtom
    : Identifier
    | NEW Identifier LPAREN arguments? RPAREN
    | THIS
    ;

suffixOperation
    : LPAREN arguments? RPAREN
    | LBRACK expression RBRACK
    | DOT Identifier
    ;

arguments
    : expression (COMMA expression)*
    ;

arrayLiteral
    : LBRACK (expression (COMMA expression)*)? RBRACK
    ;

type
    : baseType (LBRACK RBRACK)*
    ;

baseType
    : BOOLEAN
    | INTEGER
    | STRING
    | Identifier
    ;

LET: 'let';
VAR: 'var';
CONST: 'const';
FUNCTION: 'function';
CLASS: 'class';
PRINT: 'print';
IF: 'if';
ELSE: 'else';
WHILE: 'while';
DO: 'do';
FOR: 'for';
FOREACH: 'foreach';
IN: 'in';
BREAK: 'break';
CONTINUE: 'continue';
RETURN: 'return';
TRY: 'try';
CATCH: 'catch';
SWITCH: 'switch';
CASE: 'case';
DEFAULT: 'default';
NEW: 'new';
THIS: 'this';
NULL: 'null';
TRUE: 'true';
FALSE: 'false';
BOOLEAN: 'boolean';
INTEGER: 'integer';
STRING: 'string';

OR: '||';
AND: '&&';
EQUAL: '==';
NOT_EQUAL: '!=';
LE: '<=';
GE: '>=';
LT: '<';
GT: '>';
ASSIGN: '=';
PLUS: '+';
MINUS: '-';
STAR: '*';
SLASH: '/';
PERCENT: '%';
NOT: '!';
QUESTION: '?';
COLON: ':';
SEMI: ';';
COMMA: ',';
DOT: '.';
LPAREN: '(';
RPAREN: ')';
LBRACE: '{';
RBRACE: '}';
LBRACK: '[';
RBRACK: ']';

IntegerLiteral
    : [0-9]+
    ;

StringLiteral
    : '"' (EscapeSequence | ~["\\\r\n])* '"'
    ;

Identifier
    : [a-zA-Z_] [a-zA-Z0-9_]*
    ;

fragment EscapeSequence
    : '\\' ["\\nrt]
    ;

WS
    : [ \t\r\n]+ -> skip
    ;

LINE_COMMENT
    : '//' ~[\r\n]* -> skip
    ;

BLOCK_COMMENT
    : '/*' .*? '*/' -> skip
    ;
