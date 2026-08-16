# -*- coding: utf-8 -*-
import os
from bs4 import BeautifulSoup
from bs4.element import NavigableString
import config
from utils import (
    logger, init_task_file, init_result_file,
    load_tasks, load_results, replace_terms, should_skip_element
)

def build_bilingual_pages():
    init_task_file()
    init_result_file()
    task_list = load_tasks()
    result_map = load_results()

    # 按页面+原文合并分段翻译结果
    page_text_dict = {}
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
                    # 跳过代码/特殊标记
                    skip_prefix = ("```", "//", "/*", "{", "(", "#")
                    if raw_text.startswith(skip_prefix):
                        continue
                    # 仅当该文本在映射中才处理
                    if raw_text not in trans_mapping:
                        continue
                    trans_text = trans_mapping[raw_text]
                    term_text = replace_terms(trans_text)

                    en_span = soup.new_tag("span", attrs={"class": "en-text"})
                    en_span.string = raw_text
                    split_mark = soup.new_string(" | ")
                    cn_span = soup.new_tag("span", attrs={"class": "cn-text"})
                    cn_span.string = term_text
                    elem.replace_with(en_span, split_mark, cn_span)

            # 双语切换样式脚本（默认显示中文）
            switch_code = """
            <style>
            .en-text { color: #333; }
            .cn-text { color: #c0392b; }
            </style>
            <button onclick="toggleBilingual()" style="position:fixed;top:10px;right:10px;z-index:9999;padding:8px 16px;background:#3498db;color:#fff;border:none;border-radius:4px;cursor:pointer;">
                切换中英双语
            </button>
            <script>
            var showChinese = true;
            function toggleBilingual() {
                showChinese = !showChinese;
                var cnElements = document.querySelectorAll('.cn-text');
                var enElements = document.querySelectorAll('.en-text');
                for (var i = 0; i < cnElements.length; i++) {
                    cnElements[i].style.display = showChinese ? 'inline' : 'none';
                }
                for (var i = 0; i < enElements.length; i++) {
                    enElements[i].style.display = showChinese ? 'none' : 'inline';
                }
            }
            window.onload = function() {
                var cnElements = document.querySelectorAll('.cn-text');
                var enElements = document.querySelectorAll('.en-text');
                for (var i = 0; i < cnElements.length; i++) {
                    cnElements[i].style.display = 'inline';
                }
                for (var i = 0; i < enElements.length; i++) {
                    enElements[i].style.display = 'none';
                }
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