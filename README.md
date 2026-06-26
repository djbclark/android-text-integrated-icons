# launcher_icons

**Launcher-style PNG Icon Processor + Full Icon Pack + CLI APK Builder**

Creates beautiful Pixel Launcher-style icons (icon + label below) from plain PNGs. Can generate a complete, Gradle-based Android icon pack project and build a real `.apk` from the command line — no Android Studio or GUI required.

**Version:** 1.4.0

## Features

- Pixel Launcher style: icon + white label with shadow below
- Auto darkens icons for better readability
- Auto-prompts for Pillow install (fully automatic inside Termux)
- **Icon pack + APK build are on by default** — just point the script at your icons folder
- Java + Gradle auto-installed via **pkg** (Termux) or **apt** (Debian/Ubuntu) when missing
- `-y` / `--yes` / `--auto` also auto-installs the full Android SDK with no prompts
- `--no-icon-pack` / `--no-apk` to skip those steps
- Generates **full Gradle Android project** (not just resources)
- Includes a `build.sh` helper script inside generated packs
- Dry-run support
- Works on Termux, Linux, macOS, Windows (Python + Pillow)

## Requirements

- Python 3
- Pillow

The script will offer to install Pillow for you.

APK builds are on by default. The script auto-installs Java + Gradle via **pkg** (Termux) or **apt** (Debian/Ubuntu) when missing.
- On Termux: also sets up the Android SDK automatically after installing build tools.
- Add `-y` on other platforms for zero-prompt Android SDK setup (large download).

The generated pack also gets an aggressive `build.sh`.

See [requirements.txt](requirements.txt).

## Installation

```bash
# 1. Get the code
git clone https://github.com/djbclark/android-text-integrated-icons.git
cd android-text-integrated-icons

# 2. Make executable
chmod +x launcher_icons.py

# 3. (Optional) Install to PATH
mkdir -p ~/.local/bin
cp launcher_icons.py ~/.local/bin/launcher_icons
chmod +x ~/.local/bin/launcher_icons
export PATH="$HOME/.local/bin:$PATH"
```

## Basic Usage

### Default (recommended — icon pack + APK)

```bash
./launcher_icons.py /path/to/icons \
    --icon-pack-name "MyOneUI" \
    --package-name "com.yourname.myoneui"
```

This styles icons, creates the Gradle project, and builds the APK. Java/Gradle install via pkg/apt automatically if missing.

Add `-y` for zero-prompt Android SDK setup:

```bash
./launcher_icons.py /path/to/icons -y \
    --icon-pack-name "MyOneUI" \
    --package-name "com.yourname.myoneui"
```

### Just style the icons (no pack, no APK)

```bash
./launcher_icons.py /path/to/raw/icons --no-icon-pack
```

Creates `processed_icons/` next to your sources.

### Icon pack only (skip APK build)

```bash
./launcher_icons.py /path/to/icons --no-apk \
    --icon-pack-name "MyOneUI" \
    --package-name "com.yourname.myoneui"
```

Inside the generated folder you will also find `build.sh` you can run directly:

```bash
cd MyOneUI
./build.sh
```

The APK will appear next to the project folder.

### Other useful flags

```bash
--dry-run                    # Preview only
--max-label-chars 12         # Control label length
--output-dir my_styled       # Custom output folder name (or absolute path)
```

## How Styled Icons Look

- Icons are slightly colorized toward black
- A label area is appended below (using the filename)
- White text + dark outline for readability (mimics stock Pixel launcher)

## Generated Icon Pack Projects

The generated project is a **real Android app project** with:

- Proper Gradle + `app/build.gradle`
- `settings.gradle`, `gradle.properties`
- `app/src/main/res/drawable/` + `xml/appfilter.xml`
- Minimal `MainActivity`
- App launcher icon (auto-generated)
- `build.sh` helper for pure CLI builds

After generation:

1. Edit `app/src/main/res/xml/appfilter.xml` and fill in real `ComponentInfo{package/activity}` entries.
2. Run `./build.sh` or `./gradlew assembleRelease`

## CLI APK Building Requirements

To build APKs (on by default) or run `./build.sh` you need:

- Java + Gradle
- Android SDK (compileSdk, build tools)

**On Termux** this is possible but advanced:
```bash
pkg install openjdk-17 gradle
# Full Android SDK setup is non-trivial
```

If the build tools are not present, the script will still generate the complete project and give you clear next steps.

## Tips

- Rename your source PNGs nicely before running (filenames become labels + drawable names)
- High-res square icons (512px+) work best
- After building, install the APK and choose it as icon pack in your launcher

## File Structure of This Repo

```
android-text-integrated-icons/
├── launcher_icons.py
├── README.md
├── LICENSE
├── requirements.txt
├── install.sh
└── .gitignore
```

## License

MIT — see [LICENSE](LICENSE).

---

Made for people who want nice launcher icons + real APKs without being forced into Android Studio.
