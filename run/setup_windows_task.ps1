# Stock5 - Windows任务计划配置
# 创建两个任务：上午12:00和下午15:00运行LLM分析

$WorkDir = "E:\stock5\run"

# 任务1：上午12:00 LLM分析
$Action1 = New-ScheduledTaskAction -Execute "python" -Argument "$WorkDir\llm_analyzer_minute.py" -WorkingDirectory $WorkDir
$Trigger1 = New-ScheduledTaskTrigger -Daily -At 12:00
$Settings1 = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdle
Register-ScheduledTask -TaskName "Stock5_LLM_Morning" -Action $Action1 -Trigger $Trigger1 -Settings $Settings1 -Description "Stock5上午LLM深度分析"

# 任务2：下午15:00 LLM分析
$Action2 = New-ScheduledTaskAction -Execute "python" -Argument "$WorkDir\llm_analyzer_minute.py" -WorkingDirectory $WorkDir
$Trigger2 = New-ScheduledTaskTrigger -Daily -At 15:00
$Settings2 = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdle
Register-ScheduledTask -TaskName "Stock5_LLM_Afternoon" -Action $Action2 -Trigger $Trigger2 -Settings $Settings2 -Description "Stock5下午LLM深度分析"

Write-Host "✅ Windows任务计划已创建"
Write-Host "任务1: Stock5_LLM_Morning (每天12:00)"
Write-Host "任务2: Stock5_LLM_Afternoon (每天15:00)"
