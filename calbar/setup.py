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
    ],
}

setup(
    name="CalBar",
    app=APP,
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
