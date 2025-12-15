# 修改 main.py 头部，添加 Playwright 浏览器自动安装
import subprocess
import sys


def install_playwright_browser():
    try:
        # 检查并安装 Chromium
        subprocess.check_call([sys.executable, "-m", "playwright", "install", "chromium"])
        print("Chromium 浏览器安装成功")
    except Exception as e:
        print(f"浏览器安装失败，请手动执行：playwright install chromium，错误：{e}")
        sys.exit(1)


# 在登录逻辑前执行安装
if __name__ == "__main__":
    # 自动安装 Playwright 浏览器（首次运行时触发）
    install_playwright_browser()

    # 原有项目逻辑
    from spider.wechat.run import WeChatSpiderRunner

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

    # 爬取并生成PDF
    wechat_runner.scrape_single_account(
        name="腾讯科技",
        pages=1,
        days=7,
        generate_pdf=True,
        pdf_output_dir="./wechat_pdf"
    )