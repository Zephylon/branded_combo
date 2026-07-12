"""
Branded Deck Editor
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
from pathlib import Path
import sqlite3
from PIL import Image, ImageTk
from branded_combo_engine import find_cdb_files # 고정 파일명 참조

class DeckEditorWindow(tk.Toplevel):
    def __init__(self, master, cdb_paths, ydk_path=None, app_dir=None, pics_dirs=None):
        super().__init__(master)
        self.title("YDK 덱 편집기")
        self.geometry("1100x650")
        self.configure(bg="#F4F9F9")
        
        self.cdb_paths = cdb_paths
        self.current_ydk_path = ydk_path
        self.app_dir = app_dir or Path(".")
        self.pics_dirs = pics_dirs or []
        
        self.all_cards = [] 
        self.main_deck = []
        self.extra_deck = []
        self.side_deck = []
        
        self.TYPE_FUSION = 0x40
        self.TYPE_SYNCHRO = 0x2000
        self.TYPE_XYZ = 0x800000
        self.TYPE_LINK = 0x4000000
        self.TYPE_EXTRA = self.TYPE_FUSION | self.TYPE_SYNCHRO | self.TYPE_XYZ | self.TYPE_LINK
        
        self.photo_ref = None 
        
        self._load_database()
        self._build_ui()
        if self.current_ydk_path and Path(self.current_ydk_path).exists():
            self._load_ydk(self.current_ydk_path)

    def _load_database(self):
        seen_ids = set()
        actual_cdb_files = find_cdb_files(self.app_dir, self.cdb_paths)
        
        for cdb in actual_cdb_files:
            try:
                con = sqlite3.connect(str(cdb))
                cur = con.cursor()
                tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
                if "texts" in tables and "datas" in tables:
                    for r in cur.execute("SELECT datas.id, texts.name, texts.desc, datas.type FROM datas JOIN texts ON datas.id = texts.id").fetchall():
                        cid = str(r[0])
                        if cid not in seen_ids:
                            seen_ids.add(cid)
                            self.all_cards.append({"id": cid, "name": r[1], "desc": r[2], "type": r[3]})
                con.close()
            except Exception:
                pass
        self.all_cards.sort(key=lambda x: x["name"])

    def _build_ui(self):
        style = ttk.Style(self)
        style.configure("Pastel.TFrame", background="#F4F9F9")
        style.configure("Pastel.TLabelframe", background="#F4F9F9")
        style.configure("Pastel.TLabelframe.Label", background="#F4F9F9", font=("Malgun Gothic", 10, "bold"))
        
        main_frame = ttk.Frame(self, padding=10, style="Pastel.TFrame")
        main_frame.pack(fill="both", expand=True)
        
        # Left Panel
        info_frame = ttk.LabelFrame(main_frame, text="카드 정보", padding=10, style="Pastel.TLabelframe")
        info_frame.pack(side="left", fill="y", padx=(0, 10))
        
        self.img_container = tk.Frame(info_frame, width=180, height=262, bg="#F4F9F9")
        self.img_container.pack(pady=(0, 10))
        self.img_container.pack_propagate(False)
        
        self.img_lbl = tk.Label(self.img_container, bg="#F4F9F9", text="이미지\n없음", font=("Malgun Gothic", 9))
        self.img_lbl.pack(expand=True, fill="both")
        
        self.desc_text = ScrolledText(info_frame, width=30, height=15, font=("Malgun Gothic", 9), wrap="word", bg="#ffffe6") 
        self.desc_text.pack(fill="both", expand=True)
        self.desc_text.insert("1.0", "카드를 선택하면 정보가 표시됩니다.")
        self.desc_text.config(state="disabled")

        # Middle Panel
        search_frame = ttk.LabelFrame(main_frame, text="카드 검색", padding=10, style="Pastel.TLabelframe")
        search_frame.pack(side="left", fill="both", expand=True, padx=(0, 10))
        
        search_row = ttk.Frame(search_frame, style="Pastel.TFrame")
        search_row.pack(fill="x", pady=(0, 5))
        self.search_var = tk.StringVar()
        self.search_var.trace("w", self._on_search_change)
        ttk.Entry(search_row, textvariable=self.search_var).pack(side="left", fill="x", expand=True)
        
        self.result_list = tk.Listbox(search_frame, font=("Malgun Gothic", 10), bg="#e6f7ff") 
        self.result_list.pack(fill="both", expand=True)
        self.result_list.bind("<Double-Button-1>", self._add_card)
        self.result_list.bind("<<ListboxSelect>>", lambda e: self._on_select_card(self.result_list, self.current_results))
        self._update_search_results("")
        
        # Guide
        mid_lbl_frame = ttk.Frame(main_frame, style="Pastel.TFrame")
        mid_lbl_frame.pack(side="left", fill="y", padx=5)
        tk.Label(mid_lbl_frame, text="▶\n더블클릭\n추가", bg="#F4F9F9", fg="#888", font=("Malgun Gothic", 9, "bold")).pack(pady=150)

        # Right Panel
        deck_frame = ttk.Frame(main_frame, style="Pastel.TFrame")
        deck_frame.pack(side="left", fill="both", expand=True)
        
        self.notebook = ttk.Notebook(deck_frame)
        self.notebook.pack(fill="both", expand=True, pady=(0, 10))
        
        self.main_list = tk.Listbox(self.notebook, font=("Malgun Gothic", 10), bg="#fcf2f2")
        self.extra_list = tk.Listbox(self.notebook, font=("Malgun Gothic", 10), bg="#f1f0ff") 
        self.side_list = tk.Listbox(self.notebook, font=("Malgun Gothic", 10), bg="#f4f9f4") 
        
        self.notebook.add(self.main_list, text="메인 덱")
        self.notebook.add(self.extra_list, text="엑스트라 덱")
        self.notebook.add(self.side_list, text="사이드 덱")
        
        self.main_list.bind("<Double-Button-1>", lambda e: self._remove_card("main"))
        self.extra_list.bind("<Double-Button-1>", lambda e: self._remove_card("extra"))
        self.side_list.bind("<Double-Button-1>", lambda e: self._remove_card("side"))
        
        self.main_list.bind("<<ListboxSelect>>", lambda e: self._on_select_card(self.main_list, self.main_deck))
        self.extra_list.bind("<<ListboxSelect>>", lambda e: self._on_select_card(self.extra_list, self.extra_deck))
        self.side_list.bind("<<ListboxSelect>>", lambda e: self._on_select_card(self.side_list, self.side_deck))

        btn_row = ttk.Frame(deck_frame, style="Pastel.TFrame")
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="저장", command=self._save_deck).pack(side="right", padx=5)
        ttk.Button(btn_row, text="다른 이름으로 저장", command=self._save_as_deck).pack(side="right")
        self.status_lbl = tk.Label(btn_row, text="", bg="#F4F9F9", fg="#555")
        self.status_lbl.pack(side="left")

    def _on_search_change(self, *args):
        self._update_search_results(self.search_var.get())

    def _update_search_results(self, query):
        self.result_list.delete(0, tk.END)
        self.current_results = []
        q = query.lower().replace(" ", "")
        for c in self.all_cards:
            if q in c["name"].lower().replace(" ", ""):
                self.current_results.append(c)
                self.result_list.insert(tk.END, c["name"])
                if len(self.current_results) > 100: break

    def _on_select_card(self, listbox, data_list):
        sel = listbox.curselection()
        if not sel: return
        card = data_list[sel[0]]
        self._display_card_info(card)

    def _display_card_info(self, card):
        self.desc_text.config(state="normal")
        self.desc_text.delete("1.0", tk.END)
        self.desc_text.insert("1.0", f"[{card['name']}]\n\n{card['desc']}")
        self.desc_text.config(state="disabled")
        
        self.photo_ref = None
        cid = card["id"]
        img_path = None
        
        for pdir in self.pics_dirs:
            for ext in [".jpg", ".png"]:
                p = Path(pdir) / f"{cid}{ext}"
                if p.exists():
                    img_path = p
                    break
            if img_path: break
            
        if img_path and Image:
            try:
                im = Image.open(img_path)
                im.thumbnail((180, 262))
                self.photo_ref = ImageTk.PhotoImage(im)
                self.img_lbl.config(image=self.photo_ref, text="")
            except Exception:
                self.img_lbl.config(image='', text="이미지 로드 실패")
        else:
            self.img_lbl.config(image='', text="이미지 없음")

    def _add_card(self, event):
        sel = self.result_list.curselection()
        if not sel: return
        card = self.current_results[sel[0]]
        
        if card["type"] & self.TYPE_EXTRA:
            self.extra_deck.append(card)
        else:
            self.main_deck.append(card)
        self._refresh_deck_lists()

    def _remove_card(self, deck_type):
        if deck_type == "main":
            sel = self.main_list.curselection()
            if sel: self.main_deck.pop(sel[0])
        elif deck_type == "extra":
            sel = self.extra_list.curselection()
            if sel: self.extra_deck.pop(sel[0])
        elif deck_type == "side":
            sel = self.side_list.curselection()
            if sel: self.side_deck.pop(sel[0])
        self._refresh_deck_lists()

    def _refresh_deck_lists(self):
        self.main_list.delete(0, tk.END)
        for c in self.main_deck: self.main_list.insert(tk.END, c["name"])
        self.extra_list.delete(0, tk.END)
        for c in self.extra_deck: self.extra_list.insert(tk.END, c["name"])
        self.side_list.delete(0, tk.END)
        for c in self.side_deck: self.side_list.insert(tk.END, c["name"])
        
        self.notebook.tab(0, text=f"메인 덱 ({len(self.main_deck)})")
        self.notebook.tab(1, text=f"엑스트라 덱 ({len(self.extra_deck)})")
        self.notebook.tab(2, text=f"사이드 덱 ({len(self.side_deck)})")

    def _load_ydk(self, path):
        id_dict = {c["id"]: c for c in self.all_cards}
        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            section = "main"
            for line in f:
                s = line.strip()
                if not s: continue
                if s.startswith("#main"): section = "main"; continue
                if s.startswith("#extra"): section = "extra"; continue
                if s.startswith("!side"): section = "side"; continue
                if s.startswith("#") or not s.isdigit(): continue
                
                cid = str(int(s))
                if cid in id_dict:
                    if section == "main": self.main_deck.append(id_dict[cid])
                    elif section == "extra": self.extra_deck.append(id_dict[cid])
                    elif section == "side": self.side_deck.append(id_dict[cid])
        self._refresh_deck_lists()
        self.status_lbl.config(text=f"불러옴: {Path(path).name}")

    def _save_deck(self):
        if not self.current_ydk_path:
            self._save_as_deck()
            return
        self._write_ydk(self.current_ydk_path)

    def _save_as_deck(self):
        p = filedialog.asksaveasfilename(defaultextension=".ydk", filetypes=[("YDK", "*.ydk")])
        if p:
            self.current_ydk_path = p
            self._write_ydk(p)

    def _write_ydk(self, path):
        with open(path, "w", encoding="utf-8") as f:
            f.write("#created by Branded Deck Editor\n")
            f.write("#main\n")
            for c in self.main_deck: f.write(f"{c['id']}\n")
            f.write("#extra\n")
            for c in self.extra_deck: f.write(f"{c['id']}\n")
            f.write("!side\n")
            for c in self.side_deck: f.write(f"{c['id']}\n")
        self.status_lbl.config(text=f"저장 완료: {Path(path).name}")
        messagebox.showinfo("저장", "YDK 덱 저장이 완료되었습니다.")

def launch_editor(master, cdb_paths, ydk_path=None, app_dir=None, pics_dirs=None):
    DeckEditorWindow(master, cdb_paths, ydk_path, app_dir, pics_dirs)
