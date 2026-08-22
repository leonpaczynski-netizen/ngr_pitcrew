<#
    rig_usb_power.ps1 - stop Windows putting the rig's USB devices to sleep.

    Measured 22 Aug 2026 on this machine, while chasing the ButtKicker dropout:

      * USB selective suspend was ENABLED on AC even under the Ultimate
        Performance plan. Ultimate Performance does not turn it off.
      * The ButtKicker carried DeviceSelectiveSuspended=1 on the composite
        device, on its USB AUDIO interface (MI_00), and on its HID interface
        (MI_02). Only the Fanatec devices were already set to 0.
      * "Allow the computer to turn off this device" was checked on both
        Intel xHCI controllers, a Generic USB Hub, a Generic SuperSpeed Hub,
        the display-audio endpoint, and the ButtKicker/JBL HID interfaces.
      * The CH340 wind controller sits on the SAME root hub as the ButtKicker
        (ports 6 and 9), and that controller had power management enabled.

    An audio device that is silent between haptic events, and a fan
    controller that sends twelve bytes every 250 ms, are exactly the traffic
    profile selective suspend was written to catch.

    Run as Administrator. Re-run after a Windows feature update or a driver
    reinstall - both put these back.

        -WhatIf   show what would change, change nothing
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param()

$ErrorActionPreference = "Stop"

$identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "This needs Administrator. Start PowerShell with 'Run as administrator' and try again."
    exit 1
}

function Write-Step { param($Text) Write-Host "`n=== $Text" -ForegroundColor Cyan }
function Write-Did  { param($Text) Write-Host "    [changed] $Text" -ForegroundColor Green }
function Write-Same { param($Text) Write-Host "    [already] $Text" -ForegroundColor DarkGray }

# ---------------------------------------------------------------------------
# 1. USB selective suspend, on the ACTIVE power plan, both AC and DC.
# ---------------------------------------------------------------------------
Write-Step "USB selective suspend"

$USB_SUBGROUP  = "2a737441-1930-4402-8d77-b2bebba308a3"
$USB_SELECTIVE = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"

if ($PSCmdlet.ShouldProcess("active power plan", "disable USB selective suspend, AC and DC")) {
    powercfg /setacvalueindex SCHEME_CURRENT $USB_SUBGROUP $USB_SELECTIVE 0 | Out-Null
    powercfg /setdcvalueindex SCHEME_CURRENT $USB_SUBGROUP $USB_SELECTIVE 0 | Out-Null
    powercfg /setactive SCHEME_CURRENT | Out-Null
    Write-Did "USB selective suspend = Disabled (AC and DC)"
}

# ---------------------------------------------------------------------------
# 2. "Allow the computer to turn off this device to save power" - the
#    per-device checkbox. This is the one that pulls the rug on a live handle.
# ---------------------------------------------------------------------------
Write-Step "Per-device power management (USB controllers, hubs, audio, serial)"

$pnp = @{}
Get-PnpDevice | ForEach-Object { $pnp[$_.InstanceId] = $_ }

$targets = @()
try {
    $targets = Get-CimInstance -Namespace root/wmi -ClassName MSPower_DeviceEnable -ErrorAction Stop
} catch {
    Write-Warning "    MSPower_DeviceEnable is not available: $($_.Exception.Message)"
}

foreach ($t in $targets) {
    $id = $t.InstanceName -replace "_\d+$", ""
    $dev = $pnp[$id]
    if (-not $dev) { continue }

    $interesting = ($id -like "USB\*") -or ($id -like "PCI\*USB*") -or
                   ($dev.Class -in @("USB", "MEDIA", "AudioEndpoint", "Ports")) -or
                   ($dev.FriendlyName -match "USB|xHCI|Hub|Audio|ButtKicker|CH340|Serial")
    if (-not $interesting) { continue }

    # Leave the wheelbase alone - Fanatec's own service manages it, and it
    # was already correct.
    if ($id -match "VID_0EB7") { Write-Same "skipped, Fanatec: $($dev.FriendlyName)"; continue }

    if ($t.Enable -eq $false) { Write-Same $dev.FriendlyName; continue }

    if ($PSCmdlet.ShouldProcess($dev.FriendlyName, "uncheck 'allow the computer to turn off this device'")) {
        try {
            $t | Set-CimInstance -Property @{ Enable = $false }
            Write-Did $dev.FriendlyName
        } catch {
            Write-Warning "    could not change $($dev.FriendlyName): $($_.Exception.Message)"
        }
    }
}

# ---------------------------------------------------------------------------
# 3. The registry flags Windows consults independently of that checkbox.
#    EnhancedPowerManagementEnabled=0 is the documented fix for ButtKicker
#    USB enumeration failures; DeviceSelectiveSuspended=0 stops the audio
#    interface itself being suspended between haptic events.
# ---------------------------------------------------------------------------
Write-Step "Registry: EnhancedPowerManagementEnabled / DeviceSelectiveSuspended"

$FLAGS = @("EnhancedPowerManagementEnabled", "DeviceSelectiveSuspended",
           "AllowIdleIrpInD3", "EnableSelectiveSuspend")

function Clear-SuspendFlags {
    param($Label, $DeviceKey)
    foreach ($inst in (Get-ChildItem $DeviceKey.PSPath -ErrorAction SilentlyContinue)) {
        $params = Join-Path $inst.PSPath "Device Parameters"
        if (-not (Test-Path $params)) { continue }
        foreach ($name in $FLAGS) {
            $cur = (Get-ItemProperty -Path $params -Name $name -ErrorAction SilentlyContinue).$name
            if ($null -eq $cur) { continue }
            if ($cur -eq 0) { Write-Same "$Label :: $name"; continue }
            if ($PSCmdlet.ShouldProcess("$Label $($DeviceKey.PSChildName)", "set $name = 0")) {
                Set-ItemProperty -Path $params -Name $name -Value 0 -Type DWord
                Write-Did "$Label :: $name  $cur -> 0"
            }
        }
    }
}

$usbEnum = "HKLM:\SYSTEM\CurrentControlSet\Enum\USB"

$rigDevices = @(
    @{ Name = "ButtKicker PRO";       Match = "VID_33A1&PID_52DA" },
    @{ Name = "JBL Endurance Run 3C"; Match = "VID_0ECB&PID_2155" },
    @{ Name = "CH340 wind sim";       Match = "VID_1A86&PID_7523" }
)

foreach ($v in $rigDevices) {
    $keys = Get-ChildItem -Path $usbEnum -ErrorAction SilentlyContinue |
            Where-Object { $_.PSChildName -like "*$($v.Match)*" }
    if (-not $keys) { Write-Warning "    $($v.Name): not found in the USB enum tree"; continue }
    foreach ($k in $keys) { Clear-SuspendFlags -Label $v.Name -DeviceKey $k }
}

# Every hub and root hub, which is where the suspend decision is actually made.
$hubKeys = Get-ChildItem -Path $usbEnum -ErrorAction SilentlyContinue |
           Where-Object { $_.PSChildName -like "*ROOT_HUB*" -or $_.PSChildName -match "VID_05E3|VID_8087" }
foreach ($k in $hubKeys) { Clear-SuspendFlags -Label "hub $($k.PSChildName)" -DeviceKey $k }

# ---------------------------------------------------------------------------
# 4. Stop the machine itself sleeping or parking the PCIe link. A rig PC that
#    sleeps mid-session takes every USB handle down with it.
# ---------------------------------------------------------------------------
Write-Step "System sleep, hibernate and PCIe link power"

if ($PSCmdlet.ShouldProcess("this machine", "disable sleep, hibernate, disk spindown and PCIe ASPM")) {
    powercfg /change standby-timeout-ac 0    | Out-Null
    powercfg /change standby-timeout-dc 0    | Out-Null
    powercfg /change hibernate-timeout-ac 0  | Out-Null
    powercfg /change hibernate-timeout-dc 0  | Out-Null
    powercfg /change disk-timeout-ac 0       | Out-Null
    powercfg /change monitor-timeout-ac 0    | Out-Null
    Write-Did "sleep / hibernate / disk spindown / monitor blank = Never (AC)"

    # PCIe Active State Power Management -> Off. It was already Off on AC
    # here, but Maximum power savings on DC.
    $PCIE_SUB = "501a4d13-42af-4429-9fd1-a8218c268e20"
    $ASPM     = "ee12f906-d277-404b-b6da-e5fa1a576df5"
    powercfg /setacvalueindex SCHEME_CURRENT $PCIE_SUB $ASPM 0 | Out-Null
    powercfg /setdcvalueindex SCHEME_CURRENT $PCIE_SUB $ASPM 0 | Out-Null
    powercfg /setactive SCHEME_CURRENT | Out-Null
    Write-Did "PCIe link state power management = Off (AC and DC)"
}

# ---------------------------------------------------------------------------
# 5. Report the result, so the change is auditable.
# ---------------------------------------------------------------------------
Write-Step "Verification"

Write-Host "`n  USB selective suspend:" -ForegroundColor Yellow
powercfg /q SCHEME_CURRENT $USB_SUBGROUP $USB_SELECTIVE |
    Select-String "Power Setting Index" | ForEach-Object { "    $_" }

Write-Host "`n  Devices Windows may still power down:" -ForegroundColor Yellow
$still = @()
try {
    $still = Get-CimInstance -Namespace root/wmi -ClassName MSPower_DeviceEnable -ErrorAction Stop |
             Where-Object { $_.Enable -eq $true }
} catch { }
if ($still) {
    foreach ($s in $still) {
        $d = $pnp[($s.InstanceName -replace "_\d+$", "")]
        if ($d) { "    $($d.FriendlyName)" } else { "    $($s.InstanceName)" }
    }
} else {
    Write-Host "    none" -ForegroundColor Green
}

Write-Host "`nDone." -ForegroundColor Cyan
Write-Host "A reboot is not needed for these settings - but the ButtKicker endpoint" -ForegroundColor Cyan
Write-Host "is currently in its degraded state, so restart before the next race." -ForegroundColor Cyan
