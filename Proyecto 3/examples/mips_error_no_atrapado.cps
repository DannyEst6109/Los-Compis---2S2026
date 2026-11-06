// Proyecto 3 · Error en tiempo de ejecución sin try/catch
// Sin un manejador, el programa muestra el error y termina.
// Salida esperada: examples/salidas/mips_error_no_atrapado.txt

function promedio(datos: integer[], cantidad: integer): integer {
  let suma: integer = 0;
  foreach (d in datos) {
    suma = suma + d;
  }
  return suma / cantidad;
}

let vacio: integer[] = [];
print(promedio([4, 8, 6], 3));
print(promedio(vacio, 0));
print("esto ya no se imprime");

// ---------------------------------------------------------------------
// print(promedio(vacio));
