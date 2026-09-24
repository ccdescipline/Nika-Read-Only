# Run inside the Windows guest: ask vmctl to force-off + randomize + boot THIS VM (identified by source IP).
# Gateway changes after net-rotate, so detect it (pure .NET, works on stripped LTSC without CIM).
$gw = [System.Net.NetworkInformation.NetworkInterface]::GetAllNetworkInterfaces() |
    Where-Object { $_.OperationalStatus -eq "Up" } |
    ForEach-Object { $_.GetIPProperties().GatewayAddresses } |
    Where-Object { $_.Address.AddressFamily -eq "InterNetwork" -and $_.Address.ToString() -ne "0.0.0.0" } |
    Select-Object -First 1 -ExpandProperty Address
if (-not $gw) { $gw = "192.168.4.158" }
Invoke-RestMethod -Method Post -Uri "http://${gw}:8787/api/self/rotate" -ContentType application/json -Body '{}'
