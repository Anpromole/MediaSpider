#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
RSS 新闻采集模块
================
提供 RSS Feed 解析和新闻采集功能。

主要功能:
    1. RSS 源解析 - 解析 RSS/Atom Feed
    2. 关键词过滤 - 按关键词筛选新闻
    3. 日期过滤 - 按日期范围筛选
"""

import os
import csv
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from bs4 import BeautifulSoup

try:
    import feedparser
except ImportError:
    feedparser = None
    print("警告：feedparser 未安装，请运行：pip install feedparser")

# 导入日志模块
from spider.log.utils import logger


class RSSCollector:
    """RSS 新闻采集器"""

    def __init__(self):
        """初始化采集器"""
        self.keep_running = True
        self.sources = []

    def stop(self):
        """停止采集"""
        logger.warning("收到停止指令，正在终止 RSS 采集任务...")
        self.keep_running = False

    def reset_stop(self):
        """重置停止标志"""
        self.keep_running = True

    def add_source(self, name: str, url: str):
        """
        添加 RSS 源

        Args:
            name: 源名称
            url: RSS Feed URL
        """
        self.sources.append({'name': name, 'url': url})

    def set_sources(self, sources: List[Dict]):
        """
        批量设置 RSS 源

        Args:
            sources: 源列表，每项包含 name 和 url
        """
        self.sources = sources

    def fetch(self, keyword: str = None, pages: int = 1,
              start_date: str = None, end_date: str = None,
              progress_callback=None) -> List[Dict]:
        """
        采集 RSS 新闻

        Args:
            keyword: 关键词过滤
            pages: 每个源最多采集条目数（0 表示不限制）
            start_date: 开始日期 YYYY-MM-DD
            end_date: 结束日期 YYYY-MM-DD
            progress_callback: 进度回调

        Returns:
            list: 新闻列表
        """
        if feedparser is None:
            logger.error("feedparser 未安装，无法采集 RSS")
            return []

        logger.info(f"开始 RSS 采集，关键词：{keyword or '无'}")
        self.reset_stop()

        all_news = []

        for i, source in enumerate(self.sources):
            if not self.keep_running:
                break

            logger.info(f"正在采集：{source['name']} - {source['url']}")

            try:
                feed = feedparser.parse(source['url'])

                entries = feed.entries[:pages] if pages > 0 else feed.entries

                for entry in entries:
                    if not self.keep_running:
                        break

                    title = getattr(entry, 'title', '')

                    # 关键词过滤
                    if keyword and keyword not in title:
                        continue

                    # 日期解析
                    pub_date = self._parse_date(entry)

                    # 日期范围过滤
                    if start_date or end_date:
                        article_date = pub_date.date()
                        if start_date:
                            start = datetime.strptime(start_date, '%Y-%m-%d').date()
                            if article_date < start:
                                continue
                        if end_date:
                            end = datetime.strptime(end_date, '%Y-%m-%d').date()
                            if article_date > end:
                                continue

                    # 提取内容
                    news = {
                        'title': title,
                        'content': self._clean_html(getattr(entry, 'summary', getattr(entry, 'description', ''))),
                        'link': getattr(entry, 'link', ''),
                        'source': source['name'],
                        'publish_timestamp': int(pub_date.timestamp()),
                        'author': getattr(entry, 'author', '')
                    }

                    if news['title'] and news['link']:
                        all_news.append(news)

            except Exception as e:
                logger.error(f"采集 RSS 源 {source['name']} 失败：{e}")

            if progress_callback:
                progress_callback(i + 1, len(self.sources), f"已采集 {len(all_news)} 条新闻")

        logger.info(f"RSS 采集完成，共获取 {len(all_news)} 条新闻")
        return all_news

    def _parse_date(self, entry) -> datetime:
        """解析发布日期"""
        # 尝试多种日期字段
        for field in ['published_parsed', 'updated_parsed', 'created_parsed']:
            if hasattr(entry, field) and entry[field]:
                try:
                    return datetime(*entry[field][:6])
                except (TypeError, IndexError):
                    pass

        # 尝试字符串格式
        for field in ['published', 'updated', 'created']:
            if hasattr(entry, field) and entry[field]:
                date_str = entry[field]
                for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%d', '%a, %d %b %Y %H:%M:%S', '%Y/%m/%d']:
                    try:
                        return datetime.strptime(date_str, fmt)
                    except:
                        continue

        return datetime.now()

    def _clean_html(self, text: str) -> str:
        """清理 HTML 标签"""
        if not text:
            return ""
        soup = BeautifulSoup(text, 'lxml')
        return soup.get_text(strip=True)

    def save_to_csv(self, news_list: List[Dict], filename: str):
        """
        保存新闻到 CSV 文件

        Args:
            news_list: 新闻列表
            filename: 文件名
        """
        if not news_list:
            logger.warning("没有新闻数据可保存")
            return

        os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)

        with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
            writer = csv.writer(f)
            writer.writerow(['来源', '作者', '标题', '发布时间', '链接', '内容'])

            for news in news_list:
                writer.writerow([
                    news.get('source', 'RSS'),
                    news.get('author', ''),
                    news.get('title', ''),
                    datetime.fromtimestamp(news.get('publish_timestamp', 0)).strftime('%Y-%m-%d %H:%M:%S'),
                    news.get('link', ''),
                    news.get('content', '')
                ])

        logger.info(f"新闻已保存到：{filename}")
