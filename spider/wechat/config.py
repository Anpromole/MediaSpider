#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号爬虫 - 配置文件
========================

提供爬虫的各种配置参数，包括请求频率、重试策略等。
"""

# 爬取模式配置
FETCH_MODES = {
    'fast': '快速模式（使用偏移量顺序获取）',
    'date_range': '日期范围模式（使用二分查找定位）'
}

# 默认爬取模式
DEFAULT_FETCH_MODE = 'fast'

# 请求延迟配置（秒）
REQUEST_DELAY = {
    'fast': {
        'min': 3,
        'max': 5
    },
    'date_range': {
        'min': 15,
        'max': 25
    },
    'binary_search': {
        'min': 20,
        'max': 30
    }
}

# 重试配置
RETRY_CONFIG = {
    'max_retries': 3,
    'base_wait': 5,  # 基础等待时间（秒）
    'backoff_multiplier': 2,  # 退避倍数
    'freq_control_ret': 200013  # 频率限制错误码
}

# 分页配置
PAGE_CONFIG = {
    'page_size': 5,  # 每页文章数
    'max_pages': 100,  # 最大爬取页数
    'max_articles': 500  # 最大文章数
}

# 日期范围配置
DATE_RANGE_CONFIG = {
    'max_range_days': 365,  # 最大日期范围（天）
    'default_days': 30  # 默认日期范围（天）
}

# 代理 IP 配置（可通过环境变量或代码覆盖）
PROXY_CONFIG = {
    'enabled': False,
    'http': None,
    'https': None
}

# 批量爬取不同公众号之间的休息间隔（秒）
BATCH_INTER_ACCOUNT_DELAY = {
    'min': 15,
    'max': 35
}

