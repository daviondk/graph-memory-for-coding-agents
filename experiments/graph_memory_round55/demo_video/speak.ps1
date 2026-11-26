param([Parameter(Mandatory=$true)][string]$Spec)
$ErrorActionPreference='Stop'
Add-Type -AssemblyName System.Speech
$speech=[System.Speech.Synthesis.SpeechSynthesizer]::new()
try {
    $available=$speech.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'en-US' }
    $chosen=$available | Where-Object { $_.VoiceInfo.Name -eq 'Microsoft Zira Desktop' } | Select-Object -First 1
    if ($null -eq $chosen) { $chosen=$available | Select-Object -First 1 }
    if ($null -eq $chosen) { throw 'An installed English speech voice is required.' }
    $speech.SelectVoice($chosen.VoiceInfo.Name)
    $speech.Rate=0
    foreach ($item in (Get-Content -Raw -Encoding UTF8 -LiteralPath $Spec | ConvertFrom-Json)) {
        $speech.SetOutputToWaveFile($item.path)
        $speech.Speak($item.text)
        $speech.SetOutputToNull()
    }
    Write-Output $chosen.VoiceInfo.Name
} finally {
    $speech.Dispose()
}
