# demo.ps1 -- Trend Arbitrage & Zero-Day Response
# Usage:  .\demo.ps1

$ROOT = $PSScriptRoot

function Write-Step { param($msg) Write-Host "  >>  $msg" -ForegroundColor Cyan   }
function Write-Ok   { param($msg) Write-Host "  OK  $msg" -ForegroundColor Green  }
function Write-Warn { param($msg) Write-Host "  !!  $msg" -ForegroundColor Yellow }
function Write-Fail { param($msg) Write-Host " ERR  $msg" -ForegroundColor Red    }

Clear-Host
Write-Host ""
Write-Host "  TREND ARBITRAGE . ZERO-DAY RESPONSE" -ForegroundColor White
Write-Host "  --------------------------------------------------------" -ForegroundColor DarkGray
Write-Host ""

# -- 1. Clean ports 8000 and 3000 ----------------------------------------------
Write-Step "Cleaning ports 8000 and 3000..."
foreach ($port in @(8000, 3000)) {
    $lines = netstat -ano | Select-String ":${port}.*LISTENING"
    foreach ($line in $lines) {
        $procId = ($line.ToString().Trim() -split '\s+')[-1]
        if ($procId -match '^\d+$') {
            Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue
        }
    }
}
Start-Sleep -Seconds 1
Write-Ok "Ports cleared"

# -- 2. .env -------------------------------------------------------------------
Set-Location $ROOT
if (-not (Test-Path "$ROOT\.env")) {
    Write-Fail ".env not found. Copy .env.example to .env and fill in your values."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Ok ".env found"

# -- 2b. Load .env into current process so alembic / uvicorn inherit values ----
Write-Step "Loading .env into process environment..."
Get-Content "$ROOT\.env" | ForEach-Object {
    $line = $_.Trim()
    if ($line -and -not $line.StartsWith('#') -and $line -match '^([^=]+)=(.*)$') {
        $key = $matches[1].Trim()
        $val = $matches[2].Trim()
        if (($val.StartsWith('"') -and $val.EndsWith('"')) -or
            ($val.StartsWith("'") -and $val.EndsWith("'"))) {
            $val = $val.Substring(1, $val.Length - 2)
        }
        [System.Environment]::SetEnvironmentVariable($key, $val, 'Process')
    }
}
Write-Ok "Environment variables loaded"

# -- 3. Docker daemon ----------------------------------------------------------
Write-Step "Checking Docker..."
$dockerVer = docker version --format "{{.Server.Version}}"
if ($LASTEXITCODE -ne 0 -or -not $dockerVer) {
    Write-Fail "Docker daemon not responding. Start Docker Desktop and retry."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Ok "Docker Engine $dockerVer"

# -- 4. Locate Python (venv preferred) ----------------------------------------
$pythonExe = $null
foreach ($candidate in @(
    "$ROOT\.venv\Scripts\python.exe",
    "$ROOT\venv\Scripts\python.exe"
)) {
    if (Test-Path $candidate) { $pythonExe = $candidate; break }
}
if (-not $pythonExe) {
    $found = Get-Command python -ErrorAction SilentlyContinue
    if ($found) {
        $pythonExe = $found.Source
        Write-Warn "No .venv found -- using system Python: $pythonExe"
    } else {
        Write-Fail "Python not found. Create a .venv or install Python 3.11+."
        Read-Host "Press Enter to exit"
        exit 1
    }
} else {
    Write-Ok "Python: $pythonExe"
}

# -- 5. Docker Compose up ------------------------------------------------------
Write-Step "Starting Docker Compose services..."
docker compose up -d --remove-orphans
if ($LASTEXITCODE -ne 0) {
    Write-Fail "docker compose up failed. Check the output above."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Ok "Compose services requested"

# -- 6. Wait for PostgreSQL ----------------------------------------------------
Write-Step "Waiting for PostgreSQL (trend_postgres)..."
$timeout = 120; $elapsed = 0; $status = ""
while ($elapsed -lt $timeout) {
    $status = docker inspect --format "{{.State.Health.Status}}" trend_postgres
    if ($status -eq "healthy") { break }
    Start-Sleep -Seconds 4; $elapsed += 4
    Write-Host "    [$elapsed s] postgres: $status" -ForegroundColor DarkGray
}
if ($status -ne "healthy") {
    Write-Fail "PostgreSQL did not become healthy within ${timeout}s."
    Read-Host "Press Enter to exit"; exit 1
}
Write-Ok "PostgreSQL healthy"

# -- 7. Wait for Redis ---------------------------------------------------------
Write-Step "Waiting for Redis (trend_redis)..."
$timeout = 60; $elapsed = 0; $status = ""
while ($elapsed -lt $timeout) {
    $status = docker inspect --format "{{.State.Health.Status}}" trend_redis
    if ($status -eq "healthy") { break }
    Start-Sleep -Seconds 3; $elapsed += 3
    Write-Host "    [$elapsed s] redis: $status" -ForegroundColor DarkGray
}
if ($status -ne "healthy") {
    Write-Fail "Redis did not become healthy within ${timeout}s."
    Read-Host "Press Enter to exit"; exit 1
}
Write-Ok "Redis healthy"

# -- 8. Alembic migrations -----------------------------------------------------
Write-Step "Running Alembic migrations..."
$scriptsDir = Split-Path $pythonExe
$alembicExe = Join-Path $scriptsDir "alembic.exe"
if (-not (Test-Path $alembicExe)) {
    Write-Warn "alembic.exe not in venv -- using system alembic"
    $alembicExe = "alembic"
}
& $alembicExe upgrade head
if ($LASTEXITCODE -ne 0) {
    Write-Fail "Alembic migration failed. Check the output above."
    Read-Host "Press Enter to exit"; exit 1
}
Write-Ok "Database schema up to date"

# -- 8b. Verify uvicorn is installed -------------------------------------------
$uvicornCheck = & $pythonExe -c "import uvicorn" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Warn "uvicorn not found in venv. Installing requirements..."
    & $pythonExe -m pip install -r "$ROOT\requirements.txt" --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "pip install failed. Run: .venv\Scripts\pip install -r requirements.txt"
        Read-Host "Press Enter to exit"; exit 1
    }
    Write-Ok "Requirements installed"
}

# -- 9. FastAPI window ---------------------------------------------------------
Write-Step "Opening FastAPI window (port 8000)..."
$apiCmd = "`$host.UI.RawUI.WindowTitle = 'TA -- FastAPI :8000'; Write-Host '  FastAPI + uvicorn' -ForegroundColor Cyan; & '$pythonExe' -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload"
$apiEnc = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($apiCmd))
Start-Process powershell.exe -WorkingDirectory "$ROOT" -ArgumentList "-NoExit", "-EncodedCommand", $apiEnc
Write-Ok "FastAPI window opened"

# -- 10. Vite window -----------------------------------------------------------
if (-not (Test-Path "$ROOT\dashboard\node_modules")) {
    Write-Step "node_modules missing -- running npm install..."
    Push-Location "$ROOT\dashboard"
    npm install
    Pop-Location
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "npm install failed."
        Read-Host "Press Enter to exit"; exit 1
    }
    Write-Ok "npm install complete"
}
Write-Step "Opening Vite window (port 3000)..."
# Use node directly -- npm run dev invokes vite via cmd.exe which splits the
# path at the & in the folder name, causing MODULE_NOT_FOUND.
$viteCmd = "`$host.UI.RawUI.WindowTitle = 'TA -- Vite :3000'; Write-Host '  Vite dev server' -ForegroundColor Cyan; node .\node_modules\vite\bin\vite.js"
$viteEnc = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($viteCmd))
Start-Process powershell.exe -WorkingDirectory "$ROOT\dashboard" -ArgumentList "-NoExit", "-EncodedCommand", $viteEnc
Write-Ok "Vite window opened"

# -- 11. Open browser ----------------------------------------------------------
Write-Step "Giving services 5s to bind ports..."
Start-Sleep -Seconds 5
Start-Process "http://localhost:3000"

# -- Done ----------------------------------------------------------------------
Write-Host ""
Write-Host "  --------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  Services running:" -ForegroundColor White
Write-Host "    Dashboard  ->  http://localhost:3000"      -ForegroundColor Cyan
Write-Host "    API docs   ->  http://localhost:8000/docs"  -ForegroundColor Cyan
Write-Host "    Airflow    ->  http://localhost:8080  (admin / admin)" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Kafka and Airflow warm up in the background (~2 min)." -ForegroundColor DarkGray
Write-Host "  Close FastAPI and Vite windows to stop those services." -ForegroundColor DarkGray
Write-Host "  Run: docker compose down   to stop all infrastructure." -ForegroundColor DarkGray
Write-Host ""
