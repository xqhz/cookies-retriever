import argparse
import configparser
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
import tempfile


def get_firefox_root():
    """Return Firefox root directory"""
    if sys.platform.startswith("win"):
        return Path(os.environ["APPDATA"]) / "Mozilla" / "Firefox"
    elif sys.platform.startswith("linux"):
        return Path.home() / ".mozilla" / "firefox"
    else:
        raise RuntimeError("Unsupported OS")


def find_default_profile():
    firefox_root = get_firefox_root()
    profiles_ini = firefox_root / "profiles.ini"

    if not profiles_ini.exists():
        raise FileNotFoundError("profiles.ini not found")

    config = configparser.ConfigParser()
    config.read(profiles_ini, encoding="utf-8")

    # --- 1. Новый формат Firefox (через InstallXXXX) ---
    for section in config.sections():
        if section.startswith("Install"):
            default_path = config.get(section, "Default", fallback=None)
            if default_path:
                profile_path = firefox_root / default_path
                if profile_path.exists():
                    cookies = profile_path / "cookies.sqlite"
                    if cookies.exists():
                        return profile_path

    # --- 2. Старый формат (Default=1) ---
    for section in config.sections():
        if section.startswith("Profile"):
            if config.get(section, "Default", fallback="0") == "1":
                path = config.get(section, "Path", fallback=None)
                if not path:
                    continue

                is_relative = config.get(section, "IsRelative", fallback="1") == "1"
                profile_path = (firefox_root / path) if is_relative else Path(path)

                if profile_path.exists():
                    cookies = profile_path / "cookies.sqlite"
                    if cookies.exists():
                        return profile_path

    # --- 3. Фолбэк: просто берем первый профиль с cookies.sqlite ---
    for section in config.sections():
        if section.startswith("Profile"):
            path = config.get(section, "Path", fallback=None)
            if not path:
                continue

            is_relative = config.get(section, "IsRelative", fallback="1") == "1"
            profile_path = (firefox_root / path) if is_relative else Path(path)

            if profile_path.exists():
                cookies = profile_path / "cookies.sqlite"
                if cookies.exists():
                    return profile_path

    raise FileNotFoundError("No Firefox profile with cookies.sqlite found")


def load_cookies(db_path, domain=None):
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()

    if domain:
        cur.execute(
            "SELECT host, name, value FROM moz_cookies WHERE host LIKE ?",
            (f"%{domain}%",)
        )
    else:
        cur.execute(
            "SELECT host, name, value FROM moz_cookies"
        )

    rows = cur.fetchall()
    conn.close()
    return rows


def main():
    parser = argparse.ArgumentParser(
        description="Read Firefox cookies (Windows / Linux)"
    )
    parser.add_argument("--domain", help="Filter cookies by domain")
    parser.add_argument("--all", action="store_true", help="Show all cookies")
    parser.add_argument("--out", help="Save cookies to JSON")

    args = parser.parse_args()

    if not args.domain and not args.all:
        parser.error("Use --domain or --all")

    profile = find_default_profile()
    cookies_db = profile / "cookies.sqlite"

    # Работаем с копией (Firefox может быть запущен)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp_path = Path(tmp.name)

    shutil.copy(cookies_db, tmp_path)

    try:
        cookies = load_cookies(tmp_path, args.domain)
    finally:
        tmp_path.unlink(missing_ok=True)

    if args.out:
        data = [
            {"host": h, "name": n, "value": v}
            for h, n, v in cookies
        ]
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[+] Saved {len(cookies)} cookies to {args.out}")
    else:
        for host, name, value in cookies:
            print(f"{host}\t{name}={value}")


if __name__ == "__main__":
    main()
