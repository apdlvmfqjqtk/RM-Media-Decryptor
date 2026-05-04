# RM-Media-Decryptor
> A GUI decryption tool for RPG Maker (MV/MZ) media files.

흔히 쯔꾸르 게임이라 불리는 RPG Maker (MV/MZ) 게임의 암호화된 미디어 리소스(오디오, 이미지)를 손쉽게 복호화해 주는 GUI 기반 프로그램입니다.

## 기능
- 자동 키 추출: 게임 폴더를 지정하면 `system.json` 파일을 분석하여 암호화 키를 메모리에 자동 로드합니다.
- 선택적 복호화: 오디오 파일, 이미지 파일 또는 둘 다 선택하여 복호화할 수 있습니다.
- 직관적인 UI: 해독 과정과 결과가 실시간으로 로그창에 출력됩니다.

## 사용법
1. 저장소(Releases 등)에서 `RM-Media-Decryptor.exe` 실행 파일을 다운로드하여 실행합니다. (별도의 설치 필요 없음)
2. '게임 폴더 선택' 버튼을 눌러 대상 게임의 최상위 폴더를 지정합니다.
3. 복호화할 대상(오디오, 이미지)을 체크합니다.
4. '저장 폴더 선택' 버튼을 눌러 결과물이 저장될 경로를 지정합니다.
5. '복호화 시작'을 누르고 로그 창의 진행 상황을 확인합니다.

## 문제 해결 (Troubleshooting)
- 프로그램 설정이 꼬이거나 완전한 초기화가 필요한 경우, 윈도우 탐색기 주소창에 `%APPDATA%\RPGDecrypter`를 입력하여 해당 폴더로 이동한 뒤, 내부의 설정 파일을 삭제하고 프로그램을 다시 실행해 주십시오.

## 면책 조항
이 프로그램은 기술적인 학습 및 본인이 정당하게 소유한 파일의 개인적인 백업/수정 목적으로만 사용해야 합니다. 추출한 리소스를 무단으로 배포하거나 상업적으로 이용하는 등 타인의 저작권을 침해하는 행위에 대해 개발자는 어떠한 법적 책임도 지지 않습니다.

## Credits
**Font:** 본 프로그램의 UI는 [Pretendard](https://cactus.tistory.com/306) 폰트를 사용하였습니다.
---

# RM-Media-Decryptor
> A GUI decryption tool for RPG Maker (MV/MZ) media files.

A GUI-based program that easily decrypts encrypted media resources (audio, images) from RPG Maker (MV/MZ) games.

## Features
- Automatic Key Extraction: Specify the game folder, and it will automatically analyze the `system.json` file to load the encryption key into memory.
- Selective Decryption: You can choose to decrypt audio files, image files, or both.
- Intuitive UI: The decryption process and results are displayed in the log window in real-time.

## Usage
1. Download the `RM-Media-Decryptor.exe` executable from the repository (e.g., Releases) and run it. (No installation required)
2. Click the 'Select Game Folder' button to specify the root folder of the target game.
3. Check the target media types (Audio, Image) you want to decrypt.
4. Click the 'Select Save Folder' button to specify the destination path for the decrypted files.
5. Click 'Start Decryption' and monitor the progress in the log window.

## Troubleshooting
- If you experience configuration issues or need to reset the program settings, go to `%APPDATA%\RPGDecrypter` in the Windows File Explorer address bar, delete the settings file inside, and restart the program.

## Disclaimer
This program is intended solely for educational purposes and for creating personal backups or modifications of files you legally own. The developer assumes no legal responsibility for any copyright infringement, including unauthorized distribution or commercial use of the extracted resources.

## Credits
- **Font:** The UI of this program uses the [Pretendard](https://cactus.tistory.com/306) font.
---

# RM-Media-Decryptor
> A GUI decryption tool for RPG Maker (MV/MZ) media files.

RPGツクール (MV/MZ) 製ゲームの暗号化されたメディアリソース（音声、画像）を簡単に復号化するGUIベースのツールです。

## 機能
- キーの自動抽出: ゲームフォルダを指定すると、`system.json`ファイルを解析し、暗号化キーを自動的にメモリに読み込みます。
- 選択的な復号化: 音声ファイル、画像ファイル、またはその両方を選択して復号化できます。
- 直感的なUI: 復号化の進行状況や結果がリアルタイムでログウィンドウに出力されます。

## 使い方
1. リポジトリ（Releasesなど）から実行ファイル `RM-Media-Decryptor.exe` をダウンロードして実行します。（インストール不要）
2. 「ゲームフォルダ選択」 ボタンをクリックし、対象ゲームのルートフォルダを指定します。
3. 復号化する対象（音声、画像）にチェックを入れます。
4. 「保存フォルダ選択」 ボタンをクリックし、復号化されたファイルの保存先を指定します。
5. 「復号化開始」 をクリックし、ログウィンドウで進行状況を確認します。

## トラブルシューティング (Troubleshooting)
- プログラムの設定に問題が発生したり、初期化が必要な場合は、エクスプローラのアドレスバーに `%APPDATA%\RPGDecrypter` を入力して該当フォルダへ移動し、内部の設定ファイルを削除してからプログラムを再起動してください。

## 免責事項 (Disclaimer)
本プログラムは、技術的な学習、およびユーザー自身が正当に所有するファイルの個人的なバックアップや改変を目的としてのみ使用してください。抽出したリソースの無断配布や商用利用など、他者の著作権を侵害する行為について、開発者はいかなる法的責任も負いません。

## クレジット (Credits)
- **Font:** 本プログラムのUIには [Pretendard](https://cactus.tistory.com/306) フォントを使用しています。

*Developed with AI assistance.*
