# install.ps1 - Windows PowerShell installer (parallel to install.sh)
# Usage:  .\install.ps1 <adapter-name> [target-dir] [-NewProject NAME] [-Yes] [-Reconfigure] [-Force]
#   adapter-name:     claude-code | cursor | windsurf | opencode | openclient | hermes | standalone-python
#   target-dir:       where your project lives (default: current dir)
#   -NewProject NAME  create a fresh dir NAME, git init it, seed .gitignore
#                     and README, then install into it. Shortcut for "I'm
#                     starting something from zero."
#   -Yes              accept all wizard defaults (safe for CI)
#   -Reconfigure      re-run the wizard on an existing project
#   -Force            overwrite even customized PREFERENCES.md

[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Adapter,

    [Parameter(Position = 1)]
    [string]$TargetDir = (Get-Location).Path,

    [string]$NewProject = "",
    [switch]$Yes,
    [switch]$Reconfigure,
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
$Here = Split-Path -Parent $MyInvocation.MyCommand.Path

$ValidAdapters = @(
    'claude-code', 'cursor', 'windsurf',
    'opencode', 'openclient', 'hermes',
    'standalone-python'
)
if ($Adapter -notin $ValidAdapters) {
    Write-Error "unknown adapter '$Adapter'. valid: $($ValidAdapters -join ' ')"
    exit 1
}

$Src = Join-Path $Here "adapters/$Adapter"
if (-not (Test-Path $Src -PathType Container)) {
    Write-Error "adapter '$Adapter' not found at $Src"
    exit 1
}

# ── -NewProject bootstrap ──────────────────────────────────────────────
# Resolve relative names against the caller's CWD so `.\install.ps1
# claude-code -NewProject foo` lands `foo\` next to where you ran it from.
# Refuse to bootstrap over a non-empty dir so --new-project always means a
# clean slate; pass target-dir positionally if you meant to retarget.
if ($NewProject) {
    if ([System.IO.Path]::IsPathRooted($NewProject)) {
        $TargetDir = $NewProject
    } else {
        $TargetDir = Join-Path (Get-Location).Path $NewProject
    }

    if ((Test-Path $TargetDir) -and (Get-ChildItem -Force $TargetDir | Select-Object -First 1)) {
        Write-Error "$TargetDir already exists and is non-empty; refusing to bootstrap over it. Drop -NewProject and pass the path positionally if that's what you want."
        exit 1
    }
    New-Item -ItemType Directory -Path $TargetDir -Force | Out-Null

    if (Get-Command git -ErrorAction SilentlyContinue) {
        git -C $TargetDir init -q
        Write-Host "  + git init"
    } else {
        Write-Warning "git not on PATH; skipping git init"
    }

    $giPath = Join-Path $TargetDir '.gitignore'
    if (-not (Test-Path $giPath)) {
        @'
# env / secrets
.env
.env.local
*.key

# python
__pycache__/
*.py[cod]
.venv/
venv/
.pytest_cache/

# editor
.DS_Store
.idea/
.vscode/
*.swp

# runtime logs (auto_dream writes here)
.agent/memory/dream.log
*.log

# keep the brain, ignore generated artefacts inside it
.agent/memory/.index/
.agent/memory/.index/**
.agent/memory/working/REVIEW_QUEUE.md
.agent/memory/working/COVERAGE.md
.agent/memory/working/coverage.json
.agent/**/__pycache__/
.agent/**/*.py[cod]
'@ | Set-Content -NoNewline -Path $giPath
        Write-Host "  + .gitignore"
    }

    $readmePath = Join-Path $TargetDir 'README.md'
    if (-not (Test-Path $readmePath)) {
        $projName = Split-Path -Leaf $TargetDir
        @"
# $projName

Bootstrapped with [agentic-stack-op](https://github.com/claudlos/agentic-stack-op)
using the ``$Adapter`` adapter.

The portable brain is in ``.agent/``. Your AI harness reads it at the start of
every session.

## Next steps

- Edit ``.agent/memory/personal/PREFERENCES.md`` to describe how you work
  (the onboarding wizard just populated it with defaults).
- Run your AI harness in this directory; it will read ``.agent/AGENTS.md``
  on startup and follow the protocol there.
- Nightly: ``python .agent/memory/auto_dream.py`` to stage candidate
  lessons and refresh the review queue.
"@ | Set-Content -NoNewline -Path $readmePath
        Write-Host "  + README.md"
    }
}

Write-Host "installing '$Adapter' into $TargetDir"

# Copy .agent/ brain only if the target does not already have one
$TargetAgent = Join-Path $TargetDir ".agent"
if (-not (Test-Path $TargetAgent -PathType Container)) {
    Copy-Item -Path (Join-Path $Here ".agent") -Destination $TargetAgent -Recurse
    Write-Host "  + .agent/ (portable brain)"
}

# Pick the python binary the hooks will actually use on this box. Probe with
# --version — `python3` on Windows often resolves to the MS Store app-execution
# alias that prints "Python was not found" when invoked, so Get-Command alone
# lies to us. We trust only binaries that successfully answer --version.
function Test-PythonBinary($name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) { return $false }
    try {
        $out = & $name --version 2>&1
        if ($LASTEXITCODE -eq 0 -and "$out" -match '^Python ') { return $true }
    } catch { }
    return $false
}
if (Test-PythonBinary 'python') {
    $PyBin = 'python'
} elseif (Test-PythonBinary 'python3') {
    $PyBin = 'python3'
} else {
    $PyBin = 'python'
    Write-Warning "no working python interpreter on PATH; hooks will fail until you install one."
}

switch ($Adapter) {
    'claude-code' {
        Copy-Item (Join-Path $Src 'CLAUDE.md') (Join-Path $TargetDir 'CLAUDE.md') -Force
        $claudeDir = Join-Path $TargetDir '.claude'
        New-Item -ItemType Directory -Path $claudeDir -Force | Out-Null
        $settingsDst = Join-Path $claudeDir 'settings.json'
        Copy-Item (Join-Path $Src 'settings.json') $settingsDst -Force
        # Substitute the detected python binary into hook commands. We read
        # raw text rather than parsing JSON so preserved formatting + schema
        # fields survive round-tripping.
        $raw = Get-Content -Raw $settingsDst
        $patched = $raw -replace '"command": "python ', ('"command": "' + $PyBin + ' ')
        if ($patched -ne $raw) {
            Set-Content -NoNewline -Path $settingsDst -Value $patched
        }
        # Render permissions.json deny patterns into settings.json so the
        # two layers (Claude Code permission engine + pre_tool_call hook)
        # can't drift.
        $permissionsJson = Join-Path $TargetDir '.agent/protocols/permissions.json'
        $renderScript = Join-Path $TargetDir '.agent/tools/render_claude_settings.py'
        if ((Test-Path $permissionsJson) -and (Test-Path $renderScript)) {
            try {
                & $PyBin $renderScript $settingsDst $permissionsJson | Out-Null
            } catch {
                Write-Warning "failed to merge permissions into settings.json: $_"
            }
        }
    }
    'cursor' {
        $rulesDir = Join-Path $TargetDir '.cursor/rules'
        New-Item -ItemType Directory -Path $rulesDir -Force | Out-Null
        Copy-Item (Join-Path $Src '.cursor/rules/agentic-stack.mdc') (Join-Path $rulesDir 'agentic-stack.mdc') -Force
    }
    'windsurf' {
        Copy-Item (Join-Path $Src '.windsurfrules') (Join-Path $TargetDir '.windsurfrules') -Force
    }
    'opencode' {
        Copy-Item (Join-Path $Src 'AGENTS.md') (Join-Path $TargetDir 'AGENTS.md') -Force
        Copy-Item (Join-Path $Src 'opencode.json') (Join-Path $TargetDir 'opencode.json') -Force
    }
    'openclient' {
        Copy-Item (Join-Path $Src 'config.md') (Join-Path $TargetDir '.openclient-system.md') -Force
    }
    'hermes' {
        Copy-Item (Join-Path $Src 'AGENTS.md') (Join-Path $TargetDir 'AGENTS.md') -Force
    }
    'standalone-python' {
        Copy-Item (Join-Path $Src 'run.py') (Join-Path $TargetDir 'run.py') -Force
    }
}

Write-Host "done."

# ── Onboarding wizard ──────────────────────────────────────────────
$OnboardPy = Join-Path $Here 'onboard.py'
if (-not (Test-Path $OnboardPy -PathType Leaf)) {
    Write-Host "tip: customize $TargetDir\.agent\memory\personal\PREFERENCES.md with your conventions."
    exit 0
}

if (-not (Test-PythonBinary $PyBin)) {
    Write-Host "tip: no working python interpreter - edit .agent\memory\personal\PREFERENCES.md manually."
    exit 0
}

$wizardArgs = @($OnboardPy, $TargetDir)
if ($Yes)         { $wizardArgs += '--yes' }
if ($Reconfigure) { $wizardArgs += '--reconfigure' }
if ($Force)       { $wizardArgs += '--force' }

& $PyBin @wizardArgs
exit $LASTEXITCODE
