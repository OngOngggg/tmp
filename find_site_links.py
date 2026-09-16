from audit_csu_sites import fetch
from dump_csu_pages import Visible
from urllib.parse import urljoin
import sys

base=sys.argv[1]
r=fetch(base)
p=Visible(); p.feed(r['html'])
for a in p.parts: pass
from html.parser import HTMLParser
class A(HTMLParser):
 def __init__(self): super().__init__(); self.h=''; self.t=''; self.out=[]
 def handle_starttag(self,tag,attrs):
  if tag=='a': self.h=dict(attrs).get('href',''); self.t=''
 def handle_data(self,d):
  if self.h:self.t+=d
 def handle_endtag(self,tag):
  if tag=='a' and self.h:self.out.append((' '.join(self.t.split()),urljoin(base,self.h)));self.h='';self.t=''
a=A();a.feed(r['html'])
for t,u in a.out:
 if any(k in t for k in ['巡视','组织','领导','机构','人员','职责','联系','概况','简介']): print(t,'=>',u)
