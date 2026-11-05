// Entrada válida: clases, objetos, atributos con valor inicial, this,
// herencia, redefinición de métodos y despacho dinámico.

class Figura {
  let nombre: string = "figura";
  let lados: integer = 0;

  function constructor(nombre: string) {
    this.nombre = nombre;
  }

  function area(): integer {
    return 0;
  }

  function describir(): string {
    // Atributo nombrado sin «this.»: se traduce como this.nombre.
    return "Figura " + nombre;
  }

  function esGrande(): boolean {
    // «area()» sin this: se despacha según la clase real del objeto.
    return area() > 10;
  }

  function crecer(veces: integer) {
    lados = lados + veces;
  }
}

class Rectangulo : Figura {
  let ancho: integer;
  let alto: integer;

  function constructor(ancho: integer, alto: integer) {
    this.nombre = "rectángulo";
    this.ancho = ancho;
    this.alto = alto;
    this.lados = 4;
  }

  function area(): integer {
    return this.ancho * this.alto;
  }
}

class Cuadrado : Rectangulo {
  let esCuadrado: boolean = true;

  function area(): integer {
    return this.ancho * this.ancho;
  }
}

let figura: Figura = new Figura("genérica");
let rect: Rectangulo = new Rectangulo(3, 4);
let cuadro: Figura = new Cuadrado(5, 5);

print(figura.describir());
print(rect.area());
print(cuadro.area());
print(cuadro.esGrande());
rect.crecer(2);
rect.alto = rect.alto + 1;
print(rect.lados);
print(new Rectangulo(1, 2).area());
