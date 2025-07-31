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

# 尝试导入sounddevice作为备用方案
try:
    import sounddevice as sd
    import numpy as np
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

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
current_system_device = None  # 当前选择的系统音频设备
ffmpeg_process = None  # FFmpeg进程
system_audio_queue = queue.Queue()  # 系统音频数据队列
sounddevice_stream = None  # sounddevice流对象
ffmpeg_path = None  # 自定义FFmpeg路径

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
    'enable_tts': False,
    'asr_model': 'gummy-realtime-v1',  # 默认ASR模型
    'api': {
        'enabled': True  # 默认启用API调用
    }
}

# 全局配置
config = DEFAULT_CONFIG.copy()

def load_config():
    """加载配置文件"""
    global config, audio_source, ffmpeg_path, target_language, current_system_device, enable_tts, enable_api_calls
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
                config.update(saved_config)
                print(f"已加载配置文件: {CONFIG_FILE}")
        else:
            print("未找到配置文件，使用默认配置")
    except Exception as e:
        print(f"加载配置文件失败: {e}，使用默认配置")
        config = DEFAULT_CONFIG.copy()
    
    # 应用配置到全局变量
    audio_source = config.get('audio_source', 'system')
    ffmpeg_path = config.get('ffmpeg_path', None)
    target_language = config.get('target_language', 'zh')
    current_system_device = config.get('current_system_device', None)
    enable_tts = config.get('enable_tts', False)
    enable_api_calls = config.get('api', {}).get('enabled', True)

def save_config():
    """保存配置文件"""
    global config, enable_api_calls
    
    # 更新配置
    config['audio_source'] = audio_source
    config['ffmpeg_path'] = ffmpeg_path
    config['target_language'] = target_language
    config['current_system_device'] = current_system_device
    config['enable_tts'] = enable_tts
    # asr_model会在设置对话框中更新，这里不需要修改
    
    # 确保api配置存在
    if 'api' not in config:
        config['api'] = {}
    config['api']['enabled'] = enable_api_calls
    
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        print(f"配置已保存到: {CONFIG_FILE}")
    except Exception as e:
        print(f"保存配置文件失败: {e}")

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
    elif config.get('dashscope_api_key') and config['dashscope_api_key'] != '<your-dashscope-api-key>':
        dashscope.api_key = config['dashscope_api_key']
    else:
        dashscope.api_key = '<your-dashscope-api-key>'  # set API-key manually

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
                print(f"使用配置中的FFmpeg: {ffmpeg_path}")
                return True
        except (subprocess.TimeoutExpired, FileNotFoundError):
            print(f"配置中的FFmpeg路径无效: {config['ffmpeg_path']}")
    
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
                    print(f"找到FFmpeg: {path}")
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

def test_audio_capture():
    """测试音频捕获功能"""
    print("\n" + "=" * 60)
    print("🧪 音频捕获测试")
    print("=" * 60)
    
    if not check_ffmpeg():
        print("❌ FFmpeg不可用，无法进行测试")
        return False
    
    print("🎵 开始测试系统音频捕获...")
    print("请在系统中播放一些音频（音乐、视频等）")
    print("测试将运行10秒钟...")
    
    # 启动音频捕获
    success = start_ffmpeg_audio_capture()
    
    if not success:
        print("❌ 音频捕获启动失败")
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
                        print(f"⏱️  已捕获 {data_count} 个音频数据包...")
            except queue.Empty:
                continue
                
    except KeyboardInterrupt:
        print("用户中断测试")
    
    # 停止捕获
    stop_ffmpeg_audio_capture()
    
    print(f"\n📊 测试结果:")
    print(f"  捕获的数据包数量: {data_count}")
    
    if data_count > 0:
        print("✅ 音频捕获测试成功！")
        print("  系统音频可以正常捕获")
        return True
    else:
        print("❌ 音频捕获测试失败！")
        print("  可能的原因:")
        print("  1. 系统没有播放音频")
        print("  2. 立体声混音未启用")
        print("  3. 需要使用虚拟音频设备")
        print("  4. 权限问题")
        return False

def list_all_audio_devices():
    """列出所有可用的音频设备用于调试"""
    print("\n" + "=" * 60)
    print("🔍 检测系统音频设备")
    print("=" * 60)
    
    # 1. 检查FFmpeg设备
    print("\n📺 FFmpeg DirectShow 设备:")
    ffmpeg_devices = get_windows_audio_devices()
    if ffmpeg_devices:
        for i, device in enumerate(ffmpeg_devices):
            print(f"  {i}: {device['name']}")
    else:
        print("  未检测到FFmpeg DirectShow设备")
    
    # 2. 检查PyAudio设备
    print("\n🎤 PyAudio 设备:")
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
            
            print(f"  {i}: {device_info['name']} ({device_type})")
        
        p.terminate()
    except Exception as e:
        print(f"  获取PyAudio设备失败: {e}")
    
    # 3. 检查sounddevice设备
    if SOUNDDEVICE_AVAILABLE:
        print("\n🔊 Sounddevice 设备:")
        try:
            devices = sd.query_devices()
            for i, device in enumerate(devices):
                device_type = ""
                if device['max_input_channels'] > 0:
                    device_type += "输入 "
                if device['max_output_channels'] > 0:
                    device_type += "输出 "
                print(f"  {i}: {device['name']} ({device_type})")
        except Exception as e:
            print(f"  获取sounddevice设备失败: {e}")
    else:
        print("\n🔊 Sounddevice: 不可用")
    
    print("\n" + "=" * 60)

def show_audio_source_selection():
    """显示音频源选择对话框"""
    # 检查FFmpeg状态
    ffmpeg_available = check_ffmpeg()
    ffmpeg_status = "✅ 可用" if ffmpeg_available else "❌ 不可用"
    
    print()
    print("=" * 60)
    print("🎵 请选择音频输入源")
    print("=" * 60)
    print()
    print("🎤 选项1: 麦克风录音")
    print("   - 捕获麦克风输入的语音")
    print("   - 适用于用户直接说话的场景")
    print("   - 稳定可靠，无需额外配置")
    print()
    print(f"🔊 选项2: 系统音频 (FFmpeg: {ffmpeg_status})")
    print("   - 捕获电脑播放的音频")
    print("   - 适用于翻译视频、音乐等系统声音")
    print("   - 需要FFmpeg或虚拟音频设备支持")
    print()
    print("=" * 60)
    
    while True:
        try:
            choice = input("请输入选择 (1=麦克风, 2=系统音频, q=退出): ").strip().lower()
            
            if choice == 'q' or choice == 'quit':
                print("用户选择退出程序")
                return None
            elif choice == '1' or choice == 'mic' or choice == 'microphone':
                print("✅ 已选择: 麦克风录音")
                return 'microphone'
            elif choice == '2' or choice == 'system':
                print("✅ 已选择: 系统音频")
                
                if not ffmpeg_available:
                    print()
                    print("⚠️  注意: 系统音频捕获需要额外组件支持")
                    print("-" * 50)
                    print("📦 方案1: 安装FFmpeg (推荐)")
                    print("  • winget install FFmpeg")
                    print("  • 或手动下载: https://www.gyan.dev/ffmpeg/builds/")
                    print()
                    print("🐍 方案2: 安装Python库")
                    print("  • pip install sounddevice numpy")
                    print()
                    print("🔌 方案3: 虚拟音频设备")
                    print("  • VB-CABLE: https://vb-audio.com/Cable/")
                    print("  • VoiceMeeter: https://vb-audio.com/Voicemeeter/")
                    print("-" * 50)
                    print()
                    
                    while True:
                        confirm = input("是否继续使用系统音频模式？(y/n): ").strip().lower()
                        if confirm in ['y', 'yes', '是']:
                            print("继续使用系统音频模式（程序会尝试使用可用的备用方案）")
                            return 'system'
                        elif confirm in ['n', 'no', '否']:
                            print("重新选择音频源...")
                            break
                        else:
                            print("请输入 y 或 n")
                else:
                    return 'system'
            else:
                print("❌ 无效选择，请输入 1、2 或 q")
                
        except KeyboardInterrupt:
            print("\n用户中断程序")
            return None
        except Exception as e:
            print(f"输入错误: {e}")
            print("请重新输入")

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
            print("FFmpeg stderr输出为空")
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
        print(f"FFmpeg输出编码错误: {e}")
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
            print(f"使用GBK编码也失败: {fallback_e}")
        return []
    except Exception as e:
        print(f"获取FFmpeg音频设备失败: {e}")
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
        
        # 尝试多种捕获方法
        capture_methods = []
        
        # 方法1: WASAPI loopback (Windows 默认音频输出)
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
        
        # 方法2: WASAPI with loopback flag
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
        
        # 方法3: DirectShow Stereo Mix
        if device_name is None:
            device_name = "立体声混音 (Realtek(R) Audio)"  # 常见的立体声混音名称
        
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
        
        # 方法4: 尝试其他常见的立体声混音设备名称
        common_stereo_mix_names = [
            "Stereo Mix",
            "立体声混音",
            "混音器",
            "What U Hear",
            "Wave Out Mix"
        ]
        
        for mix_name in common_stereo_mix_names:
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
        
        # 依次尝试每种方法
        for method in capture_methods:
            print(f"尝试音频捕获方法: {method['name']}")
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
                    print(f"✅ {method['name']} 启动成功")
                    break
                else:
                    # 进程已退出，获取错误信息
                    stderr_output = ffmpeg_process.stderr.read().decode('utf-8', errors='ignore')
                    print(f"❌ {method['name']} 失败: {stderr_output[:200]}...")
                    ffmpeg_process = None
                    
            except Exception as e:
                print(f"❌ {method['name']} 异常: {e}")
                ffmpeg_process = None
        
        if ffmpeg_process is None:
            print("所有音频捕获方法都失败了")
            return False
        
        # 启动线程读取音频数据
        audio_thread = threading.Thread(target=read_ffmpeg_audio, daemon=True)
        audio_thread.start()
        
        print(f"FFmpeg音频捕获已启动")
        return True
        
    except Exception as e:
        print(f"启动FFmpeg音频捕获失败: {e}")
        return False

def read_ffmpeg_audio():
    """读取FFmpeg输出的音频数据"""
    global ffmpeg_process, system_audio_queue
    
    if ffmpeg_process is None:
        print("FFmpeg进程为空，无法读取音频")
        return
    
    try:
        # 跳过WAV文件头（44字节）
        header = ffmpeg_process.stdout.read(44)
        if len(header) < 44:
            print(f"警告: WAV文件头不完整，只读取到 {len(header)} 字节")
            return
        
        print("开始读取FFmpeg音频数据...")
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
                        print(f"已读取 {audio_data_count} 个音频数据块，队列大小: {system_audio_queue.qsize()}")
                else:
                    print("FFmpeg输出流结束")
                    break
            except Exception as read_error:
                print(f"读取音频数据块时出错: {read_error}")
                break
                
    except Exception as e:
        print(f"读取FFmpeg音频数据出错: {e}")
    finally:
        if ffmpeg_process:
            # 获取错误输出
            try:
                stderr_output = ffmpeg_process.stderr.read().decode('utf-8', errors='ignore')
                if stderr_output.strip():
                    print(f"FFmpeg错误输出: {stderr_output}")
            except:
                pass
        print(f"FFmpeg音频读取线程结束，总共读取了 {audio_data_count} 个数据块")

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
            print(f"停止FFmpeg进程出错: {e}")
        finally:
            ffmpeg_process = None

# Sounddevice backup functions
def start_sounddevice_capture():
    """使用sounddevice捕获系统音频（备用方案）"""
    global sounddevice_stream, system_audio_queue
    
    if not SOUNDDEVICE_AVAILABLE:
        return False
    
    try:
        def audio_callback(indata, frames, time_info, status):
            """音频回调函数"""
            if status:
                print(f"Sounddevice status: {status}")
            
            # 转换numpy数组到bytes
            audio_data = (indata * 32767).astype(np.int16).tobytes()
            system_audio_queue.put(audio_data)
        
        # 启动录音流
        sounddevice_stream = sd.InputStream(
            device=current_system_device,
            channels=1,
            samplerate=16000,
            dtype=np.float32,
            blocksize=1600,  # 0.1秒的数据块
            callback=audio_callback
        )
        
        sounddevice_stream.start()
        print("Sounddevice系统音频捕获已启动")
        return True
        
    except Exception as e:
        print(f"启动sounddevice捕获失败: {e}")
        return False

def stop_sounddevice_capture():
    """停止sounddevice音频捕获"""
    global sounddevice_stream
    
    if sounddevice_stream:
        try:
            sounddevice_stream.stop()
            sounddevice_stream.close()
        except Exception as e:
            print(f"停止sounddevice流出错: {e}")
        finally:
            sounddevice_stream = None

def get_sounddevice_devices():
    """获取sounddevice音频设备列表"""
    if not SOUNDDEVICE_AVAILABLE:
        return []
    
    try:
        devices = sd.query_devices()
        device_list = []
        
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                device_list.append({
                    'index': i,
                    'name': device['name'],
                    'sample_rate': int(device['default_samplerate']),
                    'type': 'sounddevice'
                })
        
        return device_list
    except Exception as e:
        print(f"获取sounddevice设备失败: {e}")
        return []

# Function to get VB-Cable or Virtual Audio Cable devices
def get_virtual_audio_devices():
    """获取虚拟音频设备（VB-CABLE, Virtual Audio Cable等）"""
    devices = get_system_audio_devices()
    virtual_devices = []
    
    # 常见虚拟音频设备关键词
    virtual_keywords = ['vb-cable', 'virtual audio cable', 'voicemeeter', 
                       'cable', 'virtual', 'vac', 'line', 'aux']
    
    for device in devices:
        if device['type'] == 'input':
            device_name_lower = device['name'].lower()
            for keyword in virtual_keywords:
                if keyword in device_name_lower:
                    virtual_devices.append(device)
                    break
    
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
        print(f"获取音频设备列表失败: {e}")
        return []

# Function to find stereo mix or similar loopback devices
def find_loopback_devices():
    """查找环回录音设备（如立体声混音）"""
    devices = get_system_audio_devices()
    loopback_devices = []
    
    # 常见的环回录音设备名称关键词
    loopback_keywords = ['stereo mix', 'what u hear', 'wave out mix', 'mixed output', 
                        '立体声混音', '您听到的声音', '混合输出', 'loopback']
    
    for device in devices:
        if device['type'] == 'input':
            device_name_lower = device['name'].lower()
            for keyword in loopback_keywords:
                if keyword in device_name_lower:
                    loopback_devices.append(device)
                    break
    
    return loopback_devices

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
            print("正在停止旧的translator...")
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
                print('新的TranslationRecognizerCallback已打开')

            def on_close(self) -> None:
                global translator_stopped
                print('TranslationRecognizerCallback关闭')
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
                            print('target_language sentence end')
                            self.sentence_ptr += 1
                            self.tg_word_ptr = 0
                            self.zh_word_ptr = 0
                            asr_fixed_words.put(['', True])
                            is_sentence_end = True
                wx_text_queue.put([transcription_result, translation_result])

        callback = Callback()

        # 创建新的translator
        asr_model = config.get('asr_model', 'gummy-realtime-v1')
        print(f"使用ASR模型: {asr_model}")
        
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

        print('重启translator...')
        new_translator.start()
        print(f'新translator request_id: {new_translator.get_last_request_id()}')
        
        return new_translator
        
    except Exception as e:
        print(f"重启translator失败: {e}")
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
            
            with pyaudio_lock:
                print('TranslationRecognizerCallback open.')
                
                if audio_source == 'microphone' or audio_source is None:
                    # 麦克风录音（包括未选择的情况默认使用麦克风）
                    mic = pyaudio.PyAudio()
                    audio_stream = mic.open(format=pyaudio.paInt16,
                                            channels=1,
                                            rate=16000,
                                            input=True)
                    print("已连接到麦克风")
                    
                elif audio_source == 'system':
                    # 使用FFmpeg捕获系统音频
                    print("尝试使用FFmpeg捕获系统音频...")
                    
                    if check_ffmpeg():
                        device_name = None
                        if current_system_device is not None:
                            # 如果选择了特定设备
                            devices = get_windows_audio_devices()
                            if current_system_device < len(devices):
                                device_name = devices[current_system_device]['name']
                        
                        success = start_ffmpeg_audio_capture(device_name)
                        if success:
                            print("FFmpeg系统音频捕获启动成功")
                            # 不需要设置PyAudio流，因为我们使用FFmpeg
                            mic = None
                            audio_stream = None
                        else:
                            print("FFmpeg启动失败，回退到麦克风")
                            # 回退到麦克风
                            mic = pyaudio.PyAudio()
                            audio_stream = mic.open(format=pyaudio.paInt16,
                                                    channels=1,
                                                    rate=16000,
                                                    input=True)
                    else:
                        print("未找到FFmpeg，尝试备用方案...")
                        
                        # 尝试使用sounddevice作为备用方案
                        if SOUNDDEVICE_AVAILABLE:
                            print("尝试使用sounddevice捕获音频...")
                            success = start_sounddevice_capture()
                            if success:
                                print("Sounddevice音频捕获启动成功")
                                mic = None
                                audio_stream = None
                            else:
                                print("Sounddevice启动失败，尝试虚拟音频设备...")
                                # 尝试使用虚拟音频设备
                                virtual_devices = get_virtual_audio_devices()
                                if virtual_devices and current_system_device is not None:
                                    try:
                                        mic = pyaudio.PyAudio()
                                        device_info = mic.get_device_info_by_index(current_system_device)
                                        print(f"尝试连接到虚拟音频设备: {device_info['name']}")
                                        
                                        audio_stream = mic.open(
                                            format=pyaudio.paInt16,
                                            channels=1,
                                            rate=16000,
                                            input=True,
                                            input_device_index=current_system_device,
                                            frames_per_buffer=3200
                                        )
                                        print(f"已连接到虚拟音频设备: {device_info['name']}")
                                    except Exception as e:
                                        print(f"连接虚拟音频设备失败: {e}")
                                        # 最后回退到麦克风
                                        mic = pyaudio.PyAudio()
                                        audio_stream = mic.open(format=pyaudio.paInt16,
                                                                channels=1,
                                                                rate=16000,
                                                                input=True)
                                        print("回退到麦克风录音")
                                else:
                                    # 最后回退到麦克风
                                    mic = pyaudio.PyAudio()
                                    audio_stream = mic.open(format=pyaudio.paInt16,
                                                            channels=1,
                                                            rate=16000,
                                                            input=True)
                                    print("回退到麦克风录音")
                        else:
                            print("Sounddevice不可用，尝试虚拟音频设备...")
                            # 尝试使用虚拟音频设备
                            virtual_devices = get_virtual_audio_devices()
                            if virtual_devices and current_system_device is not None:
                                try:
                                    mic = pyaudio.PyAudio()
                                    device_info = mic.get_device_info_by_index(current_system_device)
                                    print(f"尝试连接到虚拟音频设备: {device_info['name']}")
                                    
                                    audio_stream = mic.open(
                                        format=pyaudio.paInt16,
                                        channels=1,
                                        rate=16000,
                                        input=True,
                                        input_device_index=current_system_device,
                                        frames_per_buffer=3200
                                    )
                                    print(f"已连接到虚拟音频设备: {device_info['name']}")
                                except Exception as e:
                                    print(f"连接虚拟音频设备失败: {e}")
                                    # 最后回退到麦克风
                                    mic = pyaudio.PyAudio()
                                    audio_stream = mic.open(format=pyaudio.paInt16,
                                                            channels=1,
                                                            rate=16000,
                                                            input=True)
                                    print("回退到麦克风录音")
                            else:
                                # 最后回退到麦克风
                                mic = pyaudio.PyAudio()
                                audio_stream = mic.open(format=pyaudio.paInt16,
                                                        channels=1,
                                                        rate=16000,
                                                        input=True)
                                print("回退到麦克风录音")
                else:
                    # 默认使用麦克风
                    mic = pyaudio.PyAudio()
                    audio_stream = mic.open(format=pyaudio.paInt16,
                                            channels=1,
                                            rate=16000,
                                            input=True)
                    print("使用默认麦克风")

        def on_close(self) -> None:
            # Clean up the audio stream and microphone
            global mic
            global audio_stream
            global translator_stopped
            print('TranslationRecognizerCallback close.')
            translator_stopped = True  # 标记translator已停止
            
            # 停止FFmpeg进程
            try:
                stop_ffmpeg_audio_capture()
            except Exception as e:
                print(f"停止FFmpeg时出错: {e}")
            
            # 停止sounddevice流
            try:
                stop_sounddevice_capture()
            except Exception as e:
                print(f"停止sounddevice时出错: {e}")
            
            if audio_stream is None:
                print('audio_stream is None')
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
                print(f"清理音频资源时出错: {e}")

        def on_event(
            self,
            request_id,
            transcription_result: TranscriptionResult,
            translation_result: TranslationResult,
            usage,
        ) -> None:
            new_chinese_words = ''
            new_target_language_words = ''
            is_sentence_end = False

            # Process transcription results. Only new fixed words will be pushed back.
            if transcription_result != None:
                for i, word in enumerate(transcription_result.words):
                    if word.fixed:
                        if i >= self.zh_word_ptr:
                            # print('new fixed ch word: ', word.text)
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
                                # print('new fixed {} word: '.format(
                                #     target_language, word.text))
                                asr_fixed_words.put([word.text, False])
                                new_target_language_words += word.text
                                self.tg_word_ptr += 1
                    # Check if the current sentence has ended
                    if target_language_translation.is_sentence_end:
                        print('target_language sentence end')
                        self.sentence_ptr += 1
                        self.tg_word_ptr = 0
                        self.zh_word_ptr = 0
                        asr_fixed_words.put(['', True])
                        is_sentence_end = True
            wx_text_queue.put([transcription_result, translation_result])

    callback = Callback()

    # Set up the ASR translator
    asr_model = config.get('asr_model', 'gummy-realtime-v1')
    print(f"使用ASR模型: {asr_model}")
    
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

    print('translator start')
    translator.start()
    print('translator request_id: {}'.format(translator.get_last_request_id()))

    # Open a file to save microphone audio data
    saved_mic_audio_file = open('mic_audio.pcm', 'wb')

    try:
        # Continuously read audio data from the microphone or FFmpeg
        pause_cleanup_counter = 0  # 暂停时的清理计数器
        
        while True:  # 主循环，用于处理translator重启
            data = None
            
            # 检查是否需要重启translator
            if need_restart_translator and not listening_paused:
                print("检测到需要重启translator...")
                translator = restart_translator(translator)
                if translator is None:
                    print("重启translator失败，退出")
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
                                print(f"暂停期间清理了 {discarded_count} 个音频数据块，当前队列大小: {system_audio_queue.qsize()}")
                    pause_cleanup_counter = 0
                
                time.sleep(0.1)  # 暂停时短暂休息
                continue
            
            # 如果translator已停止且不在暂停状态，退出循环等待重启
            if translator_stopped and not listening_paused:
                print("translator已停止，等待重启...")
                time.sleep(0.1)
                continue
            
            if audio_source == 'system' and (ffmpeg_process is not None or sounddevice_stream is not None):
                # 从FFmpeg队列或sounddevice队列读取音频数据
                try:
                    data = system_audio_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
            elif audio_stream:
                # 从PyAudio流读取音频数据
                try:
                    data = audio_stream.read(3200, exception_on_overflow=False)
                except Exception as e:
                    print(f"PyAudio读取错误: {e}")
                    break
            else:
                break
            
            if data and not listening_paused and not translator_stopped:  # 检查translator状态
                try:
                    translator.send_audio_frame(data)
                    saved_mic_audio_file.write(data)
                except Exception as e:
                    print(f"发送音频数据错误: {e}")
                    if "has stopped" in str(e):
                        print("检测到translator已停止")
                        translator_stopped = True
                    # 不要break，让循环继续等待重启
    except Exception as e:
        print(f"音频处理循环出错: {e}")
    finally:
        saved_mic_audio_file.close()
        
        # 安全地停止translator
        if not translator_stopped:
            try:
                print('translator stop')
                translator.stop()
                translator_stopped = True
            except Exception as e:
                print(f"停止translator时出错: {e}")
        else:
            print('translator已经停止，跳过stop调用')


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
                print('send sentence: ', buffer)
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
                                #print("len_chunk:", len(chunk))
                                buffer2 += chunk  # 将数据块添加到缓冲区
                                #print("len_buffer:",len(buffer2))
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
                        print(f"请求失败，状态码：{response.status_code}")
                    buffer = ''
                except requests.exceptions.RequestException as e:
                    print(f"请求异常: {e}")
                except Exception as e :
                    print(f"其他异常：{e}")
            else:
                buffer += word
                #print('buffer: ', buffer)
                    
        else:
            # Sleep briefly if no words are available
            time.sleep(0.01)

class SettingsDialog(wx.Dialog):
    """设置对话框"""
    
    def __init__(self, parent, config):
        super().__init__(parent, title="设置", size=(500, 400))
        
        self.config = config.copy()
        
        # 创建主面板
        panel = wx.Panel(self)
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建笔记本控件（标签页）
        notebook = wx.Notebook(panel)
        
        # API设置页面
        api_panel = wx.Panel(notebook)
        api_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # DashScope API Key
        api_sizer.Add(wx.StaticText(api_panel, label="DashScope API Key:"), 0, wx.ALL, 5)
        self.dashscope_key = wx.TextCtrl(api_panel, value=self.config.get('dashscope_api_key', ''))
        api_sizer.Add(self.dashscope_key, 0, wx.EXPAND | wx.ALL, 5)
        
        # SiliconFlow API Key
        api_sizer.Add(wx.StaticText(api_panel, label="SiliconFlow API Key:"), 0, wx.ALL, 5)
        self.siliconflow_key = wx.TextCtrl(api_panel, value=self.config.get('siliconflow_api_key', ''))
        api_sizer.Add(self.siliconflow_key, 0, wx.EXPAND | wx.ALL, 5)
        
        # TTS Voice
        api_sizer.Add(wx.StaticText(api_panel, label="TTS Voice:"), 0, wx.ALL, 5)
        voice_choices = [
            'FunAudioLLM/CosyVoice2-0.5B:alex',
            'FunAudioLLM/CosyVoice2-0.5B:bella',
            'FunAudioLLM/CosyVoice2-0.5B:carter',
            'FunAudioLLM/CosyVoice2-0.5B:emma'
        ]
        self.tts_voice = wx.Choice(api_panel, choices=voice_choices)
        current_voice = self.config.get('tts_voice', voice_choices[0])
        if current_voice in voice_choices:
            self.tts_voice.SetSelection(voice_choices.index(current_voice))
        else:
            self.tts_voice.SetSelection(0)
        api_sizer.Add(self.tts_voice, 0, wx.EXPAND | wx.ALL, 5)
        
        # ASR Model
        api_sizer.Add(wx.StaticText(api_panel, label="ASR模型:"), 0, wx.ALL, 5)
        model_choices = [
            'gummy-realtime-v1',
            'paraformer-realtime-v1',
            'paraformer-realtime-v2',
            'sensevoice-realtime-v1'
        ]
        self.asr_model = wx.Choice(api_panel, choices=model_choices)
        current_model = self.config.get('asr_model', model_choices[0])
        if current_model in model_choices:
            self.asr_model.SetSelection(model_choices.index(current_model))
            custom_model_value = ""
        else:
            self.asr_model.SetSelection(0)
            custom_model_value = current_model
        api_sizer.Add(self.asr_model, 0, wx.EXPAND | wx.ALL, 5)
        
        # 或者使用文本框让用户自定义输入模型名称
        api_sizer.Add(wx.StaticText(api_panel, label="自定义ASR模型 (可选):"), 0, wx.ALL, 5)
        self.custom_asr_model = wx.TextCtrl(api_panel, value=custom_model_value)
        api_sizer.Add(self.custom_asr_model, 0, wx.EXPAND | wx.ALL, 5)
        
        # 添加说明文字
        help_text = wx.StaticText(api_panel, label="提示: 如果填写了自定义模型名称，将优先使用自定义模型")
        help_text.SetForegroundColour(wx.Colour(100, 100, 100))
        api_sizer.Add(help_text, 0, wx.ALL, 5)
        
        api_panel.SetSizer(api_sizer)
        notebook.AddPage(api_panel, "API设置")
        
        # 路径设置页面
        path_panel = wx.Panel(notebook)
        path_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # FFmpeg路径
        path_sizer.Add(wx.StaticText(path_panel, label="FFmpeg可执行文件路径:"), 0, wx.ALL, 5)
        ffmpeg_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ffmpeg_path = wx.TextCtrl(path_panel, value=self.config.get('ffmpeg_path', '') or '')
        ffmpeg_sizer.Add(self.ffmpeg_path, 1, wx.ALL, 5)
        
        browse_btn = wx.Button(path_panel, label="浏览...")
        browse_btn.Bind(wx.EVT_BUTTON, self.on_browse_ffmpeg)
        ffmpeg_sizer.Add(browse_btn, 0, wx.ALL, 5)
        
        path_sizer.Add(ffmpeg_sizer, 0, wx.EXPAND)
        
        # 自动检测按钮
        detect_btn = wx.Button(path_panel, label="自动检测FFmpeg")
        detect_btn.Bind(wx.EVT_BUTTON, self.on_detect_ffmpeg)
        path_sizer.Add(detect_btn, 0, wx.ALL, 5)
        
        path_panel.SetSizer(path_sizer)
        notebook.AddPage(path_panel, "路径设置")
        
        # 音频设置页面
        audio_panel = wx.Panel(notebook)
        audio_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 音频源选择
        audio_sizer.Add(wx.StaticText(audio_panel, label="默认音频源:"), 0, wx.ALL, 5)
        self.audio_source = wx.Choice(audio_panel, choices=["麦克风", "系统音频"])
        self.audio_source.SetSelection(0 if self.config.get('audio_source') == 'microphone' else 1)
        audio_sizer.Add(self.audio_source, 0, wx.EXPAND | wx.ALL, 5)
        
        # 目标语言
        audio_sizer.Add(wx.StaticText(audio_panel, label="翻译目标语言:"), 0, wx.ALL, 5)
        lang_choices = ["zh", "en", "ja", "ko", "fr", "es", "de", "ru"]
        self.target_language = wx.Choice(audio_panel, choices=lang_choices)
        target_lang = self.config.get('target_language', 'zh')
        if target_lang in lang_choices:
            self.target_language.SetSelection(lang_choices.index(target_lang))
        else:
            self.target_language.SetSelection(0)
        audio_sizer.Add(self.target_language, 0, wx.EXPAND | wx.ALL, 5)
        
        # TTS启用
        self.enable_tts = wx.CheckBox(audio_panel, label="默认启用TTS")
        self.enable_tts.SetValue(self.config.get('enable_tts', False))
        audio_sizer.Add(self.enable_tts, 0, wx.ALL, 5)
        
        audio_panel.SetSizer(audio_sizer)
        notebook.AddPage(audio_panel, "音频设置")
        
        main_sizer.Add(notebook, 1, wx.EXPAND | wx.ALL, 10)
        
        # 按钮
        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        
        test_btn = wx.Button(panel, label="测试设置")
        test_btn.Bind(wx.EVT_BUTTON, self.on_test_settings)
        btn_sizer.Add(test_btn, 0, wx.ALL, 5)
        
        btn_sizer.AddStretchSpacer()
        
        cancel_btn = wx.Button(panel, wx.ID_CANCEL, "取消")
        btn_sizer.Add(cancel_btn, 0, wx.ALL, 5)
        
        ok_btn = wx.Button(panel, wx.ID_OK, "确定")
        btn_sizer.Add(ok_btn, 0, wx.ALL, 5)
        
        main_sizer.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 10)
        
        panel.SetSizer(main_sizer)
        
        self.Center()
    
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
    
    def get_config(self):
        """获取用户设置的配置"""
        config = {}
        
        # API设置
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
        config['audio_source'] = 'microphone' if self.audio_source.GetSelection() == 0 else 'system'
        config['target_language'] = self.target_language.GetStringSelection()
        config['enable_tts'] = self.enable_tts.GetValue()
        
        return config

class FloatingSubtitleWindow(wx.Frame):
    def __init__(self):
        # 初始化背景相关属性
        self.is_dark_mode = False  # 初始为亮色模式
        self.bg_alpha = 0  # 初始背景透明度值(0-255)
        self.text_color = wx.Colour(0, 0, 0)  # 初始文字颜色
        # 根据初始模式设置背景颜色
        brightness = int((255 - self.bg_alpha) * 1)
        self.bg_color = wx.Colour(brightness, brightness, brightness) if not self.is_dark_mode else wx.Colour(0, 0, 0)
        
        # 设置背景样式为透明
        style = wx.STAY_ON_TOP | wx.RESIZE_BORDER | wx.DEFAULT_FRAME_STYLE
        
        super().__init__(
            parent=None,
            title='实时翻译字幕',
            style=style
        )
        
        # 属性初始化
        self.transparency = 255
        self.font_size = 14
        self.font_family = wx.FONTFAMILY_DEFAULT
        self.text_color = wx.Colour(0, 0, 0)
        self.MAX_CHARS = 1000

        self.SetSize((900,110))
    
        # 添加文本面板透明度属性
        self.text_alpha = 128  # 初始背景透明度值
        self.background_color = wx.Colour(0, 0, 0)  # 黑色背景
        
        # 初始化文本面板背景透明度
        self.panel_alpha = 200  # 初始透明度值，增大初始值使文本更容易看见
        
        if wx.Platform == "__WXMSW__":
            # 启用窗口透明
            hwnd = self.GetHandle()
            GWL_EXSTYLE = -20
            WS_EX_LAYERED = 0x80000
            style = ctypes.windll.user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            ctypes.windll.user32.SetWindowLongW(hwnd, GWL_EXSTYLE, style | WS_EX_LAYERED)
            
            # 设置整个窗口的初始透明度
            ctypes.windll.user32.SetLayeredWindowAttributes(hwnd, 0, self.panel_alpha, 0x02)
        
        # 创建主面板
        self.panel = wx.Panel(self, style=wx.BORDER_NONE)
        self.panel.SetBackgroundColour(wx.Colour(255, 255, 255, 0))
        
        # 初始化布局
        self.main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        # 创建文本面板
        self.chinese_panel = self.create_language_panel("源语言", "chinese_text_box")
        self.target_panel = self.create_language_panel("目标语言", "target_language_text_box")
        
        # 添加到布局
        self.main_sizer.Add(self.chinese_panel, 0, wx.EXPAND | wx.ALL, 2)
        self.main_sizer.AddSpacer(5)  # 添加一个高度为 10 的空白区域
        self.main_sizer.Add(self.target_panel, 1, wx.EXPAND | wx.ALL, 2)
        
        # 创建状态栏
        self.status_bar = self.CreateStatusBar(1)
        self.update_status_bar()
        
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

        self.Center()
        self.Show()


    def check_mouse_position(self, event):
        """定时检查鼠标位置"""
        x, y = wx.GetMousePosition()  # 获取鼠标全局坐标
        rect = self.GetScreenRect()  # 获取窗口全局坐标的矩形区域
        if not rect.Contains(wx.Point(x, y)):
            if self.has_titlebar:
                #print("Mouse left the window (timer)")
                self.SetWindowStyleFlag(self.GetWindowStyleFlag() & ~wx.CAPTION)
                self.has_titlebar = False
                self.Refresh()
        else:
            if not self.has_titlebar:
                #print("Mouse in the window (timer)")
                self.SetWindowStyleFlag(self.GetWindowStyleFlag() | wx.CAPTION)
                self.has_titlebar = True
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
            print(f"定时器更新出错: {e}")
        event.Skip()

    def create_language_panel(self, title, text_box_name):
        panel = wx.Panel(self.panel)

        text_box = rt.RichTextCtrl(
            panel,
            style=wx.NO_BORDER | rt.RE_READONLY | rt.RE_MULTILINE
        )
        # text_box = stc.StyledTextCtrl(
        #     panel,
        #     style=wx.NO_BORDER
        # )
        text_box.SetMinSize((300, 25))

        font = wx.Font(
            wx.FontInfo(self.font_size)  # 字号
                .Family(wx.FONTFAMILY_DEFAULT)
                .Style(wx.FONTSTYLE_NORMAL)
                .Weight(wx.FONTWEIGHT_NORMAL)
                .AntiAliased(True)  # 关键：启用抗锯齿
                #.FaceName("微软雅黑")
        )
        text_box.SetFont(font)

        # 设置初始背景色
        text_box.SetBackgroundColour(self.bg_color)
        text_box.SetMargins(5, 2)

        # 设置文字颜色和样式
        #attr = wx.TextAttr()

        attr = rt.RichTextAttr()
        attr.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)  #左对齐
        attr.SetLineSpacing(14)  # 设置行间距

        attr.SetTextColour(self.text_color)
        text_box.SetDefaultStyle(attr)

        sizer = wx.BoxSizer(wx.VERTICAL)
        #label = wx.StaticText(panel, label=title)
        #sizer.Add(label, 0, wx.EXPAND | wx.ALL, 1)
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

            print(f"背景透明度已更新: alpha={alpha}, 亮度值={brightness}")
        except Exception as e:
            print(f"设置背景透明度时出错: {e}")
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
        global config, ffmpeg_path, audio_source, target_language, current_system_device, enable_tts, enable_api_calls
        
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
                print("音频监听已恢复 - translator将重启")
            else:
                print("音频监听已恢复")
            listening_paused = False
        else:
            # 暂停监听
            listening_paused = True
            print("音频监听已暂停")
        
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
        else:
            self.SetWindowStyle(self.GetWindowStyle() | wx.CAPTION)
            self.has_titlebar = True
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
        
        print(f"已切换到: {source_name}")
        
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
                
                print(f"已选择音频设备: 索引={current_system_device}, 类型={selected_type}")
        
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
            print(f"切换颜色模式时出错: {e}")
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
                         print(f"Error setting dark title bar (DWM): {dwm_error} / {dwm_error_fallback}")


            except Exception as theme_error:
                print(f"Error setting window theme: {theme_error}")

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

            # Clear and update text box
            text_box.Clear()

            attr = rt.RichTextAttr()
            attr.SetAlignment(wx.TEXT_ALIGNMENT_LEFT)  #左对齐
            attr.SetLineSpacing(14)  # 设置行间距
            #attr.SetTextColour(self.text_color)
            text_box.SetDefaultStyle(attr)

            # Write all lines except the last one in black
            normal_font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                                 wx.FONTWEIGHT_NORMAL)
            text_box.BeginFont(normal_font)
            text_box.BeginTextColour(wx.BLACK)
            if self.is_dark_mode:
                text_box.BeginTextColour(wx.WHITE)

            if len(text_buffer) > 1:
                text_box.WriteText(
                    ''.join([x[0] + x[1] for x in text_buffer[:-1]]))
                    #'\n'.join([x[0] + x[1] for x in text_buffer[:-1]]) + '\n')
                    #''.join([x[0] + x[1] for x in text_buffer[:-1]]) + '\n')

            # Write the last line in blue with larger font
            large_font = wx.Font(14, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL,
                                 wx.FONTWEIGHT_BOLD)
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
        print("=" * 50)
        print("🎵 Gummy翻译器启动")
        print("=" * 50)
        print(f"默认音频源: {'🎤 麦克风' if audio_source == 'microphone' else '🔊 系统音频'}")
        print(f"TTS状态: {'启用' if enable_tts else '禁用'}")
        ffmpeg_available = check_ffmpeg()
        print(f"FFmpeg状态: {'可用' if ffmpeg_available else '不可用'}")
        print("=" * 50)
        
        # 如果选择系统音频，检查可用的捕获方法
        if audio_source == 'system':
            sounddevice_available = SOUNDDEVICE_AVAILABLE
            
            if ffmpeg_available:
                # FFmpeg可用，直接启动
                print(f"✅ 使用FFmpeg进行系统音频捕获")
            elif sounddevice_available:
                # FFmpeg不可用，但有Sounddevice，提示并继续
                print(f"ℹ️  FFmpeg不可用，将使用Sounddevice作为备用方案")
                print(f"💡 提示：安装FFmpeg可获得更好的兼容性")
            else:
                # 两种方法都不可用，需要用户确认
                print(f"⚠️  系统音频捕获组件不可用!")
                print(f"   FFmpeg: ❌ 不可用")
                print(f"   Sounddevice: ❌ 不可用")
                print(f"\n建议解决方案:")
                print(f"1. 安装FFmpeg: winget install FFmpeg")
                print(f"2. 安装Python库: pip install sounddevice numpy")
                print(f"3. 安装虚拟音频设备: VB-CABLE, VoiceMeeter等")
                print(f"4. 切换到麦克风模式")
                
                continue_choice = input("\n是否仍要继续启动程序？(y/n): ").strip().lower()
                if continue_choice not in ['y', 'yes', '是']:
                    print("程序退出")
                    exit(0)
        
        print(f"\n快捷键:")
        print(f"  Alt+A: 切换音频源（麦克风/系统音频）")
        print(f"  Alt+D: 选择系统音频设备")
        print(f"  Alt+S: 切换TTS")
        print(f"  Alt+T: 切换颜色模式")
        print(f"  Alt+P: 打开设置")
        print(f"  Ctrl+H: 切换标题栏")
        print()
        
        asr_thread = threading.Thread(target=gummyAsrTask, daemon=True)
        asr_thread.start()
        tts_thread = threading.Thread(target=cosyvoiceTtsTask, daemon=True)
        tts_thread.start()
        
        app = wx.App(False)
        frame = FloatingSubtitleWindow()
        app.MainLoop()
    except KeyboardInterrupt:
        print("程序正在退出...")
    finally:
        # 清理资源
        stop_ffmpeg_audio_capture() 
        stop_sounddevice_capture()
        if 'audio_stream' in globals() and audio_stream is not None:
            audio_stream.stop_stream()
            audio_stream.close()
        if 'mic' in globals() and mic is not None:
            mic.terminate()
        
        # 保存配置
        save_config()
