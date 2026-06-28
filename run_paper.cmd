@echo off
REM TFZ paper-trading cycle runner (invoked by the scheduled task every 15 min).
cd /d "C:\Users\jarta\Downloads\Krasnov Trading Course\tfz-bot"
set INSECURE_SSL=1
echo. >> paper_log.txt
echo ##### cycle start %DATE% %TIME% ##### >> paper_log.txt
python -u main.py paper --timeframe 5m,15m --fresh 4 >> paper_log.txt 2>&1
