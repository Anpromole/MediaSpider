#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号爬虫核心模块
==================

提供微信公众号文章爬取的核心功能，
不依赖于任何GUI界面，可以被导入到任何项目中使用。

核心功能:
    1. 自动登录 - 自动获取token和cookie
    2. 批量爬取 - 支持多公众号、时间范围筛选的批量爬取
    3. 数据存储 - 支持CSV和SQLite数据库存储
    4. 内容解析 - 解析文章内容、摘要等

版本: 1.0
"""

__version__ = "1.0"
__author__ = "seanzhang-zhichen"

from .login import WeChatSpiderLogin
from .scraper import WeChatScraper, BatchWeChatScraper
from .utils import get_timestamp, format_time 