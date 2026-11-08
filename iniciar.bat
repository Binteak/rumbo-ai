@echo off
REM ============================================================
REM  Rumbo AI - arranque en Windows con doble clic
REM  Abre dos ventanas (backend y frontend) y el navegador.
REM  La primera vez instala dependencias (puede tardar unos minutos).
REM ============================================================
chcp 65001 >nul
cd /d "%~dp0"

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No se encuentra Python. Instala Python 3.11 o superior desde https://www.python.org
  pause
  exit /b 1
)
where npm >nul 2>&1
if errorlevel 1 (
  echo [ERROR] No se encuentra Node.js. Instala Node 20.19 o superior desde https://nodejs.org
  pause
  exit /b 1
)

if not exist "backend\.venv" (
  echo [1/4] Creando entorno virtual de Python...
  python -m venv "backend\.venv"
)
echo [2/4] Instalando dependencias del backend...
call "backend\.venv\Scripts\python.exe" -m pip install -q -r "backend\requirements.txt"
if errorlevel 1 (
  echo [ERROR] Fallo instalando las dependencias de Python.
  pause
  exit /b 1
)
if not exist "backend\.env" copy "backend\.env.example" "backend\.env" >nul

if not exist "frontend\node_modules" (
  echo [3/4] Instalando dependencias del frontend, solo la primera vez...
  pushd frontend
  call npm install
  popd
)

echo [4/4] Arrancando Rumbo...
start "Rumbo - backend (puerto 8000)" cmd /k "cd /d "%~dp0backend" && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --reload-dir app --port 8000"
start "Rumbo - frontend (puerto 4200)" cmd /k "cd /d "%~dp0frontend" && npm start"

echo.
echo Esperando a que arranque Angular...
timeout /t 25 /nobreak >nul
start "" http://localhost:4200
echo.
echo Rumbo esta en http://localhost:4200
echo Para pararlo, cierra las dos ventanas negras (backend y frontend).
pause
