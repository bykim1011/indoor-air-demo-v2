# -*- coding: utf-8 -*-
"""
Created on Tue Jun 23 10:11:52 2026

@author: Admin
"""

# app_v2.py
# ------------------------------------------------------------
# 실내공기질 안내서비스 2차 웹 데모
# 평리3동복지센터 설치 예정 장비 화면 예시
#
# 기능:
# 1. 실내/실외 공기질 좌우 비교
# 2. PM2.5, PM10 등급 판정
# 3. 얼굴 아이콘 + 색상 카드
# 4. 오늘의 대기질 안내판형 등급표
# 5. 행동요령 표시
# 6. 이용자 반응 버튼 저장
# 7. 향후 AirKorea API / 실내 간이측정기 연동 가능 구조
# ------------------------------------------------------------
from bs4 import BeautifulSoup
import streamlit as st
import pandas as pd
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
import math

# ============================================================
# 1. 기본 설정
# ============================================================

st.set_page_config(
    page_title="실내공기질 안내서비스 2차 데모",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed"
)

KST = timezone(timedelta(hours=9))

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

FEEDBACK_FILE = DATA_DIR / "user_feedback_log.csv"
# 대구 서구 행정동 행정복지센터 기준 좌표
seogu_location_options = {
    "내당1동": {
        "address": "대구광역시 서구 서대구로4길 35",
        "lat": 35.86063650,
        "lon": 128.56069310
    },
    "내당2·3동": {
        "address": "대구광역시 서구 달구벌대로375길 27, 다우빌딩 2층",
        "lat": 35.86727483,
        "lon": 128.57453230
    },
    "내당4동": {
        "address": "대구광역시 서구 서대구로3길 46",
        "lat": 35.85902046,
        "lon": 128.55184330
    },
    "비산1동": {
        "address": "대구광역시 서구 북비산로65길 18",
        "lat": 35.88117120,
        "lon": 128.56896960
    },
    "비산2·3동": {
        "address": "대구광역시 서구 국채보상로81길 43",
        "lat": 35.87581379,
        "lon": 128.57479480
    },
    "비산4동": {
        "address": "대구광역시 서구 국채보상로78길 29-4",
        "lat": 35.86975923,
        "lon": 128.57430750
    },
    "비산5동": {
        "address": "대구광역시 서구 달서천로65길 17",
        "lat": 35.88632435,
        "lon": 128.56964210
    },
    "비산6동": {
        "address": "대구광역시 서구 문화로67길 3",
        "lat": 35.87630025,
        "lon": 128.56909400
    },
    "비산7동": {
        "address": "대구광역시 서구 염색공단로5길 4",
        "lat": 35.88797180,
        "lon": 128.55357420
    },
    "상중이동": {
        "address": "대구광역시 서구 당산로 343",
        "lat": 35.86697580,
        "lon": 128.54611410
    },
    "원대동": {
        "address": "대구광역시 서구 달서로 257",
        "lat": 35.88514100,
        "lon": 128.57352980
    },
    "평리1동": {
        "address": "대구광역시 서구 문화로 280",
        "lat": 35.87559866,
        "lon": 128.56326350
    },
    "평리2동": {
        "address": "대구광역시 서구 국채보상로60길 6",
        "lat": 35.87121857,
        "lon": 128.56368700
    },
    "평리3동": {
        "address": "대구광역시 서구 서대구로42길 52",
        "lat": 35.87679660,
        "lon": 128.56083900
    },
    "평리4동": {
        "address": "대구광역시 서구 국채보상로46길 37-3",
        "lat": 35.86734009,
        "lon": 128.55678170
    },
    "평리5동": {
        "address": "대구광역시 서구 문화로 160",
        "lat": 35.87451714,
        "lon": 128.55046030
    },
    "평리6동": {
        "address": "대구광역시 서구 서대구로41길 41",
        "lat": 35.87657200,
        "lon": 128.54999040
    }
}

air_station_locations = {
    "내당동": {
        "address": "대구광역시 서구 서대구로3길 46",
        "place": "내당4동 행정복지센터",
        "lat": 35.85902046,
        "lon": 128.55184330
    },
    "이현동": {
        "address": "대구광역시 서구 국채보상로 135",
        "place": "중리초등학교",
        "lat": 35.8695524,
        "lon": 128.5453239
    },
    "평리동": {
        "address": "대구광역시 서구 통학로 217",
        "place": "대평중학교",
        "lat": 35.8802764,
        "lon": 128.5624917
    },
}

def get_kst_now():
    return datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")

@st.cache_data(ttl=1200)
def fetch_airkorea_realtime(station_name):
    """
    AirKorea 측정소별 실시간 측정정보 조회
    """

    service_key = st.secrets.get("AIRKOREA_SERVICE_KEY", "")

    if service_key == "":
        return {
            "success": False,
            "error": "AIRKOREA_SERVICE_KEY가 secrets.toml에 없습니다."
        }

    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"

    params = {
        "serviceKey": service_key,
        "returnType": "json",
        "numOfRows": 1,
        "pageNo": 1,
        "stationName": station_name,
        "dataTerm": "DAILY",
        "ver": "1.3"
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        items = data.get("response", {}).get("body", {}).get("items", [])

        if len(items) == 0:
            return {
                "success": False,
                "error": f"{station_name} 측정소 자료가 없습니다."
            }

        item = items[0]

        def to_number(value):
            return pd.to_numeric(value, errors="coerce")

        return {
            "success": True,
            "station": station_name,
            "data_time": item.get("dataTime"),
            "pm10": to_number(item.get("pm10Value")),
            "pm25": to_number(item.get("pm25Value")),
            "o3": to_number(item.get("o3Value")),
            "no2": to_number(item.get("no2Value")),
            "co": to_number(item.get("coValue")),
            "so2": to_number(item.get("so2Value")),
            "khai": item.get("khaiValue"),
            "khai_grade": item.get("khaiGrade")
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }
@st.cache_data(ttl=1200)
def fetch_airkorea_realtime_with_fallback(preferred_station, station_candidates):
    """
    AirKorea 선택 측정소 조회 후 실패 시 서구 관내 다른 측정소로 자동 대체
    """

    # 1. 우선 선택 측정소 먼저 조회
    station_order = [preferred_station] + [
        station for station in station_candidates
        if station != preferred_station
    ]

    errors = []

    for station in station_order:
        result = fetch_airkorea_realtime(station)

        if result.get("success"):
            # PM2.5 또는 PM10 중 하나라도 유효하면 사용
            pm25 = result.get("pm25")
            pm10 = result.get("pm10")

            has_pm25 = not pd.isna(pm25)
            has_pm10 = not pd.isna(pm10)

            if has_pm25 or has_pm10:
                result["fallback_used"] = station != preferred_station
                result["preferred_station"] = preferred_station
                result["station"] = station
                return result

            errors.append(f"{station}: PM 자료 없음")
        else:
            errors.append(f"{station}: {result.get('error')}")

    return {
        "success": False,
        "error": " / ".join(errors)
    }
    
def get_kma_base_datetime():
    """
    기상청 초단기실황 조회용 base_date, base_time 계산
    초단기실황은 정시 자료가 즉시 제공되지 않을 수 있으므로
    현재 시각에서 40분을 뺀 정시를 사용
    """
    now = datetime.now(KST) - timedelta(minutes=5)
    base_date = now.strftime("%Y%m%d")
    base_time = now.strftime("%H00")
    return base_date, base_time

def haversine_distance_km(lat1, lon1, lat2, lon2):
    """
    위도/경도 두 지점 사이의 대권거리(km) 계산
    """
    R = 6371.0088

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
    )

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def get_nearest_air_station(selected_dong, seogu_location_options, air_station_locations):
    """
    선택 행정동 행정복지센터 좌표 기준으로 가장 가까운 AirKorea 측정소 추천
    """
    dong_info = seogu_location_options[selected_dong]

    dong_lat = dong_info["lat"]
    dong_lon = dong_info["lon"]

    distance_rows = []

    for station_name, station_info in air_station_locations.items():
        distance_km = haversine_distance_km(
            dong_lat,
            dong_lon,
            station_info["lat"],
            station_info["lon"]
        )

        distance_rows.append({
            "station": station_name,
            "place": station_info["place"],
            "address": station_info["address"],
            "distance_km": distance_km
        })

    distance_rows = sorted(distance_rows, key=lambda x: x["distance_km"])

    nearest_station = distance_rows[0]["station"]
    nearest_distance_km = distance_rows[0]["distance_km"]

    return nearest_station, nearest_distance_km, distance_rows
def latlon_to_kma_grid(lat, lon):
    """
    위경도(WGS84)를 기상청 동네예보 격자(nx, ny)로 변환
    기상청 DFS 격자 변환식 기반
    """

    RE = 6371.00877  # 지구 반경(km)
    GRID = 5.0       # 격자 간격(km)
    SLAT1 = 30.0     # 투영 위도1
    SLAT2 = 60.0     # 투영 위도2
    OLON = 126.0     # 기준점 경도
    OLAT = 38.0      # 기준점 위도
    XO = 43          # 기준점 X좌표
    YO = 136         # 기준점 Y좌표

    DEGRAD = math.pi / 180.0

    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)

    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn

    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)

    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / (ra ** sn)

    theta = lon * DEGRAD - olon

    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi

    theta *= sn

    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)

    return nx, ny

def kma_grid_to_latlon(x, y):
    """
    기상청 격자(nx, ny)를 위경도(WGS84)로 역변환
    x, y는 정수뿐 아니라 88.5 같은 소수도 가능
    격자 경계 표시를 위해 사용
    """

    RE = 6371.00877
    GRID = 5.0
    SLAT1 = 30.0
    SLAT2 = 60.0
    OLON = 126.0
    OLAT = 38.0
    XO = 43
    YO = 136

    DEGRAD = math.pi / 180.0
    RADDEG = 180.0 / math.pi

    re = RE / GRID
    slat1 = SLAT1 * DEGRAD
    slat2 = SLAT2 * DEGRAD
    olon = OLON * DEGRAD
    olat = OLAT * DEGRAD

    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)

    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn

    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)

    xn = x - XO
    yn = ro - y + YO

    ra = math.sqrt(xn * xn + yn * yn)

    if sn < 0.0:
        ra = -ra

    alat = (re * sf / ra) ** (1.0 / sn)
    alat = 2.0 * math.atan(alat) - math.pi * 0.5

    if abs(xn) <= 0.0:
        theta = 0.0
    else:
        if abs(yn) <= 0.0:
            theta = math.pi * 0.5
            if xn < 0.0:
                theta = -theta
        else:
            theta = math.atan2(xn, yn)

    alon = theta / sn + olon

    lat = alat * RADDEG
    lon = alon * RADDEG

    return lat, lon

def get_kma_grid_boundary_polygon(nx, ny):
    """
    선택한 기상청 격자의 대략적인 경계 polygon 생성
    반환 형식: pydeck PolygonLayer용 [[lon, lat], ...]
    """

    corners_xy = [
        (nx - 0.5, ny - 0.5),
        (nx + 0.5, ny - 0.5),
        (nx + 0.5, ny + 0.5),
        (nx - 0.5, ny + 0.5),
        (nx - 0.5, ny - 0.5)
    ]

    polygon = []

    for x, y in corners_xy:
        lat, lon = kma_grid_to_latlon(x, y)
        polygon.append([lon, lat])

    return polygon

@st.cache_data(ttl=1800)
def fetch_kma_ultra_short_nowcast(nx=89, ny=90):
    """
    기상청 단기예보 조회서비스 - 초단기실황 조회

    주요 항목:
    T1H: 기온 ℃
    REH: 습도 %
    WSD: 풍속 m/s
    VEC: 풍향 deg
    PTY: 강수형태
    RN1: 1시간 강수량
    """

    service_key = st.secrets.get("KMA_SERVICE_KEY", "")

    if service_key == "":
        return {
            "success": False,
            "error": "KMA_SERVICE_KEY가 secrets.toml에 없습니다."
        }

    base_date, base_time = get_kma_base_datetime()

    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst"

    params = {
        "serviceKey": service_key,
        "pageNo": 1,
        "numOfRows": 100,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()

        data = response.json()

        items = (
            data.get("response", {})
                .get("body", {})
                .get("items", {})
                .get("item", [])
        )

        if len(items) == 0:
            return {
                "success": False,
                "error": f"기상청 초단기실황 자료가 없습니다. base_date={base_date}, base_time={base_time}"
            }

        result = {
            "success": True,
            "base_date": base_date,
            "base_time": base_time,
            "nx": nx,
            "ny": ny
        }

        for item in items:
            category = item.get("category")
            value = item.get("obsrValue")
            result[category] = value

        pty_map = {
            "0": "없음",
            "1": "비",
            "2": "비/눈",
            "3": "눈",
            "5": "빗방울",
            "6": "빗방울눈날림",
            "7": "눈날림"
        }

        result["T1H_text"] = f"{result.get('T1H', '자료없음')}℃"
        result["REH_text"] = f"{result.get('REH', '자료없음')}%"
        result["WSD_text"] = f"{result.get('WSD', '자료없음')} m/s"
        result["PTY_text"] = pty_map.get(str(result.get("PTY", "")), "자료없음")
        result["RN1_text"] = f"{result.get('RN1', '0')} mm"

        return result

    except requests.exceptions.HTTPError as e:
        status_code = e.response.status_code if e.response is not None else None
    
        if status_code == 429:
            return {
                "success": False,
                "error": "기상청 API 요청이 일시적으로 많아 제한되었습니다. 잠시 후 다시 조회해 주세요."
            }
    
        if status_code == 403:
            return {
                "success": False,
                "error": "기상청 API 인증 또는 권한 문제가 발생했습니다."
            }
    
        return {
            "success": False,
            "error": f"기상청 API 조회 중 HTTP 오류가 발생했습니다. 상태코드: {status_code}"
        }
    
    except Exception:
        return {
            "success": False,
            "error": "기상청 API 조회 중 오류가 발생했습니다."
        }

@st.cache_data(ttl=1800)
def fetch_seogu_odor_chartdata(year=None, month=None, day=None):
    """
    대구 서구 자체 악취측정망 - 다이텍연구원 B동 옥상 일별 시간자료 조회

    조회 구조:
    1. moni3_c.html GET
    2. HTML 내부 CSRF token 추출
    3. /airinfo/chartData POST
    4. JSON 응답을 DataFrame으로 변환

    대상 항목:
    - NH₃
    - H₂S
    - TVOC
    """

    now = datetime.now(KST)

    if year is None:
        year = now.year
    if month is None:
        month = now.month
    if day is None:
        day = now.day

    base = "http://222.104.245.139:8080"
    page_url = base + "/airinfo/monitor/moni3_c.html"
    chart_url = base + "/airinfo/chartData"

    params = {
        "node": "1,1,1,8",
        "year": year,
        "month": month,
        "day": day,
        "name": "다이텍연구원 B동 옥상",
    }

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": page_url,
    }

    try:
        session = requests.Session()

        page = session.get(
            page_url,
            params=params,
            headers=headers,
            timeout=15
        )
        page.raise_for_status()

        soup = BeautifulSoup(page.text, "html.parser")

        csrf_token = None

        for script in soup.find_all("script"):
            text = script.get_text("\n", strip=False)

            if "Csrf.TOKEN" in text:
                part = text.split("Csrf.TOKEN = ", 1)[1]
                csrf_token = part.split(";", 1)[0].strip().strip("'").strip('"')
                break

        if not csrf_token:
            return {
                "success": False,
                "error": "악취측정망 CSRF token을 찾지 못했습니다."
            }

        payload = {
            "node": "1,1,1,8",
            "_csrf": csrf_token,
            "year": year,
            "month": month,
            "day": day,
        }

        post_headers = {
            "User-Agent": "Mozilla/5.0",
            "Referer": page.url,
            "X-CSRF-TOKEN": csrf_token,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
        }

        response = session.post(
            chart_url,
            data=payload,
            headers=post_headers,
            timeout=15
        )
        response.raise_for_status()

        data = response.json()

        target_items = ["NH₃", "H₂S", "TVOC"]

        rows = []

        for item in data:
            item_name = item.get("name")
            unit = item.get("unit")
            points = item.get("points", [])

            if item_name not in target_items:
                continue

            for p in points:
                rows.append({
                    "측정항목": item_name,
                    "단위": unit,
                    "time_raw": p.get("time"),
                    "측정값": pd.to_numeric(p.get("value"), errors="coerce"),
                })

        df_long = pd.DataFrame(rows)

        if df_long.empty:
            return {
                "success": True,
                "data": pd.DataFrame(),
                "long_data": df_long,
                "raw": data,
                "message": "조회는 성공했지만 NH₃, H₂S, TVOC 측정값이 없습니다."
            }

        # 서버 timestamp가 ms 단위 Unix time 형태로 제공됨
        df_long["측정시각"] = pd.to_datetime(
            df_long["time_raw"],
            unit="ms",
            utc=True,
            errors="coerce"
        ).dt.tz_convert("Asia/Seoul")

        df_long["시각"] = df_long["측정시각"].dt.strftime("%H:%M")

        df_wide = df_long.pivot_table(
            index=["측정시각", "시각"],
            columns="측정항목",
            values="측정값",
            aggfunc="mean"
        ).reset_index()

        df_wide.columns.name = None

        # 컬럼 순서 고정
        ordered_cols = ["측정시각", "시각"] + [
            col for col in target_items if col in df_wide.columns
        ]
        df_wide = df_wide[ordered_cols]

        return {
            "success": True,
            "data": df_wide,
            "long_data": df_long,
            "raw": data,
            "url": response.url,
        }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
        }
# ============================================================
# 2. 등급 판정 함수
# ============================================================

def get_pm25_grade(pm25):
    if pd.isna(pm25):
        return "자료없음"
    if pm25 <= 15:
        return "좋음"
    elif pm25 <= 35:
        return "보통"
    elif pm25 <= 75:
        return "나쁨"
    else:
        return "매우나쁨"


def get_pm10_grade(pm10):
    if pd.isna(pm10):
        return "자료없음"
    if pm10 <= 30:
        return "좋음"
    elif pm10 <= 80:
        return "보통"
    elif pm10 <= 150:
        return "나쁨"
    else:
        return "매우나쁨"


def get_final_grade(pm25, pm10):
    pm25_grade = get_pm25_grade(pm25)
    pm10_grade = get_pm10_grade(pm10)

    order = {
        "좋음": 1,
        "보통": 2,
        "나쁨": 3,
        "매우나쁨": 4,
        "자료없음": 0
    }

    if order[pm25_grade] >= order[pm10_grade]:
        return pm25_grade
    return pm10_grade


def get_grade_info(grade):
    info = {
        "좋음": {
            "face": "😊",
            "color": "#2F80ED",
            "bg": "#EAF3FF",
            "message": "공기질이 양호합니다. 현재 상태를 유지해 주세요."
        },
        "보통": {
            "face": "🙂",
            "color": "#27AE60",
            "bg": "#EAF8EF",
            "message": "대체로 무난한 상태입니다. 민감군은 장시간 노출을 주의해 주세요."
        },
        "나쁨": {
            "face": "😷",
            "color": "#F2994A",
            "bg": "#FFF4E6",
            "message": "공기질이 좋지 않습니다. 환기 여부와 공기청정기 가동을 확인해 주세요."
        },
        "매우나쁨": {
            "face": "🤢",
            "color": "#EB5757",
            "bg": "#FFECEC",
            "message": "공기질이 매우 나쁩니다. 즉시 환기 또는 공기정화 조치가 필요합니다."
        },
        "자료없음": {
            "face": "❔",
            "color": "#828282",
            "bg": "#F2F2F2",
            "message": "측정값이 없어 상태를 판정할 수 없습니다."
        }
    }
    return info.get(grade, info["자료없음"])


def get_outdoor_action(indoor_grade, outdoor_grade):
    order = {"좋음": 1, "보통": 2, "나쁨": 3, "매우나쁨": 4, "자료없음": 0}

    if indoor_grade == "자료없음" or outdoor_grade == "자료없음":
        return "실내 또는 실외 자료가 부족합니다. 측정기 연결 상태를 확인해 주세요."

    if order[indoor_grade] >= 3 and order[outdoor_grade] <= 2:
        return "실내 공기질이 실외보다 나쁜 편입니다. 짧은 환기와 공기청정기 가동을 권장합니다."

    if order[indoor_grade] <= 2 and order[outdoor_grade] >= 3:
        return "실외 미세먼지가 높은 편입니다. 창문 개방을 줄이고 실내 공기정화 상태를 유지해 주세요."

    if order[indoor_grade] >= 3 and order[outdoor_grade] >= 3:
        return "실내와 실외 모두 공기질이 좋지 않습니다. 환기보다는 공기청정기 가동과 활동 조정을 권장합니다."

    return "실내외 공기질이 대체로 양호합니다. 현재 상태를 유지해 주세요."


# ============================================================
# 3. 이용자 반응 저장
# ============================================================

def save_feedback(feedback, indoor_pm25, indoor_pm10, outdoor_pm25, outdoor_pm10, indoor_grade, outdoor_grade):
    now = get_kst_now()

    new_row = pd.DataFrame([{
        "feedback_time_kst": now,
        "feedback": feedback,
        "indoor_pm25": indoor_pm25,
        "indoor_pm10": indoor_pm10,
        "outdoor_pm25": outdoor_pm25,
        "outdoor_pm10": outdoor_pm10,
        "indoor_grade": indoor_grade,
        "outdoor_grade": outdoor_grade
    }])

    if FEEDBACK_FILE.exists():
        old_df = pd.read_csv(FEEDBACK_FILE, encoding="utf-8-sig")
        result_df = pd.concat([old_df, new_row], ignore_index=True)
    else:
        result_df = new_row

    result_df.to_csv(FEEDBACK_FILE, index=False, encoding="utf-8-sig")


# ============================================================
# 4. CSS: 키오스크형 화면
# ============================================================

st.markdown(
    """
    <style>

    .header-wrap {
        margin-top: 38px;
        margin-bottom: 22px;
        padding-left: 0px;
        padding-right: 0px;
    }
    
    .header-panel {
        background: linear-gradient(90deg, #1F4E79, #2F80ED);
        border-radius: 26px;
        padding: 30px 36px 26px 36px;
        color: white;
        box-sizing: border-box;
        overflow: hidden;
    }
    
    .header-title {
        font-size: 40px;
        font-weight: 800;
        line-height: 1.3;
        margin: 0 0 8px 0;
        padding: 0;
    }
    
    .header-subtitle {
        font-size: 20px;
        line-height: 1.4;
        margin: 0;
        opacity: 0.95;
    }
    
    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1.5rem;
        padding-left: 2.0rem;
        padding-right: 2.0rem;
    }    
    .main {
        background-color: #F7F9FB;
    }

    .air-card {
        padding: 26px;
        border-radius: 26px;
        background-color: white;
        box-shadow: 0 4px 16px rgba(0,0,0,0.08);
        border: 1px solid #E6EAF0;
        min-height: 450px;
    }

    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 14px;
    }

    .card-title {
        font-size: 34px;
        font-weight: 800;
        color: #1F2937;
    }

    .grade-badge {
        padding: 8px 18px;
        border-radius: 999px;
        color: white;
        font-size: 22px;
        font-weight: 800;
    }

    .face {
        text-align: center;
        font-size: 104px;
        margin-top: 6px;
        margin-bottom: 2px;
    }

    .grade-text {
        text-align: center;
        font-size: 46px;
        font-weight: 900;
        margin-bottom: 10px;
    }

    .value-row {
        display: flex;
        justify-content: space-around;
        margin-top: 18px;
    }

    .value-box {
        width: 46%;
        background-color: #F8FAFC;
        border-radius: 18px;
        padding: 18px;
        text-align: center;
        border: 1px solid #E5E7EB;
    }

    .value-label {
        font-size: 20px;
        color: #4B5563;
        font-weight: 700;
    }

    .value-number {
        font-size: 42px;
        color: #111827;
        font-weight: 900;
    }

    .value-unit {
        font-size: 20px;
        color: #4B5563;
        font-weight: 700;
    }

    .small-note {
        margin-top: 18px;
        font-size: 18px;
        line-height: 1.45;
        color: #6b7280;
        text-align: center;
        min-height: 58px;
        display: flex;
        flex-direction: column;
        justify-content: center;
        word-break: keep-all;
    }
    
    .small-note .note-line {
        display: block;
    }
    .action-box {
        background-color: #111827;
        color: white;
        padding: 24px 30px;
        border-radius: 22px;
        margin-top: 22px;
        font-size: 28px;
        font-weight: 800;
        text-align: center;
    }

    .scale-wrap {
        background-color: white;
        border-radius: 24px;
        padding: 24px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.08);
        border: 1px solid #E6EAF0;
        margin-top: 22px;
    }

    .scale-title {
        font-size: 28px;
        font-weight: 900;
        margin-bottom: 16px;
        text-align: center;
    }

    .scale-grid {
        display: grid;
        grid-template-columns: repeat(4, 1fr);
        gap: 14px;
    }

    .scale-item {
        color: white;
        border-radius: 18px;
        padding: 18px 8px;
        text-align: center;
        font-weight: 900;
    }

    .scale-face {
        font-size: 46px;
    }

    .scale-grade {
        font-size: 24px;
    }

    .scale-range {
        font-size: 16px;
        opacity: 0.95;
    }

    .feedback-title {
        font-size: 30px;
        font-weight: 900;
        text-align: center;
        margin-top: 18px;
        margin-bottom: 10px;
    }

    div.stButton > button {
        height: 82px;
        font-size: 28px;
        font-weight: 900;
        border-radius: 18px;
    }
    </style>
    """,
    unsafe_allow_html=True
)


# ============================================================
# 5. 사이드바: 실내 샘플값 / 외부 API 설정
# ============================================================

st.sidebar.header("2차 데모 설정")

if st.sidebar.button("외부자료 새로고침", width="stretch"):
    st.cache_data.clear()
    st.sidebar.success("외부자료를 새로 조회했습니다.")


# ------------------------------------------------------------
# 5-1. 실내 샘플값
# ------------------------------------------------------------

st.sidebar.subheader("실내 샘플값")

indoor_pm25 = st.sidebar.slider("실내 PM2.5 (µg/m³)", 0, 150, 13)
indoor_pm10 = st.sidebar.slider("실내 PM10 (µg/m³)", 0, 250, 14)
indoor_temp = st.sidebar.slider("실내 온도 (℃)", 0.0, 40.0, 24.5, 0.1)
indoor_hum = st.sidebar.slider("실내 습도 (%)", 0.0, 100.0, 55.0, 0.1)


# ------------------------------------------------------------
# 5-2. AirKorea 외부 대기질 설정
# ------------------------------------------------------------

st.sidebar.subheader("기준 행정동")

dong_options = list(seogu_location_options.keys())

if "selected_dong" not in st.session_state:
    st.session_state["selected_dong"] = "평리3동"

selected_dong = st.sidebar.selectbox(
    "행정동 선택",
    dong_options,
    key="selected_dong"
)

selected_location_info = seogu_location_options[selected_dong]

display_location_name = f"{selected_dong} 행정복지센터"

selected_lat = selected_location_info["lat"]
selected_lon = selected_location_info["lon"]

KMA_NX, KMA_NY = latlon_to_kma_grid(selected_lat, selected_lon)

nearest_air_station, nearest_distance_km, air_distance_rows = get_nearest_air_station(
    selected_dong,
    seogu_location_options,
    air_station_locations
)

st.sidebar.subheader("외부자료 기준")

manual_external_setting = st.sidebar.checkbox(
    "외부자료 기준 수동 설정",
    value=False
)

station_options = list(air_station_locations.keys())

if manual_external_setting:
    outdoor_station = st.sidebar.selectbox(
        "AirKorea 측정소",
        station_options,
        index=station_options.index(nearest_air_station)
    )

    st.sidebar.caption(
        f"자동 추천: {nearest_air_station} ({nearest_distance_km:.2f} km)"
    )

else:
    outdoor_station = nearest_air_station

    st.sidebar.caption(
        f"기상청 기준: {selected_dong} 행정복지센터"
    )
    st.sidebar.caption(
        f"AirKorea 자동 추천: {outdoor_station} ({nearest_distance_km:.2f} km)"
    )

with st.sidebar.expander("AirKorea 측정소 거리 확인", expanded=False):
    distance_df = pd.DataFrame(air_distance_rows)
    distance_df["distance_km"] = distance_df["distance_km"].round(3)
    st.dataframe(distance_df, width="stretch")

# ------------------------------------------------------------
# 5-3. 기상청 자료 설정
# ------------------------------------------------------------

air_result = fetch_airkorea_realtime_with_fallback(
    outdoor_station,
    station_options
)

if air_result.get("success"):
    outdoor_pm25 = air_result.get("pm25")
    outdoor_pm10 = air_result.get("pm10")
    outdoor_time = air_result.get("data_time", "자료없음")
    used_station = air_result.get("station", outdoor_station)

    if air_result.get("fallback_used"):
        st.sidebar.warning(
            f"{air_result.get('preferred_station')} 자료 문제로 "
            f"{used_station} 측정소 자료를 사용합니다."
        )
    else:
        st.sidebar.success(f"AirKorea 조회 성공: {used_station}")

else:
    outdoor_pm25 = pd.NA
    outdoor_pm10 = pd.NA
    outdoor_time = "자료없음"
    used_station = outdoor_station

    st.sidebar.warning("AirKorea 자료 임시 조회 불가")
    st.sidebar.write(air_result.get("error"))


st.sidebar.subheader("기상청 외부 기상")

kma_result = fetch_kma_ultra_short_nowcast(KMA_NX, KMA_NY)

if kma_result["success"]:
    st.sidebar.success("기상청 조회 성공")
    st.sidebar.write(f"기준시각: {kma_result.get('base_date')} {kma_result.get('base_time')}")
    st.sidebar.write(f"기온: {kma_result.get('T1H_text')}")
    st.sidebar.write(f"습도: {kma_result.get('REH_text')}")
    st.sidebar.write(f"풍속: {kma_result.get('WSD_text')}")
    st.sidebar.write(f"강수: {kma_result.get('PTY_text')}")
else:
    st.sidebar.warning("기상청 자료 임시 조회 불가")
    st.sidebar.write(kma_result["error"])

# ============================================================
# 6. 등급 계산
# ============================================================

indoor_grade = get_final_grade(indoor_pm25, indoor_pm10)
outdoor_grade = get_final_grade(outdoor_pm25, outdoor_pm10)

indoor_info = get_grade_info(indoor_grade)
outdoor_info = get_grade_info(outdoor_grade)

action_message = get_outdoor_action(indoor_grade, outdoor_grade)


# ============================================================
# 7. 상단 제목
# ============================================================

st.markdown(
    f"""
<div class="header-wrap">
    <div class="header-panel">
        <div class="header-title">{display_location_name} 실내공기질 안내서비스</div>
        <div class="header-subtitle">
            실내 미세먼지와 외부 대기질을 한눈에 비교합니다 · {get_kst_now()} 기준
        </div>
    </div>
</div>
""",
    unsafe_allow_html=True
)

# ============================================================
# 8. 실내/실외 좌우 비교 카드
# ============================================================

def render_air_card(title, pm25, pm10, grade, info, note):
    html = (
        f'<div class="air-card">'
        f'<div class="card-header">'
        f'<div class="card-title">{title}</div>'
        f'<div class="grade-badge" style="background-color:{info["color"]};">{grade}</div>'
        f'</div>'
        f'<div class="face">{info["face"]}</div>'
        f'<div class="grade-text" style="color:{info["color"]};">{grade}</div>'
        f'<div class="value-row">'
        f'<div class="value-box">'
        f'<div class="value-label">초미세먼지 PM2.5</div>'
        f'<div class="value-number">{pm25}</div>'
        f'<div class="value-unit">µg/m³</div>'
        f'</div>'
        f'<div class="value-box">'
        f'<div class="value-label">미세먼지 PM10</div>'
        f'<div class="value-number">{pm10}</div>'
        f'<div class="value-unit">µg/m³</div>'
        f'</div>'
        f'</div>'
        f'<div class="small-note">{note}</div>'
        f'</div>'
    )

    st.markdown(html, unsafe_allow_html=True)


left_col, right_col = st.columns(2)

indoor_note = (
    f"<span class='note-line'>온도 {indoor_temp:.1f}℃ · 습도 {indoor_hum:.1f}%</span>"
    f"<span class='note-line'>간이측정기 샘플값</span>"
)

with left_col:
    render_air_card(
        title="실내",
        pm25=indoor_pm25,
        pm10=indoor_pm10,
        grade=indoor_grade,
        info=indoor_info,
        note=indoor_note
    )

if kma_result.get("success"):
    rain_text = kma_result.get("PTY_text")

    if rain_text and rain_text != "없음":
        weather_line = (
            f"외부기상 {kma_result.get('T1H_text')} · "
            f"습도 {kma_result.get('REH_text')} · "
            f"바람 {kma_result.get('WSD_text')} · "
            f"{rain_text}"
        )
    else:
        weather_line = (
            f"외부기상 {kma_result.get('T1H_text')} · "
            f"습도 {kma_result.get('REH_text')} · "
            f"바람 {kma_result.get('WSD_text')}"
        )

    outdoor_note = (
        f"<span class='note-line'>AirKorea {used_station} · {outdoor_time} 기준</span>"
        f"<span class='note-line'>{weather_line}</span>"
    )
else:
    outdoor_note = (
        f"<span class='note-line'>AirKorea {used_station} · {outdoor_time} 기준</span>"
        f"<span class='note-line'>외부기상 자료없음</span>"
    )

with right_col:
    render_air_card(
        title="실외",
        pm25=outdoor_pm25,
        pm10=outdoor_pm10,
        grade=outdoor_grade,
        info=outdoor_info,
        note=outdoor_note
    )
# ============================================================
# 9. 행동요령
# ============================================================

st.markdown(
    f"""
    <div class="action-box">
        오늘의 안내: {action_message}
    </div>
    """,
    unsafe_allow_html=True
)

# ============================================================
# 9-1. 대구 서구 자체 악취측정망
# ============================================================

odor_result = fetch_seogu_odor_chartdata()

st.markdown("### 대구 서구 자체 악취측정망")

if odor_result.get("success"):
    odor_df = odor_result.get("data", pd.DataFrame())

    if odor_df.empty:
        st.info("다이텍연구원 B동 옥상 악취측정값이 아직 없습니다.")
    else:
        odor_cols = [
            col for col in ["NH₃", "H₂S", "TVOC"]
            if col in odor_df.columns
        ]

        valid_df = odor_df.dropna(subset=odor_cols, how="all")

        if valid_df.empty:
            st.info("오늘 조회된 악취측정값 중 유효한 값이 없습니다.")
        else:
            latest = valid_df.iloc[-1]

            st.caption(
                "측정지점: 다이텍연구원 B동 옥상 · "
                "측정주기: 1시간 · "
                "단위: ppm "
            )
            def format_odor_value(value):
                if pd.isna(value):
                    return "자료없음"
                return f"{value:.3f} ppm"
            
            
            nh3_value = latest.get("NH₃")
            h2s_value = latest.get("H₂S")
            tvoc_value = latest.get("TVOC")
            
            st.markdown(
                f"""
                <div style="
                    display:grid;
                    grid-template-columns: repeat(3, 1fr);
                    gap: 18px;
                    margin-top: 14px;
                    margin-bottom: 10px;
                ">
                    <div style="
                        background:white;
                        border:1px solid #E5E7EB;
                        border-radius:18px;
                        padding:22px 26px;
                        box-shadow:0 3px 10px rgba(0,0,0,0.06);
                        text-align:center;
                    ">
                        <div style="font-size:26px; font-weight:900; color:#374151; margin-bottom:8px;">NH₃</div>
                        <div style="font-size:38px; font-weight:900; color:#111827;">{format_odor_value(nh3_value)}</div>
                        <div style="font-size:15px; color:#6B7280; margin-top:6px;">암모니아</div>
                    </div>
            
                    <div style="
                        background:white;
                        border:1px solid #E5E7EB;
                        border-radius:18px;
                        padding:22px 26px;
                        box-shadow:0 3px 10px rgba(0,0,0,0.06);
                        text-align:center;
                    ">
                        <div style="font-size:26px; font-weight:900; color:#374151; margin-bottom:8px;">H₂S</div>
                        <div style="font-size:38px; font-weight:900; color:#111827;">{format_odor_value(h2s_value)}</div>
                        <div style="font-size:15px; color:#6B7280; margin-top:6px;">황화수소</div>
                    </div>
            
                    <div style="
                        background:white;
                        border:1px solid #E5E7EB;
                        border-radius:18px;
                        padding:22px 26px;
                        box-shadow:0 3px 10px rgba(0,0,0,0.06);
                        text-align:center;
                    ">
                        <div style="font-size:26px; font-weight:900; color:#374151; margin-bottom:8px;">TVOC</div>
                        <div style="font-size:38px; font-weight:900; color:#111827;">{format_odor_value(tvoc_value)}</div>
                        <div style="font-size:15px; color:#6B7280; margin-top:6px;">총휘발성유기화합물</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True
            )

            st.caption(f"최신 측정시각: {latest.get('시각')}")

            with st.expander("당일 시간대별 악취측정 추이", expanded=False):
                if "NH₃" in odor_df.columns and "H₂S" in odor_df.columns:
                    st.markdown("#### NH₃ / H₂S")
                    st.line_chart(
                        odor_df.set_index("시각")[["NH₃", "H₂S"]]
                    )

                if "TVOC" in odor_df.columns:
                    st.markdown("#### TVOC")
                    st.line_chart(
                        odor_df.set_index("시각")[["TVOC"]]
                    )

            with st.expander("시간대별 악취측정 자료", expanded=False):
                show_df = odor_df[["시각"] + odor_cols].copy()

                for col in odor_cols:
                    show_df[col] = show_df[col].round(4)

                st.dataframe(
                    show_df,
                    width="stretch",
                    hide_index=True
                )

else:
    st.warning("대구 서구 자체 악취측정망 자료를 불러오지 못했습니다.")
    st.write(odor_result.get("error"))
# ============================================================
# 10. 등급표
# ============================================================

st.markdown(
    """
    <div class="scale-wrap">
        <div class="scale-title">오늘의 대기질 안내 기준</div>
        <div class="scale-grid">
            <div class="scale-item" style="background-color:#2F80ED;">
                <div class="scale-face">😊</div>
                <div class="scale-grade">좋음</div>
                <div class="scale-range">PM2.5 0~15<br>PM10 0~30</div>
            </div>
            <div class="scale-item" style="background-color:#27AE60;">
                <div class="scale-face">🙂</div>
                <div class="scale-grade">보통</div>
                <div class="scale-range">PM2.5 16~35<br>PM10 31~80</div>
            </div>
            <div class="scale-item" style="background-color:#F2994A;">
                <div class="scale-face">😷</div>
                <div class="scale-grade">나쁨</div>
                <div class="scale-range">PM2.5 36~75<br>PM10 81~150</div>
            </div>
            <div class="scale-item" style="background-color:#EB5757;">
                <div class="scale-face">🤢</div>
                <div class="scale-grade">매우나쁨</div>
                <div class="scale-range">PM2.5 76~<br>PM10 151~</div>
            </div>
        </div>
    </div>
    """,
    unsafe_allow_html=True
)


# ============================================================
# 11. 이용자 반응 버튼
# ============================================================

st.markdown('<div class="feedback-title">현재 안내가 체감과 맞나요?</div>', unsafe_allow_html=True)

btn1, btn2, btn3 = st.columns(3)

with btn1:
    if st.button("👍 좋아요", width="stretch"):
        save_feedback("좋아요", indoor_pm25, indoor_pm10, outdoor_pm25, outdoor_pm10, indoor_grade, outdoor_grade)
        st.success("반응이 저장되었습니다.")

with btn2:
    if st.button("😐 보통이에요", width="stretch"):
        save_feedback("보통이에요", indoor_pm25, indoor_pm10, outdoor_pm25, outdoor_pm10, indoor_grade, outdoor_grade)
        st.success("반응이 저장되었습니다.")

with btn3:
    if st.button("🙁 불편해요", width="stretch"):
        save_feedback("불편해요", indoor_pm25, indoor_pm10, outdoor_pm25, outdoor_pm10, indoor_grade, outdoor_grade)
        st.warning("반응이 저장되었습니다.")


# ============================================================
# 12. 하단 설명
# ============================================================

with st.expander("향후 연동 구조"):
    st.markdown("""
    - 장비 설치 후: 실내 간이측정기 CSV, DB, API, IoT 수집 방식 중 하나로 연결
    - 현장 적용: 키오스크, 태블릿, 스탠바이미 화면에 전체화면으로 띄우는 방식 검토
    """)

if FEEDBACK_FILE.exists():
    with st.expander("이용자 반응 기록 확인"):
        feedback_df = pd.read_csv(FEEDBACK_FILE, encoding="utf-8-sig")
        st.dataframe(feedback_df.tail(20), width="stretch", hide_index=True)
        
