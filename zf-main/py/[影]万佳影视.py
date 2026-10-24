# -*- coding: utf-8 -*-
# TVBox/影视仓 Python 爬虫 - 万佳影视 wjys.py
# 站点: https://www.wjys.cc/
# 模板: maccms V10 (自定义主题)
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

CACHE_TTL = 300
_HOST_CACHE = {"host": None, "ts": 0}
_REQ_CACHE = {}

UA = ('Mozilla/5.0 (Linux; Android 13; SM-S9180) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')

HOSTS = [
    "https://www.wjys.cc",
    "https://wjys.cc",
]

CATEGORIES = [
    {"type_id": "dy", "type_name": "电影"},
    {"type_id": "juji", "type_name": "剧集"},
    {"type_id": "zongyi", "type_name": "综艺"},
    {"type_id": "dongman", "type_name": "动漫"},
    {"type_id": "jilupian", "type_name": "纪录片"},
    {"type_id": "dj", "type_name": "短剧"},
]

_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _log(*args):
    try:
        print("[万佳影视]", *args)
    except Exception:
        pass


def _http_get(url, referer=None, timeout=12):
    headers = {'User-Agent': UA, 'Accept': 'text/html,*/*;q=0.8',
               'Accept-Language': 'zh-CN,zh;q=0.9', 'Accept-Encoding': 'gzip'}
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
            _log("GET失败(%d/2)" % (attempt + 1), url[:80], repr(e)[:60])
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

    def probe(h):
        try:
            html = _http_get(h + "/", timeout=6)
            if html and 'voddetail' in html:
                alive.append(h.rstrip('/'))
        except Exception:
            pass

    alive = []
    threads = [threading.Thread(target=probe, args=(h,), daemon=True) for h in HOSTS]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=8)
    host = alive[0] if alive else HOSTS[0].rstrip('/')
    _HOST_CACHE.update(host=host, ts=time.time() + 3600)
    return host


def _abs(u):
    if not u:
        return ''
    if u.startswith('//'):
        return 'https:' + u
    if u.startswith('http'):
        return u
    return _host() + u


def _fix_pic(u):
    if not u or u == '/':
        return ''
    return _abs(u)


def _parse_items(html):
    """列表条目: .module-item → voddetail/{id}.html + img + title"""
    vods = []
    seen = set()
    for m in re.finditer(r'<div class="module-item">(.*?)</div>\s*</div>\s*</div>', html, re.S):
        block = m.group(1)
        # 提取 vod_id
        link_m = re.search(r'/voddetail/(\d+)\.html', block)
        if not link_m:
            continue
        vid = link_m.group(1)
        if vid in seen:
            continue
        # 标题
        title = ''
        tm = re.search(r'title="([^"]+)"', block)
        if tm:
            title = tm.group(1).strip()
        else:
            tm = re.search(r'<img[^>]*alt="([^"]+)"', block)
            if tm:
                title = tm.group(1).strip()
        if not title:
            continue
        # 封面
        pic = ''
        pm = re.search(r'<img[^>]*src="([^"]+)"', block)
        if pm:
            pic = pm.group(1)
        seen.add(vid)
        vods.append({
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": _fix_pic(pic),
            "vod_remarks": '',
        })
    return vods


def _parse_detail(html):
    """详情页 → (vod, [{线名, urlstr}])"""
    # vod_id
    m = re.search(r'/voddetail/(\d+)\.html', html)
    vid = m.group(1) if m else ''
    # 标题: 优先 page-title-name
    title = ''
    m = re.search(r'<span class="page-title-name">([^<]+)</span>', html)
    if m:
        title = m.group(1).strip()
    else:
        m = re.search(r'<h1[^>]*>(.*?)</h1>', html, re.S)
        if m:
            title = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    if not title:
        tm = re.search(r'<title>([^<]+)</title>', html)
        if tm:
            title = re.sub(r'\d{4}年.*', '', tm.group(1)).strip()
    # 海报
    pic = ''
    m = re.search(r'<div class="module-item-pic[^"]*"[^>]*>\s*<img[^>]*src="([^"]+)"', html, re.S)
    if m:
        pic = m.group(1)
    # 简介
    desc = ''
    m = re.search(r'class="module-info-introduction[^"]*"[^>]*>(.*?)</div>', html, re.S)
    if m:
        desc = re.sub(r'<[^>]+>', '', m.group(1)).strip()
    # m3u8 直链
    m3u8 = ''
    m = re.search(r'(https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*)', html)
    if m:
        m3u8 = m.group(1)
    # 播放列表
    plays = []
    if m3u8:
        plays = [("在线播放", "正片$" + m3u8)]
    vod = {
        "vod_id": vid,
        "vod_name": title,
        "vod_pic": _fix_pic(pic),
        "type_name": '',
        "vod_year": '',
        "vod_area": '',
        "vod_remarks": '',
        "vod_director": '',
        "vod_actor": '',
        "vod_content": desc,
    }
    return vod, plays


def home_content(filter_=False):
    return {
        "class": [{"type_id": c["type_id"], "type_name": c["type_name"]} for c in CATEGORIES],
        "filters": {},
    }


def home_video_content():
    html = _get(_host() + '/', ttl=600)
    vods = _parse_items(html) if html else []
    return {"list": vods[:36]}


def category_content(tid, pg="1", filter_=None, extend=None):
    try:
        pg = int(pg)
    except Exception:
        pg = 1
    if pg < 1:
        pg = 1
    base = _host()
    if pg == 1:
        url = '%s/vodtype/%s.html' % (base, tid)
    else:
        url = '%s/vodtype/%s/page/%d.html' % (base, tid, pg)
    html = _get(url)
    vods = _parse_items(html) if html else []
    return {
        "list": vods,
        "page": pg,
        "pagecount": 9999 if vods else pg,
        "limit": 24,
        "total": 999999 if vods else 0,
    }


def detail_content(ids):
    if isinstance(ids, list):
        ids = ids[0]
    m = re.search(r'(\d+)', str(ids))
    if not m:
        return {"list": []}
    vid = m.group(1)
    url = '%s/voddetail/%s.html' % (_host(), vid)
    html = _get(url)
    if not html:
        return {"list": []}
    vod, plays = _parse_detail(html)
    if not vod["vod_name"]:
        return {"list": []}
    if plays:
        vod["vod_play_from"] = '$$$'.join(nm for nm, _ in plays)
        vod["vod_play_url"] = '$$$'.join(urls for _, urls in plays)
    return {"list": [vod]}


def search_content(key, quick=False, pg="1"):
    try:
        pg = int(pg)
    except Exception:
        pg = 1
    if not key or pg < 1:
        return {"list": [], "page": pg}
    wd = urllib.parse.quote(key)
    if pg == 1:
        url = '%s/vodsearch/wd/%s.html' % (_host(), wd)
    else:
        url = '%s/vodsearch/wd/%d/%s.html' % (_host(), pg, wd)
    html = _get(url)
    vods = _parse_items(html) if html else []
    return {
        "list": vods,
        "page": pg,
        "pagecount": 9999 if vods else pg,
        "limit": 24,
        "total": 999999 if vods else 0,
    }


def play_parse(flag, id_, flags=None):
    pid = str(id_ or '').strip()
    hdr = json.dumps({"User-Agent": UA, "Referer": _host() + '/'}, ensure_ascii=False)
    # pid 直接就是 m3u8 地址
    if pid.startswith('http') and '.m3u8' in pid:
        return {"parse": 0, "url": pid, "header": hdr, "playUrl": ""}
    return {"parse": 0, "url": pid, "header": hdr, "playUrl": ""}


class Spider(_BaseSpider):
    def getName(self):
        return "万佳影视"

    def init(self, extend=""):
        def warm():
            try:
                h = _host()
                _get(h + '/', ttl=600)
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
    print("万佳影视爬虫")
    print("测试: python wjys.py home|hot|cat|detail|search|play")
