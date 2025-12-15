from spider.wechat.run import WeChatSpiderRunner

# 创建爬虫实例
wechat_runner = WeChatSpiderRunner()

# 登录
if not wechat_runner.login():
    print("微信登录失败")
    exit(1)

# 搜索公众号
accounts = wechat_runner.search_account("腾讯科技")
if not accounts:
    print("未找到匹配的微信公众号")
    exit(1)

# 爬取单个公众号
wechat_runner.scrape_single_account(
    "腾讯科技",
    pages=1,
    days=7,
    generate_pdf=True,
    pdf_output_dir="./wechat_pdf"
)