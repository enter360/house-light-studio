# Contributing to House Light Studio

Thanks for your interest! This is a single-file browser app — contributions of all sizes are welcome, from fixing typos to adding major features.

## Getting Started

No build step required. Just open `index.html` in a browser and start hacking.

```bash
git clone https://github.com/YOUR_USERNAME/house-light-studio.git
cd house-light-studio
open index.html   # macOS
# or: xdg-open index.html (Linux)
# or: start index.html (Windows)
```

## How to Contribute

1. Fork the repo and create a branch: `git checkout -b feature/your-feature`
2. Make your changes in `index.html` (or add new files as needed)
3. Test in at least one modern browser
4. Open a pull request with a clear description of what changed and why

## Reporting Bugs

Open an issue with:
- Your browser + version
- Your Govee device model (if relevant)
- Steps to reproduce
- What you expected vs what happened

## Device Compatibility

If you've tested with a device not listed in the README, please open a PR or issue to add it to the supported devices table. Include:
- Device model (SKU)
- Number of segments
- Whether Grafiti mode worked as-is or needed tweaks

## Code Style

- Vanilla JS, no frameworks
- Keep it as a single `index.html` unless a feature genuinely requires separate files
- CSS variables for all colors (existing theme in `:root`)
- Comment non-obvious protocol logic

## Protocol Research

If you're reverse-engineering Govee protocols, document your findings in `docs/protocol.md` and link to any upstream issues/repos.

## License

By contributing, you agree your contributions will be licensed under the MIT License.
