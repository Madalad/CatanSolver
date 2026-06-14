# Dev shell for CatanSolver.
#
# A venv built from Anaconda's Python lacks OpenSSL on its PATH, so pip/HTTPS
# fail with "the ssl module is not available". Prepend Anaconda's Library\bin,
# then activate the venv. Dot-source this: `. .\scripts\dev-shell.ps1`
$Anaconda = "C:\Users\ollie\anaconda3"
$env:PATH = "$Anaconda\Library\bin;$Anaconda;" + $env:PATH
& "$PSScriptRoot\..\.venv\Scripts\Activate.ps1"
Write-Host "catansolver dev shell ready (venv active, OpenSSL on PATH)."
