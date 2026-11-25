"""Resolve a launcher model before dispatch and validate Astra's launch reason."""

import json
import os
import re
import sys

from round_gate import is_single_line

ASTRA_MODEL = re.compile(r"gpt-\d+(?:\.\d+)*-astra(?:[-_.][a-z0-9]+)*")


def valid_model(model):
    return (isinstance(model, str) and bool(model.strip()) and is_single_line(model)
            and "\0" not in model and not model.startswith("-"))


def astra_reason(model, raw, kind="", gate_json="", must_only="no"):
    if not ASTRA_MODEL.fullmatch(model.strip().casefold()):
        return ""
    if must_only == "yes":
        raise ValueError("Must 解消だけを確認する巡には Astra を使えません")
    reason = raw.strip()
    basis = reason[1:].lstrip(" :：\t\u3000")
    if (not is_single_line(raw) or not reason or reason[0] not in "①②③"
            or not any(char.isalpha() for char in basis)):
        raise ValueError("Astra には CODEX_ASTRA_REASON に ①〜③ と具体的な根拠を1行で指定してください")
    if reason[0] == "①":
        # The prompt's fallback round 1 is not evidence (e.g. none: or bypass).
        round_number = json.loads(gate_json).get("total_round") if gate_json else None
        if kind != "設計" or type(round_number) is not int or round_number != 1:
            raise ValueError("Astra の理由①は、巡数ゲートで設計巡1が確認できたレビューに限ります")
    return reason


def model_reason(model, raw):
    if model == "gpt-6-luna":
        return ""
    try:
        raw.encode("utf-8")
    except UnicodeEncodeError:
        return None
    if not raw.strip() or not is_single_line(raw):
        return None
    return raw.strip()


def main():
    workdir, model, model_option, *review = sys.argv[1:]
    if not model.strip():
        print(f"拒否: モデルの指定がありません。{model_option} を付けて起動し直してください。", file=sys.stderr)
        if model_option == "CODEX_REVIEW_MODEL":
            print("通常は gpt-6.2-sol、全体の設計・レビューの繰り返し・設計し直しは "
                  "astra（理由の指定が必要）を使用してください。", file=sys.stderr)
        else:
            print("判断の要らない機械作業は gpt-6-luna、通常は gpt-6.1-terra、大事な場面・難しい作業は gpt-6.2-sol、", file=sys.stderr)
            print("全体の設計・設計し直しは astra（理由の指定が必要）を使用してください。", file=sys.stderr)
        return 2
    if not valid_model(model):
        print(f"拒否: {model_option} には有効なモデル名を1行で指定してください。", file=sys.stderr)
        return 2
    try:
        reason = astra_reason(model, os.environ.get("CODEX_ASTRA_REASON", ""), *review)
    except ValueError as error:
        print(f"拒否: {error}", file=sys.stderr)
        return 2
    if model_option == "CODEX_IMPL_MODEL":
        try:
            extra_reason = model_reason(model, os.environ.get("CODEX_MODEL_REASON", ""))
        except Exception:
            print("警告: CODEX_MODEL_REASON の確認に失敗したため起動を続けます。", file=sys.stderr)
            extra_reason = ""
        if extra_reason is None:
            print("拒否: luna 以外を使うときは CODEX_MODEL_REASON に luna で足りない理由を1行書いてください（例: CODEX_MODEL_REASON='設計の判断が要る'）。判断の要らない機械作業は gpt-6-luna。", file=sys.stderr)
            return 2
    # Review retains its two-line protocol; impl adds the reason as line three.
    print(reason)
    print(model)
    if model_option == "CODEX_IMPL_MODEL":
        print(extra_reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
