@echo off
:: GitHub Actions 강제 실행 스크립트
:: 사용법: trigger_github.bat [GitHub_PAT_Token]
:: PAT 토큰: https://github.com/settings/tokens 에서 repo+workflow 권한으로 생성

set REPO=sung121722/blog-auto
set WORKFLOW=auto_publish.yml
set BRANCH=main

if "%1"=="" (
    echo.
    echo [사용법] trigger_github.bat YOUR_GITHUB_TOKEN
    echo.
    echo GitHub PAT 토큰 발급: https://github.com/settings/tokens
    echo 권한: repo + workflow 체크
    echo.
    pause
    exit /b
)

set TOKEN=%1

echo GitHub Actions 강제 실행 중...
curl -X POST ^
  -H "Accept: application/vnd.github.v3+json" ^
  -H "Authorization: token %TOKEN%" ^
  https://api.github.com/repos/%REPO%/actions/workflows/%WORKFLOW%/dispatches ^
  -d "{\"ref\":\"%BRANCH%\"}"

echo.
echo 완료! GitHub Actions 탭에서 실행 상태 확인:
echo https://github.com/%REPO%/actions
echo.
pause
