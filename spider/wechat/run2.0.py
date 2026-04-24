#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号爬虫运行模块
======================

提供微信公众号爬取功能的接口，包括登录、单个账号爬取和批量爬取功能。
可以作为库被导入使用或通过命令行工具调用。

版本: 2.0
"""

import os
import sys
import time
import json
from datetime import datetime, timedelta

# 导入日志模块
from spider.log.utils import logger

# 导入爬虫模块
from .login import WeChatSpiderLogin, quick_login
from .scraper import WeChatScraper, BatchWeChatScraper
from spider.db.factory import DatabaseFactory


class WeChatSpiderRunner:
    """微信爬虫运行器，封装爬虫的主要功能"""
    
    def __init__(self):
        """初始化爬虫运行器"""
        self.login_manager = WeChatSpiderLogin()
    
    def login(self):
        """登录微信公众平台并获取token和cookie"""
        logger.info("正在登录微信公众平台...")
        token, cookies, headers = quick_login()
        
        if not token or not cookies or not headers:
            logger.error("登录失败")
            return False
        
        logger.success(f"登录成功！")
        logger.debug(f"Token: {token[:8]}...{token[-4:]}")
        logger.debug(f"Cookie: {len(headers['cookie'])} 个字符")
        logger.info("登录信息已保存到缓存文件")
        
        return True
    
    def search_account(self, name, output_file=None):
        """搜索公众号"""
        logger.info(f"搜索公众号: {name}")
        
        # 检查登录状态
        if not self.login_manager.is_logged_in():
            logger.error("未登录或登录已过期，请先登录")
            return None
        
        token = self.login_manager.get_token()
        headers = self.login_manager.get_headers()
        
        # 创建爬虫实例
        scraper = WeChatScraper(token, headers)
        
        # 搜索公众号
        results = scraper.search_account(name)
        
        if not results:
            logger.warning(f"未找到匹配的公众号: {name}")
            return None
        
        logger.info(f"找到 {len(results)} 个匹配的公众号:")
        for i, account in enumerate(results):
            logger.info(f"{i+1}. {account['wpub_name']} (fakeid: {account['wpub_fakid']})")
        
        # 保存结果
        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"搜索结果已保存到: {output_file}")
        
        return results
    
    def scrape_single_account(self, name, pages=10, days=30, include_content=False, 
                              interval=10, output_file=None, use_db=False, db_type="sqlite"):
        """爬取单个公众号"""
        logger.info(f"爬取公众号: {name}")
        
        # 检查登录状态
        if not self.login_manager.is_logged_in():
            logger.error("未登录或登录已过期，请先登录")
            return False
        
        token = self.login_manager.get_token()
        headers = self.login_manager.get_headers()
        
        # 创建爬虫实例
        scraper = WeChatScraper(token, headers)
        
        # 搜索公众号
        logger.info(f"搜索公众号: {name}")
        results = scraper.search_account(name)
        
        if not results:
            logger.warning(f"未找到匹配的公众号: {name}")
            return False
        
        # 使用第一个匹配结果
        account = results[0]
        logger.info(f"使用公众号: {account['wpub_name']} (fakeid: {account['wpub_fakid']})")
        
        # 进度回调
        def progress_callback(current, total):
            logger.info(f"进度: {current}/{total} 页")
        
        scraper.set_callback('progress', progress_callback)
        
        # 获取文章列表
        logger.info(f"获取文章列表，最大 {pages} 页...")
        articles = scraper.get_account_articles(
            account['wpub_name'],
            account['wpub_fakid'],
            pages
        )
        
        logger.info(f"获取到 {len(articles)} 篇文章")
        
        # 按日期过滤
        if days:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            
            logger.info(f"过滤日期范围: {start_date} 至 {end_date}")
            filtered_articles = scraper.filter_articles_by_date(articles, start_date, end_date)
            logger.info(f"过滤后剩余 {len(filtered_articles)} 篇文章")
        else:
            filtered_articles = articles
            start_date = None
            end_date = None
        
        # 获取文章内容
        if include_content:
            logger.info("获取文章内容...")
            for i, article in enumerate(filtered_articles):
                logger.info(f"获取第 {i+1}/{len(filtered_articles)} 篇文章内容...")
                article = scraper.get_article_content_by_url(article)
                
                # 请求间隔，避免被限制
                if i < len(filtered_articles) - 1:
                    time.sleep(interval)
        
        # 保存结果到CSV
        if output_file:
            output_path = output_file
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"{account['wpub_name']}_{timestamp}.csv"
        
        logger.info(f"保存结果到: {output_path}")
        success = scraper.save_articles_to_csv(filtered_articles, output_path)
        
        # 保存到数据库
        if use_db and filtered_articles:
            output_dir = os.path.dirname(output_path) or "."
            db_file = os.path.join(output_dir, "content_spider.db")
            
            # 使用工厂创建数据库实例
            try:
                db = DatabaseFactory.create_database(db_type, db_file=db_file)
                
                # 保存账号
                account_db_id = db.save_account(
                    name=account['wpub_name'],
                    platform='wechat',
                    account_id=account['wpub_fakid']
                )
                
                if account_db_id:
                    # 保存文章
                    logger.info(f"保存 {len(filtered_articles)} 篇文章到数据库...")
                    saved_count = 0
                    for article in filtered_articles:
                        success = db.save_article(
                            account_id=account_db_id,
                            title=article.get('title', ''),
                            url=article.get('link', ''),
                            publish_time=article.get('publish_time', ''),
                            content=article.get('content', ''),
                            details={
                                'digest': article.get('digest', ''),
                                'publish_timestamp': article.get('publish_timestamp', 0)
                            }
                        )
                        if success:
                            saved_count += 1
                    
                    logger.success(f"数据库保存完成，成功保存 {saved_count} 篇文章: {db_file}")
                else:
                    logger.error("保存账号失败，无法保存文章")
                    
            except ValueError as e:
                logger.error(f"数据库初始化失败: {e}")
                return False
        
        if success:
            logger.success(f"成功保存 {len(filtered_articles)} 篇文章")
            return True
        else:
            logger.error("保存失败")
            return False

    def batch_scrape(self, accounts_file, pages=10, days=30, include_content=False,
                    interval=10, threads=3, output_dir=None, use_db=False, db_type="sqlite"):
        """批量爬取多个公众号"""
        logger.info(f"批量爬取公众号，输入文件: {accounts_file}")
        
        # 读取公众号列表
        try:
            with open(accounts_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # 支持多种分隔符：换行、逗号、分号
            import re
            accounts = re.split(r'[\n\r,;，；、\s\t|]+', content.strip())
            accounts = [acc.strip() for acc in accounts if acc.strip()]
        except Exception as e:
            logger.error(f"读取公众号列表失败: {str(e)}")
            return False
        
        if not accounts:
            logger.warning("公众号列表为空")
            return False
        
        logger.info(f"共读取 {len(accounts)} 个公众号")
        
        # 检查登录状态
        if not self.login_manager.is_logged_in():
            logger.error("未登录或登录已过期，请先登录")
            return False
        
        token = self.login_manager.get_token()
        headers = self.login_manager.get_headers()
        
        # 创建批量爬虫实例
        batch_scraper = BatchWeChatScraper()
        
        # 设置回调函数
        def progress_callback(current, total):
            logger.info(f"进度: {current}/{total} 公众号")
        
        def account_status_callback(account_name, status, message):
            if status == 'start':
                logger.info(f"开始爬取: {account_name}")
            elif status == 'done':
                logger.info(f"完成爬取: {account_name}, {message}")
            elif status == 'skip':
                logger.warning(f"跳过爬取: {account_name}, {message}")
        
        def batch_completed_callback(total_articles):
            logger.success(f"批量爬取完成，总共获取 {total_articles} 篇文章")
        
        def error_callback(account_name, error_message):
            logger.error(f"爬取出错: {account_name}, {error_message}")
        
        batch_scraper.set_callback('progress_updated', progress_callback)
        batch_scraper.set_callback('account_status', account_status_callback)
        batch_scraper.set_callback('batch_completed', batch_completed_callback)
        batch_scraper.set_callback('error_occurred', error_callback)
        
        # 计算时间范围
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)
        
        # 确保输出目录存在
        output_dir = output_dir or "results"
        os.makedirs(output_dir, exist_ok=True)
        
        # 准备配置
        timestamp = int(time.time())
        config = {
            'accounts': accounts,
            'start_date': start_date.strftime('%Y-%m-%d'),
            'end_date': end_date.strftime('%Y-%m-%d'),
            'token': token,
            'headers': headers,
            'max_pages_per_account': pages,
            'request_interval': interval,
            'use_threading': threads > 1,
            'max_workers': threads,
            'include_content': include_content,
            'output_file': os.path.join(output_dir, f"wechat_articles.csv")
        }
        
        # 初始化数据库（如果需要）
        db = None
        if use_db:
            db_file = os.path.join(output_dir, "content_spider.db")
            # 使用工厂创建数据库实例
            try:
                db = DatabaseFactory.create_database(db_type, db_file=db_file)
                logger.info(f"使用 {db_type} 数据库: {db_file}")
            except ValueError as e:
                logger.error(f"数据库初始化失败: {e}")
                logger.info("将不保存到数据库")
                db = None
        
        # 开始爬取
        logger.info("\n开始批量爬取...")
        logger.info(f"时间范围: {start_date} 至 {end_date}")
        logger.info(f"每个公众号最多爬取 {pages} 页")
        logger.info(f"请求间隔: {interval} 秒")
        
        start_time = time.time()
        articles = batch_scraper.start_batch_scrape(config)
        end_time = time.time()
        
        # 保存到数据库
        if db and articles:
            logger.info(f"保存 {len(articles)} 篇文章到数据库...")
            saved_count = 0
            
            # 先保存所有账号
            for account_name in accounts:
                logger.info(f"保存账号: {account_name}")
                db.save_account(
                    name=account_name,
                    platform='wechat'
                )
            
            # 再保存文章
            for article in articles:
                account_name = article.get('name', '')
                account = db.get_account(name=account_name, platform='wechat')

                if not account:
                    logger.error(f"账号不存在: {account_name}")
                    continue
                    
                success = db.save_article(
                    account_id=account['id'],
                    title=article.get('title', ''),
                    url=article.get('link', ''),
                    publish_time=article.get('publish_time', ''),
                    content=article.get('content', ''),
                    details={
                        'digest': article.get('digest', ''),
                        'publish_timestamp': article.get('publish_timestamp', 0)
                    }
                )
                
                if success:
                    logger.success(f"成功保存文章: {article.get('title', '')}")
                    saved_count += 1
            
            logger.success(f"数据库保存完成，成功保存 {saved_count} 篇文章")
        
        logger.info(f"\n爬取完成，耗时 {end_time - start_time:.2f} 秒")
        logger.info(f"共获取 {len(articles)} 篇文章，已保存到 {config['output_file']}")
        
        if db:
            logger.info(f"数据库文件: {db_file}")
        
        return True


# 为了保持向后兼容性，提供一些直接可调用的函数
def login():
    """登录微信公众平台并获取token和cookie"""
    runner = WeChatSpiderRunner()
    return runner.login()


def search(name, output_file=None):
    """搜索公众号"""
    runner = WeChatSpiderRunner()
    return runner.search_account(name, output_file)


def scrape_account(name, **kwargs):
    """爬取单个公众号"""
    runner = WeChatSpiderRunner()
    return runner.scrape_single_account(name, **kwargs)


def batch_scrape(accounts_file, **kwargs):
    """批量爬取多个公众号"""
    runner = WeChatSpiderRunner()
    return runner.batch_scrape(accounts_file, **kwargs)
