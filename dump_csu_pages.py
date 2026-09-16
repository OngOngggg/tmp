import re
from html.parser import HTMLParser
from audit_csu_sites import fetch


class Visible(HTMLParser):
    def __init__(self):
        super().__init__(); self.skip=0; self.parts=[]
    def handle_starttag(self, tag, attrs):
        if tag.lower() in ('script','style','noscript'): self.skip+=1
    def handle_endtag(self, tag):
        if tag.lower() in ('script','style','noscript') and self.skip: self.skip-=1
    def handle_data(self, data):
        if not self.skip: self.parts.append(data)

def text(url):
    r=fetch(url)
    if not r.get('ok'): return 'ERROR '+str(r)
    p=Visible(); p.feed(r['html']); return ' '.join(' '.join(p.parts).split())

pages={
 '学校办公室首页':'https://office.csu.edu.cn/',
 '政策研究室领导分工':'https://zys.csu.edu.cn/bmgk/ldfg.htm',
 '政策研究室联系我们':'https://zys.csu.edu.cn/bmgk/lxwm.htm',
 '纪委组织机构':'https://jjjc.csu.edu.cn/jgsz/zzjg.htm',
 '巡视办首页':'https://dwxsb.csu.edu.cn/',
 '巡视办组织机构':'https://dwxsb.csu.edu.cn/zzjg1/xsgzldxz.htm',
 '组织部领导分工':'https://zzb.csu.edu.cn/bmxx/ldfg.htm',
 '组织部联系电话':'https://zzb.csu.edu.cn/bmxx/lxdh.htm',
 '宣传部领导分工':'https://xcb.csu.edu.cn/bmgk/ldfg.htm',
 '宣传部组织机构':'https://xcb.csu.edu.cn/bmgk/zzjg.htm',
 '宣传部联系我们':'https://xcb.csu.edu.cn/bmgk/lxwm.htm',
 '统战部基本概况':'https://tzb.csu.edu.cn/bmjs/jbgk.htm',
 '机关党委机构设置':'https://jgdw.csu.edu.cn/bmgk/jgsz.htm',
 '机关党委联系我们':'https://jgdw.csu.edu.cn/bmgk/lxwm.htm',
 '人事处领导分工':'https://rsc.csu.edu.cn/jgsz/ldfg.htm',
 '科学研究部部门概况':'https://kxyjb.csu.edu.cn/bmgk.htm',
 '人文社科处机构设置':'https://rwskc.csu.edu.cn/wkgl/jgsz.htm',
 '人文社科处联系我们':'https://rwskc.csu.edu.cn/dpzwy.jsp?urltype=tree.TreeTempUrl&wbtreeid=1007',
}
if __name__ == '__main__':
    for label,u in pages.items():
        t=text(u)
        print('\n### '+label+'\nURL '+u+'\n'+t[:5000])
