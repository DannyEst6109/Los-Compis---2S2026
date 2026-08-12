class Animal {
  let nombre: string;

  function constructor(nombre: string) {
    this.nombre = nombre;
  }

  function hablar(): string {
    return this.nombre + " hace ruido.";
  }
}

class Perro : Animal {
  function hablar(): string {
    return this.nombre + " ladra.";
  }
}

function factorial(n: integer): integer {
  if (n <= 1) return 1;
  return n * factorial(n - 1);
}

function crearContador(): integer {
  function siguiente(): integer {
    return 1;
  }
  return siguiente();
}

const LIMITE: integer = 5;
let perro: Perro = new Perro("Toby");
let animal: Animal = new Animal("Rex");
let notas: integer[] = [90, 85, 100];
let matriz: integer[][] = [[1, 2], [3, 4]];
let total: integer = 0;
var activo: boolean = true;
let vacio = null;
let estado: string = activo && !(total < 0 || total > 100) ? "válido" : "inválido";

if (activo) {
  print(estado);
} else {
  print("inactivo");
}

{
  let local: integer = crearContador();
  print(local);
}

for (let i: integer = 0; i < LIMITE; i = i + 1) {
  total = total + i;
}

foreach (nota in notas) {
  if (nota < 60) continue;
  if (nota == 100) break;
  print(nota);
}

do {
  total = total - 1;
} while (total > 10);

while (total < 10) {
  total = total + 1;
}

switch (total) {
  case 10:
    print("diez");
  default:
    print("otro");
}

try {
  print(matriz[0][1]);
} catch (err) {
  print("Error: " + err);
}

print(perro.hablar());
print(animal.hablar());
print(factorial(5));
