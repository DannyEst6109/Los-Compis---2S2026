// Proyecto 3 · Herencia en MIPS
// Tres niveles de herencia, atributos heredados, redefinición de métodos,
// despacho dinámico (también desde un método de la superclase), arreglos de
// objetos de distintas clases y un parámetro sin tipo (búsqueda dinámica).
// Salida esperada: examples/salidas/mips_herencia.txt

class Empleado {
  let nombre: string;
  let salario: integer;

  function constructor(nombre: string, salario: integer) {
    this.nombre = nombre;
    this.salario = salario;
  }

  function bono(): integer {
    return 0;
  }

  // Despacho dinámico desde la superclase: bono() es el de la clase real.
  function pago(): integer {
    return this.salario + this.bono();
  }

  function puesto(): string {
    return "empleado";
  }

  function describir(): string {
    return nombre + " (" + puesto() + ")";
  }
}

class Gerente : Empleado {
  let equipo: integer = 0;

  function bono(): integer {
    return 100 * equipo;
  }

  function puesto(): string {
    return "gerente";
  }

  function contratar() {
    equipo = equipo + 1;
  }
}

class Director : Gerente {
  let acciones: integer;

  function constructor(nombre: string, salario: integer) {
    this.nombre = nombre;
    this.salario = salario * 2;
    this.acciones = 7;
  }

  function bono(): integer {
    return 1000 + acciones;
  }

  function puesto(): string {
    return "director";
  }
}

class Practicante : Empleado {
  function pago(): integer {
    return 50;
  }
}

let ana: Empleado = new Empleado("Ana", 1000);
let beto: Gerente = new Gerente("Beto", 2000);
beto.contratar();
beto.contratar();
beto.contratar();
let carla: Director = new Director("Carla", 3000);
let dani: Practicante = new Practicante("Dani", 999);

print(beto.nombre);
print(beto.equipo);
print(carla.salario);
print(carla.equipo);
print(carla.acciones);

let planilla: Empleado[] = [ana, beto, carla, dani];
let total: integer = 0;
foreach (e in planilla) {
  print(e.describir());
  total = total + e.pago();
}
print(total);

// Un Director visto como Empleado y como Gerente
let jefe: Empleado = carla;
print(jefe.bono());
let g: Gerente = carla;
g.contratar();
print(carla.equipo);
print(carla.bono());
print(beto.bono());

// Parámetro sin tipo: «nombre» y «puesto» están en posiciones distintas en
// Empleado y en Producto, así que se buscan según la clase del objeto.
class Producto {
  let codigo: integer;
  let nombre: string;

  function constructor(codigo: integer, nombre: string) {
    this.codigo = codigo;
    this.nombre = nombre;
  }

  function puesto(): string {
    return "producto";
  }
}

function etiqueta(x): string {
  return x.nombre + " -> " + x.puesto();
}

print(etiqueta(ana));
print(etiqueta(carla));
print(etiqueta(new Producto(7, "Lápiz")));

// ---------------------------------------------------------------------
// class Pasante : Estudiante { }
