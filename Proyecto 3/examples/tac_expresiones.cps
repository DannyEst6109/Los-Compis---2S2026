// Generación de TAC: expresiones, asignaciones y temporales.

let a: integer = 3;
let b: integer = 4;
let c: integer = 5;

// Precedencia: t1 = b * 5 ; t1 = a + t1 ; x = t1
let x: integer = a + b * 5;

// Árbol balanceado: necesita tres temporales vivos a la vez.
let y: integer = (a * b) + (a - c) * (b % 2);

// Cadena larga: un solo temporal reciclado.
let z: integer = a + b + c + a + b + c;

// Menos unario, relacionales y negación lógica.
let negativo: integer = -(a + b);
let esMenor: boolean = x < 10;
let noEsMenor: boolean = !(x < 10);
let iguales: boolean = a == b;

// Concatenación de strings.
let nombre: string = "Compiscript";
let saludo: string = "Hola " + nombre + "!";

// Arreglos.
let lista: integer[] = [1, 2, a + b];
let matriz: integer[][] = [[1, 2], [3, 4]];
lista[1] = lista[0] * -2;
let esquina: integer = matriz[1][0];

// Asignación encadenada y shadowing.
x = y = 7;
{
  let a: integer = 10;
  print(a + x);
}
print(a);
print(saludo);
