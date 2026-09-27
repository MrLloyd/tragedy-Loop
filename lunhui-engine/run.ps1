param([ValidateSet('install','check','test','typecheck','demo','baseline')][string]$Task = 'check')
$ErrorActionPreference = 'Stop'
$bundledNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin'
$bundledPnpm = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\bin\fallback\pnpm.cmd'
$oldPath = $env:PATH
Push-Location $PSScriptRoot
try {
  if (Test-Path -LiteralPath (Join-Path $bundledNode 'node.exe')) { $env:PATH = "$bundledNode;$env:PATH" }
  $major = [int]((& node --version).TrimStart('v').Split('.')[0])
  if ($major -lt 22) { throw '需要 Node.js 22 或更新版本。' }
  switch ($Task) {
    'typecheck' { & node './node_modules/typescript/bin/tsc' --noEmit }
    'test' { & node './node_modules/vitest/vitest.mjs' run }
    'demo' { & node './node_modules/tsx/dist/cli.mjs' 'apps/cli/demo.ts' }
    'baseline' { & node './node_modules/tsx/dist/cli.mjs' 'scripts/baseline.ts' }
    'check' {
      & node './node_modules/tsx/dist/cli.mjs' 'scripts/baseline.ts'
      if ($LASTEXITCODE -ne 0) { throw '规则基线检查失败' }
      & node './node_modules/prettier/bin/prettier.cjs' --check .
      if ($LASTEXITCODE -ne 0) { throw '格式检查失败' }
      & node './node_modules/typescript/bin/tsc' --noEmit
      if ($LASTEXITCODE -ne 0) { throw '类型检查失败' }
      & node './node_modules/vitest/vitest.mjs' run
    }
    'install' { if (Test-Path -LiteralPath $bundledPnpm) { & $bundledPnpm install } else { & pnpm.cmd install } }
  }
  if ($LASTEXITCODE -ne 0) { throw "任务失败：$Task，退出码 $LASTEXITCODE" }
} finally { $env:PATH = $oldPath; Pop-Location }
