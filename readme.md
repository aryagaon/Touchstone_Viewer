# Touchstone_Viewer
A lightweight local web app for viewing and comparing Touchstone **.s2p / .sNp** files using **Python + scikit-rf** with a clean UI built on **Streamlit**.
## What it does
- Upload **multiple** Touchstone files and compare them
- Choose **traces per file** (e.g., *File A: S11* vs *File B: S11*) and overlay them on one plot
- Plots:
  - Magnitude (dB or linear)
  - Phase (optional unwrap)
  - Group delay
  - Smith chart overlay (best for reflections)
- Customize plots:
  - X/Y limits
  - Axis labels and title
  - Legend options (show/hide, location, columns, font size, frame)
- Export from plots:
  - **PNG** (with DPI selection)
  - **JPG**
  - **CSV (wide / Excel-style)**: one column per curve
---
## Screenshots
- `docs/screenshot-magnitude.png`

- `docs/screenshot-smith.png`
---
## Repo contents

- Touchstone_Viewer/
  - app.py
  - requirements.txt
  - touchstone_viewer.bat   (optional Windows launcher)
  - README.md
  - LICENSE
 ---
# Quick start (recommended: virtual environment)

## Windows (PowerShell)

``` PowerShell
cd path\to\Touchstone_Viewer
py -3 -m venv .venv
.\.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```
## Linux
```bash
cd path/to/Touchstone_Viewer
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m streamlit run app.py
```
## Windows launcher batch (optional)
1. Install Python 3.9+
2. Download repo ZIP and extract 
3. In PowerShell, pip install -r requirements.txt
4. Double-click touchstone_viewer.bat
## How to use the app

1. Upload one or more `.s2p` / `.sNp` files (multi-file upload uses Streamlit’s uploader). 
2. For each file:
    - Give it a short legend label (used in plot legends)
    - Select the traces you want (S-parameters)
3. Select a frequency window.
4. Use the tabs to view plots and Smith chart.
5. Use **Save as…** on each plot to download PNG/JPG/CSV.
---
## Export formats
### PNG / JPG
Exports the current plot as an image.
- PNG includes a DPI selector for higher/lower resolution.
### CSV (wide / Excel-style)
- Index columns: `freq_Hz`, `freq_GHz`
- One column per curve: `FileLabel · Sij`
---
## Troubleshooting
### `No module named streamlit` (or similar)
Install dependencies in the same Python environment you are running:
```bash
Copypython -m pip install -r requirements.txt
```
### SSL / corporate proxy errors during pip install
If you see errors like: `SSLCertVerificationError: certificate verify failed`
You are likely behind SSL inspection or a corporate proxy. The correct fixes are:
- Use a corporate CA bundle with pip (`--cert` or environment variables like `PIP_CERT` / `REQUESTS_CA_BUNDLE`) [Source](https://pip.pypa.io/en/stable/topics/https-certificates/)
- Use your company’s internal PyPI mirror (Artifactory/Nexus/etc.)
Ask IT for the approved configuration.
### Port already in use
Run Streamlit on a different port:
```bash
Copypython -m streamlit run app.py --server.port 8502
```
Streamlit run options are documented here. [Source](https://docs.streamlit.io/develop/api-reference/cli/run)

---
## Credits
- UI framework: Streamlit docs: [https://docs.streamlit.io/](https://docs.streamlit.io/)
- RF Touchstone/network handling: scikit-rf Network tutorials: [https://scikit-rf.readthedocs.io/en/v1.8.0/tutorials/Networks.html](https://scikit-rf.readthedocs.io/en/v1.8.0/tutorials/Networks.html)
- Group delay concept/property in scikit-rf: [https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.network.Network.group_delay.html](https://scikit-rf.readthedocs.io/en/latest/api/generated/skrf.network.Network.group_delay.html)
---
## License

MIT License — see [LICENSE](https://www.genspark.ai/LICENSE).

````

---

# `LICENSE` (MIT)

Replace the copyright holder line with your name or your organization.

```text
MIT License

Copyright (c) 2026 <YOUR NAME OR ORG>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
````