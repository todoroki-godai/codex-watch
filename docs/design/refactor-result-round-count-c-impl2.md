済: C §2.2 fallback・前置き/state/判定の共通値・旧特例経路を実装。
commit: 無し（指示どおり）。HEAD f5c9267ee2965d23593f86c61079221acb0ab6b3、変更を残した。
試験: python3 -m pytest tests -q、766成功・5skip・赤0。
変異: 陰性13赤・陽性2緑・生存0、差分/実行証跡/復旧hashを保存。
影響: OPEN33・現/新HEADとも新規停止0、通過3/4、前回6件は本線と同じ。
未実行: DB（対象外）、実対象の公開前特例。実発注/実台帳書込なし。
外部指定先はsandbox書込許可外のため、このファイルを転記用に作成。
次候補: 依頼元が差分をcommit。詳報 docs/design/round-count-c-REPORT.md。
