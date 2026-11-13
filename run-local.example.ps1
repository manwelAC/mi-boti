param([switch]$ResetToken)

# Copy to ignored run-local.ps1 and optionally fill the nonsecret IDs below.
# Never put a token in this file. Windows encrypts the local credential cache.
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$runtimePython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtimePython)) {
    throw 'Create .venv and install the project first; see README.md.'
}
if (-not (Test-Path -LiteralPath 'config.toml')) {
    Copy-Item -LiteralPath 'config.example.toml' -Destination 'config.toml'
}
if (-not $env:MI_BOTI_GUILD_ID) { $env:MI_BOTI_GUILD_ID = Read-Host 'Discord server ID' }
if (-not $env:MI_BOTI_OWNER_IDS) { $env:MI_BOTI_OWNER_IDS = Read-Host 'Owner user ID (comma-separated for multiple owners)' }
if (-not $env:MI_BOTI_APPLICATION_ID) { $env:MI_BOTI_APPLICATION_ID = Read-Host 'Discord application ID' }
$env:MI_BOTI_CONFIG_FILE = Join-Path $PSScriptRoot 'config.toml'
$savedBotToken = $env:MI_BOTI_DISCORD_TOKEN
$credentialRoot = Join-Path ([Environment]::GetFolderPath('LocalApplicationData')) 'MiBoti\credentials'
$credentialFile = Join-Path $credentialRoot ("discord-{0}.xml" -f $env:MI_BOTI_APPLICATION_ID)
try {
    if ($ResetToken -and (Test-Path -LiteralPath $credentialFile)) {
        Remove-Item -LiteralPath $credentialFile
    }
    if (Test-Path -LiteralPath $credentialFile) {
        try {
            $credential = Import-Clixml -LiteralPath $credentialFile
            if ($credential -isnot [System.Management.Automation.PSCredential]) { throw 'Invalid cache.' }
            $maskedBotToken = $credential.Password
        }
        catch { throw 'Cannot unlock the saved token. Run .\run-local.ps1 -ResetToken to replace it.' }
        Write-Host 'Using the saved Windows-encrypted bot token.'
    }
    else {
        $maskedBotToken = Read-Host 'Regenerated Discord bot token (hidden; saved encrypted for this Windows account)' -AsSecureString
        if ($maskedBotToken.Length -eq 0) { throw 'A regenerated token is required.' }
        New-Item -ItemType Directory -Path $credentialRoot -Force | Out-Null
        $credential = [System.Management.Automation.PSCredential]::new('MiBoti', $maskedBotToken)
        $credential | Export-Clixml -LiteralPath $credentialFile
        Write-Host 'Token saved with Windows user-bound encryption outside the project.'
    }
    $env:MI_BOTI_DISCORD_TOKEN = $credential.GetNetworkCredential().Password
    & $runtimePython -m mi_boti run
    if ($LASTEXITCODE -ne 0) { throw 'The bot stopped with an error. Review the safe message above.' }
}
finally {
    $env:MI_BOTI_DISCORD_TOKEN = $savedBotToken
    if ($null -ne $maskedBotToken) { $maskedBotToken.Dispose() }
    Remove-Variable savedBotToken, credential -ErrorAction SilentlyContinue
}
