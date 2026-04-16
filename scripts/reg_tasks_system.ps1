Start-Transcript -Path 'C:\Users\kang_\Downloads\blog-writer_mcp\logs\reg_tasks.log' -Force

$WRAPPER = 'C:\Users\kang_\Downloads\blog-writer_mcp\run_publish.bat'
$USER = 'SUNGGYU\kang_'

# Delete old tasks
$oldNames = @('BlogAuto_MWF_AM3','BlogAuto_TTS_AM3','BlogAuto_MWF_AM9','BlogAuto_TTS_AM9','BlogAuto_MWF','BlogAuto_TTS')
foreach ($n in $oldNames) {
    Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue
}

$action = New-ScheduledTaskAction -Execute $WRAPPER

# StartWhenAvailable: 놓친 시간에 PC 켜지면 바로 실행
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

# S4U: 사용자 계정으로 실행, 로그인 없어도 실행 (비밀번호 저장 불필요)
$principal = New-ScheduledTaskPrincipal `
    -UserId $USER `
    -RunLevel Highest `
    -LogonType S4U

$trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Wednesday,Friday -At '03:00'
Register-ScheduledTask -TaskName 'BlogAuto_MWF_AM3' -Action $action -Trigger $trigger1 -Settings $settings -Principal $principal -Force | Out-Null
Write-Host '[OK] MWF 03:00 registered (S4U - no login required)'

$trigger2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Thursday,Saturday -At '03:00'
Register-ScheduledTask -TaskName 'BlogAuto_TTS_AM3' -Action $action -Trigger $trigger2 -Settings $settings -Principal $principal -Force | Out-Null
Write-Host '[OK] TTS 03:00 registered (S4U)'

$trigger3 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Wednesday,Friday -At '09:00'
Register-ScheduledTask -TaskName 'BlogAuto_MWF_AM9' -Action $action -Trigger $trigger3 -Settings $settings -Principal $principal -Force | Out-Null
Write-Host '[OK] MWF 09:00 registered (S4U)'

$trigger4 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Tuesday,Thursday,Saturday -At '09:00'
Register-ScheduledTask -TaskName 'BlogAuto_TTS_AM9' -Action $action -Trigger $trigger4 -Settings $settings -Principal $principal -Force | Out-Null
Write-Host '[OK] TTS 09:00 registered (S4U)'

Write-Host ''
Write-Host 'Done! All tasks run as kang_ without requiring login.'

# Show next run times
Get-ScheduledTask | Where-Object { $_.TaskName -like 'BlogAuto_*' } | ForEach-Object {
    $info = Get-ScheduledTaskInfo -TaskName $_.TaskName -ErrorAction SilentlyContinue
    if ($info) {
        Write-Host ($_.TaskName + ' -> NextRun: ' + $info.NextRunTime)
    }
}

Stop-Transcript
