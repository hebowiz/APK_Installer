# ADB APK Installer

Windows向けのシンプルなAPKインストーラー。Python 3.11.9 / Tkinterで作成。
アプリ本体はPython標準ライブラリだけで動作します。

リポジトリは[hebowiz/APK_Installer](https://github.com/hebowiz/APK_Installer)です。
要求仕様と設計は[設計書](docs/ADB_APK_Installer_Design.md)を参照してください。

## フォルダ構成

```text
APK_Installer/
├── adb_apk_installer.py        # アプリ本体
├── docs/
│   └── ADB_APK_Installer_Design.md
├── tests/
│   ├── __init__.py
│   └── test_installer.py       # ADBを模擬した自動テスト
├── setup.bat                  # Python 3.11.9の仮想環境を準備
├── run.bat                    # 仮想環境で起動
├── test.bat                   # 自動テストを実行
├── build_exe.bat              # Windows用exeを作成
├── requirements-build.txt     # ビルド専用の依存パッケージ
├── .python-version            # 使用するPythonのバージョン
├── .gitattributes             # 改行コードの設定
├── .gitignore                 # Git管理から除外するファイル
├── AGENTS.md                  # 日本語ドキュメントの編集方針
└── README.md
```

`.venv`はローカルで作成します。仮想環境、`build`、`dist`、APK、Platform-Tools、個人設定はGit管理から除外します。
アプリ本体は当面1ファイルで管理し、機能が増えた段階でGUI・ADB操作・設定管理を分割します。

## 開発環境

Python 3.11.9を、TkinterとPython Launcherを含めてインストールします。
新しいPCではリポジトリを取得し、プロジェクトのフォルダでセットアップを実行します。

```powershell
git clone https://github.com/hebowiz/APK_Installer.git
cd APK_Installer
.\setup.bat
.\.venv\Scripts\python.exe --version
```

既にフォルダがある場合は、そのフォルダで`.\setup.bat`から実行します。
`setup.bat`は`.venv`を作成し、Pythonのバージョンが3.11.9であることとTkinterを読み込めることを確認します。
既存の`.venv`が別のバージョンの場合は処理を止めます。必要なファイルを確認してから既存環境を別名にし、再実行してください。
`.python-version`にも3.11.9を記録していますが、バッチでは実際に使うPythonを確認します。

起動とテストには追加パッケージが不要です。各バッチは`.venv`内のPythonを直接使うので、仮想環境の有効化は不要です。
エディターでも`.venv\Scripts\python.exe`をPythonインタープリターに指定します。

## 起動

1. リポジトリを取得するか、ZIPをすべて展開します。
2. Python 3.11.9を用意します。
3. `run.bat`をダブルクリックします。

`run.bat`は`setup.bat`で仮想環境を確認してから起動します。
PowerShellからは次のコマンドで起動します。

```powershell
.\run.bat
```

## 使い方

1. Android端末でUSBデバッグを有効にし、USB接続します。初回は端末上でPCの接続を許可してください。
2. 起動時にADBを検出し、`adb version`と`adb devices -l`を実行します。
   一覧にはシリアル番号・接続状態・型番（Model）・Productを表示します。許可済み端末の型番は`adb -s SERIAL shell getprop ro.product.model`で取得し、空白を含む表記も保持します。取得できない場合は`adb devices -l`のmodel情報を使用します。商品名や販売地域別の型番が必ず得られるわけではなく、端末メーカーが設定した値を表示します。
3. ADBが見つからない場合は「Select adb.exe」で選びます。
4. 端末一覧でインストール先を選択します。使用可能な端末が1台だけなら自動選択します。
5. 「Select apk」でAPKを選び、「Install」を押します。
6. 完了ダイアログとログの`Success`を確認します。

端末の接続・切断やUSBデバッグ許可の後は「Refresh」を押してください。
一覧は起動時とRefresh時に更新します。定期ポーリングは行いません。

## ADBの検出と設定保存

ADBの探索順は次のとおりです。

1. 前回保存したADBのパス
2. 環境変数PATHから見つかるADB
3. このプログラムと同じフォルダの`adb.exe`
4. このプログラムのフォルダ内の`platform-tools\adb.exe`

「Select adb.exe」「Select apk」で選択したフルパスは、その場で保存し、次回起動時に復元します。
保存先は`%APPDATA%\ADB_APK_Installer\settings.json`です。exeの置き場所が変わっても、同じWindowsユーザーでは設定を引き継ぎます。
保存したファイルが移動・削除されていた場合、元のパスを表示して再指定を促します。
ADBを再探索する場合は「Auto detect」を使います。この操作では保存済みADB指定を外してPATHと配置先から探し直します。APKの設定は維持します。

ADBはAndroid SDK Platform-Toolsを使用してください。`adb.exe`だけを移動すると、必要なDLLがなく起動できない場合があります。Platform-Toolsフォルダをそのまま置き、その中の`adb.exe`を指定してください。

## インストール動作

- 選択した端末のシリアル番号を必ず`-s`に指定します。別の端末への自動切り替えはしません。
- 実行前に対象端末の`get-state`を確認します。
- `adb -s SERIAL install -r APK`で転送とインストールを行います。
- 同一アプリの更新では既存データを保持します。署名が異なるAPKやバージョンダウンはエラーになることがあります。
- 自動アンインストールやデータ削除は行いません。
- 単体APK用です。分割APK（複数APK、APKS、XAPK）とAABは対象外です。
- アプリの自動起動は行いません。
- ADB処理はバックグラウンドで実行し、GUIを応答可能な状態に保ちます。
- 最下段は、動くインジケーター・現在の処理・経過時間を表示します。完了／失敗時はアニメーションを止め、結果と処理時間を残します。
- 転送率を取得していないため、パーセントや進捗率のバーは表示しません。転送とインストールは同じADBコマンドで実行するので、両者をまとめて表示します。
- 処理中はパス変更、再実行、通常のウィンドウ終了を抑止します。
- 検出処理は各コマンド30秒（追加の型番取得は各端末5秒）、インストールは300秒でタイムアウトします。タイムアウト後も端末側の処理が継続する場合があるため、端末の状態を確認してから再実行してください。

## 端末の状態

| State | 対応 |
|---|---|
| device | インストール可能。端末側のポリシーなどで失敗する場合はログを確認 |
| unauthorized | 端末の画面を開き、USBデバッグの接続許可を承認してRefresh |
| offline | USB接続をやり直してRefresh |
| 端末なし | USBデバッグ、データ通信対応ケーブル、必要に応じてWindows用USBドライバーを確認 |

## Windows実行ファイルの作成

Python 3.11.9をインストールしたWindows上で`build_exe.bat`をダブルクリックします。
起動・テストと共通の`.venv`にPyInstallerを導入し、コンソール非表示の単一exeを作成します。
初回ビルド時はパッケージダウンロードのためインターネット接続が必要です。

出力先は`dist\ADB_APK_Installer.exe`です。

手動でビルドする場合は、次のコマンドを実行します。

```powershell
.\setup.bat
.\.venv\Scripts\python.exe -m pip install -r .\requirements-build.txt
.\.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --onefile --windowed --specpath build --name ADB_APK_Installer .\adb_apk_installer.py
```

exeを使う人にはPythonのインストールは不要です。ただしADBとその必要ファイルは別途必要です。ADB本体はこのリポジトリにも生成exeにも含めません。
Windows用exeはWindows上でビルドしてください。

## 確認

ロジックの自動テストは、プロジェクトのルートで実行します。

```powershell
.\test.bat
# 仮想環境のPythonから直接実行する場合
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

作成時にPython 3.11.17（Linux）で16件の自動テストに合格しました。
移行後はWindows / Python 3.11.9でも16件に合格し、exeのビルドを確認しました。
画面の目視確認、生成exeの起動、実機へのインストールは未検証です。

テストはADBを模擬し、端末一覧の解析、パス保存・復元、指定シリアルへの接続、パス内の空白・日本語、ADBエラー、タイムアウト、成功応答の判定を確認します。
実機確認では、起動 → ADB/APK選択 → 再起動後のパス復元 → 端末選択 → Installを確認してください。

## GitHubとの連携

リモート名は`origin`、通常の開発ブランチは`main`です。接続先と変更内容は次のコマンドで確認します。

```powershell
git remote -v
git status
git diff
```

変更後は必要なファイルを指定してコミットし、GitHubへ送信します。たとえばREADMEを変更した場合は次のように実行します。

```powershell
git add README.md
git commit -m "Update README"
git push
```

## 参照

- Android ADB: https://developer.android.com/tools/adb
- Platform-Tools: https://developer.android.com/tools/releases/platform-tools
- PyInstaller: https://pyinstaller.org/en/stable/usage.html
- PyInstallerの対象OS: https://pyinstaller.org/en/stable/operating-mode.html

## 更新履歴

- 2026-11-06: 設計書とテストをフォルダに分け、Python 3.11.9の仮想環境とGitHub連携の手順を整備。
- 2026-11-06: 進捗率と誤認しやすいバーを、処理状態・動くインジケーター・経過時間表示に変更。完了／失敗時の結果を保持するよう修正。
