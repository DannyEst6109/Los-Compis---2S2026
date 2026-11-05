
// 09  Clases y objetos

class Contador {
  let valor: integer = 0;

  function constructor(inicial: integer) {
    this.valor = inicial;
  }

  function incrementar(): integer {
    this.valor = this.valor + 1;
    return this.valor;
  }
}

let c: Contador = new Contador(5);
c.incrementar();
c.valor = c.valor * 2;
print(c.valor);

// ---------------------------------------------------------------------
// c.decrementar();
