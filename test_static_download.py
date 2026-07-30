# -*- coding: utf-8 -*-
import requests
from urllib.parse import urljoin
import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": config.BASE_URL
}

test_resources = [
    "/jsplumb.browser-ui.umd.js",
    "/jsplumb.css",
    "/community-logo.svg",
    "/lib/style.css"
]

def test_download():
    print("===== 静态资源下载测试工具 =====")
    for res_path in test_resources:
        full_url = urljoin(config.DOMAIN, res_path)
        print(f"\n测试地址: {full_url}")
        try:
            resp = requests.get(full_url, headers=HEADERS, timeout=10)
            print(f"状态码: {resp.status_code}")
            if resp.status_code == 200:
                print("✅ 下载正常")
            elif resp.status_code == 403:
                print("❌ 403 防盗链拦截，缺少Referer/UA")
            elif resp.status_code == 404:
                print("❌ 404 资源路径错误")
            else:
                print(f"❌ 访问失败，code:{resp.status_code}")
        except Exception as e:
            print(f"❌ 请求异常: {str(e)}")

if __name__ == "__main__":
    test_download()