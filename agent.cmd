@echo off
set "PYTHONPATH=%~dp0src"
python -m job_agent.cli %*

