# -*- coding: utf-8 -*-
import time
import json
import hashlib
import random
import requests
import deepl
import config
from tencentcloud.common import credential
from tencentcloud.tmt.v20180321 import tmt_client, models
from utils import (
    logger, init_task_file, init_result_file,
    load_tasks, save_tasks, load_results, save_results
)

# ==================== 百度翻译 ====================
def translate_baidu(text: str) -> str:
    """百度翻译API"""
    appid = config.TRANSLATE_BAIDU.get("appid")
    secret = config.TRANSLATE_BAIDU.get("secret")
    if not appid or not secret:
        logger.warning("百度翻译密钥未配置，跳过")
        return None

    salt = str(random.randint(32768, 65536))
    sign_str = appid + text + salt + secret
    sign = hashlib.md5(sign_str.encode("utf-8")).hexdigest()

    url = "https://fanyi-api.baidu.com/api/trans/vip/translate"
    params = {
        "q": text,
        "from": "en",
        "to": "zh",
        "appid": appid,
        "salt": salt,
        "sign": sign
    }

    try:
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json()
        if "trans_result" in data:
            return "".join([item["dst"] for item in data["trans_result"]])
        else:
            logger.warning(f"百度翻译返回错误：{data}")
            return None
    except Exception as e:
        logger.debug(f"百度翻译异常：{str(e)}")
        return None

# ==================== 翻译降级主函数 ====================
def translate_segment(text: str) -> str:
    """
    翻译降级：百度优先 → DeepL次选 → 腾讯兜底
    """
    text = text.strip()
    if not text or len(text) < 2:
        return text

    # 跳过代码/注释片段
    skip_prefix = ("```", "//", "/*", "{", "(", "#")
    if text.startswith(skip_prefix):
        return text

    # ----- 1. 百度翻译 -----
    try:
        baidu_result = translate_baidu(text)
        if baidu_result:
            logger.debug(f"百度翻译成功：{text[:30]}...")
            return baidu_result
    except Exception as e:
        logger.warning(f"百度翻译异常，切换DeepL：{str(e)}")

    # ----- 2. DeepL翻译 -----
    try:
        if config.DEEPL_KEY:
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
            logger.debug(f"DeepL翻译成功：{text[:30]}...")
            return trans_text
    except deepl.exceptions.AuthorizationException:
        logger.warning("DeepL鉴权失败，切换腾讯")
    except Exception as e:
        logger.debug(f"DeepL翻译异常：{str(e)}")

    # ----- 3. 腾讯翻译 -----
    try:
        sid = config.TRANSLATE_TENCENT.get("secret_id")
        skey = config.TRANSLATE_TENCENT.get("secret_key")
        if not sid or not skey:
            logger.warning("腾讯密钥未配置，跳过")
        else:
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
                logger.debug(f"腾讯翻译成功：{text[:30]}...")
                return resp.TargetText
    except Exception as e:
        logger.debug(f"腾讯翻译异常：{str(e)}")

    logger.warning(f"全部翻译接口失效：{text[:40]}")
    return f"〖翻译失败〗{text}"

# ==================== 阶段2：批量翻译 ====================
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
        if trans_txt.startswith("〖翻译失败〗"):
            task["status"] = "fail"
            fail += 1
        else:
            task["status"] = "done"
            task["translated_text"] = trans_txt
            result_map[task["task_id"]] = trans_txt
            success += 1

        if (index + 1) % 20 == 0:
            save_tasks(task_list)
            save_results(result_map)

        time.sleep(config.REQUEST_DELAY)

    save_tasks(task_list)
    save_results(result_map)
    logger.info(f"翻译完成：成功{success}条，失败{fail}条，结果文件：{config.RESULT_JSON_PATH}")