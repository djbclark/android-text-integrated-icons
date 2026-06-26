#!/usr/bin/env python3
"""
Launcher-style PNG Icon Processor + Icon Pack + CLI APK Builder
Version 1.4.0

Features:
- Creates launcher-style images (icon + label below) mimicking Pixel Launcher
- Icon pack + APK build are ON by default (use --no-icon-pack / --no-apk to skip)
- Java + Gradle auto-installed via pkg (Termux) or apt (Debian/Ubuntu) when missing
- -y / --yes / --auto : also auto-install full Android SDK with zero prompts
- Includes build.sh helper inside generated packs
"""

import argparse
import os
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

__version__ = "1.4.1"

GRADLE_VERSION = "8.5"
GRADLE_WRAPPER_PROPERTIES = f"""distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-{GRADLE_VERSION}-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
"""
GRADLE_WRAPPER_JAR_URL = (
    f"https://raw.githubusercontent.com/gradle/gradle/v{GRADLE_VERSION}.0/"
    "gradle/wrapper/gradle-wrapper.jar"
)
GRADLEW_URL = f"https://raw.githubusercontent.com/gradle/gradle/v{GRADLE_VERSION}.0/gradlew"


def _apk_enabled_by_default() -> bool:
    """True unless the user explicitly opts out of icon pack / APK steps."""
    argv = sys.argv[1:]
    if any(flag in argv for flag in ("--dry-run", "--no-icon-pack", "--no-apk", "--version", "--help", "-h")):
        return False
    # No directory argument → likely --version / --help only
    if not any(a for a in argv if not a.startswith("-")):
        return False
    return True


# ==================== AUTO-INSTALL PILLOW ====================
def is_termux() -> bool:
    """Return True only when we are quite confident we are inside Termux."""
    env = os.environ
    prefix = env.get("PREFIX", "")
    # Strong, reliable signals from Termux
    if "com.termux" in prefix:
        return True
    if env.get("TERMUX_VERSION"):
        return True
    # termux-info is very Termux-specific
    if shutil.which("termux-info"):
        return True
    # pkg binary living under com.termux is a good extra clue
    pkg_path = shutil.which("pkg")
    if pkg_path and "/com.termux/" in pkg_path:
        return True
    return False


def ensure_pillow() -> None:
    try:
        import PIL  # noqa: F401
        return
    except ImportError:
        pass

    force_prompt = bool(os.environ.get("LAUNCHER_ICONS_FORCE_PROMPT"))

    if not force_prompt and is_termux():
        # Automatic install on Termux (original behavior)
        print("Pillow not found. Installing dependencies and Pillow...")
        print("This may take 1–4 minutes on the first run.\n")

        try:
            subprocess.run(["pkg", "update", "-y"], check=False)
            subprocess.run(
                ["pkg", "install", "-y",
                 "python", "python-pip", "clang", "make",
                 "ndk-sysroot", "libjpeg-turbo"],
                check=True
            )

            env = os.environ.copy()
            env["LDFLAGS"] = "-L/system/lib64"
            env["CFLAGS"] = "-I/data/data/com.termux/files/usr/include/"

            subprocess.run(
                [sys.executable, "-m", "pip", "install", "Pillow"],
                env=env,
                check=True
            )

            print("\nPillow installed successfully! Restarting script...\n")
            os.execv(sys.executable, [sys.executable] + sys.argv)

        except subprocess.CalledProcessError:
            print("\nAutomatic installation failed.", file=sys.stderr)
            print("Please run these commands manually:", file=sys.stderr)
            print("  pkg install -y python python-pip clang make ndk-sysroot libjpeg-turbo")
            print("  LDFLAGS='-L/system/lib64' CFLAGS='-I/data/data/com.termux/files/usr/include/' pip install Pillow")
            sys.exit(1)
        return

    # Prompt path (normal desktop systems, or forced)
    if not sys.stdin.isatty():
        # Non-interactive (scripts, CI, pipes) — don't hang on input()
        print("Error: Pillow is not installed.", file=sys.stderr)
        print("Please install it with: pip install Pillow", file=sys.stderr)
        print("(Use --break-system-packages or a venv if your OS blocks it.)", file=sys.stderr)
        sys.exit(1)

    if AUTO_INSTALL:
        print("AUTO_INSTALL mode: installing Pillow automatically (no prompt).")
        response = "y"
    else:
        print("Pillow is required but not installed.")
        print()
        try:
            response = input("Install Pillow now using pip? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(1)

    if response in ("", "y", "yes"):
        print("Installing Pillow...\n")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "Pillow"],
                check=True
            )
            print("\nPillow installed successfully!\n")
            # Re-verify the import works in this environment
            try:
                import PIL  # noqa: F401
            except ImportError:
                print("Pillow installation reported success, but the import still failed.", file=sys.stderr)
                print("You may need to restart your shell / use a virtualenv, or run:", file=sys.stderr)
                print("    pip install --break-system-packages Pillow", file=sys.stderr)
                sys.exit(1)
            return
        except subprocess.CalledProcessError:
            print("\nAutomatic pip install failed.", file=sys.stderr)
            print("Common fixes:", file=sys.stderr)
            print("  - Use a virtual environment: python -m venv venv && source venv/bin/activate", file=sys.stderr)
            print("  - Or force install: pip install --break-system-packages Pillow", file=sys.stderr)
            print("  - Then re-run this script.", file=sys.stderr)
            sys.exit(1)
        except Exception as exc:
            print(f"\nUnexpected error while installing: {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        print("\nPlease install it manually and re-run this script:")
        print("    pip install Pillow")
        print("\n(Or with --break-system-packages if your system blocks it.)")
        sys.exit(1)


def _make_executable(path: Path) -> None:
    """Ensure a file can be executed (zip extracts often drop the +x bit)."""
    try:
        mode = path.stat().st_mode
        path.chmod(mode | 0o111)
    except OSError:
        pass


def _java_available() -> bool:
    if shutil.which("java"):
        return True
    java_home = os.environ.get("JAVA_HOME")
    return bool(java_home and (Path(java_home) / "bin" / "java").exists())


def _set_java_home() -> None:
    for candidate in [
        "/data/data/com.termux/files/usr/lib/jvm/java-17-openjdk",
        "/data/data/com.termux/files/usr/lib/jvm/java-17-openjdk-arm64",
        "/data/data/com.termux/files/usr/lib/jvm/java-17",
        "/usr/lib/jvm/default-java",
        "/usr/lib/jvm/java-17-openjdk",
    ]:
        if os.path.exists(candidate):
            os.environ["JAVA_HOME"] = candidate
            os.environ["PATH"] = candidate + "/bin:" + os.environ.get("PATH", "")
            break


def _apt_cmd(*args: str) -> list[str]:
    """Build an apt-get command, using sudo only when not root."""
    base = ["apt-get", *args]
    if os.geteuid() != 0:
        return ["sudo", *base]
    return base


def _install_java_gradle_via_pkg_or_apt() -> bool:
    """Install Java + Gradle using pkg (Termux) or apt (Debian/Ubuntu). Returns True on success."""
    # pkg refuses to run as root; prefer apt when both are available.
    if is_termux() and os.geteuid() != 0:
        print("Termux detected — installing openjdk-17 + gradle via pkg...")
        subprocess.run(["pkg", "update", "-y"], check=False)
        subprocess.run(
            ["pkg", "install", "-y", "openjdk-17", "gradle", "unzip", "wget", "coreutils"],
            check=True,
        )
        return True

    if shutil.which("apt-get") or shutil.which("apt"):
        print("Installing default-jdk + gradle via apt...")
        subprocess.run(_apt_cmd("update", "-y"), check=False)
        subprocess.run(
            _apt_cmd("install", "-y", "default-jdk", "gradle", "unzip", "wget"),
            check=True,
        )
        return True

    return False


def ensure_build_tools() -> bool:
    """Ensure Java is available for APK builds. Installs via pkg/apt by default when missing."""
    if _java_available():
        return True

    print("\nJava is required for APK builds (enabled by default).")

    try:
        if _install_java_gradle_via_pkg_or_apt():
            _set_java_home()
            if _java_available():
                print("✅ Java installed via package manager.")
                if is_termux() or AUTO_INSTALL:
                    print("Setting up Android SDK...")
                    setup_minimal_android_sdk()
                return True
            print("Package manager reported success but java is still missing from PATH.")
    except subprocess.CalledProcessError as e:
        print(f"Package manager install failed: {e}")

    # Fallback for distros without pkg/apt
    if not sys.stdin.isatty() and not AUTO_INSTALL:
        print("Non-interactive session: could not install Java automatically.")
        print("Install Java (JDK 17+) manually, or re-run with -y.")
        return False

    print("Trying other package managers...")
    success = False
    try:
        if shutil.which("dnf"):
            subprocess.run(["sudo", "dnf", "install", "-y", "java-17-openjdk", "gradle"], check=True)
            success = True
        elif shutil.which("yum"):
            subprocess.run(["sudo", "yum", "install", "-y", "java-17-openjdk", "gradle"], check=True)
            success = True
        elif shutil.which("pacman"):
            subprocess.run(["sudo", "pacman", "-S", "--noconfirm", "jdk17-openjdk", "gradle"], check=True)
            success = True
        elif shutil.which("brew"):
            subprocess.run(["brew", "install", "openjdk@17", "gradle"], check=True)
            os.environ["JAVA_HOME"] = "/opt/homebrew/opt/openjdk@17/libexec/openjdk.jdk/Contents/Home"
            success = True
        else:
            success = download_gradle_manually()
    except subprocess.CalledProcessError as e:
        print(f"Install command failed: {e}")
    except Exception as e:
        print(f"Unexpected error during install: {e}")

    if success:
        _set_java_home()
        if _java_available():
            print("✅ Java installation attempted and verified.")
            if AUTO_INSTALL:
                setup_minimal_android_sdk()
            return True
        print("Install commands ran but java is still missing from PATH.")

    print("Could not auto-install Java. Please install JDK 17+ manually.")
    return False


def download_gradle_manually() -> bool:
    """Download and install Gradle to ~/.gradle or /usr/local if possible."""
    import urllib.request
    import zipfile
    import tempfile

    gradle_version = "8.5"
    url = f"https://services.gradle.org/distributions/gradle-{gradle_version}-bin.zip"
    target_dir = Path.home() / ".local" / "gradle"

    try:
        print(f"Downloading Gradle {gradle_version}...")
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "gradle.zip"
            urllib.request.urlretrieve(url, zip_path)
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(target_dir.parent)
        # The extracted folder is gradle-8.5
        gradle_bin = target_dir.parent / f"gradle-{gradle_version}" / "bin" / "gradle"
        if gradle_bin.exists():
            _make_executable(gradle_bin)
            # Symlink or add to PATH suggestion
            (Path.home() / ".local" / "bin").mkdir(parents=True, exist_ok=True)
            link = Path.home() / ".local" / "bin" / "gradle"
            if link.exists():
                link.unlink()
            link.symlink_to(gradle_bin)
            _make_executable(link)
            os.environ["PATH"] = str(link.parent) + os.pathsep + os.environ.get("PATH", "")
            print(f"Gradle installed to {gradle_bin}")
            return True
    except Exception as e:
        print(f"Manual Gradle download failed: {e}")
    return False


def setup_minimal_android_sdk() -> None:
    """Aggressively download and install a minimal but sufficient Android SDK for building icon pack APKs.

    This is called automatically on Termux and offered on other platforms.
    Tries hard to make ./gradlew assembleRelease "just work".
    """
    import urllib.request
    import zipfile
    import tempfile
    import shutil

    print("Aggressively setting up Android SDK for CLI builds...")

    # Use linux tools for Termux (which reports as linux)
    url = "https://dl.google.com/android/repository/commandlinetools-linux-11076708_latest.zip"
    if sys.platform == "darwin":
        url = "https://dl.google.com/android/repository/commandlinetools-mac-11076708_latest.zip"
    elif sys.platform.startswith("win"):
        url = "https://dl.google.com/android/repository/commandlinetools-win-11076708_latest.zip"

    # Prefer user-writable locations
    if is_termux():
        sdk_root = Path("/data/data/com.termux/files/usr") / "android-sdk"
    else:
        sdk_root = Path.home() / "Android" / "Sdk"

    cmdline_tools_dir = sdk_root / "cmdline-tools"
    latest_dir = cmdline_tools_dir / "latest"

    try:
        print(f"Downloading command line tools to {sdk_root} (large download, please wait)...")
        sdk_root.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmp:
            zip_path = Path(tmp) / "cmdline-tools.zip"
            # Prefer wget/curl if available for better progress on Termux
            if shutil.which("wget"):
                subprocess.run(["wget", "-q", "--show-progress", "-O", str(zip_path), url], check=True)
            elif shutil.which("curl"):
                subprocess.run(["curl", "-L", "--progress-bar", "-o", str(zip_path), url], check=True)
            else:
                urllib.request.urlretrieve(url, zip_path)

            print("Extracting...")
            with zipfile.ZipFile(zip_path) as z:
                z.extractall(cmdline_tools_dir)

        # The archive usually contains a "cmdline-tools" folder. Move/rename to "latest"
        possible_extracted = cmdline_tools_dir / "cmdline-tools"
        if possible_extracted.exists() and possible_extracted != latest_dir:
            if latest_dir.exists():
                shutil.rmtree(latest_dir)
            possible_extracted.rename(latest_dir)

        # Make sure binaries are executable
        for bin_dir in [latest_dir / "bin", sdk_root / "platform-tools"]:
            if bin_dir.exists():
                for f in bin_dir.iterdir():
                    if f.is_file():
                        f.chmod(0o755)

        sdkmanager = latest_dir / "bin" / "sdkmanager"
        if not sdkmanager.exists() and (latest_dir / "bin" / "sdkmanager.bat").exists():
            sdkmanager = latest_dir / "bin" / "sdkmanager.bat"

        if not sdkmanager.exists():
            print("WARNING: sdkmanager not found after extraction. Path may need manual fix.")
            return

        print("Configuring environment...")
        java_home = os.environ.get("JAVA_HOME", "")
        env = os.environ.copy()
        if java_home:
            env["JAVA_HOME"] = java_home

        # Set standard env vars now
        os.environ["ANDROID_HOME"] = str(sdk_root)
        os.environ["ANDROID_SDK_ROOT"] = str(sdk_root)
        path_add = f"{latest_dir / 'bin'}:{sdk_root / 'platform-tools'}:{sdk_root / 'build-tools'}"
        os.environ["PATH"] = path_add + os.pathsep + os.environ.get("PATH", "")

        print("Accepting all licenses (auto)...")
        # Feed yes to all license prompts
        yes_input = (b"y\n" * 50)
        subprocess.run(
            [str(sdkmanager), "--sdk_root=" + str(sdk_root), "--licenses"],
            input=yes_input,
            env=env,
            check=False,
            timeout=120
        )

        print("Installing required SDK components (platform, build-tools, platform-tools)...")
        packages = [
            "platform-tools",
            "platforms;android-34",
            "build-tools;34.0.0",
            "build-tools;33.0.2",  # fallback
        ]
        for pkg in packages:
            print(f"  Installing {pkg}...")
            subprocess.run(
                [str(sdkmanager), "--sdk_root=" + str(sdk_root), pkg],
                input=yes_input,
                env=env,
                check=False,
                timeout=300
            )

        print(f"\n✅ Android SDK setup COMPLETE at: {sdk_root}")
        print("Key environment variables (export these if the build complains):")
        print(f'  export ANDROID_HOME="{sdk_root}"')
        print(f'  export ANDROID_SDK_ROOT="{sdk_root}"')
        print(f'  export PATH="{latest_dir / "bin"}:{sdk_root / "platform-tools"}:$PATH"')

        # Verify
        if (sdk_root / "platform-tools" / "adb").exists() or (sdk_root / "platform-tools" / "adb.exe").exists():
            print("✓ platform-tools present.")
        if (sdk_root / "build-tools" / "34.0.0" / "aapt").exists() or list((sdk_root / "build-tools").glob("*/aapt*")):
            print("✓ build-tools present.")

    except Exception as e:
        print(f"SDK setup had an issue: {e}")
        print("The project is still generated. You can finish setup manually with:")
        print("  sdkmanager --licenses")
        print("  sdkmanager \"platforms;android-34\" \"build-tools;34.0.0\" platform-tools")
        print(f"Then set ANDROID_HOME={sdk_root}")


# Early detection so Pillow and Android SDK can auto-install with no prompts.
# Java/Gradle always install via pkg/apt when missing; -y also pulls the full SDK.
AUTO_INSTALL = (
    bool(os.environ.get("LAUNCHER_ICONS_YES"))
    or bool(os.environ.get("LAUNCHER_ICONS_AUTO"))
    or "-y" in sys.argv
    or "--yes" in sys.argv
    or "--auto" in sys.argv
    or "--build-apk" in sys.argv
)

ensure_pillow()

from PIL import Image, ImageDraw, ImageFont, ImageEnhance


# ==================== CORE FUNCTIONS ====================
def get_font(size: int):
    for path in [
        "/system/fonts/Roboto-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    ]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def colorize_toward_black(img: Image.Image, amount: float = 0.5) -> Image.Image:
    if img.mode != "RGBA":
        img = img.convert("RGBA")
    black = Image.new("RGBA", img.size, (0, 0, 0, 255))
    return Image.blend(img, black, amount)


def process_icon(
    src_path: Path,
    dst_path: Path,
    base_font: ImageFont.ImageFont,
    max_label_chars: int,
    label_area_ratio: float,
    dry_run: bool = False,
) -> bool:
    try:
        with Image.open(src_path) as im:
            if im.mode != "RGBA":
                im = im.convert("RGBA")

            icon = colorize_toward_black(im, 0.5)
            w, h = icon.size

            label_area_h = int(h * label_area_ratio) + 24
            total_h = h + label_area_h

            new_im = Image.new("RGBA", (w, total_h), (0, 0, 0, 0))
            new_im.paste(icon, (0, 0))

            appname = src_path.stem
            label = appname if len(appname) <= max_label_chars else appname[:max_label_chars - 1] + "…"

            pointsize = max(16, min(32, w // 9))
            try:
                text_font = ImageFont.truetype(base_font.path, pointsize) if hasattr(base_font, "path") else get_font(pointsize)
            except Exception:
                text_font = get_font(pointsize)

            draw = ImageDraw.Draw(new_im)
            draw.text(
                (w // 2, h + 10),
                label,
                font=text_font,
                fill="white",
                stroke_width=2,
                stroke_fill="#1f1f1f",
                anchor="mt",
            )

            if dry_run:
                print(f"  [DRY-RUN] Would create: {dst_path}")
            else:
                new_im.save(dst_path, "PNG")

            return True

    except Exception as e:
        print(f"[!] Skipping {src_path.name}: {e}", file=sys.stderr)
        return False


def _download_file(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    if shutil.which("wget"):
        subprocess.run(["wget", "-q", "-O", str(dest), url], check=True)
    elif shutil.which("curl"):
        subprocess.run(["curl", "-fsSL", "-o", str(dest), url], check=True)
    else:
        urllib.request.urlretrieve(url, dest)


def bootstrap_gradle_wrapper(project_dir: Path) -> bool:
    """Create gradlew + wrapper files without requiring system gradle."""
    import urllib.error

    wrapper_dir = project_dir / "gradle" / "wrapper"
    wrapper_dir.mkdir(parents=True, exist_ok=True)

    props = wrapper_dir / "gradle-wrapper.properties"
    if not props.exists():
        props.write_text(GRADLE_WRAPPER_PROPERTIES)

    jar_path = wrapper_dir / "gradle-wrapper.jar"
    if not jar_path.exists():
        print(f"  Downloading gradle-wrapper.jar ({GRADLE_VERSION})...")
        try:
            _download_file(GRADLE_WRAPPER_JAR_URL, jar_path)
        except (urllib.error.URLError, subprocess.CalledProcessError, OSError) as e:
            print(f"  Could not download gradle-wrapper.jar: {e}")
            return False

    gradlew = project_dir / "gradlew"
    if not gradlew.exists():
        print("  Downloading gradlew launcher script...")
        try:
            _download_file(GRADLEW_URL, gradlew)
        except (urllib.error.URLError, subprocess.CalledProcessError, OSError) as e:
            print(f"  Could not download gradlew: {e}")
            return False

    _make_executable(gradlew)
    return gradlew.exists() and jar_path.exists()


def ensure_gradle_wrapper(project_dir: Path, env: dict[str, str]) -> bool:
    """Ensure ./gradlew exists and is executable."""
    gradlew = project_dir / "gradlew"
    if gradlew.exists():
        _make_executable(gradlew)
        return True

    search_path = env.get("PATH", os.environ.get("PATH", ""))
    gradle_cmd = shutil.which("gradle", path=search_path)
    if gradle_cmd:
        gradle_path = Path(gradle_cmd)
        _make_executable(gradle_path)
        if _java_available():
            print("  Generating Gradle wrapper using system gradle...")
            subprocess.run(
                [str(gradle_path), "wrapper", f"--gradle-version={GRADLE_VERSION}"],
                cwd=project_dir,
                env=env,
                check=False,
            )
            if gradlew.exists():
                _make_executable(gradlew)
                return True

    if not shutil.which("gradle", path=search_path):
        print("  No gradle in PATH — bootstrapping wrapper directly...")
    else:
        print("  System gradle could not create wrapper — bootstrapping directly...")

    if bootstrap_gradle_wrapper(project_dir):
        return True

    if download_gradle_manually():
        gradle_cmd = shutil.which("gradle", path=os.environ.get("PATH", ""))
        if gradle_cmd and _java_available():
            subprocess.run(
                [gradle_cmd, "wrapper", f"--gradle-version={GRADLE_VERSION}"],
                cwd=project_dir,
                env=env,
                check=False,
            )
            if gradlew.exists():
                _make_executable(gradlew)
                return True
        return bootstrap_gradle_wrapper(project_dir)

    return bootstrap_gradle_wrapper(project_dir)


def build_apk(project_dir: Path, pack_name: str) -> None:
    """Aggressively attempt to build a release APK using whatever tools we just installed."""
    print("\n🔨 Aggressively attempting CLI APK build...")

    if not _java_available():
        print("  Java is not installed or not on PATH.")
        print("  Re-run with -y to auto-install Java, or install default-jdk / openjdk-17 manually.")
        print("  The icon pack project was still generated — run ./build.sh after installing Java.")
        return

    # Make sure critical env vars from our setup are in the subprocess env
    env = os.environ.copy()
    _set_java_home()
    if env.get("JAVA_HOME"):
        env["PATH"] = str(Path(env["JAVA_HOME"]) / "bin") + os.pathsep + env.get("PATH", "")

    sdk_root = env.get("ANDROID_HOME") or env.get("ANDROID_SDK_ROOT") or str(Path.home() / "Android" / "Sdk")
    if not env.get("ANDROID_HOME"):
        env["ANDROID_HOME"] = sdk_root
    if not env.get("ANDROID_SDK_ROOT"):
        env["ANDROID_SDK_ROOT"] = sdk_root

    # Add common SDK paths to PATH for this build
    for p in [
        f"{sdk_root}/cmdline-tools/latest/bin",
        f"{sdk_root}/platform-tools",
        f"{sdk_root}/build-tools/34.0.0",
    ]:
        if Path(p).exists():
            env["PATH"] = p + os.pathsep + env.get("PATH", "")

    try:
        if not ensure_gradle_wrapper(project_dir, env):
            print("\nCould not create gradlew.")
            print("Try manually inside the pack folder:")
            print(f"  cd {project_dir.name}")
            print("  ./build.sh")
            return

        gradlew = project_dir / "gradlew"
        _make_executable(gradlew)
        print("  Running ./gradlew assembleRelease (this may take several minutes on first run)...")
        result = subprocess.run(
            [str(gradlew), "assembleRelease", "--console=plain"],
            cwd=project_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=600,
        )

        apk_dir = project_dir / "app" / "build" / "outputs" / "apk" / "release"
        apk_files = list(apk_dir.glob("*.apk")) if apk_dir.exists() else []
        if apk_files:
            apk_src = apk_files[0]
            apk_dest = project_dir.parent / f"{pack_name}-release.apk"
            shutil.copy2(apk_src, apk_dest)
            print(f"\n🎉 SUCCESS! APK built and copied:")
            print(f"   {apk_dest}")
            print(f"   Size: {apk_dest.stat().st_size / 1024 / 1024:.1f} MB")
            return

        print("Build finished but no APK found in expected location.")
        print(f"Check: {apk_dir}")
        if result.returncode != 0:
            print("\n--- Gradle output (last part) ---")
            out = (result.stdout or "") + "\n" + (result.stderr or "")
            print(out[-2000:])

    except subprocess.TimeoutExpired:
        print("Build timed out (10 minutes). Try building manually.")
    except OSError as e:
        print(f"Build attempt encountered an issue: {e}")
        print("The project is still fully generated and can be built in Android Studio or with proper Gradle + SDK setup.")
    except Exception as e:
        print(f"Build attempt encountered an issue: {e}")
        print("The project is still fully generated and can be built in Android Studio or with proper Gradle + SDK setup.")


def create_icon_pack_project(
    processed_icons_dir: Path,
    pack_name: str,
    package_name: str,
    build_apk_flag: bool = False
):
    """Create a complete, Gradle-based, CLI-buildable Android icon pack project."""
    project_dir = processed_icons_dir.parent / pack_name

    # Full modern Android project layout
    app_dir = project_dir / "app"
    src_main = app_dir / "src" / "main"
    res_dir = src_main / "res"
    drawable_dir = res_dir / "drawable"
    xml_dir = res_dir / "xml"
    java_pkg_dir = src_main / "java" / package_name.replace(".", "/")

    for d in [drawable_dir, xml_dir, java_pkg_dir, res_dir / "mipmap-hdpi"]:
        d.mkdir(parents=True, exist_ok=True)

    icon_files = list(processed_icons_dir.glob("*.png"))

    # Copy + sanitize drawable names
    drawable_names = []
    for icon_file in icon_files:
        name = icon_file.stem.lower()
        name = name.replace(" ", "_").replace("-", "_").replace(".", "_")
        name = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
        if name and name[0].isdigit():
            name = "icon_" + name
        shutil.copy2(icon_file, drawable_dir / f"{name}.png")
        drawable_names.append(name)

    # Generate a simple app launcher icon (so @mipmap/ic_launcher works)
    try:
        icon_img = Image.new("RGBA", (192, 192), (30, 136, 229, 255))  # Material blue
        draw = ImageDraw.Draw(icon_img)
        draw.rounded_rectangle([24, 24, 168, 168], radius=32, fill=(255, 255, 255, 230))
        icon_img.save(res_dir / "mipmap-hdpi" / "ic_launcher.png")
        # Quick copies for other densities
        for density in ["mdpi", "xhdpi", "xxhdpi"]:
            (res_dir / f"mipmap-{density}").mkdir(exist_ok=True)
            icon_img.save(res_dir / f"mipmap-{density}" / "ic_launcher.png")
    except Exception:
        pass  # non-fatal

    # AndroidManifest.xml (modern, inside app/src/main)
    manifest = f'''<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android"
    package="{package_name}">

    <application
        android:label="{pack_name}"
        android:icon="@mipmap/ic_launcher"
        android:theme="@android:style/Theme.DeviceDefault">

        <activity
            android:name=".MainActivity"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

    </application>
</manifest>
'''
    (src_main / "AndroidManifest.xml").write_text(manifest)

    # Minimal MainActivity.java
    main_activity = f'''package {package_name};

import android.app.Activity;
import android.os.Bundle;

public class MainActivity extends Activity {{
    @Override
    protected void onCreate(Bundle savedInstanceState) {{
        super.onCreate(savedInstanceState);
        // This is an icon pack. No UI needed.
        finish();
    }}
}}
'''
    (java_pkg_dir / "MainActivity.java").write_text(main_activity)

    # appfilter.xml with placeholders
    appfilter = ET.Element("resources")
    for dname in drawable_names:
        item = ET.SubElement(appfilter, "item")
        item.set("component", "ComponentInfo{com.example.app/com.example.app.MainActivity}")
        item.set("drawable", dname)

    tree = ET.ElementTree(appfilter)
    ET.indent(tree, space="    ")
    tree.write(xml_dir / "appfilter.xml", encoding="utf-8", xml_declaration=True)

    # Gradle project files
    (project_dir / "settings.gradle").write_text(f"""rootProject.name = "{pack_name}"
include ':app'
""")

    (project_dir / "build.gradle").write_text("""plugins {
    id 'com.android.application' version '8.2.0' apply false
}
""")

    (project_dir / "gradle.properties").write_text("""android.useAndroidX=true
android.nonTransitiveRClass=true
org.gradle.jvmargs=-Xmx2048m -Dfile.encoding=UTF-8
android.nonFinalResIds=false
""")

    app_build = f'''plugins {{
    id 'com.android.application'
}}

android {{
    namespace "{package_name}"
    compileSdk 34

    defaultConfig {{
        applicationId "{package_name}"
        minSdk 21
        targetSdk 34
        versionCode 1
        versionName "1.0"
    }}

    buildTypes {{
        release {{
            minifyEnabled false
            proguardFiles getDefaultProguardFile('proguard-android-optimize.txt'), 'proguard-rules.pro'
        }}
    }}

    compileOptions {{
        sourceCompatibility JavaVersion.VERSION_1_8
        targetCompatibility JavaVersion.VERSION_1_8
    }}
}}

dependencies {{}}
'''
    (app_dir / "build.gradle").write_text(app_build)
    (project_dir / "proguard-rules.pro").write_text("# Add custom ProGuard rules here\n")

    # Helpful build.sh for pure CLI usage
    build_sh_content = f'''#!/bin/bash
# {pack_name} - CLI APK build helper (aggressive "just work" mode)
set -e
echo "==> Building {pack_name} release APK (aggressive mode)"

# Aggressive auto-install for common environments
if ! command -v gradle >/dev/null 2>&1 || ! command -v java >/dev/null 2>&1; then
    if [ -n "$PREFIX" ] && [[ "$PREFIX" == *"com.termux"* ]]; then
        echo "Termux detected: installing everything needed..."
        pkg update -y || true
        pkg install -y openjdk-17 gradle unzip wget coreutils || true
    elif command -v apt-get >/dev/null 2>&1; then
        echo "apt detected: installing JDK + gradle..."
        if [ "$(id -u)" -eq 0 ]; then
            apt-get update -y || true
            apt-get install -y default-jdk gradle unzip wget || true
        else
            sudo apt-get update -y || true
            sudo apt-get install -y default-jdk gradle unzip wget || true
        fi
    fi
fi

# Try to ensure Android SDK if missing (downloads if needed)
if [ -z "$ANDROID_HOME" ] && [ -z "$ANDROID_SDK_ROOT" ]; then
    for cand in "$HOME/Android/Sdk" "/data/data/com.termux/files/usr/android-sdk" ; do
        if [ -d "$cand" ] && [ -f "$cand/cmdline-tools/latest/bin/sdkmanager" ]; then
            export ANDROID_HOME="$cand"
            export ANDROID_SDK_ROOT="$cand"
            export PATH="$cand/cmdline-tools/latest/bin:$cand/platform-tools:$PATH"
            break
        fi
    done
fi

if [ ! -f gradlew ]; then
    echo "Bootstrapping gradle wrapper (no system gradle required)..."
    mkdir -p gradle/wrapper
    curl -fsSL -o gradle/wrapper/gradle-wrapper.jar \\
        "https://raw.githubusercontent.com/gradle/gradle/v8.5.0/gradle/wrapper/gradle-wrapper.jar" || true
    curl -fsSL -o gradlew \\
        "https://raw.githubusercontent.com/gradle/gradle/v8.5.0/gradlew" || true
    cat > gradle/wrapper/gradle-wrapper.properties <<'EOF'
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https\\://services.gradle.org/distributions/gradle-8.5-bin.zip
networkTimeout=10000
validateDistributionUrl=true
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
EOF
fi

if [ -f gradlew ]; then
    chmod +x gradlew
    echo "Running assembleRelease (first time may download Gradle/Android bits)..."
    ./gradlew assembleRelease --console=plain
    APK=$(find app/build/outputs/apk/release -name "*.apk" 2>/dev/null | head -1 || true)
    if [ -n "$APK" ]; then
        cp "$APK" "../{pack_name}-release.apk" 2>/dev/null || true
        echo "✅ APK ready: ../{pack_name}-release.apk"
    fi
else
    echo "Still no gradlew."
    echo "Re-run launcher_icons.py on your icons folder (APK build is on by default)."
fi
'''
    build_sh_path = project_dir / "build.sh"
    build_sh_path.write_text(build_sh_content)
    build_sh_path.chmod(0o755)

    # Rich README inside the pack
    readme = f"""# {pack_name} Icon Pack

Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} using launcher_icons.py

This is a **complete, buildable Android project** (Gradle + Java).

## Fastest one-shot CLI build (no GUI — APK is on by default)

```bash
# From the icons folder
python /path/to/launcher_icons.py . -y --icon-pack-name {pack_name} --package-name {package_name}
```

Or after generation:
```bash
cd {pack_name}
./build.sh
```

The final APK will be placed next to this folder as `{pack_name}-release.apk`.

## Requirements & auto-setup

Running `launcher_icons.py` on an icons folder **by default**:
- styles icons
- creates this Gradle project
- builds the APK

It auto-installs via pkg/apt when needed:
- Pillow (if missing)
- openjdk + gradle

Add `-y` for zero-prompt Android SDK setup too:

```bash
./launcher_icons.py /path/to/icons -y ...
```

## Updating icon mappings

1. Open `app/src/main/res/xml/appfilter.xml`
2. For every `<item>`, replace the `component="..."` value with the **real** ComponentInfo for that app.
   - Tools that help: "Activity Launcher", "Package Name Viewer", or `adb shell dumpsys package`

## Building manually (if you didn't use the launcher script)

```bash
cd {pack_name}
./build.sh
```

Or:
```bash
gradle wrapper
./gradlew assembleRelease
```

APK location: `app/build/outputs/apk/release/`

**Pro tip:** Just point the script at your icons folder — icon pack + APK are on by default:
```bash
launcher_icons.py /path/to/icons -y
```
Use `--no-apk` or `--no-icon-pack` only if you want to skip those steps.

## Notes

- The icons in `res/drawable/` are the styled launcher versions.
- You can add more icons later by dropping PNGs in drawable and updating appfilter.xml.
- This project structure works with Nova Launcher, Lawnchair, Smart Launcher, etc.

Enjoy your custom icons!
"""
    (project_dir / "README.md").write_text(readme)

    # Pre-bootstrap the Gradle wrapper so fresh systems don't need system gradle installed.
    bootstrap_gradle_wrapper(project_dir)

    print(f"\n✅ Full Gradle icon pack project created at: {project_dir}")
    print("   • Contains complete build files + build.sh + gradlew")
    print("   • Edit appfilter.xml with real component names")

    if build_apk_flag:
        build_apk(project_dir, pack_name)


# ==================== MAIN ====================
def main():
    parser = argparse.ArgumentParser(
        description="Create launcher-style icons (icon + label below), generate an Android icon pack, and build an APK (all on by default)."
    )
    parser.add_argument("directory", help="Folder containing PNG icons")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing files")
    parser.add_argument("--max-label-chars", type=int, default=14, help="Max characters before ellipsis (default: 14)")
    parser.add_argument("--label-area-ratio", type=float, default=1/3, help="Extra height ratio for label area")
    parser.add_argument("--output-dir", default="processed_icons", help="Output subdirectory name")
    parser.add_argument("--no-icon-pack", action="store_true",
                        help="Only style icons; skip icon pack project generation")
    parser.add_argument("--no-apk", action="store_true",
                        help="Create icon pack project but skip APK build")
    parser.add_argument("--create-icon-pack", action="store_true",
                        help=argparse.SUPPRESS)  # legacy; icon pack is now default
    parser.add_argument("--build-apk", action="store_true",
                        help=argparse.SUPPRESS)  # legacy; APK build is now default
    parser.add_argument("-y", "--yes", "--auto", dest="auto_install", action="store_true",
                        help="Also auto-install full Android SDK with ZERO prompts (Java/Gradle already install via pkg/apt by default)")
    parser.add_argument("--icon-pack-name", default="CustomIcons", help="Name of the icon pack folder/app")
    parser.add_argument("--package-name", default="com.yourname.customicons", help="Android package name")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    create_icon_pack = not args.no_icon_pack
    build_apk = create_icon_pack and not args.no_apk

    if build_apk and not args.dry_run:
        ensure_build_tools()

    target = Path(args.directory).expanduser().resolve()
    if not target.is_dir():
        print(f"Error: {target} is not a directory", file=sys.stderr)
        sys.exit(1)

    output_dir = target / args.output_dir
    if not args.dry_run:
        output_dir.mkdir(exist_ok=True)

    png_files = sorted(f for f in target.iterdir() if f.is_file() and f.suffix.lower() == ".png")
    total = len(png_files)

    if total == 0:
        print("No PNG files found in the directory.")
        return

    mode = "DRY RUN - " if args.dry_run else ""
    print(f"{mode}Processing {total} icons...")

    base_font = get_font(24)
    processed = skipped = 0

    for i, src in enumerate(png_files, 1):
        dst = output_dir / src.name
        print(f"\r[{i}/{total}] {src.name}", end="", flush=True)

        if process_icon(src, dst, base_font, args.max_label_chars,
                        args.label_area_ratio, args.dry_run):
            processed += 1
        else:
            skipped += 1

    print("\r" + " " * 90 + "\r", end="")

    if args.dry_run:
        print(f"(DRY RUN) Would have created {processed} icons → {output_dir}")
    else:
        print(f"(^_^) Icons saved to: {output_dir}")

    print(f"Summary: Total={total} | Processed={processed} | Skipped={skipped}")

    if create_icon_pack and not args.dry_run:
        create_icon_pack_project(output_dir, args.icon_pack_name, args.package_name, build_apk)


if __name__ == "__main__":
    main()
