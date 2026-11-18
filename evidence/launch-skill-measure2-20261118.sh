#!/bin/zsh
set -u
W=/Users/matsukaze-takashi/matsukaze-utils/codex-watch/_wt.noindex/launch-skill-allowlist
for mode in default off; do for n in 1 2 3; do
  if [[ $mode == off ]]; then extra=(CODEX_SKILLS_FILTER=off); else extra=(); fi
  out=$( cd $W && env -u CODEX_SKILLS_FILTER -u CODEX_SKILLS_ALLOW -u CODEX_MEMORIES -u CODEX_REVIEW_ALLOW_SKILLS -u CODEX_REVIEW_GATE_CHECK -u REVIEW_TARGET CODEX_SUMMARY='#65 起動の重さの測定' CODEX_REVIEW_KIND_LABEL=コード CODEX_REVIEW_NO_GATE=初回入力の比較 "${extra[@]}" bin/codex-review $W /private/tmp/claude-501/-Users-matsukaze-takashi-matsukaze-utils-harness-nudge/aaf0f9cd-841e-41ef-9a68-0868e2a4c488/scratchpad/measure-prompt.md skill-measure2-$mode-$n 2>&1 )
  id=$(print -r -- "$out" | tail -1)
  ~/matsukaze-utils/codex-watch/bin/codex-watch "$id" >/dev/null 2>&1
  sid=$(awk '/^session id:/{print $NF;exit}' ~/.codex-watch/$id.log)
  f=$(find ~/.codex/sessions -name "*$sid.jsonl" | head -1)
  tok=$( [[ -n $sid && -n $f ]] && grep -o '"input_tokens":[0-9]*' "$f" | head -1 | cut -d: -f2 )
  print -r -- "$mode	$n	$id	sid=$sid	input=$tok	$(print -r -- "$out" | grep -v '^routing' | head -2 | tr '\n' ' ')	$(date '+%H:%M:%S')"
  touch ~/.codex-watch/$id.ack
done; done
