# -*- coding: utf-8 -*-
"""Language options and translation table for RPG Decrypter."""

# =====================================================================
# 8. Language options
# =====================================================================
LANGUAGE_OPTIONS = {
    "ko": "한국어",
    "en": "English",
    "ja": "日本語",
}
LANGUAGE_CODES_BY_LABEL = {label: code for code, label in LANGUAGE_OPTIONS.items()}


# =====================================================================
# 9. Translation strings
#
#    Terminology notes
#      KO: uses "복호화"  (decryption / decrypt)
#      EN: uses "decryption / decrypt"
#      JA: uses "復号"   (no -化 suffix — modern standard usage)
# =====================================================================
TEXT = {
    "ko": {
        # window / header
        "window_title": "RPG Decrypter",
        "app_title":    "RPG Decrypter",
        "app_subtitle": "RPG Maker MV/MZ 암호화 미디어 에셋을 복호화 합니다",

        # sections
        "settings_section": "00  설정",
        "section_game":     "01  원본 게임 폴더",
        "section_output":   "02  결과물 저장 폴더",

        # settings
        "appearance_label": "화면 모드",
        "language_label":   "언어",
        "dark_mode":        "다크 모드",
        "target_label":     "복호화 대상",
        "target_both":      "이미지 + 오디오",
        "target_image":     "이미지 파일만",
        "target_audio":     "오디오 파일만",

        # fields
        "input_placeholder":  "게임 폴더를 선택하세요",
        "output_placeholder": "복호화된 파일이 저장될 폴더",
        "key_label":          "복호화 키",
        "key_placeholder":    "System.json에서 자동 추출되거나 직접 입력 (저장되지 않음)",

        # buttons
        "folder_button":     "폴더 선택",
        "save_button":       "설정 저장",
        "run_button":        "  ▶  복호화 시작",
        "searching_button":  "탐색 중…",
        "progress_button":   "처리 중…  {processed} / {total}  ({percent}%)",

        # log header
        "log_header": "● LOG",

        # dialogs
        "select_game_dialog":   "원본 게임 폴더 선택",
        "select_output_dialog": "결과물 저장 폴더 선택",
        "save_title":           "저장",
        "save_done":            "설정이 저장되었습니다.",
        "warning_title":        "경고",
        "error_title":          "오류",

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
        "key_search_path_check":  "    - 확인: {path}  →  {status}",
        "status_not_found":       "파일 없음",
        "status_read_error":      "읽기 오류 ({error})",
        "status_key_missing":     "encryptionKey 필드 없음",
        "status_key_empty":       "encryptionKey 값이 비어 있음",
        "status_key_bad_length":  "encryptionKey 길이 오류 ({length}자, 32자 필요)",
        "status_key_non_hex":     "encryptionKey에 HEX가 아닌 문자 포함",
        "status_ok":              "유효한 키 발견",
        "key_found":              "[*] 복호화 키 자동 추출 성공: {key}",
        "key_search_failed":      "[!] System.json에서 유효한 키를 찾지 못했습니다.",

        # appearance / language change
        "lang_changed": "[Lang] 언어가 한국어로 변경되었습니다.",
        "mode_dark":    "[Dark] 다크 모드로 전환되었습니다.",
        "mode_light":   "[Light] 라이트 모드로 전환되었습니다.",

        # processing
        "start_log":          "[Start] 복호화 작업을 시작합니다.",
        "scan_log":           "[Scan] 입력 폴더를 탐색 중…",
        "count_log":          "[Info] 복호화 대상 파일 {total}개를 찾았습니다.",
        "progress_log":       "[Progress] 진행률 {percent}% ({processed}/{total})",
        "failed_files_header": "[Failed] 실패한 파일 목록:",
        "no_files":           "[!] 복호화 대상 파일이 없습니다. (.rpgmvp / .png_ / .rpgmvo / .ogg_ / .rpgmvm / .m4a_)",
        "skip_symlink":       "[Skip] 심볼릭 링크는 건너뜁니다: {path}",
        "skip_unsupported":   "[Skip] 지원하지 않는 형식입니다 ({kind}): {path}",
        "skip_already_png":   "[Skip] 이미 복호화된 PNG로 보입니다: {path}",
        "skip_already_ogg":   "[Skip] 이미 복호화된 OGG로 보입니다: {path}",
        "skip_already_m4a":   "[Skip] 이미 복호화된 M4A로 보입니다: {path}",
        "plain_media_summary":"[Info] 암호화되지 않은 일반 미디어 파일 발견: PNG {png}개, OGG {ogg}개, M4A {m4a}개",
        "skip_not_encrypted": "[Skip] RPG Maker 헤더가 없어 암호화된 파일이 아닙니다: {path}",
        "skip_too_small":     "[Skip] 파일이 너무 작아 헤더를 읽을 수 없습니다: {path}",
        "file_ok":            "[OK]   {path}",
        "file_failed":        "[X]    실패: {path} / 이유: {reason}",
        "renamed_to":         "[i]    출력 파일명 충돌 → {path}",
        "done_log":           "[Done] 작업 완료 — 성공 {success}개, 실패 {failed}개, 건너뜀 {skipped}개, 전체 {total}개",
        "done_all_success":   "모든 대상 파일이 정상적으로 복호화되었습니다.",
        "done_some_failed":   "일부 파일 처리에 실패했습니다. 로그를 확인해 주세요.",

        # decrypt errors
        "file_too_small":   "파일 크기가 32바이트 미만입니다.",
        "bad_png":          "복호화 결과가 PNG 시그니처와 일치하지 않습니다. 키가 틀렸을 가능성이 큽니다.",
        "bad_ogg":          "복호화 결과가 OGG 시그니처와 일치하지 않습니다. 키가 틀렸을 가능성이 큽니다.",
        "bad_m4a":          "복호화 결과가 M4A 시그니처와 일치하지 않습니다. 키가 틀렸을 가능성이 큽니다.",
        "unknown_error":    "알 수 없는 오류",
        "io_error":         "I/O 오류: {error}",

        # misc
        "key_note":             "복호화 키는 설정 파일에 저장되지 않으며, 프로그램 실행 중에만 메모리에서 사용됩니다.",
        "fatal_error":          "[Fatal] 프로그램 실행 중 치명적인 오류가 발생했습니다: {error}",
        "close_while_processing": "복호화 작업 중에는 창을 닫을 수 없습니다. 작업이 끝난 뒤 종료해 주세요.",
        "fonts_missing_note":   "[i] Pretendard 폰트 파일을 찾을 수 없어 시스템 기본 글꼴을 사용합니다.",
    },

    "en": {
        "window_title": "RPG Decrypter",
        "app_title":    "RPG Decrypter",
        "app_subtitle": "Decrypts RPG Maker MV/MZ encrypted media assets.",

        "settings_section": "00  Settings",
        "section_game":     "01  Source Game Folder",
        "section_output":   "02  Output Folder",

        "appearance_label": "Appearance",
        "language_label":   "Language",
        "dark_mode":        "Dark mode",
        "target_label":     "Decryption Target",
        "target_both":      "Images + Audio",
        "target_image":     "Images only",
        "target_audio":     "Audio only",

        "input_placeholder":  "Select the game folder",
        "output_placeholder": "Folder for the decrypted files",
        "key_label":          "Decryption Key",
        "key_placeholder":    "Auto-detected from System.json or entered manually (not saved)",

        "folder_button":    "Browse",
        "save_button":      "Save Settings",
        "run_button":       "  ▶  Start Decryption",
        "searching_button": "Searching…",
        "progress_button":  "Processing…  {processed} / {total}  ({percent}%)",

        "log_header": "● LOG",

        "select_game_dialog":   "Select Source Game Folder",
        "select_output_dialog": "Select Output Folder",
        "save_title":           "Saved",
        "save_done":            "Settings were saved.",
        "warning_title":        "Warning",
        "error_title":          "Error",

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
        "key_search_path_check":  "    - check: {path}  →  {status}",
        "status_not_found":       "not found",
        "status_read_error":      "read error ({error})",
        "status_key_missing":     "encryptionKey field missing",
        "status_key_empty":       "encryptionKey field is empty",
        "status_key_bad_length":  "encryptionKey has invalid length ({length} chars, expected 32)",
        "status_key_non_hex":     "encryptionKey contains non-HEX characters",
        "status_ok":              "valid key found",
        "key_found":              "[*] Decryption key auto-detected: {key}",
        "key_search_failed":      "[!] Could not find a valid key in any System.json.",

        "lang_changed": "[Lang] Language changed to English.",
        "mode_dark":    "[Dark] Dark mode enabled.",
        "mode_light":   "[Light] Light mode enabled.",

        "start_log":          "[Start] Starting decryption.",
        "scan_log":           "[Scan] Scanning input folder…",
        "count_log":          "[Info] Found {total} target file(s).",
        "progress_log":       "[Progress] {percent}% ({processed}/{total})",
        "failed_files_header": "[Failed] Failed file list:",
        "no_files":           "[!] No encrypted target files were found (.rpgmvp / .png_ / .rpgmvo / .ogg_ / .rpgmvm / .m4a_).",
        "skip_symlink":       "[Skip] Symbolic link skipped: {path}",
        "skip_unsupported":   "[Skip] Unsupported format ({kind}): {path}",
        "skip_already_png":   "[Skip] File already looks like a decrypted PNG: {path}",
        "skip_already_ogg":   "[Skip] File already looks like a decrypted OGG: {path}",
        "skip_already_m4a":   "[Skip] File already looks like a decrypted M4A: {path}",
        "plain_media_summary":"[Info] Normal unencrypted media found: PNG {png}, OGG {ogg}, M4A {m4a}",
        "skip_not_encrypted": "[Skip] No RPG Maker header — file is not encrypted: {path}",
        "skip_too_small":     "[Skip] File is too small to contain a header: {path}",
        "file_ok":            "[OK]   {path}",
        "file_failed":        "[X]    Failed: {path} / Reason: {reason}",
        "renamed_to":         "[i]    Output filename collision → {path}",
        "done_log":           "[Done] Completed — {success} succeeded, {failed} failed, {skipped} skipped, {total} total",
        "done_all_success":   "All target files were decrypted successfully.",
        "done_some_failed":   "Some files failed. Please check the log for details.",

        "file_too_small":   "File is smaller than 32 bytes.",
        "bad_png":          "Decrypted output does not match the PNG signature. The key is likely wrong.",
        "bad_ogg":          "Decrypted output does not match the OGG signature. The key is likely wrong.",
        "bad_m4a":          "Decrypted output does not match the M4A signature. The key is likely wrong.",
        "unknown_error":    "Unknown error",
        "io_error":         "I/O error: {error}",

        "key_note":             "The decryption key is not stored in the config file. It only lives in memory while the app is running.",
        "fatal_error":          "[Fatal] A critical error occurred: {error}",
        "close_while_processing": "You cannot close the window while decryption is running. Please wait until the task finishes.",
        "fonts_missing_note":   "[i] Pretendard font files were not found. Falling back to the system default font.",
    },

    "ja": {
        "window_title": "RPG Decrypter",
        "app_title":    "RPG Decrypter",
        "app_subtitle": "RPG Maker MV/MZ で暗号化されたメディアアセットを復号します。",

        "settings_section": "00  設定",
        "section_game":     "01  元ゲームフォルダー",
        "section_output":   "02  出力フォルダー",

        "appearance_label": "表示モード",
        "language_label":   "言語",
        "dark_mode":        "ダークモード",
        "target_label":     "復号対象",
        "target_both":      "画像 + オーディオ",
        "target_image":     "画像ファイルのみ",
        "target_audio":     "オーディオのみ",

        "input_placeholder":  "ゲームフォルダーを選択してください",
        "output_placeholder": "復号後のファイルを保存するフォルダー",
        "key_label":          "復号キー",
        "key_placeholder":    "System.json から自動取得、または手動入力(保存されません)",

        "folder_button":    "フォルダー選択",
        "save_button":      "設定を保存",
        "run_button":       "  ▶  復号開始",
        "searching_button": "検索中…",
        "progress_button":  "処理中…  {processed} / {total}  ({percent}%)",

        "log_header": "● LOG",

        "select_game_dialog":   "元ゲームフォルダーを選択",
        "select_output_dialog": "出力フォルダーを選択",
        "save_title":           "保存",
        "save_done":            "設定を保存しました。",
        "warning_title":        "警告",
        "error_title":          "エラー",

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
        "key_search_path_check":  "    - 確認: {path}  →  {status}",
        "status_not_found":       "見つかりません",
        "status_read_error":      "読み込みエラー ({error})",
        "status_key_missing":     "encryptionKey フィールドがありません",
        "status_key_empty":       "encryptionKey が空です",
        "status_key_bad_length":  "encryptionKey の長さが不正です ({length} 文字、32 文字必要)",
        "status_key_non_hex":     "encryptionKey に HEX 以外の文字が含まれています",
        "status_ok":              "有効なキーを発見",
        "key_found":              "[*] 復号キーを自動取得しました: {key}",
        "key_search_failed":      "[!] 有効なキーを含む System.json が見つかりませんでした。",

        "lang_changed": "[Lang] 言語を日本語に変更しました。",
        "mode_dark":    "[Dark] ダークモードに切り替えました。",
        "mode_light":   "[Light] ライトモードに切り替えました。",

        "start_log":          "[Start] 復号処理を開始します。",
        "scan_log":           "[Scan] 入力フォルダーを走査中…",
        "count_log":          "[Info] 対象ファイルを {total} 個検出しました。",
        "progress_log":       "[Progress] 進行率 {percent}% ({processed}/{total})",
        "failed_files_header": "[Failed] 失敗したファイル一覧:",
        "no_files":           "[!] 対象ファイルがありません (.rpgmvp / .png_ / .rpgmvo / .ogg_ / .rpgmvm / .m4a_)。",
        "skip_symlink":       "[Skip] シンボリックリンクをスキップ: {path}",
        "skip_unsupported":   "[Skip] 対応していない形式 ({kind}): {path}",
        "skip_already_png":   "[Skip] すでに復号済みの PNG のようです: {path}",
        "skip_already_ogg":   "[Skip] すでに復号済みの OGG のようです: {path}",
        "skip_already_m4a":   "[Skip] すでに復号済みの M4A のようです: {path}",
        "plain_media_summary":"[Info] 暗号化されていない通常メディアを検出: PNG {png} 個、OGG {ogg} 個、M4A {m4a} 個",
        "skip_not_encrypted": "[Skip] RPG Maker ヘッダーがないため暗号化されていません: {path}",
        "skip_too_small":     "[Skip] ヘッダーを読み取れない小さなファイル: {path}",
        "file_ok":            "[OK]   {path}",
        "file_failed":        "[X]    失敗: {path} / 理由: {reason}",
        "renamed_to":         "[i]    出力ファイル名の衝突 → {path}",
        "done_log":           "[Done] 完了 — 成功 {success} / 失敗 {failed} / スキップ {skipped} / 合計 {total}",
        "done_all_success":   "すべての対象ファイルを正常に復号しました。",
        "done_some_failed":   "一部のファイル処理に失敗しました。ログをご確認ください。",

        "file_too_small":   "ファイルサイズが 32 バイト未満です。",
        "bad_png":          "復号結果が PNG シグネチャと一致しません。キーが間違っている可能性が高いです。",
        "bad_ogg":          "復号結果が OGG シグネチャと一致しません。キーが間違っている可能性が高いです。",
        "bad_m4a":          "復号結果が M4A シグネチャと一致しません。キーが間違っている可能性が高いです。",
        "unknown_error":    "不明なエラー",
        "io_error":         "I/O エラー: {error}",

        "key_note":             "復号キーは設定ファイルに保存されません。アプリ実行中のメモリ上にのみ保持されます。",
        "fatal_error":          "[Fatal] 実行中に重大なエラーが発生しました: {error}",
        "close_while_processing": "復号処理中はウィンドウを閉じられません。完了するまでお待ちください。",
        "fonts_missing_note":   "[i] Pretendard フォントが見つからないため、システム既定のフォントを使用します。",
    },
}
