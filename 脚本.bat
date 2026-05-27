@echo off
chcp 65001
title Stock Launcher
cd /d "E:\stock5"
start /b python web_server.py
start /b python realtime_fetcher.py
start /b stock5_gui_launcher.py
pause