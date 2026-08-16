# -*- coding: utf-8 -*-
import os
import json
import logging
import uuid
from bs4 import BeautifulSoup

# ========== 日志初始化 ==========
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler("crawler.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger("jsplumb-crawler")

# 加载术语表
with open("api_terms.json", "r", encoding="utf-8") as f:
    TERM_MAP = json.load(f)

# ==================== 缓存工具函数 ====================
def init_task_file():
    import config
    os.makedirs(config.CACHE_HTML_DIR, exist_ok=True)
    os.makedirs(config.SAVE_DIR, exist_ok=True)
    if not os.path.exists(config.TASK_JSON_PATH) or os.path.getsize(config.TASK_JSON_PATH) == 0:
        with open(config.TASK_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def init_result_file():
    import config
    if not os.path.exists(config.RESULT_JSON_PATH) or os.path.getsize(config.RESULT_JSON_PATH) == 0:
        with open(config.RESULT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

def load_tasks() -> list:
    import config
    with open(config.TASK_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tasks(task_list: list):
    import config
    with open(config.TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task_list, f, ensure_ascii=False, indent=2)

def load_results() -> dict:
    import config
    with open(config.RESULT_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_results(res_map: dict):
    import config
    with open(config.RESULT_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(res_map, f, ensure_ascii=False, indent=2)

def split_long_text(text: str, max_len: int):
    """超长文本按最大字符分段，尽量空格分割不拆分单词"""
    parts = []
    start = 0
    text_len = len(text)
    while start < text_len:
        end = start + max_len
        if end >= text_len:
            parts.append(text[start:])
            break
        split_pos = text.rfind(" ", start, end)
        if split_pos == -1 or split_pos <= start:
            split_pos = end
        parts.append(text[start:split_pos])
        start = split_pos
    return parts

def replace_terms(text: str) -> str:
    """专业术语替换"""
    for en, cn in TERM_MAP.items():
        text = text.replace(en, f"{en}({cn})")
    return text

def should_skip_element(elem):
    """判断是否需要跳过该元素（代码块、脚本等）"""
    if elem.name in ['script', 'style', 'noscript', 'pre', 'code', 'kbd', 'samp']:
        return True
    if elem.get('class'):
        classes = ' '.join(elem.get('class'))
        if 'hljs' in classes or 'language-' in classes or 'code' in classes:
            return True
    return False