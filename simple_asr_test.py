#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简单的ASR测试脚本
使用真实音频文件测试ASR功能
"""

import os
import sys
import time
import wave
import struct

# 确保能够导入主程序的模块
sys.path.insert(0, os.path.dirname(__file__))

import dashscope
from dashscope.audio.asr import *
from gummy_translator import (
    load_config, init_dashscope_api_key, check_api_status,
    config, enable_api_calls, target_language
)

def create_test_audio():
    """创建包含简单音频信号的测试文件"""
    print("创建测试音频数据...")
    
    # 创建一个包含简单正弦波的音频信号
    sample_rate = 16000
    duration = 2  # 2秒
    frequency = 440  # A音的频率
    
    audio_data = []
    for i in range(sample_rate * duration):
        # 创建正弦波信号
        import math
        value = int(30000 * math.sin(2 * math.pi * frequency * i / sample_rate))
        audio_data.append(struct.pack('<h', value))
    
    return b''.join(audio_data)

def test_asr_with_real_audio():
    """使用包含信号的音频测试ASR"""
    print("\n" + "=" * 60)
    print("🧪 ASR测试（使用音频信号）")
    print("=" * 60)
    
    # 检查API状态
    check_api_status()
    
    if not enable_api_calls:
        print("❌ API调用被禁用，无法进行测试")
        return False
    
    # 创建测试音频
    test_audio = create_test_audio()
    print(f"创建了 {len(test_audio)} 字节的测试音频")
    
    class TestCallback(TranslationRecognizerCallback):
        def __init__(self):
            super().__init__()
            self.events_received = 0
            self.connection_successful = False
            
        def on_open(self):
            print("✅ ASR连接已建立")
            self.connection_successful = True
            
        def on_close(self):
            print("🔚 ASR连接已关闭")
            
        def on_event(self, request_id, transcription_result, translation_result, usage):
            self.events_received += 1
            print(f"📨 收到第 {self.events_received} 个事件:")
            print(f"   Request ID: {request_id}")
            
            if transcription_result:
                print(f"   转录结果: {len(transcription_result.words)} 个词")
                if transcription_result.words:
                    words_text = ''.join([w.text for w in transcription_result.words])
                    print(f"   转录内容: {words_text}")
            else:
                print("   转录结果: None")
                
            if translation_result:
                trans = translation_result.get_translation(target_language)
                if trans:
                    print(f"   翻译结果: {len(trans.words)} 个词")
                    if trans.words:
                        trans_text = ''.join([w.text for w in trans.words])
                        print(f"   翻译内容: {trans_text}")
                else:
                    print("   翻译结果: 无目标语言翻译")
            else:
                print("   翻译结果: None")
                
            if usage:
                print(f"   使用情况: {usage}")
    
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
        
        if not callback.connection_successful:
            print("❌ ASR连接失败")
            return False
            
        print(f"ASR translator启动成功, request_id: {translator.get_last_request_id()}")
        
        # 分块发送音频数据
        chunk_size = 3200  # 0.1秒的音频数据
        total_chunks = len(test_audio) // chunk_size
        
        print(f"开始发送 {total_chunks} 个音频数据块...")
        
        for i in range(0, len(test_audio), chunk_size):
            chunk = test_audio[i:i+chunk_size]
            if len(chunk) == chunk_size:  # 确保块大小正确
                translator.send_audio_frame(chunk)
                print(f"发送第 {i//chunk_size + 1}/{total_chunks} 个数据块")
                time.sleep(0.1)
        
        # 等待处理结果
        print("等待ASR处理结果...")
        time.sleep(5)
        
        print("停止ASR translator...")
        translator.stop()
        
        print(f"\n测试结果:")
        print(f"  连接状态: {'成功' if callback.connection_successful else '失败'}")
        print(f"  收到事件: {callback.events_received} 个")
        
        if callback.events_received > 0:
            print("✅ ASR测试成功！")
            return True
        else:
            print("❌ ASR测试失败：未收到任何事件")
            print("\n可能的原因:")
            print("  1. 音频信号不被识别为语音")
            print("  2. ASR模型需要真实的语音输入")
            print("  3. 服务端处理延迟")
            return False
            
    except Exception as e:
        print(f"❌ ASR测试异常: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    print("🔧 简单ASR测试工具")
    print("=" * 40)
    
    # 加载配置
    print("加载配置...")
    load_config()
    init_dashscope_api_key()
    
    # 运行测试
    test_asr_with_real_audio()

if __name__ == '__main__':
    main()
