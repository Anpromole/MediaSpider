#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微博爬虫运行模块
==============
提供微博搜索和文章爬取功能。

主要功能:
    1. 关键词搜索 - 搜索微博内容
    2. 用户主页爬取 - 爬取指定用户的微博
    3. 详情页爬取 - 获取微博完整内容
"""

import os
import re
import json
import time
import random
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests

# 导入日志模块
from spider.log.utils import logger


class WeiboSpiderRunner:
    """微博爬虫运行器"""

    def __init__(self):
        """初始化爬虫"""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
        })
        self.keep_running = True
        self.cookies = None

    def stop(self):
        """停止当前任务"""
        logger.warning("收到停止指令，正在终止微博爬取任务...")
        self.keep_running = False

    def reset_stop(self):
        """重置停止标志"""
        self.keep_running = True

    def set_cookies(self, cookies: str):
        """
        设置微博 cookies（可选，用于绕过部分反爬）

        Args:
            cookies: cookie 字符串
        """
        self.cookies = cookies
        if cookies:
            cookie_dict = {}
            for item in cookies.split(';'):
                if '=' in item:
                    key, value = item.strip().split('=', 1)
                    cookie_dict[key] = value
            self.session.cookies.update(cookie_dict)

    def search_keyword(self, keyword: str, pages: int = 5,
                       start_date: str = None, end_date: str = None,
                       progress_callback=None) -> List[Dict]:
        """
        搜索微博内容

        Args:
            keyword: 搜索关键词
            pages: 爬取页数
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            progress_callback: 进度回调函数

        Returns:
            list: 微博列表
        """
        logger.info(f"开始搜索微博，关键词：{keyword}")
        self.reset_stop()

        all_weibos = []
        base_url = "https://m.weibo.cn/api/container/getIndex"

        for page in range(1, pages + 1):
            if not self.keep_running:
                logger.warning("用户停止了微博爬取任务")
                break

            try:
                # 构建请求参数
                params = {
                    'containerid': f'100103type=1&q={keyword}',
                    'page_type': 'searchall',
                    'page': page
                }

                response = self.session.get(base_url, params=params, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    cards = data.get('data', {}).get('cards', [])

                    for card in cards:
                        mblog = card.get('mblog', {})
                        if not mblog:
                            continue

                        text = mblog.get('text', '')
                        # 清理 HTML 标签
                        clean_text = BeautifulSoup(text, 'lxml').get_text(strip=True)

                        if not clean_text:
                            continue

                        # 构建微博信息
                        weibo = {
                            'id': mblog.get('id', ''),
                            'title': clean_text[:100],  # 标题取前 100 字
                            'content': clean_text,
                            'link': f"https://m.weibo.cn/status/{mblog.get('id', '')}",
                            'source': '微博',
                            'author': mblog.get('user', {}).get('screen_name', '未知用户'),
                            'publish_timestamp': self._parse_weibo_time(mblog.get('created_at', '')),
                            'reposts_count': mblog.get('reposts_count', 0),
                            'comments_count': mblog.get('comments_count', 0),
                            'attitudes_count': mblog.get('attitudes_count', 0)
                        }

                        # 日期过滤
                        if start_date or end_date:
                            weibo_date = datetime.fromtimestamp(weibo['publish_timestamp']).date()
                            if start_date:
                                start = datetime.strptime(start_date, '%Y-%m-%d').date()
                                if weibo_date < start:
                                    continue
                            if end_date:
                                end = datetime.strptime(end_date, '%Y-%m-%d').date()
                                if weibo_date > end:
                                    continue

                        all_weibos.append(weibo)

                    if progress_callback:
                        progress_callback(page, pages, f"已爬取 {len(all_weibos)} 条微博")

                    # 随机延迟
                    time.sleep(random.uniform(1, 3))
                else:
                    logger.warning(f"微博搜索请求失败，状态码：{response.status_code}")

            except json.JSONDecodeError:
                logger.error(f"微博搜索响应解析失败，第{page}页")
            except Exception as e:
                logger.error(f"微博搜索出错：{e}")

        logger.info(f"微博搜索完成，共获取 {len(all_weibos)} 条结果")
        return all_weibos

    def scrape_user(self, user_id: str, pages: int = 5,
                    progress_callback=None) -> List[Dict]:
        """
        爬取指定用户的微博

        Args:
            user_id: 用户 ID
            pages: 爬取页数
            progress_callback: 进度回调

        Returns:
            list: 微博列表
        """
        logger.info(f"开始爬取用户 {user_id} 的微博")
        self.reset_stop()

        all_weibos = []
        base_url = "https://m.weibo.cn/api/container/getIndex"

        # 先获取用户的 containerid
        try:
            params = {'uid': user_id}
            response = self.session.get(base_url, params=params, timeout=15)
            data = response.json()
            containerid = data.get('data', {}).get('tabsInfo', {}).get('tabs', [{}])[0].get('containerid', '')

            if not containerid:
                containerid = f'230413{user_id}'  # 默认格式
        except:
            containerid = f'230413{user_id}'

        for page in range(1, pages + 1):
            if not self.keep_running:
                break

            try:
                params = {
                    'containerid': containerid,
                    'page_type': 'profile',
                    'page': page
                }

                response = self.session.get(base_url, params=params, timeout=15)

                if response.status_code == 200:
                    data = response.json()
                    cards = data.get('data', {}).get('cards', [])

                    for card in cards:
                        mblog = card.get('mblog', {})
                        if not mblog:
                            continue

                        text = mblog.get('text', '')
                        clean_text = BeautifulSoup(text, 'lxml').get_text(strip=True)

                        if not clean_text:
                            continue

                        weibo = {
                            'id': mblog.get('id', ''),
                            'title': clean_text[:100],
                            'content': clean_text,
                            'link': f"https://m.weibo.cn/status/{mblog.get('id', '')}",
                            'source': '微博',
                            'author': mblog.get('user', {}).get('screen_name', '未知用户'),
                            'publish_timestamp': self._parse_weibo_time(mblog.get('created_at', ''))
                        }

                        all_weibos.append(weibo)

                    if progress_callback:
                        progress_callback(page, pages)

                    time.sleep(random.uniform(0.5, 2))

            except Exception as e:
                logger.error(f"爬取用户微博出错：{e}")

        return all_weibos

    def get_article_detail(self, url: str) -> Optional[Dict]:
        """
        获取微博详情页内容

        Args:
            url: 微博链接

        Returns:
            dict: 微博详情
        """
        try:
            response = self.session.get(url, timeout=15)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, 'lxml')

            # 提取内容
            content_elem = soup.select_one('.weibo-detail')
            content = content_elem.get_text(strip=True) if content_elem else ''

            return {
                'link': url,
                'content': content,
                'source': '微博'
            }
        except Exception as e:
            logger.error(f"获取微博详情失败：{e}")
            return None

    def save_to_csv(self, weibos: List[Dict], filename: str):
        """
        保存微博到 CSV 文件

        Args:
            weibos: 微博列表
            filename: 文件名
        """
        import csv

        if not weibos:
            logger.warning("没有微博数据可保存")
            return

        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['来源', '作者', '标题', '发布时间', '链接', '内容'])

            for weibo in weibos:
                writer.writerow([
                    weibo.get('source', '微博'),
                    weibo.get('author', ''),
                    weibo.get('title', ''),
                    datetime.fromtimestamp(weibo.get('publish_timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                    weibo.get('link', ''),
                    weibo.get('content', '')
                ])

        logger.info(f"微博已保存到：{filename}")

    def _parse_weibo_time(self, time_str: str) -> int:
        """
        解析微博时间字符串为时间戳

        Args:
            time_str: 时间字符串

        Returns:
            int: 时间戳
        """
        if not time_str:
            return int(time.time())

        now = datetime.now()

        # 处理各种格式
        if '秒前' in time_str:
            seconds = int(re.search(r'(\d+)', time_str).group(1))
            return int((now - timedelta(seconds=seconds)).timestamp())
        elif '分钟前' in time_str:
            minutes = int(re.search(r'(\d+)', time_str).group(1))
            return int((now - timedelta(minutes=minutes)).timestamp())
        elif '小时前' in time_str:
            hours = int(re.search(r'(\d+)', time_str).group(1))
            return int((now - timedelta(hours=hours)).timestamp())
        elif '今天' in time_str:
            time_part = time_str.replace('今天', '').strip()
            try:
                t = datetime.strptime(time_part, '%H:%M')
                return now.replace(hour=t.hour, minute=t.minute).timestamp()
            except:
                return int(now.timestamp())
        elif '昨天' in time_str:
            time_part = time_str.replace('昨天', '').strip()
            try:
                t = datetime.strptime(time_part, '%H:%M')
                yesterday = now - timedelta(days=1)
                return yesterday.replace(hour=t.hour, minute=t.minute).timestamp()
            except:
                return int((now - timedelta(days=1)).timestamp())
        else:
            # 标准格式：MM 月 DD 日 HH:mm 或 YYYY-MM-DD
            for fmt in ['%m 月%d 日 %H:%M', '%Y-%m-%d %H:%M', '%Y/%m/%d %H:%M']:
                try:
                    return int(datetime.strptime(time_str, fmt).timestamp())
                except:
                    continue

        return int(time.time())
