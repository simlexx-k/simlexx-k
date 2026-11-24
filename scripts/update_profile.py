"""Refresh the GitHub project lists in the profile README."""

from datetime import datetime, timedelta, timezone
from html import escape
import json
import os
from pathlib import Path
import re
from urllib.parse import urlencode
from urllib.request import Request, urlopen


START = "<!-- BEGIN GITHUB PROJECTS -->"
END = "<!-- END GITHUB PROJECTS -->"
FEATURED_TOPIC = "profile-featured"
RECENT_DAYS = 90
RECENT_LIMIT = 5


def public_repositories(owner):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-readme",
    }
    if token := os.environ.get("GH_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"

    page = 1
    while True:
        query = urlencode({"type": "owner", "per_page": 100, "page": page})
        request = Request(f"https://api.github.com/users/{owner}/repos?{query}", headers=headers)
        with urlopen(request, timeout=20) as response:
            repositories = json.load(response)
            has_next_page = 'rel="next"' in response.headers.get("Link", "")

        if not isinstance(repositories, list):
            raise ValueError("GitHub returned an unexpected repository response")
        yield from repositories
        if not has_next_page:
            return
        page += 1


def markdown_text(value):
    text = escape(" ".join(value.split()), quote=False).replace("@", "&#64;")
    return re.sub(r"([\\`*_\[\]~])", r"\\\1", text)


def repository_entry(repo):
    heading = f"- **[{markdown_text(repo['name'])}]({repo['html_url']})**"
    if repo["language"]:
        heading += f" · {markdown_text(repo['language'])}"
    if repo["pushed_at"]:
        heading += f" · last push {repo['pushed_at'][:10]}"
    description = markdown_text(repo["description"] or "")
    return f"{heading}\\\n  {description}" if description else heading


def project_sections(repositories, profile_repo, today):
    available = sorted(
        (
            repo for repo in repositories
            if repo["visibility"] == "public"
            and repo["full_name"].casefold() != profile_repo.casefold()
            and repo["size"] > 0
            and not repo["archived"]
            and not repo["disabled"]
        ),
        key=lambda repo: (repo["pushed_at"] or "", repo["full_name"]),
        reverse=True,
    )
    featured = [repo for repo in available if FEATURED_TOPIC in repo["topics"]]
    cutoff = (today - timedelta(days=RECENT_DAYS)).isoformat()
    recent = [
        repo for repo in available
        if not repo["fork"]
        and FEATURED_TOPIC not in repo["topics"]
        and (repo["pushed_at"] or "")[:10] >= cutoff
    ][:RECENT_LIMIT]

    sections = []
    if featured:
        sections.append("## Featured projects\n\n" + "\n".join(map(repository_entry, featured)))
    if recent:
        sections.append("## Recent public work\n\n" + "\n".join(map(repository_entry, recent)))

    owner = profile_repo.split("/", 1)[0]
    sections.append(f"[Browse all public repositories](https://github.com/{owner}?tab=repositories)")
    return "\n\n".join(sections)


def replace_projects(readme, projects):
    if readme.count(START) != 1 or readme.count(END) != 1:
        raise ValueError("README must contain exactly one pair of GitHub project markers")
    before, _, rest = readme.partition(START)
    _, end, after = rest.partition(END)
    if not end:
        raise ValueError("GitHub project markers are out of order")
    return f"{before}{START}\n\n{projects}\n\n{END}{after}"


def main():
    profile_repo = os.environ.get("GITHUB_REPOSITORY", "simlexx-k/simlexx-k")
    owner = profile_repo.split("/", 1)[0]
    path = Path(__file__).resolve().parents[1] / "README.md"
    readme = path.read_text(encoding="utf-8")
    today = datetime.now(timezone.utc).date()
    projects = project_sections(public_repositories(owner), profile_repo, today)
    updated = replace_projects(readme, projects)
    if updated != readme:
        path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
