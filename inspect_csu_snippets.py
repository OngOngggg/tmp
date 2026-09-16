import json
import re
from audit_csu_sites import fetch, clean_text

d = json.load(open("csu_site_audit.json", encoding="utf-8"))
for name, item in d.items():
    print("\n###", name)
    root = fetch(item["root"]["url"])
    if root.get("ok"):
        _, root_text = clean_text(root["html"])
        for term in ["负责人", "领导", "主任", "办公地点", "固定电话", "联系电话", "机构设置", "内设机构"]:
            pos = root_text.find(term)
            if pos >= 0:
                print("ROOT", term, root_text[max(0, pos-100):pos+220])
    for p in item.get("pages", []):
        if not p.get("ok"):
            print("ERROR", p)
        if p.get("label") in ["首页", "部门简介", "部门概况", "部门职责", "职能简介", "领导分工", "机构设置", "组织机构", "联系我们"]:
            print(p.get("label"), p.get("url"), "title=", p.get("title"), "dates=", p.get("dates"), "leader=", p.get("has_leader_terms"), "org=", p.get("has_org_terms"))
            pg = fetch(p.get("url"))
            if pg.get("ok"):
                _, txt = clean_text(pg["html"])
                for term in ["负责人", "领导", "主任", "办公地点", "固定电话", "联系电话", "机构设置", "内设机构", "部门职责"]:
                    pos = txt.find(term)
                    if pos >= 0:
                        print("  ", term, txt[max(0, pos-80):pos+180])
