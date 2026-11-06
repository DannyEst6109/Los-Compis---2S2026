// Proyecto 3 · Variables, constantes, expresiones aritméticas y lógicas, y arreglos
// Salida esperada: examples/salidas/mips_basicos.txt

const LIMITE: integer = 10;
let a: integer = 7;
let b: integer = 3;
let activo: boolean = true;
let nombre: string = "Compiscript";
let nulo = null;

// Aritméticas: precedencia, agrupación, división entera, módulo y menos unario
print(a + b * 2);
print((a + b) * 2);
print(a - b - 1);
print(a / b);
print(a % b);
print(-a + LIMITE);

// Lógicas y relacionales (los boolean se imprimen como 1 y 0)
print(a > b && b > 0);
print(!(a < b) || false);
print(a == 7 && b != 3);
print(activo);
activo = !activo;
print(activo);

// Cadenas y null
print(nombre + " 2026");
print(nulo);

// Arreglos: lectura, escritura, matrices y foreach
let lista: integer[] = [5, 3, 8, 1];
lista[1] = lista[0] + lista[2];
print(lista[1]);
let matriz: integer[][] = [[1, 2], [3, 4]];
matriz[1][0] = matriz[0][1] * 10;
print(matriz[1][0]);
let total: integer = 0;
foreach (x in lista) {
  total = total + x;
}
print(total);
let palabras: string[] = ["hola", "mundo"];
print(palabras[0] + " " + palabras[1]);

// ---------------------------------------------------------------------
// LIMITE = 5;
