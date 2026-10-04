# Daybook AI Development Guide

## Environment Setup

### Prerequisites
- Python 3.12.x
- macOS, Windows, or Linux (x86_64 or ARM64)
- llama.cpp with `llama-server` binary (optional, for AI features)

### Installation
```bash
git clone https://github.com/mschemerii/daybook-ai.git
cd daybook-ai
bash install.sh
```

### Virtual Environment
The installer creates a `.venv` directory. Activate it:
```bash
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows
```

## Running Tests

### Full Test Suite (Offscreen)
```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q --tb=short
```

### Specific Test Categories
```bash
# Desktop tests only
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/desktop/

# Lifecycle and reporting tests
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_lifecycle*.py

# AI integration tests (requires llama.cpp running)
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/test_model_runtime.py
```

### Code Compilation Check
```bash
.venv/bin/python -m compileall -q run.py src tests scripts
```

### Git Integrity Check
```bash
git diff --check
```

## Running the Application

### Desktop Mode
```bash
.venv/bin/python run.py --desktop
```

Or simply:
```bash
.venv/bin/python run.py
```

### Configuration
Edit `.env` to configure:
- Database path (`DAYBOOK_DB_PATH`)
- Model settings (`DAYBOOK_MODEL_*`)
- Controller ports (`DAYBOOK_CONTROLLER_*`)

## Development Workflow

### Branching Strategy
```
main (production)
├── feature/* (new features)
├── bugfix/* (bug fixes)
└── chore/* (refactoring, cleanup)
```

### Commit Messages
Follow conventional commits:
- `feat:` New feature
- `fix:` Bug fix
- `chore:` Maintenance, cleanup
- `docs:` Documentation changes

### Pull Requests
1. Create a feature branch from `main`
2. Make your changes
3. Run tests: `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/`
4. Push and create a PR to `main`
5. Ensure all CI checks pass

## Architecture Overview

### Core Modules
- **src/desktop/**: PySide6 UI components and application logic
- **src/runtime/**: Runtime initialization, hardware detection, model management
- **src/repositories/**: Database operations and data access patterns
- **src/services/**: Business logic for tasks, reporting, exports
- **src/models/**: Data models and entity definitions

### Database Schema
SQLite database at `data/daybook.db` with versioned migrations.

### AI Integration
- Uses llama.cpp's OpenAI-compatible API
- Local model: `Qwen3.5-0.8B-UD-Q4_K_XL.gguf`
- Human approval required before AI-originated changes persist

## Troubleshooting

### PySide6 Import Errors
```bash
.venv/bin/pip install --upgrade PySide6
```

### llama.cpp Not Found
Ensure `llama-server` is in your PATH or set `DAYBOOK_LLAMA_SERVER` in `.env`.

### Database Migration Issues
```bash
# Backup first
cp data/daybook.db data/daybook.db.backup

# Delete and recreate (data loss!)
rm data/daybook.db
.venv/bin/python run.py --desktop
```

### Test Failures on CI
Ensure `QT_QPA_PLATFORM=offscreen` is set for headless testing.

## Release Process (Phase 12)

### Building Executables
GitHub Actions automatically builds executables on tag pushes:
```bash
git tag -a v0.9.1 -m "Release v0.9.1"
git push origin v0.9.1
```

### Manual Build (Local)
```bash
# macOS
python -m PyInstaller --name DaybookAI --windowed --onefile run.py

# Windows
pyinstaller --name DaybookAI --windowed --onefile run.py

# Linux
pyinstaller --name DaybookAI --windowed --onefile run.py
```

## Code Style

- Follow PEP 8 guidelines
- Use type hints for function signatures
- Add docstrings to public APIs
- Keep functions focused and testable

## Security Considerations

- No network access by default (loopback-only)
- API keys generated per-launch for llama.cpp
- Database files stored locally
- No external dependencies beyond requirements.txt

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests and ensure they pass
5. Submit a pull request

See [CONTRIBUTING.md](./CONTRIBUTING.md) for detailed contribution guidelines.
