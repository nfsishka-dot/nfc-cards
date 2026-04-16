#Requires -RunAsAdministrator
<#
  Пытается починить ситуацию «интернет только с VPN»:
  ставит DNS Cloudflare (1.1.1.1) на активные физические адаптеры и flush DNS.
  Запуск: правый клик → «Запуск от имени администратора» на fix-windows-dns.bat
  Перед запуском выключи VPN. После — проверь браузер без VPN.
#>

$ErrorActionPreference = 'Continue'
$DnsPrimary = '1.1.1.1'
$DnsSecondary = '1.0.0.1'

# Не трогаем типичные виртуальные/VPN-адаптеры
$ExcludeName = 'Loopback|VirtualBox|VMware|Wintun|TAP|Tailscale|ZeroTier|FlClash|Clash|vEthernet|VPN|Tun|Pseudo'

Write-Host ''
Write-Host 'Активные адаптеры (кроме виртуальных): задаю DNS' $DnsPrimary ',' $DnsSecondary -ForegroundColor Cyan

Get-NetAdapter -ErrorAction SilentlyContinue |
    Where-Object {
        $_.Status -eq 'Up' -and
        $_.Name -notmatch $ExcludeName
    } |
    ForEach-Object {
        $if = $_.InterfaceIndex
        $name = $_.Name
        try {
            Set-DnsClientServerAddress -InterfaceIndex $if -ServerAddresses @($DnsPrimary, $DnsSecondary) -ErrorAction Stop
            Write-Host "  OK: $name" -ForegroundColor Green
        }
        catch {
            Write-Host "  Пропуск $name : $_" -ForegroundColor Yellow
        }
    }

Write-Host ''
Write-Host 'Сброс кэша DNS...' -ForegroundColor Cyan
ipconfig /flushdns | Out-Null
Write-Host 'Готово.' -ForegroundColor Green
Write-Host ''
Write-Host 'Дальше: выключи VPN, открой любой сайт. Если не помогло — проблема не в DNS (провайдер/фильтрация).' -ForegroundColor DarkGray
Write-Host ''
Read-Host 'Нажми Enter для выхода'
