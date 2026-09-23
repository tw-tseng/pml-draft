# PA_pmllibE3D2.1 — AVEVA E3D 2.1 的 PML 程式庫

## 目錄與命名
- `design/` 是 DESIGN 模組、`draft/` 是 DRAFT 模組。檔名前綴決定模組：`DrawingPlan*` = DESIGN（建圖框 BOX），`DrawingPlan1*` = DRAFT（出圖／標註／版次）。新表單照這個規則命名。
- 一個 `.pmlfnc` 一個全域函式，PML 靠檔名找函式。
- `draft/PA-LIBY.txt` 是 DRAFT 裡 `/PA-LIBY` 這個 DEPT 用 E3D `OUTPUT` 倒出來的巨集：出圖用的 representation／hatch 的 rule 與 style 都在裡面，DrawingPlan1 出圖時若目的 DB 沒有 `/PA-LIBY` 會自動 `$M` 匯入。在 E3D 改了那組 LIBY 要重新 OUTPUT 覆蓋這個檔，不要手改。
- `pml.index` 由 E3D 的 `pml rehash all` 重建，不入庫。新增 `.pmlfnc`/`.pmlfrm` 後要 rehash，否則呼叫失敗會被 `handle any` 吃掉、變成無聲的無作用。
- 設計文件與各主題的定案在 Notion 頁面「E3D-管線平面圖程式摘要」（page id `3c8dd89e-3acd-80a7-9a3d-cecae639393f`），每個主題一個 toggle。改 出圖／版次／標註／柱位線 的行為前先讀對應的 toggle。

## 查 API
- 先 grep AVEVA 自己的 PMLLIB（先找 `C:\AVEVA\Everything3D2.10\PMLLIB`，沒有再找 `D:\AVEVA\Everything3D2.10\PMLLIB`），再猜 PML 指令或物件方法。EDGPACKET／pick 機制、REFGLN／GRIDPL、ORIENTATION 方法都在那裡有先例。

## PML 的坑（都實際踩過）
- 沒有 `do while`，用 `do !i from 1 to n` 加 `break if (...)`。
- 方法不能接在括號運算式或全域函式的回傳值上：`(a+b).sqrt()`、`abs(!x).gt(1)`、`string(!x).real()` 都是 syntax error，而且只在執行到那行才炸。拆成一步一個變數。
- `!!Form.Method()` 不會自動載入表單（函式和物件會）。跨表單借方法前：`if (undefined(!!X)) then loadform !!X endif`。
- 表單物件會快取：改了 `.pmlfrm` 要 `kill !!X`、`pml reload form X`、再 `show !!X`，否則看不到修改。回覆使用者時要提醒這件事。
- E3D 讀 PML 是 Big5：`!!alert` 等對話框字串保持 ASCII，表單標籤可以用中文。
- `executecommand` 要給 Command key，不是 Button 名；打錯不報錯、只是沒反應。
- 用 `object POSITION()` 逐欄填的 POSITION 沒有座標系，`.distance()`/`.direction()` 會炸；用 `DrawingPlan.PosOf()` 那種帶 `WRT /*` 的字串建。POSITION 直接展開給 AID 會帶 `WRT /*` 尾巴，AID 不吃，座標要一個一個寫。
- LDIM 的斷口：CE 在 LDIM，`gap at x <X> y <Y> length <L>`。
- EDGPACKET 的 action 傳進方法的 `!pos` 是 packet 自己 `return[1].position` 的參考（方法參數傳參考）。`!!edgCntrl.remove()` → `retrieve()` 會把整個 EDGSTATE 換掉，先 `DropPicking()` 再用 `!pos` 就炸 `(2,750) Cannot invoke method WRT on non-existent object`，再往下傳會變 `Method X(<UNTYPED>) not found`。先把 E/N/U 取出來（或複製進 member）再 drop。

## E3D 格線（REFGRD → GRIDEL → GRIDPL → REFGLN）
- 平面柱位線在 Z 軸的 GRIDEL（專案裡叫 `Elev`）底下的水平 GRIDPL 裡，不是頂層。
- REFGLN 是「GRDREF 那個平面」畫在「owner 那個平面」上的痕跡，圈圈印的號碼是 `idplane of grdref`，REFGLN 的 NAME 是空的。
- 同一條邊在資料庫裡存在兩次（高程面的小孩、柱位面的小孩），3D pick 碰到哪一個是運氣。要知道使用者點一條線是什麼意思，用階段（先平面後高程），不要靠元素判斷。

## 版次
- REVI snapshot 可以用純 PML 建：`PmlRevisionControl` 物件（推翻了「只能手動按」的舊結論）。

## 這台機器
- 這是測試機，E3D 版本跟正式機不同：缺屬性／缺命令用 `HANDLE ANY` 包掉，能跑完就好，不必真的修。
- PML 寫到 `L:`，對應這台的 `D:`；使用者說「請看 check」是指 `D:\...\CHECK.TXT`（check*.txt 都是除錯 dump，已 gitignore）。
- Notion MCP（`.mcp.json`，被 gitignore）用固定 integration token，讀 `NOTION_TOKEN` 使用者環境變數。hosted MCP 端點常對這個 token 回 403，連不上就直接用 REST API（`api.notion.com`，同一個 token）讀寫。MCP 回 401 `invalid_token` 多半是 VS Code 行程沒繼承到 `NOTION_TOKEN`（PowerShell 查 `$env:NOTION_TOKEN` 為空、User 層有值）：重開 VS Code，當下可先用 User 層的值走 REST。

## 待實測（2026-09-21 已併回 master，`bd8079f`..`1c99bc6`）
- 原本在 `feature/drawingplan-grid-merge`。2026-09-21 使用者決定連同尚未實測的部份一起併進 master（我有先提醒下面那條「還沒在 E3D 實測」）。分支本身還在，內容已全部包含在 master 裏。
- 做了什麼（9 個 commit，都只動 `design/forms/DrawingPlan.pmlfrm`）：
  - `DrawingPlanGrid.pmlfrm` 併進 `DrawingPlan` 成 **Grid** 分頁，獨立表單刪掉。方法加 `Grid` 前綴，gadget 撞名的加 `g`（`.gubot/.gutop/.gcreate/.glines/.gstatus/.gresult`），`edgdesc`／`DropPicking`／`Close` 共用一份——兩種 pick 用同一個 packet description，在 Grid 開始點線會把 Pick 分頁做一半的 4 點丟掉。
  - Grid：Esc 只結束該輪，BOX 只有按 Create Boxes 才建；Top U／Bottom U 各有 Pick 鈕（點一個點取 U）；Top/Bottom U 跟點到的高程線一起排序去重分層（`SortedLevels`）。
  - Split/Merge 分頁改名 **Modify**，新增 **Move Face**：一個面推出去／拉進來、對面不動，BOX 就地改 POS＋該軸長度（不建新 BOX）。面用 BOX 自己的軸命名（+X/−X/+Y/−Y/Top/Bottom）。兩種給法：`by offset`＋Move、`to coordinate` 的 Pick（點完直接移、欄位顯示移完的座標）；欄位手打＋Enter 也會移（text CALLBACK，用 `facetolast` 擋重複觸發）。
  - Modify 分頁重排：頂端三步驟提示、Show Box 旁顯示目前 BOX 名稱／XYZ／U 底..頂、三個功能各自一個子框；Show Box 不再是 toggle。
- **還沒在 E3D 實測**：Move Face 全部（`XLEN $!newlen` 展開帶不帶 mm；Enter callback 是按 Enter 才觸發還是離開欄位也觸發——若是後者改回顯式按鈕）；Modify 分頁版面（Move Face 右側按鈕用固定 `xmin.faceoff+46` 對齊）；Grid 分頁 Top/Bottom U 併入分層後的結果。已實測 OK：Grid 分頁合併後能建 BOX、Bottom U 的 Pick（修過 DropPicking 順序後）。
- 工作樹上另外有兩個舊備份的刪除（`DrawingPlan1MatchLine(20260122)/(20260311).pmlfnc`）沒進任何 commit，使用者說不要進 master。
- 討論過、沒做：Import 分頁的「兩個對角點」格式（現在只有三點法；要做的話加「3 點／2 對角點」切換，兩對角點展開成 P1/P2/P3 丟 `MakeBox`）；DESIGN 端還缺的：多選一起改高程、鄰框縫／重疊檢查＋貼齊（DRAFT MatchSorted 在邊外 50mm 找鄰居）、複製到其他樓層、圍住選取物建 BOX、BOX 總覽清單。
- 舊的 `develop` 分支是 7 月練 git 的孤兒分支，可以刪（2026-09-21 查本機還在）。

## 設備尺寸的標註點（2026-09-21，`8c69f54`＋`1c99bc6`，已在 master，**未在 E3D 實測**）
- 尺寸鏈上設備那一點，從「`SheetLimitsOfVolume()` 的紙面外接框邊緣＋2mm」改成「設備中心線的端點，落在 BOX 外就沿線夾回邊界」＝ 中心線與 matchline 的交點。
- 為什麼要夾：P1501A/B 兩台泵跨在 match line 上，WVOL 往北伸出上邊界 942mm，端點落到紙面 y=529.343，比 up 尺寸線（510.942）還高 18.4mm，投影線整條畫在尺寸線上方、伸進標籤區。
- 端點本來就在 BOX 內的不動——管線自己的位置在 BOX 內時也是就地標，設備不該被特別推到邊界。
- 除錯行 `EQUIDIM`（origin／中心線端點／有沒有夾／夾完的點）會寫進 `check_rebuild.txt`。
- 還沒決定：中心線本身要不要也畫到 matchline，讓中心線＋投影線變成連續一條；捨入／貼齊要不要收緊（目前只有 `!esh` 那層 `.string('D3')`）。

## Check 分頁：框與框之間的縫／重疊（分支 `feature/box-neighbour-check`，2026-09-23，**未在 E3D 實測**）
- 1 個 commit `0b959c3`，從 master 開出來，只動 `design/forms/DrawingPlan.pmlfrm`（+938 行，五處純插入，沒刪任何東西）。**分支只在本機**，換電腦前要 `git push -u origin feature/box-neighbour-check`。跟 `feature/moveface-multi` 互不相干（那支改的是 Modify 分頁的方法，這支加新分頁＋新方法，之後併回應該只在 tabset 尾端與方法區塊有小衝突）。
- 為什麼做：DRAFT 的 `DrawingPlan1MatchSorted` 只在框線外 50mm 的薄片裡收鄰框（`MatchSorted.pmlfnc:47-68`），縫大於 50 就沒有鄰框，`MatchLine1.pmlfnc:94` 整段標籤被跳過——沒有 tick、沒有 `MATCH LINE Exxxxx`、也沒有 `SEE <鄰圖號>`。縫上的廠房兩張圖都沒有；重疊則是同一段畫兩次。都要等出圖才發現。
- 分類：每一對 BOX 在**第一個 BOX 自己的座標系**比三個區間（格線轉 12.5 度，用世界 E/N 比會把對齊的兩框讀成兩軸都重疊）。看幾個軸分開：≥2 軸＝對角或不相鄰；1 軸＝有縫；0 軸但有一軸在容差內＝正常貼齊；0 軸＝重疊（取最小貫入）。貼齊且是平面相鄰的再比 ubot/utop，差了就報高程不一致。
- 排序：>50 的縫 ＞ 重疊 ＞ ≤50 的縫 ＞ 高程不一致，同級數字大的在前。
- 兩個欄位：Tolerance（預設 1mm，差這麼多以內算貼齊）、Max gap（預設 2000mm，比這寬就不是鄰居——一樓到三樓差一整層、中間夾著二樓，圖框不可能比一層窄）。Max gap 同時是外接球預篩的門檻，調大會一路放寬到全部都比（用來驗證預篩沒漏東西）。
- 點清單一列：畫兩個框的平面外框＋中間那條縫／重疊（都在兩框共用的 U 中點），CE 移到第一個框，接著直接按 Modify 分頁的 Show Box。
- 只讀不改。補縫還是走 Move Face——哪一個框該讓是製圖決定，已發出去的圖框自己長大比縫更糟。
- 順手改了 `MarkLine`：標籤空字串就只畫線不寫字（一個矩形四條線只有一條帶標籤）。Grid 那邊一律傳非空標籤，行為不變。
- 要測：`coll all box for /<proj>_DrawingPlanBox` 在沒導覽到該 SITE 時收不收得到；`list` 的 `callback` ＋ `.selection()` 回傳的是不是列文字；大 SITE 跑起來多久（n² 對，預篩過濾掉約七成）；AID 畫的矩形位置對不對；實際專案上報出來的 finding 是不是真的。
- 還沒做：Move Face 加第四種給法 `to neighbour`（貼到鄰框的面）。要改 `FaceDistance()`，而那個方法在 `feature/moveface-multi` 上被大改過，等那支實測完併回 master 再做。

## 換電腦
1. `git clone https://github.com/tw-tseng/pml-draft.git` 到 E3D 的 PMLLIB 搜尋路徑下，E3D 裡 `pml rehash all`。進行中的分支只在本機（`feature/moveface-multi`、`feature/box-neighbour-check`），要先從舊機器 `git push -u origin <branch>`，新機器再 `git checkout` 它。
2. 設使用者環境變數 `NOTION_TOKEN`。舊 token 已失效（2026-09-20 起 MCP 與 REST 都回 401 `API token is invalid`），到 notion.so/my-integrations 重新產一個，並確認 integration 有連到「E3D-管線平面圖程式摘要」那頁。
3. 重建 `.mcp.json`：
   ```json
   {"mcpServers":{"notion":{"type":"http","url":"https://mcp.notion.com/mcp","headers":{"Authorization":"Bearer ${NOTION_TOKEN}"}}}}
   ```
4. `bin/` 裡的 BlankPos.exe、RevCloud.exe 不在 repo（各 25MB），從舊機器或 `Documents\Python\blankpos`、`revcloud` 重建後手動放到 PMLLIB 搜尋路徑下的 bin。**PyInstaller 產出的是 `dist\start-完整版06.exe`，要改名複製成 `bin\BlankPos.exe`**——2026-09-21 就是 build 完沒部署，出圖一整天都在吃舊 exe，表現得跟「改了沒用」一模一樣。改完 exe 先 `ls -la bin/` 對時間戳。
5. Claude Code 的 memory 在 `%USERPROFILE%\.claude\projects\<repo路徑編碼>\memory\`，整個資料夾複製過去就接得上；沒複製的話，本檔加 Notion 也夠開工。
