// Entrada válida: funciones, parámetros, return, llamadas y recursión.
// No se ejecuta; se analiza y traduce a TAC.

function suma(a: integer, b: integer): integer {
  return a + b;
}

// Recursión simple.
function factorial(n: integer): integer {
  if (n <= 1) {
    return 1;
  }
  return n * factorial(n - 1);
}

// Recursión con dos llamadas por activación.
function fibonacci(n: integer): integer {
  if (n < 2) {
    return n;
  }
  return fibonacci(n - 1) + fibonacci(n - 2);
}

// Recursión mutua: esPar se usa antes de declarar esImpar.
function esPar(n: integer): boolean {
  if (n == 0) {
    return true;
  }
  return esImpar(n - 1);
}

function esImpar(n: integer): boolean {
  if (n == 0) {
    return false;
  }
  return esPar(n - 1);
}

// Procedimiento (sin tipo de retorno) con variables locales.
function imprimirRango(desde: integer, hasta: integer) {
  for (let i: integer = desde; i <= hasta; i = i + 1) {
    print(i);
  }
}

// Función anidada que usa variables de la función que la contiene.
function escalar(valores: integer[], factor: integer): integer {
  let total: integer = 0;
  function aplicar(x: integer): integer {
    return x * factor;
  }
  foreach (v in valores) {
    total = total + aplicar(v);
  }
  return total;
}

let resultado: integer = suma(factorial(5), fibonacci(6) * 2);
let par: boolean = esPar(10);
imprimirRango(1, 3);
print(escalar([1, 2, 3], suma(1, 1)));
if (esImpar(resultado) || par) {
  print("Resultado: " + "listo");
}
