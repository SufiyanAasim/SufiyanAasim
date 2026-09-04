#!/usr/bin/env python3
"""Generate an auditable animated SVG from a user's real GitHub language data."""

from __future__ import annotations

import argparse
import html
import json
import os
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


API_ROOT = "https://api.github.com"
USER_AGENT = "SufiyanAasim-profile-language-card"
LANGUAGE_COLORS = {
    "Python": "#3776ab",
    "JavaScript": "#f7df1e",
    "TypeScript": "#3178c6",
    "C#": "#9b4f96",
    "Jupyter Notebook": "#f37626",
    "HTML": "#e34f26",
    "Java": "#ed8b00",
    "Shell": "#89e051",
    "C++": "#00599c",
    "C": "#a8b9cc",
    "Other": "#64748b",
}
FALLBACK_COLORS = ("#22d3ee", "#38bdf8", "#818cf8", "#a78bfa", "#f472b6")


class GitHubAPIError(RuntimeError):
    """Raised when GitHub data cannot be fetched or is unusable."""


def request_json(url: str, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": USER_AGENT,
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise GitHubAPIError(f"GitHub request failed for {url}: {exc}") from exc


def fetch_owned_repositories(username: str, token: str | None = None) -> list[dict[str, Any]]:
    repositories: list[dict[str, Any]] = []
    for page in range(1, 11):
        query = urllib.parse.urlencode(
            {"per_page": 100, "page": page, "type": "owner", "sort": "full_name"}
        )
        payload = request_json(f"{API_ROOT}/users/{urllib.parse.quote(username)}/repos?{query}", token)
        if not isinstance(payload, list):
            raise GitHubAPIError("GitHub repositories response was not a list")
        repositories.extend(payload)
        if len(payload) < 100:
            break
    return repositories


def eligible_repositories(
    repositories: Iterable[dict[str, Any]], username: str
) -> list[dict[str, Any]]:
    profile_name = username.casefold()
    return [
        repo
        for repo in repositories
        if not repo.get("fork")
        and not repo.get("archived")
        and not repo.get("private")
        and str(repo.get("name", "")).casefold() != profile_name
        and repo.get("languages_url")
    ]


def aggregate_language_bytes(
    repositories: Iterable[dict[str, Any]], token: str | None = None
) -> tuple[dict[str, int], int]:
    totals: defaultdict[str, int] = defaultdict(int)
    repository_count = 0
    for repository in repositories:
        payload = request_json(str(repository["languages_url"]), token)
        if not isinstance(payload, dict):
            raise GitHubAPIError(
                f"Languages response for {repository.get('full_name', repository.get('name'))} was not an object"
            )
        repository_count += 1
        for language, raw_bytes in payload.items():
            if isinstance(language, str) and isinstance(raw_bytes, int) and raw_bytes > 0:
                totals[language] += raw_bytes
    return dict(totals), repository_count


def summarize_languages(
    totals: dict[str, int], repository_count: int, limit: int = 5
) -> dict[str, Any]:
    positive = {name: count for name, count in totals.items() if count > 0}
    total_bytes = sum(positive.values())
    if total_bytes <= 0:
        raise GitHubAPIError("No public language data was available")

    ordered = sorted(positive.items(), key=lambda item: (-item[1], item[0].casefold()))
    top = ordered[:limit]
    other_bytes = total_bytes - sum(count for _, count in top)
    rows: list[dict[str, Any]] = []
    for index, (name, count) in enumerate(top):
        rows.append(
            {
                "name": name,
                "bytes": count,
                "percent": round(count * 100 / total_bytes, 1),
                "color": LANGUAGE_COLORS.get(name, FALLBACK_COLORS[index % len(FALLBACK_COLORS)]),
            }
        )
    displayed_other_percent = round(100.0 - sum(row["percent"] for row in rows), 1)
    rows.append(
        {
            "name": "Other",
            "bytes": other_bytes,
            "percent": displayed_other_percent,
            "color": LANGUAGE_COLORS["Other"],
        }
    )
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repository_count": repository_count,
        "total_bytes": total_bytes,
        "languages": rows,
    }


def render_svg(username: str, summary: dict[str, Any]) -> str:
    rows = summary["languages"]
    row_markup: list[str] = []
    for index, row in enumerate(rows):
        y = 104 + index * 39
        width = max(2, round(330 * float(row["percent"]) / 100))
        label = html.escape(str(row["name"]))
        percent = f"{float(row['percent']):.1f}%"
        color = html.escape(str(row["color"]))
        delay = index * 0.12
        row_markup.append(
            f'''    <g class="language-row" style="animation-delay:{delay:.2f}s">
      <text x="28" y="{y + 5}" fill="#e2e8f0" font-size="14" font-weight="700">{label}</text>
      <rect x="190" y="{y - 9}" width="330" height="15" rx="7.5" fill="#0f2a3b"/>
      <rect class="bar" x="190" y="{y - 9}" width="{width}" height="15" rx="7.5" fill="{color}" style="animation-delay:{delay:.2f}s"/>
      <circle class="endpoint" cx="{190 + width}" cy="{y - 1.5}" r="4" fill="{color}" style="animation-delay:{delay:.2f}s"/>
      <text class="percent" x="602" y="{y + 5}" text-anchor="end" fill="#a5f3fc" font-size="14" font-weight="700" style="animation-delay:{delay:.2f}s">{percent}</text>
    </g>'''
        )

    generated = html.escape(str(summary["generated_at"]).replace("+00:00", "Z"))
    repositories = int(summary["repository_count"])
    safe_username = html.escape(username)
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360" viewBox="0 0 640 360" role="img" aria-labelledby="title desc">
  <title id="title">{safe_username} most used GitHub languages</title>
  <desc id="desc">Real language-byte percentages aggregated from {repositories} public, owned, non-fork repositories</desc>
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#08111f"/><stop offset="1" stop-color="#071b2a"/></linearGradient>
    <linearGradient id="scan" x1="0" x2="1"><stop stop-color="#22d3ee" stop-opacity="0"/><stop offset=".5" stop-color="#67e8f9" stop-opacity=".55"/><stop offset="1" stop-color="#22d3ee" stop-opacity="0"/></linearGradient>
    <filter id="glow"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
  </defs>
  <style>
    text {{ font-family:Consolas,ui-monospace,monospace; }}
    .bar {{ transform-box:fill-box;transform-origin:left center;animation:grow 8s ease-out infinite; }}
    .endpoint {{ animation:node 8s ease-out infinite;filter:url(#glow); }}
    .percent,.language-row {{ animation:reveal 8s ease-out infinite; }}
    .scan {{ animation:scan 5s linear infinite; }}
    .signal {{ animation:signal 2.6s ease-in-out infinite; }}
    @keyframes grow {{ 0%,5%{{transform:scaleX(0);opacity:.3}}28%,88%{{transform:scaleX(1);opacity:1}}100%{{transform:scaleX(0);opacity:.2}} }}
    @keyframes node {{ 0%,5%{{opacity:0}}30%,88%{{opacity:1}}100%{{opacity:0}} }}
    @keyframes reveal {{ 0%,4%{{opacity:.2}}24%,90%{{opacity:1}}100%{{opacity:.2}} }}
    @keyframes scan {{ from{{transform:translateX(-560px)}}to{{transform:translateX(560px)}} }}
    @keyframes signal {{ 0%,100%{{opacity:.35}}50%{{opacity:1}} }}
    @media (prefers-reduced-motion:reduce){{.bar,.endpoint,.percent,.language-row,.scan,.signal{{animation:none!important}}}}
  </style>
  <rect x="1" y="1" width="638" height="358" rx="20" fill="url(#bg)" stroke="#164e63" stroke-width="2"/>
  <rect x="14" y="14" width="612" height="332" rx="14" fill="none" stroke="#0e7490" stroke-opacity=".35"/>
  <text x="28" y="40" fill="#f8fafc" font-size="18" font-weight="800">MOST USED LANGUAGES</text>
  <text x="28" y="63" fill="#67e8f9" font-size="11" letter-spacing="1.2">REAL PUBLIC-REPOSITORY TELEMETRY</text>
  <g class="signal"><circle cx="590" cy="35" r="5" fill="#22d3ee" filter="url(#glow)"/><text x="575" y="65" text-anchor="end" fill="#94a3b8" font-size="10">{repositories} REPOS</text></g>
  <clipPath id="content"><rect x="20" y="78" width="600" height="246" rx="10"/></clipPath>
  <g clip-path="url(#content)">
{chr(10).join(row_markup)}
    <rect class="scan" x="190" y="82" width="86" height="230" fill="url(#scan)" opacity=".28"/>
  </g>
  <text x="28" y="337" fill="#64748b" font-size="9">UPDATED {generated}</text>
  <text x="612" y="337" text-anchor="end" fill="#64748b" font-size="9">SHARE OF GITHUB LANGUAGE BYTES</text>
</svg>
'''


def write_artifacts(output_dir: Path, username: str, summary: dict[str, Any]) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(summary, indent=2, ensure_ascii=False) + "\n"
    svg = render_svg(username, summary)
    for filename, content in (("languages.json", payload), ("most-used-languages.svg", svg)):
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=output_dir, delete=False, prefix=f".{filename}."
        ) as handle:
            handle.write(content)
            temporary = Path(handle.name)
        temporary.replace(output_dir / filename)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", required=True, help="GitHub username to aggregate")
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    try:
        repositories = fetch_owned_repositories(args.username, token)
        eligible = eligible_repositories(repositories, args.username)
        totals, repository_count = aggregate_language_bytes(eligible, token)
        summary = summarize_languages(totals, repository_count)
        write_artifacts(args.output_dir, args.username, summary)
    except GitHubAPIError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(
        f"Generated language card for {args.username}: "
        f"{repository_count} repositories, {summary['total_bytes']} language bytes"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
