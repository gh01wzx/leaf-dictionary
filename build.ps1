$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
Set-Location -LiteralPath $taskRoot
$env:PYTHONPATH = Join-Path $taskRoot 'vendor'
# PyInstaller is not part of the repository: install it with `pip install pyinstaller`.
# Small files travel inside Leaf.exe. The two large dictionaries (about 180 MB)
# stay in the data folder next to Leaf.exe, so launching does not unpack them
# to a temporary folder every time.
$taskWeb = (Join-Path $taskRoot 'web') + ';web'
$taskManifest = (Join-Path $taskRoot 'data\manifest.json') + ';data'
$taskInsights = (Join-Path $taskRoot 'data\insights.json') + ';data'
$taskLicenses = (Join-Path $taskRoot 'licenses') + ';licenses'
foreach ($required in 'data\dictionary.sqlite3', 'data\learner.sqlite3') {
  if (-not (Test-Path -LiteralPath (Join-Path $taskRoot $required))) { throw "Missing $required" }
}
python -m PyInstaller --noconfirm --windowed --onefile --name Leaf --distpath $taskRoot --workpath (Join-Path $taskRoot 'build') --specpath (Join-Path $taskRoot 'build') --paths (Join-Path $taskRoot 'vendor') --hidden-import fsrs --exclude-module fsrs.optimizer --exclude-module torch --exclude-module pandas --exclude-module numpy --add-data $taskWeb --add-data $taskManifest --add-data $taskInsights --add-data $taskLicenses (Join-Path $taskRoot 'app.py')
if ($LASTEXITCODE -ne 0) { throw 'Packaging failed.' }
Write-Host 'Built Leaf.exe. Keep it next to the data and user_data folders.'
