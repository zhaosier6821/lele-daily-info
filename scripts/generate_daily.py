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
    ("机车", "motorcycle news safety new model"),
    ("新兴生活", "emerging niche lifestyle trend"),
    ("全球音乐榜", "Billboard Global 200 top 10 this week"),
    ("咖啡", "coffee science brewing specialty coffee"),
    ("DIY 调酒", "cocktail recipe technique DIY"),
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
    system = """你是《乐乐日报》的主编。依据提供的新闻标题与链接，写一份准确、自然、信息密度高的中文日报。严禁编造事实、数据、作品、榜单名次和价格；材料不足时明确写‘尚无可靠数据’，不要补全想象。每类只做一张卡片。不是生硬翻译，而是解释背景、事实、影响、争议和限制。旅行卡必须给出7天内可执行路线，并把交通、住宿、餐饮、活动费用分别列为人民币区间，注明是动态估算、预订前复核。音乐榜卡只有在材料明确支持时才列前十，否则说明缺项。健康内容避免诊断和夸大。最终只返回合法 JSON，不要 Markdown。"""
    schema = {"date": today, "cards": [{"tag": "分类", "title": "标题", "lead": "两三句核心信息", "detail": ["背景与事实", "影响、争议或执行建议"], "source": "https://...", "sourceName": "来源"}]}
    user = f"日期：{today}\n请按这13类及原顺序输出，每类一张卡：{', '.join(x[0] for x in CATEGORIES)}。\nJSON结构示例：{json.dumps(schema, ensure_ascii=False)}\n检索材料：\n{json.dumps(sources, ensure_ascii=False)}"
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
