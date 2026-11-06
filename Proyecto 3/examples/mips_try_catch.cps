// Proyecto 3 · try/catch en MIPS
// Errores en tiempo de ejecución atrapados en el mismo bloque, en funciones
// llamadas (se descartan sus marcos), con objetos nulos, dentro de ciclos con
// break/continue, con return dentro del try, try anidados y muchos errores
// seguidos sin dañar la pila.
// Salida esperada: examples/salidas/mips_try_catch.txt

let numeros: integer[] = [10, 20, 30];

// 1. Error directo en el bloque try: lo que sigue al error no se ejecuta
try {
  print(numeros[3]);
  print("no se imprime");
} catch (error) {
  print("1: " + error);
}

// 2. Error dentro de una cadena de llamadas recursivas
function profundidad(n: integer): integer {
  if (n == 0) {
    return 100 / n;
  }
  return profundidad(n - 1) + 1;
}

try {
  print(profundidad(5));
} catch (error) {
  print("2: " + error);
}

// 3. Acceso a un atributo de un objeto nulo
class Caja {
  let contenido: integer;
}

let caja: Caja = null;
try {
  caja.contenido = 5;
} catch (error) {
  print("3: " + error);
}

// 4. try dentro de un ciclo, con continue y break dentro del try
let errores: integer = 0;
let i: integer = 0;
while (i < 6) {
  i = i + 1;
  try {
    if (i == 2) {
      continue;
    }
    if (i == 5) {
      break;
    }
    print(numeros[i]);
  } catch (error) {
    errores = errores + 1;
  }
}
print(errores);

// 5. return dentro del try de una función
function dividirSeguro(a: integer, b: integer): integer {
  try {
    return a / b;
  } catch (error) {
    print("5: " + error);
  }
  return -1;
}

print(dividirSeguro(20, 4));
print(dividirSeguro(20, 0));

// 6. try anidados: un error dentro del catch interno lo atrapa el externo
try {
  try {
    print(numeros[-1]);
  } catch (interno) {
    print("6a: " + interno);
    print(10 / 0);
  }
} catch (externo) {
  print("6b: " + externo);
}

// 7. Después de atrapar muchos errores la pila sigue intacta
function factorial(n: integer): integer {
  if (n <= 1) {
    return 1;
  }
  return n * factorial(n - 1);
}

let atrapados: integer = 0;
for (let k: integer = 0; k < 100; k = k + 1) {
  try {
    profundidad(10);
  } catch (e) {
    atrapados = atrapados + 1;
  }
}
print(atrapados);
print(factorial(10));

// ---------------------------------------------------------------------
// print(error);
