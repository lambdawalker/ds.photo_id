@echo off
setlocal
uv run --locked --project "%~dp0." python "%~dp0photo_id_generator.py" %*
exit /b %errorlevel%
