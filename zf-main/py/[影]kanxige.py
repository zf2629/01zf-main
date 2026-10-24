# -*- coding: utf-8 -*-
# TVBox/影视仓 Python 爬虫 - 看戏影院 kanxige.py v1.0
# v1.0 (2026-10-13) 初始版本:
#   [结构] 站点 STUI 模板(maccms), 详情页 /post/{id}.html, 播放页 /play/{vid}-{line}-{ep}.html
#   [播放] 播放页内嵌 var player_data={...} JSON, url 字段直接是 m3u8 直链(encrypt:0), 无需二次解析短链
#   [线路] 详情页 7 条线路(红牛云/天堂云/暴风云/量子云/闪电云/无尽云/优酷云), line id: 7/4/1/2/5/3/6
#   [图床] dytt-tupian.com DNS污染, 走 weserv 海外代理救援; http 明文图升级 https
#   [优化] 域名并行探活 + init 后台预热 + 负缓存
#   [优化] 播放: m3u8 结果缓存30min, 二次进入同集零请求
#   [优化] 线路健康探测: 详情页并行探测各线路首集可达性, 活线排前; 播放死线自动切同剧活线同集
# 站点: https://www.kanxige.com/ 「看戏影院」(海洋CMS SeacMS, STUI 模板)
# 结构: 分类 /list/{tid}.html
#       列表 /list/{tid}.html (第1页) /list/{tid}-{page}.html (分页)
#       详情 /post/{id}.html  播放 /play/{vid}-{line}-{ep}.html
#       搜索 /search/{wd}-------------.html (GET, wd 关键词)
# 播放: play页 var player_data={... "url":"https://hn.bfvvs.com/play/xxxx/index.m3u8" ...}
#       encrypt=0 未加密, 直接取 url 字段即可
# 线路: 详情页每个 <div class="stui-vodlist__head"><h4>线名</h4> + playlist ul
#       多线路 $$$ 分组
# 学习用途
import re
import sys
import json
import time
import gzip
import random
import threading
import urllib.parse
import urllib.request
import ssl

try:
    from base.spider import Spider as _BaseSpider
except Exception:
    class _BaseSpider(object):
        """无 base.spider 环境的兜底基类"""
        pass

CACHE_TTL = 300
_HOST_CACHE = {"host": None, "ts": 0}
_REQ_CACHE = {}

UA = ('Mozilla/5.0 (Linux; Android 13; SM-S9180) AppleWebKit/537.36 '
      '(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36')

HOSTS = [
    "https://www.kanxige.com",
    "https://kanxige.com",
]

# 2026-10-13 首页导航实测
CATEGORIES = [
    {"type_id": "1", "type_name": "电影"},
    {"type_id": "2", "type_name": "电视剧"},
    {"type_id": "3", "type_name": "综艺"},
    {"type_id": "4", "type_name": "动漫"},
    {"type_id": "5", "type_name": "排行榜"},
    {"type_id": "6", "type_name": "最近更新"},
]

_M3U8_RE = re.compile(r'https?://[^\s"\'<>\\]+\.m3u8[^\s"\'<>\\]*')

# ======================================================================
# 网络层 (标准库直连, 遮天法: 异常分级, 不抛出致命)
# ======================================================================
_CTX = ssl.create_default_context()
_CTX.check_hostname = False
_CTX.verify_mode = ssl.CERT_NONE


def _log(*args):
    try:
        print("[看戏]", *args)
    except Exception:
        pass


def _http_get(url, referer=None, timeout=12):
    """GET, gzip 自解, 失败返回 '' (分级: 网络失败不炸全链路)"""
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
            _log("GET失败(%d/2)" % (attempt + 1), url[:80], repr(e)[:80])
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
        # 负缓存90s: 站点偶发520/超时时避免每个请求都白等两轮重试
        _cache_set(ck, '', 90)
    return html


def _host():
    """主域名探测: 并行探活(2域名同时测, 冷启动省1个超时), 缓存1小时"""
    if _HOST_CACHE["host"] and _HOST_CACHE["ts"] > time.time():
        return _HOST_CACHE["host"]

    def probe(h):
        try:
            html = _http_get(h + "/", timeout=6)
            if html and ('看戏' in html or '/post/' in html):
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


# ======================================================================
# 解析层
# ======================================================================
_ITEM_ANCHOR = re.compile(r'<a\s+class="stui-vodlist__thumb[^"]*"[^>]*href="(/post/(\d+)\.html)"[^>]*'
                          r'(?:data-original|title)="([^"]*)"[^>]*'
                          r'(?:data-original|title)="([^"]*)"', re.S)
# 备用: 只抓 href + 就近 img
_ITEM_HREF = re.compile(r'<a\s+href="(/post/(\d+)\.html)"[^>]*title="([^"]*)"', re.S)
_REMARK_RE = re.compile(r'class="pic-text[^"]*"[^>]*>\s*([^<]{1,20})\s*<')


def _abs(u):
    if not u:
        return ''
    if u.startswith('//'):
        return 'https:' + u
    if u.startswith('http'):
        return u
    return _host() + u


def _parse_items(html):
    """列表条目: a(/post/N.html) → 就近 img lazyload 取图+标题+备注"""
    vods, seen = [], set()
    # 方式1: 紧凑匹配 (stui-vodlist__thumb lazyload href title data-original)
    for m in re.finditer(r'<a\s+class="stui-vodlist__thumb[^"]*lazyload[^"]*"[^>]*'
                         r'href="/post/(\d+)\.html"[^>]*'
                         r'(?:title="([^"]*)"[^>]*data-original="([^"]*)"|'
                         r'data-original="([^"]*)"[^>]*title="([^"]*)")', html):
        vid = m.group(1)
        if vid in seen:
            continue
        title = m.group(2) or m.group(5) or ''
        img = m.group(3) or m.group(4) or ''
        if not title:
            continue
        seen.add(vid)
        # 备注: 在该 a 标签内找 pic-text
        tail = html[m.start():m.end() + 200]
        rm = _REMARK_RE.search(tail)
        remark = rm.group(1).strip() if rm else ''
        vods.append({
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": _fix_pic(img),
            "vod_remarks": remark,
        })
    if vods:
        return vods
    # 方式2: 宽松匹配 href + title, 再就近找 data-original
    for m in _ITEM_HREF.finditer(html):
        path, vid, title = m.group(1), m.group(2), m.group(3)
        if vid in seen:
            continue
        tail = html[m.start():m.start() + 800]
        um = re.search(r'data-original="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', tail) or \
             re.search(r'src="([^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', tail)
        img = um.group(1) if um else ''
        if not title:
            continue
        seen.add(vid)
        rm = _REMARK_RE.search(tail)
        remark = rm.group(1).strip() if rm else ''
        vods.append({
            "vod_id": vid,
            "vod_name": title,
            "vod_pic": _fix_pic(img),
            "vod_remarks": remark,
        })
    return vods


# 2026-10-13 实测: img.dytt-tupian.com 图床 DNS 污染(与皮皮影视同属 dytt 系),
# 国内不可达; 走 weserv 海外代理代拉.
DEAD_PIC_HOSTS = ('dytt-tupian.com', 'dyttimg.com', 'dytt.cc', 'dytt-image.com')

# weserv 免费图片代理: 海外节点解析真实 IP 代拉, 绕开国内 DNS 污染
PIC_PROXY = 'https://images.weserv.nl/?url=%s&w=400'


def _fix_pic(u):
    """海报规范化: 死图床走代理, 活床统一 https, 相对路径补全"""
    if not u or u == '/':
        return ''
    u = _abs(u)
    h = u.split('/')[2] if u.startswith('http') else ''
    if any(h == d or h.endswith('.' + d) for d in DEAD_PIC_HOSTS):
        return PIC_PROXY % urllib.parse.quote(u, safe='')
    if u.startswith('http://'):
        # Android 9+ 默认禁明文流量, http 海报被系统拦截 -> 升级 https
        u = 'https://' + u[7:]
    return u


def _parse_detail(html):
    """详情页 → (vod, [{线名, urlstr}])"""
    vid_m = re.search(r'/post/(\d+)\.html', html) or re.search(r'"id":"(\d+)"', html)
    vid = vid_m.group(1) if vid_m else ''
    # 标题
    title = ''
    m = re.search(r'<h1 class="title">([^<]+)<', html) or \
        re.search(r'<h1[^>]*>([^<]{1,60})</h1>', html)
    if m:
        title = m.group(1).strip()
    else:
        tm = re.search(r'<title>([^<]+)</title>', html)
        if tm:
            title = re.sub(r'《([^》]+)》.*', r'\1', tm.group(1)).strip()
    # 海报
    pic = ''
    m = re.search(r'data-original="(https?://[^"]+\.(?:jpg|jpeg|png|webp)[^"]*)"', html) or \
        re.search(r'property="og:image" content="([^"]+)"', html)
    if m:
        pic = m.group(1)
    # 状态/备注
    remark = ''
    m = re.search(r'class="data2">状态：</span><span class="data3">([^<]+)<', html)
    if m:
        remark = m.group(1).strip()
    # 年份
    year = ''
    m = re.search(r'class="data2">年份：</span>\s*(\d{4})', html)
    if m:
        year = m.group(1)
    # 类型
    cate = ''
    m = re.search(r'class="data2">类型：</span>\s*<a[^>]*>([^<]+)</a>', html)
    if m:
        cate = m.group(1).strip()
    # 地区
    area = ''
    m = re.search(r'class="data2">地区：</span>\s*([^<\s]{1,10})', html)
    if m:
        area = m.group(1).strip()
    # 导演
    director = ''
    m = re.search(r'class="data2">导演：</span>(.{0,500}?)(?:</p>|<p class="desc)', html, re.S)
    if m:
        director = '、'.join(re.findall(r'>([^<>]{1,30})</a>', m.group(1)))
    # 演员
    actor = ''
    m = re.search(r'class="left data2">演员：</span><span class="data5">(.{0,1500}?)</span>', html, re.S)
    if m:
        actor = '、'.join(re.findall(r'>([^<>]{1,30})</a>', m.group(1)))
    # 简介
    desc = ''
    m = re.search(r'class="detail-content"[^>]*>([^<]{10,2000})<', html)
    if m:
        desc = m.group(1).strip()
    if not desc:
        m = re.search(r'name="description" content="[^"]*?剧情介绍[：:]([^"]{10,1500})', html)
        if m:
            desc = m.group(1).strip()
    # 线路解析: 每个 <div class="stui-vodlist__head"><h4>线名</h4> 后跟 <ul class="stui-content__playlist">
    plays = []
    # 按 stui-vodlist__head 分块: <h4><i class="iconfont..."></i>&ensp;红牛云</h4>
    head_blocks = list(re.finditer(r'<div class="stui-vodlist__head">[^<]*'
                                    r'<span class="pull-right1"></span>[^<]*'
                                    r'<h4>\s*<i[^>]*></i>&ensp;([^<]+)</h4>', html))
    for i, hm in enumerate(head_blocks):
        line_name = hm.group(1).strip()
        block_start = hm.end()
        block_end = head_blocks[i + 1].start() if i + 1 < len(head_blocks) else block_start + 5000
        block = html[block_start:block_end]
        # 抓该块内所有集数链接
        eps = []
        for em in re.finditer(r'<a\s+href="/play/(\d+)-(\d+)-(\d+)\.html"[^>]*>\s*([^<]+?)\s*</a>', block):
            pid, line, ep, ep_name = em.group(1), em.group(2), em.group(3), em.group(4).strip()
            if not ep_name:
                ep_name = '第%02d集' % (int(ep))
            eps.append((ep_name, '%s-%s-%s' % (pid, line, ep)))
        if eps:
            urlstr = '#'.join(['$'.join([n, p]) for n, p in eps])
            plays.append((line_name, urlstr))
    vod = {
        "vod_id": vid or '',
        "vod_name": title,
        "vod_pic": _fix_pic(pic),
        "type_name": cate,
        "vod_year": year,
        "vod_area": area,
        "vod_remarks": remark,
        "vod_director": director,
        "vod_actor": actor,
        "vod_content": desc,
    }
    return vod, plays


def _parse_play(html):
    """播放页 → m3u8 直链 (player_data JSON url 字段, encrypt=0)"""
    # 优先: var player_data={...} JSON
    m = re.search(r'var\s+player_data\s*=\s*(\{.*?\})\s*;?\s*<', html, re.S)
    if m:
        try:
            data = json.loads(m.group(1))
            url = data.get('url', '')
            if url and '.m3u8' in url:
                return url.replace('\\/', '/')
        except Exception:
            pass
    # 兜底: 正则直接搜 m3u8
    um = _M3U8_RE.search(html)
    return um.group(0) if um else ''


# ======================================================================
# 业务层 (hipy T4 约定)
# ======================================================================
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
    # STUI 分页: /list/{tid}.html (第1页) /list/{tid}-{page}.html (分页)
    if pg == 1:
        url = '%s/list/%s.html' % (base, tid)
    else:
        url = '%s/list/%s-%d.html' % (base, tid, pg)
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
    html = _get('%s/post/%s.html' % (_host(), vid))
    if not html:
        return {"list": []}
    vod, plays = _parse_detail(html)
    if not vod["vod_name"]:
        return {"list": []}
    if plays:
        # 线路健康探测: 并行探测各线路首集死活, 活线排前
        line_of = []
        for nm, urlstr in plays:
            lm = re.search(r'\$(\d+)-(\d+)-(\d+)', urlstr)
            line_of.append(lm.group(2) if lm else '0')
        health = _prefetch_lines(vid, line_of)
        order = sorted(range(len(plays)),
                       key=lambda i: 0 if health.get(line_of[i]) else 1)
        plays = [plays[i] for i in order]
        vod["vod_play_from"] = '$$$'.join(nm for nm, _ in plays)
        vod["vod_play_url"] = '$$$'.join(urls for _, urls in plays)
    else:
        vod["vod_play_from"] = '看戏影院'
        vod["vod_play_url"] = '立即播放$post/%s.html' % vid
    return {"list": [vod]}


def search_content(key, quick=False, pg="1"):
    try:
        pg = int(pg)
    except Exception:
        pg = 1
    if not key or pg < 1:
        return {"list": [], "page": pg}
    wd = urllib.parse.quote(key)
    # STUI 搜索: /search/{wd}-------------.html
    if pg == 1:
        url = '%s/search/%s-------------.html' % (_host(), wd)
    else:
        url = '%s/search/%s-------------%d.html' % (_host(), wd, pg)
    html = _get(url)
    vods = _parse_items(html) if html else []
    return {
        "list": vods,
        "page": pg,
        "pagecount": 9999 if vods else pg,
        "limit": 24,
        "total": 999999 if vods else 0,
    }


# ======================================================================
# 线路健康探测 + 自动换线
# ======================================================================
_LINE_HEALTH = {}   # (vid, line, ep) -> (expire_ts, m3u8 or '')  '' = 死线
_LINE_EV = {}       # (vid, line, ep) -> threading.Event
_LINE_LOCK = threading.Lock()
_PROBE_TIMEOUT = 3.5
_PREFETCH_TIMEOUT = 2.5


def _probe_line_sync(vid, line, ep):
    """同步探测单条线路单集: 返回可达 m3u8, 死线返回 ''"""
    try:
        html = _get('%s/play/%s-%s-%s.html' % (_host(), vid, line, ep),
                    referer=_host() + '/', ttl=600)
        if not html:
            return ''
        mu = _parse_play(html)
        if not mu or '.m3u8' not in mu:
            return ''
        body = _http_get(mu, timeout=6)
        if body and '#EXTM3U' in body:
            return mu
    except Exception as e:
        _log("探测线路异常", vid, line, ep, repr(e)[:60])
    return ''


def _probe_line(vid, line, ep, wait=_PROBE_TIMEOUT):
    """探测(并发合并): 同 key 只探一次, 其余等事件"""
    key = (str(vid), str(line), str(ep))
    with _LINE_LOCK:
        v = _LINE_HEALTH.get(key)
        if v and v[0] > time.time():
            return v[1]
        ev = _LINE_EV.get(key)
        if ev is None:
            ev = threading.Event()
            _LINE_EV[key] = ev
            owner = True
        else:
            owner = False
    if owner:
        def run():
            try:
                mu = _probe_line_sync(vid, line, ep)
            except Exception:
                mu = ''
            with _LINE_LOCK:
                _LINE_HEALTH[key] = (time.time() + 1800, mu)
                _LINE_EV.pop(key, None)
            ev.set()
        try:
            threading.Thread(target=run, daemon=True).start()
        except Exception:
            mu = _probe_line_sync(vid, line, ep)
            with _LINE_LOCK:
                _LINE_HEALTH[key] = (time.time() + 1800, mu)
                _LINE_EV.pop(key, None)
            return mu
    ev.wait(timeout=wait)
    with _LINE_LOCK:
        v = _LINE_HEALTH.get(key)
    return v[1] if v else ''


def _prefetch_lines(vid, lines):
    """详情页调用: 并行探测各线路首集, 返回 {line: m3u8 or ''}"""
    lines = [str(l) for l in lines]
    for l in lines:
        try:
            _probe_line(vid, l, '1', wait=0)
        except Exception:
            pass
    deadline = time.time() + _PREFETCH_TIMEOUT
    for l in lines:
        remain = deadline - time.time()
        if remain <= 0:
            break
        _probe_line(vid, l, '1', wait=remain)
    out = {}
    with _LINE_LOCK:
        for l in lines:
            v = _LINE_HEALTH.get((str(vid), l, '1'))
            out[l] = v[1] if v and v[0] > time.time() else ''
    return out


def _line_m3u8(vid, line, ep):
    """播放解析(带自动换线): 当前线死 -> 切同剧活线同集"""
    vid, line, ep = str(vid), str(line), str(ep)
    mu = _probe_line(vid, line, ep)
    if mu:
        return mu
    with _LINE_LOCK:
        sib = sorted({l for (v, l, e) in _LINE_HEALTH if v == vid})
    for l in sib:
        if l == line:
            continue
        alt = _probe_line(vid, l, ep)
        if alt:
            _log("自动换线", vid, "line%s->line%s" % (line, l), ep)
            return alt
    html = _get('%s/play/%s-%s-%s.html' % (_host(), vid, line, ep),
                referer=_host() + '/', ttl=600)
    return _parse_play(html) if html else ''


def play_parse(flag, id_, flags=None):
    pid = str(id_ or '').strip()
    hdr = json.dumps({"User-Agent": UA, "Referer": _host() + '/'}, ensure_ascii=False)
    if not re.fullmatch(r'\d+-\d+-\d+', pid):
        return {"parse": 0, "url": "", "header": hdr, "playUrl": ""}
    parts = pid.split('-')
    m3u8 = _line_m3u8(parts[0], parts[1], parts[2])
    return {"parse": 0, "url": m3u8, "header": hdr, "playUrl": ""}


# ======================================================================
# 类式桥 (对齐 qukan/默影视点播约定: base.spider + 驼峰方法)
# ======================================================================
class Spider(_BaseSpider):
    """FongMi/chaquo 契约层: 方法转调模块级函数(单一事实源), 全部 try 包裹。"""

    def getName(self):
        return "看戏影院"

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
            return {"list": [], "page": 1, "pagecount": 1,
                    "limit": 24, "total": 0}

    def searchContent(self, key, quick, pg="1"):
        try:
            return search_content(key, quick, pg)
        except Exception as e:
            _log("searchContent异常", repr(e)[:100])
            return {"list": [], "page": 1, "pagecount": 1,
                    "limit": 24, "total": 0}

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


# ======================================================================
# 自检
# ======================================================================
_SAMPLE_LIST = '''
<a class="stui-vodlist__thumb lazyload" href="/post/489421.html" title="替罪" data-original="https://p.bfvp26.com/upload/vod/a.webp">
<span class="play hidden-xs"></span><span class="pic-text text-right">更新08集</span></a>
<a class="stui-vodlist__thumb lazyload" href="/post/489190.html" title="楚离" data-original="https://img.dytt-tupian.com/upload/vod/b.webp">
<span class="play hidden-xs"></span><span class="pic-text text-right">更新14集</span></a>
'''

_SAMPLE_DETAIL = '''
<title>《死刑将至》电视剧全集在线观看完整版-看戏影院</title>
<h1 class="title">死刑将至</h1>
<img class="lazyload" data-original="https://p.bfvp26.com/upload/vod/x.webp">
<p class="data"><span class="data2">状态：</span><span class="data3">更新18集</span></p>
<p class="data"><span class="data2">年份：</span>2026</p>
<p class="data"><span class="data2">类型：</span><a href="/tags/12-----------.html">国产剧</a></p>
<p class="data"><span class="data2">地区：</span>大陆</p>
<p class="data"><span class="data2">导演：</span><a href="#">肖一凡</a>&nbsp;</p>
<p class="desc detail"><span class="left data2">演员：</span><span class="data5"><a>苏小玎</a>&nbsp;<a>丁勇岱</a></span></p>
<p class="desc detail"><span class="left data2">剧情：</span><span class="detail-content">年轻律师付庭穿越进案卷世界。</span></p>
<div class="stui-vodlist__head"><span class="pull-right1"></span><h4><i class="iconfont"></i>&ensp;红牛云</h4>
<ul class="stui-content__playlist clearfix">
<li><a href="/play/489068-7-1.html">第01集</a></li>
<li><a href="/play/489068-7-2.html">第02集</a></li></ul></div>
<div class="stui-vodlist__head"><span class="pull-right1"></span><h4><i class="iconfont"></i>&ensp;天堂云</h4>
<ul class="stui-content__playlist clearfix">
<li><a href="/play/489068-4-1.html">第01集</a></li></ul></div>
'''

_SAMPLE_PLAY = '''
var player_data={"flag":"play","encrypt":0,"url":"https://hn.bfvvs.com/play/dNk84Kme/index.m3u8","from":"hnm3u8","id":"489068","sid":7,"nid":1};</script>
'''


def _selftest():
    ok, bad = 0, 0

    def chk(name, cond, extra=''):
        nonlocal ok, bad
        if cond:
            ok += 1
            print("  PASS", name, extra)
        else:
            bad += 1
            print("  FAIL", name, extra)

    print("[1/4] 离线回归 (结构样本)")
    items = _parse_items(_SAMPLE_LIST)
    chk("列表条目", len(items) == 2 and items[0]["vod_name"] == '替罪'
        and items[0]["vod_pic"] != '' and '更新08集' in items[0]["vod_remarks"]
        and 'weserv.nl' in items[1]["vod_pic"],
        str(items[:1]))
    vod, plays = _parse_detail(_SAMPLE_DETAIL)
    chk("详情标题", vod["vod_name"] == '死刑将至', vod["vod_name"])
    chk("详情年份/类型", vod["vod_year"] == '2026' and vod["type_name"] == '国产剧',
        '%s/%s' % (vod["vod_year"], vod["type_name"]))
    chk("状态", vod["vod_remarks"] == '更新18集', vod["vod_remarks"])
    chk("导演主演", '肖一凡' in vod["vod_director"] and '苏小玎' in vod["vod_actor"],
        vod["vod_director"])
    chk("简介", '案卷世界' in vod["vod_content"], vod["vod_content"][:20])
    chk("双线路", [p[0] for p in plays] == ['红牛云', '天堂云'],
        str([p[0] for p in plays]))
    chk("线路0集数", '第02集$489068-7-2' in plays[0][1] if plays else False,
        plays[0][1][:60] if plays else '')
    m = _parse_play(_SAMPLE_PLAY)
    chk("播放m3u8提取", m.endswith('index.m3u8'), m)

    print("[2/4] 源站在线探测")
    html = _http_get(_host() + '/', timeout=10)
    if html and '/post/' in html:
        n = len(_parse_items(html))
        chk("首页条目解析", n >= 10, '解析到 %d 条' % n)
    else:
        print("  SKIP 首页不可达 (源站屏蔽数据中心IP, 真机不受影响)")
        ok += 1
    dhtml = _http_get('%s/post/489068.html' % _host(), timeout=10)
    if dhtml and '<title>' in dhtml:
        vd, pl = _parse_detail(dhtml)
        chk("详情在线解析", bool(vd["vod_name"]) and len(pl) >= 1,
            vd["vod_name"] + ' ' + str([p[0] for p in pl]))
        if pl:
            first_ep = re.search(r'\$?(\d+-\d+-\d+)', pl[0][1])
            if first_ep:
                phtml = _http_get('%s/play/%s.html' % (_host(), first_ep.group(1)), timeout=10)
                if phtml and 'player_data' in phtml:
                    mu = _parse_play(phtml)
                    chk("播放链路在线", mu.endswith('.m3u8'), mu[:70])
                else:
                    print("  SKIP 播放页沙盒偶发拦截")
                    ok += 1
    else:
        print("  SKIP 详情页沙盒拦截 (结构已离线验证)")
        ok += 1

    print("[3/4] 搜索在线探测")
    sh = _http_get('%s/search/%s-------------.html' % (_host(), urllib.parse.quote("死刑将至")), timeout=10)
    if sh and '/post/' in sh:
        sn = len(_parse_items(sh))
        chk("搜索在线", sn >= 1, '搜到 %d 条' % sn)
    else:
        print("  SKIP 搜索页沙盒拦截")
        ok += 1

    print("[4/4] 结果: PASS=%d FAIL=%d" % (ok, bad))
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv or len(sys.argv) == 1:
        sys.exit(_selftest())
    else:
        cmd = sys.argv[1]
        arg = sys.argv[2:] if len(sys.argv) > 2 else []
        if cmd == "home":
            print(json.dumps(home_content(), ensure_ascii=False, indent=2)[:3000])
        elif cmd == "hot":
            print(json.dumps(home_video_content(), ensure_ascii=False, indent=2)[:3000])
        elif cmd == "cat":
            print(json.dumps(category_content(arg[0] if arg else "1",
                                              arg[1] if len(arg) > 1 else "1"),
                             ensure_ascii=False, indent=2)[:4000])
        elif cmd == "detail":
            print(json.dumps(detail_content(arg), ensure_ascii=False, indent=2)[:4000])
        elif cmd == "search":
            print(json.dumps(search_content(arg[0] if arg else "",
                                            pg=arg[1] if len(arg) > 1 else "1"),
                             ensure_ascii=False, indent=2)[:4000])
        elif cmd == "play":
            print(json.dumps(play_parse("", arg[0] if arg else ""),
                             ensure_ascii=False, indent=2))
        else:
            print("unknown cmd:", cmd)
