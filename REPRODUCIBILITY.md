# Rebuilding and checking Glyph Goblin 0.4.0

The TIFF/GIF contains the reviewed interpreter source, compressed into black/white pixels, plus visible expression glyphs. `runtime_bootstrap.py` checks the approved source SHA-256 before compiling those exact recovered bytes in memory. CPython, `ast`, `math`, `operator`, image decoding, JA21 preprocessing, Tesseract and the desktop UI are external bootstrap components. Neither the frozen executable nor its ordinary support files contain an importable copy of the interpreter. `source.zip` is corresponding source for developers; the player never opens it.

The approved interpreter SHA-256 is `b21b3a8d0e9a96466477423f1c03ccae296a7f4c472a5ae8471aee2b122a1513`. Source normalization is UTF-8 with LF line endings; gzip uses a zero modification time. `python build_runtime.py` regenerates the payload and approved-hash module from reviewed `image_interpreter.py`. A changed module requires a newly reviewed bootstrap allowlist and newly authored images; a stock player rejects it. Visible supported operators may be changed without replacing the interpreter.

## Source tests

Use Python 3.12 and install `requirements.txt`. The audited Windows build used Python 3.12.14, NumPy 2.3.5 and Pillow 12.3.0. Set the following paths to your local Tesseract executable and directory containing `eng.traineddata`:

```powershell
python -m pip install -r requirements.txt
python build_runtime.py
$env:TESSERACT_TEST_CMD = (Resolve-Path .\ocr\tesseract.exe).Path
$env:TESSDATA_PREFIX = (Resolve-Path .\ocr\tessdata).Path
python -m unittest discover -s tests -v
python run.py run demo.tiff --tesseract $env:TESSERACT_TEST_CMD --tessdata-dir $env:TESSDATA_PREFIX
```

The real-backend tests are skipped when `TESSERACT_TEST_CMD` is absent; a skipped run does not establish real OCR correctness. The tests exercise exact AST agreement, resource limits, damaged pixels, unsupported modules, output preservation, actual operator-only image mutations, and reexecution of output TIFF/GIF images.

## Minimal OCR sensor

Obtain the official [Tesseract 5.5.0 source](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.0), [Leptonica 1.85.0 source](https://github.com/DanBloomberg/leptonica/releases/tag/1.85.0), and [English tessdata_fast model](https://github.com/tesseract-ocr/tessdata_fast/blob/main/eng.traineddata). Exact source archive hashes and the model hash are in `audit.json` and the consumer package manifest. The release includes those source archives. The model is pinned by content hash, not by the moving upstream branch name.

The audited compiler was native MinGW-w64 UCRT GCC 16.2.0 with CMake 4.4.4. Set `UCRT_TOOLCHAIN` to its root directory, containing `bin/gcc.exe`, `bin/g++.exe` and `bin/make.exe`. Set `CMAKE_EXE` to CMake. The following uses local archives and makes no network requests:

```powershell
python packaging/build_tesseract.py --cmake $env:CMAKE_EXE --toolchain $env:UCRT_TOOLCHAIN --tesseract-source downloads/tesseract-5.5.0.tar.gz --leptonica-source downloads/leptonica-1.85.0.tar.gz --work build/native-ocr
```

The build disables legacy OCR, graphics, OpenMP, network/archive support and external image codecs, and statically links the compiler runtimes. The sensor receives lossless BMP files generated after JA21 preprocessing. It does not need TIFF/GIF codecs itself. The Python image reader validates and decodes the carrier first. The produced executable imports only Windows system/UCRT libraries; the packager checks that allowlist.

## Windows consumer ZIP

On Windows x64, install PyInstaller 6.22.3 into a local build-tools directory. Supply the compiler distribution's license folder. The bundler uses fresh staging, excludes the interpreter module, preserves existing ZIPs, and includes exact dependency notices and corresponding project source.

```powershell
python -m pip install --target build-tools PyInstaller==6.22.3
python package_release.py --pyinstaller-path build-tools --tesseract build/native-ocr/tesseract-build/bin/tesseract.exe --model downloads/eng.traineddata --tesseract-source downloads/tesseract-5.5.0.tar.gz --leptonica-source downloads/leptonica-1.85.0.tar.gz --compiler-licenses "$env:UCRT_TOOLCHAIN/share/licenses" --out releases/Glyph-Goblin-0.4.0-win-x64.zip
```

Packaging must pass all executable checks before creating the ZIP: original and operator-edited TIFF/GIF programs, four output-image reexecutions, blank-glyph and unapproved-runtime rejection, and automatic desktop execution. These checks remove Python/Tesseract/.NET settings and installed-toolchain directories from the child process environment. The embedded-archive audit requires the loader and hash allowlist while rejecting an interpreter fallback.

The ZIP has sorted entries and fixed timestamps. This makes packaging the same staged files repeatable. A complete native/frozen rebuild is not claimed byte-identical across different compilers, Python distributions or build paths. Check the build manifest's individual file hashes, interpreter identity and executable tests rather than treating an unverified binary hash as equivalent. Windows security policy is respected; the scripts fail if execution is blocked and do not change policy or attempt bypasses.

This is a bounded OCR arithmetic demonstration. It is not a general Python sandbox, optical computer, or claim that all 32 Penteract workflow packages have passed release qualification. OCR agreement does not establish ground truth.
