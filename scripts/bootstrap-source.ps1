$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
foreach ($file in @('src/cfra/CMakeLists.txt', 'src/cfra/cuBool/CMakeLists.txt', 'src/cfra/cuBool/deps/gtest/CMakeLists.txt')) {
    if (-not (Test-Path (Join-Path $root $file))) { throw "Missing source file: $file" }
}
Write-Output 'All sources are included. No download or patch application required.'
