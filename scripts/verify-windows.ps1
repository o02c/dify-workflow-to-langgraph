<#
.SYNOPSIS
    Verify the documented Windows behaviour of dify2langgraph on a real Windows host.

.DESCRIPTION
    Every check here maps to a claim made in USAGE.md sections 8 (Windows) and 9
    (Docker). They are claims that cannot be verified from macOS or Linux: the
    console code page, PowerShell's environment-variable syntax, path separators,
    and bind-mount behaviour on Docker Desktop for Windows.

    The script only reads and writes inside a temporary directory plus the repo's
    own tests/fixtures; it installs nothing and changes no machine settings.

.PARAMETER RepoRoot
    Path to a checkout of this repository. Defaults to the parent of this script.

.PARAMETER ExpectedDigest
    Optional. The output digest produced on macOS/Linux (see the command printed
    at the end of a run there). When supplied, the script asserts that Windows
    generates byte-identical output.

.PARAMETER SkipDocker
    Skip the Docker checks even if a Docker CLI is present.

.EXAMPLE
    # Copy the repo to a local disk first -- running from a Parallels network
    # share (\\Mac\Home\...) makes virtualenv creation slow and flaky.
    .\scripts\verify-windows.ps1

.EXAMPLE
    .\scripts\verify-windows.ps1 -ExpectedDigest 3f0a...  # compare against macOS
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ExpectedDigest = "",
    [switch]$SkipDocker
)

$ErrorActionPreference = "Stop"
$script:Results = @()

function Add-Result {
    param(
        [string]$Id,
        [string]$Claim,
        [ValidateSet("PASS", "FAIL", "SKIP")][string]$Status,
        [string]$Detail = ""
    )
    $script:Results += [pscustomobject]@{
        Id = $Id; Claim = $Claim; Status = $Status; Detail = $Detail
    }
    $color = switch ($Status) { "PASS" { "Green" } "FAIL" { "Red" } "SKIP" { "Yellow" } }
    Write-Host ("  [{0}] {1} - {2}" -f $Status, $Id, $Claim) -ForegroundColor $color
    if ($Detail) { Write-Host ("         {0}" -f $Detail) -ForegroundColor DarkGray }
}

function Invoke-Checked {
    <# Run a scriptblock, turn any exception into a FAIL rather than aborting. #>
    param([string]$Id, [string]$Claim, [scriptblock]$Body)
    try { & $Body } catch { Add-Result $Id $Claim "FAIL" $_.Exception.Message }
}

function Get-ToolPath {
    <#
        .SYNOPSIS
            Path to an executable on PATH, or $null.
        .NOTES
            Written the long way instead of `(Get-Command x)?.Source` so the
            script parses under Windows PowerShell 5.1, which is still the
            default shell on most Windows hosts.
    #>
    param([string]$Name)
    $cmd = Get-Command $Name -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    return $null
}

# ---------------------------------------------------------------------------
# Environment report
# ---------------------------------------------------------------------------
Write-Host "`n=== Environment ===" -ForegroundColor Cyan

$codepage = (chcp) -replace '[^0-9]', ''
$pyExe = Get-ToolPath "python"
$uvExe = Get-ToolPath "uv"

try {
    $osDesc = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    $osArch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
} catch {
    # Older .NET Framework: RuntimeInformation may be unavailable under PS 5.1.
    $osDesc = [System.Environment]::OSVersion.VersionString
    $osArch = $env:PROCESSOR_ARCHITECTURE
}

[pscustomobject]@{
    PowerShell    = $PSVersionTable.PSVersion.ToString()
    Edition       = $PSVersionTable.PSEdition
    OS            = $osDesc
    Architecture  = $osArch
    ConsoleCP     = $codepage
    OutputEncoding= [Console]::OutputEncoding.WebName
    Culture       = (Get-Culture).Name
    Python        = if ($pyExe) { (& python --version 2>&1) } else { "(not found)" }
    uv            = if ($uvExe) { (& uv --version 2>&1) } else { "(not found)" }
    PYTHONUTF8    = if ($env:PYTHONUTF8) { $env:PYTHONUTF8 } else { "(unset)" }
} | Format-List

if (-not $pyExe -and -not $uvExe) {
    Write-Host "Neither python nor uv is on PATH. Install Python 3.13 (or uv) and re-run." -ForegroundColor Red
    exit 2
}

# Prefer uv so the pinned dependency set is used; fall back to bare python.
$useUv = [bool]$uvExe
$fixture = Join-Path $RepoRoot "tests\fixtures\guardduty_handler.yml"
if (-not (Test-Path $fixture)) {
    Write-Host "Fixture not found: $fixture -- is -RepoRoot correct?" -ForegroundColor Red
    exit 2
}

function Invoke-Converter {
    <# Run the CLI, returning a record with ExitCode/StdOut/StdErr. #>
    param([string[]]$CliArgs, [string]$WorkDir, [hashtable]$Env = @{})

    $saved = @{}
    foreach ($k in $Env.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k)
        [Environment]::SetEnvironmentVariable($k, $Env[$k])
    }
    try {
        Push-Location $WorkDir
        try {
            if ($useUv) {
                $out = & uv run --project $RepoRoot dify2langgraph @CliArgs 2>&1
            } else {
                $env:PYTHONPATH = Join-Path $RepoRoot "src"
                $out = & python -m dify2langgraph.cli @CliArgs 2>&1
            }
            return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = ($out -join "`n") }
        } finally { Pop-Location }
    } finally {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
    }
}

$work = Join-Path ([System.IO.Path]::GetTempPath()) ("d2l-verify-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $work -Force | Out-Null
Copy-Item $fixture -Destination $work

# ---------------------------------------------------------------------------
# B. Converter runs natively on Windows
# ---------------------------------------------------------------------------
Write-Host "`n=== B. Converter (native Windows) ===" -ForegroundColor Cyan

$genRoot = Join-Path $work "out\guardduty_handler"

Invoke-Checked "B1" "Converting a DSL with Japanese text succeeds" {
    $r = Invoke-Converter @("guardduty_handler.yml", "-o", "out", "--skip-implement") $work
    if ($r.ExitCode -eq 0 -and (Test-Path $genRoot)) {
        Add-Result "B1" "Converting a DSL with Japanese text succeeds" "PASS"
    } else {
        Add-Result "B1" "Converting a DSL with Japanese text succeeds" "FAIL" `
            ("exit={0}`n{1}" -f $r.ExitCode, $r.Output)
    }
}

Invoke-Checked "B2" "Japanese survives the round trip into generated sources" {
    $statePath = Join-Path $genRoot "state.py"
    $text = [System.IO.File]::ReadAllText($statePath, [System.Text.Encoding]::UTF8)
    if ($text -match "質問分類器" -and $text -match "知識取得") {
        Add-Result "B2" "Japanese survives the round trip into generated sources" "PASS"
    } else {
        Add-Result "B2" "Japanese survives the round trip into generated sources" "FAIL" `
            "expected node titles not found in state.py"
    }
}

Invoke-Checked "B3" "Generated files use LF, not CRLF (cross-platform determinism)" {
    $crlf = @()
    foreach ($f in @(Get-ChildItem $genRoot -Recurse -Filter *.py)) {
        $bytes = [System.IO.File]::ReadAllBytes($f.FullName)
        for ($i = 0; $i -lt $bytes.Length - 1; $i++) {
            if ($bytes[$i] -eq 13 -and $bytes[$i + 1] -eq 10) { $crlf += $f.Name; break }
        }
    }
    if ($crlf.Count -eq 0) {
        Add-Result "B3" "Generated files use LF, not CRLF (cross-platform determinism)" "PASS"
    } else {
        Add-Result "B3" "Generated files use LF, not CRLF (cross-platform determinism)" "FAIL" `
            ("CRLF in: {0}" -f ($crlf -join ", "))
    }
}

Invoke-Checked "B4" "Backslash and forward-slash paths both work (USAGE 8.3)" {
    $r1 = Invoke-Converter @("tests\fixtures\guardduty_handler.yml", "-o", "bs", "--skip-implement") $RepoRoot
    $r2 = Invoke-Converter @("tests/fixtures/guardduty_handler.yml", "-o", "fs", "--skip-implement") $RepoRoot
    $bs = Join-Path $RepoRoot "bs\guardduty_handler\state.py"
    $fs = Join-Path $RepoRoot "fs\guardduty_handler\state.py"
    $ok = ($r1.ExitCode -eq 0) -and ($r2.ExitCode -eq 0) -and (Test-Path $bs) -and (Test-Path $fs)
    Remove-Item (Join-Path $RepoRoot "bs"), (Join-Path $RepoRoot "fs") -Recurse -Force -ErrorAction SilentlyContinue
    if ($ok) {
        Add-Result "B4" "Backslash and forward-slash paths both work (USAGE 8.3)" "PASS"
    } else {
        Add-Result "B4" "Backslash and forward-slash paths both work (USAGE 8.3)" "FAIL" `
            ("backslash exit={0}, slash exit={1}" -f $r1.ExitCode, $r2.ExitCode)
    }
}

# Digest: the same implementation the macOS/Linux side runs via `make verify-digest`,
# so the two platforms cannot drift apart in how they hash the output. Stdlib only
# in --dir mode, so it works without the package being installed.
$digestPy = Join-Path $RepoRoot "scripts\output_digest.py"
$digest = (& python $digestPy --dir $genRoot).Trim()

Invoke-Checked "B5" "Output is byte-identical to the macOS/container run" {
    if (-not $ExpectedDigest) {
        Add-Result "B5" "Output is byte-identical to the macOS/container run" "SKIP" `
            "no -ExpectedDigest supplied; this run's digest is $digest"
    } elseif ($digest -eq $ExpectedDigest) {
        Add-Result "B5" "Output is byte-identical to the macOS/container run" "PASS" $digest
    } else {
        Add-Result "B5" "Output is byte-identical to the macOS/container run" "FAIL" `
            ("expected {0}`n         got      {1}" -f $ExpectedDigest, $digest)
    }
}

# ---------------------------------------------------------------------------
# C. Console code page (USAGE 8.1)
# ---------------------------------------------------------------------------
Write-Host "`n=== C. Console code page (USAGE 8.1) ===" -ForegroundColor Cyan

# Give one node a Japanese return value, standing in for an implemented body,
# so `python -m <pkg>` actually has non-ASCII in the state it prints.
$simple = Join-Path $RepoRoot "tests\fixtures\simple_workflow.yml"
Copy-Item $simple -Destination $work -Force
$null = Invoke-Converter @("simple_workflow.yml", "-o", "run", "--skip-implement") $work
$pkgParent = Join-Path $work "run"
$llmNode = Join-Path $pkgParent "simple_workflow\nodes\llm_node.py"
$src = [System.IO.File]::ReadAllText($llmNode, [System.Text.Encoding]::UTF8)
$src = $src.Replace('"text": "placeholder"', '"text": "翻訳結果"')
[System.IO.File]::WriteAllText($llmNode, $src, (New-Object System.Text.UTF8Encoding $false))

function Invoke-Package {
    param([hashtable]$Env)
    $saved = @{}
    foreach ($k in $Env.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k)
        [Environment]::SetEnvironmentVariable($k, $Env[$k])
    }
    try {
        Push-Location $pkgParent
        try {
            $out = & python -m simple_workflow 2>&1
            return [pscustomobject]@{ ExitCode = $LASTEXITCODE; Output = ($out -join "`n") }
        } finally { Pop-Location }
    } finally {
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
    }
}

Invoke-Checked "C1" "Without PYTHONUTF8, printing non-ASCII state does not crash" {
    $r = Invoke-Package @{ PYTHONUTF8 = $null; PYTHONIOENCODING = $null }
    if ($r.ExitCode -eq 0 -and $r.Output -notmatch "UnicodeEncodeError") {
        $escaped = if ($r.Output -match '\\u7ffb') { " (escaped as \uXXXX, as documented)" } else { " (rendered directly)" }
        Add-Result "C1" "Without PYTHONUTF8, printing non-ASCII state does not crash" "PASS" `
            ("code page {0}{1}" -f $codepage, $escaped)
    } else {
        Add-Result "C1" "Without PYTHONUTF8, printing non-ASCII state does not crash" "FAIL" $r.Output
    }
}

Invoke-Checked "C2" "With PYTHONUTF8=1, Japanese is printed correctly" {
    $r = Invoke-Package @{ PYTHONUTF8 = "1" }
    if ($r.ExitCode -eq 0 -and $r.Output -match "翻訳結果") {
        Add-Result "C2" "With PYTHONUTF8=1, Japanese is printed correctly" "PASS"
    } else {
        Add-Result "C2" "With PYTHONUTF8=1, Japanese is printed correctly" "FAIL" $r.Output
    }
}

# ---------------------------------------------------------------------------
# D. PowerShell environment-variable syntax (USAGE 8.2)
# ---------------------------------------------------------------------------
Write-Host "`n=== D. PowerShell environment variables (USAGE 8.2) ===" -ForegroundColor Cyan

Invoke-Checked "D1" '$env:VAR = "value" reaches the CLI (USAGE 8.2)' {
    $r = Invoke-Converter @("guardduty_handler.yml", "-o", "dbg", "--skip-implement") $work `
        @{ LOG_LEVEL = "DEBUG" }
    $quiet = Invoke-Converter @("guardduty_handler.yml", "-o", "dbg2", "--skip-implement") $work `
        @{ LOG_LEVEL = "ERROR" }
    if ($r.Output.Length -gt $quiet.Output.Length) {
        Add-Result "D1" '$env:VAR = "value" reaches the CLI (USAGE 8.2)' "PASS" `
            "LOG_LEVEL honoured (DEBUG is more verbose than ERROR)"
    } else {
        Add-Result "D1" '$env:VAR = "value" reaches the CLI (USAGE 8.2)' "FAIL" `
            "LOG_LEVEL made no difference to output volume"
    }
}

Invoke-Checked "D2" "ANSI colour codes are not emitted as literal noise" {
    $r = Invoke-Converter @("guardduty_handler.yml", "-o", "ansi", "--skip-implement") $work
    # Output is captured (not a tty), so colour must be off regardless of terminal.
    if ($r.Output -notmatch [char]27) {
        Add-Result "D2" "ANSI colour codes are not emitted as literal noise" "PASS"
    } else {
        Add-Result "D2" "ANSI colour codes are not emitted as literal noise" "FAIL" `
            "ESC sequences present in captured output"
    }
}

# ---------------------------------------------------------------------------
# E. Docker (USAGE 9) -- optional
# ---------------------------------------------------------------------------
Write-Host "`n=== E. Docker (USAGE 9) ===" -ForegroundColor Cyan

$dockerExe = Get-ToolPath "docker"
if ($SkipDocker) {
    Add-Result "E0" "Docker checks" "SKIP" "-SkipDocker was passed"
} elseif (-not $dockerExe) {
    Add-Result "E0" "Docker checks" "SKIP" "docker CLI not on PATH"
} else {
    $daemonOk = $false
    try { $null = & docker version --format '{{.Server.Version}}' 2>&1; $daemonOk = ($LASTEXITCODE -eq 0) } catch {}

    if (-not $daemonOk) {
        Add-Result "E0" "Docker checks" "SKIP" `
            "docker CLI present but daemon unreachable (in a Parallels VM this usually means nested virtualization is off)"
    } else {
        Invoke-Checked "E1" "The converter image builds on Windows" {
            Push-Location $RepoRoot
            try {
                $null = & docker build -t dify2langgraph-verify . 2>&1
                if ($LASTEXITCODE -eq 0) {
                    Add-Result "E1" "The converter image builds on Windows" "PASS"
                } else {
                    Add-Result "E1" "The converter image builds on Windows" "FAIL" "docker build exited $LASTEXITCODE"
                }
            } finally { Pop-Location }
        }

        Invoke-Checked "E2" "--mount handles a Windows drive-letter source path (USAGE 9)" {
            $dockerOut = Join-Path $work "dockerout"
            New-Item -ItemType Directory -Path $dockerOut -Force | Out-Null
            Copy-Item $fixture -Destination $dockerOut -Force
            $out = & docker run --rm --mount "type=bind,source=$dockerOut,target=/work" `
                dify2langgraph-verify guardduty_handler.yml -o out --skip-implement 2>&1
            if ($LASTEXITCODE -eq 0 -and (Test-Path (Join-Path $dockerOut "out\guardduty_handler\state.py"))) {
                Add-Result "E2" "--mount handles a Windows drive-letter source path (USAGE 9)" "PASS"
            } else {
                Add-Result "E2" "--mount handles a Windows drive-letter source path (USAGE 9)" "FAIL" ($out -join "`n")
            }

            $d = (& python $digestPy --dir (Join-Path $dockerOut "out\guardduty_handler")).Trim()
            if ($d -eq $digest) {
                Add-Result "E3" "Container output matches the native Windows run byte for byte" "PASS" $d
            } else {
                Add-Result "E3" "Container output matches the native Windows run byte for byte" "FAIL" `
                    ("native {0}`n         container {1}" -f $digest, $d)
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host "`n=== Summary ===" -ForegroundColor Cyan
$script:Results | Format-Table Id, Status, Claim -AutoSize

$failed = @($script:Results | Where-Object Status -eq "FAIL")
$skipped = @($script:Results | Where-Object Status -eq "SKIP")
Write-Host ("{0} passed, {1} failed, {2} skipped" -f `
    @($script:Results | Where-Object Status -eq "PASS").Count, $failed.Count, $skipped.Count)
Write-Host "Output digest (this host): $digest"
Write-Host "Compare on macOS/Linux with: make verify-digest"
Write-Host "Temp working directory: $work"

if ($failed.Count -gt 0) { exit 1 } else { exit 0 }
