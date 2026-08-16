# -*- coding: utf-8 -*-
from crawler import crawl_only_save_html
from translator import batch_translate_tasks
from generator import build_bilingual_pages

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