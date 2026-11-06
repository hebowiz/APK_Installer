"""Simple Android APK installer. Python 3.11+, standard library only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from dataclasses import dataclass

APP_NAME = "ADB APK Installer"


def settings_path() -> Path:
    base = Path(os.environ.get("APPDATA", str(Path.home() / ".config")))
    return base / "ADB_APK_Installer" / "settings.json"


def load_settings(path: Path) -> tuple[dict, str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("設定の形式が不正です")
        return {key: value[key] for key in ("adb_path", "apk_path")
                if isinstance(value.get(key), str)}, ""
    except FileNotFoundError:
        return {}, ""
    except (OSError, ValueError) as error:
        return {}, f"設定を読み込めませんでした: {error}"


def save_settings(path: Path, values: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f"settings.{os.getpid()}.tmp")
    try:
        temp.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def detect_adb(saved: str = "") -> str:
    # A missing explicitly selected path is retained so the user can correct it.
    if saved:
        return saved
    found = shutil.which("adb.exe" if os.name == "nt" else "adb")
    if found:
        return str(Path(found).resolve())
    folder = Path(sys.executable if getattr(sys, "frozen", False) else __file__).resolve().parent
    for candidate in (folder / "adb.exe", folder / "platform-tools" / "adb.exe"):
        if candidate.is_file():
            return str(candidate)
    return ""


@dataclass(frozen=True)
class Device:
    serial: str
    state: str
    model: str = ""
    product: str = ""


def parse_devices(output: str) -> list[Device]:
    devices = []
    for line in output.splitlines():
        line = line.strip()
        if not line or line.startswith(("List of devices", "*")):
            continue
        fields = line.split()
        if len(fields) < 2:
            continue
        state = "no permissions" if fields[1:3] == ["no", "permissions"] else fields[1]
        attrs = dict(part.split(":", 1) for part in fields[2:] if ":" in part)
        devices.append(Device(fields[0], state, attrs.get("model", ""), attrs.get("product", "")))
    return devices


class AdbError(RuntimeError):
    pass


def run_adb(adb: str, args: list[str], timeout: int = 30) -> str:
    if not adb or not Path(adb).is_file():
        raise AdbError("adb.exeが見つかりません。Select adb.exeから指定してください。")
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if os.name == "nt" else {}
    try:
        result = subprocess.run(
            [adb, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8", errors="replace",
            timeout=timeout, check=False, **options,
        )
    except subprocess.TimeoutExpired as error:
        detail = "\n端末側で処理が継続している可能性があります。結果を確認してから再実行してください。" if "install" in args else ""
        raise AdbError(f"ADBが{timeout}秒以内に応答しませんでした。{detail}") from error
    except OSError as error:
        raise AdbError(f"ADBを起動できません: {error}") from error
    output = "\n".join(part.strip() for part in (result.stdout, result.stderr) if part.strip())
    if result.returncode != 0:
        raise AdbError(output or f"ADB終了コード: {result.returncode}")
    return output


def read_devices(adb: str) -> tuple[str, list[Device], list[str]]:
    output = run_adb(adb, ["devices", "-l"])
    devices, warnings = [], []
    for device in parse_devices(output):
        if device.state == "device":
            try:
                model = run_adb(adb, ["-s", device.serial, "shell", "getprop", "ro.product.model"], timeout=5).strip()
                if model:
                    device = Device(device.serial, device.state, model, device.product)
            except AdbError as error:
                warnings.append(f"{device.serial}: 型番の詳細取得に失敗（一覧情報を使用）。{error}")
        devices.append(device)
    return output, devices, warnings


def install_apk(adb: str, serial: str, apk: str, on_stage=None) -> str:
    target = Path(apk)
    if not target.is_file() or target.suffix.lower() != ".apk":
        raise AdbError("有効なAPKファイルを選択してください。")
    if not serial:
        raise AdbError("インストール先の端末を選択してください。")
    if on_stage:
        on_stage("接続先の状態を確認中")
    # Always address the selected serial; never fall back to another device.
    if run_adb(adb, ["-s", serial, "get-state"]).strip() != "device":
        raise AdbError("選択した端末が使用可能な状態ではありません。Refreshで再確認してください。")
    if on_stage:
        on_stage("APKを転送・インストール中")
    output = run_adb(adb, ["-s", serial, "install", "-r", str(target.resolve())], timeout=300)
    if not any(line.strip() == "Success" for line in output.splitlines()):
        raise AdbError(f"インストール成功を確認できませんでした。\n{output}")
    return output


class InstallerApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("780x640")
        self.minsize(680, 580)
        self.config_file = settings_path()
        self.saved, warning = load_settings(self.config_file)
        self.adb = tk.StringVar(value=detect_adb(self.saved.get("adb_path", "")))
        self.apk = tk.StringVar(value=self.saved.get("apk_path", ""))
        self.version = tk.StringVar(value="未確認")
        self.status = tk.StringVar(value="起動中…")
        self.events = queue.Queue()
        self.busy = False
        self.started_at = 0.0
        self.stage = ""
        self.activity = tk.StringVar(value="待機中")
        self.devices: dict[str, Device] = {}
        self._build()
        self.protocol("WM_DELETE_WINDOW", self._close)
        self.after(80, self._poll)
        if warning:
            self._log(warning)
        if self.apk.get() and not Path(self.apk.get()).is_file():
            self._log("保存されたAPKが見つかりません。Select apkから再指定してください。")
        self.after(150, self.refresh)

    def _build(self):
        style = ttk.Style(self)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.rowconfigure(3, weight=1)

        adb_box = ttk.LabelFrame(body, text="ADB information", padding=12)
        adb_box.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        adb_box.columnconfigure(1, weight=1)
        ttk.Label(adb_box, text="PATH:").grid(row=0, column=0, padx=(0, 8))
        ttk.Entry(adb_box, textvariable=self.adb, state="readonly").grid(row=0, column=1, sticky="ew")
        ttk.Label(adb_box, textvariable=self.version).grid(row=1, column=0, columnspan=2, sticky="w", pady=6)
        buttons = ttk.Frame(adb_box)
        buttons.grid(row=2, column=0, columnspan=2, sticky="w")
        self.adb_button = ttk.Button(buttons, text="Select adb.exe", command=self.select_adb)
        self.adb_button.pack(side="left")
        self.auto_button = ttk.Button(buttons, text="Auto detect", command=self.auto_detect)
        self.auto_button.pack(side="left", padx=8)

        device_box = ttk.LabelFrame(body, text="ADB Device information", padding=12)
        device_box.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        device_box.columnconfigure(0, weight=1)
        table_box = ttk.Frame(device_box)
        table_box.grid(row=0, column=0, sticky="ew")
        table_box.columnconfigure(0, weight=1)
        self.table = ttk.Treeview(table_box, columns=("serial", "state", "model", "product"), show="headings", height=4, selectmode="browse")
        for key, title, width in (("serial", "Serial", 230), ("state", "State", 110), ("model", "型番 (Model)", 150), ("product", "Product", 140)):
            self.table.heading(key, text=title)
            self.table.column(key, width=width, minwidth=70)
        self.table.grid(row=0, column=0, sticky="ew")
        bar = ttk.Scrollbar(table_box, orient="vertical", command=self.table.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.table.configure(yscrollcommand=bar.set)
        self.table.bind("<<TreeviewSelect>>", lambda event: self._update_install())
        self.refresh_button = ttk.Button(device_box, text="Refresh", command=self.refresh)
        self.refresh_button.grid(row=1, column=0, sticky="e", pady=(8, 0))
        ttk.Label(device_box, text="インストール先を選択してください（State = device の端末）。").grid(row=2, column=0, sticky="w", pady=(4, 0))

        apk_box = ttk.LabelFrame(body, text="APK", padding=12)
        apk_box.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        apk_box.columnconfigure(0, weight=1)
        ttk.Entry(apk_box, textvariable=self.apk, state="readonly").grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.apk_button = ttk.Button(apk_box, text="Select apk", command=self.select_apk)
        self.apk_button.grid(row=0, column=1)
        self.install_button = ttk.Button(apk_box, text="Install", command=self.install, state="disabled")
        self.install_button.grid(row=1, column=1, pady=(10, 0))
        ttk.Label(apk_box, text="既存アプリはデータを保持して更新します（adb install -r）。").grid(row=1, column=0, sticky="w", pady=(10, 0))

        self.log = ScrolledText(body, height=6, wrap="word", state="disabled", font=("TkFixedFont", 9))
        self.log.grid(row=3, column=0, sticky="nsew")
        ttk.Label(body, textvariable=self.activity).grid(
            row=4, column=0, sticky="w", pady=(10, 6))
        ttk.Label(body, textvariable=self.status, wraplength=700).grid(row=5, column=0, sticky="w")

    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text.rstrip() + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _save(self):
        try:
            save_settings(self.config_file, {"adb_path": self.adb.get(), "apk_path": self.apk.get()})
        except OSError as error:
            self._log(f"設定保存に失敗: {error}")
            messagebox.showwarning(APP_NAME, f"選択したパスを保存できませんでした。\n{error}", parent=self)

    def select_adb(self):
        path = filedialog.askopenfilename(parent=self, title="adb.exeを選択", filetypes=[("ADB executable", "adb.exe"), ("All files", "*.*")])
        if path:
            self.adb.set(path)
            self._save()
            self.refresh()

    def auto_detect(self):
        self.adb.set(detect_adb())
        self._save()
        self.refresh()

    def select_apk(self):
        options = {}
        old = Path(self.apk.get()) if self.apk.get() else None
        if old and old.parent.is_dir():
            options["initialdir"] = str(old.parent)
        path = filedialog.askopenfilename(parent=self, title="APKファイルを選択", filetypes=[("Android package", "*.apk")], **options)
        if path:
            self.apk.set(path)
            self._save()
            self._update_install()

    def _selected(self) -> Device | None:
        selection = self.table.selection()
        return self.devices.get(selection[0]) if selection else None

    def _update_install(self):
        device = self._selected()
        enabled = (not self.busy and device is not None and device.state == "device"
                   and bool(self.adb.get()) and Path(self.adb.get()).is_file()
                   and bool(self.apk.get()) and Path(self.apk.get()).is_file()
                   and Path(self.apk.get()).suffix.lower() == ".apk")
        self.install_button.configure(state="normal" if enabled else "disabled")

    def _busy(self, value: bool):
        self.busy = value
        for button in (self.adb_button, self.auto_button, self.apk_button, self.refresh_button):
            button.configure(state="disabled" if value else "normal")
        if value:
            self.started_at = time.monotonic()
            self._update_activity()
            self.table.state(["disabled"])
        else:
            self.table.state(["!disabled"])
        self._update_install()

    def _update_activity(self):
        if not self.busy:
            return
        elapsed = time.monotonic() - self.started_at
        dots = ("●○○", "○●○", "○○●", "○●○")[int(elapsed * 3) % 4]
        seconds = int(elapsed)
        self.activity.set(f"{dots}  {self.stage}  |  経過 {seconds // 60:02d}:{seconds % 60:02d}")

    def _start(self, kind: str, work):
        self.stage = "ADB・端末情報を取得中" if kind == "refresh" else "インストールを準備中"
        self._busy(True)
        def worker():
            try:
                self.events.put((kind, work(), None))
            except Exception as error:
                self.events.put((kind, None, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def refresh(self):
        if self.busy:
            return
        selected = self._selected()
        old_serial = selected.serial if selected else ""
        self.table.delete(*self.table.get_children())
        self.devices.clear()
        self.version.set("未確認")
        self._update_install()
        adb = self.adb.get()
        if not adb:
            self.status.set("ADB未検出：Select adb.exeから指定してください。")
            self.activity.set("待機中（ADB未指定）")
            return
        self.status.set("ADBと接続端末を確認しています…")
        def work():
            version = run_adb(adb, ["version"])
            output, devices, warnings = read_devices(adb)
            return version, output, devices, old_serial, warnings
        self._start("refresh", work)

    def install(self):
        if self.busy:
            return
        device = self._selected()
        if not device or device.state != "device":
            return
        adb, apk, serial = self.adb.get(), self.apk.get(), device.serial
        self._save()
        self.status.set(f"インストール中：{serial}")
        self._log(f"\nインストール先: {serial}\nAPK: {apk}")
        self._start("install", lambda: install_apk(
            adb, serial, apk,
            on_stage=lambda stage: self.events.put(("stage", stage, None)),
        ))

    def _poll(self):
        try:
            while True:
                kind, payload, error = self.events.get_nowait()
                if kind == "stage":
                    self.stage = payload
                    continue
                elapsed = time.monotonic() - self.started_at
                self._busy(False)
                result_label = "失敗" if error else ("確認完了" if kind == "refresh" else "インストール完了")
                self.activity.set(f"{result_label}  |  処理時間 {elapsed:.1f} 秒")
                if error:
                    self.status.set("処理に失敗しました。ログを確認してください。")
                    self._log(error)
                    if kind == "install":
                        messagebox.showerror(APP_NAME, error, parent=self)
                elif kind == "refresh":
                    version, output, devices, old_serial, warnings = payload
                    self.version.set(version.splitlines()[0] if version else "バージョン不明")
                    self._log(version + "\n" + output)
                    for warning in warnings:
                        self._log(warning)
                    for index, device in enumerate(devices):
                        iid = str(index)
                        self.devices[iid] = device
                        self.table.insert("", "end", iid=iid, values=(device.serial, device.state, device.model, device.product))
                    candidates = [iid for iid, device in self.devices.items() if device.state == "device"]
                    previous = next((iid for iid in candidates if self.devices[iid].serial == old_serial), None)
                    if previous is not None:
                        self.table.selection_set(previous)
                    elif len(candidates) == 1:
                        self.table.selection_set(candidates[0])
                    if not devices:
                        self.status.set("端末が見つかりません。USB接続・USBデバッグを確認し、Refreshを押してください。")
                    elif not candidates:
                        self.status.set("接続可能な端末がありません。unauthorized：端末でUSBデバッグを許可／offline：再接続後Refresh。")
                    else:
                        self.status.set(f"検出 {len(devices)} 台 / 使用可能 {len(candidates)} 台。端末とAPKを選択してInstall。")
                    self._update_install()
                else:
                    self._log(payload)
                    self.status.set("インストールが完了しました。")
                    messagebox.showinfo(APP_NAME, "インストールが完了しました。", parent=self)
        except queue.Empty:
            pass
        self._update_activity()
        self.after(80, self._poll)

    def _close(self):
        if self.busy:
            messagebox.showinfo(APP_NAME, "処理が完了してから終了してください。", parent=self)
            return
        self.destroy()


def main():
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            pass
    InstallerApp().mainloop()


if __name__ == "__main__":
    main()
