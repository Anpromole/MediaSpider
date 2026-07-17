#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
微信公众号爬虫 - 多账号与 Cookie 池管理模块
========================================

提供多账号凭证管理、状态监测（正常/频次受限/失效过期）、
智能冷却恢复以及无缝自动切号功能。

版本: 1.5.0
"""

import json
import os
import time
from datetime import datetime, timedelta
from spider.log.utils import logger

ACCOUNTS_FILE = 'wechat_accounts.json'
DEFAULT_CACHE_FILE = 'wechat_cache.json'
DEFAULT_COOLDOWN_MINUTES = 30


class WeChatAccount:
    """单个微信公众号凭证对象"""

    def __init__(self, token, cookies, name=None, account_id=None, status="active",
                 request_count=0, last_used=None, cooldown_until=None):
        self.token = str(token)
        self.cookies = cookies
        self.name = name or f"Account_{self.token[:6]}"
        self.account_id = account_id or self.token
        self.status = status  # active / rate_limited / expired
        self.request_count = request_count
        self.last_used = last_used or time.time()
        self.cooldown_until = cooldown_until  # float timestamp

    def is_available(self):
        """检查账号当前是否可用（考虑冷却解封）"""
        if self.status == "expired":
            return False

        if self.status == "rate_limited":
            if self.cooldown_until and time.time() >= self.cooldown_until:
                # 冷却结束，恢复为 active
                logger.info(f"账号 [{self.name}] 冷却时间已到，自动解封恢复可用。")
                self.status = "active"
                self.cooldown_until = None
                return True
            return False

        return True

    def to_dict(self):
        return {
            'account_id': self.account_id,
            'name': self.name,
            'token': self.token,
            'cookies': self.cookies,
            'status': self.status,
            'request_count': self.request_count,
            'last_used': self.last_used,
            'cooldown_until': self.cooldown_until
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            token=data['token'],
            cookies=data['cookies'],
            name=data.get('name'),
            account_id=data.get('account_id'),
            status=data.get('status', 'active'),
            request_count=data.get('request_count', 0),
            last_used=data.get('last_used'),
            cooldown_until=data.get('cooldown_until')
        )


class AccountPoolManager:
    """账号池管理器"""

    def __init__(self, accounts_file=ACCOUNTS_FILE):
        self.accounts_file = accounts_file
        self.accounts = []
        self.current_index = 0
        self.load_pool()

    def load_pool(self):
        """加载账号池数据，若不存在则尝试导入旧的 wechat_cache.json"""
        self.accounts = []
        if os.path.exists(self.accounts_file):
            try:
                with open(self.accounts_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    for item in data:
                        self.accounts.append(WeChatAccount.from_dict(item))
                logger.info(f"账号池已成功加载 {len(self.accounts)} 个微信凭证。")
            except Exception as e:
                logger.error(f"读取账号池文件失败: {e}")

        # 如果账号池为空，尝试从默认单缓存 wechat_cache.json 导入
        if not self.accounts and os.path.exists(DEFAULT_CACHE_FILE):
            try:
                with open(DEFAULT_CACHE_FILE, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)
                if 'token' in cache_data and 'cookies' in cache_data:
                    acc = WeChatAccount(
                        token=cache_data['token'],
                        cookies=cache_data['cookies'],
                        name="默认账号"
                    )
                    self.accounts.append(acc)
                    self.save_pool()
                    logger.info("已将默认 wechat_cache.json 自动导入为账号池主账号。")
            except Exception as e:
                logger.error(f"导入单缓存文件失败: {e}")

    def save_pool(self):
        """保存账号池列表到本地 JSON 文件"""
        try:
            data = [acc.to_dict() for acc in self.accounts]
            with open(self.accounts_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存账号池文件失败: {e}")

    def add_account(self, token, cookies, name=None):
        """添加或更新账号到凭证池"""
        token_str = str(token)
        for acc in self.accounts:
            if acc.token == token_str:
                acc.cookies = cookies
                acc.status = "active"
                acc.cooldown_until = None
                if name:
                    acc.name = name
                self.save_pool()
                logger.info(f"更新账号池凭证: {acc.name}")
                return acc

        # 新新增账号
        new_acc = WeChatAccount(token=token_str, cookies=cookies, name=name)
        self.accounts.append(new_acc)
        self.save_pool()
        logger.info(f"新增凭证到账号池: {new_acc.name}")
        return new_acc

    def get_active_account(self):
        """获取当前可用的账号，按顺序轮流调度"""
        if not self.accounts:
            self.load_pool()

        available_accounts = [acc for acc in self.accounts if acc.is_available()]
        if not available_accounts:
            logger.warning("⚠️ 账号池中当前无可用的微信凭证（可能均已触发频次限制或过期）。")
            return None

        # 如果 current_index 超出可用范围，归零
        if self.current_index >= len(available_accounts):
            self.current_index = 0

        selected = available_accounts[self.current_index]
        selected.last_used = time.time()
        self.save_pool()
        return selected

    def mark_rate_limited(self, token, cooldown_minutes=DEFAULT_COOLDOWN_MINUTES):
        """将指定 token 标记为受限挂起，并设定冷却时间"""
        token_str = str(token)
        cooldown_until = time.time() + (cooldown_minutes * 60)
        for acc in self.accounts:
            if acc.token == token_str:
                acc.status = "rate_limited"
                acc.cooldown_until = cooldown_until
                logger.warning(f"🚫 账号 [{acc.name}] (Token: {acc.token[:8]}...) 触发微信频次限制，已标记进入 {cooldown_minutes} 分钟冷却挂起状态。")
                self.save_pool()
                return

    def mark_expired(self, token):
        """将指定 token 标记为失效"""
        token_str = str(token)
        for acc in self.accounts:
            if acc.token == token_str:
                acc.status = "expired"
                logger.error(f"❌ 账号 [{acc.name}] (Token: {acc.token[:8]}...) Cookie 凭证已过期失效，请重新登录。")
                self.save_pool()
                return

    def rotate(self, current_token=None):
        """无缝切换到下一个可用账号"""
        available_accounts = [acc for acc in self.accounts if acc.is_available()]
        if not available_accounts:
            logger.warning("账号池中无其他可用凭证，无法切号。")
            return None

        if len(available_accounts) == 1:
            logger.info("账号池中仅有 1 个可用账号。")
            return available_accounts[0]

        # 找到当前账号在可用列表中的位置，切到下一个
        current_idx = 0
        if current_token:
            for idx, acc in enumerate(available_accounts):
                if acc.token == str(current_token):
                    current_idx = idx
                    break
            self.current_index = (current_idx + 1) % len(available_accounts)
        else:
            self.current_index = (self.current_index + 1) % len(available_accounts)

        new_acc = available_accounts[self.current_index]
        logger.info(f"🔄 成功切换微信凭证至账号: [{new_acc.name}]")
        return new_acc


# 全局单例账号池对象
account_pool = AccountPoolManager()
