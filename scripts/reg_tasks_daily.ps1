# 매일 새벽 3시 + 오전 9시 실행 (일요일 포함 전일)
# 관리자 권한으로 실행 필요

$python  = 'C:\Users\kang_\Downloads\blog-writer_mcp\venv\Scripts\python.exe'
$script  = 'C:\Users\kang_\Downloads\blog-writer_mcp\auto_publish.py'
$workdir = 'C:\Users\kang_\Downloads\blog-writer_mcp'
$logfile = 'C:\Users\kang_\Downloads\blog-writer_mcp\logs\scheduler.log'
$user    = $env:USERNAME

$cmd  = $python
$args = "auto_publish.py >> `"$logfile`" 2>&1"

# 기존 태스크 삭제
@('BlogAuto_MWF_AM3','BlogAuto_MWF_AM9','BlogAuto_TTS_AM3','BlogAuto_TTS_AM9',
  'BlogAuto_Daily_AM3','BlogAuto_Daily_AM9') | ForEach-Object {
    Unregister-ScheduledTask -TaskName $_ -Confirm:$false -ErrorAction SilentlyContinue
}

# Action: python auto_publish.py >> logs\scheduler.log 2>&1
$action = New-ScheduledTaskAction `
    -Execute 'cmd.exe' `
    -Argument "/c `"$python`" `"$script`" >> `"$logfile`" 2>&1" `
    -WorkingDirectory $workdir

# 새벽 3시 매일
$trigger3 = New-ScheduledTaskTrigger -Daily -At '03:00'
# 오전 9시 매일
$trigger9 = New-ScheduledTaskTrigger -Daily -At '09:00'

$settings = New-ScheduledTaskSettingsSet `
    -StartWhenAvailable `
    -WakeToRun `
    -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
    -MultipleInstances IgnoreNew

# S4U 방식 — 로그인 없이 실행
Register-ScheduledTask `
    -TaskName 'BlogAuto_Daily_AM3' `
    -Action $action `
    -Trigger $trigger3 `
    -Settings $settings `
    -RunLevel Highest `
    -User $user `
    -Force

Register-ScheduledTask `
    -TaskName 'BlogAuto_Daily_AM9' `
    -Action $action `
    -Trigger $trigger9 `
    -Settings $settings `
    -RunLevel Highest `
    -User $user `
    -Force

Write-Host ""
Write-Host "=== 등록 완료 ==="
Get-ScheduledTask | Where-Object { $_.TaskName -like 'BlogAuto_Daily*' } | ForEach-Object {
    $info = Get-ScheduledTaskInfo -TaskName $_.TaskName
    Write-Host "$($_.TaskName) | State: $($_.State) | Next: $($info.NextRunTime)"
}
