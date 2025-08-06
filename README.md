# gummy-translator-simultaneous-interpreting

## 项目描述

# Gummy Translator 同声传译工具

Gummy Translator 是一个基于 DashScope 语音识别与翻译 API、SiliconFlow CosyVoice TTS 语音合成、支持系统音频/麦克风输入的同声传译桌面工具。支持 Windows 平台，具备浮动字幕、音频源灵活切换、配置可视化等特性。

## 主要特性
- 支持系统音频（如视频、会议、音乐等）和麦克风音频输入
- 实时语音识别（ASR）与翻译，支持多种目标语言
- 支持 TTS 语音合成，自动朗读翻译结果
- 可自定义 DashScope/SiliconFlow API Key、ASR 模型、TTS 声音
- 可视化设置界面，配置持久化
- 浮动字幕窗口，便于字幕展示
- 支持 FFmpeg、sounddevice、虚拟音频设备多种音频采集方案

## 快速开始
1. 安装依赖（见下方 requirements 部分）
2. 配置 API Key（DashScope、SiliconFlow）
3. 运行 `gummy_translator.py`
4. 按提示选择音频输入源，开始同声传译

## PREREQUISITES
- **操作系统**：Windows 10/11
- **Python**：建议 3.8 及以上
- **FFmpeg**：推荐安装（用于系统音频采集）
    - [FFmpeg 官方下载](https://www.gyan.dev/ffmpeg/builds/)
    - 安装后将 ffmpeg.exe 路径加入系统 PATH，或在设置中手动指定
- **DashScope API Key**：
    - 参考 [DashScope 语音 API 文档](https://help.aliyun.com/zh/dashscope/developer-reference/quickstart-2)
    - 注册并获取 API Key
- **SiliconFlow API Key**（用于 TTS）：
    - 访问 [SiliconFlow 官网](https://www.siliconflow.cn/) 注册获取
- **可选**：
    - 虚拟音频设备（如 VB-CABLE、VoiceMeeter）用于系统音频采集
    - sounddevice/numpy 作为备用音频采集方案

## requirements.txt
```
pyaudio
wxPython
requests
dashscope
sounddevice  # 可选，推荐安装
numpy        # 可选，推荐安装
```
> 注：如需使用 sounddevice 采集音频，需安装 sounddevice 和 numpy。

## AUDIO_GUIDE
### 音频输入源说明
- **麦克风**：直接采集本地麦克风输入，适合语音对话、演讲等场景。
- **系统音频**：采集电脑正在播放的声音，适合翻译视频、会议、音乐等。
    - 推荐使用 FFmpeg 采集（需安装 FFmpeg）。
    - 若 FFmpeg 不可用，可尝试 sounddevice（需安装 sounddevice/numpy），或配置虚拟音频设备（如 VB-CABLE、VoiceMeeter）。
    - 选择系统音频时，程序会自动检测可用采集方式并优先使用 FFmpeg。

### 常见音频采集方案
1. **FFmpeg 方案**（推荐）
    - 安装 FFmpeg 并配置路径。
    - 支持大多数 Windows 设备的系统音频采集。
2. **sounddevice 方案**
    - 安装 sounddevice 和 numpy。
    - 适用于部分声卡支持的系统音频环回。
3. **虚拟音频设备**
    - 安装 VB-CABLE、VoiceMeeter 等虚拟音频驱动。
    - 将系统音频输出路由到虚拟设备，再作为输入采集。

### 音频设备调试
- 程序内置音频设备检测与测试功能，可在设置界面或命令行下查看和测试音频采集效果。
- 若系统音频采集失败，请检查：
    - FFmpeg 是否安装并可用
    - 虚拟音频设备是否正确配置
    - 声卡驱动是否支持立体声混音/环回录音

## 配置说明
- 首次运行会生成 `gummy_translator_config.json` 配置文件
- 可通过设置界面修改 API Key、音频源、FFmpeg 路径、ASR/TTS 参数等
- 支持自定义 ASR 模型、TTS 声音、目标语言

## 运行
```bash
python gummy_translator.py
```

## 常见问题
- **FFmpeg 未检测到/不可用**：请检查 FFmpeg 是否安装，或在设置中手动指定路径
- **API Key 无效**：请确认 DashScope/SiliconFlow API Key 已正确填写
- **系统音频采集失败**：尝试更换采集方案，或安装虚拟音频设备

## 参考链接
- [DashScope 语音 API 文档](https://help.aliyun.com/zh/dashscope/developer-reference/quickstart-2)
- [SiliconFlow 官网](https://www.siliconflow.cn/)
- [FFmpeg 官方下载](https://www.gyan.dev/ffmpeg/builds/)
- [VB-CABLE 虚拟音频驱动](https://vb-audio.com/Cable/)
- [VoiceMeeter 虚拟音频设备](https://vb-audio.com/Voicemeeter/)

## 主要功能
- 浮动字幕窗口

## 准备工作

- 开通**阿里云账号**及**阿里云百炼模型服务**、创建阿里云百炼**API\_KEY**并进行必要的**环境配置**，以及安装阿里云百炼**DashScope SDK**，有关步骤的向导请参见[运行示例代码的前提条件](./PREREQUISITES.md)。

## 使用方法

#### 克隆项目

```bash
git clone https://github.com/LoveYou9t/gummy-translator-simultaneous-interpreting.git
```
- 或者通过[`Download Zip`](https://github.com/LoveYou9t/gummy-translator-simultaneous-interpreting/archive/refs/heads/master.zip)下载源代码，并在本地解压到文件。

#### 安装依赖

- cd 到 `项目目录` 下，执行以下命令来安装依赖：

```bash
pip install -r requirements.txt
```

#### 配置APIkey

- 在 `gummy_translator.py` 文件中设置SiliconFlow的api-key及voice。

#### 运行程序

```bash
python gummy_translator.py
```
#### 功能（快捷键）

  Alt+A: 切换音频源（麦克风/系统音频）
  Alt+D: 选择系统音频设备
  Alt+S: 打开设置
  Alt+T: 切换颜色模式
  Ctrl+H: 切换标题栏

## 许可证

- 本项目遵循MIT许可证，参考使用了以下项目：
- [aliyun/alibabacloud-bailian-speech-demo]  
  - Source: [alibabacloud-bailian-speech-demo](https://github.com/aliyun/alibabacloud-bailian-speech-demo)
  - License: MIT  
  - Copyright (c) [2024] [Alibaba Cloud]

