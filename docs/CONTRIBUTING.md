# Contributing to Daybook AI

Thank you for your interest in contributing to Daybook AI! This document provides guidelines and instructions for contributors.

## Code of Conduct

- Be respectful and inclusive in all interactions
- Provide constructive feedback
- Focus on what's best for the project and community

## Getting Started

1. **Fork** the repository on GitHub
2. **Clone** your fork locally:
   ```bash
   git clone https://github.com/your-username/daybook-ai.git
   cd daybook-ai
   ```
3. **Set up** the development environment:
   ```bash
   bash install.sh
   ```
4. **Create** a new branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Guidelines

### Code Style
- Follow PEP 8 guidelines
- Use type hints for function signatures
- Add docstrings to public APIs
- Keep functions focused and testable

### Testing
- Run the full test suite before submitting:
  ```bash
  QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest tests/ -q --tb=short
  ```
- Write tests for new features
- Ensure existing tests still pass

### Commit Messages
Follow conventional commits format:
- `feat:` New feature
- `fix:` Bug fix
- `chore:` Maintenance, cleanup
- `docs:` Documentation changes
- `refactor:` Code refactoring

Example:
```
feat(desktop): add task completion dialog with AI suggestions

Implements a new dialog that shows AI-generated task
decomposition proposals when completing tasks. Users can
accept, modify, or reject the suggestions.

Co-authored-by: Claude Code <noreply@anthropic.com>
```

## Pull Request Process

1. **Sign off** your commits with `Co-authored-by` line
2. **Update** documentation if needed
3. **Run** all tests and ensure they pass
4. **Push** your branch to GitHub:
   ```bash
   git push origin feature/your-feature-name
   ```
5. **Create** a pull request to `main` branch
6. **Fill out** the PR template with:
   - Description of changes
   - Motivation for changes
   - Testing performed
   - Screenshots (for UI changes)

## PR Review Process

1. Maintainers will review your PR
2. Address any feedback or requested changes
3. Ensure all CI checks pass
4. Request approval from maintainers
5. Once approved, your PR will be merged

## Reporting Issues

When reporting bugs or requesting features:
- Describe the problem clearly
- Provide steps to reproduce (for bugs)
- Include expected vs actual behavior
- Mention your environment (OS, Python version)

## Architecture Decisions

Major changes should include:
- Clear rationale for the approach
- Impact analysis on existing functionality
- Migration plan if needed
- Performance considerations

## Security Considerations

- No external network access by default (loopback-only)
- API keys generated per-launch for llama.cpp
- Database files stored locally
- No external dependencies beyond requirements.txt

## Getting Help

- Check existing issues and documentation
- Ask questions in the project's discussion channel
- Reach out to maintainers for guidance

## License

By contributing, you agree that your contributions will be licensed under the project's license.

## Questions?

Reach out to the maintainers or open an issue for clarification.
