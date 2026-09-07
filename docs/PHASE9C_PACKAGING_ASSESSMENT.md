# Phase 9C desktop packaging assessment

## Decision

Daybook AI should complete Phase 9C as a stable source-run PySide6 application.
Packaging is feasible but is not a functional-completion requirement. No
packaging framework or build output is added in this phase.

## Recommended approach

The leading Phase 10 candidate is Qt's `pyside6-deploy`, which wraps Nuitka,
accepts the main Python entry point, manages Qt module/plugin collection, and
produces `.app` output on macOS and `.exe` output on Windows. PyInstaller is the
primary alternative and should be included in the packaging spike. Either tool
introduces a major build dependency and generated configuration, so the choice
must be approved and pinned on a dedicated packaging branch before adoption.

The packaging entry point should be `run.py` with no arguments. That path now
starts the native application. The legacy `--streamlit` mode is transitional
and does not need to be included in a final desktop distribution unless Phase
10 deliberately retains it.

## Runtime inputs and writable data

| Concern | Packaging requirement |
|---|---|
| PySide6 | Collect Qt libraries and platform plugins; verify Cocoa on macOS and the Windows platform plugin on Windows. |
| Python modules | Include `src`, migrations, report generation dependencies, and required package metadata. |
| Model | Keep the GGUF outside the executable bundle. Reuse or download it into a user-writable application-data directory. |
| llama.cpp | Ship a separately validated per-platform executable or download the pinned verified runtime into application data. Preserve process-handle ownership. |
| SQLite | Move the default database from the source tree to a user-writable application-data directory for packaged builds. Preserve configurable paths and migrations. |
| Preferences | Store preferences beside other user data, not inside a signed/read-only application bundle. |
| Exports | Continue using the native save dialog and user-selected destination. |

The source-run defaults remain unchanged in Phase 9C. Selecting and migrating
packaged writable-data locations is Phase 10/distribution work and requires a
backward-compatible policy for existing databases.

## Platform considerations

### macOS

- Build separately for Apple silicon and Intel unless a tested universal build
  is produced.
- Sign the `.app` and all nested executables/libraries with an Apple Developer
  ID, enable hardened runtime, notarize the distribution, and staple the
  notarization ticket.
- Verify Qt Cocoa plugins, report fonts, spawned `llama-server`, quarantine,
  executable permissions, first-launch downloads, and clean model shutdown.
- Expected artifacts are a signed `.app` plus a signed/notarized DMG or ZIP.

### Windows

- Build on Windows for the target architecture and verify PySide6 plugins,
  path quoting, antivirus behavior, long paths, and the selected llama.cpp CPU,
  CUDA, HIP, or SYCL package.
- Code-sign the executable and installer. An installer such as Inno Setup or
  WiX can be assessed after the frozen application is stable.
- Expected artifacts are a signed application directory or executable plus a
  signed installer.

## Work remaining before distribution

1. Compare `pyside6-deploy` and current PyInstaller with a minimal signed-build
   spike, then approve and pin one packaging framework.
2. Define platform-specific application-data directories and an existing-data
   migration/selection policy.
3. Create deterministic resource collection and hidden-import configuration.
4. Decide whether llama.cpp is bundled or downloaded after install.
5. Build on each target operating system; packaging is not cross-platform.
6. Exercise install, upgrade, uninstall, model download, offline fallback,
   exports, database persistence, and owned/external process lifecycle.
7. Add signing, notarization, artifact checksums, and release automation.

## Phase 9C readiness conclusion

The application entry point and direct service composition are packaging-ready.
Distribution is not yet release-ready because writable-data placement,
framework selection, platform builds, signing/notarization, and installer
validation remain intentionally deferred.

## Primary references

- [Qt for Python: pyside6-deploy](https://doc.qt.io/qtforpython-6/deployment/deployment-pyside6-deploy.html)
- [Qt for Python: PyInstaller](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)
- [PyInstaller: supporting multiple platforms](https://pyinstaller.org/en/stable/usage.html#supporting-multiple-platforms)
- [Apple: notarizing macOS software](https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution)
- [Microsoft SignTool](https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool)
