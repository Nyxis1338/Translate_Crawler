## 爬虫 + 资源下载 + 翻译 + 生成双语文档一体化
```
jsplumb-docs-crawler/
├─ main.py               # 主程序（爬虫+翻译+页面生成一体化）
├─ api_terms.json          # 统一中英API术语对照表（单独分离便于修改）
├─ template.html         # 双语切换UI组件（css+js，自动注入所有页面）
├─ .gitignore
└─ output/               # 程序自动生成输出目录
   ├─ raw_en/            # 原始英文网页（爬取源文件）
   ├─ assets/            # 本地静态资源（css/js/image）
   └─ bilingual_docs/    # 最终成品：离线双语完整文档站
```
### 以上结构为最初的结构内容
后期出现的文件，均是用程序生成的
```
python main.py
```



### 安装依赖
```
pip install requests beautifulsoup4 lxml deepl
```


### 示例替换谷歌翻译： 
先引入
```
from deepl import GoogleTranslator
```
然后在 translate_single_text(text):中替换
```
res = GoogleTranslator(source='en', target='zh-CN').translate(processed)
```
