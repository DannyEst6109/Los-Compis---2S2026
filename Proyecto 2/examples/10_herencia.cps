// 10 Herencia


class Animal {
  let nombre: string;

  function constructor(nombre: string) {
    this.nombre = nombre;
  }

  function hablar(): string {
    return this.nombre + " hace ruido.";
  }

  function presentarse(): string {
    return "Soy " + this.nombre;
  }
}

class Perro : Animal {
  let raza: string = "criollo";

  function hablar(): string {
    return this.nombre + " ladra.";
  }
}

let perro: Perro = new Perro("Toby");
let animal: Animal = perro;
print(animal.hablar());
print(perro.presentarse());
print(perro.raza);

// ---------------------------------------------------------------------
// class Gato : Felino { }
