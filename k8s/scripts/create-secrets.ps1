<#
.SYNOPSIS
  backend/.env 를 읽어서 dearvoice 네임스페이스에 실제 Kubernetes Secret 을 만듭니다.

.DESCRIPTION
  만드는 Secret
    - mysql-secret   : MySQL 계정. 이미 있으면 그대로 둡니다. 없으면 비밀번호를 무작위로 만듭니다.
    - backend-secret : backend 비밀 값. .env 에서 읽고, DB_USER / DB_PASSWORD 는 mysql-secret 에서 가져옵니다.
    - google-tts-key : .env 의 GOOGLE_APPLICATION_CREDENTIALS 경로에 있는 키 파일.

  - 비밀 값은 화면에 출력하지 않고, 파일로도 저장하지 않습니다. (kubectl 에 바로 전달)
  - 다시 실행해도 안전합니다. .env 값이 바뀌었으면 Secret 만 새 값으로 바뀝니다.
  - .env 의 DB_USER / DB_PASSWORD / DB_HOST 는 내 PC 의 MySQL 용이라 쓰지 않습니다.

.EXAMPLE
  powershell -ExecutionPolicy Bypass -File k8s/scripts/create-secrets.ps1
#>
param(
    [string]$EnvFile = (Join-Path $PSScriptRoot "..\..\backend\.env"),
    [string]$Namespace = "dearvoice",
    [string]$MysqlUser = "dearvoice_dev"
)

$ErrorActionPreference = "Stop"

# backend-secret 에 넣을 키 (backend/config/settings.py 가 읽는 비밀 값)
$BackendSecretKeys = @(
    "SECRET_KEY",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "CLOVA_SPEECH_SECRET_KEY",
    "CLOVA_SPEECH_INVOKE_URL",
    "OPENAI_API_KEY",
    "EMAIL_HOST_USER",
    "EMAIL_HOST_PASSWORD"
)
# 꼭 있어야 하는 키 (없으면 Django 가 시작하지 않음)
$RequiredKeys = @("SECRET_KEY")

function Write-Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Write-Warn($msg) { Write-Host "  [경고] $msg" -ForegroundColor Yellow }
function Stop-WithError($msg) { Write-Host "[오류] $msg" -ForegroundColor Red; exit 1 }

function Read-EnvFile($path) {
    $result = @{}
    foreach ($line in Get-Content -LiteralPath $path -Encoding UTF8) {
        $trimmed = $line.Trim()
        if ($trimmed -eq "" -or $trimmed.StartsWith("#")) { continue }
        $idx = $trimmed.IndexOf("=")
        if ($idx -lt 1) { continue }
        $key = $trimmed.Substring(0, $idx).Trim()
        $value = $trimmed.Substring($idx + 1).Trim()
        if ($value.Length -ge 2 -and (($value.StartsWith('"') -and $value.EndsWith('"')) -or ($value.StartsWith("'") -and $value.EndsWith("'")))) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $result[$key] = $value
    }
    return $result
}

function Test-Placeholder($value) {
    return ($value -eq "" -or $value -match '^(your-|change-me)' -or $value -match 'example\.com')
}

function New-RandomPassword([int]$length = 24) {
    $chars = [char[]]'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789'
    $bytes = New-Object byte[] $length
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    return -join ($bytes | ForEach-Object { $chars[$_ % $chars.Length] })
}

function ConvertTo-B64([string]$text) {
    return [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes($text))
}

function ConvertFrom-B64([string]$b64) {
    return [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($b64))
}

# 값을 base64 로 바꿔 kubectl 표준입력으로 바로 넘깁니다. (디스크/화면에 남기지 않음)
function Set-K8sSecret([string]$name, [hashtable]$b64Data) {
    $manifest = [ordered]@{
        apiVersion = "v1"
        kind       = "Secret"
        type       = "Opaque"
        metadata   = [ordered]@{
            name      = $name
            namespace = $Namespace
            labels    = [ordered]@{
                "app.kubernetes.io/part-of"    = "dearvoice"
                "app.kubernetes.io/managed-by" = "create-secrets-script"
            }
        }
        data       = $b64Data
    }
    $json = $manifest | ConvertTo-Json -Depth 5 -Compress
    # --server-side: 값이 last-applied 주석에 한 번 더 복사되지 않도록 합니다.
    $json | kubectl apply --server-side --force-conflicts --field-manager=create-secrets -f - | Out-Null
    if ($LASTEXITCODE -ne 0) { Stop-WithError "$name 적용에 실패했습니다." }
}

function Get-K8sSecretData([string]$name) {
    $raw = kubectl -n $Namespace get secret $name -o json --ignore-not-found 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    $obj = ($raw -join "`n") | ConvertFrom-Json
    $data = @{}
    foreach ($p in $obj.data.PSObject.Properties) { $data[$p.Name] = ConvertFrom-B64 $p.Value }
    return $data
}

# ---------------------------------------------------------------- 사전 확인
Write-Step "사전 확인"
if (-not (Get-Command kubectl -ErrorAction SilentlyContinue)) {
    Stop-WithError "kubectl 을 찾을 수 없습니다. Docker Desktop 의 Kubernetes 를 켰는지 확인해 주세요."
}
if (-not (Test-Path -LiteralPath $EnvFile)) {
    Stop-WithError ".env 파일이 없습니다: $EnvFile (backend/.env.example 을 복사해서 만들어 주세요)"
}
kubectl get namespace $Namespace 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Stop-WithError "'$Namespace' 네임스페이스가 없습니다. 먼저 'kubectl apply -k k8s' 를 실행해 주세요."
}
Write-Host "  클러스터: $(kubectl config current-context)"
Write-Host "  .env    : $((Resolve-Path -LiteralPath $EnvFile).Path)"
$envValues = Read-EnvFile $EnvFile

# ---------------------------------------------------------------- mysql-secret
Write-Step "mysql-secret"
$mysql = Get-K8sSecretData "mysql-secret"
if ($mysql -and $mysql["MYSQL_USER"] -and $mysql["MYSQL_PASSWORD"]) {
    Write-Host "  이미 있어서 그대로 둡니다. (MySQL 은 처음 시작할 때만 계정을 만들기 때문에 바꾸지 않습니다)"
} else {
    $dbName = if ($envValues["DB_NAME"]) { $envValues["DB_NAME"] } else { "dearvoice_db" }
    $mysql = @{
        MYSQL_ROOT_PASSWORD = New-RandomPassword
        MYSQL_DATABASE      = $dbName
        MYSQL_USER          = $MysqlUser
        MYSQL_PASSWORD      = New-RandomPassword
    }
    $b64 = @{}
    foreach ($k in $mysql.Keys) { $b64[$k] = ConvertTo-B64 $mysql[$k] }
    Set-K8sSecret "mysql-secret" $b64
    Write-Host "  새로 만들었습니다. (비밀번호는 무작위로 생성)"
}

# ---------------------------------------------------------------- backend-secret
Write-Step "backend-secret"
$backend = @{
    DB_USER     = ConvertTo-B64 $mysql["MYSQL_USER"]
    DB_PASSWORD = ConvertTo-B64 $mysql["MYSQL_PASSWORD"]
}
$missing = @()
$placeholders = @()
foreach ($k in $BackendSecretKeys) {
    if (-not $envValues.ContainsKey($k)) { $missing += $k; continue }
    $v = $envValues[$k]
    if (Test-Placeholder $v) { $placeholders += $k }
    $backend[$k] = ConvertTo-B64 $v
}
foreach ($k in $RequiredKeys) {
    if ($missing -contains $k) { Stop-WithError ".env 에 $k 가 없습니다. backend 가 시작하지 못하니 채워 주세요." }
}
Set-K8sSecret "backend-secret" $backend
Write-Host "  넣은 키: $(($backend.Keys | Sort-Object) -join ', ')"
if ($missing.Count -gt 0) { Write-Warn ".env 에 없어서 빠진 키: $($missing -join ', ')" }
if ($placeholders.Count -gt 0) { Write-Warn "예시 값 그대로인 키 (해당 기능이 동작하지 않음): $($placeholders -join ', ')" }

# ---------------------------------------------------------------- google-tts-key
Write-Step "google-tts-key"
$keyPath = $envValues["GOOGLE_APPLICATION_CREDENTIALS"]
if ($keyPath -and (Test-Path -LiteralPath $keyPath -PathType Leaf)) {
    $bytes = [IO.File]::ReadAllBytes((Resolve-Path -LiteralPath $keyPath).Path)
    Set-K8sSecret "google-tts-key" @{ "google-tts.json" = [Convert]::ToBase64String($bytes) }
    Write-Host "  키 파일을 key.json 으로 넣었습니다."
} else {
    Write-Warn "GOOGLE_APPLICATION_CREDENTIALS 경로에 파일이 없어 건너뜁니다. (TTS 기능만 동작하지 않음)"
}

# ---------------------------------------------------------------- 마무리
Write-Step "완료"
kubectl -n $Namespace get secret mysql-secret backend-secret google-tts-key --ignore-not-found
Write-Host ""
Write-Host "Secret 을 바꾼 뒤에는 backend 를 다시 시작해야 새 값이 적용됩니다:"
Write-Host "  kubectl -n $Namespace rollout restart deployment/backend"
