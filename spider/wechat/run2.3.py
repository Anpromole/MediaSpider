#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号爬虫运行模块
======================
提供微信公众号爬取功能的接口，包括登录、单个账号爬取和批量爬取功能。
支持爬取文章并生成 PDF 文件（基于 Playwright 渲染动态内容）。
可以作为库被导入使用或通过命令行工具调用。

版本: 2.5 (最终版：修复所有 PDF 生成参数错误 + 图片懒加载问题)
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
    """微信爬虫运行器，封装爬虫的主要功能（新增 PDF 生成）"""

    def __init__(self):
        """初始化爬虫运行器"""
        self.login_manager = WeChatSpiderLogin()

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
        :param article_url: 文章原始 URL
        :param pdf_path: PDF 保存路径
        :param cookies: 登录后的微信 cookie 字符串/列表
        :param wait_time: 基础页面渲染等待时间（秒）
        :return: 是否生成成功
        """
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

                # 创建浏览器上下文（移除所有无效参数）
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

                # 导入登录态 cookie（关键：微信文章需要登录才能访问）
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
                                'sameSite': 'None'  # 修复跨域 cookie 问题
                            })
                    elif isinstance(cookies, list):
                        cookie_list = cookies

                    if cookie_list:
                        context.add_cookies(cookie_list)
                        logger.debug(f"导入 {len(cookie_list)} 个登录 cookie")

                # 访问文章 URL（优化加载策略）
                page = context.new_page()
                # 确保所有资源（包括图片）都不被拦截
                page.route("**/*", lambda route: route.continue_())

                page.goto(
                    article_url,
                    wait_until='load',  # 等待页面完全加载
                    timeout=120000  # 延长超时时间到2分钟（应对慢网络）
                )

                # 步骤1：等待核心内容区域加载
                try:
                    page.wait_for_selector('#js_content', timeout=30000)
                    logger.debug("文章核心内容区域加载完成")
                except PlaywrightTimeoutError as e:
                    logger.warning(f"文章内容加载超时，但尝试继续生成 PDF: {e}")

                # 步骤2：模拟页面滚动，触发所有懒加载图片（关键修复！）
                logger.debug("模拟页面滚动，触发图片懒加载...")
                # 获取页面总高度
                scroll_height = page.evaluate("document.documentElement.scrollHeight")
                # 分段滚动（每次滚动500px，等待图片加载）
                for i in range(0, int(scroll_height), 500):
                    page.evaluate(f"window.scrollTo(0, {i})")
                    page.wait_for_timeout(500)  # 每滚动一次等待500ms

                # 步骤3：滚动到页面底部，确保最后一批图片加载
                page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                page.wait_for_timeout(1000)

                # 步骤4：显式等待所有图片元素加载完成
                logger.debug("等待所有图片元素加载完成...")
                try:
                    # 等待所有 img 元素加载（包括懒加载的）
                    page.wait_for_selector('#js_content img', state='attached', timeout=wait_time * 1000)
                    # 验证图片是否加载完成（通过 naturalWidth 判断）
                    loaded_images = page.evaluate("""
                        () => {
                            const imgs = document.querySelectorAll('#js_content img');
                            let loaded = 0;
                            imgs.forEach(img => {
                                if (img.naturalWidth > 0) loaded++;
                            });
                            return { total: imgs.length, loaded: loaded };
                        }
                    """)
                    logger.debug(f"图片加载状态：总共 {loaded_images['total']} 张，已加载 {loaded_images['loaded']} 张")
                except PlaywrightTimeoutError as e:
                    logger.warning(f"部分图片加载超时，但继续生成 PDF: {e}")

                # 步骤5：基础等待（兜底）
                page.wait_for_timeout(wait_time * 1000)

                # 生成 PDF（移除所有无效参数，仅保留 Playwright 支持的参数）
                page.pdf(
                    path=pdf_path,
                    format='A4',
                    margin={
                        'top': '15mm',
                        'bottom': '15mm',
                        'left': '10mm',
                        'right': '10mm'
                    },
                    print_background=True,  # 保留背景色/图片（必须开启）
                    display_header_footer=False,
                    scale=1.0  # 仅保留支持的 scale 参数
                )

                # 清理资源
                browser.close()
                logger.info(f"PDF 生成成功: {pdf_path} (图片加载完成)")
                return True

        except Exception as e:
            logger.error(f"生成 PDF 失败 [{article_url}]: {str(e)}")
            # 清理生成失败的空文件
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
        logger.debug(f"Token: {token[:8]}...{token[-4:]}")
        logger.debug(f"Cookie: {len(headers['cookie'])} 个字符")
        logger.info("登录信息已保存到缓存文件")

        return True

    def search_account(self, name, output_file=None):
        """搜索公众号（原功能不变）"""
        logger.info(f"搜索公众号: {name}")

        if not self.login_manager.is_logged_in():
            logger.error("未登录或登录已过期，请先登录")
            return None

        token = self.login_manager.get_token()
        headers = self.login_manager.get_headers()

        scraper = WeChatScraper(token, headers)
        results = scraper.search_account(name)

        if not results:
            logger.warning(f"未找到匹配的公众号: {name}")
            return None

        logger.info(f"找到 {len(results)} 个匹配的公众号:")
        for i, account in enumerate(results):
            logger.info(f"{i + 1}. {account['wpub_name']} (fakeid: {account['wpub_fakid']})")

        if output_file:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, ensure_ascii=False, indent=2)
            logger.info(f"搜索结果已保存到: {output_file}")

        return results

    def scrape_single_account(
            self, name, pages=10, days=30, include_content=False,
            interval=10, output_file=None, use_db=False, db_type="sqlite",
            generate_pdf=False, pdf_output_dir=None,
            article_progress_callback=None  # 新增 PDF 相关参数
    ):
        """
        爬取单个公众号（新增 PDF 生成功能）
        :param generate_pdf: 是否生成文章 PDF
        :param pdf_output_dir: PDF 输出目录（默认：公众号名称_时间戳_pdf）
        """
        logger.info(f"爬取公众号: {name}")

        if not self.login_manager.is_logged_in():
            logger.error("未登录或登录已过期，请先登录")
            return False

        token = self.login_manager.get_token()
        headers = self.login_manager.get_headers()
        scraper = WeChatScraper(token, headers)

        # 搜索公众号
        logger.info(f"搜索公众号: {name}")
        results = scraper.search_account(name)

        if not results:
            logger.warning(f"未找到匹配的公众号: {name}")
            return False

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

        # 初始化 PDF 输出目录
        pdf_dir = None
        login_cookies = headers.get('cookie', '')  # 获取登录 cookie
        if generate_pdf:
            if not pdf_output_dir:
                # 默认 PDF 目录：公众号名称_时间戳_pdf
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                pdf_output_dir = f"{self._clean_filename(account['wpub_name'])}_{timestamp}_pdf"
            pdf_dir = pdf_output_dir
            os.makedirs(pdf_dir, exist_ok=True)
            logger.info(f"PDF 将保存到目录: {pdf_dir}")

            # 获取文章内容 + 生成 PDF
            if include_content or generate_pdf:
                logger.info("获取文章内容并/或生成 PDF...")
                pdf_success_count = 0
                total_articles = len(filtered_articles)  # 定义总文章数

                # 边界处理：无文章时直接跳过后续逻辑
                if total_articles == 0:
                    logger.warning("无符合条件的文章，跳过内容爬取/PDF生成")
                    if article_progress_callback:
                        article_progress_callback(100, "无符合条件的文章")
                    return  # 结束当前逻辑，避免进入后续for循环

                for i, article in enumerate(filtered_articles):
                    article_title = article.get('title', f"未知文章_{i + 1}")
                    logger.info(f"处理第 {i + 1}/{total_articles} 篇: {article_title}")

                    # 触发进度回调（转换为百分比）
                    if article_progress_callback:
                        progress_percent = int((i + 1) / total_articles * 100)
                        article_progress_callback(progress_percent,
                                                  f"处理第 {i + 1}/{total_articles} 篇：{article_title}")

                    # 获取文章内容（原逻辑）
                    if include_content:
                        article = scraper.get_article_content_by_url(article)

                    # 生成 PDF（新增逻辑）
                    if generate_pdf and article.get('link'):
                        # 构建 PDF 文件名（避免重复）
                        cleaned_title = self._clean_filename(article_title)
                        pdf_filename = f"{cleaned_title}.pdf"
                        pdf_path = os.path.join(pdf_dir, pdf_filename)

                        # 避免文件名重复（添加序号）
                        counter = 1
                        while os.path.exists(pdf_path):
                            pdf_filename = f"{cleaned_title}_{counter}.pdf"
                            pdf_path = os.path.join(pdf_dir, pdf_filename)
                            counter += 1

                        # 生成 PDF（延长等待时间到10秒）
                        success = self._generate_article_pdf(
                            article_url=article['link'],
                            pdf_path=pdf_path,
                            cookies=login_cookies,
                            wait_time=10
                        )

                        if success:
                            pdf_success_count += 1
                            article['pdf_path'] = pdf_path  # 记录 PDF 路径
                        else:
                            article['pdf_path'] = ''

                    # 请求间隔（避免反爬）
                    if i < len(filtered_articles) - 1:
                        time.sleep(interval)

                if generate_pdf:
                    logger.info(f"PDF 生成完成：成功 {pdf_success_count}/{total_articles} 篇")

        # 保存结果到 CSV（原逻辑）
        if output_file:
            output_path = output_file
        else:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = f"{account['wpub_name']}_{timestamp}.csv"

        logger.info(f"保存结果到: {output_path}")
        success = scraper.save_articles_to_csv(filtered_articles, output_path)

        # 保存到数据库（原逻辑，新增 PDF 路径字段）
        if use_db and filtered_articles:
            output_dir = os.path.dirname(output_path) or "."
            db_file = os.path.join(output_dir, "content_spider.db")

            try:
                db = DatabaseFactory.create_database(db_type, db_file=db_file)

                # 保存账号
                account_db_id = db.save_account(
                    name=account['wpub_name'],
                    platform='wechat',
                    account_id=account['wpub_fakid']
                )

                if account_db_id:
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
                                'publish_timestamp': article.get('publish_timestamp', 0),
                                'pdf_path': article.get('pdf_path', '')  # 新增 PDF 路径
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

    def batch_scrape(
            self, accounts_file, pages=10, days=30, include_content=False,
            interval=10, threads=3, output_dir=None, use_db=False, db_type="sqlite",
            generate_pdf=False, pdf_output_dir=None  # 新增 PDF 相关参数
    ):
        """
        批量爬取多个公众号（新增 PDF 生成功能）
        :param generate_pdf: 是否生成文章 PDF
        :param pdf_output_dir: PDF 输出根目录
        """
        logger.info(f"批量爬取公众号，输入文件: {accounts_file}")

        # 读取公众号列表
        try:
            with open(accounts_file, 'r', encoding='utf-8') as f:
                content = f.read()

            # 支持多种分隔符
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

        if not self.login_manager.is_logged_in():
            logger.error("未登录或登录已过期，请先登录")
            return False

        token = self.login_manager.get_token()
        headers = self.login_manager.get_headers()

        # 批量爬虫回调
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

        batch_scraper = BatchWeChatScraper()
        batch_scraper.set_callback('progress_updated', progress_callback)
        batch_scraper.set_callback('account_status', account_status_callback)
        batch_scraper.set_callback('batch_completed', batch_completed_callback)
        batch_scraper.set_callback('error_occurred', error_callback)

        # 时间范围
        end_date = datetime.now().date()
        start_date = end_date - timedelta(days=days)

        # 输出目录
        output_dir = output_dir or "results"
        os.makedirs(output_dir, exist_ok=True)

        # PDF 配置
        login_cookies = headers.get('cookie', '')
        batch_pdf_dir = None
        if generate_pdf:
            batch_pdf_dir = pdf_output_dir or os.path.join(output_dir, "wechat_batch_pdf")
            os.makedirs(batch_pdf_dir, exist_ok=True)
            logger.info(f"批量 PDF 输出目录: {batch_pdf_dir}")

        # 爬取配置
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

        # 数据库初始化（原逻辑）
        db = None
        if use_db:
            db_file = os.path.join(output_dir, "content_spider.db")
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

        # 批量生成 PDF（新增逻辑）
        if generate_pdf and articles and batch_pdf_dir:
            logger.info(f"\n开始为 {len(articles)} 篇文章生成 PDF...")
            pdf_success_count = 0

            for i, article in enumerate(articles):
                article_url = article.get('link')
                account_name = article.get('name', '未知账号')

                if not article_url:
                    logger.warning(f"第 {i + 1} 篇文章（账号：{account_name}）无 URL，跳过 PDF 生成")
                    continue

                # 按公众号分目录存储 PDF
                account_pdf_dir = os.path.join(batch_pdf_dir, self._clean_filename(account_name))
                os.makedirs(account_pdf_dir, exist_ok=True)

                # 构建 PDF 文件名
                article_title = self._clean_filename(article.get('title', f"article_{i + 1}"))
                pdf_filename = f"{article_title}.pdf"
                pdf_path = os.path.join(account_pdf_dir, pdf_filename)

                # 避免重复文件名
                counter = 1
                while os.path.exists(pdf_path):
                    pdf_filename = f"{article_title}_{counter}.pdf"
                    pdf_path = os.path.join(account_pdf_dir, pdf_filename)
                    counter += 1

                # 生成 PDF
                success = self._generate_article_pdf(
                    article_url=article_url,
                    pdf_path=pdf_path,
                    cookies=login_cookies,
                    wait_time=10
                )

                if success:
                    pdf_success_count += 1
                    article['pdf_path'] = pdf_path
                else:
                    article['pdf_path'] = ''

                # PDF 生成间隔（避免反爬）
                if i < len(articles) - 1:
                    time.sleep(interval / 2)

            logger.success(f"批量 PDF 生成完成：成功 {pdf_success_count}/{len(articles)} 篇")

        # 保存到数据库（原逻辑，新增 PDF 路径）
        if db and articles:
            logger.info(f"保存 {len(articles)} 篇文章到数据库...")
            saved_count = 0

            # 保存账号
            for account_name in accounts:
                logger.info(f"保存账号: {account_name}")
                db.save_account(
                    name=account_name,
                    platform='wechat'
                )

            # 保存文章
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
                        'publish_timestamp': article.get('publish_timestamp', 0),
                        'pdf_path': article.get('pdf_path', '')  # 新增 PDF 路径
                    }
                )

                if success:
                    saved_count += 1

            logger.success(f"数据库保存完成，成功保存 {saved_count} 篇文章")

        logger.info(f"\n爬取完成，耗时 {end_time - start_time:.2f} 秒")
        logger.info(f"共获取 {len(articles)} 篇文章，已保存到 {config['output_file']}")

        if db:
            logger.info(f"数据库文件: {db_file}")

        if generate_pdf:
            logger.info(f"PDF 保存目录: {batch_pdf_dir}")

        return True


# 向后兼容的快捷函数（新增 PDF 参数支持）
def login():
    """登录微信公众平台"""
    runner = WeChatSpiderRunner()
    return runner.login()


def search(name, output_file=None):
    """搜索公众号"""
    runner = WeChatSpiderRunner()
    return runner.search_account(name, output_file)


def scrape_account(name, **kwargs):
    """爬取单个公众号（支持 generate_pdf/pdf_output_dir 参数）"""
    runner = WeChatSpiderRunner()
    return runner.scrape_single_account(name, **kwargs)


def batch_scrape(accounts_file, **kwargs):
    """批量爬取多个公众号（支持 generate_pdf/pdf_output_dir 参数）"""
    runner = WeChatSpiderRunner()
    return runner.batch_scrape(accounts_file, **kwargs)