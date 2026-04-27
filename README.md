# 道路塌陷爬虫系统 - MediaSpider

一个集成了微信公众号、微博、RSS 采集和 AI 总结的新闻采集系统，支持将总结上传到 Dify 知识库。

## 功能特性

### 已实现功能
| 功能 | 状态 | 说明 |
|------|------|------|
| 微信登录 | ✅ | Selenium 扫码登录，缓存 4 天 |
| 公众号搜索 | ✅ | 搜索公众号并获取 fakeid |
| 微信文章爬取 | ✅ | 按页数/日期/关键词筛选 |
| 文章 PDF 生成 | ✅ | Playwright 渲染生成 PDF |
| 定时任务 | ✅ | 定时自动爬取公众号 |
| **微博爬取** | ✅ | 关键词搜索微博内容 |
| **RSS 采集** | ✅ | 支持自定义 RSS 源 |
| **AI 总结** | ✅ | Dify AI 生成新闻简报 |
| **知识库上传** | ✅ | 上传总结到 Dify 知识库 |

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 安装浏览器

程序首次启动会自动安装 Playwright 浏览器，或手动执行：
```bash
playwright install chromium
```

### 3. 配置 Dify（可选）

编辑 `config.py` 修改 Dify 配置：

```python
DIFY_API_BASE = "http://dify.gmdi.cn/v1"
DIFY_API_KEY = "dataset-5q55ouqiSx5P5ibfDpFSPYmS"
DIFY_DATASET_ID = "7414c8c4-1671-4c82-b47b-d8f18d05805f"
```

### 4. 运行程序

**Windows:**
```bash
run.bat
```

**跨平台:**
```bash
python main.py
```

## 界面功能说明

### 1. 微信登录
- 点击"扫码登录"，用手机微信扫码登录
- 登录成功后缓存 token 和 cookie，4 天内有效

### 2. 公众号搜索
- 输入公众号名称搜索
- 自动选择第一个匹配结果

### 3. 爬取设置与执行
- **筛选关键词**: 多个用逗号分隔
- **爬取页数**: 每页约 5 篇文章
- **日期范围**: 起始和结束日期
- **生成 PDF**: 勾选后为每篇文章生成 PDF

### 4. 定时任务设置
- 输入公众号列表（每行一个）
- 设置爬取频率（小时/次）
- 设置开始时间

### 5. 微博爬取
- 输入搜索关键词（默认：道路塌陷）
- 设置爬取页数（最多 20 页）
- 点击"开始爬取微博"

### 6. RSS 采集
- 输入关键词过滤
- 点击"开始 RSS 采集"
- 结果保存到 CSV

### 7. Dify 总结与上传
- **AI 总结**: 对已采集的微博/RSS 新闻进行 AI 总结
- **上传知识库**: 将总结上传到 Dify 知识库

## 项目结构

```
MediaSpider/
├── main.py              # 主程序入口（PyQt5 UI）
├── config.py            # 配置文件
├── threads.py           # 后台线程
├── widgets.py           # 自定义组件
├── requirements.txt     # Python 依赖
├── run.bat              # Windows 启动脚本
│
├── spider/              # 爬虫模块
│   ├── wechat/          # 微信爬虫
│   │   ├── run.py       # 运行器
│   │   ├── login.py     # 登录
│   │   └── scraper.py   # 爬取
│   ├── weibo/           # 微博爬虫
│   │   └── run.py       # 微博搜索/爬取
│   ├── rss/             # RSS 采集
│   │   └── collector.py # RSS 解析
│   ├── dify/            # Dify 集成
│   │   ├── client.py    # API 客户端
│   │   └── summarizer.py# 新闻总结
│   ├── db/              # 数据库
│   └── log/             # 日志
```

## 依赖说明

核心依赖：
- `PyQt5` - 图形界面
- `selenium` - 微信登录自动化
- `playwright` - PDF 生成
- `feedparser` - RSS 解析
- `thefuzz` - 文本去重
- `beautifulsoup4` - HTML 解析

## 常见问题

### 微信登录失败
- 检查网络连接
- 确保二维码能正常显示
- 清除 `wechat_cache.json` 后重试

### PDF 生成失败
- 确保已安装浏览器：`playwright install chromium`
- 检查文章链接是否有效

### Dify 上传失败
- 检查 `config.py` 中的 API Key 和 Dataset ID
- 确认 Dify 服务可访问

## 许可证

MIT License
