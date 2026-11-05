"""Optimizaciones locales para MIPS de MARS sin saltos retardados."""

import re


# Los emisores usan registros con nombre y literales decimales.
_REGISTER = r"\$(?:zero|v[01]|a[0-3]|t[0-9]|s[0-7]|gp|sp|fp|ra)"
_IDENTITY = re.compile(
    rf"(?:addiu|sll) ({_REGISTER}), ({_REGISTER}), 0"
    rf"|(?:addu|subu) ({_REGISTER}), ({_REGISTER}), \$zero"
    rf"|addu ({_REGISTER}), \$zero, ({_REGISTER})"
)
_MOVE = re.compile(rf"move ({_REGISTER}), ({_REGISTER})")
_LI = re.compile(rf"li {_REGISTER}, -?\d+")
_JUMP = re.compile(r"j ([A-Za-z_][A-Za-z_0-9]*)")


def optimize_mips(lines: list[str]) -> list[str]:
    """Simplifica el texto emitido preservando etiquetas y comentarios.

    Cada regla opera sobre instrucciones completas. Las etiquetas, directivas
    e instrucciones ajenas cortan las reglas que necesitan adyacencia.
    """
    result = []
    previous = ""
    for line in lines:
        code = line.strip()
        if not code or code.startswith("#"):
            result.append(line)
            continue
        if code.endswith(":") and (jump := _JUMP.fullmatch(previous)) and jump[1] == code[:-1]:
            index = len(result) - 1
            while not result[index].strip() or result[index].lstrip().startswith("#"):
                index -= 1
            del result[index]

        # addiu con cero, desplazamiento de cero, suma con cero y resta de cero.
        if identity := _IDENTITY.fullmatch(code):
            dest, source = (group for group in identity.groups() if group is not None)
            code = f"move {dest}, {source}"
            line = line[:len(line) - len(line.lstrip())] + code
        # Un movimiento a sí mismo o la segunda de dos cargas idénticas.
        if (move := _MOVE.fullmatch(code)) and move[1] == move[2]:
            continue
        if code == previous and _LI.fullmatch(code):
            continue
        result.append(line)
        previous = code
    return result
