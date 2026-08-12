# DrawingPlan1 開發筆記

> 本檔案記錄與 Claude 討論的進度，供下次繼續。目錄結構、程式細節請以實際程式碼為準（此檔可能與程式不同步）。

## 目前狀態（2026-07-23）

使用者發現 `d:\E3D\pdms_prog\E3D2.1\PA_pmllibE3D2.1` 這個目錄不是最新版本，**要先更新程式**，之後再回來繼續下面的討論。

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
