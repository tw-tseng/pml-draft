# Git 操作小抄（實測可行版）—— PA_pmllibE3D2.1

適用情境：單人在本機（Windows）維護 PML 程式庫，資料夾位於共用/網路磁碟機（D:\E3D\pdms_prog\...），取代原本用檔名加日期／Copy／複製 做備份的方式。

## 0. 安裝 Git for Windows

1. 下載頁：https://git-scm.com/install/windows
   直接下載連結（依當時最新版為準）：https://github.com/git-for-windows/git/releases
   或用 winget：`winget install --id Git.Git -e --source winget`
2. 安裝精靈一路 Next 用預設值即可（"Adjusting your PATH environment" 這頁新版安裝程式可能不會出現，不影響，屬正常現象）
3. 驗證安裝：開新的 **CMD 或 PowerShell**（不是 Git Bash）輸入：
   ```bash
   git --version
   ```
   有顯示版本號（如 `git version 2.55.0.windows.2`）即成功，PATH 也已正確設定

## 1. 初次設定（在資料夾內開 Git Bash Here）

```bash
git config --global user.name "tw.tseng"
git config --global user.email "tw.tseng610216@gmail.com"

git init
```

### 建立 .gitignore

**不要**把內容直接貼在終端機執行（會被當成指令跑，出現 `command not found`）。用下面任一方式建立檔案：

方式一，指令建立：
```bash
cat > .gitignore << 'EOF'
*.bak
Thumbs.db
.DS_Store
_temp/
EOF
```

方式二，用記事本新增 `.gitignore` 檔案（檔名前面有點、無副檔名），貼入同樣內容存檔。

### 解決「dubious ownership」錯誤

如果資料夾在網路磁碟機/共用磁碟上，`git add` 或 `git commit` 可能出現：

```
fatal: detected dubious ownership in repository at ...
```

這是因為資料夾擁有者跟目前登入帳號不同（常見於共用/網路路徑）。解法（照錯誤訊息指示的那行執行即可）：

```bash
git config --global --add safe.directory D:/E3D/pdms_prog/E3D2.1/PA_pmllibE3D2.1
```

### 第一次提交（baseline）

```bash
git add -A
git commit -m "Initial baseline"
```

執行時若看到類似：
```
warning: in the working copy of 'xxx', LF will be replaced by CRLF the next time Git touches it
```
這是 Windows 換行符號正常提示，**不影響**、不會擋提交，可以忽略。

驗證是否成功：
```bash
git log --oneline
```
有看到一行 `<commit hash> (HEAD -> master) Initial baseline` 就代表成功。

---

## 2. 日常操作

```bash
git status                        # 看哪些檔案被改了
git diff                          # 看改動內容
git diff 檔名                      # 只看單一檔案改動

git add -A                        # 加入所有改動
git add 檔名                       # 只加特定檔案

git commit -m "說明這次改了什麼"      # 提交一個版本
```

## 3. 查歷史 / 比較版本

```bash
git log --oneline                 # 精簡版歷史列表
git log --oneline -- 檔名           # 只看某檔案的歷史
git log -p 檔名                     # 看某檔案每次改了什麼內容

git diff HEAD~1 HEAD              # 跟上一版比較
git diff <commit1> <commit2>      # 比較兩個特定版本
```

## 4. 回到舊版本

```bash
git show <commit>:檔案路徑           # 只看內容，不影響現況
git checkout <commit> -- 檔名        # 把單一檔案還原成舊版本
git reset --hard <commit>          # 整個資料夾退回某版本（會清掉之後改動，先確認）
```

## 5. 分支（測試新寫法用）

```bash
git checkout -b test-新功能
# 修改、commit...
git checkout master               # 放棄就切回主線
git merge test-新功能               # 測試OK就合併回主線
```

## 6. 常見情境對照表

| 舊做法 | 現在用 git |
|---|---|
| 複製一份改檔名加日期 | `git commit -m "說明"` |
| 檔名加 `- Copy` / `- 複製` | 不用複製，git 自動記住舊版本 |
| 想找回上個月的版本 | `git log` 找到 commit，`git checkout <commit> -- 檔名` |
| 想知道這次改了哪裡 | `git diff` 或 `git log -p` |
| 存 `.bak` 檔案 | `.gitignore` 排除，靠 git 歷史取代 |

---

## 7. 同步到 GitHub（可選，多一層備份/協作用）

1. 到 github.com 建一個新 repository（建議 Private，不要自動加 README）
2. 複製 repo 網址，本機執行：
   ```bash
   git remote add origin https://github.com/你的帳號/PA_pmllibE3D2.1.git
   git branch -M main
   git push -u origin main
   ```
3. 之後同步：
   ```bash
   git push     # 本機 → GitHub
   git pull     # GitHub → 本機
   ```
4. 第一次 push 需要身分驗證：GitHub 不支援密碼登入，改用 **Personal Access Token**（GitHub網頁 Settings → Developer settings → Personal access tokens 產生後當密碼輸入），或改裝 **GitHub Desktop**（圖形介面，登入一次即可，不用碰指令）

---

## 8. 注意事項

- commit 前先 `git status` 確認要加的檔案對不對
- 每完成一小段（例如某個 pmlfnc 改完能跑了）就 commit 一次
- `git reset --hard` 會清掉未提交的改動，執行前務必先確認
- 資料夾在網路磁碟機上，如遇到鎖定/權限類錯誤，多半是 `safe.directory` 或磁碟機權限問題，非 git 本身故障
- 舊的帶日期/Copy/複製後綴備份檔，可等 git 穩定運作一段時間後再陸續清掉
