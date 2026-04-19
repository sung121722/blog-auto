Set-Location 'C:\Users\kang_\Downloads\blog-writer_mcp'
$python = 'C:\Users\kang_\Downloads\blog-writer_mcp\venv\Scripts\python.exe'
& $python auto_publish.py 2>&1 | Tee-Object -FilePath 'C:\Users\kang_\Downloads\blog-writer_mcp\logs\test_run_output.log'
