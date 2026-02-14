#!/usr/bin/env python3
"""CalBar - macOS メニューバー Google カレンダー通知アプリ"""

import logging
import os
import sys

# calbar ディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def setup_logging():
    """ロギング設定"""
    log_dir = os.path.expanduser("~/.calbar")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "calbar.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    logger.info("CalBar を起動します...")

    try:
        from app import CalBarApp

        app = CalBarApp()
        app.run()
    except KeyboardInterrupt:
        logger.info("CalBar を終了します")
    except Exception as e:
        logger.exception(f"予期しないエラー: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
