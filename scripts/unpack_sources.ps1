# unpack_sources.ps1
# 统一解压脚本
# 功能:扫描 data/sources/ 下所有压缩包,按格式分发到对应解压工具
#       支持断点续解压(已存在目录跳过)、自动清理压缩包、记录日志
#
# 用法:
#   pwsh scripts/unpack_sources.ps1                  # 默认解压全部格式
#   pwsh scripts/unpack_sources.ps1 -DryRun          # 只列出待处理文件
#   pwsh scripts/unpack_sources.ps1 -KeepZip         # 解压后保留压缩包
#   pwsh scripts/unpack_sources.ps1 -Format zip      # 只处理 .zip
#   pwsh scripts/unpack_sources.ps1 -Format tar      # 只处理 .tar.gz/.tar.bz2
#   pwsh scripts/unpack_sources.ps1 -Format 7z       # 只处理 .7z
#   pwsh scripts/unpack_sources.ps1 -Format all      # 处理所有(默认)
#
# 作者:挑战杯团队
# 创建日期:2026-07-15

[CmdletBinding()]
param(
    [switch]$DryRun = $false,
    [switch]$KeepZip = $false,
    [ValidateSet("all", "zip", "tar", "7z")]
    [string]$Format = "all"
)

$ErrorActionPreference = "Continue"

# ─── 配置 ───
$ProjectRoot = "d:\tiaozhanbei\robot-data-integrator"
$DataRoot    = Join-Path $ProjectRoot "data\sources"
$LogDir      = Join-Path $ProjectRoot "data\logs"
$Timestamp   = Get-Date -Format "yyyyMMdd_HHmmss"
$LogFile     = Join-Path $LogDir "unpack_$Timestamp.log"

# ─── 初始化日志目录 ───
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
}

# ─── 日志函数 ───
function Write-Log {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[$(Get-Date -Format 'HH:mm:ss')] [$Level] $Message"
    Write-Host $line
    Add-Content -Path $LogFile -Value $line -Encoding utf8
}

# ─── 解压单个文件 ───
function Expand-ArchiveFile {
    param(
        [System.IO.FileInfo]$File,
        [string]$TargetDir
    )
    $ext = $File.Extension.ToLower()
    $baseName = $File.BaseName -replace '\.tar$', ''

    try {
        switch ($ext) {
            ".zip" {
                Write-Log "解压(zip): $($File.Name) -> $TargetDir"
                # 优先 Expand-Archive,失败回退 7z
                try {
                    Expand-Archive -Path $File.FullName -DestinationPath $TargetDir -Force -ErrorAction Stop
                } catch {
                    if (Get-Command 7z -ErrorAction SilentlyContinue) {
                        Write-Log "  Expand-Archive 失败,回退 7z" "WARN"
                        & 7z x $File.FullName "-o$TargetDir" -y | Out-Null
                    } else {
                        throw $_
                    }
                }
            }
            ".gz" {
                if ($File.Name -like "*.tar.gz") {
                    $tarPath = $File.FullName -replace '\.gz$', ''
                    Write-Log "解压(tar.gz): $($File.Name) -> $TargetDir"
                    # 先解压 .gz
                    if (Get-Command 7z -ErrorAction SilentlyContinue) {
                        & 7z x $File.FullName "-o$TargetDir" -y | Out-Null
                    } else {
                        # PowerShell 7+ 内置 tar
                        tar -xzf $File.FullName -C $TargetDir
                    }
                } else {
                    Write-Log "解压(gz): $($File.Name) -> $TargetDir"
                    tar -xzf $File.FullName -C $TargetDir
                }
            }
            ".bz2" {
                if ($File.Name -like "*.tar.bz2") {
                    Write-Log "解压(tar.bz2): $($File.Name) -> $TargetDir"
                    tar -xjf $File.FullName -C $TargetDir
                } else {
                    Write-Log "解压(bz2): $($File.Name) -> $TargetDir"
                    tar -xjf $File.FullName -C $TargetDir
                }
            }
            ".xz" {
                if ($File.Name -like "*.tar.xz") {
                    Write-Log "解压(tar.xz): $($File.Name) -> $TargetDir"
                    tar -xJf $File.FullName -C $TargetDir
                } else {
                    Write-Log "解压(xz): $($File.Name) -> $TargetDir"
                    tar -xJf $File.FullName -C $TargetDir
                }
            }
            ".7z" {
                Write-Log "解压(7z): $($File.Name) -> $TargetDir"
                if (Get-Command 7z -ErrorAction SilentlyContinue) {
                    & 7z x $File.FullName "-o$TargetDir" -y | Out-Null
                } else {
                    throw "7z 未安装,无法解压 .7z 文件。请先运行: winget install 7zip.7zip"
                }
            }
            default {
                Write-Log "跳过未知格式: $($File.Name)" "WARN"
                return $false
            }
        }
        return $true
    } catch {
        Write-Log "解压失败: $($File.Name) - $_" "ERROR"
        return $false
    }
}

# ─── 统计目录中的文件数 ───
function Get-DirFileCount {
    param([string]$Path)
    if (Test-Path $Path) {
        return (Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
    }
    return 0
}

# ─── 主流程 ───
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "  统一解压脚本" -ForegroundColor Cyan
Write-Host "=" * 70 -ForegroundColor Cyan
Write-Host "数据根: $DataRoot"
Write-Host "日志文件: $LogFile"
Write-Host "模式: $(if ($DryRun) {'预览'} else {'实际解压'}) | 格式: $Format | 保留压缩包: $KeepZip"
Write-Host ""

if (-not (Test-Path $DataRoot)) {
    Write-Log "数据根目录不存在: $DataRoot" "ERROR"
    exit 1
}

# ─── 扫描压缩包 ───
Write-Host "[1/3] 扫描压缩包..." -ForegroundColor Yellow
Write-Log "开始扫描压缩包,模式: $Format"

$patterns = @()
if ($Format -eq "all") { $patterns = @("*.zip", "*.tar.gz", "*.tar.bz2", "*.tar.xz", "*.7z", "*.gz", "*.bz2", "*.xz") }
elseif ($Format -eq "zip") { $patterns = @("*.zip") }
elseif ($Format -eq "tar") { $patterns = @("*.tar.gz", "*.tar.bz2", "*.tar.xz", "*.gz", "*.bz2", "*.xz") }
elseif ($Format -eq "7z") { $patterns = @("*.7z") }

$archives = @()
foreach ($pat in $patterns) {
    $found = Get-ChildItem -Path $DataRoot -Recurse -File -Filter $pat -ErrorAction SilentlyContinue
    $archives += $found
}

if ($archives.Count -eq 0) {
    Write-Host "  ℹ️  未发现压缩包" -ForegroundColor Gray
    Write-Log "未发现压缩包,退出"
    exit 0
}

Write-Host "  发现 $($archives.Count) 个压缩包"
foreach ($a in $archives) {
    $rel = $a.FullName.Substring($DataRoot.Length)
    Write-Host "    - $rel ($([math]::Round($a.Length/1MB, 1)) MB)"
}
Write-Host ""

# ─── 解压 ───
$success = 0
$failed = 0
$skipped = 0

if (-not $DryRun) {
    Write-Host "[2/3] 解压中..." -ForegroundColor Yellow
    foreach ($archive in $archives) {
        # 计算目标目录
        # data/sources/datasets/ycb/002_master_chef_can.zip -> data/sources/datasets/ycb/002_master_chef_can/
        $targetDir = $archive.Directory.FullName
        # 特殊处理:对于 ycb 等场景,目标目录名为 zip 的 basename
        # (保持现有结构)

        # 断点续解压:若目标目录已存在且非空,跳过
        $existingCount = Get-DirFileCount $targetDir
        if ($existingCount -gt 0) {
            # 检查是否存在同名子目录(用于单文件解压到子目录)
            $expectedSubDir = Join-Path $targetDir $archive.BaseName
            if (Test-Path $expectedSubDir) {
                $subCount = Get-DirFileCount $expectedSubDir
                if ($subCount -gt 0) {
                    Write-Log "  跳过(已存在): $($archive.Name) -> $expectedSubDir ($subCount 文件)"
                    $skipped++
                    continue
                }
            } elseif ($existingCount -gt 5) {
                # 目标目录已有足够文件,认为已解压
                Write-Log "  跳过(已存在): $($archive.Name) 所在目录 $existingCount 文件"
                $skipped++
                continue
            }
        }

        if (Expand-ArchiveFile -File $archive -TargetDir $targetDir) {
            $fileCount = Get-DirFileCount $targetDir
            $sizeMB = [math]::Round($archive.Length/1MB, 1)
            Write-Log "  ✅ $($archive.Name): $fileCount 文件, $sizeMB MB"
            $success++

            # 清理压缩包(可选)
            if (-not $KeepZip) {
                try {
                    Remove-Item $archive.FullName -Force
                    Write-Log "    🗑️  已删除压缩包: $($archive.Name)"
                } catch {
                    Write-Log "    ⚠️  删除压缩包失败: $($archive.Name) - $_" "WARN"
                }
            }
        } else {
            $failed++
        }
    }
} else {
    Write-Host "[2/3] DRY-RUN: 跳过实际解压" -ForegroundColor Yellow
}

# ─── 汇总 ───
Write-Host ""
Write-Host "[3/3] 汇总" -ForegroundColor Yellow
if ($DryRun) {
    Write-Host "  📋 DRY-RUN: 共发现 $($archives.Count) 个待处理压缩包" -ForegroundColor Cyan
} else {
    Write-Host "  ✅ 成功: $success" -ForegroundColor Green
    Write-Host "  ❌ 失败: $failed" -ForegroundColor Red
    Write-Host "  ⏭️  跳过: $skipped" -ForegroundColor Yellow
    Write-Log "完成: 成功 $success, 失败 $failed, 跳过 $skipped"
}

Write-Host ""
Write-Host "日志文件: $LogFile" -ForegroundColor Gray
Write-Host ""
