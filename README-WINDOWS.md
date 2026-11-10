# FolderExporter 1.10.0 for Windows 10 x64

Original Tkinter interface and PSD/CSP export logic. No redesign or feature removal. Source files are the existing Mac application files, with Windows-specific packaging added.

The GitHub Actions workflow creates `FolderExporter.exe` with PyInstaller from Python 3.11. The executable does not require Python to be separately installed. Project files are read-only; image and Studio Link exports are handled as before.

Use `build_windows.ps1` locally on Windows (Python 3.11 required to build, not to run), or run the Windows GitHub workflow. No commercial services or external APIs are required. The CLIP format remains experimental, as in the original.
