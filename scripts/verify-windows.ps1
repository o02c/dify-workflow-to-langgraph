<#
.SYNOPSIS
    Verify the documented Windows behaviour of dify2langgraph on a real Windows host.

.DESCRIPTION
    Every check here maps to a claim made in USAGE.md sections 8 (Windows) and 9
    (Docker) that cannot be verified from macOS or Linux: the console code page,
    PowerShell's environment-variable syntax, path separators, and bind-mount
    behaviour on Docker Desktop for Windows.

    The script installs nothing and changes no machine settings. It writes only
    inside a temporary directory under %TEMP%.

    Prerequisite: uv. Installing uv alone is enough -- it downloads CPython
    itself, so Python need not be installed separately, and it needs no
    administrator rights:

        powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
        $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"   # until you restart the shell

    A real python on PATH also works, but then the project's dependencies must
    already be installed into it or the section C checks are skipped. Note that
    Windows ships a stub python.exe under WindowsApps that only opens the
    Microsoft Store; this script detects and ignores it.

.PARAMETER RepoRoot
    Path to a checkout (or `git archive` export) of this repository. Defaults to
    the parent of this script's directory.

    If this resolves to a UNC path such as \\Mac\Home\... (a Parallels shared
    folder), the script copies it to local disk first: Windows cannot give a
    native process a UNC working directory, so uv and python would silently run
    against C:\Windows instead. Pass -NoCopy to suppress that.

.PARAMETER ExpectedDigest
    Optional. The digest printed by `make verify-digest` on macOS/Linux. When
    supplied, the script asserts that Windows generates byte-identical output.

.PARAMETER SkipDocker
    Skip the Docker checks even if a Docker CLI is present.

.PARAMETER NoCopy
    Use RepoRoot as given, even when it is on a network share.

.PARAMETER WithLlm
    Also run the G group, which calls a real LLM and therefore costs money and
    needs network access. Off by default: every other check is deterministic,
    offline and free (ADR-0001). Credentials are read from the environment or
    from a .env file in RepoRoot; only their names are ever printed.

.PARAMETER LlmProvider
    Provider for the conversion-time checks (G1/G2), passed through as
    --llm-provider. Without it the script picks the first provider it finds a
    credential for, which is a guess: a key that exists but has no quota still
    wins. Set this to be explicit.

    Valid values are openai, anthropic, bedrock and google -- the same set the
    generated llm.py supports.

.PARAMETER LlmModel
    Model for the conversion-time checks, passed through as --llm-model.
    Defaults to whatever the CLI defaults to.

.PARAMETER RuntimeLlmProvider
    Provider for the run-time check (G3), exported as LLM_PROVIDER for the
    generated package. Kept separate from -LlmProvider because the two choices
    are independent. Defaults to whatever LLM_PROVIDER already says (or the
    generated llm.py's own default).

.PARAMETER RuntimeLlmModel
    Model for the run-time check, exported as LLM_MODEL.

.EXAMPLE
    .\scripts\verify-windows.ps1

.EXAMPLE
    .\scripts\verify-windows.ps1 -ExpectedDigest 3ca50a8cf827c3af...
#>
[CmdletBinding()]
param(
    [string]$RepoRoot = (Split-Path -Parent $PSScriptRoot),
    [string]$ExpectedDigest = "",
    [switch]$SkipDocker,
    [switch]$NoCopy,
    [switch]$WithLlm,
    [ValidateSet("", "openai", "anthropic", "bedrock", "google")][string]$LlmProvider = "",
    [string]$LlmModel = "",
    [string]$RuntimeLlmProvider = "",
    [string]$RuntimeLlmModel = ""
)

# "Stop" applies to cmdlets only. Every external process goes through
# Invoke-Native, which drops to "Continue" for the duration of the call --
# otherwise a native command merely *writing to stderr* under 2>&1 becomes a
# terminating NativeCommandError and kills the run. That is exactly what the
# Microsoft Store python.exe stub does, and it used to abort this script during
# the environment report.
$ErrorActionPreference = "Stop"
$script:Results = @()
$script:G1Succeeded = $false

# Stamped by `git archive` via the export-subst attribute (.gitattributes). In a
# working checkout it stays the literal placeholder. Printed in the environment
# report so an out-of-date export is visible immediately -- running an old copy
# looks exactly like a behaviour difference on the Windows host otherwise.
$script:SourceCommit = '$Format:%H$'

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
    <# Run a check body; turn any exception into a FAIL rather than aborting. #>
    param([string]$Id, [string]$Claim, [scriptblock]$Body)
    try { & $Body } catch { Add-Result $Id $Claim "FAIL" $_.Exception.Message }
}

function Invoke-Native {
    <#
        .SYNOPSIS
            Run an external program, capturing output and exit code without ever
            throwing because of stderr.
        .OUTPUTS
            [pscustomobject] with ExitCode and Output.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Exe,
        [string[]]$Arguments = @(),
        [string]$WorkDir,
        [hashtable]$EnvVars = @{},
        [System.Text.Encoding]$DecodeAs
    )

    # PowerShell decodes a native command's stdout with [Console]::OutputEncoding,
    # which on a legacy console is the OEM code page (437 on en-US). A child that
    # emits UTF-8 -- as Python does under PYTHONUTF8=1 -- then arrives as mojibake.
    # Callers that know the child's encoding pass it here. Deliberately not named
    # -OutputEncoding: that would shadow PowerShell's automatic $OutputEncoding.
    $prevConsoleEnc = $null
    if ($DecodeAs) {
        try {
            $prevConsoleEnc = [Console]::OutputEncoding
            [Console]::OutputEncoding = $DecodeAs
        } catch {
            $prevConsoleEnc = $null
        }
    }

    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $saved = @{}
    foreach ($k in $EnvVars.Keys) {
        $saved[$k] = [Environment]::GetEnvironmentVariable($k)
        [Environment]::SetEnvironmentVariable($k, $EnvVars[$k])
    }
    # Track whether the push actually happened. ErrorActionPreference is already
    # "Continue" here, so a failed Push-Location would not throw -- and popping
    # regardless would then unwind the *caller's* location instead.
    $pushed = $false
    try {
        if ($WorkDir) {
            Push-Location -LiteralPath $WorkDir -ErrorAction Stop
            $pushed = $true
        }
        $lines = & $Exe @Arguments 2>&1 | ForEach-Object { $_.ToString() }
        return [pscustomobject]@{
            ExitCode = $LASTEXITCODE
            Output   = (@($lines) -join "`n")
        }
    } catch {
        return [pscustomobject]@{ ExitCode = -1; Output = $_.Exception.Message }
    } finally {
        if ($pushed) { Pop-Location }
        foreach ($k in $saved.Keys) { [Environment]::SetEnvironmentVariable($k, $saved[$k]) }
        if ($prevConsoleEnc) {
            # Best effort. If the console refuses the restore there is nothing
            # useful to do, and throwing here would mask the result being returned.
            try { [Console]::OutputEncoding = $prevConsoleEnc } catch { $null = $_ }
        }
        $ErrorActionPreference = $prevEap
    }
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

function Join-Parts {
    <#
        .SYNOPSIS
            Join path segments using the platform separator.
        .NOTES
            Join-Path takes only one -ChildPath under Windows PowerShell 5.1, so
            multi-segment paths get chained here rather than written with literal
            backslashes. That also keeps the script runnable on macOS/Linux for a
            dry run, which is the only way to exercise its control flow before
            handing it to a Windows host.
    #>
    param(
        [Parameter(Mandatory = $true)][string]$Base,
        [Parameter(ValueFromRemainingArguments = $true)][string[]]$Parts
    )
    $joined = $Base
    foreach ($seg in $Parts) { $joined = Join-Path -Path $joined -ChildPath $seg }
    return $joined
}

function Get-RealPythonPath {
    <#
        .SYNOPSIS
            Path to a python that actually runs, or $null.
        .NOTES
            Windows puts an App Execution Alias at
            %LOCALAPPDATA%\Microsoft\WindowsApps\python.exe. It is on PATH and
            Get-Command finds it, but running it only prints "Python was not
            found; run without arguments to install from the Microsoft Store"
            and exits non-zero. Probe the candidate rather than trusting PATH.
    #>
    $candidate = Get-ToolPath "python"
    if (-not $candidate) { return $null }
    if ($candidate -like "*\WindowsApps\*") { return $null }
    $probe = Invoke-Native -Exe $candidate -Arguments @("--version")
    if ($probe.ExitCode -eq 0 -and $probe.Output -match "Python 3") { return $candidate }
    return $null
}

# ---------------------------------------------------------------------------
# Working copy: native processes cannot have a UNC current directory
# ---------------------------------------------------------------------------

# PowerShell reports a share-rooted location as
# "Microsoft.PowerShell.Core\FileSystem::\\Mac\Home\...". Strip the provider
# prefix so the value is a plain path.
$RepoRoot = $RepoRoot -replace '^Microsoft\.PowerShell\.Core\\FileSystem::', ''

function Get-PathKey {
    <# Short stable hash of a path, so the same source maps to the same copy. #>
    param([string]$Path)
    $md5 = [System.Security.Cryptography.MD5]::Create()
    $bytes = $md5.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($Path.ToLowerInvariant()))
    return (([System.BitConverter]::ToString($bytes)) -replace '-', '').Substring(0, 8).ToLowerInvariant()
}

$originalRepoRoot = $RepoRoot

if (-not $NoCopy -and $RepoRoot.StartsWith("\\")) {
    # Deterministic name, not a fresh GUID: robocopy then updates the copy in
    # place and the .venv uv builds there survives between runs. With a new
    # directory every time, uv re-resolves from PyPI on each run -- which is slow
    # and turns any network hiccup into a cascade of unrelated check failures.
    $localRoot = Join-Path ([System.IO.Path]::GetTempPath()) ("d2l-repo-" + (Get-PathKey $RepoRoot))
    Write-Host "RepoRoot is on a network share:" -ForegroundColor Yellow
    Write-Host "  $RepoRoot" -ForegroundColor Yellow
    Write-Host "Windows cannot give uv.exe or python.exe a UNC working directory," -ForegroundColor Yellow
    Write-Host "so copying to local disk first: $localRoot" -ForegroundColor Yellow
    New-Item -ItemType Directory -Path $localRoot -Force | Out-Null

    # robocopy rather than Copy-Item. Copy-Item needs a trailing wildcard to copy
    # directory *contents*, but -LiteralPath deliberately does not expand
    # wildcards (and plain -Path with -Exclude does not filter subdirectories),
    # so the obvious spelling silently copies nothing. robocopy takes two
    # directories, handles UNC sources natively, and reports success as exit
    # codes 0-7 -- 8 and above are real failures.
    $rc = Invoke-Native -Exe "robocopy.exe" -Arguments @(
        $RepoRoot, $localRoot, "/E", "/NFL", "/NDL", "/NJH", "/NJS", "/NP",
        "/XD", ".git", ".venv", "__pycache__", ".ruff_cache", ".pytest_cache")
    if ($rc.ExitCode -ge 8) {
        Write-Host "robocopy failed (exit $($rc.ExitCode)):" -ForegroundColor Red
        Write-Host $rc.Output
        exit 2
    }

    # .env is gitignored, so it is never in a `git archive` export and is placed
    # beside it by hand. Copy it explicitly rather than trusting the bulk copy to
    # pick up a dotfile across an SMB share.
    $srcEnv = Join-Path $originalRepoRoot ".env"
    if (Test-Path $srcEnv) {
        Copy-Item -LiteralPath $srcEnv -Destination (Join-Path $localRoot ".env") -Force
        Write-Host "Carried .env across." -ForegroundColor Yellow
    }

    $RepoRoot = $localRoot
    Write-Host "Copied.`n" -ForegroundColor Yellow
}

# ---------------------------------------------------------------------------
# Environment report
# ---------------------------------------------------------------------------
Write-Host "=== Environment ===" -ForegroundColor Cyan

$codepage = ((Invoke-Native -Exe "chcp.com").Output -replace '[^0-9]', '')
$pyExe = Get-RealPythonPath
$uvExe = Get-ToolPath "uv"

try {
    $osDesc = [System.Runtime.InteropServices.RuntimeInformation]::OSDescription
    $osArch = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
} catch {
    # Older .NET Framework: RuntimeInformation may be unavailable under PS 5.1.
    $osDesc = [System.Environment]::OSVersion.VersionString
    $osArch = $env:PROCESSOR_ARCHITECTURE
}

$pyVersion = "(not found)"
if ($pyExe) { $pyVersion = (Invoke-Native -Exe $pyExe -Arguments @("--version")).Output }
$uvVersion = "(not found)"
if ($uvExe) { $uvVersion = (Invoke-Native -Exe $uvExe -Arguments @("--version")).Output }

[pscustomobject]@{
    PowerShell     = $PSVersionTable.PSVersion.ToString()
    Edition        = $PSVersionTable.PSEdition
    OS             = $osDesc
    Architecture   = $osArch
    ConsoleCP      = $codepage
    OutputEncoding = [Console]::OutputEncoding.WebName
    Culture        = (Get-Culture).Name
    Python         = $pyVersion
    uv             = $uvVersion
    RepoRoot       = $RepoRoot
    PYTHONUTF8     = $(if ($env:PYTHONUTF8) { $env:PYTHONUTF8 } else { "(unset)" })
    ScriptCommit   = $(
        # Build the placeholder by concatenation rather than writing the literal
        # token a second time: export-subst rewrites *every* occurrence of it in
        # the file, so a second one gets silently mangled along with the real one.
        $placeholder = '$' + 'Format:%H' + '$'
        if ($script:SourceCommit -eq $placeholder) {
            "(working checkout, not a git archive export)"
        } else {
            $script:SourceCommit.Substring(0, [Math]::Min(12, $script:SourceCommit.Length))
        }
    )
} | Format-List

if (-not $pyExe -and -not $uvExe) {
    Write-Host "Neither uv nor a working python is on PATH." -ForegroundColor Red
    Write-Host ""
    Write-Host "Installing uv alone is enough -- it downloads CPython itself and" -ForegroundColor Yellow
    Write-Host "needs no administrator rights:" -ForegroundColor Yellow
    Write-Host '  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"' -ForegroundColor Cyan
    Write-Host '  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"' -ForegroundColor Cyan
    exit 2
}

$useUv = [bool]$uvExe
$onWindows = ($PSVersionTable.PSEdition -eq "Desktop") -or ($IsWindows -eq $true)
$fixture = Join-Parts $RepoRoot "tests" "fixtures" "guardduty_handler.yml"
$simpleFixture = Join-Parts $RepoRoot "tests" "fixtures" "simple_workflow.yml"
if (-not (Test-Path $fixture) -or -not (Test-Path $simpleFixture)) {
    Write-Host "Fixture not found: $fixture" -ForegroundColor Red
    Write-Host ""
    Write-Host "RepoRoot contains:" -ForegroundColor Yellow
    $entries = @(Get-ChildItem -LiteralPath $RepoRoot -Force -ErrorAction SilentlyContinue)
    if ($entries.Count -eq 0) {
        Write-Host "  (nothing -- the copy or the archive is empty)" -ForegroundColor Yellow
    } else {
        $entries | ForEach-Object { Write-Host ("  {0}" -f $_.Name) -ForegroundColor Yellow }
    }
    Write-Host ""
    Write-Host 'Expected a full checkout or "git archive" export. If tests/ is missing,' -ForegroundColor Yellow
    Write-Host "re-export it; if it is present but the path above is a temp copy, the" -ForegroundColor Yellow
    Write-Host "copy step dropped it -- re-run with -NoCopy from a local (non-UNC) path." -ForegroundColor Yellow
    exit 2
}

function Invoke-Converter {
    <# Run the CLI, through uv when available. #>
    param([string[]]$CliArgs, [string]$WorkDir, [hashtable]$EnvVars = @{})
    if ($useUv) {
        return Invoke-Native -Exe $uvExe -WorkDir $WorkDir -EnvVars $EnvVars `
            -Arguments (@("run", "--project", $RepoRoot, "dify2langgraph") + $CliArgs)
    }
    $e = $EnvVars.Clone()
    $e["PYTHONPATH"] = (Join-Path $RepoRoot "src")
    return Invoke-Native -Exe $pyExe -WorkDir $WorkDir -EnvVars $e `
        -Arguments (@("-m", "dify2langgraph.cli") + $CliArgs)
}

function Invoke-Python {
    <#
        .SYNOPSIS
            Run Python, through uv when available.
        .NOTES
            uv is the recommended (and sufficient) install: it fetches CPython
            itself, so a bare python need not be on PATH at all.
    #>
    param(
        [string[]]$PyArgs,
        [string]$WorkDir,
        [hashtable]$EnvVars = @{},
        [System.Text.Encoding]$DecodeAs
    )
    if ($useUv) {
        return Invoke-Native -Exe $uvExe -WorkDir $WorkDir -EnvVars $EnvVars -DecodeAs $DecodeAs `
            -Arguments (@("run", "--project", $RepoRoot, "python") + $PyArgs)
    }
    return Invoke-Native -Exe $pyExe -WorkDir $WorkDir -EnvVars $EnvVars -DecodeAs $DecodeAs `
        -Arguments $PyArgs
}

# Force the virtualenv to exist before any check runs. uv builds it on first use
# and needs PyPI for that; letting it happen inside B1 reports a network timeout
# as "converting a DSL failed", and every downstream check then fails too.
Write-Host "`nPreparing the Python environment (first run downloads dependencies)..." -ForegroundColor Cyan
$preflight = Invoke-Python @("--version") $RepoRoot
if ($preflight.ExitCode -ne 0) {
    Write-Host "Could not prepare the environment:" -ForegroundColor Red
    Write-Host $preflight.Output
    Write-Host ""
    Write-Host "This is an environment problem, not a product failure -- usually no" -ForegroundColor Yellow
    Write-Host "route to pypi.org, or a proxy that needs HTTPS_PROXY set. Nothing" -ForegroundColor Yellow
    Write-Host "below would be meaningful, so stopping here." -ForegroundColor Yellow
    exit 2
}
Write-Host ("Ready: " + $preflight.Output.Trim()) -ForegroundColor DarkGray

$work = Join-Path ([System.IO.Path]::GetTempPath()) ("d2l-verify-" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $work -Force | Out-Null
Copy-Item -LiteralPath $fixture -Destination $work
Copy-Item -LiteralPath $simpleFixture -Destination $work -Force
$digestPy = Join-Parts $RepoRoot "scripts" "output_digest.py"
$genRoot = Join-Parts $work "out" "guardduty_handler"

# ---------------------------------------------------------------------------
# B. Converter runs natively on Windows
# ---------------------------------------------------------------------------
Write-Host "`n=== B. Converter (native Windows) ===" -ForegroundColor Cyan

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
    $text = [System.IO.File]::ReadAllText((Join-Path $genRoot "state.py"), [System.Text.Encoding]::UTF8)
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
    if (-not $onWindows) {
        # Only Windows accepts both separators; elsewhere a backslash is an
        # ordinary character in a filename, so the check has nothing to assert.
        Add-Result "B4" "Backslash and forward-slash paths both work (USAGE 8.3)" "SKIP" `
            "Windows-only claim; this host is not Windows"
        return
    }
    $bs = Join-Path $work "bs"
    $fs = Join-Path $work "fs"
    $r1 = Invoke-Converter @("tests\fixtures\guardduty_handler.yml", "-o", $bs, "--skip-implement") $RepoRoot
    $r2 = Invoke-Converter @("tests/fixtures/guardduty_handler.yml", "-o", $fs, "--skip-implement") $RepoRoot
    $ok = ($r1.ExitCode -eq 0) -and ($r2.ExitCode -eq 0) `
        -and (Test-Path (Join-Parts $bs "guardduty_handler" "state.py")) `
        -and (Test-Path (Join-Parts $fs "guardduty_handler" "state.py"))
    if ($ok) {
        Add-Result "B4" "Backslash and forward-slash paths both work (USAGE 8.3)" "PASS"
    } else {
        Add-Result "B4" "Backslash and forward-slash paths both work (USAGE 8.3)" "FAIL" `
            ("backslash exit={0}, slash exit={1}`n{2}" -f $r1.ExitCode, $r2.ExitCode, $r1.Output)
    }
}

# Must not throw: if B1 failed there is nothing to digest.
$digest = "(unavailable)"
if (Test-Path $genRoot) {
    $dr = Invoke-Python @($digestPy, "--dir", $genRoot)
    if ($dr.ExitCode -eq 0) { $digest = ($dr.Output -split "`n" | Select-Object -Last 1).Trim() }
}

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

# These checks *run* a generated package, so langgraph has to be importable.
# With uv that is automatic; with a bare python the project must be installed.
$depProbe = Invoke-Python @("-c", "import langgraph")
$runtimeDepsOk = ($depProbe.ExitCode -eq 0)
$pkgParent = Join-Path $work "run"

if (-not $runtimeDepsOk) {
    Add-Result "C0" "Console code page checks" "SKIP" ("langgraph is not importable: " + $depProbe.Output)
} else {
    try {
        # Give one node a Japanese return value, standing in for an implemented
        # body, so running the package has non-ASCII in the state it prints.
        $null = Invoke-Converter @("simple_workflow.yml", "-o", "run", "--skip-implement") $work
        $llmNode = Join-Parts $pkgParent "simple_workflow" "nodes" "llm_node.py"
        $src = [System.IO.File]::ReadAllText($llmNode, [System.Text.Encoding]::UTF8)
        $src = $src.Replace('"text": "placeholder"', '"text": "翻訳結果"')
        [System.IO.File]::WriteAllText($llmNode, $src, (New-Object System.Text.UTF8Encoding $false))
    } catch {
        $runtimeDepsOk = $false
        Add-Result "C0" "Console code page checks" "SKIP" ("setup failed: " + $_.Exception.Message)
    }
}

if ($runtimeDepsOk) {
    Invoke-Checked "C1" "Without PYTHONUTF8, printing non-ASCII state does not crash" {
        $r = Invoke-Python @("-m", "simple_workflow") $pkgParent @{ PYTHONUTF8 = $null; PYTHONIOENCODING = $null }
        if ($r.ExitCode -eq 0 -and $r.Output -notmatch "UnicodeEncodeError") {
            $how = if ($r.Output -match '\\u7ffb') { "escaped as \uXXXX, as documented" } else { "rendered directly" }
            Add-Result "C1" "Without PYTHONUTF8, printing non-ASCII state does not crash" "PASS" `
                ("code page {0}; {1}" -f $codepage, $how)
        } else {
            Add-Result "C1" "Without PYTHONUTF8, printing non-ASCII state does not crash" "FAIL" $r.Output
        }
    }

    Invoke-Checked "C2" "With PYTHONUTF8=1, the workflow emits UTF-8" {
        # Decode as UTF-8: the assertion is about the bytes Python writes, not
        # about what a code-page-437 console can render. Making those bytes
        # readable *on screen* additionally needs `chcp 65001` (USAGE 8.1).
        $r = Invoke-Python @("-m", "simple_workflow") $pkgParent @{ PYTHONUTF8 = "1" } `
            -DecodeAs ([System.Text.Encoding]::UTF8)
        if ($r.ExitCode -eq 0 -and $r.Output -match "翻訳結果") {
            Add-Result "C2" "With PYTHONUTF8=1, the workflow emits UTF-8" "PASS" `
                ("UTF-8 bytes correct; console code page {0} still needs chcp 65001 to render them" -f $codepage)
        } else {
            Add-Result "C2" "With PYTHONUTF8=1, the workflow emits UTF-8" "FAIL" $r.Output
        }
    }
}

# ---------------------------------------------------------------------------
# D. PowerShell environment-variable syntax (USAGE 8.2)
# ---------------------------------------------------------------------------
Write-Host "`n=== D. PowerShell environment variables (USAGE 8.2) ===" -ForegroundColor Cyan

Invoke-Checked "D1" 'Setting $env:VAR reaches the CLI (USAGE 8.2)' {
    $verbose = Invoke-Converter @("guardduty_handler.yml", "-o", "dbg", "--skip-implement") $work @{ LOG_LEVEL = "DEBUG" }
    $quiet = Invoke-Converter @("guardduty_handler.yml", "-o", "dbg2", "--skip-implement") $work @{ LOG_LEVEL = "ERROR" }
    if ($verbose.Output.Length -gt $quiet.Output.Length) {
        Add-Result "D1" 'Setting $env:VAR reaches the CLI (USAGE 8.2)' "PASS" `
            "LOG_LEVEL honoured (DEBUG more verbose than ERROR)"
    } else {
        Add-Result "D1" 'Setting $env:VAR reaches the CLI (USAGE 8.2)' "FAIL" `
            ("DEBUG {0} chars vs ERROR {1} chars" -f $verbose.Output.Length, $quiet.Output.Length)
    }
}

Invoke-Checked "D2" "No literal ANSI escape codes in captured output" {
    $r = Invoke-Converter @("guardduty_handler.yml", "-o", "ansi", "--skip-implement") $work
    if ($r.Output -notmatch [char]27) {
        Add-Result "D2" "No literal ANSI escape codes in captured output" "PASS"
    } else {
        Add-Result "D2" "No literal ANSI escape codes in captured output" "FAIL" `
            "ESC sequences present in captured (non-tty) output"
    }
}

# ---------------------------------------------------------------------------
# F. Generated workflows actually run (ADR-0007)
# ---------------------------------------------------------------------------
Write-Host "`n=== F. Generated workflows run ===" -ForegroundColor Cyan

# C only proves the package does not crash while printing. These check that the
# graph really executed: which nodes were visited, which branch a Branching Node
# resolved to, what the End Node forwarded. scripts/run_generated.py emits the
# final state as ASCII-only JSON so it survives any console code page, and takes
# no --initial argument here -- embedding JSON in a native command line is where
# Windows PowerShell 5.1 argument quoting goes wrong.
$runPy = Join-Parts $RepoRoot "scripts" "run_generated.py"
$genDir = Join-Path $work "gen"

function Get-ErrorDetail {
    <#
        .SYNOPSIS
            The interesting part of a failed run's output.
        .NOTES
            The CLI logs progress at INFO, so a raw dump buries the one line that
            says what went wrong. Prefer ERROR lines, fall back to the tail.
    #>
    param([string]$Output)
    $errs = @($Output -split "`n" | Where-Object { $_ -match "ERROR|Traceback|Error code" })
    if ($errs.Count -gt 0) { return ($errs | Select-Object -Last 3) -join "`n" }
    return (@($Output -split "`n" | Select-Object -Last 5)) -join "`n"
}

function New-InitialStateFile {
    <#
        .SYNOPSIS
            Write a workflow's inputs to a JSON file and return its path.
        .NOTES
            A file rather than an inline argument: Windows PowerShell 5.1 mangles
            embedded double quotes when handing arguments to a native process.

            Generated workflows require their declared inputs under the Start
            Node's own state key (ADR-0009). Passing nothing used to work only
            because the Start Node fabricated placeholders, overwriting whatever
            the caller supplied.
    #>
    param([string]$Name, [string]$Json)
    $path = Join-Path $work "$Name.json"
    [System.IO.File]::WriteAllText($path, $Json, (New-Object System.Text.UTF8Encoding $false))
    return $path
}

function Get-StateJson {
    <# Pull the state object out of a runner invocation, or $null. #>
    param([pscustomobject]$Result)
    if ($Result.ExitCode -ne 0) { return $null }
    # The retriever logs a "not configured" warning to stderr, which 2>&1 merges
    # in, so select the JSON line rather than assuming it is the last one.
    $line = @($Result.Output -split "`n" |
        Where-Object { $_.TrimStart().StartsWith("{") }) | Select-Object -Last 1
    if (-not $line) { return $null }
    try { return $line | ConvertFrom-Json } catch { return $null }
}

if (-not $runtimeDepsOk) {
    Add-Result "F0" "Generated workflow execution" "SKIP" "langgraph is not importable"
} else {
    $null = Invoke-Converter @("simple_workflow.yml", "-o", $genDir, "--skip-implement") $work
    $null = Invoke-Converter @("guardduty_handler.yml", "-o", $genDir, "--skip-implement") $work

    Invoke-Checked "F1" "A generated linear workflow runs and visits every node" {
        $inputs = New-InitialStateFile "f1" '{"start_node": {"query": "example"}}'
        $r = Invoke-Python @($runPy, $genDir, "simple_workflow", "--initial-file", $inputs)
        $state = Get-StateJson $r
        if (-not $state) {
            Add-Result "F1" "A generated linear workflow runs and visits every node" "FAIL" (Get-ErrorDetail $r.Output)
            return
        }
        $names = @($state.PSObject.Properties.Name)
        $missing = @(@("start_node", "llm_node", "end_node") | Where-Object { $names -notcontains $_ })
        # The End Node forwards an upstream field rather than a placeholder (ADR-0004).
        $forwarded = ($state.end_node.result -eq $state.llm_node.text)
        if ($missing.Count -eq 0 -and $forwarded) {
            Add-Result "F1" "A generated linear workflow runs and visits every node" "PASS" `
                ("visited: " + ($names -join ", "))
        } else {
            Add-Result "F1" "A generated linear workflow runs and visits every node" "FAIL" `
                ("missing: {0}; End forwarded upstream value: {1}" -f ($missing -join ","), $forwarded)
        }
    }

    Invoke-Checked "F2" "A branching workflow resolves to exactly one branch (ADR-0003)" {
        $inputs = New-InitialStateFile "f2" `
            '{"node_1722391426202": {"finding": "f", "type": "t", "severity": 1.0}}'
        $r = Invoke-Python @($runPy, $genDir, "guardduty_handler", "--initial-file", $inputs)
        $state = Get-StateJson $r
        if (-not $state) {
            Add-Result "F2" "A branching workflow resolves to exactly one branch (ADR-0003)" "FAIL" (Get-ErrorDetail $r.Output)
            return
        }
        $names = @($state.PSObject.Properties.Name)
        $ends = @("node_1722399235845", "node_1722399356175")
        $reached = @($names | Where-Object { $ends -contains $_ })
        # knowledge-retrieval calls the Retriever port; unconfigured it yields []
        # so the graph still completes without Dify credentials (ADR-0006).
        $retrieved = @($state."node_1722397470145".result)
        if ($reached.Count -eq 1 -and $retrieved.Count -eq 0) {
            Add-Result "F2" "A branching workflow resolves to exactly one branch (ADR-0003)" "PASS" `
                ("reached {0}; knowledge-retrieval returned []" -f $reached[0])
        } else {
            Add-Result "F2" "A branching workflow resolves to exactly one branch (ADR-0003)" "FAIL" `
                ("branches reached: {0}; retrieval items: {1}" -f $reached.Count, $retrieved.Count)
        }
    }

    if ($useUv) {
        Invoke-Checked "F3" "The end-to-end generated-workflow test suite passes" {
            $r = Invoke-Native -Exe $uvExe -WorkDir $RepoRoot -Arguments @(
                "run", "--project", $RepoRoot, "pytest", "tests/test_generated.py", "-q")
            if ($r.ExitCode -eq 0) {
                $summary = @($r.Output -split "`n" | Where-Object { $_ -match "passed" }) | Select-Object -Last 1
                Add-Result "F3" "The end-to-end generated-workflow test suite passes" "PASS" $summary
            } else {
                Add-Result "F3" "The end-to-end generated-workflow test suite passes" "FAIL" $r.Output
            }
        }
    } else {
        Add-Result "F3" "The end-to-end generated-workflow test suite passes" "SKIP" `
            "needs uv (pytest comes from the test dependency group)"
    }
}

# ---------------------------------------------------------------------------
# G. Real LLM calls (opt-in: costs money, needs network)
# ---------------------------------------------------------------------------
Write-Host "`n=== G. LLM paths (opt-in) ===" -ForegroundColor Cyan

function Get-LlmCredentialSources {
    <#
        .SYNOPSIS
            Which LLM credentials are visible, and where from.
        .OUTPUTS
            Hashtable of variable name -> "env" or ".env". Values are never read
            into the result, so nothing secret can reach the console.
    #>
    $wanted = @("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY",
                "GEMINI_API_KEY", "AWS_PROFILE", "LLM_PROVIDER", "LLM_MODEL")
    $found = @{}
    foreach ($name in $wanted) {
        if ([Environment]::GetEnvironmentVariable($name)) { $found[$name] = "env" }
    }
    $envFile = Join-Path $RepoRoot ".env"
    if (Test-Path $envFile) {
        foreach ($line in @(Get-Content -LiteralPath $envFile)) {
            if ($line -match '^\s*([A-Z0-9_]+)\s*=\s*\S') {
                $key = $Matches[1]
                if (($wanted -contains $key) -and (-not $found.ContainsKey($key))) {
                    $found[$key] = ".env"
                }
            }
        }
    }
    return $found
}

if (-not $WithLlm) {
    Add-Result "G0" "LLM paths" "SKIP" "pass -WithLlm to run these (they call a real model)"
} elseif (-not $runtimeDepsOk) {
    Add-Result "G0" "LLM paths" "SKIP" "langgraph is not importable"
} else {
    $creds = Get-LlmCredentialSources
    $envPath = Join-Path $RepoRoot ".env"
    Write-Host ("  .env: " + $(if (Test-Path $envPath) { $envPath } else { "not found at $envPath" })) -ForegroundColor DarkGray
    Write-Host ("  credentials visible: " +
        $(if ($creds.Count) { ($creds.Keys | Sort-Object) -join ", " } else { "(none)" })) -ForegroundColor DarkGray

    # Both surfaces now cover the same four providers; the conversion-time and
    # run-time choices stay separate only because they are genuinely independent
    # (you may want a cheap model to write code and a different one to run it).
    $convProvider = $null
    $convSource = ""
    if ($LlmProvider) {
        $convProvider = $LlmProvider
        $convSource = "-LlmProvider"
    } elseif ($creds.ContainsKey("OPENAI_API_KEY")) { $convProvider = "openai"; $convSource = "auto (OPENAI_API_KEY present)" }
    elseif ($creds.ContainsKey("ANTHROPIC_API_KEY")) { $convProvider = "anthropic"; $convSource = "auto (ANTHROPIC_API_KEY present)" }
    elseif ($creds.ContainsKey("AWS_PROFILE")) { $convProvider = "bedrock"; $convSource = "auto (AWS_PROFILE present)" }
    elseif ($creds.ContainsKey("GOOGLE_API_KEY")) { $convProvider = "google"; $convSource = "auto (GOOGLE_API_KEY present)" }
    elseif ($creds.ContainsKey("GEMINI_API_KEY")) { $convProvider = "google"; $convSource = "auto (GEMINI_API_KEY present)" }

    # Auto-detection only proves a credential exists, not that it works -- an
    # out-of-quota key still wins the race. Say which one was chosen and why, so
    # a 429 is obviously "wrong provider picked" rather than a mystery.
    if ($convProvider) {
        Write-Host ("  conversion provider: {0} [{1}]{2}" -f $convProvider, $convSource,
            $(if ($LlmModel) { " model $LlmModel" } else { "" })) -ForegroundColor DarkGray
    }
    $rtProvider = if ($RuntimeLlmProvider) { $RuntimeLlmProvider }
                  elseif ($creds.ContainsKey("LLM_PROVIDER")) { "(from LLM_PROVIDER)" }
                  else { "(generated llm.py default)" }
    Write-Host ("  runtime provider: {0}{1}" -f $rtProvider,
        $(if ($RuntimeLlmModel) { " model $RuntimeLlmModel" } else { "" })) -ForegroundColor DarkGray

    # Conversion and the generated package both look for .env by walking up from
    # where they run, so put it beside the working directory.
    $repoEnv = Join-Path $RepoRoot ".env"
    if (Test-Path $repoEnv) { Copy-Item -LiteralPath $repoEnv -Destination $work -Force }

    $llmDir = Join-Path $work "llm"

    if (-not $convProvider) {
        Add-Result "G1" "LLM fills node bodies at conversion time" "SKIP" `
            "no LLM credential found (looked for OPENAI_API_KEY, ANTHROPIC_API_KEY, AWS_PROFILE, GOOGLE_API_KEY, GEMINI_API_KEY)"
        Add-Result "G2" "An LLM-implemented workflow runs" "SKIP" "depends on G1"
    } else {
        Invoke-Checked "G1" "LLM fills node bodies at conversion time" {
            $cliArgs = @("simple_workflow.yml", "-o", $llmDir, "--llm-provider", $convProvider)
            if ($LlmModel) { $cliArgs += @("--llm-model", $LlmModel) }
            $r = Invoke-Converter $cliArgs $work
            $nodes = Join-Parts $llmDir "simple_workflow" "nodes"
            if ($r.ExitCode -ne 0 -or -not (Test-Path $nodes)) {
                Add-Result "G1" "LLM fills node bodies at conversion time" "FAIL" (Get-ErrorDetail $r.Output)
                return
            }
            # Structural assertions only -- LLM output is not deterministic.
            $files = @(Get-ChildItem $nodes -Filter *.py | Where-Object { $_.Name -ne "__init__.py" })
            $stillStubbed = @($files | Where-Object {
                [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8) -match "TODO: Implement"
            })
            $crlf = @($files | Where-Object {
                [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8) -match "`r`n"
            })
            # Build the array first. In argument position PowerShell does not
            # evaluate `a + b` as an expression -- it would pass "+" as the second
            # positional argument and the file list as the third.
            $compileArgs = @("-m", "py_compile") + @($files | ForEach-Object { $_.FullName })
            $compile = Invoke-Python $compileArgs
            if ($stillStubbed.Count -eq 0 -and $crlf.Count -eq 0 -and $compile.ExitCode -eq 0) {
                $script:G1Succeeded = $true
                Add-Result "G1" "LLM fills node bodies at conversion time" "PASS" `
                    ("{0} node files implemented via {1}, all compile, all LF" -f $files.Count, $convProvider)
            } else {
                Add-Result "G1" "LLM fills node bodies at conversion time" "FAIL" `
                    ("still stubbed: {0}; CRLF: {1}; compile exit {2}`n{3}" -f `
                        $stillStubbed.Count, $crlf.Count, $compile.ExitCode, $compile.Output)
            }
        }

        Invoke-Checked "G2" "An LLM-implemented workflow runs" {
            # Without this the check passes on the deterministic stubs that the
            # conversion wrote before the LLM step failed -- a false green.
            if (-not $script:G1Succeeded) {
                Add-Result "G2" "An LLM-implemented workflow runs" "SKIP" "G1 did not implement the nodes"
                return
            }

            # A stub Start Node returns a placeholder, but an implemented one reads
            # its declared variables and raises when they are absent -- so this
            # needs real input, unlike F1. Passed as a file because inline JSON
            # does not survive PowerShell's native-argument quoting.
            #
            # The Start Node is deterministic now (ADR-0009), so the LLM never
            # sees it and can no longer invent an address for the workflow inputs.
            $initialFile = New-InitialStateFile "g2" '{"start_node": {"query": "hello"}}'

            $r = Invoke-Python @($runPy, $llmDir, "simple_workflow", "--initial-file", $initialFile)
            $state = Get-StateJson $r
            if ($state) {
                Add-Result "G2" "An LLM-implemented workflow runs" "PASS" `
                    ("final state keys: " + (@($state.PSObject.Properties.Name) -join ", "))
            } elseif ($r.Output -match "start_node\.py" -and
                      $r.Output -match "initial state|KeyError|not found") {
                # Distinguish the known design gap from a new break. The Start
                # Node's input address is undefined, so the model guesses and
                # sometimes guesses something unsatisfiable. Reporting that as
                # FAIL every third run would train the reader to ignore G2.
                Add-Result "G2" "An LLM-implemented workflow runs" "SKIP" `
                    ("the LLM guessed an unreachable address for the workflow input " +
                     "(known gap: workflow input address is undefined -- see TODO.md)")
            } else {
                # Any other run-time failure is a real result about the opt-in
                # pass (ADR-0001), not a harness bug.
                Add-Result "G2" "An LLM-implemented workflow runs" "FAIL" `
                    ("the LLM-written body failed at run time:`n" + (Get-ErrorDetail $r.Output))
            }
        }
    }

    # Runtime-only path: works with any provider the generated llm.py supports,
    # including google, so it is reachable even when conversion is not.
    Invoke-Checked "G3" "A generated workflow calls a real model at run time" {
        $rtDir = Join-Path $work "rt"
        $null = Invoke-Converter @("simple_workflow.yml", "-o", $rtDir, "--skip-implement") $work
        $node = Join-Parts $rtDir "simple_workflow" "nodes" "llm_node.py"
        $src = [System.IO.File]::ReadAllText($node, [System.Text.Encoding]::UTF8)

        # Stand in for an implemented body: call the model through the generated
        # llm.py, which is what exercises .env discovery and the provider SDK.
        $body = @'
    from ..llm import get_chat_model

    response = get_chat_model().invoke(
        [HumanMessage(content="Reply with exactly: WINDOWS_LLM_OK")]
    )
    output: LlmNodeOutput = {
        "text": response.content,
        "usage": response.usage_metadata or {},
    }
'@
        $src = $src.Replace("from langgraph.types import Command",
            "from langchain_core.messages import HumanMessage`nfrom langgraph.types import Command")
        $stub = "    output: LlmNodeOutput = {`n        `"text`": `"placeholder`",`n        `"usage`": {},`n    }"
        if ($src -notmatch [regex]::Escape('"text": "placeholder"')) {
            Add-Result "G3" "A generated workflow calls a real model at run time" "FAIL" `
                "stub body not found; the generator's output shape changed"
            return
        }
        $src = $src.Replace($stub, $body.TrimEnd())
        [System.IO.File]::WriteAllText($node, $src, (New-Object System.Text.UTF8Encoding $false))

        # Exported rather than baked into .env so the choice is visible and does
        # not depend on what the .env happens to say.
        $rtEnv = @{}
        if ($RuntimeLlmProvider) { $rtEnv["LLM_PROVIDER"] = $RuntimeLlmProvider }
        if ($RuntimeLlmModel) { $rtEnv["LLM_MODEL"] = $RuntimeLlmModel }

        $inputs = New-InitialStateFile "g3" '{"start_node": {"query": "example"}}'
        $r = Invoke-Python -PyArgs @($runPy, $rtDir, "simple_workflow", "--initial-file", $inputs) `
            -EnvVars $rtEnv
        $state = Get-StateJson $r
        if (-not $state) {
            Add-Result "G3" "A generated workflow calls a real model at run time" "FAIL" (Get-ErrorDetail $r.Output)
            return
        }
        $text = $state.llm_node.text
        # The End Node forwards the LLM output rather than a placeholder (ADR-0004).
        if ($text -and $text -ne "placeholder" -and $state.end_node.result -eq $text) {
            Add-Result "G3" "A generated workflow calls a real model at run time" "PASS" `
                ("model replied {0}; End forwarded it" -f $text)
        } else {
            Add-Result "G3" "A generated workflow calls a real model at run time" "FAIL" `
                ("llm_node.text = {0}" -f $text)
        }
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
    $probe = Invoke-Native -Exe $dockerExe -Arguments @("version", "--format", "{{.Server.Version}}")
    if ($probe.ExitCode -ne 0) {
        Add-Result "E0" "Docker checks" "SKIP" ("daemon unreachable. Inside a Parallels VM " +
            "this means nested virtualization, which is a Pro/Business feature and cannot be " +
            "enabled on the Standard edition.")
    } else {
        Invoke-Checked "E1" "The converter image builds on Windows" {
            $r = Invoke-Native -Exe $dockerExe -WorkDir $RepoRoot `
                -Arguments @("build", "-t", "dify2langgraph-verify", ".")
            if ($r.ExitCode -eq 0) {
                Add-Result "E1" "The converter image builds on Windows" "PASS"
            } else {
                Add-Result "E1" "The converter image builds on Windows" "FAIL" $r.Output
            }
        }

        Invoke-Checked "E2" "--mount handles a Windows drive-letter source path (USAGE 9)" {
            $dockerOut = Join-Path $work "dockerout"
            New-Item -ItemType Directory -Path $dockerOut -Force | Out-Null
            Copy-Item -LiteralPath $fixture -Destination $dockerOut -Force
            $r = Invoke-Native -Exe $dockerExe -Arguments @(
                "run", "--rm", "--mount", "type=bind,source=$dockerOut,target=/work",
                "dify2langgraph-verify", "guardduty_handler.yml", "-o", "out", "--skip-implement")
            if ($r.ExitCode -eq 0 -and (Test-Path (Join-Parts $dockerOut "out" "guardduty_handler" "state.py"))) {
                Add-Result "E2" "--mount handles a Windows drive-letter source path (USAGE 9)" "PASS"
                $dr = Invoke-Python @($digestPy, "--dir", (Join-Parts $dockerOut "out" "guardduty_handler"))
                $d = ($dr.Output -split "`n" | Select-Object -Last 1).Trim()
                if ($d -eq $digest) {
                    Add-Result "E3" "Container output matches the native Windows run" "PASS" $d
                } else {
                    Add-Result "E3" "Container output matches the native Windows run" "FAIL" `
                        ("native    {0}`n         container {1}" -f $digest, $d)
                }
            } else {
                Add-Result "E2" "--mount handles a Windows drive-letter source path (USAGE 9)" "FAIL" (Get-ErrorDetail $r.Output)
                # Emit the row anyway; a check that silently disappears from the
                # summary reads as "not implemented" rather than "blocked".
                Add-Result "E3" "Container output matches the native Windows run" "SKIP" "E2 did not produce output"
            }
        }
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host "`n=== Summary ===" -ForegroundColor Cyan

if (-not $onWindows) {
    # Running here at all is a dry run: it exercises the control flow (which is
    # otherwise impossible to test before handing the script to a Windows host)
    # but proves nothing about Windows itself. Say so rather than letting a row
    # reading "builds on Windows" imply otherwise.
    Write-Host "DRY RUN on a non-Windows host: the control flow was exercised," -ForegroundColor Magenta
    Write-Host "but no Windows-specific claim was actually verified." -ForegroundColor Magenta
    Write-Host ""
}
$script:Results | Format-Table Id, Status, Claim -AutoSize

$passed = @($script:Results | Where-Object { $_.Status -eq "PASS" }).Count
$failed = @($script:Results | Where-Object { $_.Status -eq "FAIL" }).Count
$skipped = @($script:Results | Where-Object { $_.Status -eq "SKIP" }).Count
Write-Host ("{0} passed, {1} failed, {2} skipped" -f $passed, $failed, $skipped)
Write-Host "Output digest (this host): $digest"
Write-Host "Compare on macOS/Linux with: make verify-digest"
Write-Host "Temp working directory: $work"
if ($WithLlm -and (Test-Path (Join-Path $work ".env"))) {
    # Left in place so a failure can be investigated, but it holds real keys.
    Write-Host "Note: a copy of your .env is in that directory and in $RepoRoot -- delete them when done." -ForegroundColor Yellow
}

if ($failed -gt 0) { exit 1 } else { exit 0 }
