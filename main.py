# -*- coding: utf-8 -*-
import os
import time
import json
import logging
import requests
import uuid
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from bs4.element import NavigableString
import deepl
import config
from tencentcloud.common import credential
from tencentcloud.tmt.v20180321 import tmt_client, models

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

# ==================== 缓存工具函数 ====================
def init_task_file():
    # 创建目录
    os.makedirs(config.CACHE_HTML_DIR, exist_ok=True)
    os.makedirs(config.SAVE_DIR, exist_ok=True)
    # 处理任务文件：不存在 / 空文件 都重建
    if not os.path.exists(config.TASK_JSON_PATH) or os.path.getsize(config.TASK_JSON_PATH) == 0:
        with open(config.TASK_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump([], f, ensure_ascii=False, indent=2)

def init_result_file():
    if not os.path.exists(config.RESULT_JSON_PATH) or os.path.getsize(config.RESULT_JSON_PATH) == 0:
        with open(config.RESULT_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False, indent=2)

def load_tasks() -> list:
    with open(config.TASK_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_tasks(task_list: list):
    with open(config.TASK_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(task_list, f, ensure_ascii=False, indent=2)

def load_results() -> dict:
    with open(config.RESULT_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def save_results(res_map: dict):
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

# ==================== 通用工具函数 ====================
def replace_terms(text: str) -> str:
    """专业术语替换"""
    for en, cn in TERM_MAP.items():
        text = text.replace(en, f"{en}({cn})")
    return text

def translate_segment(text: str) -> str:
    """翻译降级：DeepL优先，失败切腾讯，单段文本"""
    text = text.strip()
    if not text or len(text) < 2:
        return text
    skip_prefix = ("```", "//", "/*", "{", "(", "#")
    if text.startswith(skip_prefix):
        return text

    translate_apis = ["deepl", "tencent"]
    for api in translate_apis:
        try:
            if api == "deepl" and config.DEEPL_KEY:
                raw_key = config.DEEPL_KEY.strip()
                if config.DEEPL_FREE_PLAN:
                    server_host = "https://api-free.deepl.com"
                else:
                    server_host = "https://api.deepl.com"
                client = deepl.DeepLClient(raw_key, server_url=server_host)
                trans_res = client.translate_text(text, target_lang="ZH")
                if isinstance(trans_res, list):
                    trans_text = "".join([item.text for item in trans_res])
                else:
                    trans_text = trans_res.text
                return trans_text
            elif api == "tencent":
                sid = config.TRANSLATE_TENCENT["secret_id"]
                skey = config.TRANSLATE_TENCENT["secret_key"]
                if not sid or not skey:
                    logger.warning("腾讯密钥未配置，跳过")
                    continue
                cred = credential.Credential(sid, skey)
                client = tmt_client.TmtClient(cred, "ap-beijing")
                req = models.TextTranslateRequest()
                params = {
                    "SourceText": text,
                    "Source": "en",
                    "Target": "zh",
                    "ProjectId": 0
                }
                req.from_json_string(json.dumps(params))
                resp = client.TextTranslate(req)
                if resp.TargetText:
                    return resp.TargetText
        except deepl.exceptions.AuthorizationException:
            logger.warning("DeepL鉴权失败，切换腾讯")
            continue
        except Exception as e:
            logger.debug(f"【{api}】翻译异常：{str(e)}")
            continue
    logger.warning(f"全部翻译接口失效：{text[:40]}")
    return f"【翻译失败】{text}"

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

def parse_page_links(html: str, base_url: str):
    """提取站内页面链接"""
    soup = BeautifulSoup(html, "html.parser")
    links = []
    for a in soup.find_all("a", href=True):
        href = str(a["href"])
        full_url = urljoin(base_url, href)
        if full_url.startswith(config.BASE_URL) and "#" not in full_url:
            links.append(full_url)
    return list(set(links))

# ==================== 阶段1：仅抓取缓存原始HTML，生成翻译任务 ====================
def crawl_only_save_html():
    init_task_file()
    init_result_file()
    task_list = load_tasks()
    existing_task_ids = set([t["task_id"] for t in task_list])
    visited_urls.clear()
    queue = [config.BASE_URL]

    def extract_text_tasks(soup: BeautifulSoup, page_save_key: str):
        nonlocal task_list
        for elem in soup.find_all(string=True):
            if isinstance(elem, NavigableString):
                raw_text = str(elem).strip()
                if not raw_text:
                    continue
                skip_prefix = ("```", "//", "/*", "{", "(", "#")
                if raw_text.startswith(skip_prefix):
                    continue
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

    while queue:
        current_url = queue.pop(0)
        if current_url in visited_urls:
            continue
        visited_urls.add(current_url)
        logger.info(f"【抓取缓存页面】{current_url}")
        page_html = None
        for i in range(config.RETRY_TIMES):
            try:
                resp = requests.get(current_url, headers=HEADERS, timeout=10)
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
    save_tasks(task_list)
    logger.info(f"抓取完成，生成翻译任务总数：{len(task_list)}，缓存目录：{config.CACHE_HTML_DIR}")

# ==================== 阶段2：批量翻译所有pending文本片段 ====================
def batch_translate_tasks():
    init_task_file()
    init_result_file()
    task_list = load_tasks()
    result_map = load_results()
    total_task = len(task_list)
    success = 0
    fail = 0
    logger.info(f"开始批量翻译，总任务条数：{total_task}")
    for index, task in enumerate(task_list):
        if task["status"] == "done":
            success += 1
            continue
        seg_txt = task["segment_text"].strip()
        if not seg_txt:
            task["status"] = "done"
            success += 1
            continue
        logger.info(f"进度 {index+1}/{total_task} 文本片段：{seg_txt[:60]}...")
        trans_txt = translate_segment(seg_txt)
        if trans_txt.startswith("【翻译失败】"):
            task["status"] = "fail"
            fail += 1
        else:
            task["status"] = "done"
            task["translated_text"] = trans_txt
            result_map[task["task_id"]] = trans_txt
            success += 1
        # 每20条落地保存，防止中途丢失
        if (index + 1) % 20 == 0:
            save_tasks(task_list)
            save_results(result_map)
        time.sleep(config.REQUEST_DELAY)
    # 最终全量落地
    save_tasks(task_list)
    save_results(result_map)
    logger.info(f"翻译完成：成功{success}条，失败{fail}条，结果文件：{config.RESULT_JSON_PATH}")

# ==================== 阶段3：读取缓存+翻译结果，生成双语HTML ====================
def build_bilingual_pages():
    init_task_file()
    init_result_file()
    task_list = load_tasks()
    result_map = load_results()
    page_text_dict = {}
    # 按页面+原文合并分段翻译结果
    for t in task_list:
        pk = t["page_key"]
        raw_full = t["raw_full_text"]
        seg_trans = result_map.get(t["task_id"], "")
        if pk not in page_text_dict:
            page_text_dict[pk] = {}
        if raw_full not in page_text_dict[pk]:
            page_text_dict[pk][raw_full] = []
        page_text_dict[pk][raw_full].append(seg_trans)
    # 拼接分段译文为完整译文
    page_full_trans = {}
    for page_k, raw_map in page_text_dict.items():
        page_full_trans[page_k] = {}
        for raw_txt, seg_list in raw_map.items():
            page_full_trans[page_k][raw_txt] = "".join(seg_list)
    # 遍历缓存HTML生成双语页面
    for root, _, filenames in os.walk(config.CACHE_HTML_DIR):
        for fname in filenames:
            if not fname.endswith(".html"):
                continue
            cache_path = os.path.join(root, fname)
            page_key = os.path.relpath(cache_path, config.CACHE_HTML_DIR)
            with open(cache_path, "r", encoding="utf-8") as f:
                html_raw = f.read()
            soup = BeautifulSoup(html_raw, "html.parser")
            trans_mapping = page_full_trans.get(page_key, {})
            # 替换所有文本节点为双语
            for elem in soup.find_all(string=True):
                if isinstance(elem, NavigableString):
                    raw_text = str(elem).strip()
                    if not raw_text:
                        continue
                    skip_prefix = ("```", "//", "/*", "{", "(", "#")
                    if raw_text.startswith(skip_prefix):
                        continue
                    trans_text = trans_mapping.get(raw_text, f"【无翻译结果】{raw_text}")
                    term_text = replace_terms(trans_text)
                    en_span = soup.new_tag("span", attrs={"class": "en-text"})
                    en_span.string = raw_text
                    split_mark = soup.new_string(" | ")
                    cn_span = soup.new_tag("span", attrs={"class": "cn-text"})
                    cn_span.string = term_text
                    elem.replace_with(en_span, split_mark, cn_span)
            # 双语切换样式脚本
            switch_code = """
<style>
.lang-switch{position:fixed;top:10px;right:10px;z-index:9999}
.en-text{display:inline} .cn-text{display:none}
body.show-cn .en-text{display:none}
body.show-cn .cn-text{display:inline}
</style>
<div class="lang-switch">
    <button onclick="document.body.classList.toggle('show-cn')">切换中英双语</button>
</div>
<script>
const lang = localStorage.getItem("lang");
if(lang === "cn") document.body.classList.add("show-cn");
document.querySelector(".lang-switch button").onclick = function(){
    document.body.classList.toggle("show-cn");
    localStorage.setItem("lang", document.body.classList.contains("show-cn") ? "cn" : "en");
}
</script>
            """
            body_tag = soup.find("body")
            if body_tag is None:
                body_tag = soup.new_tag("body")
                if soup.html:
                    soup.html.append(body_tag)
                else:
                    soup.append(body_tag)
            body_tag.append(BeautifulSoup(switch_code, "html.parser"))
            # 写入输出目录
            output_file = os.path.join(config.SAVE_DIR, page_key)
            os.makedirs(os.path.dirname(output_file), exist_ok=True)
            with open(output_file, "w", encoding="utf-8") as f:
                f.write(str(soup))
    logger.info(f"全部双语页面生成完毕，输出目录：{config.SAVE_DIR}")

# ==================== 程序入口 ====================
def main():
    print("========== 离线文档爬虫（分三阶段）==========")
    print("1 = 仅抓取页面，缓存原始HTML，生成翻译任务")
    print("2 = 批量翻译所有待处理文本片段")
    print("3 = 根据缓存+译文，生成中英双语网页")
    print("4 = 完整流程：抓取 → 翻译 → 生成页面")
    choice = input("请输入执行数字：").strip()
    if choice == "1":
        crawl_only_save_html()
    elif choice == "2":
        batch_translate_tasks()
    elif choice == "3":
        build_bilingual_pages()
    elif choice == "4":
        crawl_only_save_html()
        batch_translate_tasks()
        build_bilingual_pages()
    else:
        print("输入无效，程序退出")

if __name__ == "__main__":
    main()