import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import os
from urllib.parse import urljoin

# 1. 키워드 기반 자동 분류 함수 (기존 로직 동일)
def guess_category(text):
    if any(k in text for k in ['냉방', '에어컨', '선풍기', '인버터', '압축기']): return '냉방설비'
    if any(k in text for k in ['단열', '창호', '외풍', '리모델링', '변압기']): return '단열 불량'
    if any(k in text for k in ['보일러', '난방', '연탄']): return '난방설비'
    if any(k in text for k in ['태양광', '신재생', '친환경', '햇빛']): return '친환경 설비'
    if any(k in text for k in ['온실가스', '감축', '탄소']): return '절약시설'
    return '운영 습관'

def guess_level(need_text):
    if any(k in need_text for k in ['어려움', '사업자', '확인서', '증명서', '공사']): return '어려움'
    if any(k in need_text for k in ['신청서', '주민등록', '보조금', '제출', '공문']): return '중간'
    if need_text == "상세내용확인필요" or not need_text: return "확인필요"
    return '쉬움'

# 2. 메인 크롤링 함수
def update_rag_data_from_web():
    base_url = "https://www.e-policy.or.kr/web/lay1/program/S1T9C14/curation/list.do"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    response = requests.get(base_url, headers=headers)
    
    if response.status_code != 200:
        print(f"상태 코드 오류: {response.status_code}")
        return

    soup = BeautifulSoup(response.text, 'html.parser')
    cards = soup.select('a.curating__con')
    data = []
    
    print(f"총 {len(cards)}개의 정책 목록을 발견했습니다. 상세 데이터 추출을 시작합니다...\n")
    
    for idx, card in enumerate(cards):
        # 1차 정보: 리스트 페이지 추출
        raw_text = card.select_one('p.tit').text.strip()
        clean_title = re.sub(r'\[D-\d+\]|\[마감\]', '', raw_text).strip()
        
        target = "확인필요"
        takes = "확인필요"
        apply_time = "확인필요"
        
        wraps = card.select('.txt-wrap')
        for wrap in wraps:
            tit_tag = wrap.select_one('p.tit')
            txt_tag = wrap.select_one('p.txt')
            
            if tit_tag and txt_tag:
                tit_val = tit_tag.text.strip()
                txt_val = txt_tag.text.strip()
                
                if "지원대상" in tit_val:
                    target = txt_val
                elif "지원혜택" in tit_val:
                    takes = txt_val
                elif "신청기간" in tit_val:
                    apply_time = txt_val
        
        # URL 추출 
        link = urljoin(base_url, card.get('href'))
        
        # 2차 정보: 기본값 세팅
        action_des = "상세내용확인필요"
        need = "상세내용확인필요"
        source = "한국에너지정보문화재단"
        final_url = link 
        
        print(f"[{idx+1}/{len(cards)}] 수집 중: {clean_title}")
        
        try:
            detail_res = requests.get(link, headers=headers)
            if detail_res.status_code == 200:
                detail_soup = BeautifulSoup(detail_res.text, 'html.parser')
                
                # 사이트 바로가기 버튼 및 URL 매핑
                site_btn = detail_soup.find(lambda tag: tag.name == 'a' and ('사이트 바로가기' in tag.get_text() or '홈페이지' in tag.get_text()))
                if site_btn and site_btn.get('href'):
                    source_url = site_btn.get('href')
                    final_url = source_url 
                    
                    domain_dict = {
                        "mois.go.kr": "행정안전부", "motie.go.kr": "산업통상자원부", 
                        "energy.or.kr": "한국에너지공단", "kepco.co.kr": "한국전력공사",
                        "seoul.go.kr": "서울특별시", "gg.go.kr": "경기도",
                        "https://www.nowon.kr/www/user/bbs/BD_selectBbs.do?q_bbsCode=1003&q_bbscttSn=20260406114143655&q_estnColumn7=&q_estnColumn1=11&q_ntceSiteCode=11&q_clCode=0&q_rowPerPage=10&q_currPage=1&q_sortName=&q_sortOrder=&q_searchKeyTy=sj___1002&q_searchVal=&":"노원구청",
                        "https://www.gg.go.kr/bbs/boardView.do?bIdx=230465845&bsIdx=469&bcIdx=0&menuId=1547&isManager=false&isCharge=false&keyfield=SUBJECTANDREMARK&keyword=%EC%97%90%EB%84%88%EC%A7%80&page=1":"경기도청",
                        "https://www.bokjiro.go.kr/":"보건복지부, 복지로",
                        "https://www.energy.or.kr/":"한국에너지공단",
                        "https://koat2026.careeron.co.kr/#/":"한국농업기술진흥원",
                        "https://online.kepco.co.kr/":"한국전력공사",
                        "https://blog.naver.com/dongjaksaran/224246740448":"동작구청"
                    }
                    matched_source = None
                    for domain, org_name in domain_dict.items():
                        if domain in source_url:
                            matched_source = org_name
                            break
                    source = matched_source if matched_source else source_url
                
                content_area = detail_soup.select_one('.content')
                if content_area:
                    full_text = content_area.get_text(separator=" ", strip=True)
                    
                    # 지원내용
                    if '지원내용' in full_text:
                        chunk = full_text.split('지원내용')[1] 
                        for cutoff in ['관련정보', '신청방법', '신청기간', '목록으로']:
                            if cutoff in chunk:
                                chunk = chunk.split(cutoff)[0]
                        action_des = chunk.strip()
                        
                    # 신청방법
                    if '신청방법' in full_text:
                        chunk = full_text.split('신청방법')[1] 
                        for cutoff in ['문의처', '유의사항', '목록으로', '사이트 바로가기']:
                            if cutoff in chunk:
                                chunk = chunk.split(cutoff)[0]
                        need = chunk.strip()
                        
        except Exception as e:
            print(f"  -> 오류 발생: {e}")
            
        time.sleep(1) # 대기
        
        # 3차 정보: 가공 및 요약
        search_context = clean_title + " " + action_des
        cause_val = guess_category(search_context)
        level_val = guess_level(need)
        action_name = clean_title[:15] + ("..." if len(clean_title) > 15 else "")
        
        data.append({
            "cause": cause_val,
            "name": clean_title,
            "url": final_url,
            "target": target,
            "action_name": action_name,
            "action_des": action_des,
            "source": source,
            "takes": takes,
            "time": apply_time,
            "need": need,
            "level": level_val,
            "saving": "기존 설비 대비 절감 (추정)"
        })
        
    # 전송 로직
    # 결과 저장용 DataFrame 생성 및 공백문자 전처리
    new_df = pd.DataFrame(data)
    new_df = new_df.replace('\xa0', ' ', regex=True) 

    # 크롤링한 데이터를 JSON으로 변환
    json_data = new_df.to_dict(orient='records')
    
    # 백엔드담당자가 알려줄 API 주소
    backend_url = os.environ.get("BACKEND_URL", "http://백엔드_API_주소/api/crawling")
    
    print(f"\n총 {len(data)}개의 데이터를 추출 완료했습니다.")
    print("백엔드로 데이터를 전송합니다...")
    
    try:
        # 데이터 POST 전송
        res = requests.post(backend_url, json={"new_data": json_data})
        if res.status_code in [200, 201]:
            print("데이터 전송 완료! 🎉")
        else:
            print(f"전송 실패 (상태 코드: {res.status_code}): {res.text}")
    except Exception as e:
        print(f"백엔드 연결 에러 발생: {e}")

# 파이썬 함수를 작동
if __name__ == "__main__":
    update_rag_data_from_web()