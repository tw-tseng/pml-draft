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

## 換電腦
1. `git clone https://github.com/tw-tseng/pml-draft.git` 到 E3D 的 PMLLIB 搜尋路徑下，E3D 裡 `pml rehash all`。
2. 設使用者環境變數 `NOTION_TOKEN`（值在舊機器的使用者環境變數裡，不在 repo）。
3. 重建 `.mcp.json`：
   ```json
   {"mcpServers":{"notion":{"type":"http","url":"https://mcp.notion.com/mcp","headers":{"Authorization":"Bearer ${NOTION_TOKEN}"}}}}
   ```
4. `bin/` 裡的 BlankPos.exe、RevCloud.exe 不在 repo（各 25MB），從舊機器或 `Documents\Python\blankpos`、`revcloud` 重建後手動放到 PMLLIB 搜尋路徑下的 bin。
5. Claude Code 的 memory 在 `%USERPROFILE%\.claude\projects\<repo路徑編碼>\memory\`，整個資料夾複製過去就接得上；沒複製的話，本檔加 Notion 也夠開工。
