# 配置常量定义
import os

DEFAULT_PDF_DIR = "./wechat_pdf"
SYSTEM_TITLE = "道路塌陷爬虫系统"
WINDOW_SIZE = (1400, 900)  # 增大窗口以适应所有功能卡片
LOG_LIST_MAX_WIDTH_OFFSET = 80  # 日志气泡宽度偏移量

# Dify 配置
DIFY_API_BASE = "http://dify.gmdi.cn/v1"
# 知识库 API Key (用于上传文档)
DIFY_DATASET_API_KEY = "dataset-5q55ouqiSx5P5ibfDpFSPYmS"
DIFY_DATASET_ID = "19b42fa8-ae5c-43d0-910c-942cae6666f3"
# 聊天应用 API Key (用于 AI 总结) - 请在 Dify 平台创建聊天应用后获取
DIFY_CHAT_API_KEY = "app-bIx82tDu3BVtR0yZfLGUVVpK"

# 采集主题
DEFAULT_TOPIC = "道路塌陷"

# RSS 默认配置
DEFAULT_RSS_SOURCES = [
    {"name": "百度新闻 - 道路塌陷", "url": "http://news.baidu.com/ns?word=%E9%81%93%E8%B7%AF%E5%A1%8C%E9%99%B7&tn=newsrss"},
]

# 微博默认关键词
DEFAULT_WEIBO_KEYWORD = "道路塌陷"

# ==================== 自动化任务配置 ====================

class AutoTaskConfig:
    """自动化任务配置类"""
    def __init__(self):
        # 微信公众号开启
        self.wechat_enabled = True

        # 微信公众号列表（假如有 fakeid 则用元组 (名称，fakeid)）
        self.wechat_accounts = []

        # 微信关键词（列表，满足任一即爬取）
        self.wechat_keywords = []

        # PDF 保存配置
        self.pdf_base_dir = "./wechat_pdf"
        self.generate_pdf = True

        # Dify 上传配置
        self.dify_upload_enabled = True
        self.dify_dataset_id = DIFY_DATASET_ID
        self.dify_dataset_api_key = DIFY_DATASET_API_KEY

        # 爬取配置
        self.pages_per_account = 5
        self.date_range_days = 7

        # 爬取方式：'fast' (快速偏移量) 或 'date_range' (日期范围二分查找)
        self.wechat_fetch_mode = 'fast'  # 'fast' | 'date_range'

        # 日期范围配置（自动化任务）
        self.start_date = None
        self.end_date = None

    def get_wechat_pdf_dir(self):
        return self.pdf_base_dir

    def to_dict(self):
        return {
            "wechat_enabled": self.wechat_enabled,
            "wechat_accounts": self.wechat_accounts,
            "wechat_keywords": self.wechat_keywords,
            "pdf_base_dir": self.pdf_base_dir,
            "generate_pdf": self.generate_pdf,
            "dify_upload_enabled": self.dify_upload_enabled,
            "pages_per_account": self.pages_per_account,
            "date_range_days": self.date_range_days,
            "wechat_fetch_mode": self.wechat_fetch_mode,
            "start_date": self.start_date,
            "end_date": self.end_date,
        }

    @classmethod
    def from_dict(cls, data):
        config = cls()
        config.wechat_enabled = data.get("wechat_enabled", True)
        config.wechat_accounts = data.get("wechat_accounts", [])
        config.wechat_keywords = data.get("wechat_keywords", [])
        config.pdf_base_dir = data.get("pdf_base_dir", "./wechat_pdf")
        config.generate_pdf = data.get("generate_pdf", True)
        config.dify_upload_enabled = data.get("dify_upload_enabled", True)
        config.pages_per_account = data.get("pages_per_account", 5)
        config.date_range_days = data.get("date_range_days", 7)
        config.wechat_fetch_mode = data.get("wechat_fetch_mode", "fast")
        config.start_date = data.get("start_date")
        config.end_date = data.get("end_date")
        return config