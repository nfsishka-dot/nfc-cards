# Запуск Django для доступа с телефона по Wi‑Fi.
# 1) Пытается открыть порт 8000 в брандмауэре Windows (один раз от администратора).
# 2) Показывает ссылки http://<ваш-IP>:8000/
# 3) Стартует runserver 0.0.0.0:8000

$ErrorActionPreference = "Continue"
$RuleName = "Django NFC dev TCP 8000"
$Port = if ($env:DJANGO_DEV_PORT) { $env:DJANGO_DEV_PORT } else { "8000" }

Set-Location (Split-Path -Parent $PSScriptRoot)

Write-Host ""
Write-Host "=== NFC site_admin — режим для мобилы (LAN) ===" -ForegroundColor White
Write-Host ""

$showRule = netsh advfirewall firewall show rule name="$RuleName" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Добавляю правило брандмауэра для входящих TCP $Port ..." -ForegroundColor Yellow
    netsh advfirewall firewall add rule name="$RuleName" dir=in action=allow protocol=TCP localport=$Port | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Host "Готово: входящие на порт $Port разрешены." -ForegroundColor Green
    }
    else {
        Write-Host "Не удалось добавить правило (нужны права администратора)." -ForegroundColor Red
        Write-Host "Откройте PowerShell от имени администратора и выполните:" -ForegroundColor Gray
        Write-Host "  netsh advfirewall firewall add rule name=`"$RuleName`" dir=in action=allow protocol=TCP localport=$Port" -ForegroundColor DarkGray
    }
}
else {
    Write-Host "Правило брандмауэра `"$RuleName`" уже есть." -ForegroundColor Green
}

Write-Host ""
Write-Host "Откройте на телефоне (тот же Wi‑Fi, только http, не https):" -ForegroundColor Cyan

Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue | Where-Object {
    $ip = $_.IPAddress
    $ip -notmatch '^127\.' -and
    $ip -notmatch '^169\.254\.' -and
    $ip -notmatch '^198\.18\.' -and
    (
        $ip -match '^192\.168\.' -or
        $ip -match '^10\.' -or
        $ip -match '^172\.(1[6-9]|2[0-9]|3[0-1])\.'
    )
} | Sort-Object -Property IPAddress -Unique | ForEach-Object {
    Write-Host ("  http://{0}:{1}/" -f $_.IPAddress, $Port) -ForegroundColor White
}

Write-Host ""
Write-Host "Если список пуст — смотрите IPv4 в ipconfig (адаптер Wi‑Fi / Ethernet)." -ForegroundColor DarkGray
Write-Host "На время проверки отключите VPN (FlClash и т.п.) на ПК." -ForegroundColor DarkGray
Write-Host ""
Write-Host "Запуск: python manage.py runserver 0.0.0.0:$Port" -ForegroundColor White
Write-Host ""

$env:DJANGO_DEV_PORT = $Port
python manage.py runserver "0.0.0.0:$Port"
