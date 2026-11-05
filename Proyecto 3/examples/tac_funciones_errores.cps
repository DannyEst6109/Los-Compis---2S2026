// Entrada inválida: varios errores de funciones, clases y llamadas.
// Debe reportarlos todos y no generar código intermedio.

function suma(a: integer, b: integer): integer {
  return a + b;
}

function saludo(): string {
  return 10;
}

class Animal {
  let nombre: string;
  function hablar(): string {
    return this.nombre;
  }
}

let x: integer = suma(1);
let y: integer = suma("uno", 2);
let z = noExiste(3);
let a: Animal = new Animal();
print(a.volar());
let n: integer = x();
let c: Gato = new Gato();
return 5;
