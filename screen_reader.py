"""
Screen Reader for YGO Branded Combo Recommender (Up to 9 cards support)
"""
import cv2
import numpy as np
from pathlib import Path

def get_card_image_path(cid, pics_dirs):
    for pdir in pics_dirs:
        for ext in [".jpg", ".png", ".jpeg"]:
            p = Path(pdir) / f"{cid}{ext}"
            if p.exists():
                return str(p)
    return None

def recognize_hand_from_image(pil_image, main_ids, pics_dirs, expected_cards=9):
    screen_np = np.array(pil_image)
    
    if len(screen_np.shape) == 3:
        if screen_np.shape[2] == 4:
            screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_RGBA2GRAY)
        else:
            screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_RGB2GRAY)
    else:
        screen_gray = screen_np

    sift = cv2.SIFT_create()
    kp_screen, des_screen = sift.detectAndCompute(screen_gray, None)

    if des_screen is None or len(kp_screen) == 0:
        return []

    bf = cv2.BFMatcher()
    card_scores = []
    unique_ids = list(set(main_ids))
    
    for cid in unique_ids:
        img_path = get_card_image_path(cid, pics_dirs)
        if not img_path:
            continue
            
        img_array = np.fromfile(img_path, np.uint8)
        if img_array.size == 0:
            continue
        template = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
        
        if template is None:
            continue
            
        th, tw = template.shape
        art_roi = template[int(th*0.15):int(th*0.55), int(tw*0.15):int(tw*0.85)]
        
        kp_temp, des_temp = sift.detectAndCompute(art_roi, None)
        if des_temp is None or len(kp_temp) == 0:
            continue
            
        matches = bf.knnMatch(des_temp, des_screen, k=2)
        
        good_matches = []
        for m_n in matches:
            if len(m_n) == 2:
                m, n = m_n
                if m.distance < 0.75 * n.distance:
                    good_matches.append(m)
        
        if len(good_matches) >= 3:
            x_coords = [kp_screen[m.trainIdx].pt[0] for m in good_matches]
            x_coords.sort()
            
            clusters = []
            current_cluster = [x_coords[0]]
            for x in x_coords[1:]:
                # 패가 많아지면 간격이 좁아지므로 군집화 거리를 70픽셀로 약간 타이트하게 조정
                if x - current_cluster[-1] < 70:
                    current_cluster.append(x)
                else:
                    clusters.append(current_cluster)
                    current_cluster = [x]
            clusters.append(current_cluster)
            
            valid_clusters = [c for c in clusters if len(c) >= 3]
            
            for _ in valid_clusters:
                card_scores.append({"cid": cid, "score": len(good_matches)})

    card_scores.sort(key=lambda x: x["score"], reverse=True)
    return [item["cid"] for item in card_scores[:expected_cards]]
