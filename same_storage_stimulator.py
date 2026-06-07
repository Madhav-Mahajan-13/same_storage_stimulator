import ctypes
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from tkinter import (
    BOTH,
    BOTTOM,
    END,
    LEFT,
    RIGHT,
    TOP,
    Button,
    Checkbutton,
    DoubleVar,
    Frame,
    IntVar,
    Label,
    Listbox,
    Message,
    StringVar,
    Tk,
    filedialog,
    messagebox,
    ttk,
)


APP_NAME = "Same Storage Stimulator"
APP_FOLDER = "SameStorageStimulator"
ALLOWED_EXTENSIONS = {".bin", ".arc", ".dat", ".pak", ".rar", ".zip", ".7z", ".cab"}
BLOCKED_EXTENSIONS = {".exe", ".msi", ".bat", ".cmd", ".ps1", ".com", ".scr"}
DEFAULT_MIN_SIZE_MB = 512
COPY_CHUNK_SIZE = 16 * 1024 * 1024
FAT32_MAX_FILE_SIZE = (4 * 1024 * 1024 * 1024) - 1

DRIVE_REMOVABLE = 2


class SymlinkPermissionError(ValueError):
    pass


@dataclass
class CandidateFile:
    path: Path
    size: int

    @property
    def name(self):
        return self.path.name


@dataclass
class DriveInfo:
    root: str
    label: str
    filesystem: str
    free_bytes: int
    total_bytes: int

    @property
    def display(self):
        label = f" {self.label}" if self.label else ""
        return f"{self.root}{label} - {format_bytes(self.free_bytes)} free - {self.filesystem}"


def format_bytes(value):
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def get_drive_type(root):
    return ctypes.windll.kernel32.GetDriveTypeW(ctypes.c_wchar_p(root))


def get_volume_info(root):
    volume_name = ctypes.create_unicode_buffer(261)
    filesystem = ctypes.create_unicode_buffer(261)
    serial = ctypes.c_ulong()
    max_component = ctypes.c_ulong()
    flags = ctypes.c_ulong()
    ok = ctypes.windll.kernel32.GetVolumeInformationW(
        ctypes.c_wchar_p(root),
        volume_name,
        len(volume_name),
        ctypes.byref(serial),
        ctypes.byref(max_component),
        ctypes.byref(flags),
        filesystem,
        len(filesystem),
    )
    if not ok:
        return "", ""
    return volume_name.value, filesystem.value


def get_free_space(root):
    free_available = ctypes.c_ulonglong()
    total = ctypes.c_ulonglong()
    total_free = ctypes.c_ulonglong()
    ok = ctypes.windll.kernel32.GetDiskFreeSpaceExW(
        ctypes.c_wchar_p(root),
        ctypes.byref(free_available),
        ctypes.byref(total),
        ctypes.byref(total_free),
    )
    if not ok:
        raise OSError(f"Could not read free space for {root}")
    return free_available.value, total.value


def list_removable_drives():
    drives = []
    mask = ctypes.windll.kernel32.GetLogicalDrives()
    for index in range(26):
        if not mask & (1 << index):
            continue
        root = f"{chr(65 + index)}:\\"
        if get_drive_type(root) != DRIVE_REMOVABLE:
            continue
        try:
            free_bytes, total_bytes = get_free_space(root)
            label, filesystem = get_volume_info(root)
        except OSError:
            continue
        drives.append(
            DriveInfo(
                root=root,
                label=label,
                filesystem=filesystem or "Unknown",
                free_bytes=free_bytes,
                total_bytes=total_bytes,
            )
        )
    return drives


def scan_candidates(folder, min_size_mb):
    min_size = int(min_size_mb * 1024 * 1024)
    candidates = []
    for item in Path(folder).iterdir():
        if not item.is_file():
            continue
        suffix = item.suffix.lower()
        if suffix in BLOCKED_EXTENSIONS:
            continue
        if suffix not in ALLOWED_EXTENSIONS:
            continue
        try:
            size = item.stat().st_size
        except OSError:
            continue
        if size >= min_size:
            candidates.append(CandidateFile(item, size))
    return sorted(candidates, key=lambda candidate: candidate.size, reverse=True)


class SameStorageApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("920x660")
        self.root.minsize(840, 580)

        self.folder = StringVar(value="")
        self.min_size_mb = DoubleVar(value=DEFAULT_MIN_SIZE_MB)
        self.status = StringVar(value="Select a repack folder to begin.")
        self.drive_status = StringVar(value="No removable drive selected.")
        self.progress_text = StringVar(value="")
        self.progress_value = DoubleVar(value=0)
        self.selected_drive_index = IntVar(value=-1)

        self.candidates = []
        self.selected_vars = []
        self.drives = []
        self.busy = False

        self.build_ui()
        self.refresh_drives()

    def build_ui(self):
        outer = Frame(self.root, padx=16, pady=14)
        outer.pack(fill=BOTH, expand=True)

        title = Label(outer, text=APP_NAME, font=("Segoe UI", 18, "bold"), anchor="w")
        title.pack(fill="x")

        note = Message(
            outer,
            text=(
                "Move selected top-level archive/source files to removable storage, "
                "then create file symbolic links so setup can still read them from the original folder."
            ),
            width=860,
            font=("Segoe UI", 9),
        )
        note.pack(fill="x", pady=(4, 12))

        folder_row = Frame(outer)
        folder_row.pack(fill="x", pady=(0, 8))
        Button(folder_row, text="Select Repack Folder", command=self.choose_folder).pack(side=LEFT)
        Label(folder_row, textvariable=self.folder, anchor="w").pack(side=LEFT, padx=10, fill="x", expand=True)

        filter_row = Frame(outer)
        filter_row.pack(fill="x", pady=(0, 10))
        Label(filter_row, text="Minimum file size (MB):").pack(side=LEFT)
        ttk.Spinbox(
            filter_row,
            from_=1,
            to=1048576,
            increment=128,
            textvariable=self.min_size_mb,
            width=10,
            command=self.rescan_if_ready,
        ).pack(side=LEFT, padx=(6, 10))
        Button(filter_row, text="Scan", command=self.scan_folder).pack(side=LEFT)
        Label(filter_row, textvariable=self.status, anchor="w").pack(side=LEFT, padx=12, fill="x", expand=True)

        main = Frame(outer)
        main.pack(fill=BOTH, expand=True)

        files_frame = ttk.LabelFrame(main, text="Eligible files")
        files_frame.pack(side=LEFT, fill=BOTH, expand=True, padx=(0, 10))
        self.files_canvas = Frame(files_frame)
        self.files_canvas.pack(fill=BOTH, expand=True, padx=8, pady=8)

        drive_frame = ttk.LabelFrame(main, text="Removable drive")
        drive_frame.pack(side=RIGHT, fill=BOTH, expand=False)
        self.drive_list = Listbox(drive_frame, width=42, height=10)
        self.drive_list.pack(fill=BOTH, expand=False, padx=8, pady=(8, 4))
        self.drive_list.bind("<<ListboxSelect>>", self.on_drive_selected)
        Button(drive_frame, text="Refresh Drives", command=self.refresh_drives).pack(fill="x", padx=8, pady=4)
        Message(drive_frame, textvariable=self.drive_status, width=300, font=("Segoe UI", 9)).pack(
            fill="x", padx=8, pady=8
        )

        summary_frame = ttk.LabelFrame(outer, text="Preparation")
        summary_frame.pack(fill="x", pady=(12, 0))
        self.summary = Message(summary_frame, width=850, text="", font=("Segoe UI", 9))
        self.summary.pack(fill="x", padx=8, pady=(8, 4))
        self.progress = ttk.Progressbar(summary_frame, variable=self.progress_value, maximum=100)
        self.progress.pack(fill="x", padx=8, pady=(4, 4))
        Label(summary_frame, textvariable=self.progress_text, anchor="w").pack(fill="x", padx=8, pady=(0, 8))

        action_row = Frame(outer)
        action_row.pack(fill="x", side=BOTTOM, pady=(12, 0))
        Button(action_row, text="Select All", command=self.select_all).pack(side=LEFT)
        Button(action_row, text="Clear", command=self.clear_selection).pack(side=LEFT, padx=6)
        self.prepare_button = Button(action_row, text="Move, Link, and Verify", command=self.start_prepare)
        self.prepare_button.pack(side=RIGHT)

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Select repack folder")
        if not folder:
            return
        self.folder.set(folder)
        self.scan_folder()

    def rescan_if_ready(self):
        if self.folder.get():
            self.scan_folder()

    def scan_folder(self):
        if self.busy:
            return
        folder = self.folder.get()
        if not folder:
            messagebox.showinfo(APP_NAME, "Select a repack folder first.")
            return
        try:
            min_size = float(self.min_size_mb.get())
            self.candidates = scan_candidates(folder, min_size)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Scan failed:\n{exc}")
            return
        self.render_candidates()
        total = sum(candidate.size for candidate in self.candidates)
        self.status.set(f"Found {len(self.candidates)} eligible file(s), {format_bytes(total)} total.")
        self.update_summary()

    def render_candidates(self):
        for child in self.files_canvas.winfo_children():
            child.destroy()
        self.selected_vars = []
        if not self.candidates:
            Label(
                self.files_canvas,
                text="No eligible top-level archive/source files found.",
                anchor="w",
            ).pack(fill="x")
            return
        for candidate in self.candidates:
            var = IntVar(value=0)
            self.selected_vars.append(var)
            text = f"{candidate.name}    {format_bytes(candidate.size)}"
            Checkbutton(self.files_canvas, text=text, variable=var, command=self.update_summary, anchor="w").pack(
                fill="x"
            )

    def refresh_drives(self):
        self.drives = list_removable_drives()
        self.drive_list.delete(0, END)
        for drive in self.drives:
            self.drive_list.insert(END, drive.display)
        self.selected_drive_index.set(-1)
        if self.drives:
            self.drive_status.set("Select the removable drive that should hold the moved files.")
        else:
            self.drive_status.set("No removable drives detected.")
        self.update_summary()

    def on_drive_selected(self, _event=None):
        selection = self.drive_list.curselection()
        if not selection:
            self.selected_drive_index.set(-1)
            return
        self.selected_drive_index.set(selection[0])
        self.drive_status.set(self.drives[selection[0]].display)
        self.update_summary()

    def selected_files(self):
        selected = []
        for candidate, var in zip(self.candidates, self.selected_vars):
            if var.get():
                selected.append(candidate)
        return selected

    def selected_drive(self):
        index = self.selected_drive_index.get()
        if index < 0 or index >= len(self.drives):
            return None
        return self.drives[index]

    def select_all(self):
        for var in self.selected_vars:
            var.set(1)
        self.update_summary()

    def clear_selection(self):
        for var in self.selected_vars:
            var.set(0)
        self.update_summary()

    def update_summary(self):
        selected = self.selected_files()
        total = sum(candidate.size for candidate in selected)
        drive = self.selected_drive()
        lines = [f"Selected: {len(selected)} file(s), {format_bytes(total)}."]
        if drive:
            lines.append(f"Target: {drive.display}")
            lines.append(
                f"Destination folder: {drive.root}{APP_FOLDER}\\{Path(self.folder.get()).name if self.folder.get() else ''}"
            )
        else:
            lines.append("Target: no removable drive selected.")
        self.summary.configure(text="\n".join(lines))

    def set_busy(self, busy):
        self.busy = busy
        state = "disabled" if busy else "normal"
        self.prepare_button.configure(state=state)

    def validate_selection(self, selected, drive):
        if not selected:
            raise ValueError("Select at least one file to move.")
        if drive is None:
            raise ValueError("Select a removable drive.")
        if get_drive_type(drive.root) != DRIVE_REMOVABLE:
            raise ValueError(f"{drive.root} is no longer detected as removable.")
        free_bytes, _total = get_free_space(drive.root)
        required = sum(candidate.size for candidate in selected)
        if free_bytes <= required:
            raise ValueError(
                f"Not enough free space. Required {format_bytes(required)}, available {format_bytes(free_bytes)}."
            )
        filesystem = drive.filesystem.upper()
        if filesystem == "FAT32":
            too_large = [candidate.name for candidate in selected if candidate.size > FAT32_MAX_FILE_SIZE]
            if too_large:
                raise ValueError("FAT32 cannot hold files larger than 4 GB:\n" + "\n".join(too_large))
        target_base = Path(drive.root) / APP_FOLDER / Path(self.folder.get()).name
        target_base.mkdir(parents=True, exist_ok=True)
        test_file = target_base / ".write_test"
        try:
            test_file.write_text("ok", encoding="ascii")
            test_file.unlink()
        except OSError as exc:
            raise ValueError(f"Drive is not writable: {exc}") from exc
        self.validate_symlink_permission(Path(self.folder.get()), target_base)
        return target_base

    def validate_symlink_permission(self, original_folder, target_base):
        source_probe = original_folder / ".same_storage_symlink_probe"
        link_probe = original_folder / ".same_storage_symlink_probe_link"
        target_probe = target_base / ".same_storage_symlink_probe_target"
        try:
            if source_probe.exists() or link_probe.exists() or target_probe.exists():
                raise ValueError(
                    "A previous symlink permission probe file exists. Remove files beginning with "
                    ".same_storage_symlink_probe and try again."
                )
            target_probe.write_text("ok", encoding="ascii")
            os.symlink(target_probe, link_probe)
            if link_probe.read_text(encoding="ascii") != "ok":
                raise ValueError("Symlink permission probe could not be read.")
        except OSError as exc:
            raise SymlinkPermissionError(
                "Windows blocked file symbolic link creation.\n\n"
                "Enable Windows Developer Mode, or run this app from an administrator PowerShell window, "
                "then try again. No files were moved by this preflight check."
            ) from exc
        finally:
            for probe in (link_probe, source_probe, target_probe):
                try:
                    if probe.exists() or probe.is_symlink():
                        probe.unlink()
                except OSError:
                    pass

    def start_prepare(self):
        if self.busy:
            return
        selected = self.selected_files()
        drive = self.selected_drive()
        try:
            target_base = self.validate_selection(selected, drive)
        except SymlinkPermissionError as exc:
            self.ask_for_admin_permission(str(exc))
            return
        except Exception as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        warning = (
            "The selected files will be moved to the removable drive and replaced by file symbolic links.\n\n"
            "Keep the removable drive connected until installation finishes.\n\n"
            "Continue?"
        )
        if not messagebox.askyesno(APP_NAME, warning):
            return
        self.set_busy(True)
        thread = threading.Thread(target=self.prepare_worker, args=(selected, target_base), daemon=True)
        thread.start()

    def ask_for_admin_permission(self, message):
        should_relaunch = messagebox.askyesno(
            APP_NAME,
            f"{message}\n\nDo you want to relaunch {APP_NAME} as administrator now?",
        )
        if not should_relaunch:
            return
        try:
            self.relaunch_as_admin()
            self.root.destroy()
        except Exception as exc:
            messagebox.showerror(
                APP_NAME,
                "Could not request administrator permission automatically.\n\n"
                f"{exc}\n\n"
                "Open PowerShell as administrator and run:\n"
                "py .\\same_storage_stimulator.py",
            )

    def relaunch_as_admin(self):
        script = Path(__file__).resolve()
        if Path(sys.executable).name.lower() == "py.exe":
            executable = sys.executable
            parameters = f'"{script}"'
        else:
            executable = sys.executable
            parameters = f'"{script}"'
        result = ctypes.windll.shell32.ShellExecuteW(
            None,
            "runas",
            executable,
            parameters,
            str(script.parent),
            1,
        )
        if result <= 32:
            raise OSError(f"ShellExecuteW failed with code {result}.")

    def prepare_worker(self, selected, target_base):
        succeeded = []
        moved = []
        failed = None
        total_bytes = sum(candidate.size for candidate in selected)
        done_bytes = 0
        try:
            for candidate in selected:
                destination = self.unique_destination(target_base / candidate.name)
                self.post_progress(done_bytes, total_bytes, f"Moving {candidate.name}...")
                self.move_with_progress(candidate.path, destination, candidate.size, done_bytes, total_bytes)
                moved.append((candidate.name, str(destination)))
                done_bytes += candidate.size

                self.post_progress(done_bytes, total_bytes, f"Creating link for {candidate.name}...")
                os.symlink(destination, candidate.path)

                self.post_progress(done_bytes, total_bytes, f"Verifying {candidate.name}...")
                self.verify_link(candidate.path, destination, candidate.size)
                succeeded.append((candidate.name, str(destination)))
            self.post_done(succeeded, moved, None)
        except Exception as exc:
            failed = str(exc)
            self.post_done(succeeded, moved, failed)

    def move_with_progress(self, source, destination, size, done_before, total_bytes):
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_destination = destination.with_name(destination.name + ".moving")
        if temp_destination.exists():
            raise FileExistsError(f"Temporary destination already exists: {temp_destination}")
        copied = 0
        with source.open("rb") as reader, temp_destination.open("wb") as writer:
            while True:
                chunk = reader.read(COPY_CHUNK_SIZE)
                if not chunk:
                    break
                writer.write(chunk)
                copied += len(chunk)
                self.post_progress(done_before + copied, total_bytes, f"Moving {source.name}...")
        if copied != size:
            raise OSError(f"Move verification failed for {source.name}: copied size mismatch.")
        temp_destination.replace(destination)
        source.unlink()

    def verify_link(self, apparent_path, destination, expected_size):
        if not apparent_path.exists():
            raise FileNotFoundError(f"Link does not exist at original path: {apparent_path}")
        if not destination.exists():
            raise FileNotFoundError(f"Moved file does not exist: {destination}")
        apparent_size = apparent_path.stat().st_size
        destination_size = destination.stat().st_size
        if apparent_size != expected_size or destination_size != expected_size:
            raise OSError(f"Size mismatch for {apparent_path.name}")
        with apparent_path.open("rb") as handle:
            handle.read(1)

    def unique_destination(self, destination):
        if not destination.exists():
            return destination
        stem = destination.stem
        suffix = destination.suffix
        parent = destination.parent
        for index in range(1, 1000):
            candidate = parent / f"{stem}_{index}{suffix}"
            if not candidate.exists():
                return candidate
        raise FileExistsError(f"Could not create a unique destination for {destination.name}")

    def post_progress(self, done_bytes, total_bytes, text):
        percent = 0 if total_bytes == 0 else min(100, (done_bytes / total_bytes) * 100)
        self.root.after(0, lambda: self.apply_progress(percent, text))

    def apply_progress(self, percent, text):
        self.progress_value.set(percent)
        self.progress_text.set(text)

    def post_done(self, succeeded, moved, failed):
        self.root.after(0, lambda: self.apply_done(succeeded, moved, failed))

    def apply_done(self, succeeded, moved, failed):
        self.set_busy(False)
        if failed:
            verified = set(succeeded)
            moved_only = [entry for entry in moved if entry not in verified]
            success_details = "\n".join(f"- {name} -> {target}" for name, target in succeeded) or "None"
            moved_details = "\n".join(f"- {name} -> {target}" for name, target in moved_only) or "None"
            messagebox.showerror(
                APP_NAME,
                "Preparation stopped after a failure.\n\n"
                f"Moved, linked, and verified:\n{success_details}\n\n"
                f"Moved but not verified:\n{moved_details}\n\n"
                f"Failure:\n{failed}\n\n"
                "Handle cleanup manually before trying again.",
            )
            self.progress_text.set("Stopped after failure.")
            self.scan_folder()
            return
        details = "\n".join(f"- {name} -> {target}" for name, target in succeeded)
        messagebox.showinfo(
            APP_NAME,
            "Ready.\n\n"
            f"Moved and verified:\n{details}\n\n"
            "Run setup manually from the original folder. Keep the removable drive connected.",
        )
        self.progress_value.set(100)
        self.progress_text.set("Ready. Keep the removable drive connected during installation.")
        self.scan_folder()


def main():
    root = Tk()
    style = ttk.Style()
    if "vista" in style.theme_names():
        style.theme_use("vista")
    SameStorageApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
