param(
    [switch]$Yes,
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

function Write-Step([string]$Message) {
    Write-Host $Message
}

function Confirm-Step([string]$Message) {
    if ($Yes) { return $true }
    $reply = Read-Host "$Message [y/N]"
    return $reply -match '^(?i:y|yes)$'
}

function Test-Python([string]$Exe, [string[]]$PrefixArgs = @()) {
    try {
        & $Exe @PrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

function Find-SystemPython {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        foreach ($selector in @("-3.12")) {
            if (Test-Python $py.Source @($selector)) {
                return [pscustomobject]@{ Exe = $py.Source; Args = @($selector) }
            }
        }
    }

    foreach ($name in @("python3", "python")) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command -and (Test-Python $command.Source)) {
            return [pscustomobject]@{ Exe = $command.Source; Args = @() }
        }
    }
    return $null
}

function Find-Uv {
    $command = Get-Command uv -ErrorAction SilentlyContinue
    if ($command) { return $command.Source }

    $localUv = Join-Path $HOME ".local\bin\uv.exe"
    if (Test-Path $localUv) { return $localUv }
    return $null
}

function Ensure-Uv {
    $uv = Find-Uv
    if ($uv) { return $uv }

    if (-not (Confirm-Step "No usable Python environment is available. Install Astral uv so Daybook can install a managed Python 3.12 runtime?")) {
        throw "The validated Daybook AI runtime requires Python 3.12.x."
    }

    Write-Step "Installing uv from Astral's official installer..."
    $oldNoModify = $env:UV_NO_MODIFY_PATH
    try {
        $env:UV_NO_MODIFY_PATH = "1"
        Invoke-Expression (Invoke-RestMethod "https://astral.sh/uv/install.ps1")
    }
    finally {
        if ($null -eq $oldNoModify) {
            Remove-Item Env:UV_NO_MODIFY_PATH -ErrorAction SilentlyContinue
        }
        else {
            $env:UV_NO_MODIFY_PATH = $oldNoModify
        }
    }

    $uv = Find-Uv
    if (-not $uv) { throw "uv was installed but its executable could not be located." }
    return $uv
}

function Create-VenvWithUv([string]$UvPath) {
    Write-Step "Creating .venv with managed Python 3.12 (downloaded only if necessary)..."
    & $UvPath venv (Join-Path $Root ".venv") --python 3.12
    if ($LASTEXITCODE -ne 0) { throw "uv could not create .venv." }
}

foreach ($required in @("run.py", "requirements.txt", "scripts\preflight.py")) {
    if (-not (Test-Path (Join-Path $Root $required))) {
        throw "$required was not found. Run this installer from an extracted/cloned Daybook AI repository."
    }
}

Write-Step "Daybook AI installer"
Write-Step "Project: $Root"
if (Test-Path (Join-Path $Root ".git")) {
    Write-Step "Source: Git clone"
}
else {
    Write-Step "Source: extracted folder / GitHub ZIP"
}
Write-Host ""

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $VenvPython) {
    if (Test-Python $VenvPython) {
        Write-Step "Using existing compatible .venv."
    }
    else {
        Write-Warning "Existing .venv uses an incompatible Python interpreter."
        if (Confirm-Step "Remove and recreate .venv?") {
            Remove-Item -Recurse -Force (Join-Path $Root ".venv")
        }
        else {
            throw "Cannot continue with the incompatible .venv."
        }
    }
}

if (-not (Test-Path $VenvPython)) {
    $systemPython = Find-SystemPython
    if ($systemPython) {
        $version = & $systemPython.Exe @($systemPython.Args) --version 2>&1
        Write-Step "Compatible Python detected: $version"
        Write-Step "Creating project virtual environment..."
        & $systemPython.Exe @($systemPython.Args) -m venv (Join-Path $Root ".venv")
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Python's venv module could not create the environment."
            $uv = Ensure-Uv
            Create-VenvWithUv $uv
        }
    }
    else {
        $uv = Ensure-Uv
        Create-VenvWithUv $uv
    }
}

if (-not (Test-Path $VenvPython)) { throw ".venv was not created successfully." }

& $VenvPython (Join-Path $Root "scripts\preflight.py")
if ($LASTEXITCODE -ne 0) { throw "Environment preflight failed." }

& $VenvPython (Join-Path $Root "scripts\preflight.py") --verify-deps --quiet *> $null
$depsReady = $LASTEXITCODE -eq 0

if ($depsReady) {
    Write-Step "Python dependencies already satisfy requirements.txt."
}
else {
    if (-not (Confirm-Step "Install or update Daybook AI Python dependencies in .venv from requirements.txt?")) {
        throw "Daybook AI dependencies are not ready."
    }
    Write-Step "Installing Python dependencies..."
    & $VenvPython -m pip install --disable-pip-version-check --upgrade pip
    if ($LASTEXITCODE -ne 0) { throw "pip upgrade failed." }
    & $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $Root "requirements.txt")
    if ($LASTEXITCODE -ne 0) { throw "Dependency installation failed." }
}

& $VenvPython -m pip check
if ($LASTEXITCODE -ne 0) { throw "pip reported an inconsistent environment." }

& $VenvPython (Join-Path $Root "scripts\preflight.py") --verify-deps
if ($LASTEXITCODE -ne 0) { throw "Post-install dependency verification failed." }

$EnvFile = Join-Path $Root ".env"
if (-not (Test-Path $EnvFile)) {
    $EnvExample = Join-Path $Root ".env.example"
    if (-not (Test-Path $EnvExample)) { throw ".env.example was not found." }
    Copy-Item $EnvExample $EnvFile
    Write-Step "Created .env from .env.example. Existing .env files are never overwritten."
}
else {
    Write-Step "Existing .env preserved."
}

Write-Host ""
Write-Step "Environment setup is complete."
Write-Step "Activation is not required; Daybook uses .venv's Python directly."

if (-not $NoLaunch) {
    if (Confirm-Step "Launch Daybook AI now? The existing Daybook launcher may download missing llama.cpp/model runtime components on first launch.") {
        & $VenvPython (Join-Path $Root "run.py")
        exit $LASTEXITCODE
    }
}

Write-Step "To launch later: run.bat"
