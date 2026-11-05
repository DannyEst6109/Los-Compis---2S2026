// 04  Expresiones lógicas


let a: integer = 5;
let b: integer = 10;

let menor: boolean = a < b;
let menorIgual: boolean = a <= b;
let mayor: boolean = a > b;
let mayorIgual: boolean = a >= b;
let igual: boolean = a == b;
let distinto: boolean = a != b;

let ambos: boolean = a > 0 && b > 0;
let alguno: boolean = a > 100 || b > 5;
let negado: boolean = !(a < b);
let combinada: boolean = (a < b && b < 20) || !(a == 5);

// ---------------------------------------------------------------------
// let malo: boolean = 1 && true;
