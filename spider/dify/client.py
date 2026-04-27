#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Dify API 客户端
"""

import os
import requests
from typing import Optional, Dict
from spider.log.utils import logger


class DifyClient:
    """Dify API 客户端"""

    def __init__(self, api_base: str, chat_api_key: str, dataset_api_key: str = None):
        """
        初始化客户端

        Args:
            api_base: Dify API 基础 URL
            chat_api_key: 聊天应用 API Key (用于 AI 总结)
            dataset_api_key: 知识库 API Key (用于上传文档，可选)
        """
        self.api_base = api_base.rstrip('/')
        self.chat_api_key = chat_api_key
        self.dataset_api_key = dataset_api_key or chat_api_key
        self.session = requests.Session()
        # 聊天请求使用聊天 API Key
        self.chat_session = requests.Session()
        self.chat_session.headers.update({
            'Authorization': f'Bearer {self.chat_api_key}',
            'Content-Type': 'application/json'
        })
        # 知识库请求使用知识库 API Key
        self.dataset_session = requests.Session()
        self.dataset_session.headers.update({
            'Authorization': f'Bearer {self.dataset_api_key}',
            'Content-Type': 'application/json'
        })

    def chat(self, query: str, inputs: Optional[Dict] = None,
             user: str = "media-spider") -> Optional[str]:
        """
        调用 Dify 聊天 API

        Args:
            query: 用户问题
            inputs: 额外输入参数
            user: 用户标识

        Returns:
            str: AI 回复内容
        """
        url = f"{self.api_base}/chat-messages"

        payload = {
            "inputs": inputs or {},
            "query": query,
            "response_mode": "blocking",
            "user": user
        }

        try:
            response = self.chat_session.post(url, json=payload, timeout=60)

            if response.status_code == 200:
                result = response.json()
                answer = result.get('answer', '')
                logger.info("Dify AI 回复成功")
                return answer
            else:
                logger.error(f"Dify API 调用失败：{response.status_code} - {response.text}")
                return None

        except requests.RequestException as e:
            logger.error(f"调用 Dify API 失败：{e}")
            return None

    def upload_document(self, dataset_id: str, text: str,
                        name: str, indexing_technique: str = "high_quality") -> bool:
        """
        上传文档到知识库

        Args:
            dataset_id: 知识库 ID
            text: 文档内容
            name: 文档名称
            indexing_technique: 索引模式

        Returns:
            bool: 是否成功
        """
        if not dataset_id:
            logger.error("未提供知识库 ID")
            return False

        url = f"{self.api_base}/datasets/{dataset_id}/document/create_by_text"

        payload = {
            "name": name,
            "text": text,
            "indexing_technique": indexing_technique,
            "process_rule": {
                "mode": "automatic"
            }
        }

        try:
            response = self.dataset_session.post(url, json=payload, timeout=60)

            if response.status_code in [200, 201]:
                logger.info(f"文档上传成功：{name}")
                return True
            else:
                logger.error(f"文档上传失败：{response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"上传文档失败：{e}")
            return False

    def check_dataset(self, dataset_id: str) -> bool:
        """
        检查知识库是否存在

        Args:
            dataset_id: 知识库 ID

        Returns:
            bool: 是否存在
        """
        url = f"{self.api_base}/datasets/{dataset_id}"

        try:
            response = self.session.get(url, timeout=10)
            return response.status_code == 200
        except:
            return False

    def upload_pdf_file(self, dataset_id: str, pdf_path: str,
                        name: str, indexing_technique: str = "high_quality") -> bool:
        """
        上传 PDF 文件到知识库

        Args:
            dataset_id: 知识库 ID
            pdf_path: PDF 文件路径
            name: 文档名称
            indexing_technique: 索引模式

        Returns:
            bool: 是否成功
        """
        if not dataset_id:
            logger.error("未提供知识库 ID")
            return False

        if not os.path.exists(pdf_path):
            logger.error(f"PDF 文件不存在：{pdf_path}")
            return False

        url = f"{self.api_base}/datasets/{dataset_id}/document/create_by_file"

        try:
            # 使用 multipart/form-data 格式上传
            with open(pdf_path, 'rb') as f:
                files = {
                    'file': (os.path.basename(pdf_path), f, 'application/pdf')
                }
                data = {
                    'name': name,
                    'indexing_technique': indexing_technique,
                    'process_rule': '{"mode": "automatic"}'
                }

                # 不使用 session，直接用 requests.post 避免 session 处理 files 的问题
                response = requests.post(
                    url,
                    files=files,
                    data=data,
                    headers={'Authorization': f'Bearer {self.dataset_api_key}'},
                    timeout=120
                )

            if response.status_code in [200, 201]:
                logger.info(f"PDF 上传成功：{name}")
                return True
            else:
                logger.error(f"PDF 上传失败：{response.status_code} - {response.text}")
                return False

        except requests.RequestException as e:
            logger.error(f"上传 PDF 失败：{e}")
            return False
