#!/usr/bin/env python3
"""Generate per-article assets (charts, mermaid diagrams, styled HTML).

Usage:
    python3 scripts/generate_article_assets.py --all
    python3 scripts/generate_article_assets.py --article 1
    python3 scripts/generate_article_assets.py --article 4 --charts-only
    python3 scripts/generate_article_assets.py --article 2 --html-only
"""

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

import markdown
from jinja2 import Environment, FileSystemLoader

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CHARTS_ROOT = PROJECT_ROOT / "output" / "charts"
OUTPUT_ROOT = PROJECT_ROOT / "output" / "articles"
TEMPLATE_DIR = PROJECT_ROOT / "scripts" / "templates"
MERMAID_CONFIG = PROJECT_ROOT / "scripts" / "mermaid-config.json"
ARTICLES_SRC = Path("/home/vince/Downloads/articles_substack_linkedin")
MERMAID_SRC = OUTPUT_ROOT / "mermaid"
MMDC_BIN = Path("/home/vince/.nvm/versions/node/v22.14.0/bin/mmdc")

# ---------------------------------------------------------------------------
# Article / asset mapping
# ---------------------------------------------------------------------------

#: Maps article number -> (chart_prefixes, mermaid_stems)
ARTICLE_ASSETS: dict[int, tuple[list[str], list[str]]] = {
    1:  (["01_pipeline_flow", "15_mc_vs_llm_comparison"], ["diagram-01-architecture"]),
    2:  (["02_economic_dashboard", "03_yield_curve", "04_indicators_table", "19_vintage_timeline"], []),
    3:  ([], ["diagram-03-graphrag"]),
    4:  (["12_belief_evolution", "13_vote_breakdown", "14_meeting_structure"], ["diagram-04-deliberation"]),
    5:  (["09_rate_distribution", "10_mc_agent_beliefs", "11_mc_summary_stats"], []),
    6:  ([], []),
    7:  ([], []),
    8:  (["15_mc_vs_llm_comparison"], []),
    9:  (["01_pipeline_flow", "18_service_dependency_dag"], []),
    10: ([], []),
    11: (["16_rate_trajectory", "17_backtest_accuracy"], []),
    12: (["05_agent_dot_plot", "06_hawk_dove_spectrum", "07_stance_distribution"], []),
    13: (["16_rate_trajectory"], []),
}

SLUGS: dict[int, str] = {
    1: "overview", 2: "point_in_time", 3: "graphrag", 4: "deliberation",
    5: "monte_carlo", 6: "beige_book", 7: "agent_framework", 8: "comparison",
    9: "infrastructure", 10: "dashboard", 11: "backtesting",
    12: "persona_factory", 13: "conclusion",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_best_chart_dir() -> Path | None:
    """Return the chart date-directory with the most PNGs."""
    if not CHARTS_ROOT.is_dir():
        return None
    best, best_count = None, 0
    for d in CHARTS_ROOT.iterdir():
        if d.is_dir():
            count = len(list(d.glob("*.png")))
            if count > best_count:
                best, best_count = d, count
    return best


def extract_title(md_text: str) -> str:
    """Extract the first H1 from markdown source."""
    for line in md_text.splitlines():
        m = re.match(r"^#\s+(.+)$", line.strip())
        if m:
            return m.group(1).strip()
    return "Untitled"


def find_article_md(article_num: int) -> Path | None:
    """Find the markdown source for a given article number."""
    slug = SLUGS.get(article_num)
    if not slug:
        return None
    pattern = f"substack_{article_num:02d}_{slug}.md"
    candidate = ARTICLES_SRC / pattern
    if candidate.exists():
        return candidate
    # Fallback: glob
    matches = list(ARTICLES_SRC.glob(f"substack_{article_num:02d}_*.md"))
    return matches[0] if matches else None


# ---------------------------------------------------------------------------
# Copy charts
# ---------------------------------------------------------------------------

def copy_charts(article_num: int, chart_dir: Path, out_dir: Path) -> list[str]:
    """Copy relevant chart PNGs to per-article charts/ directory.

    Returns list of relative paths (for HTML embedding).
    """
    prefixes, _ = ARTICLE_ASSETS.get(article_num, ([], []))
    if not prefixes:
        return []

    charts_out = out_dir / "charts"
    charts_out.mkdir(parents=True, exist_ok=True)

    copied: list[str] = []
    for prefix in prefixes:
        src = chart_dir / f"{prefix}.png"
        if src.exists():
            dst = charts_out / src.name
            shutil.copy2(src, dst)
            copied.append(f"charts/{src.name}")
            print(f"  [chart] {src.name}")
        else:
            print(f"  [chart] MISSING: {src.name}", file=sys.stderr)
    return copied


# ---------------------------------------------------------------------------
# Render mermaid diagrams
# ---------------------------------------------------------------------------

def render_mermaid(article_num: int, out_dir: Path) -> list[str]:
    """Render mermaid .mermaid files to PNG via mmdc.

    Returns list of relative paths.
    """
    _, mermaid_stems = ARTICLE_ASSETS.get(article_num, ([], []))
    if not mermaid_stems:
        return []

    charts_out = out_dir / "charts"
    charts_out.mkdir(parents=True, exist_ok=True)

    rendered: list[str] = []
    for stem in mermaid_stems:
        src = MERMAID_SRC / f"{stem}.mermaid"
        if not src.exists():
            # Fallback to legacy location
            src = ARTICLES_SRC / f"{stem}.mermaid"
        if not src.exists():
            print(f"  [mermaid] MISSING: {stem}.mermaid", file=sys.stderr)
            continue

        dst = charts_out / f"{stem}.png"
        cmd = [
            str(MMDC_BIN),
            "-i", str(src),
            "-o", str(dst),
            "-t", "dark",
            "-b", "#06090f",
            "-C", str(MERMAID_CONFIG),
            "-w", "1200",
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=60)
            rendered.append(f"charts/{dst.name}")
            print(f"  [mermaid] {dst.name}")
        except FileNotFoundError:
            print(f"  [mermaid] mmdc not found at {MMDC_BIN}", file=sys.stderr)
        except subprocess.CalledProcessError as exc:
            print(f"  [mermaid] FAILED {stem}: {exc.stderr.decode()[:200]}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print(f"  [mermaid] TIMEOUT rendering {stem}", file=sys.stderr)

    return rendered


# ---------------------------------------------------------------------------
# Generate HTML
# ---------------------------------------------------------------------------

def generate_html(article_num: int, out_dir: Path, images: list[str]) -> None:
    """Convert markdown to styled HTML via Jinja2 template."""
    md_path = find_article_md(article_num)
    if not md_path:
        print(f"  [html] No markdown source for article {article_num}", file=sys.stderr)
        return

    md_text = md_path.read_text(encoding="utf-8")
    title = extract_title(md_text)

    # Convert markdown to HTML
    extensions = ["fenced_code", "tables", "toc"]
    body = markdown.markdown(md_text, extensions=extensions)

    # Render via Jinja2
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=False)
    template = env.get_template("article.html.j2")
    html = template.render(
        article_num=article_num,
        title=title,
        body=body,
        images=images,
    )

    out_file = out_dir / f"article_{article_num:02d}.html"
    out_file.write_text(html, encoding="utf-8")
    print(f"  [html] {out_file.name} ({len(html):,} bytes)")


# ---------------------------------------------------------------------------
# Per-article pipeline
# ---------------------------------------------------------------------------

def process_article(
    article_num: int,
    chart_dir: Path | None,
    *,
    charts_only: bool = False,
    html_only: bool = False,
) -> None:
    """Run the full asset pipeline for one article."""
    slug = SLUGS.get(article_num, "unknown")
    label = f"{article_num:02d}"
    out_dir = OUTPUT_ROOT / label
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n--- Article {label}: {slug} ---")

    images: list[str] = []

    if not html_only:
        # Copy charts
        if chart_dir:
            images.extend(copy_charts(article_num, chart_dir, out_dir))
        else:
            print("  [chart] No chart directory found", file=sys.stderr)

        # Render mermaid diagrams
        images.extend(render_mermaid(article_num, out_dir))

    if not charts_only:
        # If html_only, gather existing image paths from output dir
        if html_only:
            charts_subdir = out_dir / "charts"
            if charts_subdir.is_dir():
                images = [f"charts/{p.name}" for p in sorted(charts_subdir.glob("*.png"))]
        generate_html(article_num, out_dir, images)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate per-article assets (charts, mermaid diagrams, styled HTML)."
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--all", action="store_true", help="Process all articles")
    group.add_argument("--article", type=int, metavar="N", help="Process a single article (1-13)")
    parser.add_argument("--charts-only", action="store_true", help="Only copy charts and render mermaid (no HTML)")
    parser.add_argument("--html-only", action="store_true", help="Only generate HTML (skip chart copy / mermaid)")

    args = parser.parse_args()

    if args.charts_only and args.html_only:
        parser.error("--charts-only and --html-only are mutually exclusive")

    chart_dir = find_best_chart_dir()
    if chart_dir:
        print(f"Using chart directory: {chart_dir}")
    else:
        print("Warning: no chart directory found under output/charts/", file=sys.stderr)

    if args.all:
        for num in sorted(ARTICLE_ASSETS.keys()):
            process_article(num, chart_dir, charts_only=args.charts_only, html_only=args.html_only)
    else:
        if args.article not in ARTICLE_ASSETS:
            parser.error(f"Article {args.article} not in range 1-13")
        process_article(args.article, chart_dir, charts_only=args.charts_only, html_only=args.html_only)

    print("\nDone.")


if __name__ == "__main__":
    main()
