param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe"
)

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

& $PythonExe -m pip install -e ".[build]"
& $PythonExe -m PyInstaller `
    --noconfirm `
    --clean `
    --windowed `
    --name "CodexBridgeGUI" `
    --hidden-import "tkinter" `
    codexbridge_gui.py

Write-Host "Build completed. Output: dist\CodexBridgeGUI"

