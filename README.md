# launcher_icons

**Launcher-style PNG Icon Processor + Full Icon Pack + CLI APK Builder**

Creates beautiful Pixel Launcher-style icons (icon + label below) from plain PNGs. Can generate a complete, Gradle-based Android icon pack project and build a real `.apk` from the command line — no Android Studio or GUI required.

**Version:** 1.3.0

## Features

- Pixel Launcher style: icon + white label with shadow below
- Auto darkens icons for better readability
- Auto-prompts for Pillow install (fully automatic inside Termux)
- `--build-apk -y` : the default one-shot mode. Aggressively auto-installs **everything** (Pillow + Java + Gradle + full Android SDK) with no prompts.
- `-y` / `--yes` / `--auto` flag forces full non-interactive auto-install for any command.
- Generates **full Gradle Android project** (not just resources)
- `--build-apk` flag: builds a real release APK using Gradle from CLI
- Includes a `build.sh` helper script inside generated packs
- Dry-run support
- Works on Termux, Linux, macOS, Windows (Python + Pillow)

## Requirements

- Python 3
- Pillow

The script will offer to install Pillow for you.

When you use `--build-apk`, the script is **aggressive** about making it "just work":
- On Termux: fully automatic install of Pillow + openjdk-17 + gradle + unzip + wget + Android cmdline-tools + platform + build-tools (no questions, big downloads happen).
- On desktop: prompts with defaults leaning toward yes for the SDK.

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

### Just style the icons

```bash
./launcher_icons.py /path/to/raw/icons
```

Creates `processed_icons/` next to your sources.

### Create styled icons + full icon pack project

```bash
./launcher_icons.py /path/to/icons \
    --create-icon-pack \
    --icon-pack-name "MyOneUI" \
    --package-name "com.yourname.myoneui"
```

### One-shot (recommended — default "just works" behavior)

```bash
./launcher_icons.py /path/to/icons \
    --create-icon-pack \
    --build-apk \
    -y \
    --icon-pack-name "MyOneUI" \
    --package-name "com.yourname.myoneui"
```

- `-y` / `--yes` / `--auto` = full one-shot, zero prompts. Installs **everything** automatically.
- `--build-apk -y` is now the recommended default for making a real APK from the command line.

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

To use `--build-apk` or `./build.sh` you need:

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
