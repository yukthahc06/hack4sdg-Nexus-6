@echo off
cd /d "%~dp0"
python -m streamlit run app.py --server.address=0.0.0.0
pause
