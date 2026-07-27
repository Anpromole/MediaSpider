#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
历史记录与防重机制管理器 (HistoryManager)
负责文章指纹哈希计算、PDF 渲染复用校验与 Dify 知识库上传去重。
"""

import os
import json
import hashlib
from typing import Dict, Optional, Any
from spider.log.utils import logger


class HistoryManager:
    """去重与历史记录持久化管理器"""

    def __init__(self, data_dir: Optional[str] = None):
        if data_dir is None:
            # 默认保存在 repository/.data 目录中
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            data_dir = os.path.join(base_dir, ".data")
        
        self.data_dir = data_dir
        os.makedirs(self.data_dir, exist_ok=True)
        self.history_file = os.path.join(self.data_dir, "history_records.json")
        self.records: Dict[str, Dict[str, Any]] = {}
        self._load_records()

    def _load_records(self):
        """从 JSON 文件装载历史记录"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    self.records = json.load(f)
                logger.info(f"成功加载历史去重记录：共 {len(self.records)} 条")
            except Exception as e:
                logger.error(f"加载历史记录文件失败: {e}，将初始化为空记录")
                self.records = {}
        else:
            self.records = {}

    def save_records(self):
        """将历史记录持久化到 JSON 文件"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(self.records, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存历史去重记录失败: {e}")

    @staticmethod
    def compute_article_hash(article: dict) -> str:
        """
        计算文章唯一指纹 MD5
        优先采用文章的 link (URL)；若无 URL 则使用 account + title + update_time
        """
        url = article.get('link') or article.get('url') or ''
        if url:
            raw = f"url:{url.split('?')[0] if '?' in url else url}"
        else:
            acc = article.get('account') or article.get('wpub_name') or ''
            title = article.get('title', '')
            utime = str(article.get('update_time', ''))
            raw = f"meta:{acc}_{title}_{utime}"
        
        return hashlib.md5(raw.encode('utf-8')).hexdigest()

    def is_pdf_exists(self, article: dict) -> Optional[str]:
        """
        校验文章对应的 PDF 是否已被成功渲染且文件物理存在
        Returns:
            str: 若存在且有效，返回 PDF 文件绝对路径；否则返回 None
        """
        article_hash = self.compute_article_hash(article)
        record = self.records.get(article_hash)
        if record:
            pdf_path = record.get('pdf_path')
            if pdf_path and os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                return pdf_path
        return None

    def mark_pdf_generated(self, article: dict, pdf_path: str):
        """记录文章的 PDF 生成结果"""
        article_hash = self.compute_article_hash(article)
        if article_hash not in self.records:
            self.records[article_hash] = {
                "title": article.get('title', ''),
                "link": article.get('link', ''),
                "account": article.get('wpub_name', ''),
                "pdf_path": pdf_path,
                "dify_uploaded_datasets": []
            }
        else:
            self.records[article_hash]["pdf_path"] = pdf_path
        
        self.save_records()

    def is_uploaded_to_dify(self, article_or_path: Any, dataset_id: str) -> bool:
        """
        校验文章/PDF 文件是否已经成功上传到特定的 Dify 知识库 (dataset_id)
        """
        if not dataset_id:
            return False

        if isinstance(article_or_path, dict):
            article_hash = self.compute_article_hash(article_or_path)
            record = self.records.get(article_hash)
            if record and dataset_id in record.get("dify_uploaded_datasets", []):
                return True
        elif isinstance(article_or_path, str):
            # 通过 pdf_path 反查
            pdf_path = article_or_path
            for record in self.records.values():
                if record.get("pdf_path") == pdf_path:
                    if dataset_id in record.get("dify_uploaded_datasets", []):
                        return True
        return False

    def mark_dify_uploaded(self, article_or_path: Any, dataset_id: str):
        """标记文章/PDF 文件已成功上传至某 Dify 知识库"""
        if not dataset_id:
            return

        if isinstance(article_or_path, dict):
            article_hash = self.compute_article_hash(article_or_path)
            if article_hash not in self.records:
                self.records[article_hash] = {
                    "title": article_or_path.get('title', ''),
                    "link": article_or_path.get('link', ''),
                    "pdf_path": article_or_path.get('pdf_path', ''),
                    "dify_uploaded_datasets": [dataset_id]
                }
            else:
                datasets = self.records[article_hash].setdefault("dify_uploaded_datasets", [])
                if dataset_id not in datasets:
                    datasets.append(dataset_id)
        elif isinstance(article_or_path, str):
            pdf_path = article_or_path
            found = False
            for record in self.records.values():
                if record.get("pdf_path") == pdf_path:
                    datasets = record.setdefault("dify_uploaded_datasets", [])
                    if dataset_id not in datasets:
                        datasets.append(dataset_id)
                    found = True
                    break
            if not found:
                # 兜底生成新条目
                raw_hash = hashlib.md5(f"path:{pdf_path}".encode('utf-8')).hexdigest()
                self.records[raw_hash] = {
                    "title": os.path.basename(pdf_path),
                    "pdf_path": pdf_path,
                    "dify_uploaded_datasets": [dataset_id]
                }

        self.save_records()
