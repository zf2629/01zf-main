# -*- coding: utf-8 -*-
# 小宝影院 https://www.xiaobaoyy.com/ TVBox 蜘蛛
# 标准 MacCMS 站（mytheme 模板）：5 分类动态；列表 /vod/type/{id}[-{pg}].html；
# 二级筛选走 /vod/show/ 路由（id/class/area/year/lang/by 组合）；详情 /vod/detail/{id}.html；
# 播放 /vod/play/{id}-{sid}-{nid}.html，player_aaaa JSON 中 url 即 m3u8 直链（encrypt=0）
import re
import json
import html as _html
from urllib.parse import quote, unquote
import requests
from base.spider import Spider


class Spider(Spider):
    def getName(self):
        return "小宝影院"

    def init(self, extend=""):
        self.host = "http://xiaobaoyy.com/"
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.host + "/",
        })
        self._filter_cache = {}
        return {}

    CATS = [
        ("1", "电影"),
        ("2", "连续剧"),
        ("3", "综艺"),
        ("4", "动漫"),
        ("27", "短剧"),
        ("20", "理论片"),
    ]

    FILTERS = {
        "1": [
            {"key": "child", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "动作片", "v": "5"},
                {"n": "喜剧片", "v": "6"},
                {"n": "爱情片", "v": "7"},
                {"n": "科幻片", "v": "8"},
                {"n": "恐怖片", "v": "9"},
                {"n": "剧情片", "v": "10"},
                {"n": "战争片", "v": "11"},
                {"n": "纪录片", "v": "22"},
            ]},
            {"key": "class", "name": "剧情", "value": [
                {"n": "全部", "v": ""},
                {"n": "喜剧", "v": "喜剧"},
                {"n": "爱情", "v": "爱情"},
                {"n": "动作", "v": "动作"},
                {"n": "恐怖", "v": "恐怖"},
                {"n": "科幻", "v": "科幻"},
                {"n": "剧情", "v": "剧情"},
                {"n": "战争", "v": "战争"},
                {"n": "犯罪", "v": "犯罪"},
                {"n": "动画", "v": "动画"},
                {"n": "奇幻", "v": "奇幻"},
                {"n": "冒险", "v": "冒险"},
                {"n": "历史", "v": "历史"},
                {"n": "悬疑", "v": "悬疑"},
                {"n": "纪录", "v": "纪录"},
                {"n": "其他", "v": "其他"},
            ]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "美国", "v": "美国"},
                {"n": "韩国", "v": "韩国"},
                {"n": "日本", "v": "日本"},
                {"n": "泰国", "v": "泰国"},
                {"n": "英国", "v": "英国"},
                {"n": "法国", "v": "法国"},
                {"n": "其它", "v": "其它"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
                {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"},
                {"n": "2017", "v": "2017"},
                {"n": "2016", "v": "2016"},
                {"n": "2015", "v": "2015"},
                {"n": "2014", "v": "2014"},
                {"n": "2013", "v": "2013"},
                {"n": "2012", "v": "2012"},
                {"n": "2011", "v": "2011"},
                {"n": "2010", "v": "2010"},
            ]},
            {"key": "by", "name": "排序", "value": [
                {"n": "时间", "v": "time"},
                {"n": "人气", "v": "hits"},
                {"n": "评分", "v": "score"},
            ]},
        ],
        "2": [
            {"key": "child", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "国产剧", "v": "12"},
                {"n": "香港剧", "v": "13"},
                {"n": "台湾剧", "v": "14"},
                {"n": "日本剧", "v": "15"},
                {"n": "韩国剧", "v": "16"},
                {"n": "欧美剧", "v": "17"},
                {"n": "海外剧", "v": "18"},
                {"n": "泰国剧", "v": "19"},
            ]},
            {"key": "class", "name": "剧情", "value": [
                {"n": "全部", "v": ""},
                {"n": "剧情", "v": "剧情"},
                {"n": "爱情", "v": "爱情"},
                {"n": "古装", "v": "古装"},
                {"n": "悬疑", "v": "悬疑"},
                {"n": "都市", "v": "都市"},
                {"n": "喜剧", "v": "喜剧"},
                {"n": "战争", "v": "战争"},
                {"n": "犯罪", "v": "犯罪"},
                {"n": "奇幻", "v": "奇幻"},
                {"n": "动作", "v": "动作"},
                {"n": "历史", "v": "历史"},
                {"n": "其他", "v": "其他"},
            ]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "美国", "v": "美国"},
                {"n": "韩国", "v": "韩国"},
                {"n": "日本", "v": "日本"},
                {"n": "泰国", "v": "泰国"},
                {"n": "英国", "v": "英国"},
                {"n": "其它", "v": "其它"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
                {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"},
                {"n": "2017", "v": "2017"},
                {"n": "2016", "v": "2016"},
                {"n": "2015", "v": "2015"},
                {"n": "2014", "v": "2014"},
                {"n": "2013", "v": "2013"},
                {"n": "2012", "v": "2012"},
                {"n": "2011", "v": "2011"},
                {"n": "2010", "v": "2010"},
            ]},
            {"key": "by", "name": "排序", "value": [
                {"n": "时间", "v": "time"},
                {"n": "人气", "v": "hits"},
                {"n": "评分", "v": "score"},
            ]},
        ],
        "3": [
            {"key": "child", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "内地综艺", "v": "23"},
                {"n": "港台综艺", "v": "24"},
                {"n": "日韩综艺", "v": "25"},
                {"n": "欧美综艺", "v": "26"},
            ]},
            {"key": "class", "name": "剧情", "value": [
                {"n": "全部", "v": ""},
                {"n": "真人秀", "v": "真人秀"},
                {"n": "脱口秀", "v": "脱口秀"},
                {"n": "音乐", "v": "音乐"},
                {"n": "竞技", "v": "竞技"},
                {"n": "访谈", "v": "访谈"},
                {"n": "其他", "v": "其他"},
            ]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "韩国", "v": "韩国"},
                {"n": "日本", "v": "日本"},
                {"n": "欧美", "v": "欧美"},
                {"n": "其它", "v": "其它"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
                {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"},
            ]},
            {"key": "by", "name": "排序", "value": [
                {"n": "时间", "v": "time"},
                {"n": "人气", "v": "hits"},
                {"n": "评分", "v": "score"},
            ]},
        ],
        "4": [
            {"key": "child", "name": "类型", "value": [
                {"n": "全部", "v": ""},
                {"n": "国产动漫", "v": "28"},
                {"n": "港台动漫", "v": "29"},
                {"n": "日韩动漫", "v": "30"},
                {"n": "欧美动漫", "v": "31"},
                {"n": "海外动漫", "v": "32"},
            ]},
            {"key": "class", "name": "剧情", "value": [
                {"n": "全部", "v": ""},
                {"n": "冒险", "v": "冒险"},
                {"n": "战斗", "v": "战斗"},
                {"n": "搞笑", "v": "搞笑"},
                {"n": "科幻", "v": "科幻"},
                {"n": "奇幻", "v": "奇幻"},
                {"n": "恋爱", "v": "恋爱"},
                {"n": "日常", "v": "日常"},
                {"n": "校园", "v": "校园"},
                {"n": "其他", "v": "其他"},
            ]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "日本", "v": "日本"},
                {"n": "韩国", "v": "韩国"},
                {"n": "欧美", "v": "欧美"},
                {"n": "其它", "v": "其它"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
                {"n": "2019", "v": "2019"},
                {"n": "2018", "v": "2018"},
            ]},
            {"key": "by", "name": "排序", "value": [
                {"n": "时间", "v": "time"},
                {"n": "人气", "v": "hits"},
                {"n": "评分", "v": "score"},
            ]},
        ],
        "27": [
            {"key": "class", "name": "剧情", "value": [
                {"n": "全部", "v": ""},
                {"n": "古装", "v": "古装"},
                {"n": "复仇", "v": "复仇"},
                {"n": "悬疑", "v": "悬疑"},
                {"n": "甜宠", "v": "甜宠"},
                {"n": "穿越", "v": "穿越"},
                {"n": "逆袭", "v": "逆袭"},
                {"n": "重生", "v": "重生"},
                {"n": "萌宝", "v": "萌宝"},
            ]},
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "日本", "v": "日本"},
                {"n": "韩国", "v": "韩国"},
                {"n": "其它", "v": "其它"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
            ]},
            {"key": "by", "name": "排序", "value": [
                {"n": "时间", "v": "time"},
                {"n": "人气", "v": "hits"},
                {"n": "评分", "v": "score"},
            ]},
        ],
        "20": [
            {"key": "area", "name": "地区", "value": [
                {"n": "全部", "v": ""},
                {"n": "大陆", "v": "大陆"},
                {"n": "香港", "v": "香港"},
                {"n": "台湾", "v": "台湾"},
                {"n": "日本", "v": "日本"},
                {"n": "韩国", "v": "韩国"},
                {"n": "欧美", "v": "欧美"},
                {"n": "其它", "v": "其它"},
            ]},
            {"key": "year", "name": "年份", "value": [
                {"n": "全部", "v": ""},
                {"n": "2026", "v": "2026"},
                {"n": "2025", "v": "2025"},
                {"n": "2024", "v": "2024"},
                {"n": "2023", "v": "2023"},
                {"n": "2022", "v": "2022"},
                {"n": "2021", "v": "2021"},
                {"n": "2020", "v": "2020"},
            ]},
            {"key": "by", "name": "排序", "value": [
                {"n": "时间", "v": "time"},
                {"n": "人气", "v": "hits"},
                {"n": "评分", "v": "score"},
            ]},
        ],
    }

    # ---------- 基础 ----------
    def _fetch(self, url, params=None):
        try:
            r = self.session.get(url, params=params, timeout=20)
            if r.status_code != 200:
                return ""
            r.encoding = "utf-8"
            return r.text
        except Exception:
            return ""

    def _abs(self, u):
        u = _html.unescape((u or "").strip())
        if not u:
            return ""
        if u.startswith("http"):
            return u
        if u.startswith("//"):
            return "http:" + u
        return self.host.rstrip("/") + (u if u.startswith("/") else "/" + u)

    # ---------- 卡片解析 ----------
    def _parse_cards(self, html):
        vods = []
        seen = set()
        # 按整个 <a class="...myui-vodlist__thumb...">...</a> 切块，
        # 封面属性可能挂在 a 上（data-original），也可能在 style 背景图里
        for am in re.finditer(
                r'<a\b[^>]*class="[^"]*myui-vodlist__thumb[^"]*"[^>]*>.*?</a>',
                html, re.S):
            block = am.group(0)

            hm = re.search(r'href="(/vod/detail/(\d+)\.html)"', block)
            if not hm:
                continue
            vid = hm.group(2)
            if vid in seen:
                continue
            seen.add(vid)

            tm = re.search(r'title="([^"]*)"', block)
            nm = _html.unescape(tm.group(1).strip()) if tm else vid

            # 封面多级回退：
            # data-original → data-src → style 背景图 → img data-original → img src
            pm = (re.search(r'data-original="([^"]+)"', block)
                  or re.search(r'data-src="([^"]+)"', block)
                  or re.search(r'style="[^"]*?background(?:-image)?\s*:\s*'
                               r'url\(\s*[\'"]?([^\'")]+)', block)
                  or re.search(r'<img[^>]+?data-original="([^"]+)"', block)
                  or re.search(r'<img[^>]+?src="([^"]+)"', block))
            pic = self._abs(pm.group(1) if pm else "")

            # 备注：pic-text 里不是片名的那个（幻灯卡片 pic-text 是片名，跳过）
            remarks = ""
            for rm in re.finditer(
                    r'<span class="pic-text[^"]*">([^<]*)</span>', block):
                t = rm.group(1).strip()
                if t and t != nm:
                    remarks = t
                    break

            vods.append({
                "vod_id": vid,
                "vod_name": nm,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
        return vods

    # ---------- 二级分类 ----------
    def _opt_keyval(self, href, parent):
        """从筛选项 href 解析出 (key, value)"""
        u = unquote(href)
        m = re.search(r"/vod/show/id/(\d+)\.html", u)
        if m:
            return ("child", "") if m.group(1) == parent else ("child", m.group(1))
        m = re.search(r"/vod/show/class/([^/]+)/id/", u)
        if m:
            return ("class", m.group(1))
        m = re.search(r"/vod/show/area/([^/]+)/id/", u)
        if m:
            return ("area", m.group(1))
        m = re.search(r"/vod/show/id/\d+/year/(\d+)", u)
        if m:
            return ("year", m.group(1))
        m = re.search(r"/vod/show/id/\d+/lang/([^/]+?)(?:\.html|/|$)", u)
        if m:
            return ("lang", m.group(1))
        m = re.search(r"/vod/show/by/([^/]+)/id/", u)
        if m:
            return ("by", m.group(1))
        return (None, None)

    def _load_filters(self, cid):
        if cid in self._filter_cache:
            return self._filter_cache[cid]
        html = self._fetch("%s/vod/type/%s.html" % (self.host, cid))
        groups = []
        seen_keys = set()
        for um in re.finditer(
                r'<ul class="myui-screen__list[^"]*"[^>]*>(.*?)</ul>', html, re.S):
            block = um.group(1)
            dm = re.search(r'<li[^>]*>\s*<a[^>]*class="[^"]*text-muted[^"]*"[^>]*>([^<]{1,12})</a>',
                           block)
            dim_name = dm.group(1).strip() if dm else "筛选"
            items = []
            fkey = None
            for href, nm in re.findall(r'<a[^>]*href="(/vod/show/[^"]+)"[^>]*>([^<]+)</a>',
                                       block):
                if nm.strip() == "全部":
                    continue
                key, _ = self._opt_keyval(href, cid)
                if key:
                    fkey = key
                    break
            if not fkey:
                continue
            for href, nm in re.findall(r'<a[^>]*href="(/vod/show/[^"]+)"[^>]*>([^<]+)</a>',
                                       block):
                key, val = self._opt_keyval(href, cid)
                nm = nm.strip()
                if nm == "全部":
                    if not any(x["v"] == "" for x in items):
                        items.insert(0, {"n": "全部", "v": ""})
                    continue
                if key != fkey:
                    continue
                if nm and all(x["n"] != nm for x in items):
                    items.append({"n": nm, "v": val})
            if fkey and fkey not in seen_keys and len(items) > 1:
                seen_keys.add(fkey)
                groups.append({"key": fkey, "name": dim_name, "value": items})
        self._filter_cache[cid] = groups
        return groups

    def homeContent(self, filter=False):
        classes = [{"type_id": cid, "type_name": cn} for cid, cn in self.CATS]
        result = {"class": classes}
        if filter:
            result["filters"] = self.FILTERS
        return result

    def homeVideoContent(self):
        html = self._fetch(self.host + "/")
        return {"list": self._parse_cards(html), "parse": 0, "jx": 0}

    def _show_url(self, cid, pg, extend):
        ext = extend if isinstance(extend, dict) else {}
        child = (ext.get("child") or "").strip()
        base = "/vod/show/%s-----------" % (child if child else cid)
        # MacCMS 的 vod/show URL 形如 /vod/show/{id}-{class}-{area}-{year}-{lang}-{by}.html
        # 这里改用参数顺序拼装
        cls = (ext.get("class") or "").strip()
        area = (ext.get("area") or "").strip()
        year = (ext.get("year") or "").strip()
        lang = (ext.get("lang") or "").strip()
        by = (ext.get("by") or "").strip()
        parts = [child if child else cid,
                 quote(cls) if cls else "",
                 quote(area) if area else "",
                 year,
                 quote(lang) if lang else "",
                 by]
        base = "/vod/show/" + "-".join(parts)
        if pg > 1:
            base += "/page/%d" % pg
        return self.host + base + ".html"

    def categoryContent(self, tid, pg, filter=False, extend=None):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
            cid = tid if any(tid == c for c, _ in self.CATS) else "1"
            if isinstance(extend, str):
                try:
                    extend = json.loads(extend)
                except Exception:
                    extend = {}
            if extend and any((extend.get(k) or "").strip()
                              for k in ("child", "class", "area", "year", "lang", "by")):
                url = self._show_url(cid, pg, extend)
            else:
                url = "%s/vod/type/%s%s.html" % (
                    self.host, cid, "-%d" % pg if pg > 1 else "")
            html = self._fetch(url)
            vods = self._parse_cards(html)
            pagecount = 1
            pages = re.findall(r'/vod/type/%s-(\d+)\.html' % cid, html)
            if pages:
                pagecount = max(int(p) for p in pages)
            else:
                allp = re.findall(r'/page/(\d+)\.html', html)
                if allp:
                    pagecount = max(int(p) for p in allp)
                elif len(vods) < 20:
                    pagecount = pg
            return {"list": vods, "page": pg, "pagecount": pagecount,
                    "limit": 90, "total": 999999}
        except Exception as e:
            print("[%s] categoryContent 异常: %s" % (self.getName(), e))
            return {"list": [], "page": 1, "pagecount": 1, "limit": 90, "total": 0}

    def detailContent(self, ids):
        vods = []
        try:
            vid = re.sub(r"\D", "", ids[0] if ids else "")
            html = self._fetch("%s/vod/detail/%s.html" % (self.host, vid))
            if not html:
                return {"list": []}
            vod = {"vod_id": vid}
            m = re.search(r'<h1 class="title">([^<]+)</h1>', html)
            vod["vod_name"] = m.group(1).strip() if m else vid
            # 封面：myui-content__thumb 里可能用 data-original 也可能是 style 背景
            m = re.search(r'myui-content__thumb.*?data-original="([^"]+)"', html, re.S)
            if m:
                vod["vod_pic"] = self._abs(m.group(1))
            else:
                m = re.search(r'myui-content__thumb.*?url\(\s*[\'"]?([^\'")]+)', html, re.S)
                vod["vod_pic"] = self._abs(m.group(1) if m else "")
            m = re.search(r'<span class="text-red">([^<]*)</span>', html)
            vod["vod_remarks"] = m.group(1).strip() if m else ""
            m = re.search(r'<span class="sketch[^"]*"[^>]*>(.*?)</span>', html, re.S)
            if m:
                vod["vod_content"] = re.sub(r"<[^>]+>", "", m.group(1)).strip()[:500]
            actors = re.findall(r'/search/actor/[^"]*"[^>]*>([^<]+)</a>', html)
            vod["vod_actor"] = ",".join(dict.fromkeys(a.strip() for a in actors))[:200]
            directors = re.findall(r'/search/director/[^"]*"[^>]*>([^<]+)</a>', html)
            vod["vod_director"] = ",".join(dict.fromkeys(d.strip() for d in directors))[:200]

            play_from, play_url = [], []
            tabs = re.findall(
                r'<a[^>]*href="#playlist(\d+)"[^>]*>([^<]+)</a>', html)
            for num, src_name in tabs:
                src_name = src_name.strip()
                pm = re.search(
                    r'<div[^>]*id="playlist%s"[^>]*>(.*?)</div>\s*</div>' % num,
                    html, re.S)
                if not pm:
                    pm = re.search(r'id="playlist%s"' % num, html)
                    seg = html[pm.start():pm.start() + 20000] if pm else ""
                else:
                    seg = pm.group(1)
                eps = []
                for href, nm in re.findall(
                        r'<a[^>]*href="(/vod/play/\d+-\d+-\d+\.html)"[^>]*>([^<]*)</a>',
                        seg):
                    nm = nm.strip() or "正片"
                    eps.append("%s$%s" % (nm, self._abs(href)))
                if eps:
                    play_from.append(src_name)
                    play_url.append("#".join(eps))
            vod["vod_play_from"] = "$$$".join(play_from)
            vod["vod_play_url"] = "$$$".join(play_url)
            vods.append(vod)
        except Exception as e:
            print("[%s] detailContent 异常: %s" % (self.getName(), e))
        return {"list": vods}

    def searchContent(self, key, quick=False, pg=1):
        try:
            pg = int(pg) if str(pg).isdigit() else 1
            # MacCMS 搜索路径：/search/{wd}-------------.html
            html = self._fetch("%s/search/%s-------------.html" % (
                self.host, quote(key)))
            if not html:
                html = self._fetch("%s/search.html" % self.host,
                                   params={"wd": key, "submit": ""})
            vods = self._parse_cards(html)
            return {"list": vods, "page": pg, "pagecount": 1,
                    "limit": 90, "total": len(vods)}
        except Exception as e:
            print("[%s] searchContent 异常: %s" % (self.getName(), e))
            return {"list": [], "page": 1, "pagecount": 1, "limit": 90, "total": 0}

    def playerContent(self, flag, id, vipFlags=None):
        result = {"parse": 0, "playUrl": "", "url": "", "header": {}}
        try:
            pid = (id or "").strip()
            if not pid:
                return result
            if pid.startswith("http") and ".m3u8" in pid:
                result["url"] = pid
            else:
                page_url = pid if pid.startswith("http") else self._abs(pid)
                html = self._fetch(page_url)
                m = re.search(r'var player_aaaa=(\{.*?\})\s*</script>', html, re.S)
                if m:
                    try:
                        data = json.loads(m.group(1))
                    except Exception:
                        data = {}
                    url = (data.get("url") or "").replace("\\/", "/")
                    if url.startswith("http"):
                        result["url"] = url
            if result["url"]:
                result["header"] = {
                    "Referer": self.host + "/",
                    "User-Agent": self.session.headers.get("User-Agent", "Mozilla/5.0"),
                }
            return result
        except Exception as e:
            print("[%s] playerContent 异常: %s" % (self.getName(), e))
            return result

    def isVideoFormat(self, url):
        return bool(url) and (".m3u8" in url or ".mp4" in url)

    def manualVideoCheck(self):
        return False

    def localProxy(self, param):
        return [404, "text/plain", ""]