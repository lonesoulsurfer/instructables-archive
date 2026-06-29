@echo off
title lonesoulsurfer - Update Site
color 0A

echo ============================================
echo   lonesoulsurfer.github.io - Site Updater
echo ============================================
echo.
echo This will:
echo   1. Scrape your Instructables profile
echo   2. Update projects.json
echo   3. Archive any new Instructables locally
echo   4. Build HTML pages for new projects
echo   5. Push everything to GitHub
echo.
echo Press any key to start, or close this window to cancel.
pause > nul

cd /d "%~dp0"

echo.
echo [1/5] Running scraper...
echo.
python3 scraper\scrape.py
if errorlevel 1 (
    echo.
    echo ERROR: Scraper failed. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo [2/5] Archiving any new Instructables...
echo.
python3 scraper\download_archive.py --new-only
if errorlevel 1 (
    echo WARNING: Archive step had some issues but continuing...
)

echo.
echo [3/5] Building HTML pages for new projects...
echo.
python3 build_html.py
if errorlevel 1 (
    echo WARNING: HTML build had some issues but continuing...
)

echo.
echo [4/5] Committing changes...
echo.
git add projects.json archive/
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "update: scrape %date%"
) else (
    echo No changes detected - your site is already up to date.
    echo.
    pause
    exit /b 0
)

echo.
echo [5/5] Pushing to GitHub...
echo.
git push

echo.
echo ============================================
echo   Done! Your site will update in ~30 seconds.
echo   https://lonesoulsurfer.github.io
echo ============================================
echo.
pause
