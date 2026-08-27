#!/usr/bin/env python3
"""Generate a plain-text Oryntra technical reference from the checked-out source.

The output is intentionally source-derived: it inventories public modules,
functions, classes, routes, environment-variable names, browser hooks, and
tests without reading private `.env` values or local market-data files.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


ROOT = Path(__file__).resolve().parents[2]
SERVER = ROOT / "server"
OUTPUT = ROOT / "docs" / "Oryntra_AI_Master_Technical_Documentation.txt"
EXCLUDED_DIRS = {".git", ".venv", "venv", "__pycache__", "node_modules", "data"}
SUFFIXES = {
    ".py", ".js", ".css", ".html", ".md", ".json", ".sh", ".command", ".txt",
    ".dart", ".swift", ".plist", ".storyboard", ".yaml", ".yml", ".rb", ".h", ".m",
    ".xcconfig", ".xcscheme", ".xcworkspacedata", ".pbxproj", ".entitlements", ".podspec",
}


def source_files() -> list[Path]:
    files = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        if path == OUTPUT:
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        if path.name.startswith(".") and path.name != ".env.example":
            continue
        files.append(path)
    return sorted(files, key=lambda item: item.relative_to(ROOT).as_posix())


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def git_value(*args: str) -> str:
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def line_count(text: str) -> int:
    return text.count("\n") + (1 if text else 0)


def section(title: str, level: int = 1) -> str:
    return f"\n{'=' * 88 if level == 1 else '-' * 88}\n{title}\n{'=' * 88 if level == 1 else '-' * 88}\n"


def paragraph(text: str) -> str:
    return text.strip() + "\n\n"


def category_for(path: Path) -> str:
    value = rel(path)
    if value == "README.md":
        return "Product and operating model"
    if value.startswith("server/backend/routes/"):
        return "HTTP API route"
    if value.startswith("server/backend/patterns/"):
        return "Deterministic pattern analysis"
    if value.startswith("server/backend/"):
        return "Backend service or research engine"
    if value.startswith("server/frontend/legal/"):
        return "Legal and policy surface"
    if value.startswith("server/frontend/static/"):
        return "Browser presentation or client behaviour"
    if value.startswith("server/frontend/"):
        return "Browser application structure"
    if value.startswith("server/maintenance_site/"):
        return "Maintenance-mode application"
    if value.startswith("server/tests/"):
        return "Automated regression test"
    if value.startswith("server/tools/"):
        return "Operator or research utility"
    if value.startswith("server/"):
        return "Server configuration or operator asset"
    if value.startswith("ios-app/lib/"):
        return "Flutter mobile application"
    if value.startswith("ios-app/ios/"):
        return "Native iOS integration or build configuration"
    if value.startswith("ios-app/"):
        return "Mobile application configuration or operator asset"
    return "Repository asset"


def purpose_for(path: Path) -> str:
    name = path.name
    mapping = {
        "main.py": "Composes the FastAPI application, its middleware, route boundaries, static assets, and health surface.",
        "run.py": "Loads local environment configuration and starts the Uvicorn service.",
        "market_repository.py": "Normalizes cache and provider history into a provenance-carrying market-data interface.",
        "quant_research.py": "Defines transparent strategy sleeves, portfolio controls, simulations, validation, and visual diagnostics for Quant Lab.",
        "twelvedata_client.py": "Provides rate-limited, server-side Twelve Data access when configured.",
        "market_cache.py": "Maintains cached market history and scheduled refresh behaviour.",
        "database.py": "Owns SQLite schema initialization and durable application-data helpers.",
        "app.js": "Implements browser interactions, API calls, result rendering, navigation, and private Quant Desk behaviour.",
        "refined.css": "Provides the current restrained blue research-desk visual system.",
        "index.html": "Defines the browser workspace structure, controls, panels, and accessibility hooks.",
        "QUANT_LAB.md": "Documents Quant Lab scope, provider configuration, and research limitations.",
        "main.dart": "Composes the Flutter mobile application and its navigation/runtime configuration.",
        "api_service.dart": "Defines the mobile client interface to Oryntra API endpoints.",
        "app_config.dart": "Centralizes mobile application configuration and endpoint selection.",
    }
    if name in mapping:
        return mapping[name]
    if path.parent.name == "tests":
        return "Exercises a focused behavioural or regression contract for the named subsystem."
    if path.parent.name == "routes":
        return "Defines request validation and API behaviour for the named capability."
    if path.parent.name == "patterns":
        return "Implements a deterministic component of the pattern-detection layer."
    if path.parent.name == "tools":
        return "Provides a command-line or maintenance workflow for the named subsystem."
    if path.suffix == ".css":
        return "Defines visual layout, typography, responsive behaviour, and component states."
    if path.suffix == ".dart":
        return "Implements a Flutter mobile screen, service, widget, or configuration component."
    if path.suffix == ".swift":
        return "Implements native iOS application or widget behaviour."
    if path.suffix == ".html":
        return "Defines a rendered document or browser surface and its semantic structure."
    return "Contributes configuration, implementation, or documentation to the Oryntra system."


def safe_docstring(node: ast.AST) -> str:
    text = ast.get_docstring(node) or ""
    return " ".join(text.split())[:280]


def format_args(node: ast.arguments) -> str:
    items = [arg.arg for arg in node.posonlyargs + node.args]
    if node.vararg:
        items.append("*" + node.vararg.arg)
    items.extend(arg.arg for arg in node.kwonlyargs)
    if node.kwarg:
        items.append("**" + node.kwarg.arg)
    return ", ".join(items)


def decorator_name(decorator: ast.expr) -> str:
    try:
        return ast.unparse(decorator)
    except Exception:
        return decorator.__class__.__name__


class SymbolVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.stack: list[str] = []
        self.symbols: list[dict[str, object]] = []
        self.imports: list[str] = []
        self.routes: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        self.imports.extend(alias.name for alias in node.names)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = "." * node.level + (node.module or "")
        self.imports.append(module or ".")

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified = ".".join([*self.stack, node.name])
        self.symbols.append({"kind": "class", "name": qualified, "line": node.lineno, "detail": safe_docstring(node)})
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    def _function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified = ".".join([*self.stack, node.name])
        decorators = [decorator_name(item) for item in node.decorator_list]
        signature = f"{qualified}({format_args(node.args)})"
        self.symbols.append({"kind": "async function" if isinstance(node, ast.AsyncFunctionDef) else "function", "name": signature, "line": node.lineno, "detail": safe_docstring(node), "decorators": decorators})
        for decorator in decorators:
            if any(marker in decorator for marker in ("router.get", "router.post", "router.put", "router.patch", "router.delete", "app.get", "app.post")):
                self.routes.append(f"line {node.lineno}: {decorator} -> {qualified}")
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = _function
    visit_AsyncFunctionDef = _function


def python_entry(path: Path, text: str) -> str:
    try:
        tree = ast.parse(text)
    except SyntaxError as error:
        return paragraph(f"Python parsing failed: {error}. This should be investigated before relying on the file.")
    visitor = SymbolVisitor()
    visitor.visit(tree)
    chunks = []
    doc = safe_docstring(tree)
    if doc:
        chunks.append(paragraph("Module statement: " + doc))
    if visitor.imports:
        chunks.append(paragraph("Imports: " + ", ".join(sorted(dict.fromkeys(visitor.imports))[:40]) + (" …" if len(visitor.imports) > 40 else "")))
    if visitor.routes:
        chunks.append("HTTP route decorators:\n" + "\n".join(f"  - {item}" for item in visitor.routes) + "\n\n")
    if visitor.symbols:
        chunks.append("Public code inventory:\n")
        for symbol in visitor.symbols:
            decorators = symbol.get("decorators", [])
            extra = f" [decorators: {', '.join(decorators)}]" if decorators else ""
            detail = f" — {symbol['detail']}" if symbol["detail"] else ""
            chunks.append(f"  - {symbol['kind']} {symbol['name']} (line {symbol['line']}){extra}{detail}\n")
        chunks.append("\n")
    else:
        chunks.append(paragraph("No classes or functions were found at module scope. The file is likely declarative configuration, package initialization, or command glue."))
    return "".join(chunks)


def js_entry(text: str) -> str:
    functions = re.findall(r"(?m)^\s*(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(([^)]*)\)", text)
    const_functions = re.findall(r"(?m)^\s*(?:const|let)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(([^)]*)\)\s*=>", text)
    api_calls = sorted(dict.fromkeys(re.findall(r"\bAPI\.([A-Za-z_$][\w$]*)", text)))
    chunks = []
    if functions or const_functions:
        chunks.append("Client function inventory:\n")
        for name, args in [*functions, *const_functions]:
            chunks.append(f"  - {name}({args.strip()})\n")
        chunks.append("\n")
    if api_calls:
        chunks.append(paragraph("Referenced browser API namespaces or methods: " + ", ".join(api_calls) + "."))
    return "".join(chunks) or paragraph("No named JavaScript function declarations were detected by the static inventory.")


def language_entry(text: str, language: str) -> str:
    classes = re.findall(r"(?m)^\s*(?:abstract\s+)?class\s+([A-Za-z_][\w<>]*)", text)
    functions = re.findall(r"(?m)^\s*(?:Future(?:<[^>]+>)?|void|Widget|String|bool|int|double|static\s+\w+)\s+([A-Za-z_][\w]*)\s*\(([^)]*)\)", text)
    imports = re.findall(r"(?m)^\s*import\s+['\"]([^'\"]+)", text)
    chunks = []
    if imports:
        chunks.append(paragraph(f"{language} imports: " + ", ".join(imports[:40]) + (" …" if len(imports) > 40 else "")))
    if classes:
        chunks.append("Class inventory:\n" + "\n".join(f"  - {item}" for item in classes) + "\n\n")
    if functions:
        chunks.append("Function inventory:\n" + "\n".join(f"  - {name}({args.strip()})" for name, args in functions) + "\n\n")
    return "".join(chunks) or paragraph(f"No simple {language} class/function inventory was detected; inspect this configuration or declarative source directly.")


def html_entry(text: str) -> str:
    ids = sorted(dict.fromkeys(re.findall(r'\bid=["\']([^"\']+)', text)))
    forms = re.findall(r"<form\b[^>]*", text, flags=re.I)
    nav_items = re.findall(r"data-tab=[\"']([^\"']+)", text)
    chunks = [paragraph(f"HTML identifiers: {len(ids)}. Forms: {len(forms)}. Tab hooks: {len(nav_items)}.")]
    if ids:
        chunks.append("Representative IDs (first 80):\n" + "\n".join(f"  - {item}" for item in ids[:80]) + "\n\n")
    if nav_items:
        chunks.append(paragraph("Tab identifiers: " + ", ".join(sorted(dict.fromkeys(nav_items))) + "."))
    return "".join(chunks)


def css_entry(text: str) -> str:
    selectors = re.findall(r"(?m)^([^@/][^{]+)\{", text)
    normalized = []
    for selector in selectors:
        value = " ".join(selector.split())
        if value and len(value) < 160:
            normalized.append(value)
    return paragraph(f"Approximate stylesheet selector blocks: {len(normalized)}. The first selectors are: " + "; ".join(normalized[:40]) + ("." if normalized else ""))


def json_entry(text: str) -> str:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return paragraph("JSON parsing failed. This file should be reviewed for syntax or non-JSON templating.")
    if isinstance(value, dict):
        return paragraph("Top-level object keys: " + ", ".join(map(str, value.keys())) + ".")
    if isinstance(value, list):
        return paragraph(f"Top-level array entries: {len(value)}.")
    return paragraph(f"Top-level JSON value type: {type(value).__name__}.")


def text_entry(path: Path, text: str) -> str:
    if path.suffix == ".py":
        return python_entry(path, text)
    if path.suffix == ".js":
        return js_entry(text)
    if path.suffix == ".dart":
        return language_entry(text, "Dart")
    if path.suffix == ".swift":
        return language_entry(text, "Swift")
    if path.suffix == ".html":
        return html_entry(text)
    if path.suffix == ".css":
        return css_entry(text)
    if path.suffix == ".json":
        return json_entry(text)
    preview = " ".join(line.strip() for line in text.splitlines() if line.strip())[:700]
    return paragraph("Content overview: " + (preview if preview else "Empty or whitespace-only file.") )


def environment_inventory(files: Iterable[Path]) -> list[str]:
    names: set[str] = set()
    for path in files:
        if path.suffix not in {".py", ".sh", ".command", ".md", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        names.update(re.findall(r"\b(?:ORYNTRA|POLYGON|TWELVEDATA|ADSENSE|WEB_ADS|PORT|PUBLIC_[A-Z_]+)_[A-Z0-9_]+\b", text))
        names.update(re.findall(r"os\.getenv\([\"']([A-Z0-9_]+)", text))
    return sorted(name for name in names if "KEY" not in name or name in {"POLYGON_API_KEY", "TWELVEDATA_API_KEY"})


def main() -> None:
    files = source_files()
    counts = Counter(category_for(path) for path in files)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    output = []
    output.append("ORYNTRA AI — MASTER TECHNICAL DOCUMENTATION\n")
    output.append("SOURCE-DERIVED PLAIN-TEXT COMPENDIUM\n")
    output.append("Generated: " + now + "\n")
    output.append("Git commit: " + git_value("rev-parse", "HEAD") + "\n")
    output.append("Git branch: " + git_value("branch", "--show-current") + "\n")
    output.append("\n")
    output.append(paragraph("Purpose: This reference explains the checked-out Oryntra AI repository as a software system. It combines an architecture narrative with a static inventory of every included documentation, application, client, test, and operator file. It deliberately excludes `.env`, local databases, cached market data, virtual environments, build products, and credentials. A file being documented here does not prove that a corresponding production server is currently deployed or healthy."))
    output.append(paragraph("Reading rule: material is separated into current-source facts, source-derived inventories, and historical context. The adjacent Notion workspace contains useful older NAS and Pattern Lab records, but those records describe different snapshots and must not be merged into current GitHub behaviour without a direct verification."))
    output.append(section("1. SYSTEM PURPOSE AND SAFETY BOUNDARY"))
    output.append(paragraph("Oryntra AI is a market-intelligence and systematic-research application. It accepts historical market data through a server-side repository, computes deterministic technical and pattern observations, exposes a policy-aware public scanner, and provides a private Quant Lab for transparent daily-bar simulations. It is research software: it does not connect to a brokerage, route an order, or provide an assurance that an observed historical relationship will persist."))
    output.append("\nSYSTEM FLOW\n\n")
    output.append("  Data providers / local cache\n")
    output.append("              |\n")
    output.append("              v\n")
    output.append("  Market repository -> validation + provenance -> deterministic analysis\n")
    output.append("              |                              |\n")
    output.append("              v                              v\n")
    output.append("  Private Quant Lab                    Derived scanner output\n")
    output.append("              |                              |\n")
    output.append("              v                              v\n")
    output.append("  risk/return diagnostics             browser workspace + explanations\n\n")
    output.append(section("2. CURRENT-SOURCE ARCHITECTURE"))
    output.append(paragraph("The FastAPI composition root is `server/backend/main.py`. It initializes durable state, configures compression and response headers, mounts static assets, registers account/intelligence/watchlist/paper/AI routes, and mounts sensitive analysis, backtest, pattern, developer, Quant Lab, and Pro routes only when private research mode is enabled. `server/run.py` is the local Uvicorn launcher."))
    output.append(paragraph("The market repository is responsible for provider selection and data provenance. It normalizes symbols and periods, checks the local cache, validates returned daily bars, optionally uses Polygon or Twelve Data when configured, records provider/freshness metadata, and creates a dataset fingerprint for reproducibility. Provider credentials are an environment concern and are not captured in this document."))
    output.append(paragraph("Quant Lab is a transparent simulator, not a live-trading subsystem. It forms strategy signals using information through the session close, applies portfolio controls, holds next-session target weights, deducts configured transaction/borrow costs, and reports return and risk diagnostics. Its reported heatmaps and curves are generated from the exact simulated net-return series."))
    output.append(section("3. PRIVATE QUANT LAB OPERATING MODEL"))
    output.append(paragraph("Current strategy comparators are time-series trend, cross-sectional momentum, mean reversion, and defensive low volatility. Model profiles specify visible allocations across selected positive sleeves. Portfolio controls include gross-exposure and single-name caps, daily/weekly/monthly rebalancing, and volatility targeting that can reduce but not expand exposure. Research outputs include return, volatility, drawdown, turnover, historical VaR/expected shortfall, concentration, correlation, data coverage, chronological holdout, regime report, monthly net-return heatmap, equity path, drawdown path, and rolling volatility."))
    output.append(paragraph("Important limitations: the current model is based on historical daily closes and configured costs. It does not establish point-in-time fundamentals, delisted-security completeness, institutional liquidity, order-book dynamics, market impact, or executable alpha. A positive backtest is a hypothesis to investigate further, not a product claim."))
    output.append(section("4. NOTION RECONCILIATION"))
    output.append(paragraph("The connected Notion workspace contains a Project Intelligence hub, a Technical Map, Research & Sources standards, a historical system architecture snapshot, a historical V8/VAI/Pattern Lab handoff, and a Code Atlas. Those pages make clear that the prior NAS documentation centered on an August 1 `0.5.0 Optimized` snapshot and associated deployment paths. The current GitHub source is separately reconciled in the Notion child page `Oryntra — GitHub Source Reconciliation — 2026-08-27`. This compendium documents the current checkout only; it does not silently elevate historical deployment records into current production facts."))
    output.append(section("5. REPOSITORY INVENTORY"))
    output.append(f"Included files: {len(files)}\n")
    for category, count in sorted(counts.items()):
        output.append(f"  - {category}: {count}\n")
    output.append("\n")
    output.append("FILE LIST\n\n")
    for path in files:
        text = path.read_text(encoding="utf-8", errors="replace")
        output.append(f"  - {rel(path)} ({line_count(text)} lines; {category_for(path)})\n")
    output.append(section("6. ENVIRONMENT VARIABLE REFERENCE"))
    output.append(paragraph("The following names were found in safe source/configuration files. Values are intentionally omitted. Keep populated environment files and service credentials out of source control and out of public documentation."))
    for name in environment_inventory(files):
        output.append(f"  - {name}\n")
    output.append("\n")
    output.append(section("7. FILE-BY-FILE TECHNICAL REFERENCE"))
    for number, path in enumerate(files, 1):
        text = path.read_text(encoding="utf-8", errors="replace")
        output.append(f"\n[{number:03d}] {rel(path)}\n")
        output.append(f"Category: {category_for(path)}\n")
        output.append(f"Lines: {line_count(text)}\n")
        output.append("Role: " + purpose_for(path) + "\n\n")
        output.append(text_entry(path, text))
    output.append(section("8. TEST AND REVIEW GUIDANCE"))
    output.append(paragraph("Run tests from `server/` so imports resolve from the application root: `PYTHONPATH=. .venv/bin/python3 -m unittest discover -s tests -v`. For a focused Quant Lab check, run `PYTHONPATH=. .venv/bin/python3 -m unittest tests.test_quant_research`. Validate the browser client with `node --check frontend/static/js/app.js`. A release candidate should also be started locally and checked through the actual `/health` endpoint and intended access modes."))
    output.append(paragraph("The document is a static audit aid. It should be regenerated after architectural changes, and the resulting commit ID should be recorded with any environment-specific deployment evidence. Do not treat this document as legal, investment, tax, security, or market-data licensing advice."))
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("".join(output), encoding="utf-8")
    print(f"Wrote {OUTPUT}")
    print(f"Documented {len(files)} files")


if __name__ == "__main__":
    main()
