# Componentes de terceros

Este proyecto incluye ANTLR 4.13.2 y su runtime para Python 3, distribuidos bajo licencia BSD de 3 cláusulas.

- Proyecto: ANTLR
- Sitio: https://www.antlr.org/
- Licencia: https://github.com/antlr/antlr4/blob/master/LICENSE.txt

El lexer y el parser de `src/generated` fueron producidos a partir de `grammar/Compiscript.g4` con ANTLR 4.13.2.

También incluye el simulador MARS 4.5 (`tools/Mars4_5.jar`), que se usa para ensamblar y ejecutar el código MIPS generado. Se distribuye bajo licencia MIT.

- Proyecto: MARS (MIPS Assembler and Runtime Simulator), Pete Sanderson y Kenneth Vollmar
- Sitio: https://github.com/dpetersanderson/MARS
- Licencia: MIT (el texto completo está en `MARSlicense.txt`, dentro del `.jar`)
