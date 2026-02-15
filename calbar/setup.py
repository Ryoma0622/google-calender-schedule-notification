#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "py2app>=0.28",
#     "setuptools>=68.0",
#     "rumps>=0.4.0",
#     "playwright>=1.40.0",
# ]
# ///
from setuptools import setup

APP = ["main.py"]
DATA_FILES = ["resources"]
OPTIONS = {
    "argv_emulation": True,
    "iconfile": "resources/icon.png",
    "plist": {
        "LSUIElement": True,  # Dock にアイコンを表示しない
        "CFBundleName": "CalBar",
        "CFBundleDisplayName": "CalBar",
        "CFBundleIdentifier": "com.calbar.app",
        "CFBundleVersion": "1.0.0",
        "CFBundleShortVersionString": "1.0.0",
    },
    "packages": [
        "rumps",
        "playwright",
        "playwright.sync_api",
        "playwright._impl",
    ],
    "includes": [
        "playwright.sync_api",
    ],
    "excludes": [
        "playwright._impl.__pyinstaller",  # PyInstaller 専用フックを除外
    ],
}

setup(
    name="CalBar",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
