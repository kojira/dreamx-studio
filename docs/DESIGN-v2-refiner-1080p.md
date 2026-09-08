# v2：動画アップロード → 1080p高解像度化（詳細設計案）

**進行指示受領。** この案を提示した後、ユーザーから「私の判断待たないでください」と指示を受けたため、提示済み本案の範囲で実装・検証へ進める。通常の内部実装判断で確認待ちにしない。安全方針の変更・破壊的操作・PR作成/マージは既存の個別ゲートを維持する。Issue #1の単体Refiner要件に対応する。Refiner動作確認を先に行うというユーザー指示は完了したため、次にブラウザ機能を設計する。

## 利用目的に関する最新フィードバック

ユーザーは生成結果をクローン用途には不適と評価し、本来は口を閉じたまま発話させないことを望んでいたと明示した。この要件は満たしていない。本案は手持ち動画の高解像度化という別機能であり、閉口制御・発話除去・本人性の補正を実現する設計ではない。Refiner試験の技術的成功をクローン用途の受入へ流用しない。この区別は実装・検証後も維持する。

## 1. 実証済みと未実証

成功条件：1248×704、69フレーム/24fps、音声付き入力から1920×1080、69フレーム、元音声一致の出力。総267秒、最小空き17.724GiB。これは全動画・長尺への性能保証ではない。2倍の2496×1408処理は実空き8GiBを下回り未完了。

初版は**短尺・横動画・1080p固定**の試用機能。上限3秒、出力24fps。長尺・縦動画・2K・バッチ処理は別検証後の拡張とし、初版で対応済みと表示しない。3秒上限も下記の実機受入を通過するまで有効化しない。今回確認済みの2.875秒動画のみを根拠に上限全域の動作を保証しない。

## 2. 画面責務

既存画面に「画像から生成」「動画を1080p化」の切り替えを追加。既存生成の220/440/880選択は変更しない。

Refiner画面：
- MP4選択、元動画プレビュー、ファイルサイズ・解像度・時間・fpsの検証結果。
- 対応範囲を選択前から表示：「横動画・3秒以内・720p以下、出力1080p/24fps」。
- 出力固定1920×1080。追加プロンプト、自由解像度、seed、品質高速化の設定欄は設けない。
- 「高解像度化」ボタン。未検証/アップロード中/サーバー未準備/他ジョブ実行中は無効。押下後は入力と設定を固定。
- 準備→高解像度化→動画デコード→音声結合/出力確認→完了を表示。実測ログにない進捗率や残り時間を創作しない。
- 完了時に入力と出力を別々に再生、MP4ダウンロード。元動画を上書きしない。画質・顔の改善は保証しないと明記。
- 処理中はキャンセルを提供。タブ切替/再読み込みでジョブを失わず、履歴から復帰できる。
- 履歴に処理種別を表示。既存のoperator_testジョブもRefiner試験と表示し、画像生成と誤表示しない。

## 3. 入力契約・検証・前処理

初版の許可入力：実コンテナがMP4、映像1本/H264/yuv420p、音声0または1本/AAC（1～2ch、48kHz以下）。画像寸法は幅256～1280、高さ144～720、SAR1、回転なし、横比率16:9から±1%以内。表示上の拡張子/MIMEだけでは判定しない。

時間0.25～3.0秒、実フレームをデコードできること、CFRで1～60fps。VFR・破損・外部参照・複数映像・字幕/添付・対応外codec/方向は理由付き422。入力100MiBまで。これらは初版の明示した対応範囲であり、黙って切り捨てない。

前処理でfps24、時刻原点0、SAR1のMP4に正規化する。フレーム数Nは正規化後に数えて6～72、時間の差は原動画比1/24秒以内。差が大きければ失敗。もともと24fpsの場合は全フレームを維持。音声AACは再圧縮せず保持する。音声開始が映像開始から1/24秒以上ずれる、または音声終了が映像終了より1/24秒を超えて長い入力はUNSUPPORTED_AUDIO_TIMINGで拒否し、黙って切らない。短い音声は許可し、映像末尾を保持する。元のfpsと出力24fpsを画面に併記する。

VAEの4n+1制約には、N以上の最小値P=4*ceil((N-1)/4)+1を明示指定し、末尾を最大3フレームだけ処理用に複製する。Refiner出力後にP-Nの追加分のみ除去し、元のNフレームは削除しない。実装確認：固定上流は読み込み直後のNを`T_pixel`に保持し、テンソルをPへpaddingした後、書き出し前に`video_out[:T_pixel]`で追加分を既に除去する。このため中間MP4もN枚を検証し、さらにP-N枚を二重に除去しない。--num_frames=-1による切り下げは使わない。

入力をFFmpegへ渡す検証/正規化は、ネットワークなし・非root・CPU2・RAM2GiB・pids128・最大60秒の専用CPUコンテナで実施。入力ファイルと当該作業ディレクトリのみマウント、Docker socketや他入力を渡さない。メタデータ寸法/時間確認後に全フレーム検証する。タイムアウト/強制終了を成功扱いにしない。

## 4. APIと永続化

既存自動ローカルセッション、Origin検証、変更系CSRFを全APIに適用。公開URL、ユーザー任意のパス/コマンド/モデル名は受け取らない。ローカル信頼境界は既存と同じで、ユーザー別の秘密保管サービスとは称さない。

- `POST /api/video-inputs`：Content-Type application/octet-stream、本文はMP4バイト。100MiBの実受信上限、Content-Length不明もストリームで計数。メモリへ全体を溜めず新規UUIDファイルへ書く。成功201 `{input_id, width, height, duration_seconds, source_fps, normalized_fps:24, normalized_frames, has_audio}`。rawを受領後に隔離検証を実行し、検証完了まで画面は「検証中」。切断/上限超過は当該未完了ファイルだけを後述規則で扱う。
- `GET /api/video-inputs/{id}/preview`：検証済み正規化MP4のみ。UUID→固定ディレクトリ、symlink拒否。未検証は409、未知は404。
- `POST /api/refiner-jobs`：JSON `{input_id}` のみ、未知キー拒否。Idempotency-Key必須1～128文字。固定recipe `refiner1080-v2`、seed42。成功202 `{job_id,state}`。同キー同内容は稼働中でも元ジョブを返し、別内容は409。
- 既存 `/api/jobs`、詳細、cancel、artifacts/mp4 を共用。一覧/詳細に `kind: generate|refine|operator_test` と、該当時 `output_size` を追加。旧payloadでkind省略はgenerate。ただしoperator_testフィールドを持つ旧試験はoperator_test。既存生成の旧クライアント互換を保つ。
- Refinerに音声がなければ正常な無音動画として成功。artifact一覧を詳細レスポンスに追加し、存在しないwav/first_frameをリンクしない。元の生成では従来の成果物を維持。

SQLiteにvideo_inputs表（id、state、created_at、width、height、duration、source_fps、normalized_frames、has_audio、raw_sha256、normalized_sha256）を追加。既存jobsのJSONpayloadにkind、input_id、recipe、seed、frames、has_audioを保存。ジョブ作成後は不変。旧DBを破壊せず追加migrationをトランザクションで行う。

入力/処理成果物はprivateなUUID配下に保存し、ファイル名をユーザー由来の文字列にしない。元データの自動期限削除/全体pruneは追加しない。リクエスト失敗時に削除できるのは、そのリクエストが排他的に新規作成した未完了tempのみ。既存ファイルや別ジョブは触らない。

## 5. 排他・runner・権限

operator専用テストの別supervisor方式は製品経路に流用しない。**既存host_runnerにrefine分岐を追加して、UIキャンセルとactive状態を一元管理する。** source videoやrecipeはAPIで検証したIDからhost側で再解決し、任意argvはUNIX socketからも受け付けない。

動画検証もGPUジョブと共通の排他を使用し、重いCPU検証を推論と競合させない。小さなoperations表による単一leaseを設け、host runnerがvalidate_video/generate/refineの全実行で取得・解放する。ジョブDBの既存one_active制約も維持。APIのstatus先読みだけで排他を保証しない。取得はSQLite BEGIN IMMEDIATEで原子的に行う。生成/refineではjobs作成とlease取得を同一transactionにし、runner.submitはそのleaseの所有者を照合して開始する（submit時に取り直さない）。競合時はjob行を作らず409。validate_videoはCPU検証直前に同じleaseを取得する。

validate_video socket要求はinput UUIDだけ。予約済みtemp入力のパスをhost側で構築。API uploadはrunner BUSY時には本文を読む前に409、検証予約時の競合も409。当該tempだけを取り消す。受信は120秒、CPU検証は60秒を上限とする。ジョブ作成前の「取消」はアップロード接続を中断する操作と明記する。検証開始後に接続が切れた場合はhostへ当該input_idの検証中止要求を送り、停止確認までleaseは保持する。中止要求が届かなくても検証は60秒で終了し、未送達結果を誤ってGPU実行しない。ページ表示には「動画検証中」もbusyとして返す。

leaseにkind/job_idまたはinput_id/container_id/startを持たせる。期限だけでleaseを解除しない。再起動時は対象containerの停止を確認してから、実行中ジョブをinterrupted、入力検証をfailedにし解放する。停止未確認はbusyのまま管理者対応。

## 6. Refiner実行と状態遷移

`admitted → preparing → generating → muxing → succeeded`。既存状態名を増やさずprogress.phaseで段階を区別する。preparingは入力照合/フレーム正規化/モデルロード、generatingはrefining/decoding、muxingは追加フレーム除去・1080p整形・音声/成果物検証。

固定内部サイズ1920×1088。標準FlashLatentUpsamplerは2x学習済みなので、公式処理がLRを960×544へ調整する。任意倍率学習モデルとは説明しない。BF16、Triton window attention、KV9、sigma0.6251、seed42、成功した試験と同じ固定prompt。FP8/LightVAE/mmapは使わない。試験済みのSDPA条件修正とaudio mux -shortest撤去を、元ファイルhash検証付きでRefiner専用イメージに含める。生成モデル用イメージ/依存は変えない。

最終映像は原入力w,hからs=min(1920/w,1080/h)、W=2*floor(w*s/2)、H=2*floor(h*s/2)を求め、W×HへLanczos整形して1920×1080へ中央黒余白を付ける。奇数余白位置はyuv420pの偶数座標へ切り下げ、左右/上下最大2px差を許容する。切り抜かない。SAR1、H264/CRF18/fast/yuv420p。上流がP-Nだけ除去済みのNフレームを検証し、最終整形でもNを保持する。元音声を再圧縮せず結合、-shortest禁止。音声がない入力も扱う。video/audioの時刻原点を0とし、動画時間を短い音声に合わせない。

キャンセルは準備/推論/後処理を含む正確なworkerプロセス群へTERM、5秒後まだ実行中ならKILL。FFmpeg後処理も同じworker/監視範囲に含め、host上の監視対象外子プロセスとして残さない。停止確認後だけcancelled/lease解放。完了済みcancelは200で状態を返す。成功判定後に届いたcancelで成功動画を消さない。

## 7. 安全・進捗・エラー

現在のユーザー指定を維持：実MemAvailable<8GiB、100ms監視、Docker RAM上限なし、worker swap0をロード前設定/検証し監視、heartbeat2秒、180分上限、admission96GiB/空きdisk150GiB、同時1件。新たな72/80/112GiB停止は設けない。他の停止済みサービスは再起動しない。

statusは現在kind、busy理由、実空きRAMを返す。進捗はRefinerのチャンク完了ログを読み `completed_chunks/total_chunks` を表示。100%チャンク完了をジョブ完了と同一視せず、その後は「デコード/保存中」。観測が10秒以上更新されない場合は更新待ちとし、過去の完了数を消さない。経過時間は開始時刻から算出し、未計測ETAを表示しない。

主要エラー：413 UPLOAD_TOO_LARGE、422 INVALID_VIDEO/UNSUPPORTED_VIDEO/INVALID_DURATION、409 BUSY/IDEMPOTENCY_CONFLICT、503 RUNNER_NOT_READY/INSUFFICIENT_MEMORY/INSUFFICIENT_DISK。実行エラーはHOST_MEMORY_GUARD、SWAP_POLICY_LOST、GUARDIAN_LOST、RUNNER_HEARTBEAT_LOST、TIME_LIMIT、INFERENCE_FAILED、OUTPUT_VALIDATION_FAILED、STOP_UNCONFIRMEDを区別。利用者表示は日本語説明＋コード。stderrやprivateパスをレスポンスへ露出しない。自動再試行なし。

## 8. 変更範囲・受入

対象：API/入力検証モジュール、追加migration/lease、runner socketクライアント・host_runner、Refiner worker/専用Dockerfile・固定patch、progress collector、React画面、テスト/運用手順。host driver、既存モデル値、既存画像生成パラメータ、ネットワーク公開範囲は変更しない。

受入：
1. CPU単体/API：破損/長さ/fps/codec/容量超過拒否、CSRF/Origin、パス・symlink拒否、chunked upload、切断、冪等性、検証と生成/refineの競合、旧生成DB/API互換。
2. フレーム：N=6/24/68/69/72のpadding計算と出力N保持。音声あり/なし、音声が映像より僅かに短い場合、24fps入力のフレーム不変。
3. 安全：合成センサーで8GiB境界、swap/heartbeat喪失、キャンセル各段階、再起動/停止未確認lease保持。危険な実RAM枯渇実験は禁止。
4. 実機：既存成功69frameケースのUI経由再現、および公開可能な合成3秒/720p/30fps→24fpsケース。両方で正確な1920×1080と音声/長さ、ログ/GPU/最小空き/時間を確認。上限試験が失敗したら対応範囲を勝手に狭めたり保護を緩めず設計へ戻る。
5. モバイル/PCでアップロード、検証状態、進捗、cancel、再読込/履歴復帰、プレビュー/保存。ユーザーの画質評価を得る。

実装対象はこのv2設計。上記の進行指示を記録したcommitを基点に実装ブランチを作る。配備確認は対象commit/環境/操作を提示し、PR作成とマージはそれぞれ別の明示OKを得る。
