@echo off
echo Deploying Learn With Gemini Vision Service to Google Cloud Run...

REM Load API key from .env file
for /f "tokens=1,* delims==" %%a in (.env) do (
    if "%%a"=="GOOGLE_API_KEY" set GOOGLE_API_KEY=%%b
)

if "%GOOGLE_API_KEY%"=="" (
    echo ERROR: GOOGLE_API_KEY not found in .env file
    pause
    exit /b 1
)

cd cloud
gcloud run deploy learn-with-gemini-vision ^
  --source . ^
  --region us-central1 ^
  --project learn-with-gemini-2026 ^
  --allow-unauthenticated ^
  --set-env-vars="GOOGLE_API_KEY=%GOOGLE_API_KEY%" ^
  --memory=512Mi

echo.
echo Deployment complete!
pause
