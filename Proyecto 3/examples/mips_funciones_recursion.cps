// Proyecto 3 · Funciones, parámetros, recursión y funciones anidadas
// Ejecútelo desde la pestaña «Ejecución» (F6) para ver el árbol de activación.
// Salida esperada: examples/salidas/mips_funciones_recursion.txt

function potencia(base: integer, exponente: integer): integer {
  if (exponente == 0) {
    return 1;
  }
  return base * potencia(base, exponente - 1);
}

// Torres de Hanoi: cantidad de movimientos (dos llamadas recursivas)
function hanoi(n: integer, origen: integer, destino: integer, auxiliar: integer): integer {
  if (n == 0) {
    return 0;
  }
  let movimientos: integer = hanoi(n - 1, origen, auxiliar, destino);
  movimientos = movimientos + 1;
  return movimientos + hanoi(n - 1, auxiliar, destino, origen);
}

function sumaDigitos(n: integer): integer {
  if (n < 10) {
    return n;
  }
  return n % 10 + sumaDigitos(n / 10);
}

// Función anidada que modifica una variable de la función que la contiene
function contador(inicio: integer): integer {
  let cuenta: integer = inicio;
  function siguiente(): integer {
    cuenta = cuenta + 1;
    return cuenta;
  }
  siguiente();
  siguiente();
  return siguiente();
}

// Más de cuatro parámetros: todos viajan por la pila
function ponderada(a: integer, b: integer, c: integer, d: integer, e: integer, f: integer): integer {
  return a * 1 + b * 2 + c * 3 + d * 4 + e * 5 + f * 6;
}

print(potencia(2, 10));
print(hanoi(5, 1, 3, 2));
print(sumaDigitos(98765));
print(contador(10));
print(ponderada(1, 1, 1, 1, 1, 1));
print(potencia(3, 4) + sumaDigitos(potencia(2, 10)));

// ---------------------------------------------------------------------
// print(potencia(2));
