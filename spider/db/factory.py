#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
数据库工厂
=========

用于创建不同类型的数据库实例的工厂类。
"""

from .interface import DatabaseInterface
from .sqlite import SQLiteDatabase
from .mysql import MySQLDatabase


class DatabaseFactory:
    """数据库工厂类，用于创建不同类型的数据库实例"""
    
    @staticmethod
    def create_database(db_type: str = 'sqlite', **kwargs) -> DatabaseInterface:
        """
        创建数据库实例
        
        Args:
            db_type: 数据库类型，如 'sqlite', 'mysql', 'mongodb' 等
            **kwargs: 数据库连接参数
            
        Returns:
            DatabaseInterface: 数据库实例
        """
        if db_type.lower() == 'sqlite':
            db_file = kwargs.get('db_file', 'content_spider.db')
            return SQLiteDatabase(db_file)
        elif db_type.lower() == 'mysql':
            # MySQL连接参数
            host = kwargs.get('host', 'localhost')
            port = kwargs.get('port', 3306)
            user = kwargs.get('user', 'root')
            password = kwargs.get('password', '')
            database = kwargs.get('database', 'content_spider')
            
            try:
                return MySQLDatabase(host, port, user, password, database)
            except ImportError as e:
                raise ValueError(f"无法初始化MySQL数据库: {e}")
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}") 