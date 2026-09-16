import re
import urllib.request
from html.parser import HTMLParser
from urllib.parse import urljoin


class AnchorParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.href = ""
        self.text = ""
        self.items = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self.href = dict(attrs).get("href", "")
            self.text = ""

    def handle_data(self, data):
        if self.href:
            self.text += data

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self.href:
            text = " ".join(self.text.split())
            self.items.append((text, self.href))
            self.href = ""
            self.text = ""


url = "https://www.csu.edu.cn/zjzn/jgsz.htm"
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
html = urllib.request.urlopen(req, timeout=20).read().decode("utf-8", "ignore")
print("length", len(html))
parser = AnchorParser()
parser.feed(html)
keywords = ["办公室", "政策研究", "纪委", "巡视", "组织部", "宣传部", "统战部", "机关党委", "人事处", "科学技术", "人文社科"]
for text, href in parser.items:
    if text and any(k in text for k in keywords):
        print(text, "=>", urljoin(url, href))
for needle in ["机关党委", "人文社科处", "人文社会科学处", "社科处"]:
    pos = html.find(needle)
    print("TEXT", needle, pos)
    if pos >= 0:
        print(html[max(0, pos-500):pos+500])
