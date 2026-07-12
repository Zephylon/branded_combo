"""
Tkinter GUI for the Branded combo recommender v6.1 
"""
from __future__ import annotations

import random
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from PIL import ImageGrab

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

try:
    from branded_combo_engine_v6_1 import load_data, load_ydk, recommend, split_card_lines, normalize, TYPE_EXTRA, TYPE_MONSTER, TYPE_FIELD
    from branded_deck_editor_v6_1 import launch_editor
except Exception as e:
    raise SystemExit(f"필수 파이썬 파일을 같은 폴더에 두세요. Import error: {e}")

APP_DIR = Path(__file__).resolve().parent

MINI_W = int(92 * 0.5) 
MINI_H = int(134 * 0.5) 
CARD_W = 92
CARD_H = 134

class TextToolTip:
    """일반 텍스트용 툴팁 (깜빡임 방지를 위해 마우스 위치 기반)"""
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.close)
        self.tw = None
        
    def enter(self, event=None):
        if not event: return
        x = event.x_root + 20
        y = event.y_root + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tw, text=self.text, justify='left', background="#ffffe0", relief='solid', borderwidth=1, font=("Malgun Gothic", 9))
        label.pack(ipadx=10, ipady=5)
        
    def close(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

class CardImageToolTip:
    """미니 필드의 카드에 마우스를 올렸을 때 큰 이미지를 띄워주는 툴팁"""
    def __init__(self, widget, card_name, app_instance):
        self.widget = widget
        self.card_name = card_name
        self.app = app_instance
        self.tw = None
        self.photo = None
        
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.close)
        
    def enter(self, event=None):
        if not event: return
        x = event.x_root + 20
        y = event.y_root + 20
        
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        
        # 툴팁용 큰 이미지 (약 200x290)
        self.photo = self.app._get_card_photo(self.card_name, 200, 290)
        if self.photo:
            lbl = tk.Label(self.tw, image=self.photo, bg="#fff", relief='solid', borderwidth=2)
            lbl.pack()
        else:
            lbl = tk.Label(self.tw, text=self.card_name, bg="#ffffe0", relief='solid', borderwidth=1, font=("Malgun Gothic", 9))
            lbl.pack(ipadx=10, ipady=5)
            
    def close(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

class ImageToolTip:
    """패/묘지 구역에 마우스를 올렸을 때 여러 장의 이미지를 격자로 띄워주는 툴팁"""
    def __init__(self, widget, card_dict, app_instance):
        self.widget = widget
        self.card_dict = card_dict
        self.app = app_instance
        self.tw = None
        self.photos = [] 
        
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.close)
        
    def enter(self, event=None):
        if not self.card_dict or not event: return
        
        x = event.x_root + 20
        y = event.y_root + 20
        
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        
        frame = tk.Frame(self.tw, bg="#ffffff", relief='solid', borderwidth=2)
        frame.pack(padx=2, pady=2)
        
        self.photos = []
        row, col = 0, 0
        for name, count in self.card_dict.items():
            for _ in range(count):
                photo = self.app._get_card_photo(name, MINI_W, MINI_H)
                if photo:
                    lbl = tk.Label(frame, image=photo, bg="#fff")
                    lbl.grid(row=row, column=col, padx=2, pady=2)
                    self.photos.append(photo)
                else:
                    lbl = tk.Label(frame, text=name, bg="#eee", width=8, height=4, wraplength=MINI_W, font=("Malgun Gothic", 7), relief="solid", bd=1)
                    lbl.grid(row=row, column=col, padx=2, pady=2)
                
                col += 1
                if col >= 5: 
                    col = 0
                    row += 1
                    
    def close(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

class BrandedComboApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("낙인 전개 추천기 v6.1")
        self.geometry("1400x860")
        self.data = []
        self.deck = None
        self.recommendations = []
        self.cdb_paths = []
        self.pics_dirs = [APP_DIR / "pics"]
        self.card_id_by_name = {}
        self.global_name_to_type = {} # 자동 배치를 위한 전체 DB 변수
        self._photo_refs = []
        self._mini_photo_refs = []

        self._setup_style()
        self._build_ui()
        self._auto_load_data()
        
        self.bind("<Control-v>", self._on_global_paste)
        self.bind("<Control-V>", self._on_global_paste)

    def _setup_style(self):
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except: pass
        style.configure("Card.TFrame", background="#ffffff", relief="flat", borderwidth=1)
        style.configure("Title.TLabel", font=("Malgun Gothic", 16, "bold"))
        style.configure("CardTitle.TLabel", font=("Malgun Gothic", 11, "bold"), background="#ffffff")
        style.configure("Small.TLabel", font=("Malgun Gothic", 8), background="#ffffff", foreground="#555")
        style.configure("Treeview", font=("Malgun Gothic", 9), rowheight=26)
        style.configure("Treeview.Heading", font=("Malgun Gothic", 9, "bold"))

    def _build_ui(self):
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        header = ttk.Frame(root)
        header.pack(fill="x", pady=(0, 10))
        ttk.Label(header, text="낙인 전개 추천기 v6.1", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="내장 덱 편집기 열기", command=self._open_deck_editor).pack(side="right")

        paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, style="Card.TFrame", padding=12)
        right = ttk.Frame(paned, style="Card.TFrame", padding=12)
        paned.add(left, weight=0)
        paned.add(right, weight=1)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, parent):
        ttk.Label(parent, text="1. 덱리 (YDK) 연동", style="CardTitle.TLabel").pack(anchor="w")

        ydk_row = ttk.Frame(parent, style="Card.TFrame")
        ydk_row.pack(fill="x", pady=4)
        self.ydk_var = tk.StringVar()
        ttk.Entry(ydk_row, textvariable=self.ydk_var, width=38).pack(side="left", fill="x", expand=True)
        ttk.Button(ydk_row, text="YDK 찾기", command=self._browse_ydk).pack(side="left", padx=5)
        
        btn_row = ttk.Frame(parent, style="Card.TFrame")
        btn_row.pack(fill="x", pady=4)
        ttk.Button(btn_row, text="CDB 폴더 추가", command=self._add_cdb_folder).pack(side="left")
        ttk.Button(btn_row, text="YDK 새로고침", command=self._load_ydk).pack(side="left", padx=5)

        self.deck_status = tk.StringVar(value="yugioh_branded_combos.json 로드 대기 중...")
        ttk.Label(parent, textvariable=self.deck_status, wraplength=360).pack(anchor="w", pady=(0, 10))

        ttk.Separator(parent).pack(fill="x", pady=8)

        hand_header_row = ttk.Frame(parent, style="Card.TFrame")
        hand_header_row.pack(fill="x", pady=(0, 4))
        ttk.Label(hand_header_row, text="2. 현재 패 입력 (최대 9장)", style="CardTitle.TLabel").pack(side="left")
        ttk.Button(hand_header_row, text="클립보드 인식 (베타)", command=self._process_clipboard_image).pack(side="right")
        ttk.Button(hand_header_row, text="무작위 5장 뽑기", command=self._draw_random_hand).pack(side="right", padx=(0, 5))

        self.hand_text = ScrolledText(parent, height=8, font=("Malgun Gothic", 10))
        self.hand_text.pack(fill="x", pady=4)
        self.hand_text.insert("1.0", "천저의 사도\n혁의 성녀 카르테시아\n비스테드 살로니르\n하루 우라라\n무한포영")
        ttk.Label(parent, text="💡 Tip: 캡처 도구(Win+Shift+S)로 패를 캡처 후 여기서 Ctrl+V를 누르세요!", style="Small.TLabel").pack(anchor="w", pady=(2,4))

        ttk.Separator(parent).pack(fill="x", pady=8)

        filter_header = ttk.Frame(parent, style="Card.TFrame")
        filter_header.pack(fill="x", pady=(0, 4))
        ttk.Label(filter_header, text="3. 추천 필터 및 가중치", style="CardTitle.TLabel").pack(side="left")
        
        help_btn = tk.Label(filter_header, text=" ? ", font=("Arial", 9, "bold"), bg="#e0e0e0", fg="#333", cursor="question_arrow")
        help_btn.pack(side="left", padx=5)
        
        help_text = (
            "• 락: 상대 필드에 몬스터를 소환시켜 특수 소환 락을 거는 방법\n"
            "• 지속: 낙인의 에튀드 등 지속 함정 등으로 상대에게 불이익을 강요하는 방식\n"
            "• 구식: 신규 낙인 지원이 나오기 이전의 전개 방법"
        )
        TextToolTip(help_btn, help_text)
        
        self.tag_lock = tk.BooleanVar()
        self.tag_cont = tk.BooleanVar()
        self.tag_no_old = tk.BooleanVar()
        self.tag_no_cost = tk.BooleanVar()
        
        opts = ttk.Frame(parent, style="Card.TFrame")
        opts.pack(fill="x", pady=4)
        ttk.Checkbutton(opts, text="우선 추천: 락", variable=self.tag_lock).pack(anchor="w")
        ttk.Checkbutton(opts, text="우선 추천: 지속", variable=self.tag_cont).pack(anchor="w")
        ttk.Checkbutton(opts, text="제외: 구식 태그", variable=self.tag_no_old).pack(anchor="w")
        ttk.Checkbutton(opts, text="조건: 추가 코스트 X", variable=self.tag_no_cost).pack(anchor="w")

        top_row = ttk.Frame(parent, style="Card.TFrame")
        top_row.pack(fill="x", pady=4)
        ttk.Label(top_row, text="표시 개수:").pack(side="left")
        self.top_var = tk.IntVar(value=5)
        ttk.Spinbox(top_row, from_=1, to=10, textvariable=self.top_var, width=5).pack(side="left", padx=5)

        ttk.Button(parent, text="전개 추천 실행", command=self._run_recommend, style="TButton").pack(fill="x", pady=15)

    def _build_right(self, parent):
        top = ttk.Frame(parent, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="추천 결과", style="CardTitle.TLabel").pack(side="left")

        columns = ("rank", "disrupt", "cost", "tags", "name")
        self.tree = ttk.Treeview(parent, columns=columns, show="headings", height=6)
        headings = {"rank": "순위", "disrupt": "견제 수", "cost": "소모패", "tags": "특이점", "name": "전개법 이름"}
        widths = {"rank": 50, "disrupt": 60, "cost": 60, "tags": 120, "name": 300}
        
        for col in columns:
            self.tree.heading(col, text=headings[col])
            self.tree.column(col, width=widths[col], anchor="w" if col == "name" else "center")
            
        self.tree.pack(fill="x", pady=8)
        self.tree.bind("<<TreeviewSelect>>", self._on_select_result)

        vis_header = ttk.Frame(parent, style="Card.TFrame")
        vis_header.pack(fill="x", pady=(10, 0))
        ttk.Label(vis_header, text="필요 파츠 및 예상 결과 필드", style="CardTitle.TLabel").pack(side="left")

        self.visual_outer = ttk.Frame(parent, style="Card.TFrame")
        self.visual_outer.pack(fill="x", pady=4)
        
        self.parts_frame = ttk.Frame(self.visual_outer, style="Card.TFrame")
        self.parts_frame.pack(side="left", fill="y", padx=(0, 20))
        
        self.field_frame = ttk.Frame(self.visual_outer, style="Card.TFrame")
        self.field_frame.pack(side="left", fill="both", expand=True)

        ttk.Label(parent, text="상세 결과물 및 비고", style="CardTitle.TLabel").pack(anchor="w", pady=(10,0))
        self.detail = ScrolledText(parent, font=("Malgun Gothic", 10), wrap="word")
        self.detail.pack(fill="both", expand=True, pady=4)

    def _open_deck_editor(self):
        if not self.cdb_paths:
            for p in APP_DIR.glob("**/*.cdb"):
                self.cdb_paths.append(str(p.parent))
                break
        launch_editor(self, self.cdb_paths, self.ydk_var.get(), APP_DIR)

    def _auto_load_data(self):
        p = APP_DIR / "yugioh_branded_combos.json" 
        if p.exists():
            try:
                self.data = load_data(p)
                self.deck_status.set("✅ 데이터(JSON) 로드 완료. 덱리(YDK)를 불러와주세요.")
            except Exception as e: 
                messagebox.showerror("데이터 오류", f"JSON 파싱 실패:\n{e}")
        else:
            self.deck_status.set("⚠️ yugioh_branded_combos.json 파일이 없습니다!")

    def _browse_ydk(self):
        p = filedialog.askopenfilename(filetypes=[("YDK", "*.ydk")])
        if p: 
            self.ydk_var.set(p)
            self._load_ydk() 

    def _add_cdb_folder(self):
        p = filedialog.askdirectory()
        if p: self.cdb_paths.append(p)

    def _load_ydk(self):
        p = self.ydk_var.get()
        if not p or not self.data: return
        self.deck = load_ydk(p, self.data, cdb_paths=self.cdb_paths)
        
        self.card_id_by_name = {}
        self.global_name_to_type = {}
        
        for cid, name in zip(self.deck.main_ids + self.deck.extra_ids, self.deck.main_names + self.deck.extra_names):
            self.card_id_by_name[normalize(name)] = str(cid)

        # 전체 DB를 기반으로 자동 배치를 위한 카드 종류 캐싱
        for cid, cdata in self.deck.id_to_data.items():
            self.global_name_to_type[normalize(cdata["name"])] = cdata["type"]

        unres = len(self.deck.unresolved_ids)
        msg = f"YDK 로드 완료 (메인: {len(self.deck.main_ids)}장 / 엑스트라: {len(self.deck.extra_ids)}장)"
        if unres > 0:
            msg += f" | ⚠️ 미해결 카드 {unres}장 (CDB 확인 필요)"
        self.deck_status.set(msg)

    def _draw_random_hand(self):
        if not self.deck or not self.deck.main_names:
            messagebox.showwarning("덱 없음", "먼저 YDK를 불러와주세요.")
            return
        
        valid_cards = [name for name in self.deck.main_names if not name.startswith("UNKNOWN:")]
        if len(valid_cards) < 5:
            messagebox.showwarning("카드 부족", "메인 덱에 인식된 카드가 5장 미만입니다. CDB 연동을 확인하세요.")
            return
            
        sampled = random.sample(valid_cards, 5)
        self.hand_text.delete("1.0", "end")
        self.hand_text.insert("1.0", "\n".join(sampled))

    def _on_global_paste(self, event=None):
        try:
            img = ImageGrab.grabclipboard()
            if img and not isinstance(img, str): 
                self._run_image_recognition(img)
                return "break" 
        except Exception:
            pass

    def _process_clipboard_image(self):
        try:
            img = ImageGrab.grabclipboard()
            if img and not isinstance(img, str):
                self._run_image_recognition(img)
            else:
                messagebox.showwarning("인식 실패", "클립보드에 이미지 데이터가 없습니다.\n캡처 도구(Win+Shift+S) 등으로 패 영역을 캡처한 뒤 시도해주세요.")
        except Exception as e:
            messagebox.showerror("오류", f"클립보드 이미지를 읽어오는 중 실패했습니다:\n{e}")

    def _run_image_recognition(self, pil_image):
        if not self.deck or not self.deck.main_ids:
            messagebox.showwarning("덱 없음", "먼저 YDK를 불러와주세요.\n(덱리 기반으로 후보를 좁혀 대조합니다)")
            return
            
        try:
            import screen_reader
        except ImportError:
            messagebox.showerror("모듈 부족", "screen_reader.py 모듈이나 opencv-python 라이브러리가 없습니다.")
            return

        expanded_ids = set()
        for name in self.deck.main_names:
            if name.startswith("UNKNOWN:"):
                continue
            norm_target = normalize(name)
            for cid, db_name in self.deck.full_db.items():
                if normalize(db_name) == norm_target:
                    if str(cid).isdigit():
                        expanded_ids.add(str(cid))
                        
        main_ids = list(expanded_ids)

        self.deck_status.set("클립보드 이미지를 분석하고 있습니다...")
        self.update()

        try:
            matched_ids = screen_reader.recognize_hand_from_image(pil_image, main_ids, self.pics_dirs)
            
            if not matched_ids:
                messagebox.showinfo("결과 없음", "이미지에서 일치하는 카드를 찾지 못했습니다.\n캡처 구역이 정확한지 혹은 pics 매핑을 확인하세요.")
                self.deck_status.set("클립보드 매칭 실패.")
                return

            matched_names = []
            for cid in matched_ids:
                found_name = self.deck.full_db.get(str(cid), f"UNKNOWN:{cid}")
                matched_names.append(found_name)
            
            while len(matched_names) < 5:
                matched_names.append("인식불가 (수동수정)")
                
            self.hand_text.delete("1.0", "end")
            self.hand_text.insert("1.0", "\n".join(matched_names))
            self.deck_status.set(f"클립보드 이미지 매칭 완료! ({len(matched_ids)}장 식별)")
            
        except Exception as e:
            messagebox.showerror("오류", f"매칭 연산 중 예외가 발생했습니다:\n{e}")
            self.deck_status.set("매칭 연산 중 오류 발생.")

    def _run_recommend(self):
        if not self.deck:
            messagebox.showwarning("덱 없음", "먼저 YDK를 불러와주세요.")
            return

        hand = split_card_lines(self.hand_text.get("1.0", "end"))
        
        if len(hand) < 1:
            messagebox.showwarning("패 확인", "패를 1장 이상 입력해주세요.")
            return
        if len(hand) < 5:
            if not messagebox.askyesno("패 확인", f"패가 {len(hand)}장만 입력되었습니다. 이대로 진행할까요?"):
                return

        valid_recs, failed_recs = recommend(
            self.data, hand, self.deck.main_names, self.deck.name_to_data, self.deck.extra_names,
            top_n=self.top_var.get(),
            prioritize_lock=self.tag_lock.get(),
            prioritize_cont=self.tag_cont.get(),
            exclude_old=self.tag_no_old.get(),
            no_extra_cost=self.tag_no_cost.get()
        )
        self.recommendations = valid_recs

        self.tree.delete(*self.tree.get_children())
        for w in self.parts_frame.winfo_children(): w.destroy()
        for w in self.field_frame.winfo_children(): w.destroy()
        
        if not valid_recs:
            self.detail.delete("1.0", "end")
            fail_text = "조건을 만족하는 전개법이 없습니다.\n\n[주요 덱 구축 미달 사유 (참고용)]\n"
            
            filtered_fails = []
            for f in failed_recs:
                meaningful_reasons = [r for r in f.missing_reasons if not r.startswith("패 부족") and not r.startswith("총 패 장수 부족")]
                if meaningful_reasons:
                    filtered_fails.append((f.combo_name, meaningful_reasons))
                    
            for combo_name, reasons in filtered_fails[:10]:
                fail_text += f"■ {combo_name}\n  -> {', '.join(reasons)}\n\n"
                
            self.detail.insert("1.0", fail_text)
            messagebox.showinfo("결과 없음", "가능한 전개가 없습니다. 우측 상세 창에서 누락된 덱 파츠 사유를 확인하세요.")
            return

        for i, rec in enumerate(self.recommendations, 1):
            self.tree.insert("", "end", iid=str(i-1), values=(
                i, rec.disruption_display, f"{rec.cost}장", rec.tags, rec.combo_name
            ))
            
        self.detail.delete("1.0", "end")

    def _on_select_result(self, event):
        sel = self.tree.selection()
        if not sel: return
        rec = self.recommendations[int(sel[0])]
        c = rec.combo
        
        text = f"■ 전개법: {rec.combo_name}\n"
        text += f"■ 견제 수: {rec.disruption_display}\n" 
        text += f"■ 추가 소모패: {rec.cost}장\n"
        
        end_field = ", ".join([f"{k}({v})" for k,v in c.get("전개 결과물(필드)", {}).items()]) or "없음"
        end_hand_dict = c.get("전개 결과물(패)", {})
        end_grave_dict = c.get("전개 결과물(묘지)", {})
        end_hand_text = ", ".join([f"{k}({v})" for k,v in end_hand_dict.items()]) or "없음"
        end_grave_text = ", ".join([f"{k}({v})" for k,v in end_grave_dict.items()]) or "없음"
        
        text += f"\n[결과물]\n- 필드: {end_field}\n- 패: {end_hand_text}\n- 묘지: {end_grave_text}\n"
        text += f"\n[비고]\n{c.get('비고', '없음')}\n"
        text += f"\n[리플레이]\n{c.get('전개법 링크', '없음')}\n"

        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)

        for w in self.parts_frame.winfo_children(): w.destroy()
        self._photo_refs.clear()

        for name, count in c.get("필요한 파츠", {}).items():
            self._make_visual_card(self.parts_frame, name, f"필요 파츠\n({count}장)").pack(side="left", padx=5)
            
        for cond in c.get("조건부 필요 파츠", []):
            desc = cond.get("설명", "조건부 카드")
            count = cond.get("수량", 1)
            self._make_visual_placeholder(self.parts_frame, f"{desc}\n({count}장)").pack(side="left", padx=5)
            
        if rec.cost > 0:
            for _ in range(rec.cost):
                self._make_visual_placeholder(self.parts_frame, "추가 코스트\n(1장)").pack(side="left", padx=5)

        # 미니 필드 시각화
        self._draw_mini_field(c.get("전개 결과물(필드)", {}), end_hand_dict, end_grave_dict)

    def _draw_mini_field(self, field_dict, hand_dict, grave_dict):
        for w in self.field_frame.winfo_children(): w.destroy()
        self._mini_photo_refs.clear()

        extra_list = []
        mmz_list = []
        stz_list = []
        field_spell = None

        # 1. 자동 분류 로직
        for name, count in field_dict.items():
            norm_name = normalize(name)
            ctype = self.global_name_to_type.get(norm_name, 0)
            
            for _ in range(count):
                if ctype & TYPE_FIELD:
                    field_spell = name
                elif ctype & TYPE_EXTRA:
                    extra_list.append(name)
                elif ctype & TYPE_MONSTER:
                    mmz_list.append(name)
                else: 
                    stz_list.append(name)

        # 2. 엑스트라 몬스터 우선순위 정렬
        def emz_priority(name):
            if "그랑기뇰" in name: return 0
            if "미라제이드" in name: return 1
            return 2
            
        extra_list.sort(key=emz_priority)
        
        emz_list = []
        if extra_list:
            emz_list.append(extra_list.pop(0)) # 1순위는 반드시 EMZ
        mmz_list.extend(extra_list) # 남은 엑덱몹은 전부 메인 몬스터 존으로

        # --- 레이아웃 구조 (Row 0: EMZ, Row 1: MMZ+Field, Row 2: STZ, Row 3: Hand) ---
        
        # Row 0: EMZ (우측 우선 배치)
        if len(emz_list) == 1:
            self._grid_mini_card(emz_list[0], row=0, col=4, bg_color="#f2e6ff")
            self._create_empty_slot(row=0, col=2, bg_color="#f2e6ff")
        else:
            self._create_empty_slot(row=0, col=2, bg_color="#f2e6ff")
            self._create_empty_slot(row=0, col=4, bg_color="#f2e6ff")

        # Row 1: Field Spell (Col 0) + MMZ (Col 1~5)
        if field_spell:
            self._grid_mini_card(field_spell, row=1, col=0, bg_color="#fff5e6")
        else:
            self._create_empty_slot(row=1, col=0, bg_color="#fff5e6", text="필드")
            
        mmz_cols = [3, 2, 4, 1, 5]
        for i in range(5):
            if i < len(mmz_list):
                self._grid_mini_card(mmz_list[i], row=1, col=mmz_cols[i], bg_color="#e6f2ff")
            else:
                self._create_empty_slot(row=1, col=mmz_cols[i], bg_color="#e6f2ff")

        # Row 2: STZ (Col 1~5)
        stz_cols = [3, 2, 4, 1, 5]
        for i in range(5):
            if i < len(stz_list):
                self._grid_mini_card(stz_list[i], row=2, col=stz_cols[i], bg_color="#e6ffe6")
            else:
                self._create_empty_slot(row=2, col=stz_cols[i], bg_color="#e6ffe6")

        # Grave (우측 긴 상자)
        grave_text = "묘지\n(0장)"
        if grave_dict:
            grave_count = sum(grave_dict.values())
            grave_text = f"묘지\n({grave_count}장)"
            
        grave_canvas = tk.Canvas(self.field_frame, width=MINI_W, height=MINI_H*3 + 8, bg="#ffffff", highlightthickness=0)
        grave_canvas.grid(row=0, column=6, rowspan=3, padx=5, pady=2)
        grave_canvas.create_rectangle(2, 2, MINI_W-2, (MINI_H*3 + 8)-2, dash=(4,4), outline="#ff9999", fill="#ffe6e6")
        grave_canvas.create_text(MINI_W//2, (MINI_H*3 + 8)//2, text=grave_text, fill="#cc0000", font=("Malgun Gothic", 9, "bold"), justify="center")
        
        if grave_dict:
            ImageToolTip(grave_canvas, grave_dict, self)

        # Hand (하단 넓은 상자)
        hand_text = "패 (결과물 없음)"
        if hand_dict:
            hand_count = sum(hand_dict.values())
            hand_text = f"패에 결과물 존재 ({hand_count}장) - 마우스를 올려 확인"
            
        hand_canvas = tk.Canvas(self.field_frame, width=MINI_W*5 + 16, height=MINI_H*0.6, bg="#ffffff", highlightthickness=0)
        hand_canvas.grid(row=3, column=1, columnspan=5, pady=(5,0))
        hand_canvas.create_rectangle(2, 2, (MINI_W*5 + 16)-2, (MINI_H*0.6)-2, outline="#999", fill="#e9ecef")
        hand_canvas.create_text((MINI_W*5 + 16)//2, (MINI_H*0.6)//2, text=hand_text, fill="#333", font=("Malgun Gothic", 9, "bold"))
        
        if hand_dict:
            ImageToolTip(hand_canvas, hand_dict, self)

    def _create_empty_slot(self, row, col, bg_color, text=""):
        c = tk.Canvas(self.field_frame, width=MINI_W, height=MINI_H, bg="#ffffff", highlightthickness=0)
        c.grid(row=row, column=col, padx=2, pady=2)
        c.create_rectangle(2, 2, MINI_W-2, MINI_H-2, dash=(4, 4), outline="#aaa", fill=bg_color)
        if text:
            c.create_text(MINI_W//2, MINI_H//2, text=text, fill="#777", font=("Malgun Gothic", 8, "bold"))
        return c

    def _grid_mini_card(self, name: str, row: int, col: int, bg_color: str):
        photo = self._get_card_photo(name, MINI_W, MINI_H)
        if photo:
            lbl = tk.Label(self.field_frame, image=photo, bg="#fff", bd=1, relief="solid")
            lbl.grid(row=row, column=col, padx=2, pady=2)
            CardImageToolTip(lbl, name, self) # 이미지 툴팁 호출
            self._mini_photo_refs.append(photo)
        else:
            lbl = self._create_empty_slot(row, col, bg_color, text="?")
            TextToolTip(lbl, name) # 사진이 없을 때만 텍스트 툴팁
            
    def _get_card_photo(self, name, width, height):
        cid = self.card_id_by_name.get(normalize(name))
        if cid:
            for pdir in self.pics_dirs:
                for ext in [".jpg", ".png"]:
                    img_path = pdir / f"{cid}{ext}"
                    if img_path.exists() and Image:
                        im = Image.open(img_path)
                        im.thumbnail((width, height))
                        return ImageTk.PhotoImage(im)
        return None

    def _make_visual_card(self, parent_frame, name: str, label_txt: str):
        frame = ttk.Frame(parent_frame, style="Card.TFrame")
        photo = self._get_card_photo(name, CARD_W, CARD_H)

        if photo:
            lbl = tk.Label(frame, image=photo, bg="#fff", bd=1, relief="solid")
            lbl.pack()
            self._photo_refs.append(photo)
        else:
            box = tk.Frame(frame, width=CARD_W, height=CARD_H, bg="#e9ecef", bd=1, relief="solid")
            box.pack_propagate(False)
            box.pack()
            tk.Label(box, text=name, bg="#e9ecef", font=("Malgun Gothic", 9, "bold"), wraplength=CARD_W-10).pack(expand=True)
            
        ttk.Label(frame, text=label_txt, style="Small.TLabel", justify="center").pack(pady=2)
        return frame

    def _make_visual_placeholder(self, parent_frame, text: str):
        frame = ttk.Frame(parent_frame, style="Card.TFrame")
        box = tk.Frame(frame, width=CARD_W, height=CARD_H, bg="#e9ecef", bd=1, relief="solid")
        box.pack_propagate(False)
        box.pack()
        tk.Label(box, text="임의의 패", bg="#e9ecef", font=("Malgun Gothic", 9, "bold"), wraplength=CARD_W-10).pack(expand=True)
        ttk.Label(frame, text=text, style="Small.TLabel", justify="center").pack(pady=2)
        return frame

if __name__ == "__main__":
    app = BrandedComboApp()
    app.mainloop()
