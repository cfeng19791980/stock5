$ErrorActionPreference = "Stop"

# This recipe command is responsible for printing METRIC lines.
$global:LASTEXITCODE = 0
cd E:\stock5; python autoresearch_benchmark.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
