# Spooky Lite

### A lightweight companion for [NotScare.Me](https://notscare.me/)

Spooky Lite is a desktop app that helps my gf avoid getting caught off guard by jump scares.

Paste in a NotScare.Me movie URL, and Spooky Lite will load the movie's jump-scare timestamps, display them on an interactive timeline, and warn you before each scare with a visual countdown and cheerful audio cue.

---

## Features

- Load supported NotScare.Me movie pages
- Automatically extract jump-scare timestamps
- Distinguish between major and minor scares
- Display the movie poster
- Interactive movie timeline
- Start and pause the companion timer
- Jump backward 15 seconds
- Jump forward 15 seconds
- Click the timeline to seek
- Double-click scare entries to jump directly to them
- Adjustable warning lead time
- Full-window jump-scare countdown overlay
- Friendly audio alerts
- Dark interface designed to stay unobtrusive during movies
- Native dark Windows title bar

---

## Requirements

- Python 3.10+
- Windows recommended
- Internet connection for loading NotScare.Me data and movie posters

### Python Packages

```bash
pip install requests beautifulsoup4 pillow
```

Tkinter is normally included with standard Python installations on Windows.

---

## Installation

Clone the repository:

```bash
git clone https://github.com/YOUR-USERNAME/spooky-lite.git
cd spooky-lite
```

Install the dependencies:

```bash
pip install requests beautifulsoup4 pillow
```

Run Spooky Lite:

```bash
python spooky_lite_main.py
```

---

## Usage

### 1. Find Your Movie on NotScare.Me

For example:

```text
https://notscare.me/movies/jump-scares-in-weapons-2025
```

### 2. Paste the URL Into Spooky Lite

Click:

```text
Load movie
```

Spooky Lite will load:

- Movie title
- Poster
- Runtime
- Jump-scare timestamps
- Major/minor classifications
- Jump-scare descriptions

### 3. Start Your Movie

When your movie begins, press **Start** in Spooky Lite.

The companion timer will run alongside the movie.

### 4. Get Warned

When a jump scare is approaching, Spooky Lite displays a large countdown.

An audio chime also plays when the warning begins.

---

## Warning Lead Time

The warning interval is customizable.

By default:

```text
30 seconds
```

You can enter a different value in the **Warn me** field.

The jump-scare warning times in the table will update automatically.

---

## Controls

| Control | Action |
| --- | --- |
| **Start / Pause** | Start or pause the companion timer |
| **-15 sec** | Move backward 15 seconds |
| **+15 sec** | Move forward 15 seconds |
| **Restart** | Return to the beginning |
| **Timeline Click** | Seek to a specific time |
| **Double-click Scare** | Jump to that scare's timestamp |
| **Esc** | Dismiss the warning overlay |

---

## Current Limitation

Spooky Lite currently runs its own independent timer.

It does **not yet read the playback position of your actual media player**.

That means if you:

- Pause the movie
- Rewind
- Skip forward
- Seek to another scene

you should make the same adjustment in Spooky Lite.

The `-15 sec`, `+15 sec`, and interactive timeline controls make resynchronizing quick.

---

## Building a Windows Executable

Spooky Lite can be packaged using PyInstaller.

Install PyInstaller:

```bash
pip install pyinstaller
```

Build the application:

```bash
pyinstaller --onefile --windowed spooky_lite.py
```

The resulting executable will be placed in:

```text
dist/
```

Additional configuration may be useful for application icons and bundled resources.

---

## Contributing

Contributions, bug reports, and feature suggestions are welcome.

If you find an issue, open a GitHub Issue and include:

- Your operating system
- Python version
- The NotScare.Me URL you were using
- What you expected to happen
- What actually happened

Pull requests are also welcome.

---

## Disclaimer

Spooky Lite is an independent project and is **not affiliated with, endorsed by, or maintained by NotScare.Me**.

Jump-scare information is retrieved from NotScare.Me and depends on the availability and structure of their website.

Movie posters and related metadata may originate from third-party services referenced by NotScare.Me.

---

## Credits

Jump-scare data provided by:

**[NotScare.Me](https://notscare.me/)**

Spooky Lite is simply a companion interface built around that data.

---

## Spooky Lite

> **Enjoy Spooky Season *Lite*.**