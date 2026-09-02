class Vehiculo {
  let marca: string;
  let velocidad: integer;

  function constructor(marca: string, velocidad: integer) {
    this.marca = marca;
    this.velocidad = velocidad;
  }

  function describir(): string {
    return this.marca + " a " + this.velocidad + " km/h";
  }
}

class Auto : Vehiculo {
  let puertas: integer;

  function constructor(marca: string, velocidad: integer, puertas: integer) {
    this.marca = marca;
    this.velocidad = velocidad
    this.puertas = puertas;
  }

  function resumen(): string {
    return this.describir() + " con " + this.puertas + " puertas";
  }
}

function acelerar(velocidad: integer, incremento: integer): integer {
  return velocidad + incremento;
}

function esRapido(velocidad: integer): boolean {
  return velocidad > 120;
}

const LIMITE: integer = 120;
let velocidades: integer[] = [80, 150, 200];
let auto1: Vehiculo = new Auto("Toyota", 90, 4);
let auto2: Auto = new Auto("Mazda" 100, 4);

let total: integer = 0;
let promedio integer = 0;

if (total > LIMITE {
  print("excede el limite");
} else {
  print("dentro del limite");
}

for (let i: integer = 0; i < 3; i = i + 1) {
  total = total + velocidades[i];
}

foreach (v in velocidades) {
  if (esRapido(v)) print(v);
}

switch (total)
  case 0:
    print("sin datos");
  default:
    print(auto2.resumen());
}
