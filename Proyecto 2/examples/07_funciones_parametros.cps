
// 07  Funciones y parámetros

function suma(a: integer, b: integer): integer {
  return a + b;
}

function saludar(nombre: string): string {
  return "Hola " + nombre;
}

function mostrar(valor: integer) {
  print(valor);
}

function calcular(): integer {
  let local: integer = 5;
  return local * 2;
}

let resultado: integer = suma(2, 3);
let texto: string = saludar("Ana");
mostrar(suma(resultado, calcular()));

// ---------------------------------------------------------------------
// let malo: integer = suma(1);
