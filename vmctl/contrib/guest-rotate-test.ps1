# vmctl self-rotate test (run inside the Windows guest, PowerShell 5.1 OK)
#   powershell -ExecutionPolicy Bypass -File .\guest-rotate-test.ps1          # check only
#   powershell -ExecutionPolicy Bypass -File .\guest-rotate-test.ps1 -Rotate  # really rotate (VM will be force-killed)
param(
    [switch]$Rotate,
    [string]$HostAddr = "",
    [int]$Port = 8787
)
$ErrorActionPreference = "Stop"

function Show($title, $obj) {
    Write-Host "== $title" -ForegroundColor Cyan
    $obj | ConvertTo-Json -Depth 6 | Write-Host
}

# 1. local network info (pure .NET, no CIM/WMI: works on stripped LTSC)
$myIp = ""; $mac = ""; $gw = ""
foreach ($nic in [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces()) {
    if ($nic.OperationalStatus -ne "Up") { continue }
    if ($nic.NetworkInterfaceType -eq "Loopback") { continue }
    $props = $nic.GetIPProperties()
    $g = $props.GatewayAddresses | Where-Object { $_.Address.AddressFamily -eq "InterNetwork" -and $_.Address.ToString() -ne "0.0.0.0" } | Select-Object -First 1
    if (-not $g) { continue }
    $a = $props.UnicastAddresses | Where-Object { $_.Address.AddressFamily -eq "InterNetwork" } | Select-Object -First 1
    $myIp = $a.Address.ToString()
    $mac  = ($nic.GetPhysicalAddress().ToString() -replace '(..)(?!$)', '$1-')
    $gw   = $g.Address.ToString()
    break
}
if (-not $gw) {
    # fallback: parse "route print"
    $line = route print -4 | Select-String '^\s*0\.0\.0\.0\s+0\.0\.0\.0\s+(\S+)\s+(\S+)' | Select-Object -First 1
    if ($line) { $gw = $line.Matches[0].Groups[1].Value; $myIp = $line.Matches[0].Groups[2].Value }
}
Write-Host "guest ip  = $myIp"
Write-Host "guest mac = $mac"
Write-Host "gateway   = $gw"

# 2. pick host: -HostAddr, else gateway, else LAN ip
$candidates = @()
if ($HostAddr) { $candidates += $HostAddr }
if ($gw) { $candidates += $gw }
$candidates += "192.168.4.158"
$base = $null
foreach ($h in $candidates) {
    $u = "http://${h}:${Port}"
    try {
        $self = Invoke-RestMethod -Uri "$u/api/self" -TimeoutSec 5
        $base = $u
        break
    } catch {
        Write-Host "  $u unreachable: $($_.Exception.Message)" -ForegroundColor Yellow
    }
}
if (-not $base) { Write-Host "FAIL: cannot reach vmctl on port $Port" -ForegroundColor Red; exit 1 }

Show "GET $base/api/self" $self
if (-not $self.name) {
    Write-Host "FAIL: host sees ip $($self.ip) but no running VM matches it" -ForegroundColor Red
    exit 1
}
if ($self.ip -ne $myIp) {
    Write-Host "WARN: host sees ip $($self.ip), local ip is $myIp" -ForegroundColor Yellow
}
Write-Host "OK: host identifies this VM as '$($self.name)'" -ForegroundColor Green

if (-not $Rotate) {
    Write-Host ""
    Write-Host "Check only. Re-run with -Rotate to force-off + randomize + boot '$($self.name)'."
    exit 0
}

# 3. trigger rotate
$ans = Read-Host "Force-off and randomize '$($self.name)' now? type YES"
if ($ans -ne "YES") { Write-Host "aborted"; exit 0 }

$r = Invoke-RestMethod -Method Post -Uri "$base/api/self/rotate" -ContentType "application/json" -Body "{}"
Show "POST $base/api/self/rotate" $r
"$base/api/jobs/$($r.job)" | Out-File -Encoding ascii "$env:PUBLIC\vmctl-last-job.txt"
Write-Host "job url saved to $env:PUBLIC\vmctl-last-job.txt"
Write-Host "This VM will be powered off in ~1s. After reboot run:"
Write-Host "  Invoke-RestMethod (Get-Content `$env:PUBLIC\vmctl-last-job.txt) | ConvertTo-Json -Depth 6"

# poll until we die
while ($true) {
    Start-Sleep -Milliseconds 300
    try {
        $j = Invoke-RestMethod -Uri "$base/api/jobs/$($r.job)" -TimeoutSec 2
        Write-Host ("  job {0}: {1}" -f $j.status, ($j.log -join " | "))
        if ($j.status -ne "running") { break }
    } catch { }
}
