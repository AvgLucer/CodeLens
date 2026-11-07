# CodeLens — Source Code

**AI-Powered Code Intelligence & Risk Analysis**

Welcome to the source code directory of **CodeLens**, developed by **AvgLucer | Glox Industries**.

This directory contains the Python implementation, dependency list, and configuration guidance required to run and understand the CodeLens application.

## Project Structure

```text
SRC/
├── codelens.py
├── requirements.txt
├── .env
└── README.md
```

| File | Purpose |
|---|---|
| `codelens.py` | Main CodeLens application |
| `requirements.txt` | Required Python packages |
| `.env` | OpenRouter API configuration |
| `README.md` | Source directory documentation |

## Features

- PySide6-based desktop application.
- AI-powered source code analysis through OpenRouter.
- Project-wide source file scanning.
- Static analysis and potential security risk detection.
- Duplicate file detection using SHA-256.
- AI-generated project summaries and recommendations.
- Risk findings with source file references.
- Commit suggestion assistant.
- Professional PDF report generation.
- Pillow-powered image processing.
- Windows executable packaging support.

## Requirements

- Python 3.10 or newer recommended.
- Internet connection for AI analysis.
- OpenRouter API key.
- Windows recommended for the provided executable build instructions.

## Installation

Open a terminal inside the `SRC` directory.

Install the dependencies:

```bash
pip install -r requirements.txt
```

## API Configuration

CodeLens uses OpenRouter to access compatible AI models.

Create a `.env` file inside the `SRC` directory:

```env
OPENROUTER_API_KEY=sk-or-v1-YOUR_API_KEY
```

Obtain your API key:

https://openrouter.ai/keys

**Security Notice:** Never publish your actual API key or upload your `.env` file to GitHub.

## Running the Application

Execute:

```bash
python codelens.py
```

The CodeLens desktop interface should launch.

Select a project directory to begin inspecting its source code.

## Building a Windows Executable

Install PyInstaller if it is not already installed:

```bash
pip install pyinstaller
```

Build the application:

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name CodeLens --collect-all PySide6 --collect-all reportlab --collect-all PIL --hidden-import dotenv codelens.py
```

The executable will be generated inside:

```text
dist/CodeLens.exe
```

Keep your `.env` file beside the executable:

```text
CodeLens/
├── CodeLens.exe
└── .env
```

The application uses an external environment configuration file so that API credentials do not need to be embedded into the executable.

## Technologies

| Technology | Usage |
|---|---|
| Python | Core application |
| PySide6 | GUI development |
| OpenRouter | AI integration |
| Requests | HTTP communication |
| python-dotenv | Environment configuration |
| Pillow | Image processing |
| ReportLab | PDF generation |
| Python AST | Static code inspection |
| SHA-256 | Duplicate detection |
| PyInstaller | Executable packaging |

## Important Disclaimer

CodeLens is an AI-assisted code analysis tool.

Its findings are not guaranteed to identify every vulnerability, bug, or security issue. Always review generated recommendations and independently verify important findings.

AI analysis requires an internet connection and a valid OpenRouter API key.

## Educational Use & Project Integrity

This source code is provided for educational, teaching, learning, experimentation, and software-understanding purposes.

You may explore the implementation and learn from its architecture. However, do not claim the original project, implementation, or branding as your own.

Appropriate credit must be provided when referencing or using this project.

## Developer Credits

**Developed by AvgLucer**

**Gaurav Wadhwani**  
CEO & Founder at Glox Industries

Project: CodeLens  
Organization: Glox Industries

GitHub Repository:  
<YOUR_GITHUB_REPOSITORY_LINK>

---

**CodeLens — See Beyond the Code.**

Built with dedication by AvgLucer | Glox Industries.
