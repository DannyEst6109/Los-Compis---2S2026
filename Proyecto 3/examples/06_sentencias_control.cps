
// 06  Sentencias de control


let n: integer = 0;
let total: integer = 0;

if (n == 0) {
  total = 1;
} else {
  total = 2;
}

while (n < 3) {
  n = n + 1;
}

do {
  n = n - 1;
} while (n > 0);

for (let i: integer = 0; i < 5; i = i + 1) {
  if (i == 1) continue;
  if (i == 3) break;
  total = total + i;
}

foreach (x in [1, 2, 3]) {
  total = total + x;
}

switch (total) {
  case 1:
    print("uno");
    break;
  case 2:
    print("dos");
  default:
    print("otro");
}

let mensaje: string = total > 2 ? "grande" : "pequeño";

// ---------------------------------------------------------------------
// while (n) { n = n - 1; }
