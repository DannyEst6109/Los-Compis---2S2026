# Analizador Compiscript

Aplicación de escritorio para el análisis léxico y sintáctico de archivos `.cps`. Los analizadores fueron generados con ANTLR 4.13.2 y los diagnósticos se presentan en español con tipo, línea, columna, símbolo y descripción.

## Ejecución

En Windows, ejecute `iniciar.bat`. También puede iniciar la aplicación con:

```powershell
python src\app.py
```

La librería de ejecución de ANTLR está incluida en `src/vendor`; no se requiere instalar paquetes.

## Uso

1. Seleccione **Abrir archivo** y elija un archivo con extensión `.cps`.
2. Presione **Analizar** o `F5`.
3. Revise los diagnósticos en la tabla. Un doble clic lleva el cursor a la línea y columna indicadas.
4. Corrija el código y vuelva a analizarlo. `Ctrl+S` guarda los cambios.

Los archivos de prueba se encuentran en `examples`.

## Pruebas

```powershell
python -m unittest discover -s tests -v
```

## Regeneración

La gramática se encuentra en `grammar/Compiscript.g4`. Para regenerar el lexer y el parser se requiere Java 11 o superior:

```powershell
.\generar_analizadores.ps1
```

La aplicación realiza únicamente análisis léxico y sintáctico. No ejecuta el programa, no valida tipos y no genera código.
