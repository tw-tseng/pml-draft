# DrawingPlan1 開發筆記

> 本檔案記錄與 Claude 討論的進度，供下次繼續。目錄結構、程式細節請以實際程式碼為準（此檔可能與程式不同步）。

## 目前狀態（2026-07-23）

使用者發現 `d:\E3D\pdms_prog\E3D2.1\PA_pmllibE3D2.1` 這個目錄不是最新版本，**要先更新程式**，之後再回來繼續下面的討論。

## 已改：view 要設 Agside 'All'，四邊的柱位線才會預設顯示（2026-08-13，**尚未實機驗證，改的是 .pmlfrm，要 kill/show**）

使用者要求：view 的屬性 `Agside` 要設為 `'All'`，這樣四邊的柱位線才會預設顯示。`forms/DrawingPlan1.pmlfrm` 建立 view 的地方（`Crsf Nulref` / `Agmode 'OFF'` 那兩行旁邊，`:674` 附近）加了一行 `Agside 'All'`。

**這是 `.pmlfrm`，要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1` 才會生效。**

## 已改：LINE NO. 標籤的 Pltxt 用了不存在的巨集，文字整串消失變 #DEF（2026-08-13，**尚未實機驗證**）

### 症狀

轉過的 box 出圖後，使用者在紅框標出一條沒有文字的尺寸線。用樹狀結構導到那個 DPOI（`ateLINE_up_R` 底下的 DPOI2），確認 `DDNA` 有指到一個真實元件（`ELBOW 4 of BRANCH /80-A-11/B1`），但 `q pltxt` 查出來是 `#DEF`——PDMS 屬性從未被真正設定過的預設值。

### 原因

`DrawingPlan1LineNoAnnotation.pmlfnc`（`:951` 附近，處理「非 BRAN、非 EQUI 的一般元件」分支）：

```pml
if (abs(!pabop.position().up - !bop) le 5) then
	...
	NEW DPOI POS $!attapos DDNA $!mem Pltxt '#PIPE(c2:) BOP EL#PABOPU+'
	...
```

`#PIPE(c2:)` 是真正的 PDMS 巨集（讀 DDNA 的管號，會在 PDMS 端動態解析）。但 `#PABOPU+`／`#PLBOPU+` **不是**——對照同一支函式裡 BRAN 分支已經在用、確定有效的寫法（`:918`）：

```pml
NEW DPOI POS $!attapos DDNA $!mem Pltxt '#PIPE(c2:) BOP EL+$!bopu'
```

BOP 數字是 PML 先算好、用 `$!bopu` 代換成純文字塞進字串，不是丟給 PDMS 現場解析。壞掉的這兩行完全沒做這個代換——`!pabop`／`!plbop` 兩行確實算了，但算完從沒被用進字串裡，`#PABOPU+`／`#PLBOPU+` 是照抄巨集寫法但打錯的殘留，PDMS 認不得，整串 `Pltxt`（連帶 `#PIPE(c2:)`）一起失效退回 `#DEF`。

同一個彎頭在「上邊」跟「左邊」被兩個獨立的 TYPE1 迴圈各抓到一次（同一元件在不同側各標一次，跟前面 `Copy-of-250-B-5` 那次一樣，是合理的行為，不是重複）——只是「上邊」這一份剛好落進這個壞掉的分支，變成一條看不出是什麼的空白尺寸線。

**為什麼一直沒被發現**：這個分支只有在收集到的元件**不是** BRAN、也**不是** EQUI（也就是 ELBO/TEE/VALV/FLAN 這類一般管件）**而且**這個元件是 TYPE1（邊界穿越點，不是 implied tube 的擁有者，而是元件本身剛好卡在邊界上）時才會走到。多數 TYPE1 命中的是 implied tube（在別的分支處理）或 BRAN，這個分支平常很少被踩到。

### 作法

拿掉 `#PABOPU+`／`#PLBOPU+`，改成跟 BRAN 分支一樣：算出選中那一端（`!pabop` 或 `!plbop`，看哪個更接近通用算出來的 `!bop`）的高程、四捨五入、用 `$!endbopu` 代換進字串，並補上 BRAN 分支就有、這裡完全沒做的正負號判斷（`BOP EL+` vs `BOP EL`）。

`!pabop`／`!plbop` 選端點的邏輯本身沒動——那是在判斷「用元件哪一端的 BOP 比較準」，這次只修「選完之後怎麼把值寫進文字」這一步。

### 實機驗證結果：文字修好了，但使用者提出更根本的問題——這個標註根本不該存在（2026-08-13）

`80-A-11` 的標籤確實顯示文字了，但使用者比對 3D 模型後回報：這個標註（`ateLINE_up_R` 的 DPOI2）對應的元件是 **`80-A-11` 的第 4 個彎頭**，那個彎頭實際上在圖面很內側的位置，不像會碰到上邊界；而且截圖上那條紅色標註線的位置（screen x≈235）跟彎頭實際所在（紅框，screen x≈365）明顯對不上。

### 懷疑方向：ITLE 讀不到時的退路，把沒驗證過的猜測當成真的交點

`.CrossingOfTube()`（`:2182`）在 `itle of $!tube` 讀不到時的退路是：

```pml
if (!tubelen gt 0) then
	!p2 = !p1.offset(!stdir.direction(), !tubelen)
else
	!p2 = !p1.offset(!stdir.direction(), 1000)   -- 猜一個 1000mm
endif
...
if (!ok and !tubelen gt 0) then
	-- 交點要落在管段兩端之間 -- 這道檢查只在 !tubelen gt 0 才做
	...
endif
```

如果 `!tubelen` 讀不到（`itle of` 失敗，`!tubelen` 停在 `0`），程式會**憑空往 `!stdir` 方向走 1000mm**當作管段終點，而且「交點要落在管段兩端之間」這道防呆**完全不會執行**——只要這條猜出來的 1000mm 延伸線剛好掃到邊界，不管真正的管子有沒有那麼長、有沒有朝那個方向走那麼遠，都會被當成「真的穿越邊界」接受。這個缺口在 README 更早的位置就寫過（`.CrossingOfTube()` 一節本身的註解），但這是第一次找到疑似真的踩到的案例。

### 作法：加診斷直接驗證，不再猜

`forms/DrawingPlan1.pmlfrm` 的 `.CrossingOfTube()` 結尾加了一段：只要**最後真的接受了一個交點、但 `!tubelen` 是 0**（代表這個交點完全沒經過「落在管段兩端之間」的驗證），就寫一行到 `L:\E3D\pdms_prog\E3D2.1\PA_pmllibE3D2.1\check2.txt`：

```
CROSSING-NOLEN tube=... elem=... dir=... stpos=... stdir=... answer=...
```

**這次改的是 `.pmlfrm`，需要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1`。**

### 實機驗證結果：`check2.txt` 是空的，ITLE 猜測的懷疑排除（2026-08-13）

`check2.txt` 完全沒有產生——這次執行沒有任何一筆交點是在 `!tubelen` 為 0（ITLE 讀不到）的情況下被接受的。`80-A-11` 這筆交點的 `!tubelen` 讀得到、「交點要落在管段兩端之間」的防呆真的執行過也真的通過了。這個懷疑方向排除。

### 使用者提供關鍵反證：交點跟管子是真的，但 DPOI2 的座標對不上任何一筆

使用者確認彎頭 4（`=2013286676/1630`）確實接了一段約 3 公尺、大致朝東的直管（用紅色箭頭標出來，跟算出來的 `ΔE≈2969mm ΔN≈0mm` 吻合），但那段管的圖面位置跟 DPOI2（使用者點選確認的那條紅線）的位置對不上。

直接查 DPOI2 的 `q pos wrt worl`：

```
Position W 311379mm N 310592mm U 106437mm
```

拿這個座標去對這次執行 `check.txt` 記錄到的全部 5 筆 TYPE1 交點（`300-A-42`／`80-A-11`／`40-B-10`／`100-C-12`／`150-A-57`），**沒有一筆對得上**（差距從幾百到三千多 mm 不等）。`U≈106437` 這個特徵值倒是跟每一筆交點都一樣——這是另一個獨立的小毛病：`.CrossingOfTube()` 用 `.before('U')` 把高程從字串砍掉、再用 `enupos of` 轉回世界座標時，PML 用 view 的參考深度面補上缺的高程，所以每一筆交點的 `U` 都長一樣。不影響對錯判斷（`U` 之後會被呼叫端用元件自己的高程覆蓋掉），但確認了 DPOI2 應該也是某個 TYPE1 交點——只是不是這 5 筆裡的任何一筆。

**已排除「舊圖」**：使用者重新 `kill/show` → Create Drawings → 立刻查 DPOI2，`q pos` 結果完全相同，`check.txt` 內容也完全相同。這是最新一次執行的真實資料。

### 作法：不再挑診斷點，改成記錄每一個 DPOI 建立當下的完整資訊

`functions/DrawingPlan1LineNoAnnotation.pmlfnc` 加了 `!dpoiseq`（每個 `!dir` 開始時歸零），在**全部三個**會建立 DPOI 的地方（標籤主迴圈、格線交點、兩個邊角補點）建立之前各印一行：

```
DPOISEQ <序號> section=labelled/grid/corner1/corner2 [pipe=...] mem=... attapos=E .. N .. U ..
```

這樣輸出的行號順序就是 DPOI 在這條 LDIM 上的**真實建立順序**——跟 Draw Explorer 樹狀結構裡 `DPOI 1, DPOI 2, ...` 的編號直接對得上，不用再靠推測「第幾個 label 對應第幾個 DPOI」。

### 實機要看的地方

重新 Create Drawings，把 `check.txt` 裡 `DPOISEQ` 開頭的所有行給我。第 2 行（`DPOISEQ 2 ...`）理論上就是 DPOI2，直接比對它印出來的 `attapos` 跟使用者查到的 `W 311379mm N 310592mm U 106437mm` 是否一致：

- **一致** → 找到是哪個 `section`／哪個 `mem` 產生的，順著查下去。
- **序號對不上**（比如 `DPOISEQ 2` 的座標不是這個，但某個別的序號是）→ 代表 DPOI 在 Draw Explorer 裡的編號和這條 LDIM 的建立順序其實不是同一件事，要換角度查。
- **完全沒有任何一筆 `attapos` match** → 代表這個 DPOI 根本不是這次 `!!DrawingPlan1LineNoAnnotation` 呼叫建立的，要查是不是別的函式或別的時機建到同一條 LDIM 上。

**只改了 `.pmlfnc`，不用 kill/show。**

### 實機驗證結果：序號對不上——DPOI2 其實是格線交點，不是任何一筆標籤（2026-08-13）

`check.txt` 這次跑出 9 行 `DPOISEQ`（5 筆 labelled、2 筆 grid、2 筆 corner）。第 2 行（`DPOISEQ 2 section=labelled pipe=80-A-11 ...`，就是 README 稍早懷疑的那個彎頭）的 `attapos` 是 `E -308134mm N 309345mm U 104925mm`，跟使用者查到的 `W 311379mm N 310592mm U 106437mm` **對不上**（差了 3200mm／1200mm／1500mm）。

但第 6 行對上了，幾乎是逐位對齊：

```
DPOISEQ 6 section=grid attapos=E -311378.722130884mm N 310592.169447837mm U 106437.491663mm
```

`E -311378.72` = `W 311378.72`、`N 310592.17`、`U 106437.49`，跟使用者的 `W 311379 / N 310592 / U 106437` 只差零點幾 mm（四捨五入誤差範圍內）。

這是 README 自己列的三個分支裡的**第二種**：「序號對不上，但某個別的序號是」——代表 Draw Explorer 樹狀結構裡的 `DPOI 1, DPOI 2, ...` 編號，跟這條 LDIM 的**建立順序不是同一件事**。最可能的原因是 `:1139`（`OWNER` 之後）的 `SORT DIM`：這個指令很可能是照「沿著尺寸線的實際位置」重排每個 DPOI 的顯示順序，而不是照程式建立它們的先後——建立順序（`!dpoiseq`）跟顯示順序因此各自獨立。

**新的矛盾**：使用者查到的這個位置（`section=grid`）在程式碼裡是 `NEW DPOI POS $!attapos` 建的（`:1071` 附近），**完全沒有帶 `DDNA` 或 `Pltxt`**——理論上這種點的 DDNA 應該是空的，不該指到任何元件，更不該是使用者稍早查到的 `ELBOW 4 of BRANCH /80-A-11/B1`（那其實是 `DPOISEQ 2` 自己的 DDNA，是另一個點）。兩種可能：

1. 使用者當時點的其實不是同一個 DPOI——9 個節點長得很像，樹狀結構裡容易點錯一個。
2. PDMS 的 `NEW DPOI`（沒指定 `DDNA`）在這個情境下不是留空，而是延續了 session 裡某個「目前預設值」，把前面某次 `DDNA $!mem`（不一定是緊接在前的那筆）留下來的值繼續套用在後面沒指定的點上。

### 實機驗證結果：同一次 q session 直接確認——不是點錯節點（2026-08-13）

使用者提供截圖：Draw Explorer 樹狀結構裡選取的節點標題列清楚寫著 `POINT 2 of LDIMENSION /26001-AG-002/SS/S1/V1/ateLINE_up_R`（`DPOI2` 也在樹上被反白選取），命令視窗裡**連續**下了兩個指令：

```
q pos
Position W 311379mm N 310592mm U 106437mm
q ddna

Ddname ELBOW 4 of BRANCH /80-A-11/B1
```

同一個節點、同一次選取、連續兩個查詢——上面的可能 1（點錯節點）排除。確定是同一個 DPOI 身上，`q pos` 對上這次執行 `DPOISEQ 6`（`section=grid`，程式碼沒帶 `DDNA`），`q ddna` 卻對上 `DPOISEQ 2`（`section=labelled`，`80-A-11` 彎頭）的 `mem`。

### 作法：直接在建立當下讀回 DDNA，不再猜

`DrawingPlan1LineNoAnnotation.pmlfnc` 在全部三個建立 DPOI 的地方（`labelled` 分支結束處、`grid`、`corner1`、`corner2`，緊接在每個 `NEW DPOI` 之後、CE 還是剛建出來那個 DPOI 的當下）都加了一行：

```
var !liveddna ddna of ce
```

寫進 `check.txt`：`LIVEDDNA <序號> section=... liveddna=...`。這樣可以直接看到**建立當下**（`OWNER` / `SORT DIM` 執行之前）grid／corner 這幾個沒帶 `DDNA` 參數的點，DDNA 到底是空的、還是一出生就已經是某個真實元件：

- 如果 `LIVEDDNA 6 section=grid liveddna=` 是空的 → 建立當下確實沒有 DDNA，代表是 `OWNER`／`SORT DIM`（或更後面的步驟）把 `DPOISEQ 2` 的 DDNA 之類的屬性複製/搬動到了這個點上，要往那邊查。
- 如果一出生就已經是某個真實元件（不一定是 80-A-11 彎頭，任何非空值都算）→ 代表 PDMS 的 `NEW DPOI`（沒指定 `DDNA`）在這個情境下真的會延續 session 裡某個「目前預設值」，之後要在建立這類點之前主動清掉或蓋掉這個預設。

### 實機驗證結果：手動查完全部 9 個 DPOI，證實是 SORT DIM 依座標重排，且真正的管號標籤都沒被搞混（2026-08-13）

使用者在 Draw Explorer 用 `next` 依序把 `ateLINE_up_R` 底下 9 個 DPOI 的 `q pos` 和 `q ddna` 都查了一遍（`check.1txt`）。把這 9 筆位置換算成 N（北）座標由大到小排序，順序正好是 `8, 6, 1, 7, 2, 3, 4, 5, 9`（用這次 `check.txt` 的建立順序編號 `DPOISEQ`）——跟使用者手動查到的 `DPOI1~9` 順序**完全吻合**。`:1160` 附近的 `SORT DIM` 確定就是照座標（這裡是 N 值由大到小）重排顯示順序，跟建立順序無關。

更重要的是：5 筆 `labelled`（程式碼裡有明確 `DDNA $!mem` 的）不管被排到第幾個，`q ddna` 查到的都跟建立時設定的完全一致，一個沒錯——`SORT DIM` 只是重排顯示位置，**不會**把 DDNA 弄錯或搬到別的點上，真正要標管號的那 5 個點沒有問題。

使用者最早紅框標出的那條「沒有文字的尺寸線」就是 `DPOI2`，對照 `DPOISEQ` 是 `section=grid`（柱位線跟邊界的交點）——程式碼裡這種點本來就不給 `Pltxt`，因為它不是在標某個管件。**這條線段落空白是設計如此，不是 bug**；`q ddna` 查到的 `ELBOW 4 of BRANCH /80-A-11/B1` 也已知跟這個點的 `Pltxt`／畫面顯示無關（畫面只看 `Pltxt`，不看 `DDNA`）。

`section=grid`／`corner1`／`corner2` 這 4 個沒帶 `DDNA` 的點裡，有 3 個（對應 `DPOI1`／`2`／`4`）`q ddna` 卻查得到別的點的 DDNA，只有 1 個（`DPOI9` / `corner2`）是真的空的（`Nulref`）——這個次要謎團還沒解，已加了 `LIVEDDNA` 診斷在等下一次執行結果，但不影響上面的結論。

### 實機驗證結果：`LIVEDDNA` 證實建立當下這 4 個點真的都是空的，不是 PDMS 的預設值延續（2026-08-13）

重新執行後 `check.txt` 印出：

```
DPOISEQ 6 section=grid refgln==23414/847 attapos=...
LIVEDDNA 6 section=grid liveddna==0/0
DPOISEQ 7 section=grid refgln==23414/850 attapos=...
LIVEDDNA 7 section=grid liveddna==0/0
DPOISEQ 8 section=corner1 attapos=...
LIVEDDNA 8 section=corner1 liveddna==0/0
DPOISEQ 9 section=corner2 attapos=...
LIVEDDNA 9 section=corner2 liveddna==0/0
```

`=0/0` 是 PDMS 空參照的表示法（跟使用者查到 `DPOI9` 是 `Nulref`一致）。**四個點在剛建立、`OWNER`／`SORT DIM` 都還沒跑的當下，DDNA 全部是空的**——排除了「`NEW DPOI` 延續 session 預設值」這個猜測。也就是說，使用者查到的 `DPOI1`／`2`／`4` 帶著別的點的 DDNA，是 `OWNER` 或 `SORT DIM`（`:1160` 附近）跑完之後才出現的，不是建立當下就有。這兩個指令怎麼會把 DDNA 貼到本來沒有的點上，目前還沒細查——但這不影響任何畫面上顯示的文字（`Pltxt` 從頭到尾没被動過），純粹是 Draw Explorer 查詢時看到的附加資訊，先擱置。

### 使用者提出：從畫面看不出這個 DPOI2 是哪一條柱位線

`.allintersections` 原本的格式（`GridAnnotation.pmlfnc:151`）只帶了邊界交點座標和柱位線末端座標，沒帶柱位線自己的名字，所以現有的 `DPOISEQ` 記錄查不出 DPOI2 對應的是哪一條柱位線。

### 作法：`.allintersections` 多帶一節柱位線的 NAME

`DrawingPlan1GridAnnotation.pmlfnc:148` 附近：`.allintersections` 追加時多接一個 `'~' & <NAME>`。第一版直接讀 `name of $!refgln`，實機一跑發現是空的——輸出的 `refgln==23414/847`／`=23414/850` 是 `NAME OF` 對沒設名字的元件的預設回傳值（DB 參照本身），不是真正的柱位線名稱。原因是 `!refgln`（`:80`）只是這條柱位線在**這個view 切出來的幾何線段**，本身沒有名字；真正掛名字的是外層 `do !gridel values !gridels`（`:78`）的 `!gridel`（從 `REFGRD` 收集回來的柱位線元件），在 `!refgln` 這層迴圈裡仍然在 scope 內，改讀 `name of $!gridel` 就對了（`.intersections` 本身不動，兩個 `.CreateGridSymbol*()` 還在讀它，不受影響）。`DrawingPlan1LineNoAnnotation.pmlfnc` 的 `section=grid` 那段（`:1092` 附近）跟著多讀這個第三欄，記進 `DPOISEQ` 那行：

```
DPOISEQ <序號> section=grid refgln=<柱位線名稱> attapos=E .. N .. U ..
```

### 實機驗證結果：DPOI2 對應的柱位線是 `/PIPERACK_P1_A01/Elev`，調查收斂（2026-08-13）

```
DPOISEQ 6 section=grid refgln=/PIPERACK_P1_A01/Elev attapos=E -311378.72mm N 310592.17mm U 106437.49mm
DPOISEQ 7 section=grid refgln=/PIPERACK_P1_A01/Elev attapos=E -308559.59mm N 309745.57mm U 106437.49mm
```

`DPOISEQ 6`（= Draw Explorer 的 `DPOI2`）對應的是管架 P1、位置 A01 的參考網格線 `/PIPERACK_P1_A01/Elev`。`DPOISEQ 7`（= `DPOI4`）印的名字一樣，不是重複記錄——同一條網格線在同一個 `gridpl` 底下拆成兩段 `refgln` 幾何線（`GridAnnotation.pmlfnc:80`），各自跟上邊界交會一次，兩段都掛在同一個 `!gridel` 名下。`LIVEDDNA` 仍是 `=0/0`，跟前一次一致，沒有新東西。

### 使用者在 3D 裡把 `/PIPERACK_P1_A01/Elev` 叫出來，看不出是哪一條柱位

使用者提供截圖：3D 視角裡把 `/PIPERACK_P1_A01/Elev` 高亮成紅色，是一條跟主結構脫節的短斜線，不像 `P1.3`／`P1.4`（畫面下方兩個格線圓牌，中間有 `5180mm` 尺寸的那種）那種認得出來的柱位線。

使用者說明規則：**在這個專案的 E3D 模型裡，平面（plan view）的柱位線要在 `Elev` 底下才找得到**，`Elev` 本身不是柱位線，是柱位線的容器層。

### 作法：往下一層抓 `!gridpls[1]` 的名字

`DrawingPlan1GridAnnotation.pmlfnc:80` 附近：`!refglns` 是從 `!gridpls[1]`（`Elev` 底下、實際用來收集這條線幾何的那個 grid plane）收集來的。新增 `var !gridplname name of $!gridpls[1]`，串進 `.allintersections` 的第三欄，變成 `<gridel名字>/<gridpl名字>`。`DrawingPlan1LineNoAnnotation.pmlfnc` 那邊不用改，`.split('~').getindexed(3)` 讀到的就是整串。

### 實機驗證結果：`Elev_1` 也只是自動編號，不是柱位名稱（2026-08-13）

```
DPOISEQ 6 section=grid refgln=/PIPERACK_P1_A01/Elev//PIPERACK_P1_A01/Elev_1 attapos=...
```

`!gridpls[1]` 的名字是 `/PIPERACK_P1_A01/Elev_1`——只是在 `Elev` 後面加了自動編號的 `_1`，不是 `P1.3`／`P1.4` 那種柱位名稱。往下一層還是沒找到。

### 作法：不再逐層猜，一次把整個 gridel/gridpl/refgln 階層印出來

第一版程式碼有語法錯誤（`do !gp index !gpi values !gridpls` 不是合法的 PML 語法，IDE 有報錯），已改用一般計數器變數修正。`DrawingPlan1GridAnnotation.pmlfnc:77` 附近：開一個新的診斷檔 `check3.txt`，在 `!gridel` 迴圈一開始，把這個 `!gridel` 底下**所有** `!gridpls` 成員（不只 `[1]`）的名字，以及每個 `gridpl` 底下**所有** `refgln` 的名字跟 TYPE，全部印出來：

```
GRIDEL name=... gridpls.size=...
  GRIDPL 1 name=... refglns.size=...
    REFGLN 1 name=... type=...
    REFGLN 2 name=... type=...
  GRIDPL 2 name=... refglns.size=...
    ...
```

### 實機要看的地方（下一步）

重新 Create Drawings，把 `check3.txt` 整個內容給我，直接找哪一個 `GRIDPL` 或 `REFGLN` 的 `name=` 長得像 `P1.3`／`P1.4`。

### 實機驗證結果：整個階層都沒有名字，`P1.3`／`P1.4` 不是存在這裡的 NAME 屬性（2026-08-13）

`check3.txt` 全文：這次跑的 box 只收集到 1 個 `gridel`（`/PIPERACK_P1_A01/Elev`），底下 5 個 `gridpl`（`Elev_1`~`Elev_5`，都是自動編號），每個底下 6 個 `refgln`，**全部 30 個 `REFGLN` 的 `name of` 都是裸的 DB 參照**（`=23414/845` 這種），一個有名字的都沒有。

也就是說：`P1.3`／`P1.4` 這種柱位名稱**不是**存在 `!!DrawingPlan1GridAnnotation()` 這支函式在走的 `gridel`／`gridpl`／`refgln` 這條階層裡的 `NAME` 屬性上——這條路徑走到底都是空的，不是還沒找對層級，是這整條階層本來就不存名字。`P1.3`／`P1.4` 那兩個牌子應該是另一組完全不同的元件（可能是獨立的 SLAB／LABEL，或用别的屬性像位置、間距算出來的），不是這條 `REFGRD → gridel → gridpl → refgln` 幾何線本身帶的名字。

**要不要繼續往下查**：這條路徑已經走到底，要找到 `P1.3` 真正掛在哪個元件上，得換一個完全不同的切入點（例如直接在 3D 裡點開畫面上 `P1.3` 那個圓牌本身查它的 TYPE／OWNER），不是再從 `refgln` 這邊挖。這不影響最早已經修好、驗證過的文字消失 bug，也不影響「DPOI2 是柱位線交點、不是漏標」這個結論本身——只是還沒辦法讓 `check.txt` 自動印出使用者慣用的柱位牌子名稱。是否要繼續查，還是先在這裡停下，等使用者確認即可。

如果之後找到了，整條調查線就收斂：
1. 最早的 `#DEF` 文字消失（`#PABOPU+`／`#PLBOPU+` 巨集打錯字）——已修，已實機驗證。
2. 使用者紅框標出的空白尺寸線（`DPOI2`）——是某條柱位線跟上邊界的交點，本來就不該有文字，**不是 bug**。
3. `DDNA` 在 `OWNER`／`SORT DIM` 之後被貼到這些空白點上——只影響 Draw Explorer 查詢看到的附加資訊，不影響圖面上實際顯示的 `Pltxt`，擱置不追。

到時候這幾輪加的暫時診斷（`!dbgln = true`、`DPOISEQ`／`LIVEDDNA`／`refgln` 記錄、`.pmlfrm` 裡 `.CrossingOfTube()` 結尾寫 `check2.txt` 的那段）都可以清掉，只留下 `#PABOPU+`／`#PLBOPU+` 那個真正的修正。

## 已改：box 轉 10 度時，圖上空白處卻標了一堆管線編號（2026-08-12，**尚未實機驗證**）

症狀（見 `error.png` 紅框）：box 轉 10 度切出來的圖，左下角一大片沒有畫出任何管子，但左側的 LINE NO. 標註仍然在那個高度範圍標了 8~9 個編號，而且同一條管、同一個 BOP 高程重複出現 3~4 次（`Copy-of-100-C-12 BOP EL+100566` ×3、`Copy-of-200-B-4 BOP EL+100235` ×3）。同一批管線在下方的標註也再出現一次。

### 原因：view 的世界座標裁切體積比 box 本身還小

`.Apply()` 算 box 範圍的地方（`forms/DrawingPlan1.pmlfrm:464-473` 附近）是這樣算的：

```pml
!maxE1 = !boxPos.position().offset(!efpla, !elen.real() * 0.5 + 0.025).east
```

`!efpla` 是 **box 自己的軸方向**（已經轉了 10 度）。沿著轉過的方向走半個邊長之後再取 `.east`，得到的是

```
Ec + (elen / 2) * cos(10°)
```

但轉過的 box 真正的最東點是 `Ec + (elen / 2) * cos(10°) + (nlen / 2) * sin(10°)`。也就是說這組 `!minE / !maxE / !minN / !maxN` **既不是 box、也不是 box 的 bounding box，而是 box 各邊乘上 cos(角度) 之後的縮小版**。box 是正的時候 cos = 1，三者相同，所以以前看不出來。

這組縮小的值被拿去設兩個**世界座標軸對齊**的裁切：

| 位置 | 指令 | 作用 |
|---|---|---|
| `:475` | `limits E .. TO E ..` | DRAWLIST 的 IDLI limits，限制這個 drawlist 項目畫出來的體積 |
| `:711` | `:CDLIMITS \|FROM E .. TO E ..\|` | view 的裁切範圍 |

而 view 的**外框**（`size $!sizeX $!sizeY` = `elen * vsca` × `nlen * vsca`，加上 `Adegrees`）是**完整的 box**。於是畫出來的東西 = 完整 box ∩ 縮小的世界方盒，等於**從 box 上斜切掉兩個大楔形**。

用 tan 算一下就知道有多大：在 view 自己的座標裡，被畫出來的條件是 `|u·sinθ + v·cosθ| ≤ (H/2)·cosθ`，也就是 `v ≥ -H/2 - u·tanθ`。θ = 10° 時 `tan θ = 0.176`，所以在 view 最左邊（`u = -W/2`）底部被切掉 `0.088·W`；W = 2H 的橫式圖就是**高度的 17.6%**，一路往中間收斂到 0。另一個楔形在對角（右上）。這正好就是紅框那片空白。

**標註沒有跟著被切掉**，因為 `DrawingPlan1LineNoAnnotation` 走的是 2026-08-10 改過的圖紙座標路線：`.SheetBandOfSide()` 用的是 `viewLLsh / viewURsh`（來自 view 的 `shxypos` + `size`，也就是**完整的 box**），`.WorldLimitsOfSheetRect()` 再包成世界方盒餵給 `WITHIN`。所以被 CDLIMITS 切掉、沒畫出來的那些管子，標註照樣抓得到、照樣標。兩邊對 view 範圍的認知不一致，這就是「沒看到管子卻標了編號」。

同一條管重複 3~4 次也是同一個根因的延伸：楔形區域同時落在左側帶與下側帶裡，一條分支在帶內的每個管件各標一次，而 TYPE 1 的去重門檻只有圖紙 1mm（見下方 2026-08-10「同一條管在同一邊標了兩次」那節）。

### 作法

`limits` 與 `:CDLIMITS` 改用 **box 的世界 bounding box**（`wvol`，`:427-432` 本來就讀好了，只是後來被覆蓋掉），另存成 `!wminE .. !wmaxU`（各留 0.025 容差，沿用原本的用意）。

**為什麼放寬是安全的**：view 底下已經有六個 FPLA + VSEC（`:496-525`、`:717-734`），平面位置是 box 的面中心、法線是 box 轉過的方向，**那六個平面才是真正把 view 切成轉過的 box 形狀的東西**。世界軸對齊的方盒本來就不可能貼合一個轉過的 box，它的角色只能是「不小於 box 的超集合」。box 是正的時候 `wvol` 就等於原本那組值（差 0.025），行為不變。

`!lim = limits`（`:476`）是沒有人讀的死碼，一併移除。

**`!this.minE / .maxE / .minN / .maxN`（`:477-482`）維持用原本那組面中心的值，沒有動**——理由見下面「還沒做」。

### 實機驗證結果：這個假設是錯的（2026-08-12）

使用者改完重載表單、重新 Create Drawings，**紅框那片空白依然沒有管子**。

回頭重算 `.ViewSheetTransform()` 底下那六個 FPLA（`:520-549`）才發現：`position` 用的兩個分量雖然分別來自 `!thpoEforN` 這類「中心沿 efpla/nfpla 偏移半邊長」的值和 `!maxE`/`!maxN` 這類「同樣沿 efpla/nfpla 偏移（另加 0.025）」的值，兩者其實是**同一個偏移點**的 E 分量和 N 分量分開算出來的——代入角度可以證明這六個平面的位置點準確落在轉過的 box 真正的面上，法線也用 `efpla`/`nfpla`（已經是轉過的方向）。也就是說**這六個 FPLA/VSEC 本來就是照轉過的 box 正確切的**，`limits` / `:CDLIMITS` 那組世界軸對齊的值從頭到尾就只是 DRAWLIST／CD 的輔助資訊，不是實際裁切 view 內容的東西——這次的改動大機率是無效更動（改了但沒改到真正裁切的地方），予以保留但不再視為這個症狀的答案，真正原因待查。

### 真正原因（2026-08-12，靠診斷輸出找到，已修）

`functions/DrawingPlan1LineNoAnnotation.pmlfnc` 加了 `!dbgln`，只在 `!dir.eq('left')` 印 TYPE 1 迴圈每一步，重新 Create Drawings 一次、把 Command Window 的 `TYPE1` 行存成 `check.txt` 比對之後找到的。

前一輪懷疑「`.CheckInSheetBand()` 對 implied TUBE 放行、`.CrossingOfTube()` 的 `itle` 分支漏檢查」——**這個懷疑是錯的**。`check.txt` 顯示 `.CrossingOfTube()` 的判斷完全正確：真的沒碰到邊界的管都拿到 `crossenu=NONE` 並且被丟掉（例如 `pipe=Copy-of-200-B-4 ... crossenu=NONE`，後面沒有 `KEPT` 那行）；真的垂直、投影成一點的管拿到 `crossenu=`（空字串），照文件描述的行為退回用元件自己的位置，這兩種都對。

**真正壞掉的是「算出正確交點之後，把交點包回字串」這一步**（`:222-224`）：

```pml
!crosspos = object position(!crossenu)
!crosspos.up = !memenupos.position().up
!memenupos = !crosspos.string()
```

`check.txt` 裡四筆「管真的穿過邊界」的紀錄，`crossenu`（`.CrossingOfTube()` 的原始回傳，來自 `enupos of`）明明是四個差好幾百公尺的世界座標：

```
crossenu=W 365567.882945mm N 243650.028102mm U 104749.080026mm  (pipe Copy-of-100-B-1)
crossenu=W 366611.385066mm N 237732.033324mm U 104749.080026mm  (pipe Copy-of-100-C-13)
crossenu=W 365880.277896mm N 241878.348126mm U 104749.080026mm  (pipe Copy-of-250-B-5)
crossenu=W 365027.319571mm N 246715.715336mm U 104749.080026mm  (pipe Copy-of-150-A-3)
```

但转成 `!memenupos`、再 `shpos of` 算出圖紙座標之後，**X 全部變成同一個數**（`201.934545mm` / `201.934546mm`，六位小數都幾乎一樣），只有 Y 還照實際位置變化。四條完全不相關的管，圖紙 X 不可能只差千分之一毫米。

原因：`object position(<string>)` 建構出來的 POSITION，`.string()` 印回去的格式**不是**單純的 `E .. N .. U ..`，會多一段 `WRT /*`（`memenupos=W ...mm N ...mm U ...mm WRT /*`）——這是 `check.txt` 直接印出來、肉眼可見的。這條尾巴是 `object position()` 建構出來的物件特有的，`enupos of` / `hpos of` / `worpos of` 這類直接查詢出來的字串從來沒有這段（`check.txt` 裡其餘幾十筆 `KEPT` 都沒有 `WRT`）。`SHPOS OF` 後面接到這段尾巴時解析壞掉，算出來的圖紙 X 變成某個跟真正座標無關的固定值。

這條路徑只有在「管真的穿過邊界、`.CrossingOfTube()` 算出實際交點」時才會走到——也就是**唯一真正該標註、真正在紅框那個位置有管子的情況，反而是唯一座標算壞的情況**。壞掉的圖紙 X 落在別的地方（不是它真正該在的深度），標籤跟著跑位，看起來就像「這裡標了編號但沒看到管子」。box 是正的時候這條路徑（`.CrossingOfTube()` 走到真交點）比較少被觸發，轉了角度之後管跟邊界斜交，才常態性地踩進來。

### 作法（第一版，不完整）

不依賴 `.string()`，改成跟這個檔案其他地方（`!vlfm`/`!vlto`、`.ViewSheetTransform()` 的 `!c0sh`）一樣的手動組字串，用 `.east` / `.north` / `.up` 三個分量直接拼：

```pml
!memenupos = 'E ' & string(!crosspos.east) & ' N ' & string(!crosspos.north) & ' U ' & string(!crosspos.up)
```

### 實機驗證結果：拿掉 WRT 尾巴不夠（2026-08-12）

重新 Create Drawings 之後，`check.txt` 裡 `WRT /*` 確實不見了，但**圖紙 X 還是卡在同一個 201.934545/6mm**，跟修之前一模一樣（`error.png` 也沒有變化）：

```
crossenu=W 365567.882945mm ...  → memenupos=E -365567.882945mm ...  → memshpos X 201.934545mm
crossenu=W 366611.385066mm ...  → memenupos=E -366611.385066mm ...  → memshpos X 201.934546mm
```

問題不在 `WRT`，在**負的東座標被印成 `E -365567.88mm`**。`!crosspos.east` 對這個案場是負值（案場世界座標在原點西側），`string()` 一個負的 real 會直接帶負號，`'E ' & string(...)` 就組出 `E -365567.88mm`。但這個檔案裡其他每一筆成功算出來的座標，負的東座標從來不是這樣寫的——一律是 `W 365567.88mm`（正數 + 相反方位字母），`check.txt` 裡幾十筆 `KEPT`／`SKIPPED` 沒有一筆例外（`.CrossingOfTube()` 內部處理 N/S/E/W 也是同一個假設：`.replace('N', 'Y').replace('S', 'Y').replace('E', 'X').replace('W', 'X')`，前提就是負值一定印成反方位字母而不是負號）。`SHPOS OF` 認得 `W <正數>`，不認得 `E <負數>`，兩種都解析不出正確結果，所以退回同一個固定答案（哪來的固定答案還不確定，但兩次都恰好是 201.93 這件事，比較像是同一個解析失敗路徑，不是巧合）。

### 作法（第二版）

把符號換成方位字母，跟這個檔案其他地方一致：

```pml
if (!crosspos.east geq 0) then
	!epfx = 'E '
	!eval = !crosspos.east
else
	!epfx = 'W '
	!eval = !crosspos.east * -1
endif
-- north、up 同一套邏輯（north 負值用 S，up 負值用 D）
!memenupos = !epfx & string(!eval) & ' ' & !npfx & string(!nval) & ' ' & !upfx & string(!uval)
```

`!dbgln` 診斷還留著（預設開），下一次重新 Create Drawings 時要看 `memshpos` 的 X 是不是四條管各自不同、不再卡在 201.93 附近；確認沒問題後把 `!dbgln` 改回 `false` 或整段拿掉。

**尚未查證、留意**：`object position()` 建構物件的 `.string()` 帶 `WRT` 尾巴、以及「負座標要用方位字母不能用負號」這兩件事，這次都只在這一處發現、也只修這一處。全 repo 還有幾十處 `object position(...)` 用法（`DrawingPlan1EquiAnnotation.pmlfnc`、`DrawingPlan1MatchLine*.pmlfnc` 等），大部分後續是直接當物件用（`.distance()`／`.on()`／`.intersection()`），沒有再轉成字串餵回 `shpos of`/`coll ... within` 這類指令替換，所以不會踩到同一個坑；但沒有逐一確認過，之後若又遇到「座標卡在同一個怪數字」或「東西南北對不起來」的症狀，先往這兩個方向查。

### 實機驗證結果：X 座標修好了，但紅框依然沒有管子——之前的懷疑診斷錯了方向（2026-08-12）

第二版重新 Create Drawings 之後，`check.txt` 裡 `memenupos` 已經是正確的 `W ###mm N ###mm U ###mm` 格式，不再有 `WRT` 尾巴或 `E -###`。但 `error.png` 跟改之前**逐像素相同**——紅框那片還是沒有管子。

回頭比對 `check.txt` 才發現，**「四筆穿越邊界的交點，圖紙 X 幾乎相同」這件事本身不是 bug，是必然如此**：這四個交點都精確落在 view 的**左邊界**上，而左邊界在圖紙（sheet-local）座標系裡定義就是一條 X 為定值的直線（`.SheetBandOfSide()`／`viewLLsh`／`viewULsh` 用的就是這個 local 座標系，view 在裡面永遠是方的）——落在同一條「X 為定值」的邊界線上的點，`SHPOS OF` 算出來的 X 本來就該相等，只有沿邊界方向的 Y 會依各自實際位置變化，而 `check.txt` 裡確實是 Y 在變、X 幾乎不變。這是**正確**行為，不是我之前說的「壞掉」。E/W 那個修正本身是對的（保留），但**它不是紅框沒有管子這件事的答案**——那件事從頭到尾就不是這個函式的 bug。

重新看 `check.txt` 全文，`.CheckInSheetBand()`、`.CrossingOfTube()`、IDLN 判斷這一整條鏈路其實**都對得上**：紅框附近那些 `Copy-of-100-C-12` 的 VALV/TEE/ELBO/FLAN（`:147-167`）全部 `check=Included`、`inband=TRUE`，位置也都是同一個 E/N（`W 366767.32mm N 236859.96mm`，只有 U 高程不同——這是一根立管/riser），标注邏輯正確地把它們都收了進去、標了 8 個不同高程。問題不是「標註誤判」，是**這些元件明明 `IDLN` 查出來是 `Included`（已經在 drawlist 裡），畫面上卻看不到**——這把問題指回 view 本身的幾何範圍，而不是 `DrawingPlan1LineNoAnnotation.pmlfnc`。等於繞了一圈，回到 2026-08-12 最早那個「FPLA/VSEC」方向，但那次推導位置公式沒找到破綻，法線方向（`norm`）也重新檢查過，六個面全部朝內、成對對稱，公式本身看不出錯。

### 下一步：直接印出兩種候選邊界，對照已知的真實座標

不再靠推導，`forms/DrawingPlan1.pmlfrm`（`:507-519` 附近，`limits` 那行之後）加了三行 `$p BOXLIM ...`，印出：

- 縮小版方盒 `!minE/!maxE/!minN/!maxN/!minU/!maxU`（原本疑似有問題、後來 CDLIMITS 已經不用它，但 `.this.minE` 等成員還在用，Nozzle/Valve/Instrument 也還在用）
- 真正的 wvol bounding box `!wminE/!wmaxE/!wminN/!wmaxN`
- box 中心座標、`efpla`/`nfpla`/`elen`/`nlen`

`check.txt` 裡那根 riser 的真實世界座標已知：`W 366767.319826mm N 236859.958272mm`。下一次重新 Create Drawings 後，把 Command Window 裡 `BOXLIM` 開頭的三行也存進 `check.txt`，我們直接拿這個真實座標去對兩種方盒的邊界，看它是被兩種都收、只被寬的收（縮小版方盒真的漏掉它——坐實最早的楔形猜測）、還是兩種都收（那問題就在 FPLA/VSEC 或別的地方，縮小方盒這條線可以排除）。

**改的是 `.pmlfrm`，這次要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1` 才會生效**（`.pmlfnc` 那邊的 `!dbgln` 診斷不用，會自動重讀）。

### 使用者提供關鍵線索：問題方向反了（2026-08-12）

在等 `BOXLIM` 診斷結果之前，使用者直接貼了 3D model 畫面（不是圖紙）：金色/深黃色是切圖用的 box（轉了 10 度），內部是綠色管——這是真的在 box 範圍內、該畫進圖的東西。box **外面、左側**另外有一條**藍色**管，明顯不在 box 範圍內。

使用者指出：紅框那些多標的管線編號，對應的正是這條**藍色、box 外的管**，不是「box 裡的管沒畫出來」。

這翻轉了先前的假設方向。之前的推理鏈是「這些元件 `IDLN` 查出來是 `Included`、位置也對得上，所以問題在 view 沒把它畫出來」——但如果它們根本不該在 box 裡，`Included` 本身就不該是 `true`，問題就不是「view 漏畫」，是**「收集階段把 box 外的東西收了進來」**。這正好對回最早（`.CheckInSheetBand()`／`.CrossingOfTube()` 加入的那次改動）就留過的一個缺口，一直沒有實際驗證過：

```pml
define method .CheckInSheetBand(!elem is string, !band is array, !trans is array) is boolean
	!answer = true
	if (!trans[10] neq 1) then
		var !wvol wvol of $!elem
		handle any
			-- 沒有體積可以比對，直接放行 --
		elsehandle none
			...做真正的圖紙座標重疊檢查...
		endhandle
	endif
	return !answer
endmethod
```

`WITHIN` 收集用的世界方盒本來就是「包住轉過的 box 的世界軸對齊超集合」，範圍一定比真正的 box 大，這是刻意的、安全的（見更早「box 相對世界座標歪一個角度」那節），**過濾漏網之魚的責任全部壓在 `.CheckInSheetBand()` 這道複驗上**。而它查 `wvol of $!elem` 時，`!elem` 對 implied TUBE（`IL TUB OF ...`）而言是不是真的能查到 WVOL，這次會第一次靠診斷確認——如果查不到，直接 `handle any` 放行，等於這道複驗對所有 implied tube 形同虛設，退回到「只要落在超集合裡就收」，那條藍色管只要有一小段（或它的世界方盒一角）落進超集合，就會被收進來標註。

`.pmlfrm` 的 `.CheckInSheetBand()`（`:2034-2050`）加了一行 `$p CHECKBAND WVOL-FAIL elem=$!elem`，放在 `handle any`（WVOL 讀不到）那個分支——如果那條藍色管的 implied tube 觸發了這行，就證實是這個缺口；如果完全沒觸發，代表 WVOL 讀得到、問題出在 `.SheetLimitsOfVolume()` 或 `.ViewSheetTransform()` 的座標換算本身算錯（兩個都已經手算驗證過公式，但沒有拿真實數字對過，不排除還是有問題）。

**下一次重新 Create Drawings 時**，麻煩把 Command Window 裡 `BOXLIM`（前一節加的）跟 `CHECKBAND`（這節加的）開頭的行都存進 `check.txt`——兩者會在同一次執行裡一起出現，不用分兩次測。

### 實機驗證結果：WVOL 沒有失敗，但用 BOXLIM 的數字反算出真正落點（2026-08-12）

`check.txt` 全文**沒有任何一行 `CHECKBAND WVOL-FAIL`**——`.CheckInSheetBand()` 對每一個元件（包括所有 implied tube）查 `wvol of` 都成功，先前「implied tube 讀不到 WVOL、直接放行」這個猜測**排除**。

但 `BOXLIM` 印出的兩組方盒，直接拿紅框那根 riser（`Copy-of-100-C-12`，`check.txt` 裡 `W 366767.319826mm N 236859.958272mm`）的座標去對，可以確認它真正的落點：

```
縮小版方盒：minE=-366090.48  maxE=-356929.33
wvol 超集合：wminE=-367019.93 wmaxE=-355999.88
riser E = -366767.32
```

`-366767.32` **小於** `-366090.48`（縮小版方盒的西界）——不在縮小版方盒內，但落在 `wvol` 超集合的範圍裡（`-367019.93` 到 `-355999.88` 之間）。換算成局部座標（用 `efpla`/`nfpla`、box 中心 `boxE=-361509.91` `boxN=239874.36` 手算），這根 riser 在 box 自己的旋轉座標系裡，沿 `efpla`（東西向）方向大約在 box 真正邊界**外側 1000mm 左右**——不是貼著邊界的誤差，是**明顯在 box 外**，跟使用者說「藍色管在 box 外」完全吻合。

問題就是：`.CheckInSheetBand()` 的 `wvol of` 查詢成功、`.SheetLimitsOfVolume()` 也算出了一個 `!lim`，但這個 `!lim` 顯然跟 `!band`（真正邊界附近的窄帶）判定成有重疊，才會 `answer=true` 一路被收進來標註。`!bandthin`（TYPE 1 用的窄帶深度）只有 `10mm 模型 × vsca`，這個案子 vsca 落在 0.0333 附近，換算下來窄帶只有約 0.3mm 深——一個真正在 box 外 1000mm 的元件，不應該有任何機會落進一條 0.3mm 深的窄帶，除非 `.SheetLimitsOfVolume()` 或 `.ViewSheetTransform()` 算出來的座標本身就是錯的（不只是精度問題，量級對不上）。

### 下一步：直接印 `.CheckInSheetBand()` 內部比較的兩組數字

`.CheckInSheetBand()`（`:2048-2059`）的 `elsehandle none` 分支加了一行：

```pml
$p CHECKBAND elem=$!elem answer=$!answer lim=$!lim[1] $!lim[2] $!lim[3] $!lim[4] band=$!band[1] $!band[2] $!band[3] $!band[4]
```

這會印出**每一個**查得到 WVOL 的元件、它换算到圖紙座標的 `!lim`（元件的圖紙外框）、以及當下比對用的 `!band`（窄帶範圍），還有最後的 `answer`。輸出量會比之前大（TYPE1/2a/2b/3/equipment、四個邊都會印），下次把 Command Window 全部內容存進 `check.txt` 即可，我會直接用元件 ref（`=2013286676/3253`、`/3254`、`/3255`、`/3248`、`/3249`、`/3251` 這幾個已知在紅框那根 riser 上的 ref，以及它們對應的 `IL TUB OF` implied tube）去撈出相關的行比對 `!lim` 跟 `!band` 的實際數字，直接看是 `!lim` 算錯、還是 `!band` 算錯。

**改的還是 `.pmlfrm`，一樣要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1`。**

### 實機驗證結果：印太兇，Command Window 捲軸把想看的行擠掉了（2026-08-12）

那個「每個查得到 WVOL 的元件都印」的診斷太貪心：這次重新 Create Drawings，`.CheckInSheetBand()` 在四個邊 × 五種類型（TYPE1/2a/2b/3/equipment）加起來被呼叫幾百次，`check.txt` 存回來的 171 行**全部是 `CHECKBAND`，一行 `TYPE1` 都沒有**，而且 `3249`/`3251`/`3253`/`3254` 這四個 ref 完全沒出現——不是這次沒被呼叫到，是 Command Window 的捲動緩衝區被灌爆，較早印出的內容（包含這幾個 ref、以及所有 `TYPE1` 那組診斷）在使用者複製的時候已經被沖掉了。唯一還留著的兩個（`3248`、`3255`）看數字也對不上：`band` 寬達 300+mm，明顯是 TYPE2a/2b/equipment 那種寬帶，不是 TYPE1 用的 0.3mm 窄帶，所以連這兩筆都不是我們要看的那次呼叫。

**改法**：把印出條件收窄到只印這六個已知在紅框那根 riser 上的 ref（`3248`/`3249`/`3251`/`3253`/`3254`/`3255`，含它們的 `IL TUB OF` implied tube），其餘一律不印：

```pml
if (!elem.matchwild('*3248*') or !elem.matchwild('*3249*') or !elem.matchwild('*3251*') or !elem.matchwild('*3253*') or !elem.matchwild('*3254*') or !elem.matchwild('*3255*')) then
	$p CHECKBAND elem=$!elem answer=$!answer lim=$!lim[1] $!lim[2] $!lim[3] $!lim[4] band=$!band[1] $!band[2] $!band[3] $!band[4]
endif
```

這樣輸出量會降到幾十行，跟 `.pmlfnc` 那邊本來就有、且已經證實印得下的 `TYPE1`（`!dir.eq('left')`，上一次 330 行都完整存下來過）加在一起，應該不會再把彼此擠出緩衝區。

**還是 `.pmlfrm`，一樣要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1`。**

### 實機驗證結果：找到真正原因了（2026-08-12）

收窄後的 `check.txt` 終於同時拿到 `TYPE1` 跟 `CHECKBAND` 兩組數字，而且問使用者直接在 E3D 點了那條藍色管確認就是 `Copy-of-100-C-12`（跟一路假設的一樣）。拿 `/3248` 這筆對數字：

```
CHECKBAND elem==2013286676/3248 answer=TRUE
  lim = 196.558 180.782 206.649 191.868   (元件 WVOL 換算到圖紙座標的外框)
  band= 201.935 136.558 202.268 493.442   (TYPE 1 左邊界窄帶，寬只有 0.33mm)
```

`!lim` 橫跨 196.6~206.6，寬達 10mm，band 只有 0.33mm 寬、剛好整條落在 `!lim` 的範圍裡——`!lim` 的中心點 `(196.558+206.649)/2 = 201.6`，比 band 的左界 `201.935` 還小 0.33mm，也就是**這個元件的圖紙中心其實在 band 外面一點點，但因為它的圖紙外框有 10mm 寬，還是「碰到」了那條窄帶，判定成重疊**。

**根因**：`.CheckInSheetBand()` 拿元件的 `WVOL`（世界座標軸對齊的外框）換算到圖紙座標再跟窄帶比對。`WVOL` 是**世界軸對齊**的，box 轉了 10 度之後，同一個元件的真實外框（可能只是一個普通尺寸的凡爾/法蘭，實體沒多大）投影到圖紙座標系，會因為兩個座標系差了角度而被「斜著撐大」成一個更大、對角拉長的矩形——不是元件真的變大了，是**軸對齊外框硬套進轉過的座標系必然產生的膨脹**。`!bandthin`（TYPE 1 用的窄帶深度）只有模型 10mm，換算成圖紙才 0.33mm，本來就是設計成「幾乎貼著邊界才算數」的門檻，但只要元件的圖紙外框被撐大超過 10mm（很常見），這個窄帶幾乎攔不住任何東西——元件即使中心點明顯在 box 外，外框的一角只要划過那條線就算「有重疊」。

box 是正的時候 `WVOL` 换算不會被撐大（軸對齊的世界座標系跟圖紙座標系方向一致），這個問題才一直沒被踩到。

### 作法

`functions/DrawingPlan1LineNoAnnotation.pmlfnc` 的 TYPE 1 迴圈：拿掉一開始（拿到原始 collect 項目、還沒做 mtbe 換算之前）呼叫 `.CheckInSheetBand()` 的那次判斷，改成在算出 `!memenupos`／`!memshpos`（元件真正會拿去標註的那個代表點，implied tube 已經套用 `.CrossingOfTube()` 的交點覆寫）之後，直接拿這個**點**跟 `!band` 比對範圍：

```pml
!inband = true
if (!memshx.lt(!band[1]) or !memshx.gt(!band[3]) or !memshy.lt(!band[2]) or !memshy.gt(!band[4])) then
	!inband = false
endif
```

一個點沒有「軸對齊外框」可以被撐大，不會受轉角度影響；而且這個點本來就是最後真的會拿去畫標註的那個位置，比起元件整個外框，語意上也更貼近「這個標註是不是真的在邊界附近」。

**沒有動** `TYPE 2a/2b/3/equipment` 幾段——那幾個用的 `!banddeep`（33%）/`!bandshal`（10%）比 `!bandthin`（0.33mm）寬得多，同樣的膨脹問題在那個尺度下不容易造成誤判，這次沒有實測證據顯示那幾段有壞，先不動，維持改動範圍只對症下藥。

**這次只改了 `.pmlfnc`，不用 kill/show，`.pmlfnc` 每次呼叫會自動重讀**，直接重新 Create Drawings 即可。

### 實機驗證結果：主要問題修好了，但抓到一個浮點邊界的小回歸（2026-08-12）

`check.txt` 顯示 `Copy-of-100-C-12`（`3231`~`3268` 全部）這次每一筆都正確判定 `inband=FALSE`，`error.png` 的紅框重複標籤也從 `EL+100566` ×3 + `EL+100553` 收斂成 `EL+102278` ×2——主要症狀解決。

但同時發現新的嚴格點座標比對，對真正落在邊界上的交點會不穩定：

```
pipe=Copy-of-100-B-1  inband=TRUE  memshx=201.934545  band[1]=201.9345455
pipe=Copy-of-150-A-3  inband=FALSE memshx=201.934545  band[1]=201.9345455
```

兩筆印出來的 `memshx` 到小數點後 6 位完全一樣，`Copy-of-150-A-3` 那筆 `crossenu` 也是真的算出交點（不是 `NONE`），照理該保留，卻被判定在邊界外。原因：真正的邊界交點本來就是**從邊界線本身**算出來的，跟 `!band[1]`（也是從邊界線算出來的）理論上該是同一個數，但兩者的浮點運算路徑不同（一個經過 `.CrossingOfTube()` 的 `enupos of`，一個經過 `.ViewSheetTransform()` 的差分），完整精度下可能各自帶著 1e-7mm 量級的誤差，剛好卡在門檻兩側。

**作法**：比對加上 `0.01mm` 容差（`!postol`），這個量級遠低於任何有意義的幾何差異，只用來吃掉浮點噪訊：

```pml
!postol = 0.01
!inband = true
if (!memshx.lt(!band[1] - !postol) or !memshx.gt(!band[3] + !postol) or !memshy.lt(!band[2] - !postol) or !memshy.gt(!band[4] + !postol)) then
	!inband = false
endif
```

**還是只改 `.pmlfnc`，不用 kill/show**，直接重新 Create Drawings。這次要看兩件事：`Copy-of-100-C-12` 的紅框標籤應該完全消失（不是只剩 2 筆）；`Copy-of-150-A-3`／`Copy-of-100-B-1` 這種真正的邊界交點應該都還在，沒有被容差加大之後又誤刪或誤留別的東西。

### 實機驗證結果：TYPE 1 完全乾淨了，剩下的來自 TYPE 2a/2b/3（2026-08-12）

TYPE 1 這次只留下 3 筆（`Copy-of-100-B-1`、`Copy-of-100-C-13`、`Copy-of-250-B-5`，全部是真正穿過左邊界的交點），`Copy-of-100-C-12` 的每一個管件都正確判成 `inband=FALSE`。TYPE 1 到此確認修好。

但圖上還有 `Copy-of-100-C-12` 的標籤，因為 **TYPE 2a/2b/3 三段都還在用舊的 `.CheckInSheetBand()`（WVOL 版）**。用 `check.txt` 的數字驗算：那根 riser 的圖紙點是 `memshx=201.863495`，而 TYPE 2a/2b/3 用的 `!banddeep` 左帶起點是 `band[1]=201.9345455`——**點在帶外 0.07mm**，但它的 WVOL 換算外框橫跨 `196.56~206.65`，照樣蓋過帶的起點，所以 WVOL 版一律放行。同一個膨脹問題，只是換一段程式碼。

**作法**：TYPE 2a/2b/3 三段比照 TYPE 1 改成點座標比對（一樣的 `!postol = 0.01`），拿掉迴圈開頭那次 `.CheckInSheetBand()` 呼叫。**equipment 那段沒有動**：設備本來體積就大、WVOL 大是實情不是膨脹假象，而且它後面本來就有自己的「大部分體積在 view 內」「pos 在 view 內」兩道檢查，沒有證據顯示它有問題。

三段各加了一行 `$p TYPE2A/2B/3 KEPT ...` 診斷（一樣只在 `!dir.eq('left')`），下一輪就能把圖上剩下的每個標籤歸到來源。

### 實機驗證結果：`Copy-of-100-C-12` 從一堆收斂成 1 筆，而且那 1 筆看起來是對的（2026-08-12）

TYPE 2a/2b/3 改成點座標比對之後，`check.txt` 裡 `Copy-of-100-C-12` 只剩 **1 筆**（`TYPE3 KEPT ... memshx=230.524117 memshy=196.046627`），圖上也只剩一個 `Copy-of-100-C-12 BOP EL+102278`。

**這 1 筆很可能是正確的，不是漏網之魚**：view 的圖紙矩形是 X `201.93~512.07`、Y `136.56~493.44`，而這個彎頭在 `(230.52, 196.05)`——**距離左邊界 28mm、距離下邊界 60mm，扎扎實實在 view 裡面**，不是貼在邊界外的那根 riser（那根在 `memshx=201.86`，已經被正確排除）。也就是說 `Copy-of-100-C-12` 這條管**一部分在 box 外（riser 那段）、一部分在 box 內（這個彎頭）**，內側那段本來就該標。

### 已確認：`Copy-of-250-B-5 BOP EL+104716` 標兩次是合理的，不用改

使用者確認：**同一條管在同一側、但在明顯不同的兩個位置各標一次，算合理**。這兩筆來源不同（一筆 TYPE 1 的邊界交點 `memshy=355.49`，一筆 TYPE 3 的彎頭 `memshy=221.42`），Y 差 130 多 mm，`!types` 併回 `!result` 那道 4mm 去重（`:706`）本來就攔不住，行為正確，不動。

### 推翻：剩下那 1 筆 `Copy-of-100-C-12` 也是錯的（2026-08-12）

上一節推論「這個彎頭距離左邊界 28 圖紙 mm、在 view 裡面，所以標它是對的」——**使用者看 3D 實機否決了這個推論**：那條引線指到的是 model 裡被反白（洋紅色）的那個彎頭，位置就在 box 邊界上，**並不在 box 裡面，不該標**。

所以「`memshx=230.52`（換算約在 box 內 857mm）」這個數字**對不上實際幾何**。

> **後續（同日）**：不是歸錯元件——`/3256` 的座標是對的，圖紙座標也是對的。對不上的原因是 **view 本身轉錯邊**，圖紙座標系跟 box 座標系差了 20 度，所以「圖紙上在框內」跟「實際上在 box 內」是兩回事。見下一節。
>
> 同一節提到的另一個疑點——`/3256`、`/3257`、`/3258`、`/3280`、`/3281`、`/3282` 六個連續元件圖紙座標**完全相同到小數點後 6 位**（`230.524117, 196.046627`）且橫跨 `C-12`／`C-13` 兩條管——**還沒有解釋，也還沒查**。`/3256` 本身經實機 `q worpos` 確認是對的，所以至少它不是殘值；但其餘幾個是否為 `var !memenupos worpos of $!mem` 查詢失敗後 PML 保留舊值，仍未確認。它們這次都被判在框外丟掉了所以沒出事，但這是會讓元件被標到**別人位置**的隱患，列在下面「還沒做」。

### 真正的根本原因：view 的旋轉方向反了（2026-08-12，**已實機驗證，結案**）

拿到實機數值之後對出來的。使用者查出的 ground truth：

```
=2013286676/3256  →  Wposition W 365866.221mm N 237018.846mm U 102335.1mm
box               →  Wposition W 361509.906mm N 239874.364mm U 104749.08mm
                     Xlength 9302.428mm  Ylength 10704.993mm  Zlength 9498.161mm
                     Orientation Y is S 10 E and Z is U
```

元件座標、box 中心、`elen`/`nlen` 全部跟 `BOXLIM` 印的一致——**兩邊的輸入資料都是對的**，所以先前那兩個懷疑方向（BOXLIM 數字不符、`worpos` 讀到殘值）都排除。

用 `ori Y is S 10 E` 推回去：`boxYdir = (0.1736, -0.9848)`、`boxXdir = (-0.9848, -0.1736)`，走完 `.Apply()` 的分支得到 `efpla = E 10 N`、`nfpla = N 10 W`、`elen = xlength`、`nlen = ylength`——跟 `BOXLIM` 印的完全一樣。拿這組軸算 `/3256` 在 box 自己座標系的位置：

```
u（沿 efpla）= -4785.98   對照半長 4651.21  →  超出 135mm，在 box 外 ✓ 跟使用者說的一致
v（沿 nfpla）= -2055.68   對照半長 5352.50  →  這個方向在內
```

但同一顆元件的**圖紙**座標反推出來卻是內縮 857mm。兩者差 20 度。再用 `/2860`（管與西邊界的交點，圖紙 X 剛好落在西邊界上）交叉驗證：它在 box 座標系是內縮 1310mm，在圖紙座標系卻剛好在邊界上。

**結論：sheet X 軸對應的模型方向是 `E 10 S`，而 box 的軸是 `E 10 N`——view 轉錯邊了。**

原因在 `.Apply()`（`:627` 附近）：

```pml
!temp = !efpla.angle(object direction('E'))
...
Adegrees $!temp
```

`.angle()` **只回傳 0~180 的無號角**。box 往北偏 10 度和往南偏 10 度，這行都得到 `10`，然後一律 `Adegrees +10`——其中一種轉向必然是錯的。**這跟 README 前面記過的流向箭頭 bug 是同一類**（「`angle()` 只回傳無號角，正負號必須由別的東西決定，門檻應該是 90 度不是 40 度」那節），只是當時沒發現這裡也踩到。

**後果**：view 的外框不再等於 box 的外框，而是 box 繞自己中心轉了 **兩倍角度（20 度）** 的矩形。於是 box 外的元件投影進框內（被標註），box 內的東西被裁掉（留下空白）。使用者最早回報的「紅框那片沒有管子卻標了一堆編號」，根源就是這一件事——不是標註邏輯，是 view 本身擺錯角度。

因為兩種轉向都得到同一個 `Adegrees`，**正的 box（角度 0）完全不受影響，往南偏的 box 一直都是對的**，只有往北偏的 box 會壞，所以這個 bug 能存活這麼久。

### 作法

補回 `.angle()` 丟掉的正負號，判斷方式沿用這個檔案同一段既有的寫法（比對 N/S 哪個夾角小，不依賴 DIRECTION 有沒有 `.north` 這種屬性）：

```pml
!temp = !efpla.angle(object direction('E'))
if (abs(!efpla.angle(object direction('N'))) lt abs(!efpla.angle(object direction('S')))) then
	!temp = !temp * -1
endif
```

用修正後的角度重算，兩顆有問題的元件都會落到框外、自然被排除：

| 元件 | box 座標 u | 修正後圖紙 X | view 矩形 X 範圍 |
|---|---|---|---|
| `/3255` | −5700.97（外 1050mm）| 166.97 | 201.96 ~ 512.04 → **框外** |
| `/3256` | −4785.98（外 135mm）| 197.47 | 201.96 ~ 512.04 → **框外** |

### 實機驗證結果：正確（2026-08-12）

使用者並排比較修改前後兩張圖：

- **柱位線（藍色點鏈線）與 match line 現在跟圖框正交**，修改前是整片斜掉的。這正是「view 外框終於等於 box 外框」該有的樣子——廠區格線本來就跟 box 對齊，所以在正確的 view 裡一定是正的。
- **多餘的 `Copy-of-100-C-12` / `Copy-of-100-C-13` 標籤消失**。
- 使用者判定：「這個版本應該是對的」。

一併確認了先前所有繞路的方向都只是治標：真正的缺陷從頭到尾都是 view 擺錯角度，不是標註邏輯。

### 收尾

- `functions/DrawingPlan1LineNoAnnotation.pmlfnc` 的 `!dbgln` 改回 `false`（比照 `DrawingPlan1FlowAnnotation` 保留 `!dbg` 的作法，整套診斷留著備用，不刪）。裡面最有價值的是 **`LABEL` 那行**：每畫出一個標籤就印一行，帶元件 ref 和是哪個 TYPE 找到的，圖上任何一個標籤都能直接回溯，不必再靠推測——這次就是靠它才定位到問題。
- `forms/DrawingPlan1.pmlfrm` 的 `BOXLIM` 三行 `$p` 已移除（無條件輸出，留著會每次洗畫面）。`CHECKBAND` 那行也先前移除了。

### 先前卡住的地方（保留記錄）：程式算出來的座標跟實機看到的位置對不上

`LABEL` 診斷確定了標籤來源：

```
LABEL pipe=Copy-of-100-C-12 src=type3 mem==2013286676/3256 type=ELBO
      mempos=W 365866.220732mm N 237018.846355mm U 102335.1mm
      mempossh=X 230.524117mm Y 196.046627mm
```

使用者實機導到 `/3256` 確認：**`/3255` 和 `/3256` 兩顆彎頭都不在 box 裡**。

但程式的數字說 `/3256` 在 box **裡面**。當時的理由是「view 在圖紙上的矩形**就是** box 的外框（`size = elen × nlen × vsca`），所以只要比圖紙座標就夠」——**這個前提正是後來查出來壞掉的那件事**（view 轉錯邊，框跟 box 差 20 度），所以下表的最後一欄結論是錯的，保留只為記錄當時的推理：

| | 圖紙 X | view 矩形 X 範圍 | 換算成 box 長軸座標 | 對照半長 4651.21 |
|---|---|---|---|---|
| `/3255` | 201.863 | 201.96 ~ 512.04 | −4653.35 | 超出 **2.1mm**（在外，已排除）|
| `/3256` | 230.524 | 201.96 ~ 512.04 | −3794.28 | 內縮 **857mm**（在內）|

（`vsca = 0.0333333`，view 角點各含 ±0.025mm 容差；用 `/2860` 那筆「管與西邊界的交點」校驗過：算出來剛好落在西面邊界上，誤差 0.76mm，所以換算式本身是對的。）

`/3256` 的高程 `U 102335.1` 也在 box 的 `minU 99999.97 ~ maxU 109498.19` 之內。三個方向都在裡面。

**兩件事必有一件錯**，但不是靠再推導能解決的：

1. `BOXLIM` 印出的 box 中心／尺寸（`boxE=-361509.906 boxN=239874.364 elen=9302.428 nlen=10704.993`）跟實機那個 box 不符——例如那組數字是別的 box 的、或 box 在出圖後被移動過。
2. `/3256` 的 `worpos`（`W 365866.22 N 237018.85 U 102335.1`）不是它真正的位置。

第 2 點有個旁證值得留意：`check.txt` 裡 `/3257`、`/3258`、`/3280`、`/3281`、`/3282` 的座標跟 `/3256` **完全相同到小數點後 6 位**，還橫跨 `C-12`／`C-13` 兩條管，幾乎確定是 `var !memenupos worpos of $!mem` 查詢失敗時 PML 保留舊值。不過 `/3256` 這一筆在 TYPE 1 和 TYPE 3 兩個**獨立**迴圈都算出同一個值（兩者的前一個元件不同，若是殘值應該會不一樣），所以 `/3256` 本身看起來是讀到的、不是殘值。

**下一步不再推導，直接取實機數值比對**：請使用者在 E3D 裡分別對 `/3256` 和那個切圖 box 查 `worpos` / `xlength` / `ylength` / `zlength` / `ori wrt worl`，跟 `BOXLIM` 對照，看是哪一邊對不上。

### 先前那一步：把診斷放在「標籤真正產生的那一行」

先前幾輪的診斷都印在**收集階段**，然後由我推論哪一筆變成哪個標籤——這一步猜錯過不只一次。改成直接在 DPOI 產生處（`:871` 附近，`NEW DPOI POS` 之前）印一行：

```pml
$p LABEL pipe=$!dbgpipe src=$!dbgsrc mem=$!mem type=$!type mempos=$!mempos mempossh=$!mempossh
```

`src` 是 `type1`/`type2a`/`type2b`/`type3`/`type4`，`mem` 是元件 ref，`mempos`/`mempossh` 是這個標籤實際用的世界座標與圖紙座標。**圖上看到的每一個標籤，都會對應到剛好一行 `LABEL`**，不需要再由我推測對應關係。

下一輪請把 `LABEL` 開頭的行一起存進 `check.txt`——只要找出 `pipe=Copy-of-100-C-12` 那一行，就能直接知道是哪個元件、哪個 TYPE、座標多少。

### 更正一個先前寫錯的數字

前面「用 `BOXLIM` 反算」那段說這根 riser 在 box 邊界外約 **1000mm**，**這個數字是錯的**——那是我用 `efpla`/`nfpla` 手動反推局部座標時算錯的（當時也已經察覺推導有矛盾）。用程式自己算出來的圖紙座標對照才是對的：`memshx=201.863` 對 view 左邊界 `201.9345`，差 **0.07 圖紙 mm**，換算回模型大約 **2mm**。也就是這根管只是**剛好貼在 box 邊界外面一點點**，不是離很遠。這不影響結論（在外面就是在外面，不該標），但避免下次拿錯的量級去判斷別的事情。

### 還沒做

- ~~**六個元件圖紙座標完全相同的疑點**~~ → **查證後沒有問題，結案（2026-08-12）**。實機查五個元件的 `worpos`：E/N 全部是 `W 365866.221 N 237018.846`，但高程各不相同（`/3256` 102335.1、`/3257` `/3258` 102106.5、`/3280` 100835、`/3281` 100833.5、`/3282` 100604.9）。也就是這六個本來就落在**同一條鉛直線**上——C-12 的立管在 `U 102106~102335`，C-13 的立管在 `U 100605~100835`，兩條管在同一個平面位置上下疊置。平面投影是同一點，圖紙座標相同是**正確**的，`worpos of` 沒有失敗、也沒有沿用殘值。
  > 當初誤判的原因：前面才確認過 `/3248`~`/3255` 共用座標是立管的正常現象，卻在「跨兩條不同的管」這點上直接跳到「不可能重疊」，漏掉兩條管上下疊置也會共用平面位置。**同一個平面座標出現在不同管線上，不足以推論是殘值——要比對高程才算數。**
- **1mm 去重門檻**：同一條管在同一邊重複標，TYPE 1 只濾掉圖紙相距 1mm 以內的（TYPE 2/3/4 對 TYPE 1 用的是 4mm）。修好 view 之後的圖面已經看不到同編號同高程的重複，**目前沒有證據顯示這是問題**，不要為了改而改；若之後又出現貼在一起的重複標註再回來調。
- ~~**Nozzle / Valve / Instrument / ATTA 仍用縮小的方盒收集**~~ → **已改，尚未實機驗證（2026-08-12）**，見下方專節。
- **`limits` / `:CDLIMITS` 改用 wvol bounding box 那次改動，效果從未被單獨驗證**：當時實機沒有變化，被判定為疑似無效更動而保留。view 轉向修好之後應該回頭確認一次它到底有沒有必要、有沒有副作用。

## 已改：Nozzle / Valve / Instrument / ATTA 在轉過的 box 會漏標（2026-08-12，**尚未實機驗證**）

### 問題

`.NozzleAnnotation()`、`.ValveAnnotation()`、`.InstAnnotation()` 和支撐的 ATTA 收集，四處都是同一個寫法：

```pml
var !nozzs coll <type> within E $!this.minE N $!this.minN U $!this.minU TO E $!this.maxE N $!this.maxN U $!this.maxU
```

`!this.minE .. .maxN` 是 box 各面沿 box 自己的方向量出來的值，box 轉過角度之後等於 **box 各邊乘 cos(角度) 的縮小版**（推導見上面 LIMITS/CDLIMITS 那節）。實測數字：`minE=-366090.48` 對真正的 `wminE=-367019.93`，差 **929mm**；N 方向差 **808mm**。也就是 box 四個角落各有一塊寬達 0.8~0.9m 的區域**根本不會被收集到**，裡面的管嘴／閥件／儀錶／支撐就靜靜地不標，不會有任何錯誤訊息。

而且這四處**完全沒有圖紙座標複驗**——LineNo 那邊至少還有一道，這裡連一道都沒有。

### 作法

跟 LineNo 同一個模式：**用足夠大的世界方盒收集，再用圖紙座標把多收的丟掉**。

1. 新增 4 個 member `.wmaxE / .wminE / .wmaxN / .wminN`，在 `.Apply()` 裡跟 `.maxE` 等一起設定，值取自 box 的 `wvol`（世界 bounding box，一定包住轉過的 box）。
2. 四處的 `COLLECT ... WITHIN` 改用這組值。U 範圍不變——box 只繞鉛直軸轉（`ori ... Z is U`），`wvol` 的 U 範圍跟 `minU`/`maxU` 相同。
3. 新增 `.InViewOnSheet(!shpos)`：判斷一個圖紙座標字串是否落在 view 的矩形內。四個迴圈本來就已經算出 `!apos1 = shpos of !apos`，所以直接拿它來擋，`skip` 掉框外的。

**正的 box 行為完全不變**：`wvol` 就等於 box，收集範圍一樣，而 box 內的元件投影必定落在 view 矩形內，全部通過。

`.minE / .maxE / .minN / .maxN` **維持原本的面中心值沒有動**——MATCH LINE 的文字（`MATCH LINE N 244xxx`）要印的是 box 的邊界座標，用面中心的值才對，不能換成 bounding box。

**支撐那段的順序有調整**：原本 `NEW SLAB` 在算出位置之前，現在把位置查詢提到迴圈開頭、先擋掉框外的再建立 SLAB，免得替一個馬上要丟掉的 ATTA 建出空的標註元素。

### 實機要看的地方

1. **正的 box 應該完全沒變**（管嘴／閥件／儀錶／支撐標註數量與位置一模一樣）。
2. **轉過的 box 應該多出角落的標註**——之前漏掉的那些。
3. **不應該出現框外的標註**。若有，代表 `.InViewOnSheet()` 的矩形取錯了。

## 已改：標籤連接點的排序丟給 AteSortLineNo 會炸（2026-08-12，**尚未實機驗證**）

症狀（見 `error.png` 左半，同一張圖）：box 轉 10 度之後，Create Drawings 跑到一半跳

```
PML Error in method METHOD：輸入字串格式不正確。
In line 1040 of PML function drawingplan1.APPLY
    !sortedtypes = !obj.method('y', !tboxp)
```

`輸入字串格式不正確` 是 .NET `FormatException` 的中文訊息，`AteSortLineNo.Method()` 裡唯一會丟它的是 `double.Parse(entrystrs[0])`，也就是排序鍵。那個鍵在 PML 這邊是這樣組出來的：

```pml
!apos1.position().distance(!tempp).string().replace('mm', '')
```

**確定的部分**：距離被 `.string()` 轉成字串、跨過 PML.NET 邊界、再讓 C# 重新 parse 回數字，而某個角度下這個字串不是 `double.Parse` 吃得下的形式。**沒有確定的部分**：實際炸掉的那個字串長什麼樣（沒有印出來）。README 6-3 記過的兩次是 `.up` 把 `mm` 帶進鍵裡，這一處已經有 `.replace('mm','')`，所以不是同一個。

為什麼轉 10 度才出現：這段在算「標籤方框四條邊」與「引線」的交點。box 正的時候引線通常斜穿方框，四個交點離附著點都有明確距離；轉過角度之後引線方向跟著轉，容易讓某個交點幾乎剛好落在附著點上。所以角度本身沒問題，是角度改變了幾何、踩到這個既有地雷。

### 作法

不去猜那個字串，直接**把這條「數字 → 字串 → 數字」的路徑拿掉**。這裡本來就只是要「四個交點裡離附著點最近的那個」，用不著排序，更用不著跨語言：

- `!tboxp`（打包好的字串陣列）換成 `!tboxpt`（直接存 POSITION）。
- 在 PML 裡跑一個小迴圈比 `.distance()` 取最小，距離全程是 PML 的 real。
- 標籤中心點改成直接讀 `!lines[!i].part(2) / part(3)`（原本繞一圈從打包字串第 3 欄拆回來的就是這兩個值）。
- 加 `if !tboxpt.size().gt(0)`：四條邊都沒有有效交點時就不下 `cpoftx`，維持原本的連接點，不會拿空陣列去索引。

這段因此不再用到 `AteSortLineNo`，但**授權檢查不受影響**——`.Apply()` 開頭的 `.CheckCompanyNetwork()` → `IsAuthorized()` 照跑。

### 實機要看的地方

錯誤不再出現之外，要確認**引線的連接點仍然落在標籤方框邊上**，不是跑到方框中心（那樣引線會穿進文字裡）。

## 已改：把隱藏在 AteSort/AteSortLineNo 裡的公司網路授權檢查獨立出來（2026-08-11，**已實機驗證，結案**）

### 背景

使用者發現：流向標註那次改動（見下方「6-6 排序改用手寫選擇排序」）把 `AteSortLineNo` 換成手寫排序後，一個原本藏在這個物件建構裡的授權機制也跟著被拿掉了——`atesort.dll`（`AteSort` / `AteSortLineNo` 兩個類別）除了排序，還會嘗試連公司的 SQL Server，藉此判斷「是不是在公司網路內」，藉此限制轉平面圖工具能不能執行。

### 讀原始碼後的實際發現（`D:\Documents\NET_Code\E3D\AteSort\AteSort.cs`、`AteSortLineNo\AteSortLineNo.cs`）

兩個類別各自的 `Method`/`Method1` 開頭都內嵌同一段（完全重複，兩個組件各一份）：

```csharp
string connectionString = "Server=SVR26;Database=isometric;User Id=sa;Password=AteMorphine57272!;";
...
catch (SqlException ex)
{
    if (Environment.MachineName == "PANB19052") { checkok = true; }
    if (!checkok) { MessageBox.Show("..."); }  // 亂碼，Big5 訊息被存成別的編碼
}
```

幾個跟原本認知不同、值得注意的地方：

1. **不是拋例外中止，是靜靜回傳空的 Hashtable**。`SqlException` 在方法內被接住，`checkok = false` 時直接跳過排序邏輯、回傳 `new Hashtable()`。呼叫端（PML）拿到空結果後續繼續用 `!sortedtypes[1]` 之類的索引，才會在別的地方炸開——使用者原本認知的「拋出例外、巨集中止」，實際上是這個空結果傳到下游才間接造成的，不是這段本身拋出來的。
2. **`PANB19052` 是主機名稱白名單，形同後門**。只要把任何一台電腦改名成這個字串，離線也能繞過這個檢查，不需要連得到 SQL Server。
3. **`sa` 密碼是明碼寫死在原始碼、編譯進兩個 DLL 裡**。任何拿得到 `AteSort.dll`／`AteSortLineNo.dll` 的人，用 ILSpy/dotPeek 之類的工具幾秒鐘就能反編譯出這個連線字串——等於這組 DLL 只要離開公司就同時外流了公司 SQL Server 的 `sa`（等同資料庫管理員）帳密，風險遠大於「授權檢查被繞過」本身。**這組密碼現在等於已外流，不管這次怎麼改，都建議直接在 SQL Server 上換掉。**

### 這次做的事（只動 PML 端，DLL 沒有重新編譯/部署）

`forms/DrawingPlan1.pmlfrm` 新增 `.CheckCompanyNetwork()`（放在 `.NearEndOfGrid()` 之後、`.CheckDimensionAttachPoint()` 之前）：沿用既有的 `AteSortLineNo` 物件，餵一筆假資料進去，用「回傳結果是不是空的」判斷連線有沒有成功，包成一個有名字、回傳 boolean 的方法。`.Apply()` 開頭第一件事就明確呼叫它，失敗就 `!!alert.error(...)` 並 `return`，不再繼續往下跑。

這樣至少讓這個檢查變成看得見的一步，不會再因為某個函式改寫排序方式就無聲無息消失。**但沒有解決根本問題**——`sa` 密碼、主機名稱白名單這些都還在 DLL 裡，只是現在會被明確呼叫到而已。

### 後續：改成不需要真密碼的版本（2026-08-11）

使用者說明：轉圖程式還沒公佈，這組密碼目前沒有外流風險，但也沒辦法換掉（其他系統還在用）。問題變成「如果還是要用這組帳號，能不能讓程式裡看不到密碼」。

發現一個比「藏起來」更好的答案：**這個檢查其實不需要密碼是對的**。`SqlConnection.Open()` 失敗時，「帳密被拒絕」跟「根本連不到」丟出的都是 `SqlException`，但錯誤碼（`SqlException.Errors[].Number`）不同——帳密被拒絕（如 18456 Login failed）代表 TCP/TDS 交握已經成功，本來就已經證明連得到伺服器，跟登入是否真的成功無關。原本的程式把兩種情況混在一起、一律當失敗，才會需要密碼真的是對的。

**已改**（不在這個 git repo，在 `D:\Documents\NET_Code\E3D\AteSort\AteSort.cs` 與 `AteSortLineNo\AteSortLineNo.cs`）：

1. 兩個檔案都新增 `ReachedServer(SqlException ex)`：檢查 `ex.Errors` 裡有沒有代表「連得到、只是帳密/資料庫被拒絕」的錯誤碼（目前先放 18456 / 4060 / 18452 / 18470，**沒有對著真的 SVR26 校準過**，第一次離線測試時要印 `ex.Number` 對一下，不對就補進 `ReachedServerErrorNumbers`）。
2. `catch (SqlException ex)` 區塊：先判斷 `ReachedServer(ex)`，成立就當作通過；不成立才落到原本的 `PANB19052` 主機名稱後門。
3. 連線字串的帳密換成 `User Id=nobody;Password=notarealpassword;`（外加 `Connect Timeout=5`，避免離線時卡太久）——不是真帳號，因為這個檢查只在乎連不連得到，不在乎登不登得進去。真正的 `sa` 密碼完全沒有出現在這兩個檔案裡了。
4. `MessageBox.Show("...")` 那行亂碼文字**沒有動**（原始檔案編碼看起來就有問題，Read 工具顯示的也是亂碼，不確定原文，怕改錯字改成別的亂碼，維持原樣沒有風險）。

### 後續：連線池讓離線測試測不出來（2026-08-11）

使用者部署新 DLL 後用防火牆規則封鎖 `172.25.41.26`（SVR26）測試，結果 Create Drawings 還是順利跑完（見 `error.png`）。原因不是規則沒生效，是 **ADO.NET 連線池**：`SqlConnection.Close()` 預設不會真的斷線，只是把連線還回池子。如果這個 E3D session 在封鎖之前就已經成功連過一次 SVR26，之後每次 `Open()`/`Close()` 都在重用那條池住的舊連線，根本沒有嘗試建立新連線去撞防火牆規則。

這不只是測試不方便——正式環境下同一個道理會讓這個檢查失去「每次都重新驗證」的意義：使用者在公司內開 E3D（連線成功、被池住）之後帶著筆電離開，同一個 session 裡繼續操作，也會因為吃到池住的舊連線而誤判成還在公司內。

**已改**：兩個檔案的連線字串都加上 `Pooling=False;`，強制每次呼叫都真的重新建立連線。目前狀態：

```
Server=SVR26;Database=isometric;User Id=nobody;Password=notarealpassword;Connect Timeout=5;Pooling=False;
```

**測試時的提醒**：加了 `Pooling=False` 之後，新行為只有在**重新編譯部署的 DLL**生效後才會出現；如果 E3D 還是舊 session、載入的還是舊版 DLL，一樣測不出封鎖效果。務必：改完 build → 完整關閉 E3D → 重開 → 再測一次防火牆封鎖情境。

### 後續：空 Hashtable 當「否」在 PML.NET 邊界不可靠（2026-08-11）

用 hosts 檔案確認真的連不到 SVR26 之後，`AteSortLineNo.Method()` 內部的 `MessageBox.Show(...)` 有正確跳出來（證明 `checkok` 在 .NET 那邊真的是 `false`），但按掉那個視窗後 **E3D 還是順利轉圖，我們自己加的英文 `!!alert.error(...)` 完全沒出現**。

代表 `.CheckCompanyNetwork()` 判斷錯了。原本的寫法是：

```pml
!checked = !obj.method('y', !probe)
return (!checked.size().gt(0))
```

用「回傳的 Hashtable 是不是空的」來判斷成功與否。實測證實：.NET 那邊真的回傳了空的 Hashtable，但轉換到 PML 這邊之後 `!checked.size()` 讀出來不是 0——這個訊號在 PML.NET 的邊界上不可靠，猜測是空的 .NET `Hashtable` 轉成 PML 物件時沒有正確映射成一個 `.size()=0` 的陣列/雜湊表。這是本來就有風險、只是一直沒被抓到的邊界情況（見更早之前的討論，這種失敗路徑幾年來大概沒真的被觸發過）。

**改法**：不要用「結果是不是空的」這種間接訊號，改成讓 .NET 端提供一個**直接回傳 `bool` 的方法**：

1. `AteSort.cs` / `AteSortLineNo.cs`：原本內嵌在 `Method`/`Method1` 裡的連線判斷邏輯抽成共用的 `private static bool CheckNetwork()`，`Method`/`Method1` 改成呼叫它決定要不要繼續排序（行為不變，只是不重複程式碼）。新增 `[PMLNetCallable()] public bool IsAuthorized()`，直接回傳 `CheckNetwork()` 的結果——一個真正的布林值，不必再靠猜 Hashtable 是不是空的。
2. `forms/DrawingPlan1.pmlfrm` 的 `.CheckCompanyNetwork()` 改成直接呼叫 `!obj.IsAuthorized()`，拿掉組假資料、判斷 `.size()` 那一整套，也拿掉先前為了診斷加的暫時 `$p` 除錯輸出。

這也回應了最早設計這個檢查時就提過的建議：失敗要回傳明確的布林值，不要靠副作用/空結果去猜。

### 後續：離線時跳兩次對話框，拿掉 .NET 端的 MessageBox（2026-08-11）

整個流程確認正確運作後，使用者回報離線時會跳兩次對話框：先是 `AteSortLineNo`/`AteSort` 內部 `MessageBox.Show(...)`（那個亂碼文字），按掉才會出現 `.Apply()` 裡我們加的英文 `!!alert.error(...)`。同一次失敗跳兩個「你不能這樣做」的視窗，多餘。

**已改**：`AteSort.cs`、`AteSortLineNo.cs` 的 `CheckNetwork()` 拿掉 `MessageBox.Show(...)`，`using System.Windows.Forms;` 也一併拿掉（兩個檔案裡都只有這一個用途）。理由：`.Apply()` 一開始就會呼叫 `IsAuthorized()` 並在失敗時顯示清楚的英文訊息，`Method`/`Method1` 內部再跳一次原生對話框只是重複，而且那個亂碼文字始終沒人確認過原文是什麼，乾脆拿掉比硬猜著修更乾淨。

`Method`/`Method1` 的行為不變：`CheckNetwork()` 回傳 `false` 時一樣不會排序、回傳空結果，只是不再彈視窗。因為 `.CheckCompanyNetwork()` 已經在 `.Apply()` 最前面擋過一次，正常流程下 `Method`/`Method1` 內部這個判斷不會真的失敗——它比較像是保留給萬一有人繞過 `.Apply()`、直接呼叫這兩個排序方法的防呆。

### 還沒做，需要使用者決定

- **`ReachedServerErrorNumbers` 要對真的 SVR26 校準**：目前四個錯誤碼是常見值，不保證跟這台 SQL Server 版本/防火牆設定回傳的一致。建議先在 `catch` 裡暫時印一次 `ex.Number`，離線跑一次、用錯密碼在線上跑一次，兩邊數字都記下來再調整清單。
- **編譯與部署**：`AteSort.csproj` 的 PostBuildEvent 會直接把編譯結果 xcopy 到 `C:\AVEVA\Everything3D2.10`（正式安裝目錄），這是共用環境，且會影響 `LineNoAnnotation`、`EquiAnnotation`、`MatchLine` 等其他還在用這兩個類別排序的地方——建置與部署需要使用者自己動手驗證，還沒有人幫忙 build。
- **主機名稱白名單 `PANB19052`**：這次沒拿掉，只是排到 `ReachedServer` 判斷之後當備援。要不要整個拿掉（改成別的離線開發繞過方式）由使用者決定。

### 提醒：`.pmlfrm` 改了要重載

這次改的是 `forms/DrawingPlan1.pmlfrm`，照專案慣例（見「陷阱」段落）：form 是常駐物件，`kill !!DrawingPlan1` 再 `show !!DrawingPlan1` 才會生效，否則會看到舊版行為或 `Method <FORM>.CheckCompanyNetwork not found`。

## 已改：流向標註（2026-08-10，**已實機驗證，結案**）

最終參數（`functions/DrawingPlan1FlowAnnotation.pmlfnc`）：

| 參數 | 值 | 作用 |
|---|---|---|
| `!minrun` | 10 | 可見長度低於此值的管段不標。**這是最關鍵的一個**，見 6-7 |
| `!mindist` | 20 | 箭頭之間的理想間距 |
| `!hardmin` | 10 | 可讀性下限，低於此值寧可不標 |
| `!dbg` | false | 診斷開關，需要時改 true |

驗收結果：view 內 20 條分支，標註 7 條、跳過 13 條（5 條可見段 2.5~5.4mm 放不下箭頭，6 條完全沒有可見管段，2 條同上）。標註的 7 條彼此最近 28.3mm，避讓機制未觸發。

rcode = up 與 rcode = left（Portrait to Landscape）兩種情況的箭頭方向都已驗證正確。

下面各節依當時的發現順序記錄，保留錯誤的假設與被推翻的過程，避免重踩。

## 已改：流向標註漏標、位置飛掉、箭頭反向（2026-08-10）

目標規則：圖面上每一條管線至少標一個流向，標在管段最長的地方。`functions/DrawingPlan1FlowAnnotation.pmlfnc` 有四個缺陷讓這條規則做不到，一次改掉。

### 1. 裁切點永遠落在 view 上緣

`shpos of` 回傳的是**字串**，字串沒有 `.distance()`。原本四行 `!distN = !p1possh.distance(...)` 每一行都會掉進自己的 `handle any`，四個距離全部變成代表「沒有交點」的 `1111111111111`，於是 `min(...) eq !dist1` 恆為真，**不管管線實際從哪一邊出圖，裁切點一律被拉到上邊界線上**。上邊界是無限延伸的直線，交點可能遠在圖框外。

作法：`shpos` 拿到之後立刻 `.position()` 轉成 POSITION，之後 `.distance()` 才真的在算距離。另外把 `min(...)` 收進 `!distmin`，四個都是 `!nocross` 時就不動那個端點，不再硬選一邊。

### 2. 型別中途被換掉，整個 function 中斷

`!p1possh` 來自 `var !p1possh shpos of ...`，是 STRING；裁切時卻被指派成 `intersection()` 回傳的 POSITION。**PML 不允許把 POSITION 指派給已經是 STRING 的變數**，會直接拋：

```
(2,761) Cannot assign variable to result - incompatible types (STRING=POSITION)
```

錯誤沒有 `handle` 接，會**中止整個 function**，排在後面還沒處理到的管線全部沒有流向標註——這就是「有些管線沒標」的主因。因為只有端點落在 view 外時才會走到那行，正好都在圖框邊緣，所以一直沒被當成 bug 看。

作法：不要覆寫 `shpos` 的字串，另外開 `!p1pt` / `!p2pt` 兩個 POSITION 變數承接，裁切結果也放這裡，`!mid = !p1pt.midpoint(!p2pt)`。`.CheckInsideView()` 的參數宣告是 string，維持傳原本的 `!p1possh`。

> **陷阱**：這個型別限制是實機跑出來才確認的（見 `error.png`）。第一版修法寫成 `!p1possh = !p1possh.position()` 想「統一成 POSITION」，結果在同一行踩到同一條規則。PML 變數一旦被 `var` 或第一次指派定了型別就不能換，跨型別一律換新變數名。

### 3. 覆蓋不足：一條 PIPE 只標一個，其他分支的管路沒箭頭（第三輪修正）

> 這一節取代下面 3 號原本的作法。第二輪改成「每條 PIPE 只標一次」之後，實機發現一條很長的橫管完全沒有箭頭（見 `error.png` 紅框）——那條是同一條 PIPE 的另一個 BRAN，中間靠立管連上去。

要講清楚的是**這個漏洞原本就有，不是 dedup 改壞的**。原始程式雖然每個 BRAN 跑一次迴圈，但抓管段是用 **PIPE 名**抓的，所以每個 BRAN 都挑到同一根全域最長的管段：一條有三個 BRAN 的 PIPE 會得到三個**疊在同一點**的箭頭，另外兩條分支的管路本來就一個都沒有。dedup 只是把疊起來的重複刪掉，讓這個既有漏洞顯出來。

**作法**：改成**按 BRAN 抓管段**（`vscan for all tubi for $!bran`），不要按 PIPE。每條分支挑自己可見最長的那根，位置各自不同——既不會疊，每條分支的管路也都有箭頭。`!pipes` / `unique()` 那段就不需要了。

`!tubis` 在掃描前先 `= object array()` 清空，這樣某條 BRAN 掃描失敗時不會沿用上一條 BRAN 的管段（`var` 失敗時舊值會留著）。

### 3-舊. 迴圈跑 BRAN，查詢卻用 PIPE，同一條管重複標

`do !bran values !brans` 逐分支跑，裡面卻 `vscan for all tubi with matchwild(name of pipe, ...)` 抓整條 PIPE 的管段。一條 PIPE 有 N 個 BRAN 在圖上，就挑到同一根最長管段 N 次，在**同一個位置疊 N 個箭頭**，vscan 也白跑 N 次。

作法：照 `forms/E3dDraftModify.pmlfrm:47-54` 既有寫法，先把 pipe 名收成陣列、`unique()` 之後再跑。`name of pipe` 加了 `handle any`，未命名的管跳過就好，不要讓它中止後面所有管線。

`unique()` 是就地修改，所以維持 `!pipes.unique()` 不寫成指派（見下方「陷阱」段的同一條記錄）。

### 4. 箭頭角度的 ±40° 判斷是錯的

`angle()` 只回傳 0~180 的無號角，正負號必須由「方向在 view right 上的分量是正是負」決定，門檻應該是 **90 度，不是 40 度**。實際代數：

| 管線方向 | 對 up 夾角 | 對 right 夾角 | 正確 | 原本 |
|---|---|---|---|---|
| 東 / 西 / 南 / 北 | — | — | — | 都對 |
| up 偏東 30° | 30 | 60 | −30 | −30 ✓ |
| up 偏**西** 30° | 30 | 120 | +30 | −30 ✗ 鏡射 |
| down 偏東 30° | 150 | 60 | −150 | +150 ✗ 反向 |

四個正交方向碰巧都對，所以正交管路看不出問題；斜管會鏡射，往下斜的管箭頭直接指反。整段簡化成一次 `.lt(90)` 判斷。

### 5. 箭頭跑到圖框外 / 被擠在 view limits 上（第二輪，實機回報）

實機跑出來兩個現象（見 `error.png` 紅框）：左下角紅框有兩個箭頭飄在圖框外的空白處；右上角紅框的箭頭疊在 view 上緣的線號標註裡；左下長管那根的箭頭貼在左邊界上。

同一個根因，就是上一輪列在「還沒做」的第 6 項：**挑最長管段用的是 `ltle`（模型 3D 長度），完全沒管那根管段在不在圖上**。view 的 drawlist 收的是整條 PIPE，`vscan for all tubi` 就把整條管的管段都吐回來，包含完全在圖外的。於是：

- 一條管最長的管段整根在圖外 → 箭頭直接畫在圖框外的空白處。
- 最長的管段大半在圖外、只切到一角 → 裁切後只剩邊界附近那一小截，箭頭就貼在 view limits 上。

第二層原因是裁切規則本身也不對。`intersection()` 把 view 邊界當**無限長的直線**，所以「跟四條邊界線求交點、取離端點最近的那個」會挑到邊界**延長線上**的點（在圖框外），也可能挑到在起點**後方**的點。`DrawingPlan1LineNoAnnotation.pmlfnc:713-725` 和 `.CrossingOfTube()` 都各自有補防呆，流向這邊一個都沒有。

**作法**：`forms/DrawingPlan1.pmlfrm` 新增 `.VisibleSheetRunOfTube(!tube, !vwx1, !vwy1, !vwx2, !vwy2)`，直接把管段**線段**對 view 矩形做參數式裁切（Liang–Barsky），回傳 `[可見長度平方, 中點 x, 中點 y]`，完全在圖外就回空陣列。因為 view 在圖紙座標永遠是正矩形（見 `.SheetBandOfSide()` 的註解），可以一條邊一條邊地夾 `!t0` / `!t1`，不必用 `intersection()`，也就沒有無限延長線的問題。

`DrawingPlan1FlowAnnotation` 改成：排序鍵用**可見長度**而不是 `ltle`，可見長度為零的管段根本不進候選；贏的那根把箭頭放在**可見段的中點**。這樣箭頭在幾何上不可能跑到框外，也不會貼在邊界上。

順帶解掉的：

- 整段 `CheckInsideView` + 四個距離 + `!nocross` + `!p1pt`/`!p2pt` 都不需要了，刪掉。
- `!mid1` 的 `.string().before(' U').replace(...)` 字串處理也不需要了，改成照 `LineNoAnnotation.pmlfnc:861-862` 的寫法直接組 `'x <數字> y <數字>'` 再 `enupos of`。下面那條 E/N 對 W/S 的疑慮就不存在了。
- 排序鍵從 3D mm（可到 7 位數）變成圖紙 mm 的平方，`1e-10 * !tt` 的浮點精度風險沒有變糟。回傳平方是為了不用 sqrt，跟 `.ViewSheetTransform()` 的作法一致；這個值只拿來比大小，不當長度用。

**要注意的副作用（效能）**：原本每根管段只查 `gradient` + `ltle` 兩次，現在每根要多查 `pos p1`、`pos p2`、`shpos` ×2，管段迴圈的 DB 查詢大約變 2.5 倍。大圖如果明顯變慢再回來想辦法（例如先用 `ltle` 粗篩掉明顯太短的）。

**PML 語法陷阱**：`-!dx` 這種對變數的一元負號，整個 repo 沒有任何先例，不確定 PML parser 吃不吃。已改成 repo 既有的 `!dx * -1` 寫法（同 `!ang * -1`）。

**陷阱：不要用容差測試去保護除法**。裁切迴圈原本寫成 `if (abs(!p) lt 0.000001) then ... elseif (!p lt 0) then !t = !q / !p else !t = !q / !p endif`，實機馬上拋 `CALCULATOR ERROR: division by zero (element =0/0)`。正交管在圖紙上一定會讓四條邊裡的兩條 `!p` **剛好等於 0**，而那個 `abs(...) lt 0.000001` 沒有擋下來（沒去追為什麼）。改成先測 `!p lt 0` / `!p gt 0`、把「管段平行於這條邊」留給 `else`，`!p = 0` 在結構上就進不到除法。Liang–Barsky 本來也不需要容差：接近平行時 `!t` 會很大，很大的 `!t` 既不會把 `!t1` 拉下來也不會把 `!t0` 推上去，行為是對的。

**改到 `.pmlfrm` 一定要重載**：`.pmlfnc` 每次呼叫會重讀，form 是常駐物件，改完要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1`，否則會看到 `Method <FORM>.XXX not found`。新增檔案才需要 `pml rehash all`。

### 6. 兩個箭頭撞在一起（第四輪，實機回報）

`error.png` 兩個紅框都在設備管嘴附近：兩條平行的短立管分屬不同 BRAN，各自的箭頭只差幾 mm，疊在一起看不清楚。

**作法**（三層，依序退讓）：

1. **沿著自己那根管滑開**。`.VisibleSheetRunOfTube()` 多回傳可見段的兩個端點（index 4~7），箭頭依序試 `!fracs` = 0.5 / 0.35 / 0.65 / 0.2 / 0.8 這幾個位置，第一個離所有已放箭頭都超過 `!mindist` 的就用。滑動後箭頭仍在自己的管上，語意不變——這是關鍵，不能為了避讓把箭頭移到別的管上。
2. **換這條 BRAN 的下一根管段**。`!sorted` 由長到短走，整根都擠不下就換次長的。
3. **都不行就容許重疊**，退回最長那根的中點。寧可疊也不要漏標，這是使用者的原始規則。

`!usedx` / `!usedy` 記錄已放的位置，跨 BRAN 累積，所以是全圖避讓不是只有同一條管。貪心法，先掃到的 BRAN 先佔好位置。

**可調參數**：`!mindist`（圖紙 mm，中心到中心）。箭頭實際大小取決於 `Cheitx '2mm'` 和符號本身，太密或太鬆就調這個數字。

#### 6-2. 第一版避讓不夠力（第五輪，實機回報）

改完還是有兩個箭頭很接近。原因是**第 3 層退讓寫錯了方向**：找不到夠開的位置時，退回「最長管段的中點」——而那正是最擠的地方，等於白繞一圈。管嘴附近全是短立管，可見段本來就只有幾 mm，五個 `!fracs` 位置全部落在彼此的 `!mindist` 內，所以每次都走到第 3 層。

**改法**：

- 第 3 層改成**取試過的位置裡最寬鬆的那個**（離最近的已放箭頭最遠），不再退回中點。就算擠不到 `!mindist`，也把兩個箭頭推到這條分支能做到的最開。
- 距離改成真正的歐氏距離平方（原本是 `abs(dx) < d and abs(dy) < d` 的方框判斷，對角線方向會誤判成「夠遠」）。一樣用平方避免 sqrt。
- `!fracs` 從 5 個加到 9 個（0.05 ~ 0.95），短管段多一點滑動空間。
- `!mindist` 從 6 加大到 8。因為第 3 層現在保證會取最寬鬆的位置，加大門檻不會有「找不到就爛掉」的副作用。

**取捨**：最寬鬆的位置可能落在比較短的管段上，不一定是最長那根。判斷是「箭頭標在同一條管的短管段上」比「兩個箭頭疊在一起」好讀。如果實際看起來不是這樣，把第 3 層的搜尋範圍限制在最長那根就好。

### 6-3. 依高程由高到低放置（第六輪）

使用者的觀察：兩個箭頭靠這麼近，是因為那兩條管高程不同、在平面上重疊。提議「底層的管不要標流向」。

**沒有照提議做，理由**：丟掉下層管的箭頭跟最初「每條管線至少一個流向」的規則直接衝突。被壓在下面的管在圖上還是看得到，讀圖的人一樣需要知道它的流向。

**改成取這個洞察但不丟箭頭**：放置順序改成**依高程由高到低**。平面圖上兩條管重疊時，看得到的是上面那條，所以讓上層的管先挑位置、佔住自己管線上最好的點；下層的管接著才放，被迫沿自己的管滑到還有空間的地方。先到先得的貪心法本來就存在，這裡只是把「誰先到」定義成「誰在上面」。

高程取自 BRAN 的 `hpos`。只有接近水平的管段會被標註，所以分支不會離自己的 head 太遠，這個近似足夠判斷兩條管誰在上面。

**陷阱：排序鍵一定要先去單位、而且不能是極小數**。第一版寫 `!branu = !hp.position().up` 直接當鍵，實機拋 `PML Error in method METHOD：輸入字串格式不正確`（.NET 的 `FormatException`）。兩個原因：

1. `.up` 回傳的是**帶單位的 real**，`&` 串接時把 `mm` 一起帶進鍵裡，`Double.Parse("102930mm")` 就炸了。這個檔案其他地方都有防：`!ltle.replace('mm', '').real()`、`!memshpos.split().getindexed(2).replace('mm','').real()`——只有這行漏了。改成 `string(!hp.position().up).replace('mm', '').real()`。用 `position().up` 而不是 `part(6)`，是為了讓低於基準面的高程（會印成 `D` 不是 `U`）保住負號。
2. 唯一鍵的微量從 `+ 1e-10 * !bb` 改成 `* 1000 + !bb`。`hpos` 查不到時 `!branu` 是 0，`0 + 1e-10` 會被渲染成 `1E-10`，同樣讀不回數字。放大一千倍再加整數計數，千分之一 mm 遠比兩條管的間距細，排序結果不變。

`!seenkey` 有同一個隱患（管段在圖上投影成一點時 `!seen[1]` 是 0），一併改成 `* 1000 + !tt`。這個還沒實際炸過，是順手補的。

如果實機看下來還是希望下層乾脆不標，那是三行的事（放置時比對已放箭頭的高程，較低者跳過）。

### 6-4. `!mindist` 加大到 20，並加診斷開關（第七輪）

放大看之後確認：避讓**有在動**（兩個箭頭沒有完全重疊、是上下排開的），但中間只隔大約半個箭頭長，讀起來還是像一坨。也就是 `!mindist = 8` 相對箭頭實際長度太小。門檻必須**明顯大於**箭頭長度，不能只是等於。

`!mindist` 8 → 20。**放大是安全的**，因為：

- 第 3 層退讓保證會取最寬鬆的位置，門檻再大也不會「找不到就爛掉」，只是讓更多分支走第 3 層。
- 孤立的管不受影響：還沒有任何箭頭時所有候選位置的 `!near2` 都是那個大數，而比較用的是嚴格大於，所以第一個候選（正中央）會勝出、不會被推到管末端。

另外加了 `!dbg` 開關（預設 `false`）。打開之後每條分支會在 command window 印出：分支、高程、最後落點 x/y、離最近箭頭的距離平方、以及是否走了第 3 層。這一處已經猜錯兩次，與其再猜，不如直接看實際數字。

打開的方式是把 `!dbg = false` 改成 `true`。`near2` 是**距離平方**，開根號才是 mm——例如 `near2 400` 就是 20mm。

### 6-5. 診斷結果：高程排序是壞的，共線短管確實無解（第八輪）

打開 `!dbg` 之後拿到實際數字，兩個發現。

**發現 1：高程排序完全沒作用。** `u` 欄印出 `0.2EX-01`、`0.18EX-01`、`0.9EX-02`……解開科學記號是 0.020, 0.018, 0.017, 0.016, 0.013, 0.011, 0.009……乘回 1000 剛好就是 `!bb`。也就是 **`!branu` 每一條都是 0**，「由高到低」實際上只是掃描順序的反序。

原因：`vscan for all bran` 回傳的是 `BRAN =2013286676/2167`（**型別前綴 + ref**），我把整串丟給 `hpos of`，每次都掉進 handle。管段那邊本來就有處理（`!tubis[!tt].part(2)`），branch 這裡漏了。改成先 `!bran.part(2)` 取出 ref 再查。

順帶把讀高程的方式也換掉：原本 `string(!hp.position().up).replace('mm','').real()`，改成直接 `!hp.part(6).replace('mm','').real()`，並用 `!hp.part(5).eqnocase('D')` 判斷是否在基準面以下、是的話 `* -1`。只用這個檔案已經在用的 `.part()` / `.replace()` / `.real()` / `.eqnocase()`，不依賴 `string()` 對帶單位 real 的行為。

> **注意**：`vscan for all tubi for $!bran` 用的是**完整字串**（含 `BRAN ` 前綴）而且是正常的，不要一起改掉。只有屬性查詢要用 ref。

**發現 2：那兩對箭頭是真的無解。**

| 分支 | x | y | near2 | roomiest |
|---|---|---|---|---|
| /2167 | 362.740233 | 475.703784 | 999999999 | no |
| /1597 | 362.740233 | 482.8363168 | 46.4 → 6.8mm | **yes** |
| /2164 | 301.740239 | 475.703784 | 1404 | no |
| /1595 | 301.740239 | 482.8363168 | 47.0 → 6.9mm | **yes** |

**x 完全相同**，只差 7mm 的 y——平面上共線的上下層管。`roomiest yes` 表示整條分支的所有管段、所有位置都試過，6.8mm 已是極限。它們是管嘴短接管，可見段只有幾 mm，滑不開也沒有別的管段可換。其他分支的 near2 都在 3000~4500（55~67mm），避讓運作正常，**只有共線短管無解**。

**作法：加第二道門檻 `!hardmin = 10`**，整條分支連 10mm 都達不到就**不標**這條。因為順序是由高到低，已經放下的必定是上層管（讀者看得到的那條），讓開的就是被壓在下面的那條——這就是使用者一開始提的「底層的管不要標流向」，只是收斂成「真的擠不下時才讓」。

這確實違反了「每條管線至少一個流向」的原始規則，但只在**箭頭畫了也讀不出來**的情況下違反。有呼吸空間的管一律照標。

兩道門檻的分工：`!mindist = 20` 是理想間距（驅動快速路徑），`!hardmin = 10` 是可讀性下限（低於就放棄）。套在上面的資料上：/1597 和 /1595（6.8/6.9mm）會被 drop，/1839、/1820（10.5mm）和 /1578（13.9mm）仍保留。覺得 10.5mm 還是太近就把 `!hardmin` 調大。

### 6-6. 排序改成「高程 + 可見長度」（第九輪）

修好高程之後的實測顯示：擠在一起的 `/2167`、`/2164`、`/1597`、`/1595` **高程完全相同**（都是 101076，`u` 欄的小數位是 `!bb` 露出來的）。所以「下層讓上層」在這一組完全沒有作用，drop 掉哪兩條純粹看掃描順序 —— 是巧合，不是判斷。

使用者提的 drop 三條件（方向一致 / 高程不同 / 兩條都很短）評估結果：

- **方向一致**：抓到了正確的幾何原因（平行才滑不開，交叉滑一下就開了），但搜尋失敗這件事本身就蘊含它，額外再測會漏掉「短管垂直交叉」這種同樣該處理的情況。
- **兩條都很短**：同理。長管搜尋時就找到位置了，根本走不到 drop。
- **高程不同**：被實測資料推翻，出問題的那組高程相同。

真正的缺陷不是「何時 drop」而是「**drop 哪一條**」。高程的正確用途是**選受害者**（下層被蓋住），不是偵測衝突。

**作法**：排序鍵從「高程」改成「**高程 + 可見長度**」，同高程時可見段長的先放、短的讓位。長管是比較值得標流向的地方。

**排序改用手寫選擇排序，不再用 `AteSortLineNo`**。理由：那個 sort 只吃一個數字，要把高程和長度塞進單一鍵就得做數字打包 —— 高程六位數，乘上倍率再加長度和計數會逼近 real 的有效位數，而且大數字容易被渲染成科學記號，正是已經踩過兩次的 `輸入字串格式不正確`。兩個欄位直接比較就沒有這些問題：不用打包、不怕重複鍵、不怕格式。一個 view 幾十條分支，O(n²) 的比較相對於前面的 DB 查詢是零成本。

迴圈用 `if (!ord.size() gt 1)` 包住，比照 `LineNoAnnotation.pmlfnc:938` 對自己 `to !mcount - 1` 迴圈的防護。

**代價**：管段迴圈跑兩次（一次算排序用的最長可見段，一次放箭頭），DB 查詢加倍。使用者確認正確性優先。

診斷輸出多一欄 `run2`（可見長度平方），可以驗證同高程時是不是真的長的先放。

### 6-7. 最小可見長度 `!minrun = 10`：擁擠的真正原因（第十輪）

加上 `run2` 診斷欄之後，把可見長度開根號排出來，看到一道極明顯的斷層：

| 分支 | 可見長度 |
|---|---|
| /1600 | 90.5mm |
| /1531 | 77.1mm |
| /1625 | 61.3mm |
| /1578 | 56.3mm |
| /1590 | 19.1mm |
| /2610 | 17.1mm |
| /1619 | 11.2mm |
| /1845 | **5.4mm** |
| /1597 /1595 | **4.0mm** |
| /2167 /2164 | **3.95mm** |
| /1820 | **2.55mm** |
| /1839 | **2.50mm** |

**11.2mm 以上七條，5.4mm 以下七條，中間什麼都沒有。** 而所有的爭執、drop、擁擠，全部發生在下半那七條上。

箭頭本身約 10mm 長，**比那些管段的可見長度還長兩到四倍**。在一段 2.5mm 的可見管上畫流向箭頭，本來就畫不出可讀的東西，跟旁邊擠不擠無關。前面幾輪一直在調 `!mindist` / `!hardmin` / 排序，其實都在處理症狀。

第九輪那個「同高程比可見長度」的排序，實際上是在比 4.04mm 和 3.95mm 誰長——這個精度沒有意義，淨效果只是把 drop 從 3 條變 5 條、換了受害者。

**作法**：加 `!minrun = 10`（圖紙 mm），可見長度放不下箭頭的管段**根本不進候選**。濾網只套在**收集候選**那一處，用巢狀 if 而非 `and`（PML 的 `and` 不保證短路，`!seen` 為空時 `!seen[1]` 會出錯）。

> 一開始把濾網也套進排序用的前置掃描，結果 `!bR` 只記錄合格的管段、不合格就留在 0，診斷輸出裡每條被跳過的分支都變成 `run2 0`，**看不出它實際多短**——而那正是要調 `!minrun` 時唯一需要的數字。排序用的 `!bR` 改回記錄真實長度。不影響行為：沒有合格管段的分支輪到它時本來就找不到候選，它排在哪裡都一樣。

用實測資料驗算的預期結果：**存活 7 條，彼此最近的一對是 /1625 對 /1600 的 28.3mm**，遠大於 `!mindist = 20`。也就是 `!mindist`、`!hardmin`、滑動、讓位那一整套在這張圖上一次都不會觸發——擁擠問題自動消失。

避讓機制全部保留。別的圖面或別的比例尺，還是可能讓兩條長管並排。

診斷多一種輸出：`NO RUN reaches minrun`，用來區分「因為太短沒標」和「因為擠沒標」。

**實測驗證（第十輪）**：放置 7 條，位置與推算完全一致；沒有任何 `roomiest yes` 或 `DROPPED`；最小 `near2` 800.15（28.3mm）。避讓機制一次都沒觸發，確認擁擠只是症狀。

這一輪同時暴露出一個先前看不見的事實：view 裡共 20 條分支，其中 6 條（/1592、/1621、/2170、/1832、/1826、/1850）**完全沒有可見管段**（`run2 0`）。它們一直都被略過，只是以前 debug 行寫在 `if (not(!tubiss.empty()))` 裡面，什麼都不會印。新加的 else 分支才讓它們現形。

### 6-8. rcode = left 時箭頭方向錯 90 度（第十一輪，**已實機驗證**）

症狀：勾選 "Portrait to Landscape"（`.Apply()` 對 view 下 `RCODE LEFT`）之後，流向箭頭方向錯誤。

原因跟柱位線 2026-08-07 那個 bug 完全同源，README 下面已經記過：**`shpos` 回傳 sheet 座標，但 SLAB 的屬性是 view 座標，`RCODE LEFT` 讓 view 在 sheet 上逆時針轉 90 度，兩個座標系差 90 度。**

`!ang` 算出來是**圖紙上**的角度 —— `viewdir up` / `viewdir right` 給的是「在圖紙上看起來朝上 / 朝右」的模型方向，本來就跟著 rcode 走，所以它們跟管線方向的夾角是圖紙角度。但 SLAB 的 `ADEGREES` 是在 **view** 裡讀的，差的就是那 90 度。

**作法**：`!this.rcode` 是 `left` 時 `!ang = !ang - 90`，並在低於 -180 時加回 360。和 `.CreateGridSymbol()` 的 `Adegrees -90` 是同一個補償。

跟柱位線不同的是，流向只需要補角度：`XYPO 0 0` 是零偏移、旋轉不影響，`POS` 也不必換算（使用者回報的是方向錯，位置沒跑掉）。柱位線當時還要換 `XYPO` / `APOF`，因為那兩個是非零的 view 座標偏移量。

實機驗證通過，`-90` 的符號正確。

### 7. 順手修掉的既有 bug：`!checkok = fasle`（2026-08-10）

`forms/DrawingPlan1.pmlfrm` 的 `.CheckDimensionAttachPoint()` 裡把 `false` 拼成 `fasle`，**`max` 和 `min` 兩個分支各一處**（原本只回報了一處，實際有兩處）。那會變成參照未定義變數，走到 `EQUI` 分支時就拋錯。`!checkok` 在上面已經初始化成 `false`，所以意圖很明確：EQUI 就是不合格、停止往下找。兩處都已改成 `false`。

`DrawingPlan1 - 複製.pmlfrm` 裡也有兩處同樣的拼錯，那是備份檔沒有動。

### 還沒做（需要先定圖面規範）

- **「至少一個」還不成立**：`abs(gradient) leq 1` 排除坡度大於 45 度的管段，一條管在這個 view 裡只有立管時 `!tubiss` 是空的，靜靜什麼都不標。要補 fallback，但立管在平面圖上投影成一點，箭頭該怎麼表示要使用者決定。
- **角度是 3D 夾角不是投影角**：往北同時上升 45 度的管，平面圖上投影是正北（0 度），但 3D 夾角是 45 度，箭頭會歪。`.VisibleSheetRunOfTube()` 裡已經算出圖紙座標的兩個端點，要修的話從那裡取方向最準（裁切保持 p1→p2 的順序，所以方向就是流向）。這一輪沒動，因為使用者沒回報角度問題，不想在無法實測的情況下再改一次。
- **只避開別的箭頭，沒避開文字**：第 6 節做的是箭頭對箭頭。箭頭還是可能疊在線號引線、尺寸線、格線上。要一併避讓的話得拿到那些標註的圖紙範圍，LineNo 跑在 Flow 之前，可以考慮讓它把佔用範圍記在 form 的 member 上給 Flow 用。
- **`AteSortLineNo` 是數值排序還是字串排序未確認**：若是字串排序，`9.5` 會排在 `100.2` 後面，`.last()` 就不是最長那根。
- **流向語意**：現在用分支的 head→tail 方向。若有管線被反向建模，箭頭就會指錯，程式沒有依據流向屬性做任何校驗。

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

**已解決（2026-08-17）**：使用者確認 `design/forms/DrawingPlan.pmlfrm` 就是切圖程式，沒有別的版本。上面列的 5 個問題連同三點法、CAD 匯入一起處理掉了，見下面「改寫：`DrawingPlan.pmlfrm` 改成三點法 + CAD 匯入」。

### 方式 B：依結構網格自動切 box（未來項目）

使用者認同這是「另一個好方法」，但**這次不深入設計**，只需在架構/UI 上預留擴充空間，讓使用者之後可以在兩種建 box 方式間切換。細節尚未討論。

## 已改：View 分頁的 Save/Load 沒有把 Keyplan Y axis 跟整個 BorderText 分頁存進檔案（2026-08-14，**尚未實機驗證，改的是 .pmlfrm，要 kill/show**）

使用者貼 `error.png`，紅框標出 View 分頁的 `Save`／`Load` 按鈕（`.Save()`/`.Load()`，`:1398`/`:1476` 附近），要求把「平面圖設定儲存及讀取」這個功能完整解決。

### 找到的問題

1. **`Keyplan Y axis`（`.keytext5.val`）從未被 `.Save()` 寫出**：Keyplan 分頁的 `.keytext1`~`.keytext4`（左下角紙面座標、模型座標 E/N、比例尺）都有存，唯獨 `.keytext5`（`N`/`S`/`E`/`W`，決定 keyplan 上高亮框的旋轉方向，`:891-936` 直接拿它算 `!keytrans[5..8]`）漏掉。`.Load()` 讀完檔案後這個欄位完全不會被覆寫，永遠停在表單當下的值（新開表單是初始值 `.DrawingPlan1()`(`:244`) 設的 `'N'`）——如果專案實際用的是別的方向（`error.png` 舊版截圖裡查到的元件名稱是 `..._KEYPLAN_E`，不是 `_N`），Load 之後算出來的高亮框方向就會跟存檔當時對不上。
2. **BorderText 整個分頁（24 個欄位：`dwgnopos/hei`、`scalepos/hei`、`revpos/hei`、`title1~3pos/hei`、`name1~3pos/hei`、`date1~3pos/hei`）完全沒有存也沒有讀**。其中 `dwgnopos/hei`、`revpos/hei`、`title1~3pos/hei` 這 5 組其實有在 `.Apply()`（`:960-984`）真的拿來決定圖號/Rev/Title1-3 文字要印在圖紙的哪個位置，Save 沒寫、Load 自然救不回來，等於這幾個位置設定每次都要重新手動輸入。
3. **`.Load()` 用 `!line.split('=').getindexed(2)` 取值**，任何存檔值本身若含第二個 `=`（例如以後 Rule/Format 欄位寫成類似 `X=1` 的條件字串），會被從第二個 `=` 那裡截斷。
4. **`.Load()` 真正做賦值的 `$!option = $!val` 完全沒被 `handle` 保護到**——它寫在 `elsehandle none` 的 body 裡，而 `handle`/`elsehandle none` 只保護它前面切字串那兩行。只要檔案裡任何一行賦值失敗（例如存檔來自舊版表單、某個欄位已經不存在了），就會整個中斷迴圈、後面所有設定都不會被套用，而且不會有任何錯誤訊息，看起來像是「讀檔沒反應」。

### 作法

`forms/DrawingPlan1.pmlfrm`：

- `.Save()`（`:1398`）補上 `!this.keytext5.val` 那行，以及 BorderText 分頁全部 24 個欄位（`dwgnopos/hei` ... `date3pos/hei`），寫在 `frametext` 之後、`keyovertext` 之前，跟分頁順序（View→BorderText→Keyplan）一致。
- `.Load()`（`:1476`）：
  - 切 key/value 改用 `.before('=')`/`.after('=')`（這個檔案別處，如 `:371` 的 `.after('rev:')`、`.CrossingOfTube()` 附近的 `.before('WRT')`，已經在用同一套字串方法），只切第一個 `=`，不會再被值裡的第二個 `=` 截斷。
  - 在 `elsehandle none` 裡面再包一層 `handle any / elsehandle none`，把真正的賦值 `$!option = $!val` 包進去——單一行賦值失敗只會跳過那一行，不會讓後面所有設定一起遺失。

**改的是 `.pmlfrm`，要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1` 才會生效。**

### 實機驗證結果：真的按了 Load，噴了語法錯誤，抓到另一個獨立的存檔 bug（2026-08-14）

使用者馬上按 `Load` 測試，直接跳出：

```
(47,15)  CP: Syntax error
In line 1506 of PML function drawingplan1.LOAD
        !this.insttext1.val = ^^ALL INST WITH ISNAMED
 Called from line 1 of Command/Form Callback Command
!This.Load()
```

**根因**：`.Save()` 裡 `insttext1`／`nozztext1`／`valvtext1`／`usertext1` 這 4 個「Rule」欄位（預設值像 `ALL INST WITH ISNAMED` 這種帶空白的自由文字）**從一開始就沒有加 `|...|` 引號**，跟同一批的 `insttext2`／`nozztext2`／`valvtext2`／`usertext2` 寫法不一致（那 4 個有引號）。這是舊碼本來就有的問題，不是這次新加的欄位造成的——`.Load()` 讀回沒引號的 `ALL INST WITH ISNAMED` 之後，`$!option = $!val` 展開成 `!this.insttext1.val = ALL INST WITH ISNAMED`，PML 沒辦法把這幾個沒加引號的裸字當成字串常數解析，直接語法錯誤。

**這類語法錯誤是在展開 `$!val` 之後、PDMS 的 command processor 解析那一行時才發生的，`handle any` 包不住**（`handle`/`elsehandle` 抓的是執行期錯誤，不是巨集展開後的語法錯誤）——這也是為什麼前一版加的內層 `handle` 沒能擋下來，這次是實機驗證才抓到，光看程式碼看不出這一步會被 handle 漏接。

### 作法

1. `.Save()`（`:1454/1458/1461/1466`）把 `insttext1`／`nozztext1`／`valvtext1`／`usertext1` 也加上 `|...|`，跟其餘字串欄位一致——這樣**之後新存的檔案**不會再有裸字問題。
2. 但使用者剛剛已經用舊版 `.Save()` 存過檔，那個檔案裡這 4 行還是沒引號的舊格式，光修 `.Save()` 救不回**已經存在的檔案**。`.Load()`（`:1495-1527`）補上一段防呆：對每一行算出來的 `!val`，如果**不是**已經用 `|` 包起來、也不是 `TRUE`/`FALSE`、且轉不成 `real()`（代表它是一段自由文字），就在展開成指令之前**自己先補上 `|...|`**。這樣不管存檔是新版（已加引號）還是舊版（沒加引號）都能正確讀回來，不用使用者手動重存一次舊檔。

**改的是 `.pmlfrm`，要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1` 才會生效。**

## 已改：Save 沒有把 Drawing 分頁的「In Use」box 清單存起來（2026-08-14，**尚未實機驗證，改的是 .pmlfrm，要 kill/show**）

使用者又貼了一版 `error.png`，紅框這次標的是 Drawing 分頁「In Use」那個清單（`.files`，靠 `>`/`>>`/`<`/`<<` 四個按鈕跟左邊「All」清單（`.files1`）互相搬動的那個 multiple-selection list），問 Save 能不能也把這個存起來。

### 原因

`.files.dtext` 是陣列（要建哪幾張圖），不是一般欄位的單一 `.val`，`.Save()`/`.Load()` 原本整套機制只處理 `.val` 這種純量欄位，陣列完全沒被涵蓋——所以 Save 存檔完全沒寫這個清單，Load 也就沒有東西可以讀回來，每次都要重新在 Drawing 分頁手動勾選一次要建的 box。

### 作法

`forms/DrawingPlan1.pmlfrm`：

- `.Save()`（`:1410` 附近）：把 `.files.dtext` 用逗號接成一行字串（box 名稱本身不會有逗號，安全），寫成 `!this.files.dtext=|26001-AG-001,26001-AG-002|` 這種格式，跟其他欄位共用同一個檔案、同一套一行一筆的格式，只是這行是陣列的特例。
- `.Load()`（`:1522` 附近）：既有的逐行迴圈在真正做 `$!option = $!val` 之前，先判斷這一行的 `!option` 是不是 `!this.files.dtext`——是的話走專門的分支：拆逗號還原成陣列、指定回 `.files.dtext`，並且比照 `.selectce()`（`:271`）原本的作法，把同樣這些名字從「All」清單（`.files1`）裡拔掉、重新算一次 `Create Drawings` 按鈕該不該 active（`!this.dest.val` 有值且 `.files.dtext` 非空才 active）——不這樣做的話，讀回來的名字會同時留在「All」和「In Use」兩邊，跟正常用 `>` 按鈕手動加入的狀態不一致。不是這個特例的其他所有行，才會繼續走原本的 `$!option = $!val` 通用機制。

**沒有存 `Destination`（`.dest.val`）**：那是一串裸的 DB 位址（`=2013286677/35036` 這種），不是穩定的名稱，資料庫重整之後同一個位置的位址可能會變，存起來反而可能指到錯的地方，跟「In Use」清單用的是穩定的 box 名稱字串不是同一類東西，這次刻意不動它。

**改的是 `.pmlfrm`，要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1` 才會生效。**

## 已改：Destination 也存起來，位置失效時改跳警告（2026-08-14，**尚未實機驗證，改的是 .pmlfrm，要 kill/show**）

使用者：上一版特意不存 `Destination` 是對的顧慮（裸 DB 位址不穩定），但要求還是存起來，只是**位置失效時要跳警告訊息**，不要默默留著一個死掉的位址。

### 作法

`forms/DrawingPlan1.pmlfrm`：

- `.Save()`（`:1411` 附近）：`!this.dest.val`（`=2013286677/35036` 這種裸 DB 位址）跟其他欄位一樣包 `|...|` 存進檔案。
- `.Load()`（`:1549` 附近）：讀到 `!this.dest.val` 這行時走專門分支，**先驗證再相信**——不是直接賦值，而是仿照 `.desce()`（`:1298`）的作法先 `!savedce = name` 記住目前位置，`handle any` 包住 `$!destref` 試著把 CE 導到存檔裡的那個位址：
  - 導得過去 → 是有效位址，`!this.dest.val = !destref`。
  - 導不過去（`handle any` 抓到）→ `!this.dest.val` 設回空字串，`!!alert.warning(...)` 跳出訊息告訴使用者這個位置已經找不到了、要重新用 `Destination` 旁的 `CE` 按鈕設定。
  - 不管哪種結果，驗證完都用 `$!savedce` 把 CE 導回驗證前的位置——這個檢查只是「問一下這個位址還在不在」，不應該真的把使用者目前所在的位置搬走。
  - 跟 `.desce()`（`:1309`）、`.files.dtext` 那個分支一樣，驗證完重新算一次 `Create Drawings` 按鈕該不該 active。

**改的是 `.pmlfrm`，要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1` 才會生效。**

### 待實機驗證

1. 重新 `kill/show` 之後直接用使用者剛剛那個舊存檔按 `Load`，確認不再噴語法錯誤、`Inst/Nozz/Valv/User Rule` 那幾個欄位有正確讀回文字。
2. 把 Keyplan 分頁的 `Y axis` 改成非預設值（例如 `E`）、BorderText 分頁幾個位置欄位也改一下，`Save` 存一個新檔，`Load` 讀回來，確認這些欄位都正確回填。
3. 確認 `Load` 一個更舊的存檔（沒有 `keytext5`/BorderText/`files.dtext`/`dest.val` 那幾行）不會報錯，其餘欄位一樣正常套用。
4. Drawing 分頁「In Use」清單勾幾個 box、`Save`，清空重開表單（或按幾下 `<<` 清空)、`Load`，確認這幾個 box 正確回到「In Use」、同時從「All」消失，`Create Drawings` 按鈕也正確變成可按。
5. `Destination` 按 `CE` 設一個有效位置、`Save`、`Load`，確認正確回填、`Create Drawings` 按鈕狀態也對。
6. 存檔後（在 E3D 裡）把那個 `Destination` 指到的元素刪掉或改名，再 `Load` 同一個檔案，確認會跳出警告訊息，而不是默默塞一個死位址進 `Destination` 欄位。

## 新增：NorthArrow 分頁與指北向符號（2026-08-17，**尚未實機驗證，改的是 .pmlfrm，要 kill/show**）

使用者要求比照 Keyplan 分頁新增一個 `NorthArrow` 分頁，並把符號實際畫到圖上。

### 表單（`forms/DrawingPlan1.pmlfrm:91-97`）

新增 `frame .northarrow 'NorthArrow'`，三列：

| 欄位 | Gadget | 型式 | 按鍵 |
|---|---|---|---|
| North Arrow | `.northtext` | string | `.northbutn` → `.typepick('SYTM', 'northtext')`，旁邊 `SYTM` 提示詞 |
| Scale | `.northsca` | real，內定 1 | 無 |
| POS | `.northpostext` | string | `.northposbutn` → `.northarrowpick()`（滑鼠點圖紙位置） |

改過兩輪：

1. 第一版 `North Arrow` 的型式寫成 `OVER`（照抄 Keyplan），使用者更正為 `SYTM`——指北向是符號樣板，不是 overlay。
2. 第二列原本是另一個 SYTM 欄位 `North Arrow When View is Rotated`，使用者改成 `Scale`（real，內定 1），當作符號的比例大小。**視圖旋轉時不再換符號，改成把同一個符號轉到指向真北**（角度算法本來就已經寫好了，見下）。

其他：

- `.northsca.val = 1` 的內定值設在 `.DrawingPlan1()`（`:197` 附近），跟 `griddist`/`gridgap` 那幾個 real 欄位放一起。
- `.northarrowpick()`（`:1803` 附近）整支比照 `.keyplanpick()`：`var !size1 shpo @` 讓使用者在圖紙上點一點，換算成 `X <x> Y <y>` 字串填回欄位。
- `.Save()`（`:1568` 附近）加了這三個欄位，`.northsca.val` 是 real 所以不包 `|...|`（跟 `griddist` 那幾行一樣）；`.Load()` 不用改，走既有的通用 `$!option = $!val` 分支。

### 實作（`.Apply()`，`forms/DrawingPlan1.pmlfrm:995-1088`）

放在填 BorderText 之後、`!!DrawingPlan1MatchLine()` 之前。

**元素放哪裡**：使用者指定「CE 在 SHEE 時要先進 `note 1` 階層，才能 `new symb`」——SYMB 不能直接掛在 SHEE 底下，要放進 sheet 的 NOTE 裡，也就是 BorderText 那些 `new texp` 待的同一個 note（`:900` 的 `new note` 建的）。建完設 `tmrf` 為欄位裡的 SYTM、`XYPO` 為 POS、`XYSCALE` 為 Scale，再把 `Txcolour` 跟 `LFColour` 都設成 `white`——使用者指出這兩個屬性都要給，符號才會是白色的，只設一個的話會留著 SYTM 原本畫的顏色。這條路徑跟 `functions/DrawingPlan1MatchLine.pmlfnc:16-20` 一樣（`note 1` 之後直接用絕對圖紙座標下 `fpt`/`tpt`），所以 `XYPO X <x> Y <y>` 也是絕對圖紙座標。

**要不要轉**：不是去問 `ADEGREES` 或 `RCODE`，而是量出來的。`.ViewSheetTransform()` 的第 7、8 個回傳值就是「往北走 1mm 在圖紙上的 x, y」，北向沒有正對圖紙上方就算旋轉——這樣 box 傾斜產生的 `Adegrees`、portrait→landscape 的 `RCODE LEFT`、以及兩者疊在一起的情況都涵蓋到，不用分開判斷。判斷式跟 `.ViewSheetTransform():2265-2268` 一樣比平方，避開 sqrt。這個矩陣要在 CE 還在 view 的時候量（它內部要讀 `SHPOS`/`ENUPOS`），所以量完才能把 CE 移到 sheet 的 note。

**轉幾度**：`ADEGREES` 是逆時針轉，指北向符號畫的時候是朝圖紙上方，所以要轉的角度就是「把圖紙上方轉到量出來的北向」那個角度。把 `(0,1)` 逆時針轉 `t` 得到 `(-sin t, cos t)`，所以 `cos t = ndy / len`，正負號跟 `ndx` 相反：

```pml
!ncos = !ndy / sqrt(!nlen2)
!nang = acos(!ncos)
if (!ndx gt 0) then
    !nang = !nang * -1
endif
```

`!ncos` 有夾在 -1 .. 1 之間再送進 `acos()`——浮點捨入讓它跑出界一點點的話 `acos()` 是沒有解的。

**這裡有個假設**：角度算法假設 SYTM 本身是畫成箭頭朝上（圖紙 +Y）。如果符號是朝右畫的，實機會差 90 度，`!nang` 減 90 即可。

**防呆**：

- `Scale` 空白或 `le 0` 時退回 1（也就是 SYTM 原本畫的大小），不要把箭頭縮成看不見。
- `!nlen2` 是 0（量不到東西）時當作沒旋轉，避免除以零。
- POS 欄位除了 Pick 按鍵寫進去的 `X <x> Y <y>`，也吃 BorderText 那幾個欄位用的 `x,y` 格式（使用者可能手打）。
- `POS` 空白就整段不做；`North Arrow` 空白也不做。

### 待實機驗證

1. 填 `North Arrow` + `POS`，跑一個**沒有旋轉**的 box，確認符號出現在指定的圖紙位置、方向朝上、大小是 SYTM 原本的大小。
2. `Scale` 改成 2 跟 0.5 各跑一次，確認符號真的跟著放大縮小，而且顏色是白的。
3. 跑一個**傾斜的 box**（會下 `Adegrees` 的那種），確認箭頭真的指向模型北，而不是差 90 度（差 90 度就是上面那個「朝上/朝右」的假設錯了）。
4. 跑一個觸發 `portrait → landscape`（`RCODE LEFT`）的 box，確認一樣轉到正確的北向。
5. `POS` 留空，確認完全不畫、也不報錯。
6. `Save` / `Load` 一輪，確認三個欄位都存得回來（`Scale` 是 real，特別確認讀回來不是空的）。

## 已修：`.Load()` 讀到「這版表單已經沒有的欄位」會整個中斷（2026-08-17，**由使用者實機回報**）

### 症狀

按 `Load` 讀一個稍早存的檔，跳出錯誤視窗：

```
(2,759)  Object does not have a member NORTHROTTEXT
In line 1761 of PML function drawingplan1.LOAD
         $!option = $!val
```

那個存檔是 `North Arrow When View is Rotated` 還存在時存的，欄位改成 `Scale` 之後 `.northrottext` 已經不存在了。

### 原因：那個「跳過失敗的行」的 `handle any` 其實沒有保護到任何東西

`.Load()` 裡本來是這樣寫的：

```pml
!option = !line.before('=')
!val = !line.after('=')
handle any
elsehandle none
    handle any
        -- this one line failed to apply ... skip it
    elsehandle none
        ...
        $!option = $!val
    endif
    endhandle
endhandle
```

PML 的 `handle` 區塊是掛在**它前面那一個敘述**上的（這一點檔案裡別處的註解也寫過）。裡面那個 `handle any` 被放在 `elsehandle none` 區塊的第一行，前面根本沒有敘述可以掛，所以它什麼都沒保護——`$!option = $!val` 是裸的，一出錯整個 `.Load()` 就斷在那裡，後面的欄位全部沒讀到。外面那個 `handle any` 也只保護到 `!val = !line.after('=')`。

（註解寫的意圖是對的：「這行套用失敗就跳過，繼續讀下一行」。只是位置錯了，所以從來沒生效過。）

### 作法（`forms/DrawingPlan1.pmlfrm:1621-1765`）

- 刪掉那個沒作用的巢狀 `handle any / elsehandle none` 與對應的 `endhandle`，整段 body 往回縮排一層。
- 在 `$!option = $!val` 的**正下方**補上真正的 `handle any / endhandle`（空的），跟這個檔案其他地方（`:1602`、`:1745`）一樣的寫法。

這樣任何「存檔裡有、這版表單沒有」的欄位都會被安靜略過，Load 繼續讀完剩下的行。使用者手上那個舊存檔不用改，直接再按一次 `Load` 就會過。

**改的是 `.pmlfrm`，要 `kill !!DrawingPlan1` 再 `show !!DrawingPlan1` 才會生效。**

### 待實機驗證

1. 用出錯的那個舊存檔再按一次 `Load`，確認不再跳錯誤視窗，而且 `northrottext` 以外的欄位都有正確讀回來。
2. 重新 `Save` 一個新檔再 `Load`，確認 `NorthArrow` 三個欄位（含 real 型式的 `Scale`）都正確回填。

## 改寫：`DrawingPlan.pmlfrm` 改成三點法 + CAD 匯入（2026-08-17，**尚未實機驗證**）

切圖範圍（box）的建立方式整支改寫。程式位置：`design/forms/DrawingPlan.pmlfrm`（DESIGN 模組，`!!DrawingPlan`，不是 DRAFT 的 `!!DrawingPlan1`）。

### 使用者定案的需求

1. **CAD 圖由使用者自己縮放到 1:1 並放到正確位置**，E3D 端不做任何座標轉換（明確要求不要多這一層）
2. **高程（Z）由表單輸入**，CAD 2D 圖沒有這個資訊
3. **三個點決定一個圖框**，角度由點自己算出來
4. **沒有圖號也要能建 box**，草圖階段常常只是要知道會切成幾張圖
5. **不做重複判斷**。原本設計過用一個 CAD 端唯一 ID（entity handle）存成 `cadid:` TEXT 當比對鍵，使用者否決：那個 ID 在 E3D 裡看不到，使用者無法把清單上的 box 對應回 CAD 上哪一格。改用「使用者自訂短代號」也不行——E3D 不接受重名，讓使用者自由輸入遲早撞名。結論是**草圖階段能轉出正確範圍的圖面就夠了，重複匯入就重複建**

### 三點如何變成 box（`.MakeBox()`）

- `P1 -> P2` 是第一條邊，長短邊不限，程式自己算
- `P3` 落在該線之外，決定另一個方向的長度和圖框往哪一側長
- 作法：求 P3 在 P1P2 上的垂足，`垂足 -> P3` 就是 box 的第二軸（側邊符號已經內含在方向裡），兩點距離就是第二個邊長。**不需要三角函數也不需要開根號**，只用到 `POSITION.distance()` 和 `POSITION.direction()`，兩者 repo 內都有現成用例（`DrawingPlan1GridAnnotation.pmlfnc:95`、`ImportATTAtoATE.pmlfnc:57`）
- 只設 `ORI Y is <dir> Z is U`，X 軸由 Y、Z 推導出來，會落在 P1->P2 這條線上。X 指向正或反描述的是同一個 box（box 對自己的軸對稱），所以不必處理符號
- `.Apply()` 的 `efpla`/`nfpla` 判斷會自己把 box 的軸對應到 E/N，所以長邊被指派成 X 還是 Y 都無所謂

### 表單結構（為了以後擴充）

改成 tabset，目前兩個分頁，共用底下的 `Elevation` 欄位（`Bottom U` / `Top U`）：

- **Pick 分頁**：在 3D 點三點（`EDGPACKET` + `definePosition`），可空的 `Drawing No.`，Create / Clear Points / Delete Box
- **Import 分頁**：選檔、格式說明、Import、結果清單

**關鍵：分頁只負責把三個點和高程湊齊，然後呼叫同一支 `.MakeBox()`。** 導 site、命名、建 EQUI/BOX/TEXT、防呆全部只有一份。使用者確認以後還會有第三種方式（例如依結構網格自動切），到時候只要新增分頁接上 `.MakeBox()`。

### 匯入檔格式

```
E1;N1;E2;N2;E3;N3;DwgNo;Rev;Title1;Title2;Title3;Ubot;Utop
```

只有前六個座標必填。`Ubot`/`Utop` 留空就吃表單的 Elevation 欄位。`--` 開頭的行忽略。

**`.SplitKeep()` 不能改用 `STRING.split()`**：PML 的 `split()` 會把空 token 丟掉，只要使用者留空一個選填欄位，後面所有欄位就整排位移。所以自己用 `.before()`/`.after()` 走分隔符，保留空欄位。

CAD 端還需要一支 LISP：讓使用者依序點三點、append 一行到 CSV。**尚未撰寫。**

### 順手修掉的既有問題

1. **寫死的 `=2013286748/281463` 拿掉**，改成 `.GotoBoxSite()`：導到 `/<projid>_DrawingPlanBox`，site 不存在就 `WORLD` 後 `new site`（並跳訊息告知建在哪個 DB，因為新元素會落在當下的 DB，這點要讓使用者看得到）。**EQUI 不能直接掛在 SITE 底下**，所以還要找/建一個 ZONE（`/<projid>_DrawingPlanBox_Z1`）
2. **`.DeleteBox()` 補上了**（原本按鈕呼叫一個不存在的 method，按下去必報錯）。加了防呆：只有 CE 在 `/<projid>_DrawingPlanBox` 底下才准刪，刪整個 EQUI，刪前跳確認
3. **`new text` 之後 CE 會停在剛建立的 TEXT 上**，原本連建 rev/title1~3 四個 tag 會變成一個套在另一個底下。`.MakeTagText()` 每次進來先 `$!equi` 導回去
4. **匯入時單筆失敗不中斷整批**：`.MakeBox()` 成功回傳空字串、失敗回傳原因字串，呼叫端記到結果清單繼續跑。圖號撞名是最可能的失敗原因
5. **`return` 不寫在 `handle any` 區塊裡面，也不用巢狀 `handle`**，一律改成 `!ok = true` / `handle any` 設 false / `endhandle` 後才判斷。PML 在這兩處的行為沒把握，扁平寫法比較安全
6. **刪掉的死 UI**：`Calculate by Drawinglist`、`Margin`、那排 lock toggle、`Apply` 按鈕——全部沒有 `call` 也沒有任何程式碼

### 實機驗證結果：Pick 分頁點完第一點就噴 Syntax error（2026-08-17，已修，待再驗）

使用者貼 `error.png`：點完 P1 之後跳 `Aborted !!DrawingPlan.MarkPoint(!this.return[1].position, 1) (Removed) - (47,15) CP: Syntax error.`。

關鍵線索是**表單上的 P1 欄位已經填好了**（`-245010.0000mm` / `4565676.0000mm`），所以 `.MarkPoint()` 前半段有跑完，錯在後面的 `.RefreshMarks()` → `.MarkOne()`。兩個獨立的 bug 疊在一起：

1. **`REAL.string('D4')` 會把單位一起帶出來**，欄位存的是 `-245010.0000mm`，而 `STRING.real()` 解析不了尾巴的 `mm`。`.Apply()` 讀 `WVOL` 時本來就是 `.replace('mm','').real()`，這裡漏了。加了 `.NumOf()` 統一處理，Pick / Import 兩邊讀數字全部走它。
   - 附註：舊版 `.modifyText()` 也是直接 `.val.real()`，同樣的問題，只是那個 method 只有文字欄位 CALLBACK 會呼叫，使用者大概從來沒觸發過。
2. **`AID TEXT |P1| AT $!pos` 的 `$!pos` 展開會帶 `WRT /*` 尾巴**，AID 不吃。錯誤訊息裡的 column 47 剛好就是 `AID TEXT |P1| AT E -245010mm N 4565676mm U 0mm` 之後 `WRT` 開始的位置。改成把 E/N/U 一個一個寫出來。

**這個 `$!pos` 帶 `WRT` 尾巴的陷阱要記住**：丟進 `AID` 會死，丟進 `POS` 反而是對的（見下一節，`POS $!pcen` 就是刻意這樣寫）。

### 實機驗證結果：`Create Box` 在 `.distance()` 就死（2026-08-17，已修，待再驗）

Command Window：

```
(2,869)  Error in conversion to world co-ordinates. Check for unset objects
 In line 155 of PML function drawingplan.MAKEBOX
    !xlen = !pfrom.distance(!pto2)
```

**`object POSITION()` 建出來再逐項填 `.east`/`.north`/`.up` 的 POSITION，身上沒有座標系**，`.distance()` 和 `.direction()` 要轉世界座標時就抓不到東西。上一節那個 `$!pos` 會帶出 `WRT /*` 尾巴的現象，其實就是同一件事的另一面——正常的 POSITION 本來就帶著它。

改法：加 `.PosOf(!e, !n, !u)`，用字串建 POSITION 並在尾巴補上 `WRT /*`。負座標不寫負號，改成翻轉方位字母（`E -245010` 寫成 `W 245010`），確保產生的字串一定是 PDMS 吃得下的形式（這個專案的座標是 `E -245010 / N 4565676` 這種等級的數字，一定會遇到負值）。

全部建 POSITION 的地方（`.MakeBox()` 的四個、Pick 分頁的三個、Import 分頁的三個）都改走 `.PosOf()`。box 的 `POS` 也順便改成 `POS $!pcen`，省掉自己在命令列上處理負數。

### 實機驗證結果：`.PosOf()` 本身語法錯誤（2026-08-17，已修，待再驗）

```
(47,15)  CP: Syntax error
 In line 440 of PML function drawingplan.POSOF
    !estr = 'W ' & (0 - !e)^^.string().replace('mm', '')
```

**PML 不接受在括號運算式上直接呼叫 method**，`(0 - !e).string()` 是語法錯誤，訊息裡的 `^^` 剛好標在 `)` 和 `.string()` 中間。翻正負號要先存進變數再呼叫。

注意這跟 method 串接是兩回事：`!str.replace('mm','').trim().real()`、`!this.files.dtext.size().gt(0)` 這種在變數或前一個 method 回傳值上繼續串是正常的，repo 裡到處都是。壞掉的只有「括號包住的算式」後面接 method 這一種。

### 實機驗證結果：幾何過關了，卡在 `.GotoBoxSite()` 查 DB 名稱（2026-08-17，已修，待再驗）

```
(2,111)  Cannot access element type DB from the level of SITE /400999DAC_DrawingPlanBox
    var !dbname name of db of ce
 Called from line 182 of PML function drawingplan.MAKEBOX
```

**三點法的幾何運算（`.PosOf` / `.distance()` / 垂足 / `.direction()`）全部跑完沒事**，這是第一次走到建立元素的階段。

`var !dbname name of db of ce` 在 SITE 層級不合法。這行純粹是為了跳訊息告訴使用者新 site 建在哪個 DB，結果反而把流程打斷。改成包 `handle any`，查不到就只講「建好了，請自己確認 DB」。

**這次的副作用要注意**：`/400999DAC_DrawingPlanBox` 這個 site 已經被建出來了（`new site` 成功之後才死在下一行），但底下還沒有 ZONE。下一次執行會走 `!found = true` 的路徑跳過建立、然後補上 ZONE，會自己收斂，不用手動清。**但要確認這個 site 落在正確的 DB**——`new site` 會建在當下的 DB，這正是原本寫死 db 位址想避免又沒避免掉的問題。

### 實機驗證結果：`ORI` 兩個軸中間要有 `and`（2026-08-17，已修，待再驗）

```
(47,15)  CP: Syntax error
 In line 227 of PML function drawingplan.MAKEBOX
    ORI Y is S  ^^Z is U WRT /*
```

`^^` 標在 `Z` 前面。PDMS 的 `ORI` 一次給兩個軸時中間必須有 `and`，`ORI Y is S Z is U` 是語法錯誤，要寫 `ORI Y is $!ydir and Z is U WRT /*`。

這次 SITE → ZONE → `EQUI 1` → `BOX 1` 都建出來了，`POS` 也下完，死在下一行，所以 `XLEN`/`YLEN`/`ZLEN`/`LEVEL` 都還沒設。**tree 裡會留下一個半成品 `EQUI 1`，用表單的 `Delete Box` 清掉即可**（導到那個 BOX 或 EQUI 再按）。

### 實機驗證結果：box 建出來了；接著改成四點、單一 Pick 鍵（2026-08-17）

加上 `and` 之後 box 順利建立，**三點法 + site/zone/equi/box 這條路整條打通**。

使用者接著提出改版需求：

1. **只要一顆 Pick 按鈕**，按一次就連續點四個點
2. **改成四點**：前三點的意義跟原本一樣（P1→P2 一條邊、P3 決定深度），**第四點只取它的 U，當第二個高程**；第一個高程取 **P1 的 U**
3. **點完第四點直接建立 box**，不用再按 Create Box

作法：

- `.PickPoints()` → `.PickOne(!idx)` → `.PickDone(!pos, !idx)` → `.PickOne(!idx+1)`，**四個 EDGPACKET 接力**，每一個在自己的 action 裡掛下一個，第四個點完直接呼叫 `.CreateBox()`
- **一開始寫成「一個 packet 掛四個 `definePosition()`」是錯的**，實機噴 `(2,752) Array element 2 does not exist`，而且提示框顯示的是 P4 的文字。四次 `definePosition()` 只是**互相覆蓋同一個輸入**（提示文字被最後一個蓋掉），packet 仍然只收一個點就觸發 action，所以 `!this.return[2]` 不存在。`!this.return[1]` 這個索引寫法會讓人以為支援多個回傳值，實際上不是這樣用的。
- 欄位從 3 列 E/N 變成 4 列 E/N/U——高程改由取點決定，所以 U 一定要看得到、也要能手動改
- **表單根部的 `Elevation` frame 移進 Import 分頁**。Pick 分頁的高程來自 P1/P4 的 U，但 Import 分頁沒有取點，仍需要這兩個欄位當 CSV 留空時的預設值
- `Create Box` 按鈕保留，但只是給「手動打字修改座標後重建」用，畫面上加了說明

`.MakeBox()` 完全沒動——它的介面本來就是「三個平面點 + 兩個高程」，這次的改動全部落在取點與湊參數這一層。這正是當初把它抽出來共用的目的。

### 實機驗證結果：接力取點被「是否取代目前作用中的公用程式」對話框打斷（2026-08-17，已修，待再驗）

使用者回報：按 `Pick 4 Points` 選完第一點後跳出

```
Confirm
OK to replace currently active major application/utility "Basic Position" ?
   [Yes]  [No]
```

然後就停止選點，四個座標欄位全是空的。

原因：**在前一個 packet 還掛在事件系統上的時候去 add 下一個**，E3D 認為你要換掉目前作用中的 utility（`Basic Position` 就是定位取點這支），於是跳確認框把整條接力打斷。`.PickOne(!idx+1)` 是在 `.PickDone()` 裡呼叫的，而 `.PickDone()` 本身就是前一個 packet 的 action，執行當下那個 packet 還沒被移除。

解法照 `design/forms/componentcreation.pmlfrm:5879-5900` 的既有寫法（這是 repo 裡唯一另一支用 EDGPACKET 的程式）：

- `!packet.description` 給一個固定字串（`member .edgdesc`），`!!edgCntrl.remove(<description>)` 就能依它把自己的 packet 取下來
- `.PickOne()` 每次 **先 `.DropPicking()` 再 add**，加進去的時候事件系統是乾淨的，就不會跳確認框
- `!packet.remove` 改成 **FALSE**。原本是 TRUE，等於 framework 會在 action 結束後自己再移除一次——但那時候我們已經把下一個 packet 掛上去了，它移除的會是**剛加進去的那個**，接力會無聲無息地停掉。改成 FALSE 之後移除只有我們自己在做，時機完全確定
- `!!edgCntrl.add()` 有回傳值（`if (!!edgCntrl.add(!packet)) then endif`），照既有寫法接住
- `.Close()` 也要 `.DropPicking()`，否則關掉表單後 packet 還留在事件系統裡

### 實機驗證結果：四點建立 box 成功（2026-08-17）

`Pick 4 Points` → 依序點四點 → box 自動建立，整條流程通了。使用者接著提出兩個調整：

1. **建立成功不要跳對話框**。取點的用意就是一張接一張連續切，每張都要按掉一個視窗很煩
2. **圖號和其它圖面資訊移到新的 `Info` 分頁**

作法：

- 新增 `frame .infofr 'Info'`，含 `Drawing No.`、`Rev`、`Title 1~3`，`Drawing No.` 從 Pick 分頁搬過來
- `.CreateBox()` 把這五個欄位一起傳進 `.MakeBox()`（原本 rev/title 四個參數都是傳空字串），所以 `rev:` / `title1:` 那幾個 TEXT 元素現在真的會被建出來
- 拿掉成功時的 `!!alert.message('Created ...')`。**錯誤訊息全部保留**，失敗還是要講
- **建立成功後只清空 `Drawing No.`**，`Rev` 和三個 title 留著。圖號每張圖唯一，不清掉的話連續切下一張一定撞名報錯；但 title 通常整套圖共用，清掉反而要重打。這是我自己下的判斷，不是使用者指定的
- `.ClearPoints()` 不再管圖號（那個欄位已經不在 Pick 分頁），Info 分頁自己有一顆 `Clear`

### 新增：Info 分頁的 `Apply`，套用到目前選取的 box（2026-08-17，**尚未實機驗證**）

使用者說明實際工作流程：**先把所有 box 都點完，再一個一個選取、輸入圖面資訊**。所以 Info 分頁要有 `Apply`，作用在目前導覽到的那個 box 上。另外圖號怕重名，按下 Apply 時要先檢查。

- `.ApplyInfo()`：從 CE 找出所屬 EQUI → 檢查圖號 → 改名 → 寫入 rev/title 的 TEXT
- **圖號重名檢查**：先 `$/圖號` 試著導覽過去，導得到就代表名字被佔用了，跳錯訊息並指出是誰佔用（`Drawing No. xxx is already used by /yyy`）。**導到的如果就是正在標的這個 box，不算衝突**——那只是 Apply 按了第二次。E3D 自己也會擋重名，但它的錯誤訊息說不清楚是撞到哪一個
- `.CurrentBoxEqui()` 抽出來共用：確認 CE 在 `<projid>_DrawingPlanBox` 底下、取得所屬 EQUI，失敗時自己跳訊息並回傳空字串。`Delete Box` 也改成走它，兩條路的判斷不會再各寫一份
- **`.MakeTagText()` 改名 `.SetTagText()` 並改成「有就覆寫、沒有才新增」**。原本一律 `new text`，Apply 按兩次就會在同一個 EQUI 底下留下兩個 `rev:`，`DrawingPlan1.Apply()` 掃到哪一個是碰運氣。**空白欄位維持不動**，不會清掉 box 上已有的資料——因為表單不會把選取 box 的現有資訊載回來，「所見即所得」在這裡是危險的
- Apply 成功不跳訊息，跟建立 box 的處理一致；錯誤照跳

### 新增：Info 分頁的 `Read CE`（2026-08-18，**尚未實機驗證**）

使用者提出：Apply 只會覆寫有填的欄位、空白欄位不動——但表單本身不會顯示 box 目前已經有什麼，等於盲改。加一顆 `Read CE`，把目前選取 box 的既有 `Drawing No.` / `Rev` / `Title1~3` 讀回表單，改完再 Apply。

- `.FindTagText(!equinav, !tag)` 從 `.SetTagText()` 裡拆出來獨立成一個 method：找出 `tag:*` 那個 TEXT 的 ref，兩邊共用同一段掃描邏輯
- `.TagValue(!equinav, !tag)` 用 `.FindTagText()` 定位、導過去讀 `STEXT`、取 `:` 後面的值，找不到回傳空字串
- `.ReadInfo()`：`.CurrentBoxEqui()` 取得所屬 EQUI，`namn` 開頭是 `=`（無名 box）就把 `Drawing No.` 留空，否則填入名稱；四個 tag 值分別讀回四個欄位
- Pick / Import / Info 三個分頁現在共用同一套「先找、再判斷有沒有、要嘛覆寫要嘛新增」的邏輯，`.SetTagText()` 本身沒有變化，只是內部的掃描搬到 `.FindTagText()`

### 改動：Pick 分頁和 Info 分頁徹底切開，拿掉 Info 的 `Clear`（2026-08-18，**尚未實機驗證**）

使用者問「Info 的 Clear 按鍵是否還有存在必要」，討論後發現一個比按鍵本身更重要的問題：**`.CreateBox()` 一直都在讀 Info 分頁的 `Drawing No.`/`Rev`/`Title1~3`**，這是分頁還沒拆開時留下的行為。照使用者的實際流程（先把所有 box 都點完、不命名，再一個一個用 Info 分頁 `Read CE` + 改 + `Apply`），這代表：如果在用 Info 分頁改某個 box 的資訊、還沒按 `Apply` 就切回 `Pick` 分頁點下一個 box，**新 box 會悄悄繼承 Info 分頁裡還沒套用的那些值**。

使用者確認要徹底切開，兩件事一起做：

- **`.CreateBox()` 一律建立無名、無 rev/title 的 box**：呼叫 `.MakeBox()` 時 `dwgno`/`rev`/`title1~3` 全部傳空字串。命名和填資訊完全交給 `Info` 分頁的 `Apply`。這樣 Info 分頁裡任何還沒套用的內容都不可能滲透進新建立的 box
- **拿掉 `Info` 分頁的 `Clear` 按鈕**。`.ClearInfo()` 這個 method 留著，但只在 `.DrawingPlan()` 表單啟動時呼叫一次，用來把欄位歸零；不再綁按鈕。理由：`Read CE` 對「已經選好的 box」做得比 `Clear` 更好（載入真實現況，而不是盲目清空），`Clear` 唯一顧得到、`Read CE` 顧不到的情況（沒有選到有效 box、`Read CE` 什麼都不做）在切開兩個分頁之後已經不會再有殘留資料造成的副作用——不會有東西可以「不小心用到」

`.MakeBox()` 本身完全沒動，它的介面一直都是「三個平面點 + 兩個高程 + 五個可留空的字串」，這次改動一樣全部落在呼叫端。

### 待實機驗證（都沒在 E3D 上跑過）

1. `ORI Y is <dir> Z is U WRT /*` 這個語法能不能被接受，以及建出來的 box 角度對不對。**這是最需要先確認的一項**，整個三點法都靠它
2. `new text` 能不能建在 EQUI 底下（README 舊記錄寫「box 底下的 TEXT」，實際掛在 EQUI 還是 BOX 底下沒有確認過）。`.Apply()` 用 `coll all text for <equi>` 收，掛在 EQUI 底下應該收得到。失敗的話 `.MakeTagText()` 會靜默跳過，box 還是會建出來，但 rev/title 會遺失
3. `.GotoBoxSite()` 在 site 不存在時能不能順利建 SITE + ZONE，以及建到哪個 DB
4. 匯入一個含空欄位的 CSV，確認 `.SplitKeep()` 的欄位對應沒有位移
5. 建好的 box 拿到 DRAFT 的 `!!DrawingPlan1` 清單裡，確認 `.AllBoxes()` 收得到、`.Apply()` 轉得出正確範圍（**這才是真正的驗收點**）
6. 轉過角度的 box 大量出現後，`.Apply()` 挑比例那段（`forms/DrawingPlan1.pmlfrm:708`）的疑慮見下

### 明確決定「先不動」的項目

`.Apply()` 挑比例用 `!boxXlen`/`!boxYlen`（box 自己的軸）去配 500/400（圖紙的軸），但前面算 `!elen`/`!nlen` 就是為了把 box 的軸對應到圖紙的軸。box 正交時兩者一致所以看不出來，一旦大量出現轉過的 box，當 box 的 X 軸對到圖紙的 Y 方向時就會拿錯邊算比例。**使用者要求先不要改，他要自己再測。**

### 優化：`DrawingPlan1.pmlfrm` 的 `.AllBoxes()` 載入速度（2026-08-19，**已實機驗證**）

使用者反映案子比較大時，載入 `DrawingPlan1.pmlfrm`（表單建構子 `.DrawingPlan1()` 一開始就會呼叫 `.AllBoxes()`）會變慢。原因：`.AllBoxes()`（`forms/DrawingPlan1.pmlfrm:263`）用 `coll all equi with (matchwild(name of site, |/$!projid_DrawingPlanBox|))`，沒有 `for`/`within` 限縮範圍，等於對整個 project 的**所有 DB 的所有 EQUI** 做一次全域掃描，逐一比對每個 EQUI 所屬 SITE 的名稱——掃描量跟全專案 EQUI 總數成正比，不是跟真正的 DrawingPlanBox 數量成正比。

改成先確認 `/<projid>_DrawingPlanBox` 這個 site 是否存在（`$!sitename` 包 `handle any` 判斷，寫法跟 `design/forms/DrawingPlan.pmlfrm` 的 `.GotoBoxSite()` 一致），存在的話才用 `coll all equi for $!sitename` 只掃該 site 底下的子樹；不存在就直接給空清單，不報錯。CE 用 `!ce = ref` / `$!ce` 存回，掃描前後不改動使用者原本所在位置。

**實機驗證結果**：使用者確認清單內容跟舊寫法一致，載入效率提升不少。

## 其他已讀程式時發現的疑點（尚未確認是否為真正 bug，僅供之後查證）

1. **`functions/DrawingPlan1EquiAnnotation.pmlfnc:143-161, 212, 218, 415`**：多處使用 `!namedir` 判斷 up/down/left/right，但整支函式內都沒有對 `!namedir` 賦值。
2. **`functions/DrawingPlan1MatchLine1.pmlfnc:48`**：`down` 方向的 `!tempp6` 用了 `!tempdirr`（往右），對照 `right`/`left`/`up` 三個方向的對稱寫法，這裡疑似應該是 `!tempdirl`（往左），可能複製貼上時漏改。
3. **`forms/DrawingPlan1.pmlfrm:1885-2064`（`.MachLineCode()` method）**：邏輯很像 `DrawingPlan1MatchLine1.pmlfnc` 的舊版，帶大量 `$( old = ... $)` 註解，但全 repo 搜尋不到任何呼叫它的地方，疑似未使用的舊版遺留程式碼。
4. **`functions/DrawingPlan1LineNoAnnotation.pmlfnc:807-899`**：`endfunction` 後面還有一大段被 `$( ... $)` 包住的死碼，也是舊版邏輯殘留。

## Git / Repo 狀態

- `draft` 目錄是獨立 git repo，目前 branch `master`
- Remote：`https://github.com/tw-tseng/pml-draft`（已 push，含 2 個 commit：`5e35eed` Initial baseline、`28c5c9f` "claude未修改的版本"）
- `functions/DrawingPlan1LineNoAnnotation.pmlfnc` 曾有一次縮排/清理的 commit（修正 `handle any` 縮排、移除未用的 `viewdirup`/`viewdirleft` 變數宣告）

## 新增：CAD 端取點程式 `cad/DrawingPlanBox.lsp`（2026-08-19，**尚未實機驗證**）

README 先前停在「CAD 端還需要一支 LISP：讓使用者依序點三點、append 一行到 CSV。**尚未撰寫。**」——這次寫了，檔案在 `cad/DrawingPlanBox.lsp`，指令 `E3DBOX`。

### 使用者定案的兩點

1. **高程（Ubot/Utop）預設留空，由 E3D 表單的 Elevation 欄位決定**，但 LISP 開頭提供一次性輸入（P1 提示列的 `Elev` 選項），設了就寫進之後每一行。**不是每格問一次**——同一張 CAD 平面圖幾乎一定同一層樓，每格問是重複勞動又容易打錯；而一個 dwg 擺兩三層樓的情況也真的有，所以留一個整批設定的入口。預設留空的理由是高程是 E3D 端的概念（model 座標），錯了改表單一個欄位就好，寫死在 CSV 裡要改就得編檔案或重點。
2. **CAD 端只出座標，圖號/Rev/Title 一律在 E3D 的 `Info` 分頁填**。所以第 7~11 欄永遠寫空字串，`.Field()` 讀到空的照樣安全（`.MakeBox()` 對這五個參數本來就允許空）。

### 幾個實作上的決定

- **座標一律 `(trans p 1 0)` 轉成 WCS**。使用者若轉過 UCS，直接拿 `getpoint` 的回傳值會是 UCS 座標，寫出去就整批偏掉。
- **數字用 `rtos` mode 2 精度 4，並在前後強制 `DIMZIN` 為 0**。`DIMZIN` 有些設定會把 `0.5` 縮成 `.5`，PML 的 `STRING.real()` 解析不了。
- **每切一格就在 `E3D_DWGBOX` 圖層畫出 box 的四角外框加編號**。外框是照 `.MakeBox()` 同一套算法（P1P2 當一邊、P3 的垂足向量當另一邊）算出來的**真正四角**，不是三個點連線——所以使用者在 CAD 上看到的就是 E3D 會建出來的範圍。編號是**該筆在 CSV 裡的實體行號**，E3D 匯入結果清單講的也是同一個行號（`line 7 - created ...`），所以填圖號那一輪可以拿畫面上的號碼對回 E3D 的清單。這正好補上當初否決 `cadid:` 時留下的缺口（那次否決的理由是 ID 在 E3D 裡看不到）。圖層可以隨時凍結或刪掉，程式不會回頭讀它。
- **每筆寫完在命令列 echo 出圖框尺寸（mm）**。CAD 圖沒縮到 1:1 的話這裡會直接看出來（`40000 x 30000` vs `40 x 30`），不用等到 E3D 建出一堆小 box 才發現。
- **幾何防呆在 CAD 端也做一次**（P1=P2、P3 落在 P1P2 線上），跟 `.MakeBox()` 的判斷一致。與其讓它變成匯入時的一行 skipped，不如當場講。
- **提示文字全用 ASCII**。LISP 檔是照系統 codepage 讀的，中文在某些 AutoCAD 版本會變亂碼。
- 檔名預設是 `<dwg 檔名>_e3dbox.csv` 放在 dwg 同目錄，不用先選檔就能開始；`File` 選項可以改。**既有檔案一律用附加（`open` 的 `"a"`），不會覆蓋**——`getfiled` 用 flag 1 會跳「檔案已存在，是否取代」的確認框，那是對話框自己的行為，按確定也不會清掉檔案內容。
- 新建檔案時寫兩行 `--` 開頭的表頭（E3D 會跳過），讓 CSV 用文字編輯器打開時看得懂欄位順序。

### 待實機驗證

1. `E3DBOX` 在使用者的 AutoCAD 版本能不能載入、`entmake` 的 LWPOLYLINE / TEXT 有沒有正確產生
2. 寫出來的 CSV 丟進 E3D `!!DrawingPlan` 的 Import 分頁，`.SplitKeep()` 的欄位對應正不正確（**這同時也驗證了 README 上面那條掛著的「匯入含空欄位的 CSV」項目**——本程式產生的每一行第 7~11 欄都是空的）
3. 匯進去的 box 拿到 DRAFT 的 `!!DrawingPlan1`，確認範圍跟 CAD 上畫出來的外框一致

### 實機驗證結果：`.SplitKeep()` 的 `do while` 不是合法 PML（2026-08-19，已修，待再驗）

按 `Import` 直接噴：

```
(47,15)  CP: Syntax error
 In line 1029 of PML function drawingplan.SPLITKEEP
    do ^^while (!rest.matchwild(!pat))
 Called from line 969 of PML function drawingplan.IMPORTFILE
    !f = !this.SplitKeep(!line, ';')
```

`^^` 標在 `while` 上。**PML 沒有 `do while` 這個迴圈**——全 repo 搜尋 `do while` 只有這一行，其他地方一律是 `do !i from 1 to n` / `do !x values !arr` / 空的 `do`，配 `break` 或 `break if (...)` 跳出（例：`design/forms/componentcreation.pmlfrm:1698`、`:6252`）。

改成：

```pml
do !i from 1 to 500
	break if (not(!rest.matchwild(!pat)))
	!out.append(!rest.before(!sep))
	!rest = !rest.after(!sep)
enddo
```

用有上限的 `do !i from 1 to 500` 而不是空的 `do`，是因為失控的迴圈會把 E3D 整個卡死；500 遠大於這個格式的 13 個欄位，正常資料碰不到。

**這是 `.pmlfrm`，要 `kill !!DrawingPlan` 再 `show !!DrawingPlan` 才會生效。**

### 實機驗證結果：`.SplitKeep()` 過關了，但每一行都因為沒有高程被跳過（2026-08-19，已修，待再驗）

```
line 3 - skipped, no elevation on the line and none in the Elevation boxes
line 4 - skipped, no elevation on the line and none in the Elevation boxes
line 5 - skipped, no elevation on the line and none in the Elevation boxes
line 6 - skipped, no elevation on the line and none in the Elevation boxes

0 box(es) created, 4 line(s) skipped
```

不是 bug——`do while` 那個問題確實修好了（沒有再跳語法錯誤）。原因是 `Bottom U`/`Top U` 這兩個欄位**表單啟動時從來沒有給過內定值**，每次開表單都是空的，`cad/DrawingPlanBox.lsp` 產生的 CSV 本身第 12、13 欄也照設計留空（高程刻意留給 E3D 端決定），兩邊都空自然整批 skip。

使用者上一輪講的「Bottom U 內定值設為 0，Top U 內定值設為 50000」原來是要這兩個值**寫進表單的啟動內定值**，不是每次手動填。`.DrawingPlan()` 加了：

```pml
!this.ubot.val = 0
!this.utop.val = 50000
```

50000 只是起始值，之後每個專案自己在 Import 分頁改掉即可。

### 新增：`Split` 分頁，把既有 box 沿 X/Y/Z 切成 2 個（或以上）（2026-08-19，**尚未實機驗證**）

使用者提出四點需求：判斷 CE 是不是 box → 在 box 中心顯示 X/Y/Z 方向（箭頭+文字）→ 表單用 checkbox 選要切哪幾個方向 → 選一個點，切成 2 個（或以上）box。

### 整體設計

- **`Show Box`**：確認 CE 是 BOX、在 `<projid>_DrawingPlanBox` 底下（沿用 `.CurrentBoxEqui()` 的安全檢查，跟 `Delete Box`/`Apply` 同一套），讀出 box 的 `worpos`/`xlength`/`ylength`/`zlength`/`ori wrt worl`，**存進表單 member**，然後畫出中心球 + X/Y/Z 三支箭頭（`AID ARROW`，箭頭末端加文字標籤）
- **存成 member 而不是每次現查**：因為選分割點（`Pick Split Point`）是另一次使用者互動，中間 CE 可能已經移動到別的地方，分割一定要對「按 Show Box 當下那顆 box」動手，不能依賴分割當下的 CE
- **checkbox（`toggle .splitx/.splity/.splitz`）+ `Pick Split Point`**：只點一個點，同時勾幾個軸就切幾刀。勾 1 個軸 = 2 個 box，2 個軸 = 4 個，3 個軸 = 8 個（笛卡兒積）
- **原 box 的 rev/title1~3 會複製到每一個新 box，但圖號不會**——圖號本來就必須每張圖唯一，切完的每一片都要在 `Info` 分頁重新命名；rev/title 通常整套圖共用，延續下去比清空更省事（沿用先前 `Apply`/`Read CE` 就已經定案的邏輯）
- **原 box 只有在全部新 box 都成功建立後才刪除**；中途若有一片失敗，已建立的那幾片會回滾刪除，原 box 完全不動——避免「切一半」的狀態發生

### 重構：把 `.MakeBox()` 拆成兩半

`.MakeBox()`（3 點版）原本從算幾何一路做到 `new equi`/`new box`/`POS`/`ORI`/`XLEN`/`SetTagText`。這次把後半段（拿到 pcen/ydir 字串/xlen/ylen/zlen 之後才做的事）抽成新的 `.MakeBoxAt(!pcen, !ydirstr, !xlen, !ylen, !zlen, !dwgno, !rev, !title1, !title2, !title3)`，`.MakeBox()` 算完幾何後直接呼叫它。Split 用的是同一支 `.MakeBoxAt()`——不用點三個點，直接算好中心跟長寬高丟進去。純粹的邏輯搬移，`.MakeBox()` 原本的行為完全沒變。

### 分割點怎麼換算成 box 自己的座標

`Show Box` 存下來的是 box 的 X/Y/Z 方向（每個軸用字串形式存，如 `!this.splitxdirstr`），配合 `.offset(dir, 1mm)` 前後兩點的 E/N/U 差，反推出這個方向在世界座標裡的單位向量分量，再跟「撿到的點 - box 中心」做點積，得到撿到的點在 box 自己 X/Y 軸上的偏移量。這跟 `forms/DrawingPlan1.pmlfrm` 的 `.Apply()` 算 `efpla`/`nfpla` 用的「偏移再相減」手法是同一招，只是反過來用。Z 軸的分量因為假設永遠是世界 Up，直接就是 `dU`。

### 明確的假設與已知限制

1. **Z 軸永遠當作世界 Up**，不是從 box 自己的 ORI 讀出來的。全 repo 找不到任何 `.zdir()` 的用例可以確認 ORIENTATION 物件有沒有這個方法；但這個工具建出來的 box 全部都是 `ORI ... Z is U`（見 `.MakeBoxAt()`），所以拿來切的 box 本來就應該是水平的。如果之後要切一顆不是這樣建出來的、Z 軸真的歪掉的 box，這裡的 Z 軸顯示和切割都會是錯的。
2. **`AID ARROW` 全 repo 只有一個先例**（`design/forms/componentcreation.pmlfrm:1525`），這支表單自己從沒用過。已经照那個先例的語法照抄（`$!<...>` 傳 POSITION/DIRECTION/REAL，帶 `NUMBER`），但沒有實機跑過，箭頭畫不畫得出來、方向對不對、`PROPORTION 0.15` 好不好看都还不知道。中心球和 X/Y/Z 文字標籤沿用 `.MarkOne()` 已經實測過的 E/N/U 拆解寫法，這部分風險低很多。
3. **`member .splitcen is POSITION` 這個型別沒有在目前這支重寫過的檔案裡實測過**（舊版 `DrawingPlan.pmlfrm` 用過 `member .pointSt is POSITION`，但那是我重寫前的版本）。原本也想把 X/Y 方向存成 `member ... is DIRECTION`，但全 repo 完全找不到這種用法的先例，改成存字串（`.splitxdirstr`/`.splitydirstr`）、要用的時候再 `object direction(!str)` 現組，降低這裡的風險。
4. **切割防呆的門檻是 1mm**：撿到的點在某個要切的軸上，離兩端都要留至少 1mm，否則整批不建立、直接報錯，訊息會指出是哪個軸太靠邊。

### 待實機驗證

1. `Show Box` 對著一顆已經用 Import 建出來的 box 按下去，中心球和三支箭頭會不會正確顯示（**這是目前最大的未知數，`AID ARROW` 完全沒測過**）
2. 三支箭頭的方向對不對得上 box 實際的長寬高方向，長度是不是延伸到面上
3. 只勾 X：撿一個點，是否正確切成 2 個 box，範圍對不對
4. 同時勾 X 和 Y：是否正確切成 4 個，四個角落的範圍對不對
5. 撿的點太靠邊（<1mm）會不會正確擋下、不建立任何東西
6. 切完之後原 box 是否被刪除、新 box 是否能在 `Info` 分頁 `Read CE` 讀到複製過來的 rev/title
7. 故意讓某一片建立失敗（例如先手動占用某個名稱——不過這次圖號全部留空，比較難自然觸發，可能要另外設計測試方式），確認回滾邏輯真的會把已建立的幾片清掉、原 box 保持原樣

### 實機驗證結果：`Pick Split Point` 選完點後噴 `DOSPLITAT(<UNTYPED>) not found`（2026-08-19，已修，待再驗）

`Show Box` 本身順利跑完（tree 上看得到 `EQUIPMENT 1` 底下的 `BOX 1`，畫面也導到那顆 box），Split 分頁勾了 X、按 `Pick Split Point`、選完點後：

```
Aborted $!!edgCntrl.navigateAction (Reinstated) - (2,779)
Method <FORM>.DOSPLITAT(<UNTYPED>) not found.
```

### 原因

`.SplitPointPicked(!pos is POSITION)` 本身確實有跑（錯誤指名的是 `DOSPLITAT`，不是 `SPLITPOINTPICKED`），代表 EDGPACKET 回傳的 position 第一次交給一個宣告 `is POSITION` 的方法沒問題。問題出在**第二次**：`.SplitPointPicked()` 把自己收到的 `!pos`（已經是型別化的方法參數）**原封不動當唯一引數**再傳給 `.DoSplitAt(!pos is POSITION)`，這一步失敗，PDMS 判定引數是 `<UNTYPED>`，找不到吻合的方法。

沒有把握這確切是 PML 的什麼規則（可能跟「只有一個引數」有關，也可能跟別的因素有關）——`.PickDone(!pos is POSITION, !idx is REAL)` 傳給 `.SetPoint(!idx, !pos)` 是同樣「收到型別化參數再轉手」的寫法，卻沒有出這個錯，兩者間唯一明顯的差異是 `.SetPoint()` 是兩個引數、`.DoSplitAt()` 原本只有一個。既然原因抓不準，**改成完全避開這個傳遞形狀**，而不是猜一個修法。

### 作法

參照 `.PickDone()` 到最後一步 `.CreateBox()` 的方式——那一步用的是**零引數**方法，資料是先寫進表單 member，再由 `.CreateBox()` 自己讀回來，POSITION 從來沒有被當成引數轉手兩次。`.SplitPointPicked()` 照同一個模式改：

```pml
define method .SplitPointPicked(!pos is POSITION)
	!!DrawingPlan.splitpickpos = !pos
	!!DrawingPlan.DropPicking()
	!!DrawingPlan.DoSplitAt()
endmethod
```

新增 `member .splitpickpos is POSITION`，`.DoSplitAt()` 改成零引數，開頭讀 `!this.splitpickpos.wrt(WORL)` 取代原本的參數 `!pos`。`.DoSplitAt()` 內部其餘邏輯完全沒動。

**這個坑要記住**：POSITION（可能其他物件型別也一樣）當成方法參數收下來之後，**不要再原封不動當唯一引數轉手給下一個方法**——先寫進 member，讓下一個方法自己讀回來。

### 待實機驗證

1. 這次的修法本身有沒有解決問題——`Pick Split Point` 選完點後應該要繼續往下跑到 `.DoSplitAt()` 的正文（防呆檢查、建立新 box、刪除原 box），而不是卡在方法找不到
2. 前一輪列的「三支箭頭方不方向對」「切出來的 box 範圍對不對」等項目都還沒驗到，這次要是這關過了才輪得到

### 實機驗證結果：`Show Box` 的箭頭真的畫出來了，Z 軸切割也成功了；X 軸切割噴單位不合的錯誤（2026-08-19）

使用者這輪回報的截圖帶來兩個好消息，順便一個新 bug：

1. **`AID ARROW` 沒問題**——3D 畫面上 X/Y/Z 三個標籤都正確顯示，這是這個功能最大的未知數，過關了
2. **勾 Z、切一刀，成功了**——Result 清單有兩筆 `created =67128186/19424560`／`created =67128186/19424562`，代表 `.DoSplitAt()` 整條路（防呆、建立、刪原 box、回報）都走通了
3. **但勾 X 再切，噴** `DIMENSION(UNIT) MISMATCH in real arithmetic (+-*/ POW): cannot combine physical quantities DIST and SQDI`

### 原因

算 X/Y 方向單位向量時，直接拿「偏移 1mm 後的座標」減去「中心座標」（`!refx.east - !cen.east`），這個差值本身還帶著「長度」的單位標籤（DIST）。後面 `!dE * !uxE`（長度 × 長度）就被 PDMS 判定成「面積」（SQDI），跟其他純長度的量混在一起就報單位不合。

Z 軸沒事是因為 Z 那條路完全沒有這個乘法（`!localz = !dU` 是直接賦值，不是點積），只有 X/Y 這條「投影到 box 自己軸向」的路徑才會踩到。

`.MakeBox()` 原本沒這問題，是因為它算方向分量用的是「長度差 ÷ 長度」（`!ux = (!e2-!e1)/!xlen`）——除法會讓單位互相抵消變成純數字，才能拿去再乘別的長度。我這次少做了那個除法。

### 作法

改成除以偏移點與中心的實際距離（用 `.distance()` 取得，跟 `.MakeBox()` 的 `!xlen = !pfrom.distance(!pto2)` 是同一招），而不是相信自己傳給 `.offset()` 的那個裸數字：

```pml
!refx = !cen.offset(!xdir, 1000)
!lenx = !cen.distance(!refx)
!uxE = (!refx.east - !cen.east) / !lenx
!uxN = (!refx.north - !cen.north) / !lenx
!uxU = (!refx.up - !cen.up) / !lenx
```

Y 軸同樣處理。Z 軸的 `!localz = !dU` 完全沒動（本來就沒問題）。

**這個坑要記住**：POSITION 的 `.east`/`.north`/`.up` 差值帶著 DIST 單位，可以互相加減、可以乘一個「已經確認是純數字」的量，但**不能兩個差值直接相乘**——要嘛先除掉一個同單位的量變成純數字，要嘛就不要乘。

## 使用者這輪同時要求的三個調整（一併做了）

1. **CE 是 EQUI 時自動跳到底下的 BOX，不要報「不是 BOX」**。`.CurrentSplitBox()` 加了一段：CE 是 EQUI 的話先 `coll all box for ce` 找底下唯一的那個 BOX（這個工具建的 box 本來就是一個 EQUI 配一個 BOX），自動導過去再往下走；CE 已經是 BOX 就跟原本一樣直接用；兩者都不是才報錯
2. **`Pick Split Point` 不用先按過 `Show Box`**。`.PickSplitPoint()` 開頭直接呼叫 `!this.ShowBox()`，用當下的 CE 重新鎖定目標、重畫箭頭，`Show Box` 從此變成「純預覽、非必要」的按鈕——兩顆按鈕永遠對同一份邏輯，不會有「先按過的那次」跟「現在要切的」是兩顆不同 box 的落差。配合這個改動，`.ShowBox()` 開頭加了 `!this.splitequi = ''`，確保失敗的時候不會殘留上一次成功時的舊資料
3. **`Split along Z` 內定打勾**（X/Y 維持不勾）。`.DrawingPlan()` 表單啟動時設 `!this.splitz.val = true`——大部分切圖是按樓層切，Z 是最常用的方向

### 待實機驗證

1. X 軸單位修好之後，勾 X 切一刀能不能成功（這次的重點）
2. 同時勾 X+Y（甚至 X+Y+Z）切出來的 4 個（或 8 個）box 範圍對不對
3. CE 導在 EQUI 上直接按 `Pick Split Point`（不先按 `Show Box`）能不能正常運作

### 調整：`Show Box` 改成開關、X/Y/Z 直排並加偏移量欄位、Result 改用單行文字（2026-08-19，**尚未實機驗證**）

使用者三個要求：

1. **`Show Box` 變成開關**：按一次顯示，再按一次隱藏
2. **X/Y/Z 改直排，各配一個偏移量輸入欄**：例如切高程時常常只能點到鋼構底面，但真正要切的位置在那之下 50mm，就是靠這個欄位補
3. **`Split` 分頁的 `Result` 不需要清單，只要一行文字講建了幾個 box**

### `Show Box` 開關 vs `Pick Split Point` 不用先按過它——兩個需求會互相打架，拆成兩支方法解決

上一輪才把「`Pick Split Point` 不用先按 `Show Box`」做成內部呼叫 `!this.ShowBox()`。這次 `Show Box` 一變成開關，若還是呼叫同一支方法，`Pick Split Point` 有可能在「使用者剛好前一刻按過 Show Box、箭頭正顯示著」的狀況下，反而把顯示關掉而不是重新鎖定目標——兩個需求對同一個方法有衝突的期待。

拆開：

- **`.RefreshBox()`**：真正做事的方法（原本 `.ShowBox()` 的全部內容——確認 CE、鎖定目標、存 geometry、畫箭頭），沒有開關語意，每次呼叫就是「用目前的 CE 重新來一次」
- **`.ShowBox()`**：純粹是按鈕的開關邏輯——`!this.splitequi` 有值代表正顯示著，再按一次就 `AID CLEAR ALL` + 清空後直接 return；沒有值才呼叫 `.RefreshBox()`
- **`Pick Split Point` 改呼叫 `.RefreshBox()`**，不再經過會開關的 `.ShowBox()`，永遠確保重新鎖定「當下 CE」，不受使用者之前有沒有按過 `Show Box`、箭頭現在是顯示還是隱藏狀態影響

### 偏移量欄位

X/Y/Z 三個 `toggle` 直排，每個右邊配一個 `is REAL` 的偏移量欄位（`.splitxoff`/`.splityoff`/`.splitzoff`），留空當 0（跟 `.ubot.val`/`.utop.val` 判斷 `.unset()` 同一招）。`.DoSplitAt()` 在算出撿到的點在 box 自己 X/Y/Z 上的投影座標（`!localx`/`!localy`/`!localz`）之後，直接加上對應的偏移量，之後所有防呆檢查和切割計算都用調整過的座標。

**正負號的意義**：偏移量往該軸的正方向移動用正數，往負方向用負數。以 Z 為例，Z 軸固定對應世界 Up，往下 50mm 就是輸入 `-50`。表單上的提示文字有講這個例子。

### `Result` 改成一行文字

`list .splitlog` 換成 `para .splitresult`（初始 `text ''`，PSD.pmlfrm 也有這個空字串預設值的先例）。`.DoSplitAt()` 原本每建一個 box 就 `!log.append('created ' & !newequi)`，這次拿掉，只保留 `!created`（回滾要用，不能拿掉），成功時改成：

```pml
!this.splitresult.val = !created.size().string() & ' box(es) created'
```

失敗時的行為完全沒變——還是 `!!alert.error(...)` 跳錯誤視窗，不寫進這個 paragraph。

### 待實機驗證

1. `Show Box` 按兩下，第二下箭頭有沒有正確消失
2. CE 沒有先按過 `Show Box`（或箭頭正被上一次按 Show Box 隱藏著）的狀態下，直接按 `Pick Split Point` 能不能正常運作、重新鎖定目標
3. Z 偏移量填 `-50`（或任意值），切出來的高程分界是不是真的往下移了 50mm，不是往上
4. `Result` 那行文字在成功後有沒有正確顯示數量

### 實機驗證結果：Split 分頁全部功能都測過了，OK（2026-08-19，**已實機驗證，結案**）

使用者確認：`Show Box` 開關、直排的 X/Y/Z 加偏移量、`Result` 單行文字，全部照預期運作。截圖顯示 `Split along Z` 打勾、Offset 填 `-100`，`Pick Split Point` 後 `Result` 正確顯示 `2 box(es) created`。

**`Split` 分頁（判斷 box、顯示軸向、勾選切割方向、偏移量、選點分割）到此收尾，功能完整可用。**

### 調整：拿掉三段說明文字，太占空間（2026-08-19）

使用者貼的截圖裡三段說明文字都被紅框標出來——`Show Box` 下方兩行、Offset 下方兩行、`Pick Split Point` 下方四行——要求全部拿掉。

移除：`.showhint`/`.showhint2`（Show Box 用法）、`.splithint0`/`.splithint0b`（Offset 說明）、`.splithint`~`.splithint4`（Pick Split Point 用法）。拿掉之後把 `Split along/Offset` 標題、X/Y/Z 三排、`Pick Split Point` 按鈕、`Result` 文字重新接起來，中間沒有留空隙。這些說明只存在於畫面上，不影響任何邏輯，純版面調整。

### 新增：`Merge` 功能，跟 `Split` 共用同一個頁籤，改名 `Split/Merge`（2026-08-19，**尚未實機驗證**）

使用者提出：多選幾個 box，按 Merge 合併成一個。順帶問「要不要跟 Split 放同一頁籤」——同意，Merge 只有一個按鈕，單獨開一頁太空曠，而且兩者都是「重新整理既有 box 的範圍」，操作對象和底層機制高度重疊。頁籤標籤從 `Split` 改成 `Split/Merge`（frame 內部代號 `.splitfr` 沒有動，只改顯示文字）。

### 怎麼選多個 box

沒有用 3D 多選（PML 沒有現成、有把握的方式讀出「使用者在 Explorer/3D 裡 ctrl 選了哪些元素」），改用這個專案已經有先例的做法：`draft/forms/DrawingPlan1.pmlfrm` 的 Drawing 分頁本來就是用一個 `multiple` 的 `list` 讓使用者多選 box（`.files1`/`.files`），照抄同一套：

- `list .mergelist 'Boxes' multiple`，`.RefreshMergeList()` 填內容——查詢照抄 `DrawingPlan1.AllBoxes()`（`coll all equi for $!sitename` 只在 `<projid>_DrawingPlanBox` 這個子樹底下找，不掃全專案；site 還不存在時安全跳過），這支已經在姊妹工具裡驗證過效能和正確性
- `Refresh List` 按鈕手動刷新（表單開啟時也會自動跑一次）。因為 Pick／Import／Split／Merge 都可能在同一次開表單期間建立新 box，用按鈕明確刷新比自動同步簡單、行為好預測
- `.MergeBoxes()` 讀 `!this.mergelist.selection()`（多選清單的既有寫法，`DrawingPlan1.pmlfrm` 的 `.selectce()` 已經在用），少於 2 個直接擋

### 合併範圍怎麼算

**前提：所有選到的 box 方向要完全一樣**——用 Y 軸方向字串（跟 Split 用同一招，`.ori.orientation().ydir().string().before('WRT')`）互相比對，不一樣就整批擋下、講清楚是哪一個 box 方向不對。沒有這個前提，「合併」在數學上沒有意義（不同方向的 box 沒辦法用一個 axis-aligned 的新 box 同時包住）。

以清單裡第一個 box 當參照座標系，其餘每個 box 的中心點都用 `.DoSplitAt()` 已經驗證過的「偏移 1000mm、除以 `.distance()` 得到單位向量、點積」手法投影到參照 box 的 X/Y（Z 固定世界 Up，跟 Split 同一個假設），算出每個 box 在這個共同座標系裡的範圍，**取所有 box 範圍的聯集**（每軸分別取最小下界、最大上界），聯集的中點和長度就是合併後新 box 的中心和長寬高。

**這不會檢查選到的 box 是否真的相鄰、中間有沒有縫**——只是把選到的全部包起來，跟這個工具一貫「草圖階段能框出正確範圍就好」的定位一致。如果選了兩個離很遠的 box，合併出來的新 box 會涵蓋中間一大片沒被選到的空間，這是預期行為，不是 bug。

### 建立順序：先建新 box，成功才刪舊的

跟 Split 同一個安全原則——`.MakeBoxAt()` 失敗就整批不動，不刪任何東西；新 box 建立成功後才逐一刪除被合併的來源 EQUI，如果某個來源刪不掉只跳警告（新 box 已經是好的，不會因為刪舊的失敗就撤銷合併）。

### 合併後的名稱/Rev/Title

**新 box 一律無名、rev/title 全空**。被合併的幾個來源可能各自有不同的圖號和 rev/title（尤其常見於「先 Split 切開、後來又想合回去」這種情境），沒有一個天經地義該保留誰的，所以乾脆全部清空，交給使用者事後在 `Info` 分頁重新填。

### 順手做的重構

`.CurrentSplitBox()` 裡「CE 在 EQUI 上、找底下唯一的 BOX 並導過去」那段邏輯抽成 `.BoxUnderEqui()`——現在 Merge 的清單迴圈裡每一筆也要做同樣的事，兩個呼叫點共用同一份判斷，不會有改一邊忘了改另一邊的風險。

### 待實機驗證

1. `Refresh List` 能不能正確列出 `<projid>_DrawingPlanBox` 底下所有 box（含剛剛 Split 出來的那幾個）
2. 選兩個方向相同的 box 按 `Merge`，合併出來的範圍對不對（尤其是拿一組先前 Split 出來的 box 合回去，範圍應該要跟原本切之前的 box 幾乎一樣）
3. 選兩個方向不同的 box，能不能正確擋下並指出是哪一個
4. 合併後 `Result` 文字、清單有沒有正確刷新（原本被合併的幾個名字應該從清單消失，新的無名 box 出現）

### 改法：Merge 改用 `object SELECTION()` 讀 3D/Explorer 多選，拿掉清單 widget（2026-08-19，**尚未實機驗證**）

使用者指到 `CHECK.TXT`（`D:\E3D\pdms_prog\E3D2.1\PA_pmllibE3D2.1\CHECK.TXT`，PML 端寫的是 `L:\...`，兩台機器同一個資料夾，見 memory 裡的路徑對應筆記），內容：

```pml
!sele = object selection()
!sele.getcurrent()
!sels = !sele.getselection()
!boxes = object array()
do !sel values !sels
	var !type type of $!sel
	if !type.eqnocase('BOX') then
		var !equi name of equi of $!sel
		if !equi.matchwild('*_DrawingPlan') then
			!boxes.append(!sel)
		endif
	endif
enddo
```

這證實 PDMS 有現成的方式讀出「使用者在 Design Explorer / 3D 裡目前選了哪些元素」（`object SELECTION()` → `.getcurrent()` → `.getselection()`，回傳一個可導覽的 ref 陣列）。上一輪因為沒有把握這件事，改用清單 widget（`multiple` 的 `list`，仿照 `DrawingPlan1.pmlfrm` 的 Drawing 分頁）繞過去——現在有了依據，換掉。

### 跟原本清單版的差異

- **拿掉 `.mergelist`/`.mergerefresh`，也拿掉 `.RefreshMergeList()`**。不再需要維護一份快取的清單、不需要「刷新」的概念——`Merge Selected` 按下去就是讀當下即時的選取，永遠是最新的
- **`Merge` 區塊縮成一顆按鈕**：畫面上只剩 `Merge` 標籤 + `Merge Selected` 按鈕，比清單版更省空間（延續使用者上一輪對版面精簡的要求）
- **驗證邏輯沒有照抄 `CHECK.TXT` 的 `matchwild('*_DrawingPlan')`（比對 EQUI 名稱）**，改成沿用這整支表單一貫的規則——比對**所屬 SITE** 是不是 `/<projid>_DrawingPlanBox`（跟 `.CurrentBoxEqui()`／`.GotoBoxSite()` 同一套判斷）。`CHECK.TXT` 那行比對的是 EQUI 名稱字串，跟這支表單建立 box 時用的「SITE 名稱」規則是兩個不同的東西，用 SITE 判斷才會跟其他分頁一致
- **選到 EQUI 也接受，自動往下找 BOX**（沿用 `.BoxUnderEqui()`，跟 Split 那邊 CE 在 EQUI 上的處理一致）
- **選到不相關的東西（不是 BOX/EQUI、或不在我們的 site 底下）就靜靜跳過，不報錯**。這是掃描一批多選結果、篩出「看起來像我們的 box」的情境，跟 Split 那種「使用者明確選了一個東西、告訴他錯在哪」的情境不一樣——如果使用者多選時不小心多框到一根管子，不該讓整個 Merge 因此擋下來

`.MergeBoxes()` 從蒐集完 `!names`（合格的 EQUI 名稱陣列）之後的邏輯完全沒動——方向一致性檢查、投影算聯集、建新 box、刪舊 box，全部沿用上一輪已經寫好的部分。

### 待實機驗證

1. `object selection()`/`.getcurrent()`/`.getselection()` 這組 API 能不能在這個環境正常運作（`CHECK.TXT` 是使用者提供的參考，這支表單自己還沒跑過）
2. 在 3D 或 Explorer 裡 ctrl 選兩個以上的 box，按 `Merge Selected`，能不能正確蒐集到、算出正確的合併範圍
3. 選取內容混了一些不相關的元素（例如一根管子），確認會被安靜跳過，不影響其餘 box 的合併
4. 只選到 EQUI（沒選到底下的 BOX）能不能正確自動往下找

### 調整：Delete Box 拿掉確認/結果對話框、Pick 和 Import 分頁再拿掉說明文字（2026-08-19）

使用者一次提四點，前三點已在對話中處理，第四點補上：

1. **確認合併邏輯（方向一致性檢查、投影算聯集）是否完整**——重新讀了一次目前 `.MergeBoxes()` 的內容，`!thisydirstr.neq(!ydirstr)` 的方向比對、`!ox`/`!oy`/`!oz` 投影、`!minx`~`!maxz` 的聯集計算全部都在，上一輪換成 `object SELECTION()` 讀取選取時只換了蒐集 `!names` 的那一段，後面的合併運算完全沒被動到，不是殘缺的。
2. **`Delete Box` 拿掉確認對話框和成功訊息**，直接刪除。錯誤訊息保留（刪不掉還是要講）
3. **Pick 分頁拿掉兩段說明**：`P1 -> P2 ... / P3 ... / P4 ...` 那三行，以及 `Create Box` 下面「Picking makes the box on its own...」那一行
4. **Import 分頁拿掉四行格式說明**（`One line per drawing...` 到 `Lines starting with -- are ignored.`）

拿掉的都是畫面上的靜態說明文字，沒有任何邏輯或欄位跟著被動到——欄位名稱、call 目標、資料流全部不變。目前四個分頁（Pick / Info / Import / Split-Merge）都已經照使用者要求把純說明性文字清掉，只剩必要的欄位標籤和按鈕。

### 實機驗證結果：7 個 box 成功合併，但 3 個 box 誤判成「方向不同」（2026-08-19，已修，待再驗）

好消息先講：**`Merge` 端到端真的跑通了**——`Result` 顯示 `Merged 7 box(es) into 1`，`object SELECTION()` 讀取 3D/Explorer 多選這條路確認可用。

使用者接著選 3 個從圖面上看明顯該合併的 box，卻被擋下說方向不同。使用者在 Command Window 對三顆分別下 `q ori`：

```
Orientation Y is N 12.523 E and Z is U
Orientation Y is S 12.523 W and Z is U
Orientation Y is S 12.523 W and Z is U
```

### 原因

`N 12.523 E` 跟 `S 12.523 W` 剛好相差 180 度——對一個以自身軸對稱的 box 來說，Y 指向正的還是反的描述的是**同一個實體方向**（`.MakeBox()` 的註解本來就寫過這件事：「whether it points forwards or backwards along that edge describes the same box」）。原本的比對是 `!thisydirstr.neq(!ydirstr)`，單純比字串是否完全相等，沒有把「互為相反」算進去，所以把這種物理上相同、只是符號相反的方向誤判成不同。

### 作法

改用 `.angle()`（跟 `forms/DrawingPlan1.pmlfrm` 的 `.Apply()` 判斷 `efpla`/`nfpla` 同一個方法）比對兩個 Y 方向的夾角，而不是比字串：

```pml
!ang = !thisydir.angle(!ydir)
if (!ang.gt(0.5) and !ang.lt(179.5)) then
	!badori = true
	!bad = !nm
endif
```

`.angle()` 只會回傳 0~180（沒有正負號），**夾角接近 0（同向）或接近 180（反向）都算通過**，只有真正不同角度（例如 90 度）才判定方向不合。留 0.5 度的容差是為了浮點數誤差。

**這個改動不影響合併範圍的計算**：投影用的 `!xdir`/`!ydir` 從頭到尾都是「清單第一個 box 自己的方向」，其他 box 只是拿它們的中心點和長寬高去投影、取聯集，跟每個 box 自己的方向符號無關，本來就不會因為某個 box 的 Y 反過來而算錯範圍——錯的只有「要不要放行」這一關的判斷。

### 待實機驗證

1. 這次修好的方向容差，能不能讓那 3 個 box 順利通過檢查並正確合併
2. 合併出來的範圍跟圖面上原本三個 box 框起來的範圍是否一致

### 新增：`Info` 分頁的 `Batch Number`，前綴字+序號批次命名，加「跳過已命名」開關（2026-08-19，**尚未實機驗證**）

使用者已經用 Split/Import 切出很多沒有圖號的 box，想要批次指定圖號：前綴字+序號，序號順序由「方向」決定（例如由下往上）。設計討論定案：

- **選取方式沿用 `Merge` 已驗證的 `object SELECTION()`**——3D/Explorer 多選要編號的 box，不用另外做清單，實際編號順序完全由「Order by」決定，跟選取/點擊順序無關（PML 沒有辦法讀出多選的點擊順序，只能讀出「選了哪些」）
- **「由左至右」不猜，改成明確的座標軸選項**：`Bottom -> Top (U)` / `Top -> Bottom (U)` / `West -> East (E)` / `East -> West (E)` / `South -> North (N)` / `North -> South (N)`，用 `option` 單選 gadget（`.batchdir`）。使用者確認「由左至右」在北上平面圖慣例下對應西到東，內定選項是 `Bottom -> Top (U)`（樓層切割最常見）
- **前綴字 + 起始序號 + 補零位數**：`Prefix`/`Start at`/`Digits` 三個欄位，起始值留空當 1、位數留空不補零
- **`Skip already-named` 開關**（使用者這輪加的）：打勾（預設）只動目前還沒有圖號的 box（ref 名稱 `=nnnn/nnnn`）；不打勾則選取範圍內全部 box 都重新編號，不管原本有沒有圖號——用來整批重新編號用

### 排序怎麼做

沒有「依 key 排序」的內建工具可用（這個 codebase 只在 STRING 陣列上見過 `.sort()`，沒有帶 key 的版本），改成手刻**選擇排序**：`!names`（EQUI 名稱）跟 `!keys`（該 box 中心點在選定座標軸上的世界座標）兩個平行陣列，用巢狀迴圈找最小/最大值互換位置。box 數量頂多幾十個，O(n²) 完全不是問題，換來的是不用去猜測、依賴不確定的排序 API。

### 命名怎麼避免撞名

`.BatchName(prefix, seq, digits)` 產生候選名稱字串（含補零）；命名迴圈裡每一個候選名稱先用「導覽看看存不存在」判斷是否已被佔用（跟 `.ApplyInfo()` 判斷圖號重複同一招），撞到就把序號加一繼續找，最多試 10000 次。這代表**同一個前綴可以分批跑、跑到哪算到哪**，或者兩個不同前綴共用同一個 site 也不會互撞。

### 蒐集邏輯完全沿用 `.MergeBoxes()`

BOX 或自動從 EQUI 往下找、必須在 `<projid>_DrawingPlanBox` 底下、其他不相關的東西安靜跳過——這段掃描邏輯跟 `Merge` 一模一樣，只是多了 `Skip already-named` 這一層過濾，以及順便記下每個 box 的排序用座標。

### 待實機驗證

1. `option` 這個 gadget類型（`.batchdir`）在這支表單裡是第一次用，`.dtext`/`.val`/`.selection()` 這組存取方式能不能正常運作
2. 選幾個沒有圖號的 box，`Order by` 選 `Bottom -> Top (U)`，按 `Assign Numbers`，編號順序是不是真的由下往上
3. `Skip already-named` 打勾時，選取範圍裡混著已命名的 box 會不會被正確跳過；取消勾選時，已命名的 box 會不會被正確覆蓋重新編號
4. 補零位數（`Digits`）填 3 的時候，產生的名稱是不是 `P-001`、`P-002` 這種形式

### 調整：`Batch Number` 拆成獨立 `Batch` 分頁、加第二個 `Order by`、Info 分頁清空說明文字（2026-08-19，**尚未實機驗證**）

使用者四點：

1. `Order by` 要有兩個
2. `Prefix` 內定 `"DWGNO-"`、`Start at` 內定 1、`Digits` 內定 3
3. Batch Number 要不要跟 Info 分開
4. Info 分頁所有說明文字都殺掉，怕介面太大

第 3 點使用者是用問的，但跟第 4 點（Info 太大）其實是同一件事——直接把 Batch Number 整區搬到新分頁 `Batch`，Info 分頁自然就瘦下來，兩點一次處理掉。分頁順序：`Pick / Info / Batch / Import / Split/Merge`。

### 兩個 `Order by`

`.batchdir`（1st）/ `.batchdir2`（2nd），都是同一組六個座標軸選項（跟原本一樣，不猜「左右」，明講 E/N/U）。**2nd 只在 1st 打平的時候才生效**，例如 1st 選「由下往上」、2nd 選「西到東」，效果就是先分樓層，同一樓層內再由左到右編號——這正是使用者原本說的「由下往上或由左至右」，只是兩個條件同時生效而不是二選一。內定值：1st = `Bottom -> Top (U)`、2nd = `West -> East (E)`。

**排序邏輯改成兩層比較**，不是把兩個 key 硬湊成一個數字（那樣容易因為座標尺度不同而互相干擾出錯）。改成明確的比較器：先比對兩個 box 在軸 1 的座標，差距在 1mm 以內視為「打平」（同一樓層可能因為浮點數誤差沒有完全相等），打平才去比軸 2。這個容差跟排序本身都是自己刻的選擇排序（`.MergeBoxes()` 也沒有現成的「依 key 排序」工具可用，同一個限制）。

### 三個欄位的內定值

`.DrawingPlan()` 表單啟動時設定 `!this.batchprefix.val = 'DWGNO-'`、`!this.batchstart.val = 1`、`!this.batchdigits.val = 3`——一開表單三個欄位就有值，不用每次手動打。

### Info 分頁瘦身

拿掉 `.pano`（Drawing No. 下面「Leave blank while still sketching...」那行）跟 `.infohint`/`.infohint2`/`.infohint3`（「Select a box... Read CE... Apply...」那三行）。Info 分頁現在只剩 `Drawing No.`/`Rev`/`Title1~3` 五個欄位加 `Read CE`/`Apply` 兩顆按鈕，沒有任何說明文字。

### 待實機驗證

1. `Batch` 分頁的兩個 `option`（`Order by (1st)`/`(2nd)`）能不能正確顯示、切換、內定值對不對
2. 找一批分佈在多個樓層、同樓層內東西向也分散的無圖號 box，1st 選 U、2nd 選 E，跑出來的順序是不是「先分樓層、樓層內再左到右」
3. Prefix/Start at/Digits 的內定值（`DWGNO-`/1/3）開表單時有沒有正確帶出來

### 調整：`Start at` 和 `Digits` 合併、`Prefix`/`Start at` 同一行、`Order by (2nd)` 加 `(none)`（2026-08-19，**尚未實機驗證**）

使用者三點：

1. `Start at`/`Digits` 合併成一個欄位——輸入 `001` 就同時表示起始值 1、補零到 3 位
2. `Prefix`/`Start at` 放同一行
3. `Order by (2nd)` 要有 `(none)` 選項

### `Start at` 合併

**型別改成 STRING**（原本是 REAL）——這是關鍵，REAL 欄位打 `001` 存進去只會剩 `1`，前面的零會被吃掉，沒辦法拿字元數當補零位數。改成 STRING 之後直接讀使用者打了幾個字元：

```pml
!startstr = !this.batchstart.val
!start = !startstr.real()
!digits = !startstr.length()
```

打 `001` → 起始值 1、補零 3 位。打 `1` → 起始值 1、不補零（長度 1，`.BatchName()` 判斷 `!digits.gt(0)` 且需要的位數已經夠，不會再加零）。`.batchdigits` 欄位整個拿掉，`.BatchName()` 本身不用改，一樣是「prefix + 補零字串」，只是 `!digits` 現在從 `Start at` 自己的字元數推算，不再是另一個獨立欄位。

內定值從原本的 `1`/`3` 改成一個 `.batchstart.val = '001'`，效果跟原本一樣（起始 1、補 3 位），但現在只用一個欄位表達。

### `Prefix`/`Start at` 同一行

拿掉原本的直排，`Start at` 改成 `at xmax.batchprefix+1 ymin.batchprefix`，跟 `Prefix` 並排。

### `Order by (2nd)` 的 `(none)`

清單開頭加一個 `(none)` 選項（內定 2nd 還是 `West -> East (E)`，只是清單裡多了這個選擇，索引位置跟著往後移一位）。選了 `(none)` 時設 `!use2 = false`，排序比較器裡「軸 1 打平才比軸 2」那個分支多加一個條件 `and !use2`——`(none)` 的時候永遠不會比對軸 2，打平的 box 就維持掃描到的順序，不會被沒有意義的第二軸硬排。

### 待實機驗證

1. `Start at` 打 `001`，跑出來的圖號是不是 `DWGNO-001`、`DWGNO-002`……而不是 `DWGNO-1`、`DWGNO-2`
2. `Start at` 只打 `1`（不含前導零），確認不補零
3. `Order by (2nd)` 選 `(none)`，同一 U 高程的 box 順序是不是保持原樣（不會被硬用某個軸排序）

### 實機驗證結果：Batch 分頁確認 OK；Split 撿到 box 外的點會整批擋下（2026-08-19，已修，待再驗）

`Batch` 分頁使用者確認可以了。

接著回報 `Split`：切一個 box 時，參考點選在一個高程落在 box 外的彎頭上，畫面顯示 X/Y/Z 都勾了，錯誤訊息 `The picked point is too close to the Z ends of the box (or outside it)`——整個 Split 被擋下，即使 X、Y 那兩軸的投影其實是在 box 範圍內的。

使用者說明：切圖時常常會拿 box 外的東西（例如彎頭）當參考點對齊,不是每次都要點在 box 裡面。

### 原因

`.DoSplitAt()` 原本的邏輯是「勾選的軸只要有一個驗證失敗（太靠邊或在範圍外）就整批中止」。這對「參考點剛好只有某一軸落在 box 外」的情況太嚴格——使用者其實只是想用那個點對齊 X/Y，Z 有沒有落在 box 內根本不重要。

### 作法

改成**單軸失敗不再中止整個操作，只是那一軸不切**，等同於使用者根本沒勾選那一軸。只有「勾選的軸全部都失敗」才真正擋下（這種情況代表整個點都用不上，沒東西可切）。

具體改法：把原本「驗證失敗就 `!!alert.error()` + `return`」，改成把失敗的軸記進 `!skipped` 陣列、對應的 `!usex`/`!usey`/`!usez` 維持 `false`；後面建立分割片段那三段（原本用 `!this.splitx.val` 判斷要不要切那一軸）改成用 `!usex`/`!usey`/`!usez`。切完之後 `Result` 文字會附註哪些軸被跳過，例如 `2 box(es) created (Z skipped - point too close/outside)`，讓使用者知道實際上只切了哪幾軸，不是靜默發生。

**「太靠邊（1mm 內）」和「完全在範圍外」這次用同一套處理**——都算那一軸不能用，跳過就好，不特別區分兩種情況分別報錯或跳過，行為比較一致好預期。

### 待實機驗證

1. 同樣的場景（Z 落在 box 外，X/Y 在範圍內）再切一次，確認只切 X/Y 兩軸，Z 不受影響
2. `Result` 文字有沒有正確顯示被跳過的軸
3. 三個勾選軸全部都失敗的情況，確認會正確跳出「沒東西可切」的錯誤，不會建立奇怪的 box
