#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号爬虫 - 爬取模块
======================

提供微信公众号文章爬取的核心功能，支持单个公众号爬取和批量爬取。
不依赖于任何GUI界面，可作为独立模块使用。

主要功能:
    1. 单个爬取 - 爬取单个公众号的文章
    2. 批量爬取 - 批量爬取多个公众号的文章
    3. 内容获取 - 获取文章的完整内容
    4. 数据存储 - 将爬取结果存储到CSV或数据库

技术特性:
    - 多线程支持: 可选择多线程并发爬取
    - 进度跟踪: 提供进度回调接口
    - 错误处理: 单个公众号失败不影响其他爬取
    - 断点续爬: 支持中断后继续爬取

版本: 1.0
"""

import json
import os
import csv
import random
import time
import threading
from datetime import datetime, date, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# 导入日志模块
from spider.log.utils import logger
from spider.wechat.utils import get_fakid, get_articles_list, get_article_content, format_time


class WeChatScraper:
    """微信公众号爬虫基础类"""
    
    def __init__(self, token=None, headers=None):
        """
        初始化爬虫
        
        Args:
            token: 访问token
            headers: 请求头（包含cookie等信息）
        """
        self.token = token
        self.headers = headers
        
        # 请求间隔范围（秒）
        self.request_delay = (1, 3)
        
        # 回调函数
        self.callbacks = {
            'progress': None,
            'error': None,
            'complete': None,
            'status': None
        }
    
    def set_token(self, token):
        """设置token"""
        self.token = token
    
    def set_headers(self, headers):
        """设置请求头"""
        self.headers = headers
    
    def set_callback(self, event_type, callback_func):
        """
        设置回调函数
        
        Args:
            event_type: 事件类型（progress/error/complete/status）
            callback_func: 回调函数
        """
        if event_type in self.callbacks:
            self.callbacks[event_type] = callback_func
    
    def search_account(self, query):
        """
        搜索公众号
        
        Args:
            query: 公众号名称关键词
            
        Returns:
            list: 匹配的公众号列表
        """
        if not self.token or not self.headers:
            self._trigger_error("未设置token或headers")
            return []
        
        try:
            return get_fakid(self.headers, self.token, query)
        except Exception as e:
            self._trigger_error(f"搜索公众号失败: {e}")
            return []
    
    def get_account_articles(self, account_name, fakeid=None, max_pages=10):
        """
        获取公众号文章列表
        
        Args:
            account_name: 公众号名称
            fakeid: 公众号fakeid，如果为None则自动搜索
            max_pages: 最大页数限制
            
        Returns:
            list: 文章信息列表
        """
        if not self.token or not self.headers:
            self._trigger_error("未设置token或headers")
            return []
        
        try:
            # 如果未提供fakeid，则尝试搜索获取
            if not fakeid:
                search_results = self.search_account(account_name)
                if not search_results:
                    self._trigger_error(f"未找到公众号: {account_name}")
                    return []
                
                fakeid = search_results[0]['wpub_fakid']
            
            self._trigger_status(account_name, "fetching", f"正在获取文章列表...")
            
            all_articles = []
            page_start = 0
            
            for page in range(max_pages):
                self._trigger_progress(page, max_pages)
                
                # 获取一页文章
                titles, links, update_times = get_articles_list(
                    page_num=1, 
                    start_page=page_start,
                    fakeid=fakeid,
                    token=self.token,
                    headers=self.headers
                )
                
                if not titles:
                    break  # 没有更多文章
                
                # 构建文章信息
                for title, link, update_time in zip(titles, links, update_times):
                    article = {
                        'name': account_name,
                        'title': title,
                        'link': link,
                        'publish_timestamp': int(update_time),
                        'publish_time': format_time(update_time),
                        'digest': '',  # 稍后可能会获取
                        'content': ''  # 稍后可能会获取
                    }
                    all_articles.append(article)
                
                page_start += 5
                
                # 请求间延迟
                delay = random.uniform(*self.request_delay)
                time.sleep(delay)
            
            self._trigger_status(account_name, "fetched", f"获取到 {len(all_articles)} 篇文章")
            self._trigger_progress(max_pages, max_pages)
            
            return all_articles
            
        except Exception as e:
            self._trigger_error(f"获取文章列表失败: {e}")
            return []
    
    def get_article_content_by_url(self, article):
        """
        获取单篇文章内容
        
        Args:
            article: 包含link的文章信息字典
            
        Returns:
            dict: 更新后的文章字典
        """
        if not self.headers:
            return article
        
        try:
            url = article['link']
            content = get_article_content(url, self.headers)
            article['content'] = content
            return article
        except Exception as e:
            logger.error(f"获取文章内容失败: {e}")
            article['content'] = f"获取内容失败: {str(e)}"
            return article
    
    def filter_articles_by_date(self, articles, start_date=None, end_date=None):
        """
        按日期范围过滤文章
        
        Args:
            articles: 文章列表
            start_date: 开始日期，格式为YYYY-MM-DD或datetime.date对象
            end_date: 结束日期，格式为YYYY-MM-DD或datetime.date对象
            
        Returns:
            list: 过滤后的文章列表
        """
        if not start_date and not end_date:
            return articles
        
        # 解析日期
        if isinstance(start_date, str):
            start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        if isinstance(end_date, str):
            end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        
        filtered_articles = []
        for article in articles:
            timestamp = article.get('publish_timestamp', 0)
            if timestamp:
                article_date = datetime.fromtimestamp(int(timestamp)).date()
                
                if start_date and article_date < start_date:
                    continue
                if end_date and article_date > end_date:
                    continue
                    
                filtered_articles.append(article)
        
        return filtered_articles
    
    def save_articles_to_csv(self, articles, filename):
        """
        保存文章到CSV文件
        
        Args:
            articles: 文章列表
            filename: 文件名
            
        Returns:
            bool: 保存是否成功
        """
        if not articles:
            return False
        
        try:
            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
            
            with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                
                # 写入标题行
                writer.writerow(['公众号', '标题', '发布时间', '链接', '内容'])
                
                # 写入数据行
                for article in articles:
                    writer.writerow([
                        article['name'],
                        article['title'],
                        article.get('publish_time', ''),
                        article['link'],
                        article.get('content', '')
                    ])
                    
            return True
            
        except Exception as e:
            logger.error(f"保存CSV失败: {e}")
            return False
    
    def _trigger_progress(self, current, total):
        """触发进度回调"""
        if self.callbacks['progress']:
            self.callbacks['progress'](current, total)
    
    def _trigger_error(self, error_msg):
        """触发错误回调"""
        if self.callbacks['error']:
            self.callbacks['error'](error_msg)
        else:
            logger.error(f"错误: {error_msg}")
    
    def _trigger_complete(self, result):
        """触发完成回调"""
        if self.callbacks['complete']:
            self.callbacks['complete'](result)
    
    def _trigger_status(self, account_name, status, message):
        """触发状态回调"""
        if self.callbacks['status']:
            self.callbacks['status'](account_name, status, message)
        else:
            logger.info(f"{account_name}: {message}")


class BatchWeChatScraper:
    """批量爬取类"""
    
    def __init__(self):
        """初始化批量爬取器"""
        self.scraper = WeChatScraper()
        self.is_cancelled = False
        
        # 默认配置
        self.default_config = {
            'max_pages_per_account': 10,
            'request_interval': 10,
            'account_interval': (15, 30),
            'use_threading': False,
            'max_workers': 3,
            'include_content': False
        }
        
        # 回调函数
        self.callbacks = {
            'progress_updated': None,
            'account_status': None,
            'batch_completed': None,
            'error_occurred': None
        }
    
    def set_callback(self, event_type, callback_func):
        """
        设置回调函数
        
        Args:
            event_type: 事件类型
            callback_func: 回调函数
        """
        if event_type in self.callbacks:
            self.callbacks[event_type] = callback_func
    
    def cancel_batch_scrape(self):
        """取消批量爬取"""
        self.is_cancelled = True
    
    def start_batch_scrape(self, config):
        """
        开始批量爬取
        
        Args:
            config: 爬取配置，包含以下字段:
                - accounts: 公众号列表
                - start_date: 开始日期
                - end_date: 结束日期
                - token: 访问token
                - headers: 请求头
                - output_file: 输出文件（可选）
                - 其他配置参数（见default_config）
                
        Returns:
            list: 爬取的文章列表
        """
        # 合并默认配置
        for key, value in self.default_config.items():
            if key not in config:
                config[key] = value
        
        # 设置token和headers
        self.scraper.set_token(config['token'])
        self.scraper.set_headers(config['headers'])
        
        # 重置状态
        self.is_cancelled = False
        
        # 解析日期
        try:
            start_date = datetime.strptime(config['start_date'], '%Y-%m-%d').date()
            end_date = datetime.strptime(config['end_date'], '%Y-%m-%d').date()
        except:
            self._trigger_error("系统", "日期格式错误，应为YYYY-MM-DD")
            return []
        
        if start_date > end_date:
            self._trigger_error("系统", "开始日期不能晚于结束日期")
            return []
        
        accounts = config['accounts']
        total_accounts = len(accounts)
        
        # 决定使用何种方式爬取
        if config.get('use_threading', False) and total_accounts > 1:
            # 多线程爬取
            all_articles = self._process_accounts_threaded(config, accounts, start_date, end_date)
        else:
            # 单线程顺序爬取
            all_articles = self._process_accounts_sequential(config, accounts, start_date, end_date)
        
        # 保存结果到CSV
        if not self.is_cancelled:
            output_file = config.get('output_file')
            if output_file:
                self.scraper.save_articles_to_csv(all_articles, output_file)
            
            # 触发完成回调
            self._trigger_batch_completed(len(all_articles))
        
        return all_articles
    
    def _process_accounts_sequential(self, config, accounts, start_date, end_date):
        """
        顺序处理公众号
        
        Args:
            config: 爬取配置
            accounts: 公众号列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            list: 爬取的文章列表
        """
        all_articles = []
        total_accounts = len(accounts)
        
        for i, account in enumerate(accounts):
            if self.is_cancelled:
                break
                
            self._trigger_account_status(account, "processing", f"正在处理 ({i+1}/{total_accounts})")
            self._trigger_progress_updated(i, total_accounts)
            
            try:
                # 爬取单个公众号
                articles = self._scrape_single_account(config, account, start_date, end_date)
                all_articles.extend(articles)
                
                self._trigger_account_status(account, "completed", f"完成，获得 {len(articles)} 篇文章")
                
                # 账号间延迟
                if i < total_accounts - 1:
                    interval_range = config.get('account_interval', (15, 30))
                    delay = random.uniform(*interval_range)
                    time.sleep(delay)
                    
            except Exception as e:
                error_msg = f"处理失败: {str(e)}"
                self._trigger_account_status(account, "error", error_msg)
                self._trigger_error(account, error_msg)
                continue
        
        self._trigger_progress_updated(total_accounts, total_accounts)
        return all_articles
    
    def _process_accounts_threaded(self, config, accounts, start_date, end_date):
        """
        多线程处理公众号
        
        Args:
            config: 爬取配置
            accounts: 公众号列表
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            list: 爬取的文章列表
        """
        all_articles = []
        total_accounts = len(accounts)
        max_workers = min(config.get('max_workers', 3), total_accounts)
        completed_count = 0
        
        # 创建线程池
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # 提交任务
            future_to_account = {
                executor.submit(self._scrape_single_account, config, account, start_date, end_date): account 
                for account in accounts
            }
            
            # 处理结果
            for future in as_completed(future_to_account):
                account = future_to_account[future]
                completed_count += 1
                
                try:
                    articles = future.result()
                    all_articles.extend(articles)
                    
                    self._trigger_account_status(
                        account, "completed", f"完成，获得 {len(articles)} 篇文章"
                    )
                    
                except Exception as e:
                    error_msg = f"处理失败: {str(e)}"
                    self._trigger_account_status(account, "error", error_msg)
                    self._trigger_error(account, error_msg)
                
                self._trigger_progress_updated(completed_count, total_accounts)
                
                if self.is_cancelled:
                    break
        
        return all_articles
    
    def _scrape_single_account(self, config, account_name, start_date, end_date):
        """
        爬取单个公众号
        
        Args:
            config: 爬取配置
            account_name: 公众号名称
            start_date: 开始日期
            end_date: 结束日期
            
        Returns:
            list: 爬取的文章列表
        """
        self._trigger_account_status(account_name, "searching", "正在搜索公众号...")
        
        # 获取公众号fakeid
        search_results = self.scraper.search_account(account_name)
        if not search_results:
            raise Exception(f"未找到公众号: {account_name}")
        
        fakeid = search_results[0]['wpub_fakid']
        
        # 设置请求间隔
        self.scraper.request_delay = (1, config.get('request_interval', 60) / 10)
        
        # 获取文章列表
        self._trigger_account_status(account_name, "fetching", "正在获取文章列表...")
        max_pages = config.get('max_pages_per_account', 100)
        all_articles = self.scraper.get_account_articles(account_name, fakeid, max_pages)
        
        # 按日期过滤
        self._trigger_account_status(account_name, "filtering", "正在按日期过滤文章...")
        articles_in_range = self.scraper.filter_articles_by_date(all_articles, start_date, end_date)
        
        # 获取文章内容
        if config.get('include_content', False) and articles_in_range:
            self._trigger_account_status(account_name, "content", f"正在获取 {len(articles_in_range)} 篇文章的内容...")
            
            for i, article in enumerate(articles_in_range):
                if self.is_cancelled:
                    break
                    
                try:
                    # 获取内容
                    article = self.scraper.get_article_content_by_url(article)
                    
                    # 请求间延迟
                    if i < len(articles_in_range) - 1:
                        delay = random.uniform(1, config.get('request_interval', 60) / 10)
                        time.sleep(delay)
                        
                except Exception as e:
                    logger.error(f"获取文章内容失败: {e}")
                    continue
        
        return articles_in_range
    
    def _trigger_progress_updated(self, current, total):
        """触发进度更新回调"""
        if self.callbacks['progress_updated']:
            self.callbacks['progress_updated'](current, total)
    
    def _trigger_account_status(self, account_name, status, message):
        """触发账号状态回调"""
        if self.callbacks['account_status']:
            self.callbacks['account_status'](account_name, status, message)
        else:
            logger.info(f"{account_name}: {message}")
    
    def _trigger_batch_completed(self, total_articles):
        """触发批次完成回调"""
        if self.callbacks['batch_completed']:
            self.callbacks['batch_completed'](total_articles)
    
    def _trigger_error(self, account_name, error_message):
        """触发错误回调"""
        if self.callbacks['error']:
            self.callbacks['error'](account_name, error_message)
        else:
            logger.error(f"错误 - {account_name}: {error_message}") 