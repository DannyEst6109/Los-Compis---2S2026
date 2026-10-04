
// 13 Nuevas funcionalidades en la tabla de símbolos


let contador: integer = 1;
let bandera: boolean = true;
let texto: string = "hola";
let numeros: integer[] = [1, 2];

function area(base: integer, altura: integer): integer {
  let resultado: integer = base * altura;
  return resultado;
}

class Punto {
  let x: integer;
  let y: integer;

  function constructor(x: integer, y: integer) {
    this.x = x;
    this.y = y;
  }

  function suma(): integer {
    return this.x + this.y;
  }
}

let p: Punto = new Punto(3, 4);
print(area(p.x, p.y) + p.suma());

// ---------------------------------------------------------------------
// let contador: integer = 2;
