import subprocess
import sys
import threading
import os
from datetime import datetime, timedelta
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QGroupBox, QLabel, QLineEdit, QPushButton, QSpinBox, QCheckBox,
    QTextEdit, QFileDialog, QMessageBox
)
from PyQt5.QtGui import QFont, QPalette, QColor, QIcon
from PyQt5.QtCore import Qt, QThread, pyqtSignal

# 导入爬虫核心模块
from spider.wechat.run import WeChatSpiderRunner
from spider.log.utils import logger


# ------------------------------
# 1. 浏览器自动安装工具类（保留原功能）
# ------------------------------
def install_playwright_browser(log_callback=None):
    """自动安装 Playwright Chromium 浏览器，支持日志回调"""
    try:
        if log_callback:
            log_callback("正在自动安装 Chromium 浏览器（首次运行需1-3分钟）...")
        # 调用 Playwright 安装命令
        subprocess.check_call(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        if log_callback:
            log_callback("✅ Chromium 浏览器安装成功")
        return True
    except Exception as e:
        err_msg = f"❌ 浏览器安装失败：{str(e)}\n请手动执行命令：playwright install chromium"
        if log_callback:
            log_callback(err_msg)
        QMessageBox.critical(None, "安装错误", err_msg)
        return False


# ------------------------------
# 2. 爬虫任务线程类（避免 UI 卡顿）
# ------------------------------
class SpiderWorker(QThread):
    """后台爬虫线程，通过信号传递日志和结果"""
    log_signal = pyqtSignal(str)  # 日志信号
    finish_signal = pyqtSignal(bool, str, object)  # 任务完成信号（成功状态，提示信息）

    def __init__(self, runner, task_type, **kwargs):
        super().__init__()
        self.runner = runner  # 爬虫实例
        self.task_type = task_type  # 任务类型：login/search/scrape
        self.kwargs = kwargs  # 任务参数

    def run(self):
        try:
            if self.task_type == "login":
                # 执行登录
                success = self.runner.login()
                if success:
                    self.log_signal.emit("✅ 微信公众平台登录成功")
                    self.finish_signal.emit(True, "登录成功，可开始搜索公众号", None)
                else:
                    self.log_signal.emit("❌ 微信登录失败（请检查扫码或网络）")
                    self.finish_signal.emit(False, "登录失败", None)

            elif self.task_type == "search":
                # 搜索公众号
                account_name = self.kwargs.get("account_name")
                self.log_signal.emit(f"🔍 正在搜索公众号：{account_name}")
                accounts = self.runner.search_account(account_name)
                # 在SpiderWorker的run方法中（搜索任务部分）
                if accounts:
                    account = accounts[0]
                    msg = f"✅ 找到公众号：{account['wpub_name']}（fakeid：{account['wpub_fakid']}）"
                    self.log_signal.emit(msg)
                    # 修正：传递3个参数（状态、消息、额外数据account）
                    self.finish_signal.emit(True, msg, account)
                else:
                    self.log_signal.emit(f"❌ 未找到匹配公众号：{account_name}")
                    # 无额外数据时，第三个参数传None
                    self.finish_signal.emit(False, "未找到公众号", None)

            elif self.task_type == "scrape":
                # 执行爬取
                account = self.kwargs.get("account")
                pages = self.kwargs.get("pages")
                days = self.kwargs.get("days")
                generate_pdf = self.kwargs.get("generate_pdf")
                pdf_dir = self.kwargs.get("pdf_dir")

                self.log_signal.emit(f"📥 开始爬取：{account['wpub_name']}（{pages}页，{days}天内）")
                # 执行爬取
                success = self.runner.scrape_single_account(
                    name=account['wpub_name'],
                    pages=pages,
                    days=days,
                    include_content=True,
                    generate_pdf=generate_pdf,
                    pdf_output_dir=pdf_dir,
                    interval=5  # 请求间隔，避免反爬
                )
                if success:
                    pdf_msg = "（含PDF生成）" if generate_pdf else ""
                    msg = f"✅ 爬取完成 {pdf_msg}，结果已保存为CSV"
                    self.log_signal.emit(msg)
                    if generate_pdf:
                        self.log_signal.emit(f"📄 PDF文件保存路径：{pdf_dir}")
                    self.finish_signal.emit(True, msg, None)
                else:
                    self.log_signal.emit("❌ 爬取任务失败")
                    self.finish_signal.emit(False, "爬取失败", None)

        except Exception as e:
            err_msg = f"⚠️ 任务异常：{str(e)}"
            self.log_signal.emit(err_msg)
            self.finish_signal.emit(False, err_msg, None)


# ------------------------------
# 3. 主窗口类（蓝白科技风 UI）
# ------------------------------
class WeChatSpiderUI(QMainWindow):
    def __init__(self):
        super().__init__()
        # 初始化爬虫实例
        self.spider_runner = WeChatSpiderRunner()
        # 存储当前选中的公众号信息
        self.current_account = None
        # 初始化 UI
        self.init_ui()
        # 新增：检查缓存登录状态（启动时自动执行）
        self.check_cached_login()
        # 自动安装浏览器（首次运行）
        self.auto_install_browser()

    def init_ui(self):
        """初始化蓝白科技风界面"""
        # 1. 窗口基础设置
        self.setWindowTitle("微信公众号爬虫（蓝白科技版）")
        self.setGeometry(100, 100, 1000, 700)  # 位置（x,y）+ 大小（宽,高）
        self.setWindowIcon(QIcon("icons/icon.ico"))  # 可自行添加图标文件

        # 2. 中心Widget与主布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # 3. 全局样式（蓝白科技风）
        self.set_style()

        # 4. 组件创建与布局
        # 4.1 登录区域
        self.login_group = self.create_login_widget()
        # 4.2 公众号搜索区域
        self.search_group = self.create_search_widget()
        # 4.3 爬取设置区域
        self.setting_group = self.create_setting_widget()
        # 4.4 日志显示区域
        self.log_group = self.create_log_widget()

        # 5. 添加组件到主布局
        main_layout.addWidget(self.login_group)
        main_layout.addWidget(self.search_group)
        main_layout.addWidget(self.setting_group)
        main_layout.addWidget(self.log_group, stretch=1)  # 日志区域占满剩余空间

        # 6. 初始状态禁用后续功能（未登录时）
        self.disable_after_login(True)

    # 新增：缓存登录检查方法
    def check_cached_login(self):
        """检查是否存在有效缓存登录，自动启用后续组件"""
        if self.spider_runner.login_manager.is_logged_in():
            self.add_log("✅ 检测到有效缓存登录信息，自动恢复登录状态")
            self.disable_after_login(False)  # 启用搜索、爬取等组件
        else:
            self.add_log("ℹ️ 未检测到缓存登录信息，请点击登录按钮扫码登录")

    def set_style(self):
        """设置蓝白科技风样式（QSS）"""
        style_sheet = """
            /* 全局字体 */
            * {
                font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
                font-size: 14px;
            }

            /* 主窗口背景 */
            QMainWindow {
                background-color: #f8fafc;
            }

            /* 分组框样式（蓝白科技感边框） */
            QGroupBox {
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                margin-top: 15px;
                padding: 15px;
                background-color: #ffffff;
            }
            QGroupBox::title {
                color: #1e88e5;
                font-size: 16px;
                font-weight: bold;
                margin-left: 10px;
            }

            /* 按钮样式（蓝白渐变+ hover效果） */
            QPushButton {
                background-color: #1e88e5;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 8px 16px;
                font-weight: 500;
            }
            QPushButton:hover {
                background-color: #1976d2;
            }
            QPushButton:disabled {
                background-color: #90caf9;
                color: #e3f2fd;
            }

            /* 输入框样式（聚焦蓝色边框） */
            QLineEdit, QSpinBox {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 8px 12px;
                background-color: #ffffff;
            }
            QLineEdit:focus, QSpinBox:focus {
                border-color: #1e88e5;
                outline: none;
            }

            /* 复选框样式 */
            QCheckBox {
                color: #334155;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #e2e8f0;
            }
            QCheckBox::indicator:checked {
                background-color: #1e88e5;
                image: url(:/icons/check.png);  /* 可添加勾选图标 */
            }

            /* 日志区域样式 */
            QTextEdit {
                border: 1px solid #e2e8f0;
                border-radius: 6px;
                padding: 10px;
                background-color: #ffffff;
                color: #334155;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 13px;
            }

            /* 标签样式 */
            QLabel {
                color: #334155;
            }
        """
        self.setStyleSheet(style_sheet)

    def create_login_widget(self):
        """创建登录区域组件"""
        group = QGroupBox("1. 微信登录")
        layout = QHBoxLayout()

        self.login_btn = QPushButton("扫码登录微信公众平台")
        self.login_btn.clicked.connect(self.start_login_task)

        layout.addWidget(self.login_btn)
        group.setLayout(layout)
        return group

    def create_search_widget(self):
        """创建公众号搜索区域组件"""
        group = QGroupBox("2. 公众号搜索")
        layout = QHBoxLayout()

        # 搜索输入框
        self.account_input = QLineEdit()
        self.account_input.setPlaceholderText("请输入公众号名称（如：腾讯科技）")
        layout.addWidget(self.account_input, stretch=1)

        # 搜索按钮
        self.search_btn = QPushButton("搜索公众号")
        self.search_btn.clicked.connect(self.start_search_task)
        layout.addWidget(self.search_btn)

        group.setLayout(layout)
        return group

    def create_setting_widget(self):
        """创建爬取设置区域组件"""
        group = QGroupBox("3. 爬取设置与执行")
        layout = QVBoxLayout()

        # 3.1 基础设置（页数+天数）
        base_layout = QHBoxLayout()

        # 爬取页数
        page_layout = QHBoxLayout()
        page_layout.addWidget(QLabel("爬取页数："))
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 50)
        self.page_spin.setValue(1)  # 默认1页（5-10篇文章）
        page_layout.addWidget(self.page_spin)
        page_layout.addWidget(QLabel("页（1页≈5-10篇）"))
        base_layout.addLayout(page_layout)

        # 时间范围
        day_layout = QHBoxLayout()
        day_layout.addWidget(QLabel("时间范围："))
        self.day_spin = QSpinBox()
        self.day_spin.setRange(1, 365)
        self.day_spin.setValue(7)  # 默认7天内
        day_layout.addWidget(self.day_spin)
        day_layout.addWidget(QLabel("天内"))
        base_layout.addLayout(day_layout)

        layout.addLayout(base_layout)

        # 3.2 PDF生成设置
        pdf_layout = QHBoxLayout()
        self.pdf_checkbox = QCheckBox("生成文章PDF文件")
        self.pdf_checkbox.setChecked(True)  # 默认生成PDF
        pdf_layout.addWidget(self.pdf_checkbox)

        # PDF保存路径选择
        self.pdf_dir_btn = QPushButton("选择PDF保存目录")
        self.pdf_dir_btn.clicked.connect(self.select_pdf_dir)
        self.pdf_dir_label = QLabel("（默认：./wechat_pdf）")
        self.pdf_dir_label.setStyleSheet("color: #64748b; font-size: 12px;")
        pdf_layout.addWidget(self.pdf_dir_btn)
        pdf_layout.addWidget(self.pdf_dir_label)
        pdf_layout.addStretch(1)
        layout.addLayout(pdf_layout)

        # 3.3 开始爬取按钮
        self.scrape_btn = QPushButton("开始爬取公众号文章")
        self.scrape_btn.clicked.connect(self.start_scrape_task)
        layout.addWidget(self.scrape_btn, alignment=Qt.AlignRight)

        group.setLayout(layout)
        return group

    def create_log_widget(self):
        """创建日志显示区域组件"""
        group = QGroupBox("4. 运行日志")
        layout = QVBoxLayout()

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)  # 日志只读
        self.log_text.setLineWrapMode(QTextEdit.NoWrap)  # 不自动换行（适合代码日志）
        layout.addWidget(self.log_text)

        group.setLayout(layout)
        return group

    # ------------------------------
    # 4. 界面交互逻辑
    # ------------------------------
    def auto_install_browser(self):
        """启动时自动安装浏览器（后台线程，不卡UI）"""

        def install_task():
            install_playwright_browser(self.add_log)

        threading.Thread(target=install_task, daemon=True).start()

    def select_pdf_dir(self):
        """选择PDF保存目录"""
        dir_path = QFileDialog.getExistingDirectory(self, "选择PDF保存目录")
        if dir_path:
            self.pdf_dir_label.setText(f"（已选：{os.path.abspath(dir_path)}）")
            self.pdf_dir_label.setStyleSheet("color: #1e88e5; font-size: 12px;")

    def disable_after_login(self, disable):
        """控制“登录后可用”的组件状态"""
        self.search_group.setEnabled(not disable)
        self.setting_group.setEnabled(not disable)
        self.account_input.setEnabled(not disable)
        self.search_btn.setEnabled(not disable)
        self.scrape_btn.setEnabled(not disable)

    def add_log(self, msg):
        """添加日志到界面（带时间戳）"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_msg = f"[{timestamp}] {msg}\n"
        self.log_text.append(log_msg)
        # 自动滚动到最新日志
        self.log_text.moveCursor(self.log_text.textCursor().End)

    # ------------------------------
    # 5. 爬虫任务启动逻辑
    # ------------------------------
    def start_login_task(self):
        """启动登录任务（后台线程）"""
        if self.spider_runner.login_manager.is_logged_in():
            QMessageBox.information(self, "提示", "已处于登录状态，无需重复登录")
            return

        self.login_btn.setEnabled(False)
        self.add_log("📱 请在弹出的微信窗口中扫码登录...")

        # 创建并启动登录线程
        self.login_thread = SpiderWorker(
            runner=self.spider_runner,
            task_type="login"
        )
        self.login_thread.log_signal.connect(self.add_log)
        self.login_thread.finish_signal.connect(self.on_login_finish)
        self.login_thread.start()

    def on_login_finish(self, success, msg):
        """登录完成回调"""
        self.login_btn.setEnabled(True)
        if success:
            self.disable_after_login(False)  # 启用后续功能
        QMessageBox.information(self, "登录结果", msg)

    def start_search_task(self):
        """启动公众号搜索任务"""
        account_name = self.account_input.text().strip()
        if not account_name:
            QMessageBox.warning(self, "输入错误", "请输入公众号名称")
            return

        self.search_btn.setEnabled(False)
        self.add_log(f"🔍 开始搜索公众号：{account_name}")

        # 创建并启动搜索线程
        self.search_thread = SpiderWorker(
            runner=self.spider_runner,
            task_type="search",
            account_name=account_name
        )
        self.search_thread.log_signal.connect(self.add_log)
        self.search_thread.finish_signal.connect(self.on_search_finish)
        self.search_thread.start()

    def on_search_finish(self, success, msg, account=None):
        """搜索完成回调（适配3个参数）"""
        self.search_btn.setEnabled(True)
        if success and account:
            self.current_account = account
            self.add_log(f"📌 已选中公众号：{account['wpub_name']}")
        QMessageBox.information(self, "搜索结果", msg)

    def start_scrape_task(self):
        """启动爬取任务"""
        if not self.current_account:
            QMessageBox.warning(self, "未选择公众号", "请先搜索并选中一个公众号")
            return

        # 获取爬取参数
        pages = self.page_spin.value()
        days = self.day_spin.value()
        generate_pdf = self.pdf_checkbox.isChecked()
        # 获取PDF保存目录（默认或用户选择）
        pdf_dir = self.pdf_dir_label.text().replace("（已选：", "").replace("）", "")
        if pdf_dir.startswith("（默认："):
            pdf_dir = "./wechat_pdf"

        # 确认爬取设置
        confirm_msg = f"""
        即将开始爬取以下内容：
        📌 公众号：{self.current_account['wpub_name']}
        📄 爬取页数：{pages}页（≈{pages * 8}篇文章）
        ⏰ 时间范围：{days}天内
        📄 生成PDF：{"是" if generate_pdf else "否"}
        📁 PDF保存目录：{pdf_dir}

        是否确认开始？
        """
        if QMessageBox.question(self, "确认爬取", confirm_msg) != QMessageBox.Yes:
            return

        self.scrape_btn.setEnabled(False)
        self.add_log("📥 爬取任务已启动，请勿关闭窗口...")

        # 创建并启动爬取线程
        self.scrape_thread = SpiderWorker(
            runner=self.spider_runner,
            task_type="scrape",
            account=self.current_account,
            pages=pages,
            days=days,
            generate_pdf=generate_pdf,
            pdf_dir=pdf_dir
        )
        self.scrape_thread.log_signal.connect(self.add_log)
        self.scrape_thread.finish_signal.connect(self.on_scrape_finish)
        self.scrape_thread.start()

    def on_scrape_finish(self, success, msg):
        """爬取完成回调"""
        self.scrape_btn.setEnabled(True)
        QMessageBox.information(self, "爬取结果", msg)


# ------------------------------
# 6. 程序入口
# ------------------------------
if __name__ == "__main__":
    # 解决PyQt5中文显示问题
    QApplication.setStyle("Fusion")
    app = QApplication(sys.argv)

    # 创建并显示主窗口
    window = WeChatSpiderUI()
    window.show()

    sys.exit(app.exec_())