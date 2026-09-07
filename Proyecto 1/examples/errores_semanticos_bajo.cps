// errores_semanticos_bajo.cps
// Complejidad baja: solo variables y expresiones sueltas a nivel global,
// sin funciones ni clases. Cada bloque de abajo contiene exactamente UN
// error semántico intencional. El archivo es válido léxica y
// sintácticamente en su totalidad; todos los diagnósticos esperados aquí
// son de tipo "Semántico".

let x: integer = 10;
let y: boolean = true;

// Error esperado: operando booleano en una operación aritmética (+).
let z: integer = x + y;

// Error esperado: operando entero en una operación lógica (&&).
let valido: boolean = x && true;

// Error esperado: comparación entre tipos incompatibles (integer vs string).
let esIgual: boolean = x == "diez";

// Error esperado: asignar un valor de tipo string a una variable integer.
x = "hola";

// Error esperado: uso de una variable que nunca fue declarada.
print(noExiste);

// Error esperado: redeclaración de "x" en el mismo ámbito (global).
let x: integer = 5;

// Error esperado: lista con elementos de tipos distintos.
let mezcla: integer[] = [1, "dos", 3];

// Error esperado: "break" usado fuera de cualquier ciclo.
break;
