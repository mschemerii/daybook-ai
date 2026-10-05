# GitHub Actions Workflows

This directory contains CI/CD workflows for Daybook AI v0.9 and beyond.

## Workflows

### test.yml
Runs the full test suite on Ubuntu, Windows, and macOS. Validates:
- All 296 unit/integration tests pass (offscreen Qt)
- Python compilation check (`compileall`)
- Git diff integrity

### build-macos.yml
Builds a macOS application using py2app/PyInstaller. Triggers on:
- Tag pushes (v*)
- Manual dispatch

### build-windows.yml
Builds a Windows executable using PyInstaller. Triggers on:
- Tag pushes (v*)
- Manual dispatch

### build-linux.yml
Builds a Linux executable using PyInstaller. Triggers on:
- Tag pushes (v*)
- Manual dispatch

### release.yml
Creates GitHub Releases with build artifacts from all three platforms. Triggers on:
- Tag pushes (v*)

## Usage

### Triggering builds manually
```bash
# From GitHub UI: Actions > workflow_dispatch on any build/release workflow
```

### Creating a release tag
```bash
git tag -a v0.9.1 -m "Release v0.9.1"
git push origin v0.9.1
```

This will trigger:
1. Build workflows for all three platforms
2. Release workflow to create GitHub Release with artifacts

## Architecture Decisions

### Packaging Tools
- **macOS**: PyInstaller (cross-platform consistency)
- **Windows**: PyInstaller
- **Linux**: PyInstaller

### Data Bundling
The `data/` directory is bundled with each executable using `--add-data`. This includes:
- Default database schema migrations
- Demo seed data scripts

### Model Handling
The llama.cpp model (`models/Qwen3.5-0.8B-UD-Q4_K_XL.gguf`) is NOT bundled with the executable. Users must:
1. Have the model downloaded locally, or
2. Configure `DAYBOOK_MODEL_PATH` to point to a local GGUF file

This keeps executable sizes manageable and respects user data ownership.

### Authentication
Each build generates a fresh API key for llama.cpp requests. The key is stored in the `.env` file and should never be committed to version control.

## Limitations

- **No code signing**: Executables are unsigned. macOS users may need to allow "Developer ID" apps in System Preferences > Security & Privacy.
- **No notarization**: macOS builds are not notarized for App Store distribution.
- **Single-user only**: No multi-user or network deployment support.
- **No auto-update**: Users must manually download and install updates.

## Future Improvements (Phase 12+)

- Code signing and notarization for macOS
- Auto-update mechanism
- Cross-platform installer generation (pkg, MSI, AppImage)
- Checksums and SHA-256 verification
- Release notes automation from commit history
