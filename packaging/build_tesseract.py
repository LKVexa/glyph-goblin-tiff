# SPDX-License-Identifier: GPL-3.0-only
"""Build the deliberately minimal native OCR input device from official sources.

Requires Windows x64, CMake and a native MinGW-w64 UCRT GCC toolchain. This does
not download or execute an installer. Pass already-downloaded source archives.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cmake", required=True, type=Path)
    parser.add_argument("--toolchain", required=True, type=Path, help="Native MinGW-w64 UCRT directory, containing bin/gcc.exe")
    parser.add_argument("--tesseract-source", required=True, type=Path)
    parser.add_argument("--leptonica-source", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=False)
    source = work / "source"
    source.mkdir()
    inputs = {}
    for path in (args.tesseract_source, args.leptonica_source):
        inputs[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
        with tarfile.open(path) as archive:
            members = archive.getmembers()
            if len(members) > 10000 or sum(item.size for item in members) > 300 * 1024 * 1024:
                raise ValueError("Source archive limits exceeded")
            archive.extractall(source, filter="data")
    environment = os.environ.copy()
    environment["PATH"] = str(args.toolchain.resolve() / "bin") + os.pathsep + str(Path(environment["SystemRoot"]) / "System32")
    cmake = str(args.cmake.resolve())
    prefix = work / "native"
    common = ["-G", "MinGW Makefiles", "-DCMAKE_BUILD_TYPE=Release", "-DBUILD_SHARED_LIBS=OFF", "-DSW_BUILD=OFF",
              "-DCMAKE_MAKE_PROGRAM=" + str(args.toolchain.resolve() / "bin/make.exe"),
              "-DCMAKE_C_COMPILER=" + str(args.toolchain.resolve() / "bin/gcc.exe"),
              "-DCMAKE_CXX_COMPILER=" + str(args.toolchain.resolve() / "bin/g++.exe"),
              "-DCMAKE_INSTALL_PREFIX=" + str(prefix)]
    def run(arguments):
        subprocess.run([cmake, *arguments], check=True, env=environment, timeout=600)
    leptonica = work / "leptonica-build"
    run(["-S", str(source / "leptonica-1.85.0"), "-B", str(leptonica), *common, "-DBUILD_PROG=OFF",
         *["-DENABLE_" + name + "=OFF" for name in ("ZLIB", "PNG", "GIF", "JPEG", "TIFF", "WEBP", "OPENJPEG")]])
    run(["--build", str(leptonica), "--parallel", "6"])
    run(["--install", str(leptonica)])
    tesseract = work / "tesseract-build"
    flags = ["-DBUILD_TRAINING_TOOLS=OFF", "-DGRAPHICS_DISABLED=ON", "-DDISABLED_LEGACY_ENGINE=ON", "-DENABLE_NATIVE=OFF",
             "-DOPENMP_BUILD=OFF", "-DDISABLE_TIFF=ON", "-DDISABLE_ARCHIVE=ON", "-DDISABLE_CURL=ON",
             "-DCMAKE_EXE_LINKER_FLAGS=-static -static-libgcc -static-libstdc++"]
    run(["-S", str(source / "tesseract-5.5.0"), "-B", str(tesseract), *common, *flags, "-DCMAKE_PREFIX_PATH=" + str(prefix)])
    run(["--build", str(tesseract), "--target", "tesseract", "--parallel", "6"])
    binary = tesseract / "bin/tesseract.exe"
    report = {"source_archives": inputs, "tesseract": "5.5.0", "leptonica": "1.85.0", "input_transport": "lossless BMP",
              "network_and_archive_support": False, "external_image_codecs": False,
              "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "bytes": binary.stat().st_size,
              "cmake_version": subprocess.check_output([cmake, "--version"], text=True).splitlines()[0],
              "compiler_version": subprocess.check_output([str(args.toolchain.resolve() / "bin/g++.exe"), "--version"], text=True, env=environment).splitlines()[0]}
    (work / "tesseract-build.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(binary)


if __name__ == "__main__":
    main()
