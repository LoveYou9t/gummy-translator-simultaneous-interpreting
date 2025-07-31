# 音频源切换功能说明

本程序现在支持多种音频输入源，提供**三种不同的系统音频捕获方案**：

## 🎵 音频源类型

### 1. 麦克风录音（默认）
- 直接从麦克风录制语音
- 适用于实时翻译自己的语音

### 2. 系统音频监听（三种方案可选）
- **FFmpeg直接捕获**：高性能，无需额外配置
- **Sounddevice Python库**：简单易用，Python原生支持
- **虚拟音频设备**：图形界面，专业音频处理

## 🔧 快捷键操作

- **Alt + A**: 切换音频源（麦克风 ↔ 系统音频）
- **Alt + D**: 选择音频设备
- **Alt + S**: 切换TTS开关
- **Alt + T**: 切换黑白颜色模式
- **Ctrl + H**: 切换标题栏显示

## 🚀 三种系统音频捕获方案

### 方案1: Sounddevice (推荐新手) 🐍

**安装方法：**
```bash
pip install sounddevice numpy
```

**优点：**
- ✅ 安装简单，一个命令搞定
- ✅ Python原生支持，稳定性好
- ✅ 跨平台兼容
- ✅ 无需额外配置

**使用：**
1. 安装后重启程序
2. 程序会自动检测并显示"Sounddevice: ✅ 可用"
3. 按 `Alt + A` 切换到系统音频模式即可

---

### 方案2: FFmpeg (推荐高级用户) 🎬

**安装方法：**

#### Windows 10/11 (推荐):
```bash
winget install FFmpeg
```

#### 手动安装:
1. 访问: https://www.gyan.dev/ffmpeg/builds/
2. 下载 "release builds" 中的 `ffmpeg-release-essentials.zip`
3. 解压到 `C:\ffmpeg\`
4. 将 `C:\ffmpeg\bin` 添加到系统PATH环境变量
5. 重启命令行/程序

#### 其他方式:
```bash
# 如果有Chocolatey
choco install ffmpeg

# 如果有Scoop  
scoop install ffmpeg
```

**优点：**
- ⭐ 性能最佳，音质最好
- ⭐ 功能最全，支持各种音频格式
- ⭐ 直接捕获系统音频输出
- ⭐ 专业级音频处理

---

### 方案3: 虚拟音频设备 (推荐追求稳定) 🔌

**推荐软件：**

1. **VB-CABLE** (免费)
   - 下载: https://vb-audio.com/Cable/
   - 特点: 简单易用，一条虚拟音频线缆

2. **VoiceMeeter** (免费，功能丰富)
   - 下载: https://vb-audio.com/Voicemeeter/
   - 特点: 专业音频混音器，多输入输出

3. **Virtual Audio Cable** (付费)
   - 特点: 专业级解决方案

**设置步骤：**
1. 安装虚拟音频软件
2. 重启电脑
3. 将系统音频输出设置为虚拟设备
4. 在程序中选择对应的虚拟输入设备
5. 重启程序

**优点：**
- 🔒 最稳定的解决方案
- 🎛️ 图形界面，易于管理
- 🔧 可以同时用于其他应用
- 🎵 专业音频处理功能

## � 快速开始

### 🏃‍♂️ 最简单的方式（推荐）
```bash
# 运行安装脚本
install_audio_components.bat

# 或手动安装sounddevice
pip install sounddevice numpy
```

### 🔍 检查安装状态
启动程序后查看输出：
```
系统音频捕获方法状态:
  FFmpeg: ✅ 可用 / ❌ 不可用
  Sounddevice: ✅ 可用 / ❌ 不可用
```

### 🎯 使用系统音频捕获
1. 确保至少有一种方案可用
2. 按 `Alt + A` 切换到系统音频模式
3. 按 `Alt + D` 选择音频设备
4. 播放任何音频内容即可实时翻译

## 📊 方案对比

| 方案 | 安装难度 | 性能 | 音质 | 稳定性 | 适合人群 |
|------|----------|------|------|--------|----------|
| Sounddevice | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 新手用户 |
| FFmpeg | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 高级用户 |
| 虚拟设备 | ⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 专业用户 |

## 🔧 故障排除

### 问题1: 所有方案都显示"不可用"
**解决方案：**
- 运行 `install_audio_components.bat` 安装脚本
- 或手动安装：`pip install sounddevice numpy`

### 问题2: 系统音频模式下无声音
**解决方案：**
- 确保有音频正在播放
- 检查选择的音频设备是否正确
- 如果使用虚拟设备，确保系统输出已切换到虚拟设备

### 问题3: FFmpeg安装后仍显示不可用
**解决方案：**
- 重启命令行窗口
- 检查PATH环境变量是否包含FFmpeg
- 在命令行运行 `ffmpeg -version` 测试

### 问题4: sounddevice安装失败
**解决方案：**
- 以管理员权限运行命令行
- 更新pip：`python -m pip install --upgrade pip`
- 使用国内镜像：`pip install -i https://pypi.tuna.tsinghua.edu.cn/simple sounddevice numpy`

## 🎯 使用场景

- ✅ 翻译YouTube视频
- ✅ 翻译在线会议音频  
- ✅ 翻译游戏中的对话
- ✅ 翻译音乐和播客
- ✅ 翻译任何系统播放的音频内容

## 💡 小贴士

1. **初次使用**建议安装sounddevice，简单快速
2. **追求性能**可以后续升级到FFmpeg
3. **专业用户**可以使用虚拟音频设备进行复杂的音频路由
4. 可以同时安装多种方案，程序会自动选择最佳可用方案
