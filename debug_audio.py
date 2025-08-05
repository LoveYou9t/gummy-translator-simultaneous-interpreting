#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
音频捕获和ASR调试脚本
用于诊断gummy_translator的音频处理问题
"""

import os
import sys
import time
import queue
import threading
import json
import subprocess
import tempfile

# 确保能够导入主程序的模块
sys.path.insert(0, os.path.dirname(__file__))

import dashscope
from dashscope.audio.asr import *
from gummy_translator import (
    load_config, init_dashscope_api_key, check_api_status,
    start_ffmpeg_audio_capture, stop_ffmpeg_audio_capture,
    system_audio_queue, config, enable_api_calls, target_language
)

def test_asr_only():
    """仅测试ASR功能，不进行音频捕获"""
    print("\n" + "=" * 60)
    print("🧪 ASR单独测试（使用预录制音频）")
    print("=" * 60)
    
    # 检查API状态
    check_api_status()
    
    if not enable_api_calls:
        print("❌ API调用被禁用，无法进行测试")
        return False
    
    # 创建测试音频数据（静音，用于测试连接）
    test_audio_data = b'\x00\x00' * 1600  # 0.1秒的16khz单声道静音
    
    class TestCallback(TranslationRecognizerCallback):
        def __init__(self):
            super().__init__()
            self.events_received = 0
            
        def on_open(self):
            print("✅ ASR连接已建立")
            
        def on_close(self):
            print("🔚 ASR连接已关闭")
            
        def on_event(self, request_id, transcription_result, translation_result, usage):
            self.events_received += 1
            print(f"📨 收到第 {self.events_received} 个事件:")
            print(f"   Request ID: {request_id}")
            if transcription_result:
                print(f"   转录结果: {len(transcription_result.words)} 个词")
            if translation_result:
                print(f"   翻译结果: 存在")
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
        print(f"ASR translator启动成功, request_id: {translator.get_last_request_id()}")
        
        # 发送测试音频数据
        print("发送测试音频数据...")
        for i in range(10):
            translator.send_audio_frame(test_audio_data)
            time.sleep(0.1)
        
        # 等待几秒钟接收响应
        print("等待ASR响应...")
        time.sleep(3)
        
        print("停止ASR translator...")
        translator.stop()
        
        if callback.events_received > 0:
            print(f"✅ ASR测试成功！收到 {callback.events_received} 个事件")
            return True
        else:
            print("❌ ASR测试失败：未收到任何事件")
            print("可能的原因:")
            print("  1. API密钥无效")
            print("  2. 网络连接问题")
            print("  3. 服务端问题")
            return False
            
    except Exception as e:
        print(f"❌ ASR测试异常: {e}")
        return False

def test_audio_to_asr():
    """测试完整的音频捕获到ASR流程"""
    print("\n" + "=" * 60)
    print("🧪 完整音频捕获+ASR测试")
    print("=" * 60)
    
    # 先启动音频捕获
    print("启动音频捕获...")
    if not start_ffmpeg_audio_capture():
        print("❌ 音频捕获启动失败")
        return False
    
    # 等待音频数据
    print("等待音频数据...")
    audio_data_received = 0
    start_time = time.time()
    
    try:
        while time.time() - start_time < 5:
            try:
                data = system_audio_queue.get(timeout=0.1)
                if data:
                    audio_data_received += 1
                    if audio_data_received == 1:
                        print(f"✅ 收到第一个音频数据包，大小: {len(data)} 字节")
            except queue.Empty:
                continue
        
        if audio_data_received == 0:
            print("❌ 未收到任何音频数据")
            stop_ffmpeg_audio_capture()
            return False
        
        print(f"✅ 5秒内收到 {audio_data_received} 个音频数据包")
        
        # 现在测试ASR
        class TestCallback(TranslationRecognizerCallback):
            def __init__(self):
                super().__init__()
                self.events_received = 0
                self.frames_sent = 0
                
            def on_open(self):
                print("✅ ASR连接已建立，开始发送音频数据")
                
            def on_close(self):
                print(f"🔚 ASR连接已关闭，总共发送了 {self.frames_sent} 个音频帧")
                
            def on_event(self, request_id, transcription_result, translation_result, usage):
                self.events_received += 1
                print(f"📨 ASR事件 #{self.events_received}:")
                if transcription_result:
                    words = [w.text for w in transcription_result.words]
                    print(f"   转录: {''.join(words)}")
                if translation_result:
                    trans = translation_result.get_translation(target_language)
                    if trans:
                        words = [w.text for w in trans.words]
                        print(f"   翻译: {''.join(words)}")
        
        callback = TestCallback()
        asr_model = config.get('asr_model', 'gummy-realtime-v1')
        
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
        
        # 发送实际音频数据到ASR
        print("开始发送音频数据到ASR...")
        start_time = time.time()
        
        while time.time() - start_time < 10:  # 测试10秒
            try:
                data = system_audio_queue.get(timeout=0.1)
                if data:
                    translator.send_audio_frame(data)
                    callback.frames_sent += 1
                    
                    if callback.frames_sent % 50 == 0:
                        print(f"已发送 {callback.frames_sent} 个音频帧到ASR")
            except queue.Empty:
                continue
            except Exception as e:
                print(f"发送音频数据错误: {e}")
                break
        
        print("停止ASR translator...")
        translator.stop()
        
        print(f"\n测试结果:")
        print(f"  音频数据包: {audio_data_received} 个")
        print(f"  发送到ASR: {callback.frames_sent} 个帧")
        print(f"  ASR事件: {callback.events_received} 个")
        
        if callback.events_received > 0:
            print("✅ 完整测试成功!")
            return True
        else:
            print("❌ 完整测试失败：ASR无响应")
            return False
            
    except Exception as e:
        print(f"❌ 测试异常: {e}")
        return False
    finally:
        stop_ffmpeg_audio_capture()

def main():
    print("🔧 Gummy Translator 音频调试工具")
    print("=" * 60)
    
    # 加载配置
    print("加载配置...")
    load_config()
    init_dashscope_api_key()
    
    while True:
        print("\n请选择测试项目:")
        print("1. API状态检查")
        print("2. ASR单独测试（推荐先执行）")
        print("3. 完整音频+ASR测试")
        print("4. 退出")
        
        choice = input("\n请输入选择 (1-4): ").strip()
        
        if choice == '1':
            check_api_status()
        elif choice == '2':
            test_asr_only()
        elif choice == '3':
            test_audio_to_asr()
        elif choice == '4':
            print("退出调试工具")
            break
        else:
            print("无效选择，请重试")

if __name__ == '__main__':
    main()
