#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号爬虫 - 登录模块
=======================

提供微信公众平台自动登录功能，获取爬虫所需的token和cookie。
使用Selenium模拟浏览器操作，实现扫码登录并缓存登录信息。

主要功能:
    1. 自动登录 - 启动浏览器并打开登录页面
    2. 缓存管理 - 缓存和验证登录信息
    3. Token获取 - 提取访问token
    4. Cookie管理 - 获取和格式化cookie

技术特性:
    - 自动化测试: 使用Selenium模拟用户操作
    - 缓存机制: 减少重复登录次数
    - 清理功能: 自动清理临时文件和进程
    - 跨平台支持: 兼容Windows/Mac/Linux

版本: 1.0
"""

import json
import os
import random
import time
import platform
import tempfile
import shutil
import subprocess
from datetime import datetime, timedelta
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import requests
import re

# 导入日志模块
from spider.log.utils import logger

# 配置常量
CACHE_FILE = 'wechat_cache.json'
CACHE_EXPIRE_HOURS = 24 * 4  # 缓存有效期（小时），4天


class WeChatSpiderLogin:
    """微信公众号登录管理器"""

    def __init__(self, cache_file=CACHE_FILE):
        """
        初始化登录管理器
        
        Args:
            cache_file (str): 缓存文件路径
        """
        self.token = None
        self.cookies = None
        self.cache_file = cache_file
        self.cache_expire_hours = CACHE_EXPIRE_HOURS
        self.driver = None
        self.temp_user_data_dir = None

    def save_cache(self):
        """保存token和cookies到缓存文件"""
        if self.token and self.cookies:
            cache_data = {
                'token': self.token,
                'cookies': self.cookies,
                'timestamp': datetime.now().timestamp()
            }
            try:
                with open(self.cache_file, 'w', encoding='utf-8') as f:
                    json.dump(cache_data, f, ensure_ascii=False, indent=2)
                logger.success(f"登录信息已保存到缓存文件 {self.cache_file}")
                return True
            except Exception as e:
                logger.error(f"保存缓存失败: {e}")
                return False
        return False

    def load_cache(self):
        """从缓存文件加载token和cookies"""
        if not os.path.exists(self.cache_file):
            logger.info("缓存文件不存在，需要重新登录")
            return False
        
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            cache_time = datetime.fromtimestamp(cache_data['timestamp'])
            current_time = datetime.now()
            hours_diff = (current_time - cache_time).total_seconds() / 3600
            
            if hours_diff > self.cache_expire_hours:
                logger.info(f"缓存已过期（{hours_diff:.1f}小时前），需要重新登录")
                return False
            
            self.token = cache_data['token']
            self.cookies = cache_data['cookies']
            logger.info(f"从缓存加载登录信息（{hours_diff:.1f}小时前保存）")
            return True
            
        except Exception as e:
            logger.error(f"读取缓存失败: {e}，需要重新登录")
            return False

    def validate_cache(self):
        """验证缓存的token和cookies是否仍然有效"""
        if not self.token or not self.cookies:
            return False
        
        try:
            headers = {
                "HOST": "mp.weixin.qq.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36"
            }
            
            test_url = 'https://mp.weixin.qq.com/cgi-bin/searchbiz'
            test_params = {
                'action': 'search_biz', 
                'token': self.token, 
                'lang': 'zh_CN', 
                'f': 'json', 
                'ajax': '1',
                'random': random.random(), 
                'query': 'test', 
                'begin': '0', 
                'count': '1',
            }
            
            response = requests.get(
                test_url, 
                cookies=self.cookies, 
                headers=headers, 
                params=test_params, 
                timeout=10
            )
            response.raise_for_status()

            result = response.json()
            
            if 'base_resp' in result:
                if result['base_resp']['ret'] == 0:
                    logger.success("缓存的登录信息验证有效")
                    return True
                elif result['base_resp']['ret'] in (-6, 200013):
                    logger.warning("缓存的token已失效")
                    return False
                else:
                    logger.warning(f"验证失败: {result['base_resp'].get('err_msg', '未知错误')}")
                    return False
            else:
                logger.warning("验证响应格式异常")
                return False
                
        except Exception as e:
            logger.error(f"验证缓存时发生错误: {e}")
            return False

    def clear_cache(self):
        """清除缓存文件"""
        try:
            if os.path.exists(self.cache_file):
                os.remove(self.cache_file)
                logger.info("缓存已清除")
            return True
        except Exception as e:
            logger.error(f"清除缓存失败: {e}")
            return False

    def _setup_chrome_options(self):
        """设置Chrome选项"""
        options = webdriver.ChromeOptions()
        
        # 创建临时目录保存用户数据
        self.temp_user_data_dir = tempfile.mkdtemp()
        options.add_argument(f"--user-data-dir={self.temp_user_data_dir}")
        
        # 其他选项
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-plugins")
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        
        # 页面缩放
        options.add_argument("--force-device-scale-factor=0.9")
        options.add_argument("--high-dpi-support=0.9")
        
        # 对无头模式的检测进行反规避
        options.add_argument("--disable-blink-features=AutomationControlled")
        
        # 自定义用户代理
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/107.0.0.0 Safari/537.36")
        
        return options

    def _cleanup_chrome_processes(self):
        """清理残留的Chrome进程"""
        try:
            system = platform.system()
            if system == "Windows":
                subprocess.run(["taskkill", "/F", "/IM", "chrome.exe", "/T"], 
                              stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            elif system in ("Linux", "Darwin"):  # Linux或Mac
                subprocess.run(["pkill", "-f", "chrome"], 
                              stderr=subprocess.DEVNULL, stdout=subprocess.DEVNULL)
            logger.debug("残留浏览器进程已清理")
        except Exception as e:
            logger.warning(f"清理Chrome进程时出现警告: {e}")

    def _cleanup_temp_files(self):
        """清理临时文件"""
        if self.temp_user_data_dir and os.path.exists(self.temp_user_data_dir):
            try:
                shutil.rmtree(self.temp_user_data_dir, ignore_errors=True)
                logger.debug("临时用户数据目录已清理")
            except Exception as e:
                logger.warning(f"清理临时目录时出现警告: {e}")

    def login(self):
        """
        登录微信公众号平台
        
        Returns:
            bool: 登录是否成功
        """
        logger.info("\n" + "="*60)
        logger.info("开始登录微信公众号平台...")
        logger.info("="*60)
        
        # 检查缓存
        if self.load_cache() and self.validate_cache():
            logger.success("使用有效的缓存登录信息")
            return True
        else:
            logger.info("缓存无效或不存在，需要重新扫码登录")
            self.clear_cache()
        
        # 清理残留进程
        self._cleanup_chrome_processes()
        
        try:
            logger.info("正在启动Chrome浏览器...")
            
            # 配置Chrome选项
            chrome_options = self._setup_chrome_options()
            
            # 创建WebDriver
            try:
                service = ChromeService()
                self.driver = webdriver.Chrome(service=service, options=chrome_options)
                logger.success("Chrome浏览器启动成功")
            except Exception as e:
                logger.error(f"Chrome浏览器启动失败: {e}")
                return False

            # 隐藏自动化特征
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )

            # 访问微信公众号平台
            logger.info("正在访问微信公众号平台...")
            self.driver.get('https://mp.weixin.qq.com/')
            logger.success("页面加载完成")
            
            logger.info("请在浏览器窗口中扫码登录...")
            logger.info("等待登录完成（最长等待5分钟）...")

            # 等待登录成功（URL中包含token）
            wait = WebDriverWait(self.driver, 300)  # 5分钟超时
            wait.until(EC.url_contains('token'))
            
            # 提取token
            current_url = self.driver.current_url
            logger.success("检测到登录成功！正在获取登录信息...")
            
            token_match = re.search(r'token=(\d+)', current_url)
            if token_match:
                self.token = token_match.group(1)
                logger.success(f"Token获取成功: {self.token}")
            else:
                logger.error("无法从URL中提取token")
                return False

            # 获取cookies
            raw_cookies = self.driver.get_cookies()
            self.cookies = {item['name']: item['value'] for item in raw_cookies}
            logger.success(f"Cookies获取成功，共{len(self.cookies)}个")
            
            # 保存到缓存
            if self.save_cache():
                logger.success("登录信息已保存到缓存")
            
            logger.success("登录完成！")
            return True
            
        except Exception as e:
            logger.error(f"登录过程中出现错误: {e}")
            return False
            
        finally:
            # 清理资源
            if self.driver:
                try:
                    self.driver.quit()
                    logger.debug("浏览器已关闭")
                except:
                    pass
            
            self._cleanup_chrome_processes()
            self._cleanup_temp_files()

    def check_login_status(self):
        """
        检查当前登录状态
        
        Returns:
            dict: 登录状态信息
        """
        if self.load_cache() and self.validate_cache():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                cache_time = datetime.fromtimestamp(cache_data['timestamp'])
                expire_time = cache_time + timedelta(hours=self.cache_expire_hours)
                hours_since_login = (datetime.now() - cache_time).total_seconds() / 3600
                hours_until_expire = (expire_time - datetime.now()).total_seconds() / 3600
                
                return {
                    'isLoggedIn': True,
                    'loginTime': cache_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'expireTime': expire_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'hoursSinceLogin': round(hours_since_login, 1),
                    'hoursUntilExpire': round(hours_until_expire, 1),
                    'token': self.token,
                    'message': f'已登录 {round(hours_since_login, 1)} 小时'
                }
            except:
                pass
        
        return {
            'isLoggedIn': False,
            'message': '未登录或登录已过期'
        }

    def logout(self):
        """
        退出登录
        
        Returns:
            bool: 退出是否成功
        """
        logger.info("正在退出登录...")
        
        # 清除缓存和状态
        self.clear_cache()
        self.token = None
        self.cookies = None
        
        # 清理进程和临时文件
        self._cleanup_chrome_processes()
        self._cleanup_temp_files()
        
        logger.success("退出登录完成")
        return True

    def get_token(self):
        """
        获取token
        
        Returns:
            str: token字符串，如果未登录返回None
        """
        if not self.token and not (self.load_cache() and self.validate_cache()):
            return None
        return self.token

    def get_cookies(self):
        """
        获取cookies字典
        
        Returns:
            dict: cookies字典，如果未登录返回None
        """
        if not self.cookies and not (self.load_cache() and self.validate_cache()):
            return None
        return self.cookies

    def get_cookie_string(self):
        """
        获取cookie字符串格式
        
        Returns:
            str: cookie字符串，如果未登录返回None
        """
        cookies = self.get_cookies()
        if not cookies:
            return None
        
        cookie_string = '; '.join([f"{key}={value}" for key, value in cookies.items()])
        return cookie_string

    def get_headers(self):
        """
        获取标准的HTTP请求头
        
        Returns:
            dict: 包含cookie和user-agent的请求头，如果未登录返回None
        """
        cookie_string = self.get_cookie_string()
        if not cookie_string:
            return None
        
        return {
            "cookie": cookie_string,
            "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/104.0.0.0 Safari/537.36"
        }

    def is_logged_in(self):
        """
        检查是否已登录
        
        Returns:
            bool: 是否已登录
        """
        return self.check_login_status()['isLoggedIn']


# 便捷函数
def quick_login():
    """
    快速登录函数
    
    Returns:
        tuple: (token, cookies, headers) 如果登录成功，否则返回 (None, None, None)
    """
    login_manager = WeChatSpiderLogin()
    if login_manager.login():
        return (
            login_manager.get_token(),
            login_manager.get_cookies(),
            login_manager.get_headers()
        )
    return (None, None, None)


def check_login():
    """
    检查登录状态的便捷函数
    
    Returns:
        dict: 登录状态信息
    """
    login_manager = WeChatSpiderLogin()
    return login_manager.check_login_status() 