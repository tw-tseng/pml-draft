# DrawingPlan1 開發筆記

> 本檔案記錄與 Claude 討論的進度，供下次繼續。目錄結構、程式細節請以實際程式碼為準（此檔可能與程式不同步）。

## 目前狀態（2026-07-23）

使用者發現 `d:\E3D\pdms_prog\E3D2.1\PA_pmllibE3D2.1` 這個目錄不是最新版本，**要先更新程式**，之後再回來繼續下面的討論。

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
