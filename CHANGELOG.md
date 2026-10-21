# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the version numbers follow
[Semantic Versioning](https://semver.org/): `major.minor.patch`.

- **Major**: incompatible behaviour changes (config key renames, CLI changes, minimum Python bump)
- **Minor**: backwards-compatible features
- **Patch**: backwards-compatible fixes

## [Unreleased]

Nothing yet.

## [1.3.0] - 2026-10-21

### Added

- **Subject text filter** (`screengrab/subject.py`): decides which layer of text the user wants by
  font size × ink chroma, and drops the background text sitting underneath. On by default; the
  `Subject 3/8` button in the result window switches back to all text, and the pill context menu can turn it off.
- Config key `subject_filter`: `auto` (default) / `off` / `large` / `red` / `color:blue`.
- Subject toggle in the result window; the change panel states the criterion
  (`Subject red · 144px large · 5 boxes filtered`).
- `python -m screengrab` and the `textgrabber` console entry point.

### Fixed

- **Headlines merged with the body text behind them**: line grouping now requires a height ratio
  below 2.2 and a horizontal overlap below 0.35. Before the fix the same region produced 122 characters
  of scrambled text; now it reconstructs as three correct lines.
- The subject filter no longer deletes anything when the requested colour is absent; it falls back to all text.

### Changed

- In stylised display text, the raw view reads much closer to the original reading order.
- Docs: `docs/技术方案.html` gained section 09 (subject filter); sections 09–12 shifted down.

## [1.2.0] - 2026-10-21

### Added

- **Text tidying** (`screengrab/tidy.py`): merges hard wraps introduced by window width, normalizes
  punctuation, removes noise spaces between CJK characters, re-blocks headings and lists, and applies
  conservative typo correction.
- Tidied/raw views and a change panel in the result window: counts, before/after samples and a
  content-similarity score for every rule.
- Config keys `tidy_enabled` and `result_view`; the pill menu can disable tidying.

### Changed

- The result window wraps text with no horizontal scrollbar; below 480 logical pixels the buttons become a 2×2 grid.

## [1.1.0] - 2026-10-20

### Added

- **Structure analysis** (`screengrab/structure.py`): column candidates, row signatures, block segmentation,
  cell recovery and font-size levels, distinguishing icon grids, parameter tables and multi-column prose.
- `layout.py` rewritten as per-block dispatch: grids align columns with tabs, columns are read one at a
  time, and headings form their own level.

### Fixed

- Adjacent rows in a grid collapsing into one (`Name John  Dept R&D`); single-letter badges (`W`, `ZIP`)
  no longer occupy a row of their own.

## [1.0.0] - 2026-10-20

### Added

- First release: global hotkey `Ctrl+Alt+Q` → local RapidOCR → editable, copyable result window.
- Floating pill entry point, 9× magnifier, `Ctrl+Alt+D` to re-read the last region, multi-monitor and
  high-DPI support.
- Pluggable OCR backends with a fallback chain: RapidOCR 3.x → RapidOCR 1.x → PaddleOCR.
- Configuration persisted to `%APPDATA%\TextGrabber\config.json`.

[Unreleased]: https://github.com/nineone-spirits/nineone-spirits/compare/v1.3.0...HEAD
[1.3.0]: https://github.com/nineone-spirits/nineone-spirits/releases/tag/v1.3.0
[1.2.0]: https://github.com/nineone-spirits/nineone-spirits/releases/tag/v1.2.0
[1.1.0]: https://github.com/nineone-spirits/nineone-spirits/releases/tag/v1.1.0
[1.0.0]: https://github.com/nineone-spirits/nineone-spirits/releases/tag/v1.0.0
