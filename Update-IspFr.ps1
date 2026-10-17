<#
.SYNOPSIS
    Fusionne les plages IPv4 des operateurs grand public francais en une seule liste
    (isp-fr.txt) et la pousse sur le depot GitHub.
.DESCRIPTION
    Source : https://github.com/ipverse/as-ip-blocks (mise a jour quotidienne).
    Si un telechargement echoue ou si le resultat est anormalement court, rien n'est
    ecrit ni pousse : la liste publiee reste l'ancienne.
#>
[CmdletBinding()]
param(
    # Clone local du depot GitHub (dans le workflow : $env:GITHUB_WORKSPACE)
    [string]$RepoPath = '.',
    [string]$FileName = 'isp-fr.txt',
    # Garde-fou : environ 500 plages attendues
    [int]$MinLines = 300
)

$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$base = 'https://raw.githubusercontent.com/ipverse/as-ip-blocks/master/as'

# Pour ajouter un operateur : ajouter son ASN ici
$asns = [ordered]@{
    3215  = 'Orange'
    12322 = 'Free (fixe)'
    51207 = 'Free Mobile'
    15557 = 'SFR'
    5410  = 'Bouygues Telecom'
}

function Invoke-Git {
    & git -C $RepoPath @args
    if ($LASTEXITCODE -ne 0) { throw "git $($args -join ' ') a echoue (code $LASTEXITCODE)" }
}

if (-not (Test-Path (Join-Path $RepoPath '.git'))) { throw "$RepoPath n'est pas un depot git" }

# 1. Se remettre a jour avant d'ecrire
Invoke-Git pull --quiet --ff-only

# 2. Telecharger les listes (toute erreur arrete le script)
$lines = foreach ($asn in $asns.Keys) {
    $text = Invoke-RestMethod -Uri "$base/$asn/ipv4-aggregated.txt" -UseBasicParsing
    Write-Verbose "AS$asn ($($asns[$asn])) telecharge"
    $text -split "`r?`n"
}

# 3. Nettoyer, valider, dedoublonner, trier par adresse
$cidr = '^(\d{1,3}\.){3}\d{1,3}(/(\d|[12]\d|3[0-2]))?$'
$ranges = $lines |
    ForEach-Object { ($_ -replace '#.*', '').Trim() } |
    Where-Object { $_ -match $cidr } |
    Sort-Object -Unique |
    Sort-Object { [version]($_ -split '/')[0] }, { [int]($_ -split '/')[1] }

$count = @($ranges).Count
if ($count -lt $MinLines) {
    throw "Liste trop courte ($count plages) : rien n'est publie"
}

# 4. Ecrire en UTF-8 sans BOM avec des fins de ligne LF
$target = Join-Path $RepoPath $FileName
$content = ($ranges -join "`n") + "`n"
[IO.File]::WriteAllText($target, $content, (New-Object Text.UTF8Encoding($false)))

# 5. Pousser seulement si la liste a change (ou si elle n'existait pas encore)
$changed = & git -C $RepoPath status --porcelain -- $FileName
if (-not $changed) {
    Write-Output "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - aucun changement ($count plages)"
    return
}

Invoke-Git add -- $FileName
Invoke-Git commit --quiet -m "Mise a jour isp-fr : $count plages ($(Get-Date -Format 'yyyy-MM-dd'))"
Invoke-Git push --quiet
Write-Output "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') - $count plages publiees"
