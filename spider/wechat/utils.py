#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号爬虫 - 工具函数模块
==========================

提供爬虫过程中需要的各种实用工具函数,包括公众号搜索、
文章URL获取、内容解析等功能,这些函数被其他模块调用。

主要功能:
    1. 公众号搜索 - 根据名称获取公众号fakeid
    2. 文章列表获取 - 分页获取公众号文章列表
    3. 时间戳转换 - 将时间戳转换为可读格式
    4. 关键词筛选 - 根据关键词筛选文章标题

版本: 1.0
"""

import requests
import random
import time
import os
import csv
from datetime import datetime
from tqdm import tqdm
import bs4
from markdownify import MarkdownConverter

# 导入日志模块
from spider.wechat.config import REQUEST_DELAY, DEFAULT_FETCH_MODE
from spider.log.utils import logger


class ImageBlockConverter(MarkdownConverter):
    """
    Create a custom MarkdownConverter that adds two newlines after an image
    """
    def convert_img(self, el, text, parent_tags):
        alt = el.attrs.get('alt', None) or ''
        src = el.attrs.get('src', None) or ''
        if not src:
            src = el.attrs.get('data-src', None) or ''
        title = el.attrs.get('title', None) or ''
        title_part = ' "%s"' % title.replace('"', r'\"') if title else ''
        if ('_inline' in parent_tags
                and el.parent.name not in self.options['keep_inline_images_in']):
            return alt

        return '\n![%s](%s%s)\n' % (alt, src, title_part)

# Create shorthand method for conversion
def md(soup, **options):
    return ImageBlockConverter(**options).convert_soup(soup)



def get_fakid(headers, tok, query):
    """
    获取公众号fakeid
    
    Args:
        headers: 请求头,包含cookie等认证信息
        tok: 访问token
        query: 公众号名称关键词
        
    Returns:
        list: 包含匹配公众号信息的字典列表,每个字典包含wpub_name和wpub_fakid
    """
    url = 'https://mp.weixin.qq.com/cgi-bin/searchbiz'
    data = {
        'action': 'search_biz',
        'scene': 1,
        'begin': 0,
        'count': 10,
        'query': query,
        'token': tok,
        'lang': 'zh_CN',
        'f': 'json',
        'ajax': '1',
    }
    
    # 发送请求
    r = requests.get(url, headers=headers, params=data)
    
    # 解析json
    dic = r.json()
    
    # 获取公众号名称、fakeid
    wpub_list = [
        {
            'wpub_name': item['nickname'],
            'wpub_fakid': item['fakeid']
        }
        for item in dic['list']
    ]
    
    return wpub_list


def get_articles_list(page_num, start_page, fakeid, token, headers, fetch_mode="fast"):
    """
    按偏移量获取公众号文章列表

    Args:
        page_num: 要获取的页数
        start_page: 起始页码
        fakeid: 公众号的 fakeid
        token: 访问 token
        headers: 请求头
        fetch_mode: 爬取模式 ("fast" / "date_range")

    Returns:
        tuple: (title_list, link_list, timestamp_list)
    """
    url = 'https://mp.weixin.qq.com/cgi-bin/appmsg'
    title = []
    link = []
    update_time = []

    # 根据模式设置延迟
    delay_config = REQUEST_DELAY.get(fetch_mode, REQUEST_DELAY["fast"])
    delay_range = (delay_config["min"], delay_config["max"])

    with tqdm(total=page_num) as pbar:
        for page in range(start_page, start_page + page_num):
            # 构建请求参数
            data = {
                'action': 'list_ex',
                'begin': page * 5,
                'count': '5',
                'fakeid': fakeid,
                'type': '9',
                'query': '',
                'token': token,
                'lang': 'zh_CN',
                'f': 'json',
                'ajax': '1',
            }

            # 随机延时，避免被反爬
            delay = random.uniform(*delay_range)
            logger.info(f"[{fetch_mode} 模式] 等待 {delay:.1f} 秒后发送请求...")
            time.sleep(delay)

            r = requests.get(url, headers=headers, params=data)
            # 解析 json
            dic = r.json()

            # 检查是否有文章列表
            if 'app_msg_list' not in dic:
                logger.warning(f"未找到文章列表，响应为：{dic}")
                break

            for item in dic['app_msg_list']:
                title.append(item['title'])
                link.append(item['link'])
                update_time.append(item['update_time'])

            pbar.update(1)

    return title, link, update_time


def get_articles_by_offset(fakeid, token, headers, begin_offset=0, count=5, fetch_mode='fast'):
    """
    按偏移量获取公众号文章列表 (带频率限制保护)

    Args:
        fakeid: 公众号的 fakeid
        token: 访问 token
        headers: 请求头
        begin_offset: 起始偏移量 (默认 0,即最新)
        count: 每次获取数量 (默认 5)
        fetch_mode: 爬取模式 ('fast' / 'date_range' / 'binary_search')

    Returns:
        list: 文章列表,每项包含 title, link, update_time, digest 等字段
    """
    url = 'https://mp.weixin.qq.com/cgi-bin/appmsg'
    data = {
        'action': 'list_ex',
        'begin': begin_offset,
        'count': str(count),
        'fakeid': fakeid,
        'type': '9',
        'query': '',
        'token': token,
        'lang': 'zh_CN',
        'f': 'json',
        'ajax': '1',
    }

    # 根据爬取模式设置延迟
    delay_config = {
        'fast': (3, 5),
        'date_range': (15, 25),
        'binary_search': (20, 30)
    }
    delay_range = delay_config.get(fetch_mode, (3, 5))
    delay = random.uniform(*delay_range)

    logger.info(f"[{fetch_mode}模式] 偏移量 {begin_offset},等待 {delay:.1f} 秒后发送请求...")
    time.sleep(delay)

    # 指数退避重试机制
    max_retries = 3
    base_wait = 5  # 基础等待时间 (秒)

    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=headers, params=data, timeout=30)
        except requests.RequestException as e:
            logger.warning(f"请求异常：{e}, 准备重试...")
            if attempt < max_retries - 1:
                wait_time = base_wait * (2 ** attempt)
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            return []

        # 检查响应状态
        if r.status_code != 200:
            logger.warning(f"请求失败,状态码：{r.status_code}, 准备重试...")
            if attempt < max_retries - 1:
                wait_time = base_wait * (2 ** attempt)
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            return []

        try:
            dic = r.json()
        except json.JSONDecodeError:
            logger.warning("JSON 解析失败,准备重试...")
            if attempt < max_retries - 1:
                wait_time = base_wait * (2 ** attempt)
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            return []

        # 检查是否是频率限制 (ret 200013)
        ret_code = dic.get('base_resp', {}).get('ret', 0)
        if ret_code == 200013:
            wait_time = base_wait * (2 ** attempt)  # 5s, 10s, 20s
            logger.warning(f"触发频率限制 (ret 200013),等待 {wait_time} 秒后重试... (尝试 {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                logger.info(f"等待 {wait_time} 秒...")
                time.sleep(wait_time)
                # 额外随机延迟,避免规律性请求
                time.sleep(random.uniform(2, 5))
                continue
            logger.error(f"重试 {max_retries} 次后仍触发频率限制,建议暂停爬取至少 30 分钟后再试")
            return []

        # 其他业务错误
        if ret_code != 0:
            logger.warning(f"业务错误码：{ret_code}, 响应：{dic}")
            if attempt < max_retries - 1:
                wait_time = base_wait * (2 ** attempt)
                logger.info(f"等待 {wait_time} 秒后重试...")
                time.sleep(wait_time)
                continue
            return []

        # 请求成功
        break
    else:
        # 重试多次仍失败
        logger.warning(f"请求失败,最终响应为：{dic}")
        return []

    if 'app_msg_list' not in dic:
        logger.warning(f"未找到文章列表,响应为：{dic}")
        return []

    articles = []
    for item in dic['app_msg_list']:
        articles.append({
            'title': item.get('title', ''),
            'link': item.get('link', ''),
            'update_time': item.get('update_time', 0),
            'digest': item.get('digest', ''),
            'cover': item.get('cover', ''),
        })

    logger.info(f"[{fetch_mode}模式] 成功获取 {len(articles)} 篇文章 (offset={begin_offset})")
    return articles


def get_articles_by_date_range(fakeid, token, headers, start_date, end_date, max_pages=100, progress_callback=None):
    """
    按日期范围获取公众号文章(使用二分查找定位 + 持续爬取)

    Args:
        fakeid: 公众号的 fakeid
        token: 访问 token
        headers: 请求头
        start_date: 开始日期 (datetime.date 对象)
        end_date: 结束日期 (datetime.date 对象)
        max_pages: 最大爬取页数限制(默认 100 页,约 500 篇文章)
        progress_callback: 进度回调函数 callback(current_offset, total_checked)

    Returns:
        list: 在日期范围内的文章列表
    """
    from datetime import datetime

    def offset_to_date(offset):
        """根据偏移量获取该页最早文章的日期(用于二分查找)"""
        articles = get_articles_by_offset(fakeid, token, headers, begin_offset=offset, count=5, fetch_mode='binary_search')
        if not articles:
            return None
        # 返回该页最早文章的日期(列表最后一项)
        return datetime.fromtimestamp(articles[-1]['update_time']).date()

    # 1. 先检查最新一页的日期
    latest_articles = get_articles_by_offset(fakeid, token, headers, begin_offset=0, count=5, fetch_mode='date_range')
    if not latest_articles:
        logger.warning("该公众号没有文章")
        return []

    # 最新文章的日期(列表第一项)
    latest_date = datetime.fromtimestamp(latest_articles[0]['update_time']).date()

    # 如果最新文章日期早于结束日期,说明没有符合条件的文章
    if latest_date < end_date:
        logger.info(f"最新文章日期 ({latest_date}) 早于目标结束日期 ({end_date}),无符合条件的文章")
        return []

    # 2. 检查最后一页(max_pages*5)的日期,判断是否需要二分查找
    max_offset = max_pages * 5
    oldest_date = offset_to_date(max_offset)

    # 如果最老日期仍晚于开始日期,说明所有文章都在范围内,直接获取
    if oldest_date and oldest_date >= start_date:
        logger.info(f"所有文章都在目标日期范围内,全量获取")
        result = []
        current_offset = 0
        while current_offset < max_offset:
            articles = get_articles_by_offset(fakeid, token, headers, begin_offset=current_offset, count=5, fetch_mode='date_range')
            if not articles:
                break

            # 过滤在结束日期之前的文章
            for article in articles:
                article_date = datetime.fromtimestamp(article['update_time']).date()
                if article_date <= end_date:
                    result.append(article)

            current_offset += 5
            # 额外延迟(已在 get_articles_by_offset 中处理)
            if progress_callback:
                progress_callback(current_offset, max_offset)

        return result

    # 3. 最老日期早于开始日期,需要用二分法定位开始日期所在的页
    if oldest_date and oldest_date < start_date:
        logger.info(f"使用二分法定位开始日期 {start_date} 所在的页...")
        low, high = 0, max_offset
        binary_search_steps = 0

        while low < high:
            mid = (low + high) // 2
            mid_date = offset_to_date(mid)
            binary_search_steps += 1

            if progress_callback:
                progress_callback(mid, max_offset)

            if mid_date is None:
                # 该偏移量没有文章,说明超出范围
                logger.info(f"二分查找步骤 {binary_search_steps}: offset={mid}, 无文章")
                high = mid
                continue

            logger.info(f"二分查找步骤 {binary_search_steps}: offset={mid}, 日期={mid_date}")

            if mid_date < start_date:
                # 中间日期早于开始日期,需要往新日期方向找(减小偏移量)
                high = mid
            else:
                # 中间日期晚于或等于开始日期,可能还要更早
                low = mid + 1

        # 二分查找完成,low 是第一个日期 < start_date 的偏移量
        # 所以从 low-5 开始获取(确保覆盖 start_date)
        start_offset = max(0, (low // 5 - 1) * 5)
        logger.info(f"二分查找完成,从偏移量 {start_offset} 开始获取文章")

    # 4. 从定位点开始获取,直到超过结束日期
    result = []
    current_offset = start_offset
    total_checked = 0

    while current_offset < max_offset:
        articles = get_articles_by_offset(fakeid, token, headers, begin_offset=current_offset, count=5, fetch_mode='date_range')
        if not articles:
            logger.info(f"偏移量 {current_offset} 无更多文章,停止爬取")
            break

        total_checked += len(articles)

        for article in articles:
            article_date = datetime.fromtimestamp(article['update_time']).date()

            # 如果早于开始日期,跳过
            if article_date < start_date:
                continue

            # 如果在结束日期范围内,加入结果
            if article_date <= end_date:
                result.append(article)
            else:
                # 晚于结束日期,继续往下找
                pass

        # 如果该页最早文章已晚于结束日期,继续；如果已早于开始日期,停止
        if articles and datetime.fromtimestamp(articles[-1]['update_time']).date() < start_date:
            logger.info(f"到达开始日期之前,停止爬取")
            break

        current_offset += 5
        # 额外延迟(已在 get_articles_by_offset 中处理)
        if progress_callback:
            progress_callback(current_offset, max_offset)

    logger.info(f"共获取 {len(result)} 篇符合条件的文章")
    return result


def get_article_content(url, headers):
    """
    获取单篇文章的内容
    
    Args:
        url: 文章链接
        headers: 请求头
        
    Returns:
        str: 文章内容
    """
    try:
        # 发送请求
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            return f"请求失败,状态码: {response.status_code}"
        
        # 解析HTML
        soup = bs4.BeautifulSoup(response.text, 'lxml')
        content_ele = soup.select(".rich_media_content")
        if len(content_ele) == 0:
            content = ""
        else:
            # 将HTML转换为Markdown
            content = md(content_ele[0], keep_inline_images_in=["section", "span"])
        return content
        
    except Exception as e:
        return f"获取文章内容失败: {str(e)}"


def get_timestamp(update_time):
    """
    将时间戳转换为可读时间
    
    Args:
        update_time: UNIX时间戳
        
    Returns:
        str: 格式化的时间字符串 (YYYY-MM-DD HH:MM:SS)
    """
    try:
        dt = datetime.fromtimestamp(int(update_time))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except Exception as e:
        return f"时间戳转换失败: {str(e)}"


def format_time(timestamp):
    """
    格式化时间戳
    
    Args:
        timestamp: UNIX时间戳
        
    Returns:
        str: 格式化的日期时间 (YYYY-MM-DD HH:MM:SS)
    """
    try:
        dt = datetime.fromtimestamp(int(timestamp))
        return dt.strftime('%Y-%m-%d %H:%M:%S')
    except:
        return ''


def filter_by_keywords(articles, keywords, field='title'):
    """
    根据关键词过滤文章
    
    Args:
        articles: 文章列表,每篇文章为一个字典
        keywords: 关键词列表
        field: 要搜索的字段,默认为'title'
        
    Returns:
        list: 匹配关键词的文章列表
    """
    if not keywords:
        return articles
    
    filtered = []
    for article in articles:
        if field not in article:
            continue
            
        content = article[field].lower()
        if any(keyword.lower() in content for keyword in keywords):
            filtered.append(article)
            
    return filtered


def save_to_csv(data, filename, fieldnames=None):
    """
    保存数据到CSV文件
    
    Args:
        data: 要保存的数据列表
        filename: 文件名
        fieldnames: 字段名列表,如果为None则使用data的第一项的keys
        
    Returns:
        bool: 是否保存成功
    """
    if not data:
        return False
        
    # 如果未提供字段名,尝试从数据中获取
    if not fieldnames:
        if isinstance(data[0], dict):
            fieldnames = list(data[0].keys())
        else:
            logger.error(f"保存CSV失败: 未提供字段名且无法自动获取")
            return False
    
    try:
        # 创建目录
        os.makedirs(os.path.dirname(filename) or '.', exist_ok=True)
        
        # 写入CSV
        with open(filename, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(data)
        
        logger.info(f"数据已保存到: {filename}")
        return True
    except Exception as e:
        logger.error(f"保存CSV失败: {str(e)}")
        return False


def mkdir(path):
    """
    创建目录
    
    Args:
        path: 目录路径
    
    Returns:
        bool: 是否成功
    """
    # 去除首尾空格
    path = path.strip()
    
    # 判断路径是否存在
    if not path or os.path.exists(path):
        logger.info(f"{path} 目录已存在")
        return True
    
    # 创建目录
    os.makedirs(path)
    logger.info(f"{path} 创建成功")
    return True 