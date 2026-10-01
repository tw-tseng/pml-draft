# NWD → 平面圖 DXF

廠商的設備、鋼構只有 NWD 時，把它轉成平面圖的背景線（只有外形、不標註）。
跟 E3D 的 PML 程式無關：這裡只有 Python 和批次檔，`pml rehash` 不會收它們。

需要：Python 3，加上 `numpy`、`shapely`、`ezdxf`、`Pillow`。

## 步驟

1. **Navisworks 匯出 FBX**：輸出 → FBX，要 ASCII 格式（二進位格式程式會直接告訴你）。
   要 Manage／Simulate 才能匯出，Freedom 不行。
2. **建快取**（一個 FBX 只要做一次）：把 FBX 拖到 `nwdcache.bat`。
   旁邊會出現 `<檔名>.cache` 資料夾。3.7 GB 的 FBX 約 2 分鐘。
3. **出平面圖**：把 `.cache` 資料夾拖到 `nwdplan.bat`，依序輸入：
   - 範圍 `X1 Y1 X2 Y2`，直接按 Enter＝整個模型
   - 切的高程 Z（這個高程以上拿掉），Enter＝不切
   - 底部高程 Z（這個高程以下拿掉），Enter＝不限
   - 圖名

   結果在 `plans/`：DXF 和同名的 PNG 預覽。視窗一開始會印出模型的範圍與高程範圍。

座標、高程都是 **Navisworks 的座標**（mm），不是 E3D 的。
放進 AutoCAD 時插入點 `0,0`、比例 1。

## DXF 圖層

- 每個來源檔一個圖層（`XMRV_GEN`、`XMRV-SB_SUPPORT`……）
- `*_SPACE`：維修空間（名稱含 MSPA），藍色虛線外框，不遮東西
- `*_CL`：中心線，不受高程裁切
- `AREA_FRAME`：出圖範圍的外框
- `*_HIDDEN`：被擋住的線，加 `--hidden` 才有，預設關閉

## 自動排除

- **螺栓**：靠名稱認（`_M10_P`、`_M12_T` 這類螺栓組，`U...JIS(15A)` 這類 U 型螺栓）。
  日文在匯出時已經變亂碼，只剩英數字部分可以認。`--keep-bolts` 保留。
- **小於 50mm 的物件**：`--min-size` 可改。名稱含 `PIP` 的圖層不套用——
  小管徑管線的管件都很短，套了會讓管線斷成一截一截。

## 其他指令（命令列）

```
python nwdplan.py <cache> info                      模型範圍、圖層
python nwdplan.py <cache> plan --rect X1 Y1 X2 Y2 --cut Z --bottom Z --name 名稱
python nwdplan.py <cache> align pairs.txt           NWD 與 E3D 座標對齊（2 點以上）
python nwdplan.py <cache> probe X Y Z               某一點附近有哪些物件
```

`pairs.txt` 一行一組共同點：`NWD-X NWD-Y NWD-Z  E3D-E E3D-N E3D-U  名稱`（W、S 為負）。
`plan` 加 `--align pairs.txt` 之後，範圍、高程、DXF 都改用 E3D 座標。
這部分還沒有用真的 E3D 模型測過。

## 已知的事

- Navisworks 把 FBX 讀回來時模型是躺著的：FBX 檔頭宣告 X 軸朝上，但資料其實是 Z 軸朝上。
  程式不看檔頭，出圖方位跟 NWD 的俯視一致。
- AutoCAD 沒有 FBX 匯入；Blender 讀不了 ASCII FBX，所以才自己寫讀檔。
