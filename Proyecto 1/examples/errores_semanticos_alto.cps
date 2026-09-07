// errores_semanticos_alto.cps
// Complejidad alta: herencia multinivel, funciones anidadas (closures),
// recursión, listas multidimensionales, switch, ternario, do-while y
// foreach. Cada bloque contiene exactamente UN error semántico
// intencional. El archivo es válido léxica y sintácticamente en su
// totalidad.

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

function esPar(n: integer): boolean {
  if (n == 0) {
    return true;
  }
  // Error esperado: llamada recursiva con un argumento de tipo incorrecto.
  return esPar("uno");
}

function crearAcumulador(inicial: integer): integer {
  let total: integer = inicial;

  function sumar(cantidad: integer): integer {
    total = total + cantidad;
    return total;
  }

  // Error esperado: la función declara integer pero retorna boolean.
  return sumar(5) > 0;
}

let perro: Perro = new Perro("Toby");
let matriz: integer[][] = [[1, 2], [3, 4]];

// Error esperado: el índice de una lista debe ser integer, no string.
print(matriz[0]["uno"]);

switch (matriz[0][0]) {
  // Error esperado: el valor del case (string) no es comparable con el
  // tipo de la expresión del switch (integer).
  case "uno":
    print("uno");
  default:
    print("otro");
}

// Error esperado: las dos ramas del operador ternario tienen tipos distintos.
let resultado = true ? 10 : "diez";

// Error esperado: la condición del do-while no es de tipo boolean
// (se usa el objeto "perro" en vez de una comparación real).
do {
  print(perro.hablar());
} while (perro);

// Error esperado: "perro" no es una lista; "foreach" no se puede usar.
foreach (letra in perro) {
  print(letra);
}

// Error esperado: "Perro" no tiene un atributo "edad" (ni propio ni heredado).
print(perro.edad);

// Error esperado: "Animal" es una clase, no una función; falta "new".
Animal("Rex");

class Gato : Perro {
  function maullar(): string {
    // Error esperado: "sonidoFavorito" no existe en toda la cadena de
    // herencia (Gato -> Perro -> Animal).
    return this.sonidoFavorito;
  }
}
