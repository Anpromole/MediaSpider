#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据库接口定义
===============

定义所有数据库操作的抽象接口，作为不同数据库实现的基类。
"""

import abc
from typing import List, Dict, Any, Optional

# 数据库接口抽象类
class DatabaseInterface(abc.ABC):
    """数据库接口抽象类，定义所有数据库操作的接口"""
    
    @abc.abstractmethod
    def init_database(self) -> None:
        """初始化数据库结构"""
        pass
    
    @abc.abstractmethod
    def save_account(self, 
                    name: str, 
                    platform: str, 
                    account_id: Optional[str] = None, 
                    details: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """
        保存账号信息
        
        Args:
            name: 账号名称
            platform: 平台类型（如 wechat, weibo 等）
            account_id: 平台上的账号ID
            details: 其他账号详情
            
        Returns:
            str: 数据库中的账号ID
        """
        pass
    
    @abc.abstractmethod
    def get_account(self, 
                   id: Optional[str] = None, 
                   name: Optional[str] = None, 
                   platform: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        获取账号信息
        
        Args:
            id: 数据库中的账号ID
            name: 账号名称
            platform: 平台类型
            
        Returns:
            Dict: 账号信息
        """
        pass
    
    @abc.abstractmethod
    def save_article(self, 
                    account_id: str, 
                    title: str, 
                    url: str, 
                    publish_time: Optional[str] = None, 
                    content: Optional[str] = None, 
                    details: Optional[Dict[str, Any]] = None,
                    summary: Optional[str] = None) -> bool:
        """
        保存文章
        
        Args:
            account_id: 账号ID
            title: 文章标题
            url: 文章URL
            publish_time: 发布时间
            content: 文章内容
            details: 其他详情
            summary: 文章摘要
            
        Returns:
            bool: 是否保存成功
        """
        pass
    
    @abc.abstractmethod
    def get_articles(self, 
                    account_id: Optional[str] = None, 
                    platform: Optional[str] = None,
                    start_date: Optional[str] = None, 
                    end_date: Optional[str] = None, 
                    keywords: Optional[List[str]] = None, 
                    limit: int = 100, 
                    offset: int = 0) -> List[Dict[str, Any]]:
        """
        查询文章
        
        Args:
            account_id: 账号ID
            platform: 平台类型
            start_date: 开始日期
            end_date: 结束日期
            keywords: 关键词列表
            limit: 返回数量限制
            offset: 偏移量
            
        Returns:
            List[Dict]: 文章列表
        """
        pass
    
    @abc.abstractmethod
    def count_articles(self, 
                      account_id: Optional[str] = None, 
                      platform: Optional[str] = None) -> int:
        """
        统计文章数量
        
        Args:
            account_id: 账号ID
            platform: 平台类型
            
        Returns:
            int: 文章数量
        """
        pass
    
    @abc.abstractmethod
    def get_article_by_id(self, article_id: str) -> Optional[Dict[str, Any]]:
        """
        根据ID获取单篇文章
        
        Args:
            article_id: 文章ID
            
        Returns:
            Dict[str, Any] or None: 文章信息，不存在则返回None
        """
        pass
    
    @abc.abstractmethod
    def update_article_summary(self, article_id: str, summary: str) -> bool:
        """
        更新文章摘要
        
        Args:
            article_id: 文章ID
            summary: 文章摘要内容
            
        Returns:
            bool: 更新是否成功
        """
        pass
    
    @abc.abstractmethod
    def get_article_summary(self, article_id: str) -> Optional[str]:
        """
        获取文章摘要
        
        Args:
            article_id: 文章ID
            
        Returns:
            Optional[str]: 文章摘要内容，不存在则返回None
        """
        pass
    
    @abc.abstractmethod
    def get_platforms(self) -> List[str]:
        """
        获取所有平台类型
        
        Returns:
            List[str]: 平台类型列表
        """
        pass
    
    @abc.abstractmethod
    def get_accounts_by_platform(self, platform: str) -> List[Dict[str, Any]]:
        """
        获取指定平台的所有账号
        
        Args:
            platform: 平台类型
            
        Returns:
            List[Dict]: 账号列表
        """
        pass 