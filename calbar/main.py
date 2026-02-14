#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "rumps>=0.4.0",
#     "playwright>=1.40.0",
# ]
# ///
"""CalBar - macOS メニューバー Google カレンダー通知アプリ"""

import logging
import os
import sys
import fcntl

# calbar ディレクトリをパスに追加
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def setup_logging():
    """ロギング設定"""
    log_dir = os.path.expanduser("~/.calbar")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, "calbar.log")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [pid=%(process)d] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


class SingleInstanceLock:
    """同時起動を防ぐためのファイルロック。"""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self._fp = None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        self._fp = open(self.lock_path, "w")
        try:
            fcntl.flock(self._fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return False

        self._fp.seek(0)
        self._fp.truncate()
        self._fp.write(str(os.getpid()))
        self._fp.flush()
        return True

    def release(self):
        if self._fp is None:
            return
        try:
            fcntl.flock(self._fp.fileno(), fcntl.LOCK_UN)
        finally:
            self._fp.close()
            self._fp = None


def main():
    setup_logging()
    logger = logging.getLogger(__name__)
    instance_lock = SingleInstanceLock(os.path.expanduser("~/.calbar/calbar.lock"))
    if not instance_lock.acquire():
        logger.warning("CalBar は既に起動中です。既存プロセスを終了してから再実行してください。")
        return

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
    finally:
        instance_lock.release()


if __name__ == "__main__":
    main()
