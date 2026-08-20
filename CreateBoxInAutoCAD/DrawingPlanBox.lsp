;;; ==================================================================
;;; DrawingPlanBox.lsp
;;;
;;; Pick drawing frames on a 1:1 CAD plan and append them to the CSV
;;; the E3D form !!DrawingPlan reads on its Import tab.
;;;
;;;   Command:  E3DBOX
;;;
;;; The drawing has to be at 1:1 already and sitting on the real model
;;; coordinates - CAD X is E, CAD Y is N, units are mm.  Nothing here
;;; scales, moves or rotates anything, so what is picked is what E3D
;;; gets.  The frame size is echoed after every pick, which is where a
;;; drawing at the wrong scale shows up (40000 x 30000, not 40 x 30).
;;;
;;; Three picks make one frame:
;;;
;;;   P1 -> P2   one whole edge of the frame, the long one or the
;;;              short one, at whatever angle it happens to be
;;;   P3         anywhere on the opposite side.  Only its distance
;;;              from the line P1-P2 is used, and the side it is on
;;;              is the side the frame grows towards
;;;
;;; Every frame is also drawn on the layer E3D_DWGBOX with its CSV
;;; line number in the middle.  E3D's import log names the same line
;;; numbers ("line 7 - created ..."), so a frame on screen can be
;;; matched back to a box in E3D while the drawing numbers are being
;;; typed in.  The layer can be frozen or deleted whenever it is in
;;; the way - nothing ever reads it back.
;;;
;;; Elevation is left blank by default and then comes from the two
;;; Elevation boxes on the E3D form.  Type E at the P1 prompt to put
;;; it in the file instead, for a drawing carrying more than one level.
;;;
;;; Prompts are kept plain ASCII on purpose - LISP files are read as
;;; the system codepage and non-ASCII text comes out as garbage on
;;; some AutoCAD versions.
;;; ==================================================================

(vl-load-com)

(setq *e3dbox-layer* "E3D_DWGBOX")

;;; ------------------------------------------------------------------
;;; DIMZIN can suppress a leading zero and turn 0.5 into ".5", which
;;; the PML side cannot parse, so it is forced off around the format
;;; ------------------------------------------------------------------
(defun e3d:num (x / z s)
  (setq z (getvar "DIMZIN"))
  (setvar "DIMZIN" 0)
  (setq s (rtos x 2 4))
  (setvar "DIMZIN" z)
  s
)

(defun e3d:join (lst sep / r)
  (setq r (car lst) lst (cdr lst))
  (foreach x lst (setq r (strcat r sep x)))
  r
)

(defun e3d:linecount (f / h n)
  (setq n 0)
  (if (setq h (open f "r"))
    (progn
      (while (read-line h) (setq n (1+ n)))
      (close h)
    )
  )
  n
)

;;; ------------------------------------------------------------------
;;; a new file gets the two comment lines.  E3D skips any line whose
;;; first two characters are '--', so the header costs nothing there
;;; and keeps the column order readable in a text editor
;;; ------------------------------------------------------------------
(defun e3d:ensure (f / h)
  (if (findfile f)
    T
    (if (setq h (open f "w"))
      (progn
        (write-line "-- E3D !!DrawingPlan - Import tab.  one drawing frame per line" h)
        (write-line "-- E1;N1;E2;N2;E3;N3;DwgNo;Rev;Title1;Title2;Title3;Ubot;Utop" h)
        (close h)
        T
      )
      nil
    )
  )
)

(defun e3d:layer ()
  (if (not (tblsearch "LAYER" *e3dbox-layer*))
    (entmake (list (cons 0 "LAYER")
                   (cons 100 "AcDbSymbolTableRecord")
                   (cons 100 "AcDbLayerTableRecord")
                   (cons 2 *e3dbox-layer*)
                   (cons 70 0)
                   (cons 62 3)
                   (cons 6 "Continuous")))
  )
)

(defun e3d:elevtext ()
  (if *e3dbox-ubot*
    (strcat (e3d:num *e3dbox-ubot*) " to " (e3d:num *e3dbox-utop*))
    "blank - taken from the Elevation boxes on the E3D form"
  )
)

(defun e3d:setfile (/ f)
  (setq f (getfiled "E3D box list - an existing file is appended to, never overwritten"
                    (if *e3dbox-file* *e3dbox-file* (getvar "DWGPREFIX"))
                    "csv"
                    1))
  (if f
    (progn
      (setq *e3dbox-file* f)
      (princ (strcat "\nFile: " f))
    )
  )
  (princ)
)

(defun e3d:setelev (/ b tp)
  (princ "\nEnter on its own clears it and hands the elevation back to the E3D form.")
  (setq b (getreal "\nBottom U in mm <clear>: "))
  (if (null b)
    (progn
      (setq *e3dbox-ubot* nil *e3dbox-utop* nil)
      (princ "\nElevation: blank - taken from the Elevation boxes on the E3D form")
    )
    (progn
      (setq tp (getreal "\nTop U in mm: "))
      (if tp
        (progn
          (setq *e3dbox-ubot* b *e3dbox-utop* tp)
          (princ (strcat "\nElevation: " (e3d:elevtext)))
        )
        (princ "\nCancelled - elevation left as it was")
      )
    )
  )
  (princ)
)

;;; ------------------------------------------------------------------
;;; the same geometry PML's .MakeBox() does, repeated here only so a
;;; bad pick is caught on the spot instead of turning into a skipped
;;; line in the import log much later
;;; ------------------------------------------------------------------
(defun e3d:write (a b c / w1 w2 w3 dx dy xlen ux uy tt fx fy vx vy ylen
                          corners cen ang h n lbl row ub ut)
  (setq w1 (trans a 1 0)
        w2 (trans b 1 0)
        w3 (trans c 1 0))
  (setq dx   (- (car w2) (car w1))
        dy   (- (cadr w2) (cadr w1))
        xlen (sqrt (+ (* dx dx) (* dy dy))))
  (cond
    ((< xlen 1.0)
     (princ "\n** P1 and P2 are the same point - nothing written."))
    (T
     (setq ux (/ dx xlen)
           uy (/ dy xlen))
     (setq tt (+ (* (- (car w3) (car w1)) ux)
                 (* (- (cadr w3) (cadr w1)) uy)))
     (setq fx (+ (car w1) (* ux tt))
           fy (+ (cadr w1) (* uy tt)))
     (setq vx   (- (car w3) fx)
           vy   (- (cadr w3) fy)
           ylen (sqrt (+ (* vx vx) (* vy vy))))
     (cond
       ((< ylen 1.0)
        (princ "\n** P3 sits on the line P1-P2 - its distance from that line is the other size of the frame, so pick it well off - nothing written."))
       ((not (e3d:ensure *e3dbox-file*))
        (princ (strcat "\n** Cannot create " *e3dbox-file* " - nothing written.")))
       (T
        (setq n (e3d:linecount *e3dbox-file*))
        (setq ub (if *e3dbox-ubot* (e3d:num *e3dbox-ubot*) "")
              ut (if *e3dbox-utop* (e3d:num *e3dbox-utop*) ""))
        (setq row (e3d:join (list (e3d:num (car w1)) (e3d:num (cadr w1))
                                  (e3d:num (car w2)) (e3d:num (cadr w2))
                                  (e3d:num (car w3)) (e3d:num (cadr w3))
                                  "" "" "" "" ""
                                  ub ut)
                            ";"))
        (if (setq h (open *e3dbox-file* "a"))
          (progn
            (write-line row h)
            (close h)
            (setq lbl (itoa (1+ n)))
            ;; the four corners the box will really have, so what gets
            ;; drawn is the frame itself and not just the three picks
            (setq corners (list (list (car w1) (cadr w1))
                                (list (car w2) (cadr w2))
                                (list (+ (car w2) vx) (+ (cadr w2) vy))
                                (list (+ (car w1) vx) (+ (cadr w1) vy))))
            (setq cen (list (+ (car w1) (* ux xlen 0.5) (* vx 0.5))
                            (+ (cadr w1) (* uy xlen 0.5) (* vy 0.5))))
            (setq ang (atan uy ux))
            ;; keep the number the right way up on a frame whose first
            ;; edge happened to be picked backwards
            (if (> (abs ang) (/ pi 2.0))
              (setq ang (- ang (* pi (if (> ang 0) 1.0 -1.0))))
            )
            (e3d:layer)
            (entmake (append (list (cons 0 "LWPOLYLINE")
                                   (cons 100 "AcDbEntity")
                                   (cons 8 *e3dbox-layer*)
                                   (cons 100 "AcDbPolyline")
                                   (cons 90 4)
                                   (cons 70 1))
                             (mapcar (function (lambda (p) (cons 10 p))) corners)))
            (entmake (list (cons 0 "TEXT")
                           (cons 100 "AcDbEntity")
                           (cons 8 *e3dbox-layer*)
                           (cons 100 "AcDbText")
                           (cons 10 cen)
                           (cons 40 (/ (min xlen ylen) 8.0))
                           (cons 1 lbl)
                           (cons 50 ang)
                           (cons 72 1)
                           (cons 11 cen)
                           (cons 100 "AcDbText")
                           (cons 73 2)))
            (princ (strcat "\n#" lbl " written - frame " (e3d:num xlen)
                           " x " (e3d:num ylen) " mm"))
          )
          (princ (strcat "\n** Cannot write to " *e3dbox-file*
                         " - is it open in Excel?"))
        )
       )
     )
    )
  )
  (princ)
)

(defun c:E3DBOX (/ p1 p2 p3 done)
  (if (not *e3dbox-file*)
    (setq *e3dbox-file* (strcat (getvar "DWGPREFIX")
                                (vl-filename-base (getvar "DWGNAME"))
                                "_e3dbox.csv"))
  )
  (princ "\n--- E3D DrawingPlan box list ---")
  (princ (strcat "\nFile     : " *e3dbox-file*))
  (princ (strcat "\nElevation: " (e3d:elevtext)))
  (princ "\nThe drawing must be at 1:1 on the real model coordinates.")
  (setq done nil)
  (while (not done)
    (initget "File Elev")
    (setq p1 (getpoint "\n\nP1 first corner of the frame [File/Elev] <exit>: "))
    (cond
      ((null p1) (setq done T))
      ((= (type p1) 'STR)
       (cond
         ((= p1 "File") (e3d:setfile))
         ((= p1 "Elev") (e3d:setelev))
       )
      )
      (T
       (setq p2 (getpoint p1 "\nP2 the other corner of that same edge: "))
       (if p2
         (progn
           (setq p3 (getpoint p2 "\nP3 any point on the opposite side: "))
           (if p3 (e3d:write p1 p2 p3))
         )
       )
      )
    )
  )
  (princ "\nDone. Load the file on the Import tab of !!DrawingPlan in E3D.")
  (princ)
)

(princ "\nDrawingPlanBox.lsp loaded - type E3DBOX to pick drawing frames.")
(princ)
