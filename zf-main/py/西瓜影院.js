import { Crypto, load, _ } from 'assets://js/lib/cat.js';

let siteUrl = 'https://jsntdl.com';
let siteKey = '';
let siteType = 0;
let headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36',
    'Referer': 'https://jsntdl.com/',
};

async function request(reqUrl, postData, get) {
    let res = await req(reqUrl, {
        method: get ? 'get' : 'post',
        headers: headers,
        data: postData || {},
        postType: get ? '' : 'form',
    });
    return res.content;
}

async function init(cfg) {
    siteKey = cfg.skey;
    siteType = cfg.stype;
}

async function home(filter) {
    let classes = [{
        type_id: '1',
        type_name: '电影',
    }, {
        type_id: '13',
        type_name: '电视剧',
    }, {
        type_id: '3',
        type_name: '综艺',
    }, {
        type_id: '4',
        type_name: '动漫',
    }, {
        type_id: '14',
        type_name: '短剧',
    }, {
        type_id: '15',
        type_name: 'B站',
    }];
    let filterObj = genFilterObj();
    return JSON.stringify({
        class: classes,
        filters: filterObj
    });
}

async function homeVod() {
    let videos = await getVideos(siteUrl);
    return JSON.stringify({ list: videos });
}

async function category(tid, pg, filter, extend) {
    try {
        extend = extend || {};
        let api = siteUrl + '/index.php/api/vod';
        let type = extend['id'] || tid;
        let page = parseInt(pg || 1);

        let t = Math.round(Date.now() / 1e3).toString();
        let key = Crypto.MD5('DS' + t + 'DCC147D11943AF75').toString();

        let postData = {
            type: String(type),
            class: extend['class'] || '',
            area: extend['area'] || '',
            lang: extend['lang'] || '',
            version: '',
            state: '',
            letter: '',
            year: extend['year'] || '',
            page: String(page),
            time: t,
            key: key,
        };

        let res = await req(api, {
            method: 'post',
            headers: {
                'User-Agent': headers['User-Agent'],
                'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': siteUrl + '/',
                'Origin': siteUrl,
            },
            data: postData,
            postType: 'form',
        });

        let data = JSON.parse(res.content || '{}');
        let videos = _.map(data.list || [], function(it) {
            return {
                vod_id: '/xgdetail/' + it.vod_id + '.html',
                vod_name: it.vod_name,
                vod_pic: it.vod_pic || '',
                vod_remarks: it.vod_remarks || '',
            };
        });

        return JSON.stringify({
            page: parseInt(data.page || page),
            pagecount: parseInt(data.pagecount || 1),
            limit: parseInt(data.limit || 20),
            total: parseInt(data.total || 0),
            list: videos,
        });
    } catch (e) {
        return JSON.stringify({
            page: 1,
            pagecount: 1,
            limit: 20,
            total: 0,
            list: [],
        });
    }
}

async function detail(id) {
    try {
        let url = siteUrl + id;
        const html = await request(url, null, true);
        const $ = load(html);

        let title = $('h3.slide-info-title').text().trim();
        let content = $('div#height_limit').text().trim();

        let director = '';
        let actor = '';
        let remarks = '';
        let year = '';
        let vodType = '';
        $('.slide-info-remarks a').each(function() {
            let href = $(this).attr('href') || '';
            let text = $(this).text().trim();
            if (href.includes('-------------') && /\d{4}/.test(href)) {
                year = text;
            } else if (href.includes('xiguasp')) {
                vodType = text;
            }
        });
      
        $('div.slide-info').each(function(i, n) {
            let label = $(n).find('strong').text();
            if (label.indexOf('导演') > -1) {
                director = _.map($(n).find('a'), function(a) {
                    return $(a).text().trim();
                }).join(' ');
            } else if (label.indexOf('演员') > -1) {
                actor = _.map($(n).find('a'), function(a) {
                    return $(a).text().trim();
                }).join(' ');
            } else if (label.indexOf('备注') > -1) {
                remarks = $(n).text().replace(/备注\s*[:：]/, '').trim();
            }
        });

        const sourceTabs = $('div.anthology-tab a.swiper-slide');
        const playLists = $('ul.anthology-list-play');

        let playFromList = [];
        let playUrlList = [];

        playLists.each(function(i, ul) {
            let tabName = '';
            if (sourceTabs.length > i) {
                tabName = $(sourceTabs[i]).clone().children().remove().end().text().trim();
                if (!tabName) {
                    tabName = $(sourceTabs[i]).text().trim();
                }
            }
            playFromList.push(tabName || ('线路' + (i + 1)));

            let eps = [];
            $(ul).find('li > a').each(function(j, a) {
                let name = $(a).text().trim();
                let href = $(a).attr('href') || '';
                if (href) {
                    eps.push(name + '$' + href);
                }
            });
            playUrlList.push(eps.join('#'));
        });

        if (playFromList.length === 0) {
            playFromList.push('西瓜影院');
            let cards = $('ul.anthology-list-play > li > a');
            let eps = _.map(cards, function(n) {
                return $(n).text().trim() + '$' + ($(n).attr('href') || '');
            });
            playUrlList.push(eps.join('#'));
        }

        let playFrom = playFromList.join('$$$');
        let playUrl = playUrlList.join('$$$');

        const video = {
            vod_name: title,
            vod_actor: actor,
            vod_director: director,
            vod_content: content,
            vod_remarks: remarks,
          	vod_year: year,        // 新增
    		type_name: vodType,
            vod_play_from: playFrom,
            vod_play_url: playUrl,
        };
        return JSON.stringify({ list: [video] });
    } catch (e) {
    }
    return null;
}

async function play(flag, id, flags) {
    try {
        let playPageUrl = siteUrl + id;
        const html = await request(playPageUrl, null, true);
        const $ = load(html);

        let info = '';
        for (const n of $('script')) {
            let text = $(n).text();
            let pos = text.indexOf('player_aaaa=');
            if (pos > -1) {
                info = text.substring(pos + 'player_aaaa='.length);
                let start = info.indexOf('{');
                let end = info.lastIndexOf('}');
                if (start > -1 && end > start) {
                    info = info.substring(start, end + 1);
                }
                break;
            }
        }
        let obj = JSON.parse(info);

        let playUrl = obj.url || '';
        let enc = String(obj.encrypt);
        if (enc == '1') {
            playUrl = unescape(playUrl);
        } else if (enc == '2') {
            playUrl = unescape(base64Decode(playUrl));
        }

        // 媒体直链直接播放；平台页面等地址走 getdate 解析 + AES 解密拿真实地址
        if (/\.(m3u8|mp4|flv|ts|mpd)(\?|#|$)/i.test(playUrl)) {
            return JSON.stringify({
                parse: 0,
                url: playUrl,
            });
        }

        let real = await getPlayUrl(obj, playPageUrl);
        if (real && real.videoUrl) {
            return JSON.stringify({
                parse: 0,
                url: real.videoUrl,
            });
        }

        return JSON.stringify({
            parse: 0,
            url: playUrl,
        });
    } catch (e) {
    }
    return null;
}

async function getPlayUrl(obj, playPageUrl) {
    let apiUrl = siteUrl + '/static/player/artplayer/api.php?ac=getdate';
    let postData = {
        url: obj.url,
        type: 'mp4',
        name: obj.vod_data ? obj.vod_data.vod_name : '',
        id: String(obj.id),
        sid: String(obj.sid),
        nid: String(obj.nid),
        referer: playPageUrl,
    };

    let res = await req(apiUrl, {
        method: 'post',
        headers: {
            'User-Agent': headers['User-Agent'],
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
            'X-Requested-With': 'XMLHttpRequest',
            'Referer': playPageUrl,
            'Origin': siteUrl,
        },
        data: postData,
        postType: 'form',
    });

    let resp = JSON.parse(res.content);
    if (resp.code != 200 || !resp.data) return null;

    let key = Crypto.enc.Hex.parse('50426641556e54644d6a4e446536704c');
    let iv = Crypto.enc.Utf8.parse(resp.iv);
    let decrypted = Crypto.AES.decrypt(resp.data, key, {
        iv: iv,
        mode: Crypto.mode.CBC,
        padding: Crypto.pad.Pkcs7
    });
    return JSON.parse(Crypto.enc.Utf8.stringify(decrypted));
}

async function search(wd, quick, pg) {
    let page = pg || 1;
    let parts = new Array(14).fill('');
    parts[0] = wd;
    if (page > 1) parts[10] = String(page);
    let url = siteUrl + '/vodsearch/' + parts.join('-') + '.html';
    const html = await request(url, null, true);
    const $ = load(html);
    const cards = $('div.public-list-box.search-box');
    let videos = _.map(cards, function(n) {
        let link = $($(n).find('a.public-list-exp')[0]);
        let id = link.attr('href') || '';
        let img = $($(n).find('img')[0]);
        let pic = img.attr('data-src') || img.attr('src') || '';
        if (pic.indexOf('data:') === 0) pic = '';
        let name = $(n).find('div.thumb-txt a').text().trim();
        let remark = $(n).find('span.public-list-prb').text().trim();
        return {
            vod_id: id,
            vod_name: name,
            vod_pic: pic,
            vod_remarks: remark,
        };
    });
    return JSON.stringify({ list: videos });
}

async function getVideos(url) {
    const html = await request(url, null, true);
    const $ = load(html);
    const cards = $('div.public-list-box.public-pic-a');
    let videos = _.map(cards, function(n) {
        let link = $($(n).find('a.public-list-exp')[0]);
        let id = link.attr('href') || '';
        let name = link.attr('title') || '';
        let img = $($(n).find('img')[0]);
        let pic = img.attr('data-src') || img.attr('src') || '';
        if (pic.indexOf('data:') === 0) {
            let src = img.attr('src') || '';
            pic = src.indexOf('data:') === 0 ? '' : src;
        }
        let remark = $(n).find('span.public-prt').text().trim();
        if (!remark) remark = $(n).find('span.public-list-prb').text().trim();
        return {
            vod_id: id,
            vod_name: name,
            vod_pic: pic,
            vod_remarks: remark,
        };
    });
    return videos;
}

function base64Decode(text) {
    return Crypto.enc.Utf8.stringify(Crypto.enc.Base64.parse(text));
}

function genFilterObj() {
    return {
        '1': [{
            key: 'id',
            name: '类型',
            value: [{n:'全部',v:''},{n:'动作片',v:'dogzopian'},{n:'喜剧片',v:'xijupian'},{n:'爱情片',v:'aiqingpian'},{n:'科幻片',v:'kehuanpian'},{n:'恐怖片',v:'kongbupian'},{n:'纪录片',v:'jilupian'},{n:'剧情片',v:'juqingpian'},{n:'战争片',v:'zhanzhengpian'},{n:'冒险片',v:'maoxianpian'},{n:'奇幻片',v:'qihuanpian'},{n:'惊悚片',v:'jingsongpian'},{n:'犯罪片',v:'fanzuipian'},{n:'动画片',v:'donghuapian'},{n:'悬疑片',v:'xuanyipian'},{n:'武侠片',v:'wuxiapian'}]
        }, {
            key: 'class',
            name: '剧情',
            value: [{n:'全部',v:''},{n:'喜剧',v:'喜剧'},{n:'爱情',v:'爱情'},{n:'恐怖',v:'恐怖'},{n:'动作',v:'动作'},{n:'科幻',v:'科幻'},{n:'剧情',v:'剧情'},{n:'战争',v:'战争'},{n:'警匪',v:'警匪'},{n:'犯罪',v:'犯罪'},{n:'伦理',v:'伦理'},{n:'动画',v:'动画'},{n:'奇幻',v:'奇幻'},{n:'武侠',v:'武侠'},{n:'冒险',v:'冒险'},{n:'枪战',v:'枪战'},{n:'悬疑',v:'悬疑'},{n:'惊悚',v:'惊悚'},{n:'经典',v:'经典'},{n:'青春',v:'青春'},{n:'文艺',v:'文艺'},{n:'微电影',v:'微电影'},{n:'古装',v:'古装'},{n:'历史',v:'历史'},{n:'运动',v:'运动'},{n:'农村',v:'农村'},{n:'儿童',v:'儿童'},{n:'网络电影',v:'网络电影'}]
        }, {
            key: 'area',
            name: '地区',
            value: [{n:'全部',v:''},{n:'大陆',v:'大陆'},{n:'香港',v:'香港'},{n:'台湾',v:'台湾'},{n:'美国',v:'美国'},{n:'法国',v:'法国'},{n:'英国',v:'英国'},{n:'日本',v:'日本'},{n:'韩国',v:'韩国'},{n:'德国',v:'德国'},{n:'泰国',v:'泰国'},{n:'印度',v:'印度'},{n:'意大利',v:'意大利'},{n:'西班牙',v:'西班牙'},{n:'加拿大',v:'加拿大'},{n:'其他',v:'其他'}]
        }, {
            key: 'lang',
            name: '语言',
            value: [{n:'全部',v:''},{n:'国语',v:'国语'},{n:'英语',v:'英语'},{n:'粤语',v:'粤语'},{n:'闽南语',v:'闽南语'},{n:'韩语',v:'韩语'},{n:'日语',v:'日语'},{n:'法语',v:'法语'},{n:'德语',v:'德语'},{n:'其它',v:'其它'}]
        }, {
            key: 'year',
            name: '年份',
            value: [{n:'全部',v:''},{n:'2026',v:'2026'},{n:'2025',v:'2025'},{n:'2024',v:'2024'},{n:'2023',v:'2023'},{n:'2022',v:'2022'},{n:'2021',v:'2021'},{n:'2020',v:'2020'},{n:'2019',v:'2019'},{n:'2018',v:'2018'},{n:'2017',v:'2017'},{n:'2016',v:'2016'},{n:'2015',v:'2015'},{n:'2014',v:'2014'},{n:'2013',v:'2013'},{n:'2012',v:'2012'},{n:'2011',v:'2011'},{n:'2010',v:'2010'},{n:'2009',v:'2009'},{n:'2008',v:'2008'},{n:'2007',v:'2007'},{n:'2006',v:'2006'},{n:'2005',v:'2005'},{n:'2004',v:'2004'},{n:'2003',v:'2003'},{n:'2002',v:'2002'},{n:'2001',v:'2001'},{n:'2000',v:'2000'}]
        }],
        '13': [{
            key: 'id',
            name: '类型',
            value: [{n:'全部',v:''},{n:'国产剧',v:'guochanju'},{n:'港台剧',v:'gangtaiju'},{n:'日韩剧',v:'rihanju'},{n:'海外剧',v:'haiwaiju'},{n:'欧美剧',v:'oumeiju'},{n:'泰国剧',v:'taiguoju'}]
        }, {
            key: 'class',
            name: '剧情',
            value: [{n:'全部',v:''},{n:'古装',v:'古装'},{n:'战争',v:'战争'},{n:'青春偶像',v:'青春偶像'},{n:'喜剧',v:'喜剧'},{n:'家庭',v:'家庭'},{n:'犯罪',v:'犯罪'},{n:'动作',v:'动作'},{n:'奇幻',v:'奇幻'},{n:'剧情',v:'剧情'},{n:'历史',v:'历史'},{n:'经典',v:'经典'},{n:'乡村',v:'乡村'},{n:'情景',v:'情景'},{n:'商战',v:'商战'},{n:'网剧',v:'网剧'},{n:'悬疑',v:'悬疑'},{n:'谍战',v:'谍战'},{n:'刑侦',v:'刑侦'},{n:'律政',v:'律政'},{n:'都市',v:'都市'},{n:'爱情',v:'爱情'},{n:'仙侠',v:'仙侠'},{n:'武侠',v:'武侠'},{n:'玄幻',v:'玄幻'},{n:'科幻',v:'科幻'},{n:'年代',v:'年代'},{n:'军旅',v:'军旅'},{n:'励志',v:'励志'},{n:'穿越',v:'穿越'},{n:'宫斗',v:'宫斗'},{n:'权谋',v:'权谋'},{n:'其他',v:'其他'}]
        }, {
            key: 'area',
            name: '地区',
            value: [{n:'全部',v:''},{n:'内地',v:'内地'},{n:'韩国',v:'韩国'},{n:'香港',v:'香港'},{n:'台湾',v:'台湾'},{n:'日本',v:'日本'},{n:'美国',v:'美国'},{n:'泰国',v:'泰国'},{n:'英国',v:'英国'},{n:'新加坡',v:'新加坡'},{n:'其他',v:'其他'}]
        }, {
            key: 'lang',
            name: '语言',
            value: [{n:'全部',v:''},{n:'国语',v:'国语'},{n:'英语',v:'英语'},{n:'粤语',v:'粤语'},{n:'闽南语',v:'闽南语'},{n:'韩语',v:'韩语'},{n:'日语',v:'日语'},{n:'其它',v:'其它'}]
        }, {
            key: 'year',
            name: '年份',
            value: [{n:'全部',v:''},{n:'2026',v:'2026'},{n:'2025',v:'2025'},{n:'2024',v:'2024'},{n:'2023',v:'2023'},{n:'2022',v:'2022'},{n:'2021',v:'2021'},{n:'2020',v:'2020'},{n:'2019',v:'2019'},{n:'2018',v:'2018'},{n:'2017',v:'2017'},{n:'2016',v:'2016'},{n:'2015',v:'2015'},{n:'2014',v:'2014'},{n:'2013',v:'2013'},{n:'2012',v:'2012'},{n:'2011',v:'2011'},{n:'2010',v:'2010'},{n:'2009',v:'2009'},{n:'2008',v:'2008'},{n:'2007',v:'2007'},{n:'2006',v:'2006'},{n:'2005',v:'2005'},{n:'2004',v:'2004'},{n:'2003',v:'2003'},{n:'2002',v:'2002'},{n:'2001',v:'2001'},{n:'2000',v:'2000'}]
        }],
        '3': [{
            key: 'id',
            name: '类型',
            value: [{n:'全部',v:''},{n:'大陆',v:'daluzongyi'},{n:'港台',v:'gtzongyi'},{n:'日韩',v:'rhzongyi'},{n:'欧美',v:'omzongyi'}]
        }, {
            key: 'class',
            name: '剧情',
            value: [{n:'全部',v:''},{n:'真人秀',v:'真人秀'},{n:'情感',v:'情感'},{n:'爱情',v:'爱情'},{n:'访谈',v:'访谈'},{n:'旅游',v:'旅游'},{n:'音乐',v:'音乐'},{n:'美食',v:'美食'},{n:'纪实',v:'纪实'},{n:'竞技',v:'竞技'},{n:'曲艺',v:'曲艺'},{n:'生活',v:'生活'},{n:'游戏互动',v:'游戏互动'},{n:'财经',v:'财经'},{n:'求职',v:'求职'}]
        }, {
            key: 'area',
            name: '地区',
            value: [{n:'全部',v:''},{n:'内地',v:'内地'},{n:'港台',v:'港台'},{n:'日韩',v:'日韩'},{n:'欧美',v:'欧美'}]
        }, {
            key: 'lang',
            name: '语言',
            value: [{n:'全部',v:''},{n:'国语',v:'国语'},{n:'英语',v:'英语'},{n:'粤语',v:'粤语'},{n:'闽南语',v:'闽南语'},{n:'韩语',v:'韩语'},{n:'日语',v:'日语'},{n:'其它',v:'其它'}]
        }, {
            key: 'year',
            name: '年份',
            value: [{n:'全部',v:''},{n:'2026',v:'2026'},{n:'2025',v:'2025'},{n:'2024',v:'2024'},{n:'2023',v:'2023'},{n:'2022',v:'2022'},{n:'2021',v:'2021'},{n:'2020',v:'2020'},{n:'2019',v:'2019'},{n:'2018',v:'2018'},{n:'2017',v:'2017'},{n:'2016',v:'2016'},{n:'2015',v:'2015'},{n:'2014',v:'2014'},{n:'2013',v:'2013'},{n:'2012',v:'2012'},{n:'2011',v:'2011'},{n:'2010',v:'2010'},{n:'2009',v:'2009'},{n:'2008',v:'2008'},{n:'2007',v:'2007'},{n:'2006',v:'2006'},{n:'2005',v:'2005'},{n:'2004',v:'2004'},{n:'2003',v:'2003'},{n:'2002',v:'2002'},{n:'2001',v:'2001'},{n:'2000',v:'2000'}]
        }],
        '4': [{
            key: 'id',
            name: '类型',
            value: [{n:'全部',v:''},{n:'国产动漫',v:'dalucm'},{n:'日韩动漫',v:'rihancm'},{n:'欧美动漫',v:'uscm'},{n:'动漫片',v:'domanpian'}]
        }, {
            key: 'class',
            name: '剧情',
            value: [{n:'全部',v:''},{n:'动作',v:'动作'},{n:'玄幻',v:'玄幻'},{n:'亲子',v:'亲子'},{n:'科幻',v:'科幻'},{n:'热血',v:'热血'},{n:'推理',v:'推理'},{n:'搞笑',v:'搞笑'},{n:'冒险',v:'冒险'},{n:'校园',v:'校园'},{n:'机战',v:'机战'},{n:'运动',v:'运动'},{n:'战争',v:'战争'},{n:'少年',v:'少年'},{n:'少女',v:'少女'},{n:'社会',v:'社会'},{n:'原创',v:'原创'},{n:'益智',v:'益智'},{n:'励志',v:'励志'},{n:'动漫',v:'动漫'},{n:'惊悚',v:'惊悚'},{n:'治愈',v:'治愈'},{n:'神魔',v:'神魔'},{n:'武侠',v:'武侠'},{n:'其他',v:'其他'}]
        }, {
            key: 'area',
            name: '地区',
            value: [{n:'全部',v:''},{n:'中国',v:'中国'},{n:'日本',v:'日本'},{n:'欧美',v:'欧美'},{n:'其他',v:'其他'}]
        }, {
            key: 'lang',
            name: '语言',
            value: [{n:'全部',v:''},{n:'国语',v:'国语'},{n:'英语',v:'英语'},{n:'粤语',v:'粤语'},{n:'闽南语',v:'闽南语'},{n:'韩语',v:'韩语'},{n:'日语',v:'日语'},{n:'其它',v:'其它'}]
        }, {
            key: 'year',
            name: '年份',
            value: [{n:'全部',v:''},{n:'2026',v:'2026'},{n:'2025',v:'2025'},{n:'2024',v:'2024'},{n:'2023',v:'2023'},{n:'2022',v:'2022'},{n:'2021',v:'2021'},{n:'2020',v:'2020'},{n:'2019',v:'2019'},{n:'2018',v:'2018'},{n:'2017',v:'2017'},{n:'2016',v:'2016'},{n:'2015',v:'2015'},{n:'2014',v:'2014'},{n:'2013',v:'2013'},{n:'2012',v:'2012'},{n:'2011',v:'2011'},{n:'2010',v:'2010'},{n:'2009',v:'2009'},{n:'2008',v:'2008'},{n:'2007',v:'2007'},{n:'2006',v:'2006'},{n:'2005',v:'2005'},{n:'2004',v:'2004'},{n:'2003',v:'2003'},{n:'2002',v:'2002'},{n:'2001',v:'2001'},{n:'2000',v:'2000'}]
        }],
        '14': [{
            key: 'area',
            name: '地区',
            value: [{n:'全部',v:''},{n:'大陆',v:'大陆'},{n:'香港',v:'香港'},{n:'台湾',v:'台湾'},{n:'美国',v:'美国'},{n:'法国',v:'法国'},{n:'英国',v:'英国'},{n:'日本',v:'日本'},{n:'韩国',v:'韩国'},{n:'德国',v:'德国'},{n:'泰国',v:'泰国'},{n:'印度',v:'印度'},{n:'意大利',v:'意大利'},{n:'西班牙',v:'西班牙'},{n:'加拿大',v:'加拿大'},{n:'其他',v:'其他'}]
        }, {
            key: 'year',
            name: '年份',
            value: [{n:'全部',v:''},{n:'2026',v:'2026'},{n:'2025',v:'2025'},{n:'2024',v:'2024'},{n:'2023',v:'2023'},{n:'2022',v:'2022'},{n:'2021',v:'2021'},{n:'2020',v:'2020'},{n:'2019',v:'2019'},{n:'2018',v:'2018'},{n:'2017',v:'2017'},{n:'2016',v:'2016'},{n:'2015',v:'2015'},{n:'2014',v:'2014'}]
        }],
        '15': [{
            key: 'id',
            name: '类型',
            value: [{n:'全部',v:''},{n:'番剧（B站）',v:'fanjuBzhan'},{n:'国创（B站）',v:'guochuangBzhan'},{n:'电影（B站）',v:'dianyingBzhan'},{n:'电视剧（B站）',v:'dianshijuBzhan'}]
        }]
    };
}

export function __jsEvalReturn() {
    return {
        init: init,
        home: home,
        homeVod: homeVod,
        category: category,
        detail: detail,
        play: play,
        search: search,
    };
}