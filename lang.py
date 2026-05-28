# -*- coding: utf-8 -*-
"""Language options and translation strings for RPG Decrypter.

Lite-rewrite notes:
    The decorative header (app_title / subtitle / quick_guide / key_note)
    and the dark-mode strings have been removed. Menu-bar items, worker
    count, and priority labels have been added.
"""

# =====================================================================
# 1. Language options
# =====================================================================
LANGUAGE_OPTIONS = {
    "ko": "한국어",
    "en": "English",
    "ja": "日本語",
    "zh": "中文",
}
LANGUAGE_CODES_BY_LABEL = {label: code for code, label in LANGUAGE_OPTIONS.items()}


# =====================================================================
# 2. Translation strings
# =====================================================================
TEXT = {
    "ko": {
        "window_title": "RPG Decrypter",

        # sections
        "section_game":   "게임 폴더",
        "section_output": "저장 폴더",
        "key_label":      "키",

        # menu bar
        "menu_language": "언어",
        "menu_mode":     "저장 대상",
        "target_both":   "이미지 + 오디오",
        "target_image":  "이미지 파일만",
        "target_audio":  "오디오 파일만",

        # checkbox
        "auto_open_label": "완료 후 폴더 자동 열기",

        # placeholders
        "input_placeholder":  "게임 폴더를 선택하세요",
        "output_placeholder": "복호화된 파일이 저장될 폴더",
        "key_placeholder":    "System.json에서 자동 추출되거나 직접 입력 (저장되지 않음)",

        # buttons
        "folder_button_game":   "선택",
        "folder_button_output": "선택",
        "key_show":             "표시",
        "key_hide":             "숨기기",
        "run_button":           "복호화 시작",
        "cancel_button":        "취소",
        "cancelling_button":    "취소 중...",

        # log header
        "log_header":              "LOG",
        "log_copy":                "복사",
        "log_clear":               "지우기",
        "log_clear_confirm_title": "확인",
        "log_clear_confirm_msg":   "로그를 모두 지우시겠습니까?",

        # right-click context menu (key entry)
        "ctx_cut":   "잘라내기",
        "ctx_copy":  "복사",
        "ctx_paste": "붙여넣기",

        # status label
        "scan_status":    "스캔 중...",
        "decrypt_status": "복호화 중  {processed}/{total} ({percent}%)  |  {eta}",
        "encrypt_status": "암호화 중  {processed}/{total} ({percent}%)  |  {eta}",
        "cancel_status":   "취소되었습니다.",
        "complete_status": "복호화가 완료되었습니다.",
        "encrypt_complete_status": "암호화가 완료되었습니다.",
        "unpack_complete_status": "아카이브 추출이 완료되었습니다.",
        "idle_status":     "대기 중",

        # ETA formatting
        "eta_seconds":  "{s}초",
        "eta_min_sec":  "{m}분 {s}초",
        "eta_hour_min": "{h}시간 {m}분",
        "eta_unknown":  "-",

        # dialogs
        "select_game_dialog":   "원본 게임 폴더 선택",
        "select_output_dialog": "결과물 저장 폴더 선택",
        "warning_title":        "경고",
        "error_title":          "오류",
        "done_title":           "완료",
        "done_success_msg":     "{count}개 파일이 모두 복호화되었습니다.",
        "done_failed_msg":      "{failed}개 파일 처리에 실패했습니다. 로그를 확인해 주세요.",
        "close_confirm_title":  "종료 확인",
        "close_confirm_msg":    "복호화 작업이 진행 중입니다.\n작업을 취소하고 종료하시겠습니까?",

        # validation
        "missing_fields":      "복호화 키, 원본 폴더, 결과물 저장 폴더를 모두 설정해 주세요.",
        "invalid_input_dir":   "원본 게임 폴더가 존재하지 않습니다.",
        "invalid_output_dir":  "결과물 저장 폴더가 존재하지 않습니다.",
        "same_dir":            "안전을 위해 입력 폴더와 출력 폴더는 다르게 설정해 주세요.",
        "output_inside_input": "안전을 위해 출력 폴더를 입력 폴더 내부로 설정하지 마세요.",
        "key_empty":           "복호화 키가 비어 있습니다.",
        "key_len":             "복호화 키는 32자리 HEX 문자열이어야 합니다.",
        "key_hex":             "복호화 키에 HEX가 아닌 문자가 포함되어 있습니다.",

        # config
        "config_loaded_fail": "[!] 설정 파일 읽기 실패: {error}",
        "config_saved_fail":  "[!] 설정 저장 실패: {error}",

        # key auto-detection
        "key_search_header":      "[*] System.json 자동 탐색 시작:",
        "key_search_path_check":  "    - 확인: {path}  ->  {status}",
        "status_not_found":       "파일 없음",
        "status_read_error":      "읽기 오류 ({error})",
        "status_key_missing":     "encryptionKey 필드 없음",
        "status_key_empty":       "encryptionKey 값이 비어 있음",
        "status_key_bad_length":  "encryptionKey 길이 오류 ({length}자, 32자 필요)",
        "status_key_non_hex":     "encryptionKey에 HEX가 아닌 문자 포함",
        "status_ok":              "유효한 키 발견",
        "key_found":              "[*] 복호화 키 자동 추출 성공: {key}",
        "key_search_failed":      "[!] System.json에서 유효한 키를 찾지 못했습니다.",
        "unencrypted_game":       "[i] 이 게임은 암호화되어 있지 않습니다. 복호화가 필요 없습니다.",
        "encrypted_no_key":       "[!] 암호화된 게임이지만 System.json에서 키를 찾지 못했습니다. 직접 입력해 주세요.",
        "not_rpg_folder_title":   "폴더 확인",
        "not_rpg_folder_msg":     "선택한 폴더가 RPG Maker 게임 폴더로 보이지 않습니다.\n(data, www, img, audio 등이 없음)\n\n그래도 진행하시겠습니까?",

        # menu changes
        "lang_changed": "[Lang] 언어가 한국어로 변경되었습니다.",
        "mode_changed": "[Cfg] 복호화 대상: {label}",

        # processing
        "start_log":           "[Start] 복호화 작업을 시작합니다.",
        "scan_log":            "[Scan] 입력 폴더를 탐색 중...",
        "count_log":           "[Info] 복호화 대상 파일 {total}개를 찾았습니다.",
        "progress_log":        "[Progress] 진행률 {percent}% ({processed}/{total})",
        "failed_files_header": "[Failed] 실패한 파일 목록:",
        "no_files":            "[!] 복호화 대상 파일이 없습니다. (.rpgmvp / .png_ / .rpgmvo / .ogg_ / .rpgmvm / .m4a_)",
        "cancel_log":          "[취소] 사용자가 복호화를 취소했습니다.",
        "plain_media_summary": "[Info] 암호화되지 않은 일반 미디어 파일 발견: PNG {png}개, OGG {ogg}개, M4A {m4a}개",
        "file_failed":         "[X]    실패: {path} / 이유: {reason}",
        "done_log":            "[Done] 작업 완료 - 성공 {success}개, 실패 {failed}개, 건너뜀 {skipped}개, 전체 {total}개",
        "done_all_success":    "[Done] 모든 대상 파일이 정상적으로 복호화되었습니다.",
        "done_some_failed":    "일부 파일 처리에 실패했습니다. 로그를 확인해 주세요.",

        # decrypt errors
        "bad_png":       "복호화 결과가 PNG 시그니처와 일치하지 않습니다. 키가 틀렸을 가능성이 큽니다.",
        "bad_ogg":       "복호화 결과가 OGG 시그니처와 일치하지 않습니다. 키가 틀렸을 가능성이 큽니다.",
        "bad_m4a":       "복호화 결과가 M4A 시그니처와 일치하지 않습니다. 키가 틀렸을 가능성이 큽니다.",
        "key_too_short": "복호화 키 바이트가 부족합니다. (내부 오류)",
        "unknown_error": "알 수 없는 오류",
        "io_error":      "I/O 오류: {error}",

        # misc
        "fatal_error": "[Fatal] 프로그램 실행 중 치명적인 오류가 발생했습니다: {error}",

        # new options & features
        "menu_task_mode":         "작업 모드",
        "task_mode_decrypt":      "복호화 (Decrypter)",
        "task_mode_encrypt":      "재암호화 (Encrypter)",
        "task_mode_unpack":       "구버전 추출 (Archive Unpacker)",
        "no_key_png_label":       "키 없이 이미지 강제 복원",
        "flatten_label":          "폴더 구조 평탄화 (단일 폴더 저장)",
        "no_key_png_status":      "키 없이 이미지 복원 모드로 시작합니다.",
        "encrypt_start_log":      "[Start] 재암호화 작업을 시작합니다.",
        "unpack_start_log":       "[Start] 구버전 아카이브 추출을 시작합니다.",
        "unpack_status":          "아카이브 추출 중... {processed}/{total}",
        "unpack_success_log":     "[Done] 아카이브 추출 완료 - {success}개 파일 성공",
        "key_recovered_log":      "[*] 이미지 파일로부터 암호화 키 역추출 성공: {key}",
        "key_recovery_fail_log":  "[!] 이미지 파일로부터 키를 추출하는 데 실패했습니다.",
        "output_folder_dropped":  "[i] 결과물 저장 폴더가 설정되었습니다: {path}",
    },

    "en": {
        "window_title": "RPG Decrypter",

        "section_game":   "Game Folder",
        "section_output": "Save Folder",
        "key_label":      "Key",

        "menu_language": "Language",
        "menu_mode":     "Save Target",
        "target_both":   "Images + Audio",
        "target_image":  "Images only",
        "target_audio":  "Audio only",

        "auto_open_label": "Open folder when done",

        "input_placeholder":  "Select the game folder",
        "output_placeholder": "Folder for the decrypted files",
        "key_placeholder":    "Auto-detected from System.json or entered manually (not saved)",

        "folder_button_game":   "Select",
        "folder_button_output": "Select",
        "key_show":             "Show",
        "key_hide":             "Hide",
        "run_button":           "Start Decryption",
        "cancel_button":        "Cancel",
        "cancelling_button":    "Cancelling...",

        "log_header":              "LOG",
        "log_copy":                "Copy",
        "log_clear":               "Clear",
        "log_clear_confirm_title": "Confirm",
        "log_clear_confirm_msg":   "Clear all log entries?",

        "ctx_cut":   "Cut",
        "ctx_copy":  "Copy",
        "ctx_paste": "Paste",

        "scan_status":    "Scanning...",
        "decrypt_status": "Decrypting  {processed}/{total} ({percent}%)  |  ETA {eta}",
        "encrypt_status": "Encrypting  {processed}/{total} ({percent}%)  |  ETA {eta}",
        "cancel_status":   "Cancelled.",
        "complete_status": "Decryption complete.",
        "encrypt_complete_status": "Encryption complete.",
        "unpack_complete_status": "Archive extraction complete.",
        "idle_status":     "Idle",

        "eta_seconds":  "{s}s",
        "eta_min_sec":  "{m}m {s}s",
        "eta_hour_min": "{h}h {m}m",
        "eta_unknown":  "-",

        "select_game_dialog":   "Select Source Game Folder",
        "select_output_dialog": "Select Output Folder",
        "warning_title":        "Warning",
        "error_title":          "Error",
        "done_title":           "Done",
        "done_success_msg":     "All {count} file(s) decrypted successfully.",
        "done_failed_msg":      "{failed} file(s) failed. Check the log for details.",
        "close_confirm_title":  "Close confirmation",
        "close_confirm_msg":    "Decryption is in progress.\nCancel the task and quit?",

        "missing_fields":      "Please set the decryption key, source folder, and output folder.",
        "invalid_input_dir":   "The source game folder does not exist.",
        "invalid_output_dir":  "The output folder does not exist.",
        "same_dir":            "For safety, the input and output folders should be different.",
        "output_inside_input": "For safety, the output folder should not be inside the input folder.",
        "key_empty":           "The decryption key is empty.",
        "key_len":             "The decryption key must be a 32-character HEX string.",
        "key_hex":             "The decryption key contains non-HEX characters.",

        "config_loaded_fail": "[!] Failed to read config file: {error}",
        "config_saved_fail":  "[!] Failed to save config: {error}",

        "key_search_header":      "[*] Auto-detecting System.json:",
        "key_search_path_check":  "    - check: {path}  ->  {status}",
        "status_not_found":       "not found",
        "status_read_error":      "read error ({error})",
        "status_key_missing":     "encryptionKey field missing",
        "status_key_empty":       "encryptionKey field is empty",
        "status_key_bad_length":  "encryptionKey has invalid length ({length} chars, expected 32)",
        "status_key_non_hex":     "encryptionKey contains non-HEX characters",
        "status_ok":              "valid key found",
        "key_found":              "[*] Decryption key auto-detected: {key}",
        "key_search_failed":      "[!] Could not find a valid key in any System.json.",
        "unencrypted_game":       "[i] This game is not encrypted - no decryption is needed.",
        "encrypted_no_key":       "[!] Encrypted game detected, but no key found in System.json. Please enter the key manually.",
        "not_rpg_folder_title":   "Confirm folder",
        "not_rpg_folder_msg":     "The selected folder does not look like an RPG Maker game folder.\n(no data, www, img, audio, etc.)\n\nProceed anyway?",

        "lang_changed": "[Lang] Language changed to English.",
        "mode_changed": "[Cfg] Target mode: {label}",

        "start_log":           "[Start] Starting decryption.",
        "scan_log":            "[Scan] Scanning input folder...",
        "count_log":           "[Info] Found {total} target file(s).",
        "progress_log":        "[Progress] {percent}% ({processed}/{total})",
        "failed_files_header": "[Failed] Failed file list:",
        "no_files":            "[!] No encrypted target files were found (.rpgmvp / .png_ / .rpgmvo / .ogg_ / .rpgmvm / .m4a_).",
        "cancel_log":          "[Cancelled] Decryption was cancelled by the user.",
        "plain_media_summary": "[Info] Normal unencrypted media found: PNG {png}, OGG {ogg}, M4A {m4a}",
        "file_failed":         "[X]    Failed: {path} / Reason: {reason}",
        "done_log":            "[Done] Completed - {success} succeeded, {failed} failed, {skipped} skipped, {total} total",
        "done_all_success":    "[Done] All target files were decrypted successfully.",
        "done_some_failed":    "Some files failed. Please check the log for details.",

        "bad_png":       "Decrypted output does not match the PNG signature. The key is likely wrong.",
        "bad_ogg":       "Decrypted output does not match the OGG signature. The key is likely wrong.",
        "bad_m4a":       "Decrypted output does not match the M4A signature. The key is likely wrong.",
        "key_too_short": "Decryption key bytes are too short. (internal error)",
        "unknown_error": "Unknown error",
        "io_error":      "I/O error: {error}",

        "fatal_error": "[Fatal] A critical error occurred: {error}",

        # new options & features
        "menu_task_mode":         "Task Mode",
        "task_mode_decrypt":      "Decrypt (Decrypter)",
        "task_mode_encrypt":      "Re-Encrypt (Encrypter)",
        "task_mode_unpack":       "Extract Archive (Archive Unpacker)",
        "no_key_png_label":       "Force restore PNGs without key",
        "flatten_label":          "Flatten folder structure",
        "no_key_png_status":      "Starting image restoration without key.",
        "encrypt_start_log":      "[Start] Starting re-encryption.",
        "unpack_start_log":       "[Start] Starting archive extraction.",
        "unpack_status":          "Extracting archive... {processed}/{total}",
        "unpack_success_log":     "[Done] Archive extraction completed - {success} files extracted",
        "key_recovered_log":      "[*] Encryption key recovered from image: {key}",
        "key_recovery_fail_log":  "[!] Failed to recover key from image.",
        "output_folder_dropped":  "[i] Output folder set to: {path}",
    },

    "ja": {
        "window_title": "RPG Decrypter",

        "section_game":   "ゲームフォルダー",
        "section_output": "保存フォルダー",
        "key_label":      "キー",

        "menu_language": "言語",
        "menu_mode":     "保存対象",
        "target_both":   "画像 + オーディオ",
        "target_image":  "画像ファイルのみ",
        "target_audio":  "オーディオのみ",

        "auto_open_label": "完了後にフォルダーを自動で開く",

        "input_placeholder":  "ゲームフォルダーを選択してください",
        "output_placeholder": "復号後のファイルを保存するフォルダー",
        "key_placeholder":    "System.json から自動取得、または手動入力(保存されません)",

        "folder_button_game":   "選択",
        "folder_button_output": "選択",
        "key_show":             "表示",
        "key_hide":             "非表示",
        "run_button":           "復号開始",
        "cancel_button":        "キャンセル",
        "cancelling_button":    "キャンセル中...",

        "log_header":              "LOG",
        "log_copy":                "コピー",
        "log_clear":               "クリア",
        "log_clear_confirm_title": "確認",
        "log_clear_confirm_msg":   "ログをすべて消去しますか?",

        "ctx_cut":   "切り取り",
        "ctx_copy":  "コピー",
        "ctx_paste": "貼り付け",

        "scan_status":    "スキャン中...",
        "decrypt_status": "復号中  {processed}/{total} ({percent}%)  |  残り {eta}",
        "encrypt_status": "暗号化中  {processed}/{total} ({percent}%)  |  残り {eta}",
        "cancel_status":   "キャンセルされました。",
        "complete_status": "復号完了。",
        "encrypt_complete_status": "暗号化完了。",
        "unpack_complete_status": "アーカイブ抽出が完了しました。",
        "idle_status":     "待機中",

        "eta_seconds":  "{s} 秒",
        "eta_min_sec":  "{m} 分 {s} 秒",
        "eta_hour_min": "{h} 時間 {m} 分",
        "eta_unknown":  "-",

        "select_game_dialog":   "元ゲームフォルダーを選択",
        "select_output_dialog": "出力フォルダーを選択",
        "warning_title":        "警告",
        "error_title":          "エラー",
        "done_title":           "完了",
        "done_success_msg":     "{count} 個のファイルをすべて正常に復号しました。",
        "done_failed_msg":      "{failed} 個のファイルが失敗しました。ログをご確認ください。",
        "close_confirm_title":  "終了確認",
        "close_confirm_msg":    "復号処理が進行中です。\nタスクをキャンセルして終了しますか?",

        "missing_fields":      "復号キー、元フォルダー、出力フォルダーをすべて設定してください。",
        "invalid_input_dir":   "元ゲームフォルダーが存在しません。",
        "invalid_output_dir":  "出力フォルダーが存在しません。",
        "same_dir":            "安全のため、入力フォルダーと出力フォルダーは別にしてください。",
        "output_inside_input": "安全のため、出力フォルダーを入力フォルダーの内側に置かないでください。",
        "key_empty":           "復号キーが空です。",
        "key_len":             "復号キーは 32 文字の HEX 文字列である必要があります。",
        "key_hex":             "復号キーに HEX 以外の文字が含まれています。",

        "config_loaded_fail": "[!] 設定ファイルの読み込みに失敗しました: {error}",
        "config_saved_fail":  "[!] 設定の保存に失敗しました: {error}",

        "key_search_header":      "[*] System.json の自動検出を開始:",
        "key_search_path_check":  "    - 確認: {path}  ->  {status}",
        "status_not_found":       "見つかりません",
        "status_read_error":      "読み込みエラー ({error})",
        "status_key_missing":     "encryptionKey フィールドがありません",
        "status_key_empty":       "encryptionKey が空です",
        "status_key_bad_length":  "encryptionKey の長さが不正です ({length} 文字、32 文字必要)",
        "status_key_non_hex":     "encryptionKey に HEX 以外の文字が含まれています",
        "status_ok":              "有効なキーを発見",
        "key_found":              "[*] 復号キーを自動取得しました: {key}",
        "key_search_failed":      "[!] 有効なキーを含む System.json が見つかりませんでした。",
        "unencrypted_game":       "[i] このゲームは暗号化されていません。復号は不要です。",
        "encrypted_no_key":       "[!] 暗号化ゲームですが System.json からキーを取得できませんでした。手動で入力してください。",
        "not_rpg_folder_title":   "フォルダー確認",
        "not_rpg_folder_msg":     "選択したフォルダーは RPG Maker ゲームフォルダーには見えません。\n(data, www, img, audio などがありません)\n\nそれでも続行しますか?",

        "lang_changed": "[Lang] 言語を日本語に変更しました。",
        "mode_changed": "[Cfg] 復号対象: {label}",

        "start_log":           "[Start] 復号処理を開始します。",
        "scan_log":            "[Scan] 入力フォルダーを走査中...",
        "count_log":           "[Info] 対象ファイルを {total} 個検出しました。",
        "progress_log":        "[Progress] 進行率 {percent}% ({processed}/{total})",
        "failed_files_header": "[Failed] 失敗したファイル一覧:",
        "no_files":            "[!] 対象ファイルがありません (.rpgmvp / .png_ / .rpgmvo / .ogg_ / .rpgmvm / .m4a_)。",
        "cancel_log":          "[Cancelled] ユーザーによって復号がキャンセルされました。",
        "plain_media_summary": "[Info] 暗号化されていない通常メディアを検出: PNG {png} 個、OGG {ogg} 個、M4A {m4a} 個",
        "file_failed":         "[X]    失敗: {path} / 理由: {reason}",
        "done_log":            "[Done] 完了 - 成功 {success} / 失敗 {failed} / スキップ {skipped} / 合計 {total}",
        "done_all_success":    "[Done] すべての対象ファイルを正常に復号しました。",
        "done_some_failed":    "一部のファイル処理に失敗しました。ログをご確認ください。",

        "bad_png":       "復号結果が PNG シグネチャと一致しません。キーが間違っている可能性が高いです。",
        "bad_ogg":       "復号結果が OGG シグネチャと一致しません。キーが間違っている可能性が高いです。",
        "bad_m4a":       "復号結果が M4A シグネチャと一致しません。キーが間違っている可能性が高いです。",
        "key_too_short": "復号キーのバイト数が不足しています。(内部エラー)",
        "unknown_error": "不明なエラー",
        "io_error":      "I/O エラー: {error}",

        "fatal_error": "[Fatal] 実行中に重大なエラーが発生しました: {error}",

        # new options & features
        "menu_task_mode":         "作業モード",
        "task_mode_decrypt":      "復号 (Decrypter)",
        "task_mode_encrypt":      "再暗号化 (Encrypter)",
        "task_mode_unpack":       "アーカイブ展開 (Archive Unpacker)",
        "no_key_png_label":       "キーなしで画像を強制復元",
        "flatten_label":          "フォルダ構造の平坦化",
        "no_key_png_status":      "キーなしの画像復元モードで開始します。",
        "encrypt_start_log":      "[Start] 再暗号化処理を開始します。",
        "unpack_start_log":       "[Start] アーカイブ展開処理を開始します。",
        "unpack_status":          "展開中... {processed}/{total}",
        "unpack_success_log":     "[Done] アーカイブ展開完了 - {success} 個のファイルを抽出",
        "key_recovered_log":      "[*] 画像ファイルからの暗号化キー逆抽出成功: {key}",
        "key_recovery_fail_log":  "[!] 画像ファイルからのキー抽出に失敗しました。",
        "output_folder_dropped":  "[i] 保存先フォルダが設定されました: {path}",
    },

    "zh": {
        "window_title": "RPG Decrypter",

        "section_game":   "游戏文件夹",
        "section_output": "保存文件夹",
        "key_label":      "密钥",

        "menu_language": "语言",
        "menu_mode":     "保存目标",
        "target_both":   "图像 + 音频",
        "target_image":  "仅图像",
        "target_audio":  "仅音频",

        "auto_open_label": "完成后自动打开文件夹",

        "input_placeholder":  "请选择游戏文件夹",
        "output_placeholder": "解密文件保存位置",
        "key_placeholder":    "从 System.json 自动提取或手动输入(不保存)",

        "folder_button_game":   "选择",
        "folder_button_output": "选择",
        "key_show":             "显示",
        "key_hide":             "隐藏",
        "run_button":           "开始解密",
        "cancel_button":        "取消",
        "cancelling_button":    "正在取消...",

        "log_header":              "LOG",
        "log_copy":                "复制",
        "log_clear":               "清除",
        "log_clear_confirm_title": "确认",
        "log_clear_confirm_msg":   "确定要清除全部日志吗?",

        "ctx_cut":   "剪切",
        "ctx_copy":  "复制",
        "ctx_paste": "粘贴",

        "scan_status":    "扫描中...",
        "decrypt_status": "解密中  {processed}/{total} ({percent}%)  |  剩余 {eta}",
        "encrypt_status": "加密中  {processed}/{total} ({percent}%)  |  剩余 {eta}",
        "cancel_status":   "已取消。",
        "complete_status": "解密完成。",
        "encrypt_complete_status": "加密完成。",
        "unpack_complete_status": "归档提取完成。",
        "idle_status":     "待机",

        "eta_seconds":  "{s} 秒",
        "eta_min_sec":  "{m} 分 {s} 秒",
        "eta_hour_min": "{h} 小时 {m} 分",
        "eta_unknown":  "-",

        "select_game_dialog":   "选择源游戏文件夹",
        "select_output_dialog": "选择输出文件夹",
        "warning_title":        "警告",
        "error_title":          "错误",
        "done_title":           "完成",
        "done_success_msg":     "已成功解密 {count} 个文件。",
        "done_failed_msg":      "{failed} 个文件处理失败。请查看日志。",
        "close_confirm_title":  "退出确认",
        "close_confirm_msg":    "解密任务正在进行中。\n是否取消任务并退出?",

        "missing_fields":      "请设置解密密钥、源文件夹和输出文件夹。",
        "invalid_input_dir":   "源游戏文件夹不存在。",
        "invalid_output_dir":  "输出文件夹不存在。",
        "same_dir":            "为安全起见,输入文件夹和输出文件夹应不同。",
        "output_inside_input": "为安全起见,输出文件夹不应位于输入文件夹内部。",
        "key_empty":           "解密密钥为空。",
        "key_len":             "解密密钥必须是 32 位 HEX 字符串。",
        "key_hex":             "解密密钥包含非 HEX 字符。",

        "config_loaded_fail": "[!] 读取配置文件失败: {error}",
        "config_saved_fail":  "[!] 保存配置失败: {error}",

        "key_search_header":      "[*] 开始自动检测 System.json:",
        "key_search_path_check":  "    - 检查: {path}  ->  {status}",
        "status_not_found":       "未找到",
        "status_read_error":      "读取错误 ({error})",
        "status_key_missing":     "缺少 encryptionKey 字段",
        "status_key_empty":       "encryptionKey 为空",
        "status_key_bad_length":  "encryptionKey 长度错误 ({length} 个字符,需要 32 个)",
        "status_key_non_hex":     "encryptionKey 包含非 HEX 字符",
        "status_ok":              "找到有效密钥",
        "key_found":              "[*] 已自动提取解密密钥: {key}",
        "key_search_failed":      "[!] 未在 System.json 中找到有效密钥。",
        "unencrypted_game":       "[i] 此游戏未加密,无需解密。",
        "encrypted_no_key":       "[!] 检测到加密游戏,但未在 System.json 中找到密钥。请手动输入。",
        "not_rpg_folder_title":   "确认文件夹",
        "not_rpg_folder_msg":     "所选文件夹看起来不像 RPG Maker 游戏文件夹。\n(没有 data、www、img、audio 等)\n\n仍要继续吗?",

        "lang_changed": "[Lang] 语言已更改为中文。",
        "mode_changed": "[Cfg] 解密对象: {label}",

        "start_log":           "[Start] 开始解密任务。",
        "scan_log":            "[Scan] 正在扫描输入文件夹...",
        "count_log":           "[Info] 找到 {total} 个目标文件。",
        "progress_log":        "[Progress] 进度 {percent}% ({processed}/{total})",
        "failed_files_header": "[Failed] 失败文件列表:",
        "no_files":            "[!] 未找到目标文件 (.rpgmvp / .png_ / .rpgmvo / .ogg_ / .rpgmvm / .m4a_)。",
        "cancel_log":          "[Cancelled] 用户已取消解密。",
        "plain_media_summary": "[Info] 检测到未加密的普通媒体文件: PNG {png} 个、OGG {ogg} 个、M4A {m4a} 个",
        "file_failed":         "[X]    失败: {path} / 原因: {reason}",
        "done_log":            "[Done] 任务完成 - 成功 {success} / 失败 {failed} / 跳过 {skipped} / 总计 {total}",
        "done_all_success":    "[Done] 所有目标文件已成功解密。",
        "done_some_failed":    "部分文件处理失败。请查看日志。",

        "bad_png":       "解密结果与 PNG 签名不匹配。密钥可能不正确。",
        "bad_ogg":       "解密结果与 OGG 签名不匹配。密钥可能不正确。",
        "bad_m4a":       "解密结果与 M4A 签名不匹配。密钥可能不正确。",
        "key_too_short": "解密密钥字节不足。(内部错误)",
        "unknown_error": "未知错误",
        "io_error":      "I/O 错误: {error}",

        "fatal_error": "[Fatal] 运行期间发生致命错误: {error}",

        # new options & features
        "menu_task_mode":         "工作模式",
        "task_mode_decrypt":      "解密 (Decrypter)",
        "task_mode_encrypt":      "重新加密 (Encrypter)",
        "task_mode_unpack":       "解包归档 (Archive Unpacker)",
        "no_key_png_label":       "无密钥强制恢复图像",
        "flatten_label":          "扁平化文件夹结构",
        "no_key_png_status":      "启动无密钥图像恢复模式。",
        "encrypt_start_log":      "[Start] 开始重新加密。",
        "unpack_start_log":       "[Start] 开始解包归档。",
        "unpack_status":          "正在解包归档... {processed}/{total}",
        "unpack_success_log":     "[Done] 归档解包完成 - 成功提取 {success} 个文件",
        "key_recovered_log":      "[*] 从图像文件成功恢复加密密钥: {key}",
        "key_recovery_fail_log":  "[!] 无法从图像中恢复密钥。",
        "output_folder_dropped":  "[i] 输出文件夹已设置为: {path}",
    },
}

# =====================================================================
# 3. Translation key validation
# =====================================================================
# Programmatically verify translation key completeness at import time
_all_keys = set(TEXT["ko"].keys())
for _lang in ("en", "ja", "zh"):
    _missing = _all_keys - set(TEXT[_lang].keys())
    if _missing:
        raise AssertionError(f"Language '{_lang}' is missing translation keys: {_missing}")
    _extra = set(TEXT[_lang].keys()) - _all_keys
    if _extra:
        raise AssertionError(f"Language '{_lang}' has extra translation keys: {_extra}")

