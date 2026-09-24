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
- **PML 檔要放中文，存成 UTF-8 with BOM。** E3D 的 PML 讀取器**有 BOM 就讀 UTF-8，沒有就退回 Latin-1**（一個位元組一個字元），所以沒 BOM 的 UTF-8 或 Big5 都會變亂碼。AVEVA 自己的 PMLLIB 同時示範了兩半，用的還是同一個 `°`：`common/functions/charactersymbol.pmlfnc` 有 BOM、字是 UTF-8 的 `C2 B0`，檔頭寫著 `THIS FILE MUST BE SAVED AS UNICODE UTF-8 WITH BOM`；`common/forms/gphanglemeasure.pmlfrm` 和 `psi-r2/forms/pceRtwoSettings.pmlfrm`（gadget 標籤 `'Design Temperature (°C):'`）沒有 BOM，字是 Latin-1 的單一位元組 `B0`。
- 推論：`°`、`¬` 這種落在 Latin-1 範圍內的字元，不加 BOM、直接寫單一位元組也會對（AVEVA 就是這樣用）；CJK 沒有這條路，只能靠 BOM。
- 注意 PMLLIB 裡有一百多個檔帶 BOM 但內容全是 ASCII（整個 `sai` 模組），所以「有沒有 BOM」不能拿來反推那個檔有沒有非 ASCII。
- 兩次亂碼都是同一個原因：2026-08-21 `!!alert.warning('已儲存的…')` → `å·²å„²å­˜çš„`（UTF-8 位元組被當 Latin-1）；2026-09-23 先試 Big5 也一樣（`重疊` = AD AB BD C6 → `­«½Æ`）。**判斷方式**：把畫面上的亂碼 `.encode('latin-1')` 再用原編碼 decode，解得回來就表示位元組是對的、只是讀取端用錯編碼。
- repo 裡其他檔（`Inspection.pmlfrm` 等）的中文全在註解而且沒有 BOM，等於是壞的，只是沒人看得出來——不要拿它們當先例。
- `!!alert` 的字串跟 `AID TEXT` 的標籤仍然留 ASCII：那兩條走的是對話框／命令列，不是表單顯示，還沒驗證過。
- （`DrawingPlan.pmlfrm` 從 2026-09-23 起是 UTF-8 with BOM。BOM 掉了中文就全毀，存檔前確認。）
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
  - Modify 分頁重排：頂端三步驟提示、Show Box 旁顯示目前 BOX 名稱／XYZ／U 底..頂、三個功能各自一個子框；Show Box 不再是 toggle（`feature/moveface-multi` 又改回開關，見下）。
- **還沒在 E3D 實測**：Grid 分頁 Top/Bottom U 併入分層後的結果。已實測 OK：Grid 分頁合併後能建 BOX、Bottom U 的 Pick（修過 DropPicking 順序後）；Move Face 單 BOX（2026-09-21 使用者實測，含 Enter callback 與版面）。
- 工作樹上另外有兩個舊備份的刪除（`DrawingPlan1MatchLine(20260122)/(20260311).pmlfnc`）沒進任何 commit，使用者說不要進 master。
- 討論過、沒做：Import 分頁的「兩個對角點」格式（現在只有三點法；要做的話加「3 點／2 對角點」切換，兩對角點展開成 P1/P2/P3 丟 `MakeBox`）；DESIGN 端還缺的：多選一起改高程、鄰框縫／重疊檢查＋貼齊（DRAFT MatchSorted 在邊外 50mm 找鄰居）、複製到其他樓層（使用者 2026-09-24 決定不做：只有土木鋼構改了才用得到，很少見；樓高改用多選 Move Face／Snap，插夾層用 Split U/D。真的碰到一層很多框要插夾層，先做 Split 多選，比做複製功能小很多）、圍住選取物建 BOX（2026-09-24 做了，見「Pick 分頁：圍住選取物」）、BOX 總覽清單（使用者 2026-09-24 決定不做：Assign Numbers 會把 ZONE 成員 REORDER 成號碼順序，Model Explorer 就是清單。「在 3D 每個框中心 AID 印圖號」那半也不做：框一多標籤疊在一起反而看不清楚（使用者，2026-09-24）；要確認編號順序就看 `check_batch.txt`）。
- 舊的 `develop` 分支（7 月練 git 的孤兒分支）已經不在了（2026-09-23 查）。

## Move Face 多選（2026-09-24 已併回 master，`3c50023`..`16410c8`＋merge commit，**已在 E3D 實測**）
- 4 個 commit，只動 `DrawingPlan.pmlfrm` 跟本檔，在分支 `feature/moveface-multi` 上做完、實測通過後用 `--no-ff` 併回 master，分支已刪。合併時跟 Check 分頁有兩處文字衝突（member 區塊、本檔換電腦第 1 點，兩邊都留），另外還有一處**語意衝突**是 git 看不出來的：Check 分頁點清單列時自己下 `AID CLEAR ALL`，畫面清了但 Show Box 的按鈕還停在 `Hide Box`，下一次按會變成清而不是畫。在 merge commit 裡把那兩處改成 `ClearAids()`，2026-09-24 已實測 OK。
- 面改用 North/South/East/West/Top/Bottom 命名，每個 BOX 自己取「法線最接近該方向的側面」；原因是現場同一批 BOX 的 Y 有 `N 12.523 E` 也有 `S 12.523 W`（Merge 那段註解），`+Y` 在隔壁 BOX 是反的，多選時各推各的。轉到接近 45°（內積 < cos 40°）的 BOX 分不出 N/E，跳過並回報。
- Show Box 讀 `object selection()`：選 2 個以上 DrawingPlanBox 就一起鎖定，否則退回 CE（單選不信選取——命令列導覽不會更新選取，會拿到十分鐘前點的那個）。Split 原本維持單 BOX，2026-09-24 也改成多選（`bed38fb`，2026-09-24 併回 master，**已在 E3D 實測**；使用者要 Modify 分頁三個功能都能多選，才不會搞混）：一個點、每個框被過該點且垂直於自己軸的平面切，勾 U/D 就是整排框在同一個 U 插夾層。每個框各自全有或全無（`SplitOne()`，失敗只回滾那個框），平面沒穿過的軸照舊跳過，一個框都沒切成時畫面與資訊列不動、只跳 alert。sheet texts（rev/title1~3）逐框從自己的 EQUI 讀，不再用 `split*` 那組只存第一個框的 member。已實測 OK（使用者）：單框行為不變、多選 U/D 插夾層、多選 E/W 有的框沒被穿過、全部都切不到時的 alert。rev/title 沒測：使用者說這些現在都在 DRAFT 模組處理，DESIGN 端 EQUI 上的 rev/title 不再是依據。
- Show Box 在每個側面中心印 `+X = N` 標籤；boxinfo 多選時列數量與名稱。
- 三種輸入逐 BOX 算距離：offset 同距、coordinate 各自對齊到同一座標、Pick 各自移到過該點的平面（同向一排 BOX 就是整條 match line 平移）。這個廠格線轉 12.5°，N/S/E/W 面的 coordinate 輸入會被「不與 E/N/U 平行」擋掉，改用 Pick；Top/Bottom 不受影響。
- 使用者看過第一版截圖後又改了三件事（`2034e99`、`16410c8`）：
  - Show Box 改回開關：按一下畫、再按一下清（推翻前一天「不要 toggle」的決定），用按鈕標籤解決「按了沒反應」——畫著時按鈕字變 `Hide Box`（`!this.showbox.tag = '...'`，AVEVA 先例 `aba/Forms/abaeditusertask.pmlfrm:61`）。所有 `AID CLEAR ALL` 收進 `ClearAids()`，任何分頁清畫面都會把開關歸零。隱藏不清快取、不清 boxinfo。
  - Split 的 X/Y/Z 勾選改成 E/W、N/S、U/D（gadget 改名 `splitew/splitns/splitud`），`DoSplitAt` 用 `SideNormal`+`NearestWorld` 看 BOX 的 +X 朝 E 還是 W 來對回 X/Y；offset 的 + 一律朝 E/N/U，+X 朝 W 的 BOX 會把 E/W offset 反號。
  - 最下面的 `splitresult` 結果行整個拿掉。Move Face 的結果由 Show Box 旁那行（移完 `ReadBoxes` 重讀）顯示，完全沒動到才 `!!alert.message`；Split/Merge 做完 BOX 已不在，「N box(es) created／Merged N into 1」寫到同一行。
- 已實測 OK（2026-09-24，使用者）：單選 Show Box 側面標籤方向、`AID TEXT |$!lbl|` 帶空格與 `=` 印得出來、按鈕 `.tag` 改字、Split 預設勾 U/D、多選三種給法、多選 Pick 後 ShowFaceCoord 只在座標一致時填欄位、有 BOX 出問題時 alert 一次列完（offset `-100000` 全部擋下）、一部分成功一部分失敗時成功的照移。
- Batch／Merge 各自還有一份讀選取的迴圈，新的 `SelectedBoxEquis()` 沒去動它們（怕動到已實測的東西），之後可以收成一份。

## 設備尺寸的標註點（2026-09-21，`8c69f54`＋`1c99bc6`，已在 master，**未在 E3D 實測**）
- 尺寸鏈上設備那一點，從「`SheetLimitsOfVolume()` 的紙面外接框邊緣＋2mm」改成「設備中心線的端點，落在 BOX 外就沿線夾回邊界」＝ 中心線與 matchline 的交點。
- 為什麼要夾：P1501A/B 兩台泵跨在 match line 上，WVOL 往北伸出上邊界 942mm，端點落到紙面 y=529.343，比 up 尺寸線（510.942）還高 18.4mm，投影線整條畫在尺寸線上方、伸進標籤區。
- 端點本來就在 BOX 內的不動——管線自己的位置在 BOX 內時也是就地標，設備不該被特別推到邊界。
- 除錯行 `EQUIDIM`（origin／中心線端點／有沒有夾／夾完的點）會寫進 `check_rebuild.txt`。
- 還沒決定：中心線本身要不要也畫到 matchline，讓中心線＋投影線變成連續一條；捨入／貼齊要不要收緊（目前只有 `!esh` 那層 `.string('D3')`）。

## Name 分頁（取代 Info，2026-09-24 已併回 master，分支 `feature/name-tab` 已刪，**已在 E3D 實測**）
- rev／title 改由 DRAFT 處理（使用者）。查證：`DrawingPlan1.pmlfrm:667-669` 每張圖把 `!title1..3` 設成空字串後再也沒給值，DESIGN 端 EQUI 上的 rev/title TEXT 從來沒被讀過——Info 分頁填了等於沒填，還會讓人以為改了圖上的版次。
- Info 分頁刪掉；Batch 分頁改名 **Name**（gadget 仍叫 `.batchfr`），上面「One box (CE)」：Drawing No.＋Read CE（`ReadBoxName()`）＋Rename（`RenameBox()`，沿用原本的重名檢查）；下面原本的批次編號原封不動包進子框。
- 建框／Split／Merge／Import 寫 rev/title 的程式**刻意不動**（使用者決定）：沒有輸入的地方，不會再有新值；碰那幾條要全部重測。`SetTagText`／`TagValue` 因此還在。
- Assign Numbers 的舊 bug（不是這次改出來的）：同一批框重按，第 2 次變 015～028、第 3 次回 001～014——查重名時把「這批框自己的名字」也算成被佔用。改成先算好每框號碼、只有這批以外的東西佔用才跳號，再兩段式：要換號的先 `UNNAME`（AVEVA 先例 `admin/forms/admdisciplines.pmlfrm:189`），再逐一 `NAME`，用 ref 找回框。號碼已經對的不動，結果列多一句「N already had their number」。
- Assign Numbers 另一個舊 bug：Order by 兩個 option 只設了 dtext，`.selection()` 不帶參數回的是 rtext，跟程式裡比對的字串都對不上，全部掉進最後的 else（North -> South），選什麼都一樣。改成 `.selection('DTEXT')`（AVEVA 先例 `admin/objects/admstamp.pmlobj:2477`）。**option 只有 dtext 時一律用 `.selection('DTEXT')` 或 `.dtext[.val]`**。
- Order by 的意思改了（使用者，2026-09-24，看 `check_batch.txt` 確認排序本身沒錯、是語意跟使用者直覺相反）：原本 1st＝先分組（主鍵），S->N＋Bottom->Top 會每一疊由下往上編；改成 1st＝**號碼連續時走的方向**（次鍵）、2nd＝下一排往哪走（主鍵）。標籤改 `Number along`／`Then`，gadget 名不變；程式只在收集前把兩組 axis/asc 對調。預設改成 along W->E、then Bottom->Top（同層由西往東、再往上一層）。每次按都把排序過程寫到 `check_batch.txt`（BATCH／KEYS／IN／ORDER／OUT）。第三個方向 `And then`（`.batchdir3`，使用者要求，預設 (none)）：三個選項由快到慢，排序鍵反過來由慢到快（key1＝最慢的那個有用的），(none) 直接略過；解讀選項收成 `BatchDir()`、取座標收成 `BatchKey()`，最後一個鍵不帶容差、前面的鍵差 1mm 內算平手。
- 「跳號」其實是 Model Explorer 照建立順序列 ZONE 的成員、不照名字（check_batch 的 OUT 顯示 001～014 一個不缺）。Assign Numbers 編完號後，每個框 `REORDER` 到前一號後面（CE 在 owner，先例 `admin/forms/admmaturity.pmlfrm:425`），不同 ZONE 各自排、這批以外的框不動；dump 多一行 `ORDER n moved, m would not move`。
- 已實測 OK（2026-09-24，使用者）：Read CE、Rename、重名被擋、空欄位的 alert、Assign Numbers 連按結果不變、兩個／三個方向的排序、Model Explorer 照號碼排。

## Pick 分頁：圍住選取物建 BOX（2026-09-24，分支 `feature/box-around-selection`，**未在 E3D 實測**）
- 給不照格線切的局部圖用（泵區、單台設備；使用者說有可能會出）。Pick 分頁下方子框「Around the selection」：Margin（預設 500mm，六個面同一個值，使用者選的）＋ Box Around Selection 鈕。
- 框**照正東正北**（使用者選的）：範圍是每個選取物 `WVOL` 的聯集（讀法同 `DrawingPlan1.pmlfrm:728`，`part(1..6)`＝min E N U、max E N U）。不做跟格線轉 12.5° 的版本，因為 `WVOL` 永遠是世界軸，順著格線的一段管子換算到轉過的方向會寬出好幾公尺，要準就得逐一讀管件中心線點，程式量多好幾倍。
- 選取裡的 DrawingPlanBox 自己的框、沒有範圍（WVOL 全 0 或讀不到）的元素都跳過並計數；建出來的框沒命名，走 Name 分頁。結果寫在鈕旁邊：名稱、X/Y、U 底..頂、用了幾個、跳過幾個。
- 要測：選一台設備、選幾條管線＋設備、Margin 0 與 500、選取裡混一個圖框（要被跳過）、什麼都沒選的 alert、建出來的框在 DRAFT 出局部圖的範圍對不對。

## Check 分頁：框與框之間的縫／重疊／高程不一致（2026-09-23 已併回 master，`0b959c3`..`5f645cd`，**已在 E3D 實測**）
- 18 個 commit，從 master 開出來後 fast-forward 併回，分支已刪——fast-forward 沒有 merge commit，master 的歷史就是那條分支的歷史，分支名留著只是個重複的標籤。只動 `design/forms/DrawingPlan.pmlfrm`（+1541 行）與本檔。跟 `feature/moveface-multi` 之後合併只有 **2 個衝突點**，都是「兩邊在同一位置各加了幾行」：本檔換電腦第 1 點、`.pmlfrm` 的 member 區塊（一邊 `chk*` 一邊 `mf*`，兩邊都留即可）。
- 為什麼做：DRAFT 的 `DrawingPlan1MatchSorted` 只在框線外 50mm 的薄片裡收鄰框（`MatchSorted.pmlfnc:47-68`），縫大於 50 就沒有鄰框，`MatchLine1.pmlfnc:94` 整段標籤被跳過——沒有 tick、沒有 `MATCH LINE Exxxxx`、也沒有 `SEE <鄰圖號>`。縫上的廠房兩張圖都沒有；重疊則是同一段畫兩次。都要等出圖才發現。
- 分類：每一對 BOX 在**第一個 BOX 自己的座標系**比三個區間（格線轉 12.5 度，用世界 E/N 比會把對齊的兩框讀成兩軸都重疊）。看幾個軸分開：≥2 軸＝對角或不相鄰；1 軸＝有縫；0 軸但有一軸在容差內＝正常貼齊；0 軸＝重疊（取最小貫入）。（高程不再從這裡報，見下一條。）
- **高程是以「高程面」為單位報，不是一對一對**（`90f5652`，使用者指出同一個問題被報兩次）：一個框的某個面放錯高程，會跟上下的鄰框報一次縫、跟左右的鄰框報一次高程差；實測那個模型 3 個缺陷產生 5 列，而且其中一個被 `max(dbot,dtop)` 蓋掉。改成：先把框分成「站在同一塊地上」的群組（footprint 相接或重疊，可遞移，不同區可以有自己的樓層高度），群組內收集所有頂／底面高程排序後切成高程面（距該面**第一個**面超過 Max gap 就另起一個，用第一個而不是前一個量，免得一串各差一點的面被串成同一個），每個面取眾數當「應該是多少」（平手取低的，由低往高走訪），差超過容差的就是要改的框。**一列一個面**（`高程面 104880  =23718/1687 頂 低 100mm`），不是一列一個高程面——高程面的「差多少」是那個面上最大的偏差，不是任何一個框要移動的量，寫在「N 個框要改」旁邊會被讀成每個都差那麼多（使用者指出，2026-09-23）。一個面仍然只報一次，不管它跟幾個鄰框對不上。U 向的縫／U 向的重疊／高程差三種列全部收掉；U 向重疊只有在一個框的 U 範圍整個包住另一個時才留（那才是真的畫兩次）。
- 排序（rank 乘數 1e8，不是 1e6——高程要放進鍵裡，間距不夠寬會讓列跑出自己的區塊）：
  `4` >50 的平面縫 ＞ `3` 重疊 ＞ `2` 高程面 ＞ `1` ≤50 的平面縫。平面的列同級照數字大的在前；**高程面自成一區、依高程由低往高**（使用者要求，2026-09-23，跟樓層走向與 Batch 預設的 Bottom→Top 一致），同一面內用 `偏差*0.001` 破平手（偏差大的在前），那個量對「兩個高程面至少相隔 Max gap」來說小到不可能跨面。
- **只碰到一條邊不算相鄰**（`6e69aac`，使用者實測誤報）：先數有幾個軸在容差內（`!ntouch`），兩個以上就是共用一條邊或一個角、不是一個面。沒有面就沒有 match line，高程差不報（`axis` 給 `'EDGE'`，`ChkWhat` 只認 `'X'`／`'Y'`）；縫也一樣，另外兩軸有一個是邊緣共線的話那條縫沒有厚度，裡面沒東西會漏。沒修之前，一個框疊在另一個上面、側面又剛好共平面，會報出「高程差 = 較高那個框的高度」。
- U 方向的縫不要寫成「DRAFT 找不到鄰框」：`MatchSorted` 只往 view 的左右上下（平面四邊）收鄰框，從不看 U，50mm 那條規則對上下相鄰的框不適用。真正的代價是兩層之間那一段兩張圖都沒有（BOX 在 U 上也裁自己的 view）。
- 兩個欄位：Tolerance（預設 1mm，差這麼多以內算貼齊）、Max gap（預設 2000mm，比這寬就不是鄰居——一樓到三樓差一整層、中間夾著二樓，圖框不可能比一層窄）。Max gap 同時是外接球預篩的門檻，調大會一路放寬到全部都比（用來驗證預篩沒漏東西）。
- 點清單一列：平面的縫／重疊 → 畫兩個框的平面外框＋中間那條縫／重疊（都在兩框共用的 U 中點）；高程面 → 把那個面上所有框各自畫在**它自己那個面的高度**（對齊的疊在一起，偏掉的標 `top-100`／`bot-10`）。兩種都把 CE 移到**該列的那個框**，接著用 Modify 分頁的 Show Box／Move Face。
- 只讀不改。補縫還是走 Move Face——哪一個框該讓是製圖決定，已發出去的圖框自己長大比縫更糟。
- 順手改了 `MarkLine`：標籤空字串就只畫線不寫字（一個矩形四條線只有一條帶標籤）。Grid 那邊一律傳非空標籤，行為不變。
- 整個分頁是中文（說明、欄位、按鈕、清單）。先試 Big5 失敗（`ee63e50`，使用者實測是亂碼），改成 UTF-8 with BOM（`152be11`）。顯示用的字詞在 `ChkWordZh()`／`ChkSideZh()`，`ChkWhat()`／`ChkCompass()` 仍回 `GAP`／`N` 那組 ASCII 代碼給分支比較與 AID TEXT 用。清單每列控制在 62 格內（CJK 算兩格）。
- **每次按檢查都會把過程寫到 `check_box.txt`**（`23c2987`，L: 對應這台的 D:，已 gitignore）：`CHECKBOX` 設定／`BOX` 每個框的 E N U、XYZ、U 底..頂、兩個平面軸、外接球半徑／`PAIR` 每一對的 `o=`（B 心在 A 座標系）`g=`（三軸相距，負的是重疊）`npos= ntouch=` 與判定結果／`SKIP` 被預篩擋掉的（中心距與門檻）／`ROW` 真的進清單的。`PAIR` 那行是 `ChkPair` 在分類的當下寫的，用的就是分支讀到的同一組變數——對不起來的 dump 比沒有 dump 更糟。**有 finding 看起來不對，先看這個檔，不要看截圖。**
- **已實測 OK**（2026-09-23，使用者）：`coll all box for /<proj>_DrawingPlanBox` 不導覽就收得到、比對、清單、中文顯示、`list` 的 `callback` ＋ `.selection()`（回傳列文字）、點列畫 AID ＋ CE 導覽、高程面那一路（分群／分面／一列一個面／依高程排序）、`check_box.txt` 寫檔。
- **還沒試過**：大 SITE 跑多久（n² 對，預篩過濾掉約七成；`SKIP` 行也是 n² 級，太慢就先把它拿掉）；實際專案上報出來的 finding 是不是真的；**樓高小於 Max gap 的區域會不會把兩個真實高程面併成一個**（這次模型樓高都 2840 以上所以沒遇到，遇到就把 Max gap 調小）。
- Move Face 第四種給法 `to neighbour`（Snap 鈕，2026-09-24 已併回 master，`5bf07e7`，**已在 E3D 實測**）：沿用 Face 選單選的面，每個選到的 BOX 自己找「那個面正對的最近鄰框」貼過去——有縫往外長、有重疊往內縮。鄰框的條件在 `NbDistance()` 的註解：面要平行（1°）、中心在本框中心前方、在面的兩個軸上都共用超過 Check 的容差（面對面，不是只碰到邊）、距離不超過 Check 的 Max gap。好幾個符合時貼 |距離| 最小的（使用者決定，2026-09-24），跟其他鄰框剩下的縫／重疊交給 Check 分頁抓。讀全部框借 `ChkReadAll()`，讀完把 `chk*` 陣列還原——Check 清單的列用 index 指那些陣列，中間做過 Split／Merge 的話重讀會讓舊列指到別的框。已實測 OK（使用者）：單框 N/S/E/W/Top、有縫與有重疊、多選一排框一起貼、沒有鄰框時的 alert、做完回 Check 分頁點舊的列仍畫對。

## 換電腦
1. `git clone https://github.com/tw-tseng/pml-draft.git` 到 E3D 的 PMLLIB 搜尋路徑下，E3D 裡 `pml rehash all`。有只在本機的進行中分支的話，先從舊機器 `git push -u origin <分支>`，新機器再 `git checkout` 它（`git branch -vv` 沒有 `[origin/...]` 的就是只在本機）。
2. 設使用者環境變數 `NOTION_TOKEN`。舊 token 已失效（2026-09-20 起 MCP 與 REST 都回 401 `API token is invalid`），到 notion.so/my-integrations 重新產一個，並確認 integration 有連到「E3D-管線平面圖程式摘要」那頁。
3. 重建 `.mcp.json`：
   ```json
   {"mcpServers":{"notion":{"type":"http","url":"https://mcp.notion.com/mcp","headers":{"Authorization":"Bearer ${NOTION_TOKEN}"}}}}
   ```
4. `bin/` 裡的 BlankPos.exe、RevCloud.exe 不在 repo（各 25MB），從舊機器或 `Documents\Python\blankpos`、`revcloud` 重建後手動放到 PMLLIB 搜尋路徑下的 bin。**PyInstaller 產出的是 `dist\start-完整版06.exe`，要改名複製成 `bin\BlankPos.exe`**——2026-09-21 就是 build 完沒部署，出圖一整天都在吃舊 exe，表現得跟「改了沒用」一模一樣。改完 exe 先 `ls -la bin/` 對時間戳。
5. Claude Code 的 memory 在 `%USERPROFILE%\.claude\projects\<repo路徑編碼>\memory\`，整個資料夾複製過去就接得上；沒複製的話，本檔加 Notion 也夠開工。
