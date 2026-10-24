# -*- coding: utf-8 -*-
"""
520短剧 - www.wodocx.com
MacCMS（stui / okpc 模板），服务端渲染，curl 直连无验证、无签名。

按用户要求「只要短剧」：本插件仅暴露「短剧」分类（tid=36），但详情/播放接口通用。

关键结论（已实测验证）：
1. 首页 / ：卡片 <a class="stui-vodlist__thumb lazyload" href="/voddetail/{id}.html"
   data-original="封面" title="片名">，备注在 span.pic-text。
2. 分类 /vodshow/{tid}-----------.html（第1页）；分页 /vodshow/{tid}--------{pg}---.html。
   短剧 tid=36。
3. 详情 /voddetail/{id}.html：标题 <h1>…（社媒标题）或 <title>；线路块为
   div.stui-pannel-box 内 <h3 class="title">线路名</h3> + ul.stui-content__playlist
   + <a href="/vodplay/{id}-{sid}-{nid}.html">集名</a>（多为「全集」）。
4. 播放 /vodplay/{id}-{sid}-{nid}.html：
   var player_aaaa={"flag":"play","encrypt":0,"url":"https://.../index.m3u8",...}
   encrypt=0 时 url 即真实直链，可直接播放（实测 200 application/vnd.apple.mpegurl）。
5. 搜索 /vodsearch/-------------.html?wd=关键词（结果卡片同列表）。
   原生建议接口 /index.php/ajax/suggest?mid=1&wd= 可用。
"""
import re
import json
import time
import urllib.parse
import requests
from urllib.parse import quote

try:
    from base.spider import Spider
except ImportError:
    class Spider:
        def __init__(self):
            pass


class Spider(Spider):
    # ==================== 基础配置 ====================
    name = "520短剧"
    base_url = "https://www.wodocx.com"
    site_url = "https://www.wodocx.com"

    searchable = 1
    quickSearch = 1
    filterable = 1
    changeable = 1

    # 按用户要求：仅短剧
    class_name = ["短剧"]
    class_url = ["36"]
    CATEGORY_NAMES = {
        "36": "短剧",
    }

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Referer": "https://www.wodocx.com/",
        "Connection": "keep-alive",
    }

    play_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://www.wodocx.com/",
        "Accept": "*/*",
    }

    def __init__(self):
        super().__init__()
        self._session = requests.Session()
        self._session.headers.update(self.headers)
        self._play_cache = {}
        self._cache_ttl = 1800
        self._last_req_time = 0
        self._min_req_interval = 0.8
        self._re_name_garbage = re.compile(
            r'[\s\-_]*(?:HD|TC|TS|抢先版|枪版|DVD|BD|1080P|720P|4K|2K|高清|超清|蓝光|国语|粤语|中字|完整版|全集完结|全集|未删减版|(?:第[0-9一二三四五六七八九十]+[集季期]))\s*$',
            re.I)

    # ==================== 工具方法 ====================
    def _log(self, msg):
        print("[%s] %s" % (self.name, msg))

    def _clean_html(self, text):
        if not text:
            return ""
        text = re.sub(r'<br\s*/?>', ' ', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _clean_vod_name(self, name):
        if not name:
            return name
        prev = name
        while True:
            cleaned = self._re_name_garbage.sub('', prev).strip()
            if cleaned == prev:
                break
            prev = cleaned
        return prev

    def _fix_pic(self, pic):
        if not pic:
            return ""
        pic = pic.strip()
        if pic.startswith("//"):
            return "https:" + pic
        if pic.startswith("/"):
            return self.base_url + pic
        return pic

    # ==================== 请求基础 ====================
    def _apply_req_delay(self):
        now = time.time()
        elapsed = now - self._last_req_time
        if 0 < elapsed < self._min_req_interval:
            time.sleep(self._min_req_interval - elapsed)
        self._last_req_time = time.time()

    def fetch(self, url, headers=None, timeout=30):
        self._apply_req_delay()
        return self._session.get(url, headers=headers or {}, timeout=timeout)

    def _is_bad_page(self, html):
        if not html:
            return True
        if '404 Not Found' in html or 'System Error' in html:
            return True
        return False

    def _get(self, url, max_retry=3, timeout=15):
        try:
            for attempt in range(max_retry):
                resp = self.fetch(url, headers=self.headers, timeout=timeout)
                html = resp.text
                if self._is_bad_page(html):
                    self._log("页面异常(%s)，重试 %s" % (resp.status_code, url))
                    if attempt < max_retry - 1:
                        time.sleep(1 + attempt)
                        continue
                    return ""
                return html
            return ""
        except Exception as e:
            self._log("请求失败: %s, %s" % (url, e))
            return ""

    # ==================== 列表解析 ====================
    def _parse_video_list(self, html):
        """解析 stui-vodlist__thumb 卡片（首页/分类/搜索通用）"""
        videos = []
        if not html:
            return videos
        pattern = re.compile(
            r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*>(.*?)</a>', re.DOTALL)
        for m in pattern.finditer(html):
            tag = m.group(0)
            hm = re.search(r'href="(/voddetail/(\d+)\.html)"', tag)
            if not hm:
                continue
            vod_id = hm.group(2)
            tm = re.search(r'title="([^"]*)"', tag)
            pm = re.search(r'data-original="([^"]+)"', tag)
            if not pm:
                pm = re.search(r'src="([^"]+)"', tag)
            rm = re.search(r'pic-text[^>]*>([^<]*)<', tag)
            title = tm.group(1).strip() if tm else ""
            if not title:
                im = re.search(r'alt="([^"]*)"', tag)
                if im:
                    title = im.group(1).strip()
            videos.append({
                "vod_id": vod_id,
                "vod_name": self._clean_vod_name(title),
                "vod_pic": self._fix_pic(pm.group(1) if pm else ""),
                "vod_remarks": self._clean_html(rm.group(1)) if rm else "",
            })
        return videos

    # ==================== 播放源解析（详情页） ====================
    def _parse_play_sources(self, html, vod_id):
        """
        线路：div.stui-pannel-box 内 <h3 class="title">线路名</h3>
              + ul.stui-content__playlist + <a href="/vodplay/{id}-{sid}-{nid}.html">
        按播放列表块在文档中出现的顺序组织线路。
        """
        sources = []
        if not html:
            return sources
        blocks = re.findall(
            r'<ul[^>]*class="[^"]*stui-content__playlist[^"]*"[^>]*>(.*?)</ul>',
            html, re.DOTALL)
        for blk in blocks:
            eps = re.findall(
                r'href="/vodplay/%s-(\d+)-(\d+)\.html"[^>]*>([^<]*)</a>' % re.escape(str(vod_id)),
                blk)
            if not eps:
                continue
            # 线路名：取该 ul 之前最近的 .title 文本
            pos = html.find(blk)
            head = html[max(0, pos - 1200):pos]
            names = re.findall(r'class="title"[^>]*>(.*?)</h3>', head, re.DOTALL)
            name = self._clean_html(names[-1]) if names else ("线路%s" % (len(sources) + 1))
            sid = eps[0][0]
            seen = set()
            ep_list = []
            for _sid, nid, title in sorted(eps, key=lambda x: int(x[1])):
                if nid in seen:
                    continue
                seen.add(nid)
                ep_name = self._clean_html(title) or ("第%02d集" % (int(nid) + 1))
                ep_list.append({"name": ep_name, "link": "%s-%s-%s" % (vod_id, sid, nid)})
            if ep_list and not any(s["source_name"] == name for s in sources):
                sources.append({"source_name": name, "episodes": ep_list})
        return sources

    # ==================== 播放地址解析 ====================
    def _extract_player_data(self, html):
        """提取 var player_aaaa={...}（JSON），手写括号配平"""
        if not html:
            return None
        m = re.search(r'var\s+player_aaaa\s*=\s*', html)
        if not m:
            return None
        start = m.end()
        while start < len(html) and html[start] != '{':
            start += 1
        if start >= len(html):
            return None
        depth = 1
        i = start + 1
        in_string = False
        escape = False
        while i < len(html) and depth > 0:
            c = html[i]
            if in_string:
                if escape:
                    escape = False
                elif c == '\\':
                    escape = True
                elif c == '"':
                    in_string = False
            else:
                if c == '"':
                    in_string = True
                elif c == '{':
                    depth += 1
                elif c == '}':
                    depth -= 1
            i += 1
        if depth == 0:
            try:
                return json.loads(html[start:i])
            except Exception:
                pass
        return None

    def _get_play_url(self, vod_id, sid, nid):
        play_page = "%s/vodplay/%s-%s-%s.html" % (self.base_url, vod_id, sid, nid)
        cache_key = "%s-%s-%s" % (vod_id, sid, nid)
        now = time.time()
        if cache_key in self._play_cache:
            url, ts = self._play_cache[cache_key]
            if now - ts < self._cache_ttl:
                return url
        try:
            html = self._get(play_page, max_retry=2, timeout=12)
            if not html:
                return play_page
            pd = self._extract_player_data(html)
            if not pd:
                return play_page
            enc_url = (pd.get("url") or "").strip()
            encrypt = str(pd.get("encrypt", "0"))
            if encrypt == "1":
                enc_url = urllib.parse.unquote(enc_url)
            elif encrypt == "2":
                try:
                    import base64
                    enc_url = urllib.parse.unquote(base64.b64decode(enc_url).decode('utf-8'))
                except Exception:
                    pass
            if not enc_url:
                iframe = re.search(r'<iframe[^>]*src="([^"]+)"', html)
                if iframe:
                    enc_url = iframe.group(1)
                else:
                    return play_page
            self._log("播放直链: %s" % enc_url[:80])
            self._play_cache[cache_key] = (enc_url, now)
            return enc_url
        except Exception as e:
            self._log("获取播放地址异常: %s" % e)
            return play_page

    # ==================== TVBox 核心方法 ====================
    def init(self, extend=''):
        self._log("初始化完成")

    # ==================== 子分类（filters） ====================
    # 520电影网 vodshow 筛选串槽位（12 段，用 - 连接）：
    #   [0]=tid [1]=地区 [2]=排序 [3]=剧情 [4]... [8]=页码 [11]=年份
    # 实测：该站短剧类下「地区」「剧情」筛选无内容返回；「年份」「排序」有效。
    # URL 规则： /vodshow/{tid}-{area}-{order}-{class}-----{page}---{year}.html
    FILTER_YEARS = ["2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019"]
    FILTER_ORDERS = [("time", "按时间"), ("hits", "按人气"), ("score", "按评分")]

    def _build_show_url(self, tid, area="", order="", cls="", page="", year=""):
        t = [str(tid)] + [""] * 11
        t[1] = area
        t[2] = order
        t[3] = cls
        t[8] = str(page) if page else ""
        t[11] = year
        return "%s/vodshow/%s.html" % (self.base_url, "-".join(t))

    def homeContent(self, filter=False):
        result = {
            "class": [
                {"type_id": tid, "type_name": name}
                for tid, name in self.CATEGORY_NAMES.items()
            ]
        }
        if filter:
            year_vals = [{"n": "全部", "v": ""}] + [{"n": y, "v": y} for y in self.FILTER_YEARS]
            order_vals = [{"n": n, "v": v} for v, n in self.FILTER_ORDERS]
            f = [
                {"key": "year", "name": "年份", "value": year_vals},
                {"key": "order", "name": "排序", "value": order_vals},
            ]
            result["filters"] = {tid: f for tid in self.CATEGORY_NAMES}
            result["filter"] = {tid: f for tid in self.CATEGORY_NAMES}
        return result

    def homeVideoContent(self):
        try:
            # 首页无短剧专属推荐位，直接取短剧分类第一页
            html = self._get(self._build_show_url("36"))
            if not html:
                return {"list": []}
            videos = self._parse_video_list(html)
            seen = set()
            dedup = []
            for v in videos:
                if v["vod_id"] not in seen:
                    seen.add(v["vod_id"])
                    dedup.append(v)
            return {"list": dedup[:30]}
        except Exception as e:
            self._log("homeVideoContent异常: %s" % e)
            return {"list": []}

    def categoryContent(self, tid, pg, filter=False, content=None):
        try:
            pg = max(1, int(pg or 1))
            if str(tid) not in self.CATEGORY_NAMES:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 36, "total": 0}
            content = content or {}
            year = str(content.get("year", "") or "")
            order = str(content.get("order", "") or "")
            # 页码槽位：第1页可用空值，第N页填 N（实测 slot=N 对应第 N 页）
            url = self._build_show_url(
                tid, order=order, page=("" if pg == 1 else pg), year=year)
            self._log("分类请求: " + url)
            html = self._get(url)
            if not html:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 36, "total": 0}
            videos = self._parse_video_list(html)
            pagecount = 1
            # 分页链接形如 /vodshow/{tid}-...-{n}---...html，取页码槽位
            pages = re.findall(r'/vodshow/%s-[^"]*?-(\d+)---' % re.escape(str(tid)), html)
            if pages:
                pagecount = max(int(x) for x in pages)
            return {
                "list": videos,
                "page": pg,
                "pagecount": pagecount,
                "limit": 36,
                "total": pagecount * 36,
            }
        except Exception as e:
            self._log("categoryContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 36, "total": 0}

    def searchContent(self, key, quick=False, pg="1"):
        try:
            try:
                pg = max(1, int(pg or 1))
            except (TypeError, ValueError):
                pg = 1
            keyword = str(key or "").strip()
            if not keyword:
                return {"page": pg, "pagecount": 1, "limit": 0, "total": 0, "list": []}
            if pg == 1:
                url = "%s/vodsearch/-------------.html?wd=%s" % (self.base_url, quote(keyword))
            else:
                url = "%s/vodsearch/--------%d---.html?wd=%s" % (self.base_url, pg, quote(keyword))
            self._log("搜索请求: %s quick=%s" % (url, quick))
            html = self._get(url)
            if not html:
                return {"list": [], "page": pg, "pagecount": 1, "limit": 36, "total": 0}
            videos = self._parse_video_list(html)
            if not quick:
                key_lower = keyword.lower()

                def _score(v):
                    name = v.get('vod_name', '').lower()
                    if name == key_lower:
                        return 0
                    if name.startswith(key_lower):
                        return 1
                    if key_lower in name:
                        return 2
                    return 3
                videos = sorted(videos, key=_score)
            return {
                "list": videos,
                "page": pg,
                "pagecount": 9999,
                "limit": 36,
                "total": 999999,
            }
        except Exception as e:
            self._log("searchContent异常: %s" % e)
            return {"list": [], "page": pg, "pagecount": 1, "limit": 36, "total": 0}

    def detailContent(self, ids):
        try:
            vod_id = ids[0] if isinstance(ids, list) else str(ids)
            url = "%s/voddetail/%s.html" % (self.base_url, vod_id)
            self._log("详情请求: " + url)
            html = self._get(url)
            if not html:
                return {"list": []}

            vod_name = ""
            m = re.search(r'<h1[^>]*>([^<]*)</h1>', html)
            if m:
                vod_name = self._clean_html(m.group(1))
            if not vod_name:
                m = re.search(r'<title>《?([^》<]*)》?', html)
                if m:
                    vod_name = self._clean_html(m.group(1))
            vod_name = self._clean_vod_name(vod_name) or "未知"

            vod_pic = ""
            pm = re.search(r'<a[^>]*class="[^"]*stui-vodlist__thumb[^"]*"[^>]*data-original="([^"]+)"', html)
            if not pm:
                pm = re.search(r'data-original="([^"]+)"', html)
            if pm:
                vod_pic = self._fix_pic(pm.group(1))

            vod_year = vod_area = vod_actor = vod_director = vod_remarks = vod_content = ""
            # 简介
            cm = re.search(r'<p class="col-pd">(.*?)</p>', html, re.DOTALL)
            if not cm:
                cm = re.search(r'id="desc".*?<p[^>]*>(.*?)</p>', html, re.DOTALL)
            if cm:
                vod_content = self._clean_html(cm.group(1))
            # 元信息
            detail_block = ""
            db = re.search(r'<div[^>]*class="[^"]*stui-content__detail[^"]*"[^>]*>(.*?)</div>\s*</div>', html, re.DOTALL)
            if db:
                detail_block = db.group(1)
            if detail_block:
                def _pick(pat):
                    mm = re.search(pat, detail_block, re.DOTALL)
                    return self._clean_html(mm.group(1)) if mm else ""
                vod_year = _pick(r'类型[：:].*?(\d{4})') or _pick(r'年份[：:]\s*([^<|]+)')
                vod_area = _pick(r'地区[：:]\s*([^<|]+)')
                vod_actor = _pick(r'主演[：:]\s*(.+?)</p>')
                vod_director = _pick(r'导演[：:]\s*([^<|]+)')
                vod_remarks = _pick(r'状态[：:]\s*([^<|]+)')
            if not vod_content:
                m = re.search(r'<meta name="description" content="([^"]*)"', html)
                if m:
                    vod_content = self._clean_html(m.group(1))

            sources = self._parse_play_sources(html, vod_id)
            if not sources:
                self._log("未能解析到播放源")
                return {"list": []}

            from_list = []
            url_list = []
            for src in sources:
                from_list.append(src["source_name"])
                url_list.append("#".join(
                    "%s$%s" % (ep["name"], ep["link"]) for ep in src["episodes"]))

            video = {
                "vod_id": vod_id,
                "vod_name": vod_name,
                "vod_pic": vod_pic,
                "vod_year": vod_year,
                "vod_area": vod_area,
                "vod_actor": vod_actor,
                "vod_director": vod_director,
                "vod_content": vod_content,
                "vod_remarks": vod_remarks,
                "vod_play_from": "$$$".join(from_list),
                "vod_play_url": "$$$".join(url_list),
            }
            self._log("详情解析成功: %s 线路: %s" % (vod_name, "$$$".join(from_list)))
            return {"list": [video]}
        except Exception as e:
            self._log("detailContent异常: %s" % e)
            return {"list": []}

    def playerContent(self, flag, id, vipFlags=None):
        try:
            parts = str(id).split("-")
            if len(parts) != 3:
                return {"parse": 0, "url": "", "header": ""}
            vod_id, sid, nid = parts
            play_url = self._get_play_url(vod_id, sid, nid)
            if not play_url:
                play_url = "%s/vodplay/%s-%s-%s.html" % (self.base_url, vod_id, sid, nid)
            is_direct = bool(re.search(r'\.(m3u8|mp4|flv|ts|mkv)([?#&]|$)', play_url, re.I))
            is_webview = play_url.startswith(self.base_url + "/vodplay/")
            parse_flag = 0 if (is_direct or not is_webview) else 1
            self._log("播放URL: %s... parse=%d" % (play_url[:80], parse_flag))
            if parse_flag == 0:
                return {"parse": 0, "url": play_url, "header": self.play_headers.copy()}
            return {"parse": 1, "url": play_url, "header": ""}
        except Exception as e:
            self._log("playerContent异常: %s" % e)
            return {"parse": 0, "url": "", "header": ""}

    def getName(self):
        return self.name

    def isVideoFormat(self, url):
        pass

    def manualVideoCheck(self):
        pass

    def destroy(self):
        pass

    def localProxy(self, param):
        pass
