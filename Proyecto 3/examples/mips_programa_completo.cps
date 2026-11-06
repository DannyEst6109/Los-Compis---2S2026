// Proyecto 3 · Programa completo: sistema de calificaciones
// Combina clases, herencia, despacho dinámico, arreglos de objetos, ciclos
// anidados (ordenamiento burbuja), switch, recursión y try/catch.
// Salida esperada: examples/salidas/mips_programa_completo.txt

class Estudiante {
  let nombre: string;
  let notas: integer[];
  let cantidad: integer;

  function constructor(nombre: string, notas: integer[], cantidad: integer) {
    this.nombre = nombre;
    this.notas = notas;
    this.cantidad = cantidad;
  }

  function promedio(): integer {
    let suma: integer = 0;
    foreach (nota in notas) {
      suma = suma + nota;
    }
    return suma / cantidad;
  }

  function tipo(): string {
    return "regular";
  }
}

class Becado : Estudiante {
  let extra: integer = 5;

  // Los atributos heredados se usan con «this.».
  function promedio(): integer {
    let suma: integer = 0;
    foreach (nota in this.notas) {
      suma = suma + nota;
    }
    let resultado: integer = suma / this.cantidad + extra;
    if (resultado > 100) {
      return 100;
    }
    return resultado;
  }

  function tipo(): string {
    return "becado";
  }
}

function letra(nota: integer): string {
  let resultado: string = "F";
  switch (nota / 10) {
    case 10:
    case 9:
      resultado = "A";
      break;
    case 8:
      resultado = "B";
      break;
    case 7:
      resultado = "C";
      break;
    default:
      resultado = "F";
  }
  return resultado;
}

function mcd(a: integer, b: integer): integer {
  if (b == 0) {
    return a;
  }
  return mcd(b, a % b);
}

// Ordenamiento burbuja de mayor a menor promedio
function ordenar(lista: Estudiante[], n: integer) {
  for (let i: integer = 0; i < n - 1; i = i + 1) {
    for (let j: integer = 0; j < n - 1 - i; j = j + 1) {
      if (lista[j].promedio() < lista[j + 1].promedio()) {
        let temporal: Estudiante = lista[j];
        lista[j] = lista[j + 1];
        lista[j + 1] = temporal;
      }
    }
  }
}

let grupo: Estudiante[] = [
  new Estudiante("Ana", [90, 85, 100], 3),
  new Becado("Beto", [70, 75, 80], 3),
  new Estudiante("Carla", [60, 72, 81], 3),
  new Becado("Dani", [99, 98, 100], 3)
];

ordenar(grupo, 4);
let aprobados: integer = 0;
foreach (e in grupo) {
  let p: integer = e.promedio();
  print(e.nombre + " [" + e.tipo() + "] " + letra(p));
  print(p);
  if (p >= 75) {
    aprobados = aprobados + 1;
  }
}
print(aprobados);
print(mcd(84, 36));

let sinNotas: integer[] = [];
let nadie: Estudiante = new Estudiante("Nadie", sinNotas, 0);
try {
  print(nadie.promedio());
} catch (error) {
  print("No se pudo calcular: " + error);
}

try {
  print(grupo[4].nombre);
} catch (error) {
  print("No existe: " + error);
}

// ---------------------------------------------------------------------
// let x: integer = letra(90);
