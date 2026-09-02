class Persona {
  let nombre: string;
  let edad: integer;

  function constructor(nombre: string, edad: integer) {
    this.nombre = nombre;
    this.edad = edad;
  }

  function saludo(): string {
    return "Hola, soy " + this.nombre;
  }
}

class Estudiante : Persona {
  let carrera: string;

  function constructor(nombre: string, edad: integer, carrera: string) {
    this.nombre = nombre;
    this.edad = edad;
    this.carrera = carrera;
  }

  function describir(): string {
    return this.nombre + " estudia " + this.carrera;
  }
}

function promedio(notas: integer[]): integer {
  let suma: integer = 0;
  foreach (nota in notas) {
    suma = suma + nota;
  }
  return suma / 3;
}

function esAprobado(nota: integer): boolean {
  return nota >= 61;
}

const NOTA_MINIMA: integer = 61 @;
let activo: boolean = true;&
let notas: integer[] = [70, 85, 90];
let persona1: Persona = new Persona("Carlos", 30);
let persona2: Estudiante = new Estudiante("Ana", 21, "Ingeniería");

let contador: integer = 0 $;
let doble: integer = contador * 2;

if (activo) {
  print(persona1.saludo());
} else {
  print("inactivo");
}

for (let i: integer = 0; i < 3; i = i + 1) {
  contador = contador + i;
}

switch (contador) {
  case 0:
    print("cero");
  default:
    print("otro");
}

print(persona2.describir());
print(promedio(notas));
print(esAprobado(70)); #
