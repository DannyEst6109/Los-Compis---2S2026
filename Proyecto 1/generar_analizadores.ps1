$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot

if (-not (Get-Command java -ErrorAction SilentlyContinue)) {
    Write-Error "Se requiere Java 11 o superior para regenerar los analizadores."
}

Push-Location -LiteralPath "$projectRoot\grammar"
try {
    & java -jar "..\tools\antlr-4.13.2-complete.jar" `
        -Dlanguage=Python3 `
        -visitor `
        -no-listener `
        -o "..\src\generated" `
        "Compiscript.g4"
} finally {
    Pop-Location
}

Write-Host "Analizadores generados correctamente."
