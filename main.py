# -*- coding: utf-8 -*-
import os
import time
import json
import logging
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from bs4.element import NavigableString
import deepl
import config

# ========== 日志初始化 ==========
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler("crawler.log", encoding="utf-8"), logging.StreamHandler()]
)
logger = logging.getLogger("jsplumb-crawler")

# 全局变量
visited_urls = set()
downloaded_static = set()
with open("api_terms.json", "r", encoding="utf-8") as f:
    TERM_MAP = json.load(f)

# 请求头（解决JS静态403防盗链）
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36",
    "Referer": config.BASE_URL,
    "Accept-Language": "en-US,en;q=0.9"
}

# ========== 工具函数 ==========
def replace_terms(text: str) -> str:
    """术语统一替换"""
    for en, cn in TERM_MAP.items():
        text = text.replace(en, f"{en}({cn})")
    return text

def translate_segment(text: str) -> str:
    """
    多翻译源自动降级：DeepL(官方SDK) > 有道翻译
    """
    text = text.strip()
    if not text or len(text) < 2:
        return text
    # 跳过代码块、命令、符号
    if text.startswith(("```", "//", "/*", "{", "(", "#")):
        return text

    # 翻译源优先级列表
    translate_apis = ["deepl", "youdao"]
    for api in translate_apis:
        try:
            if api == "deepl" and config.DEEPL_KEY:
                raw_key = config.DEEPL_KEY.strip()
                # 补全https协议头
                if config.DEEPL_FREE_PLAN:
                    server_host = "https://api-free.deepl.com"
                else:
                    server_host = "https://api.deepl.com"
                client = deepl.DeepLClient(raw_key, server_url=server_host)
                trans_res = client.translate_text(text, target_lang="ZH")
                # 兼容列表与单个结果
                if isinstance(trans_res, list):
                    trans_text = "".join([item.text for item in trans_res])
                else:
                    trans_text = trans_res.text
                return trans_text
            elif api == "youdao" and config.YOUDAO["appKey"] and config.YOUDAO["appSecret"]:
                import hashlib, time
                appKey = config.YOUDAO["appKey"]
                appSecret = config.YOUDAO["appSecret"]
                salt = str(int(time.time()))
                signStr = appKey + text + salt + appSecret
                sign = hashlib.md5(signStr.encode()).hexdigest()
                data = {
                    "q": text,
                    "from": "en",
                    "to": "zh-CHS",
                    "appKey": appKey,
                    "salt": salt,
                    "sign": sign
                }
                resp = requests.post("https://openapi.youdao.com/api", data=data, timeout=8)
                res = resp.json()
                if res.get("errorCode") == "0":
                    return res["translation"][0]
        except deepl.exceptions.AuthorizationException:
            logger.warning(f"【deepl】鉴权失败，跳过：{text[:40]}")
            continue
        except Exception as e:
            logger.debug(f"【{api}】翻译接口失效：{str(e)}")
            continue
    # 全部接口失败，返回原文标记
    logger.warning(f"所有翻译接口全部失败，原文保留：{text[:40]}...")
    return f"【翻译失败】{text}"

def save_static_file(resource_url: str):
    """修复：完整静态资源下载，包含JS/CSS"""
    if resource_url in downloaded_static:
        return
    parsed = urlparse(resource_url)
    if not parsed.path.endswith(config.STATIC_SUFFIX):
        return
    downloaded_static.add(resource_url)
    local_path = os.path.join(config.SAVE_DIR, parsed.path.lstrip("/"))
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    # 重试下载
    for i in range(config.RETRY_TIMES):
        try:
            resp = requests.get(resource_url, headers=HEADERS, timeout=8)
            if resp.status_code == 200:
                with open(local_path, "wb") as f:
                    f.write(resp.content)
                logger.info(f"静态文件下载成功：{resource_url}")
                return
            elif 500 <= resp.status_code < 600:
                logger.warning(f"静态资源服务器5xx错误，永久跳过：{resource_url}")
                return
            else:
                logger.debug(f"静态资源{i+1}次失败，状态码{resp.status_code}：{resource_url}")
        except Exception as e:
            logger.debug(f"静态资源{i+1}次请求异常：{resource_url} | {str(e)}")
        time.sleep(config.REQUEST_DELAY)
    logger.error(f"静态资源最终下载失败：{resource_url}")

def parse_page_links(html: str, base_url: str):
    """提取文档内所有页面链接"""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        full_url = urljoin(base_url, href)
        if full_url.startswith(config.BASE_URL) and "#" not in full_url:
            links.append(full_url)
    return list(set(links))

def process_html(html: str, page_url: str):
    """页面处理：提取静态资源、双语文本转换"""
    soup = BeautifulSoup(html, "html.parser")
    # 1. 抓取所有静态资源
    for tag in soup.find_all(["script", "link", "img", "svg"]):
        src_attr = None
        if tag.name == "script" and tag.get("src"):
            src_attr = "src"
        elif tag.name == "link" and tag.get("href"):
            src_attr = "href"
        elif tag.get("src"):
            src_attr = "src"
        if src_attr:
            src_value = tag.get(src_attr)
            if not src_value:
                continue
            res_url = urljoin(page_url, str(src_value))
            save_static_file(res_url)
            # 修改为本地相对路径
            tag[src_attr] = urlparse(res_url).path
    # 2. 遍历文本节点生成双语
    for elem in soup.find_all(string=True):
        if isinstance(elem, NavigableString):
            raw_text = str(elem)
            if raw_text.strip():
                cn_text = translate_segment(raw_text)
                term_fixed = replace_terms(cn_text)
                new_tag = soup.new_tag("span", attrs={"class": "en-text"})
                new_tag.string = raw_text
                sep = soup.new_string(" | ")
                cn_tag = soup.new_tag("span", attrs={"class": "cn-text"})
                cn_tag.string = term_fixed
                elem.replace_with(new_tag, sep, cn_tag)
    # 3. 嵌入双语切换CSS+JS
    switch_script = """
    <style>
        .lang-switch{position:fixed;top:10px;right:10px;z-index:9999}
        .en-text{display:inline} .cn-text{display:none}
        body.show-cn .en-text{display:none} body.show-cn .cn-text{display:inline}
    </style>
    <div class="lang-switch">
        <button onclick="document.body.classList.toggle('show-cn')">切换中英双语</button>
    </div>
    <script>
        const mode = localStorage.getItem("lang");
        if(mode==="cn") document.body.classList.add("show-cn");
        document.querySelector(".lang-switch button").addEventListener("click",()=>{
            document.body.classList.toggle("show-cn");
            localStorage.setItem("lang", document.body.classList.contains("show-cn")?"cn":"en")
        })
    </script>
    """
    body = soup.body
    if body is None:
        body = soup.new_tag("body")
        if soup.html:
            soup.html.append(body)
        else:
            soup.append(body)
    body.append(BeautifulSoup(switch_script, "html.parser"))
    return str(soup)

def crawl_page(url: str):
    if url in visited_urls:
        return []
    visited_urls.add(url)
    logger.info(f"正在抓取页面：{url}")
    # 请求页面
    resp = None
    for i in range(config.RETRY_TIMES):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            if resp.status_code == 200:
                break
            logger.debug(f"页面第{i+1}次请求失败，code:{resp.status_code}")
        except Exception as e:
            logger.debug(f"页面第{i+1}次请求异常：{str(e)}")
        time.sleep(config.REQUEST_DELAY)
    if not resp or resp.status_code != 200:
        logger.error(f"页面抓取失败：{url}")
        return []
    # 保存本地HTML
    parsed_url = urlparse(url)
    save_path = os.path.join(config.SAVE_DIR, parsed_url.path.lstrip("/"))
    if save_path.endswith("/"):
        save_path += "index.html"
    os.makedirs(os.path.dirname(save_path), exist_ok=True)
    # 处理双语页面
    bilingual_html = process_html(resp.text, url)
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(bilingual_html)
    logger.info(f"页面生成完成：{save_path}")
    time.sleep(config.REQUEST_DELAY)
    return parse_page_links(resp.text, url)

def main():
    print("==== jsPlumb 6.x Community 离线双语文档生成工具 ====")
    start_url = config.BASE_URL
    queue = [start_url]
    all_pages = []
    # 广度优先抓取所有页面
    while queue:
        current = queue.pop(0)
        child_links = crawl_page(current)
        for link in child_links:
            if link not in visited_urls and link not in queue:
                queue.append(link)
                all_pages.append(link)
    logger.info(f"抓取完成，共处理页面：{len(visited_urls)}")
    print(f"全部双语页面生成完毕！输出目录：{config.SAVE_DIR}")

if __name__ == "__main__":
    main()