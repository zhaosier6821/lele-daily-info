#!/usr/bin/env python3
import datetime as dt
import html
import json
import os
import pathlib
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
MODEL_URL = "https://models.github.ai/inference/chat/completions"
MODEL = "openai/gpt-4.1-mini"

CATEGORIES = [
    ("各国财经", "global fiscal monetary policy central bank economy"),
    ("中国新经济", "中国 新经济 产业 结构 政策"),
    ("全球产业", "global economy industry structure new economy"),
    ("国外游戏", "new video game release international gaming"),
    ("旅行路线", "unusual travel route destination cost itinerary"),
    ("健身健康", "exercise fitness healthy living research"),
    ("机车", "new motorcycle ADV touring rally engineering suspension engine electronics technical"),
    ("新兴生活", "emerging niche lifestyle trend"),
    ("全球音乐榜", "Billboard Global 200 top 10 this week"),
    ("咖啡", "single origin coffee bean processing fermentation extraction research coffee signature drink"),
    ("今日咖啡豆", "coffee variety history origin famous auction flavor processing best brewing method"),
    ("DIY 调酒", "acid forward sour cocktail single malt Scotch whisky Glenlivet recipe technique"),
    ("健康菜谱", "healthy high protein recipe nutrition"),
    ("意外但有用", "important practical knowledge digital safety consumer health"),
]

def fetch(url, headers=None, timeout=25):
    req = urllib.request.Request(url, headers=headers or {"User-Agent": "LeleDaily/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as res:
        return res.read()

def discover(tag, query):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({
        "q": query + " when:2d", "hl": "en-US", "gl": "US", "ceid": "US:en"
    })
    root = ET.fromstring(fetch(url))
    found = []
    for item in root.findall("./channel/item")[:6]:
        title = html.unescape(item.findtext("title", "")).strip()
        link = item.findtext("link", "").strip()
        pub = item.findtext("pubDate", "").strip()
        source = item.find("source")
        found.append({"title": title, "url": link, "published": pub,
                      "publisher": source.text.strip() if source is not None and source.text else "Google News"})
    return {"tag": tag, "items": found}

def prompt_payload(today, sources):
    system = """你是《乐乐日报》的主编。依据提供的新闻标题与链接，写一份准确、自然、信息密度高的中文日报。严禁编造事实、数据、作品、榜单名次和价格；材料不足时明确写‘尚无可靠数据’，不要补全想象。每类只做一张卡片。不是生硬翻译，而是解释背景、事实、影响、争议和限制。

读者画像与三项硬性编辑标准：
1. 乐乐是完成过独自摩托进藏的资深骑手。机车卡默认他已掌握驾照、安全、基础保养与长途常识；禁止“戴头盔、雨天慢行、检查胎压”式入门科普。优先写新车型的发动机/车架/悬挂/电控与骑行取向，ADV和拉力技术、长途装备取舍、路线环境对机械设定的影响、赛事或产业变化。给出可比较的具体参数，并解释参数在真实骑行中的意义，不照抄配置表。
2. 咖啡卡禁止泛泛讲“水温、研磨、酸苦平衡”。每天从具体咖啡豆、产区与品种、处理法、烘焙和风味逻辑、萃取实验、咖啡特调中选一个窄主题。尽量给出豆种/产区/处理法及可复现的粉量、粉水比、水温、研磨思路、时间或配方；把事实和主编建议分开。
3. “今日咖啡豆”是独立于咖啡实验的固定卡片。每天只介绍一个明确的咖啡品种或有代表性的产区批次，必须包含：名称与产地、植物学或传播历史、真正出名的时间和原因、常见处理法与代表风味，以及手冲/摩卡壶/意式/法压/冷萃中哪些方式最适合、哪些会掩盖它、推荐参数。注意区分品种、产区、庄园、处理法和商品名，不准混为一谈。
4. 乐乐喜欢酸度明确的酒，日常口粮酒是格兰威特。DIY 调酒优先酸型、清爽型或酸苦型配方；可围绕格兰威特及其他斯佩塞单一麦芽设计，但不要每天都只写经典 Whisky Sour。给出毫升数、技法、冰型/杯型和酸甜微调，并说明为什么不浪费基酒本身的果香。

旅行卡必须给出7天内可执行路线，并把交通、住宿、餐饮、活动费用分别列为人民币区间，注明是动态估算、预订前复核。音乐榜卡只有在材料明确支持时才列前十，否则说明缺项。健康内容避免诊断和夸大。最终只返回合法 JSON，不要 Markdown。"""
    schema = {"date": today, "cards": [{"tag": "分类", "title": "标题", "lead": "两三句核心信息", "detail": ["背景与事实", "影响、争议或执行建议"], "source": "https://...", "sourceName": "来源"}]}
    user = f"日期：{today}\n请按这{len(CATEGORIES)}类及原顺序输出，每类一张卡：{', '.join(x[0] for x in CATEGORIES)}。\nJSON结构示例：{json.dumps(schema, ensure_ascii=False)}\n检索材料：\n{json.dumps(sources, ensure_ascii=False)}"
    return {"model": MODEL, "temperature": 0.25, "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}

def generate(today, sources):
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError("GITHUB_TOKEN is required")
    body = json.dumps(prompt_payload(today, sources)).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(MODEL_URL, data=body, method="POST", headers={
                "Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/vnd.github+json"
            })
            with urllib.request.urlopen(req, timeout=90) as res:
                response = json.loads(res.read())
            result = json.loads(response["choices"][0]["message"]["content"])
            cards = result.get("cards", [])
            if len(cards) != len(CATEGORIES):
                raise ValueError(f"expected 13 cards, got {len(cards)}")
            for card in cards:
                if not str(card.get("source", "")).startswith("http"):
                    raise ValueError("card without a valid source")
            result["date"] = today
            result["generatedAt"] = dt.datetime.now(dt.timezone.utc).isoformat()
            return result
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))

def main():
    now = dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    today = now.date().isoformat()
    sources = []
    for tag, query in CATEGORIES:
        try:
            sources.append(discover(tag, query))
        except Exception as exc:
            sources.append({"tag": tag, "items": [], "error": str(exc)})
    issue = generate(today, sources)
    DATA.mkdir(exist_ok=True)
    (DATA / f"{today}.json").write_text(json.dumps(issue, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    archive_path = DATA / "archive.json"
    archive = json.loads(archive_path.read_text(encoding="utf-8")) if archive_path.exists() else {"dates": []}
    archive["dates"] = sorted(set(archive.get("dates", []) + [today]))
    archive_path.write_text(json.dumps(archive, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    main()
