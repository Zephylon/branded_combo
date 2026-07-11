"""
Branded combo recommendation engine v5.1 (Fuzzy Matching & String Normalization)
"""
from __future__ import annotations

import json
import re
import sqlite3
import difflib
from collections import Counter
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Sequence

def normalize(s: Any) -> str:
    s = str(s)
    # 공백, &, ＆, [, ], -, _ 등 텍스트 불일치를 유발하는 모든 문자를 제거하고 소문자로 통일
    return re.sub(r"[\[\]\s\&＆\-\_]+", "", s).lower()

def load_data(path: str | Path) -> list:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data

def build_name_index(data: list) -> Dict[str, str]:
    index: Dict[str, str] = {}
    for combo in data:
        for section in ["필요한 파츠", "전개 중 필요한 메인 덱 카드", "전개 중 필요한 엑스트라 덱 카드", "반드시 덱에 있어야만 하는 카드"]:
            for card_name in combo.get(section, {}).keys():
                index[normalize(card_name)] = card_name
    return index

def canonicalize_card(card: str, name_index: Dict[str, str]) -> str:
    key = normalize(card)
    if key in name_index:
        return name_index[key]
    
    # 수정점 4: 오타 보정 (일치율 80% 이상 매핑)
    best_match = None
    highest_ratio = 0.0
    for known_key in name_index.keys():
        ratio = difflib.SequenceMatcher(None, key, known_key).ratio()
        if ratio >= 0.8 and ratio > highest_ratio:
            highest_ratio = ratio
            best_match = known_key
            
    if best_match:
        return name_index[best_match]
        
    return str(card).strip()

def canonicalize_cards(cards: Iterable[str], name_index: Dict[str, str]) -> List[str]:
    return [canonicalize_card(c, name_index) for c in cards if str(c).strip()]

def split_card_lines(text: str) -> List[str]:
    if not text:
        return []
    raw = re.split(r"[\n,;/]+", text)
    return [x.strip() for x in raw if x.strip()]

def normalize_passcode(cid: Any) -> str:
    s = re.sub(r"\D", "", str(cid or ""))
    if not s:
        return ""
    try:
        return str(int(s))
    except Exception:
        return s.lstrip("0") or "0"

@dataclass
class YdkEntry:
    section: str
    passcode: str
    line_number: int
    index_in_section: int

@dataclass
class YdkDeck:
    path: str
    main_ids: List[str]
    extra_ids: List[str]
    side_ids: List[str]
    main_names: List[str]
    extra_names: List[str]
    side_names: List[str]
    unresolved_ids: List[str]

def parse_ydk_entries(path: str | Path) -> List[YdkEntry]:
    entries: List[YdkEntry] = []
    section = "main"
    counters = {"main": 0, "extra": 0, "side": 0}
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        for line_no, line in enumerate(f, 1):
            s = line.strip()
            if not s: continue
            low = s.lower()
            if low.startswith("#main"): section = "main"; continue
            if low.startswith("#extra"): section = "extra"; continue
            if low.startswith("!side"): section = "side"; continue
            if s.startswith("#") or not re.fullmatch(r"\d+", s): continue
            counters[section] += 1
            entries.append(YdkEntry(section=section, passcode=s, line_number=line_no, index_in_section=counters[section]))
    return entries

def load_names_from_cdb(cdb_path: str | Path) -> Dict[str, str]:
    mapping: Dict[str, str] = {}
    try:
        con = sqlite3.connect(str(cdb_path))
        cur = con.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "texts" in tables:
            cols = [r[1] for r in cur.execute("PRAGMA table_info(texts)").fetchall()]
            if "id" in cols and "name" in cols:
                for cid, name in cur.execute("SELECT id, name FROM texts"):
                    norm = normalize_passcode(cid)
                    if norm and name:
                        mapping[norm] = str(name)
                        mapping[str(cid)] = str(name)
        con.close()
    except Exception:
        pass
    return mapping

def find_cdb_files(base_dir: str | Path, extra_paths: Optional[Sequence[str | Path]] = None) -> List[Path]:
    base = Path(base_dir)
    candidates: List[Path] = []
    if extra_paths:
        for raw in extra_paths:
            p = Path(raw)
            if p.is_dir():
                candidates.extend(p.glob("**/*.cdb"))
            elif p.is_file():
                candidates.append(p)
    candidates.extend(base.glob("**/*.cdb"))
    seen = set()
    out = []
    for p in candidates:
        try: rp = p.resolve()
        except: continue
        if rp not in seen and rp.exists() and p.suffix.lower() == ".cdb":
            seen.add(rp)
            out.append(p)
    return out

def build_passcode_resolver(base_dir: str | Path, cdb_paths: Optional[Sequence[str | Path]] = None) -> Dict[str, str]:
    mapping = {}
    for cdb in find_cdb_files(base_dir, extra_paths=cdb_paths):
        mapping.update(load_names_from_cdb(cdb))
    return mapping

def load_ydk(path: str | Path, data: list, cdb_paths: Optional[Sequence[str | Path]] = None) -> YdkDeck:
    path = Path(path)
    name_index = build_name_index(data)
    id_to_name = build_passcode_resolver(path.parent, cdb_paths=cdb_paths)
    entries = parse_ydk_entries(path)
    
    unresolved = []
    def resolve(items):
        names = []
        for e in items:
            cid_raw = str(e.passcode)
            name = id_to_name.get(cid_raw) or id_to_name.get(normalize_passcode(cid_raw))
            if not name:
                unresolved.append(cid_raw)
                names.append(f"UNKNOWN:{cid_raw}")
            else:
                names.append(canonicalize_card(name, name_index))
        return names

    main_e = [e for e in entries if e.section == "main"]
    extra_e = [e for e in entries if e.section == "extra"]
    side_e = [e for e in entries if e.section == "side"]

    return YdkDeck(
        path=str(path),
        main_ids=[e.passcode for e in main_e], extra_ids=[e.passcode for e in extra_e], side_ids=[e.passcode for e in side_e],
        main_names=resolve(main_e), extra_names=resolve(extra_e), side_names=resolve(side_e),
        unresolved_ids=unresolved
    )

@dataclass
class Recommendation:
    combo_name: str
    priority_score: int
    disruptions: float
    disruption_display: str
    cost: int
    tags: str
    combo: dict
    missing_reasons: List[str]

def recommend(
    data: list,
    hand: Iterable[str],
    main_deck: Iterable[str],
    extra_deck: Iterable[str] = (),
    top_n: int = 5,
    prioritize_lock: bool = False,
    prioritize_cont: bool = False,
    exclude_old: bool = False,
) -> Tuple[List[Recommendation], List[Recommendation]]:
    
    name_index = build_name_index(data)
    hand_list = canonicalize_cards(hand, name_index)
    main_list = canonicalize_cards(main_deck, name_index)
    extra_list = canonicalize_cards(extra_deck, name_index)

    hand_counter = Counter(hand_list)
    main_counter = Counter(main_list)
    extra_counter = Counter(extra_list)

    valid_candidates: List[Recommendation] = []
    failed_candidates: List[Recommendation] = []

    for combo in data:
        reasons = []
        tags_raw = combo.get("특이점", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        if exclude_old and "구식" in tags:
            continue

        # 1. 필요 파츠 (패) 확인
        required_hand = combo.get("필요한 파츠", {})
        for req_name, req_cnt in required_hand.items():
            c_name = canonicalize_card(req_name, name_index)
            if hand_counter[c_name] < req_cnt:
                reasons.append(f"패 부족: {req_name}({req_cnt}장 필요)")

        # 2. 메인 덱 투입 확인
        req_main = combo.get("전개 중 필요한 메인 덱 카드", {})
        for req_name, req_cnt in req_main.items():
            c_name = canonicalize_card(req_name, name_index)
            if main_counter[c_name] < req_cnt:
                reasons.append(f"메인 덱 투입 부족: {req_name}(현재 {main_counter[c_name]}장, 필요 {req_cnt}장)")

        # 3. 엑스트라 덱 확인
        req_extra = combo.get("전개 중 필요한 엑스트라 덱 카드", {})
        for req_name, req_cnt in req_extra.items():
            c_name = canonicalize_card(req_name, name_index)
            if extra_counter[c_name] < req_cnt:
                reasons.append(f"엑스트라 덱 부족: {req_name}(현재 {extra_counter[c_name]}장, 필요 {req_cnt}장)")

        # 4. 반드시 덱에 있어야만 하는 카드 (패에 잡히면 안 됨)
        req_must = combo.get("반드시 덱에 있어야만 하는 카드", {})
        for req_name, req_cnt in req_must.items():
            c_name = canonicalize_card(req_name, name_index)
            available = main_counter[c_name] - hand_counter[c_name]
            if available < req_cnt:
                reasons.append(f"호감 파츠 패에 잡힘: {req_name}(덱 잔여 {available}장, 필요 {req_cnt}장)")

        # 5. 추가 소모패 확인
        cost = int(combo.get("추가 소모패", 0))
        total_needed_hand_cards = sum(required_hand.values()) + cost
        if len(hand_list) < total_needed_hand_cards:
            reasons.append(f"총 패 장수 부족 (필요: {total_needed_hand_cards}, 현재: {len(hand_list)})")

        disruptions = float(combo.get("견제 수", {}).get("시스템 수치", 0.0))
        disrupt_disp = combo.get("견제 수", {}).get("표시", str(disruptions))
        
        priority = 0
        if prioritize_lock and "락" in tags: priority = 1
        if prioritize_cont and "지속" in tags: priority = 1

        rec = Recommendation(
            combo_name=combo.get("전개법 이름", "이름 없음"),
            priority_score=priority,
            disruptions=disruptions,
            disruption_display=disrupt_disp,
            cost=cost,
            tags=tags_raw,
            combo=combo,
            missing_reasons=reasons
        )

        if reasons:
            failed_candidates.append(rec)
        else:
            valid_candidates.append(rec)

    valid_candidates.sort(key=lambda r: (r.priority_score, r.disruptions, -r.cost), reverse=True)
    return valid_candidates[:top_n], failed_candidates
