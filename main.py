import sys
import os
# 确保PATH环境变量存在，若不存在则从系统中获取（适用于Windows）
if "PATH" not in os.environ:
    if sys.platform.startswith("win32"):
        try:
            import win32api
            os.environ["PATH"] = win32api.GetEnvironmentVariable("PATH")
        except ImportError:
            os.environ["PATH"] = "C:\\Windows\\system32;C:\\Windows;%s" % os.environ.get("PATH", "")
    else:
        os.environ["PATH"] = "/usr/local/bin:/usr/bin:/bin:%s" % os.environ.get("PATH", "")

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QPushButton, QLineEdit, QSpinBox, QDateEdit, QTextEdit,
    QListWidget, QListWidgetItem, QProgressBar, QGroupBox, QFileDialog,
    QMessageBox, QFrame, QCheckBox, QComboBox
)
from PyQt5.QtCore import (
    Qt, QDate, QDateTime, QEvent, QTimer
)
from datetime import datetime
import json

# 导入自定义模块
from spider.wechat.run import WeChatSpiderRunner
from spider.weibo.run import WeiboSpiderRunner
from spider.rss.collector import RSSCollector
from spider.dify.client import DifyClient
from spider.dify.summarizer import NewsSummarizer
from threads import BrowserInstaller, SpiderWorker, UploadWorker, AutoTaskWorker, is_playwright_installed
from config import AutoTaskConfig
from widgets import ChatBubble
from config import (
    DEFAULT_PDF_DIR, SYSTEM_TITLE, WINDOW_SIZE, LOG_LIST_MAX_WIDTH_OFFSET,
    DIFY_API_BASE, DIFY_DATASET_API_KEY, DIFY_DATASET_ID, DIFY_CHAT_API_KEY, DEFAULT_TOPIC
)


class WeChatSpiderUI(QMainWindow):
    """主窗口类"""
    def __init__(self):
        super().__init__()
        self.spider_runner = WeChatSpiderRunner()
        self.weibo_runner = WeiboSpiderRunner()
        self.rss_collector = RSSCollector()
        self.dify_client = DifyClient(DIFY_API_BASE, DIFY_CHAT_API_KEY, DIFY_DATASET_API_KEY)
        self.summarizer = NewsSummarizer(self.dify_client)

        self.current_account = None
        self.pdf_dir = DEFAULT_PDF_DIR
        self.login_status = False
        self.is_listening_active = False
        self.listening_start_time = None

        self.init_ui()

        # 启动浏览器安装线程
        self.installer_thread = BrowserInstaller()
        self.installer_thread.log_signal.connect(self.add_log_msg)
        self.installer_thread.start()

        self.add_log_msg("系统", "📌 系统初始化完成\n当前微信状态：未登录\n请先完成微信登录，再配置自动化持续监听任务。")

        # 加载保存的配置
        self.load_user_config()

        # 自动化任务 worker 与定时器
        self.auto_worker = None
        self.auto_timer = QTimer(self)
        self.auto_timer.setSingleShot(True)
        self.auto_timer.timeout.connect(self.run_auto_once)

    def get_data_path(self):
        """获取数据文件路径"""
        data_dir = os.path.join(os.path.dirname(__file__), '.data')
        os.makedirs(data_dir, exist_ok=True)
        return os.path.join(data_dir, 'articles.json')

    def _save_wechat_articles(self):
        """保存微信文章数据"""
        articles = getattr(self, '_last_wechat_articles', [])
        if articles:
            try:
                with open(self.get_data_path(), 'w', encoding='utf-8') as f:
                    json.dump(articles, f, ensure_ascii=False, indent=2)
            except Exception as e:
                pass

    def _load_wechat_articles(self):
        """加载微信文章数据"""
        data_path = self.get_data_path()
        if os.path.exists(data_path):
            try:
                with open(data_path, 'r', encoding='utf-8') as f:
                    articles = json.load(f)
                self._last_wechat_articles = articles
                self.add_log_msg("系统", f"📄 已加载上次爬取的 {len(articles)} 篇文章")
            except Exception as e:
                pass

    def get_config_path(self):
        """获取配置文件路径"""
        config_dir = os.path.join(os.path.dirname(__file__), '.config')
        os.makedirs(config_dir, exist_ok=True)
        return os.path.join(config_dir, 'user_config.json')

    def save_user_config(self):
        """保存用户配置"""
        try:
            config = {}
            config['pdf_dir'] = self.pdf_dir
            config['wechat_accounts'] = self.wechat_accounts_edit.toPlainText()
            config['wechat_keywords'] = self.wechat_keyword_edit.toPlainText()
            config['auto_start_date'] = self.auto_start_date.date().toString("yyyy-MM-dd")
            config['auto_end_date'] = self.auto_end_date.date().toString("yyyy-MM-dd")
            config['auto_fetch_mode'] = self.auto_fetch_mode.currentData()
            config['auto_pdf'] = self.auto_pdf_check.isChecked()
            config['dify_upload'] = self.dify_upload_check.isChecked()
            config['timer_enabled'] = self.timer_check.isChecked()
            config['timer_frequency'] = self.timer_freq_spin.value()
            config['timer_unit'] = self.timer_unit_combo.currentText()
            config['dify_topic'] = self.dify_topic_input.text()
            config['login_status'] = self.login_status
            config['current_account'] = self.current_account
            config['wechat_articles'] = getattr(self, '_last_wechat_articles', [])

            with open(self.get_config_path(), 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[FAIL] save_user_config: {e}")

    def load_user_config(self):
        """加载用户配置"""
        config_path = self.get_config_path()
        if not os.path.exists(config_path):
            return
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            if config.get('pdf_dir'):
                self.pdf_dir = config['pdf_dir']
                self.dir_label.setText(f"保存路径: .../{os.path.basename(self.pdf_dir)}")

            self.wechat_accounts_edit.setPlainText(config.get('wechat_accounts', ''))
            self.wechat_keyword_edit.setPlainText(config.get('wechat_keywords', ''))
            if config.get('auto_start_date'):
                self.auto_start_date.setDate(QDate.fromString(config['auto_start_date'], "yyyy-MM-dd"))
            if config.get('auto_end_date'):
                self.auto_end_date.setDate(QDate.fromString(config['auto_end_date'], "yyyy-MM-dd"))

            fetch_mode = config.get('auto_fetch_mode', 'fast')
            for i in range(self.auto_fetch_mode.count()):
                if self.auto_fetch_mode.itemData(i) == fetch_mode:
                    self.auto_fetch_mode.setCurrentIndex(i)
                    break

            self.auto_pdf_check.setChecked(config.get('auto_pdf', True))
            self.dify_upload_check.setChecked(config.get('dify_upload', True))
            self.timer_check.setChecked(config.get('timer_enabled', True))
            self.timer_freq_spin.setValue(config.get('timer_frequency', 30))

            unit = config.get('timer_unit', '分钟')
            for i in range(self.timer_unit_combo.count()):
                if self.timer_unit_combo.itemText(i) == unit:
                    self.timer_unit_combo.setCurrentIndex(i)
                    break

            self.dify_topic_input.setText(config.get('dify_topic', DEFAULT_TOPIC))

            self._load_wechat_articles()
            self.login_status = config.get('login_status', False)
            self.current_account = config.get('current_account', None)

            if self.login_status:
                self.login_status_label.setText("当前状态：已登录 ✅")
                self.login_status_label.setStyleSheet("color: #10b981; font-size: 14px; margin-top: 10px; font-weight: 500;")
            else:
                self.login_status_label.setText("当前状态：未登录 🚫")
                self.login_status_label.setStyleSheet("color: #ef4444; font-size: 14px; margin-top: 10px; font-weight: 500;")

            self.add_log_msg("系统", "✅ 已自动加载上次保存的配置")
        except Exception as e:
            self.add_log_msg("系统", f"⚠️ 加载配置失败：{e}")

    def init_ui(self):
        """初始化UI界面"""
        self.setWindowTitle(SYSTEM_TITLE)
        self.resize(*WINDOW_SIZE)

        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        self.create_system_header()
        self.create_content_area()
        self.apply_styles()

    def create_system_header(self):
        """创建系统头部"""
        header = QFrame()
        header.setFixedHeight(45)
        header.setObjectName("SystemHeaderFrame")

        h_layout = QHBoxLayout(header)
        h_layout.setContentsMargins(20, 0, 20, 0)

        system_title = QLabel(f"🔰 {SYSTEM_TITLE}")
        system_title.setObjectName("SystemHeaderTitle")
        menu_btn = QPushButton("☰")
        menu_btn.setObjectName("HeaderMenuBtn")

        h_layout.addWidget(system_title)
        h_layout.addStretch()
        h_layout.addWidget(menu_btn)
        self.main_layout.addWidget(header)

    def create_content_area(self):
        """创建内容区域"""
        content_widget = QWidget()
        content_layout = QHBoxLayout(content_widget)
        content_layout.setContentsMargins(20, 20, 20, 20)
        content_layout.setSpacing(25)

        self.create_left_log_panel(content_layout)
        self.create_right_function_cards(content_layout)

        self.main_layout.addWidget(content_widget)

    def create_left_log_panel(self, parent_layout):
        """创建左侧日志面板"""
        self.chat_list = QListWidget()
        self.chat_list.setObjectName("LogList")
        self.chat_list.setFocusPolicy(Qt.NoFocus)
        self.chat_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.chat_list.installEventFilter(self)
        parent_layout.addWidget(self.chat_list, stretch=6)

    def eventFilter(self, obj, event):
        """事件过滤器（调整日志气泡大小）"""
        if obj == self.chat_list and event.type() == QEvent.Resize:
            for i in range(self.chat_list.count()):
                item = self.chat_list.item(i)
                bubble = self.chat_list.itemWidget(item)
                if bubble:
                    max_width = self.chat_list.width() - LOG_LIST_MAX_WIDTH_OFFSET
                    bubble.msg_label.setMaximumWidth(max_width)
                    item.setSizeHint(bubble.sizeHint())
            return True
        return super().eventFilter(obj, event)

    def create_right_function_cards(self, parent_layout):
        """创建右侧功能卡片（双列布局）"""
        from PyQt5.QtWidgets import QScrollArea

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setObjectName("RightScrollArea")

        right_widget = QWidget()
        right_layout = QHBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(15)

        left_col_widget = QWidget()
        left_col = QVBoxLayout(left_col_widget)
        left_col.setContentsMargins(0, 0, 0, 0)
        left_col.setSpacing(12)

        right_col_widget = QWidget()
        right_col = QVBoxLayout(right_col_widget)
        right_col.setContentsMargins(0, 0, 0, 0)
        right_col.setSpacing(12)

        cards = self.create_all_cards()

        # 分配卡片：1与2放左列，3放右列
        left_col.addWidget(cards[0])
        left_col.addWidget(cards[1])
        right_col.addWidget(cards[2])

        left_col.addStretch()
        right_col.addStretch()

        right_layout.addWidget(left_col_widget, stretch=1)
        right_layout.addWidget(right_col_widget, stretch=1)

        scroll_area.setWidget(right_widget)
        parent_layout.addWidget(scroll_area, stretch=5)

    def create_all_cards(self):
        """创建精简后的功能卡片"""
        cards = []

        # 1. 微信登录卡片
        card1 = self.create_function_card("1. 微信登录")
        c1_layout = QVBoxLayout()
        self.login_btn = QPushButton("扫码登录")
        self.login_btn.setFixedHeight(40)
        self.login_btn.clicked.connect(self.start_login)
        self.login_status_label = QLabel("当前状态：未登录")
        self.login_status_label.setStyleSheet("color: #ef4444; font-size: 13px; margin-top: 8px;")
        c1_layout.addWidget(self.login_btn)
        c1_layout.addWidget(self.login_status_label)
        card1.setLayout(c1_layout)
        cards.append(card1)

        # 2. 自动化任务与持续监听配置卡片
        card2 = self.create_function_card("2. 自动化任务与持续监听配置")
        c2_layout = QVBoxLayout()
        c2_layout.setSpacing(10)

        # 保存目录选择（下沉置入自动化卡片）
        dir_group = QGroupBox("输出设置")
        dir_layout = QVBoxLayout()
        self.dir_btn = QPushButton("选择保存目录")
        self.dir_btn.setFixedHeight(35)
        self.dir_btn.clicked.connect(self.select_dir)
        self.dir_label = QLabel(f"保存路径: .../{os.path.basename(self.pdf_dir)}")
        self.dir_label.setStyleSheet("font-size: 12px; color: #e2e8f0;")
        dir_layout.addWidget(self.dir_btn)
        dir_layout.addWidget(self.dir_label)
        dir_group.setLayout(dir_layout)
        c2_layout.addWidget(dir_group)

        # 微信公众号配置
        c2_layout.addWidget(QLabel("微信公众号 (每行一个，空则搜索或按全局匹配):"))
        self.wechat_accounts_edit = QTextEdit()
        self.wechat_accounts_edit.setPlaceholderText("例如：中国应急管理\n中国消防")
        self.wechat_accounts_edit.setMaximumHeight(65)
        c2_layout.addWidget(self.wechat_accounts_edit)

        # 关键词配置
        c2_layout.addWidget(QLabel("微信关键词 (每行一个):"))
        self.wechat_keyword_edit = QTextEdit()
        self.wechat_keyword_edit.setPlaceholderText("道路塌陷\n燃气泄漏\n路面坍塌")
        self.wechat_keyword_edit.setMaximumHeight(60)
        c2_layout.addWidget(self.wechat_keyword_edit)

        # 日期范围配置
        date_row = QHBoxLayout()
        date_row.addWidget(QLabel("起始日期:"))
        self.auto_start_date = QDateEdit()
        self.auto_start_date.setDate(QDate.currentDate())
        self.auto_start_date.setDisplayFormat("yyyy-MM-dd")
        self.auto_start_date.setFixedHeight(32)
        date_row.addWidget(self.auto_start_date)
        date_row.addWidget(QLabel("至:"))
        self.auto_end_date = QDateEdit()
        self.auto_end_date.setDate(QDate.currentDate())
        self.auto_end_date.setDisplayFormat("yyyy-MM-dd")
        self.auto_end_date.setFixedHeight(32)
        date_row.addWidget(self.auto_end_date)
        c2_layout.addLayout(date_row)

        # 爬取方式选择
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("爬取方式:"))
        self.auto_fetch_mode = QComboBox()
        self.auto_fetch_mode.addItem("快速模式 (偏移量)", "fast")
        self.auto_fetch_mode.addItem("日期范围模式 (二分查找)", "date_range")
        self.auto_fetch_mode.setCurrentIndex(0)
        self.auto_fetch_mode.setFixedHeight(32)
        mode_row.addWidget(self.auto_fetch_mode)
        mode_row.addStretch()
        c2_layout.addLayout(mode_row)

        # PDF 和 Dify 配置
        pdf_row = QHBoxLayout()
        self.auto_pdf_check = QCheckBox("生成 PDF")
        self.auto_pdf_check.setChecked(True)
        self.dify_upload_check = QCheckBox("上传 Dify")
        self.dify_upload_check.setChecked(True)
        pdf_row.addWidget(self.auto_pdf_check)
        pdf_row.addWidget(self.dify_upload_check)
        c2_layout.addLayout(pdf_row)

        # 持续监听轮询配置
        timer_group = QGroupBox("实时监听与定时轮询配置")
        timer_layout = QHBoxLayout()
        self.timer_check = QCheckBox("启用定时轮询")
        self.timer_check.setChecked(True)
        self.timer_freq_spin = QSpinBox()
        self.timer_freq_spin.setRange(1, 1440)
        self.timer_freq_spin.setValue(30)
        self.timer_freq_spin.setFixedHeight(32)

        self.timer_unit_combo = QComboBox()
        self.timer_unit_combo.addItem("分钟")
        self.timer_unit_combo.addItem("小时")
        self.timer_unit_combo.setFixedHeight(32)

        timer_layout.addWidget(self.timer_check)
        timer_layout.addWidget(QLabel("每"))
        timer_layout.addWidget(self.timer_freq_spin)
        timer_layout.addWidget(self.timer_unit_combo)
        timer_layout.addWidget(QLabel("检查一次"))
        timer_layout.addStretch()
        timer_group.setLayout(timer_layout)
        c2_layout.addWidget(timer_group)

        # 进度显示
        self.auto_progress_label = QLabel("任务进度")
        self.auto_progress_percent = QLabel("0%")
        self.auto_progress_percent.setMinimumWidth(50)
        self.auto_progress_percent.setAlignment(Qt.AlignRight)
        progress_row = QHBoxLayout()
        progress_row.addWidget(self.auto_progress_label)
        progress_row.addStretch()
        progress_row.addWidget(self.auto_progress_percent)
        c2_layout.addLayout(progress_row)

        self.auto_pbar = QProgressBar()
        self.auto_pbar.setRange(0, 100)
        self.auto_pbar.setValue(0)
        self.auto_pbar.setFixedHeight(10)
        self.auto_pbar.setTextVisible(False)
        c2_layout.addWidget(self.auto_pbar)

        # 按钮控制行
        auto_btn_row = QHBoxLayout()
        self.auto_start_btn = QPushButton("▶ 启动监听任务")
        self.auto_start_btn.setFixedHeight(40)
        self.auto_start_btn.setStyleSheet("QPushButton { background-color: #10b981; } QPushButton:hover { background-color: #059669; }")
        self.auto_start_btn.clicked.connect(self.start_auto_timer)

        self.auto_run_once_btn = QPushButton("⚡ 立即抓取一次")
        self.auto_run_once_btn.setFixedHeight(40)
        self.auto_run_once_btn.clicked.connect(self.run_auto_once)

        self.auto_stop_btn = QPushButton("⏹ 停止任务")
        self.auto_stop_btn.setFixedHeight(40)
        self.auto_stop_btn.setEnabled(False)
        self.auto_stop_btn.setStyleSheet("QPushButton { background-color: #dc2626; } QPushButton:disabled { background-color: #fca5a5; }")
        self.auto_stop_btn.clicked.connect(self.stop_auto_timer)

        auto_btn_row.addWidget(self.auto_start_btn)
        auto_btn_row.addWidget(self.auto_run_once_btn)
        auto_btn_row.addWidget(self.auto_stop_btn)
        c2_layout.addLayout(auto_btn_row)

        card2.setLayout(c2_layout)
        cards.append(card2)

        # 3. Dify 总结上传卡片
        card3 = self.create_function_card("3. Dify 总结上传")
        c3_layout = QVBoxLayout()
        c3_layout.setSpacing(8)

        self.dify_topic_input = QLineEdit()
        self.dify_topic_input.setPlaceholderText("主题")
        self.dify_topic_input.setText(DEFAULT_TOPIC)
        self.dify_topic_input.setFixedHeight(32)
        c3_layout.addWidget(QLabel("主题"))
        c3_layout.addWidget(self.dify_topic_input)

        dify_row = QHBoxLayout()
        self.dify_summarize_btn = QPushButton("AI 总结")
        self.dify_summarize_btn.setFixedHeight(35)
        self.dify_summarize_btn.clicked.connect(self.start_dify_summary)

        self.dify_upload_btn = QPushButton("上传")
        self.dify_upload_btn.setFixedHeight(35)
        self.dify_upload_btn.clicked.connect(self.start_dify_upload)

        dify_row.addWidget(self.dify_summarize_btn)
        dify_row.addWidget(self.dify_upload_btn)
        c3_layout.addLayout(dify_row)

        self.dify_status_label = QLabel("状态：已连接")
        self.dify_status_label.setStyleSheet("color: #10b981; font-size: 13px;")
        c3_layout.addWidget(self.dify_status_label)

        card3.setLayout(c3_layout)
        cards.append(card3)

        return cards

    def create_function_card(self, title_text):
        """创建功能卡片容器"""
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
        """添加日志消息到界面"""
        item = QListWidgetItem(self.chat_list)
        bubble = ChatBubble(role, msg)

        max_width = self.chat_list.width() - LOG_LIST_MAX_WIDTH_OFFSET
        bubble.msg_label.setMaximumWidth(max_width)

        item.setSizeHint(bubble.sizeHint())
        self.chat_list.setItemWidget(item, bubble)
        self.chat_list.scrollToBottom()

    # ------------------------------
    # 功能逻辑：登录相关
    # ------------------------------
    def start_login(self):
        """启动登录流程"""
        self.add_log_msg("系统", "📢 请准备扫码登录")
        self.login_btn.setEnabled(False)
        self.login_status_label.setText("当前状态：登录中 🕒")
        self.login_status_label.setStyleSheet("color: #f97316; font-size: 14px; margin-top: 10px; font-weight: 500;")

        self.worker = SpiderWorker(self.spider_runner, "login")
        self.worker.log_signal.connect(self.add_log_msg)
        self.worker.finish_signal.connect(self.on_login_finished)
        self.worker.start()

    def on_login_finished(self, success, msg, data):
        """登录完成回调"""
        self.login_btn.setEnabled(True)
        if success:
            self.login_status = True
            if data and isinstance(data, dict):
                self.current_account = data
            self.login_status_label.setText("当前状态：已登录 ✅")
            self.login_status_label.setStyleSheet("color: #10b981; font-size: 14px; margin-top: 10px; font-weight: 500;")
            self.add_log_msg("系统", "🎉 微信登录成功，可开启自动化持续监听任务。")
            self.save_user_config()
        else:
            self.login_status = False
            self.login_status_label.setText("当前状态：未登录 🚫")
            self.login_status_label.setStyleSheet("color: #ef4444; font-size: 14px; margin-top: 10px; font-weight: 500;")
            self.add_log_msg("系统", "❌ 微信登录失败，请重新点击「扫码登录」重试。")

    # ------------------------------
    # 功能逻辑：输出目录相关
    # ------------------------------
    def select_dir(self):
        """选择 PDF 保存目录"""
        path = QFileDialog.getExistingDirectory(self, "选择PDF保存目录")
        if path:
            self.pdf_dir = path
            self.dir_label.setText(f"保存路径: .../{os.path.basename(path)}")
            self.add_log_msg("系统", f"📁 PDF保存目录已设置为：{path}")
            self.save_user_config()

    # ------------------------------
    # Dify 总结与上传
    # ------------------------------
    def start_dify_summary(self):
        """启动 AI 总结"""
        topic = self.dify_topic_input.text().strip()
        wechat_articles = getattr(self, '_last_wechat_articles', [])
        if not wechat_articles:
            self.add_log_msg("系统", "⚠️ 暂无可总结的内容，请先执行微信抓取任务。")
            return

        all_items = [{
            'title': article.get('title', ''),
            'content': article.get('content', '') or article.get('abstract', ''),
            'source': '微信公众号'
        } for article in wechat_articles]

        self.add_log_msg("用户", f"开始 AI 总结，主题：{topic}, 内容数：{len(all_items)}")
        self.dify_summarize_btn.setEnabled(False)

        try:
            deduped = self.summarizer.deduplicate(all_items)
            briefing = self.summarizer.generate_briefing(deduped, topic)
            ai_summary = self.summarizer.ai_summarize(deduped, topic)

            result = f"{briefing}\n\n{'='*50}\n\n# AI 智能总结\n\n{ai_summary}"
            self._last_summary = result
            self.add_log_msg("系统", f"✅ AI 总结完成")
            self.add_log_msg("系统", result[:500] + "..." if len(result) > 500 else result)

        except Exception as e:
            self.add_log_msg("系统", f"❌ AI 总结失败：{e}")
        finally:
            self.dify_summarize_btn.setEnabled(True)

    def start_dify_upload(self):
        """上传到 Dify 知识库"""
        topic = self.dify_topic_input.text().strip()
        if not hasattr(self, '_last_summary') or not self._last_summary:
            self.add_log_msg("系统", "⚠️ 暂无可上传的总结，请先生成 AI 总结。")
            return

        self.add_log_msg("用户", f"开始上传到 Dify 知识库，主题：{topic}")
        self.dify_upload_btn.setEnabled(False)

        self.upload_worker = UploadWorker(DIFY_DATASET_ID, self._last_summary, topic, self.dify_client)
        self.upload_worker.upload_success.connect(self.on_upload_success)
        self.upload_worker.upload_error.connect(self.on_upload_error)
        self.upload_worker.start()

    def on_upload_success(self):
        self.dify_upload_btn.setEnabled(True)
        self.add_log_msg("系统", "✅ 已成功上传到 Dify 知识库。")

    def on_upload_error(self, msg):
        self.dify_upload_btn.setEnabled(True)
        self.add_log_msg("系统", f"❌ 上传失败：{msg}")

    # ------------------------------
    # 自动化任务与持续监听逻辑
    # ------------------------------
    def build_auto_config(self):
        """构建自动化任务配置对象"""
        config = AutoTaskConfig()
        config.wechat_enabled = True

        accounts_text = self.wechat_accounts_edit.toPlainText().strip()
        config.wechat_accounts = [a.strip() for a in accounts_text.split("\n") if a.strip()]

        config.wechat_keywords = [k.strip() for k in self.wechat_keyword_edit.toPlainText().split("\n") if k.strip()]
        config.start_date = self.auto_start_date.date().toString("yyyy-MM-dd")
        config.end_date = self.auto_end_date.date().toString("yyyy-MM-dd")
        config.wechat_fetch_mode = self.auto_fetch_mode.currentData()
        config.pdf_base_dir = self.pdf_dir
        config.generate_pdf = self.auto_pdf_check.isChecked()
        config.dify_upload_enabled = self.dify_upload_check.isChecked()

        return config

    def validate_auto_config(self, config):
        """验证配置有效性"""
        if not config.wechat_accounts and not config.wechat_keywords:
            self.add_log_msg("系统", "⚠️ 请配置至少一个微信公众号名称或关键词！")
            return False

        if self.auto_start_date.date() > self.auto_end_date.date():
            self.add_log_msg("系统", "⚠️ 起始日期不能晚于结束日期！")
            return False

        return True

    def run_auto_once(self):
        """立即执行一次自动化任务"""
        if not is_playwright_installed():
            self.add_log_msg("系统", "⚠️ 无法启动自动化任务：Playwright 浏览器组件未完整安装！")
            QMessageBox.warning(self, "浏览器组件未就绪", "Playwright 浏览器组件未完整安装，已启动后台自动下载，请稍后再试！")
            if not self.installer_thread.isRunning():
                self.installer_thread.start()
            return

        if not self.login_status:
            self.add_log_msg("系统", "⚠️ 操作失败：未登录微信")
            QMessageBox.warning(self, "权限提示", "请先完成微信扫码登录！")
            return

        config = self.build_auto_config()
        if not self.validate_auto_config(config):
            return

        if self.auto_pdf_check.isChecked():
            os.makedirs(config.get_wechat_pdf_dir(), exist_ok=True)

        self.add_log_msg("用户", f"""
⚡ 开始执行自动化抓取任务：
- 微信公众号：{len(config.wechat_accounts)} 个 ({', '.join(config.wechat_accounts) if config.wechat_accounts else '全局'})
- 微信关键词：{len(config.wechat_keywords)} 个
- 日期范围：{config.start_date} 至 {config.end_date}
- 爬取模式：{config.wechat_fetch_mode}
- 保存目录：{config.pdf_base_dir}
- 生成 PDF: {"是" if config.generate_pdf else "否"}
- 上传 Dify: {"是" if config.dify_upload_enabled else "否"}
        """)

        self.auto_run_once_btn.setEnabled(False)
        self.auto_start_btn.setEnabled(False)
        self.auto_stop_btn.setEnabled(True)
        self.auto_pbar.setValue(0)
        self.auto_progress_percent.setText("0%")

        self.auto_worker = AutoTaskWorker(
            self.spider_runner,
            self.weibo_runner,
            self.rss_collector,
            self.dify_client,
            config
        )
        self.auto_worker.log_signal.connect(self.add_log_msg)
        self.auto_worker.progress_signal.connect(self.update_auto_progress)
        self.auto_worker.finish_signal.connect(self.on_auto_task_finished)
        self.auto_worker.start()

    def start_auto_timer(self):
        """启动实时监听任务（从当前时间开始监听到手动结束）"""
        if not is_playwright_installed():
            self.add_log_msg("系统", "⚠️ 无法启动监听任务：Playwright 浏览器组件未完整安装！")
            QMessageBox.warning(self, "浏览器组件未就绪", "Playwright 浏览器组件未完整安装，已启动后台自动下载，请稍后再试！")
            if not self.installer_thread.isRunning():
                self.installer_thread.start()
            return

        if not self.login_status:
            self.add_log_msg("系统", "⚠️ 操作失败：未登录微信")
            QMessageBox.warning(self, "权限提示", "请先完成微信扫码登录！")
            return

        config = self.build_auto_config()
        if not self.validate_auto_config(config):
            return

        # 记录启动基准时刻为当前时间
        self.is_listening_active = True
        self.listening_start_time = datetime.now()
        self.auto_start_date.setDate(QDate.currentDate())

        self.add_log_msg("系统", f"📌 实时监听任务已启动（基准时间：{self.listening_start_time.strftime('%Y-%m-%d %H:%M:%S')}）")
        self.add_log_msg("系统", "📢 系统将从当前时间起持续轮询监控新文章，直至手动点击「停止」按钮。")

        self.auto_start_btn.setEnabled(False)
        self.auto_run_once_btn.setEnabled(False)
        self.auto_stop_btn.setEnabled(True)
        self.timer_check.setEnabled(False)
        self.timer_freq_spin.setEnabled(False)
        self.timer_unit_combo.setEnabled(False)

        # 立即开启第一轮抓取
        self.run_auto_once()

    def stop_auto_timer(self):
        """手动停止监听任务"""
        self.add_log_msg("系统", "🛑 正在手动停止监听任务...")
        self.is_listening_active = False

        if hasattr(self, 'auto_timer') and self.auto_timer:
            self.auto_timer.stop()

        if hasattr(self, 'auto_worker') and self.auto_worker:
            self.auto_worker.stop()

        self.auto_start_btn.setEnabled(True)
        self.auto_run_once_btn.setEnabled(True)
        self.auto_stop_btn.setEnabled(False)
        self.timer_check.setEnabled(True)
        self.timer_freq_spin.setEnabled(True)
        self.timer_unit_combo.setEnabled(True)

        self.add_log_msg("系统", "⏹ 实时监听任务已手动结束。")

    def update_auto_progress(self, val):
        """更新自动化任务进度"""
        self.auto_pbar.setValue(val)
        self.auto_progress_percent.setText(f"{val}%")

    def on_auto_task_finished(self, success, msg):
        """自动化任务轮次完成回调"""
        if success:
            self.add_log_msg("系统", f"✅ {msg}")
        else:
            self.add_log_msg("系统", f"⚠️ {msg}")

        # 判断是否处于持续监听模式且勾选了定时轮询
        if getattr(self, 'is_listening_active', False) and self.timer_check.isChecked():
            freq = self.timer_freq_spin.value()
            unit = self.timer_unit_combo.currentText()
            interval_ms = freq * 60 * 1000 if unit == "分钟" else freq * 3600 * 1000
            self.add_log_msg("系统", f"⏳ 本轮监听完成。下一个轮询监听周期将在 {freq} {unit} 后自动启动...")

            if not hasattr(self, 'auto_timer') or not self.auto_timer:
                self.auto_timer = QTimer(self)
                self.auto_timer.setSingleShot(True)
                self.auto_timer.timeout.connect(self.run_auto_once)

            self.auto_timer.start(interval_ms)
        else:
            self.auto_start_btn.setEnabled(True)
            self.auto_run_once_btn.setEnabled(True)
            self.auto_stop_btn.setEnabled(False)
            self.timer_check.setEnabled(True)
            self.timer_freq_spin.setEnabled(True)
            self.timer_unit_combo.setEnabled(True)

    # ------------------------------
    # 样式设置
    # ------------------------------
    def apply_styles(self):
        """应用全局样式表"""
        qss = """
        * {
            font-family: "Microsoft YaHei", "SimSun", sans-serif;
        }

        QMainWindow { background-color: #f1f5f9; }

        QFrame#SystemHeaderFrame {
            background-color: #0f2c52;
            border: none;
        }
        QLabel#SystemHeaderTitle {
            color: #ffffff;
            font-size: 18px;
            font-weight: bold;
        }

        QListWidget#LogList {
            background-color: #94a3b8;
            border-radius: 8px;
            border: none;
        }

        QPushButton {
            background-color: #0f2c52;
            color: #ffffff;
            border-radius: 6px;
            border: none;
            font-weight: bold;
            font-size: 15px;
        }
        QPushButton:hover { background-color: #1e40af; }
        QPushButton:disabled { background-color: #64748b; }

        QLineEdit, QSpinBox, QDateEdit, QTextEdit, QComboBox {
            border: 1px solid #cbd5e1;
            border-radius: 4px;
            padding: 6px;
            background-color: #ffffff;
            color: #1e293b;
            font-size: 14px;
        }

        QCheckBox {
            color: #ffffff;
            font-size: 14px;
        }

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

        QPushButton#HeaderMenuBtn {
            color: white; font-size: 22px;
            background: transparent; border: none;
        }

        QDateEdit {
            min-width: 130px;
        }

        QScrollArea#RightScrollArea {
            border: none;
            background-color: transparent;
        }
        QScrollArea#RightScrollArea > QWidget > QWidget {
            background-color: transparent;
        }
        """
        self.setStyleSheet(qss)

    def closeEvent(self, event):
        """窗口关闭事件 - 保存配置"""
        try:
            self.save_user_config()
        except Exception as e:
            print(f"保存配置失败：{e}")
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = WeChatSpiderUI()
    window.show()
    sys.exit(app.exec_())