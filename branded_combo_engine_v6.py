"""
Branded combo recommendation engine v6
"""
from __future__ import annotations

import json
import re
import sqlite3
import difflib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple, Sequence

# CDB 비트마스크 상수
TYPE_MONSTER = 0x1
TYPE_SPELL = 0x2
TYPE_TRAP = 0x4

RACE_MAP = {
    "전사족": 0x1, "마법사족": 0x2, "천사족": 0x4, "악마족": 0x8, 
    "언데드족": 0x10, "기계족": 0x20, "물족": 0x40, "화염족": 0x80, 
    "암석족": 0x100, "비행야수족": 0x200, "식물족": 0x400, "곤충족": 0x800, 
    "번개족": 0x1000, "드래곤족": 0x2000, "야수족": 0x4000, "야수전사족": 0x8000, 
    "공룡족": 0x10000, "어류족": 0x20000, "해룡족": 0x40000, "파충류족": 0x80000, 
    "사이킥족": 0x100000, "환룡족": 0x800000, "사이버스족": 0x1000000, "환상마족": 0x2000000
}

def normalize(s: Any) -> str:
    s = str(s)
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
    full_db: Dict[str, str] = field(default_factory=dict)
    name_to_data: Dict[str, dict] = field(default_factory=dict)

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

def load_db_from_cdb(cdb_path: str | Path) -> Dict[str, dict]:
    mapping = {}
    try:
        con = sqlite3.connect(str(cdb_path))
        cur = con.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "texts" in tables and "datas" in tables:
            texts = {str(r[0]): r[1] for r in cur.execute("SELECT id, name FROM texts").fetchall()}
            for r in cur.execute("SELECT id, type, race, setcode FROM datas").fetchall():
                cid = str(r[0])
                name = texts.get(cid, "")
                if name:
                    norm_cid = normalize_passcode(cid)
                    data = {"name": name, "type": r[1], "race": r[2], "setcode": r[3]}
                    mapping[norm_cid] = data
                    mapping[cid] = data
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

def build_passcode_resolver(base_dir: str | Path, cdb_paths: Optional[Sequence[str | Path]] = None) -> Dict[str, dict]:
    mapping = {}
    for cdb in find_cdb_files(base_dir, extra_paths=cdb_paths):
        mapping.update(load_db_from_cdb(cdb))
    return mapping

def load_ydk(path: str | Path, data: list, cdb_paths: Optional[Sequence[str | Path]] = None) -> YdkDeck:
    path = Path(path)
    name_index = build_name_index(data)
    id_to_data = build_passcode_resolver(path.parent, cdb_paths=cdb_paths)
    entries = parse_ydk_entries(path)
    
    unresolved = []
    name_to_data = {}
    
    # name_to_data 매핑 생성 (카드 데이터를 이름으로 검색할 수 있게 만듦)
    for cid, cdata in id_to_data.items():
        c_name = canonicalize_card(cdata["name"], name_index)
        name_to_data[c_name] = cdata
        
    def resolve(items):
        names = []
        for e in items:
            cid_raw = str(e.passcode)
            cdata = id_to_data.get(cid_raw) or id_to_data.get(normalize_passcode(cid_raw))
            if not cdata:
                unresolved.append(cid_raw)
                names.append(f"UNKNOWN:{cid_raw}")
            else:
                names.append(canonicalize_card(cdata["name"], name_index))
        return names

    main_e = [e for e in entries if e.section == "main"]
    extra_e = [e for e in entries if e.section == "extra"]
    side_e = [e for e in entries if e.section == "side"]

    full_db_names = {cid: cdata["name"] for cid, cdata in id_to_data.items()}

    return YdkDeck(
        path=str(path),
        main_ids=[e.passcode for e in main_e], extra_ids=[e.passcode for e in extra_e], side_ids=[e.passcode for e in side_e],
        main_names=resolve(main_e), extra_names=resolve(extra_e), side_names=resolve(side_e),
        unresolved_ids=unresolved,
        full_db=full_db_names,
        name_to_data=name_to_data
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
    name_to_data: Dict[str, dict], # YDK에서 가져온 카드 상세 정보
    extra_deck: Iterable[str] = (),
    top_n: int = 5,
    prioritize_lock: bool = False,
    prioritize_cont: bool = False,
    exclude_old: bool = False,
    no_extra_cost: bool = False,
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

    albaz_name = canonicalize_card("알버스의 낙윤", name_index)
    white_albaz_name = canonicalize_card("하얀 용의 낙윤", name_index)

    def get_count(counter: Counter, target: str) -> int:
        if target == albaz_name and albaz_name != white_albaz_name:
            return counter[albaz_name] + counter[white_albaz_name]
        return counter[target]

    for combo in data:
        reasons = []
        tags_raw = combo.get("특이점", "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]

        if exclude_old and "구식" in tags:
            continue

        # 1. 고정된 파츠 소모 검사
        available_hand = hand_list[:]
        required_hand = combo.get("필요한 파츠", {})
        
        for req_name, req_cnt in required_hand.items():
            c_name = canonicalize_card(req_name, name_index)
            if get_count(hand_counter, c_name) < req_cnt:
                reasons.append(f"패 부족: {req_name}({req_cnt}장 필요)")
            else:
                # 조건부 파츠 연산을 위해 사용된 카드는 남은 패에서 제거
                for _ in range(req_cnt):
                    if c_name == albaz_name and albaz_name != white_albaz_name:
                        if albaz_name in available_hand: available_hand.remove(albaz_name)
                        elif white_albaz_name in available_hand: available_hand.remove(white_albaz_name)
                    else:
                        if c_name in available_hand: available_hand.remove(c_name)

        # 2. 조건부 필요 파츠 검사 (신규 기능)
        conditional_parts = combo.get("조건부 필요 파츠", [])
        for cond in conditional_parts:
            desc = cond.get("설명", "조건부 카드")
            req_cnt = cond.get("수량", 1)
            req_races = cond.get("종족", [])
            req_types = cond.get("종류", [])
            req_name_inc = cond.get("이름포함", "")

            matched_count = 0
            for card_name in list(available_hand):
                c_data = name_to_data.get(card_name)
                if not c_data: continue

                type_match = True
                if req_types:
                    type_match = False
                    if "몬스터" in req_types and (c_data["type"] & TYPE_MONSTER): type_match = True
                    if "마법" in req_types and (c_data["type"] & TYPE_SPELL): type_match = True
                    if "함정" in req_types and (c_data["type"] & TYPE_TRAP): type_match = True

                race_match = True
                if req_races:
                    race_match = False
                    for r in req_races:
                        if r in RACE_MAP and (c_data["race"] & RACE_MAP[r]):
                            race_match = True
                            break

                name_match = True
                if req_name_inc and req_name_inc not in c_data["name"]:
                    name_match = False

                if type_match and race_match and name_match:
                    matched_count += 1
                    available_hand.remove(card_name)
                    if matched_count >= req_cnt:
                        break
            
            if matched_count < req_cnt:
                reasons.append(f"패 부족 (조건부): {desc}({req_cnt}장 필요)")

        # 3. 덱 파츠 검사
        req_main = combo.get("전개 중 필요한 메인 덱 카드", {})
        for req_name, req_cnt in req_main.items():
            c_name = canonicalize_card(req_name, name_index)
            avail = get_count(main_counter, c_name)
            if avail < req_cnt:
                reasons.append(f"메인 덱 투입 부족: {req_name}(현재 {avail}장, 필요 {req_cnt}장)")

        req_extra = combo.get("전개 중 필요한 엑스트라 덱 카드", {})
        for req_name, req_cnt in req_extra.items():
            c_name = canonicalize_card(req_name, name_index)
            if get_count(extra_counter, c_name) < req_cnt:
                reasons.append(f"엑스트라 덱 부족: {req_name}(현재 {get_count(extra_counter, c_name)}장, 필요 {req_cnt}장)")

        req_must = combo.get("반드시 덱에 있어야만 하는 카드", {})
        for req_name, req_cnt in req_must.items():
            c_name = canonicalize_card(req_name, name_index)
            available = get_count(main_counter, c_name) - get_count(hand_counter, c_name)
            if available < req_cnt:
                reasons.append(f"호감 파츠 패에 잡힘: {req_name}(덱 잔여 {available}장, 필요 {req_cnt}장)")

        # 4. 추가 코스트 검사
        cost = int(combo.get("추가 소모패", 0))
        cond_cnt = sum(c.get("수량", 1) for c in conditional_parts)
        total_needed_hand_cards = sum(required_hand.values()) + cond_cnt + cost
        
        if len(hand_list) < total_needed_hand_cards:
            reasons.append(f"총 패 장수 부족 (필요: {total_needed_hand_cards}, 현재: {len(hand_list)})")

        if no_extra_cost and cost > 0:
            reasons.append(f"조건 미달: 추가 코스트 발생({cost}장)")

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
    failed_candidates.sort(key=lambda r: (len(r.missing_reasons), -r.disruptions))
    
    return valid_candidates[:top_n], failed_candidates
