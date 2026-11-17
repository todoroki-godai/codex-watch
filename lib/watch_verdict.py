"""終了通知に添えるレビュー判定行の検査結果。検査の失敗は報告を妨げない。"""
from pathlib import Path
import sys


def verdict_notice(state_file: Path, report: Path) -> str:
    try:
        from round_gate import check_verdict_line, read_state_file

        # codex-impl の state にのみ記録される。旧レビュー state（modeなし）も検査する。
        if read_state_file(state_file).get("mode") == "workspace-write":
            return ""
        # 単独CR等を改行として正規化すると、既存検査をすり抜けるため生の改行を保つ。
        with report.open(newline="") as stream:
            result = check_verdict_line(stream.read())
        if result.status == "rejected":
            return f" / 判定行の受領不可: {result.reason}"
    except Exception:
        pass  # fail-open: import・読込み・検査の障害で終了通知や本文を失わせない
    return ""


if __name__ == "__main__":
    print(verdict_notice(Path(sys.argv[1]), Path(sys.argv[2])), end="")
