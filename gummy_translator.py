import os
import queue
import threading
import time
import subprocess
import json
import tempfile

import dashscope
import pyaudio
import wx
import wx.richtext as rt
from dashscope.audio.asr import *
from dashscope.audio.tts_v2 import *

import requests
import ctypes  # 导入 ctypes 库

# Win11 UI 主题配置
class Win11Theme:
    """Win11风格主题配置"""
    
    # Win11 颜色方案
    COLORS = {
        'background': wx.Colour(243, 243, 243),      # 浅灰背景
        'surface': wx.Colour(255, 255, 255),        # 白色表面
        'surface_variant': wx.Colour(248, 248, 248), # 浅灰变体
        'primary': wx.Colour(0, 120, 215),          # Win11蓝色
        'primary_variant': wx.Colour(16, 110, 190),  # 深蓝变体
        'secondary': wx.Colour(118, 118, 118),       # 灰色
        'text_primary': wx.Colour(32, 31, 30),       # 深灰文字
        'text_secondary': wx.Colour(96, 94, 92),     # 中灰文字
        'text_disabled': wx.Colour(161, 159, 157),   # 浅灰文字
        'accent': wx.Colour(0, 120, 215),           # 强调色
        'success': wx.Colour(16, 124, 16),          # 成功绿色
        'warning': wx.Colour(255, 185, 0),          # 警告黄色
        'error': wx.Colour(196, 43, 28),            # 错误红色
        'border': wx.Colour(225, 223, 221),         # 边框颜色
        'hover': wx.Colour(243, 242, 241),          # 悬停颜色
    }
    
    # 字体配置
    @staticmethod
    def get_font(size=10, weight=wx.FONTWEIGHT_NORMAL, family=wx.FONTFAMILY_DEFAULT):
        """获取Win11风格字体"""
        font = wx.Font(size, family, wx.FONTSTYLE_NORMAL, weight, False, "Segoe UI")
        if not font.IsOk():
            # 如果Segoe UI不可用，使用系统默认字体
            font = wx.Font(size, family, wx.FONTSTYLE_NORMAL, weight)
        return font
    
    @staticmethod
    def apply_button_style(button, primary=False):
        """应用Win11按钮样式"""
        if primary:
            button.SetBackgroundColour(Win11Theme.COLORS['primary'])
            button.SetForegroundColour(wx.Colour(255, 255, 255))
        else:
            button.SetBackgroundColour(Win11Theme.COLORS['surface'])
            button.SetForegroundColour(Win11Theme.COLORS['text_primary'])
        
        button.SetFont(Win11Theme.get_font(9, wx.FONTWEIGHT_NORMAL))
        
    @staticmethod
    def apply_panel_style(panel):
        """应用Win11面板样式"""
        panel.SetBackgroundColour(Win11Theme.COLORS['surface'])
        
    @staticmethod
    def apply_textctrl_style(textctrl):
        """应用Win11文本框样式"""
        textctrl.SetBackgroundColour(Win11Theme.COLORS['surface'])
        textctrl.SetForegroundColour(Win11Theme.COLORS['text_primary'])
        textctrl.SetFont(Win11Theme.get_font(9))
        
    @staticmethod
    def apply_statictext_style(statictext, secondary=False):
        """应用Win11静态文本样式"""
        if secondary:
            statictext.SetForegroundColour(Win11Theme.COLORS['text_secondary'])
        else:
            statictext.SetForegroundColour(Win11Theme.COLORS['text_primary'])
        statictext.SetFont(Win11Theme.get_font(9))
        
    @staticmethod
    def apply_choice_style(choice):
        """应用Win11选择框样式"""
        choice.SetBackgroundColour(Win11Theme.COLORS['surface'])
        choice.SetForegroundColour(Win11Theme.COLORS['text_primary'])
        choice.SetFont(Win11Theme.get_font(9))

class Win11Panel(wx.Panel):
    """Win11风格面板"""
    
    def __init__(self, parent, **kwargs):
        super().__init__(parent, **kwargs)
        Win11Theme.apply_panel_style(self)

class Win11Button(wx.Button):
    """Win11风格按钮"""
    
    def __init__(self, parent, id=wx.ID_ANY, label="", pos=wx.DefaultPosition, 
                 size=wx.DefaultSize, style=0, primary=False, **kwargs):
        super().__init__(parent, id, label, pos, size, style, **kwargs)
        
        self.primary = primary
        Win11Theme.apply_button_style(self, primary)
        
        # 设置最小高度
        size = self.GetSize()
        if size.height < 32:
            self.SetMinSize((size.width, 32))

# Add a global variable to control TTS
enable_tts = False

# Add a global variable to control API calls
enable_api_calls = True  # 默认启用API调用

# Add a global variable to control listening/pause
listening_paused = False  # 默认不暂停监听

# Add a global variable to track translator status
translator_stopped = False  # 跟踪translator状态
need_restart_translator = False  # 标记是否需要重启translator

# Add global variables for audio source control
audio_source = 'system'  # 'microphone' or 'system' - 默认使用系统音频
current_system_device = None  # 当前选择的系统音频设备(索引)
current_system_device_name = None  # 当前选择的系统音频设备名称
ffmpeg_process = None  # FFmpeg进程
system_audio_queue = queue.Queue()  # 系统音频数据队列
ffmpeg_path = None  # 自定义FFmpeg路径

# 控制台输出控制
enable_console_output = True  # 默认启用控制台输出

def console_print(*args, **kwargs):
    """控制台输出包装器函数"""
    if enable_console_output:
        print(*args, **kwargs)

# 配置文件路径
CONFIG_FILE = 'gummy_translator_config.json'

# 默认配置
DEFAULT_CONFIG = {
    'audio_source': 'system',
    'ffmpeg_path': None,
    'dashscope_api_key': '<your-dashscope-api-key>',
    'siliconflow_api_key': '<your-SiliconFlow-api-key>',
    'target_language': 'zh',
    'tts_voice': 'FunAudioLLM/CosyVoice2-0.5B:alex',
    'current_system_device': None,
    'current_system_device_name': None,
    'enable_tts': False,
    'asr_model': 'gummy-realtime-v1',  # 默认ASR模型
    'enable_console_output': True,  # 默认启用控制台输出
    'api': {
        'enabled': True  # 默认启用API调用
    }
}

# 全局配置
config = DEFAULT_CONFIG.copy()

def load_config():
    """加载配置文件"""
    global config, audio_source, ffmpeg_path, target_language, current_system_device, current_system_device_name, enable_tts, enable_api_calls, enable_console_output
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                config.update(saved_config)
                console_print(f"已加载配置文件: {CONFIG_FILE}")
        else:
            console_print("未找到配置文件，使用默认配置")
    except Exception as e:
        console_print(f"加载配置文件失败: {e}，使用默认配置")
        config = DEFAULT_CONFIG.copy()
    
    # 应用配置到全局变量
    audio_source = config.get('audio_source', 'system')
    ffmpeg_path = config.get('ffmpeg_path', None)
    target_language = config.get('target_language', 'zh')
    current_system_device = config.get('current_system_device', None)
    current_system_device_name = config.get('current_system_device_name', None)
    enable_tts = config.get('enable_tts', False)
    enable_api_calls = config.get('api', {}).get('enabled', True)
    enable_console_output = config.get('enable_console_output', True)

def save_config():
    """保存配置文件"""
    global config, enable_api_calls, enable_console_output
    
    # 更新配置
    config['audio_source'] = audio_source
    config['ffmpeg_path'] = ffmpeg_path
    config['target_language'] = target_language
    config['current_system_device'] = current_system_device
    config['current_system_device_name'] = current_system_device_name
    config['enable_tts'] = enable_tts
    config['enable_console_output'] = enable_console_output
    # asr_model会在设置对话框中更新，这里不需要修改
    
    # 确保api配置存在
    if 'api' not in config:
        config['api'] = {}
    config['api']['enabled'] = enable_api_calls
    
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        console_print(f"配置已保存到: {CONFIG_FILE}")
    except Exception as e:
        console_print(f"保存配置文件失败: {e}")

# Set your Dashscope API key
def init_dashscope_api_key():
    """
        Set your DashScope API-key. More information:
        https://github.com/aliyun/alibabacloud-bailian-speech-demo/blob/master/PREREQUISITES.md
    """
    global config
    
    if 'DASHSCOPE_API_KEY' in os.environ:
        dashscope.api_key = os.environ['DASHSCOPE_API_KEY']
        config['dashscope_api_key'] = os.environ['DASHSCOPE_API_KEY']
        console_print(f"✅ 使用环境变量中的DashScope API Key")
    elif config.get('dashscope_api_key') and config['dashscope_api_key'] != '<your-dashscope-api-key>':
        dashscope.api_key = config['dashscope_api_key']
        console_print(f"✅ 使用配置文件中的DashScope API Key")
    else:
        dashscope.api_key = '<your-dashscope-api-key>'  # set API-key manually
        console_print(f"❌ 警告: DashScope API Key未配置！请设置正确的API密钥")
    
    # 检查API调用是否启用
    if not enable_api_calls:
        console_print(f"⚠️  警告: API调用已禁用，translator不会处理音频数据")
    else:
        console_print(f"✅ API调用已启用")

def check_api_status():
    """检查API状态"""
    console_print("\n" + "=" * 50)
    console_print("🔍 API状态检查")
    console_print("=" * 50)
    
    # 检查enable_api_calls状态
    console_print(f"API调用启用状态: {'✅ 启用' if enable_api_calls else '❌ 禁用'}")
    
    # 检查DashScope API Key
    api_key_status = "未设置"
    if hasattr(dashscope, 'api_key') and dashscope.api_key:
        if dashscope.api_key != '<your-dashscope-api-key>':
            api_key_status = f"✅ 已设置 ({dashscope.api_key[:10]}...)"
        else:
            api_key_status = "❌ 默认值，需要配置"
    console_print(f"DashScope API Key: {api_key_status}")
    
    # 检查目标语言
    console_print(f"翻译目标语言: {target_language}")
    
    console_print("=" * 50)

# Set the target language for translation
target_language = 'zh'

# Function to check if FFmpeg is available
def check_ffmpeg():
    """检查FFmpeg是否可用"""
    global ffmpeg_path, config
    
    # 如果配置中有自定义路径，优先使用
    if config.get('ffmpeg_path') and os.path.exists(config['ffmpeg_path']):
        try:
            result = subprocess.run([config['ffmpeg_path'], '-version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                ffmpeg_path = config['ffmpeg_path']
                console_print(f"使用配置中的FFmpeg: {ffmpeg_path}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            console_print(f"配置中的FFmpeg路径无效: {config['ffmpeg_path']}")
    
    # 首先尝试系统PATH中的ffmpeg
    try:
        result = subprocess.run(['ffmpeg', '-version'], 
                              capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            ffmpeg_path = 'ffmpeg'  # 使用系统PATH中的ffmpeg
            return True
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    
    # 如果系统PATH中找不到，尝试常见的安装路径
    common_paths = [
        r'C:\Users\9t\ffmpeg-7.1.1-essentials_build\bin\ffmpeg.exe',
        r'C:\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files\ffmpeg\bin\ffmpeg.exe',
        r'C:\Program Files (x86)\ffmpeg\bin\ffmpeg.exe'
    ]
    
    for path in common_paths:
        if os.path.exists(path):
            try:
                result = subprocess.run([path, '-version'], 
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    ffmpeg_path = path
                    console_print(f"找到FFmpeg: {path}")
                    return True
            except (subprocess.TimeoutExpired, FileNotFoundError):
                continue
    
    return False

def get_ffmpeg_command():
    """获取FFmpeg命令路径"""
    global ffmpeg_path
    if ffmpeg_path is None:
        check_ffmpeg()
    return ffmpeg_path or 'ffmpeg'

def test_vb_cable():
    """测试VB-Cable设备连接"""
    console_print("\n" + "=" * 60)
    console_print("🧪 VB-Cable连接测试")
    console_print("=" * 60)
    
    vb_found, vb_devices = check_vb_cable()
    
    if not vb_found:
        console_print("❌ 未找到VB-Cable设备，无法进行测试")
        return False
    
    # 查找输入设备（用于录音）
    input_devices = [d for d in vb_devices if d['type'] == 'input' and d['channels'] > 0]
    
    if not input_devices:
        console_print("❌ 未找到VB-Cable输入设备")
        return False
    
    test_device = input_devices[0]
    console_print(f"🎯 测试设备: {test_device['name']}")
    console_print("📝 测试说明:")
    console_print("  1. 确保你的音频播放设备设置为VB-Cable Output")
    console_print("  2. 播放一些音频（音乐、视频等）")
    console_print("  3. 测试将运行5秒钟检测音频数据")
    console_print()
    
    input("按回车键开始测试...")
    
    try:
        p = pyaudio.PyAudio()
        stream = p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=16000,
            input=True,
            input_device_index=test_device['index'],
            frames_per_buffer=1024
        )
        
        console_print("🎵 开始监听VB-Cable音频...")
        data_count = 0
        start_time = time.time()
        
        while time.time() - start_time < 5:
            try:
                data = stream.read(1024, exception_on_overflow=False)
                if data:
                    data_count += 1
                    if data_count % 20 == 0:  # 每秒显示一次
                        console_print(f"⏱️  已接收 {data_count} 个音频数据包...")
            except Exception as e:
                console_print(f"读取音频数据时出错: {e}")
                break
        
        stream.stop_stream()
        stream.close()
        p.terminate()
        
        console_print(f"\n📊 测试结果:")
        console_print(f"  接收的数据包数量: {data_count}")
        
        if data_count > 0:
            console_print("✅ VB-Cable测试成功！")
            console_print("  VB-Cable可以正常接收音频数据")
            return True
        else:
            console_print("❌ VB-Cable测试失败！")
            console_print("  可能的原因:")
            console_print("  1. 音频播放设备未设置为VB-Cable Output")
            console_print("  2. 系统没有播放音频")
            console_print("  3. VB-Cable驱动程序问题")
            return False
            
    except Exception as e:
        console_print(f"❌ 测试过程出错: {e}")
        return False

def test_audio_capture():
    """测试音频捕获功能"""
    console_print("\n" + "=" * 60)
    console_print("🧪 音频捕获测试")
    console_print("=" * 60)
    
    if not check_ffmpeg():
        console_print("❌ FFmpeg不可用，无法进行测试")
        return False
    
    console_print("🎵 开始测试系统音频捕获...")
    console_print("请在系统中播放一些音频（音乐、视频等）")
    console_print("测试将运行10秒钟...")
    
    # 启动音频捕获
    success = start_ffmpeg_audio_capture()
    
    if not success:
        console_print("❌ 音频捕获启动失败")
        return False
    
    # 测试10秒钟
    start_time = time.time()
    data_count = 0
    
    try:
        while time.time() - start_time < 10:
            try:
                # 检查是否有音频数据
                data = system_audio_queue.get(timeout=0.1)
                if data:
                    data_count += 1
                    if data_count % 10 == 0:  # 每秒显示一次
                        console_print(f"⏱️  已捕获 {data_count} 个音频数据包...")
            except queue.Empty:
                continue
                
    except KeyboardInterrupt:
        console_print("用户中断测试")
    
    # 停止捕获
    stop_ffmpeg_audio_capture()
    
    console_print(f"\n📊 测试结果:")
    console_print(f"  捕获的数据包数量: {data_count}")
    
    if data_count > 0:
        console_print("✅ 音频捕获测试成功！")
        console_print("  系统音频可以正常捕获")
        return True
    else:
        console_print("❌ 音频捕获测试失败！")
        console_print("  可能的原因:")
        console_print("  1. 系统没有播放音频")
        console_print("  2. 立体声混音未启用")
        console_print("  3. 需要使用虚拟音频设备")
        console_print("  4. 权限问题")
        return False

def list_all_audio_devices():
    """列出所有可用的音频设备用于调试"""
    console_print("\n" + "=" * 60)
    console_print("🔍 检测系统音频设备")
    console_print("=" * 60)
    
    # 0. 检查VB-Cable
    console_print("\n🎛️ VB-Cable检测:")
    check_vb_cable()
    
    # 1. 检查FFmpeg设备
    console_print("\n📺 FFmpeg DirectShow 设备:")
    ffmpeg_devices = get_windows_audio_devices()
    if ffmpeg_devices:
        for i, device in enumerate(ffmpeg_devices):
            console_print(f"  {i}: {device['name']}")
    else:
        console_print("  未检测到FFmpeg DirectShow设备")
    
    # 2. 检查PyAudio设备
    console_print("\n🎤 PyAudio 设备:")
    try:
        import pyaudio
        p = pyaudio.PyAudio()
        
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)
            device_type = ""
            if device_info['maxInputChannels'] > 0:
                device_type += "输入 "
            if device_info['maxOutputChannels'] > 0:
                device_type += "输出 "
            
            # 特别标记VB-Cable设备
            device_name = device_info['name']
            vb_indicator = ""
            if any(keyword in device_name.lower() for keyword in ['cable', 'vb-audio', 'vb-cable']):
                vb_indicator = " [VB-Cable]"
            
            console_print(f"  {i}: {device_name} ({device_type}){vb_indicator}")
        
        p.terminate()
    except Exception as e:
        console_print(f"  获取PyAudio设备失败: {e}")
    
    # 3. 检查虚拟音频设备
    console_print("\n🔄 虚拟音频设备:")
    virtual_devices = get_virtual_audio_devices()
    if virtual_devices:
        for device in virtual_devices:
            console_print(f"  {device['index']}: {device['name']}")
    else:
        console_print("  未检测到虚拟音频设备")
    
    console_print("\n" + "=" * 60)

def show_audio_source_selection():
    """显示音频源选择对话框"""
    # 检查FFmpeg状态
    ffmpeg_available = check_ffmpeg()
    ffmpeg_status = "✅ 可用" if ffmpeg_available else "❌ 不可用"
    
    # 检查VB-Cable状态
    vb_found, vb_devices = check_vb_cable()
    vb_status = "✅ 已安装" if vb_found else "❌ 未安装"
    
    console_print()
    console_print("=" * 60)
    console_print("🎵 请选择音频输入源")
    console_print("=" * 60)
    console_print()
    console_print("🎤 选项1: 麦克风录音")
    console_print("   - 捕获麦克风输入的语音")
    console_print("   - 适用于用户直接说话的场景")
    console_print("   - 稳定可靠，无需额外配置")
    console_print()
    console_print(f"🔊 选项2: 系统音频 (FFmpeg: {ffmpeg_status}, VB-Cable: {vb_status})")
    console_print("   - 捕获电脑播放的音频")
    console_print("   - 适用于翻译视频、音乐等系统声音")
    console_print("   - 自动优先级: VB-Cable > 立体声混音 > WASAPI")
    if vb_found:
        console_print(f"   - 🎯 检测到 {len(vb_devices)} 个VB-Cable设备，将优先使用")
    console_print("   - 📻 自动检测立体声混音设备，提高成功率")
    console_print()
    console_print("=" * 60)
    
    while True:
        try:
            choice = input("请输入选择 (1=麦克风, 2=系统音频, t=测试VB-Cable, q=退出): ").strip().lower()
            
            if choice == 'q' or choice == 'quit':
                console_print("用户选择退出程序")
                return None
            elif choice == 't' or choice == 'test':
                if vb_found:
                    test_vb_cable()
                else:
                    console_print("❌ 未检测到VB-Cable设备，无法进行测试")
                    console_print("💡 请先安装VB-Cable: https://vb-audio.com/Cable/")
                continue
            elif choice == '1' or choice == 'mic' or choice == 'microphone':
                console_print("✅ 已选择: 麦克风录音")
                return 'microphone'
            elif choice == '2' or choice == 'system':
                console_print("✅ 已选择: 系统音频")
                
                if not ffmpeg_available and not vb_found:
                    console_print()
                    console_print("⚠️  注意: 系统音频捕获需要额外组件支持")
                    console_print("-" * 50)
                    console_print("📦 方案1: 安装FFmpeg (推荐)")
                    console_print("  • winget install FFmpeg")
                    console_print("  • 或手动下载: https://www.gyan.dev/ffmpeg/builds/")
                    console_print()
                    console_print("🎛️ 方案2: 虚拟音频设备")
                    console_print("  • VB-CABLE: https://vb-audio.com/Cable/")
                    console_print("  • VoiceMeeter: https://vb-audio.com/Voicemeeter/")
                    console_print("  • 特别适合虚拟机环境测试")
                    console_print("-" * 50)
                    console_print()
                    
                    while True:
                        confirm = input("是否继续使用系统音频模式？(y/n): ").strip().lower()
                        if confirm in ['y', 'yes', '是']:
                            console_print("继续使用系统音频模式（程序会尝试使用可用的备用方案）")
                            return 'system'
                        elif confirm in ['n', 'no', '否']:
                            console_print("重新选择音频源...")
                            break
                        else:
                            console_print("请输入 y 或 n")
                else:
                    if vb_found:
                        console_print(f"✅ 检测到VB-Cable设备，适合虚拟机环境")
                    return 'system'
            else:
                console_print("❌ 无效选择，请输入 1、2、t 或 q")
                
        except KeyboardInterrupt:
            console_print("\n用户中断程序")
            return None
        except Exception as e:
            console_print(f"输入错误: {e}")
            console_print("请重新输入")

# Function to get Windows audio devices using FFmpeg
def get_windows_audio_devices():
    """使用FFmpeg获取Windows音频设备列表"""
    try:
        # 使用FFmpeg的dshow过滤器列出音频设备
        cmd = [get_ffmpeg_command(), '-f', 'dshow', '-list_devices', 'true', '-i', 'dummy']
        
        # 指定编码为utf-8，避免GBK编码问题
        result = subprocess.run(cmd, capture_output=True, text=True, 
                              encoding='utf-8', errors='ignore', timeout=10)
        
        devices = []
        
        # 检查result.stderr是否为None
        if result.stderr is None:
            console_print("FFmpeg stderr输出为空")
            return devices
            
        lines = result.stderr.split('\n')
        
        audio_section = False
        for line in lines:
            if '"DirectShow audio devices"' in line:
                audio_section = True
                continue
            elif '"DirectShow video devices"' in line:
                audio_section = False
                continue
            
            if audio_section and '] "' in line:
                # 解析设备名称
                start = line.find('] "') + 3
                end = line.find('"', start)
                if start > 2 and end > start:
                    device_name = line[start:end]
                    devices.append({
                        'name': device_name,
                        'type': 'dshow',
                        'index': len(devices)
                    })
        
        return devices
    except UnicodeDecodeError as e:
        console_print(f"FFmpeg输出编码错误: {e}")
        # 尝试使用其他编码
        try:
            result = subprocess.run(cmd, capture_output=True, 
                                  encoding='gbk', errors='ignore', timeout=10)
            if result.stderr:
                lines = result.stderr.split('\n')
                devices = []
                audio_section = False
                for line in lines:
                    if '"DirectShow audio devices"' in line:
                        audio_section = True
                        continue
                    elif '"DirectShow video devices"' in line:
                        audio_section = False
                        continue
                    
                    if audio_section and '] "' in line:
                        start = line.find('] "') + 3
                        end = line.find('"', start)
                        if start > 2 and end > start:
                            device_name = line[start:end]
                            devices.append({
                                'name': device_name,
                                'type': 'dshow',
                                'index': len(devices)
                            })
                return devices
        except Exception as fallback_e:
            console_print(f"使用GBK编码也失败: {fallback_e}")
        return []
    except Exception as e:
        console_print(f"获取FFmpeg音频设备失败: {e}")
        return []

# Function to start FFmpeg system audio capture
def start_ffmpeg_audio_capture(device_name=None):
    """启动FFmpeg系统音频捕获"""
    global ffmpeg_process, system_audio_queue
    
    try:
        # 停止之前的进程
        stop_ffmpeg_audio_capture()
        
        # 清空队列中的旧数据
        while not system_audio_queue.empty():
            try:
                system_audio_queue.get_nowait()
            except queue.Empty:
                break
        
        # 尝试多种捕获方法，优先使用VB-Cable和立体声混音
        capture_methods = []
        
        # 优先级1: 用户指定的DirectShow设备（如果有的话）
        if device_name is not None:
            capture_methods.append({
                'name': f'DirectShow - {device_name}',
                'cmd': [
                    get_ffmpeg_command(),
                    '-f', 'dshow',
                    '-i', f'audio={device_name}',
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    '-loglevel', 'info',
                    '-f', 'wav',
                    'pipe:1'
                ]
            })
        
        # 优先级2: VB-Cable虚拟音频设备（优先使用，适合虚拟机测试）
        vb_cable_names = [
            "CABLE Output (VB-Audio Virtual Cable)",
            "VB-Cable",
            "CABLE-A Output (VB-Audio Cable A)",
            "CABLE-B Output (VB-Audio Cable B)"
        ]
        
        for vb_name in vb_cable_names:
            capture_methods.append({
                'name': f'DirectShow - {vb_name}',
                'cmd': [
                    get_ffmpeg_command(),
                    '-f', 'dshow',
                    '-i', f'audio={vb_name}',
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    '-loglevel', 'info',
                    '-f', 'wav',
                    'pipe:1'
                ]
            })
        
        # 优先级3: 立体声混音设备（提前优先级）
        stereo_mix_names = [
            "立体声混音 (Realtek(R) Audio)",  # 常见的Realtek音频设备
            "Stereo Mix",
            "立体声混音", 
            "混音器",
            "What U Hear",
            "Wave Out Mix"
        ]
        
        for mix_name in stereo_mix_names:
            capture_methods.append({
                'name': f'DirectShow - {mix_name}',
                'cmd': [
                    get_ffmpeg_command(),
                    '-f', 'dshow',
                    '-i', f'audio={mix_name}',
                    '-acodec', 'pcm_s16le',
                    '-ar', '16000',
                    '-ac', '1',
                    '-loglevel', 'info',
                    '-f', 'wav',
                    'pipe:1'
                ]
            })
        
        # 优先级4: WASAPI方法（作为备用）
        capture_methods.append({
            'name': 'WASAPI默认输出设备',
            'cmd': [
                get_ffmpeg_command(),
                '-f', 'wasapi',
                '-i', 'audio=',  # 空字符串表示默认设备
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-loglevel', 'info',  # 临时提高日志级别用于调试
                '-f', 'wav',
                'pipe:1'
            ]
        })
        
        # 优先级5: WASAPI with loopback flag
        capture_methods.append({
            'name': 'WASAPI Loopback',
            'cmd': [
                get_ffmpeg_command(),
                '-f', 'wasapi',
                '-i', 'audio=@device_cm_{33D9A762-90C8-11D0-BD43-00A0C911CE86}\\wave_{B3F8FA53-0004-438E-9003-51A46E139BEB}',
                '-acodec', 'pcm_s16le',
                '-ar', '16000',
                '-ac', '1',
                '-loglevel', 'info',
                '-f', 'wav',
                'pipe:1'
            ]
        })
        
        # 依次尝试每种方法
        for method in capture_methods:
            console_print(f"尝试音频捕获方法: {method['name']}")
            try:
                ffmpeg_process = subprocess.Popen(
                    method['cmd'],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    bufsize=0
                )
                
                # 等待进程启动并检查是否成功
                time.sleep(1.0)
                
                if ffmpeg_process.poll() is None:
                    # 进程仍在运行，可能成功了
                    console_print(f"✅ {method['name']} 启动成功")
                    break
                else:
                    # 进程已退出，获取错误信息
                    stderr_output = ffmpeg_process.stderr.read().decode('utf-8', errors='ignore')
                    console_print(f"❌ {method['name']} 失败: {stderr_output[:200]}...")
                    ffmpeg_process = None
                    
            except Exception as e:
                console_print(f"❌ {method['name']} 异常: {e}")
                ffmpeg_process = None
        
        if ffmpeg_process is None:
            console_print("所有音频捕获方法都失败了")
            return False
        
        # 启动线程读取音频数据
        audio_thread = threading.Thread(target=read_ffmpeg_audio, daemon=True)
        audio_thread.start()
        
        console_print(f"FFmpeg音频捕获已启动")
        return True
        
    except Exception as e:
        console_print(f"启动FFmpeg音频捕获失败: {e}")
        return False

def read_ffmpeg_audio():
    """读取FFmpeg输出的音频数据"""
    global ffmpeg_process, system_audio_queue
    
    if ffmpeg_process is None:
        console_print("FFmpeg进程为空，无法读取音频")
        return
    
    try:
        # 跳过WAV文件头（44字节）
        header = ffmpeg_process.stdout.read(44)
        if len(header) < 44:
            console_print(f"警告: WAV文件头不完整，只读取到 {len(header)} 字节")
            return
        
        console_print("开始读取FFmpeg音频数据...")
        audio_data_count = 0
        
        while ffmpeg_process and ffmpeg_process.poll() is None:
            # 读取音频数据块（3200字节 = 16000Hz * 2字节 * 0.1秒）
            try:
                data = ffmpeg_process.stdout.read(3200)
                if data:
                    system_audio_queue.put(data)
                    audio_data_count += 1
                    
                    # 每收到100个数据块打印一次状态（约10秒）
                    if audio_data_count % 100 == 0:
                        console_print(f"已读取 {audio_data_count} 个音频数据块，队列大小: {system_audio_queue.qsize()}")
                else:
                    console_print("FFmpeg输出流结束")
                    break
            except Exception as read_error:
                console_print(f"读取音频数据块时出错: {read_error}")
                break
                
    except Exception as e:
        console_print(f"读取FFmpeg音频数据出错: {e}")
    finally:
        if ffmpeg_process:
            # 获取错误输出
            try:
                stderr_output = ffmpeg_process.stderr.read().decode('utf-8', errors='ignore')
                if stderr_output.strip():
                    console_print(f"FFmpeg错误输出: {stderr_output}")
            except:
                pass
        console_print(f"FFmpeg音频读取线程结束，总共读取了 {audio_data_count} 个数据块")

def stop_ffmpeg_audio_capture():
    """停止FFmpeg音频捕获"""
    global ffmpeg_process
    
    if ffmpeg_process:
        try:
            ffmpeg_process.terminate()
            ffmpeg_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            ffmpeg_process.kill()
        except Exception as e:
            console_print(f"停止FFmpeg进程出错: {e}")
        finally:
            ffmpeg_process = None

def find_audio_device_by_name(device_name):
    """通过设备名称查找音频设备索引"""
    try:
        p = pyaudio.PyAudio()
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)
            if device_info['maxInputChannels'] > 0 and device_info['name'] == device_name:
                p.terminate()
                return i
        p.terminate()
        return None
    except Exception as e:
        console_print(f"查找音频设备失败: {e}")
        return None

def check_vb_cable():
    """检查是否安装了VB-Cable"""
    try:
        p = pyaudio.PyAudio()
        vb_cable_found = False
        vb_devices = []
        
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)
            device_name = device_info['name'].lower()
            
            # 检查VB-Cable相关设备
            vb_indicators = ['cable', 'vb-audio', 'vb-cable']
            if any(indicator in device_name for indicator in vb_indicators):
                vb_cable_found = True
                vb_devices.append({
                    'index': i,
                    'name': device_info['name'],
                    'channels': device_info['maxInputChannels'],
                    'type': 'input' if device_info['maxInputChannels'] > 0 else 'output'
                })
        
        p.terminate()
        
        if vb_cable_found:
            console_print("✅ 检测到VB-Cable虚拟音频设备:")
            for device in vb_devices:
                console_print(f"  - {device['name']} ({device['type']}, {device['channels']}通道)")
        else:
            console_print("❌ 未检测到VB-Cable设备")
            console_print("💡 建议安装VB-Cable以支持虚拟机音频测试:")
            console_print("   下载地址: https://vb-audio.com/Cable/")
        
        return vb_cable_found, vb_devices
        
    except Exception as e:
        console_print(f"检查VB-Cable时出错: {e}")
        return False, []

# Function to get virtual audio devices
def get_virtual_audio_devices():
    """获取虚拟音频设备（VB-CABLE, Virtual Audio Cable等），优先检测VB-Cable"""
    devices = get_system_audio_devices()
    virtual_devices = []
    
    # VB-Cable特定设备名称（优先检测）
    vb_cable_names = [
        "CABLE Output (VB-Audio Virtual Cable)",
        "CABLE Input (VB-Audio Virtual Cable)", 
        "VB-Cable",
        "CABLE-A Output (VB-Audio Cable A)",
        "CABLE-A Input (VB-Audio Cable A)",
        "CABLE-B Output (VB-Audio Cable B)",
        "CABLE-B Input (VB-Audio Cable B)"
    ]
    
    # 其他虚拟音频设备关键词
    virtual_keywords = [
        'virtual audio cable', 'voicemeeter', 
        'virtual', 'vac', 'line', 'aux'
    ]
    
    # 立体声混音关键词
    stereo_mix_keywords = [
        'stereo mix', '立体声混音', '混音器', 'what u hear', 'wave out mix'
    ]
    
    for device in devices:
        if device['type'] == 'input':
            device_name = device['name']
            device_name_lower = device_name.lower()
            
            # 优先级1: 检查VB-Cable特定设备名称
            if any(vb_name.lower() in device_name_lower for vb_name in vb_cable_names):
                virtual_devices.insert(0, device)  # 插入到前面
                console_print(f"✅ 检测到VB-Cable设备: {device_name}")
                continue
            
            # 优先级2: 检查立体声混音设备
            elif any(keyword in device_name_lower for keyword in stereo_mix_keywords):
                virtual_devices.insert(len([d for d in virtual_devices if 'vb' in d['name'].lower() or 'cable' in d['name'].lower()]), device)  # 在VB-Cable后面，其他前面
                console_print(f"✅ 检测到立体声混音设备: {device_name}")
                continue
            
            # 优先级3: 检查其他虚拟音频设备关键词
            elif any(keyword in device_name_lower for keyword in virtual_keywords):
                virtual_devices.append(device)  # 添加到末尾
                console_print(f"✅ 检测到虚拟音频设备: {device_name}")
    
    return virtual_devices

# Function to get available audio output devices
def get_system_audio_devices():
    """获取系统音频输出设备列表"""
    try:
        # 使用PyAudio获取设备信息
        p = pyaudio.PyAudio()
        devices = []
        
        for i in range(p.get_device_count()):
            device_info = p.get_device_info_by_index(i)
            # 查找支持输入的设备（用于环回录音）
            if device_info['maxInputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': device_info['name'],
                    'sample_rate': int(device_info['defaultSampleRate']),
                    'type': 'input'
                })
            # 也添加输出设备信息供参考
            elif device_info['maxOutputChannels'] > 0:
                devices.append({
                    'index': i,
                    'name': device_info['name'] + ' (输出设备)',
                    'sample_rate': int(device_info['defaultSampleRate']),
                    'type': 'output'
                })
        
        p.terminate()
        return devices
    except Exception as e:
        console_print(f"获取音频设备列表失败: {e}")
        return []

# Lock for controlling access to the PyAudio stream
pyaudio_lock = threading.Lock()

# Initialize global variables for microphone and audio stream
mic = None
audio_stream = None
# Queue for text updates in wx
wx_text_queue = queue.Queue()
# Queue for fixed words from ASR
asr_fixed_words = queue.Queue()


# Handle the ASR task. This function will get audio from microphone in while loop and send it to ASR.
# The streaming output of ASR will be pushed back to the wx_text_queue and  asr_fixed_words
def restart_translator(old_translator):
    """重启translator"""
    global translator_stopped, need_restart_translator
    
    try:
        # 停止旧的translator
        if old_translator and not translator_stopped:
            console_print("正在停止旧的translator...")
            old_translator.stop()
        
        # 重置状态
        translator_stopped = False
        need_restart_translator = False
        
        # 创建新的callback
        class Callback(TranslationRecognizerCallback):
            def __init__(self):
                super().__init__()
                self.sentence_ptr = 0
                self.zh_word_ptr = 0
                self.tg_word_ptr = 0

            def on_open(self) -> None:
                console_print('新的TranslationRecognizerCallback已打开')

            def on_close(self) -> None:
                global translator_stopped
                console_print('TranslationRecognizerCallback关闭')
                translator_stopped = True

            def on_event(self, request_id, transcription_result, translation_result, usage) -> None:
                new_chinese_words = ''
                new_target_language_words = ''
                is_sentence_end = False

                if transcription_result != None:
                    for i, word in enumerate(transcription_result.words):
                        if word.fixed:
                            if i >= self.zh_word_ptr:
                                new_chinese_words += word.text
                                self.zh_word_ptr += 1

                if translation_result != None:
                    target_language_translation = translation_result.get_translation('zh')
                    if target_language_translation != None:
                        for i, word in enumerate(target_language_translation.words):
                            if word.fixed:
                                if i >= self.tg_word_ptr:
                                    asr_fixed_words.put([word.text, False])
                                    new_target_language_words += word.text
                                    self.tg_word_ptr += 1
                        if target_language_translation.is_sentence_end:
                            console_print('target_language sentence end')
                            self.sentence_ptr += 1
                            self.tg_word_ptr = 0
                            self.zh_word_ptr = 0
                            asr_fixed_words.put(['', True])
                            is_sentence_end = True
                wx_text_queue.put([transcription_result, translation_result])

        callback = Callback()

        # 创建新的translator
        asr_model = config.get('asr_model', 'gummy-realtime-v1')
        console_print(f"使用ASR模型: {asr_model}")
        
        new_translator = TranslationRecognizerRealtime(
            model=asr_model,
            format='pcm',
            sample_rate=16000,
            transcription_enabled=True,
            translation_enabled=True,
            translation_target_languages=[target_language],
            semantic_punctuation_enabled=False,
            callback=callback,
        )

        console_print('重启translator...')
        new_translator.start()
        console_print(f'新translator request_id: {new_translator.get_last_request_id()}')
        
        return new_translator
        
    except Exception as e:
        console_print(f"重启translator失败: {e}")
        translator_stopped = True
        return None

def gummyAsrTask():
    global translator_stopped, need_restart_translator
    translator_stopped = False
    
    class Callback(TranslationRecognizerCallback):
        def __init__(self):
            super().__init__()
            # Initialize pointers for tracking words
            self.sentence_ptr = 0
            self.zh_word_ptr = 0
            self.tg_word_ptr = 0

        def on_open(self) -> None:
            # When the recognizer opens, set up the audio stream
            global mic
            global audio_stream
            global audio_source
            global current_system_device
            global current_system_device_name
            
            with pyaudio_lock:
                console_print('TranslationRecognizerCallback open.')
                
                if audio_source == 'microphone' or audio_source is None:
                    # 麦克风录音（包括未选择的情况默认使用麦克风）
                    mic = pyaudio.PyAudio()
                    audio_stream = mic.open(format=pyaudio.paInt16,
                                            channels=1,
                                            rate=16000,
                                            input=True)
                    console_print("已连接到麦克风")
                    
                elif audio_source == 'system':
                    # 使用FFmpeg捕获系统音频
                    console_print("尝试使用FFmpeg捕获系统音频...")
                    
                    if check_ffmpeg():
                        device_name = None
                        
                        # 优先使用保存的设备名称
                        if current_system_device_name is not None:
                            device_name = current_system_device_name
                            console_print(f"使用配置中保存的音频设备: {device_name}")
                        elif current_system_device is not None:
                            # 如果只有索引，尝试通过索引获取设备名称
                            devices = get_windows_audio_devices()
                            if current_system_device < len(devices):
                                device_name = devices[current_system_device]['name']
                                # 同时保存设备名称以备下次使用
                                current_system_device_name = device_name
                                # 自动保存到配置文件
                                save_config()
                                console_print(f"通过索引获取到音频设备: {device_name}")
                        else:
                            console_print("未配置特定的音频设备，将使用FFmpeg的自动检测")
                        
                        success = start_ffmpeg_audio_capture(device_name)
                        if success:
                            console_print("FFmpeg系统音频捕获启动成功")
                            # 不需要设置PyAudio流，因为我们使用FFmpeg
                            mic = None
                            audio_stream = None
                        else:
                            console_print("FFmpeg启动失败，回退到麦克风")
                            # 回退到麦克风
                            mic = pyaudio.PyAudio()
                            audio_stream = mic.open(format=pyaudio.paInt16,
                                                    channels=1,
                                                    rate=16000,
                                                    input=True)
                    else:
                        console_print("未找到FFmpeg，尝试虚拟音频设备...")
                        
                        # 尝试使用虚拟音频设备
                        virtual_devices = get_virtual_audio_devices()
                        device_index = None
                        
                        # 优先使用保存的设备名称查找设备
                        if current_system_device_name is not None:
                            device_index = find_audio_device_by_name(current_system_device_name)
                            if device_index is not None:
                                console_print(f"通过设备名称找到虚拟音频设备: {current_system_device_name} (索引: {device_index})")
                        
                        # 如果通过名称找不到，且有索引配置，则使用索引
                        if device_index is None and current_system_device is not None:
                            device_index = current_system_device
                            console_print(f"使用配置的设备索引: {device_index}")
                        
                        if virtual_devices and device_index is not None:
                            try:
                                mic = pyaudio.PyAudio()
                                device_info = mic.get_device_info_by_index(device_index)
                                console_print(f"尝试连接到虚拟音频设备: {device_info['name']}")
                                
                                audio_stream = mic.open(
                                    format=pyaudio.paInt16,
                                    channels=1,
                                    rate=16000,
                                    input=True,
                                    input_device_index=device_index,
                                    frames_per_buffer=3200
                                )
                                console_print(f"已连接到虚拟音频设备: {device_info['name']}")
                                
                                # 保存设备名称以备下次使用
                                if current_system_device_name != device_info['name']:
                                    current_system_device_name = device_info['name']
                                    # 自动保存到配置文件
                                    save_config()
                            except Exception as e:
                                console_print(f"连接虚拟音频设备失败: {e}")
                                # 最后回退到麦克风
                                mic = pyaudio.PyAudio()
                                audio_stream = mic.open(format=pyaudio.paInt16,
                                                        channels=1,
                                                        rate=16000,
                                                        input=True)
                                console_print("回退到麦克风录音")
                        else:
                            # 最后回退到麦克风
                            mic = pyaudio.PyAudio()
                            audio_stream = mic.open(format=pyaudio.paInt16,
                                                    channels=1,
                                                    rate=16000,
                                                    input=True)
                            console_print("回退到麦克风录音")
                else:
                    # 默认使用麦克风
                    mic = pyaudio.PyAudio()
                    audio_stream = mic.open(format=pyaudio.paInt16,
                                            channels=1,
                                            rate=16000,
                                            input=True)
                    console_print("使用默认麦克风")

        def on_close(self) -> None:
            # Clean up the audio stream and microphone
            global mic
            global audio_stream
            global translator_stopped
            console_print('TranslationRecognizerCallback close.')
            translator_stopped = True  # 标记translator已停止
            
            # 停止FFmpeg进程
            try:
                stop_ffmpeg_audio_capture()
            except Exception as e:
                console_print(f"停止FFmpeg时出错: {e}")
            
            if audio_stream is None:
                console_print('audio_stream is None')
                return
                
            try:
                if audio_stream is not None:
                    audio_stream.stop_stream()
                    audio_stream.close()
                    audio_stream = None
                if mic is not None:
                    mic.terminate()
                    mic = None
            except Exception as e:
                console_print(f"清理音频资源时出错: {e}")

        def on_event(
            self,
            request_id,
            transcription_result: TranscriptionResult,
            translation_result: TranslationResult,
            usage,
        ) -> None:
            # 添加调试信息：显示收到的事件
            event_counter = getattr(self, '_event_counter', 0)
            event_counter += 1
            setattr(self, '_event_counter', event_counter)
            
            if event_counter % 10 == 0 or event_counter <= 5:
                console_print(f"收到第 {event_counter} 个ASR事件, request_id: {request_id}")
                if transcription_result:
                    console_print(f"  转录结果: 有 {len(transcription_result.words)} 个词")
                if translation_result:
                    console_print(f"  翻译结果: 存在")
            
            new_chinese_words = ''
            new_target_language_words = ''
            is_sentence_end = False

            # Process transcription results. Only new fixed words will be pushed back.
            if transcription_result != None:
                for i, word in enumerate(transcription_result.words):
                    if word.fixed:
                        if i >= self.zh_word_ptr:
                            console_print(f'新的固定中文词: {word.text}')
                            new_chinese_words += word.text
                            self.zh_word_ptr += 1

            # Process translation results. Only new fixed words will be pushed back.
            if translation_result != None:
                target_language_translation = translation_result.get_translation(
                    'zh')
                if target_language_translation != None:
                    for i, word in enumerate(
                            target_language_translation.words):
                        if word.fixed:
                            if i >= self.tg_word_ptr:
                                console_print(f'新的固定翻译词: {word.text}')
                                asr_fixed_words.put([word.text, False])
                                new_target_language_words += word.text
                                self.tg_word_ptr += 1
                    # Check if the current sentence has ended
                    if target_language_translation.is_sentence_end:
                        console_print('target_language sentence end')
                        self.sentence_ptr += 1
                        self.tg_word_ptr = 0
                        self.zh_word_ptr = 0
                        asr_fixed_words.put(['', True])
                        is_sentence_end = True
            wx_text_queue.put([transcription_result, translation_result])

    callback = Callback()

    # 检查API状态
    check_api_status()
    
    # Set up the ASR translator
    asr_model = config.get('asr_model', 'gummy-realtime-v1')
    console_print(f"使用ASR模型: {asr_model}")
    
    # 如果API调用被禁用，给出警告
    if not enable_api_calls:
        console_print("⚠️  警告: API调用已禁用，translator将不会工作。请在设置中启用API调用。")
        return  # 直接返回，不启动translator
    
    translator = TranslationRecognizerRealtime(
        model=asr_model,
        format='pcm',
        sample_rate=16000,
        transcription_enabled=True,
        translation_enabled=True,
        translation_target_languages=[target_language],
        semantic_punctuation_enabled=False,
        callback=callback,
    )

    console_print('translator start')
    translator.start()
    console_print('translator request_id: {}'.format(translator.get_last_request_id()))

    # Open a file to save microphone audio data
    saved_mic_audio_file = open('mic_audio.pcm', 'wb')

    try:
        # Continuously read audio data from the microphone or FFmpeg
        pause_cleanup_counter = 0  # 暂停时的清理计数器
        
        while True:  # 主循环，用于处理translator重启
            data = None
            
            # 检查是否需要重启translator
            if need_restart_translator and not listening_paused:
                console_print("检测到需要重启translator...")
                translator = restart_translator(translator)
                if translator is None:
                    console_print("重启translator失败，退出")
                    break
                continue
            
            # 检查是否暂停监听
            if listening_paused:
                # 暂停时定期清理队列中的旧数据，避免积压过多
                pause_cleanup_counter += 1
                if pause_cleanup_counter >= 50:  # 每5秒清理一次队列 (50 * 0.1秒)
                    if audio_source == 'system':
                        queue_size = system_audio_queue.qsize()
                        if queue_size > 50:  # 如果队列中有超过50个数据块（约5秒的数据）
                            # 保留最新的20个数据块，丢弃其余的
                            discarded_count = 0
                            while system_audio_queue.qsize() > 20:
                                try:
                                    system_audio_queue.get_nowait()
                                    discarded_count += 1
                                except queue.Empty:
                                    break
                            if discarded_count > 0:
                                console_print(f"暂停期间清理了 {discarded_count} 个音频数据块，当前队列大小: {system_audio_queue.qsize()}")
                    pause_cleanup_counter = 0
                
                time.sleep(0.1)  # 暂停时短暂休息
                continue
            
            # 如果translator已停止且不在暂停状态，退出循环等待重启
            if translator_stopped and not listening_paused:
                console_print("translator已停止，等待重启...")
                time.sleep(0.1)
                continue
            
            if audio_source == 'system' and ffmpeg_process is not None:
                # 从FFmpeg队列读取音频数据
                try:
                    data = system_audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
            elif audio_stream:
                # 从PyAudio流读取音频数据
                try:
                    data = audio_stream.read(3200, exception_on_overflow=False)
                except Exception as e:
                    console_print(f"PyAudio读取错误: {e}")
                    break
            else:
                break
            
            if data and not listening_paused and not translator_stopped:  # 检查translator状态
                try:
                    # 添加音频音量检测
                    import struct
                    if len(data) >= 2:
                        # 计算音频音量（RMS）
                        samples = struct.unpack('<' + 'h' * (len(data) // 2), data)
                        rms = (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
                        volume_db = 20 * (rms / 32767) if rms > 0 else -100
                        
                        # 添加调试信息：显示发送的音频数据大小和音量
                        if hasattr(translator, 'send_audio_frame'):
                            sent_frame_counter = getattr(translator, '_sent_frame_counter', 0)
                            sent_frame_counter += 1
                            setattr(translator, '_sent_frame_counter', sent_frame_counter)
                            
                            # 每100帧显示一次调试信息，但如果检测到有声音则立即显示
                            if sent_frame_counter % 100 == 0 or (rms > 1000 and sent_frame_counter % 10 == 0):
                                console_print(f"已发送 {sent_frame_counter} 个音频帧，数据大小: {len(data)} 字节，音量: RMS={rms:.1f}, dB={volume_db:.1f}")
                                if rms > 1000:
                                    console_print(f"  🔊 检测到音频信号！")
                                else:
                                    console_print(f"  🔇 音频信号很微弱或为静音")
                            
                            translator.send_audio_frame(data)
                            saved_mic_audio_file.write(data)
                        else:
                            console_print("警告: translator没有send_audio_frame方法")
                    else:
                        console_print(f"警告: 音频数据太短 ({len(data)} 字节)")
                except Exception as e:
                    console_print(f"发送音频数据错误: {e}")
                    if "has stopped" in str(e):
                        console_print("检测到translator已停止")
                        translator_stopped = True
                    # 不要break，让循环继续等待重启
    except Exception as e:
        console_print(f"音频处理循环出错: {e}")
    finally:
        saved_mic_audio_file.close()
        
        # 安全地停止translator
        if not translator_stopped:
            try:
                console_print('translator stop')
                translator.stop()
                translator_stopped = True
            except Exception as e:
                console_print(f"停止translator时出错: {e}")
        else:
            console_print('translator已经停止，跳过stop调用')


# Handle the TTS task. This function will get text in asr_fixed_words in while loop and send it to TTS.
# The streaming output of TTS will be played back by the player.
def cosyvoiceTtsTask():
    global config
    
    # Replace with SiliconFlow CosyVoice API
    url = "https://api.siliconflow.cn/v1/audio/speech"
    
    # 获取API key
    api_key = config.get('siliconflow_api_key', '<your-SiliconFlow-api-key>')
    if 'SILICONFLOW_API_KEY' in os.environ:
        api_key = os.environ['SILICONFLOW_API_KEY']
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    voice = config.get('tts_voice', 'FunAudioLLM/CosyVoice2-0.5B:alex')
    buffer = ''

    # Continuously check for new words to synthesize
    while True:
        if not enable_tts:
            time.sleep(0.1)
            continue
        if not asr_fixed_words.empty():
            if not enable_tts:
                time.sleep(0.1)
                continue  # 如果 TTS 禁用，则跳过本次循环
            word, is_sentence_end = asr_fixed_words.get()
            if is_sentence_end  or ((word == '、' or word == '，' or word == '。' ) and len(buffer) > 15) :
            #if is_sentence_end  or (word == '、' or word == '，' or word == '。' ) :

                # when the sentence ends, wait for the previous sentence to finish synthesing and playing.
                #player.stop()
                #player.reset()
                #player.start()
                word += '[breath][breath][breath]'
                buffer += word
                # buffer += '[breath][breath][breath]'
                console_print('send sentence: ', buffer)
                payload = {
                    "model": "FunAudioLLM/CosyVoice2-0.5B",
                    "input": buffer,
                    "voice": voice,
                    "response_format": "pcm",
                    "sample_rate": 24000,
                    "stream": True,
                    "speed": 1.4,
                    "gain": 0
                }

                
                buffer_size = 4096  # 缓冲区大小
                try:
                    response = requests.request("POST", url, json=payload, headers=headers, stream=True)
                    if response.status_code == 200:
                        p = pyaudio.PyAudio()
                        stream = p.open(format=8, channels=1, rate=24000, output=True) #修改format参数
                        buffer2 = b""  # 初始化缓冲区
                        for chunk in response.iter_content(chunk_size=1024):
                            if chunk:
                                #console_print("len_chunk:", len(chunk))
                                buffer2 += chunk  # 将数据块添加到缓冲区
                                #console_print("len_buffer:",len(buffer2))
                                while len(buffer2) >= buffer_size:  # 当缓冲区达到一定大小时
                                    data_to_play = buffer2[:buffer_size]  # 从缓冲区中取出数据
                                    stream.write(data_to_play)  # 播放数据
                                    buffer2 = buffer2[buffer_size:]  # 更新缓冲区
                        # 播放剩余的缓冲区数据
                        if len(buffer2) > 0 :
                            stream.write(buffer2)
                        stream.stop_stream()
                        stream.close()
                        p.terminate() 
                    else:
                        console_print(f"请求失败，状态码：{response.status_code}")
                    buffer = ''
                except requests.exceptions.RequestException as e:
                    console_print(f"请求异常: {e}")
                except Exception as e :
                    console_print(f"其他异常：{e}")
            else:
                buffer += word
                #console_print('buffer: ', buffer)
                    
        else:
            # Sleep briefly if no words are available
            time.sleep(0.01)

class SettingsDialog(wx.Dialog):
    """设置对话框 - Win11风格"""
    
    def __init__(self, parent, config):
        super().__init__(parent, title="⚙️ 应用设置", size=(650, 550))
        
        self.config = config.copy()
        
        # 设置对话框样式
        self.SetBackgroundColour(Win11Theme.COLORS['background'])
        
        # 创建主面板
        panel = Win11Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 添加标题区域
        title_panel = Win11Panel(panel)
        title_panel.SetBackgroundColour(Win11Theme.COLORS['primary'])
        title_sizer = wx.BoxSizer(wx.VERTICAL)
        
        title_label = wx.StaticText(title_panel, label="应用设置")
        title_font = Win11Theme.get_font(18, wx.FONTWEIGHT_BOLD)
        title_label.SetFont(title_font)
        title_label.SetForegroundColour(wx.Colour(255, 255, 255))
        title_sizer.Add(title_label, 0, wx.ALL | wx.CENTER, 20)
        
        subtitle_label = wx.StaticText(title_panel, label="配置应用程序的API密钥、路径和音频设置")
        subtitle_font = Win11Theme.get_font(10)
        subtitle_label.SetFont(subtitle_font)
        subtitle_label.SetForegroundColour(wx.Colour(240, 240, 240))
        title_sizer.Add(subtitle_label, 0, wx.BOTTOM | wx.CENTER, 15)
        
        title_panel.SetSizer(title_sizer)
        main_sizer.Add(title_panel, 0, wx.EXPAND)
        
        # 创建笔记本控件（标签页） - Win11风格
        notebook = wx.Notebook(panel, style=wx.NB_TOP)
        notebook.SetBackgroundColour(Win11Theme.COLORS['surface'])
        notebook.SetFont(Win11Theme.get_font(10))
        
        # API设置页面
        self._create_api_panel(notebook)
        
        # 路径设置页面
        self._create_path_panel(notebook)
        
        # 音频设置页面
        self._create_audio_panel(notebook)
        
        main_sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 20)
        
        # 按钮区域
        self._create_button_panel(panel, main_sizer)
        
        panel.SetSizer(main_sizer)
        
        self.Center()
    
    def _create_api_panel(self, notebook):
        """创建API设置页面"""
        # 创建滚动面板
        api_panel = wx.ScrolledWindow(notebook, style=wx.VSCROLL)
        api_panel.SetScrollRate(0, 20)  # 设置滚动速率
        api_panel.SetBackgroundColour(Win11Theme.COLORS['surface'])
        
        api_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 添加间距
        api_sizer.AddSpacer(15)
        
        # API密钥设置组
        api_group = wx.StaticBoxSizer(wx.VERTICAL, api_panel, "🔐 API密钥配置")
        api_group.GetStaticBox().SetFont(Win11Theme.get_font(10, wx.FONTWEIGHT_BOLD))
        api_group.GetStaticBox().SetForegroundColour(Win11Theme.COLORS['primary'])
        
        # DashScope API Key
        label = wx.StaticText(api_panel, label="DashScope API Key")
        Win11Theme.apply_statictext_style(label)
        api_group.Add(label, 0, wx.ALL, 8)
        
        # DashScope API Key 输入框和按钮
        dashscope_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.dashscope_key = wx.TextCtrl(api_panel, value=self.config.get('dashscope_api_key', ''), style=wx.TE_PASSWORD)
        Win11Theme.apply_textctrl_style(self.dashscope_key)
        self.dashscope_key.SetMinSize((-1, 26))  # 调整为一个字体高度
        # 存储原始值和当前状态
        self.dashscope_hidden = True
        self.dashscope_original_value = self.config.get('dashscope_api_key', '')
        dashscope_sizer.Add(self.dashscope_key, 1, wx.RIGHT, 8)
        
        # 显示/隐藏按钮
        self.dashscope_show_btn = Win11Button(api_panel, label="👁")
        self.dashscope_show_btn.SetMinSize((26, 26))  # 调整按钮大小匹配输入框高度
        self.dashscope_show_btn.SetToolTip("显示/隐藏API Key")
        self.dashscope_show_btn.Bind(wx.EVT_BUTTON, self.on_toggle_dashscope_visibility)
        dashscope_sizer.Add(self.dashscope_show_btn, 0)
        
        api_group.Add(dashscope_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        
        # SiliconFlow API Key
        label = wx.StaticText(api_panel, label="SiliconFlow API Key (用于TTS)")
        Win11Theme.apply_statictext_style(label)
        api_group.Add(label, 0, wx.ALL, 8)
        
        # SiliconFlow API Key 输入框和按钮
        siliconflow_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.siliconflow_key = wx.TextCtrl(api_panel, value=self.config.get('siliconflow_api_key', ''), style=wx.TE_PASSWORD)
        Win11Theme.apply_textctrl_style(self.siliconflow_key)
        self.siliconflow_key.SetMinSize((-1, 26))  # 调整为一个字体高度
        # 存储原始值和当前状态
        self.siliconflow_hidden = True
        self.siliconflow_original_value = self.config.get('siliconflow_api_key', '')
        siliconflow_sizer.Add(self.siliconflow_key, 1, wx.RIGHT, 8)
        
        # 显示/隐藏按钮
        self.siliconflow_show_btn = Win11Button(api_panel, label="👁")
        self.siliconflow_show_btn.SetMinSize((26, 26))  # 调整按钮大小匹配输入框高度
        self.siliconflow_show_btn.SetToolTip("显示/隐藏API Key")
        self.siliconflow_show_btn.Bind(wx.EVT_BUTTON, self.on_toggle_siliconflow_visibility)
        siliconflow_sizer.Add(self.siliconflow_show_btn, 0)
        
        api_group.Add(siliconflow_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        
        api_sizer.Add(api_group, 0, wx.EXPAND | wx.ALL, 10)
        
        # 语音模型设置组
        model_group = wx.StaticBoxSizer(wx.VERTICAL, api_panel, "🎙️ 语音模型配置")
        model_group.GetStaticBox().SetFont(Win11Theme.get_font(10, wx.FONTWEIGHT_BOLD))
        model_group.GetStaticBox().SetForegroundColour(Win11Theme.COLORS['primary'])
        
        # TTS Voice
        label = wx.StaticText(api_panel, label="TTS 语音模型")
        Win11Theme.apply_statictext_style(label)
        model_group.Add(label, 0, wx.ALL, 8)
        
        voice_choices = [
            'FunAudioLLM/CosyVoice2-0.5B:alex',
            'FunAudioLLM/CosyVoice2-0.5B:bella',
            'FunAudioLLM/CosyVoice2-0.5B:carter',
            'FunAudioLLM/CosyVoice2-0.5B:emma'
        ]
        self.tts_voice = wx.Choice(api_panel, choices=voice_choices)
        Win11Theme.apply_choice_style(self.tts_voice)
        self.tts_voice.SetMinSize((-1, 26))  # 调整为一个字体高度
        current_voice = self.config.get('tts_voice', voice_choices[0])
        if current_voice in voice_choices:
            self.tts_voice.SetSelection(voice_choices.index(current_voice))
        else:
            self.tts_voice.SetSelection(0)
        
        # 绑定鼠标滚轮事件，防止滚动时切换声音
        self.tts_voice.Bind(wx.EVT_MOUSEWHEEL, self.on_choice_mousewheel)
        model_group.Add(self.tts_voice, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        
        # ASR Model
        label = wx.StaticText(api_panel, label="ASR 语音识别模型")
        Win11Theme.apply_statictext_style(label)
        model_group.Add(label, 0, wx.ALL, 8)
        
        model_choices = [
            'gummy-realtime-v1',
            'paraformer-realtime-v1',
            'paraformer-realtime-v2',
            'sensevoice-realtime-v1'
        ]
        self.asr_model = wx.Choice(api_panel, choices=model_choices)
        Win11Theme.apply_choice_style(self.asr_model)
        self.asr_model.SetMinSize((-1, 26))  # 调整为一个字体高度
        current_model = self.config.get('asr_model', model_choices[0])
        if current_model in model_choices:
            self.asr_model.SetSelection(model_choices.index(current_model))
            custom_model_value = ""
        else:
            self.asr_model.SetSelection(0)
            custom_model_value = current_model
        
        # 绑定鼠标滚轮事件，防止滚动时切换模型
        self.asr_model.Bind(wx.EVT_MOUSEWHEEL, self.on_choice_mousewheel)
        model_group.Add(self.asr_model, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        
        # 自定义ASR模型
        label = wx.StaticText(api_panel, label="自定义ASR模型 (可选，优先级高于上方选择)")
        Win11Theme.apply_statictext_style(label, secondary=True)
        model_group.Add(label, 0, wx.ALL, 8)
        
        self.custom_asr_model = wx.TextCtrl(api_panel, value=custom_model_value)
        Win11Theme.apply_textctrl_style(self.custom_asr_model)
        self.custom_asr_model.SetMinSize((-1, 26))  # 调整为一个字体高度
        model_group.Add(self.custom_asr_model, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        
        api_sizer.Add(model_group, 0, wx.EXPAND | wx.ALL, 10)
        
        # 添加说明文字
        help_text = wx.StaticText(api_panel, label="💡 提示：API密钥用于访问语音识别和TTS服务，请妥善保管")
        Win11Theme.apply_statictext_style(help_text, secondary=True)
        api_sizer.Add(help_text, 0, wx.ALL, 15)
        
        api_panel.SetSizer(api_sizer)
        notebook.AddPage(api_panel, "🔑 API设置")
    
    def _create_path_panel(self, notebook):
        """创建路径设置页面"""
        # 创建滚动面板
        path_panel = wx.ScrolledWindow(notebook, style=wx.VSCROLL)
        path_panel.SetScrollRate(0, 20)  # 设置滚动速率
        path_panel.SetBackgroundColour(Win11Theme.COLORS['surface'])
        
        path_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 添加间距
        path_sizer.AddSpacer(15)
        
        # FFmpeg设置组
        ffmpeg_group = wx.StaticBoxSizer(wx.VERTICAL, path_panel, "🎬 FFmpeg 配置")
        ffmpeg_group.GetStaticBox().SetFont(Win11Theme.get_font(10, wx.FONTWEIGHT_BOLD))
        ffmpeg_group.GetStaticBox().SetForegroundColour(Win11Theme.COLORS['primary'])
        
        # 说明文字
        desc_text = wx.StaticText(path_panel, label="FFmpeg用于捕获系统音频，支持从电脑播放的声音进行实时翻译")
        Win11Theme.apply_statictext_style(desc_text, secondary=True)
        ffmpeg_group.Add(desc_text, 0, wx.ALL, 10)
        
        # FFmpeg路径
        label = wx.StaticText(path_panel, label="FFmpeg 可执行文件路径")
        Win11Theme.apply_statictext_style(label)
        ffmpeg_group.Add(label, 0, wx.ALL, 8)
        
        ffmpeg_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ffmpeg_path = wx.TextCtrl(path_panel, value=self.config.get('ffmpeg_path', '') or '')
        Win11Theme.apply_textctrl_style(self.ffmpeg_path)
        self.ffmpeg_path.SetMinSize((-1, 26))  # 调整为一个字体高度
        ffmpeg_sizer.Add(self.ffmpeg_path, 1, wx.RIGHT, 10)
        
        browse_btn = Win11Button(path_panel, label="📁 浏览")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_ffmpeg)
        ffmpeg_sizer.Add(browse_btn, 0, wx.EXPAND)
        
        ffmpeg_group.Add(ffmpeg_sizer, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        
        # 按钮行
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # 自动检测按钮
        detect_btn = Win11Button(path_panel, label="🔍 自动检测", primary=True)
        detect_btn.Bind(wx.EVT_BUTTON, self.on_detect_ffmpeg)
        btn_sizer.Add(detect_btn, 0, wx.RIGHT, 10)
        
        # 清空按钮
        clear_btn = Win11Button(path_panel, label="🗑️ 清空")
        clear_btn.Bind(wx.EVT_BUTTON, lambda evt: self.ffmpeg_path.SetValue(''))
        btn_sizer.Add(clear_btn, 0)
        
        ffmpeg_group.Add(btn_sizer, 0, wx.ALL, 8)
        
        path_sizer.Add(ffmpeg_group, 0, wx.EXPAND | wx.ALL, 10)
        
        # 安装说明
        install_group = wx.StaticBoxSizer(wx.VERTICAL, path_panel, "📋 安装说明")
        install_group.GetStaticBox().SetFont(Win11Theme.get_font(10, wx.FONTWEIGHT_BOLD))
        install_group.GetStaticBox().SetForegroundColour(Win11Theme.COLORS['secondary'])
        
        install_text = wx.StaticText(path_panel, label="""如果未安装FFmpeg，请使用以下方式安装：

方法一（推荐）：使用包管理器
• winget install FFmpeg

方法二：手动下载
• 访问 https://www.gyan.dev/ffmpeg/builds/
• 下载并解压到任意目录
• 将ffmpeg.exe路径添加到上方输入框

方法三：虚拟音频设备（适用于虚拟机）
• VB-CABLE: https://vb-audio.com/Cable/""")
        Win11Theme.apply_statictext_style(install_text, secondary=True)
        install_group.Add(install_text, 0, wx.ALL, 10)
        
        path_sizer.Add(install_group, 0, wx.EXPAND | wx.ALL, 10)
        
        path_panel.SetSizer(path_sizer)
        notebook.AddPage(path_panel, "📂 路径设置")
    
    def _create_audio_panel(self, notebook):
        """创建音频设置页面"""
        # 创建滚动面板
        audio_panel = wx.ScrolledWindow(notebook, style=wx.VSCROLL)
        audio_panel.SetScrollRate(0, 20)  # 设置滚动速率
        audio_panel.SetBackgroundColour(Win11Theme.COLORS['surface'])
        
        audio_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 添加间距
        audio_sizer.AddSpacer(15)
        
        # 音频设备设置组
        device_group = wx.StaticBoxSizer(wx.VERTICAL, audio_panel, "🎤 音频设备配置")
        device_group.GetStaticBox().SetFont(Win11Theme.get_font(10, wx.FONTWEIGHT_BOLD))
        device_group.GetStaticBox().SetForegroundColour(Win11Theme.COLORS['primary'])
        
        # 音频设备选择按钮
        device_btn = Win11Button(audio_panel, label="🎵 选择音频设备", primary=True)
        device_btn.Bind(wx.EVT_BUTTON, self.on_select_audio_device)
        device_group.Add(device_btn, 0, wx.ALL | wx.EXPAND, 10)
        
        audio_sizer.Add(device_group, 0, wx.EXPAND | wx.ALL, 10)
        
        # 语言和功能设置组
        settings_group = wx.StaticBoxSizer(wx.VERTICAL, audio_panel, "🌐 语言和功能设置")
        settings_group.GetStaticBox().SetFont(Win11Theme.get_font(10, wx.FONTWEIGHT_BOLD))
        settings_group.GetStaticBox().SetForegroundColour(Win11Theme.COLORS['primary'])
        
        # 目标语言
        label = wx.StaticText(audio_panel, label="翻译目标语言")
        Win11Theme.apply_statictext_style(label)
        settings_group.Add(label, 0, wx.ALL, 8)
        
        lang_choices = ["zh", "en", "ja", "ko", "fr", "es", "de", "ru"]
        lang_names = {"zh": "中文", "en": "English", "ja": "日本语", "ko": "한국어", 
                     "fr": "Français", "es": "Español", "de": "Deutsch", "ru": "Русский"}
        lang_display = [f"{code} ({lang_names.get(code, code)})" for code in lang_choices]
        
        self.target_language = wx.Choice(audio_panel, choices=lang_display)
        Win11Theme.apply_choice_style(self.target_language)
        self.target_language.SetMinSize((-1, 26))  # 调整为一个字体高度
        target_lang = self.config.get('target_language', 'zh')
        if target_lang in lang_choices:
            self.target_language.SetSelection(lang_choices.index(target_lang))
        else:
            self.target_language.SetSelection(0)
        
        # 绑定鼠标滚轮事件，防止滚动时切换语言
        self.target_language.Bind(wx.EVT_MOUSEWHEEL, self.on_choice_mousewheel)
        settings_group.Add(self.target_language, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 8)
        
        # 功能开关区域
        switches_panel = Win11Panel(audio_panel)
        switches_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # TTS启用
        self.enable_tts = wx.CheckBox(switches_panel, label="🔊 启用TTS语音播报")
        self.enable_tts.SetValue(self.config.get('enable_tts', False))
        self.enable_tts.SetFont(Win11Theme.get_font(10))
        self.enable_tts.SetForegroundColour(Win11Theme.COLORS['text_primary'])
        switches_sizer.Add(self.enable_tts, 0, wx.ALL, 8)
        
        # 控制台输出开关
        self.enable_console_output = wx.CheckBox(switches_panel, label="📝 启用控制台输出（调试信息）")
        self.enable_console_output.SetValue(self.config.get('enable_console_output', True))
        self.enable_console_output.SetFont(Win11Theme.get_font(10))
        self.enable_console_output.SetForegroundColour(Win11Theme.COLORS['text_primary'])
        switches_sizer.Add(self.enable_console_output, 0, wx.ALL, 8)
        
        switches_panel.SetSizer(switches_sizer)
        settings_group.Add(switches_panel, 0, wx.EXPAND | wx.ALL, 5)
        
        audio_sizer.Add(settings_group, 0, wx.EXPAND | wx.ALL, 10)
        
        # 使用说明
        usage_group = wx.StaticBoxSizer(wx.VERTICAL, audio_panel, "ℹ️ 使用说明")
        usage_group.GetStaticBox().SetFont(Win11Theme.get_font(10, wx.FONTWEIGHT_BOLD))
        usage_group.GetStaticBox().SetForegroundColour(Win11Theme.COLORS['secondary'])
        
        usage_text = wx.StaticText(audio_panel, label="""音频设备选择说明：
• 麦克风：捕获麦克风输入，适合直接语音翻译
• 系统音频：捕获电脑播放的音频，适合翻译视频、音乐等

TTS语音播报：
• 启用后会朗读翻译结果，需要SiliconFlow API Key

控制台输出：
• 启用后在控制台显示详细的调试信息和运行状态""")
        Win11Theme.apply_statictext_style(usage_text, secondary=True)
        usage_group.Add(usage_text, 0, wx.ALL, 10)
        
        audio_sizer.Add(usage_group, 0, wx.EXPAND | wx.ALL, 10)
        
        audio_panel.SetSizer(audio_sizer)
        notebook.AddPage(audio_panel, "🎵 音频设置")
    
    def _create_button_panel(self, parent, main_sizer):
        """创建按钮面板"""
        # 创建分隔线
        separator_panel = Win11Panel(parent)
        separator_panel.SetBackgroundColour(Win11Theme.COLORS['border'])
        separator_panel.SetMinSize((-1, 1))
        main_sizer.Add(separator_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT, 20)
        
        # 按钮区域
        btn_panel = Win11Panel(parent)
        btn_panel.SetBackgroundColour(Win11Theme.COLORS['surface'])
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        # 测试按钮
        test_btn = Win11Button(btn_panel, label="🧪 测试配置")
        test_btn.SetToolTip("测试当前配置是否正确")
        test_btn.Bind(wx.EVT_BUTTON, self.on_test_settings)
        btn_sizer.Add(test_btn, 0, wx.ALL, 8)
        
        btn_sizer.AddStretchSpacer()
        
        # 取消按钮
        cancel_btn = Win11Button(btn_panel, wx.ID_CANCEL, "取消")
        cancel_btn.SetMinSize((100, 40))
        btn_sizer.Add(cancel_btn, 0, wx.ALL, 8)
        
        # 确定按钮
        ok_btn = Win11Button(btn_panel, wx.ID_OK, "确定", primary=True)
        ok_btn.SetMinSize((100, 40))
        ok_btn.SetDefault()  # 设置为默认按钮，可以用Enter键触发
        # 绑定确定按钮的事件处理
        ok_btn.Bind(wx.EVT_BUTTON, self.on_ok)
        btn_sizer.Add(ok_btn, 0, wx.ALL, 8)
        
        btn_panel.SetSizer(btn_sizer)
        main_sizer.Add(btn_panel, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 15)
    
    def on_ok(self, event):
        """处理确定按钮点击"""
        try:
            # 获取配置并验证
            new_config = self.get_config()
            
            # 基本验证
            if not new_config.get('dashscope_api_key') or new_config.get('dashscope_api_key') == '<your-dashscope-api-key>':
                result = wx.MessageBox("DashScope API Key未设置，某些功能可能无法正常使用。\n\n是否继续保存？", 
                                     "警告", wx.YES_NO | wx.ICON_WARNING)
                if result == wx.NO:
                    return
            
            # 更新配置
            self.config.update(new_config)
            
            # 设置对话框结果并关闭
            self.EndModal(wx.ID_OK)
            
        except Exception as e:
            wx.MessageBox(f"保存配置时出错：{e}", "错误", wx.OK | wx.ICON_ERROR)
    
    def on_browse_ffmpeg(self, event):
        """浏览FFmpeg文件"""
        wildcard = "可执行文件 (*.exe)|*.exe|所有文件 (*.*)|*.*"
        dialog = wx.FileDialog(self, "选择FFmpeg可执行文件", 
                              wildcard=wildcard, style=wx.FD_OPEN)
        
        if dialog.ShowModal() == wx.ID_OK:
            self.ffmpeg_path.SetValue(dialog.GetPath())
        
        dialog.Destroy()
    
    def on_detect_ffmpeg(self, event):
        """自动检测FFmpeg"""
        # 临时保存当前配置
        old_ffmpeg_path = self.config.get('ffmpeg_path')
        
        # 清除配置中的FFmpeg路径以触发自动检测
        self.config['ffmpeg_path'] = None
        
        if check_ffmpeg():
            global ffmpeg_path
            self.ffmpeg_path.SetValue(ffmpeg_path or '')
            wx.MessageBox(f"检测到FFmpeg: {ffmpeg_path}", "检测成功", wx.OK | wx.ICON_INFORMATION)
        else:
            wx.MessageBox("未检测到FFmpeg，请手动指定路径", "检测失败", wx.OK | wx.ICON_WARNING)
        
        # 恢复原配置
        self.config['ffmpeg_path'] = old_ffmpeg_path
    
    def on_test_settings(self, event):
        """测试设置"""
        # 获取当前设置
        test_config = self.get_config()
        
        # 测试FFmpeg
        if test_config.get('ffmpeg_path'):
            if os.path.exists(test_config['ffmpeg_path']):
                try:
                    result = subprocess.run([test_config['ffmpeg_path'], '-version'], 
                                          capture_output=True, text=True, timeout=5)
                    if result.returncode == 0:
                        ffmpeg_status = "✅ FFmpeg测试成功"
                    else:
                        ffmpeg_status = "❌ FFmpeg无法运行"
                except Exception as e:
                    ffmpeg_status = f"❌ FFmpeg测试失败: {e}"
            else:
                ffmpeg_status = "❌ FFmpeg路径不存在"
        else:
            ffmpeg_status = "⚠️ 未设置FFmpeg路径"
        
        # 测试API Key（简单验证格式）
        dashscope_key = test_config.get('dashscope_api_key', '')
        if dashscope_key and dashscope_key != '<your-dashscope-api-key>':
            dashscope_status = "✅ DashScope API Key已设置"
        else:
            dashscope_status = "❌ DashScope API Key未设置"
        
        siliconflow_key = test_config.get('siliconflow_api_key', '')
        if siliconflow_key and siliconflow_key != '<your-SiliconFlow-api-key>':
            siliconflow_status = "✅ SiliconFlow API Key已设置"
        else:
            siliconflow_status = "❌ SiliconFlow API Key未设置"
        
        # 显示测试结果
        message = f"设置测试结果:\n\n{ffmpeg_status}\n{dashscope_status}\n{siliconflow_status}"
        wx.MessageBox(message, "设置测试", wx.OK | wx.ICON_INFORMATION)
    
    def on_toggle_dashscope_visibility(self, event):
        """切换DashScope API Key的显示/隐藏"""
        try:
            current_value = self.dashscope_key.GetValue()
            parent = self.dashscope_key.GetParent()
            
            # 获取父sizer和当前控件的位置
            parent_sizer = None
            current_sizer = None
            item_index = -1
            
            # 查找包含此控件的sizer
            def find_sizer_and_index(sizer, target_window):
                for i in range(sizer.GetItemCount()):
                    item = sizer.GetItem(i)
                    if item.IsWindow() and item.GetWindow() == target_window:
                        return sizer, i
                    elif item.IsSizer():
                        result = find_sizer_and_index(item.GetSizer(), target_window)
                        if result[0] is not None:
                            return result
                return None, -1
            
            # 从父窗口的主sizer开始查找
            main_sizer = parent.GetSizer()
            current_sizer, item_index = find_sizer_and_index(main_sizer, self.dashscope_key)
            
            if current_sizer and item_index >= 0:
                # 移除旧控件
                current_sizer.Detach(self.dashscope_key)
                self.dashscope_key.Destroy()
                
                # 创建新控件
                if self.dashscope_hidden:
                    # 创建显示状态的控件
                    self.dashscope_key = wx.TextCtrl(parent, value=current_value)
                    self.dashscope_hidden = False
                    self.dashscope_show_btn.SetLabel("🙈")
                else:
                    # 创建隐藏状态的控件
                    self.dashscope_key = wx.TextCtrl(parent, value=current_value, style=wx.TE_PASSWORD)
                    self.dashscope_hidden = True
                    self.dashscope_show_btn.SetLabel("👁")
                
                # 应用样式
                Win11Theme.apply_textctrl_style(self.dashscope_key)
                self.dashscope_key.SetMinSize((-1, 26))  # 调整为一个字体高度
                
                # 重新插入到原位置
                current_sizer.Insert(item_index, self.dashscope_key, 1, wx.RIGHT, 8)
                
                # 重新布局
                parent.Layout()
                self.Layout()
                self.Refresh()
                
        except Exception as e:
            print(f"切换DashScope API Key显示状态失败: {e}")
            import traceback
            traceback.print_exc()
    
    def on_toggle_siliconflow_visibility(self, event):
        """切换SiliconFlow API Key的显示/隐藏"""
        try:
            current_value = self.siliconflow_key.GetValue()
            parent = self.siliconflow_key.GetParent()
            
            # 获取父sizer和当前控件的位置
            parent_sizer = None
            current_sizer = None
            item_index = -1
            
            # 查找包含此控件的sizer
            def find_sizer_and_index(sizer, target_window):
                for i in range(sizer.GetItemCount()):
                    item = sizer.GetItem(i)
                    if item.IsWindow() and item.GetWindow() == target_window:
                        return sizer, i
                    elif item.IsSizer():
                        result = find_sizer_and_index(item.GetSizer(), target_window)
                        if result[0] is not None:
                            return result
                return None, -1
            
            # 从父窗口的主sizer开始查找
            main_sizer = parent.GetSizer()
            current_sizer, item_index = find_sizer_and_index(main_sizer, self.siliconflow_key)
            
            if current_sizer and item_index >= 0:
                # 移除旧控件
                current_sizer.Detach(self.siliconflow_key)
                self.siliconflow_key.Destroy()
                
                # 创建新控件
                if self.siliconflow_hidden:
                    # 创建显示状态的控件
                    self.siliconflow_key = wx.TextCtrl(parent, value=current_value)
                    self.siliconflow_hidden = False
                    self.siliconflow_show_btn.SetLabel("🙈")
                else:
                    # 创建隐藏状态的控件
                    self.siliconflow_key = wx.TextCtrl(parent, value=current_value, style=wx.TE_PASSWORD)
                    self.siliconflow_hidden = True
                    self.siliconflow_show_btn.SetLabel("👁")
                
                # 应用样式
                Win11Theme.apply_textctrl_style(self.siliconflow_key)
                self.siliconflow_key.SetMinSize((-1, 26))  # 调整为一个字体高度
                
                # 重新插入到原位置
                current_sizer.Insert(item_index, self.siliconflow_key, 1, wx.RIGHT, 8)
                
                # 重新布局
                parent.Layout()
                self.Layout()
                self.Refresh()
                
        except Exception as e:
            print(f"切换SiliconFlow API Key显示状态失败: {e}")
            import traceback
            traceback.print_exc()
    
    def on_choice_mousewheel(self, event):
        """处理Choice控件的滚轮事件，防止意外切换选项"""
        # 检查鼠标是否在Choice控件内
        control = event.GetEventObject()
        mouse_pos = event.GetPosition()
        control_rect = control.GetRect()
        
        # 如果鼠标在控件外，将事件传递给父窗口进行滚动
        if not control_rect.Contains(mouse_pos):
            parent = control.GetParent()
            if parent:
                event.SetEventObject(parent)
                parent.GetEventHandler().ProcessEvent(event)
        # 如果鼠标在控件内，则忽略滚轮事件，防止意外切换选项
        # （用户需要点击控件后用方向键或鼠标点击来选择）

    def on_select_audio_device(self, event):
        """选择音频设备的对话框"""
        try:
            # 获取主窗口实例（如果存在）
            main_window = None
            for window in wx.GetTopLevelWindows():
                if hasattr(window, 'show_audio_device_dialog'):
                    main_window = window
                    break
            
            if main_window:
                # 直接调用主窗口的音频设备选择对话框
                main_window.show_audio_device_dialog()
                wx.MessageBox("音频设备设置已完成！", "设置成功", wx.OK | wx.ICON_INFORMATION)
            else:
                wx.MessageBox("找不到主窗口，无法打开音频设备选择对话框", "错误", wx.OK | wx.ICON_ERROR)
                
        except Exception as e:
            wx.MessageBox(f"选择音频设备时出错: {e}", "错误", wx.OK | wx.ICON_ERROR)
    
    def get_config(self):
        """获取用户设置的配置"""
        config = {}
        
        # API设置 - 直接从控件获取值
        config['dashscope_api_key'] = self.dashscope_key.GetValue().strip()
        config['siliconflow_api_key'] = self.siliconflow_key.GetValue().strip()
        config['tts_voice'] = self.tts_voice.GetStringSelection()
        
        # ASR模型设置
        custom_model = self.custom_asr_model.GetValue().strip()
        if custom_model:
            config['asr_model'] = custom_model
        else:
            config['asr_model'] = self.asr_model.GetStringSelection()
        
        # 路径设置
        ffmpeg_path = self.ffmpeg_path.GetValue().strip()
        config['ffmpeg_path'] = ffmpeg_path if ffmpeg_path else None
        
        # 音频设置
        config['audio_source'] = self.config.get('audio_source', 'microphone')  # 使用保存的配置
        
        # 获取目标语言（从显示格式中提取语言代码）
        lang_selection = self.target_language.GetSelection()
        lang_choices = ["zh", "en", "ja", "ko", "fr", "es", "de", "ru"]
        if 0 <= lang_selection < len(lang_choices):
            config['target_language'] = lang_choices[lang_selection]
        else:
            config['target_language'] = 'zh'  # 默认中文
            
        config['enable_tts'] = self.enable_tts.GetValue()
        config['enable_console_output'] = self.enable_console_output.GetValue()
        
        # 音频设备设置（保留现有配置）
        config['current_system_device'] = self.config.get('current_system_device', None)
        config['current_system_device_name'] = self.config.get('current_system_device_name', None)
        
        return config

class FloatingSubtitleWindow(wx.Frame):
    def __init__(self):
        # 初始化背景相关属性
        self.is_dark_mode = False  # 初始为亮色模式
        self.bg_alpha = 200  # Win11风格透明度
        self.text_color = Win11Theme.COLORS['text_primary']  # 使用Win11主题文字颜色
        # 根据初始模式设置背景颜色
        self.bg_color = Win11Theme.COLORS['surface'] if not self.is_dark_mode else wx.Colour(45, 45, 45)
        
        # 设置窗口样式为Win11风格
        style = wx.STAY_ON_TOP | wx.RESIZE_BORDER | wx.DEFAULT_FRAME_STYLE
        
        super().__init__(
            parent=None,
            title='实时翻译字幕',
            style=style
        )
        
        # 设置窗口图标（如果有的话）
        # self.SetIcon(wx.Icon('icon.png', wx.BITMAP_TYPE_PNG))
        
        # 属性初始化
        self.transparency = 255
        self.font_size = 14
        self.font_family = wx.FONTFAMILY_DEFAULT
        self.text_color = Win11Theme.COLORS['text_primary']
        self.MAX_CHARS = 1000

        self.SetSize((950, 120))  # 略微增大窗口以适应Win11风格
        
        # 设置窗口背景色为Win11风格
        self.SetBackgroundColour(Win11Theme.COLORS['background'])
    
        # 添加文本面板透明度属性
        self.text_alpha = 180  # Win11风格透明度
        self.background_color = Win11Theme.COLORS['surface']
        
        # 初始化文本面板背景透明度
        self.panel_alpha = 220  # Win11风格透明度
        
        if wx.Platform == "__WXMSW__":
            # 启用窗口透明
            hwnd = self.GetHandle()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
            
            # 设置整个窗口的初始透明度
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, self.panel_alpha, 0x02)
        
        # 创建主面板 - Win11风格
        self.panel = Win11Panel(self, style=wx.BORDER_NONE)
        self.panel.SetBackgroundColour(Win11Theme.COLORS['surface'])
        
        # 初始化布局 - 更大的间距
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建文本面板
        self.chinese_panel = self.create_language_panel("📝 源语言", "chinese_text_box")
        self.target_panel = self.create_language_panel("🌍 目标语言", "target_language_text_box")
        
        # 添加到布局 - 调整比例：上面识别栏固定高度，下面翻译栏可扩展
        self.main_sizer.Add(self.chinese_panel, 0, wx.EXPAND | wx.ALL, 2)  # 固定高度，减少边距
        self.main_sizer.Add(self.target_panel, 1, wx.EXPAND | wx.ALL, 2)  # 可扩展，减少边距，占用剩余空间
        
        # 创建状态栏 - Win11风格，适中高度
        self.status_bar = self.CreateStatusBar(1)
        self.status_bar.SetFont(Win11Theme.get_font(9))  # 适中字体大小
        self.status_bar.SetForegroundColour(Win11Theme.COLORS['text_secondary'])
        self.status_bar.SetBackgroundColour(Win11Theme.COLORS['surface_variant'])
        # 进一步降低状态栏高度到更紧凑的尺寸
        self.status_bar.SetMinHeight(18)
        self.update_status_bar()
        # 默认显示状态栏
        self.status_bar.Show(True)
        
        self.panel.SetSizer(self.main_sizer)
        
        # 初始化缓冲区
        self.chinese_buffer = ''
        self.chinese_text_buffer = [['', '']]  # 源语言文本缓冲区
        self.target_language_text_buffer = [['', '']]  # 目标语言文本缓冲区

        # 设置定时器用于更新文本
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_timer, self.timer)
        self.timer.Start(100)  # 每100毫秒更新一次

        # 绑定快捷键事件
        self.Bind(wx.EVT_CHAR_HOOK, self.on_key_press)

        # 添加拖拽相关属性
        self.dragging = False
        self.drag_start_pos = None

        self.has_titlebar = True  # 初始状态为显示标题栏

        # 设置最小窗口大小
        self.SetMinSize((300, 100))

        # 创建定时器，每100毫秒检查一次鼠标位置
        self.mouse_check_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.check_mouse_position, self.mouse_check_timer)
        self.mouse_check_timer.Start(100)  # 100毫秒间隔

        # 初始化时立即检查鼠标位置来设置正确的状态
        wx.CallAfter(self.initial_mouse_check)

        self.Center()
        self.Show()

    def initial_mouse_check(self):
        """初始化时检查鼠标位置"""
        x, y = wx.GetMousePosition()
        rect = self.GetScreenRect()
        if not rect.Contains(wx.Point(x, y)):
            # 鼠标不在窗口内，隐藏标题栏和状态栏
            self.SetWindowStyleFlag(self.GetWindowStyleFlag() & ~wx.CAPTION)
            self.has_titlebar = False
            self.status_bar.Show(False)
            self.SendSizeEvent()
            self.Layout()
            self.Refresh()


    def check_mouse_position(self, event):
        """定时检查鼠标位置"""
        x, y = wx.GetMousePosition()  # 获取鼠标全局坐标
        rect = self.GetScreenRect()  # 获取窗口全局坐标的矩形区域
        if not rect.Contains(wx.Point(x, y)):
            if self.has_titlebar:
                #console_print("Mouse left the window (timer)")
                self.SetWindowStyleFlag(self.GetWindowStyleFlag() & ~wx.CAPTION)
                self.has_titlebar = False
                # 隐藏状态栏
                self.status_bar.Show(False)
                # 强制重新布局以完全隐藏状态栏
                self.SendSizeEvent()
                self.Layout()
                self.Refresh()
        else:
            if not self.has_titlebar:
                #console_print("Mouse in the window (timer)")
                self.SetWindowStyleFlag(self.GetWindowStyleFlag() | wx.CAPTION)
                self.has_titlebar = True
                # 显示状态栏并确保恢复正常高度
                self.status_bar.Show(True)
                # 重置状态栏的最小高度，确保可以正常显示
                self.status_bar.SetMinHeight(18)
                # 强制重新布局以显示状态栏
                self.SendSizeEvent()
                self.Layout()
                self.Refresh()
    
    on_mouse_enter = None  # 移除鼠标进入事件处理
    show_titlebar = None  # 移除显示标题栏函数
    on_mouse_leave = None  # 移除鼠标离开事件处理
    hide_titlebar = None  # 移除隐藏标题栏函数

    def on_timer(self, event):
        """处理定时器事件，从队列中获取并更新文本"""
        try:
            while not wx_text_queue.empty():
                transcription_result, translation_result = wx_text_queue.get()
                self.update_text(transcription_result, translation_result)
        except Exception as e:
            console_print(f"定时器更新出错: {e}")
        event.Skip()

    def create_language_panel(self, title, text_box_name):
        """创建Win11风格的语言面板"""
        panel = Win11Panel(self.panel)

        # 根据面板类型决定样式和功能
        is_chinese_panel = text_box_name == "chinese_text_box"
        
        if is_chinese_panel:
            # 源语言面板：使用RichTextCtrl实现单行显示（与翻译区相同逻辑）
            text_box = rt.RichTextCtrl(
                panel,
                style=wx.NO_BORDER | rt.RE_READONLY | rt.RE_MULTILINE
            )
            text_box.SetMinSize((300, 35))  # 增加高度确保文字不被遮挡
            
            # 使用Win11风格字体
            font = Win11Theme.get_font(self.font_size, wx.FONTWEIGHT_BOLD)  # 使用粗体
            text_box.SetFont(font)
            
            # 设置Win11风格背景色
            text_box.SetBackgroundColour(Win11Theme.COLORS['surface'])
            text_box.SetMargins(8, 4)  # Win11风格边距
            
            # 设置Win11风格文字颜色和样式
            attr = rt.RichTextAttr()
            attr.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)  # 左对齐，与翻译区一致
            attr.SetLineSpacing(16)  # Win11风格行间距
            attr.SetTextColour(self.text_color)
            text_box.SetDefaultStyle(attr)
            
        else:
            # 目标语言面板：使用RichTextCtrl支持多行和格式化
            text_box = rt.RichTextCtrl(
                panel,
                style=wx.NO_BORDER | rt.RE_READONLY | rt.RE_MULTILINE
            )
            text_box.SetMinSize((300, 60))  # 更大的高度以显示更多内容
            
            # 使用Win11风格字体
            font = Win11Theme.get_font(self.font_size, wx.FONTWEIGHT_NORMAL)
            text_box.SetFont(font)
            
            # 设置Win11风格背景色
            text_box.SetBackgroundColour(Win11Theme.COLORS['surface'])
            text_box.SetMargins(8, 4)  # Win11风格边距
            
            # 设置Win11风格文字颜色和样式
            attr = rt.RichTextAttr()
            attr.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)  # 左对齐
            attr.SetLineSpacing(16)  # Win11风格行间距
            attr.SetTextColour(self.text_color)
            text_box.SetDefaultStyle(attr)
        
        # 对于所有面板，尝试隐藏滚动条
        try:
            if hasattr(text_box, 'ShowScrollbars'):
                text_box.ShowScrollbars(wx.SHOW_SB_NEVER, wx.SHOW_SB_NEVER)
            elif hasattr(text_box, 'SetScrollbar'):
                text_box.SetScrollbar(wx.VERTICAL, 0, 0, 0)
                text_box.SetScrollbar(wx.HORIZONTAL, 0, 0, 0)
        except:
            pass

        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(text_box, 1, wx.EXPAND | wx.ALL, 1)
        panel.SetSizer(sizer)

        setattr(self, text_box_name, text_box)

        return panel

    def set_panel_alpha(self, alpha):
        """设置文本面板背景透明度"""
        try:
            self.bg_alpha = alpha
            # 根据颜色模式计算背景亮度和颜色
            # 统一亮度计算逻辑，两种模式都基于alpha值
            brightness = int(1*(255 - alpha))  # 基础亮度值
            self.bg_color = wx.Colour(brightness, brightness, brightness)

            self.chinese_text_box.Freeze()
            self.target_language_text_box.Freeze()

            # 更新背景色
            self.chinese_text_box.SetBackgroundColour(self.bg_color)
            self.target_language_text_box.SetBackgroundColour(self.bg_color)
            self.panel.SetBackgroundColour(self.bg_color)
            self.SetBackgroundColour(self.bg_color)

            # 确保文字颜色不变
            # attr = wx.TextAttr()
            # attr.SetTextColour(self.text_color)
            # self.chinese_text_box.SetDefaultStyle(attr)
            # self.target_language_text_box.SetDefaultStyle(attr)

            # 刷新显示
            self.chinese_text_box.Refresh()
            self.target_language_text_box.Refresh()
            self.Refresh()

            self.chinese_text_box.Thaw()
            self.target_language_text_box.Thaw()

            console_print(f"背景透明度已更新: alpha={alpha}, 亮度值={brightness}")
        except Exception as e:
            console_print(f"设置背景透明度时出错: {e}")
            if self.chinese_text_box.IsFrozen():
                self.chinese_text_box.Thaw()
            if self.target_language_text_box.IsFrozen():
                self.target_language_text_box.Thaw()

    def update_status_bar(self):
        """更新状态栏信息"""
        global audio_source, enable_tts, listening_paused, config, ffmpeg_path
        
        # 音频源状态
        audio_status = "🎤 麦克风" if audio_source == 'microphone' else "🔊 系统音频"
        
        # TTS状态
        tts_status = "🔊 TTS开" if enable_tts else "🔇 TTS关"
        
        # 监听状态
        listening_status = "⏸️ 已暂停" if listening_paused else "🎧 监听中"
        
        # FFmpeg状态
        ffmpeg_status = "FFmpeg✅" if check_ffmpeg() else "FFmpeg❌"
        
        status_text = f"{audio_status} | {tts_status} | {listening_status} | {ffmpeg_status}"
        self.status_bar.SetStatusText(status_text, 0)

    def show_settings_dialog(self):
        """显示设置对话框"""
        global config, ffmpeg_path, audio_source, target_language, current_system_device, enable_tts, enable_api_calls, enable_console_output
        
        dialog = SettingsDialog(self, config)
        if dialog.ShowModal() == wx.ID_OK:
            # 获取更新后的配置
            new_config = dialog.get_config()
            config.update(new_config)
            
            # 同步更新全局变量
            ffmpeg_path = config.get('ffmpeg_path', None)
            audio_source = config.get('audio_source', 'system')
            target_language = config.get('target_language', 'zh')
            current_system_device = config.get('current_system_device', None)
            enable_tts = config.get('enable_tts', False)
            enable_api_calls = config.get('api', {}).get('enabled', True)
            enable_console_output = config.get('enable_console_output', True)
            
            # 保存配置
            save_config()
            
            # 更新状态栏
            self.update_status_bar()
            
            wx.MessageBox(
                "设置已保存！\n部分设置需要重启程序才能生效。",
                "设置保存成功",
                wx.OK | wx.ICON_INFORMATION
            )
        
        dialog.Destroy()

    def toggle_listening(self):
        """切换监听暂停/恢复状态"""
        global listening_paused, translator_stopped, need_restart_translator
        
        if listening_paused:
            # 从暂停状态恢复
            if translator_stopped:
                # 如果translator已停止，标记需要重启
                need_restart_translator = True
                console_print("音频监听已恢复 - translator将重启")
            else:
                console_print("音频监听已恢复")
            listening_paused = False
        else:
            # 暂停监听
            listening_paused = True
            console_print("音频监听已暂停")
        
        # 更新状态栏
        self.update_status_bar()

    def on_key_press(self, event):
        key = event.GetKeyCode()
        if event.AltDown():
            if key == ord('T') or key == ord('t'):  # 检测Alt+T
                self.toggle_color_mode()
                return
            if key == ord('A') or key == ord('a'):  # 检测Alt+A - 切换音频源
                self.toggle_audio_source()
                return
            if key == ord('D') or key == ord('d'):  # 检测Alt+D - 选择系统音频设备
                self.show_audio_device_dialog()
                return
            if key == ord('P') or key == ord('p'):  # 检测Alt+P - 暂停/恢复监听
                self.toggle_listening()
                return
            if key == ord('S') or key == ord('s'):  # 检测 Alt+S - 打开设置
                self.show_settings_dialog()
                return
            if key == wx.WXK_UP or key == wx.WXK_DOWN:
                new_alpha = self.bg_alpha
                if key == wx.WXK_UP:
                    new_alpha = min(255, self.bg_alpha + 20)
                else:
                    new_alpha = max(0, self.bg_alpha - 20)

                self.set_panel_alpha(new_alpha)
                return
        if event.ControlDown():
            if key == ord('H') or key == ord('h'):  # 检测Ctrl+H
                self.on_toggle_titlebar()
                return
        event.Skip()

    def on_toggle_titlebar(self):
        """切换标题栏的显示和隐藏"""
        if self.has_titlebar:
            self.SetWindowStyle(self.GetWindowStyle() & ~wx.CAPTION)
            self.has_titlebar = False
            # 隐藏状态栏
            self.status_bar.Show(False)
            # 强制重新布局以完全隐藏状态栏
            self.SendSizeEvent()
            self.Layout()
            self.Refresh()
        else:
            self.SetWindowStyle(self.GetWindowStyle() | wx.CAPTION)
            self.has_titlebar = True
            # 显示状态栏并确保恢复正常高度
            self.status_bar.Show(True)
            # 重置状态栏的最小高度，确保可以正常显示
            self.status_bar.SetMinHeight(18)
            # 强制重新布局以显示状态栏
            self.SendSizeEvent()
            self.Layout()
            self.Refresh()

    def toggle_audio_source(self):
        """切换音频源：麦克风 <-> 系统音频"""
        global audio_source
        
        if audio_source == 'microphone' or audio_source is None:
            audio_source = 'system'
            source_name = "系统音频"
        else:
            audio_source = 'microphone'
            source_name = "麦克风录音"
        
        console_print(f"已切换到: {source_name}")
        
        # 更新状态栏
        self.update_status_bar()
        
        # 保存配置
        save_config()
        
        # 检查FFmpeg状态
        ffmpeg_status = "可用" if check_ffmpeg() else "不可用"
        
        # 显示状态提示
        message = f"音频源已切换到: {source_name}\n\n"
        
        if audio_source == 'system':
            message += f"系统音频捕获方式:\n"
            message += f"• FFmpeg直接捕获: {ffmpeg_status}\n"
            message += f"• 虚拟音频设备: 需要VB-CABLE等\n"
            message += f"• 立体声混音: 需要手动启用\n\n"
            
            if not check_ffmpeg():
                message += "⚠️ 建议安装FFmpeg以获得最佳体验\n\n"
        
        message += f"快捷键:\n"
        message += f"Alt+A: 切换音频源\n"
        message += f"Alt+D: 选择系统音频设备\n"
        message += f"Alt+P: 暂停/恢复监听\n"
        message += f"Alt+S: 打开设置\n"
        message += f"Alt+T: 切换颜色模式\n\n"
        message += f"注意: 需要重启程序以应用新的音频源设置"
        
        wx.MessageBox(message, "音频源切换", wx.OK | wx.ICON_INFORMATION)

    def show_audio_device_dialog(self):
        """显示音频设备选择对话框"""
        global current_system_device
        
        # 检查FFmpeg是否可用
        ffmpeg_available = check_ffmpeg()
        
        # 获取不同类型的音频设备
        virtual_devices = get_virtual_audio_devices()
        all_devices = get_system_audio_devices()
        
        if not all_devices and not ffmpeg_available:
            wx.MessageBox("未检测到可用的音频设备，且FFmpeg不可用", "错误", wx.OK | wx.ICON_ERROR)
            return
        
        # 构建设备列表
        device_list = []
        device_indices = []
        device_types = []  # 记录设备类型
        
        if ffmpeg_available:
            device_list.append("=== FFmpeg系统音频捕获（推荐） ===")
            device_indices.append(None)
            device_types.append('header')
            
            device_list.append("🎵 系统音频输出（自动检测）")
            device_indices.append(-1)  # 特殊索引表示使用FFmpeg默认
            device_types.append('ffmpeg')
            
            # 添加FFmpeg检测到的设备
            ffmpeg_devices = get_windows_audio_devices()
            for i, dev in enumerate(ffmpeg_devices):
                device_list.append(f"🎵 {dev['name']} (FFmpeg)")
                device_indices.append(i)
                device_types.append('ffmpeg')
        
        if virtual_devices:
            device_list.append("=== 虚拟音频设备 ===")
            device_indices.append(None)
            device_types.append('header')
            
            for dev in virtual_devices:
                device_list.append(f"🔌 {dev['name']} (索引: {dev['index']})")
                device_indices.append(dev['index'])
                device_types.append('virtual')
        
        device_list.append("=== 所有输入设备 ===")
        device_indices.append(None)
        device_types.append('header')
        
        for dev in all_devices:
            if dev['type'] == 'input':
                device_list.append(f"🎤 {dev['name']} (索引: {dev['index']})")
                device_indices.append(dev['index'])
                device_types.append('regular')
        
        # 创建设备选择对话框
        dialog = wx.SingleChoiceDialog(
            self,
            "请选择要监听的音频设备:\n\n"
            "🎵 FFmpeg系统音频 - 直接捕获系统输出（推荐）\n"
            "🔌 虚拟音频设备 - VB-CABLE等虚拟线缆\n"
            "🎤 普通输入设备 - 麦克风等\n\n"
            f"FFmpeg状态: {'✅ 可用' if ffmpeg_available else '❌ 不可用'}",
            "选择音频设备",
            device_list
        )
        
        if dialog.ShowModal() == wx.ID_OK:
            selection = dialog.GetSelection()
            selected_index = device_indices[selection]
            selected_type = device_types[selection]
            
            if selected_index is not None and selected_type != 'header':
                current_system_device = selected_index
                
                if selected_type == 'ffmpeg':
                    if selected_index == -1:
                        message = "已选择FFmpeg系统音频捕获（自动检测）\n\n"
                        message += "这将直接捕获系统音频输出，无需额外配置。\n\n"
                    else:
                        ffmpeg_devices = get_windows_audio_devices()
                        if selected_index < len(ffmpeg_devices):
                            device_name = ffmpeg_devices[selected_index]['name']
                            message = f"已选择FFmpeg设备:\n{device_name}\n\n"
                    
                    message += "优点:\n• 直接捕获系统音频\n• 无需额外软件\n• 音质优秀\n\n"
                    
                elif selected_type == 'virtual':
                    selected_device = next((dev for dev in all_devices if dev['index'] == selected_index), None)
                    if selected_device:
                        message = f"已选择虚拟音频设备:\n{selected_device['name']}\n\n"
                        message += "使用说明:\n1. 将系统音频输出设置为此虚拟设备\n2. 播放音频即可捕获\n\n"
                
                else:
                    selected_device = next((dev for dev in all_devices if dev['index'] == selected_index), None)
                    if selected_device:
                        message = f"已选择输入设备:\n{selected_device['name']}\n\n"
                
                message += "重启程序以应用新设置"
                wx.MessageBox(message, "设备选择完成", wx.OK | wx.ICON_INFORMATION)
                
                # 保存配置
                save_config()
                
                console_print(f"已选择音频设备: 索引={current_system_device}, 类型={selected_type}")
        
        dialog.Destroy()

    def toggle_color_mode(self):
        """切换黑白颜色模式"""
        self.is_dark_mode = not self.is_dark_mode
        # 设置文字颜色并应用
        self.text_color = wx.Colour(255, 255, 255) if self.is_dark_mode else wx.Colour(0, 0, 0)
        #attr = wx.TextAttr(self.text_color)
        # self.chinese_text_box.SetDefaultStyle(attr)
        # self.target_language_text_box.SetDefaultStyle(attr)
        # 应用新的背景设置
        #
        if self.is_dark_mode:
            self.set_panel_alpha(255)  # 重新应用当前透明度设置
            self.panel.SetBackgroundColour(wx.Colour(0, 0, 0, 0))
        else:
            self.set_panel_alpha(0)  # 重新应用当前透明度设置
            self.panel.SetBackgroundColour(wx.Colour(255, 255, 255, 0))

        # 立即刷新文本显示
        self.chinese_text_box.Refresh()
        self.target_language_text_box.Refresh()
        # 更新窗口透明度设置（仅Windows）
        if wx.Platform == "__WXMSW__":
            hwnd = self.GetHandle()
            ctypes.windll.user32.SetLayeredWindowAttributes(
                hwnd,
                0,
                self.bg_alpha,  # 使用实际的alpha值
                0x02  # LWA_ALPHA
            )

        # 更新UI组件
        self.chinese_text_box.Freeze()
        self.target_language_text_box.Freeze()

        try:
            # 更新背景色和文字颜色
            self.chinese_text_box.SetBackgroundColour(self.bg_color)
            self.target_language_text_box.SetBackgroundColour(self.bg_color)

            # 强制应用新的文字颜色
            attr = wx.TextAttr(self.text_color)
            attr.SetLineSpacing(14)  # 设置行间距
            self.chinese_text_box.SetDefaultStyle(attr)
            self.target_language_text_box.SetDefaultStyle(attr)
            # 重写当前文本以立即生效
            self.chinese_text_box.SetValue(self.chinese_text_box.GetValue())
            self.target_language_text_box.SetValue(self.target_language_text_box.GetValue())

            # 强制刷新显示
            self.chinese_text_box.Refresh()
            self.target_language_text_box.Refresh()
            self.panel.Layout()
            self.Refresh()

            # 更新窗口透明度设置（仅Windows）
            if wx.Platform == "__WXMSW__":
                hwnd = self.GetHandle()
                ctypes.windll.user32.SetLayeredWindowAttributes(
                    hwnd,
                    0,
                    self.panel_alpha,
                    0x02  # LWA_ALPHA
                )
        except Exception as e:
            console_print(f"切换颜色模式时出错: {e}")
        finally:
            self.chinese_text_box.Thaw()
            self.target_language_text_box.Thaw()

        # Try to set theme for RichTextCtrl (Windows specific) - Moved outside finally block
        if wx.Platform == "__WXMSW__":
            try:
                chinese_hwnd = self.chinese_text_box.GetHandle()
                target_hwnd = self.target_language_text_box.GetHandle()
                if self.is_dark_mode:
                    # Try applying explicit dark theme identifier
                    ctypes.windll.uxtheme.SetWindowTheme(chinese_hwnd, ctypes.c_wchar_p("DarkMode_Explorer"), None)
                    ctypes.windll.uxtheme.SetWindowTheme(target_hwnd, ctypes.c_wchar_p("DarkMode_Explorer"), None)
                else:
                    # Remove theme to revert to default
                    ctypes.windll.uxtheme.SetWindowTheme(chinese_hwnd, None, None)
                    ctypes.windll.uxtheme.SetWindowTheme(target_hwnd, None, None)
                # Refresh the controls after changing the theme
                self.chinese_text_box.Refresh()
                self.target_language_text_box.Refresh()

                # Attempt to set dark mode for the title bar (Windows 10 build 17763+ / Windows 11)
                try:
                    frame_hwnd = self.GetHandle()
                    # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 (Win 11 22000+) or 19 (Older Win 10/11)
                    # We'll try 20 first, might need refinement based on OS version checks
                    attribute_value = 20 
                    value = ctypes.c_int(1) if self.is_dark_mode else ctypes.c_int(0)
                    ctypes.windll.dwmapi.DwmSetWindowAttribute(frame_hwnd, attribute_value, ctypes.byref(value), ctypes.sizeof(value))
                except Exception as dwm_error:
                    # Fallback for older systems or if attribute 19 is needed
                    try:
                        attribute_value = 19
                        value = ctypes.c_int(1) if self.is_dark_mode else ctypes.c_int(0)
                        ctypes.windll.dwmapi.DwmSetWindowAttribute(frame_hwnd, attribute_value, ctypes.byref(value), ctypes.sizeof(value))
                    except Exception as dwm_error_fallback:
                         console_print(f"Error setting dark title bar (DWM): {dwm_error} / {dwm_error_fallback}")


            except Exception as theme_error:
                console_print(f"Error setting window theme: {theme_error}")

    def update_text(self, asr_result: TranscriptionResult, translation_result: TranslationResult):
        """更新文本框内容"""

        def process_result(result, text_buffer, text_box):
            is_new_sentence = False
            fixed_text = ''
            unfixed_text = ''

            if result is not None:  # 检查结果是否为空
                for word in result.words:
                    if word.fixed:
                        fixed_text += word.text
                    else:
                        unfixed_text += word.text

                # Update buffers with new text
                text_buffer[-1] = [fixed_text, unfixed_text]

                if result.is_sentence_end:
                    text_buffer.append(['', ''])

            fixed_text = ''
            unfixed_text = ''
            if result is not None and result.stash is not None:  # 检查结果和stash是否为空
                for word in result.stash.words:
                    if word['fixed']:
                        fixed_text += word.text
                    else:
                        unfixed_text += word.text
                text_buffer[-1] = [fixed_text, unfixed_text]

            # 检查是否为源语言文本框（中文面板）
            is_chinese_box = text_box == self.chinese_text_box
            
            if is_chinese_box:
                # 源语言面板：使用RichTextCtrl，与翻译区完全相同的逻辑
                text_box.Clear()

                attr = rt.RichTextAttr()
                attr.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)  # 左对齐
                attr.SetLineSpacing(14)  # 设置行间距
                text_box.SetDefaultStyle(attr)

                normal_font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
                text_box.BeginFont(normal_font)
                text_box.BeginTextColour(wx.BLACK)
                if self.is_dark_mode:
                    text_box.BeginTextColour(wx.WHITE)

                if len(text_buffer) > 1:
                    text_box.WriteText(''.join([x[0] + x[1] for x in text_buffer[:-1]]))

                # Write the last line in blue with larger font
                large_font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
                text_box.BeginFont(large_font)
                text_box.BeginTextColour(wx.BLACK)
                if self.is_dark_mode:
                    text_box.BeginTextColour(wx.WHITE)
                text_box.WriteText(text_buffer[-1][0] + text_buffer[-1][1])
                text_box.EndTextColour()
                text_box.EndFont()

                # Auto-scroll to the bottom of the text boxes
                text_box.ShowPosition(text_box.GetLastPosition() - 2)
            else:
                # 目标语言面板：使用RichTextCtrl，显示历史记录（保持原有逻辑）
                # Clear and update text box
                text_box.Clear()

                attr = rt.RichTextAttr()
                attr.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)  #左对齐
                attr.SetLineSpacing(14)  # 设置行间距
                text_box.SetDefaultStyle(attr)

                normal_font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL)
                text_box.BeginFont(normal_font)
                text_box.BeginTextColour(wx.BLACK)
                if self.is_dark_mode:
                    text_box.BeginTextColour(wx.WHITE)

                if len(text_buffer) > 1:
                    text_box.WriteText(''.join([x[0] + x[1] for x in text_buffer[:-1]]))

                # Write the last line in blue with larger font
                large_font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD)
                text_box.BeginFont(large_font)
                text_box.BeginTextColour(wx.BLACK)
                if self.is_dark_mode:
                    text_box.BeginTextColour(wx.WHITE)
                text_box.WriteText(text_buffer[-1][0] + text_buffer[-1][1])
                text_box.EndTextColour()
                text_box.EndFont()

                # Auto-scroll to the bottom of the text boxes
                text_box.ShowPosition(text_box.GetLastPosition() - 2)

        if asr_result:
            process_result(asr_result, self.chinese_text_buffer, self.chinese_text_box)

        if translation_result:
            translation = translation_result.get_translation('zh')
            if translation:
                process_result(translation, self.target_language_text_buffer, self.target_language_text_box)


if __name__ == '__main__':
    try:
        # 加载配置
        load_config()
        
        # 初始化 Dashscope API key
        init_dashscope_api_key()
        
        # 设置DPI感知
        ctypes.windll.shcore.SetProcessDpiAwareness(2) 
        
        # 显示启动信息
        console_print("=" * 50)
        console_print("🎵 Gummy翻译器启动")
        console_print("=" * 50)
        console_print(f"默认音频源: {'🎤 麦克风' if audio_source == 'microphone' else '🔊 系统音频'}")
        console_print(f"TTS状态: {'启用' if enable_tts else '禁用'}")
        ffmpeg_available = check_ffmpeg()
        console_print(f"FFmpeg状态: {'可用' if ffmpeg_available else '不可用'}")
        console_print("=" * 50)
        
        # 如果选择系统音频，检查可用的捕获方法
        if audio_source == 'system':
            if ffmpeg_available:
                # FFmpeg可用，直接启动
                console_print(f"✅ 使用FFmpeg进行系统音频捕获")
            else:
                # FFmpeg不可用，需要用户确认
                console_print(f"⚠️  系统音频捕获组件不可用!")
                console_print(f"   FFmpeg: ❌ 不可用")
                console_print(f"\n建议解决方案:")
                console_print(f"1. 安装FFmpeg: winget install FFmpeg")
                console_print(f"2. 安装虚拟音频设备: VB-CABLE, VoiceMeeter等")
                console_print(f"3. 切换到麦克风模式")
                
                continue_choice = input("\n是否仍要继续启动程序？(y/n): ").strip().lower()
                if continue_choice not in ['y', 'yes', '是']:
                    console_print("程序退出")
                    exit(0)
        
        console_print(f"\n快捷键:")
        console_print(f"  Alt+A: 切换音频源（麦克风/系统音频）")
        console_print(f"  Alt+D: 选择系统音频设备")
        console_print(f"  Alt+S: 切换TTS")
        console_print(f"  Alt+T: 切换颜色模式")
        console_print(f"  Alt+P: 打开设置")
        console_print(f"  Ctrl+H: 切换标题栏")
        console_print()
        
        asr_thread = threading.Thread(target=gummyAsrTask, daemon=True)
        asr_thread.start()
        tts_thread = threading.Thread(target=cosyvoiceTtsTask, daemon=True)
        tts_thread.start()
        
        app = wx.App(False)
        frame = FloatingSubtitleWindow()
        app.MainLoop()
    except KeyboardInterrupt:
        console_print("程序正在退出...")
    finally:
        # 清理资源
        stop_ffmpeg_audio_capture() 
        if 'audio_stream' in globals() and audio_stream is not None:
            audio_stream.stop_stream()
            audio_stream.close()
        if 'mic' in globals() and mic is not None:
            mic.terminate()
        
        # 保存配置
        save_config()
