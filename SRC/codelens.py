
import os
import sys
import ast
import json
import hashlib
import requests
from pathlib import Path
from datetime import datetime
from collections import Counter
from xml.sax.saxutils import escape

from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, Image as PDFImage
)

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QFrame, QFileDialog, QTextEdit,
    QComboBox, QTabWidget, QTableWidget, QTableWidgetItem,
    QHeaderView, QMessageBox, QProgressBar, QGridLayout
)


# ============================================================
# APPLICATION PATHS AND ENVIRONMENT
# ============================================================

def app_directory():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


APP_DIR = app_directory()
ENV_PATH = APP_DIR / ".env"
CONFIG_DIR = Path.home() / ".codelens"
CONFIG_PATH = CONFIG_DIR / "config.json"

OPENROUTER_URL = "https://openrouter.ai/api/v1"
PREFERRED_MODEL = "nvidia/nemotron-3-ultra-550b-a55b:free"

EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".cpp", ".c", ".h", ".hpp",
    ".cs", ".go", ".rs", ".php", ".rb",
    ".swift", ".kt", ".dart", ".vue",
    ".html", ".css", ".scss", ".sql",
    ".sh", ".ps1", ".json", ".yaml", ".yml"
}

IGNORED = {
    ".git", ".venv", "venv", "node_modules",
    "__pycache__", "dist", "build", ".idea",
    ".next", "coverage", ".pytest_cache"
}


def load_environment():
    """
    Load .env from the executable/script directory.
    Also support a .env in the current working directory.
    """
    candidates = [
        ENV_PATH,
        Path.cwd() / ".env"
    ]

    for candidate in candidates:
        if candidate.is_file():
            load_dotenv(candidate, override=True)

    return get_api_key()


def get_api_key():
    key = os.environ.get("OPENROUTER_API_KEY", "").strip()

    # Remove accidental surrounding quotes.
    key = key.strip('"').strip("'").strip()

    # Reject placeholder values.
    if not key or key.lower() in {
        "your_openrouter_api_key_here",
        "your_api_key",
        "replace_me"
    }:
        return ""

    return key


def validate_env():
    load_environment()

    key = get_api_key()

    if not key:
        raise RuntimeError(
            "OpenRouter API key not detected.\n\n"
            f"Expected file:\n{ENV_PATH}\n\n"
            "File contents should look like:\n"
            "OPENROUTER_API_KEY=sk-or-v1-YOUR_FULL_KEY\n\n"
            "Check that Windows has not named it .env.txt."
        )

    if not key.startswith("sk-or-"):
        raise RuntimeError(
            "The API key does not look like a standard OpenRouter key. "
            "Check that you copied the complete key."
        )

    return key


def load_config():
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    defaults = {
        "model": PREFERRED_MODEL,
        "last_folder": ""
    }

    if CONFIG_PATH.exists():
        try:
            defaults.update(
                json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            )
        except Exception:
            pass

    return defaults


def save_config(config):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps(config, indent=4),
        encoding="utf-8"
    )


# ============================================================
# OPENROUTER API
# ============================================================

def api_headers():
    return {
        "Authorization": f"Bearer {validate_env()}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/",
        "X-Title": "CodeLens"
    }


def get_free_models():
    response = requests.get(
        f"{OPENROUTER_URL}/models",
        timeout=30
    )
    response.raise_for_status()

    models = []

    for model in response.json().get("data", []):
        pricing = model.get("pricing", {})

        try:
            prompt = float(pricing.get("prompt", 1))
            completion = float(pricing.get("completion", 1))
        except (ValueError, TypeError):
            continue

        if prompt == 0 and completion == 0:
            model_id = model.get("id")
            if model_id:
                models.append(model_id)

    return sorted(set(models))


def chat_completion(model, messages, max_tokens=8000):
    """
    Robust OpenRouter response handler.
    Supports string and structured content responses,
    handles API errors, empty responses and rate limits.
    """

    import time

    url = f"{OPENROUTER_URL}/chat/completions"

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False
    }

    headers = api_headers()

    last_error = None

    # Retry temporary API failures.
    for attempt in range(3):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(30, 600)
            )

            # Handle API errors.
            if response.status_code in (408, 429, 500, 502, 503, 504):
                detail = response.text[:3000]

                try:
                    detail = response.json().get(
                        "error", {}
                    ).get("message", detail)
                except (ValueError, AttributeError):
                    pass

                last_error = (
                    f"OpenRouter HTTP {response.status_code}: "
                    f"{detail}"
                )

                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue

                raise RuntimeError(last_error)

            if not response.ok:
                try:
                    error_data = response.json()
                    detail = error_data.get(
                        "error", {}
                    ).get("message", response.text)
                except ValueError:
                    detail = response.text

                raise RuntimeError(
                    f"OpenRouter HTTP {response.status_code}:\n"
                    f"{detail[:3000]}"
                )

            # Parse JSON safely.
            try:
                data = response.json()
            except ValueError:
                raise RuntimeError(
                    "OpenRouter returned invalid JSON:\n"
                    + response.text[:2000]
                )

            choices = data.get("choices", [])

            if not choices:
                raise RuntimeError(
                    "OpenRouter returned no choices:\n"
                    + json.dumps(data, indent=2)[:3000]
                )

            message = choices[0].get("message", {})
            finish_reason = choices[0].get("finish_reason")

            content = message.get("content")

            # Some models return content as structured blocks.
            if isinstance(content, list):
                parts = []

                for block in content:
                    if isinstance(block, str):
                        parts.append(block)

                    elif isinstance(block, dict):
                        text = block.get("text")

                        if isinstance(text, str):
                            parts.append(text)

                content = "\n".join(parts)

            # Normal string response.
            if isinstance(content, str):
                content = content.strip()

            else:
                content = ""

            # Handle empty or reasoning-only responses.
            if not content:
                reasoning = message.get("reasoning")

                if isinstance(reasoning, str) and reasoning.strip():
                    raise RuntimeError(
                        "The selected model returned reasoning but "
                        "no final answer. Try another free model."
                    )

                raise RuntimeError(
                    "The AI returned an empty response.\n"
                    f"Finish reason: {finish_reason}\n"
                    f"Response:\n"
                    f"{json.dumps(data, indent=2)[:3000]}"
                )

            # Detect responses cut off by token limits.
            if finish_reason == "length":
                content += (
                    "\n\n[WARNING: The model reached its output "
                    "token limit. This response may be incomplete.]"
                )

            return content

        except requests.exceptions.Timeout:
            last_error = "OpenRouter request timed out."

            if attempt < 2:
                time.sleep(2 ** attempt)
                continue

        except requests.exceptions.ConnectionError as error:
            last_error = f"Connection error: {error}"

            if attempt < 2:
                time.sleep(2 ** attempt)
                continue

    raise RuntimeError(
        f"OpenRouter request failed after retries:\n{last_error}"
    )

# ============================================================
# SOURCE FILE DISCOVERY
# ============================================================

def discover_files(root):
    result = []

    for current, dirs, filenames in os.walk(root):
        dirs[:] = [d for d in dirs if d not in IGNORED]

        for filename in filenames:
            path = Path(current) / filename

            if path.suffix.lower() not in EXTENSIONS:
                continue

            try:
                if path.stat().st_size <= 5_000_000:
                    result.append(path)
            except OSError:
                continue

    return sorted(result)


def read_file(path):
    try:
        return path.read_text(
            encoding="utf-8",
            errors="replace"
        )
    except Exception:
        return ""


# ============================================================
# LOCAL STATIC ANALYSIS
# ============================================================

def finding(results, severity, category, message, path, line, evidence):
    results.append({
        "severity": severity,
        "category": category,
        "message": message,
        "file": str(path),
        "line": int(line or 1),
        "evidence": str(evidence)[:300]
    })


def python_analysis(path, source, results):
    try:
        tree = ast.parse(source)
    except SyntaxError as error:
        finding(
            results, "HIGH", "Syntax",
            f"Python syntax error: {error.msg}",
            path, error.lineno, ""
        )
        return

    for node in ast.walk(tree):

        if isinstance(node, ast.Call):

            # eval and exec
            if isinstance(node.func, ast.Name):
                if node.func.id in {"eval", "exec"}:
                    finding(
                        results, "HIGH", "Dynamic execution",
                        f"{node.func.id} can execute dynamically supplied code.",
                        path, node.lineno,
                        ast.get_source_segment(source, node)
                    )

            if isinstance(node.func, ast.Attribute):

                # shell=True
                if node.func.attr in {
                    "run", "Popen", "call", "system", "check_output"
                }:
                    for kw in node.keywords:
                        if (
                            kw.arg == "shell"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is True
                        ):
                            finding(
                                results, "HIGH", "Command execution",
                                "shell=True requires careful input validation.",
                                path, node.lineno,
                                ast.get_source_segment(source, node)
                            )

                # TLS disabled
                if node.func.attr in {"get", "post", "request", "put"}:
                    for kw in node.keywords:
                        if (
                            kw.arg == "verify"
                            and isinstance(kw.value, ast.Constant)
                            and kw.value.value is False
                        ):
                            finding(
                                results, "HIGH", "Network security",
                                "TLS certificate verification is disabled.",
                                path, node.lineno,
                                ast.get_source_segment(source, node)
                            )

                # Pickle
                if node.func.attr in {"load", "loads"}:
                    if (
                        isinstance(node.func.value, ast.Name)
                        and node.func.value.id == "pickle"
                    ):
                        finding(
                            results, "HIGH", "Deserialization",
                            "Pickle can execute code when loading "
                            "untrusted data.",
                            path, node.lineno,
                            ast.get_source_segment(source, node)
                        )

        if isinstance(node, ast.ExceptHandler):
            if node.type is None:
                finding(
                    results, "LOW", "Error handling",
                    "Bare except may hide unexpected failures.",
                    path, node.lineno, "except:"
                )

            elif (
                isinstance(node.type, ast.Name)
                and node.type.id == "Exception"
            ):
                finding(
                    results, "INFO", "Error handling",
                    "Broad exception handling may hide errors.",
                    path, node.lineno, "except Exception:"
                )

        if isinstance(node, ast.ImportFrom):
            if any(alias.name == "*" for alias in node.names):
                finding(
                    results, "LOW", "Maintainability",
                    "Wildcard import makes dependencies less explicit.",
                    path, node.lineno, "from module import *"
                )

        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.end_lineno:
                size = node.end_lineno - node.lineno + 1

                if size > 80:
                    finding(
                        results, "LOW", "Maintainability",
                        f"Function {node.name} contains {size} lines.",
                        path, node.lineno, node.name
                    )


def text_analysis(path, source, results):
    patterns = [
        ("TODO", "INFO", "Incomplete work", "TODO marker found."),
        ("FIXME", "LOW", "Incomplete work", "FIXME marker found."),
        ("debugger", "LOW", "Debug artifact", "Possible debugger statement."),
        ("password =", "HIGH", "Credential", "Possible hardcoded password."),
        ("api_key =", "HIGH", "Credential", "Possible hardcoded API key."),
        ("secret_key =", "HIGH", "Credential", "Possible hardcoded secret.")
    ]

    for number, line in enumerate(source.splitlines(), 1):
        lowered = line.lower()

        for pattern, severity, category, message in patterns:
            if pattern.lower() not in lowered:
                continue

            if pattern in {"password =", "api_key =", "secret_key ="}:
                value = lowered.split("=", 1)[-1].strip()

                if value in {"", '""', "''", "none", "null"}:
                    continue

                if any(x in value for x in [
                    "your_", "placeholder", "example", "change_me"
                ]):
                    continue

            finding(
                results, severity, category,
                message, path, number, line
            )


def local_analysis(root, progress=None):
    files = discover_files(root)
    results = []
    file_data = []

    for index, path in enumerate(files, 1):
        if progress:
            progress(f"Scanning {index}/{len(files)}: {path.name}")

        source = read_file(path)

        if path.suffix.lower() == ".py":
            python_analysis(path, source, results)

        text_analysis(path, source, results)

        file_data.append({
            "path": str(path),
            "relative": str(path.relative_to(root)),
            "name": path.name,
            "extension": path.suffix.lower(),
            "lines": len(source.splitlines()),
            "size": path.stat().st_size,
            "source": source
        })

    duplicates = find_duplicates(files)

    counts = Counter(x["severity"] for x in results)

    return {
        "root": str(root),
        "files": file_data,
        "findings": results,
        "duplicates": duplicates,
        "statistics": {
            "files": len(files),
            "lines": sum(x["lines"] for x in file_data),
            "findings": len(results),
            "high": counts["HIGH"],
            "low": counts["LOW"],
            "info": counts["INFO"],
            "duplicate_groups": len(duplicates)
        }
    }


# ============================================================
# DUPLICATE DETECTION
# ============================================================

def find_duplicates(files):
    groups = {}

    for path in files:
        try:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            groups.setdefault(digest, []).append(str(path))
        except OSError:
            pass

    return [
        {
            "hash": digest,
            "files": paths,
            "count": len(paths)
        }
        for digest, paths in groups.items()
        if len(paths) > 1
    ]


# ============================================================
# COMPLETE AI SOURCE ANALYSIS
# ============================================================

def make_batches(files, maximum_chars=24000):
    """
    Split every file into line-preserving chunks.

    No source file is silently truncated. Large files are split
    into multiple chunks, and every chunk is sent to the model.
    """
    batches = []
    current = []
    current_size = 0

    for file in files:
        source = file["source"]
        lines = source.splitlines()

        if not lines:
            lines = [""]

        chunk = []
        chunk_start = 1
        chunk_size = 0

        for line_number, line in enumerate(lines, 1):
            if chunk and chunk_size + len(line) + 1 > maximum_chars:
                content = "\n".join(chunk)

                entry = (
                    f"\nFILE: {file['relative']}\n"
                    f"LINES: {chunk_start}-{line_number - 1}\n"
                    f"SOURCE:\n{content}\n"
                )

                if current and current_size + len(entry) > maximum_chars:
                    batches.append(current)
                    current = []
                    current_size = 0

                current.append(entry)
                current_size += len(entry)

                chunk = []
                chunk_start = line_number
                chunk_size = 0

            chunk.append(line)
            chunk_size += len(line) + 1

        if chunk:
            entry = (
                f"\nFILE: {file['relative']}\n"
                f"LINES: {chunk_start}-{len(lines)}\n"
                f"SOURCE:\n{chr(10).join(chunk)}\n"
            )

            if current and current_size + len(entry) > maximum_chars:
                batches.append(current)
                current = []
                current_size = 0

            current.append(entry)
            current_size += len(entry)

    if current:
        batches.append(current)

    return batches


AI_SYSTEM = """
You are CodeLens, a senior software engineer, security reviewer
and software architect.

Analyze the actual supplied source code.

Inspect for:
- Security vulnerabilities
- Authentication and authorization problems
- Input validation and injection risks
- Secrets and credential exposure
- Unsafe file and command operations
- Error handling problems
- Performance bottlenecks
- Memory and resource management
- Concurrency and race conditions
- API and network reliability
- Database and data integrity issues
- Maintainability and code complexity
- Architectural problems
- Dead code and suspicious implementation patterns
- Incomplete implementation and TODOs

STRICT RULES:
1. Analyze only the supplied code.
2. Do not invent findings.
3. Give the exact supplied file path and line number.
4. If line numbers are unavailable, say so.
5. Distinguish confirmed issues from potential risks.
6. Explain impact and remediation.
7. Do not claim code was executed or tested.
8. Do not treat every style preference as a vulnerability.
9. Do not silently ignore any supplied source section.

Return a structured, professional report.
"""


def analyze_with_ai(model, analysis, user_prompt, progress=None):
    batches = make_batches(analysis["files"])

    if not batches:
        raise RuntimeError("No source code was found to analyze.")

    reports = []

    for index, batch in enumerate(batches, 1):
        if progress:
            progress(
                f"AI analyzing source batch {index}/{len(batches)}..."
            )

        source = "\n".join(batch)

        messages = [
            {"role": "system", "content": AI_SYSTEM},
            {
                "role": "user",
                "content": (
                    f"PROJECT: {analysis['root']}\n"
                    f"BATCH: {index}/{len(batches)}\n\n"
                    f"USER REQUEST: {user_prompt}\n\n"
                    f"STATIC FINDINGS:\n"
                    f"{json.dumps(analysis['findings'], indent=2)[:12000]}\n\n"
                    f"SOURCE CODE:\n{source}"
                )
            }
        ]

        report = chat_completion(
            model, messages, max_tokens=5000
        )

        reports.append(
            f"===== SOURCE ANALYSIS BATCH {index} =====\n{report}"
        )

    if progress:
        progress("Combining all source reviews into final report...")

    combined = "\n\n".join(reports)

    final_report = chat_completion(
        model,
        [
            {
                "role": "system",
                "content": """
You are the final report editor for CodeLens.

Combine the supplied individual source reviews into one complete
project-wide report.

Preserve every distinct important finding. Remove only genuine
duplicates. Keep exact file paths and line references. Do not
invent findings or pretend unreviewed code was inspected.

Use these sections:
1. EXECUTIVE SUMMARY
2. CRITICAL SECURITY RISKS
3. OTHER SECURITY CONCERNS
4. RELIABILITY AND PERFORMANCE
5. ARCHITECTURE AND MAINTAINABILITY
6. FILE-BY-FILE FINDINGS
7. RECOMMENDED FIXES
8. PRIORITIZED ACTION PLAN
9. FINAL ASSESSMENT

Be detailed and actionable.
"""
            },
            {
                "role": "user",
                "content": (
                    f"Project statistics:\n"
                    f"{json.dumps(analysis['statistics'], indent=2)}\n\n"
                    f"Duplicate files:\n"
                    f"{json.dumps(analysis['duplicates'], indent=2)}\n\n"
                    f"Individual reviews:\n{combined}"
                )
            }
        ],
        max_tokens=8000
    )

    return (
        f"FILES DISCOVERED: {len(analysis['files'])}\n"
        f"SOURCE BATCHES REVIEWED: {len(batches)}\n\n"
        + final_report
    )


# ============================================================
# AI COMMIT MESSAGE
# ============================================================

def generate_commit(model, analysis):
    evidence = {
        "project": analysis["root"],
        "file_inventory": [
            {
                "path": f["relative"],
                "lines": f["lines"]
            }
            for f in analysis["files"]
        ],
        "findings": analysis["findings"],
        "duplicates": analysis["duplicates"]
    }

    return chat_completion(
        model,
        [
            {
                "role": "system",
                "content": """
Write a professional Conventional Commit suggestion.

Use:
type(scope): description

Possible types:
feat, fix, refactor, docs, test, perf, chore.

IMPORTANT:
The evidence is a project scan, not a Git diff.
Never pretend that you know which files were changed.
Label the result as a suggested project-summary commit.
"""
            },
            {
                "role": "user",
                "content": json.dumps(evidence, indent=2)
            }
        ],
        max_tokens=700
    )


# ============================================================
# PIL COVER ART
# ============================================================

def create_cover(path, project, score):
    image = Image.new("RGB", (1400, 800), "#0B1020")
    draw = ImageDraw.Draw(image)

    for x in range(-300, 1500, 90):
        draw.line(
            (x, 0, x - 350, 800),
            fill="#17243D",
            width=2
        )

    draw.ellipse(
        (950, 100, 1430, 580),
        outline="#8B78F6",
        width=9
    )

    draw.ellipse(
        (1050, 200, 1330, 480),
        outline="#4DC7B7",
        width=5
    )

    try:
        font_big = ImageFont.truetype("arial.ttf", 68)
        font_mid = ImageFont.truetype("arial.ttf", 34)
        font_small = ImageFont.truetype("arial.ttf", 24)
    except OSError:
        font_big = font_mid = font_small = ImageFont.load_default()

    draw.text((90, 95), "CODELENS", fill="#B7AAFF", font=font_mid)
    draw.text((90, 265), "Code Intelligence", fill="#FFFFFF", font=font_big)
    draw.text((95, 385), project[:55], fill="#AAB9D3", font=font_mid)

    draw.text(
        (95, 620),
        datetime.now().strftime("%d %B %Y"),
        fill="#8291AA",
        font=font_small
    )

    draw.text(
        (1060, 610),
        f"{score}/100",
        fill="#B7AAFF",
        font=font_big
    )

    image.save(path)


# ============================================================
# PDF GENERATION
# ============================================================

def create_pdf(analysis, ai_report, destination):
    stats = analysis["statistics"]

    # This is a heuristic indicator, not a security certification.
    score = max(
        0,
        min(
            100,
            100
            - stats["high"] * 12
            - stats["low"] * 4
            - stats["duplicate_groups"] * 3
        )
    )

    project = Path(analysis["root"]).name or "Project"

    cover = Path(destination).with_name("_codelens_cover.png")
    create_cover(cover, project, score)

    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        name="CLHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#6556C8"),
        fontSize=14,
        leading=19,
        spaceBefore=14,
        spaceAfter=8
    ))

    styles.add(ParagraphStyle(
        name="CLBody",
        parent=styles["BodyText"],
        textColor=colors.HexColor("#30394B"),
        fontSize=8.5,
        leading=13,
        spaceAfter=7
    ))

    styles.add(ParagraphStyle(
        name="CLSmall",
        parent=styles["BodyText"],
        textColor=colors.HexColor("#69758B"),
        fontSize=7.5,
        leading=10
    ))

    doc = SimpleDocTemplate(
        destination,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=17 * mm,
        bottomMargin=18 * mm,
        title=f"CodeLens Report - {project}",
        author="CodeLens"
    )

    story = [
        PDFImage(str(cover), width=174 * mm, height=99.4 * mm),
        Spacer(1, 10 * mm),
        Paragraph("CODELENS PROJECT REPORT", styles["Title"]),
        Paragraph(escape(project), styles["CLBody"]),
        Paragraph(
            "Generated: " + datetime.now().strftime("%d %B %Y, %H:%M"),
            styles["CLSmall"]
        ),
        PageBreak(),
        Paragraph("01 — Project Snapshot", styles["Title"])
    ]

    data = [
        ["Metric", "Value"],
        ["Source files", str(stats["files"])],
        ["Lines of code", f"{stats['lines']:,}"],
        ["Static findings", str(stats["findings"])],
        ["High severity", str(stats["high"])],
        ["Low severity", str(stats["low"])],
        ["Informational", str(stats["info"])],
        ["Duplicate groups", str(stats["duplicate_groups"])],
        ["Illustrative score", f"{score}/100"]
    ]

    table = Table(data, colWidths=[90 * mm, 70 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17213A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#F1F3F8")
        ]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D5DCE8")),
        ("PADDING", (0, 0), (-1, -1), 8)
    ]))

    story.extend([
        table,
        Spacer(1, 10),
        Paragraph(
            "The score is a simple heuristic indicator based on "
            "local findings and duplicate groups. It is not a "
            "security certification.",
            styles["CLSmall"]
        ),
        Paragraph("02 — Static Findings", styles["Title"])
    ])

    if not analysis["findings"]:
        story.append(Paragraph(
            "No findings were detected by the configured local checks.",
            styles["CLBody"]
        ))

    for item in analysis["findings"]:
        content = (
            f"<b>[{escape(item['severity'])}] "
            f"{escape(item['category'])}</b><br/>"
            f"{escape(item['message'])}<br/>"
            f"<b>File:</b> {escape(item['file'])}:{item['line']}<br/>"
            f"<b>Evidence:</b> {escape(item['evidence'])}"
        )

        story.append(Paragraph(content, styles["CLBody"]))

    story.extend([
        PageBreak(),
        Paragraph("03 — Duplicate Files", styles["Title"])
    ])

    if not analysis["duplicates"]:
        story.append(Paragraph(
            "No exact duplicate files were detected.",
            styles["CLBody"]
        ))

    for group in analysis["duplicates"]:
        story.append(Paragraph(
            f"<b>Duplicate group: {group['count']} files</b>",
            styles["CLBody"]
        ))

        for filename in group["files"]:
            story.append(Paragraph(
                escape(filename), styles["CLSmall"]
            ))

    story.extend([
        PageBreak(),
        Paragraph("04 — Complete AI Code Review", styles["Title"])
    ])

    for line in ai_report.splitlines():
        line = line.strip()

        if not line:
            story.append(Spacer(1, 4))
            continue

        if (
            len(line) < 100
            and (
                line.isupper()
                or line.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9."))
            )
        ):
            story.append(Paragraph(escape(line), styles["CLHeading"]))
        else:
            story.append(Paragraph(
                escape(line).replace("\n", "<br/>"),
                styles["CLBody"]
            ))

    story.extend([
        PageBreak(),
        Paragraph("05 — Source File Inventory", styles["Title"])
    ])

    inventory = [["File", "Extension", "Lines"]]

    for file in analysis["files"]:
        inventory.append([
            escape(file["relative"]),
            escape(file["extension"]),
            str(file["lines"])
        ])

    inv = Table(
        inventory,
        colWidths=[105 * mm, 30 * mm, 25 * mm],
        repeatRows=1
    )

    inv.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17213A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [
            colors.white, colors.HexColor("#F1F3F8")
        ]),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#D5DCE8")),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("PADDING", (0, 0), (-1, -1), 5)
    ]))

    story.append(inv)

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#8995A9"))
        canvas.drawString(18 * mm, 10 * mm, "CodeLens • Code Intelligence")
        canvas.drawRightString(
            A4[0] - 18 * mm, 10 * mm, f"Page {document.page}"
        )
        canvas.restoreState()

    doc.build(story, onFirstPage=footer, onLaterPages=footer)

    try:
        cover.unlink(missing_ok=True)
    except OSError:
        pass

    return score


# ============================================================
# BACKGROUND WORKER
# ============================================================

class Worker(QThread):
    done = Signal(object)
    failed = Signal(str)
    status = Signal(str)

    def __init__(self, function, *args):
        super().__init__()
        self.function = function
        self.args = args

    def run(self):
        try:
            result = self.function(
                *self.args,
                progress=self.status.emit
            )
            self.done.emit(result)
        except Exception as error:
            self.failed.emit(str(error))


def analysis_task(folder, progress):
    return local_analysis(folder, progress)


def ai_task(model, analysis, prompt, progress):
    return analyze_with_ai(model, analysis, prompt, progress)


def commit_task(model, analysis, progress):
    progress("Generating commit suggestion...")
    return generate_commit(model, analysis)


# ============================================================
# MAIN APPLICATION
# ============================================================

def generate_pdf(analysis, ai_report, output_path):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table,
        TableStyle, PageBreak
    )
    from xml.sax.saxutils import escape

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CLTitle",
        parent=styles["Title"],
        fontSize=22,
        textColor=colors.HexColor("#7563D9"),
        spaceAfter=15
    )

    heading_style = ParagraphStyle(
        "CLHeading",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#7563D9"),
        spaceBefore=12,
        spaceAfter=8
    )

    body_style = ParagraphStyle(
        "CLBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=14,
        spaceAfter=7
    )

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm
    )

    story = []

    stats = analysis["statistics"]

    story.append(Paragraph("CODELENS", title_style))
    story.append(Paragraph("Complete Code Intelligence Report", heading_style))
    story.append(Paragraph(
        f"Project: {escape(str(analysis['root']))}",
        body_style
    ))
    story.append(Paragraph(
        f"Generated: {datetime.now().strftime('%d %B %Y, %H:%M')}",
        body_style
    ))
    story.append(Spacer(1, 15))

    story.append(Paragraph("01 — Project Statistics", heading_style))

    rows = [
        ["Metric", "Value"],
        ["Source files", str(stats["files"])],
        ["Lines of code", str(stats["lines"])],
        ["Potential findings", str(stats["findings"])],
        ["High severity", str(stats["high"])],
        ["Low severity", str(stats["low"])],
        ["Duplicate groups", str(stats["duplicate_groups"])]
    ]

    table = Table(rows, colWidths=[85 * mm, 75 * mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17213A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#F0F2F8")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 8)
    ]))

    story.append(table)
    story.append(Spacer(1, 15))

    story.append(Paragraph("02 — Static Risk Findings", heading_style))

    for item in analysis["findings"]:
        story.append(Paragraph(
            f"<b>{escape(str(item['severity']))} — "
            f"{escape(str(item['category']))}</b>",
            body_style
        ))
        story.append(Paragraph(
            escape(str(item["message"])),
            body_style
        ))
        story.append(Paragraph(
            f"File: {escape(str(item['file']))} | "
            f"Line: {item['line']}",
            body_style
        ))
        story.append(Paragraph(
            f"Evidence: {escape(str(item['evidence']))}",
            body_style
        ))
        story.append(Spacer(1, 5))

    story.append(PageBreak())
    story.append(Paragraph("03 — Duplicate Files", heading_style))

    if not analysis["duplicates"]:
        story.append(Paragraph("No exact duplicates detected.", body_style))

    for group in analysis["duplicates"]:
        story.append(Paragraph(
            f"Duplicate group ({group['count']} files)",
            body_style
        ))

        for file in group["files"]:
            story.append(Paragraph(escape(file), body_style))

    story.append(PageBreak())
    story.append(Paragraph("04 — AI Code Review", heading_style))

    for line in ai_report.splitlines():
        line = line.strip()

        if not line:
            story.append(Spacer(1, 5))
        elif line.isupper() and len(line) < 100:
            story.append(Paragraph(escape(line), heading_style))
        else:
            story.append(Paragraph(escape(line), body_style))

    story.append(PageBreak())
    story.append(Paragraph("05 — Source File Inventory", heading_style))

    inventory = [["File", "Type", "Lines"]]

    for file in analysis["files"]:
        inventory.append([
            escape(file["name"]),
            escape(file["extension"]),
            str(file["lines"])
        ])

    inventory_table = Table(
        inventory,
        colWidths=[90 * mm, 35 * mm, 30 * mm],
        repeatRows=1
    )

    inventory_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#17213A")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.grey),
        ("PADDING", (0, 0), (-1, -1), 6)
    ]))

    story.append(inventory_table)

    doc.build(story)

    return True

class CodeLens(QMainWindow):

    def __init__(self):
        super().__init__()

        self.config = load_config()
        self.analysis = None
        self.ai_report = ""
        self.folder = None
        self.worker = None
        self.task_type = ""

        self.setWindowTitle("CodeLens | Code Intelligence")
        self.resize(1450, 900)
        self.setMinimumSize(1100, 700)

        self.setStyleSheet("""
        QMainWindow, QWidget {
            background: #090D16;
            color: #EDF0FA;
            font-family: Segoe UI;
        }
        QFrame#panel {
            background: #121A29;
            border: 1px solid #26334A;
            border-radius: 12px;
        }
        QLabel { background: transparent; }
        QPushButton {
            background: #1A263B;
            color: #EDF0FA;
            border: 1px solid #30415F;
            border-radius: 8px;
            padding: 10px 14px;
            font-weight: 600;
        }
        QPushButton:hover { border: 1px solid #A99BFF; }
        QPushButton#primary {
            background: #8B78F6;
            color: #090D16;
            border: none;
        }
        QComboBox, QTextEdit, QLineEdit {
            background: #101827;
            color: #EDF0FA;
            border: 1px solid #2A3850;
            border-radius: 8px;
            padding: 9px;
        }
        QTabWidget::pane {
            border: 1px solid #26334A;
            background: #0E1522;
        }
        QTabBar::tab {
            background: #121A29;
            color: #A5B2C9;
            padding: 12px 17px;
        }
        QTabBar::tab:selected {
            background: #273451;
            color: white;
            border-bottom: 2px solid #A99BFF;
        }
        QTableWidget {
            background: #111A29;
            gridline-color: #26334A;
            border: 1px solid #26334A;
        }
        QHeaderView::section {
            background: #1C2940;
            color: #C6D1E4;
            padding: 9px;
            border: none;
        }
        QProgressBar {
            background: #1A263B;
            border: none;
            border-radius: 5px;
        }
        QProgressBar::chunk {
            background: #8B78F6;
            border-radius: 5px;
        }
        """)

        self.build_ui()
        self.refresh_models()

    # --------------------------------------------------------
    # UI HELPERS
    # --------------------------------------------------------

    def label(self, text, size=11, color="#EDF0FA", bold=False):
        widget = QLabel(text)
        widget.setFont(QFont(
            "Segoe UI", size,
            QFont.Weight.Bold if bold else QFont.Weight.Normal
        ))
        widget.setStyleSheet(f"color:{color};")
        return widget

    def panel(self):
        frame = QFrame()
        frame.setObjectName("panel")
        return frame

    def button(self, text, callback, primary=False):
        btn = QPushButton(text)
        btn.clicked.connect(callback)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        if primary:
            btn.setObjectName("primary")

        return btn

    def set_status(self, text):
        self.status_label.setText(text)

    def start_worker(self, task, *args):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(
                self, "Busy", "Wait for the current task to finish."
            )
            return

        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        self.worker = Worker(task, *args)
        self.worker.status.connect(self.set_status)
        self.worker.done.connect(self.worker_finished)
        self.worker.failed.connect(self.worker_failed)
        self.worker.start()

    # --------------------------------------------------------
    # MAIN UI
    # --------------------------------------------------------

    def build_ui(self):
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(25, 20, 25, 15)
        root.setSpacing(15)

        header = QHBoxLayout()

        brand = QVBoxLayout()
        brand.addWidget(self.label("◈ CodeLens", 27, "#A99BFF", True))
        brand.addWidget(self.label(
            "CODE INTELLIGENCE • AI REVIEW • PROJECT ANALYSIS",
            9, "#8291AA", True
        ))

        header.addLayout(brand)
        header.addStretch()

        self.model_box = QComboBox()
        self.model_box.setMinimumWidth(350)
        header.addWidget(self.model_box)

        self.refresh_btn = self.button(
            "↻ Models", self.refresh_models
        )
        header.addWidget(self.refresh_btn)

        root.addLayout(header)

        project = self.panel()
        project_layout = QHBoxLayout(project)
        project_layout.setContentsMargins(15, 13, 15, 13)

        info = QVBoxLayout()
        info.addWidget(self.label("PROJECT WORKSPACE", 9, "#8998B2", True))

        self.project_label = self.label(
            "No project selected", 12, "#FFFFFF", True
        )
        info.addWidget(self.project_label)

        project_layout.addLayout(info)
        project_layout.addStretch()

        project_layout.addWidget(self.button(
            "Choose Folder", self.choose_folder
        ))

        project_layout.addWidget(self.button(
            "Analyze Project", self.analyze_project, True
        ))

        root.addWidget(project)

        self.tabs = QTabWidget()

        self.tabs.addTab(self.create_overview(), "Overview")
        self.tabs.addTab(self.create_findings(), "Risk Findings")
        self.tabs.addTab(self.create_duplicates(), "Duplicates")
        self.tabs.addTab(self.create_ai(), "AI Intelligence")
        self.tabs.addTab(self.create_commit(), "Commit Assistant")
        self.tabs.addTab(self.create_pdf(), "PDF Reports")

        root.addWidget(self.tabs, 1)

        status = QHBoxLayout()

        self.status_label = self.label(
            "Ready. Select a project folder.", 9, "#91A0B8"
        )

        status.addWidget(self.status_label)
        status.addStretch()

        self.progress = QProgressBar()
        self.progress.setFixedWidth(180)
        self.progress.setVisible(False)
        status.addWidget(self.progress)

        root.addLayout(status)
        self.setCentralWidget(central)

    # --------------------------------------------------------
    # OVERVIEW
    # --------------------------------------------------------

    def create_overview(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(self.label(
            "Project Overview", 22, "#FFFFFF", True
        ))

        grid = QGridLayout()
        self.metrics = []

        for i, title in enumerate([
            "SOURCE FILES", "LINES OF CODE",
            "RISK FINDINGS", "DUPLICATE GROUPS"
        ]):
            card = self.panel()
            box = QVBoxLayout(card)
            box.setContentsMargins(17, 15, 17, 15)

            box.addWidget(self.label(title, 9, "#8998B2", True))
            value = self.label("—", 27, "#A99BFF", True)
            box.addWidget(value)

            self.metrics.append(value)
            grid.addWidget(card, 0, i)

        layout.addLayout(grid)

        self.overview_output = QTextEdit()
        self.overview_output.setReadOnly(True)
        self.overview_output.setPlaceholderText(
            "Project statistics appear here after analysis."
        )
        layout.addWidget(self.overview_output, 1)

        return page

    # --------------------------------------------------------
    # FINDINGS
    # --------------------------------------------------------

    def create_findings(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(self.label(
            "Potential Risks", 21, "#FFFFFF", True
        ))

        self.findings_table = QTableWidget(0, 5)
        self.findings_table.setHorizontalHeaderLabels([
            "SEVERITY", "CATEGORY", "FILE", "LINE", "DESCRIPTION"
        ])

        self.configure_table(self.findings_table)
        self.findings_table.horizontalHeader().setSectionResizeMode(
            4, QHeaderView.ResizeMode.Stretch
        )

        layout.addWidget(self.findings_table)
        return page

    # --------------------------------------------------------
    # DUPLICATES
    # --------------------------------------------------------

    def create_duplicates(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(self.label(
            "Exact Duplicate Files", 21, "#FFFFFF", True
        ))

        self.duplicate_output = QTextEdit()
        self.duplicate_output.setReadOnly(True)

        layout.addWidget(self.duplicate_output)
        return page

    # --------------------------------------------------------
    # AI
    # --------------------------------------------------------

    def create_ai(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(self.label(
            "AI Code Intelligence", 21, "#FFFFFF", True
        ))

        self.ai_prompt = QTextEdit()
        self.ai_prompt.setMaximumHeight(90)
        self.ai_prompt.setPlaceholderText(
            "Example: Thoroughly analyze every file. Find security "
            "issues, performance problems, architectural weaknesses "
            "and suggest fixes."
        )

        layout.addWidget(self.ai_prompt)

        self.ai_btn = self.button(
            "✧ Analyze Entire Codebase", self.start_ai, True
        )
        layout.addWidget(self.ai_btn)

        self.ai_output = QTextEdit()
        self.ai_output.setReadOnly(True)
        layout.addWidget(self.ai_output, 1)

        return page

    # --------------------------------------------------------
    # COMMIT
    # --------------------------------------------------------

    def create_commit(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(self.label(
            "Professional Commit Assistant", 21, "#FFFFFF", True
        ))

        layout.addWidget(self.label(
            "Generates a project-summary commit suggestion. "
            "It does not yet inspect Git diffs.",
            10, "#E9B65C"
        ))

        self.commit_btn = self.button(
            "Generate Commit Message", self.start_commit, True
        )
        layout.addWidget(self.commit_btn)

        self.commit_output = QTextEdit()
        self.commit_output.setReadOnly(True)
        layout.addWidget(self.commit_output, 1)

        layout.addWidget(self.button(
            "Copy Commit Message", self.copy_commit
        ))

        return page

    # --------------------------------------------------------
    # PDF
    # --------------------------------------------------------

    def create_pdf(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(18, 18, 18, 18)

        layout.addWidget(self.label(
            "Professional PDF Report", 21, "#FFFFFF", True
        ))

        layout.addWidget(self.label(
            "Includes project statistics, static risks, duplicate files, "
            "complete AI review and source file inventory.",
            10, "#91A0B8"
        ))

        card = self.panel()
        box = QVBoxLayout(card)
        box.setContentsMargins(20, 20, 20, 20)

        for item in [
            "01 — Project snapshot",
            "02 — Static analysis findings",
            "03 — Exact duplicate detection",
            "04 — Complete AI review",
            "05 — Source file inventory",
            "06 — Pillow-generated report artwork"
        ]:
            box.addWidget(self.label(item, 12, "#DDE5F4"))

        layout.addWidget(card)

        layout.addWidget(self.button(
            "Export Complete PDF", self.export_pdf, True
        ))

        layout.addStretch()
        return page

    # --------------------------------------------------------
    # TABLE HELPERS
    # --------------------------------------------------------

    def configure_table(self, table):
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )

    # --------------------------------------------------------
    # PROJECT
    # --------------------------------------------------------

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose Source Code Project"
        )

        if not folder:
            return

        self.folder = Path(folder)
        self.project_label.setText(str(self.folder))

        self.config["last_folder"] = folder
        save_config(self.config)

        self.analysis = None
        self.ai_report = ""

        self.set_status("Project selected.")

    def analyze_project(self):
        if not self.folder:
            QMessageBox.warning(
                self, "Select project", "Choose a folder first."
            )
            return

        self.task_type = "analysis"
        self.start_worker(analysis_task, self.folder)

    def update_analysis(self):
        stats = self.analysis["statistics"]

        values = [
            stats["files"],
            f"{stats['lines']:,}",
            stats["findings"],
            stats["duplicate_groups"]
        ]

        for label, value in zip(self.metrics, values):
            label.setText(str(value))

        self.overview_output.setPlainText(
            f"PROJECT: {self.analysis['root']}\n\n"
            f"Source files: {stats['files']}\n"
            f"Lines of code: {stats['lines']:,}\n"
            f"Static findings: {stats['findings']}\n"
            f"High severity: {stats['high']}\n"
            f"Low severity: {stats['low']}\n"
            f"Informational: {stats['info']}\n"
            f"Duplicate groups: {stats['duplicate_groups']}\n\n"
            "All discovered source files were included in the local "
            "scan. AI review is performed separately in source batches."
        )

        findings = self.analysis["findings"]
        self.findings_table.setRowCount(len(findings))

        for row, item in enumerate(findings):
            values = [
                item["severity"],
                item["category"],
                item["file"],
                str(item["line"]),
                item["message"]
            ]

            for col, value in enumerate(values):
                self.findings_table.setItem(
                    row, col, QTableWidgetItem(str(value))
                )

        duplicate_lines = []

        for index, group in enumerate(
            self.analysis["duplicates"], 1
        ):
            duplicate_lines.append(
                f"GROUP {index} — {group['count']} FILES"
            )

            for path in group["files"]:
                duplicate_lines.append(f"  • {path}")

            duplicate_lines.append(
                f"SHA-256: {group['hash']}\n"
            )

        self.duplicate_output.setPlainText(
            "\n".join(duplicate_lines)
            if duplicate_lines else "No exact duplicates detected."
        )

    # --------------------------------------------------------
    # WORKERS
    # --------------------------------------------------------

    def start_worker(self, task, *args):
        if self.worker and self.worker.isRunning():
            QMessageBox.information(
                self, "Busy", "Another operation is running."
            )
            return

        self.progress.setVisible(True)
        self.progress.setRange(0, 0)

        self.worker = Worker(task, *args)
        self.worker.status.connect(self.set_status)
        self.worker.done.connect(self.worker_finished)
        self.worker.failed.connect(self.worker_failed)
        self.worker.start()

    def worker_finished(self, result):
        self.progress.setVisible(False)

        if self.task_type == "analysis":
            self.analysis = result
            self.ai_report = ""
            self.update_analysis()
            self.set_status("Local analysis completed.")

        elif self.task_type == "ai":
            self.ai_report = result
            self.ai_output.setPlainText(result)
            self.ai_btn.setEnabled(True)
            self.set_status("Complete AI review generated.")

        elif self.task_type == "commit":
            self.commit_output.setPlainText(result)
            self.commit_btn.setEnabled(True)
            self.set_status("Commit suggestion generated.")

    def worker_failed(self, error):
        self.progress.setVisible(False)
        self.ai_btn.setEnabled(True)
        self.commit_btn.setEnabled(True)

        self.set_status("Operation failed.")

        QMessageBox.critical(
            self, "CodeLens Error", error
        )

    # --------------------------------------------------------
    # AI ACTIONS
    # --------------------------------------------------------

    def current_model(self):
        return self.model_box.currentText().strip()

    def start_ai(self):
        if not self.analysis:
            QMessageBox.warning(
                self, "Analysis required",
                "Analyze the project before starting AI review."
            )
            return

        try:
            validate_env()
        except Exception as error:
            QMessageBox.critical(self, "API key error", str(error))
            return

        prompt = self.ai_prompt.toPlainText().strip()

        if not prompt:
            prompt = (
                "Analyze the entire codebase thoroughly. Identify "
                "all meaningful security, reliability, performance, "
                "architecture and maintainability risks."
            )

        self.task_type = "ai"
        self.ai_btn.setEnabled(False)

        self.start_worker(
            ai_task,
            self.current_model(),
            self.analysis,
            prompt
        )

    def start_commit(self):
        if not self.analysis:
            QMessageBox.warning(
                self, "Analysis required",
                "Analyze the project first."
            )
            return

        try:
            validate_env()
        except Exception as error:
            QMessageBox.critical(self, "API key error", str(error))
            return

        self.task_type = "commit"
        self.commit_btn.setEnabled(False)

        self.start_worker(
            commit_task,
            self.current_model(),
            self.analysis
        )

    def copy_commit(self):
        text = self.commit_output.toPlainText().strip()

        if text:
            QApplication.clipboard().setText(text)
            self.set_status("Commit message copied.")

    # --------------------------------------------------------
    # MODELS
    # --------------------------------------------------------

    def refresh_models(self):
        self.refresh_btn.setEnabled(False)
        self.set_status("Fetching free OpenRouter models...")

        try:
            models = get_free_models()

            if not models:
                raise RuntimeError("No free models found.")

            preferred = self.config.get(
                "model", PREFERRED_MODEL
            )

            self.model_box.clear()
            self.model_box.addItems(models)

            if preferred in models:
                self.model_box.setCurrentText(preferred)
            elif PREFERRED_MODEL in models:
                self.model_box.setCurrentText(PREFERRED_MODEL)
            else:
                self.model_box.setCurrentIndex(0)

            self.config["model"] = self.current_model()
            save_config(self.config)

            self.set_status(
                f"Loaded {len(models)} free models."
            )

        except Exception as error:
            self.model_box.clear()
            self.model_box.addItem(PREFERRED_MODEL)

            self.set_status("Model refresh failed.")

            QMessageBox.warning(
                self, "Model refresh failed", str(error)
            )

        finally:
            self.refresh_btn.setEnabled(True)

    # --------------------------------------------------------
    # PDF EXPORT
    # --------------------------------------------------------

    def export_pdf(self):
        if not self.analysis:
            QMessageBox.warning(
                self, "No analysis",
                "Analyze a project first."
            )
            return

        if not self.ai_report:
            QMessageBox.warning(
                self, "AI review required",
                "Generate the complete AI review first."
            )
            return

        filename = (
            f"CodeLens_Report_"
            f"{datetime.now().strftime('%Y%m%d_%H%M')}.pdf"
        )

        path, _ = QFileDialog.getSaveFileName(
            self,
            "Export CodeLens Report",
            filename,
            "PDF Files (*.pdf)"
        )

        if not path:
            return

        try:
            generate_pdf(self.analysis, self.ai_report, path)

            QMessageBox.information(
                self, "PDF generated",
                f"Report saved successfully:\n{path}"
            )

        except Exception as error:
            QMessageBox.critical(
                self, "PDF error", str(error)
            )


# ============================================================
# ENTRY POINT
# ============================================================

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("CodeLens")

    window = CodeLens()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
