"""Deterministic review admission; existing state/report are the only ledger."""
import json
import os
from pathlib import Path
import re

from round_gate import (Indeterminate, Target, check_receipt, gh_fetch_body,
                        normalize_workdir, parse_target, parse_predecessor_env,
                        parse_inherited_pr_numbers, MAX_CHAIN_DEPTH)

FIELDS = ('守る対象', '信頼境界', '対象外', '止める欠陥の定義', '確かめ方', '追加変更', '修正した族')
FAMILIES = frozenset('ABCD')
RESULT_INSTRUCTION = 'review_findings= の直後にJSON配列を1行で書く。各指摘は {"severity":"Must|Should|Nit","family":"A|B|C|D"}、0件は []。族: A=根拠/状態/保護 B=入力/境界/接続 C=検出力/検査データ D=範囲/決定/巡管理。小分類は禁止。'


def require(condition, reason):
    if not condition:
        raise Indeterminate('受付拒否: ' + reason)


def sections(text):
    """Only real ATX headings outside fenced blocks define admission fields."""
    result, current, fence = {}, None, None
    for line in text.splitlines():
        mark = re.match(r'^ {0,3}(`{3,}|~{3,})', line)
        if mark:
            token = mark[1]
            if fence is None:
                fence = token
            elif token[0] == fence[0] and len(token) >= len(fence) and not line[mark.end():].strip():
                fence = None
            continue
        if fence:
            continue
        heading = re.match(r'^ {0,3}(#{1,6})\s+(.*?)\s*$', line)
        if heading:
            current = None
            if heading[1] == '##' and heading[2] in FIELDS:
                current = heading[2]
                require(current not in result, '欄が重複: ' + current)
                result[current] = []
        elif current:
            result[current].append(line)
    require(all(name in result and ''.join(result[name]).strip() for name in FIELDS), '完成条件5欄・追加変更・修正した族を非空で各1つ指定してください')
    return {name: '\n'.join(lines).strip() for name, lines in result.items()}


def families(raw):
    if raw == 'なし':
        return set()
    tags = raw.split(',')
    require(bool(tags) and all(tag in FAMILIES for tag in tags) and len(set(tags)) == len(tags), '族は A,B,C,D の重複しない一覧か「なし」にしてください')
    return set(tags)


def strict_state(path):
    text = path.read_text()
    result = {}
    for line in text.splitlines():
        key, sep, value = line.partition('=')
        require(bool(sep) and key not in result, '状態ファイルの破損・重複キー: ' + path.name)
        result[key] = value
    require(all(result.get(k) for k in ('run_id', 'workdir', 'started_at')), '状態ファイルの識別情報不足: ' + path.name)
    # Implementation runs share this directory; only review entries have review_target.
    return result


def report_families(d):
    text = Path(d['report']).read_text()
    receipt = check_receipt(d.get('head_sha', ''), d.get('content_hash', ''), text)
    require(receipt.status == 'ok', '前巡の受領照合が不成立')
    lines = [line[len('review_findings='):] for line in text.splitlines() if line.startswith('review_findings=')]
    require(len(lines) == 1, '前巡の指摘一覧が欠落・重複')
    def unique(pairs):
        out = {}
        for key, value in pairs:
            require(key not in out, '前巡JSONの重複キー')
            out[key] = value
        return out
    items = json.loads(lines[0], object_pairs_hook=unique)
    require(isinstance(items, list), '前巡の指摘一覧は配列が必要')
    for item in items:
        require(isinstance(item, dict) and set(item) == {'severity', 'family'} and
                item['severity'] in ('Must', 'Should', 'Nit') and item['family'] in FAMILIES,
                '前巡の重要度・族が不正')
    return len(items), {item['family'] for item in items}


def check(prompt, workdir, state_dir, target_raw, predecessor_raw='', fetch_body=gh_fetch_body):
    """Unknown history is a refusal, never a new first round."""
    try:
        fields = sections(Path(prompt).read_text())
        repairs = families(fields['修正した族'])
        addition = fields['追加変更']
        require(addition == 'なし' or bool(re.fullmatch(r'あり: \S[^\n]*', addition)), '追加変更は「なし」か「あり: 内容と理由」の1行が必要')
        keys, expected = set(), {}
        def visit(target, visiting, depth):
            key = target.key()
            require(key not in visiting and depth <= MAX_CHAIN_DEPTH, '前身の循環・深さ超過')
            if key in keys:
                return
            keys.add(key)
            body = fetch_body(target)
            rows = [int(n) for n in re.findall(r'^\|\s*(\d+)\s*\|\s*(?:設計|コード)\s*\|', body, re.MULTILINE)]
            expected[key] = max(rows, default=0)
            for number in parse_inherited_pr_numbers(body):
                visit(Target('pr', target.owner, target.repo, number), visiting | {key}, depth + 1)
        if target_raw.startswith(('pr:', 'issue:')):
            visit(parse_target(target_raw), set(), 0)
        for pred in parse_predecessor_env(predecessor_raw):
            visit(pred, set(), 0)
        entries = []
        folder = Path(state_dir)
        require(folder.is_dir(), '状態ディレクトリを読めません')
        # iterdir surfaces permissions errors instead of treating unreadable directories as empty.
        for path in folder.iterdir():
            if path.suffix != '.state':
                continue
            d = strict_state(path)
            if 'review_target' not in d:
                continue
            if d['review_target'] in keys or normalize_workdir(d['workdir']) == normalize_workdir(workdir):
                stamp = int(d['started_at'])
                entries.append((stamp, d['run_id'], d))
        require(len({stamp for stamp, _, _ in entries}) == len(entries), '前巡の開始時刻が同秒で順序を特定できません')
        entries.sort(key=lambda item: item[:2])
        for key, rounds in expected.items():
            matching = [d for _, _, d in entries if d['review_target'] == key]
            require(rounds == 0 or any(int(d.get('round', '0')) >= rounds for d in matching),
                    '本文に巡があるのに対応するローカル前巡記録がありません')
        inherited_keys = keys - {target_raw}
        for key in inherited_keys:
            require(any(d['review_target'] == key for _, _, d in entries), '前身のローカル記録がありません')
        if entries:
            previous = entries[-1][2]
            pid = int(previous['pid'])
            require(pid > 0, '前巡のPIDが不正')
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                pass
            else:
                require(False, '前巡が実行中または終了未確認です')
            families(previous['repair_families'])
            count, found = report_families(previous)
            require(count != 0 or addition.startswith('あり: '), '前巡0件: 追加変更の内容と理由が必要')
            require(found <= repairs, '前巡の指摘族を修正した族に全て記録してください')
            if len(entries) >= 2:
                first = families(entries[-2][2]['repair_families'])
                second = families(previous['repair_families'])
                require(not (first & second), '同じ族の修正が2巡連続: 追加発注を停止します')
        return ','.join(sorted(repairs)) or 'なし'
    except Indeterminate:
        raise
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, OverflowError, RecursionError) as exc:
        raise Indeterminate('受付拒否: 前巡または依頼文を判定できません (' + type(exc).__name__ + ')') from exc
