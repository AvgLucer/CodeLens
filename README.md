 <p align="center">
  <img src="banner.png" alt="CodeLens Banner" width="100%">
</p>

<h1 align="center">CodeLens</h1>

<p align="center">
  <strong>See Beyond the Code.</strong><br>
  AI-Powered Code Intelligence & Risk Analysis
</p>

<p align="center">
  Analyze. Understand. Secure. Improve.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Developer-AvgLucer-D4AF37?style=for-the-badge">
  <img src="https://img.shields.io/badge/Company-Glox%20Industries-111111?style=for-the-badge">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/AI-OpenRouter-6366F1?style=for-the-badge">
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Framework-PySide6-41CD52?style=flat-square&logo=qt">
  <img src="https://img.shields.io/badge/Reports-ReportLab-red?style=flat-square">
  <img src="https://img.shields.io/badge/Imaging-Pillow-yellow?style=flat-square">
  <img src="https://img.shields.io/badge/HTTP-Requests-2CA5E0?style=flat-square">
  <img src="https://img.shields.io/badge/Config-python--dotenv-green?style=flat-square">
  <img src="https://img.shields.io/badge/Platform-Windows-0078D6?style=flat-square&logo=windows">
</p>

---

## Overview

**CodeLens** is a desktop-based AI-powered source code analysis application developed under **Glox Industries**.

It combines traditional static analysis techniques with AI-powered code intelligence to help developers understand their projects, identify potential weaknesses, inspect code quality, and generate structured reports.

Instead of manually navigating hundreds of source files, CodeLens provides a centralized analysis workflow with downloadable PDF documentation.

## Features

| Feature | Description |
|---|---|
| Project Scanning | Scan project directories and discover supported source files. |
| Static Code Analysis | Identify potentially unsafe coding patterns and common programming issues. |
| AI Code Intelligence | Use OpenRouter-powered AI to review source code in batches. |
| Security Risk Detection | Highlight potential vulnerabilities and risky implementations. |
| Code Quality Insights | Identify maintainability concerns and areas for improvement. |
| Duplicate Detection | Detect exact duplicate files using SHA-256 hashing. |
| Risk Findings | Display findings with relevant file paths and line references where available. |
| AI Summary Generator | Generate consolidated project-level analysis and recommendations. |
| Commit Assistant | Suggest commit summaries based on project inventory and detected findings. |
| PDF Report Generator | Export structured project analysis into downloadable PDF reports. |
| Desktop Interface | Dedicated PySide6 interface with multiple analysis sections. |
| Free Model Support | Connect to compatible free models available through OpenRouter. |

## Technology Stack

| Technology | Purpose |
|---|---|
| Python | Core application logic |
| PySide6 | Desktop graphical interface |
| OpenRouter API | AI-powered source code analysis |
| Requests | API communication |
| python-dotenv | Environment variable configuration |
| Pillow (PIL) | Image processing and visual assets |
| ReportLab | PDF report generation |
| Python AST | Python source-code inspection |
| SHA-256 | Exact duplicate file detection |
| PyInstaller | Standalone Windows executable packaging |

## Getting Started

### 1. Clone the repository

```bash
git clone <YOUR_GITHUB_REPOSITORY_LINK>
cd CodeLens
```

### 2. Install dependencies

```bash
pip install PySide6 requests python-dotenv Pillow reportlab pyinstaller
```

### 3. Configure OpenRouter

Create a `.env` file in the same directory as `codelens.py`.

```env
OPENROUTER_API_KEY=sk-or-v1-YOUR_API_KEY
```

Get an API key from:

https://openrouter.ai/keys

**Important:** Never upload your actual API key to GitHub. Keep `.env` private and add it to `.gitignore`.

### 4. Run CodeLens

```bash
python codelens.py
```

## Building the Windows Executable

CodeLens can be packaged into a standalone Windows executable using PyInstaller.

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name CodeLens --collect-all PySide6 --collect-all reportlab --collect-all PIL --hidden-import dotenv codelens.py
```

Your executable will be generated at:

```text
dist/CodeLens.exe
```

Keep your `.env` file alongside the executable:

```text
CodeLens/
├── CodeLens.exe
└── .env
```

The API key is loaded at runtime from the external `.env` file.

## Important Notes

- AI analysis requires a valid OpenRouter API key and an internet connection.
- Analysis quality depends on the selected AI model and its context limits.
- Static analysis identifies potential issues; findings should be manually reviewed.
- AI-generated recommendations are suggestions, not guarantees of security.
- Large projects may require additional processing time.

## Educational Use & Project Integrity Warning

This project is provided for **educational, teaching, learning, experimentation, and software-understanding purposes**.

Users are welcome to explore its architecture, understand its implementation, and learn from its features.

**Do not claim this project, its original implementation, or its branding as your own work.** If you use or reference this project, provide appropriate credit to its original developer.

## Credits & Development

<p align="center">
  <strong>Developed by AvgLucer</strong><br>
  <strong>Gaurav Wadhwani</strong><br>
  CEO & Founder at Glox Industries
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Built%20with-Python-3776AB?style=for-the-badge&logo=python&logoColor=white">
  <img src="https://img.shields.io/badge/Powered%20by-OpenRouter-6366F1?style=for-the-badge">
</p>

---

<p align="center">
  <strong>CodeLens — See Beyond the Code.</strong><br>
  Built with dedication by AvgLucer | Glox Industries
</p>
