"""
网页内容抓取模块

功能：
    1. 使用 requests + BeautifulSoup 抓取网页标题、正文文本；
    2. 提取表单中的输入框（name / type / placeholder），识别敏感索取字段；
    3. 提取页面中的外部链接、重定向次数、协议类型；
    4. 断网 / 页面不可达时返回明确的错误信息，不中断整个检测流程。

返回：
    fetch(url) -> dict
        ok            抓取是否成功
        error         失败原因
        title         页面标题
        text          页面纯文本（截断）
        forms         表单输入框列表 [{"name","type","placeholder"}]
        links         外部链接列表
        final_url     最终跳转地址
        redirect_count 重定向次数
        is_https      是否 HTTPS
        status        HTTP 状态码
"""
import warnings

import requests
from bs4 import BeautifulSoup
from urllib3.exceptions import InsecureRequestWarning

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
warnings.simplefilter("ignore", InsecureRequestWarning)

class ContentFetcher:

    def __init__(self, timeout=5):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})

    def fetch(self, url):
        result = {'ok':False, 
         'error':"", 
         'title':"", 
         'text':"", 
         'forms':[],  'links':[],  'final_url':url, 
         'redirect_count':0, 
         'is_https':(url.lower().startswith)("https://"), 
         'status':0}
        try:
            resp = self.session.get(url,
              timeout=(3, 5),
              verify=False,
              allow_redirects=True)
            result["status"] = resp.status_code
            result["final_url"] = resp.url
            result["redirect_count"] = len(resp.history)
            result["is_https"] = resp.url.lower().startswith("https://")
            if resp.encoding is None or resp.encoding.lower() == "iso-8859-1":
                resp.encoding = resp.apparent_encoding
            html = resp.text
            try:
                soup = BeautifulSoup(html, "lxml")
            except Exception:
                # 打包环境若缺 lxml，退回标准库解析器，保证抓取流程不中断
                soup = BeautifulSoup(html, "html.parser")
            if soup.title and soup.title.string:
                result["title"] = soup.title.string.strip()
            # 正文与表单提取不再依赖页面是否有 <title>，避免无标题页面漏检
            for tag in soup(["script", "style", "noscript", "iframe"]):
                tag.decompose()

            result["text"] = soup.get_text(separator=" ", strip=True)[:20000]
            for form in soup.find_all("form"):
                for inp in form.find_all("input"):
                    name = (inp.get("name") or "").strip()
                    ptype = (inp.get("type") or "text").strip().lower()
                    placeholder = (inp.get("placeholder") or "").strip()
                    result["forms"].append({'name':name, 
                     'type':ptype, 
                     'placeholder':placeholder})

            for a in soup.find_all("a", href=True):
                href = a["href"].strip()
                if href.lower().startswith(('http://', 'https://')):
                    result["links"].append(href)
            result["ok"] = True

        except requests.exceptions.SSLError:
            result["error"] = "SSL证书校验异常（可能存在证书伪造或不受信任证书）"
        except requests.exceptions.Timeout:
            result["error"] = "连接超时，网站响应过慢或不可达"
        except requests.exceptions.ConnectionError:
            result["error"] = "无法连接到该网站（域名不存在、网络中断或站点拒绝访问）"
        except requests.exceptions.TooManyRedirects:
            result["error"] = "重定向次数过多，可能是钓鱼网站在跳转引流"
        except requests.exceptions.HTTPError as e:
            try:
                status = e.response.status_code if e.response else 0
                if status == 403:
                    result["error"] = "访问被拒绝（403），该网站禁止抓取或需要登录"
                elif status == 404:
                    result["error"] = "页面不存在（404），该网址可能已失效"
                elif status == 401:
                    result["error"] = "需要登录认证（401），该页面需要权限才能访问"
                elif status >= 500:
                    result["error"] = f"服务器内部错误（{status}），网站暂时不可用"
                else:
                    result["error"] = f"HTTP 错误（{status}），无法正常访问该页面"
            finally:
                e = None
                del e

        except Exception as e:
            try:
                result["error"] = f"抓取失败：{str(e)[:150]}"
            finally:
                e = None
                del e

        return result
