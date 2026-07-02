@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ============================================================
echo   Building CookiePilot.exe (PyInstaller, one-file)
echo ============================================================
python -m PyInstaller --noconfirm --onefile --windowed ^
  --name CookiePilot ^
  --add-data "templates;templates" ^
  app.py
echo.
echo ============================================================
echo   เสร็จแล้ว -^> dist\CookiePilot.exe
echo   (คัดลอกไฟล์ .exe ไปวางที่ไหนก็ได้ ดับเบิลคลิกเปิดได้เลย)
echo ============================================================
pause
