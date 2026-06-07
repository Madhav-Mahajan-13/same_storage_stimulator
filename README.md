# Same Storage Stimulator

A personal Windows 10/11 utility for moving selected large repack archive/source files to removable storage while preserving access from the original folder through file symbolic links.

## For Normal Users

You do not need to know coding to use this app.

### Option 1: Download With Git

If you do not have Git installed, install **Git for Windows** first:

```text
https://git-scm.com/download/win
```

Then open **PowerShell** and run these commands one by one:

```powershell
cd "$env:USERPROFILE\Downloads"
git clone https://github.com/Madhav-Mahajan-13/same_storage_stimulator.git
cd .\same_storage_stimulator
.\dist\SameStorageStimulator.exe
```

### Option 2: Download ZIP

1. Open this link in your browser:

```text
https://github.com/Madhav-Mahajan-13/same_storage_stimulator
```

2. Click **Code**.
3. Click **Download ZIP**.
4. Extract the ZIP file.
5. Open the extracted folder.
6. Open the `dist` folder.
7. Double-click `SameStorageStimulator.exe`.

## How To Use The App

1. Select your repack folder.
2. Select the big archive/source files you want to move.
3. Select your USB drive or memory card.
4. Click the move/link/verify button.
5. Keep the USB drive or memory card connected.
6. Run `setup.exe` manually from the original repack folder.

## If Windows Blocks It

Windows SmartScreen may warn you because this app is not code-signed.

If you trust this repo and want to run it:

1. Click **More info**.
2. Click **Run anyway**.

The app may also ask to relaunch as administrator. This is normal when Windows blocks symbolic link creation.

## For Developers / Run From Source

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
