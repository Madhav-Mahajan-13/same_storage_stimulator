# Same Storage Stimulator

A personal Windows 10/11 utility for moving selected large repack archive/source files to removable storage while preserving access from the original folder through file symbolic links.

## Run

Use the packaged app:

```powershell
.\dist\SameStorageStimulator.exe
```

Or run from source:

```powershell
py .\same_storage_stimulator.py
```

## MVP Behavior

- Scans only files directly inside the selected folder.
- Shows files at or above the selected minimum size.
- Allows only `.bin`, `.arc`, `.dat`, `.pak`, `.rar`, `.zip`, `.7z`, and `.cab`.
- Ignores installer/script executables.
- Targets removable drives only.
- Validates free space, FAT32 file-size limits, and writability.
- Moves selected files to `Drive:\SameStorageStimulator\{FolderName}\`.
- Creates file symbolic links at the original paths.
- Verifies each original apparent path exists, is readable, and has the expected size.

## Important Notes

Windows file symbolic links may require Developer Mode or administrator privileges. If the app cannot create symbolic links, it asks whether to relaunch as administrator.

The app runs a symbolic-link preflight check before moving files. If that check fails, no new files should be moved.

The app does not clean up or restore moved files in the MVP. Keep the removable drive connected until installation finishes.
