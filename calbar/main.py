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
import atexit
import signal
import faulthandler
import subprocess
import time

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


def setup_fault_logging():
    """クラッシュ時の Python スタックを別ファイルへ出力する。"""
    fault_log = os.path.expanduser("~/.calbar/calbar-fault.log")
    os.makedirs(os.path.dirname(fault_log), exist_ok=True)
    fp = open(fault_log, "a", encoding="utf-8")
    faulthandler.enable(file=fp, all_threads=True)
    for sig in (signal.SIGABRT, signal.SIGSEGV, signal.SIGBUS):
        try:
            faulthandler.register(sig, file=fp, all_threads=True, chain=True)
        except Exception:
            # 環境によっては登録できないシグナルがある
            continue
    return fp


class SingleInstanceLock:
    """同時起動を防ぐためのファイルロック。"""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self._fp = None

    def acquire(self) -> bool:
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        self._fp = open(self.lock_path, "a+")
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


def _read_lock_pid(lock_path: str) -> int | None:
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            raw = f.read().strip()
        if not raw:
            return None
        pid = int(raw)
        return pid if pid > 0 else None
    except Exception:
        return None


def _is_calbar_process(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid), "-o", "command="],
            capture_output=True,
            text=True,
            check=False,
        )
        cmdline = (result.stdout or "").strip().lower()
        return "calbar" in cmdline
    except Exception:
        return False


def _wait_process_exit(pid: int, timeout_sec: float = 5.0) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        except PermissionError:
            return False
        time.sleep(0.1)
    return False


def main():
    setup_logging()
    fault_fp = setup_fault_logging()
    logger = logging.getLogger(__name__)
    logger.info("CalBar プロセス開始: pid=%d", os.getpid())

    def _on_exit():
        logger.info("CalBar プロセス終了: pid=%d", os.getpid())
        try:
            fault_fp.flush()
            fault_fp.close()
        except Exception:
            pass

    def _signal_handler(signum, _frame):
        signame = signal.Signals(signum).name
        logger.warning("終了シグナル受信: %s", signame)
        raise KeyboardInterrupt

    atexit.register(_on_exit)
    for sig in (signal.SIGTERM, signal.SIGHUP, signal.SIGINT):
        try:
            signal.signal(sig, _signal_handler)
        except Exception:
            continue

    lock_path = os.path.expanduser("~/.calbar/calbar.lock")
    instance_lock = SingleInstanceLock(lock_path)
    if not instance_lock.acquire():
        existing_pid = _read_lock_pid(lock_path)
        if existing_pid and _is_calbar_process(existing_pid):
            logger.warning(
                "既存の CalBar プロセスを終了して再起動します (pid=%d)",
                existing_pid,
            )
            try:
                os.kill(existing_pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except Exception as e:
                logger.warning("既存プロセス終了要求に失敗: %s", e)
                return

            if not _wait_process_exit(existing_pid, timeout_sec=5.0):
                logger.warning(
                    "既存プロセスの終了待ちがタイムアウトしたため強制終了します (pid=%d)",
                    existing_pid,
                )
                try:
                    os.kill(existing_pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except Exception as e:
                    logger.warning("既存プロセス強制終了に失敗: %s", e)
                    return
                if not _wait_process_exit(existing_pid, timeout_sec=2.0):
                    logger.warning("既存プロセスを強制終了できませんでした")
                    return

            if not instance_lock.acquire():
                logger.warning("再起動のためのロック再取得に失敗しました")
                return
            logger.info("既存プロセスの終了を確認し、再起動を続行します")
        else:
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
