# -*- coding: utf-8 -*-
"""
arminer.cli
============
CLI entry point.

Designed for researchers — simple, flexible, powerful.

Quick usage::

    # Scan 1 PDF with keywords (fastest way)
    arminer scan report.pdf --keywords "blockchain, smart contract, DeFi"

    # Scan with a keyword file (any format: txt, csv, xlsx, yaml)
    arminer scan report.pdf --dict keywords.txt
    arminer scan report.pdf --dict keywords.csv
    arminer scan report.pdf --dict keywords.xlsx

    # Use built-in template
    arminer scan report.pdf --topic blockchain

    # Init + run full project
    arminer init my_research --topic esg
    arminer run --stage all

    # Dictionary tools
    arminer dict stats --file keywords.csv
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import click
from loguru import logger
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, MofNCompleteColumn, TimeElapsedColumn

# Fix Windows encoding cross-platform
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

console = Console(legacy_windows=False)


def _setup_logging(level: str = "INFO") -> None:
    logger.remove()
    logger.add(
        sys.stderr, level=level,
        format="<green>{time:HH:mm:ss}</green> | <level>{level:<7}</level> | {message}",
    )


def _load_dictionary(dict_file=None, keywords=None, topic=None):
    """
    Load dictionary from ANY source — smart detect.

    Priority: --keywords > --dict file > --topic template > project config
    """
    from arminer.core.smart_mode import FlexibleDictionary

    if keywords:
        return FlexibleDictionary.from_string(keywords)

    if dict_file:
        return FlexibleDictionary.load(dict_file)

    if topic:
        templates_dir = Path(__file__).parent / "templates"
        template_file = templates_dir / f"{topic}_dictionary.yaml"
        if template_file.exists():
            return FlexibleDictionary.load(template_file)
        else:
            available = [f.stem.replace("_dictionary", "") for f in templates_dir.glob("*_dictionary.yaml")]
            console.print(f"[red]Topic '{topic}' not found. Available: {', '.join(available)}[/]")
            raise SystemExit(1)

    # Try loading from project
    try:
        from arminer.core.project import Project
        project = Project.load(".")
        return FlexibleDictionary.load(project.root / project.config.dictionary.file)
    except Exception:
        pass

    return None


# =====================================================================
# Main
# =====================================================================

@click.group()
@click.version_option(package_name="vn-annual-report-miner")
def main():
    """arminer -- Annual Report Miner for Vietnamese Listed Companies."""
    pass


# =====================================================================
# scan — Quick scan (core command, simplest UX)
# =====================================================================

def _export_dataset(df, output_path: Path, dict_name: str = "Dictionary"):
    """Export panel dataset to requested format."""
    import pandas as pd
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    ext = output_path.suffix.lower()

    if ext in (".xlsx", ".xls"):
        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            df.to_excel(writer, sheet_name="Panel_Data", index=False)
            num = df.select_dtypes(include=["number"])
            if not num.empty:
                desc = num.describe().T
                desc["N"] = num.count()
                desc["missing"] = num.isna().sum()
                cols_desc = [c for c in ["N", "mean", "std", "min", "25%", "50%", "75%", "max", "missing"] if c in desc.columns]
                desc[cols_desc].to_excel(writer, sheet_name="Descriptive_Stats")

                skip = [c for c in num.columns if c.startswith(("year_", "ind_"))]
                cols = [c for c in num.columns if c not in skip]
                if len(cols) > 1:
                    corr = num[cols].corr().round(4)
                    corr.to_excel(writer, sheet_name="Correlation")
    elif ext == ".csv":
        df.to_csv(output_path, index=False, encoding="utf-8-sig")
    elif ext in (".dta", ".stata"):
        sdf = df.select_dtypes(include=["number", "object"]).copy()
        sdf.columns = [c.replace(" ", "_").replace("-", "_")[:32] for c in sdf.columns]
        try:
            sdf.to_stata(output_path, write_index=False, version=118)
        except Exception:
            fallback = output_path.with_suffix(".csv")
            df.to_csv(fallback, index=False, encoding="utf-8-sig")
            console.print(f"[yellow]Stata export fallback to CSV: {fallback}[/]")
    elif ext in (".parquet", ".pq"):
        df.to_parquet(output_path, index=False, engine="pyarrow")
    else:
        output_path = output_path.with_suffix(".csv")
        df.to_csv(output_path, index=False, encoding="utf-8-sig")

    console.print(f"\n[bold green]Exported:[/] [cyan]{output_path}[/] ({len(df)} rows, {len(df.columns)} variables)")


def _scan_single_file(pdf_file: Path, flex_dict, topic, fuzzy, threshold, output=None):
    """Scan a single PDF or text file."""
    import pandas as pd
    from arminer.mining.matcher import GenericFuzzyMatcher
    from arminer.core.smart_mode import SmartVariableCalculator
    from arminer.data.pdf_source import PDFSource

    console.print(f"[cyan]Scanning:[/] {pdf_file}")
    text = ""
    n_pages = 1

    if pdf_file.suffix.lower() == ".pdf":
        try:
            import fitz
            doc = fitz.open(pdf_file)
            text = "\n".join(page.get_text() for page in doc)
            n_pages = len(doc)
            doc.close()
        except Exception as e:
            console.print(f"[red]Cannot read PDF: {e}[/]")
            raise SystemExit(1)
    else:
        try:
            text = pdf_file.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            console.print(f"[red]Cannot read text file: {e}[/]")
            raise SystemExit(1)

    core_dict = flex_dict.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict, threshold=threshold)
    matches = matcher.search(text, use_fuzzy=fuzzy)
    summary = matcher.get_summary(matches)
    total_words = len(text.split())

    calc = SmartVariableCalculator()
    variables = calc.calculate_all(
        matches, total_words,
        category_names=flex_dict.categories,
        topic_prefix=topic or "topic",
        classification_rules=flex_dict.classification_rules,
    )

    console.print()
    stats_lines = [
        f"[bold]File:[/] {pdf_file.name}",
        f"[bold]Pages:[/] {n_pages}   [bold]Words:[/] {total_words:,}",
        f"[bold]Dictionary:[/] {flex_dict.name} ({len(flex_dict)} keywords)",
        "",
    ]

    var_table = Table(show_header=True, header_style="bold cyan", box=None, pad_edge=False)
    var_table.add_column("Variable", style="white")
    var_table.add_column("Value", justify="right", style="green")

    for name, val in variables.items():
        if name in ("total_words", "keyword_top5"):
            continue
        display_val = f"{val}" if isinstance(val, int) else f"{val:.4f}"
        var_table.add_row(name, display_val)

    console.print(Panel.fit(
        "\n".join(stats_lines),
        title="[bold]Scan Results[/]",
        border_style="green",
    ))
    console.print(var_table)

    if summary["keywords_found"]:
        console.print(f"\n[bold]Keywords found ({summary['unique_keywords']}):[/]")
        for kw in sorted(summary["keywords_found"]):
            freq = sum(1 for m in matches if m.get("keyword_canonical") == kw)
            console.print(f"  [cyan]{kw}[/] x{freq}")

    if summary.get("by_category") and len(summary["by_category"]) > 1:
        console.print()
        cat_table = Table(title="By Category", show_lines=False)
        cat_table.add_column("Category", style="cyan")
        cat_table.add_column("Matches", justify="right", style="green")
        for cat, count in sorted(summary["by_category"].items()):
            cat_table.add_row(cat, str(count))
        console.print(cat_table)

    if output:
        parsed = PDFSource.parse_filename(pdf_file)
        row = {
            "ticker": parsed[0] if parsed else None,
            "year": parsed[1] if parsed else None,
            "file": pdf_file.name,
            "pages": n_pages,
            **variables,
        }
        df = pd.DataFrame([row])
        _export_dataset(df, Path(output), flex_dict.name)


def _scan_directory(dir_path: Path, flex_dict, topic, fuzzy, threshold, output=None, limit=None):
    """Scan a whole directory of PDFs and/or TXT files."""
    import pandas as pd
    from arminer.data.pdf_source import PDFSource
    from arminer.mining.matcher import GenericFuzzyMatcher
    from arminer.core.smart_mode import SmartVariableCalculator

    supported_exts = {".pdf", ".txt"}
    files = sorted([f for f in dir_path.rglob("*") if f.is_file() and f.suffix.lower() in supported_exts])
    if limit:
        files = files[:limit]

    if not files:
        console.print(f"[yellow]No PDF or TXT files found in {dir_path}[/]")
        return

    console.print(f"[cyan]Scanning folder:[/] {dir_path} ({len(files)} files)")
    console.print(f"[cyan]Dictionary:[/] {flex_dict.name} ({len(flex_dict)} keywords, {len(flex_dict.categories)} categories)")

    core_dict = flex_dict.to_core_dictionary()
    matcher = GenericFuzzyMatcher(dictionary=core_dict, threshold=threshold)
    calc = SmartVariableCalculator()

    rows = []
    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"),
        BarColumn(bar_width=40), MofNCompleteColumn(),
        TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("Mining...", total=len(files))
        for f in files:
            text = ""
            n_pages = 1
            if f.suffix.lower() == ".pdf":
                try:
                    import fitz
                    doc = fitz.open(f)
                    text = "\n".join(page.get_text() for page in doc)
                    n_pages = len(doc)
                    doc.close()
                except Exception as e:
                    logger.warning(f"Failed reading {f.name}: {e}")
            else:
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except Exception as e:
                    logger.warning(f"Failed reading {f.name}: {e}")

            words = text.split()
            total_words = len(words)
            matches = matcher.search(text, use_fuzzy=fuzzy) if total_words > 0 else []

            variables = calc.calculate_all(
                matches, total_words,
                category_names=flex_dict.categories,
                topic_prefix=topic or "topic",
                classification_rules=flex_dict.classification_rules,
            )

            parsed = PDFSource.parse_filename(f)
            row = {
                "ticker": parsed[0] if parsed else None,
                "year": parsed[1] if parsed else None,
                "file": f.name,
                "pages": n_pages,
                **variables,
            }
            rows.append(row)
            progress.advance(task)

    if not rows:
        return

    df = pd.DataFrame(rows)
    first_cols = [c for c in ["ticker", "year", "file", "pages"] if c in df.columns]
    other_cols = [c for c in df.columns if c not in first_cols]
    df = df[first_cols + other_cols]

    p_name = (topic or "topic").lower()
    freq_col = f"{p_name}_frequency"
    div_col = f"{p_name}_diversity"
    score_col = f"{p_name}_score"

    if freq_col in df.columns:
        df_sorted = df.sort_values(by=freq_col, ascending=False)
    else:
        df_sorted = df

    console.print()
    table = Table(title=f"Scan Summary (Top 15 of {len(df)} files)", show_lines=False)
    table.add_column("Ticker", style="cyan bold")
    table.add_column("Year", justify="center")
    table.add_column("File", max_width=32)
    table.add_column("Words", justify="right")
    table.add_column("Freq", justify="right", style="green bold")
    table.add_column("Diversity", justify="right", style="yellow")
    table.add_column("Score", justify="right", style="magenta")

    for _, r in df_sorted.head(15).iterrows():
        table.add_row(
            str(r.get("ticker") or "-"),
            str(r.get("year") or "-"),
            str(r.get("file", "?")),
            f"{int(r.get('total_words', 0)):,}",
            str(int(r.get(freq_col, 0))),
            str(int(r.get(div_col, 0))),
            f"{float(r.get(score_col, 0.0)):.4f}",
        )
    console.print(table)

    total_hits = df[freq_col].sum() if freq_col in df.columns else 0
    firms_hit = (df[freq_col] > 0).sum() if freq_col in df.columns else 0
    console.print(f"\n[bold]Total files:[/] {len(df)} | [bold]Files with hits:[/] {firms_hit} | [bold]Total keyword mentions:[/] {int(total_hits)}")

    # Default to Excel if not provided
    out_target = Path(output) if output else Path("scan_results.xlsx")
    _export_dataset(df, out_target, flex_dict.name)


@main.command()
@click.argument("target", type=click.Path(exists=True))
@click.option("--keywords", "-k", default=None,
              help='Keywords inline: "blockchain, smart contract, DeFi"')
@click.option("--dict", "dict_file", default=None,
              help="Keyword file: .txt, .csv, .xlsx, .yaml")
@click.option("--topic", "-t", default=None,
              help="Built-in topic: blockchain, esg, fintech")
@click.option("--output", "-o", default=None,
              help="Output file (.xlsx, .csv, .dta, .parquet). Default: scan_results.xlsx")
@click.option("--fuzzy/--no-fuzzy", default=True,
              help="Enable fuzzy matching (default: on)")
@click.option("--threshold", default=85, help="Fuzzy threshold 0-100")
@click.option("--limit", type=int, default=None, help="Limit number of files to scan")
def scan(target, keywords, dict_file, topic, output, fuzzy, threshold, limit):
    """
    Scan report(s) — the fastest way to mine annual reports.

    TARGET can be 1 file (PDF/TXT) or an entire directory.

    \b
    Examples:
      arminer scan report.pdf -k "blockchain, smart contract"
      arminer scan report.pdf --dict keywords.txt
      arminer scan ./reports/ --dict keywords.xlsx -o results.xlsx
      arminer scan ./data/ocr/ --topic esg -o panel_data.dta
    """
    _setup_logging("WARNING")

    flex_dict = _load_dictionary(dict_file, keywords, topic)
    if not flex_dict or len(flex_dict) == 0:
        console.print("[red]No keywords provided. Use --keywords, --dict, or --topic[/]")
        console.print("[dim]Examples:[/]")
        console.print('  arminer scan report.pdf -k "blockchain, smart contract"')
        console.print("  arminer scan report.pdf --dict keywords.txt")
        console.print("  arminer scan ./reports/ --dict keywords.csv -o results.xlsx")
        console.print("  arminer scan ./reports/ --topic blockchain")
        raise SystemExit(1)

    target_path = Path(target)
    if target_path.is_file():
        _scan_single_file(target_path, flex_dict, topic, fuzzy, threshold, output)
    elif target_path.is_dir():
        _scan_directory(target_path, flex_dict, topic, fuzzy, threshold, output, limit)
    else:
        console.print(f"[red]Invalid target: {target}[/]")
        raise SystemExit(1)


# =====================================================================
# init
# =====================================================================

@main.command()
@click.argument("directory", default=".")
@click.option("--topic", "-t",
              type=click.Choice(["blank", "blockchain", "esg", "fintech"]),
              default="blank", help="Built-in dictionary template")
@click.option("--name", "-n", default=None, help="Project name")
def init(directory, topic, name):
    """Create a new research project."""
    from arminer.core.project import Project
    _setup_logging()

    template = topic if topic != "blank" else "blank"
    project = Project.init(directory, template=template, project_name=name)

    console.print()
    console.print(Panel.fit(
        f"[bold green]Project '{project.config.project_name}' created![/]\n\n"
        f"Location: [cyan]{project.root}[/]\n"
        f"Template: [yellow]{topic}[/]\n\n"
        f"[dim]Next steps:[/]\n"
        f"  1. Add keywords: edit [bold]dictionary.yaml[/]\n"
        f"     Or use: .txt, .csv, .xlsx (any format)\n"
        f"  2. Place PDFs in [bold]data/pdfs/[/]\n"
        f"  3. Run: [bold cyan]arminer run --stage all[/]",
        title="arminer",
        border_style="green",
    ))


# =====================================================================
# run
# =====================================================================

@main.command()
@click.option("--stage", "-s",
              type=click.Choice(["ocr", "mining", "classify", "export", "all"]),
              required=True)
@click.option("--dict", "dict_file", default=None,
              help="Keyword file (overrides project config)")
@click.option("--keywords", "-k", default=None,
              help="Keywords inline (overrides everything)")
@click.option("--topic", "-t", default=None,
              help="Built-in topic template")
@click.option("--limit", type=int, default=None)
@click.option("--log-level", default="INFO")
def run(stage, dict_file, keywords, topic, limit, log_level):
    """Run the processing pipeline."""
    from arminer.core.project import Project
    from arminer.core.smart_mode import FlexibleDictionary

    _setup_logging(log_level)

    try:
        project = Project.load(".")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        raise SystemExit(1)

    # Load dictionary (flexible)
    flex_dict = _load_dictionary(dict_file, keywords, topic)
    if flex_dict is None:
        try:
            flex_dict = FlexibleDictionary.load(
                project.root / project.config.dictionary.file
            )
        except Exception as e:
            console.print(f"[red]No dictionary: {e}[/]")
            raise SystemExit(1)

    console.print(Panel.fit(
        f"[bold]Project:[/] {project.config.project_name}\n"
        f"[bold]Stage:[/] {stage}\n"
        f"[bold]Dictionary:[/] {flex_dict.name} ({len(flex_dict)} keywords)\n"
        f"[bold]Limit:[/] {limit or 'all'}",
        title="Running Pipeline",
        border_style="blue",
    ))

    stages = ["ocr", "mining", "classify", "export"] if stage == "all" else [stage]

    for s in stages:
        console.print(f"\n[bold cyan]>> {s.upper()}[/]")
        if s == "mining":
            _run_mining(project, flex_dict, limit)
        elif s == "ocr":
            _run_ocr(project, limit)
        elif s == "export":
            _run_export(project, flex_dict)
        else:
            console.print(f"[yellow]Stage '{s}' — processing...[/]")

    console.print("\n[bold green]Pipeline completed![/]")


def _run_mining(project, flex_dict, limit=None):
    """Run text mining stage."""
    import pandas as pd
    from arminer.mining.matcher import GenericFuzzyMatcher
    from arminer.core.smart_mode import SmartVariableCalculator
    from arminer.data.pdf_source import PDFSource

    core_dict = flex_dict.to_core_dictionary()
    matcher = GenericFuzzyMatcher(
        dictionary=core_dict,
        threshold=project.config.dictionary.fuzzy_threshold,
    )
    calc = SmartVariableCalculator()

    ocr_dir = project.root / "data" / "ocr_output"
    text_files = sorted(ocr_dir.rglob("*.txt"))
    if limit:
        text_files = text_files[:limit]

    if not text_files:
        console.print("[yellow]No OCR text files found in data/ocr_output/[/]")
        return

    rows = []
    with Progress(
        SpinnerColumn(), TextColumn("{task.description}"),
        BarColumn(bar_width=40), MofNCompleteColumn(),
        TimeElapsedColumn(), console=console,
    ) as progress:
        task = progress.add_task("Mining...", total=len(text_files))
        for tf in text_files:
            text = tf.read_text(encoding="utf-8", errors="replace")
            matches = matcher.search(text, use_fuzzy=True)
            total_words = len(text.split())
            variables = calc.calculate_all(
                matches, total_words,
                category_names=flex_dict.categories,
                topic_prefix="topic",
                classification_rules=flex_dict.classification_rules,
            )
            parsed = PDFSource.parse_filename(tf.parent if tf.name == "text.txt" else tf)
            row = {
                "ticker": parsed[0] if parsed else None,
                "year": parsed[1] if parsed else None,
                "file": str(tf.relative_to(project.root)),
                **variables,
            }
            rows.append(row)
            progress.advance(task)

    df = pd.DataFrame(rows)
    first_cols = [c for c in ["ticker", "year", "file"] if c in df.columns]
    other_cols = [c for c in df.columns if c not in first_cols]
    df = df[first_cols + other_cols]

    # Save intermediate mining results
    data_dir = project.root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(data_dir / "mining_results.csv", index=False, encoding="utf-8-sig")

    # Show summary
    table = Table(title=f"Mining Results (Top 20 / {len(rows)} reports)", show_lines=False)
    table.add_column("Ticker", style="cyan bold")
    table.add_column("Year", justify="center")
    table.add_column("File", style="dim", max_width=30)
    table.add_column("Words", justify="right")
    table.add_column("Freq", justify="right", style="green bold")
    table.add_column("Div", justify="right", style="yellow")
    table.add_column("Score", justify="right", style="magenta")

    for _, r in df.head(20).iterrows():
        table.add_row(
            str(r.get("ticker") or "-"),
            str(r.get("year") or "-"),
            str(r.get("file", "?")),
            f"{int(r.get('total_words', 0)):,}",
            str(int(r.get("topic_frequency", 0))),
            str(int(r.get("topic_diversity", 0))),
            f"{float(r.get('topic_score', 0.0)):.4f}",
        )
    console.print(table)
    if len(rows) > 20:
        console.print(f"[dim]... and {len(rows) - 20} more[/]")

    total_freq = int(df["topic_frequency"].sum()) if "topic_frequency" in df.columns else 0
    console.print(f"\n[bold]{len(rows)} reports, {total_freq} total keyword mentions[/]")
    console.print(f"[green]Saved: data/mining_results.csv[/]")


def _run_ocr(project, limit=None):
    """Run OCR stage."""
    pdf_dir = project.pdf_dir
    if not pdf_dir.exists():
        console.print(f"[yellow]PDF dir not found: {pdf_dir}[/]")
        return

    pdfs = sorted(pdf_dir.rglob("*.pdf"))
    if limit:
        pdfs = pdfs[:limit]
    if not pdfs:
        console.print("[yellow]No PDFs found.[/]")
        return

    console.print(f"Found {len(pdfs)} PDFs")

    try:
        from arminer.ocr.engine import OCREngine
        engine = OCREngine()
        ocr_out = project.root / "data" / "ocr_output"

        with Progress(
            SpinnerColumn(), TextColumn("{task.description}"),
            BarColumn(bar_width=40), MofNCompleteColumn(),
            TimeElapsedColumn(), console=console,
        ) as progress:
            task = progress.add_task("OCR...", total=len(pdfs))
            for pdf in pdfs:
                text = engine.extract_text(pdf)
                out_file = ocr_out / pdf.stem / "text.txt"
                out_file.parent.mkdir(parents=True, exist_ok=True)
                out_file.write_text(text, encoding="utf-8")
                progress.advance(task)

        console.print(f"[green]OCR done: {len(pdfs)} files[/]")
    except ImportError:
        console.print("[red]OCR deps missing. pip install vn-annual-report-miner[ocr][/]")


def _run_export(project, flex_dict=None):
    """Export results to research-ready formats."""
    import pandas as pd
    from arminer.core.smart_mode import ResearchOutputGenerator

    mining_file = project.root / "data" / "mining_results.csv"
    if not mining_file.exists():
        console.print("[yellow]No mining results found. Run 'arminer run -s mining' first.[/]")
        return

    df = pd.read_csv(mining_file)
    console.print(f"[cyan]Generating complete research output package ({len(df)} rows)...[/]")

    # Check for financial data merge
    fin_file = project.root / "data" / "financial_data.csv"
    if fin_file.exists():
        try:
            fin_df = pd.read_csv(fin_file)
            if "ticker" in fin_df.columns and "year" in fin_df.columns:
                df = pd.merge(df, fin_df, on=["ticker", "year"], how="left")
                console.print(f"[green]Merged financial controls: {len(fin_df.columns)-2} indicators[/]")
        except Exception as e:
            logger.warning(f"Could not merge financial data: {e}")

    gen = ResearchOutputGenerator(project.output_dir)
    outputs = gen.generate_all(df)

    console.print()
    out_table = Table(title="Generated Research Outputs", show_lines=False)
    out_table.add_column("Output File", style="cyan bold")
    out_table.add_column("Format", style="yellow")
    out_table.add_column("Size", justify="right", style="green")

    for name, p in outputs.items():
        if p and p.exists():
            sz = f"{p.stat().st_size / 1024:.1f} KB"
            out_table.add_row(p.name, p.suffix.upper().replace(".", ""), sz)

    console.print(out_table)
    console.print(f"\n[bold green]All research outputs ready at:[/] [cyan]{project.output_dir}[/]")


# =====================================================================
# dict — Dictionary tools
# =====================================================================

@main.group("dict")
def dict_cmd():
    """Dictionary management tools."""
    pass


@dict_cmd.command("stats")
@click.option("--file", "dict_file", default=None,
              help="Dictionary file (.txt, .csv, .xlsx, .yaml)")
@click.option("--topic", "-t", default=None, help="Built-in topic")
def dict_stats(dict_file, topic):
    """Show dictionary statistics."""
    _setup_logging("WARNING")

    flex_dict = _load_dictionary(dict_file, topic=topic)
    if not flex_dict:
        console.print("[red]No dictionary specified.[/]")
        raise SystemExit(1)

    stats = flex_dict.stats()

    console.print(Panel.fit(
        f"[bold]{stats['name']}[/]\n\n"
        f"Total keywords:     [green]{stats['total_keywords']}[/]\n"
        f"With variants:      [green]{stats['total_with_variants']}[/]\n"
        f"Exclusions:         [red]{stats['exclusions']}[/]",
        title="Dictionary Stats",
        border_style="cyan",
    ))

    if stats["categories"]:
        cat_table = Table(title="Categories")
        cat_table.add_column("Category", style="cyan")
        cat_table.add_column("Keywords", justify="right", style="green")
        for name, count in stats["categories"].items():
            cat_table.add_row(name, str(count))
        console.print(cat_table)


@dict_cmd.command("validate")
@click.option("--file", "dict_file", default=None)
@click.option("--topic", "-t", default=None)
def dict_validate(dict_file, topic):
    """Validate a dictionary file."""
    _setup_logging("WARNING")
    try:
        d = _load_dictionary(dict_file, topic=topic)
        if d:
            console.print(f"[green]Valid! {len(d)} keywords loaded.[/]")
        else:
            console.print("[red]No dictionary found.[/]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/]")
        raise SystemExit(1)


@dict_cmd.command("list")
def dict_list():
    """List built-in dictionary templates."""
    _setup_logging("WARNING")

    templates_dir = Path(__file__).parent / "templates"
    files = sorted(templates_dir.glob("*_dictionary.yaml"))

    table = Table(title="Built-in Templates")
    table.add_column("Topic", style="cyan")
    table.add_column("File", style="dim")

    for f in files:
        topic = f.stem.replace("_dictionary", "")
        table.add_row(topic, f.name)

    console.print(table)
    console.print("\n[dim]Use with: arminer scan report.pdf --topic <name>[/]")


# =====================================================================
# financial — Financial data integration (vnfinancialdata)
# =====================================================================

@main.group("financial")
def financial_cmd():
    """Financial data tools (vnfinancialdata integration).

    \b
    Fetch financial indicators (ROA, ROE, Size, Leverage) and merge
    with mining results to build research-ready panel data.

    Requires: pip install vn-annual-report-miner[financial]
    """
    pass


@financial_cmd.command("fetch")
@click.option("--tickers", "-t", required=True,
              help='Comma-separated tickers: "VCB,FPT,MBB" or "all" for project tickers')
@click.option("--years", "-y", required=True,
              help='Year range: "2014-2024" or comma-separated: "2020,2021,2022"')
@click.option("--output", "-o", default="financial_data.csv",
              help="Output file (.csv, .xlsx). Default: financial_data.csv")
@click.option("--variables", default=None,
              help='Variables to fetch (comma-separated). Default: total_assets,total_equity,total_debt,revenue,net_income')
@click.option("--ratios", default=None,
              help='Ratios to compute (comma-separated). Default: roa,roe,size,leverage')
def financial_fetch(tickers, years, output, variables, ratios):
    """Fetch financial data from vnfinancialdata and compute ratios.

    \b
    Examples:
      arminer financial fetch -t VCB,FPT,MBB -y 2014-2024
      arminer financial fetch -t all -y 2018-2023 -o data/financials.xlsx
    """
    _setup_logging("WARNING")

    # Parse tickers
    if tickers.lower() == "all":
        try:
            from arminer.core.project import Project
            project = Project.load(".")
            mining_file = project.root / "data" / "mining_results.csv"
            if mining_file.exists():
                import pandas as pd
                df = pd.read_csv(mining_file)
                ticker_list = sorted(df["ticker"].dropna().unique().tolist())
                console.print(f"[cyan]Auto-detected {len(ticker_list)} tickers from mining_results.csv[/]")
            else:
                console.print("[red]No mining_results.csv found. Specify tickers manually.[/]")
                raise SystemExit(1)
        except Exception as e:
            console.print(f"[red]Cannot auto-detect tickers: {e}[/]")
            raise SystemExit(1)
    else:
        ticker_list = [t.strip().upper() for t in tickers.split(",")]

    # Parse years
    if "-" in years:
        parts = years.split("-")
        year_list = list(range(int(parts[0]), int(parts[1]) + 1))
    else:
        year_list = [int(y.strip()) for y in years.split(",")]

    # Parse optional variables/ratios
    var_list = [v.strip() for v in variables.split(",")] if variables else None
    ratio_list = [r.strip() for r in ratios.split(",")] if ratios else None

    console.print(Panel.fit(
        f"[bold]Tickers:[/] {len(ticker_list)} ({', '.join(ticker_list[:10])}{'...' if len(ticker_list) > 10 else ''})\n"
        f"[bold]Years:[/] {min(year_list)}-{max(year_list)} ({len(year_list)} years)\n"
        f"[bold]Total observations:[/] {len(ticker_list) * len(year_list)}\n"
        f"[bold]Output:[/] {output}",
        title="Financial Data Fetch",
        border_style="blue",
    ))

    try:
        from arminer.data.financial import FinancialDataProvider
        provider = FinancialDataProvider()
    except ImportError:
        console.print(
            "[red]vnfinancialdata is not installed.[/]\n"
            "[dim]Install with: pip install vn-annual-report-miner[financial][/]"
        )
        raise SystemExit(1)

    total = len(ticker_list) * len(year_list)
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=40),
        MofNCompleteColumn(),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Fetching...", total=total)

        def _on_progress(ticker, year):
            progress.update(task, description=f"Fetching {ticker}/{year}")
            progress.advance(task)

        try:
            df = provider.build_panel(
                tickers=ticker_list,
                years=year_list,
                variables=var_list,
                auto_ratios=ratio_list,
                progress_callback=_on_progress,
            )
        except ImportError:
            console.print(
                "\n[red]vnfinancialdata is not installed.[/]\n"
                "[dim]Install with: pip install vn-annual-report-miner[financial][/]"
            )
            raise SystemExit(1)

    if df.empty:
        console.print("[yellow]No data returned. Check tickers and year range.[/]")
        return

    # Show summary
    table = Table(title=f"Financial Panel (Top 15 / {len(df)} obs)", show_lines=False)
    table.add_column("Ticker", style="cyan bold")
    table.add_column("Year", justify="center")
    for col in df.columns:
        if col not in ("ticker", "year"):
            table.add_column(col, justify="right", style="green")

    for _, r in df.head(15).iterrows():
        row_vals = [str(r.get("ticker", "-")), str(r.get("year", "-"))]
        for col in df.columns:
            if col not in ("ticker", "year"):
                val = r.get(col)
                if val is None or (isinstance(val, float) and val != val):
                    row_vals.append("-")
                elif isinstance(val, float):
                    row_vals.append(f"{val:.4f}" if abs(val) < 100 else f"{val:,.0f}")
                else:
                    row_vals.append(str(val))
        table.add_row(*row_vals)
    console.print(table)

    # Non-null stats
    non_null = df.drop(columns=["ticker", "year"], errors="ignore").notna().sum()
    console.print(f"\n[bold]Data coverage:[/]")
    for col, cnt in non_null.items():
        pct = cnt / len(df) * 100
        style = "green" if pct > 80 else "yellow" if pct > 50 else "red"
        console.print(f"  [{style}]{col}: {int(cnt)}/{len(df)} ({pct:.0f}%)[/]")

    # Export
    output_path = Path(output)
    _export_dataset(df, output_path, "Financial")


@financial_cmd.command("merge")
@click.option("--financial-file", "-f", default="financial_data.csv",
              help="Financial data CSV file. Default: financial_data.csv")
@click.option("--mining-file", "-m", default=None,
              help="Mining results CSV. Default: data/mining_results.csv")
@click.option("--output", "-o", default="panel_data.xlsx",
              help="Merged output file. Default: panel_data.xlsx")
def financial_merge(financial_file, mining_file, output):
    """Merge financial data with mining results into panel data.

    \b
    Examples:
      arminer financial merge
      arminer financial merge -f financials.csv -o panel.xlsx
    """
    import pandas as pd
    _setup_logging("WARNING")

    # Find mining file
    if mining_file is None:
        try:
            from arminer.core.project import Project
            project = Project.load(".")
            mining_file = str(project.root / "data" / "mining_results.csv")
        except Exception:
            mining_file = "mining_results.csv"

    mining_path = Path(mining_file)
    fin_path = Path(financial_file)

    if not mining_path.exists():
        console.print(f"[red]Mining results not found: {mining_path}[/]")
        console.print("[dim]Run 'arminer run -s mining' or 'arminer scan' first.[/]")
        raise SystemExit(1)
    if not fin_path.exists():
        console.print(f"[red]Financial data not found: {fin_path}[/]")
        console.print("[dim]Run 'arminer financial fetch' first.[/]")
        raise SystemExit(1)

    df_mining = pd.read_csv(mining_path)
    df_fin = pd.read_csv(fin_path)

    console.print(f"[cyan]Mining data:[/] {len(df_mining)} rows, {len(df_mining.columns)} cols")
    console.print(f"[cyan]Financial data:[/] {len(df_fin)} rows, {len(df_fin.columns)} cols")

    # Merge on ticker + year
    merged = pd.merge(df_mining, df_fin, on=["ticker", "year"], how="left",
                       suffixes=("", "_fin"))

    n_matched = merged.drop(columns=["ticker", "year"], errors="ignore").notna().any(axis=1).sum()
    console.print(f"[green]Merged: {len(merged)} rows ({n_matched} with financial data)[/]")

    _export_dataset(merged, Path(output), "Panel Data")


# =====================================================================
# report
# =====================================================================

@main.command()
def report():
    """Show project report."""
    _setup_logging("WARNING")
    try:
        from arminer.core.project import Project
        project = Project.load(".")
    except FileNotFoundError as e:
        console.print(f"[red]{e}[/]")
        raise SystemExit(1)

    console.print(Panel.fit(
        f"[bold]{project.config.project_name}[/]\n{project.config.description}",
        title="Project Report", border_style="green",
    ))

    output_files = list(project.output_dir.glob("*"))
    if output_files:
        table = Table(title="Output Files")
        table.add_column("File", style="cyan")
        table.add_column("Size", justify="right")
        for f in output_files:
            sz = f.stat().st_size
            table.add_row(f.name, f"{sz/1024:.1f} KB" if sz > 1024 else f"{sz} B")
        console.print(table)
    else:
        console.print("[yellow]No output yet. Run: arminer run --stage all[/]")


# =====================================================================
# ui — Interactive Web Studio
# =====================================================================

@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind server to.")
@click.option("--port", "-p", default=8000, type=int, help="Port to bind server to.")
@click.option("--no-browser", is_flag=True, default=False, help="Do not open browser automatically.")
def ui(host, port, no_browser):
    """Launch interactive arminer Web Studio (FastAPI + Modern Web UI)."""
    from arminer.ui.server import run_ui_server
    run_ui_server(host=host, port=port, open_browser=not no_browser)


@main.command()
@click.option("--host", default="127.0.0.1", help="Host to bind server to.")
@click.option("--port", "-p", default=8000, type=int, help="Port to bind server to.")
@click.option("--no-browser", is_flag=True, default=False, help="Do not open browser automatically.")
def studio(host, port, no_browser):
    """Launch interactive arminer Web Studio (alias for `arminer ui`)."""
    from arminer.ui.server import run_ui_server
    run_ui_server(host=host, port=port, open_browser=not no_browser)


# =====================================================================
# catalog — Explore Zenodo & Local reports
# =====================================================================

@main.group("catalog")
def catalog_cmd():
    """Explore the unified repository of 14,000+ annual reports."""
    pass


@catalog_cmd.command("sectors")
def catalog_sectors():
    """List all ICB industries and report counts."""
    from arminer.data.catalog import UnifiedCatalog
    cat = UnifiedCatalog()
    cat.initialize()
    data = cat.get_sectors()

    table = Table(title="ICB Industry Classification (14,000+ Reports in Zenodo Master Index)")
    table.add_column("ICB Level 1", style="cyan bold")
    table.add_column("Sub-sectors (Level 2)", style="dim")

    for s in data.get("sectors", []):
        l2_names = [sub["name"] for sub in s.get("subsectors", [])]
        table.add_row(s["name"], ", ".join(l2_names))

    console.print(table)


@catalog_cmd.command("search")
@click.option("--ticker", "-t", default=None, help="Ticker symbol (e.g. VCB, FPT, HPG)")
@click.option("--year-from", type=int, default=None, help="From year (e.g. 2015)")
@click.option("--year-to", type=int, default=None, help="To year (e.g. 2024)")
@click.option("--sector", "-s", default=None, help="ICB sector name (e.g. 'Ngân hàng')")
@click.option("--limit", type=int, default=20, help="Max results to display")
def catalog_search(ticker, year_from, year_to, sector, limit):
    """Search for annual reports across Zenodo cloud and local drive."""
    from arminer.data.catalog import UnifiedCatalog
    cat = UnifiedCatalog()
    cat.initialize()
    results = cat.search(
        ticker=ticker,
        year_from=year_from,
        year_to=year_to,
        sector=sector,
        limit=limit,
    )

    table = Table(title=f"Report Search Results (Showing top {len(results)})")
    table.add_column("Ticker", style="cyan bold")
    table.add_column("Year", justify="center")
    table.add_column("Industry", style="yellow")
    table.add_column("Source", style="green")
    table.add_column("Status", style="magenta")
    table.add_column("Filename", max_width=40)

    for r in results:
        table.add_row(
            r["ticker"],
            str(r["year"]),
            f"{r.get('icb_l1', '')} > {r.get('icb_l2', '')}",
            r.get("source", ""),
            r.get("status", ""),
            r.get("file_name", ""),
        )

    console.print(table)


if __name__ == "__main__":
    main()

