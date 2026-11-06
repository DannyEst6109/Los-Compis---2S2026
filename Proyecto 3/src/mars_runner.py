"""Ejecución del ensamblador generado en el simulador MARS 4.5.

El compilador no necesita ejecutar el MIPS (la especificación permite
guardarlo y abrirlo en una herramienta externa), pero el IDE y las pruebas
pueden hacerlo para validar los programas. MARS se usa por línea de
comandos::

    java -jar Mars4_5.jar nc sm we ae2 se1 <pasos> programa.asm

* ``nc``: sin aviso de copyright; ``sm``: empieza en ``main``.
* ``we``: las advertencias del ensamblador son errores.
* ``ae2``/``se1``: código de salida 2 si no ensambla, 1 si falla la
  simulación.
* ``<pasos>``: máximo de instrucciones (evita colgar el IDE con un ciclo
  infinito).

Se busca el ``.jar`` en la variable de entorno ``MARS_JAR`` o en
``tools/Mars*.jar``; Java debe estar en ``PATH``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]
DEFAULT_STEPS = 5_000_000


def mars_jar() -> Path | None:
    override = os.environ.get("MARS_JAR")
    if override:
        return Path(override) if Path(override).is_file() else None
    jars = sorted((PROJECT / "tools").glob("[Mm]ars*.jar"))
    return jars[-1] if jars else None


def mars_available() -> bool:
    return shutil.which("java") is not None and mars_jar() is not None


def unavailable_reason() -> str:
    if shutil.which("java") is None:
        return "No se encontró Java en PATH (MARS es una aplicación Java)."
    return "No se encontró MARS: copie Mars4_5.jar en la carpeta tools/ o indique su ruta en MARS_JAR."


@dataclass(frozen=True, slots=True)
class MarsRun:
    output: str  # lo que imprimió el programa
    returncode: int
    stderr: str
    timed_out: bool = False
    step_limit: bool = False

    @property
    def ok(self) -> bool:
        return self.returncode == 0 and not self.timed_out and not self.step_limit

    @property
    def problem(self) -> str | None:
        """Descripción del fallo, o ``None`` si todo salió bien."""
        if self.timed_out:
            return "MARS no terminó a tiempo (posible ciclo infinito)."
        if self.step_limit:
            return "El programa alcanzó el máximo de instrucciones (posible ciclo infinito)."
        if self.returncode == 2:
            return "MARS no pudo ensamblar el programa:\n" + (self.stderr or self.output).strip()
        if self.returncode != 0:
            return "Error durante la simulación en MARS:\n" + (self.stderr or self.output).strip()
        return None


def run_mars(assembly: str, *, steps: int = DEFAULT_STEPS, timeout: float = 60) -> MarsRun:
    """Ensambla y ejecuta ``assembly`` (texto completo del ``.asm``)."""
    jar = mars_jar()
    java = shutil.which("java")
    if jar is None or java is None:
        raise RuntimeError(unavailable_reason())
    with tempfile.TemporaryDirectory() as folder:
        path = Path(folder) / "programa.asm"
        path.write_text(assembly, encoding="utf-8")
        command = [java, "-jar", str(jar), "nc", "sm", "we", "ae2", "se1", str(steps), str(path)]
        try:
            process = subprocess.run(
                command, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        except subprocess.TimeoutExpired as expired:
            output = expired.stdout if isinstance(expired.stdout, str) else ""
            return MarsRun(output, -1, "", timed_out=True)
    output = process.stdout
    step_limit = False
    marker = "Program terminated when maximum step limit"
    if marker in output:
        output = output[: output.index(marker)]
        step_limit = True
    return MarsRun(output.rstrip("\n"), process.returncode, process.stderr, step_limit=step_limit)
