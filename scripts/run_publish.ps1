Set-Location 'C:\Users\kang_\Downloads\blog-writer_mcp'
$python = 'C:\Users\kang_\Downloads\blog-writer_mcp\venv\Scripts\python.exe'
$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $python
$psi.Arguments = 'auto_publish.py'
$psi.WorkingDirectory = 'C:\Users\kang_\Downloads\blog-writer_mcp'
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.UseShellExecute = $false
$p = [System.Diagnostics.Process]::Start($psi)
$stdout = $p.StandardOutput.ReadToEnd()
$stderr = $p.StandardError.ReadToEnd()
$p.WaitForExit()
Write-Host $stdout
if ($stderr) { Write-Host "STDERR: $stderr" }
Write-Host "Exit: $($p.ExitCode)"
