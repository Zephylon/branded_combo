"""
Tkinter GUI for the Branded combo recommender v5.1 (Clipboard Ctrl+V Integration)
"""
from __future__ import annotations

import json
import random
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText
from PIL import ImageGrab # 클립보드 이미지 캡처용

try:
    from PIL import Image, ImageTk
except Exception:
    Image = None
    ImageTk = None

try:
    from branded_combo_engine_v5_1 import load_data, load_ydk, recommend, split_card_lines, normalize
except Exception as e:
    raise SystemExit(f"branded_combo_engine_v5_1.py 파일을 같은 폴더에 두세요. Import error: {e}")

APP_DIR = Path(__file__).resolve().parent
CARD_W = 92
CARD_H = 134

class BrandedComboApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("낙인 전개 추천기 v5.1")
        self.geometry("1240x820")
        self.data = []
        self.deck = None
        self.recommendations = []
        self.cdb_paths = []
        self.pics_dirs = [APP_DIR / "pics"]
        self.card_id_by_name = {}
        self._photo_refs = []

        self._setup_style()
        self._build_ui()
        self._auto_load_data()
        
        # 수정점 5: 프로그램 전역에 Ctrl+V (붙여넣기) 단축키 바인딩
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

        ttk.Label(root, text="낙인 전개 추천기 v5.1", style="Title.TLabel").pack(anchor="w", pady=(0, 10))

        paned = ttk.PanedWindow(root, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True)

        left = ttk.Frame(paned, style="Card.TFrame", padding=12)
        right = ttk.Frame(paned, style="Card.TFrame", padding=12)
        paned.add(left, weight=0)
        paned.add(right, weight=1)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, parent):
        ttk.Label(parent, text="1. 데이터 / 덱리 (YDK)", style="CardTitle.TLabel").pack(anchor="w")

        data_row = ttk.Frame(parent, style="Card.TFrame")
        data_row.pack(fill="x", pady=4)
        self.data_path_var = tk.StringVar()
        ttk.Entry(data_row, textvariable=self.data_path_var, width=38).pack(side="left", fill="x", expand=True)
        ttk.Button(data_row, text="JSON 불러오기", command=self._browse_data).pack(side="left", padx=5)

        ydk_row = ttk.Frame(parent, style="Card.TFrame")
        ydk_row.pack(fill="x", pady=4)
        self.ydk_var = tk.StringVar()
        ttk.Entry(ydk_row, textvariable=self.ydk_var, width=38).pack(side="left", fill="x", expand=True)
        ttk.Button(ydk_row, text="YDK 찾기", command=self._browse_ydk).pack(side="left", padx=5)
        
        btn_row = ttk.Frame(parent, style="Card.TFrame")
        btn_row.pack(fill="x", pady=4)
        ttk.Button(btn_row, text="CDB 폴더 추가", command=self._add_cdb_folder).pack(side="left")
        ttk.Button(btn_row, text="YDK 새로고침", command=self._load_ydk).pack(side="left", padx=5)

        self.deck_status = tk.StringVar(value="YDK를 불러와주세요.")
        ttk.Label(parent, textvariable=self.deck_status, wraplength=360).pack(anchor="w", pady=(0, 10))

        ttk.Separator(parent).pack(fill="x", pady=8)

        hand_header_row = ttk.Frame(parent, style="Card.TFrame")
        hand_header_row.pack(fill="x", pady=(0, 4))
        ttk.Label(hand_header_row, text="2. 패 5장 입력", style="CardTitle.TLabel").pack(side="left")
        
        # 버튼 명칭 및 힌트 수정
        ttk.Button(hand_header_row, text="클립보드 인식 (베타)", command=self._process_clipboard_image).pack(side="right")
        ttk.Button(hand_header_row, text="무작위 뽑기", command=self._draw_random_hand).pack(side="right", padx=(0, 5))

        self.hand_text = ScrolledText(parent, height=6, font=("Malgun Gothic", 10))
        self.hand_text.pack(fill="x", pady=4)
        self.hand_text.insert("1.0", "천저의 사도\n혁의 성녀 카르테시아\n비스테드 살로니르\n하루 우라라\n무한포영")
        
        ttk.Label(parent, text="💡 Tip: 캡처 도구(Win+Shift+S)로 패를 캡처 후 여기서 Ctrl+V를 누르세요!", style="Small.TLabel").pack(anchor="w", pady=(2,4))

        ttk.Separator(parent).pack(fill="x", pady=8)

        ttk.Label(parent, text="3. 추천 필터 및 가중치", style="CardTitle.TLabel").pack(anchor="w")
        
        self.tag_lock = tk.BooleanVar()
        self.tag_cont = tk.BooleanVar()
        self.tag_no_old = tk.BooleanVar()
        
        opts = ttk.Frame(parent, style="Card.TFrame")
        opts.pack(fill="x", pady=4)
        ttk.Checkbutton(opts, text="우선 추천: 락", variable=self.tag_lock).pack(anchor="w")
        ttk.Checkbutton(opts, text="우선 추천: 지속", variable=self.tag_cont).pack(anchor="w")
        ttk.Checkbutton(opts, text="제외: 구식 태그", variable=self.tag_no_old).pack(anchor="w")

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

        ttk.Label(parent, text="필요 파츠 / 코스트 (선택 시 표시)", style="CardTitle.TLabel").pack(anchor="w", pady=(10,0))
        self.visual_inner = ttk.Frame(parent, style="Card.TFrame")
        self.visual_inner.pack(fill="x", pady=4)

        ttk.Label(parent, text="상세 결과물 및 비고", style="CardTitle.TLabel").pack(anchor="w", pady=(10,0))
        self.detail = ScrolledText(parent, font=("Malgun Gothic", 10), wrap="word")
        self.detail.pack(fill="both", expand=True, pady=4)

    def _auto_load_data(self):
        p = APP_DIR / "yugioh_branded_combos.json" 
        if p.exists():
            self.data_path_var.set(str(p))
            try:
                self.data = load_data(p)
            except: pass

    def _browse_data(self):
        p = filedialog.askopenfilename(filetypes=[("JSON", "*.json")])
        if p:
            self.data_path_var.set(p)
            self.data = load_data(p)

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
        for cid, name in zip(self.deck.main_ids + self.deck.extra_ids, self.deck.main_names + self.deck.extra_names):
            self.card_id_by_name[normalize(name)] = str(cid)

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
        """단축키 Ctrl+V 가 입력되었을 때 호출되는 이벤트 핸들러"""
        try:
            img = ImageGrab.grabclipboard()
            if img and not isinstance(img, str): # 클립보드에 담긴 게 이미지 파일이라면
                self._run_image_recognition(img)
                return "break" # 텍스트 컴포넌트의 기본 붙여넣기 동작을 방지
        except Exception:
            pass

    def _process_clipboard_image(self):
        """버튼을 직접 클릭했을 때 호출되는 핸들러"""
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

        main_ids = list(set(self.deck.main_ids))
        self.deck_status.set("클립보드 이미지를 분석하고 있습니다...")
        self.update()

        try:
            matched_ids = screen_reader.recognize_hand_from_image(pil_image, main_ids, self.pics_dirs)
            
            if not matched_ids:
                messagebox.showinfo("결과 없음", "이미지에서 일치하는 카드를 찾지 못했습니다.\n캡처 구역이 정확한지 혹은 pics 매핑을 확인하세요.")
                self.deck_status.set("클립보드 매칭 실패.")
                return

            id_to_name = {str(cid): name for cid, name in zip(self.deck.main_ids, self.deck.main_names)}
            matched_names = [id_to_name.get(str(cid), f"UNKNOWN:{cid}") for cid in matched_ids]
            
            while len(matched_names) < 5:
                matched_names.append("인식불가 (수동수정)")
                
            self.hand_text.delete("1.0", "end")
            self.hand_text.insert("1.0", "\n".join(matched_names[:5]))
            self.deck_status.set(f"클립보드 이미지 매칭 완료! ({len(matched_ids)}장 식별)")
            
        except Exception as e:
            messagebox.showerror("오류", f"매칭 연산 중 예외가 발생했습니다:\n{e}")
            self.deck_status.set("매칭 연산 중 오류 발생.")

    def _run_recommend(self):
        if not self.deck:
            messagebox.showwarning("덱 없음", "먼저 YDK를 불러와주세요.")
            return

        hand = split_card_lines(self.hand_text.get("1.0", "end"))
        if len(hand) != 5:
            if not messagebox.askyesno("패 확인", f"{len(hand)}장 입력됨. 진행할까요?"):
                return

        valid_recs, failed_recs = recommend(
            self.data, hand, self.deck.main_names, self.deck.extra_names,
            top_n=self.top_var.get(),
            prioritize_lock=self.tag_lock.get(),
            prioritize_cont=self.tag_cont.get(),
            exclude_old=self.tag_no_old.get()
        )
        self.recommendations = valid_recs

        self.tree.delete(*self.tree.get_children())
        for w in self.visual_inner.winfo_children(): w.destroy()
        
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
        end_hand = ", ".join([f"{k}({v})" for k,v in c.get("전개 결과물(패)", {}).items()]) or "없음"
        end_grave = ", ".join([f"{k}({v})" for k,v in c.get("전개 결과물(묘지)", {}).items()]) or "없음"
        text += f"\n[결과물]\n- 필드: {end_field}\n- 패: {end_hand}\n- 묘지: {end_grave}\n"
        
        text += f"\n[비고]\n{c.get('비고', '없음')}\n"
        text += f"\n[리플레이]\n{c.get('전개법 링크', '없음')}\n"

        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)

        for w in self.visual_inner.winfo_children(): w.destroy()
        self._photo_refs.clear()

        for name, count in c.get("필요한 파츠", {}).items():
            self._make_visual_card(name, f"필요 파츠\n({count}장)").pack(side="left", padx=5)
            
        # 수정점 1: 추가 코스트 매수 수치(rec.cost)만큼 개별적으로 반복 생성하여 배치
        if rec.cost > 0:
            for _ in range(rec.cost):
                self._make_visual_placeholder("추가 코스트\n(1장)").pack(side="left", padx=5)

    def _make_visual_card(self, name: str, label_txt: str):
        frame = ttk.Frame(self.visual_inner, style="Card.TFrame")
        cid = self.card_id_by_name.get(normalize(name))
        photo = None
        
        if cid:
            for pdir in self.pics_dirs:
                for ext in [".jpg", ".png"]:
                    img_path = pdir / f"{cid}{ext}"
                    if img_path.exists() and Image:
                        im = Image.open(img_path)
                        im.thumbnail((CARD_W, CARD_H))
                        photo = ImageTk.PhotoImage(im)
                        break
                if photo: break

        if photo:
            lbl = tk.Label(frame, image=photo, bg="#fff", bd=1, relief="solid")
            lbl.pack()
            self._photo_refs.append(photo)
        else:
            self._make_placeholder_ui(frame, name)
            
        ttk.Label(frame, text=label_txt, style="Small.TLabel", justify="center").pack(pady=2)
        return frame

    def _make_visual_placeholder(self, text: str):
        frame = ttk.Frame(self.visual_inner, style="Card.TFrame")
        self._make_placeholder_ui(frame, "임의의 패")
        ttk.Label(frame, text=text, style="Small.TLabel", justify="center").pack(pady=2)
        return frame
        
    def _make_placeholder_ui(self, parent, text):
        box = tk.Frame(parent, width=CARD_W, height=CARD_H, bg="#e9ecef", bd=1, relief="solid")
        box.pack_propagate(False)
        box.pack()
        tk.Label(box, text=text, bg="#e9ecef", font=("Malgun Gothic", 9, "bold"), wraplength=CARD_W-10).pack(expand=True)

if __name__ == "__main__":
    app = BrandedComboApp()
    app.mainloop()
