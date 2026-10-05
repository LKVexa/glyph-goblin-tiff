@echo off
setlocal
cd /d "%~dp0"
if not exist "GlyphGoblin.exe" (
  echo Download and extract the Glyph Goblin Windows player release ZIP.
  echo The GitHub Source code ZIP contains developer source, not the player.
  pause
  exit /b 1
)
"%~dp0GlyphGoblin.exe"
if errorlevel 1 pause
