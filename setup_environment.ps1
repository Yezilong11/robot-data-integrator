# setup_environment.ps1
# 环境准备脚本
# 功能：检查 Python 版本、磁盘空间、网络、创建必要目录、配置 .env 文件

[CmdletBinding()]
param(
    [switch]$SkipInstall = $false
)

$ErrorActionPreference = "Stop"
$ProjectRoot = "d:\tiaozhanbei\robot-data-integrator"

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "  环境准备脚本" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""

# ─── 步骤 1: 检查 Python 版本 ───
Write-Host "[1/8] 检查 Python 版本..." -ForegroundColor Yellow
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "  ❌ Python 未安装" -ForegroundColor Red
    Write-Host "  请先安装 Python 3.11+: https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}
Write-Host "  ✅ $pythonVersion" -ForegroundColor Green

# ─── 步骤 2: 检查磁盘空间 ───
Write-Host "[2/8] 检查磁盘空间..." -ForegroundColor Yellow
$drive = Get-PSDrive C
$freeGB = [math]::Round($drive.Free / 1GB, 2)
$requiredGB = 60
if ($freeGB -lt $requiredGB) {
    Write-Host "  ⚠️  可用空间: $freeGB GB（建议至少 $requiredGB GB）" -ForegroundColor Yellow
} else {
    Write-Host "  ✅ 可用空间: $freeGB GB" -ForegroundColor Green
}

# ─── 步骤 3: 检查网络连接 ───
Write-Host "[3/8] 检查网络连接..." -ForegroundColor Yellow
$testUrls = @(
    "github.com",
    "arxiv.org",
    "huggingface.co",
    "zenodo.org"
)
foreach ($url in $testUrls) {
    try {
        $result = Test-NetConnection -ComputerName $url -Port 443 -WarningAction SilentlyContinue -InformationLevel Quiet
        if ($result) {
            Write-Host "  ✅ $url" -ForegroundColor Green
        } else {
            Write-Host "  ⚠️  $url 连接失败" -ForegroundColor Yellow
        }
    } catch {
        Write-Host "  ⚠️  $url 测试失败" -ForegroundColor Yellow
    }
}

# ─── 步骤 4: 创建项目目录结构 ───
Write-Host "[4/8] 创建项目目录结构..." -ForegroundColor Yellow
$dirs = @(
    "$ProjectRoot\scripts",
    "$ProjectRoot\data\sources\api\arxiv\metadata",
    "$ProjectRoot\data\sources\api\arxiv\pdfs",
    "$ProjectRoot\data\sources\api\github\repos",
    "$ProjectRoot\data\sources\api\github\releases",
    "$ProjectRoot\data\sources\api\huggingface\models",
    "$ProjectRoot\data\sources\api\huggingface\datasets",
    "$ProjectRoot\data\sources\api\zenodo\records",
    "$ProjectRoot\data\sources\api\ieee\metadata",
    "$ProjectRoot\data\sources\api\ieee\pdfs",
    "$ProjectRoot\data\sources\web\franka\panda",
    "$ProjectRoot\data\sources\web\robotiq\grippers",
    "$ProjectRoot\data\sources\web\allegro\hand",
    "$ProjectRoot\data\sources\web\paperswithcode\papers",
    "$ProjectRoot\data\sources\web\mujoco\examples",
    "$ProjectRoot\data\sources\web\isaac\examples",
    "$ProjectRoot\data\sources\datasets\graspnet\dataset",
    "$ProjectRoot\data\sources\datasets\graspnet\models",
    "$ProjectRoot\data\sources\datasets\graspnet\calibration",
    "$ProjectRoot\data\sources\datasets\dexgraspnet\data",
    "$ProjectRoot\data\sources\datasets\ycb\models",
    "$ProjectRoot\data\sources\datasets\google_scanned\models",
    "$ProjectRoot\data\sources\papers",
    "$ProjectRoot\data\experience_db",
    "$ProjectRoot\data\output_packages"
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Force -Path $d | Out-Null
        Write-Host "    创建: $d"
    }
}
Write-Host "  ✅ 目录结构完成" -ForegroundColor Green

# ─── 步骤 5: 配置 .env 文件 ───
Write-Host "[5/8] 配置 .env 文件..." -ForegroundColor Yellow
$envFile = "$ProjectRoot\.env"
$envExample = "$ProjectRoot\.env.example"

if (Test-Path $envExample) {
    if (-not (Test-Path $envFile)) {
        Copy-Item $envExample $envFile
        Write-Host "  ✅ 已从 .env.example 复制 .env" -ForegroundColor Green
    } else {
        Write-Host "  ✅ .env 已存在" -ForegroundColor Green
    }
} else {
    # 创建 .env 模板
    @"
# 千问模型
QWEN_API_KEY=
QWEN_MODEL=qwen-plus
QWEN_EMBEDDING_MODEL=text-embedding-v3

# GitHub
GITHUB_TOKEN=

# IEEE
IEEE_API_KEY=

# HuggingFace（可选）
HUGGINGFACE_TOKEN=

# Adapter
ADAPTER_TIMEOUT=30.0
ADAPTER_MAX_RETRY=3
ADAPTER_RATE_LIMIT=10
ADAPTER_CACHE_TTL=3600

# ChromaDB
CHROMADB_PATH=./data/experience_db

# 输出
OUTPUT_DIR=./data/output_packages

# 日志
LOG_LEVEL=INFO
LOG_FORMAT=json
"@ | Out-File -FilePath $envFile -Encoding utf8
    Write-Host "  ✅ 已创建 .env 模板" -ForegroundColor Green
}

Write-Host "  ⚠️  请编辑 $envFile 填入你的 API Key" -ForegroundColor Yellow

# ─── 步骤 6: 安装 Python 依赖 ───
if (-not $SkipInstall) {
    Write-Host "[6/8] 安装 Python 依赖..." -ForegroundColor Yellow
    Set-Location $ProjectRoot
    pip install -e . --quiet
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  ✅ Python 依赖安装完成" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  Python 依赖安装失败" -ForegroundColor Yellow
    }
} else {
    Write-Host "[6/8] 跳过 Python 依赖安装 (--SkipInstall)" -ForegroundColor Yellow
}

# ─── 步骤 7: 检查/安装下载工具 ───
Write-Host "[7/8] 检查下载工具..." -ForegroundColor Yellow
$tools = @{
    "git" = "Git.Git"
    "aria2c" = "aria2.aria2"
    "7z" = "7zip.7zip"
}

foreach ($tool in $tools.Keys) {
    $cmd = Get-Command $tool -ErrorAction SilentlyContinue
    if ($cmd) {
        Write-Host "  ✅ $tool 已安装: $($cmd.Source)" -ForegroundColor Green
    } else {
        Write-Host "  ⚠️  $tool 未安装 (建议: winget install $($tools[$tool]))" -ForegroundColor Yellow
    }
}

# ─── 步骤 8: 创建下载日志目录 ───
Write-Host "[8/8] 创建下载日志..." -ForegroundColor Yellow
$logDir = "$ProjectRoot\data\download_logs"
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$logFile = "$logDir\download_history_$(Get-Date -Format 'yyyyMMdd').log"
"环境准备完成时间: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')" | Out-File -FilePath $logFile
Write-Host "  ✅ 日志文件: $logFile" -ForegroundColor Green

Write-Host ""
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "  环境准备完成" -ForegroundColor Cyan
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host ""
Write-Host "下一步操作:" -ForegroundColor Yellow
Write-Host "  1. 编辑 $envFile 填入 GITHUB_TOKEN（必需）" -ForegroundColor White
Write-Host "  2. 运行连通性测试: python scripts\test_connectivity.py" -ForegroundColor White
Write-Host "  3. 下载 YCB 物体: python scripts\download_ycb_batch.py" -ForegroundColor White
Write-Host "  4. 下载 Allegro URDF: python scripts\download_allegro_alt.py" -ForegroundColor White
Write-Host "  5. 查看下载进度: python scripts\check_download_progress.py" -ForegroundColor White
Write-Host ""
