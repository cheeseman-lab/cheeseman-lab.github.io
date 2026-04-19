#!/usr/bin/env python3
"""
Retrieve Cheeseman Lab publications from OpenAlex (primary) + PubMed (secondary).

Usage:
    pip install requests pyyaml
    python fetch_publications.py

Outputs:
    publications.yml           – clean YAML for the website (/_data/)
    publications_detailed.json – full metadata including citation counts
"""

import requests
import json
import yaml
import time
import re
from pathlib import Path
from typing import List, Dict, Optional
from difflib import SequenceMatcher
from collections import Counter


# ── Configuration ──────────────────────────────────────────────────────────
OPENALEX_AUTHOR_ID = "A5064387359"           # Iain M. Cheeseman
PUBMED_AUTHOR_QUERY = "Cheeseman IM[Author]"
OPENALEX_EMAIL = "cheeseman-lab@mit.edu"     # polite-pool for OpenAlex
REQUEST_TIMEOUT = 30

# Publication types to exclude (OpenAlex type strings)
EXCLUDE_TYPES = {"paratext", "editorial", "erratum", "letter", "peer-review", "grant"}

# Title patterns that indicate non-research entries
SKIP_TITLE_PATTERNS = [
    r"^Editorial Board",
    r"^Faculty Opinions recommendation",
    r"^Author response:",
    r"^Decision letter:",
    r"^Material Supplemental",
    r"^Crystal structure of",
    r"^Structure of .* pdb",
    r"Citation$",
    r"^\d{4}\.\d{4}/",
]
SKIP_TITLE_RE = re.compile("|".join(SKIP_TITLE_PATTERNS), re.IGNORECASE)

# Preprint servers
PREPRINT_SOURCES = {"biorxiv", "medrxiv", "arxiv", "ssrn", "chemrxiv", "research square"}

# Journal name normalisations
JOURNAL_RENAMES = {
    "bioRxiv (Cold Spring Harbor Laboratory)": "bioRxiv",
    "medRxiv (Cold Spring Harbor Laboratory)": "medRxiv",
}


# ── Helpers ────────────────────────────────────────────────────────────────

def _get_json(url: str, params: dict = None, headers: dict = None,
              retries: int = 3, backoff: float = 3.0) -> Optional[dict]:
    """GET with retries and rate-limit handling."""
    for attempt in range(retries):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                wait = backoff * (2 ** attempt)
                print(f"  Rate-limited. Waiting {wait:.0f}s …")
                time.sleep(wait)
                continue
            r.raise_for_status()
        except requests.RequestException as exc:
            if attempt < retries - 1:
                time.sleep(backoff * (2 ** attempt))
            else:
                print(f"  Request failed after {retries} attempts: {exc}")
    return None


def _norm_title(title: str) -> str:
    """Normalize title for dedup comparison."""
    t = re.sub(r"[^a-z0-9 ]", "", title.lower())
    return re.sub(r"\s+", " ", t).strip()


def _clean_title(title: str) -> str:
    """Strip HTML tags and tidy whitespace."""
    title = re.sub(r"</?[a-z]+/?>", "", title)
    return re.sub(r"\s+", " ", title).strip()


def _clean_journal(name: str) -> str:
    """Apply journal renaming table."""
    return JOURNAL_RENAMES.get(name, name)


def _is_preprint(journal: str) -> bool:
    """Check if journal string refers to a preprint server."""
    j = journal.lower()
    return any(ps in j for ps in PREPRINT_SOURCES)


# ── OpenAlex ───────────────────────────────────────────────────────────────

def fetch_openalex(author_id: str = OPENALEX_AUTHOR_ID) -> List[Dict]:
    """Fetch all works for an author from OpenAlex (cursor pagination)."""
    print(f"[OpenAlex] Fetching works for author {author_id} …")
    works: List[Dict] = []
    cursor = "*"
    page = 0

    while cursor:
        page += 1
        params = {
            "filter": f"authorships.author.id:{author_id}",
            "per_page": 200,
            "cursor": cursor,
            "select": ("id,doi,title,publication_year,publication_date,"
                       "primary_location,type,authorships,cited_by_count,"
                       "biblio"),
            "mailto": OPENALEX_EMAIL,
        }
        data = _get_json("https://api.openalex.org/works", params=params)
        if not data:
            break
        batch = data.get("results", [])
        works.extend(batch)
        print(f"  Page {page}: {len(batch)} works (total {len(works)})")
        cursor = data.get("meta", {}).get("next_cursor")
        if not batch:
            break
        time.sleep(0.2)

    print(f"[OpenAlex] {len(works)} raw works retrieved")
    return works


def parse_openalex_work(work: dict) -> Optional[Dict]:
    """Convert an OpenAlex work to standard format."""
    title = _clean_title(work.get("title") or "")
    if not title or len(title) < 10 or SKIP_TITLE_RE.search(title):
        return None
    if (work.get("type") or "").lower() in EXCLUDE_TYPES:
        return None

    doi_raw = work.get("doi") or ""
    doi = doi_raw.replace("https://doi.org/", "").strip() if doi_raw else ""

    loc = work.get("primary_location") or {}
    source = loc.get("source") or {}
    journal = _clean_journal((source.get("display_name") or "").strip())

    authors = []
    for a in work.get("authorships", []):
        name = (a.get("author", {}).get("display_name") or "").strip()
        if name:
            authors.append(name)

    biblio = work.get("biblio") or {}
    fp, lp = biblio.get("first_page", ""), biblio.get("last_page", "")
    pages = f"{fp}-{lp}" if fp and lp else fp

    return {
        "title": title,
        "authors": authors,
        "journal": journal,
        "publication_year": work.get("publication_year"),
        "publication_date": work.get("publication_date") or "",
        "doi": doi,
        "volume": biblio.get("volume") or "",
        "pages": pages,
        "cited_by_count": work.get("cited_by_count", 0),
        "is_preprint": _is_preprint(journal),
        "source": "openalex",
        "openalex_id": work.get("id", ""),
    }


# ── PubMed ─────────────────────────────────────────────────────────────────

def fetch_pubmed_ids(query: str = PUBMED_AUTHOR_QUERY) -> List[str]:
    """Search PubMed and return PMIDs."""
    print(f"[PubMed] Searching: {query}")
    data = _get_json(
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
        params={"db": "pubmed", "term": query, "retmax": 500, "retmode": "json"},
    )
    if not data:
        return []
    ids = data.get("esearchresult", {}).get("idlist", [])
    print(f"[PubMed] {len(ids)} PMIDs found")
    return ids


def fetch_pubmed_details(pmids: List[str]) -> List[Dict]:
    """Fetch article metadata for PMIDs."""
    if not pmids:
        return []
    results = []
    for i in range(0, len(pmids), 100):
        batch = pmids[i : i + 100]
        print(f"[PubMed] Fetching {i+1}–{i+len(batch)} …")
        data = _get_json(
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi",
            params={"db": "pubmed", "id": ",".join(batch), "retmode": "json"},
        )
        if not data:
            continue
        block = data.get("result", {})
        for pmid in batch:
            art = block.get(pmid)
            if art and not isinstance(art, str):
                results.append(art)
        time.sleep(0.4)
    print(f"[PubMed] {len(results)} articles retrieved")
    return results


def parse_pubmed_article(article: dict) -> Optional[Dict]:
    """Convert PubMed esummary to standard format."""
    title = _clean_title((article.get("title") or "").rstrip("."))
    if not title or len(title) < 10 or SKIP_TITLE_RE.search(title):
        return None

    doi = ""
    for aid in article.get("articleids", []):
        if aid.get("idtype") == "doi":
            doi = aid.get("value", "")
            break

    authors = [a["name"].strip() for a in article.get("authors", []) if a.get("name")]
    journal = (article.get("fulljournalname") or article.get("source") or "").strip()

    year = None
    m = re.search(r"(\d{4})", article.get("pubdate", ""))
    if m:
        year = int(m.group(1))

    return {
        "title": title,
        "authors": authors,
        "journal": journal,
        "publication_year": year,
        "publication_date": article.get("pubdate", ""),
        "doi": doi,
        "volume": article.get("volume", ""),
        "pages": article.get("pages", ""),
        "cited_by_count": 0,
        "is_preprint": False,
        "source": "pubmed",
        "pmid": article.get("uid", ""),
    }


# ── Merge & Deduplicate ──────────────────────────────────────────────────

def merge_publications(oa_pubs: List[Dict], pm_pubs: List[Dict]) -> List[Dict]:
    """Merge by DOI then title, preferring OpenAlex data."""
    merged: Dict[str, Dict] = {}
    doi_map: Dict[str, str] = {}
    title_map: Dict[str, str] = {}

    def _add(pub: Dict):
        doi = pub.get("doi", "").strip().lower()
        tkey = _norm_title(pub.get("title", ""))

        if doi and doi in doi_map:
            existing = merged[doi_map[doi]]
            if pub["source"] == "pubmed" and not existing.get("pmid"):
                existing["pmid"] = pub.get("pmid", "")
            elif pub["source"] == "openalex":
                pub["pmid"] = existing.get("pmid", "")
                merged[doi_map[doi]] = pub
            return

        if tkey and tkey in title_map:
            existing = merged[title_map[tkey]]
            if doi and not existing.get("doi"):
                existing["doi"] = pub["doi"]
            if pub.get("pmid") and not existing.get("pmid"):
                existing["pmid"] = pub["pmid"]
            if pub["source"] == "openalex" and existing["source"] == "pubmed":
                pub["pmid"] = existing.get("pmid", "")
                merged[title_map[tkey]] = pub
            return

        key = doi or tkey or pub["title"]
        merged[key] = pub
        if doi:
            doi_map[doi] = key
        if tkey:
            title_map[tkey] = key

    for pub in oa_pubs:
        _add(pub)

    pm_new = 0
    for pub in pm_pubs:
        n_before = len(merged)
        _add(pub)
        if len(merged) > n_before:
            pm_new += 1

    print(f"[Merge] {len(oa_pubs)} OpenAlex + {len(pm_pubs)} PubMed → "
          f"{len(merged)} unique ({pm_new} new from PubMed)")
    return list(merged.values())


def deduplicate_preprints(pubs: List[Dict], threshold: float = 0.55) -> List[Dict]:
    """Remove preprints whose published journal version is also present."""
    preprints = [p for p in pubs if p.get("is_preprint")]
    non_preprints = [p for p in pubs if not p.get("is_preprint")]
    if not preprints:
        return pubs

    drop = set()
    for i, pre in enumerate(preprints):
        pn = _norm_title(pre["title"])
        for pub in non_preprints:
            if SequenceMatcher(None, pn, _norm_title(pub["title"])).ratio() > threshold:
                drop.add(i)
                break

    kept = [p for i, p in enumerate(preprints) if i not in drop]
    if drop:
        print(f"[Dedup] Removed {len(drop)} preprints with published versions")
        for i in sorted(drop):
            print(f"  – {preprints[i]['title'][:75]}")
    return non_preprints + kept


# ── Output ─────────────────────────────────────────────────────────────────

def save_yaml(pubs: List[Dict], filename: str = "publications.yml"):
    clean = [{
        "title": p["title"],
        "authors": p["authors"],
        "journal": p.get("journal", ""),
        "publication_year": p.get("publication_year"),
        "doi": p.get("doi", ""),
    } for p in pubs]
    with open(filename, "w", encoding="utf-8") as f:
        yaml.dump(clean, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
    print(f"[Output] {len(clean)} publications → {filename}")


def save_detailed_json(pubs: List[Dict], filename: str = "publications_detailed.json"):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(pubs, f, indent=2, ensure_ascii=False)
    print(f"[Output] {len(pubs)} publications → {filename}")


def print_summary(pubs: List[Dict]):
    n_preprints = sum(1 for p in pubs if p.get("is_preprint"))
    years = [p["publication_year"] for p in pubs if p.get("publication_year")]
    citations = [p.get("cited_by_count", 0) for p in pubs]
    journals = [p["journal"] for p in pubs if p.get("journal") and not p.get("is_preprint")]

    print(f"\n{'='*60}")
    print(f"  Total: {len(pubs)} ({len(pubs) - n_preprints} articles + {n_preprints} preprints)")
    if years:
        print(f"  Years: {min(years)}–{max(years)}")
    if any(c > 0 for c in citations):
        top = max(pubs, key=lambda p: p.get("cited_by_count", 0))
        print(f"  Citations: {sum(citations):,} total | top paper: {top['cited_by_count']}")
    yr = Counter(years)
    print(f"\n  Recent:")
    for y in sorted(yr, reverse=True)[:8]:
        print(f"    {y}: {yr[y]}")
    jc = Counter(journals)
    print(f"\n  Top journals:")
    for j, c in jc.most_common(10):
        print(f"    {j}: {c}")
    print(f"{'='*60}\n")


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("Fetching Cheeseman Lab publications …\n")

    oa_works = fetch_openalex()
    oa_pubs = [p for p in (parse_openalex_work(w) for w in oa_works) if p]
    print(f"[OpenAlex] {len(oa_pubs)} valid after filtering\n")
    time.sleep(0.5)

    pm_ids = fetch_pubmed_ids()
    pm_articles = fetch_pubmed_details(pm_ids)
    pm_pubs = [p for p in (parse_pubmed_article(a) for a in pm_articles) if p]
    print(f"[PubMed] {len(pm_pubs)} valid after filtering\n")

    pubs = merge_publications(oa_pubs, pm_pubs)
    pubs = deduplicate_preprints(pubs)
    pubs.sort(key=lambda x: (x.get("publication_year") or 0, x.get("cited_by_count") or 0),
              reverse=True)

    print_summary(pubs)
    script_dir = Path(__file__).parent
    save_yaml(pubs, script_dir.parent / "_data" / "publications.yml")
    save_detailed_json(pubs, script_dir / "publications_detailed.json")
    print(f"Done – {len(pubs)} publications.")
    return pubs


if __name__ == "__main__":
    pubs = main()
