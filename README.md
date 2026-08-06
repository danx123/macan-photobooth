# 📸 Macan PhotoBooth

A desktop photobooth application built with **PySide6**, part of the **Macan Angkasa** suite. Macan PhotoBooth turns any Windows PC with a webcam or capture device into a fully self-contained event photobooth — from live camera preview and countdown-driven capture, to frame composition and 4R (4×6") print-ready sheets.

> **Note:** The source code shared in this repository is a **reference / base project**. It's meant as a working starting point to build on and adapt — not a final, locked-down release — so expect ongoing changes, refactors, and feature additions on top of it.
---
<img width="1024" height="1536" alt="macan photobooth" src="https://github.com/user-attachments/assets/53f64d02-ec64-4cf5-83d8-0f94ab4dbf02" />
---

## Screenshot

<img width="1024" height="1497" alt="github_macan photobooth v2 1 0" src="https://github.com/user-attachments/assets/34ba82e3-7aed-4277-b3d7-bd87f315a807" />



## Overview

Macan PhotoBooth is designed for events (weddings, parties, corporate booths) where guests need a fast, guided photo session with minimal supervision:

1. Pick a frame template and camera source.
2. Preview the exact final composition — template grid plus overlay — before a single photo is taken.
3. Run an auto-timed or fully manual shooting session.
4. Automatically assemble the shots into a printable strip.
5. Pair two sessions' strips together onto a single 4×6" sheet, ready to export or send straight to the printer.

The interface uses a dockable panel layout (drag, resize, float, or hide any panel), a dark "charcoal" theme, and persists window layout and session preferences between launches.

---

## Features

- **Live camera preview** with a large on-screen countdown (auto-detects available camera indices).
- **Auto Shot with Timer** — a 3‑2‑1 countdown that automatically repeats ("Ready" → 3‑2‑1) until the target shot count is reached.
- **Manual Shot**, triggerable by mouse click, keyboard (`Space` / `Enter`), or a wireless/Bluetooth camera shutter remote — no mouse required during a live session.
- **Frame templates** — Classic 3, Strip 4, Strip 5, and Strip 6 photo layouts, selectable before a session starts.
- **Frame overlays** — browse the full local filesystem (Drive Tree) to pick a decorative PNG border/frame; transparent overlays are auto-composited onto the finished strip.
- **Live composite preview** of the chosen template + overlay, and a raw checkerboard preview of the overlay file itself, so it's easy to confirm the right asset before shooting.
- **Compose dialog** for manually assigning shots to slots whenever more photos are taken than a template has slots for.
- **4R (4×6") sheet export** — two session strips are placed side by side on one printable sheet ("4R dibagi 2"); a placeholder is shown while waiting for the second session.
- **Direct printing** via the system print dialog (`QPrintDialog`), scaled to fit the page.
- **EXIF/session metadata panel** showing camera source, resolution, template, overlay, shot count, timestamps, session ID, and output path.
- **Filmstrip** of thumbnails for every shot taken in the current session.
- **Dockable, persistent layout** — every panel can be moved, resized, tabbed, or hidden via the View menu, with a one-click "Restore Default Layout" option. Window geometry and panel arrangement are saved with `QSettings` and restored on next launch.
- **About dialog** with application name, version, and credits.

---

## Requirements

- Python 3.10+
- [PySide6](https://pypi.org/project/PySide6/)
- [opencv-python](https://pypi.org/project/opencv-python/)
- A connected webcam or USB/virtual capture device
- Windows is the primary target platform (camera backend uses `CAP_DSHOW`), though the app runs cross-platform with `CAP_ANY` as a fallback.

Install dependencies:

```bash
pip install PySide6 opencv-python
```

---

## Project Structure

| File                     | Purpose                                                                 |
|--------------------------|--------------------------------------------------------------------------|
| `macan_photobooth.py`    | Application entry point — main window, docking layout, menus/toolbar, session logic, export/print. |
| `macan_pb_widgets.py`    | Reusable widgets: camera worker thread, live view, filmstrip, drive tree, EXIF panel, template selector, compose dialog, about dialog. |
| `macan_pb_templates.py`  | Frame template definitions and the 4R sheet/strip rendering/compositing logic. |
| `macan_pb_style.py`      | Centralized "Charcoal" QSS theme (colors, panels, buttons, menus, toolbar, tabs). |

---

## Running the App

```bash
python macan_photobooth.py
```

On first launch, the app creates a `PhotoBooth_Output` folder next to the executable/script for exported sheets, and probes available camera indices automatically.

---

## Basic Workflow

1. **Choose a frame template** (3–6 photo grid) and, optionally, a **frame overlay** from the Drive Tree panel — single-click to preview, double-click to apply.
2. **Select a camera source** and shot count (4–6 takes), then click **Refresh** if a newly connected camera doesn't appear.
3. Click **Start Session**, then use **Auto Shot with Timer** or **Manual Shot** to capture photos.
4. Once the target shot count is reached, click **End & Compose** to assemble the strip (you'll be prompted to assign shots to slots if the counts don't match exactly).
5. Repeat for a second session to fill the other half of the 4R sheet, or export with just one session.
6. Click **Export / Print** to save the sheet as a PNG and optionally send it to a printer.

---

## Manual Shot — Remote Shutter Support

Manual Shot can be triggered without touching the mouse, which is useful for a physically mounted photobooth. The following inputs all fire a manual shot when a session is active:

- `Space`
- `Enter` / `Return`
- `Volume Up` / `Volume Down`
- `Page Up` / `Page Down`
- Media Play / Play-Pause key

These cover the key codes emulated by most inexpensive Bluetooth/USB camera shutter remotes, so a remote can be paired and used immediately without extra configuration.

---

## Settings & Persistence

The following are persisted via `QSettings` (organization `MacanAngkasa`, application `MacanPhotoBooth`) and restored automatically on the next launch:

- Window geometry and dock/panel layout
- Selected frame template
- Selected shot count
- Selected camera index
- Selected frame overlay path
- Output folder location

Use **View → Restore Default Layout** at any time to reset the panel arrangement without affecting the other saved preferences.

---

## Output

Exported sheets are saved as PNG files at 300 DPI (4×6" → 1200×1800 px) inside the configured output folder, named after the session ID(s) that make up the sheet (e.g. `session1_session2_4R.png`).

---

## License

Internal tool — part of the Macan Angkasa application suite.
