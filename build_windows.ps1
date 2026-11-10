# Create self-contained FolderExporter.exe for Windows 10 x64.
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
py -3.11 -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 for Windows is required.' }
py -3.11 -m pip install -r requirements-windows.txt
if ($LASTEXITCODE -ne 0) { throw 'Could not install source dependencies.' }
foreach ($test in @('selftest.py','integration_test.py','media_catalog_test.py','studio_link_test.py','workflow_test.py','workflow10_test.py')) {
  py -3.11 $test
  if ($LASTEXITCODE -ne 0) { throw "Test failed: $test" }
}
py -3.11 -m PyInstaller --noconfirm --clean --windowed --onefile --name FolderExporter --icon FolderExporter.ico --add-data "folder.png;." --add-data "WORKFLOW_MANUAL.md;." --collect-all psd_tools --collect-all clipparse app.py
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller packaging failed.' }
Write-Host 'EXE ready: dist\FolderExporter.exe'
