#!/usr/bin/env python3
"""
find_label_space_optimized_no_cardinal_break_leaders.py
- 與你原本版本差異：
  - 當引線與其他標籤(geometry)或既有引線相交時，將引線在交點處分段（break）
  - 只畫出位於障礙物外的段；所有段都寫入 blankpos2.dxf
  - 新增 break_leader_at_intersections() 與輔助函式
  - 保持原有找空白、避開 0/90/180/270 度、phase1/phase2 流程
"""

import os
import sys
import math
import ezdxf
from ezdxf import bbox as ezdxf_bbox
import re
from shapely.geometry import box, LineString, Point, Polygon, GeometryCollection, MultiPoint
from shapely.affinity import rotate
from rtree import index

# === 使用者設定 ===
# 資料夾由 PML 用命令列參數傳進來 —— 路徑的決定權只留在 PML 一個地方,
# 換位置不必重編 exe。PML 傳的是 !!evar('AVEVA_DESIGN_USER')(E3D 自己的
# 可寫使用者資料區),而且已經把結尾的反斜線去掉 —— Windows 的 argv 解析會
# 把引號前的反斜線當成跳脫,連引號一起吃掉。
#
# 沒給參數才退回自行推導,方便本機直接跑 .py 或跑 dist\ 底下那顆測試:
#   exe  <資料夾>\dist\BlankPos.exe -> <資料夾>
#   .py  跟 .py 同一個資料夾
if len(sys.argv) > 1 and sys.argv[1].strip():
    BASE_DIR = os.path.abspath(sys.argv[1].strip())
elif getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(sys.executable)))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DXF_A_PATH = os.path.join(BASE_DIR, "BlankPos1.dxf")
DXF_B_PATH = os.path.join(BASE_DIR, "BlankPos2.dxf")
PARAM_TXT = os.path.join(BASE_DIR, "WriteLabelToText.txt")
OUT_FILE = os.path.join(BASE_DIR, "LabelSpace.txt")
# syscom 把 stdout 吞掉,所以要看的數字同時寫進這裡。每次執行覆蓋。
LOG_FILE = os.path.join(BASE_DIR, "BlankPos.log")

def log(msg):
    print(msg)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(msg + "\n")
    except Exception:
        pass

CHECK_REGION = box(50, 80, 660, 550)
TEXT_WIDTH_RATIO = 0.65
SAFE_GAP = 1
MAX_BLOCK_DEPTH = 3  # 炸開層數

# 搜尋參數（可調）
INITIAL_RADIUS = 5
STEP_RADIUS = 1.0
STEP_ANGLE_DEG = 5
MAX_SEARCH_RADIUS = 200.0
# 標籤轉 90 度只有在「明顯」更靠近錨點時才划算。轉向候選的距離要先加這個
# 罰分再跟直立的比,不然省個 0.3mm 也會轉,整張圖看起來東倒西歪。單位 mm。
ROT_PENALTY = 3.0
# 框不准蓋到自己的錨點,而且錨點要離框緣至少這麼遠(mm)。那排閥件、儀表在
# view 裡沒有圖形,錨點四周全空,r=0 那圈就直接把框壓在錨點上;PML 的引線是
# 從錨點拉到框緣最近點,錨點在框裡就變成從文字中間穿出來,看起來像沒標。
# 錨點在管線上的(管支撐)本來就被管線擋開,不受這條影響。
ANCHOR_CLEAR = 2.0
# matchline 圍出來的矩形內優先。理由是 box 外是尺寸線的地盤,引線拉出去容易
# 打架。這是個代理指標 —— 現在 is_soft_dim_line 已經能認出尺寸線了,但引線
# 有沒有撞到尺寸線還是沒有直接檢查,所以「待在 box 內」仍然是主要手段。
# 矩形由 PML 用第二個命令列參數傳進來:"xmin ymin xmax ymax"。沒傳就是不分內外。
INSIDE_REGION = None
if len(sys.argv) > 2 and sys.argv[2].strip():
    try:
        _x1, _y1, _x2, _y2 = (float(v) for v in sys.argv[2].replace(",", " ").split())
        INSIDE_REGION = box(min(_x1, _x2), min(_y1, _y2), max(_x1, _x2), max(_y1, _y2))
    except Exception:
        INSIDE_REGION = None
# 「優先待在 box 內」要付出的引線長度上限(mm)。None = 不設限,也就是
# 只要 box 內找得到就一定用,不管拉多遠。看到標籤被拉進圖面深處再調這個。
INSIDE_MAX_RADIUS = None
# 近處先找(2026-10-01):半徑 NEAR_RADIUS 以內,box 內與 box 外那一圈一起比,
# 都找不到才照舊往遠處找。原本 box 內會一路找到 MAX_SEARCH_RADIUS,只要 box 內
# 200mm 以內有位子就絕不考慮 box 外 —— 實測一個管嘴標籤因此被拉到 120mm 外,
# box 外 14mm 明明有空位(使用者,2026-10-01:開放 box 外的空間)。
#   OUTSIDE_BAND    box 外只准放在 box 邊往外這麼寬的一圈裡(到尺寸線為止,
#                   尺寸線大約在 box 外 15～18mm),而且要整個在 box 外,
#                   不准騎在 match line 上
#   OUTSIDE_PENALTY box 外的位置要比 box 內近這麼多才用:引線要穿過 match
#                   line,只省一點點不划算(實測一個 19mm 的換成 18mm 的)
# 沒有 INSIDE_REGION(PML 沒傳矩形)時不分內外,行為跟以前一樣。
NEAR_RADIUS = 25.0
OUTSIDE_BAND = 15.0
OUTSIDE_PENALTY = 5.0
# box 外的標籤,引線不准穿過任何文字:box 邊上就是 MATCH LINE 字,一條從 box 內
# 拉出來的引線很容易整條穿過它(2026-10-01 重播實測)。文字外框由 main() 收進來
LEADER_TEXT_SHAPES = []
LEADER_TEXT_TREE = None

def leader_hits_text(leader):
    if LEADER_TEXT_TREE is None:
        return False
    for i in LEADER_TEXT_TREE.query(leader):
        if LEADER_TEXT_SHAPES[int(i)].intersects(leader):
            return True
    return False
# 尺寸線是「軟障礙」:壓上去之後 PML 會用 GAP 把線斷開,所以可以用,只是不
# 白用 —— 每個斷口都是尺寸線上的一個洞。給一個小罰分,讓搜尋優先找真正的
# 空白,找不到才用尺寸線的地盤,而不是遠遠跑掉。罰分別給大,不然 _search()
# 的提早收手會失效(它找到之後最多再多掃「罰分」那麼多 mm)。
DIM_PENALTY = 6.0
# 哪些線算軟障礙,是 **PML 指定的**,不是這邊猜的。PML 在 WriteLabelToText.txt
# 裡多寫幾筆
#     dimline <dir> <x1> <y1> <x2> <y2>
# <dir> 是 up/down/left/right,也就是那條線屬於哪一條 ateLINE_<dir> 的 LDIM。
# 只有落在這些線段上的 DXF LINE 才是軟的。
#
# 為什麼一定要 PML 指定:GAP 必須打在某個元素上,PML 拿到座標還是得知道「這條
# 線是誰的」才斷得開。所以「哪些線可以壓」和「壓了誰去斷」本來就是同一份名單
# —— 由 PML 出這份名單,兩件事就一致了,而且使用者自己畫的線、callout 天生不
# 在名單裡,自動維持硬障礙。
#
# 試過而不可行的判準,別再走:
#  * VLAYER/VLAYRF —— 對 SLAB 有效,對 LDIM 只匯出一個空的 _U block 佔位符帶
#    著圖層名,真正的線還是留在圖層 0(2026-09-10 使用者實測);groupDims 開了
#    也沒把線收進 block。
#  * 「modelspace 頂層、不在 block 裡的 LINE」—— DRAFT 確實只把 LDIM 攤平,
#    其餘都包在 block 裡(管線 VIEW1_DES、引線和標籤 LABELn、圖框 PICT_OWNER、
#    疊圖 OLAY1),但使用者手畫的線和 callout 一樣是頂層,會被誤判成軟障礙,
#    然後標籤壓上去卻沒有人去斷它(使用者指出,2026-09-10)。
#
# 只有線是軟的,文字不是 —— 尺寸數字和 MATCH LINE 文字都是 MTEXT,GAP 斷得了
# 線斷不了字,標籤壓到字就是壓壞了。
#
# 這個旗標跟 PML 兩端(DrawingPlan1DimLines 寫 dimline、DrawingPlan1MatchGaps
# 事後補 GAP)是一組的,2026-09-11 一起上線。單獨關掉沒事(退回全硬障礙);
# 單獨打開而 PML 那兩段不在,標籤就會壓在沒人斷開的線上 —— dc8a732 修掉的毛病
# 換成標籤又長回來。
DIM_SOFT_LOOSE_LINES = True
# 怎麼算「落在線段上」:深度(水平線的 y、垂直線的 x)要在 DIM_MATCH_TOL 內,
# 沿線方向則是 DXF 這條線**至少 DIM_OVERLAP_FRAC 的長度**落在 PML 報的範圍裡。
#
# 不用「包含」:投影線在 DXF 裡會超出尺寸線 2mm(2026-09-11 用 dxftest.dxf 量
# 到 2.007,製圖慣例的延伸段),PML 報的線段停在尺寸線上,包含測試就在遠端差
# 2mm 全數落空 —— 第一次正式跑 37 條一條都沒認領。用重疊比例就不必知道 E3D
# 的延伸長度是多少,PLCLTX 把近端縮短、既有 GAP 把線斷成幾截也都還是認得。
# 同一深度上的其他線(matchline 外框、對面那條鏈的投影線)跟這段的重疊是 0,
# 照樣排除。單位 mm。
DIM_MATCH_TOL = 0.5
DIM_OVERLAP_FRAC = 0.5
DIM_MIN_OVERLAP = 1.0
# 放置順序:面積大的先放,同面積維持參數檔(建立)順序。
#
# 標籤是照順序一個一個貪婪放的,檔案順序就是 PML 建立的順序,跟難不難放無關
# —— 一個 9x3.5 的閥件標籤隨手佔掉錨點旁邊 6mm 的位子,後面 37mm 長的支撐堆
# 疊組唯一放得下的那塊就沒了,只好抬高 9mm 放到另一側(2026-09-11 重播
# /165729 看到的)。大的先挑:它能放的位置本來就少,小標籤到哪都行。
#
# 2026-09-11 曾經只讓堆疊組先放:全部依面積排時儀表圈圈(100mm²)跑到閥件標籤
# (32mm²)前面,那排閥件/儀表在 view 裡沒有圖形,誰先放誰就坐在錨點上沒引線。
# 那其實是 ANCHOR_CLEAR 該管的事 —— 框不准蓋到自己的錨點之後,再拿同一份重播
# 比,依面積排反而最好:圈圈全帶 2mm 引線、閥件標籤 4~10mm、支撐一個都沒動;
# 只讓堆疊組先放的話,閥件標籤分成上下兩排卡住,一個圈圈被推到 23mm 外。
PLACE_BIG_FIRST = True
# pinned 標籤(2026-09-16,Notion 進版 toggle 第十三節):更新路徑送來的、已經
# 凍在紙上(OSET FALSE)的既有標籤。記錄多帶目前的位置:
#     <ref> <錨點x> <錨點y> <寬> <高> <type> pinned <目前中心x> <目前中心y> <rot>
# 寬高是直立時的(跟建立時同一套公式),rot 0/270 說它現在有沒有側躺。
#
# 規則是「只動被撞到的那幾顆」:框本體(不含 SAFE_GAP)跟 DXF 硬障礙真的相交
# 才算撞到,才解除 pin 重放;其餘原座標輸出、第 10 欄 kept,PML 一個屬性都不碰。
# 不整張重排 —— 這裡是貪婪、大的先放,障礙變一點就連鎖改掉一堆不相干標籤的
# 落點,進版比對會滿圖的雲,第十二節的凍結就白做了。
#
# 更新路徑的 DXF 是在標籤已經存在時匯的,所以每顆 pinned 自己的 LABELn block
# 要從障礙裡拿掉,不然它會撞到自己。判準見 excluded_label_blocks()。
PINNED_TOL = 0.5          # 錨點對 LABEL block 插入點的容差(mm)
PINNED_INSIDE_PAD = 0.5   # 「整顆 block 都在 pinned 框裡」的外推(mm),堆疊組下面幾行用
# 重放被撞到的標籤時,分數多加「離舊位置的距離」乘這個權重:錨點近、跳得少
# 兩者一起比。0 就是照新標籤的方式只看錨點。這一項 >= 0,_search() 的提早收手
# 仍然成立(score >= radius),只是找到之後會多掃到 radius > score 才停。
OLD_POS_WEIGHT = 1.0

def _place_key(ln):
    """排序鍵:標籤面積(越大越前);配合 stable sort 讓同面積維持原順序。"""
    p = ln.replace(",", " ").split()
    try:
        if len(p) >= 6:
            return float(p[3]) * float(p[4])
    except Exception:
        pass
    return 0.0

def parse_record(ln):
    """一筆標籤記錄 -> dict,格式不對回 None。

    普通:  <ref> <ax> <ay> <w> <h> <type>
    pinned: <ref> <ax> <ay> <w> <h> <type> pinned <cx> <cy> <rot>
    舊 PML 只送前 6 欄,多出來的欄位以前是被忽略的,現在只認 'pinned' 這個字。"""
    parts = ln.replace(",", " ").split()
    if len(parts) < 6:
        return None
    try:
        rec = {
            "ref": parts[0].lstrip(chr(0xFEFF)),   # 保險:ref 絕不能帶 BOM,PML 會拿它當路徑
            "ax": float(parts[1]), "ay": float(parts[2]),
            "w": float(parts[3]), "h": float(parts[4]),
            "type": parts[5].lower(),
            "pinned": False, "cx": None, "cy": None, "rot": 0,
            "line": ln,
        }
    except Exception:
        return None
    if len(parts) >= 10 and parts[6].lower() == "pinned":
        try:
            rec["cx"] = float(parts[7]); rec["cy"] = float(parts[8])
            rec["rot"] = 270 if float(parts[9]) > 45 else 0
            rec["pinned"] = True
        except Exception:
            pass
    return rec

def pinned_box(rec, gap=0.0):
    """pinned 標籤現在佔的框。側躺的寬高對調,跟輸出第 6/7 欄的慣例一樣。"""
    if rec["rot"]:
        cw, ch = rec["h"], rec["w"]
    else:
        cw, ch = rec["w"], rec["h"]
    return candidate_geom(rec["cx"], rec["cy"], cw, ch, rec["type"], gap=gap), cw, ch

def pinned_leader(rec, geom):
    """kept 標籤的引線:錨點到框緣最近點,給後面放的標籤當既有引線避開。"""
    a = Point(rec["ax"], rec["ay"])
    try:
        ring = geom.exterior
        p = ring.interpolate(ring.project(a))
        return LineString([(a.x, a.y), (p.x, p.y)])
    except Exception:
        return LineString([(a.x, a.y), (rec["cx"], rec["cy"])])

def excluded_label_blocks(msp, pinned_recs):
    """更新路徑的 DXF 裡,哪些 LABEL* block 是 pinned 標籤自己的,要從障礙裡拿掉。

    兩條判準,中一條就排除:
      1. 頂層 INSERT 的插入點落在任一 pinned 錨點 PINNED_TOL 內 —— DXFOUT 的
         LABELn block 插入點就是引線起點(設計點),Notion 進版 toggle 第十二節
         第 3 點實測確認過。
      2. 整顆 block 的幾何都落在某個 pinned 框外推 PINNED_INSIDE_PAD 內 —— 給堆疊
         組下面幾行保險用:那些 SLAB 是 Lleader false,插入點不一定在設計點,
         但字一定在頂端那顆申報的框裡。
    回傳 (排除的 block 名稱集合, 依規則 1 排除的數量, 依規則 2 排除的數量)。
    LABELn 每顆標籤一個 block 定義、只插一次,所以用名字排除就夠。"""
    if not pinned_recs:
        return set(), 0, 0
    anchors = [(r["ax"], r["ay"]) for r in pinned_recs]
    boxes = [pinned_box(r, gap=PINNED_INSIDE_PAD)[0] for r in pinned_recs]
    excluded = set()
    n_by_anchor = 0
    n_by_inside = 0
    for e in msp:
        if e.dxftype() != "INSERT":
            continue
        name = e.dxf.name
        if not name.upper().startswith("LABEL"):
            continue
        try:
            ix, iy = f(e.dxf.insert[0]), f(e.dxf.insert[1])
        except Exception:
            continue
        if any(abs(ix - ax) <= PINNED_TOL and abs(iy - ay) <= PINNED_TOL for ax, ay in anchors):
            if name not in excluded:
                excluded.add(name)
                n_by_anchor += 1
            continue
        # 規則 2:把這顆 block 炸開,所有幾何都在同一個 pinned 框裡才算
        geoms = []
        try:
            for ve, _blk in explode_all([e]):
                for g, _m in entity_to_shape_with_meta(ve):
                    if g is not None:
                        geoms.append(g)
        except Exception:
            geoms = []
        if not geoms:
            continue
        for b in boxes:
            try:
                if all(b.contains(g) for g in geoms):
                    if name not in excluded:
                        excluded.add(name)
                        n_by_inside += 1
                    break
            except Exception:
                continue
    return excluded, n_by_anchor, n_by_inside

# === Helpers ===
def f(v, default=0.0):
    try:
        return float(v)
    except Exception:
        return default

def parse_dim_segments(lines):
    """把參數檔裡的 'dimline <dir> <x1> <y1> <x2> <y2>' 和 'cloud <n>' 挑出來。
    回傳 ([(dir, x1, y1, x2, y2), ...], [n, ...], [(x, y), ...], 剩下的標籤記錄)。

    cloud <n>(2026-09-17):更新路徑的 sheet 上掛著上一版的進版雲線,DXFOUT 把
    每朵雲寫成 layer 0 的頂層 POLYLINE、頂點數剛好等於 OUTL 的 VRTX 數,版次三角
    形是 3 個頂點的封閉 POLYLINE、版次號碼 MTEXT 在裡面。它們不是圖面內容,
    不能當障礙 —— 不然標籤被雲線壓到就「撞到」、搬走、下一版在新位置又被雲、
    再下一版又撞(使用者 1->2 實測)。PML 讀不到 VRTX 的座標,但數得出來幾個,
    這裡就靠頂點數認:見 excluded_cloud_entities()。"""
    segs = []
    clouds = []
    cloud_texts = []
    rest = []
    for ln in lines:
        parts = ln.replace(",", " ").split()
        if parts and parts[0].lower() == "dimline":
            if len(parts) >= 6:
                try:
                    segs.append((parts[1].lower(), float(parts[2]), float(parts[3]),
                                 float(parts[4]), float(parts[5])))
                except Exception:
                    pass
            continue
        if parts and parts[0].lower() == "cloud":
            if len(parts) >= 2:
                try:
                    clouds.append(int(float(parts[1])))
                except Exception:
                    pass
            continue
        if parts and parts[0].lower() == "cloudtext":
            # 版次號碼 TEXP 的 origin:3 點的頂層 POLYLINE 只有裡面有這種點才是
            # 版次三角形 —— matchline 文字的箭頭(DrawingPlan1MatchArrow)也是
            # 3 點封閉外框,那個要留著當障礙
            if len(parts) >= 3:
                try:
                    cloud_texts.append((float(parts[1]), float(parts[2])))
                except Exception:
                    pass
            continue
        rest.append(ln)
    return segs, clouds, cloud_texts, rest

def excluded_cloud_entities(msp, cloud_counts, cloud_texts=()):
    """頂層 POLYLINE 裡哪些是進版雲線 / 版次三角形,以及三角形裡的版次號碼文字。
    回傳要排除的實體 id 集合。每個申報的頂點數只認領一條(多重集合),
    認領順序照 modelspace 順序。3 點的只有外框內有申報的 cloudtext 點才算
    三角形(PML 沒送 cloudtext 的舊版就照頂點數認);三角形認領後,插入點落在
    它外框內的頂層 TEXT/MTEXT 一起排除 —— 那是版次號碼。"""
    if not cloud_counts:
        return set()
    pool = list(cloud_counts)
    excluded = set()
    tri_boxes = []
    for e in msp:
        if e.dxftype() not in ("LWPOLYLINE", "POLYLINE"):
            continue
        pts = polyline_get_points(e)
        n = len(pts)
        # DXFOUT 寫的是剛好 n 個頂點;保險起見也認 n+1(首尾重複收尾的寫法)
        hit = None
        for cand in (n, n - 1):
            if cand in pool:
                hit = cand
                break
        if hit is None:
            continue
        bb = None
        if pts:
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            bb = (min(xs) - 0.5, min(ys) - 0.5, max(xs) + 0.5, max(ys) + 0.5)
        if hit == 3 and cloud_texts:
            if bb is None or not any(bb[0] <= tx <= bb[2] and bb[1] <= ty <= bb[3] for tx, ty in cloud_texts):
                continue                      # 3 點但沒有版次號碼在裡面:箭頭之類,不是三角形
        pool.remove(hit)
        excluded.add(id(e))
        if hit == 3 and bb is not None:
            tri_boxes.append(bb)
    if tri_boxes:
        for e in msp:
            if e.dxftype() not in ("TEXT", "MTEXT"):
                continue
            try:
                x, y = f(e.dxf.insert[0]), f(e.dxf.insert[1])
            except Exception:
                continue
            for x1, y1, x2, y2 in tri_boxes:
                if x1 <= x <= x2 and y1 <= y <= y2:
                    excluded.add(id(e))
                    break
    return excluded

def is_soft_dim_line(e, dim_segments):
    """這條 DXF LINE 是不是 PML 報上來、它有辦法 GAP 斷開的線。
    見 DIM_SOFT_LOOSE_LINES 的說明 —— 判準是 PML 給的名單,不是幾何猜測。"""
    if not DIM_SOFT_LOOSE_LINES or not dim_segments:
        return False
    if e.dxftype() != "LINE":
        return False
    try:
        s, t = e.dxf.start, e.dxf.end
    except Exception:
        return False
    tol = DIM_MATCH_TOL
    for _dir, x1, y1, x2, y2 in dim_segments:
        if abs(y1 - y2) <= tol:                      # PML 報的是水平線
            depth = (y1 + y2) * 0.5
            if abs(s.y - depth) > tol or abs(t.y - depth) > tol:
                continue
            lo, hi = min(x1, x2), max(x1, x2)
            a, b = min(s.x, t.x), max(s.x, t.x)
        elif abs(x1 - x2) <= tol:                    # 垂直線
            depth = (x1 + x2) * 0.5
            if abs(s.x - depth) > tol or abs(t.x - depth) > tol:
                continue
            lo, hi = min(y1, y2), max(y1, y2)
            a, b = min(s.y, t.y), max(s.y, t.y)
        else:
            continue
        overlap = min(hi, b) - max(lo, a)
        length = b - a
        if overlap >= DIM_MIN_OVERLAP and overlap >= DIM_OVERLAP_FRAC * length:
            return True
    return False

# --- TEXT bbox / MTEXT拆行 ---
def build_text_bbox(e):
    insert = e.dxf.insert
    x, y = f(insert[0]), f(insert[1])
    h = f(e.dxf.get("height", 3.0), 3.0)
    txt = (e.dxf.get("text", "") or "").rstrip()
    rot = 0.0
    try:
        rot = float(e.get_rotation())
    except Exception:
        try:
            rot = f(getattr(e, "rotation", 0.0))
        except Exception:
            rot = 0.0
    halign = e.dxf.get("halign", 0)
    w = len(txt) * h * 0.6
    if halign == 1:
        x -= w / 2
    elif halign == 2:
        x -= w
    rect = box(x, y, x + w, y + h)
    if rot:
        rect = rotate(rect, rot, origin=(f(insert[0]), f(insert[1])), use_radians=False)
    return rect, txt

def build_line_geom(e):
    try:
        sx, sy = f(e.dxf.start[0]), f(e.dxf.start[1])
        ex, ey = f(e.dxf.end[0]), f(e.dxf.end[1])
        if abs(sx - ex) < 1e-9 and abs(sy - ey) < 1e-9:
            eps = 1e-3
            return LineString([(sx, sy), (sx + eps, sy + eps)])
        return LineString([(sx, sy), (ex, ey)])
    except Exception:
        return None

def polyline_get_points(e):
    pts = []
    try:
        if hasattr(e, "get_points"):
            for p in e.get_points():
                if isinstance(p, (tuple, list)) and len(p) >= 2:
                    pts.append((f(p[0]), f(p[1])))
        elif hasattr(e, "vertices"):
            for v in e.vertices:
                loc = getattr(v.dxf, "location", None) or getattr(v.dxf, "point", None)
                if loc:
                    pts.append((f(loc[0]), f(loc[1])))
    except Exception:
        pass
    return pts

def polyline_is_bulged(e):
    # DXFOUT draws a circle as a 2-vertex, bulge=1 CLOSED polyline (two
    # semicircle bulges), not two straight lines to the far point --
    # reading only (x, y) turns the whole circle into a straight chord
    # across its diameter, and any curved symbol outline suffers the
    # same flattening (see memory dxfout-circles-are-bulged-polylines)
    try:
        if hasattr(e, "get_points"):
            return any(len(pt) > 4 and pt[4] for pt in e.get_points())
        if hasattr(e, "vertices"):
            return any(getattr(v.dxf, "bulge", 0) for v in e.vertices)
    except Exception:
        pass
    return False


def polyline_is_closed(e):
    try:
        if hasattr(e, "closed"):
            return bool(e.closed)
        if hasattr(e, "is_closed"):
            return bool(e.is_closed)
        return bool(int(e.dxf.get("flags", 0)) & 1)
    except Exception:
        return False


def build_bulged_polyline_geom(e):
    # walk the exploded LINE/ARC pieces instead of the raw vertices, and
    # sample each ARC into a short run of points so the curve is actually
    # curved. a closed outline becomes a filled Polygon -- the same way
    # build_circle_bbox already fills a true CIRCLE entity -- so a label
    # dropped entirely inside a round symbol (not just crossing its rim)
    # still reads as a collision, not just when it grazes the boundary
    pts = []
    try:
        for ve in e.virtual_entities():
            t = ve.dxftype()
            if t == "LINE":
                p1, p2 = ve.dxf.start, ve.dxf.end
                if not pts:
                    pts.append((f(p1[0]), f(p1[1])))
                pts.append((f(p2[0]), f(p2[1])))
            elif t == "ARC":
                c = ve.dxf.center
                r = f(ve.dxf.radius)
                a0 = math.radians(f(ve.dxf.start_angle))
                a1 = math.radians(f(ve.dxf.end_angle))
                if a1 <= a0:
                    a1 += 2 * math.pi
                steps = max(2, int(abs(a1 - a0) / math.radians(10)) + 1)
                for k in range(steps + 1):
                    a = a0 + (a1 - a0) * k / steps
                    pt = (f(c[0]) + r * math.cos(a), f(c[1]) + r * math.sin(a))
                    if not pts or pts[-1] != pt:
                        pts.append(pt)
    except Exception:
        return None
    if len(pts) < 2:
        return None
    if polyline_is_closed(e) and len(pts) >= 3:
        try:
            poly = Polygon(pts)
            if poly.is_valid and poly.area > 0:
                return poly
        except Exception:
            pass
    return LineString(pts)


def build_lwpolyline_geom(e):
    if polyline_is_bulged(e):
        geom = build_bulged_polyline_geom(e)
        if geom is not None:
            return geom
    pts = polyline_get_points(e)
    if not pts:
        return None
    if len(pts) == 1:
        x, y = pts[0]
        eps = 1e-3
        return LineString([(x, y), (x + eps, y + eps)])
    return LineString(pts)

def build_circle_bbox(e):
    c, r = e.dxf.center, e.dxf.radius
    return Point(f(c[0]), f(c[1])).buffer(f(r))

def build_hatch_bbox(e):
    try:
        from ezdxf import bbox as _bb
        ex = _bb.extents([e], fast=True)
        if not ex.has_data:
            return None
        return box(f(ex.extmin.x), f(ex.extmin.y), f(ex.extmax.x), f(ex.extmax.y))
    except Exception:
        return None

def build_arc_bbox(e):
    c = e.dxf.center
    r = f(e.dxf.radius)
    try:
        start = math.radians(f(e.dxf.start_angle))
        end = math.radians(f(e.dxf.end_angle))
    except Exception:
        start = 0.0
        end = 0.0
    pts = [(f(c[0]) + r * math.cos(a), f(c[1]) + r * math.sin(a)) for a in [start, end, (start + end)/2]]
    xs, ys = zip(*pts)
    return box(min(xs), min(ys), max(xs), max(ys))

def explode_mtext_manual(e):
    insert = e.dxf.insert
    x0, y0 = f(insert[0]), f(insert[1])
    char_h = float(e.dxf.get("char_height", 3.0) or 3.0)
    width = float(e.dxf.get("width", 0.0) or 0.0)
    attach = int(e.dxf.get("attachment_point", 1) or 1)
    rotation = 0.0
    try:
        rotation = float(e.get_rotation())
    except Exception:
        rotation = f(getattr(e, "rotation", 0.0))
    text_raw = ""
    try:
        text_raw = e.plain_text() if hasattr(e, "plain_text") else (e.text or "")
    except Exception:
        text_raw = (e.text or "")
    text_clean = text_raw.replace("\\~", " ").rstrip()
    lines = re.split(r"\\P|\r\n|\r|\n", text_clean) if text_clean else []
    n = len(lines)
    if n == 0:
        return []
    if width <= 0:
        max_len = max((len(s) for s in lines), default=1)
        width = max_len * char_h * TEXT_WIDTH_RATIO
    total_h = n * char_h
    if attach in (1, 4, 7):
        first_line = lines[0] if lines else ""
        leading_spaces = len(first_line) - len(first_line.lstrip(" "))
        base_x = x0 + leading_spaces * char_h * TEXT_WIDTH_RATIO
    elif attach in (2, 5, 8):
        base_x = x0 - width / 2
    else:
        base_x = x0 - width
    if attach in (7, 8, 9):
        base_y = y0
    elif attach in (4, 5, 6):
        base_y = y0 - total_h / 2
    else:
        base_y = y0 - total_h
    shapes = []
    for i, line in enumerate(lines):
        line = line.rstrip()
        y_line = base_y + (n - i - 1) * char_h
        leading_spaces = len(line) - len(line.lstrip(" "))
        w_line = len(line) * char_h * TEXT_WIDTH_RATIO
        if attach in (1, 4, 7):
            w_line -= leading_spaces * char_h * TEXT_WIDTH_RATIO
        if w_line < 0:
            w_line = 0.0
        rect = box(base_x, y_line, base_x + w_line, y_line + char_h)
        if rotation:
            rect = rotate(rect, rotation, origin=(x0, y0), use_radians=False)
        meta = {"type": "MTEXT_LINE", "block": None, "text_line": line, "rotation": rotation, "line_index": i + 1}
        shapes.append((rect, meta))
    return shapes

def entity_to_shape_with_meta(e, block_name=None):
    t = e.dxftype()
    try:
        if t == "LINE":
            geom = build_line_geom(e)
            if geom is None:
                return []
            return [(geom, {"type": "LINE", "block": block_name})]
        if t in ("LWPOLYLINE", "POLYLINE"):
            geom = build_lwpolyline_geom(e)
            if geom is None:
                return []
            return [(geom, {"type": "POLYLINE", "block": block_name})]
        if t == "CIRCLE":
            return [(build_circle_bbox(e), {"type": "CIRCLE", "block": block_name})]
        if t == "ARC":
            return [(build_arc_bbox(e), {"type": "ARC", "block": block_name})]
        if t == "TEXT":
            rect, txt = build_text_bbox(e)
            return [(rect, {"type": "TEXT", "block": block_name, "text": txt})]
        if t == "MTEXT":
            shapes = explode_mtext_manual(e)
            # 逐行估的寬度用 TEXT_WIDTH_RATIO 0.65,對 MATCH LINE 那種寬字型
            # 少算了 18mm(0.65 對實際約 0.9),標籤壓上去 1mm(2026-10-01)。
            # ezdxf 自己照字型算的外框也當障礙,兩者取聯集,只會更保守
            try:
                bb = ezdxf_bbox.extents([e])
                if bb.has_data and shapes:
                    shapes.append((box(bb.extmin.x, bb.extmin.y, bb.extmax.x, bb.extmax.y),
                                   {"type": "MTEXT_EXTENTS", "block": None}))
            except Exception:
                pass
            for _, meta in shapes:
                meta["block"] = block_name
            return shapes
        if t == "HATCH":
            # a boundary path is a PolylinePath (has .vertices) or an
            # EdgePath (line/arc/ellipse/spline edges, no .vertices at
            # all) -- a support/equipment symbol's fill is commonly drawn
            # this way and was entirely invisible here before: no HATCH
            # branch existed at all, so entity_to_shape_with_meta fell
            # through to the bare `return []` and the whole symbol
            # contributed zero obstacle shapes (2026-09-21, a support
            # label landed square on top of a nozzle symbol's fill).
            # ezdxf's own bbox walks every path/edge type correctly
            geom = build_hatch_bbox(e)
            if geom is None:
                return []
            return [(geom, {"type": "HATCH", "block": block_name})]
    except Exception:
        pass
    return []

def explode_all(layout, depth=0, max_depth=MAX_BLOCK_DEPTH, block_name=None):
    """產生 (entity, block_name)。block_name 是 None 代表這個實體就在
    modelspace 頂層,沒有被包在任何 block 裡 —— 尺寸線就是靠這個認出來的。
    巢狀 block 一律回報最外層那個名字。"""
    for e in layout:
        if e.dxftype() == "INSERT" and depth < max_depth:
            outer = block_name if block_name is not None else e.dxf.name
            try:
                for ve in e.virtual_entities():
                    if ve.dxftype() == "INSERT":
                        yield from explode_all([ve], depth + 1, max_depth, outer)
                    else:
                        yield ve, outer
            except Exception:
                yield e, block_name
        else:
            yield e, block_name

# === R-tree helpers ===
def build_rtree_from_shapes(shapes):
    idx = index.Index()
    for i, s in enumerate(shapes):
        try:
            idx.insert(i, s.bounds)
        except Exception:
            pass
    return idx

def rtree_query_ids(rtree_idx, shapes_list, candidate):
    try:
        return [i for i in rtree_idx.intersection(candidate.bounds) if i < len(shapes_list)]
    except Exception:
        return []

# === Candidate geometry ===
def orientations_for(w, h, shape_type):
    """要試哪些方向:(寬, 高, 給 PML 的 Adegrees)。

    只有 shape_type == "boxr" 的標籤准許側躺 —— PML 那邊只有管支撐送 boxr,
    其餘標籤照舊只試直立,免得整張圖的標註都可能轉向,搜尋也不會變兩倍慢。
    270 是直接給 PML 下 Adegrees 的值:E3D 的 Adegrees 270 = 文字由下往上讀,
    也就是 rcode=left 的圖本來就對每個標籤做的那個轉法。
    """
    if shape_type.lower() == "boxr" and abs(w - h) > 1e-9:
        return [(w, h, 0), (h, w, 270)]
    return [(w, h, 0)]

def candidate_geom(cx, cy, w, h, shape_type, gap=SAFE_GAP):
    if shape_type.lower() == "circle":
        return Point(cx, cy).buffer((w/2.0) + gap)
    else:
        return box(cx - w/2.0 - gap, cy - h/2.0 - gap, cx + w/2.0 + gap, cy + h/2.0 + gap)

# === Leader break helpers ===
def _extract_points_from_intersection(inter):
    pts = []
    if inter.is_empty:
        return pts
    # Point
    if inter.geom_type == "Point":
        pts.append((inter.x, inter.y))
    elif inter.geom_type == "MultiPoint":
        for p in inter:
            pts.append((p.x, p.y))
    elif inter.geom_type == "LineString":
        # line overlap: take endpoints
        coords = list(inter.coords)
        if coords:
            pts.append(coords[0])
            pts.append(coords[-1])
    elif inter.geom_type == "MultiLineString":
        for ls in inter:
            coords = list(ls.coords)
            if coords:
                pts.append(coords[0]); pts.append(coords[-1])
    elif inter.geom_type == "GeometryCollection":
        for g in inter:
            pts.extend(_extract_points_from_intersection(g))
    return pts

def break_leader_at_intersections(leader, existing_leaders, existing_labels):
    """
    將 leader( LineString ) 在與 existing_leaders / existing_labels 的交點處切割，
    並回傳一個 list of LineString segments，僅保留那些「位於障礙外」的段。
    """
    # collect intersection points (as coordinates)
    pts = []
    for obs in existing_labels:
        try:
            inter = leader.intersection(obs)
            pts.extend(_extract_points_from_intersection(inter))
        except Exception:
            continue
    for l in existing_leaders:
        try:
            # avoid comparing with identical geometry objects
            if l.equals(leader):
                continue
            inter = leader.intersection(l)
            pts.extend(_extract_points_from_intersection(inter))
        except Exception:
            continue

    # also include leader endpoints (start & end) to split between them
    try:
        coords = list(leader.coords)
    except Exception:
        return []
    if not coords:
        return []
    start = coords[0]; end = coords[-1]
    pts.append(start); pts.append(end)

    # project point on line to get distance along line for sorting
    # remove duplicates ~ within a small tolerance
    def param_along(p):
        # returns distance from start along leader
        return leader.project(Point(p))

    # dedupe by param (tolerance)
    unique = {}
    for p in pts:
        try:
            t = round(param_along(p), 6)  # 6 decimals tolerance
            if t not in unique:
                unique[t] = p
        except Exception:
            continue
    if not unique:
        return []

    parts = []
    sorted_items = sorted(unique.items(), key=lambda kv: kv[0])
    coords_sorted = [item[1] for item in sorted_items]

    # build segments between consecutive points
    segs = []
    for i in range(len(coords_sorted)-1):
        a = coords_sorted[i]; b = coords_sorted[i+1]
        # avoid zero-length
        if abs(a[0]-b[0]) < 1e-9 and abs(a[1]-b[1]) < 1e-9:
            continue
        seg = LineString([a, b])
        segs.append(seg)

    # keep only segments that are not inside any obstacle (i.e., midpoint not intersect obstacle)
    kept = []
    for seg in segs:
        mid = seg.interpolate(0.5, normalized=True)
        blocked = False
        for obs in existing_labels:
            try:
                if obs.contains(mid) or obs.intersects(mid):
                    blocked = True
                    break
            except Exception:
                continue
        if blocked:
            continue
        # also if segment overlaps an existing leader (collinear overlap) - treat as blocked
        for l in existing_leaders:
            try:
                if seg.crosses(l) or seg.touches(l) or seg.overlaps(l):
                    # if it merely touches at endpoint it's okay — we still allow segment unless midpoint blocked
                    # but to be safer, if overlap of length > tiny, consider blocked
                    inter = seg.intersection(l)
                    if not inter.is_empty:
                        # if intersection is a LineString with positive length, then block
                        if inter.geom_type == "LineString" and inter.length > 1e-6:
                            blocked = True
                            break
                # else ok
            except Exception:
                continue
        if blocked:
            continue
        kept.append(seg)

    return kept

# === Leader collision check (existing) ===
def leader_conflicts_with_existing(leader, existing_leaders, existing_labels):
    for lbl in existing_labels:
        try:
            if lbl.intersects(leader):
                return True
        except Exception:
            continue
    for l in existing_leaders:
        try:
            if l.crosses(leader):
                return True
        except Exception:
            continue
    return False

# === Find blank area with leader check (跳過 0,90,180,270) ===
def _scan_ring(shapes_list, soft_flags, rtree_idx, cx, cy, tries, shape_type, radius,
               existing_leaders, existing_labels, check_leader, region, old_pos=None,
               leader_text=False):
    """掃一圈:同一個半徑上,兩個方向的所有角度。回傳這一圈找到的候選。

    old_pos 只有重放被撞到的 pinned 標籤時才給:分數多加離它的距離乘
    OLD_POS_WEIGHT。None 時分數跟以前逐位元相同。"""
    found = []
    deg = 0
    while deg < 360:
        # 避開 0°,90°,180°,270°
        if deg % 90 == 0:
            deg += STEP_ANGLE_DEG
            continue
        rad = math.radians(deg)
        x = cx + radius * math.cos(rad)
        y = cy + radius * math.sin(rad)
        for (cw, ch, rot) in tries:
            # 錨點落在框裡(含 ANCHOR_CLEAR 的留白)就不用算了,見常數說明
            if shape_type.lower() == "circle":
                if radius < cw / 2.0 + ANCHOR_CLEAR:
                    continue
            elif abs(x - cx) < cw / 2.0 + ANCHOR_CLEAR and abs(y - cy) < ch / 2.0 + ANCHOR_CLEAR:
                continue
            cand = candidate_geom(x, y, cw, ch, shape_type)
            if region is not None and not region.contains(cand):
                continue
            # 硬障礙(管線等)一碰就淘汰;軟障礙(尺寸線)只記下來加罰分,
            # 因為 PML 事後會用 GAP 把壓到的尺寸線斷開
            blocked = False
            on_dim = False
            for i in rtree_query_ids(rtree_idx, shapes_list, cand):
                if not shapes_list[i].intersects(cand):
                    continue
                if soft_flags[i]:
                    on_dim = True
                else:
                    blocked = True
                    break
            if blocked:
                continue
            leader = LineString([(cx, cy), cand.centroid.coords[0]])
            if check_leader and leader_conflicts_with_existing(leader, existing_leaders, existing_labels):
                continue
            if leader_text and leader_hits_text(leader):
                continue
            # 分數用實際距離算,跟提早收手之前的版本逐位元相同 —— 這個值
            # 理論上就等於 radius,但浮點會差 1e-9 等級,而同一圈上一票候選
            # 的勝負正是由那點差異決定的。改用 radius 會讓結果換一個角度,
            # 位置一樣好但跟舊版不同,所以這裡照舊。
            score = (Point(cx, cy).distance(cand.centroid)
                     + (ROT_PENALTY if rot else 0.0)
                     + (DIM_PENALTY if on_dim else 0.0))
            if old_pos is not None:
                score += OLD_POS_WEIGHT * Point(old_pos).distance(cand.centroid)
            # 排序鍵帶 rot:同分時直立優先,結果才不會因為掃描順序而飄
            found.append((score, rot, cand, leader, cw, ch))
        deg += STEP_ANGLE_DEG
    return found


def _search(shapes_list, soft_flags, rtree_idx, cx, cy, tries, shape_type,
            existing_leaders, existing_labels, check_leader, region=None,
            max_radius=MAX_SEARCH_RADIUS, old_pos=None, leader_text=False):
    """由內往外一圈一圈掃,一旦半徑超過目前最佳分數就收手。

    這個提早收手是可以證明安全的:候選的 distance 恆等於當下的 radius,
    score = radius + 罰分 >= radius,所以半徑一旦大於目前最佳分數,
    後面任何候選都不可能更好。找到位置之後最多再多掃「罰分」那麼多 mm
    (沒有轉向候選時就是 0,也就是找到即停),而不是硬掃到 200mm。
    """
    best = None
    radius = 0.0
    while radius <= max_radius:
        # 容差是為了上面那點浮點雜訊:score 可能比 radius 小個 1e-9,
        # 沒有容差的話有機會早收一圈而漏掉真正最好的
        if best is not None and radius > best[0] + 1.0e-6:
            break
        for c in _scan_ring(shapes_list, soft_flags, rtree_idx, cx, cy, tries, shape_type,
                            radius, existing_leaders, existing_labels, check_leader, region, old_pos,
                            leader_text):
            if best is None or (c[0], c[1]) < (best[0], best[1]):
                best = c
        radius += STEP_RADIUS
    return best


def find_blank_area_with_leader(shapes_list, soft_flags, rtree_idx, cx, cy, w, h, shape_type, region,
                                existing_leaders, existing_labels, old_pos=None):
    """回傳 (候選框, 引線, 採用的寬, 採用的高, Adegrees)。

    old_pos:被撞到而重放的 pinned 標籤的舊中心,見 _scan_ring;新標籤是 None。

    四層,由嚴到寬,前一層找不到才往下:
      1. matchline 矩形內 + 引線不跟既有標籤/引線衝突
      2. matchline 矩形內 + 放寬引線
      3. 不限位置 + 引線不衝突
      4. 不限位置 + 放寬引線

    分層而不是「box 外加罰分」是有原因的:罰分一大,_search() 的提早收手就得
    一路掃到 MAX_SEARCH_RADIUS,先前那 77 倍的加速會整個吐回去。分層的話
    每一層各自收手,快的還是快。

    直立與側躺兩個方向在同一圈裡一起比,挑分數最低的那個(側躺要加 ROT_PENALTY)。
    """
    tries = orientations_for(w, h, shape_type)
    inside_max = INSIDE_MAX_RADIUS if INSIDE_MAX_RADIUS is not None else MAX_SEARCH_RADIUS

    # 近處先找,見 NEAR_RADIUS 的說明。每一邊先要引線不衝突的,找不到才放寬
    if region is not None:
        x1, y1, x2, y2 = region.bounds
        ring = box(x1 - OUTSIDE_BAND, y1 - OUTSIDE_BAND,
                   x2 + OUTSIDE_BAND, y2 + OUTSIDE_BAND).difference(region)
        near = []
        for rgn in (region, ring):
            got = None
            for check_leader in (True, False):
                got = _search(shapes_list, soft_flags, rtree_idx, cx, cy, tries, shape_type,
                              existing_leaders, existing_labels, check_leader, rgn,
                              NEAR_RADIUS, old_pos, leader_text=(rgn is ring))
                if got is not None:
                    break
            near.append(got)
        bi, bo = near
        best = bi
        if bo is not None and (bi is None or bo[0] + OUTSIDE_PENALTY < bi[0]):
            best = bo
        if best is not None:
            _score, rot, cand, leader, cw, ch = best
            return cand, leader, cw, ch, rot

    tiers = []
    if region is not None:
        tiers.append((region, True,  inside_max))
        tiers.append((region, False, inside_max))
    tiers.append((None, True,  MAX_SEARCH_RADIUS))
    tiers.append((None, False, MAX_SEARCH_RADIUS))

    for (rgn, check_leader, rmax) in tiers:
        best = _search(shapes_list, soft_flags, rtree_idx, cx, cy, tries, shape_type,
                       existing_leaders, existing_labels, check_leader, rgn, rmax, old_pos)
        if best is not None:
            _score, rot, cand, leader, cw, ch = best
            return cand, leader, cw, ch, rot

    # fallback:哪裡都塞不下就擺回錨點,不轉向
    cand = candidate_geom(cx, cy, w, h, shape_type)
    return cand, LineString([(cx, cy), (cx, cy)]), w, h, 0

# === Main ===
def main():
    # 公司環境的判斷留在 PML 端 —— DrawingPlan1 的 .Apply() 一開頭就呼叫
    # .CheckCompanyNetwork()(走 AteSortLineNo.IsAuthorized()),不通過會跳
    # alert 並 return,根本走不到這裡。原本這裡那份 hostname/SQL 檢查是重複的,
    # 而且失敗時是靜靜 return 什麼都不寫,PML 讀不到 LabelSpace.txt 就把標籤
    # 全留在 XYPO 15 15,沒有任何訊息 —— 加上它把 sa 密碼明文帶進 exe,所以拿掉。
    try:
        open(LOG_FILE, "w", encoding="utf-8").close()
    except Exception:
        pass
    # 參數檔先讀,因為裡面的 dimline 名單決定了下面哪些 DXF 線算軟障礙
    if not os.path.exists(PARAM_TXT):
        log("Param file missing: " + PARAM_TXT)
        return
    # utf-8-sig:E3D 的檔案物件寫檔會帶 UTF-8 BOM,用 "utf-8" 讀的話 BOM 會黏在
    # 第一筆的 ref 前面(﻿=2013…),再原樣寫回 LabelSpace.txt。輸出順序等於
    # 輸入順序時它永遠在第一行,E3D 讀檔會剝掉檔頭的 BOM,所以一直沒事;改成大
    # 的先放之後那筆被排到中間,PML 拿到 $!slab 就是 (47,50) Meaningless symbol
    # (2026-09-11)。
    with open(PARAM_TXT, "r", encoding="utf-8-sig", errors="ignore") as fp:
        raw_lines = [ln.strip() for ln in fp if ln.strip()]
    dim_segments, cloud_counts, cloud_texts, lines = parse_dim_segments(raw_lines)
    log("dimline records from PML: %d ;  revision cloud outlines listed: %d" % (len(dim_segments), len(cloud_counts)))
    recs = [r for r in (parse_record(ln) for ln in lines) if r is not None]
    pinned_recs = [r for r in recs if r["pinned"]]
    log("label records: %d ;  pinned (already on the sheet): %d" % (len(recs), len(pinned_recs)))

    # 讀取 DXF_A
    try:
        doc_a = ezdxf.readfile(DXF_A_PATH)
    except Exception as e:
        log("Fail read DXF_A: %s" % e)
        return
    msp_a = doc_a.modelspace()

    # pinned 標籤自己的 LABEL block 不是障礙,見 excluded_label_blocks()
    excluded_blocks, n_ex_anchor, n_ex_inside = excluded_label_blocks(msp_a, pinned_recs)
    if pinned_recs:
        log("LABEL blocks taken out as the pinned labels' own: %d (by anchor %d, inside a pinned box %d)"
            % (len(excluded_blocks), n_ex_anchor, n_ex_inside))
    # 上一版的進版雲線與版次三角形不是障礙,見 parse_dim_segments 的說明
    excluded_ents = excluded_cloud_entities(msp_a, cloud_counts, cloud_texts)
    if cloud_counts:
        log("revision clouds taken out of the obstacles: %d entities matched of %d listed" % (len(excluded_ents), len(cloud_counts)))

    # 準備 DXF_B
    if os.path.exists(DXF_B_PATH):
        try:
            doc_b = ezdxf.readfile(DXF_B_PATH)
            try:
                doc_b.modelspace().delete_all_entities()
            except Exception:
                for ent in list(doc_b.modelspace()):
                    try:
                        doc_b.modelspace().delete_entity(ent)
                    except Exception:
                        pass
        except Exception:
            doc_b = ezdxf.new(dxfversion="R2010")
    else:
        doc_b = ezdxf.new(dxfversion="R2010")
    msp_b = doc_b.modelspace()

    # 收集 shapes from A。尺寸線記成軟障礙 —— 標籤可以壓上去,PML 事後用 GAP
    # 把線斷開;其餘一律是硬障礙,壓到就不能用。怎麼認尺寸線見 is_soft_dim_line。
    shapes_a = []
    soft_a = []
    metas_a = []      # 跟 shapes_a 同步,只給 pinned 撞到誰的 log 用
    n_soft = 0
    n_loose_unmatched = 0
    for e, blk in explode_all(msp_a):
        if blk is not None and blk in excluded_blocks:
            continue
        if blk is None and id(e) in excluded_ents:
            continue
        try:
            is_soft = is_soft_dim_line(e, dim_segments)
            if is_soft:
                n_soft += 1
            elif blk is None and e.dxftype() == "LINE":
                # 頂層散裝的線,但沒對上 PML 報的任何一條。DRAFT 只把 LDIM
                # 攤平寫出來,所以這裡數量大得離譜就表示 dimline 名單有問題
                # (漏了某一邊,或座標系不對);少數幾條是正常的 —— matchline
                # 外框和使用者自己畫的線本來就在這裡。
                n_loose_unmatched += 1
            for geom, meta in entity_to_shape_with_meta(e):
                if geom is not None:
                    shapes_a.append(geom)
                    soft_a.append(is_soft)
                    meta["block"] = blk
                    metas_a.append(meta)
        except Exception:
            continue
    # 沒被認領的數字是名單有沒有對上的指標:正常只有 matchline 外框那十幾段
    # 和使用者手畫的線;一大堆就表示 dimline 座標跟 DXF 對不上
    log("soft (dimension) lines: %d ;  loose lines not claimed by PML: %d ;  shapes: %d"
        % (n_soft, n_loose_unmatched, len(shapes_a)))

    # box 外標籤的引線不准穿過的文字,見 LEADER_TEXT_SHAPES
    global LEADER_TEXT_SHAPES, LEADER_TEXT_TREE
    LEADER_TEXT_SHAPES = [g for g, m in zip(shapes_a, metas_a)
                          if m.get("type") in ("TEXT", "MTEXT_LINE", "MTEXT_EXTENTS")]
    if LEADER_TEXT_SHAPES:
        from shapely.strtree import STRtree
        LEADER_TEXT_TREE = STRtree(LEADER_TEXT_SHAPES)

    # 初始 shapes_b (可能為空)
    shapes_b = []
    soft_b = []
    for e, blk in explode_all(msp_b):
        try:
            for geom, meta in entity_to_shape_with_meta(e):
                if geom is not None:
                    shapes_b.append(geom)
                    soft_b.append(False)
        except Exception:
            continue

    # all_shapes 與 rtree 建立。soft_flags 必須跟 all_shapes 同步成長,
    # 索引是兩者之間唯一的對應關係。
    all_shapes = list(shapes_a) + list(shapes_b)
    soft_flags = list(soft_a) + list(soft_b)
    rtree_idx = build_rtree_from_shapes(all_shapes)
    next_id = len(all_shapes)

    # 參數檔在 main() 開頭就讀掉了(dimline 名單要先備好),recs 已經是
    # 去掉 dimline 之後的標籤記錄
    out_lines = []
    n_on_soft = 0
    existing_leaders = []  # will store LineString segments
    existing_labels = []   # will store label geometries (boxes, polygons)

    # pinned 標籤:框本體(不含留白)跟 DXF 硬障礙相交的才算撞到、才重放;
    # 其餘 kept —— 原座標輸出,而且先當硬障礙放進去(框帶 SAFE_GAP,跟放好的
    # 標籤一樣;引線是錨點到框緣最近點),後面放的東西都得避開它們。
    # 只對 DXF 幾何測,不對別的 pinned 框測:兩顆凍住的標籤彼此不會撞出新雲。
    hit_recs = []
    n_kept = 0
    for rec in pinned_recs:
        body, cw, ch = pinned_box(rec, gap=0.0)
        hit_by = None
        for i in rtree_query_ids(rtree_idx, all_shapes, body):
            if soft_flags[i]:
                continue                      # 尺寸投影線:壓著也不算,GAP 會斷開它
            # 零長度的 LINE(build_line_geom 把它撐成 1e-3 的短樁):實測 C 版
            # DXF 裡就躺在標籤底下 —— 是這顆標籤自己的 GAP 把尺寸線吃到只剩一點
            # 的殘跡,紙上看不見,不算撞到。放置時它照舊是硬障礙,不動那邊
            g = all_shapes[i]
            if g.geom_type == "LineString" and g.length < 0.01:
                continue
            if g.intersects(body):
                hit_by = metas_a[i] if i < len(metas_a) else {"type": "?", "block": None}
                break
        if hit_by is not None:
            hit_recs.append(rec)
            log("pinned %s hit at (%.3f, %.3f) by %s in block %s -> re-placed"
                % (rec["ref"], rec["cx"], rec["cy"], hit_by.get("type"), hit_by.get("block")))
            continue
        n_kept += 1
        kept_geom = pinned_box(rec, gap=SAFE_GAP)[0]
        out_lines.append(f"{rec['ref']} {rec['cx']:.3f} {rec['cy']:.3f} {rec['ax']} {rec['ay']} {cw} {ch} {rec['type']} {rec['rot']} kept")
        existing_labels.append(kept_geom)
        existing_leaders.append(pinned_leader(rec, kept_geom))
        all_shapes.append(kept_geom)
        soft_flags.append(False)
        try:
            rtree_idx.insert(next_id, kept_geom.bounds)
        except Exception:
            pass
        next_id += 1
        try:
            if rec["type"] == "circle":
                msp_b.add_circle((rec["cx"], rec["cy"]), cw/2.0, dxfattribs={"color":8})
            else:
                minx, miny, maxx, maxy = kept_geom.bounds
                msp_b.add_lwpolyline([(minx, miny), (minx, maxy), (maxx, maxy), (maxx, miny)], close=True, dxfattribs={"color":8})
        except Exception:
            pass
    if pinned_recs:
        log("pinned kept: %d ;  hit and re-placed: %d" % (n_kept, len(hit_recs)))

    # 要放的:被撞到的 pinned 加上所有非 pinned(新標籤),大的先
    todo = [r for r in recs if not r["pinned"]] + hit_recs
    if PLACE_BIG_FIRST:
        todo = sorted(todo, key=lambda r: _place_key(r["line"]), reverse=True)   # stable:鍵相同維持原順序

    for rec in todo:
        ref = rec["ref"]
        cx = rec["ax"]; cy = rec["ay"]
        label_w = rec["w"]; label_h = rec["h"]
        shape_type = rec["type"]
        old_pos = (rec["cx"], rec["cy"]) if rec["pinned"] else None

        # find candidate & proposed leader
        cand, leader, out_w, out_h, rot = find_blank_area_with_leader(
            all_shapes, soft_flags, rtree_idx, cx, cy, label_w, label_h, shape_type, INSIDE_REGION,
            existing_leaders, existing_labels, old_pos
        )

        # if candidate None (shouldn't happen), fallback to center
        if cand is None:
            cand = candidate_geom(cx, cy, label_w, label_h, shape_type)
            out_w, out_h, rot = label_w, label_h, 0

        cen = cand.centroid
        # 第 6/7 欄是「採用的」寬高 —— 轉向的話已經對調過,所以 PML 那邊算引線
        # 接點用的框界不必知道有沒有轉。第 9 欄是要下給 SLAB 的 Adegrees。
        # 第 10 欄只有 pinned 記錄才有:moved,PML 據此回填;新標籤沒有第 10 欄。
        tail = " moved" if rec["pinned"] else ""
        out_lines.append(f"{ref} {cen.x:.3f} {cen.y:.3f} {cx} {cy} {out_w} {out_h} {shape_type} {rot}{tail}")
        if rec["pinned"]:
            log("pinned %s moved (%.3f, %.3f) -> (%.3f, %.3f), %.1fmm"
                % (ref, rec["cx"], rec["cy"], cen.x, cen.y, Point(rec["cx"], rec["cy"]).distance(cen)))

        # add label shape to DXF_B
        try:
            if shape_type == "circle":
                msp_b.add_circle((cen.x, cen.y), label_w/2.0, dxfattribs={"color":3})
            else:
                minx, miny, maxx, maxy = cand.bounds
                msp_b.add_lwpolyline([(minx, miny), (minx, maxy), (maxx, maxy), (maxx, miny)], close=True, dxfattribs={"color":3})
        except Exception:
            pass

        # Update existing_labels (so future leaders know)
        existing_labels.append(cand)

        # break leader at intersections with existing_labels/existing_leaders
        segments = break_leader_at_intersections(leader, existing_leaders, existing_labels[:-1])
        # note: we pass existing_labels excluding the label we just appended (so leader touching its own label doesn't block)
        # If returned list empty, draw original leader as single segment (but still respect obstacles: we'll attempt single seg)
        if not segments:
            segments = [leader]

        # write segments to DXF_B and register them into existing_leaders
        seg_count = 0
        for seg in segments:
            try:
                sx, sy = seg.coords[0]
                ex, ey = seg.coords[-1]
                # draw only if length > tiny
                if seg.length > 1e-9:
                    msp_b.add_line((sx, sy), (ex, ey), dxfattribs={"color":1})
                    existing_leaders.append(seg)
                    seg_count += 1
            except Exception:
                continue

        # 這個標籤有沒有壓在尺寸線上 —— PML 那邊該有對應的 LGAP。純粹是給
        # check 用的數字,不影響放置
        try:
            for sid in rtree_query_ids(rtree_idx, all_shapes, cand):
                if soft_flags[sid] and all_shapes[sid].intersects(cand):
                    n_on_soft += 1
                    break
        except Exception:
            pass

        # Also add placed label geometry into all_shapes & rtree
        all_shapes.append(cand)
        soft_flags.append(False)   # 放好的標籤是硬障礙
        try:
            rtree_idx.insert(next_id, cand.bounds)
        except Exception:
            pass
        next_id += 1

    log("labels placed: %d (of which pinned kept: %d) ;  laid on a dimension line: %d"
        % (len(out_lines), n_kept, n_on_soft))

    # 輸出 LabelSpace.txt
    try:
        with open(OUT_FILE, "w", encoding="utf-8") as fout:
            fout.write("\n".join(out_lines))
    except Exception:
        pass

    # 儲存 DXF_B
    try:
        doc_b.saveas(DXF_B_PATH)
    except Exception:
        pass

if __name__ == "__main__":
    main()
