// Proyecto 3 · Sentencias de control en MIPS
// if/else anidados, while, do-while, for, foreach, switch con fall-through,
// break, continue, ciclos anidados, ternario y cortocircuito.
// Salida esperada: examples/salidas/mips_control_flujo.txt

// if/else anidados dentro de una función
function clasificar(n: integer): string {
  if (n < 0) {
    return "negativo";
  } else {
    if (n == 0) {
      return "cero";
    } else {
      if (n % 2 == 0) {
        return "par";
      } else {
        return "impar";
      }
    }
  }
}

print(clasificar(-4));
print(clasificar(0));
print(clasificar(7));
print(clasificar(10));

// while con break y continue: impares menores que 20, sin el 9
let i: integer = 0;
let suma: integer = 0;
while (true) {
  i = i + 1;
  if (i >= 20) {
    break;
  }
  if (i % 2 == 0) {
    continue;
  }
  if (i == 9) {
    continue;
  }
  suma = suma + i;
}
print(suma);

// do-while: el cuerpo se ejecuta antes de evaluar la condición
let n: integer = 100;
let vueltas: integer = 0;
do {
  vueltas = vueltas + 1;
  n = n / 2;
} while (n > 10);
print(vueltas);
print(n);

// for anidados: break sale sólo del ciclo interno, continue salta a la actualización
let pares: integer = 0;
for (let a: integer = 0; a < 5; a = a + 1) {
  for (let b: integer = 0; b < 10; b = b + 1) {
    if (b > 4) {
      break;
    }
    if (b <= a) {
      continue;
    }
    if (a + b == 5) {
      continue;
    }
    pares = pares + 1;
  }
}
print(pares);

// foreach anidados sobre una matriz: suma de la diagonal
let matriz: integer[][] = [[1, 2, 3], [4, 5, 6], [7, 8, 9]];
let diagonal: integer = 0;
let fila: integer = 0;
foreach (renglon in matriz) {
  let columna: integer = 0;
  foreach (valor in renglon) {
    if (columna != fila) {
      columna = columna + 1;
      continue;
    }
    diagonal = diagonal + valor;
    columna = columna + 1;
  }
  fila = fila + 1;
}
print(diagonal);

// switch dentro de un for: fall-through, break del switch, continue del for y default
for (let k: integer = 1; k <= 4; k = k + 1) {
  switch (k) {
    case 1:
      print("uno");
    case 2:
      print("uno o dos");
      break;
    case 3:
      print("tres");
      continue;
    default:
      print("otro");
  }
  print("fin de vuelta");
}

// Cortocircuito: la división no se evalúa cuando el divisor es 0
let divisor: integer = 0;
let seguro: boolean = divisor != 0 && 10 / divisor > 1;
print(seguro);
print(divisor == 0 || 10 / divisor > 1);

// Ternario
let tamano: string = suma > 50 ? "grande" : "pequeña";
print(tamano);

// ---------------------------------------------------------------------
// while (suma) { print(suma); }
