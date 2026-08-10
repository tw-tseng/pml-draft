# DrawingPlan1 開發筆記

> 本檔案記錄與 Claude 討論的進度，供下次繼續。目錄結構、程式細節請以實際程式碼為準（此檔可能與程式不同步）。

## 目前狀態（2026-07-23）

使用者發現 `d:\E3D\pdms_prog\E3D2.1\PA_pmllibE3D2.1` 這個目錄不是最新版本，**要先更新程式**，之後再回來繼續下面的討論。

## 已改：LINE NO. 標註在「box 相對世界座標歪一個角度」時（2026-08-10，**尚未實機驗證**）

使用者實機驗證結果：**正的 box（不管 rcode = up 或 left）都正確**；但 box 在模型裡歪一個角度時，標註會飛到圖框外很遠的地方（見 `2026-08-10_10-18-51.png`）。

### 原因

`.Apply()` 對歪的 box 會下 `Adegrees`（`forms/DrawingPlan1.pmlfrm:585-590`），讓 box 在圖紙上還是方的。於是：

1. **搜尋範圍錯邊**。`COLLECT ... WITHIN <p1> TO <p2>` 只吃「與 E/N/U 平行」的體積，但「view 右側往內 10mm」這個帶狀區在模型裡是一個**轉了角度的長方體**。原本程式直接用 `!!DrawingPlan1.maxE/minE/maxN/minN` 圍出的世界座標帶，對歪的 box 來說既漏抓（真正靠 view 邊界的管沒被抓到）又多抓（抓到斜切過去、其實在 view 中間的管）。
   - 另外 `.Apply():460-469` 的 `maxE/minE/maxN/minN` 是用 box 的**面中心**算的，歪的 box 連 bounding box 都不是。
2. **交點跑到圖框外**。`!!DrawingPlan1.viewRlinesh` 等是 `object line`，`.intersection()` 把它當**無限長直線**。多抓到的元件往邊界射線一打，交點就落在 view 外面，尺寸線因此延伸到圖框外老遠。

### 作法：全部改用圖紙座標

view 在圖紙上永遠是方的，所以把「哪一邊、多寬的帶」通通定義在圖紙座標，交給 `WITHIN` 的則是**包住那個帶的世界座標方盒**（一定是超集合，不會漏），再用第二道檢查把方盒角落多抓到的丟掉。

`forms/DrawingPlan1.pmlfrm` 新增 4 個 method（放在 `.CheckDimensionAttachPoint()` 前面）：

| method | 用途 |
|---|---|
| `.ViewSheetTransform()` | 從 view 本身量出「世界 ↔ 圖紙」的 2×2 矩陣（含 vsca、ADEGREES、RCODE）。回傳 10 個數，第 10 個是「view 在圖紙上是不是正的」旗標 |
| `.SheetBandOfSide(!dir, !depth)` | 圖紙座標下，view 某一邊往內 !depth mm 的帶，回傳 x1,y1,x2,y2 |
| `.WorldLimitsOfSheetRect(...)` | 包住某個圖紙矩形的世界方盒，回傳 minE,minN,maxE,maxN，直接餵給 `WITHIN` |
| `.SheetLimitsOfVolume(!wvol, ...)` | 某元件 WVOL 在圖紙座標的外框，回傳 x1,y1,x2,y2 |
| `.CheckInSheetBand(!elem, !band, !trans)` | 元件是否真的伸進那個帶。**box 是正的時候（`!trans[10]` = 1）直接回 true 不讀 wvol**，所以正的圖速度跟以前一樣 |

`functions/DrawingPlan1LineNoAnnotation.pmlfnc`：

1. 函式開頭算一次 `!trans` 和 view 的圖紙矩形 `!vwx1/!vwx2/!vwy1/!vwy2`。
2. 每個 side 算三種帶深（圖紙 mm）：`!bandthin` = 模型 10mm（抓穿過邊界的管，TYPE 1）、`!banddeep` = view 的 33%（TYPE 2a/2b/3）、`!bandshal` = 10%（設備）。**帶深改用 view 在圖紙上的尺寸**，因此也順便修掉「`.Apply()` 會把 xlength/ylength 對調、但這支函式固定拿 boxXlen 當 E 方向」的舊 bug。`!boxXlen`/`!boxYlen` 兩個參數已不再使用（簽名保留，呼叫端不用改）。
3. 5 個搜尋體積（TYPE 1 / 2a / 2b / 3 / equipment）全部改成 `SheetBandOfSide` + `WorldLimitsOfSheetRect`，迴圈裡多一道 `CheckInSheetBand`。
4. 設備的「大部分體積在 view 內」「pos 在 view 內」兩個檢查、TYPE 4 的「hpos/tpos 在 view 內」檢查，都改用圖紙座標比對 `!vwx1..!vwy2`。
5. 交點加上邊界檢查：落在 view 圖紙矩形外（±1mm 容差）就丟掉，尺寸不會再延伸到圖框外。

### 已改：只有直管的管線標不出編號（2026-08-10，**尚未實機驗證**）

症狀：管線在圖面上有管件時會標編號，只有直管的就不會。

原因在 TYPE 1 這段：

```pml
var !mems coll all bran members within $!vlfm to $!vlto
!mem = !mems[$!i]
var !type type of $!mem
if (!type.matchwild('*TUB*')) then
	var !mem mtbe of $!mems[$!i]     -- 直管 → 它「離開」的那個元件（或 BRAN）
endif
...
if (!type.eqnocase('BRAN')) then
	var !memenupos hpos of $!mem     -- 拿到的是 branch 頭的位置
```

一段沒有管件的直管**本身不是元素**，收集回來的是 implied tube（`ileave tube of /XXX`），`MTBE` 把它換成「這根管離開的那個元件」，可能是 BRAN，也可能是圖面另一頭的某個管件。程式接著就拿**那個元件的位置**去標，而不是這根管的位置。

box 是正的時候看不出來：穿過邊界的管一定跟邊界垂直，而尺寸線也是垂直射向邊界的，所以不管從管上哪一點射，落在邊界上的位置都一樣（沿邊界方向的座標相同），碰巧是對的。box 一歪，管跟邊界變成斜交，從老遠那個元件垂直射過去就落在邊界上的**別的地方**，甚至落到邊界線的延長線上（第一張圖那些飛出圖框的尺寸就是這樣來的）；加了邊界檢查之後這些點被丟掉，於是變成「只有直管就不標」。

改法：

1. `forms/DrawingPlan1.pmlfrm` 新增 `.CrossingOfTube(!elem, !dir)`：沿著這根管本身算出它跟 view 某一邊的交點（世界座標）。取管的起點/方向用的是這個 repo 既有的寫法（`E3dDraftModify.pmlfrm:58-74`、`DrawingPlan1FlowAnnotation.pmlfnc:169-174`）——BRAN 用 `hposition`/`hdirection`，元件用 `pl pos`/`pl dir`。
2. TYPE 1 迴圈：是直管的話，位置改用這個交點，**但高程沿用原元件的**（`!crosspos.up = !memenupos.position().up`），這樣 BOP 標註不受影響。
3. 產生 DPOI 的那個迴圈原本會**重新**去問元件位置（`var !mempos hpos of $!mem`），這樣就把上面算好的交點丟掉了。改成直接讀 `!result` 字串裡本來就存著的位置（split `'!'` 的第 2、3 欄）。順帶修掉一個舊 bug：**TYPE 4 用 tpos 的那些項目**，原本在這裡一律被重新當成 `hpos`。

只動 TYPE 1。TYPE 2a/2b（穿過上下 match line 的管）不用改 —— 那些是垂直/傾斜管，`pl pos` 跟管在平面上的位置本來就在同一點。

### 已改：同一條管在同一邊標了兩次（2026-08-10，**尚未實機驗證**）

症狀：左側出現兩個一模一樣的 `300-A-42 BOP EL+106460`，相距 140mm。

原因是上面那個 `.CrossingOfTube()` 用的是**通過這根管的無限長直線**跟邊界求交點。管線在邊界附近轉彎時，彎頭前後兩根管的「直線」都會切到那條邊界線，位置差一點點，但實際上只有其中一根真的碰得到邊界 —— 於是同一條管就標了兩次。（view 轉角度時特別容易發生，因為交給 `WITHIN` 的世界方盒比實際帶狀區大很多，本來就會多收元件進來。）

改法：`.CrossingOfTube()` 多吃一個參數（收集回來的 implied tube 本身），用 `ITLE` 取得管長算出管的另一端，再檢查交點是否**落在這根管的兩端之間**（圖紙座標比距離，兩端各留 1mm 容差，給剛好落在邊界上的彎頭）。

- 確定「這根管碰不到這條邊界」→ 回傳 `'NONE'`，呼叫端直接把這個元件丟掉。
- 「算不出來」（`pl pos`/`pl dir` 讀不到、兩線平行、`ITLE` 讀不到）→ 回傳 `''`，呼叫端維持原本用元件位置的行為，不會因此少標。

如果之後還看到同一條管在同一邊重覆標，下一個可以動的地方是 TYPE 1 的去重門檻：目前只濾掉圖紙上相距 **1mm** 以內的（TYPE 2/3/4 對 TYPE 1 去重用的是 4mm）。把 TYPE 1 那個 1 改大、或再加一條「同一條 pipe 且相距在 4mm 內就只留一個」即可。

### 已改：標註線從管件旁邊 3mm 開始，不再一律從 view 邊界開始（2026-08-10，**尚未實機驗證**）

需求：原本四邊的標註線都是從 view 邊界外 3mm 起算，看不出來是在標哪一根；沒有跑到 view 邊緣的管線，希望改成從**管件旁邊 3mm** 開始畫。

作法很小：DPOI 的位置原本一律用「從元件往邊界垂直射出去的交點」，改成直接用**元件自己的位置**，後面那個 `gridgap`（3mm）照舊往外推。

```pml
!attapos = object position(!temppos)          -- 邊界交點
if (not(!type.eqnocase('EQUI'))) then
	!attapos = object position(!mempos)       -- 改用元件自己的位置
endif
!attapos = !attapos.offset(!viewdir.direction(), !!DrawingPlan1.gridgap.val / !!DrawingPlan1.vsca)
```

為什麼這樣就夠：交點本來就是從元件垂直射向邊界得到的，所以**沿邊界方向的座標跟元件完全相同**，只有深度不同。換成元件位置只是把起點往內拉，尺寸線上的位置不會跑掉。

- **穿過邊界的直管不受影響**：上一輪已經把它的位置設成「管跟邊界的交點」，所以 `!mempos` 本來就在邊界上，加 3mm 之後跟以前一模一樣。
- **設備（EQUI）維持在邊界**：它的位置是設備中心，從中心起算會把投影線畫穿整個設備。若之後想改，比較好的作法是取設備 wvol 靠邊界那一側再加 3mm，而不是用中心。

**要看的地方**：`DOFFSET 15 / -15` 是相對「第一個 dimension point」量的，如果 AVEVA 是這樣定義，尺寸線的位置就取決於排序後第一個點的深度。程式在每一邊都會補兩個「limits」DPOI 在 view 的兩個角上（一樣在邊界外 3mm），`SORT DIM` 之後它們會排在頭尾，所以尺寸線應該還是留在原位。**如果尺寸線跟著往內跑了**，就是這個假設錯了 —— 那段補角點的程式有個「附近 5mm 內已經有點就不補」的條件（`!run = false`），把那個條件拿掉、讓角點一定存在，就會回到原位。

### 已改：柱位線的尺寸也延伸到柱位線末端前 3mm（2026-08-10，**尚未實機驗證**）

症狀：柱位線的尺寸標註，投影線只從 view 邊界畫到尺寸線，跟柱位線本身之間空一大段，看起來是斷開的。

原因：`DrawingPlan1GridAnnotation.pmlfnc` 算柱位線跟 view 四邊的交點時，用的是 `object line` 的 `.intersection()`，而它是**無限長直線**求交點。柱位線在模型裡的長度如果沒有到 view 邊界（常見，柱位線只畫到最後一根柱），交點仍然算得出來、尺寸點也照樣產生，但那個點所在的位置根本沒有柱位線。

改法（跟管線編號那次同一個概念：投影線起點拉到被標的東西旁邊 3mm）：

1. `forms/DrawingPlan1.pmlfrm` 新增 `.NearEndOfGrid(!gridline, !p1sh, !p2sh, !intpt)`：回傳柱位線上離交點最近的點 —— 交點真的落在線段上就回傳交點本身，否則回傳比較近的那個端點。
2. `functions/DrawingPlan1GridAnnotation.pmlfnc`：往 `.allintersections` 塞資料時，在後面接 `'~' & <柱位線末端>`。**`.intersections` 本身不動**，那兩個 `.CreateGridSymbol*()` 還在讀它，格式一改就會壞。
3. `functions/DrawingPlan1LineNoAnnotation.pmlfnc` 的柱位線尺寸迴圈：尺寸點的**深度**改用柱位線末端（夾在 view 範圍內），後面原有的 `gridgap`（3mm）照舊往外推。

**沿邊界方向的座標維持用原本的交點**，只換深度 —— 否則柱位線斜的時候，點沿著柱位線移動會改變它投影到尺寸線上的位置，尺寸數字就變了。

字串格式：`.allintersections` 的內容從 `viewDlinesh-E .. N .. U ..` 變成 `viewDlinesh-E .. N .. U ..~E .. N .. U ..`。原本讀邊界點的 `.split('-').getindexed(2).before('U')` 不受影響（`before('U')` 會在第一個位置的 U 就切掉）；讀末端用 `.split('~').getindexed(2)`。舊格式（沒有 `~`）會落到 `handle any`，維持用邊界點。

### 已改：`Start and End Positions of Line passed to method are Coincident` 警告（2026-08-10）

平面圖上，**往上或往下走的管**投影出來就是一個點，兩端在圖紙上重合。把這種退化的 `object line` 丟給 `.intersection()`，E3D 就會發這個警告（訊息碼 2,876），而且本來也算不出東西來。

兩個地方加了防呆，都是先量兩端在圖紙上的距離，小於 0.001mm 就不建線：

- `.CrossingOfTube()`：回傳 `''`（不是 `'NONE'`），讓呼叫端沿用元件位置 —— 對垂直管來說那本來就是同一個平面位置，結果不變。
- `.NearEndOfGrid()`：直接沿用邊界上的交點，不呼叫 `.on()`。

### 陷阱：那行 `$p $!intpt` 是有作用的，不能只註解掉

原本 `!intpt` 附近的結構是：

```pml
!intpt.delete()          -- 每圈先清掉
...
!intpt = <兩條線求交點>   -- 平行時會 raise，!intpt 維持未定義
$p $!intpt               -- !intpt 未定義時，這行會 raise
handle any
elsehandle none          -- 只有上面沒 raise 才進來
	var !temppos enupos of $!intpt
```

也就是說**那個 `$p` 不是除錯殘留，它是「跳過沒有交點的元件」的觸發器**。把它註解掉，`handle any` 就沒有東西可攔，`elsehandle none` 每圈都會執行，於是 `enupos of $!intpt` 直接爆 `ERROR - Variable INTPT not defined`（2026-08-10 實機遇到）。

已改成不依賴 `$p`：用 `!ptok` 旗標（`!intpt.part(2)` 讀不到 → `handle any` 設 false），後面 `handle any / elsehandle none` 換成 `if (!ptok) then ... endif`。現在那行 `$p` 可以放心留著註解或整行刪掉。

**上一輪加的 `!mdir`（rcode 的 sheet→model 對照表）已經拿掉** —— 帶改用圖紙座標定義後，`viewULsh` 等角點本來就已經被 `.Apply()` 轉過了，rcode 自動涵蓋，不需要再對照一次。`!shdir`（圖紙方向）保留。

### 要看的地方

1. **正的 box 應該完全沒變**：`!trans[10]` = 1 走快速路徑，`WorldLimitsOfSheetRect` 算出來就是原本那個帶（差 `.Apply()` 那個 ±0.025mm 圖紙容差，換算回模型大約 1mm，可忽略）。若正的圖跑出來不一樣，代表矩陣量錯了。
2. **歪的 box 會變慢**。TYPE 1 的帶又細又長，轉 45 度時它的世界方盒接近整個 view，`WITHIN` 會抓進很多元件，每個都要讀一次 `wvol`。如果慢到不能接受，可考慮把細帶切成幾段分別收集。
3. `wvol` 讀不到的元件一律**保留**（跟以前一樣不過濾），不會因為讀不到就漏標。

## 已改：LINE NO. 標註在 rcode = left（2026-08-10，rcode 部分使用者已驗證正確）

改的是 `functions/DrawingPlan1LineNoAnnotation.pmlfnc`。

核心觀念：函式裡的 `!dir`（`right/left/down/up`）**一直都是「圖面上 view 的哪一邊」**（跟 `DrawingPlan1MatchLine1.pmlfnc` 的 `!dir` 同義），但原本抓元件的搜尋範圍卻直接把它當成模型方向用（right→maxE、up→maxN…）。rcode = up 時兩者剛好相同，rcode = left 時 view 在 sheet 上逆時針轉 90 度就對不起來了。

換算（與 `.Apply()` 951-966、`.CreateGridSymbol*()` 同一式：view x = sheet y、view y = -sheet x）：

| 圖面邊 !dir | 模型邊 !mdir | 模型範圍 |
|---|---|---|
| right | down | minN |
| left | up | maxN |
| up | right | maxE |
| down | left | minE |

> **後續**：下面的 `!mdir` 已在同日「box 歪一個角度」那次改動中拿掉，改用圖紙座標定義帶狀區，rcode 自動涵蓋。這段留著是為了記錄圖面邊 ↔ 模型邊的對照關係（上表仍然有效，MatchLine1 的 rcode = left 分支就是照這張表）。`!shdir` 保留。

實作：迴圈開頭算出兩個新變數，其餘照舊

1. `!mdir`：rcode = left 時依上表轉換，否則 `= !dir`。**只有搜尋體積**改用它 —— TYPE 1 / 2a / 2b / 3、equipment 體積、equipment 的 `wvol` 檢查、equipment 的「pos 是否在 view 範圍內」檢查。
2. `!shdir`：`!dir` 的**圖紙座標**方向（right→E、left→W、up→N、down→S）。原本 `!templine` 是拿 `!viewdir.direction()`（模型方向）去偏移一個 `shpos`（圖紙座標）再跟 `viewRlinesh` 等求交點，混用了兩個座標系；rcode = up 又沒斜角時剛好等價，rcode = left 就完全錯邊。

**沒有動**的部分（這些本來就是圖面座標，用 `!dir` 是對的）：排序 `method('y'/'x')`、4mm 去重、`CheckDimensionAttachPoint` 的 `x/y` + `max/min`、`viewRlinesh/viewULsh` 等邊界線與角點、`DIR` / `DOFFSET`、`Dtangle` + `Dtoftx`、`Pltxt` 前後補空白。

**兩個假設，實機跑第一張圖時要看**：

1. **`VIEWDIR <dir>` 有跟著 rcode 轉**（即回傳「在圖紙上朝該方向的模型方向」）。依據：`.Apply()` 對斜的 box 會下 `Adegrees`，而 MatchLine1 用 `!viewdir.direction().eq(E/W/N/S)` 來判斷能不能寫出座標值 —— 只有 VIEWDIR 含 view 在圖紙上的旋轉，這個判斷才有意義。若實際上 VIEWDIR **不含** rcode，則要改的只有三行：`var !viewdir viewdir $!dir` → `$!mdir`，以及函式開頭的 `!viewdirdown` / `!viewdirright` 也要照表轉換。
2. **`Dtangle Horizontal/Vertical` 是相對圖紙、不是相對 view**。依據：製圖上 HORIZONTAL 的意義就是「在紙上是橫的」（否則跟 PARALLEL 沒差別）。若第一張圖跑出來字的方向轉錯 90 度，就是這個假設錯了，把最後那段 `Dtangle Horizontal` 跟 `Dtangle Vertical` 兩組對調即可（`Dtoftx` 的 X/Y 可能也要跟著換）。

## 已修：柱位線標註在 rcode = left 時方向錯誤（2026-08-07）

症狀：勾選 "Portrait to Landscape" 讓 view 轉 90 度後，grid 圓圈往格線左側偏移（應往外），圓圈內文字被轉成直排。

原因：`shpos` 回傳的是 **sheet 座標**，但 SLAB 的 `XYPO` / `APOF` 是 **view 座標**。`.Apply()` 的 `RCODE LEFT`（`forms/DrawingPlan1.pmlfrm:740` 附近）讓 view 在 sheet 上逆時針轉 90 度，兩個座標系差 90 度。`DrawingPlan1GridAnnotation.pmlfnc` 與 `.CreateGridSymbol*()` 原本完全沒有 rcode 分支（MatchLine / LabelSpace 那幾處都有）。

換算式（與 `.Apply()` 處理 LabelSpace.txt 標籤的 951-961 行同一式）：

- `view x = sheet y`、`view y = -sheet x`
- **AGSIDE 不換算**。使用者確認：不管 rcode 是 up 還是 left，在圖面上位於 view 左邊的柱位線 agside 就是 `Left`，其餘三邊依此類推。曾經一度加了 Top→Right 那組對應，是錯的，已移除。
- **`ADEGREES -90`**：rcode = left 時 SLAB 要加這個屬性，圓圈內的文字才會轉正（使用者指定的值）。

改動（皆在 `forms/DrawingPlan1.pmlfrm`）：

1. 新增 `member .rcode is string`，`.DrawingPlan1()` 初始化為 `'up'`
2. `.Apply()` 的 `var !rcode rcode` 後面加 `!this.rcode = !rcode`
3. `.CreateGridSymbolwithIntersection()` 與 `.CreateGridSymbol()` 在 `NEW SLAB` 之前，若 `!this.rcode` 是 `left` 就換算 `!x/!y/!xap/!yap`；`NEW SLAB` 之後補 `Adegrees -90`

**尚未處理（使用者指定之後再做）**：
- `DrawingPlan1GridAnnotation.pmlfnc` 的 `intersections.unique()`：使用者確認 PML 的 `unique()` 會就地修改原陣列，這行有作用，不要動。

## 已修：柱位線「只標一邊 / 位置飛掉」（2026-08-07，已驗證）

症狀：一張圖 5 條 refgln 產生 10 個 SLAB，但只有 5 個位置正確，另外 5 個跑到圖框外很遠的地方。

用暫時性 `$p` 除錯輸出跑一張圖，log 證實：

- `!!DrawingPlan1.intersections` 每張圖只在 `.Apply()` 清一次，`DrawingPlan1GridAnnotation.pmlfnc` 每條 refgln 都往裡面 append 不清空 → `int.size` 累積成 2 → 2 → 4 → 6 → 8 → 10
- `!total` 的判斷寫死用 `getindexed(1)/(2)`，第二條以後永遠讀到第一條 refgln 留下的交點 → `.on()` 恆為 false → **`!total` 全部變 0**
- 結果 `total=2` 和 `total=1` 兩個分支從來沒被執行過，`.CreateGridSymbolwithIntersection()` 一次都沒被呼叫，10 個 SLAB 全來自 `total=0` 分支
- `.CreateGridSymbol()` 在 `dist < 100` 時會拿 `intersections[!i]` 當基準算座標，讀到別條格線的交點就把標註帶偏（實測有一筆往左偏 81.8mm）；`!agside` 也全是撿別條的

修法：`.intersections` 恢復成「當前這條 refgln 的交點」，新增 `member .allintersections` 累積整張圖的交點：

1. `forms/DrawingPlan1.pmlfrm`：新增 `member .allintersections is array`，`.Apply()` 內與 `.intersections` 一起 `object array()` 重設
2. `functions/DrawingPlan1GridAnnotation.pmlfnc`：每條 refgln 開頭 `!!DrawingPlan1.intersections = object array()`；`unique()` 後把內容 append 進 `.allintersections`
3. `functions/DrawingPlan1LineNoAnnotation.pmlfnc:702`：柱距尺寸改讀 `.allintersections`（內容與順序不變，行為應相同）

兩個 `.CreateGridSymbol*()` method 不需要改。

診斷過程用的暫時性 `$p` 除錯輸出已全部移除。（`DrawingPlan1GridAnnotation.pmlfnc` 第 97 行的 `$p $!p1dirsh` 是本來就有的，不是這次加的，保留未動。）

### 過程中排除掉的兩個誤判（留著避免重踩）

- **「10 個 SLAB 只顯示 5 個」不是程式問題**。E3D 的 view 有 AGSIDE 顯示開關（top / bottom / left / right 四個），原本只開了其中兩側。使用者在 E3D 裡設定後就正常顯示了。當時從 10 筆資料歸納出的「格線必須真的到達 AGSIDE 那一側才會畫」是錯的推論。
- **AGSIDE 不隨 rcode 旋轉**。曾經在兩個 `.CreateGridSymbol*()` 裡加了 Top→Right / Right→Bottom / Bottom→Left / Left→Top 的對應，是錯的，已移除。座標（XYPO / APOF）的換算才需要，AGSIDE 不需要。

## 背景

`draft/forms/DrawingPlan1.pmlfrm` + `draft/functions/DrawingPlan1*.pmlfnc` 是一組讓使用者在 3D model 中用「建立 box」的方式來切平面圖（plan drawing）的 AVEVA E3D PML 程式。

流程：使用者先在 3D model 建立 BOX 元素（代表要切的圖框範圍），BOX 所在 site 需符合 `<projid>_DrawingPlanBox` 命名規則，然後在 `DrawingPlan1.pmlfrm` 的清單中選取這些 box，按「Create Drawings」後，`.Apply()` 會依 box 的 `worpos`/`wvol`/`xlength`/`ylength`/`zlength`/`ori wrt worl` 算出圖面範圍、比例、方向，並依序呼叫：
`DrawingPlan1GridAnnotation` → `DrawingPlan1LineNoAnnotation` → `DrawingPlan1EquiAnnotation` → `DrawingPlan1MatchLine` → `DrawingPlan1FlowAnnotation`，以及 Nozzle/Valve/Redu/Inst/Supt 等標註 method。

## 命名規則（已確認，無需更動）

- Box 名稱 = 圖號，必須唯一；使用者沒給名稱時，內定用 box 的 ref 號碼（保證唯一）
- 圖號 + 版次（rev）才是平面圖模組中完整的圖面識別碼
- rev 存放在 box 底下一個內容為 `rev:xxx` 的 TEXT 元素，`.Apply()` 掃描所有 text 找 `matchwild('rev:*')` 取值（見 `forms/DrawingPlan1.pmlfrm:345-356`）
- 使用情境：使用者常會先「check」出圖看平面圖設計有沒有問題，不是正式出圖 → **不能強制先正式命名才能建圖**（此為刻意設計，非漏洞）
- Check 階段產生的暫存圖（ref 號碼命名）保留多久由使用者自己決定，非痛點，不需要清除機制

## 待辦：`.Apply()` 覆蓋確認邏輯要修（`forms/DrawingPlan1.pmlfrm:362-392` 附近）

現況：

```pml
handle any
	!del = 'none'
elsehandle none
--	!del = !!alert.confirm('Overwrite Existing DRWG?')
	!del = 'YES'
endhandle
if (!del eq 'YES') then
	if (!this.delshee.val) then
		!order = order
		delete drwg
	else
		------------------------- for future
	endif
endif
```

- `!del = 'YES'` 寫死是**刻意的測試設定**（避免測試時每次都要按 yes/no 對話框），正式上線前使用者會自己拿掉這行、恢復 `!!alert.confirm(...)`。這不是要修的項目。
- **真正要修的**：`else` 分支目前只有 `------------------------- for future` 這行註解，是死碼。已與使用者確認：當 `delshee.val`（"Overwrite Existing DRWG" toggle）關閉時，代表使用者不想覆蓋既有圖面，應該「什麼事都不做」。
  - **修法**：把 `else` 分支改成 `!del = 'NO'`，如此可以重用後面既有的 `if (!del neq 'NO') then new drwg ...` 跳過機制，不用另外加新的控制邏輯：
    ```pml
    if (!this.delshee.val) then
    	!order = order
    	delete drwg
    else
    	!del = 'NO'
    endif
    ```
  - 若照字面直接刪掉 else 兩行（不設 `!del = 'NO'`），`!del` 仍是 `'YES'`，後面 `new drwg $!name/SS_R$!this.rev` 還是會嘗試在同一路徑建立同名同版次的 DRWG，通常會因為名稱重複直接報錯，而不是乾淨地跳過。

## 「切圖方式」設計討論：兩種 box 建立方式並存

使用者希望保留兩種讓使用者建立 box（切圖範圍）的方式，讓使用者自己選：

### 方式 A：互動式點選建 box（優先要做的）

使用者說「我已經寫好」用 3 個點建立 box：前兩點決定平面（X/Y）大小及第一個高程，第三點決定第二個高程。**這次 plan 的範圍先聚焦在把這個方式整合進 `DrawingPlan1` 流程。**

**尚未找到真正的 3 點版程式。** 已用 Explore agent 對整個 `d:\E3D\pdms_prog\E3D2.1` 目錄樹（含 `PA_pmllibE3D2.1.old`、`AWeld`、`BOLTxE3D`、`CAF_ADDINS_PATH`、`CAF_UIC_PATH`、`DesignParameter` 等 sibling 目錄）、檔名 pattern、以及兩個 repo 的 git 歷史做過完整搜尋，唯一找到會 `new box` 的自訂程式是：

**`design/forms/DrawingPlan.pmlfrm`**（注意：`!!DrawingPlan`，跟現在用的 `!!DrawingPlan1` 是不同表單，位於 `design/forms/` 而非 `draft/forms/`）

- 這支是 **2 點**版（Start/End 對角點），不是使用者描述的 3 點版，可能是使用者記錯點數，也可能真正的 3 點版在別的地方（其他機器/PDMS USER db/尚未同步到這台機器），**尚待使用者確認**。
- `.PickPoint()` 用 `EDGPACKET` + `definePosition` 做互動取點，callback 到 `.MarkText()` 存到 `.pointSt`/`.pointEn`（position）並畫 AID 標記。
- `.CreateBox()`：
  ```pml
  define method .CreateBox()
    AID CLEAR ALL
    !xcen = str(!this.pointSt.east  + (!this.pointEn.east  - !this.pointSt.east) * 0.5)
    !ycen = str(!this.pointSt.north + (!this.pointEn.north - !this.pointSt.north) * 0.5)
    !zcen = str(!this.pointSt.up + (!this.pointEn.up - !this.pointSt.up) * 0.5)
    !xlen = abs(!this.pointEn.east  - !this.pointSt.east)
    !ylen = abs(!this.pointEn.north  - !this.pointSt.north)
    !zlen = abs(!this.pointEn.up  - !this.pointSt.up)
    =2013286748/281463
    handle any
      !!alert.error ('No EQUI is available')
    elsehandle none
      new box pos e $!xcen n $!ycen u $!zcen xlen $!xlen ylen $!ylen zlen $!zlen level 1 5
    endhandle
  endmethod
  ```
- **發現的問題（尚未修復，待使用者確認是否為要處理的目標程式）**：
  1. `=2013286748/281463` 是寫死的 db 位址，box 建立在「CE 導覽到此位址後」的當前位置，**沒有導到 `<projid>_DrawingPlanBox` site**，環境不同可能導致 box 建到錯地方，或 `DrawingPlan1.pmlfrm` 的 `.AllBoxes()` 根本找不到它
  2. **沒有名稱輸入欄位**，box 建立時未設定 `name`，因此「預設用 ref」只是巧合，不是刻意的 fallback 邏輯
  3. **沒有零長度防呆**：兩點若picked 到同位置，`.CreateBox()` 本身沒擋
  4. `.delete` 按鈕呼叫 `!This.DeleteBox()`，但檔案內（155行，已全讀）**沒有 `.DeleteBox()` 這個 method**，按下去會報錯
  5. `design/functions/MarkText.pmlfnc` 有一份幾乎相同邏輯的獨立函式，但表單裡呼叫它的那行被註解掉了（`--!packet.action = |!!MarkText(...)|`），改成 inline 版的 `.MarkText()` method，看起來是舊版殘留

**下一步待辦**：跟使用者確認 `DrawingPlan.pmlfrm` 是否就是他說的那支程式（還是要重新找/在更新後的目錄裡再找一次）。

### 方式 B：依結構網格自動切 box（未來項目）

使用者認同這是「另一個好方法」，但**這次不深入設計**，只需在架構/UI 上預留擴充空間，讓使用者之後可以在兩種建 box 方式間切換。細節尚未討論。

## 其他已讀程式時發現的疑點（尚未確認是否為真正 bug，僅供之後查證）

1. **`functions/DrawingPlan1EquiAnnotation.pmlfnc:143-161, 212, 218, 415`**：多處使用 `!namedir` 判斷 up/down/left/right，但整支函式內都沒有對 `!namedir` 賦值。
2. **`functions/DrawingPlan1MatchLine1.pmlfnc:48`**：`down` 方向的 `!tempp6` 用了 `!tempdirr`（往右），對照 `right`/`left`/`up` 三個方向的對稱寫法，這裡疑似應該是 `!tempdirl`（往左），可能複製貼上時漏改。
3. **`forms/DrawingPlan1.pmlfrm:1885-2064`（`.MachLineCode()` method）**：邏輯很像 `DrawingPlan1MatchLine1.pmlfnc` 的舊版，帶大量 `$( old = ... $)` 註解，但全 repo 搜尋不到任何呼叫它的地方，疑似未使用的舊版遺留程式碼。
4. **`functions/DrawingPlan1LineNoAnnotation.pmlfnc:807-899`**：`endfunction` 後面還有一大段被 `$( ... $)` 包住的死碼，也是舊版邏輯殘留。

## Git / Repo 狀態

- `draft` 目錄是獨立 git repo，目前 branch `master`
- Remote：`https://github.com/tw-tseng/pml-draft`（已 push，含 2 個 commit：`5e35eed` Initial baseline、`28c5c9f` "claude未修改的版本"）
- `functions/DrawingPlan1LineNoAnnotation.pmlfnc` 曾有一次縮排/清理的 commit（修正 `handle any` 縮排、移除未用的 `viewdirup`/`viewdirleft` 變數宣告）
