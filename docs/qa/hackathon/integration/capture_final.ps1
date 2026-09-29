[CmdletBinding()]
param(
    [int]$ServerPort = 5127,
    [int]$DevToolsPort = 9230
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..\..\..")).Path
$outputDirectory = Join-Path $PSScriptRoot "screenshots"
$instanceDirectory = Join-Path $repositoryRoot "instance"
$databasePath = Join-Path $instanceDirectory "realtags.sqlite3"
$databaseExistedBefore = Test-Path -LiteralPath $databasePath

if ($databaseExistedBefore) {
    throw "Refusing to overwrite the existing local instance database."
}

$browserCandidates = @(
    "C:\Program Files\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    "C:\Program Files\Microsoft\Edge\Application\msedge.exe"
)
$browserPath = $browserCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $browserPath) {
    throw "Chrome or Edge is required for final screenshot capture."
}

function Test-LocalPort {
    param([int]$Port)

    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $task = $client.ConnectAsync("127.0.0.1", $Port)
        return $task.Wait(200) -and $client.Connected
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

function Wait-HttpReady {
    param(
        [string]$Uri,
        [System.Diagnostics.Process]$Process
    )

    for ($attempt = 0; $attempt -lt 40; $attempt += 1) {
        $Process.Refresh()
        if ($Process.HasExited) {
            throw "Background process exited before $Uri became ready."
        }
        try {
            $response = Invoke-WebRequest -UseBasicParsing -Uri $Uri -TimeoutSec 1
            if ($response.StatusCode -eq 200) {
                return
            }
        }
        catch {
            Start-Sleep -Milliseconds 250
        }
    }
    throw "$Uri did not become ready."
}

if (Test-LocalPort -Port $ServerPort) {
    throw "Server port $ServerPort is already in use."
}
if (Test-LocalPort -Port $DevToolsPort) {
    throw "DevTools port $DevToolsPort is already in use."
}

$tempBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$captureTemp = Join-Path $tempBase ("realtags-int001-" + [Guid]::NewGuid().ToString("N"))
$chromeProfile = Join-Path $captureTemp "chrome-profile"
New-Item -ItemType Directory -Path $chromeProfile | Out-Null

$serverProcess = $null
$browserProcess = $null
$captureSucceeded = $false

try {
    $env:DEMO_MODE = "1"
    $env:FLASK_SECRET_KEY = "integration-capture-only"
    $serverProcess = Start-Process `
        -FilePath (Join-Path $repositoryRoot ".venv\Scripts\python.exe") `
        -ArgumentList @(
            "-m", "flask", "--app", "run.py", "run",
            "--host", "127.0.0.1", "--port", [string]$ServerPort, "--no-reload"
        ) `
        -WorkingDirectory $repositoryRoot `
        -WindowStyle Hidden `
        -PassThru
    Remove-Item Env:DEMO_MODE -ErrorAction SilentlyContinue
    Remove-Item Env:FLASK_SECRET_KEY -ErrorAction SilentlyContinue

    Wait-HttpReady -Uri "http://127.0.0.1:$ServerPort/" -Process $serverProcess

    $browserProcess = Start-Process `
        -FilePath $browserPath `
        -ArgumentList @(
            "--headless=new",
            "--remote-debugging-port=$DevToolsPort",
            "--user-data-dir=$chromeProfile",
            "--disable-gpu",
            "--disable-background-networking",
            "--disable-component-update",
            "--disable-sync",
            "--no-first-run",
            "--no-default-browser-check",
            "about:blank"
        ) `
        -WindowStyle Hidden `
        -PassThru

    Wait-HttpReady -Uri "http://127.0.0.1:$DevToolsPort/json/version" -Process $browserProcess

    & node `
        (Join-Path $repositoryRoot "docs\qa\hackathon\ui\capture_evidence.mjs") `
        ([string]$DevToolsPort) `
        "http://127.0.0.1:$ServerPort/" `
        $outputDirectory
    if ($LASTEXITCODE -ne 0) {
        throw "Capture runner exited with code $LASTEXITCODE."
    }
    $captureSucceeded = $true
}
finally {
    Remove-Item Env:DEMO_MODE -ErrorAction SilentlyContinue
    Remove-Item Env:FLASK_SECRET_KEY -ErrorAction SilentlyContinue

    if ($browserProcess -and -not $browserProcess.HasExited) {
        Stop-Process -Id $browserProcess.Id -Force
        Wait-Process -Id $browserProcess.Id -ErrorAction SilentlyContinue
    }
    if ($serverProcess -and -not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force
        Wait-Process -Id $serverProcess.Id -ErrorAction SilentlyContinue
    }

    if (Test-Path -LiteralPath $databasePath) {
        Remove-Item -LiteralPath $databasePath -Force
    }

    $resolvedTemp = (Resolve-Path -LiteralPath $captureTemp).Path
    $tempPrefix = $tempBase.TrimEnd("\") + "\"
    $tempLeaf = Split-Path -Leaf $resolvedTemp
    if (
        $resolvedTemp.StartsWith($tempPrefix, [System.StringComparison]::OrdinalIgnoreCase) -and
        $tempLeaf.StartsWith("realtags-int001-")
    ) {
        Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
    }
    else {
        throw "Refusing to remove an unverified capture temporary directory."
    }
}

if (-not $captureSucceeded) {
    exit 1
}
