import sys
import os
import subprocess
import glob
from datetime import datetime
from PyQt5.QtCore import pyqtSignal, QThread
from config import AutoTaskConfig

# 全局设置 Playwright 国内镜像源以加快下载并提高成功率
os.environ["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright/"


def is_playwright_installed():
    """快速检测 Playwright 浏览器是否已完整安装"""
    # 查找默认的 ms-playwright 路径
    browsers_path = os.environ.get("PLAYWRIGHT_BROWSERS_PATH")
    if not browsers_path:
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            browsers_path = os.path.join(local_app_data, "ms-playwright")
        else:
            user_profile = os.environ.get("USERPROFILE")
            if user_profile:
                browsers_path = os.path.join(user_profile, "AppData", "Local", "ms-playwright")
                
    if not browsers_path or not os.path.exists(browsers_path):
        return False
        
    # Playwright 默认会下载：
    # 1. chromium_headless_shell-* (用于 headless)
    # 2. chromium-* (用于 headed)
    # 只要存在这二者之一的 chrome 可执行程序即视为已安装
    headless_shells = glob.glob(os.path.join(browsers_path, "chromium_headless_shell-*", "**", "chrome-headless-shell.exe"), recursive=True)
    chromiums = glob.glob(os.path.join(browsers_path, "chromium-*", "**", "chrome.exe"), recursive=True)
    
    return len(headless_shells) > 0 or len(chromiums) > 0


def install_playwright_browser(log_callback=None):
    """安装/更新 playwright 浏览器组件"""
    import subprocess
    
    def log(msg):
        if log_callback:
            log_callback("系统", msg)
    
    try:
        log("正在检查并更新浏览器组件...")
        
        # 传递包含下载镜像源的系统环境变量
        import os
        env = os.environ.copy()
        env["PLAYWRIGHT_DOWNLOAD_HOST"] = "https://npmmirror.com/mirrors/playwright/"
        
        # 使用 shell=True 并重定向输出以显示进度
        process = subprocess.Popen(
            [sys.executable, "-m", "playwright", "install", "chromium", "--force"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            env=env
        )
        
        # 实时输出安装进度
        for line in iter(process.stdout.readline, ''):
            if line.strip():
                log(line.strip())
        
        process.wait()
        
        if process.returncode == 0:
            log("✅ 浏览器组件更新完成")
            return True
        else:
            log("❌ 浏览器安装失败")
            return False
            
    except Exception as e:
        log(f"❌ 浏览器安装异常：{str(e)}")
        return False


class BrowserInstaller(QThread):
    """浏览器安装线程"""
    log_signal = pyqtSignal(str, str)

    def run(self):
        install_playwright_browser(self.log_signal.emit)


class SpiderWorker(QThread):
    """爬虫工作线程（处理登录、搜索、爬取等任务）"""
    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(int)
    finish_signal = pyqtSignal(bool, str, object)  # bool:success, str:msg, object:data

    def __init__(self, runner, task_type, **kwargs):
        super().__init__()
        self.runner = runner
        self.task_type = task_type
        self.kwargs = kwargs

    def run(self):
        # 确保每次开始任务前重置停止标志
        self.runner.reset_stop()

        try:
            if self.task_type == "login":
                login_result = self.runner.login()
                if isinstance(login_result, bool):
                    result = {
                        "success": login_result,
                        "msg": "登录成功" if login_result else "登录失败",
                        "data": {}
                    }
                else:
                    result = login_result or {"success": False, "msg": "登录返回异常", "data": {}}
                self.finish_signal.emit(result["success"], result["msg"], result.get("data", {}))


            elif self.task_type == "search":
                name = self.kwargs.get("account_name")
                result = self.runner.search_account(name)
                if result is None:
                    result = []
                self.finish_signal.emit(
                    True,
                    f"搜索完成，找到 {len(result)} 个匹配结果" if result else "未找到匹配公众号",
                    result
                )

            elif self.task_type == "scrape":
                account = self.kwargs.get("account")
                pages = self.kwargs.get("pages", 1)
                start_date = self.kwargs.get("start_date")
                end_date = self.kwargs.get("end_date")
                generate_pdf = self.kwargs.get("generate_pdf", False)
                pdf_dir = self.kwargs.get("pdf_dir", "./wechat_pdf")
                keywords = self.kwargs.get("keywords", [])

                def article_progress_callback(percent, msg):
                    self.progress_signal.emit(percent)
                    self.log_signal.emit("系统", f"进度 {percent}% | {msg}")

                result = self.runner.scrape_single_account(
                    name=account['wpub_name'],
                    pages=pages,
                    start_date=start_date,
                    end_date=end_date,
                    include_content=True,
                    generate_pdf=generate_pdf,
                    pdf_output_dir=pdf_dir,
                    progress_callback=article_progress_callback,
                    keywords=keywords
                )
                self.finish_signal.emit(result["success"], result["msg"], result.get("data", {}))

            elif self.task_type == "batch_scrape":
                accounts = self.kwargs.get("accounts", [])
                pages = self.kwargs.get("pages", 1)
                start_date = self.kwargs.get("start_date")
                end_date = self.kwargs.get("end_date")
                generate_pdf = self.kwargs.get("generate_pdf", False)
                pdf_dir = self.kwargs.get("pdf_dir", "./wechat_pdf")
                keywords = self.kwargs.get("keywords", [])

                def batch_progress_callback(percent, msg):
                    self.progress_signal.emit(percent)
                    self.log_signal.emit("系统", f"批量进度 {percent}% | {msg}")

                result = self.runner.batch_scrape(
                    accounts=accounts,
                    pages=pages,
                    start_date=start_date,
                    end_date=end_date,
                    generate_pdf=generate_pdf,
                    pdf_output_dir=pdf_dir,
                    progress_callback=batch_progress_callback,
                    keywords=keywords
                )
                self.finish_signal.emit(result["success"], result["msg"], result.get("data", {}))

        except Exception as e:
            self.finish_signal.emit(
                False,
                f"线程执行出错：{str(e)}",
                None
            )

class UploadWorker(QThread):
    """后台上传文档到 Dify 知识库的工作线程"""
    upload_success = pyqtSignal()
    upload_error = pyqtSignal(str)

    def __init__(self, dataset_id, content, topic, dify_client):
        super().__init__()
        self.dataset_id = dataset_id
        self.content = content
        self.topic = topic
        self.dify_client = dify_client

    def run(self):
        try:
            name = f"{self.topic}_简报_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            success = self.dify_client.upload_document(self.dataset_id, self.content, name)
            if success:
                self.upload_success.emit()
            else:
                self.upload_error.emit("上传失败")
        except Exception as e:
            self.upload_error.emit(str(e))


class AutoTaskWorker(QThread):
    """自动化任务工作线程 - 执行多渠道爬取 + PDF 生成 + Dify 上传"""
    log_signal = pyqtSignal(str, str)
    progress_signal = pyqtSignal(int)
    finish_signal = pyqtSignal(bool, str)

    def __init__(self, wechat_runner, weibo_runner, rss_collector, dify_client, config: AutoTaskConfig):
        super().__init__()
        self.wechat_runner = wechat_runner
        self.weibo_runner = weibo_runner
        self.rss_collector = rss_collector
        self.dify_client = dify_client
        self.config = config
        self.stop_flag = False

    def stop(self):
        self.stop_flag = True
        self.wechat_runner.stop()

    def run(self):
        try:
            total_steps = 0
            if self.config.wechat_enabled:
                total_steps += len(self.config.wechat_accounts) * 2  # 爬取+PDF
            if self.config.weibo_enabled:
                total_steps += 2  # 爬取+PDF
            if self.config.rss_enabled:
                total_steps += 2  # 爬取+PDF
            if self.config.dify_upload_enabled:
                total_steps += 1  # 上传

            current_step = 0
            all_pdf_files = []

            def update_progress(msg):
                percent = int(current_step / max(total_steps, 1) * 100)
                self.progress_signal.emit(percent)
                self.log_signal.emit("系统", msg)

            # ==================== 微信爬取 ====================
            if self.config.wechat_enabled and self.config.wechat_accounts:
                update_progress("开始微信爬取...")

                for idx, account in enumerate(self.config.wechat_accounts):
                    if self.stop_flag:
                        break

                    # 解析账号（可能是字符串或 (名称，fakeid) 元组）
                    if isinstance(account, str):
                        # 需要搜索获取 fakeid
                        update_progress(f"搜索公众号：{account}")
                        search_results = self.wechat_runner.search_account(account)
                        if not search_results:
                            update_progress(f"未找到公众号：{account}，跳过")
                            continue
                        account_info = search_results[0]
                    else:
                        account_info = {"wpub_name": account[0], "wpub_fakid": account[1]}

                    # 使用配置的日期范围和爬取方式
                    start_date = getattr(self.config, 'start_date', None)
                    end_date = getattr(self.config, 'end_date', None)
                    fetch_mode = getattr(self.config, 'wechat_fetch_mode', 'fast')

                    # 爬取
                    update_progress(f"爬取公众号：{account_info['wpub_name']} (模式：{fetch_mode})")
                    result = self.wechat_runner.scrape_single_account(
                        name=account_info['wpub_name'],
                        pages=self.config.pages_per_account,
                        start_date=start_date,
                        end_date=end_date,
                        include_content=True,
                        generate_pdf=self.config.generate_pdf,
                        pdf_output_dir=self.config.get_wechat_pdf_dir(),
                        keywords=self.config.wechat_keywords,
                        fetch_mode=fetch_mode,
                        progress_callback=lambda p, m: self.progress_signal.emit(int(current_step / total_steps * 100 + p / total_steps * 30))
                    )

                    if result.get("success") and "articles" in result.get("data", {}):
                        articles = result["data"]["articles"]
                        pdf_files = [a.get("pdf_path") for a in articles if a.get("pdf_path")]
                        all_pdf_files.extend(pdf_files)
                        update_progress(f"微信爬取完成：{len(pdf_files)} 个 PDF")

                    current_step += 1

            # ==================== 微博爬取 ====================
            if self.config.weibo_enabled and self.config.weibo_keywords:
                update_progress("开始微博爬取...")

                for keyword in self.config.weibo_keywords:
                    if self.stop_flag:
                        break

                    weibos = self.weibo_runner.search_keyword(
                        keyword=keyword,
                        pages=5,
                        progress_callback=lambda c, t, m: self.log_signal.emit("系统", f"微博：{m}")
                    )

                    if weibos:
                        # 保存为 CSV
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"weibo_{keyword}_{timestamp}.csv"
                        self.weibo_runner.save_to_csv(weibos, filename)
                        update_progress(f"微博爬取完成：{len(weibos)} 条")

                    current_step += 1

            # ==================== RSS 采集 ====================
            if self.config.rss_enabled and self.config.rss_keywords:
                update_progress("开始 RSS 采集...")

                for keyword in self.config.rss_keywords:
                    if self.stop_flag:
                        break

                    news_list = self.rss_collector.fetch(
                        keyword=keyword,
                        pages=50,
                        progress_callback=lambda c, t, m: self.log_signal.emit("系统", f"RSS: {m}")
                    )

                    if news_list:
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename = f"rss_{keyword}_{timestamp}.csv"
                        self.rss_collector.save_to_csv(news_list, filename)
                        update_progress(f"RSS 采集完成：{len(news_list)} 条")

                    current_step += 1

            # ==================== Dify 上传 ====================
            if self.config.dify_upload_enabled and all_pdf_files:
                update_progress(f"开始上传 {len(all_pdf_files)} 个 PDF 到 Dify...")

                uploaded = 0
                for pdf_path in all_pdf_files:
                    if self.stop_flag:
                        break
                    if os.path.exists(pdf_path):
                        pdf_name = os.path.basename(pdf_path)
                        if self.dify_client.upload_pdf_file(
                            self.config.dify_dataset_id,
                            pdf_path,
                            pdf_name
                        ):
                            uploaded += 1
                            update_progress(f"已上传：{uploaded}/{len(all_pdf_files)}")

                update_progress(f"Dify 上传完成：{uploaded}/{len(all_pdf_files)}")

            # ==================== 完成 ====================
            if self.stop_flag:
                self.finish_signal.emit(False, "任务已手动停止")
            else:
                self.progress_signal.emit(100)
                self.finish_signal.emit(True, f"自动化任务完成，共生成 {len(all_pdf_files)} 个 PDF")

        except Exception as e:
            self.finish_signal.emit(False, f"执行出错：{str(e)}")
