class Producto {
  let nombre: string;
  let precio: integer;

  function constructor(nombre: string, precio: integer) {
    this.nombre = nombre;
    this.precio = precio;
  }

  function etiqueta(): string {
    return this.nombre + ": Q" + this.precio;
  }
}

class Oferta : Producto {
  let descuento: integer;

  function constructor(nombre: string, precio: integer, descuento: integer) {
    this.nombre = nombre;
    this.precio = precio;
    this.descuento = descuento;
  }

  function precioFinal(): integer {
    return this.precio - this.descuento;
  }
}

function totalCarrito(precios: integer[]): integer {
  let suma: integer = 0;
  foreach (p in precios) {
    suma = suma + p;
  }
  return suma;
}

function hayDescuento(descuento: integer): boolean {
  return descuento > 0;
}

const IVA: integer = 12 @;
let precios: integer[] = [50, 75, 100];
let producto1: Producto = new Producto("Mouse", 50);
let oferta1: Oferta = new Oferta("Teclado" 75, 10);

let activo: boolean = true
let total: integer = totalCarrito(precios);

if (hayDescuento(10) {
  print(oferta1.precioFinal());
} else {
  print(producto1.etiqueta());
}

while (total > 0) {
  total = total - 1;
}

print(total); #
