# Contributing

Start with a bug report or a small reproducible case. Use a generated synthetic TIFF, not confidential, patient, unpublished, or third-party images you do not have permission to share. Do not paste absolute private paths or acquisition metadata into issues without reviewing them.

Run `python -m pip install -e ".[dev]"`, `python -m pytest -q`, and `python -m build` before submitting a change. Include tests that fail before the fix. Report operating system and package versions when a TIFF decoder or replay result differs.

Useful next contributions:

- Add synthetic fixtures for additional TIFF metadata edge cases.
- Improve error messages for unsupported compression.
- Document verified acquisition-tool export recipes, including their limitations.

Changes to mapping, calibration, crop semantics, PNG rendering, or manifest schema need explicit compatibility notes and exact-pixel tests. Never silently select a Z/time/channel plane or infer physical calibration. New scientific-reliability claims require independent evidence; tests alone do not validate experimental correctness.
