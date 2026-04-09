# Codex Profile Switch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one-click PowerShell scripts to switch Codex between official and external providers on Windows.

**Architecture:** Store small scripts under `D:\codex\tools\` that edit the existing Codex config file in the user's home directory. Each switch script validates the config path and target profile, then updates the top-level `profile` and `model_provider` keys to keep the active selection explicit.

**Tech Stack:** PowerShell 5+, Codex TOML config file, Windows user profile directory

---

### Task 1: Add the switching scripts

**Files:**
- Create: `D:\codex\tools\switch-official.ps1`
- Create: `D:\codex\tools\switch-external.ps1`
- Create: `D:\codex\tools\show-codex-profile.ps1`

- [ ] **Step 1: Create the status script**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$configPath = Join-Path $env:USERPROFILE '.codex\config.toml'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "未找到 Codex 配置文件: $configPath"
}

$content = Get-Content -LiteralPath $configPath -Raw
$profileMatch = [regex]::Match($content, '(?m)^profile = "(?<value>[^"]+)"$')
$providerMatch = [regex]::Match($content, '(?m)^model_provider = "(?<value>[^"]+)"$')

$profileValue = if ($profileMatch.Success) { $profileMatch.Groups['value'].Value } else { '未配置' }
$providerValue = if ($providerMatch.Success) { $providerMatch.Groups['value'].Value } else { '未配置' }

Write-Host "config: $configPath"
Write-Host "profile: $profileValue"
Write-Host "model_provider: $providerValue"
```

- [ ] **Step 2: Create the official switch script**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$configPath = Join-Path $env:USERPROFILE '.codex\config.toml'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "未找到 Codex 配置文件: $configPath"
}

$content = Get-Content -LiteralPath $configPath -Raw
if (-not [regex]::IsMatch($content, '(?m)^\[profiles\.official\]$')) {
    throw '配置中不存在 [profiles.official]，无法切换到官方接口。'
}

$updated = $content
if ([regex]::IsMatch($updated, '(?m)^profile = ".*"$')) {
    $updated = [regex]::Replace($updated, '(?m)^profile = ".*"$', 'profile = "official"', 1)
} else {
    $updated = $updated.TrimEnd("`r", "`n") + "`r`nprofile = `"official`"`r`n"
}

if ([regex]::IsMatch($updated, '(?m)^model_provider = ".*"$')) {
    $updated = [regex]::Replace($updated, '(?m)^model_provider = ".*"$', 'model_provider = "openai"', 1)
} else {
    $updated = 'model_provider = "openai"' + "`r`n" + $updated
}

Set-Content -LiteralPath $configPath -Value $updated -Encoding utf8
Write-Host '已切换到官方接口。'
Write-Host "config: $configPath"
Write-Host 'profile: official'
Write-Host 'model_provider: openai'
Write-Host '请重启 Codex 使配置生效。'
```

- [ ] **Step 3: Create the external switch script**

```powershell
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$configPath = Join-Path $env:USERPROFILE '.codex\config.toml'
if (-not (Test-Path -LiteralPath $configPath)) {
    throw "未找到 Codex 配置文件: $configPath"
}

$content = Get-Content -LiteralPath $configPath -Raw
if (-not [regex]::IsMatch($content, '(?m)^\[profiles\.external\]$')) {
    throw '配置中不存在 [profiles.external]，无法切换到外部接口。'
}

$updated = $content
if ([regex]::IsMatch($updated, '(?m)^profile = ".*"$')) {
    $updated = [regex]::Replace($updated, '(?m)^profile = ".*"$', 'profile = "external"', 1)
} else {
    $updated = $updated.TrimEnd("`r", "`n") + "`r`nprofile = `"external`"`r`n"
}

if ([regex]::IsMatch($updated, '(?m)^model_provider = ".*"$')) {
    $updated = [regex]::Replace($updated, '(?m)^model_provider = ".*"$', 'model_provider = "subrouter"', 1)
} else {
    $updated = 'model_provider = "subrouter"' + "`r`n" + $updated
}

Set-Content -LiteralPath $configPath -Value $updated -Encoding utf8
Write-Host '已切换到外部接口。'
Write-Host "config: $configPath"
Write-Host 'profile: external'
Write-Host 'model_provider: subrouter'
Write-Host '请重启 Codex 使配置生效。'
```

- [ ] **Step 4: Run the scripts to verify behavior**

Run: `powershell -ExecutionPolicy Bypass -File D:\codex\tools\show-codex-profile.ps1`  
Expected: prints current `profile` and `model_provider`

Run: `powershell -ExecutionPolicy Bypass -File D:\codex\tools\switch-external.ps1`  
Expected: switches to `profile: external` and `model_provider: subrouter`

Run: `powershell -ExecutionPolicy Bypass -File D:\codex\tools\switch-official.ps1`  
Expected: switches back to `profile: official` and `model_provider: openai`

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/plans/2026-03-31-codex-profile-switch.md tools/show-codex-profile.ps1 tools/switch-external.ps1 tools/switch-official.ps1
git commit -m "feat: add codex profile switch scripts"
```
