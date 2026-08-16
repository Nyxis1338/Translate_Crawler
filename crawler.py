# -*- coding: utf-8 -*-
import os
import time
import requests
import uuid
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from bs4.element import NavigableString
import config
from utils import (
    logger, init_task_file, init_result_file,
    load_tasks, save_tasks, load_results, save_results,
    split_long_text, should_skip_element
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Referer": config.BASE_URL,
    "Accept-Language": "en-US,en;q=0.9"
}

# 全局变量（仅在该模块内使用）
visited_urls = set()
downloaded_static = set()

# ==================== 静态资源下载 ====================
def save_static_file(resource_url: str):
    """下载静态资源 js/css/svg 等"""
    if resource_url in downloaded_static:
        return
    parsed = urlparse(resource_url)
    if not parsed.path.endswith(config.STATIC_SUFFIX):
        return
    downloaded_static.add(resource_url)

    local_path = os.path.join(config.SAVE_DIR, parsed.path.lstrip("/"))
    os.makedirs(os.path.dirname(local_path), exist_ok=True)

    for i in range(config.RETRY_TIMES):
        try:
            resp = requests.get(resource_url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"静态下载成功：{resource_url}")
                return
            elif 500 <= resp.status_code < 600:
                logger.warning(f"服务器5xx，跳过：{resource_url}")
                return
            else:
                logger.debug(f"第{i+1}次失败 code={resp.status_code} {resource_url}")
        except Exception as e:
            logger.debug(f"静态请求异常：{resource_url} {str(e)}")
        time.sleep(config.REQUEST_DELAY)
    logger.error(f"静态资源最终失败：{resource_url}")

# ==================== 页面链接提取 ====================
def parse_page_links(html: str, base_url: str):
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        full_url = urljoin(base_url, href)
        if not full_url.startswith(config.BASE_URL) or "#" in full_url:
            continue
        rel_path = full_url[len(config.BASE_URL):]
        # 检查是否以允许的前缀开头
        if any(rel_path.startswith(prefix) for prefix in config.ALLOWED_PAGE_PREFIXES):
            links.append(full_url)
    return list(set(links))

# ==================== 提取正文块 ====================
def extract_blocks(soup, container_selector='main'):
    """
    提取正文容器中的主要文本段落（段落和标题），忽略列表等细碎内容。
    """
    container = soup.select_one(container_selector)
    if not container:
        container = soup.body or soup

    # 可选：先移除不需要的部分（如侧边栏、页脚等）
    for unwanted in container.find_all(['aside', 'footer', 'nav']):
        unwanted.decompose()

    blocks = []
    # 只提取 <p> 和 <h1>-<h6>
    for elem in container.find_all(['p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
        if should_skip_element(elem):
            continue
        text = elem.get_text(strip=True)
        if text:
            # 合并空白
            text = ' '.join(text.split())
            blocks.append(text)
    return blocks

# ==================== 阶段1：抓取缓存 ====================
def crawl_only_save_html():
    init_task_file()
    init_result_file()
    task_list = load_tasks()
    existing_task_ids = set([t["task_id"] for t in task_list])
    visited_urls.clear()
    queue = [config.BASE_URL]

    def extract_text_tasks(soup: BeautifulSoup, page_save_key: str):
        nonlocal task_list
        # 使用合适的选择器定位正文区域，此处以 'main' 为例，您可调整
        content_blocks = extract_blocks(soup, container_selector='main')
        for raw_text in content_blocks:
            base_task_id = f"{page_save_key}_{uuid.uuid4().hex[:12]}"
            text_segments = split_long_text(raw_text, config.MAX_TRANS_LEN)
            for idx, seg in enumerate(text_segments):
                sub_task_id = f"{base_task_id}_part{idx}"
                if sub_task_id in existing_task_ids:
                    continue
                task_list.append({
                    "task_id": sub_task_id,
                    "parent_task_id": base_task_id,
                    "page_key": page_save_key,
                    "raw_full_text": raw_text,
                    "segment_text": seg,
                    "translated_text": "",
                    "status": "pending"
                })
                existing_task_ids.add(sub_task_id)

    session = requests.Session()
    session.headers.update(HEADERS)

    while queue:
        current_url = queue.pop(0)
        if current_url in visited_urls:
            continue
        visited_urls.add(current_url)

        logger.info(f"〖抓取缓存页面〗{current_url}")
        page_html = None
        for i in range(config.RETRY_TIMES):
            try:
                resp = session.get(current_url, timeout=10)
                if resp.status_code == 200:
                    page_html = resp.text
                    break
            except Exception as e:
                logger.debug(f"页面重试{i+1}异常：{str(e)}")
            time.sleep(config.REQUEST_DELAY)

        if not page_html:
            logger.error(f"页面抓取失败，跳过：{current_url}")
            continue

        # 保存原始HTML缓存
        parsed_url = urlparse(current_url)
        page_key = parsed_url.path.lstrip("/")
        if page_key.endswith("/"):
            page_key += "index.html"
        cache_file = os.path.join(config.CACHE_HTML_DIR, page_key)
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(page_html)

        # 下载页面静态资源
        soup_tmp = BeautifulSoup(page_html, "html.parser")
        for tag in soup_tmp.find_all(["script", "link", "img", "svg"]):
            src_attr = None
            if tag.name == "script" and tag.get("src"):
                src_attr = "src"
            elif tag.name == "link" and tag.get("href"):
                src_attr = "href"
            elif tag.get("src"):
                src_attr = "src"
            if src_attr:
                val = tag.get(src_attr)
                if not val:
                    continue
                res_url = urljoin(current_url, str(val))
                save_static_file(res_url)

        # 提取待翻译文本任务
        extract_text_tasks(soup_tmp, page_key)

        # 子页面入队
        child_links = parse_page_links(page_html, current_url)
        for link in child_links:
            if link not in visited_urls and link not in queue:
                queue.append(link)

        # 每处理一个页面保存一次任务，防止中断丢失
        save_tasks(task_list)

    logger.info(f"抓取完成，生成翻译任务总数：{len(task_list)}，缓存目录：{config.CACHE_HTML_DIR}")

# ==================== 阶段5：从缓存中生成翻译任务 ====================
def regenerate_tasks_from_cache():
    """
    从已有的 cache_html 目录中提取文本任务，重新生成 translate_task.json
    """
    from utils import init_task_file, save_tasks, split_long_text, logger
    import config
    import os
    from bs4 import BeautifulSoup

    init_task_file()
    task_list = []
    existing_task_ids = set()

    for root, _, filenames in os.walk(config.CACHE_HTML_DIR):
        for fname in filenames:
            if not fname.endswith(".html"):
                continue
            file_path = os.path.join(root, fname)
            page_key = os.path.relpath(file_path, config.CACHE_HTML_DIR)
            with open(file_path, "r", encoding="utf-8") as f:
                html = f.read()
            soup = BeautifulSoup(html, "html.parser")
            # 使用新的 extract_blocks 提取段落
            blocks = extract_blocks(soup, container_selector='main')
            for raw_text in blocks:
                base_task_id = f"{page_key}_{uuid.uuid4().hex[:12]}"
                text_segments = split_long_text(raw_text, config.MAX_TRANS_LEN)
                for idx, seg in enumerate(text_segments):
                    sub_task_id = f"{base_task_id}_part{idx}"
                    if sub_task_id in existing_task_ids:
                        continue
                    task_list.append({
                        "task_id": sub_task_id,
                        "parent_task_id": base_task_id,
                        "page_key": page_key,
                        "raw_full_text": raw_text,
                        "segment_text": seg,
                        "translated_text": "",
                        "status": "pending"
                    })
                    existing_task_ids.add(sub_task_id)

    save_tasks(task_list)
    logger.info(f"重新生成任务完成，共 {len(task_list)} 个文本片段")