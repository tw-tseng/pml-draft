# Git 操作小抄 —— PA_pmllibE3D2.1 版本控制

適用情境：單人在本機（Windows）維護 PML 程式庫，取代原本用檔名加日期／Copy／複製 做備份的方式。

## 0. 前置：安裝與設定（只需做一次）

1. 安裝 [Git for Windows](https://git-scm.com/download/win)
2. 在資料夾內開 Git Bash（滑鼠右鍵 → Git Bash Here），設定身分：

```bash
git config --global user.name "tw.tseng"
git config --global user.email "tw.tseng610216@gmail.com"
```

3. 建立倉庫（在 `D:\E3D\pdms_prog\E3D2.1\PA_pmllibE3D2.1` 資料夾內）：

```bash
git init
```

4. 建立 `.gitignore`（排除不需要追蹤的雜訊檔）：

```
*.bak
Thumbs.db
.DS_Store
_temp/
```

5. 建立第一個版本（baseline）：

```bash
git add -A
git commit -m "Initial baseline"
```

> 注意：如果這個資料夾是「網路磁碟機／雲端同步資料夾」而不是本機硬碟，git 有時會因為檔案鎖定機制而出問題（例如無法建立 lock file）。建議確認路徑是本機磁碟（如 D: 是實體硬碟），或改在本機路徑建 repo 再用其他方式同步。

---

## 1. 核心觀念（先懂這四個字）

| 名詞 | 意思 |
|---|---|
| working directory | 你現在看到、正在編輯的檔案 |
| staging area（暫存區） | 你用 `git add` 選好「這次要記錄哪些改動」 |
| commit（提交） | 把暫存區的內容存成一個「版本快照」，附上說明文字 |
| HEAD | 目前所在的版本（通常是最新 commit） |

工作流程永遠是：**改檔案 → git add → git commit**。

---

## 2. 每天的日常指令

```bash
git status              # 看哪些檔案被改了、還沒 commit
git diff                # 看目前改動的內容（跟上次 commit 比）
git diff DrawingPlan1FlowAnnotation.pmlfnc   # 只看單一檔案的改動

git add -A               # 把所有改動加入暫存區
git add draft/functions/DrawingPlan1FlowAnnotation.pmlfnc   # 只加特定檔案

git commit -m "修正 FlowAnnotation 箭頭方向錯誤"   # 提交一個版本
```

commit message 建議寫「這次改了什麼、為什麼改」，例如：
- `新增 GridAnnotation 支援斜向管線標註`
- `修正 MatchLine 在轉角處座標計算錯誤`
- `還原上週的座標偏移邏輯（造成標註跑版）`

---

## 3. 查看歷史紀錄

```bash
git log                          # 完整歷史（含每次 commit 的說明）
git log --oneline                # 精簡版，一行一個版本
git log --oneline -- draft/functions/DrawingPlan1MatchLine1.pmlfnc   # 只看某檔案的歷史
git log -p draft/forms/DrawingPlan1.pmlfrm   # 看某檔案每次改了什麼內容（含程式碼差異）
```

---

## 4. 比較不同版本

```bash
git diff HEAD~1 HEAD                     # 跟上一版比較
git diff <commit1> <commit2>             # 比較兩個特定版本（commit hash 從 git log 取得）
git diff <commit1> <commit2> -- 檔名       # 只比較單一檔案
```

---

## 5. 回到舊版本（取代你原本「複製一份改日期」的做法）

**只想看某個舊版本內容、不影響現在的工作：**
```bash
git show <commit>:draft/functions/DrawingPlan1MatchLine1.pmlfnc
```

**把某個檔案還原成舊版本（會覆蓋目前內容）：**
```bash
git checkout <commit> -- draft/functions/DrawingPlan1MatchLine1.pmlfnc
```

**整個資料夾都想退回某個版本（危險，會清掉之後的改動，先確認）：**
```bash
git reset --hard <commit>
```

> `<commit>` 是 `git log --oneline` 顯示的那一串 7 碼英數字（例如 `a3f9c1d`），複製前面幾碼即可。

---

## 6. 分支（要試新寫法、又怕改壞現有功能時用）

```bash
git branch                       # 看目前有哪些分支
git checkout -b test-new-matchline    # 建立並切換到新分支
# ...在這個分支上放心修改、commit...
git checkout main                # 改壞了想放棄，切回主線就好，新分支不影響主線
git merge test-new-matchline     # 測試 OK 了，合併回主線
```

---

## 7. 常見情境對照表

| 你以前的做法 | 現在用 git |
|---|---|
| 複製一份改檔名加日期 | `git commit -m "說明"` |
| 檔名加 `- Copy` / `- 複製` | 不用複製，直接改，git 會記住舊版本 |
| 想找回上個月的版本 | `git log` 找到那次 commit，再用 `git checkout <commit> -- 檔名` |
| 想知道這次到底改了哪裡 | `git diff` 或 `git log -p` |
| 存 `.bak` 檔案 | `.gitignore` 排除，靠 git 歷史取代 |

---

## 8. 圖形化工具（不想背指令可以用）

- **VS Code**：內建 Source Control 面板，改動、diff、commit 都能用滑鼠點，推薦搭配 PML 語法插件一起用
- **GitHub Desktop**：介面更簡單，適合純本機版本控制
- **TortoiseGit**：整合在檔案總管右鍵選單，Windows 使用者常用

---

## 9. 提醒事項

- commit 前先 `git status` 確認要加的檔案對不對，避免把暫存/測試檔也提交進去
- 每次告一段落（例如某個 pmlfnc 改完能跑了）就 commit 一次，不用等到全部做完
- `git reset --hard` 會清掉未提交的改動，執行前務必先確認
- 之前那些帶日期/Copy/複製 後綴的舊檔案，等 git 上路穩定後可以陸續清掉，改用 `git log` 查歷史即可，不用再手動留備份檔
