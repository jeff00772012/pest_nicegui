# pest_core.py
import datetime as dt
import html
import re
from dataclasses import dataclass
from typing import List, Dict, Tuple
from urllib.parse import quote_plus

import feedparser
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup
from sklearn.feature_extraction.text import TfidfVectorizer
import networkx as nx


# -----------------------------------------
# PEST QUERY DEFINITIONS
# -----------------------------------------

PEST_QUERIES = {
    "Political": [
        "{company} regulation", "{company} government", "{company} policy",
        "{company} antitrust", "{company} export controls", "{company} geopolitics",
        "{company} ESG governance", "{company} compliance", "{company} lobbying"
    ],
    "Economic": [
        "{company} earnings", "{company} revenue", "{company} guidance",
        "{company} inflation", "{company} interest rates", "{company} market share",
        "{company} supply chain", "{company} layoffs", "{company} M&A"
    ],
    "Social": [
        "{company} brand perception", "{company} consumer sentiment",
        "{company} workplace culture", "{company} diversity", "{company} boycott",
        "{company} privacy", "{company} safety concerns", "{company} CSR"
    ],
    "Technological": [
        "{company} R&D", "{company} product launch", "{company} innovation",
        "{company} patents", "{company} AI", "{company} roadmap", "{company} security",
        "{company} platform", "{company} competitive technology"
    ],
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

MAX_RSS_PER_QUERY = 10


# -----------------------------------------
# DATA STRUCTURE
# -----------------------------------------

@dataclass
class Article:
    pest: str
    title: str
    summary: str
    link: str
    published: str
    source: str
    query: str


# -----------------------------------------
# HELPERS
# -----------------------------------------

def clean_text(x: str) -> str:
    if not x:
        return ""
    x = html.unescape(x)
    x = re.sub(r"\s+", " ", x).strip()
    return x


def get_google_news_rss(query: str, days: int) -> List[dict]:
    """Fetch Google News RSS for a query."""
    url = f"https://news.google.com/rss/search?q={quote_plus(query)}&hl=en-US&gl=US&ceid=US:en"
    feed = feedparser.parse(url)
    cutoff = dt.datetime.utcnow() - dt.timedelta(days=days)
    entries = []

    for e in feed.entries[:MAX_RSS_PER_QUERY]:
        pub = None
        if "published_parsed" in e and e.published_parsed:
            pub = dt.datetime(*e.published_parsed[:6])
        elif "updated_parsed" in e and e.updated_parsed:
            pub = dt.datetime(*e.updated_parsed[:6])

        if pub and pub < cutoff:
            continue

        entries.append({
            "title": clean_text(getattr(e, "title", "")),
            "summary": clean_text(BeautifulSoup(getattr(e, "summary", ""), "html.parser").get_text()),
            "link": getattr(e, "link", ""),
            "published": pub.isoformat() if pub else "",
            "source": clean_text(getattr(getattr(e, "source", {}), "title", getattr(e, "source", ""))),
        })

    return entries


def fetch_page_snippet(url: str, timeout: int = 7) -> str:
    """Fetch extra text from article page if RSS summary is too short."""
    try:
        headers = {"User-Agent": USER_AGENT}
        r = requests.get(url, headers=headers, timeout=timeout)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")

        # Meta description
        meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta and meta.get("content"):
            return clean_text(meta["content"])

        ps = [p.get_text(" ", strip=True) for p in soup.find_all("p")]
        return clean_text(" ".join(ps)[:1500])
    except Exception:
        return ""


def dedupe_articles(rows: List[dict]) -> List[dict]:
    """Remove duplicates."""
    seen = set()
    out = []
    for r in rows:
        key = (r["title"].lower(), r["link"])
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def sentence_split(text: str) -> List[str]:
    """Simple sentence splitter."""
    sents = re.split(r'(?<=[.!?])\s+(?=[A-Z0-9])', text.strip())
    return [s.strip() for s in sents if len(s.strip()) > 30][:100]


def textrank_summarize(text: str, max_sentences: int = 5) -> str:
    sents = sentence_split(text)
    if not sents:
        return ""

    try:
        vect = TfidfVectorizer(stop_words="english", ngram_range=(1, 2))
        X = vect.fit_transform(sents)

        sim = (X * X.T).toarray()
        np.fill_diagonal(sim, 0.0)

        g = nx.from_numpy_array(sim)
        scores = nx.pagerank(g, max_iter=200)

        ranked = sorted(((scores[i], i, s) for i, s in enumerate(sents)), reverse=True)
        top = sorted(ranked[:max_sentences], key=lambda x: x[1])
        return " ".join([t[2] for t in top])
    except Exception:
        return " ".join(sents[:max_sentences])


def build_factor_summary(articles: List[Article], factor: str, max_items: int = 6):
    """Select the best articles & produce a summary."""
    def score(a: Article):
        recency = 0.0
        try:
            if a.published:
                days_old = (dt.datetime.utcnow() - dt.datetime.fromisoformat(a.published)).days
                recency = max(0.0, 30 - days_old) / 30
        except:
            pass
        return recency + min(len(a.title), 120) / 120

    selected = sorted(
        [a for a in articles if a.pest == factor],
        key=score,
        reverse=True
    )[:max_items]

    text = ". ".join(
        f"{a.title}. {a.summary}"
        for a in selected
        if a.title or a.summary
    )

    summary = textrank_summarize(text)
    if not summary:
        summary = "_No clear signals found._"

    return summary, selected


# -----------------------------------------
# MAIN PIPELINE
# -----------------------------------------

def run_pipeline(company: str, days: int = 14, max_articles: int = 40):
    """Returns df, picks, snapshots for UI rendering."""

    rows = []

    for factor, queries in PEST_QUERIES.items():
        for q in queries:
            q_actual = q.format(company=company)
            entries = get_google_news_rss(q_actual, days)

            for e in entries:
                extra = fetch_page_snippet(e["link"]) if len(e["summary"]) < 120 else ""
                summary = e["summary"] if len(e["summary"]) >= len(extra) else extra

                rows.append({
                    "pest": factor,
                    "title": e["title"],
                    "summary": summary,
                    "link": e["link"],
                    "published": e["published"],
                    "source": e["source"],
                    "query": q_actual,
                })

    rows = dedupe_articles(rows)

    # Balance article count per factor
    per_factor_cap = max(8, max_articles // 4)
    balanced = []
    for factor in ["Political", "Economic", "Social", "Technological"]:
        subset = [r for r in rows if r["pest"] == factor][:per_factor_cap]
        balanced.extend(subset)

    df = pd.DataFrame(balanced)

    # Convert rows to Article objects
    articles = [
        Article(
            pest=r["pest"],
            title=r["title"],
            summary=r["summary"],
            link=r["link"],
            published=r["published"],
            source=r["source"],
            query=r["query"],
        )
        for _, r in df.iterrows()
    ]

    snapshots = {}
    picks = {}

    for factor in ["Political", "Economic", "Social", "Technological"]:
        summary, selected = build_factor_summary(articles, factor)
        snapshots[factor] = summary
        picks[factor] = selected

    return df, picks, snapshots