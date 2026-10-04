// 11 try / catch

let lista: integer[] = [1, 2, 3];

try {
  print(lista[10]);
} catch (err) {
  print("Error atrapado: " + err);
}

function dividir(a: integer, b: integer): integer {
  return a / b;
}

try {
  print(dividir(10, 0));
} catch (e) {
  print("No se pudo dividir: " + e);
}

// ---------------------------------------------------------------------
// print(err);
