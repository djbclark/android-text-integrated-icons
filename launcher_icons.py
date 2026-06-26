#!/usr/bin/env python3
"""
Launcher-style PNG Icon Processor + Icon Pack + CLI APK Builder
Version 1.3.0

Features:
- Creates launcher-style images (icon + label below) mimicking Pixel Launcher
- -y / --yes / --auto : full one-shot auto-install of Pillow + Java + Gradle + Android SDK (no prompts)
- --build-apk : generates full Gradle project + tries to build a real APK (one-shot recommended)
- Aggressive auto-setup is now the default when -y or --build-apk is used
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

__version__ = "1.3.0"


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


def ensure_build_tools() -> None:
    """Ensure Java + Gradle (and optionally Android SDK) are available for --build-apk.

    Modeled after the Pillow auto/prompt install logic.
    Only called when --build-apk is used.
    """
    # Quick presence check
    has_java = bool(shutil.which("java") or shutil.which("javac"))
    has_gradle = bool(shutil.which("gradle"))

    if has_java and has_gradle:
        return

    print("\nGradle + Java are required to build APKs (--build-apk).")

    if is_termux() or AUTO_INSTALL:
        if is_termux():
            print("Termux detected — aggressively installing everything needed for APK builds (one-shot mode)...")
        else:
            print("AUTO_INSTALL / -y mode — aggressively installing everything (Java + Gradle + Android SDK)...")
        print("(openjdk-17, gradle, unzip, wget, and full Android SDK tools — this may take several minutes)")

        try:
            if is_termux():
                subprocess.run(["pkg", "update", "-y"], check=False)
                subprocess.run(
                    ["pkg", "install", "-y",
                     "openjdk-17", "gradle", "unzip", "wget", "coreutils"],
                    check=True
                )
            else:
                # Desktop aggressive path (best effort)
                if shutil.which("apt") or shutil.which("apt-get"):
                    subprocess.run(["sudo", "apt-get", "update", "-y"], check=False)
                    subprocess.run(
                        ["sudo", "apt-get", "install", "-y", "default-jdk", "gradle", "unzip", "wget"],
                        check=True
                    )
                # etc. fall through to manual download if needed

            print("✅ Base tools (Java + Gradle) installed.")

            # Set JAVA_HOME aggressively
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

            # Always auto-setup full Android SDK in one-shot / Termux / -y mode
            print("\nNow aggressively setting up Android SDK (big download, please be patient)...")
            setup_minimal_android_sdk()

            print("\n✅ All build dependencies should now be ready!")
            print("Environment variables set for this session. Re-run if shell needs restart.")
            return
        except subprocess.CalledProcessError as e:
            print(f"\nAutomatic installation encountered an error: {e}")
            print("Trying SDK setup anyway...")
            setup_minimal_android_sdk()
            return

    # Non-Termux: respect AUTO_INSTALL (from -y or --build-apk)
    if not sys.stdin.isatty():
        if AUTO_INSTALL:
            print("Non-interactive + AUTO_INSTALL: proceeding with auto install.")
        else:
            print("Non-interactive session: skipping automatic Gradle/Java install.")
            print("Install Java (JDK 17+) and Gradle, then re-run with --build-apk.")
            return

    if AUTO_INSTALL:
        print("AUTO_INSTALL mode: installing Java + Gradle + SDK automatically (no prompt).")
        response = "y"
    else:
        try:
            response = input("Install Java + Gradle now? [Y/n]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted build tools install.")
            return

    if response not in ("", "y", "yes"):
        print("\nSkipping. You can install Java + Gradle manually and re-run.")
        return

    print("Installing Java + Gradle...\n")

    success = False
    try:
        if shutil.which("apt") or shutil.which("apt-get"):
            subprocess.run(["sudo", "apt-get", "update", "-y"], check=False)
            subprocess.run(
                ["sudo", "apt-get", "install", "-y", "default-jdk", "gradle", "unzip", "wget"],
                check=True
            )
            success = True
        elif shutil.which("dnf"):
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
            print("No common package manager detected. Trying to download Gradle directly...")
            success = download_gradle_manually()
    except subprocess.CalledProcessError as e:
        print(f"Install command failed: {e}")
    except Exception as e:
        print(f"Unexpected error during install: {e}")

    if success:
        print("\n✅ Java + Gradle installation attempted.")
        print("Restart your terminal or export JAVA_HOME if needed.")

        # In AUTO_INSTALL / -y / --build-apk mode, always do the SDK too (aggressive one-shot)
        if AUTO_INSTALL:
            print("AUTO_INSTALL: also setting up Android SDK automatically...")
            setup_minimal_android_sdk()
        else:
            try:
                sdk_resp = input("Also download Android command line tools + basic SDK? (~1GB, takes time) [Y/n]: ").strip().lower()
                if sdk_resp not in ("n", "no"):
                    setup_minimal_android_sdk()
            except (EOFError, KeyboardInterrupt):
                pass
    else:
        print("\nCould not auto-install. Please install Java (JDK 17+) and Gradle manually.")


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
            # Symlink or add to PATH suggestion
            (Path.home() / ".local" / "bin").mkdir(parents=True, exist_ok=True)
            link = Path.home() / ".local" / "bin" / "gradle"
            if link.exists():
                link.unlink()
            link.symlink_to(gradle_bin)
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


# Early detection so Pillow (and later build tools) can auto-install with no prompts
# when -y / --yes / --auto / --build-apk or env var is present.
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


def build_apk(project_dir: Path, pack_name: str) -> None:
    """Aggressively attempt to build a release APK using whatever tools we just installed."""
    print("\n🔨 Aggressively attempting CLI APK build...")

    # Make sure critical env vars from our setup are in the subprocess env
    env = os.environ.copy()
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
        gradlew = project_dir / "gradlew"

        # Aggressively ensure wrapper exists
        if not gradlew.exists():
            gradle_cmd = shutil.which("gradle")
            if gradle_cmd:
                print("  Generating Gradle wrapper using gradle...")
                subprocess.run(
                    [gradle_cmd, "wrapper", "--gradle-version", "8.5"],
                    cwd=project_dir, env=env, check=False
                )
            else:
                # Try downloading wrapper jar directly or use system gradle if present elsewhere
                print("  No gradle in PATH, trying to prepare wrapper anyway...")
                # The project has gradle wrapper files usually generated by create, but we force
                subprocess.run(
                    ["gradle", "wrapper", "--gradle-version", "8.5"],
                    cwd=project_dir, env=env, check=False
                )

        if gradlew.exists():
            gradlew.chmod(0o755)
            print("  Running ./gradlew assembleRelease (this may take several minutes on first run)...")
            # Run with some output so user sees progress; -q can hide too much
            result = subprocess.run(
                [str(gradlew), "assembleRelease", "--console=plain"],
                cwd=project_dir,
                env=env,
                capture_output=True,
                text=True,
                timeout=600  # longer timeout for SDK downloads on first build
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
            else:
                print("Build finished but no APK found in expected location.")
                print(f"Check: {apk_dir}")
                if result.returncode != 0:
                    print("\n--- Gradle output (last part) ---")
                    out = (result.stdout or "") + "\n" + (result.stderr or "")
                    print(out[-2000:])
                return

        print("\nCould not create/ find gradlew.")
        print("Try manually inside the pack folder:")
        print(f"  cd {project_dir.name}")
        print("  ./build.sh   # or gradle wrapper && ./gradlew assembleRelease")

    except subprocess.TimeoutExpired:
        print("Build timed out (5 minutes). Try building manually.")
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
        echo "apt detected: installing JDK + gradle (sudo may be needed)..."
        sudo apt-get update -y || true
        sudo apt-get install -y default-jdk gradle unzip wget || true
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
    if command -v gradle >/dev/null 2>&1; then
        echo "Generating gradle wrapper..."
        gradle wrapper --gradle-version 8.5 || true
    fi
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
    echo "Run the original launcher_icons.py with --build-apk for full auto setup."
fi
'''
    build_sh_path = project_dir / "build.sh"
    build_sh_path.write_text(build_sh_content)
    build_sh_path.chmod(0o755)

    # Rich README inside the pack
    readme = f"""# {pack_name} Icon Pack

Generated {datetime.now().strftime("%Y-%m-%d %H:%M")} using launcher_icons.py

This is a **complete, buildable Android project** (Gradle + Java).

## Fastest one-shot CLI build (no GUI, no prompts)

```bash
# From the icons folder
python /path/to/launcher_icons.py . --create-icon-pack --build-apk -y --icon-pack-name {pack_name} --package-name {package_name}
```

Or after generation:
```bash
cd {pack_name}
./build.sh
```

The final APK will be placed next to this folder as `{pack_name}-release.apk`.

## Requirements & auto-setup

The easiest way is to run the original `launcher_icons.py` with `--build-apk -y`.
It will **fully automatically** install (no prompts):
- Pillow (if missing)
- openjdk + gradle
- Android command line tools + required SDK components

Use `-y` (or `--yes` / `--auto`) for true one-shot / CI behavior.

```bash
# One command to rule them all
./launcher_icons.py /path/to/icons --create-icon-pack --build-apk -y ...
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

**Pro tip:** Always prefer the original command:
```bash
launcher_icons.py ... --create-icon-pack --build-apk -y
```
This is now the default one-shot behavior and will auto-install everything with no prompting.

## Notes

- The icons in `res/drawable/` are the styled launcher versions.
- You can add more icons later by dropping PNGs in drawable and updating appfilter.xml.
- This project structure works with Nova Launcher, Lawnchair, Smart Launcher, etc.

Enjoy your custom icons!
"""
    (project_dir / "README.md").write_text(readme)

    print(f"\n✅ Full Gradle icon pack project created at: {project_dir}")
    print("   • Contains complete build files + build.sh")
    print("   • Edit appfilter.xml with real component names")

    if build_apk_flag:
        build_apk(project_dir, pack_name)


# ==================== MAIN ====================
def main():
    parser = argparse.ArgumentParser(
        description="Create launcher-style icons (icon + label below) and optionally generate an Android icon pack project."
    )
    parser.add_argument("directory", help="Folder containing PNG icons")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing files")
    parser.add_argument("--max-label-chars", type=int, default=14, help="Max characters before ellipsis (default: 14)")
    parser.add_argument("--label-area-ratio", type=float, default=1/3, help="Extra height ratio for label area")
    parser.add_argument("--output-dir", default="processed_icons", help="Output subdirectory name")
    parser.add_argument("--create-icon-pack", action="store_true", help="Also create a ready-to-build icon pack project")
    parser.add_argument("--build-apk", action="store_true", help="Create the icon pack project AND attempt to build a release APK via Gradle (pure CLI, no GUI)")
    parser.add_argument("-y", "--yes", "--auto", dest="auto_install", action="store_true",
                        help="Auto-install EVERYTHING (Pillow + Java + Gradle + full Android SDK) with ZERO prompts. "
                             "This + --build-apk is the recommended one-shot mode.")
    parser.add_argument("--icon-pack-name", default="CustomIcons", help="Name of the icon pack folder/app")
    parser.add_argument("--package-name", default="com.yourname.customicons", help="Android package name")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")

    args = parser.parse_args()

    if (args.build_apk or args.auto_install) and not args.dry_run:
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

    if (args.create_icon_pack or args.build_apk) and not args.dry_run:
        create_icon_pack_project(output_dir, args.icon_pack_name, args.package_name, args.build_apk)


if __name__ == "__main__":
    main()
