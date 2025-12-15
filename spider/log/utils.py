#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
工具模块
======================

提供各种通用工具函数和日志配置。

版本: 2.0
"""

import os
import sys
from loguru import logger

def setup_logger(log_file=None, log_level="INFO"):
    """
    设置日志记录器
    
    参数:
        log_file (str, optional): 日志文件路径，默认为None（只输出到控制台）
        log_level (str, optional): 日志级别，默认为INFO
    
    返回:
        logger: 配置好的logger实例
    """
    # 移除默认处理器
    logger.remove()
    
    # 添加控制台处理器
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
        level=log_level
    )
    
    # 如果提供了日志文件路径，添加文件处理器
    if log_file:
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        logger.add(
            log_file,
            rotation="10 MB",  # 每个日志文件最大10MB
            retention="1 week",  # 保留1周的日志
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
            level=log_level
        )
    
    return logger

# 初始化默认日志配置
logger = setup_logger() 