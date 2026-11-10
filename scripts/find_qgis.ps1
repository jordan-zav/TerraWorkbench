param(
    [string]$PreferredRoot = ""
)

$candidates = [System.Collections.Generic.List[string]]::new()

if ($PreferredRoot) {
    $candidates.Add($PreferredRoot)
}
if ($env:QGIS_ROOT -and $env:QGIS_ROOT -ne $PreferredRoot) {
    $candidates.Add($env:QGIS_ROOT)
}

foreach ($commandName in @("qgis-ltr.bat", "qgis.bat")) {
    $command = Get-Command $commandName -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) {
        $candidates.Add((Split-Path -Parent (Split-Path -Parent $command.Source)))
    }
}

foreach ($programsRoot in @($env:ProgramFiles, ${env:ProgramFiles(x86)})) {
    if (-not $programsRoot) {
        continue
    }
    Get-ChildItem -LiteralPath $programsRoot -Directory -Filter "QGIS*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending |
        ForEach-Object { $candidates.Add($_.FullName) }
}

Get-PSDrive -PSProvider FileSystem | ForEach-Object {
    $rootCandidate = Join-Path $_.Root "QGIS"
    if (Test-Path -LiteralPath $rootCandidate -PathType Container) {
        $candidates.Add($rootCandidate)
    }
}

$seen = @{}
foreach ($candidate in $candidates) {
    if (-not $candidate) {
        continue
    }
    $resolved = [System.IO.Path]::GetFullPath($candidate)
    if ($seen.ContainsKey($resolved)) {
        continue
    }
    $seen[$resolved] = $true
    $bin = Join-Path $resolved "bin"
    $hasPython = (Test-Path -LiteralPath (Join-Path $bin "python-qgis-ltr.bat")) -or
        (Test-Path -LiteralPath (Join-Path $bin "python-qgis.bat"))
    $hasLauncher = (Test-Path -LiteralPath (Join-Path $bin "qgis-ltr.bat")) -or
        (Test-Path -LiteralPath (Join-Path $bin "qgis.bat"))
    if ($hasPython -and $hasLauncher) {
        Write-Output $resolved
        exit 0
    }
}

exit 1
