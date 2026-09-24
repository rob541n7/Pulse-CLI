@echo off
rem Klik dua kali setelah menyimpan file "Ringkasan Saham-YYYYMMDD.xlsx" ke data\idx\
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtual environment .venv belum ada. Jalankan: py -3.12 -m venv .venv ^&^& .venv\Scripts\pip install -e ".[dev]"
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m pulse.core.idx daily --open
if errorlevel 1 pause
