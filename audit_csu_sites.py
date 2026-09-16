import json
import re
import ssl
import sys
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse


SSL_CTX = ssl._create_unverified_context()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"

SITES = {
    "学校办公室": "http://office.csu.edu.cn/",
    "政策研究室": "https://zys.csu.edu.cn/",
    "校纪委": "http://jjjc.csu.edu.cn/",
    "党委巡视办": "http://dwxsb.csu.edu.cn/",
    "组织部": "http://zzb.csu.edu.cn/",
    "宣传部": "http://xcb.csu.edu.cn/",
    "统战部": "http://tzb.csu.edu.cn/",
    "机关党委": "http://jgdw.csu.edu.cn/",
    "人事处": "http://rsc.csu.edu.cn/",
    "科学技术发展研究院": "http://kxyjb.csu.edu.cn/",
    "人文社科处": "https://rwskc.csu.edu.cn/",
}


class Parser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self.in_title = False
        self.links = []
        self.href = ""
        self.anchor_text = ""
        self.text = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        tag = tag.lower()
        if tag == "title":
            self.in_title = True
        elif tag == "a":
            self.href = attrs.get("href", "")
            self.anchor_text = ""

    def handle_data(self, data):
        if self.in_title:
            self.title += data
        if self.href:
            self.anchor_text += data
        self.text.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self.in_title = False
        elif tag == "a" and self.href:
            self.links.append((" ".join(self.anchor_text.split()), self.href))
            self.href = ""
            self.anchor_text = ""


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=20, context=SSL_CTX) as resp:
            body = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            try:
                text = body.decode(charset, "ignore")
            except LookupError:
                text = body.decode("utf-8", "ignore")
            return {"ok": True, "status": resp.status, "url": resp.geturl(), "html": text}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}", "url": url}


def clean_text(html):
    parser = Parser()
    parser.feed(html)
    text = " ".join(" ".join(parser.text).split())
    return parser, text


def relevant_links(base, html):
    parser, _ = clean_text(html)
    host = urlparse(base).netloc
    keys = ["机构", "组织", "部门", "简介", "概况", "领导", "联系我们", "新闻", "动态", "通知"]
    out = []
    seen = set()
    for text, href in parser.links:
        u = urljoin(base, href)
        if urlparse(u).netloc != host or u in seen or not u.startswith(("http://", "https://")):
            continue
        if text and any(k in text for k in keys):
            seen.add(u)
            out.append({"text": text, "url": u})
    return out[:50]


def main():
    result = {}
    for name, url in SITES.items():
        root = fetch(url)
        item = {"root": {k: v for k, v in root.items() if k != "html"}, "pages": []}
        if root.get("ok"):
            parser, text = clean_text(root["html"])
            item["root"]["title"] = " ".join(parser.title.split())
            item["root"]["text_len"] = len(text)
            candidates = [{"text": "首页", "url": root["url"]}] + relevant_links(root["url"], root["html"])
            seen = set()
            for c in candidates:
                if c["url"] in seen:
                    continue
                seen.add(c["url"])
                page = fetch(c["url"])
                record = {"label": c["text"], "url": c["url"]}
                record.update({k: v for k, v in page.items() if k != "html"})
                if page.get("ok"):
                    p, t = clean_text(page["html"])
                    record["title"] = " ".join(p.title.split())
                    record["text_len"] = len(t)
                    dates = sorted(set(re.findall(r"20(?:25|26)[年./-]\s*\d{1,2}[月./-]\s*\d{1,2}日?", t)))
                    record["dates"] = dates[-20:]
                    record["has_leader_terms"] = any(k in t for k in ["领导", "负责人", "办公地点", "联系电话", "固定电话"])
                    record["has_org_terms"] = any(k in t for k in ["机构设置", "内设机构", "组织机构", "部门职责"])
                    record["has_news_terms"] = any(k in (c["text"] + t[:1000]) for k in ["新闻", "动态", "通知"])
                item["pages"].append(record)
        result[name] = item
        print(name, item["root"])
        for p in item["pages"][:10]:
            print("  ", p.get("label"), p.get("status", "ERR"), p.get("url"), p.get("title", ""))
    with open("csu_site_audit.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
