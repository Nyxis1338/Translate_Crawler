# -*- coding: utf-8 -*-
import os
# 导入私有密钥配置
try:
    from secret_config import (
        DEEPL_KEY,
        DEEPL_FREE_PLAN,
        TRANSLATE_BAIDU,
        TRANSLATE_TENCENT
        # 已删除 YOUDAO
    )
except ImportError:
    raise Exception("缺少 secret_config.py 密钥文件！请复制模板创建并填入翻译API密钥")

# ===================== 公共爬虫配置（可上传git）=====================
BASE_URL = "https://community.jsplumbtoolkit.com/docs/6.x/"
DOMAIN = "https://community.jsplumbtoolkit.com"
SAVE_DIR = "output"
os.makedirs(SAVE_DIR, exist_ok=True)

# 请求延时 单位秒，0.2=200ms，可改0.1更快
REQUEST_DELAY = 0.2
RETRY_TIMES = 2  # 请求重试次数

# 静态资源白名单（全部允许下载，包含js/css/svg/png）
STATIC_SUFFIX = (".js", ".css", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".woff", ".ttf")

# 缓存相关配置
CACHE_HTML_DIR = "cache_html"
TASK_JSON_PATH = "translate_task.json"
RESULT_JSON_PATH = "translate_result.json"
MAX_TRANS_LEN = 2000

# 在 config.py 中添加
ALLOWED_PAGE_PREFIXES = ["lib/", ""]  # 空字符串表示根页面