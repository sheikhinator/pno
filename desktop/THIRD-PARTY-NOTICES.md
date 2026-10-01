# Third-party notices

This preview is not an official Majid Al Futtaim or Carrefour product. No corporate logos or proprietary data are included.

- Python: Python Software Foundation license; included in the release package.
- PySide6 / Qt: LGPLv3/GPLv3/commercial licensing, depending on components. This project uses LGPL-available QtCore, QtGui and QtWidgets, with custom-painted charts; QtCharts is not used. Source and rebuild instructions are provided in the repository. Review the LGPL obligations, including library replacement and notice requirements, with corporate legal before distribution.
- openpyxl and et-xmlfile: MIT; xlrd: BSD.
- reportlab: BSD.
- llama.cpp / llama-cpp-python: MIT.
- Qwen2.5-0.5B-Instruct: Apache License 2.0. The model's license accompanies the model pack.
- PyInstaller: GPL with its distribution exception.

Release packaging copies available notices from the installed dependency distributions and downloads version-pinned LGPLv3, Python Software Foundation, openpyxl and et-xmlfile license texts, checking each SHA-256 before packaging. See `licenses/INVENTORY.txt` and `licenses/upstream/PYTHON-SHA256SUMS.txt` inside the Windows ZIP. If a required source is unavailable or its checksum changes, packaging stops. Preserve these notices with the redistribution and have corporate legal review third-party obligations before operational rollout.
