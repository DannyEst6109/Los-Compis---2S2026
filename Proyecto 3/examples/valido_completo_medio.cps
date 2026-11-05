// valido_completo_medio.cps
// Complejidad media: una clase simple (sin herencia), una función que
// recibe y recorre una lista, control de flujo básico y acceso a listas.
// Este archivo NO debe producir ningún diagnóstico léxico, sintáctico ni
// semántico.

class Persona {
  let nombre: string;
  let edad: integer;

  function constructor(nombre: string, edad: integer) {
    this.nombre = nombre;
    this.edad = edad;
  }

  function esMayorDeEdad(): boolean {
    return this.edad >= 18;
  }

  function saludo(): string {
    return "Hola, soy " + this.nombre;
  }
}

function promedio(valores: integer[]): integer {
  let suma: integer = 0;
  let cantidad: integer = 0;
  foreach (valor in valores) {
    suma = suma + valor;
    cantidad = cantidad + 1;
  }
  return suma / cantidad;
}

const EDAD_MINIMA: integer = 18;
let notas: integer[] = [80, 95, 70, 88];
let ana: Persona = new Persona("Ana", 20);
let promedioNotas: integer = promedio(notas);

if (ana.esMayorDeEdad()) {
  print(ana.saludo());
} else {
  print("Es menor de edad.");
}

let contador: integer = 0;
while (contador < notas[0] / 10) {
  contador = contador + 1;
}

print(promedioNotas);
print(contador);
print(EDAD_MINIMA);
