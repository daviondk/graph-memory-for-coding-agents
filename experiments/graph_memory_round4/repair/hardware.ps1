$ErrorActionPreference = 'Stop'
$target = Join-Path $PSScriptRoot 'hardware.json'
$gpu = (& nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader) -join ' '
$cpu = Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores,NumberOfLogicalProcessors
$jobRecord = Get-Content (Join-Path $PSScriptRoot 'launch.json') -Raw | ConvertFrom-Json
$jobProc = Get-CimInstance Win32_Process -Filter "ProcessId=$($jobRecord.pid)"
if (!$jobProc -or !$jobProc.CommandLine.Contains('18904')) { throw 'Model server identity mismatch' }
@{utc=(Get-Date).ToUniversalTime().ToString('o'); gpu=$gpu; cpu=$cpu; exe=$jobProc.ExecutablePath; pid=$jobProc.ProcessId; server_command=$jobProc.CommandLine; machine_ram=(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory} | ConvertTo-Json | Set-Content $target -Encoding utf8
