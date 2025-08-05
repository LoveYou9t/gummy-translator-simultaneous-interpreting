#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
快速麦克风测试脚本
使用麦克风录音测试ASR功能
"""

import os
import sys
import time
import threading
import queue

# 确保能够导入主程序的模块
sys.path.insert(0, os.path.dirname(__file__))

import pyaudio
import dashscope
from dashscope.audio.asr import *
from gummy_translator import (
    load_config, init_dashscope_api_key, check_api_status,
    config, enable_api_calls, target_language
)

def test_microphone_asr():
    """使用麦克风测试ASR"""
    print("\n" + "=" * 60)
    print("🎤 麦克风ASR测试")
    print("=" * 60)
    
    # 检查API状态
    check_api_status()
    
    if not enable_api_calls:
        print("❌ API调用被禁用，无法进行测试")
        return False
    
    print("🎤 请准备对着麦克风说话...")
    print("   测试将持续10秒钟")
    print("   建议说一些简单的中文或英文句子")
    
    input("按回车键开始测试...")
    
    mic = None
    audio_stream = None
    
    class TestCallback(TranslationRecognizerCallback):
        def __init__(self):
            super().__init__()
            self.events_received = 0
            self.frames_sent = 0
            
        def on_open(self):
            nonlocal mic, audio_stream
            print("✅ ASR连接已建立，开始录音...")
            
            # 初始化麦克风
            mic = pyaudio.PyAudio()
            audio_stream = mic.open(
                format=pyaudio.paInt16,
                channels=1,
                rate=16000,
                input=True,
                frames_per_buffer=3200
            )
            
        def on_close(self):
            nonlocal mic, audio_stream
            print("🔚 ASR连接已关闭")
            
            # 清理音频资源
            if audio_stream:
                audio_stream.stop_stream()
                audio_stream.close()
                audio_stream = None
            if mic:
                mic.terminate() 
                mic = None
            
        def on_event(self, request_id, transcription_result, translation_result, usage):
            self.events_received += 1
            print(f"\n📨 ASR事件 #{self.events_received}:")
            
            if transcription_result:
                words = [w.text for w in transcription_result.words if w.fixed]
                if words:
                    print(f"   🎯 转录: {''.join(words)}")
                
                # 显示所有词（包括临时的）
                all_words = [w.text for w in transcription_result.words]
                if all_words:
                    print(f"   📝 完整: {''.join(all_words)}")
                    
            if translation_result:
                trans = translation_result.get_translation(target_language)
                if trans:
                    words = [w.text for w in trans.words if w.fixed]
                    if words:
                        print(f"   🌍 翻译: {''.join(words)}")
    
    try:
        callback = TestCallback()
        asr_model = config.get('asr_model', 'gummy-realtime-v1')
        print(f"使用ASR模型: {asr_model}")
        
        translator = TranslationRecognizerRealtime(
            model=asr_model,
            format='pcm',
            sample_rate=16000,
            transcription_enabled=True,
            translation_enabled=True,
            translation_target_languages=[target_language],
            callback=callback,
        )
        
        print("启动ASR translator...")
        translator.start()
        
        # 等待连接建立
        time.sleep(1)
        
        # 录音并发送音频数据
        print("🔴 录音开始...")
        start_time = time.time()
        
        while time.time() - start_time < 10:  # 录音10秒
            if audio_stream:
                try:
                    data = audio_stream.read(3200, exception_on_overflow=False)
                    translator.send_audio_frame(data)
                    callback.frames_sent += 1
                    
                    # 计算音量
                    import struct
                    if len(data) >= 2:
                        samples = struct.unpack('<' + 'h' * (len(data) // 2), data)
                        rms = (sum(sample * sample for sample in samples) / len(samples)) ** 0.5
                        
                        # 每秒显示一次音量
                        if callback.frames_sent % 100 == 0:
                            print(f"⏱️  {time.time() - start_time:.1f}s - 音量: {rms:.0f}")
                            
                except Exception as e:
                    print(f"录音错误: {e}")
                    break
        
        print("🔴 录音结束")
        
        # 等待最后的处理结果
        print("等待最终结果...")
        time.sleep(2)
        
        print("停止ASR translator...")
        translator.stop()
        
        print(f"\n测试结果:")
        print(f"  录音时长: 10秒")
        print(f"  音频帧数: {callback.frames_sent}")
        print(f"  ASR事件: {callback.events_received}")
        
        if callback.events_received > 0:
            print("✅ 麦克风ASR测试成功！")
            print("💡 这说明ASR功能正常，问题可能在于系统音频捕获")
            return True
        else:
            print("❌ 麦克风ASR测试失败：未收到任何事件")
            print("可能的原因:")
            print("  1. 麦克风没有声音输入")
            print("  2. ASR服务问题")
            print("  3. 音频格式问题")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🎤 麦克风ASR测试工具")
    print("=" * 40)
    
    # 加载配置
    print("加载配置...")
    load_config()
    init_dashscope_api_key()
    
    # 运行测试
    test_microphone_asr()

if __name__ == '__main__':
    main()
