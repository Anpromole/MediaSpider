#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号爬虫运行模块
======================
提供微信公众号爬取功能的接口，包括登录、单个账号爬取和批量爬取功能。
支持爬取文章并生成 PDF 文件（基于 Playwright 渲染动态内容）。
可以作为库被导入使用或通过命令行工具调用。

版本: 2.6 (新增：支持任务中断停止功能)
"""

import os
import sys
import time
import json
import re
import urllib.parse
from datetime import datetime, timedelta

# 导入日志模块
from spider.log.utils import logger

# 导入爬虫模块
from .login import WeChatSpiderLogin, quick_login
from .scraper import WeChatScraper, BatchWeChatScraper
from spider.db.factory import DatabaseFactory

# 新增：PDF 生成相关依赖
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError


class WeChatSpiderRunner:
    """微信爬虫运行器，封装爬虫的主要功能（新增 PDF 生成与中断控制）"""

    def __init__(self):
        """初始化爬虫运行器"""
        self.login_manager = WeChatSpiderLogin()
        # 新增：运行控制标志位
        self.keep_running = True

    def stop(self):
        """停止当前任务"""
        logger.warning("收到停止指令，正在终止任务...")
        self.keep_running = False

    def reset_stop(self):
        """重置运行状态"""
        self.keep_running = True

    def _clean_filename(self, filename):
        """清理文件名，移除非法字符并限制长度"""
        # 移除 Windows/Linux 非法字符
        illegal_chars = r'[\\/:*?"<>|]'
        cleaned = re.sub(illegal_chars, '_', filename.strip())
        # 限制最大长度（避免系统限制）
        return cleaned[:80]

    def _generate_article_pdf(self, article_url, pdf_path, cookies=None, wait_time=10):
        """
        生成微信公众号文章的 PDF（最终版：修复所有参数错误 + 图片懒加载问题）
        """
        # 如果已被终止，直接返回
        if not self.keep_running:
            return False

        try:
            with sync_playwright() as p:
                # 启动浏览器（优化配置：强制允许图片加载、禁用资源拦截）
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--no-sandbox',  # 兼容 Linux 无沙箱环境
                        '--disable-blink-features=AutomationControlled',  # 规避自动化检测
                        '--disable-web-security',  # 兼容跨域 cookie/图片
                        '--disable-features=ImageLazyLoading',  # 禁用懒加载（关键！）
                        '--allow-running-insecure-content',  # 允许http图片（部分公众号图片是http）
                        '--disable-extensions',  # 禁用扩展，避免干扰
                        '--disable-dev-shm-usage',  # 解决内存不足问题
                        '--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
                    ],
                    handle_sigint=False
                )

                # 创建浏览器上下文
                context = browser.new_context(
                    viewport={'width': 1280, 'height': 2000},  # 增大可视区域，减少懒加载触发
                    extra_http_headers={
                        'Accept-Language': 'zh-CN,zh;q=0.9',
                        'Referer': 'https://mp.weixin.qq.com/',
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Cache-Control': 'no-cache',
                        'Pragma': 'no-cache'
                    },
                    locale='zh-CN',
                    geolocation={'latitude': 39.9042, 'longitude': 116.4074}  # 模拟国内位置
                )

                # 导入登录态 cookie
                if cookies:
                    cookie_list = []
                    if isinstance(cookies, str):
                        # 解析 cookie 字符串为 Playwright 格式
                        for cookie_str in cookies.split('; '):
                            if '=' not in cookie_str:
                                continue
                            name, value = cookie_str.split('=', 1)
                            cookie_list.append({
                                'name': name.strip(),
                                'value': value.strip(),
                                'domain': '.weixin.qq.com',
                                'path': '/',
                                'httpOnly': True,
                                'secure': True,
                                'sameSite': 'None'
                            })
                    elif isinstance(cookies, list):
                        cookie_list = cookies

                    if cookie_list:
                        context.add_cookies(cookie_list)

                # 访问文章 URL
                page = context.new_page()
                page.route("**/*", lambda route: route.continue_())

                page.goto(
                    article_url,
                    wait_until='load',
                    timeout=120000
                )

                # 步骤1：等待核心内容区域加载
                try:
                    page.wait_for_selector('#js_content', timeout=30000)
                except PlaywrightTimeoutError:
                    pass

                # 步骤2：模拟页面滚动
                scroll_height = page.evaluate("document.documentElement.scrollHeight")
                for i in range(0, int(scroll_height), 500):
                    # 中断检查：如果用户点击停止，在滚动过程中退出
                    if not self.keep_running:
                        browser.close()
                        return False
                    page.evaluate(f"window.scrollTo(0, {i})")
                    page.wait_for_timeout(500)

                page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                page.wait_for_timeout(1000)

                # 步骤4：显式等待所有图片元素加载完成
                try:
                    page.wait_for_selector('#js_content img', state='attached', timeout=wait_time * 1000)
                except PlaywrightTimeoutError:
                    pass

                # 步骤5：基础等待（兜底）
                page.wait_for_timeout(wait_time * 1000)

                # 生成 PDF
                page.pdf(
                    path=pdf_path,
                    format='A4',
                    margin={'top': '15mm', 'bottom': '15mm', 'left': '10mm', 'right': '10mm'},
                    print_background=True,
                    display_header_footer=False,
                    scale=1.0
                )

                browser.close()
                logger.info(f"PDF 生成成功: {pdf_path}")
                return True

        except Exception as e:
            logger.error(f"生成 PDF 失败 [{article_url}]: {str(e)}")
            if os.path.exists(pdf_path):
                os.remove(pdf_path)
            return False

    def login(self):
        """登录微信公众平台并获取 token 和 cookie"""
        logger.info("正在登录微信公众平台...")
        token, cookies, headers = quick_login()

        if not token or not cookies or not headers:
            logger.error("登录失败")
            return False

        logger.success(f"登录成功！")
        return True

    def search_account(self, name, output_file=None):
        """搜索公众号（统一返回列表格式）"""
        logger.info(f"搜索公众号: {name}")
        if not self.login_manager.is_logged_in():
            logger.error("未登录或登录已过期，请先登录")
            return []
        token = self.login_manager.get_token()
        headers = self.login_manager.get_headers()
        scraper = WeChatScraper(token, headers)
        results = scraper.search_account(name)
        if not results:
            logger.warning(f"未找到匹配的公众号: {name}")
            return []
        return results

    def scrape_single_account(
            self, name, pages=10, start_date=None, end_date=None, include_content=False,
            interval=10, output_file=None, use_db=False, db_type="sqlite",
            generate_pdf=False, pdf_output_dir=None,
            progress_callback=None, keywords=None
    ):
        """
        爬取单个公众号（支持中断）
        """
        self.reset_stop()  # 确保开始前状态重置
        logger.info(f"爬取公众号: {name}")
        keywords = keywords or []

        if not self.login_manager.is_logged_in():
            return {"success": False, "msg": "未登录或登录已过期", "data": {}}

        token = self.login_manager.get_token()
        headers = self.login_manager.get_headers()
        scraper = WeChatScraper(token, headers)

        results = scraper.search_account(name)
        if not results:
            return {"success": False, "msg": "未找到匹配的公众号", "data": {}}

        account = results[0]

        # 进度回调（页面级）
        def page_progress_callback(current, total):
            if not self.keep_running: return  # 中断时不回调
            if progress_callback:
                page_percent = int(current / total * 30)
                progress_callback(page_percent, f"获取文章列表 {current}/{total} 页")

        scraper.set_callback('progress', page_progress_callback)

        # 获取文章列表
        articles = scraper.get_account_articles(
            account['wpub_name'],
            account['wpub_fakid'],
            pages
        )

        # 1. 按日期过滤
        filtered_articles = []
        if start_date and end_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d").date()
            end_dt = datetime.strptime(end_date, "%Y-%m-%d").date()
            for article in articles:
                try:
                    publish_date = datetime.fromtimestamp(article.get('publish_timestamp', 0)).date()
                    if start_dt <= publish_date <= end_dt:
                        filtered_articles.append(article)
                except:
                    pass
        else:
            filtered_articles = articles

        # 2. 按关键词筛选
        if keywords:
            keyword_filtered = []
            for article in filtered_articles:
                title = article.get('title', '').lower()
                digest = article.get('digest', '').lower()
                match = False
                for kw in keywords:
                    if kw.lower() in title or kw.lower() in digest:
                        match = True
                        break
                if match:
                    keyword_filtered.append(article)
            filtered_articles = keyword_filtered

        # PDF 输出设置
        pdf_dir = None
        login_cookies = headers.get('cookie', '')
        if generate_pdf:
            if not pdf_output_dir:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_output_dir = f"{self._clean_filename(account['wpub_name'])}_{timestamp}_pdf"
            pdf_dir = pdf_output_dir
            os.makedirs(pdf_dir, exist_ok=True)

        # 获取文章内容 + 生成 PDF (核心循环，支持中断)
        final_processed_articles = []  # 用于保存实际处理完成的文章

        if include_content or generate_pdf:
            total_articles = len(filtered_articles)
            if total_articles == 0:
                if progress_callback: progress_callback(100, "无符合条件的文章")
                return {"success": True, "msg": "无符合条件的文章", "data": {"count": 0}}

            for i, article in enumerate(filtered_articles):
                # ------------------- 中断检查点 -------------------
                if not self.keep_running:
                    logger.warning("用户停止了爬取任务，正在保存已完成的数据...")
                    if progress_callback:
                        progress_callback(int(30 + (i) / total_articles * 70), "任务已手动停止")
                    break
                # ------------------------------------------------

                article_title = article.get('title', f"未知文章_{i + 1}")
                if progress_callback:
                    content_percent = int(30 + (i + 1) / total_articles * 70)
                    progress_callback(content_percent, f"处理第 {i + 1}/{total_articles} 篇：{article_title}")

                # 获取内容
                if include_content:
                    article = scraper.get_article_content_by_url(article)

                # 生成 PDF
                if generate_pdf and article.get('link'):
                    cleaned_title = self._clean_filename(article_title)
                    pdf_path = os.path.join(pdf_dir, f"{cleaned_title}.pdf")
                    counter = 1
                    while os.path.exists(pdf_path):
                        pdf_path = os.path.join(pdf_dir, f"{cleaned_title}_{counter}.pdf")
                        counter += 1

                    success = self._generate_article_pdf(article['link'], pdf_path, login_cookies)
                    if success:
                        article['pdf_path'] = pdf_path
                    else:
                        article['pdf_path'] = ''

                final_processed_articles.append(article)

                if i < len(filtered_articles) - 1:
                    time.sleep(interval)
        else:
            final_processed_articles = filtered_articles

        # 保存结果 (即使中断，也保存已获取的部分)
        if output_file:
            output_path = output_file
        else:
            if not pdf_output_dir:
                account_dir = self._clean_filename(account['wpub_name'])
                os.makedirs(account_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = os.path.join(account_dir, f"{account['wpub_name']}_{timestamp}.csv")
            else:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                output_path = os.path.join(pdf_output_dir, f"{account['wpub_name']}_{timestamp}.csv")

        scraper.save_articles_to_csv(final_processed_articles, output_path)

        msg_prefix = "爬取已停止" if not self.keep_running else "爬取完成"
        return {
            "success": True,
            "msg": f"{msg_prefix}，已处理 {len(final_processed_articles)}/{len(filtered_articles)} 篇文章",
            "data": {"count": len(final_processed_articles), "path": output_path}
        }

    def batch_scrape(
            self, accounts, pages=10, start_date=None, end_date=None, include_content=False,
            interval=10, threads=3, output_dir=None, use_db=False, db_type="sqlite",
            generate_pdf=False, pdf_output_dir=None, progress_callback=None, keywords=None
    ):
        """
        批量爬取多个公众号（支持中断）
        """
        self.reset_stop()
        logger.info(f"批量爬取公众号，共 {len(accounts)} 个账号")
        keywords = keywords or []

        if not self.login_manager.is_logged_in():
            return {"success": False, "msg": "未登录或登录已过期", "data": {}}

        token = self.login_manager.get_token()
        headers = self.login_manager.get_headers()

        # 批量爬虫回调
        def internal_progress_callback(current, total):
            if self.keep_running and progress_callback:
                progress_callback(int(current / total * 40), f"已完成 {current}/{total} 个公众号")

        batch_scraper = BatchWeChatScraper()
        batch_scraper.set_callback('progress_updated', internal_progress_callback)

        # 注意：这里调用的是 scraper 的批量方法，如果 scraper 内部不支持中断，
        # 我们只能在文章获取完毕后的 PDF 生成阶段进行中断控制。
        # 如果需要完全中断请求，需要修改 scraper 源码支持传入 stop_signal。

        output_dir = output_dir or "results"
        os.makedirs(output_dir, exist_ok=True)

        batch_pdf_dir = None
        if generate_pdf:
            batch_pdf_dir = pdf_output_dir or os.path.join(output_dir, "wechat_batch_pdf")
            os.makedirs(batch_pdf_dir, exist_ok=True)

        config = {
            'accounts': accounts,
            'start_date': start_date,
            'end_date': end_date,
            'token': token,
            'headers': headers,
            'max_pages_per_account': pages,
            'request_interval': interval,
            'use_threading': threads > 1,
            'max_workers': threads,
            'include_content': include_content,
            'output_file': os.path.join(output_dir, f"wechat_articles_{int(time.time())}.csv")
        }

        # 第一阶段：获取文章列表（通常较快，暂不支持细粒度中断）
        logger.info("开始获取批量文章列表...")
        articles = batch_scraper.start_batch_scrape(config)

        # 关键词筛选
        if keywords:
            keyword_filtered = []
            for article in articles:
                title = article.get('title', '').lower()
                digest = article.get('digest', '').lower()
                match = False
                for kw in keywords:
                    if kw.lower() in title or kw.lower() in digest:
                        match = True
                        break
                if match:
                    keyword_filtered.append(article)
            articles = keyword_filtered

        # 第二阶段：批量生成 PDF (支持中断)
        processed_articles = []
        if generate_pdf and articles and batch_pdf_dir:
            total_articles = len(articles)
            logger.info(f"开始为 {total_articles} 篇文章生成 PDF...")

            for i, article in enumerate(articles):
                # ------------------- 中断检查点 -------------------
                if not self.keep_running:
                    logger.warning("批量任务被用户停止")
                    break
                # ------------------------------------------------

                if progress_callback:
                    pdf_percent = int(40 + (i + 1) / total_articles * 60)
                    progress_callback(pdf_percent, f"生成 PDF {i + 1}/{total_articles} 篇")

                article_url = article.get('link')
                account_name = article.get('name', '未知账号')

                if article_url:
                    account_pdf_dir = os.path.join(batch_pdf_dir, self._clean_filename(account_name))
                    os.makedirs(account_pdf_dir, exist_ok=True)

                    cleaned_title = self._clean_filename(article.get('title', f"article_{i + 1}"))
                    pdf_path = os.path.join(account_pdf_dir, f"{cleaned_title}.pdf")
                    counter = 1
                    while os.path.exists(pdf_path):
                        pdf_path = os.path.join(account_pdf_dir, f"{cleaned_title}_{counter}.pdf")
                        counter += 1

                    success = self._generate_article_pdf(article_url, pdf_path, headers.get('cookie', ''))
                    if success:
                        article['pdf_path'] = pdf_path

                processed_articles.append(article)
                if i < len(articles) - 1:
                    time.sleep(interval / 2)
        else:
            processed_articles = articles

        msg_prefix = "批量任务已停止" if not self.keep_running else "批量爬取完成"
        return {
            "success": True,
            "msg": f"{msg_prefix}，共获取 {len(processed_articles)} 篇文章",
            "data": {"count": len(processed_articles), "path": config['output_file']}
        }


# 向后兼容接口
def login(): return WeChatSpiderRunner().login()


def search(name, output_file=None): return WeChatSpiderRunner().search_account(name, output_file)


def scrape_account(name, **kwargs): return WeChatSpiderRunner().scrape_single_account(name, **kwargs)


def batch_scrape(accounts_file, **kwargs): return WeChatSpiderRunner().batch_scrape(accounts_file, **kwargs)