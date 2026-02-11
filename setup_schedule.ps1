$action = New-ScheduledTaskAction -Execute 'C:\Users\ieste\.local\bin\uv.exe' -Argument 'run --project C:\Users\ieste\Projects\claude\ai-newsletter-agent newsletter' -WorkingDirectory 'C:\Users\ieste\Projects\claude\ai-newsletter-agent'
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
Register-ScheduledTask -TaskName 'AI Newsletter Agent' -Action $action -Trigger $trigger -Description 'Send weekly AI newsletter every Monday at 9:00' -Force
