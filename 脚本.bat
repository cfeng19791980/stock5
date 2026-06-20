@echo off
chcp 65001
title Stock Launcher
cd /d "E:\stock5\run"
start /b python web_server.py
start /b python realtime_fetcher.py
start /b python em_fetcher_daemon.py
start /b python stock5_gui_launcher.py
pause