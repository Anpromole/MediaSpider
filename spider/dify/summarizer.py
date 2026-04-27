#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
新闻总结模块
"""

from datetime import datetime
from typing import List, Dict
from thefuzz import fuzz

from spider.log.utils import logger
from .client import DifyClient


class NewsSummarizer:
    """新闻总结器"""

    def __init__(self, dify_client: DifyClient):
        """
        初始化总结器

        Args:
            dify_client: Dify 客户端
        """
        self.client = dify_client

    def deduplicate(self, news_list: List[Dict],
                    threshold: float = 0.75) -> List[Dict]:
        """
        去重相似新闻

        Args:
            news_list: 新闻列表
            threshold: 相似度阈值 (0-1)

        Returns:
            list: 去重后的新闻列表
        """
        if not news_list:
            return []

        deduplicated = []
        threshold_int = int(threshold * 100)

        for news in news_list:
            is_duplicate = False

            for existing in deduplicated:
                title_similarity = fuzz.ratio(news['title'], existing['title'])

                if title_similarity >= threshold_int:
                    is_duplicate = True
                    # 保留内容更长的
                    if len(news.get('content', '')) > len(existing.get('content', '')):
                        deduplicated.remove(existing)
                        deduplicated.append(news)
                    break

            if not is_duplicate:
                deduplicated.append(news)

        logger.info(f"新闻去重：{len(news_list)} -> {len(deduplicated)} 条")
        return deduplicated

    def generate_briefing(self, news_list: List[Dict],
                          topic: str) -> str:
        """
        生成每日简报

        Args:
            news_list: 新闻列表
            topic: 主题

        Returns:
            str: 简报内容
        """
        if not news_list:
            return f"今日没有采集到关于「{topic}」的新闻。"

        parts = []
        parts.append(f"# 「{topic}」每日新闻简报")
        parts.append(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
        parts.append(f"新闻总数：{len(news_list)} 条\n")

        # 按日期分组
        news_by_date = {}
        for news in news_list:
            date_str = datetime.fromtimestamp(
                news.get('publish_timestamp', 0)
            ).strftime('%Y-%m-%d')
            if date_str not in news_by_date:
                news_by_date[date_str] = []
            news_by_date[date_str].append(news)

        for date_str, items in sorted(news_by_date.items(), reverse=True):
            parts.append(f"## {date_str}")
            for i, news in enumerate(items, 1):
                parts.append(f"{i}. **{news['title']}**")
                parts.append(f"   来源：{news.get('source', '未知')}")
                if news.get('content') and news['content'] != news['title']:
                    summary = news['content'][:200]
                    if len(news['content']) > 200:
                        summary += "..."
                    parts.append(f"   摘要：{summary}")
                parts.append("")

        return "\n".join(parts)

    def ai_summarize(self, news_list: List[Dict],
                     topic: str) -> str:
        """
        使用 Dify 进行 AI 总结

        Args:
            news_list: 新闻列表
            topic: 主题

        Returns:
            str: AI 总结内容
        """
        if not news_list:
            return f"今日没有采集到关于「{topic}」的新闻。"

        # 构建新闻内容
        news_content = []
        for i, news in enumerate(news_list[:20], 1):
            content = news.get('content', news.get('title', ''))[:300]
            news_content.append(
                f"{i}. {news['title']} (来源：{news.get('source', '未知')})\n"
                f"   {content}"
            )

        content = "\n\n".join(news_content)

        prompt = f"""你是一名专业的新闻分析师。请对以下关于「{topic}」的新闻进行总结：

{content}

请生成一份结构化的总结报告，包括：
1. 核心事件概述（100 字以内）
2. 各新闻要点（每条 50 字以内）
3. 事件发展趋势或影响分析（如果有）

要求：语言简洁、重点突出、客观准确。"""

        answer = self.client.chat(prompt)
        return answer or self.generate_briefing(news_list, topic)

    def process_and_upload(self, news_list: List[Dict], topic: str,
                           dataset_id: str) -> bool:
        """
        处理新闻并上传到 Dify 知识库

        Args:
            news_list: 新闻列表
            topic: 主题
            dataset_id: 知识库 ID

        Returns:
            bool: 是否成功
        """
        if not news_list:
            logger.warning("没有新闻可处理")
            return False

        # 去重
        news_list = self.deduplicate(news_list)

        # 生成简报
        briefing = self.generate_briefing(news_list, topic)

        # AI 总结
        ai_summary = self.ai_summarize(news_list, topic)

        # 合并内容
        full_content = f"{briefing}\n\n{'='*50}\n\n# AI 智能总结\n\n{ai_summary}"

        # 上传到 Dify
        name = f"{topic}_每日简报_{datetime.now().strftime('%Y%m%d')}"
        success = self.client.upload_document(dataset_id, full_content, name)

        return success
