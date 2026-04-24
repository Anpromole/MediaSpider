import sys
import subprocess
from PyQt5.QtCore import pyqtSignal, QThread


def install_playwright_browser(log_callback=None):
    """安装playwright浏览器组件"""
    try:
        if log_callback:
            log_callback("系统", "正在检查并安装浏览器组件...")
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if log_callback:
            log_callback("系统", "✅ 浏览器组件就绪")
            return True
    except Exception as e:
        err_msg = f"❌ 浏览器安装失败：{str(e)}"
        if log_callback:
            log_callback("系统", err_msg)
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