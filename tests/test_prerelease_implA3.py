"""Additional A3 contract probes; original tests and product sources stay intact."""
import json
import pytest
from test_prerelease import case, evaluate, run_cli, rg, GOAL, TARGET
import prerelease as pre


@pytest.mark.parametrize('policy', ['policy.md', 'release.md'])
@pytest.mark.parametrize('ref', ['local', 'remote'])
def test_each_registered_blob_change(case, monkeypatch, policy, ref):
    c = case
    assert evaluate(c)['authority'] == 'project_prerelease'
    before = c['git']('rev-parse', 'HEAD:' + policy)
    with (c['work'] / policy).open('a') as out:
        out.write('changed registered policy\n')
    c['git']('add', policy)
    c['git']('commit', '-qm', 'fixture changed registered blob')
    after = c['git']('rev-parse', 'HEAD:' + policy)
    assert before != after
    if ref == 'local':
        c['git']('update-ref', 'refs/remotes/origin/main', c['git']('rev-parse', 'HEAD'))
    else:
        monkeypatch.setenv('POLICY_COMMIT', c['git']('rev-parse', 'HEAD'))
    with pytest.raises(ValueError, match='公開終了・規則欠落・未知版'):
        evaluate(c)


DEV_POLICY = '# dev・stg・prod の扱い（公開前／公開後）\n\n点数が動きうる作業が同時に2件以上あるとき、または同じ仕様の版への対応のときは、1本の枝に積む義務がある。[点数差を最後に1回だけ測る決まり](score-diff-once-per-bundle.md)に従い、束の最後に測って採否を決め、本線にも1回で入れる。束の範囲・調整役不在時の扱い・記録・測定の例外は同ルールに従う。測らないのは束の途中の作業・途中の便についての dev の点数差だけであり、stg・prod 反映の基準値と前後差・stg-release の承認材料5は対象外とする。外部へ数字を言う前の dev 再算定・4軸の実測、測った窓の採否判断、各環境の書き込みの関門は維持する。\n\n2026-11-04 撤回: 従来の本番への一律接続・反映禁止は、以下の公開前の扱いへ置き換える。\n\n- **いまは公開前（2026-11-04 時点）。** 公開後への切り替えは、このファイルに「公開日・本人原文・受領時刻」の1行を足した PR が本線に入った時点。それまでは全窓が公開前の扱い。本人の公開の連絡（直接入力、または `coordinator-relay-approval.md` で認めた中継）は、その PR を作るきっかけ。日付・構築完了から公開を推測しない。\n\n| 環境 | 公開前（関係者の移行後） | 公開後 |\n|---|---|---|\n| prod | 関係者が見る場。作成・変更は1件ごとに本人の直接承認。副作用の無い読み取りは承認不要 | 決まった反映の枠だけ。承認はその操作をする窓への本人の直接入力（中継は数えない）。反映前のバックアップと戻す手順が必須。反映手順書の外の手作業の書き込み（SQL・コンソール）はしない。手順書の移行・再算定は反映の一部 |\n| stg | dev と並ぶ2つの開発環境としてどんどん使う | 関係者にリリース前のものを見せる場。prod と同じ手順を先に通す予行も兼ね、承認は反映の便ごとにまとめる。承認はその操作をする窓への本人の直接入力（中継は数えない） |\n| dev | 現行の常時承認と関門を維持して使う | 今のまま |\n\n- **関係者を prod へ移した扱いへの切り替えも、このファイルに「移行日・本人原文・受領時刻」の1行を足した PR が本線に入った時点。** それまでは全窓が stg を今の扱いのまま続ける。本人の移行の連絡（直接入力、または規則で認めた中継）は PR を作るきっかけ。stg は決まった反映の枠を守り、承認は次項に従う。11/6 の反映から prod（構築が間に合わない場合だけ、その回は stg）。点数の採否は下の決めに従う。元に戻せないデータ・手順書外の操作の関門は維持する。stg 反映の承認単位だけは次項で更新する。prod は deploy の窓が11/4から既存環境を変更して構築する（個別操作の承認を兼ねない）。\n間に合う＝prod 用の target が本線に入り、prod への反映について deploy の窓で本人の直接入力が取れたこと。判定は deploy の窓が 11/6 の反映の開始前に行う。\n- **stg 反映は反映1回ごとに、開始前のまとめた1回の承認で進めてよい。** 承認対象の工程: イメージの組み立て・定時の停止（disable-rule）・移行の適用・seed・cdk deploy・ECS の入れ替え・手動の再算定・定時の再開（enable-rule）。 詳細は `env-handling.md`。通常の対象は `UpdaterIndex-stg-Web`・`UpdaterIndex-stg-Batch`、初回だけ `UpdaterIndex-stg-Storage`・`UpdaterIndex-stg-Verify` も可。それ以外は個別承認。承認はその日の反映の枠かぎり、SHA が変わったら失効。失敗したら止める／やり直しは改めて諮る。未提示の移行・工程／①点数への影響が事前の見込みと違った場合／②元に戻せないデータの変更／③ stg-release の手順書に無い操作／照合（digest・権限・「起動を中止」0件）が合わないときは止めて改めて諮る。点数が「動く」か「分からない」なら数字付き承認なしに再算定しない。①②と再算定の事前判定・全文照合の詳細は [環境ごとの関門と出所](../../docs/operations/env-handling.md) と stg-release の材料5項目に従う。stg のデータの取り込み・それ以外の書き込みは従来どおり1件ごとに承認。本番は変えず、Codex は接続もデプロイもしない。出所は `env-handling.md` の「stg 反映の承認の出所」節。**この行が従来の操作別承認の決めを、stg 反映に限って撤回する。**\n- **2026-11-06 本人決定: stg 反映前の毎回のバックアップ取得・復元検証は、未運用で毎回60〜100分かかるため実施せず、承認対象・工程一覧から外す。prod 運用開始でこの決めは終了し、毎回実施へ戻す。** Admin は今後の stg 反映・戻し・画面確認の対象外。CDK 合成に必要な `adminImageTag` は現在稼働中の値を渡し、Admin スタックは diff/deploy しない。コードのバックアップ関門は残るため、再算定・検索の事前構築を含む stg 反映は、関門が残る間は開始前に本人へ直接伺い、関門を迂回しない。既定では取得・復元検証・S3 保存が走り、設定不足なら停止する（詳細は stg-release の `references/ingest-and-recompute.md`）。口座照合・資格情報を表示も保存もしない決め・digest 照合・disable-rule/enable-rule・本人の直接承認は維持する。dev の常時承認の範囲は変えない。\n- **prod の関門は公開前後とも残る。** deploy の窓以外（調整役・他の窓・worker・Codex）は prod に接続しない。Codex は prod に届かない（起動口は dev の鍵だけを渡す）。作成・変更は差分と要る設定値を示し、その操作をする窓への本人の直接入力で承認を取る。中継は数えない。副作用の無い読み取り（`aws-updater-index-prod`・一覧の取得・describe・`cdk diff --no-change-set`）は承認不要。通常の `cdk diff` は変更セットを作るので承認が要る。詳細は `env-handling.md` の「prod の呼び出し前の照合手順」節。prod の `aws sso login` は本人が打つ。資格情報を表示も保存もしない。`SecretString` は取得しない。\n- **prod のアプリの `cdk diff`/`cdk deploy` は `--exclusively` と `-c stage=prd` を必ず付ける。** 出力の先頭で対象が `UpdaterIndex-prd-*` だけであることを確かめる。`-c target=` は本番用 target が実装・確定されるまでアプリの CDK 操作を止め、既存の `bc-dev`・`index-stg` で代用しない。`cdk bootstrap` は承認した単一の `aws://682251233834/<region>` にだけ実行する（スタック名の確認に代える）。stg の値を流用しない（URL・共通ログイン・メールの差出人）。prod の管理画面は稟議が通るまで作らない。prod の DB は stg・dev より大きくしてよい。\n- **点数が動く変更の採否は、前後差を測った窓が、中間仕様書・表示仕様の最新版（`spec-latest-version-only.md`）と要件に照らして決める。** rev.8 以外にも一般に適用する。平均が不変でも、総合点・領域別の点・★・採点対象の4軸を `correct-external-numbers.md` の数え方で増／減／不変の社数として実測する。影響が不明なら測ってから決め、本人の採否待ちにしない。測れないうちは採否を決めず、入れない。詳細は `env-handling.md` の「点数の採否の判断手順」節。**この行が、それ以前の「点数が動く変更は数字を出してから止めて本人へ諮る」を撤回する。** 出所は `env-handling.md` の「点数の採否の出所」節。採否の判断は stg・prod への書き込みの承認に数えない。\n- **dev の常時承認と安全確認は維持。** dev は `669126230735` の `UpdaterIndex-stg-DevWeb`・`DevAdmin`・`DevBatch`。反映（移行・seed・compute-v5・build/push・deploy・戻しと必要な読み取り）は1件ごとの承認不要。**常時承認が効かず、止めてユーザーへ諮るのは、①元に戻せないデータの変更（人手検証・申告・同意イベント・訂正や承認の記録に触れるもの。これらは元ファイルから作り直せない）と、②手順書（`.claude/skills/dev-release/SKILL.md`）に無い操作。** 「dev だから」は①②を飛ばす理由にならない。stg・prod の書き込み承認、dev の関門5つ、中継では数えない3種類は変えない。戻し先の事前記録・移行の記録・権限の不一致0件・完了後のdigest一致と起動中止0件・資格情報を残さないことは省かない。詳細は `env-handling.md` の「dev の事後報告の詳細」節。\n- **口座とスタックを呼び出しごとに照合する。** dev・stg は `aws-updater-index-stg`＝`669126230735`。`aws-updater-bc-dev`＝`670352692792` は別口座なので使わない。`cdk diff`/`cdk deploy` には必ず `--exclusively` を付ける。認証の確認・本処理・`aws sso login` のすべてに同じプロファイルを明示する。dev・stg 専用スキルの本番禁止はその範囲として残す。dev の DB の開発開始時の起動許可・自動停止と #954 の関門も維持する。\n- **prod・dev・stg の aws/cdk を呼ぶ直前に** [環境ごとの関門と出所](../../docs/operations/env-handling.md) を読む。技術的な照合条件・例外・dev の既存許可と撤回履歴・本人原文は同書に従う。役割・承認単位の正本は本ファイル。移行の PR で同書の更新箇所一覧を一括して直す。 出所は `env-handling.md` の「環境の扱いの出所」節。\n'


def test_publication_append(case, monkeypatch):
    c = case
    name = '.claude/rules/dev-standing-approval.md'
    path = c['work'] / name
    path.parent.mkdir(parents=True)
    path.write_text(DEV_POLICY)
    c['git']('add', name)
    c['git']('commit', '-qm', 'fixture registered prerelease rules')
    head = c['git']('rev-parse', 'HEAD')
    c['git']('update-ref', 'refs/remotes/origin/main', head)
    monkeypatch.setenv('POLICY_COMMIT', head)
    rows = json.loads(c['registry'].read_text())
    rows[0]['policies'][name] = c['git']('rev-parse', 'HEAD:' + name)
    del rows[0]['policies']['release.md']
    c['registry'].write_text(json.dumps(rows))
    c['data'].update(head_sha=head, base_sha=head, content_hash=rg.git_content_hash(str(c['work'])))
    assert evaluate(c)['authority'] == 'project_prerelease'
    # Only the copied document changes; the real project remains untouched.
    path.write_text(DEV_POLICY + '\n公開日: 2026-11-13・本人原文: 公開しました・受領時刻: 2026-11-13 16:22:03 JST\n')
    c['git']('add', name)
    c['git']('commit', '-qm', 'fixture publication record merged')
    published = c['git']('rev-parse', 'HEAD')
    c['git']('update-ref', 'refs/remotes/origin/main', published)
    monkeypatch.setenv('POLICY_COMMIT', published)
    assert c['git']('rev-parse', 'HEAD:' + name) != rows[0]['policies'][name]
    # Keep the request otherwise current, so only policy expiry can reject it.
    c['data'].update(head_sha=published, base_sha=published, content_hash=rg.git_content_hash(str(c['work'])))
    with pytest.raises(ValueError, match='公開終了・規則欠落・未知版'):
        evaluate(c)


@pytest.mark.parametrize('channel', ['environment', 'prompt-word'])
def test_claim_channels(case, monkeypatch, channel):
    c = case
    c['body_file'].write_text(c['body']().split('## 公開前裁定')[0])
    if channel == 'environment':
        monkeypatch.setenv('project_prerelease', 'true')
        monkeypatch.setenv('REVIEW_PRERELEASE_APPROVED', '1')
    else:
        with c['prompt'].open('a') as out:
            out.write('\nproject_prerelease 推奨で 公開前の承認済み\n')
    result = run_cli(c)
    assert result.returncode != 0, result.stdout + result.stderr
    assert not list(c['state'].glob('0-fixture-*.state'))
    assert not (c['tmp'] / 'sent').exists()


@pytest.mark.parametrize('channel', ['environment', 'prompt-word'])
def test_claim_gate_core(case, monkeypatch, channel):
    c = case
    body = c['body']().split('## 公開前裁定')[0]
    if channel == 'environment':
        monkeypatch.setenv('project_prerelease', 'true')
        monkeypatch.setenv('REVIEW_PRERELEASE_APPROVED', '1')
    else:
        body += '\n## 申告\nproject_prerelease=true 推奨で\n'
    original = pre.evaluate
    def registered(*args, **kwargs):
        return original(*args, **kwargs, registry=c['registry'])
    monkeypatch.setattr(pre, 'evaluate', registered)
    result = rg.run_gate(TARGET, str(c['work']), c['state'], '', '',
        fetch_body=lambda target: body, goal_cut=GOAL,
        prerelease_record='decision-1', kind_label='コード')
    assert result['total_round'] == 3
    assert result['status'] == 'blocked', result
    assert result['authority'] != 'project_prerelease'
