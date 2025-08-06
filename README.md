# Gummy Translator Simultaneous Interpreting

**一个支持系统音频与麦克风输入的桌面同声传译工具**

-----

Gummy Translator 是一个基于 **[DashScope 语音识别与翻译 API](https://help.aliyun.com/zh/dashscope/developer-reference/quickstart-2)**、**[SiliconFlow CosyVoice TTS 语音合成](https://www.siliconflow.cn/)** 的桌面同声传译工具。它能实时捕捉并翻译您电脑的系统声音或麦克风输入，并通过浮动字幕和语音朗读为您提供流畅的翻译体验。

*<img width="886" height="103" alt="image" src="https://github.com/user-attachments/assets/89305856-1163-47f5-9281-daa0287f698e" />
*

## ✨ 主要特性

  - **灵活的音频源**：支持**系统音频**（会议、视频、游戏等）和**麦克风**输入，一键切换。
  - **实时识别与翻译**：基于 DashScope 的高速 ASR 服务，提供精准的实时翻译。
  - **语音合成 (TTS)**：集成 SiliconFlow CosyVoice，自动朗读翻译结果，实现真正的“同声传译”。
  - **浮动字幕窗口**：翻译结果以悬浮字幕形式展示，不干扰您的主要工作区。
  - **多种音频方案**：支持 **FFmpeg**、**sounddevice** 及**虚拟音频设备**（如 VB-CABLE）等多种音频采集方式。
  - **可视化配置**：提供图形化设置界面，轻松管理 API Key、音频设备、ASR/TTS 模型等，配置自动保存。

## ⚙️ 准备工作 (Prerequisites)

在开始之前，请确保您已准备好以下环境和工具：

  - **操作系统**：Windows 10 / 11
  - **Python**：`3.8` 或更高版本
  - **[FFmpeg](https://www.gyan.dev/ffmpeg/builds/)** (推荐): 用于系统音频采集。下载后，建议将其 `bin` 目录添加到系统环境变量 `PATH` 中，或在软件设置中手动指定 `ffmpeg.exe` 的路径。
  - **API Keys**:
      - **[DashScope API Key](https://help.aliyun.com/zh/dashscope/developer-reference/quickstart-2)**: 用于语音识别和翻译。请前往阿里云百炼服务开通并获取。
      - **[SiliconFlow API Key](https://www.siliconflow.cn/)**: 用于语音合成 (TTS)。请前往其官网注册获取。
  - **虚拟音频设备** (可选): 如果您的声卡不支持“立体声混音”且 FFmpeg 无法正常工作，则需要安装 [VB-CABLE](https://vb-audio.com/Cable/) 等工具。

## 🚀 快速开始

#### 1\. 克隆项目

```bash
git clone https://github.com/LoveYou9t/gummy-translator-simultaneous-interpreting.git
cd gummy-translator-simultaneous-interpreting
```

或者，您也可以直接下载项目的 [ZIP 压缩包](https://github.com/LoveYou9t/gummy-translator-simultaneous-interpreting/releases) 并解压。

#### 2\. 安装依赖

项目依赖项已在 `requirements.txt` 中列出。运行以下命令进行安装：

```bash
pip install -r requirements.txt
```

> **注意**：`sounddevice` 和 `numpy` 是备用音频采集方案所需的库，推荐一并安装。

#### 3\. 配置程序

  - **直接运行**：双击或在命令行中运行 `python gummy_translator.py` 启动程序。
  - **打开设置**：程序启动后，按快捷键 `Alt+S` 打开设置窗口。
  - **填写配置**：
      - 填入您的 **DashScope API Key** 和 **SiliconFlow API Key**。
      - 如果 FFmpeg 未能自动检测，请手动指定 `ffmpeg.exe` 的完整路径。
      - 在 `gummy_translator.py` 文件中，您可以根据需要预设 SiliconFlow 的 `voice` 参数。

#### 4\. 配置音频源

  - **麦克风用户**：在程序主界面选择“麦克风”作为输入源即可。
  - **系统音频用户** (如需翻译电脑播放的声音):
      - **方案一 (推荐)**: 大多数 Realtek 声卡用户，只需在 Windows 声音设置中启用“立体声混音”即可。
      - **方案二 (通用)**: 如果没有“立体声混音”，您需要配置虚拟音频设备。

\<details\>
\<summary\>\<b\>点击查看 VB-CABLE 配置教程\</b\>\</summary\>

1.  **下载并安装 VB-CABLE**

      - 前往 [VB-Audio 官网](https://vb-audio.com/Cable/) 下载。
      - 解压文件，找到 `VBCABLE_Setup_x64.exe` (64位) 或 `VBCABLE_Setup.exe` (32位)。
      - **以管理员身份运行**安装程序，并根据提示重启电脑。

2.  **设置系统主输出**

      - 打开 Windows 的“声音设置”。
      - 在“输出”设备列表中，选择 **`CABLE Input (VB-Audio Virtual Cable)`** 作为您的默认输出设备。
      - *注意：此时您的电脑将没有声音，这是正常的。*

3.  **让自己也能听到声音（关键步骤）**

      - 打开“声音控制面板” -\> “录制”选项卡。
      - 找到 **`CABLE Output`** 设备，右键点击 -\> “属性”。
      - 切换到“侦听”选项卡，勾选 **“侦听此设备”**。
      - 在下方的“通过此设备播放”下拉菜单中，选择您**实际使用的耳机或扬声器**（例如 `扬声器 (Realtek High Definition Audio)`）。
      - 点击“应用”保存。

\</details\>

## 🎹 使用方法

#### 运行程序

```bash
python gummy_translator.py
```

#### 快捷键

| 快捷键 | 功能 |
| :--- | :--- |
| `Alt + S` | 打开设置窗口 |
| `Alt + A` | 切换音频源 (麦克风 / 系统音频) |
| `Alt + D` | 选择系统音频设备 |
| `Alt + T` | 切换字幕颜色模式 (深色 / 浅色) |
| `Ctrl + H`| 隐藏/显示浮动窗口的标题栏 |

-----

## 🔧 进阶指南

### 音频采集方案详解

  - **FFmpeg 方案 (推荐)**: 兼容性最好，是采集系统音频的首选。
  - **sounddevice 方案**: 作为备用方案，依赖声卡驱动是否支持环回 (Loopback)。
  - **虚拟音频设备方案**: 最通用的方案，适用于所有复杂情况，但配置稍繁琐。

程序会自动检测可用的采集方式，并优先使用 FFmpeg。如果采集失败，请在设置中检查配置或尝试其他方案。

### 配置文件

所有配置（API Key、路径、模型选择等）都会保存在程序目录下的 `gummy_translator_config.json` 文件中。您可以通过设置界面修改，也可以直接编辑此文件。

## ❓ 常见问题 (FAQ)

  - **FFmpeg 未检测到/不可用？**

    > 请确保 FFmpeg 已正确安装，并且其路径已添加到系统环境变量中，或者在软件设置里手动指定了 `ffmpeg.exe` 的正确位置。

  - **API Key 无效？**

    > 请仔细检查您在设置中填写的 DashScope 和 SiliconFlow API Key 是否正确无误，且账户有足够额度。

  - **系统音频采集失败？**

    > 1.  优先检查 FFmpeg 配置。
    > 2.  尝试启用声卡的“立体声混音”。
    > 3.  如果以上均无效，请按照教程安装并配置 VB-CABLE。

## 📄 许可证

本项目遵循 **MIT License**。

本项目遵循MIT许可证，参考使用了以下项目：
[aliyun/alibabacloud-bailian-speech-demo]
Source: alibabacloud-bailian-speech-demo
License: MIT
Copyright (c) [2024] [Alibaba Cloud]

