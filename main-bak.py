import sys
import os
import subprocess
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDateEdit, QTextEdit,
    QListWidget, QListWidgetItem, QProgressBar, QGroupBox, QFileDialog,
    QMessageBox, QFrame, QCheckBox
)
from PyQt5.QtCore import (
    pyqtSignal, Qt, QDate, QDateTime, QEvent, QTimer, QThread
)

# 直接导入核心模块
from spider.wechat.run import WeChatSpiderRunner


# ------------------------------
# 浏览器安装线程
# ------------------------------
def install_playwright_browser(log_callback=None):
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
    log_signal = pyqtSignal(str, str)

    def run(self):
        install_playwright_browser(self.log_signal.emit)


# ------------------------------
# 爬虫工作线程
# ------------------------------
class SpiderWorker(QThread):
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


# ------------------------------
# 自定义聊天气泡
# ------------------------------
class ChatBubble(QWidget):
    def __init__(self, role, text, parent=None):
        super().__init__(parent)
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(10, 8, 10, 8)

        self.icon_label = QLabel("🔰")
        self.icon_label.setFixedSize(36, 36)
        self.icon_label.setAlignment(Qt.AlignCenter)
        self.icon_label.setStyleSheet("""
            background-color: #e2e8f0; border-radius: 18px; color: #1e293b; font-weight: bold;
            font-family: "Microsoft YaHei", "SimSun", sans-serif; 
            font-size: 16px;
        """)

        self.msg_label = QLabel(text)
        self.msg_label.setWordWrap(True)
        self.msg_label.setAlignment(Qt.AlignLeft | Qt.AlignTop)
        self.msg_label.setStyleSheet("""
            QLabel {
                padding: 12px 18px;
                border-radius: 8px;
                font-size: 15px;
                line-height: 1.5;
                background-color: #f1f5f9;
                color: #333333;
                font-family: "Microsoft YaHei", "SimSun", sans-serif;
            }
        """)

        self.layout.addWidget(self.icon_label)
        self.layout.addWidget(self.msg_label)
        self.setLayout(self.layout)

    def sizeHint(self):
        return self.layout.sizeHint()


# ------------------------------
# 主窗口
# ------------------------------
class WeChatSpiderUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.spider_runner = WeChatSpiderRunner()  # 直接初始化核心模块
        self.current_account = None
        self.pdf_dir = "./wechat_pdf"
        self.login_status = False
        self.init_ui()
        self.timer_tasks = []
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.check_timer_tasks)

        self.installer_thread = BrowserInstaller()
        self.installer_thread.log_signal.connect(self.add_log_msg)
        self.installer_thread.start()

        self.add_log_msg("系统", "📌 系统初始化完成\n当前微信状态：未登录\n请先完成微信登录，再进行公众号搜索/爬取操作")

    def init_ui(self):
        self.setWindowTitle("道路塌陷应急管理系统")
        self.resize(1200, 800)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.create_system_header()
        self.create_content_area()

        self.apply_styles()

    def create_system_header(self):
        header = QFrame()
        header.setFixedHeight(45)
        header.setObjectName("SystemHeaderFrame")

        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)

        system_title = QLabel("🔰 道路塌陷应急管理系统")
        system_title.setObjectName("SystemHeaderTitle")
        menu_btn = QPushButton("☰")
        menu_btn.setObjectName("HeaderMenuBtn")

        h_layout.addWidget(system_title)
        h_layout.addStretch()
        h_layout.addWidget(menu_btn)
        self.main_layout.addWidget(header)

    def create_content_area(self):
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(25)

        self.create_left_log_panel(content_layout)
        self.create_right_function_cards(content_layout)

        self.main_layout.addWidget(content_widget)

    def create_left_log_panel(self, parent_layout):
        self.chat_list = QListWidget()
        self.chat_list.setObjectName("LogList")
        self.chat_list.setFocusPolicy(Qt.NoFocus)
        self.chat_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.chat_list.installEventFilter(self)
        parent_layout.addWidget(self.chat_list, stretch=6)

    def eventFilter(self, obj, event):
        if obj == self.chat_list and event.type() == QEvent.Resize:
            for i in range(self.chat_list.count()):
                item = self.chat_list.item(i)
                bubble = self.chat_list.itemWidget(item)
                if bubble:
                    max_width = self.chat_list.width() - 80
                    bubble.msg_label.setMaximumWidth(max_width)
                    item.setSizeHint(bubble.sizeHint())
            return True
        return super().eventFilter(obj, event)

    def create_right_function_cards(self, parent_layout):
        right_widget = QWidget()
        v_layout = QVBoxLayout(right_widget)
        v_layout.setContentsMargins(0, 0, 0, 0)
        v_layout.setSpacing(20)

        # 卡片1：微信登录
        card1 = self.create_function_card("1. 微信登录")
        c1_layout = QVBoxLayout()

        self.login_btn = QPushButton("扫码登录")
        self.login_btn.setFixedHeight(45)
        self.login_btn.clicked.connect(self.start_login)

        self.login_status_label = QLabel("当前状态：未登录 🚫")
        self.login_status_label.setStyleSheet("""
            color: #ef4444; 
            font-size: 14px; 
            margin-top: 10px;
            font-weight: 500;
        """)

        c1_layout.addWidget(self.login_btn)
        c1_layout.addWidget(self.login_status_label)
        card1.setLayout(c1_layout)
        v_layout.addWidget(card1)

        # 卡片2：公众号搜索
        card2 = self.create_function_card("2. 公众号搜索")
        c2_layout = QVBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("请输入公众号名称")
        self.search_input.setFixedHeight(40)
        self.search_btn = QPushButton("搜索公众号")
        self.search_btn.setFixedHeight(45)
        self.search_btn.clicked.connect(self.start_search)
        c2_layout.addWidget(self.search_input)
        c2_layout.addWidget(self.search_btn)
        card2.setLayout(c2_layout)
        v_layout.addWidget(card2)

        # 卡片3：爬取设置与执行
        card3 = self.create_function_card("3. 爬取设置与执行")
        c3_layout = QVBoxLayout()
        c3_layout.setSpacing(15)

        keyword_row = QHBoxLayout()
        keyword_row.addWidget(QLabel("筛选关键词"))
        self.keywords_edit = QLineEdit()
        self.keywords_edit.setPlaceholderText("多个关键词用逗号分隔")
        self.keywords_edit.setFixedHeight(40)
        keyword_row.addWidget(self.keywords_edit)
        c3_layout.addLayout(keyword_row)

        row1 = QHBoxLayout()
        row1.addWidget(QLabel("爬取页数"))
        self.page_spin = QSpinBox()
        self.page_spin.setRange(1, 50)
        self.page_spin.setValue(1)
        row1.addWidget(self.page_spin)
        c3_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("日期范围"))
        self.start_date_edit = QDateEdit()
        self.start_date_edit.setDate(QDate.currentDate())
        self.start_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.start_date_edit.setFixedHeight(40)
        row2.addWidget(self.start_date_edit)
        row2.addWidget(QLabel("至"))
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setDate(QDate.currentDate())
        self.end_date_edit.setDisplayFormat("yyyy-MM-dd")
        self.end_date_edit.setFixedHeight(40)
        row2.addWidget(self.end_date_edit)
        c3_layout.addLayout(row2)

        self.pdf_check = QCheckBox("生成文章PDF文件")
        self.pdf_check.setChecked(True)
        c3_layout.addWidget(self.pdf_check)

        self.dir_btn = QPushButton("选择PDF保存目录")
        self.dir_btn.setFixedHeight(45)
        self.dir_btn.clicked.connect(self.select_dir)
        c3_layout.addWidget(self.dir_btn)

        # --- 新增/修改：操作按钮行 ---
        action_row = QHBoxLayout()
        self.scrape_btn = QPushButton("开始爬取")
        self.scrape_btn.setFixedHeight(50)
        self.scrape_btn.clicked.connect(self.start_scrape)

        self.stop_btn = QPushButton("停止爬取")
        self.stop_btn.setFixedHeight(50)
        self.stop_btn.setEnabled(False)  # 默认不可用
        self.stop_btn.setStyleSheet("""
            QPushButton { background-color: #dc2626; }
            QPushButton:hover { background-color: #b91c1c; }
            QPushButton:disabled { background-color: #fca5a5; }
        """)
        self.stop_btn.clicked.connect(self.stop_scrape)

        action_row.addWidget(self.scrape_btn)
        action_row.addWidget(self.stop_btn)
        c3_layout.addLayout(action_row)
        # ---------------------------

        progress_row = QHBoxLayout()
        self.progress_label = QLabel("爬取文章进度")
        self.progress_percent = QLabel("0%")
        progress_row.addWidget(self.progress_label)
        progress_row.addStretch()
        progress_row.addWidget(self.progress_percent)
        c3_layout.addLayout(progress_row)

        self.pbar = QProgressBar()
        self.pbar.setRange(0, 100)
        self.pbar.setValue(0)
        self.pbar.setFixedHeight(12)
        self.pbar.setFormat("")
        self.pbar.setTextVisible(False)
        c3_layout.addWidget(self.pbar)

        card3.setLayout(c3_layout)
        v_layout.addWidget(card3)

        # 卡片4：定时任务设置
        card4 = self.create_function_card("4. 定时任务设置")
        c4_layout = QVBoxLayout()
        c4_layout.setSpacing(15)

        self.task_accounts = QTextEdit()
        self.task_accounts.setPlaceholderText("请输入要定时爬取的公众号，每行一个")
        self.task_accounts.setFixedHeight(80)
        c4_layout.addWidget(QLabel("公众号列表"))
        c4_layout.addWidget(self.task_accounts)

        self.task_keywords = QLineEdit()
        self.task_keywords.setPlaceholderText("定时任务筛选关键词，多个用逗号分隔")
        self.task_keywords.setFixedHeight(40)
        c4_layout.addWidget(QLabel("筛选关键词"))
        c4_layout.addWidget(self.task_keywords)

        freq_layout = QHBoxLayout()
        freq_layout.addWidget(QLabel("爬取频率"))
        self.freq_spin = QSpinBox()
        self.freq_spin.setRange(1, 24)
        self.freq_spin.setValue(1)
        freq_layout.addWidget(self.freq_spin)
        freq_layout.addWidget(QLabel("小时/次"))
        c4_layout.addLayout(freq_layout)

        time_layout = QHBoxLayout()
        time_layout.addWidget(QLabel("开始时间"))
        self.task_datetime = QDateEdit()
        self.task_datetime.setDateTime(QDateTime.currentDateTime())
        self.task_datetime.setDisplayFormat("yyyy-MM-dd HH:mm")
        time_layout.addWidget(self.task_datetime)
        c4_layout.addLayout(time_layout)

        btn_layout = QHBoxLayout()
        self.add_task_btn = QPushButton("添加任务")
        self.add_task_btn.setFixedHeight(40)
        self.add_task_btn.clicked.connect(self.add_timer_task)
        self.show_tasks_btn = QPushButton("查看任务")
        self.show_tasks_btn.setFixedHeight(40)
        self.show_tasks_btn.clicked.connect(self.show_timer_tasks)
        btn_layout.addWidget(self.add_task_btn)
        btn_layout.addWidget(self.show_tasks_btn)
        c4_layout.addLayout(btn_layout)

        card4.setLayout(c4_layout)
        v_layout.addWidget(card4)

        v_layout.addStretch()
        parent_layout.addWidget(right_widget, stretch=4)

    def create_function_card(self, title_text):
        box = QGroupBox(title_text)
        box.setObjectName("FunctionCard")
        box.setStyleSheet("""
            QGroupBox#FunctionCard {
                background-color: #718096;
                border-radius: 8px;
                color: #ffffff;
                font-weight: bold;
                font-size: 16px;
                padding: 18px;
                margin: 0;
                font-family: "Microsoft YaHei", "SimSun", sans-serif;
            }
        """)
        return box

    def add_log_msg(self, role, msg):
        item = QListWidgetItem(self.chat_list)
        bubble = ChatBubble(role, msg)

        max_width = self.chat_list.width() - 80
        bubble.msg_label.setMaximumWidth(max_width)

        item.setSizeHint(bubble.sizeHint())
        self.chat_list.setItemWidget(item, bubble)
        self.chat_list.scrollToBottom()

    # ------------------------------
    # 功能逻辑
    # ------------------------------
    def start_login(self):
        self.add_log_msg("系统", "📢 请准备扫码登录")
        self.login_btn.setEnabled(False)
        self.login_status_label.setText("当前状态：登录中 🕒")
        self.login_status_label.setStyleSheet("""
            color: #f97316; 
            font-size: 14px; 
            margin-top: 10px;
            font-weight: 500;
        """)

        self.worker = SpiderWorker(self.spider_runner, "login")
        self.worker.log_signal.connect(self.add_log_msg)
        self.worker.finish_signal.connect(self.on_login_finished)
        self.worker.start()

    def on_login_finished(self, success, msg, data):
        self.login_btn.setEnabled(True)
        if success:
            self.login_status = True
            self.login_status_label.setText("当前状态：已登录 ✅")
            self.login_status_label.setStyleSheet("""
                color: #10b981; 
                font-size: 14px; 
                margin-top: 10px;
                font-weight: 500;
            """)
            self.add_log_msg("系统", "🎉 微信登录成功，可进行公众号搜索/爬取操作")
        else:
            self.login_status = False
            self.login_status_label.setText("当前状态：未登录 🚫")
            self.login_status_label.setStyleSheet("""
                color: #ef4444; 
                font-size: 14px; 
                margin-top: 10px;
                font-weight: 500;
            """)
            self.add_log_msg("系统", "❌ 微信登录失败，请重新点击「扫码登录」重试")

    def start_search(self):
        if not self.login_status:
            self.add_log_msg("系统", "⚠️ 操作失败：未登录微信")
            QMessageBox.warning(self, "权限提示", "请先完成微信扫码登录，再进行公众号搜索！")
            return

        name = self.search_input.text().strip()
        if not name:
            self.add_log_msg("系统", "⚠️ 请输入公众号名称后再搜索")
            return

        self.add_log_msg("用户", f"发起搜索：公众号名称 = {name}")
        self.search_btn.setEnabled(False)
        self.worker = SpiderWorker(self.spider_runner, "search", account_name=name)
        self.worker.log_signal.connect(self.add_log_msg)
        self.worker.finish_signal.connect(self.on_search_finished)
        self.worker.start()

    def on_search_finished(self, success, msg, data):
        self.search_btn.setEnabled(True)
        if success and isinstance(data, list):
            matched_count = len(data)
            if matched_count > 0:
                self.current_account = data[0]
                selected_account = self.current_account
                self.add_log_msg(
                    "系统",
                    f"✅ 搜索成功\n共找到 {matched_count} 个匹配公众号\n"
                    f"选中第一个：{selected_account['wpub_name']}（ID：{selected_account['wpub_fakid']}）"
                )
            else:
                self.current_account = None
                self.add_log_msg("系统", "❌ 搜索失败：未找到匹配的公众号")
        else:
            self.current_account = None
            self.add_log_msg("系统", f"❌ 搜索失败：{msg}")

    def select_dir(self):
        path = QFileDialog.getExistingDirectory(self, "选择PDF保存目录")
        if path:
            self.pdf_dir = path
            self.dir_btn.setText(f"已选: .../{os.path.basename(path)}")
            self.add_log_msg("系统", f"📁 PDF保存目录已设置：{path}")

    def start_scrape(self):
        if not self.login_status:
            self.add_log_msg("系统", "⚠️ 操作失败：未登录微信")
            QMessageBox.warning(self, "权限提示", "请先完成微信扫码登录，再进行文章爬取！")
            return

        if not self.current_account:
            self.add_log_msg("系统", "⚠️ 操作失败：未选中公众号")
            QMessageBox.warning(self, "参数提示", "请先搜索并选中一个公众号！")
            return

        start_date = self.start_date_edit.date().toString("yyyy-MM-dd")
        end_date = self.end_date_edit.date().toString("yyyy-MM-dd")
        pages = self.page_spin.value()
        generate_pdf = self.pdf_check.isChecked()
        pdf_dir = self.pdf_dir

        keywords = self.keywords_edit.text().strip()
        keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]

        start_dt = QDate.fromString(start_date, "yyyy-MM-dd")
        end_dt = QDate.fromString(end_date, "yyyy-MM-dd")
        if start_dt > end_dt:
            self.add_log_msg("系统", "⚠️ 日期范围错误：开始日期不能晚于结束日期")
            QMessageBox.warning(self, "参数提示", "开始日期不能晚于结束日期，请修正！")
            return

        keyword_info = f"- 筛选关键词：{', '.join(keyword_list)}" if keyword_list else "- 未设置筛选关键词"
        self.add_log_msg("用户", f"""
开始爬取配置：
- 目标公众号：{self.current_account['wpub_name']}
- 爬取页数：{pages}
- 时间范围：{start_date} 至 {end_date}
{keyword_info}
- 生成PDF：{"是" if generate_pdf else "否"}
- PDF保存目录：{pdf_dir}
        """)

        # UI 状态更新
        self.scrape_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)  # 启用停止按钮
        self.pbar.setValue(0)
        self.progress_percent.setText("0%")

        self.worker = SpiderWorker(
            self.spider_runner, "scrape",
            account=self.current_account,
            pages=pages,
            start_date=start_date,
            end_date=end_date,
            generate_pdf=generate_pdf,
            pdf_dir=pdf_dir,
            keywords=keyword_list
        )
        self.worker.log_signal.connect(self.add_log_msg)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finish_signal.connect(self.on_scrape_finished)
        self.worker.start()

    def stop_scrape(self):
        """停止爬取任务"""
        self.add_log_msg("系统", "🛑 正在停止爬取任务，请等待当前操作完成...")
        self.stop_btn.setEnabled(False)  # 防止重复点击
        self.spider_runner.stop()  # 调用后端停止方法

    def update_progress(self, val):
        self.pbar.setValue(val)
        self.progress_percent.setText(f"{val}%")

    def on_scrape_finished(self, success, msg, data):
        self.scrape_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)  # 任务结束，禁用停止按钮

        if success:
            if "已停止" in msg:
                self.add_log_msg("系统", f"⚠️ {msg}")
            else:
                self.add_log_msg("系统", "✅ 爬取完成：所有文章已处理完毕（含PDF生成）")
        else:
            self.add_log_msg("系统", f"❌ 爬取失败：{msg}")

    # ------------------------------
    # 定时任务相关
    # ------------------------------
    def add_timer_task(self):
        if not self.login_status:
            self.add_log_msg("系统", "⚠️ 操作失败：未登录微信")
            QMessageBox.warning(self, "权限提示", "请先完成微信扫码登录，再设置定时任务！")
            return

        accounts_text = self.task_accounts.toPlainText().strip()
        if not accounts_text:
            self.add_log_msg("系统", "⚠️ 请输入至少一个公众号")
            return

        task_keywords = self.task_keywords.text().strip()
        task_keyword_list = [k.strip() for k in task_keywords.split(',') if k.strip()]

        accounts = [acc.strip() for acc in accounts_text.split("\n") if acc.strip()]
        freq = self.freq_spin.value()
        start_time = self.task_datetime.dateTime()

        if start_time < QDateTime.currentDateTime():
            self.add_log_msg("系统", "⚠️ 开始时间不能早于当前时间")
            return

        task_id = len(self.timer_tasks) + 1
        task = {
            "id": task_id,
            "accounts": accounts,
            "keywords": task_keyword_list,
            "frequency": freq,
            "start_time": start_time,
            "last_run": None,
            "status": "等待中"
        }

        self.timer_tasks.append(task)
        keyword_info = f"关键词: {', '.join(task_keyword_list)}" if task_keyword_list else "未设置关键词"
        self.add_log_msg("系统",
                         f"✅ 定时任务添加成功 (ID: {task_id})\n公众号: {', '.join(accounts)}\n{keyword_info}\n频率: 每{freq}小时")

        if not self.timer.isActive():
            self.timer.start(60000)

    def check_timer_tasks(self):
        current_time = QDateTime.currentDateTime()

        for task in self.timer_tasks:
            if task["status"] != "等待中" and task["status"] != "运行中":
                continue

            should_run = False
            if task["last_run"] is None:
                if current_time >= task["start_time"]:
                    should_run = True
            else:
                next_run_time = task["last_run"].addSecs(task["frequency"] * 3600)
                if current_time >= next_run_time:
                    should_run = True

            if should_run:
                self.run_timer_task(task)

    def run_timer_task(self, task):
        task["status"] = "运行中"
        self.add_log_msg("系统", f"⏰ 开始执行定时任务 (ID: {task['id']})")

        self.worker = SpiderWorker(
            self.spider_runner, "batch_scrape",
            accounts=task["accounts"],
            pages=self.page_spin.value(),
            start_date=self.start_date_edit.date().toString("yyyy-MM-dd"),
            end_date=self.end_date_edit.date().toString("yyyy-MM-dd"),
            generate_pdf=self.pdf_check.isChecked(),
            pdf_dir=self.pdf_dir,
            keywords=task["keywords"]
        )
        self.worker.log_signal.connect(self.add_log_msg)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.finish_signal.connect(lambda s, m, d: self.on_task_finished(s, m, d, task))
        self.worker.start()

    def on_task_finished(self, success, msg, data, task):
        task["last_run"] = QDateTime.currentDateTime()
        task["status"] = "等待中"

        if success:
            self.add_log_msg("系统",
                             f"✅ 定时任务完成 (ID: {task['id']})\n下次运行时间: {task['last_run'].addSecs(task['frequency'] * 3600).toString('yyyy-MM-dd HH:mm')}")
        else:
            self.add_log_msg("系统", f"❌ 定时任务失败 (ID: {task['id']}): {msg}")

    def show_timer_tasks(self):
        if not self.timer_tasks:
            QMessageBox.information(self, "定时任务", "当前没有定时任务")
            return

        task_info = "当前定时任务列表:\n\n"
        for task in self.timer_tasks:
            keywords = ', '.join(task['keywords']) if task['keywords'] else '无'
            task_info += f"任务ID: {task['id']}\n"
            task_info += f"公众号: {', '.join(task['accounts'])}\n"
            task_info += f"筛选关键词: {keywords}\n"
            task_info += f"频率: 每{task['frequency']}小时\n"
            task_info += f"开始时间: {task['start_time'].toString('yyyy-MM-dd HH:mm')}\n"
            task_info += f"最后运行: {task['last_run'].toString('yyyy-MM-dd HH:mm') if task['last_run'] else '未运行'}\n"
            task_info += f"状态: {task['status']}\n\n"

        QMessageBox.information(self, "定时任务", task_info)

    # ------------------------------
    # 样式表
    # ------------------------------
    def apply_styles(self):
        qss = """
        /* 全局字体 */
        * {
            font-family: "Microsoft YaHei", "SimSun", sans-serif;
        }

        QMainWindow { background-color: #f1f5f9; }

        /* 系统顶部标题栏 */
        QFrame#SystemHeaderFrame {
            background-color: #0f2c52;
            border: none;
        }
        QLabel#SystemHeaderTitle {
            color: #ffffff;
            font-size: 18px;
            font-weight: bold;
        }

        /* 左侧日志区 */
        QListWidget#LogList {
            background-color: #94a3b8;
            border-radius: 8px;
            border: none;
        }

        /* 功能按钮 */
        QPushButton {
            background-color: #0f2c52;
            color: #ffffff;
            border-radius: 6px;
            border: none;
            font-weight: bold;
            font-size: 16px;
        }
        QPushButton:hover { background-color: #1e40af; }
        QPushButton:disabled { background-color: #64748b; }

        /* 输入控件 */
        QLineEdit, QSpinBox, QDateEdit, QTextEdit {
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            padding: 8px;
            background-color: #ffffff;
            color: #333;
            font-size: 15px;
        }

        /* 复选框 */
        QCheckBox {
            color: #ffffff;
            font-size: 15px;
        }

        /* 进度条 */
        QProgressBar {
            border: none;
            background-color: #e2e8f0;
            border-radius: 6px;
            height: 12px;
        }
        QProgressBar::chunk {
            background-color: #3b82f6;
            border-radius: 6px;
        }

        /* 菜单按钮 */
        QPushButton#HeaderMenuBtn {
            color: white; font-size: 22px;
            background: transparent; border: none;
        }

        /* 日期选择框 */
        QDateEdit {
            min-width: 140px;
        }
        """
        self.setStyleSheet(qss)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WeChatSpiderUI()
    window.show()
    sys.exit(app.exec_())