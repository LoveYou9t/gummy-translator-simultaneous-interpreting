@echo off
echo ========================================
echo Gummy Translator 系统音频捕获组件安装
echo ========================================
echo.

echo 检查当前环境...
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到Python，请先安装Python
    pause
    exit /b 1
)

echo Python已安装 ✓
echo.

echo 选择安装方案:
echo 1. 安装sounddevice (Python库，简单快速)
echo 2. 尝试安装FFmpeg (性能最佳)
echo 3. 显示虚拟音频设备信息
echo 4. 退出
echo.
set /p choice="请输入选择 (1-4): "

if "%choice%"=="1" goto install_sounddevice
if "%choice%"=="2" goto install_ffmpeg
if "%choice%"=="3" goto show_virtual_info
if "%choice%"=="4" goto end
echo 无效选择，请重新运行脚本
pause
exit /b 1

:install_sounddevice
echo.
echo 正在安装sounddevice和numpy...
pip install sounddevice numpy
if errorlevel 1 (
    echo 安装失败，请检查网络连接或使用管理员权限运行
    pause
    exit /b 1
) else (
    echo sounddevice安装成功 ✓
    echo 现在可以使用Python音频捕获功能了
)
goto end

:install_ffmpeg
echo.
echo 尝试使用winget安装FFmpeg...
winget install FFmpeg >nul 2>&1
if errorlevel 1 (
    echo winget安装失败，尝试其他方法...
    echo.
    echo 请手动安装FFmpeg:
    echo 1. 访问: https://www.gyan.dev/ffmpeg/builds/
    echo 2. 下载 "release builds" 中的 ffmpeg-release-essentials.zip
    echo 3. 解压到 C:\ffmpeg\
    echo 4. 将 C:\ffmpeg\bin 添加到系统PATH环境变量
    echo 5. 重启命令行窗口
    echo.
    echo 或者安装Chocolatey后运行: choco install ffmpeg
) else (
    echo FFmpeg安装成功 ✓
    echo 现在可以使用高性能音频捕获功能了
)
goto end

:show_virtual_info
echo.
echo ========================================
echo 虚拟音频设备信息
echo ========================================
echo.
echo 推荐的虚拟音频软件:
echo.
echo 1. VB-CABLE (免费)
echo    下载: https://vb-audio.com/Cable/
echo    特点: 简单易用，一条虚拟音频线缆
echo.
echo 2. VoiceMeeter (免费)  
echo    下载: https://vb-audio.com/Voicemeeter/
echo    特点: 功能丰富的音频混音器
echo.
echo 3. Virtual Audio Cable (付费)
echo    特点: 专业级虚拟音频解决方案
echo.
echo 安装后:
echo 1. 将系统音频输出设备设置为虚拟设备
echo 2. 在翻译程序中选择对应的虚拟输入设备
echo 3. 播放音频即可实时翻译
echo.
goto end

:end
echo.
echo 安装完成！重启翻译程序以使用新功能。
pause
