# SPDX-License-Identifier: GPL-3.0-only
"""Consumer desktop bootstrap; the arithmetic interpreter is recovered from pixels."""
import argparse
import json
import os
from pathlib import Path
import queue
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from PIL import Image, ImageTk
import glyph_goblin as app

ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
if os.name == "nt":
    # Tcl's legacy short-path probing can reject a valid long Documents path.
    # PyInstaller first supplies its own bundled library paths; preserve those
    # exact targets while using Windows' extended absolute-path syntax.
    for variable in ("TCL_LIBRARY", "TK_LIBRARY"):
        value = os.environ.get(variable)
        if value and not value.startswith("\\\\?\\"):
            os.environ[variable] = "\\\\?\\" + str(Path(value).resolve())


def backend():
    executable = ROOT / "ocr" / "tesseract.exe"
    model = ROOT / "ocr" / "tessdata"
    if executable.is_file():
        return {"tesseract": str(executable), "tessdata_dir": str(model)}
    return {"tesseract": os.environ.get("TESSERACT_CMD"), "tessdata_dir": os.environ.get("TESSDATA_PREFIX")}


def write_receipt(path, value):
    if path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise app.Rejected("Existing receipt is preserved; choose a new path")
        app.write_json(path, value)


def process(image, output):
    receipt, folder = app.execute_carrier(image, output, **backend())
    return {**receipt, "output_directory": str(folder)}


class Desktop:
    def __init__(self, root, image, output, smoke=False, receipt_path=None):
        self.root, self.path, self.output = root, Path(image), Path(output)
        self.smoke, self.receipt_path = smoke, receipt_path
        self.messages = queue.Queue()
        self.busy = False
        self.failed = False
        self.result = None
        root.title("Glyph Goblin 0.4.0 — Interpreter in pixels")
        root.geometry("980x850")
        bar = ttk.Frame(root, padding=8)
        bar.pack(fill="x")
        self.open_button = ttk.Button(bar, text="Open TIFF / GIF", command=self.open_image)
        self.open_button.pack(side="left")
        self.run_button = ttk.Button(bar, text="Read and run this image", command=self.run)
        self.run_button.pack(side="left", padx=8)
        self.result_button = ttk.Button(bar, text="Show result image", command=self.show_result, state="disabled")
        self.result_button.pack(side="left")
        self.folder_button = ttk.Button(bar, text="Open result folder", command=self.open_folder, state="disabled")
        self.folder_button.pack(side="left", padx=8)
        self.status = tk.StringVar(value="Opening the bundled image…")
        ttk.Label(root, textvariable=self.status, padding=8, wraplength=940).pack(fill="x")
        self.canvas = tk.Canvas(root, background="#101a2b", width=960, height=720, highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        ttk.Label(root, text="Real local OCR → image-resident interpreter → result TIFF/GIF. The CPU bootstrap and OCR engine are external.",
                  padding=8, wraplength=940).pack(fill="x")
        self.photo = None
        self.display_image(self.path)
        root.after(100, self.run)
        root.after(50, self.poll)

    def display_image(self, path, frame=0):
        _, image, _ = app.load_carrier(path, frame)
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

    def open_image(self):
        if self.busy:
            return
        path = filedialog.askopenfilename(title="Open a processable Glyph image", filetypes=[("TIFF / GIF / PNG", "*.tiff *.tif *.gif *.png")])
        if path:
            try:
                self.display_image(path)
                self.path = Path(path)
                self.run()
            except Exception as error:
                messagebox.showerror("Image rejected", str(error))

    def run(self):
        if self.busy:
            return
        self.busy = True
        self.run_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.status.set("Reading visible expressions with independent OCR passes. Results require exact agreement…")
        def worker():
            try:
                self.messages.put((True, process(self.path, self.output)))
            except Exception as error:
                self.messages.put((False, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def poll(self):
        try:
            success, result = self.messages.get_nowait()
        except queue.Empty:
            self.root.after(50, self.poll)
            return
        self.busy = False
        self.run_button.configure(state="normal")
        self.open_button.configure(state="normal")
        if success:
            self.result = result
            self.result_button.configure(state="normal")
            self.folder_button.configure(state="normal")
            values = "   |   ".join(str(value) for value in result["values"])
            self.status.set("Computed from the image: " + values + ". Result TIFF and GIF saved; original expression pixels retained.")
            self.show_result()
            if self.smoke:
                write_receipt(self.receipt_path, {**result, "ui_constructed": True, "automatic_image_execution": True})
                self.root.after(100, self.root.destroy)
                return
        else:
            self.failed = True
            self.status.set("Computation withheld: " + result)
            if self.smoke:
                write_receipt(self.receipt_path, {"accepted": False, "error": result, "ui_constructed": True})
                self.root.after(100, self.root.destroy)
                return
        self.root.after(50, self.poll)

    def show_result(self):
        if self.result:
            self.display_image(Path(self.result["output_directory"]) / "result.gif", len(self.result["values"]))

    def open_folder(self):
        if self.result and hasattr(os, "startfile"):
            os.startfile(self.result["output_directory"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", nargs="?", type=Path, default=ROOT / "demo.tiff")
    parser.add_argument("--process", action="store_true")
    parser.add_argument("--smoke-ui", action="store_true")
    parser.add_argument("--out", type=Path, default=ROOT / "Results")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--version", action="version", version=app.VERSION)
    args = parser.parse_args()
    try:
        if args.process:
            result = process(args.image, args.out)
            write_receipt(args.receipt, result)
            if sys.stdout is not None:
                print(json.dumps(result, indent=2))
            return 0
        root = tk.Tk()
        desktop = Desktop(root, args.image, args.out, args.smoke_ui, args.receipt)
        root.mainloop()
        return 1 if desktop.failed else 0
    except Exception as error:
        if args.receipt:
            write_receipt(args.receipt, {"accepted": False, "error": str(error)})
        if sys.stderr is not None:
            print("Image rejected:", error, file=sys.stderr)
        if not args.process and not args.smoke_ui:
            messagebox.showerror("Glyph Goblin could not start", str(error))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
