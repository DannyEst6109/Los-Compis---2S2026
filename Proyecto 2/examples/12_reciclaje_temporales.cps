// 12 · Reciclaje de variables temporales

let a: integer = 1;
let b: integer = 2;
let c: integer = 3;
let d: integer = 4;

let cadena: integer = a + b + c + d;
let balanceado: integer = (a * b) + (c * d);
let profundo: integer = (a + b) * (c - d) - (a * c) / (b + d);

function cuadradoDeSuma(x: integer, y: integer): integer {
  return (x + y) * (x + y);
}

let r: integer = cuadradoDeSuma(a, b) + cuadradoDeSuma(c, d);

// ---------------------------------------------------------------------
// let malo: integer = (a + b) * true;
