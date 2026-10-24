# -*- coding: utf-8 -*-
# 悟空影视(ysx.ys098.top) OK影视/TVBox 采集源  —— 免登录版
# 协议: 请求/响应均为 AES-CBC(key=iv='ERDFCVWESDXCYUHJ', PKCS7) 加密后 base64, POST text/plain
# 请求头: user-agent=Dart/3.9 (dart:io)  xrequestkey=onecatmgys  src=1011  content-type=text/plain
#
# 该站无可用账号(登录接口返回"账号或密码错误"), 全程游客态(ui=0/ug=2)即可, 不调用登录接口。
# 其余全部动态获取(无写死兜底):
#   分类/筛选 : /api/v1/load/resource  (homeTopNavV2 / libraryNav / rankNav)
#   首页推荐 : /api/v3/render/render   (code 取自 homeTopNavV2)
#   分类浏览 : /api/v1/vod/library     (ptype + filter + page, 真分页)
#   搜索     : /api/v1/vod/search      (keyword + page)
#   详情     : /api/v3/vod/vodinfo
#   播放地址 : /api/v1/vod/analysis    (analysisList 取自详情线路, playurl = sourceUrl)
import json
import base64
import requests
from Crypto.Cipher import AES

from base.spider import Spider

AES_KEY = b"ERDFCVWESDXCYUHJ"

# 接口地址(可被 extend 覆盖: {"host": "http://xxx"})
API_BASE = "http://ysx.ys098.top"

# 接口路径
API = {
    "resource": "/api/v1/load/resource",
    "render": "/api/v3/render/render",
    "library": "/api/v1/vod/library",
    "search": "/api/v1/vod/search",
    "detail": "/api/v3/vod/vodinfo",
    "analysis": "/api/v1/vod/analysis",
}

# 资源键
RES_KEYS = ["homeTopNavV2", "libraryNav", "rankNav"]

# 客户端公共参数(游客态, 该站免登录)
PUBLIC = {
    "db": "flutter", "di": "flutter-device", "dm": "flutter", "dt": "app", "dp": 1,
    "pf": "android", "platform": "android", "st": "flutter", "on": "android",
    "ov": "", "ol": "", "la": "zh-Hans", "av": "1.2.0", "ac": "2008",
    "sw": 0, "sh": 0, "oi": "", "nt": "unknown", "ui": 0, "ug": 2,
}

# 筛选键显示名(服务端只返回 class/area/lang/year 键名)
FILTER_LABEL = {"class": "类型", "area": "地区", "lang": "语言", "year": "年份"}

PAGE_SIZE = 30


def _pad(data):
    pad = 16 - len(data) % 16
    return data + bytes([pad]) * pad


def _enc(obj):
    raw = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return base64.b64encode(AES.new(AES_KEY, AES.MODE_CBC, iv=AES_KEY).encrypt(_pad(raw))).decode()


def _dec(text):
    data = AES.new(AES_KEY, AES.MODE_CBC, iv=AES_KEY).decrypt(base64.b64decode(text.strip()))
    pad = data[-1]
    if 1 <= pad <= 16 and data[-pad:] == bytes([pad]) * pad:
        data = data[:-pad]
    return json.loads(data)


class Spider(Spider):
    def getName(self):
        return "悟空影视"

    def init(self, extend=""):
        super().init(extend)
        self.api_base = API_BASE
        if extend:
            try:
                cfg = json.loads(extend)
                if isinstance(cfg, dict) and cfg.get("host"):
                    self.api_base = str(cfg["host"]).strip().rstrip("/")
            except Exception:
                pass
        self.headers = {
            "user-agent": "Dart/3.9 (dart:io)",
            "xrequestkey": "onecatmgys",
            "src": "1011",
            "content-type": "text/plain",
        }
        self.sess = requests.Session()
        self.sess.headers.update(self.headers)
        self.res = None           # homeTopNavV2 / libraryNav / rankNav
        self.nav = []             # 首页导航 -> render code
        self.cates = []           # 分类 -> library ptype
        self.filters = {}         # ptype -> 筛选词表
        self.vod_cache = {}       # vod_id -> 详情(播放解析用)
        self.vod_order = []

    # ========== 请求 ==========
    def _api(self, path, body):
        """加密请求, 返回解密后的 JSON"""
        body = dict(body)
        body["public"] = PUBLIC
        try:
            res = self.sess.post(self.api_base + path, data=_enc(body), timeout=20, verify=False)
            if res.status_code != 200:
                return None
            return _dec(res.text)
        except Exception:
            return None

    # ========== 动态资源 ==========
    def _resource(self):
        """动态取分类/筛选(结果缓存)"""
        if self.res:
            return self.res
        ret = self._api(API["resource"], {"resource": RES_KEYS})
        data = (ret or {}).get("data") or {}
        if (ret or {}).get("code") != 0 or not data:
            return None
        self.res = data
        self.nav = data.get("homeTopNavV2") or []
        # 分类 = libraryNav(带筛选词表) + rankNav(补齐其它分类, 无筛选)
        libs = data.get("libraryNav") or []
        self.cates = []
        seen = set()
        for c in libs + (data.get("rankNav") or []):
            tid = str(c.get("id") or "")
            if not tid or tid in seen:
                continue
            seen.add(tid)
            self.cates.append(c)
        self.cates.sort(key=lambda c: int(c["id"]) if str(c.get("id")).isdigit() else 999)
        for c in libs:
            items = []
            for f in (c.get("filterItems") or []):
                key = f.get("name")
                vals = [x for x in str(f.get("value") or "").split(",") if x and x != "0"]
                if not key or not vals:
                    continue
                items.append({
                    "key": key,
                    "name": FILTER_LABEL.get(key, key),
                    "value": [{"n": "全部", "v": ""}] + [{"n": x, "v": x} for x in vals],
                })
            if items:
                self.filters[str(c.get("id"))] = items
        return self.res

    # ========== 首页分类 + 筛选 ==========
    def homeContent(self, filter):
        result = {"class": []}
        if not self._resource():
            return result
        result["class"] = [{"type_name": c.get("name", ""), "type_id": str(c.get("id"))}
                           for c in self.cates if c.get("id") is not None]
        if filter:
            result["filters"] = self.filters
        return result

    # ========== 首页推荐 ==========
    def homeVideoContent(self):
        if not self._resource():
            return {"list": []}
        home = min(self.nav, key=lambda x: x.get("page", 999)) if self.nav else None
        if not home:
            return {"list": []}
        ret = self._api(API["render"], {"code": home.get("code")})
        video_list, seen = [], set()
        if ret and ret.get("code") == 0:
            for comp in ((ret.get("data") or {}).get("components") or []):
                for d in (comp.get("datas") or []):
                    vid = str(d.get("vod_id", ""))
                    if vid and vid not in seen:
                        seen.add(vid)
                        video_list.append(self._vod_item(d))
        return {"list": video_list}

    # ========== 分类列表(分页 + 筛选) ==========
    def categoryContent(self, tid, pg, filter, extend):
        pg = int(pg) if str(pg).isdigit() else 1
        self._resource()
        f = {}
        if extend:
            for k in self.filters.get(str(tid), []):
                v = extend.get(k["key"])
                if v:
                    f[k["key"]] = v
        body = {"ptype": int(tid) if str(tid).isdigit() else tid,
                "filter": f, "page": pg, "limit": PAGE_SIZE}
        ret = self._api(API["library"], body)
        video_list = []
        if ret and ret.get("code") == 0:
            for d in (ret.get("data") or []):
                video_list.append(self._vod_item(d))
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pg + 1 if len(video_list) >= PAGE_SIZE else pg,
            "limit": PAGE_SIZE,
            "total": len(video_list),
        }

    # ========== 详情 ==========
    def detailContent(self, ids):
        vod_id = ids[0] if ids else ""
        if not vod_id:
            return {"list": []}
        ret = self._api(API["detail"], {"vod": int(vod_id) if str(vod_id).isdigit() else vod_id})
        if not ret or ret.get("code") != 0:
            return {"list": []}
        d = ret.get("data") or {}
        self._cache_vod(str(vod_id), d)
        play_from, play_url = self._build_plays(d)
        return {"list": [{
            "vod_id": str(d.get("vod_id", vod_id)),
            "vod_name": d.get("vod_name", ""),
            "vod_pic": d.get("vod_pic", ""),
            "type_name": d.get("type_name", ""),
            "vod_actor": d.get("vod_actor", ""),
            "vod_director": d.get("vod_director", ""),
            "vod_area": d.get("vod_area", ""),
            "vod_lang": d.get("vod_lang", ""),
            "vod_year": d.get("vod_year", ""),
            "vod_remarks": d.get("vod_remarks", ""),
            "vod_score": d.get("vod_score", ""),
            "vod_content": d.get("vod_content") or d.get("vod_blurb", ""),
            "vod_play_from": play_from,
            "vod_play_url": play_url,
        }]}

    def _cache_vod(self, vod_id, data):
        self.vod_cache[vod_id] = data
        if vod_id in self.vod_order:
            self.vod_order.remove(vod_id)
        self.vod_order.append(vod_id)
        while len(self.vod_order) > 20:
            self.vod_cache.pop(self.vod_order.pop(0), None)

    def _build_plays(self, d):
        """每集写入 token(vod_id + 线路索引 + 集索引), 播放时再动态解析"""
        vod_id = str(d.get("vod_id", ""))
        froms, urls = [], []
        for li, line in enumerate(d.get("vod_all_play_list") or []):
            if not isinstance(line, dict):
                continue
            eps = line.get("play_list") or []
            if not eps:
                continue
            name = str(line.get("name") or line.get("cms_play_from") or "")
            if name in froms:      # 同名线路(如两条"主线路")加 cms 标识区分
                name = "%s(%s)" % (name, line.get("cms_play_from") or li)
            froms.append(name)
            items = []
            for ei, e in enumerate(eps):
                if not isinstance(e, dict) or not e.get("sourceUrl"):
                    continue
                token = base64.urlsafe_b64encode(
                    json.dumps({"v": vod_id, "l": li, "e": ei}, separators=(",", ":")).encode()
                ).decode()
                items.append("%s$%s" % (e.get("name") or e.get("title") or str(ei + 1), token))
            urls.append("#".join(items))
        return "$$$".join(froms), "$$$".join(urls)

    # ========== 搜索 ==========
    def searchContent(self, key, quick, pg=1):
        pg = int(pg) if str(pg).isdigit() else 1
        ret = self._api(API["search"], {"keyword": key, "page": pg, "limit": PAGE_SIZE})
        video_list = []
        if ret and ret.get("code") == 0:
            for d in (ret.get("data") or []):
                video_list.append(self._vod_item(d))
        return {
            "list": video_list,
            "page": pg,
            "pagecount": pg + 1 if len(video_list) >= PAGE_SIZE else pg,
            "limit": PAGE_SIZE,
            "total": len(video_list),
        }

    # ========== 播放 ==========
    def playerContent(self, flag, id, vipFlags):
        token = id.split("$")[-1] if "$" in id else id
        try:
            t = json.loads(base64.urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode())
        except Exception:
            return {"parse": 0, "url": "", "header": {}}
        data = self.vod_cache.get(str(t.get("v")))
        if data is None:
            ret = self._api(API["detail"], {"vod": t.get("v")})
            if not ret or ret.get("code") != 0:
                return {"parse": 0, "url": "", "header": {}}
            data = ret.get("data") or {}
            self._cache_vod(str(t.get("v")), data)
        try:
            line = (data.get("vod_all_play_list") or [])[int(t.get("l"))]
            ep = (line.get("play_list") or [])[int(t.get("e"))]
        except Exception:
            return {"parse": 0, "url": "", "header": {}}
        ret = self._api(API["analysis"], {
            "analysisList": line.get("analysis") or [],
            "playurl": ep.get("sourceUrl"),
        })
        url = ((ret or {}).get("data") or {}).get("url") or ""
        return {"parse": 0, "url": url, "header": ep.get("headers") or {}}

    def _vod_item(self, d):
        return {
            "vod_id": str(d.get("vod_id", "")),
            "vod_name": d.get("vod_name", ""),
            "vod_pic": d.get("vod_pic", ""),
            "vod_remarks": d.get("vod_remarks", ""),
        }


if __name__ == "__main__":
    print("Spider module loaded:", __file__)
