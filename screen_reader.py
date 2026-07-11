"""
Screen Reader for YGO Branded Combo Recommender (Korean Path Fix + SIFT)
- 윈도우 한글 경로 인식 불가 버그를 numpy imdecode를 통해 우회하여 해결한 버전입니다.
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

def recognize_hand_from_image(pil_image, main_ids, pics_dirs, expected_cards=5):
    # PIL 이미지를 OpenCV용 numpy 배열로 변환
    screen_np = np.array(pil_image)
    
    # 알파 채널(RGBA) 예외 처리 후 그레이스케일 변환
    if len(screen_np.shape) == 3:
        if screen_np.shape[2] == 4:
            screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_RGBA2GRAY)
        else:
            screen_gray = cv2.cvtColor(screen_np, cv2.COLOR_RGB2GRAY)
    else:
        screen_gray = screen_np

    # SIFT 알고리즘 초기화
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
            
        # [핵심 수정] 한글 경로 문제 해결: numpy로 바이너리 데이터를 먼저 읽은 후 cv2로 디코딩
        img_array = np.fromfile(img_path, np.uint8)
        if img_array.size == 0:
            continue
        template = cv2.imdecode(img_array, cv2.IMREAD_GRAYSCALE)
        
        if template is None:
            continue
            
        # 마스터 듀얼의 UI 간섭을 최소화하기 위해 순수 일러스트 영역만 크롭
        th, tw = template.shape
        art_roi = template[int(th*0.15):int(th*0.55), int(tw*0.15):int(tw*0.85)]
        
        kp_temp, des_temp = sift.detectAndCompute(art_roi, None)
        if des_temp is None or len(kp_temp) == 0:
            continue
            
        # knnMatch를 통해 가장 유사한 특징점 2개를 뽑아 비교
        matches = bf.knnMatch(des_temp, des_screen, k=2)
        
        # Lowe's ratio test: 확실하게 매칭된 특징점만 필터링
        good_matches = []
        for m_n in matches:
            if len(m_n) == 2:
                m, n = m_n
                if m.distance < 0.75 * n.distance:
                    good_matches.append(m)
        
        # 확실한 특징점이 3개 이상 잡히면 카드 존재 확인
        if len(good_matches) >= 3:
            x_coords = [kp_screen[m.trainIdx].pt[0] for m in good_matches]
            x_coords.sort()
            
            clusters = []
            current_cluster = [x_coords[0]]
            for x in x_coords[1:]:
                if x - current_cluster[-1] < 80:
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
