// Entrada válida: try/catch, incluido dentro de ciclos y funciones.

let datos: integer[] = [10, 20, 30];

try {
  print(datos[5]);
} catch (error) {
  print("Error atrapado: " + error);
}

// Un error en la función se atrapa en el try que hizo la llamada.
function dividir(a: integer, b: integer): integer {
  return a / b;
}

function seguro(a: integer, b: integer): integer {
  try {
    return dividir(a, b);
  } catch (e) {
    print(e);
  }
  return 0;
}

// break y continue dentro de try retiran el manejador antes de saltar.
let i: integer = 0;
while (i < 10) {
  i = i + 1;
  try {
    if (i == 2) {
      continue;
    }
    if (datos[i] > 15) {
      break;
    }
  } catch (fueraDeRango) {
    print("índice inválido");
  }
}

// try anidados.
try {
  try {
    print(datos[100]);
  } catch (interno) {
    print(datos[200]);
  }
} catch (externo) {
  print("externo: " + externo);
}

print(seguro(10, 0));
