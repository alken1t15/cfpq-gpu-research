$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$target = Join-Path $root 'src/cfra'
if (Test-Path $target) { throw "Source directory already exists: $target" }
git clone https://github.com/vano105/cfra.git $target
if ($LASTEXITCODE -ne 0) { throw 'Clone failed' }
git -C $target checkout -b fix/indexed-template-expansion 3bc9794a509ca2f40c82b04e6c31e21ef9d1dbf1
if ($LASTEXITCODE -ne 0) { throw 'Checkout failed' }
git -C $target submodule update --init --recursive
if ($LASTEXITCODE -ne 0) { throw 'Submodule initialization failed' }
foreach ($patch in (Get-ChildItem (Join-Path $root 'patches') -Filter '*.patch' | Sort-Object Name)) {
    git -C $target am $patch.FullName
    if ($LASTEXITCODE -ne 0) { throw 'Patch failed; inspect git am status in src/cfra' }
}
