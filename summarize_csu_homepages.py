from audit_csu_sites import SITES, fetch
from dump_csu_pages import Visible
import re

for name, url in SITES.items():
    r=fetch(url)
    print('\n###',name, r.get('status'), r.get('url'))
    if not r.get('ok'):
        print(r.get('error')); continue
    p=Visible(); p.feed(r['html']); t=' '.join(' '.join(p.parts).split())
    # compress common repeated nav fragments
    print(t[:3000])
    print('DATE TOKENS', re.findall(r'(?:20\d{2}[./-]\d{1,2}[./-]\d{1,2}|\d{1,2}[./-]\d{1,2}\s+20\d{2}|20\d{2}年\d{1,2}月\d{1,2}日)', t)[:80])
