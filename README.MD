## 爬虫 + 资源下载 + 翻译 + 生成双语文档一体化
```
Crawler-Translate/
├─ cache_html/        # 原始抓取页面缓存（阶段1输出）
├─ translate_task.json # 待翻译文本任务清单
├─ translate_result.json # 翻译完成映射结果
├─ output/            # 最终双语页面（阶段3输出）
├─ main.py            # 拆分3个执行入口：抓取/翻译/生成页面
├─ config.py
├─ secret_config.py
├─ test_translate_api.py
├─ test_static_download.py
├─ api_terms.json
└─ .gitignore

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
