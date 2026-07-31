# -*- coding: utf-8 -*-
import json
import hashlib
import time
import requests
import deepl
import config
from tencentcloud.common import credential
from tencentcloud.common.exception.tencent_cloud_sdk_exception import TencentCloudSDKException
from tencentcloud.tmt.v20180321 import tmt_client, models


test_text = "Container, endpoint, draggable node in jsPlumb 6.x"

def test_deepl():
    print("--- 1. 测试 DeepL 官方SDK翻译 ---")
    raw_key = config.DEEPL_KEY
    key = raw_key.strip()
    is_free = config.DEEPL_FREE_PLAN
    if not key:
        print("❌ 未配置DEEPL_API_KEY，跳过")
        return False
    try:
        # 修复：补全 https:// 协议头
        if is_free:
            server_addr = "https://api-free.deepl.com"
        else:
            server_addr = "https://api.deepl.com"
        client = deepl.DeepLClient(auth_key=key, server_url=server_addr)
        trans_res = client.translate_text(test_text, target_lang="ZH")
        # 兼容返回列表/单个TextResult，消除vscode类型警告
        if isinstance(trans_res, list):
            result_text = "".join([item.text for item in trans_res])
        else:
            result_text = trans_res.text
        print(f"✅ 翻译结果: {result_text}")
        return True
    except deepl.exceptions.AuthorizationException:
        print("❌ 鉴权失败：API密钥错误、账号类型不匹配或额度耗尽")
        return False
    except Exception as e:
        print(f"❌ DeepL失败: {str(e)}")
        return False

def test_youdao():
    print("\n--- 2. 测试有道翻译（免费） ---")
    appKey = config.YOUDAO["appKey"]
    appSecret = config.YOUDAO["appSecret"]
    if not appKey or not appSecret:
        print("❌ 未配置有道密钥，跳过")
        return False
    salt = str(int(time.time()))
    signStr = appKey + test_text + salt + appSecret
    sign = hashlib.md5(signStr.encode()).hexdigest()
    data = {
        "q": test_text,
        "from": "en",
        "to": "zh-CHS",
        "appKey": appKey,
        "salt": salt,
        "sign": sign
    }
    try:
        resp = requests.post("https://openapi.youdao.com/api", data=data, timeout=10)
        res = resp.json()
        if res.get("errorCode") == "0":
            print(f"✅ 翻译结果: {res['translation'][0]}")
            return True
        else:
            print(f"❌ 有道错误码：{res['errorCode']}")
            return False
    except Exception as e:
        print(f"❌ 有道接口异常: {str(e)}")
        return False

def test_baidu():
    print("\n--- 3. 测试百度翻译 ---")
    appid = config.TRANSLATE_BAIDU["appid"]
    secret = config.TRANSLATE_BAIDU["secret"]
    if not appid or not secret:
        print("❌ 未配置百度密钥，跳过")
        return False
    salt = "123456"
    sign = hashlib.md5(f"{appid}{test_text}{salt}{secret}".encode()).hexdigest()
    params = {
        "q": test_text,
        "from": "en",
        "to": "zh",
        "appid": appid,
        "salt": salt,
        "sign": sign
    }
    try:
        resp = requests.get("https://fanyi-api.baidu.com/api/trans/vip/translate", params=params)
        data = resp.json()
        if "trans_result" in data:
            print(f"✅ 翻译结果: {data['trans_result'][0]['dst']}")
            return True
        else:
            print(f"❌ 百度报错: {data}")
            return False
    except Exception as e:
        print(f"❌ 百度接口异常: {str(e)}")
        return False

def test_tencent():
    print("\n--- 4. 测试腾讯翻译 ---")

    sid = config.TRANSLATE_TENCENT["secret_id"]
    skey = config.TRANSLATE_TENCENT["secret_key"]
    if not sid or not skey:
        print("❌ 未配置腾讯翻译密钥，跳过")
        return False
    try:
        cred = credential.Credential(sid, skey)
        # 地域换成你自己的，ap-beijing / ap-guangzhou
        client = tmt_client.TmtClient(cred, "ap-beijing")

        
        req = models.TextTranslateRequest()
        params = {
            "SourceText": test_text,
            "Source": "en",      # 源语言
            "Target": "zh",      # 目标语言
            "ProjectId": 0       # 项目ID，默认0
        }
        req.from_json_string(json.dumps(params))

        # 4. 调用接口
        resp = client.TextTranslate(req)
        
        # 5. 处理返回结果
        print("翻译结果:", resp.TargetText)
        print("请求ID:", resp.RequestId)
        
    except TencentCloudSDKException as err:
        print("错误信息:", err)

if __name__ == "__main__":
    test_deepl()
    test_youdao()
    test_baidu()
    test_tencent()