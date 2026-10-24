# -*- coding: utf-8 -*-
# TVBox/影视仓 Python 爬虫 - 影视天下 hamp4.py v1.0
# 站点: https://www.hamp4.com/  (苹果CMS / STUI模板)
# 分类: /type/{tid}.html 每页96条固定; 分页列表 /show/{tid}--------{pg}---.html 每页24条(页间不重叠,翻页有效)
# 分类策略: 一次合并3页(24x3=72条), 翻页按3页步进
# 详情: /detail/{id}.html -> 线路h4 + ul.stui-content__playlist li a[href=/play/{vid}-{line}-{ep}.html]
# 播放: /play/{vid}-{line}-{ep}.html -> var player_data={"url":"https://.../index.m3u8"} 直链(encrypt=0)
# 搜索: /search/{kw}-------------.html 每页24条
import re
import sys
import json
import time
import gzip
import threading
import urllib.parse
import urllib.request
import ssl

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        pass

CACHE_TTL = 600
_HOST_CACHE = {"host": None, "ts": 0}
_REQ_CACHE = {}

UA = ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')

HOSTS = [
    "https://www.hamp4.com",
]

CATEGORIES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
]

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _log(*args):
    try:
        print("[影视天下]", *args)
    except Exception:
        pass


def _http_get(url, referer=None, timeout=12):
    headers = {'User-Agent': UA, 'Accept-Encoding': 'gzip',
               'Accept-Language': 'zh-CN,zh;q=0.9'}
    if referer:
        headers['Referer'] = referer
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=timeout, context=_CTX)
            raw = resp.read()
            if raw[:2] == b'\x1f\x8b':
                raw = gzip.decompress(raw)
            return raw.decode('utf-8', 'ignore')
        except Exception as e:
            _log("GET失败(%d/2)" % (attempt + 1), url[:70], repr(e)[:70])
            time.sleep(0.4)
    return ''


def _cache_get(key):
    v = _REQ_CACHE.get(key)
    if v and v[0] > time.time():
        return v[1]
    _REQ_CACHE.pop(key, None)
    return None


def _cache_set(key, val, ttl=CACHE_TTL):
    if len(_REQ_CACHE) > 256:
        _REQ_CACHE.clear()
    _REQ_CACHE[key] = (time.time() + ttl, val)


def _get(url, referer=None, ttl=CACHE_TTL):
    ck = 'G|%s|%s' % (url, referer or '')
    hit = _cache_get(ck)
    if hit is not None:
        return hit
    html = _http_get(url, referer=referer)
    if html:
        _cache_set(ck, html, ttl)
    else:
        _cache_set(ck, '', 90)
    return html


def _host():
    if _HOST_CACHE["host"] and _HOST_CACHE["ts"] > time.time():
        return _HOST_CACHE["host"]
    host = HOSTS[0].rstrip('/')
    _HOST_CACHE.update(host=host, ts=time.time() + 7200)
    return host


def _abs(u):
    if not u:
        return ''
    if u.startswith('//'):
        return 'https:' + u
    if u.startswith('http'):
        return u
    return _host() + u


def _parse_list(html):
    """从列表页HTML解析 vod: a[href=/detail/{id}.html title] + img data-original"""
    vods = []
    seen = set()
    # 匹配卡片: <a class="stui-vodlist__thumb lazyload" href="/detail/xxx.html" title="名称" data-original="海报">
    for m in re.finditer(
            r'<a[^>]*href="(/detail/(\d+)\.html)"[^>]*title="([^"]*)"[^>]*data-original="([^"]+)"', html):
        vid, name, pic = m.group(2), m.group(3), m.group(4)
        if vid in seen or not name:
            continue
        seen.add(vid)
        vods.append({
            "vod_id": vid,
            "vod_name": name.strip(),
            "vod_pic": _abs(pic),
            "vod_remarks": '',
        })
    # 兼容 title 在 data-original 之后的情况
    if not vods:
        for m in re.finditer(
                r'<a[^>]*href="(/detail/(\d+)\.html)"[^>]*data-original="([^"]+)"[^>]*title="([^"]*)"', html):
            vid, pic, name = m.group(2), m.group(3), m.group(4)
            if vid in seen or not name:
                continue
            seen.add(vid)
            vods.append({
                "vod_id": vid,
                "vod_name": name.strip(),
                "vod_pic": _abs(pic),
                "vod_remarks": '',
            })
    return vods


def home_content(filter_=False):
    return {
        "class": [{"type_id": c["type_id"], "type_name": c["type_name"]} for c in CATEGORIES],
        "filters": {},
    }


def home_video_content():
    # 首页取 /type/1.html 最新电影(96条), 与kanxige同族
    html = _get(_host() + '/type/1.html', _host() + '/', ttl=1800)
    vods = _parse_list(html)
    return {"list": vods[:36]}


def category_content(tid, pg="1", filter_=None, extend=None):
    try:
        pg = int(pg)
    except Exception:
        pg = 1
    if pg < 1:
        pg = 1
    # 一次合并3页: 起始页 = (pg-1)*3+1
    start = (pg - 1) * 3 + 1
    vods = []
    seen = set()
    for i in range(3):
        pno = start + i
        url = '%s/show/%s--------%d---.html' % (_host(), tid, pno)
        html = _get(url, '%s/type/%s.html' % (_host(), tid))
        if not html:
            break
        for v in _parse_list(html):
            if v['vod_id'] not in seen:
                seen.add(v['vod_id'])
                vods.append(v)
        if len(_parse_list(html)) == 0:
            break
    return {
        "list": vods,
        "page": pg,
        "pagecount": 9999 if vods else pg,
        "limit": len(vods) or 24,
        "total": 999999 if vods else 0,
    }


def detail_content(ids):
    if isinstance(ids, list):
        ids = ids[0]
    m = re.search(r'(\d+)', str(ids))
    if not m:
        return {"list": []}
    vid = m.group(1)
    html = _get('%s/detail/%s.html' % (_host(), vid), '%s/' % _host())
    if not html:
        return {"list": []}
    title = ''
    m = re.search(r'<h1[^>]*class="title"[^>]*>([^<]+)</h1>', html)
    if m:
        title = m.group(1).strip()
    if not title:
        return {"list": []}
    vod = {
        "vod_id": vid,
        "vod_name": title,
        "vod_pic": '',
        "vod_year": '',
        "vod_area": '',
        "vod_actor": '',
        "vod_director": '',
        "vod_content": '',
    }
    m = re.search(r'<img[^>]*data-original="([^"]+)"', html)
    if m:
        vod["vod_pic"] = _abs(m.group(1))
    m = re.search(r'<span class="data2">年份：</span>\s*([^<]+)', html)
    if m:
        vod["vod_year"] = m.group(1).strip()
    m = re.search(r'<span class="data2">国家：</span>\s*([^<]+)', html)
    if m:
        vod["vod_area"] = m.group(1).strip()
    m = re.search(r'<span class="data2">导演：</span>(.*?)</p>', html, re.S)
    if m:
        vod["vod_director"] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    m = re.search(r'<span class="left data2">主演：</span>(.*?)</span>', html, re.S)
    if m:
        vod["vod_actor"] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    m = re.search(r'<span class="detail-content"[^>]*>(.*?)</span>', html, re.S)
    if m:
        vod["vod_content"] = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    # 线路+剧集: <h4>...线路名...</h4><ul class="stui-content__playlist clearfix"><li><a href="/play/{vid}-{line}-{ep}.html">集名</a></li>
    groups = []
    for gm in re.finditer(
            r'<h4[^>]*>(.*?)</h4>\s*<ul class="stui-content__playlist[^"]*">(.*?)</ul>', html, re.S):
        line_name = re.sub(r'<[^>]+>', '', gm.group(1)).replace('&nbsp;', ' ').strip()
        items = []
        for am in re.finditer(r'href="(/play/%s-(\d+)-(\d+)\.html)"[^>]*>([^<]*)<' % vid, gm.group(2)):
            ep = am.group(3)
            ep_name = am.group(4).strip() or ep
            items.append('%s$%s-%s-%s' % (ep_name, vid, am.group(2), ep))
        if items:
            groups.append((line_name, items))
    if groups:
        vod["vod_play_from"] = '$$$'.join(g[0] for g in groups)
        vod["vod_play_url"] = '$$$'.join('#'.join(g[1]) for g in groups)
    else:
        vod["vod_play_from"] = '在线播放'
        vod["vod_play_url"] = '正片$%s-1-1' % vid
    return {"list": [vod]}


def search_content(key, quick=False, pg="1"):
    if not key:
        return {"list": [], "page": 1}
    url = '%s/search/%s-------------.html' % (_host(), urllib.parse.quote(key))
    html = _get(url, _host() + '/')
    vods = _parse_list(html)
    return {
        "list": vods,
        "page": 1,
        "pagecount": 1,
        "limit": 24,
        "total": len(vods),
    }


def play_parse(flag, id_, flags=None):
    pid = str(id_ or '').strip()
    hdr = json.dumps({"User-Agent": UA, "Referer": _host() + '/'}, ensure_ascii=False)
    m = re.fullmatch(r'(\d+)-(\d+)-(\d+)', pid)
    if not m:
        return {"parse": 0, "url": "", "header": hdr, "playUrl": ""}
    vid, line, ep = m.group(1), m.group(2), m.group(3)
    html = _get('%s/play/%s-%s-%s.html' % (_host(), vid, line, ep),
                '%s/detail/%s.html' % (_host(), vid), ttl=1800)
    url = ''
    mm = re.search(r'var player_data=(\{.*?\});', html, re.S)
    if mm:
        try:
            pd = json.loads(mm.group(1))
            url = pd.get('url') or ''
        except Exception:
            mm2 = re.search(r'"url"\s*:\s*"([^"]+)"', mm.group(1))
            if mm2:
                url = mm2.group(1)
    if url:
        url = url.replace('\\/', '/')
    return {"parse": 0, "url": url, "header": hdr, "playUrl": ""}


class Spider(_BaseSpider):
    def getName(self):
        return "影视天下"

    def init(self, extend=""):
        def warm():
            try:
                _get(_host() + '/type/1.html', _host() + '/', ttl=1800)
            except Exception:
                pass
        try:
            threading.Thread(target=warm, daemon=True).start()
        except Exception:
            pass
        self.site = HOSTS[0]

    def destroy(self):
        pass

    def homeContent(self, filter):
        try:
            return home_content(filter)
        except Exception as e:
            _log("homeContent异常", repr(e)[:100])
            return {"class": [], "filters": {}}

    def homeVideoContent(self):
        try:
            return home_video_content()
        except Exception as e:
            _log("homeVideoContent异常", repr(e)[:100])
            return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            return category_content(tid, pg, filter, extend)
        except Exception as e:
            _log("categoryContent异常", repr(e)[:100])
            return {"list": [], "page": 1, "pagecount": 1, "limit": 24, "total": 0}

    def searchContent(self, key, quick, pg="1"):
        try:
            return search_content(key, quick, pg)
        except Exception as e:
            _log("searchContent异常", repr(e)[:100])
            return {"list": [], "page": 1, "pagecount": 1, "limit": 24, "total": 0}

    def detailContent(self, array):
        try:
            return detail_content(array)
        except Exception as e:
            _log("detailContent异常", repr(e)[:100])
            return {"list": []}

    def playerContent(self, flag, id, vipFlags):
        try:
            return play_parse(flag, id)
        except Exception as e:
            _log("playerContent异常", repr(e)[:100])
            return {"parse": 0, "url": "", "playUrl": "", "header": ""}

    def isVideoFormat(self, url):
        return True

    def manualVideoCheck(self):
        return False


if __name__ == "__main__":
    print("影视天下爬虫 v1.0")
