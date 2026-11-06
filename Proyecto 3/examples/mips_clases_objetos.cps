// Proyecto 3 · Clases y objetos en MIPS
// Creación de objetos, lectura y escritura de atributos, atributos con valor
// inicial, constructores, métodos que usan this (o el atributo sin this),
// objetos dentro de objetos y atributos nulos.
// Salida esperada: examples/salidas/mips_clases_objetos.txt

class Punto {
  let x: integer;
  let y: integer;

  function constructor(x: integer, y: integer) {
    this.x = x;
    this.y = y;
  }

  function mover(dx: integer, dy: integer) {
    this.x = this.x + dx;
    this.y = this.y + dy;
  }

  function distancia(otro: Punto): integer {
    let dx: integer = this.x - otro.x;
    let dy: integer = this.y - otro.y;
    if (dx < 0) {
      dx = -dx;
    }
    if (dy < 0) {
      dy = -dy;
    }
    return dx + dy;
  }
}

let p: Punto = new Punto(1, 2);
let q: Punto = new Punto(4, -2);
print(p.x);
print(p.y);
p.mover(2, 3);
print(p.x);
print(p.y);
print(p.distancia(q));
q.x = q.x * 10;
print(q.x);

class CuentaBancaria {
  let titular: string;
  let saldo: integer = 0;
  let activa: boolean = true;
  let movimientos: integer = 0;

  function constructor(titular: string) {
    this.titular = titular;
  }

  function depositar(monto: integer): integer {
    saldo = saldo + monto;
    movimientos = movimientos + 1;
    return saldo;
  }

  function retirar(monto: integer): boolean {
    if (monto > saldo) {
      return false;
    }
    this.saldo = this.saldo - monto;
    this.movimientos = this.movimientos + 1;
    return true;
  }
}

let cuenta: CuentaBancaria = new CuentaBancaria("Ana");
print(cuenta.titular);
print(cuenta.saldo);
print(cuenta.depositar(500));
print(cuenta.retirar(800));
print(cuenta.retirar(200));
print(cuenta.saldo);
print(cuenta.movimientos);
print(cuenta.activa);
cuenta.activa = false;
print(cuenta.activa);

// Objetos dentro de objetos: una lista enlazada
class Nodo {
  let valor: integer;
  let siguiente: Nodo;

  function constructor(valor: integer, siguiente: Nodo) {
    this.valor = valor;
    this.siguiente = siguiente;
  }
}

class Lista {
  let cabeza: Nodo;
  let tamano: integer = 0;

  function agregar(valor: integer) {
    this.cabeza = new Nodo(valor, this.cabeza);
    this.tamano = this.tamano + 1;
  }

  function sumar(): integer {
    let total: integer = 0;
    let actual: Nodo = this.cabeza;
    while (actual != null) {
      total = total + actual.valor;
      actual = actual.siguiente;
    }
    return total;
  }
}

let lista: Lista = new Lista();
print(lista.cabeza);
for (let i: integer = 1; i <= 10; i = i + 1) {
  lista.agregar(i * i);
}
print(lista.tamano);
print(lista.sumar());
print(lista.cabeza.valor);
print(lista.cabeza.siguiente.valor);

// ---------------------------------------------------------------------
// print(p.z);
