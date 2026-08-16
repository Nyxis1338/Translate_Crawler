## 爬虫 + 资源下载 + 翻译 + 生成双语文档一体化

```
Crawler-Translate/
├── main.py                 # 程序入口
├── config.py               # 配置（已删除有道）
├── secret_config.py        # 密钥（需自行调整）
├── utils.py                # 通用工具函数
├── crawler.py              # 爬虫模块
├── translator.py           # 翻译模块
├── generator.py            # 生成双语HTML模块
├── api_terms.json          # 术语表（不变）
└── tests/                  # 测试脚本（可选）
    ├── test_translate_api.py
    └── test_static_download.py

```

### 以上结构为最初的结构内容

后期出现的文件，均是用程序生成的

```
python main.py
```

### 安装依赖

```
pip install requests beautifulsoup4 lxml deepl
pip install tencentcloud-sdk-python
pip install --upgrade tencentcloud-sdk-python-common==3.0.415
pip install --upgrade tencentcloud-sdk-python-tmt==3.0.415
```

common tmt 两个库的版本号要一致！！！

### 示例替换谷歌翻译：

先引入

```
from deepl import GoogleTranslator
```

然后在 translate_single_text(text):中替换

```
res = GoogleTranslator(source='en', target='zh-CN').translate(processed)
```
