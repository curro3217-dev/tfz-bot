# TFZ paper-trading cycle runner (invoked by the scheduled task every 15 min).
# Sets the environment, runs one cycle, appends output to paper_log.txt.
$ErrorActionPreference = "Continue"
$root = "C:\Users\jarta\Downloads\Krasnov Trading Course\tfz-bot"
Set-Location $root
$env:INSECURE_SSL = "1"
$log = Join-Path $root "paper_log.txt"

"`n##### cycle start $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') #####" | Out-File -FilePath $log -Append -Encoding utf8
python -u main.py paper --timeframe 5m,15m --fresh 4 2>&1 | Out-File -FilePath $log -Append -Encoding utf8
