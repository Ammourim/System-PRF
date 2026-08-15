@echo off
REM Backup do Sistema PRF hospedado. Use este arquivo no Agendador de Tarefas
REM do Windows. O log fica em backups\backup.log.
cd /d "%~dp0.."
if not exist "backups" mkdir "backups"
echo. >> "backups\backup.log"
echo ===== %date% %time% ===== >> "backups\backup.log"
".venv\Scripts\python.exe" "scripts\backup_remoto.py" >> "backups\backup.log" 2>&1
if errorlevel 1 (
  echo FALHOU - veja backups\backup.log >> "backups\backup.log"
  exit /b 1
)
exit /b 0
