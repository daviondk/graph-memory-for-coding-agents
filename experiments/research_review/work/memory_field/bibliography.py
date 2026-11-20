"""Build refs_meta.json from source links in the adjacent research-page JSONs."""

import concurrent.futures
import json
import re
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "refs_meta.json"
ARXIV_PATH = re.compile(r"/(?:abs|html|pdf)/([0-9]{4}\.[0-9]{4,5}|[a-z.-]+/[0-9]{7})(?:v\d+)?(?:\.pdf)?/?$", re.I)
YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

# The original PDF has no bibliographic metadata. Its first page supplies the
# full title and author order. Crossref supplies the 2012 publication date.
PDF_RECORDS = {
    "https://www.vldb.org/pvldb/vol6/p37-dong.pdf": (
        "Less is More: Selecting Sources Wisely for Integration", "Xin Luna Dong", "2012",
        "https://api.crossref.org/works/10.14778/2535568.2448938",
    )
}


def canonical_url(url):
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").lower()
    if host in {"arxiv.org", "www.arxiv.org", "export.arxiv.org"}:
        match = ARXIV_PATH.fullmatch(parts.path)
        if match:
            return "https://arxiv.org/abs/" + match[1]
    if host in {"doi.org", "dx.doi.org"}:
        match = re.fullmatch(r"/10\.48550/arxiv\.(\d{4}\.\d{4,5})(?:v\d+)?", parts.path, re.I)
        if match:
            return "https://arxiv.org/abs/" + match[1]
    if host == "aclanthology.org" and re.fullmatch(r"/[^/]+\.pdf", parts.path):
        return f"https://aclanthology.org/{parts.path[1:-4]}/"
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path, parts.query, ""))


def source_links(node):
    if isinstance(node, list):
        for child in node:
            yield from source_links(child)
    elif isinstance(node, dict):
        url = node.get("url")
        if isinstance(url, str) and url.startswith(("https://", "http://")):
            yield url, node.get("label") or node.get("title") or ""
        for child in node.values():
            yield from source_links(child)


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalized_text(value):
    return " ".join(str(value or "").split())


def author_name(value):
    parts = normalized_text(value).split(", ")
    if len(parts) == 2:
        return " ".join(reversed(parts))
    return normalized_text(value)


def named_fields(title, author="", date="", source=""):
    match = YEAR.search(normalized_text(date))
    return {
        "title": normalized_text(title),
        "first_author": author_name(author),
        "year": match[0] if match else "",
        "metadata_source": source,
    }


def lookup(key, label):
    if key in PDF_RECORDS:
        return named_fields(*PDF_RECORDS[key])
    if key.startswith("https://arxiv.org/abs/"):
        identifier = key.removeprefix("https://arxiv.org/abs/")
        paper_file = HERE.parent / "sources" / (identifier + ".json")
        if paper_file.exists():
            paper = read_json(paper_file)
            if paper.get("id") == identifier and paper.get("title") and paper.get("authors") and paper.get("date"):
                return named_fields(paper["title"], paper["authors"][0], paper["date"], key)

    response = requests.get(key, timeout=(6, 15), headers={"User-Agent": "Research bibliography metadata reader/1.0"})
    response.raise_for_status()
    if not response.headers.get("Content-Type", "").startswith(("text/html", "application/xhtml+xml")):
        return named_fields(label)
    soup = BeautifulSoup(response.content, "html.parser")
    metadata = {}
    for tag in soup.find_all("meta"):
        name = normalized_text(tag.get("name") or tag.get("property")).lower()
        value = normalized_text(tag.get("content"))
        if name and value:
            metadata.setdefault(name, value)

    def first(*names):
        return next((metadata[name] for name in names if name in metadata), "")

    title = first("citation_title", "dc.title", "dcterms.title", "og:title")
    if not title and soup.title:
        title = soup.title.get_text(" ", strip=True)
    if not title or title.lower() in {"just a moment...", "access denied", "error", "robot check"}:
        return named_fields(label)
    author = first("citation_author", "dc.creator", "dcterms.creator", "author")
    date = first("citation_publication_date", "citation_date", "dc.date.issued", "dcterms.issued",
                 "citation_online_date", "article:published_time")
    return named_fields(title, author, date, response.url)


def main():
    sources = {}
    for path in sorted(HERE.glob("*.json")):
        if path == OUTPUT:
            continue
        for url, label in source_links(read_json(path)):
            sources.setdefault(canonical_url(url), {}).setdefault(url, label)
    existing = read_json(OUTPUT) if OUTPUT.exists() else {}

    def resolve(item):
        key, mentions = item
        cached = existing.get(key, {})
        if cached.get("metadata_source") and cached.get("title"):
            fields = {name: cached.get(name, "") for name in ("title", "first_author", "year", "metadata_source")}
        else:
            label = next((label for label in mentions.values() if label), key)
            try:
                fields = lookup(key, label)
            except (requests.RequestException, OSError, ValueError) as exc:
                print(f"Could not verify {key}: {exc}")
                fields = named_fields(label)
        return key, {**fields, "url": next(iter(mentions)), "aliases": list(mentions)}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        entries = dict(pool.map(resolve, sorted(sources.items())))
    with NamedTemporaryFile(mode="w", dir=HERE, encoding="utf-8", delete=False) as temporary:
        json.dump(entries, temporary, indent=2, ensure_ascii=False)
        temporary.write("\n")
    Path(temporary.name).replace(OUTPUT)
    unresolved = [key for key, record in entries.items() if not record["metadata_source"]]
    print(f"{len(entries)} unique sources, {len(unresolved)} unverified.")
    for key in unresolved:
        print(key)


if __name__ == "__main__":
    main()
