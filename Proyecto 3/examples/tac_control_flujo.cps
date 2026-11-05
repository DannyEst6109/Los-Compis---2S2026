// Entrada válida: no se ejecuta; se analiza y traduce a TAC.
let total = 0;
let datos = [1, 2, 3];
for (let i = 0; i < 3; i = i + 1) {
    if (i == 1) { continue; }
    total = total + i;
}
foreach (dato in datos) {
    if (dato > 1 && dato < 4) { total = total + dato; }
}
while (total < 10) { total = total + 1; }
do { total = total - 1; } while (total > 9);
switch (total) {
    case 9: print("nueve"); break;
    case 10: print("diez"); break;
    default: print("otro");
}
let valido = total >= 0 || total == -1;
let mensaje = valido ? "válido" : "inválido";
print(mensaje);
