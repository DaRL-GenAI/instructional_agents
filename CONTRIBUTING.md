# Contributing to Instructional Agents

Thank you for your interest in contributing to Instructional Agents! This document provides guidelines and instructions for contributing.

## Code of Conduct

By participating in this project, you are expected to maintain a respectful and inclusive environment.

## How to Contribute

### Reporting Issues

- **Bug Reports**: Please use the GitHub Issues to report bugs. Include:
  - A clear description of the issue
  - Steps to reproduce
  - Expected vs actual behavior
  - Environment information (OS, Python version, etc.)

- **Feature Requests**: Open an issue with the "feature request" label and describe:
  - The problem you're trying to solve
  - Your proposed solution
  - Any alternatives you've considered

### Contributing Code

1. **Fork the Repository**
   ```bash
   git clone https://github.com/YOUR_USERNAME/instructional_agents.git
   cd instructional_agents
   ```

2. **Create a Branch**
   ```bash
   git checkout -b feature/your-feature-name
   # or
   git checkout -b fix/your-bug-fix
   ```

3. **Make Your Changes**
   - Follow the existing code style
   - Add comments for complex logic
   - Update documentation if needed
   - Test your changes thoroughly

4. **Test Your Changes**
   ```bash
   # Install dependencies
   pip install -r requirements.txt
   
   # Run your tests (if applicable)
   python -m pytest  # or your test command
   ```

5. **Commit Your Changes**
   ```bash
   git add .
   git commit -m "Description of your changes"
   ```
   - Write clear, descriptive commit messages
   - Reference issue numbers if applicable

6. **Push and Create Pull Request**
   ```bash
   git push origin feature/your-feature-name
   ```
   - Open a Pull Request on GitHub
   - Provide a clear description of your changes
   - Reference related issues

## Development Setup

See the [Local Development Setup](../README.md#-local-development-setup) section in the main README for detailed instructions.

## Code Style

- Follow PEP 8 for Python code
- Use meaningful variable and function names
- Add docstrings to functions and classes
- Keep functions focused and modular

## Documentation

- Update relevant documentation when adding features
- Keep code comments clear and concise
- Update README.md if adding new features that affect usage

## Pull Request Process

1. Ensure your code passes any existing tests
2. Update documentation as needed
3. Request review from maintainers
4. Address any feedback or requested changes
5. Once approved, maintainers will merge your PR

## Questions?

Feel free to open an issue for any questions about contributing!

