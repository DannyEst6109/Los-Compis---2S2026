$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 "src\app.py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    & python "src\app.py"
} else {
    Write-Error "Python 3 no está instalado o no se encuentra en PATH."
}
