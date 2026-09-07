// errores_semanticos_medio.cps
// Complejidad media: funciones con parámetros y tipo de retorno, y una
// clase simple (sin herencia). Cada bloque contiene exactamente UN error
// semántico intencional. El archivo es válido léxica y sintácticamente
// en su totalidad.

function sumar(a: integer, b: integer): integer {
  return a + b;
}

function saludar(nombre: string): string {
  return "Hola " + nombre;
}

// Error esperado: cantidad de argumentos incorrecta (sumar espera 2).
let resultado1: integer = sumar(5);

// Error esperado: tipo de argumento incorrecto (se esperaba integer).
let resultado2: integer = sumar(5, "diez");

function obtenerEdad(): integer {
  // Error esperado: el valor de retorno no coincide con el tipo declarado.
  return "veinte";
}

class Estudiante {
  let nombre: string;
  let promedio: integer;

  function constructor(nombre: string, promedio: integer) {
    this.nombre = nombre;
    this.promedio = promedio;
  }

  function aprobado(): boolean {
    return this.promedio >= 61;
  }
}

let carlos: Estudiante = new Estudiante("Carlos", 75);

// Error esperado: acceso a un atributo que no existe en la clase.
print(carlos.edad);

// Error esperado: llamada a un método que no existe en la clase.
carlos.graduarse();

// Error esperado: cantidad de argumentos incorrecta en el constructor.
let maria: Estudiante = new Estudiante("Maria");

// Error esperado: uso de "this" fuera de una clase.
print(this);

let numero: integer = 10;

// Error esperado: "numero" no es una función, no se puede invocar.
numero();

// Error esperado: "numero" no es una lista, no se puede indexar.
print(numero[0]);

let lista: integer[] = [1, 2, 3];

// Error esperado: el índice de una lista debe ser integer, no string.
print(lista["cero"]);

function procesar(): integer {
  return 1;
  // Error esperado: código muerto, esta instrucción nunca se ejecuta.
  print("esto nunca se ejecuta");
}

// Error esperado: "sumar" ya fue declarada antes en este mismo ámbito.
function sumar(x: integer): integer {
  return x;
}
