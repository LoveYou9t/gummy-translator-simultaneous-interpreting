# 音频设备选择修复说明

## 问题描述
原代码中存在音频设备配置被自动检测覆盖的问题：
1. 用户配置的音频设备索引在每次启动时会被重新获取的设备列表覆盖
2. 设备索引可能因为系统状态变化而改变，导致选择错误的设备
3. 缺少设备名称保存机制，无法持久化用户的设备选择

## 修复内容

### 1. 添加设备名称保存机制
- 新增 `current_system_device_name` 全局变量和配置字段
- 优先使用设备名称而不是索引来识别音频设备
- 自动保存成功连接的设备名称到配置文件

### 2. 改进设备选择逻辑
- 在 `on_open()` 方法中优先使用保存的设备名称
- 当设备名称不可用时，才回退到使用设备索引
- 添加更详细的调试信息显示设备选择过程

### 3. 修复FFmpeg设备捕获逻辑
- 在 `start_ffmpeg_audio_capture()` 中移除强制覆盖设备名称的逻辑
- 改为优先使用用户指定的设备，然后再尝试默认设备
- 分离用户配置设备和备用设备的处理逻辑
- **新增VB-Cable自动检测支持**，特别适合虚拟机环境测试

### 4. 增强设置界面
- 在设置对话框中添加音频设备选择功能
- 支持显示FFmpeg和PyAudio检测到的所有音频设备
- 添加设备列表刷新功能
- **特别标识VB-Cable等虚拟音频设备**

### 5. 添加辅助函数
- `find_audio_device_by_name()`: 通过设备名称查找PyAudio设备索引
- `get_all_audio_devices()`: 统一获取所有可用音频设备
- **`check_vb_cable()`**: 专门检测VB-Cable虚拟音频设备
- **`test_vb_cable()`**: VB-Cable连接测试功能
- 改进虚拟音频设备的连接逻辑

## VB-Cable虚拟机测试支持 🆕

### 什么是VB-Cable
VB-Cable是一个虚拟音频设备，可以在应用程序之间传输音频数据，特别适合：
- 虚拟机环境音频测试
- 音频路由和录制
- 多应用程序音频协作

### 自动检测功能
程序现在会自动检测以下VB-Cable设备：
- `CABLE Output (VB-Audio Virtual Cable)`
- `CABLE Input (VB-Audio Virtual Cable)`
- `VB-Cable`
- `CABLE-A Output (VB-Audio Cable A)`
- `CABLE-B Output (VB-Audio Cable B)`

### 使用方法

#### 1. 安装VB-Cable
- 下载地址: https://vb-audio.com/Cable/
- 安装后重启计算机

#### 2. 配置音频路由
1. 将系统播放设备设置为"CABLE Input"
2. 在程序中选择"CABLE Output"作为录音设备

#### 3. 测试连接
程序启动时选择音频源，输入 `t` 进行VB-Cable测试：
```
请输入选择 (1=麦克风, 2=系统音频, t=测试VB-Cable, q=退出): t
```

#### 4. 虚拟机环境
VB-Cable特别适合虚拟机环境，因为：
- 不依赖物理音频硬件
- 可以精确控制音频流
- 避免虚拟机音频驱动问题

## 使用说明

### 设置音频设备
1. 打开设置对话框
2. 在"音频设置"页面选择"系统音频"
3. 从设备列表中选择想要使用的音频设备
   - `[FFmpeg]` - FFmpeg DirectShow设备
   - `[VB-Cable]` - VB-Cable虚拟音频设备
   - `[Virtual]` - 其他虚拟音频设备
   - `[PyAudio]` - 普通PyAudio设备
4. 点击"确定"保存配置

### 设备名称vs索引
- **设备名称**：更稳定，不会因系统状态变化而改变
- **设备索引**：可能因为设备连接顺序变化而改变

程序现在会：
1. 优先使用保存的设备名称
2. 设备名称无效时回退到索引
3. 自动保存成功连接的设备名称

### 调试信息
程序启动时会输出设备选择过程：
- "使用配置中保存的音频设备: [设备名]"
- "通过索引获取到音频设备: [设备名]"
- "未配置特定的音频设备，将使用FFmpeg的自动检测"
- "检测到VB-Cable设备: [设备名]"

## 技术细节

### 配置文件变化
```json
{
  "current_system_device": 2,          // 设备索引（向后兼容）
  "current_system_device_name": "CABLE Output (VB-Audio Virtual Cable)",  // 设备名称
  // ... 其他配置
}
```

### 设备选择优先级
1. 配置中的设备名称 (`current_system_device_name`)
2. 配置中的设备索引 (`current_system_device`)
3. VB-Cable自动检测
4. FFmpeg自动检测的默认设备

### VB-Cable检测逻辑
```python
vb_keywords = ['cable', 'vb-audio', 'vb-cable']
vb_cable_names = [
    "CABLE Output (VB-Audio Virtual Cable)",
    "CABLE Input (VB-Audio Virtual Cable)", 
    "VB-Cable",
    "CABLE-A Output (VB-Audio Cable A)",
    # ...
]
```

这样修复后，用户选择的音频设备将不会被自动检测覆盖，特别增强了对VB-Cable虚拟音频设备的支持，提供更稳定和可预测的音频设备选择体验，特别适合虚拟机环境的开发和测试工作。
