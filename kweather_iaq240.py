# -*- coding: utf-8 -*-
"""Kweather Air365 official latest-value API for one subscribed IAQ-CW device.

Source: Air365 IoT API v1.6 (2025-09-25), v2/last-all.
No API key is stored in this module. Streamlit Secrets must supply it.
This module is independent of the site's older Arim/AirKorea/KMA data.
"""

from datetime import datetime, timedelta, timezone
import hashlib
import html
import math
import requests
import streamlit as st

KST = timezone(timedelta(hours=9))
SERIAL = "ICW0W2600240"
API_URL = "https://gateway.kweather.co.kr:8443/iot/groups/v2/last-all"
CACHE_TTL_SECONDS = 180  # One fetch per 3 minutes per server process/cache key
AIRKOREA_STATION = "수창동"  # Confirmed by user-provided AirKorea address search
AIRKOREA_TTL_SECONDS = 1200
AIRKOREA_STALE_MINUTES = 180
CHILDCARE_NAME = "도원센트럴어린이집"
CHILDCARE_ADDRESS = "대구광역시 중구 태평로 50"
AIRKOREA_STATION_DESCRIPTION = "수창동 도시대기측정소 (에어코리아 검색 기준 약 0.4 km)"
STALE_AFTER_MINUTES = 10  # Display safety threshold (app policy; not vendor SLA)

FIELD_RANGES = {
    "pm25": (0, 5000), "pm10": (0, 5000),
    "temp": (-60, 80), "humi": (0, 100),
    "co2": (0, 10000), "voc": (0, 60000), "noise": (30, 95),
}


def _clean_number(raw, field):
    if raw is None or isinstance(raw, bool):
        return None
    try:
        num = float(raw)
    except (ValueError, TypeError, OverflowError):
        return None
    if not math.isfinite(num) or num == -999:
        return None
    low, high = FIELD_RANGES[field]
    return num if low <= num <= high else None


def parse_latest_response(payload, serial=SERIAL):
    """Return ONLY the paid-for serial's data (or None if not in the list).

    No silent fallback to a second device or a sample response.
    Raises ValueError for unexpected API structure/application errors.
    """
    if not isinstance(payload, dict):
        raise ValueError("최상위 JSON이 객체 형태가 아닙니다. 케이웨더 응답 규격 확인 필요")

    # 공식 규격서 v1.6 p.5: 정상=0, 실패=002/101~105/901.
    # 반환 메시지는 인증키 등 민감정보를 포함할 가능성이 있어 절대 표시하지 않음.
    raw_code = payload.get("error")
    code = str(raw_code).strip() if raw_code is not None else "미기재"
    if code not in ("0", "0.0"):
        known_errors = {
            "002": "API 경로를 찾을 수 없음",
            "101": "권한 없음(인증키/계약 권한 확인)",
            "102": "파라미터 오류(stationType/idType/id 확인)",
            "103": "유효하지 않은 사용자(Air365 계정 확인)",
            "104": "접근 실패(접속 제한 예외 설정 확인)",
            "105": "케이웨더 서버 오류",
            "901": "알 수 없는 서버 오류",
        }
        # 악의적/비표준 문자열은 사용자 화면에 반영하지 않음.
        safe_code = code if code.isdigit() and len(code) <= 4 else "비표준 코드"
        detail = known_errors.get(code, "케이웨더 측 확인 필요")
        raise ValueError(f"케이웨더 API 오류 {safe_code}: {detail}")

    result = payload.get("result")
    if not isinstance(result, dict):
        raise ValueError("API 정상코드(0)이나 result 항목이 객체가 아닙니다. 케이웨더 응답 구조 확인 필요")
    # 규격서 v1.6: 7쪽 표에는 iaqList, 12쪽 예시에는 iaq_list 표기.
    devices = result.get("iaq_list")
    if devices is None:
        devices = result.get("iaqList")
    if not isinstance(devices, list):
        raise ValueError("API 정상코드(0)이나 iaq_list/iaqList 목록이 없습니다. 케이웨더 응답 구조 확인 필요")
    for device in devices:
        if not isinstance(device, dict) or str(device.get("serialNo", "")).strip() != serial:
            continue
        raw_time = str(device.get("date", "")).strip()
        try:
            if len(raw_time) != 12 or not raw_time.isdigit():
                raise ValueError
            measured_at = datetime.strptime(raw_time, "%Y%m%d%H%M").replace(tzinfo=KST)
        except ValueError:
            measured_at = None
        record = {
            "serial": serial,
            "station_name": str(device.get("stationName") or serial),
            "measured_at": measured_at,
        }
        for name in FIELD_RANGES:
            record[name] = _clean_number(device.get(name), name)
        return record
    return None


def _read_config():
    try:
        s = st.secrets.get("kweather", {})
        key = str(s.get("api_key", "")).strip()
        account = str(s.get("account_id", "dyetec")).strip()
        id_type = str(s.get("id_type", "USER")).strip().upper()
        display_location = str(s.get("display_location", "사무실 시험 · 도원센트럴어린이집 설치 예정")).strip()
        installed_at_site = s.get("installed_at_site", False) is True
    except Exception:  # Missing local .streamlit/secrets.toml
        key, account, id_type = "", "dyetec", "USER"
        display_location = "사무실 시험 · 도원센트럴어린이집 설치 예정"
        installed_at_site = False
    return {
        "key": key, "account": account, "id_type": id_type,
        "display_location": display_location,
        "installed_at_site": installed_at_site,
    }


@st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)
def _fetch_cached(account, id_type, key_hash, _key):
    """Process-shared cache, including errors, to conserve 1500 calls/day.

    The raw key is deliberately excluded from the cache key and never printed;
    key_hash invalidates cache when credential changes.
    """
    del key_hash  # Used only in Streamlit cache signature
    params = {"stationType": "IAQ", "idType": id_type,
              "id": account, "api_key": _key}
    try:
        response = requests.get(
            API_URL, params=params, headers={"Accept": "application/json"},
            timeout=(5, 12), allow_redirects=False,
        )
    except requests.RequestException:
        return {"record": None, "error": "케이웨더 API 서버에 연결하지 못했습니다."}
    status = response.status_code
    if status == 401:
        return {"record": None, "error": "인증 실패(401): API 인증키와 사용 권한을 확인하세요."}
    if status == 403:
        return {"record": None, "error": "접속 제한(403): 케이웨더에 IP 예외 적용 여부를 확인하세요."}
    if status == 429:
        return {"record": None, "error": "요청 횟수 초과(429): 케이웨더 허용 횟수를 확인하세요."}
    if status != 200:
        return {"record": None, "error": f"API 응답 실패(HTTP {status})."}
    try:
        data = response.json()
    except ValueError:
        return {"record": None, "error": "케이웨더 응답이 JSON 형식이 아닙니다(HTTP 200). 서버 확인 필요"}
    try:
        record = parse_latest_response(data)
    except (ValueError, TypeError) as exc:
        # 예외는 위의 사전에 정의한 안전한 메시지만 반환. 원문 응답은 노출하지 않음.
        return {"record": None, "error": str(exc)}
    if record is None:
        return {"record": None, "error": f"API 목록에 계약 대상 측정기 {SERIAL}가 없습니다."}
    return {"record": record, "error": None}


def get_current_reading():
    cfg = _read_config()
    if not cfg["key"]:
        return {"record": None, "error": "API 인증키가 아직 설정되지 않았습니다."}, cfg
    if not cfg["account"] or cfg["id_type"] not in ("USER", "GROUP"):
        return {"record": None, "error": "API 계정 설정이 올바르지 않습니다."}, cfg
    fingerprint = hashlib.sha256(cfg["key"].encode("utf-8")).hexdigest()
    return _fetch_cached(cfg["account"], cfg["id_type"], fingerprint, cfg["key"]), cfg


def validate_freshness(record, now=None):
    """Return (is_fresh, minutes, reason). Never treat stale data as live."""
    at = record.get("measured_at") if record else None
    if at is None:
        return False, None, "측정시각이 없거나 해석되지 않았습니다."
    now = now or datetime.now(KST)
    age_minutes = (now - at).total_seconds() / 60
    if age_minutes < -3:
        return False, age_minutes, "측정시각이 현재보다 미래입니다."
    if age_minutes > STALE_AFTER_MINUTES:
        return False, age_minutes, f"마지막 갱신 후 약 {age_minutes:.0f}분 경과하여 현재값으로 표시하지 않습니다."
    return True, age_minutes, None


def _value(rec, name, unit="", digits=0):
    value = rec.get(name)
    if value is None:
        return "자료없음"
    return f"{value:.{digits}f}{unit}"


def _grade(pm25, pm10):
    def g(val, bounds):
        if val is None:
            return None
        if val <= bounds[0]: return 0
        if val <= bounds[1]: return 1
        if val <= bounds[2]: return 2
        return 3
    grades = [g(pm25, (15, 35, 75)), g(pm10, (30, 80, 150))]
    grades = [i for i in grades if i is not None]
    return ("좋음", "보통", "나쁨", "매우나쁨")[max(grades)] if grades else "자료없음"


def _render_values():
    response, cfg = get_current_reading()
    st.caption(f"측정기 {SERIAL} · {cfg['display_location']}")
    if response["error"]:
        st.warning(response["error"])
        return
    rec = response["record"]
    fresh, minutes, reason = validate_freshness(rec)
    if not fresh:
        st.error(reason)
        if rec["measured_at"] is not None:
            st.caption(f"최종 수신 측정시각: {rec['measured_at']:%Y-%m-%d %H:%M} KST")
        return
    st.success(f"정상 수신 · 측정시각 {rec['measured_at']:%Y-%m-%d %H:%M} KST · 약 {max(0, minutes):.1f}분 전")
    st.subheader(f"실내 미세먼지 상태: {_grade(rec['pm25'], rec['pm10'])}")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("초미세먼지 PM2.5", _value(rec, "pm25", " µg/m³"))
        st.metric("온도", _value(rec, "temp", " ℃", 1))
        st.metric("CO₂", _value(rec, "co2", " ppm"))
        st.metric("VOCs", _value(rec, "voc", " ppb"))
    with c2:
        st.metric("미세먼지 PM10", _value(rec, "pm10", " µg/m³"))
        st.metric("습도", _value(rec, "humi", " %"))
        st.metric("소음", _value(rec, "noise", " dB"))
    st.caption("자료 출처: 케이웨더 Air365 최신 측정자료 API. 측정값은 인증·교정된 기준측정망 자료가 아닙니다.")


if hasattr(st, "fragment"):
    # Browser display updates automatically; calls are cached across sessions.
    render_live_reading = st.fragment(run_every="180s")(_render_values)
else:
    render_live_reading = _render_values


def _to_valid_pm(raw):
    """Normalize AirKorea PM numeric values, allowing missing markers."""
    if raw is None or str(raw).strip() in ("", "-", "None", "null"):
        return None
    try:
        val = float(raw)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(val) or val < 0:
        return None
    return val


def _parse_airkorea_datetime(text):
    # AirKorea uses YYYY-MM-DD HH:MM in local Korea time.
    try:
        return datetime.strptime(str(text), "%Y-%m-%d %H:%M").replace(tzinfo=KST)
    except (TypeError, ValueError):
        return None


@st.cache_data(ttl=AIRKOREA_TTL_SECONDS, show_spinner=False)
def _fetch_suchang_airkorea(service_key):
    """Only Suchang-dong is eligible; no substitution by another station."""
    url = "http://apis.data.go.kr/B552584/ArpltnInforInqireSvc/getMsrstnAcctoRltmMesureDnsty"
    params = {"serviceKey": service_key, "returnType": "json", "numOfRows": 1,
              "pageNo": 1, "stationName": AIRKOREA_STATION, "dataTerm": "DAILY", "ver": "1.3"}
    try:
        r = requests.get(url, params=params, timeout=(5, 12))
        r.raise_for_status()
        body = r.json().get("response", {}).get("body", {})
        rows = body.get("items", [])
        if not isinstance(rows, list) or not rows:
            return {"error": "수창동 측정소의 실외 대기질 자료가 없습니다.", "record": None}
        row = rows[0]
        if not isinstance(row, dict):
            return {"error": "에어코리아 데이터 형식이 올바르지 않습니다.", "record": None}
        return {"error": None, "record": {
            "pm25": _to_valid_pm(row.get("pm25Value")),
            "pm10": _to_valid_pm(row.get("pm10Value")),
            "measured_at": _parse_airkorea_datetime(row.get("dataTime")),
        }}
    except (requests.RequestException, ValueError, TypeError):
        return {"error": "에어코리아 측정자료를 조회하지 못했습니다.", "record": None}


def _render_outdoor_values():
    st.caption(f"{AIRKOREA_STATION_DESCRIPTION} · 어린이집 현장의 직접 측정값이 아닌 인근 대표 측정자료")
    try:
        service_key = str(st.secrets.get("AIRKOREA_SERVICE_KEY", "")).strip()
    except Exception:
        service_key = ""
    if not service_key:
        st.info("에어코리아 API 인증키(AIRKOREA_SERVICE_KEY)가 설정되지 않았습니다.")
        return
    response = _fetch_suchang_airkorea(service_key)
    if response["error"]:
        st.warning(response["error"])
        return
    rec = response["record"]
    at = rec.get("measured_at")
    if at is None:
        st.warning("수창동 측정소 측정시각을 확인할 수 없습니다.")
        return
    age = (datetime.now(KST) - at).total_seconds() / 60
    if age < -3 or age > AIRKOREA_STALE_MINUTES:
        st.warning(f"수창동 실외 측정값이 갱신되지 않았습니다. 최종시각: {at:%Y-%m-%d %H:%M} KST")
        return
    st.caption(f"수창동 실외 측정시각: {at:%Y-%m-%d %H:%M} KST")
    c1, c2 = st.columns(2)
    with c1:
        st.metric("실외 PM2.5", _value(rec, "pm25", " µg/m³"))
    with c2:
        st.metric("실외 PM10", _value(rec, "pm10", " µg/m³"))
    st.caption("출처: 에어코리아 도시대기측정망. 실내 측정값과 측정 위치·장비·시각이 다를 수 있습니다.")


if hasattr(st, "fragment"):
    render_outdoor_reading = st.fragment(run_every="180s")(_render_outdoor_values)
else:
    render_outdoor_reading = _render_outdoor_values



# ============================================================
# 도원센트럴어린이집 QR용 카드형 대시보드
# 기존 app_v2.py의 아림/기상청/이용자 반응 페이지와 독립적으로 동작
# ============================================================
CHILDCARE_CSS = """
<style>
.kwc-root {max-width:1180px;margin:0 auto;padding:2px 0 12px;font-family:inherit;color:#14233c}
.kwc-head {display:flex;gap:13px;align-items:center;margin:4px 0 12px}
.kwc-head-icon {font-size:36px}
.kwc-head-title {font-weight:850;font-size:clamp(25px,3.4vw,38px);letter-spacing:-1.1px;line-height:1.3;color:#14233c}
.kwc-head-sub {font-size:14px;color:#667588;margin:5px 0 0}
.kwc-statusbar {display:flex;align-items:center;gap:8px;flex-wrap:wrap;font-size:13px;color:#586579;margin:12px 0 18px}
.kwc-statusdot {height:7px;width:7px;border-radius:100%;background:#31a87c;display:inline-block}
.kwc-cards {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:12px 0 18px}
.kwc-card {background:#fff;border:1px solid #e2e8f0;border-radius:20px;overflow:hidden;box-shadow:0 4px 20px rgba(29,49,86,.055)}
.kwc-card-top {padding:23px 25px 8px;display:flex;align-items:center;justify-content:space-between;gap:8px}
.kwc-section-title {font-size:25px;font-weight:850;letter-spacing:-.6px;color:#1b2c48}
.kwc-tag {font-size:12px;font-weight:750;padding:6px 10px;border-radius:9px;color:#54728c;background:#edf4fb}
.kwc-grade-center {text-align:center;padding:1px 12px 12px}
.kwc-face {font-size:75px;line-height:1.1;margin-bottom:3px}
.kwc-grade {font-size:35px;font-weight:900;letter-spacing:-.6px;line-height:1.2}
.kwc-smallstatus {font-size:13px;color:#738094;margin:7px 0 0}
.kwc-pm-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:11px;padding:10px 22px 22px}
.kwc-pm-cell {background:#f6f9fc;border:1px solid #edf1f6;border-radius:14px;padding:17px 9px;text-align:center}
.kwc-pm-label {font-size:14px;font-weight:760;color:#47556b}
.kwc-pm-val {font-size:35px;font-weight:890;color:#17263e;letter-spacing:-.8px;line-height:1.4}
.kwc-pm-val span {font-size:13px;font-weight:600;letter-spacing:0;color:#617087}
.kwc-foot {padding:13px 21px;background:#f8fafc;border-top:1px solid #ecf0f5;font-size:13px;color:#68788e;line-height:1.55}
.kwc-subheading {margin:29px 0 12px;font-size:21px;font-weight:850;letter-spacing:-.5px;color:#1c2b45}
.kwc-metrics {display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:11px;margin-bottom:20px}
.kwc-metric {border:1px solid #e5ecf4;border-radius:15px;background:white;padding:17px 12px}
.kwc-metric-k {font-size:13px;color:#66758a;font-weight:730}
.kwc-metric-v {margin-top:9px;font-size:24px;font-weight:840;color:#203048;white-space:nowrap}
.kwc-metric-u {font-size:12px;color:#738094;font-weight:600;margin-left:2px}
.kwc-action {padding:19px 22px;border-radius:17px;background:#162b46;color:white;line-height:1.65;font-size:17px;font-weight:700;letter-spacing:-.2px;margin:21px 0 24px}
.kwc-action strong {color:#bde7e3;font-weight:850;margin-right:8px}
.kwc-legend {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-bottom:13px}
.kwc-legend-item {background:#f9fbfe;border:1px solid #e7ecf3;border-top:5px solid var(--grade-color);border-radius:11px;padding:13px 11px 14px;text-align:center}
.kwc-legend-name {font-size:16px;font-weight:850;color:#1e304d}
.kwc-legend-detail {font-size:11px;line-height:1.8;color:#5d6c82;margin-top:4px}
.kwc-note {font-size:12px;line-height:1.7;color:#778397;margin:9px 0}
@media(max-width:760px) {
.kwc-head-icon {font-size:29px}
.kwc-head-title {font-size:25px;letter-spacing:-.6px}
.kwc-head-sub {font-size:12px}
.kwc-cards {grid-template-columns:1fr;gap:13px}
.kwc-card-top {padding:19px 16px 6px}
.kwc-section-title {font-size:22px}
.kwc-face {font-size:67px}
.kwc-grade {font-size:32px}
.kwc-pm-grid {padding:10px 14px 16px}
.kwc-pm-val {font-size:31px}
.kwc-metrics {grid-template-columns:repeat(2,minmax(0,1fr))}
.kwc-metric-v {font-size:23px}
.kwc-action {font-size:15px;padding:16px}
.kwc-legend {grid-template-columns:repeat(2,minmax(0,1fr))}
}
</style>
"""

GRADE_INFO = {
    "좋음": {"face":"😊", "color":"#2F80ED"},
    "보통": {"face":"🙂", "color":"#27AE60"},
    "나쁨": {"face":"😷", "color":"#E78B29"},
    "매우나쁨": {"face":"😖", "color":"#E65353"},
    "자료없음": {"face":"❔", "color":"#8794A4"},
}


def _grade_rank(grade):
    return {"좋음":0, "보통":1, "나쁨":2, "매우나쁨":3}.get(grade)


def _metric_num(value, digits=0):
    if value is None:
        return "—"
    return f"{value:,.{digits}f}"


def _make_card(title, source, rec, stamp=""):
    """Render one self-contained PM card. Dynamic text is escaped."""
    pm25 = rec.get("pm25") if rec else None
    pm10 = rec.get("pm10") if rec else None
    grade = _grade(pm25, pm10)
    sty = GRADE_INFO[grade]
    measured = (f"{rec['measured_at']:%m월 %d일 %H:%M} 기준"
                if rec and rec.get("measured_at") else "측정시각 확인 불가")
    if stamp:
        measured = stamp
    note = " / ".join([source, measured])
    return (
        '<div class="kwc-card">'
        '<div class="kwc-card-top">'
        f'<div class="kwc-section-title">{html.escape(title)}</div>'
        f'<div class="kwc-tag">{html.escape(source)}</div>'
        '</div>'
        '<div class="kwc-grade-center">'
        f'<div class="kwc-face">{sty["face"]}</div>'
        f'<div class="kwc-grade" style="color:{sty["color"]}">{grade}</div>'
        '<div class="kwc-smallstatus">미세먼지 종합 상태</div>'
        '</div>'
        '<div class="kwc-pm-grid">'
        '<div class="kwc-pm-cell">'
        '<div class="kwc-pm-label">초미세먼지 PM2.5</div>'
        f'<div class="kwc-pm-val">{_metric_num(pm25)} <span>µg/m³</span></div>'
        '</div>'
        '<div class="kwc-pm-cell">'
        '<div class="kwc-pm-label">미세먼지 PM10</div>'
        f'<div class="kwc-pm-val">{_metric_num(pm10)} <span>µg/m³</span></div>'
        '</div>'
        '</div>'
        f'<div class="kwc-foot">{html.escape(note)}</div>'
        '</div>'
    )


def _action_tip(indoor_rec, outdoor_rec):
    """Cautious general guidance, not a ventilation-control rule."""
    ig = _grade_rank(_grade(indoor_rec.get("pm25"), indoor_rec.get("pm10"))) if indoor_rec else None
    og = _grade_rank(_grade(outdoor_rec.get("pm25"), outdoor_rec.get("pm10"))) if outdoor_rec else None
    co2 = indoor_rec.get("co2") if indoor_rec else None
    if ig is None and og is None:
        return "실내·실외 측정자료를 확인할 수 없습니다. 잠시 뒤 다시 확인해 주세요."
    if co2 is not None and co2 >= 1500:
        return "실내 CO₂ 농도가 높습니다. 외부 미세먼지 상태를 확인하고 안전한 환기 방법을 검토해 주세요."
    if og is not None and og >= 2:
        return "실외 미세먼지 농도가 높습니다. 장시간 창문 개방을 피하고, 실내 발생원과 공기청정기 상태를 확인해 주세요."
    if ig is not None and ig >= 2 and og is not None and og <= 1:
        return "실내 미세먼지 농도가 높습니다. 발생원을 확인하고 실외 상태를 고려해 짧게 환기해 주세요."
    if co2 is not None and co2 >= 1000:
        return "실내 CO₂ 농도가 높아지고 있습니다. 외부 미세먼지 상태를 확인한 뒤 환기를 검토해 주세요."
    if ig is not None and ig <= 1 and og is not None and og <= 1:
        return "실내와 실외의 미세먼지 상태가 양호합니다. 주기적으로 확인하고 평소 환기 습관을 유지해 주세요."
    return "실내·실외 측정값을 비교해 환기 여부를 판단해 주세요. 측정 위치와 측정시각은 서로 다릅니다."


def _read_indoor_dashboard():
    res, cfg = get_current_reading()
    rec = res.get("record")
    if res.get("error"):
        return None, res["error"], cfg
    fresh, minutes, reason = validate_freshness(rec)
    if not fresh:
        return None, reason, cfg
    return rec, "", cfg


def _read_outdoor_dashboard():
    try:
        key = str(st.secrets.get("AIRKOREA_SERVICE_KEY", "")).strip()
    except Exception:
        key = ""
    if not key:
        return None, "에어코리아 인증키가 설정되지 않았습니다."
    res = _fetch_suchang_airkorea(key)
    if res.get("error"):
        return None, res["error"]
    rec = res.get("record")
    at = rec.get("measured_at") if rec else None
    if at is None:
        return None, "수창동 측정시각을 확인할 수 없습니다."
    minutes = (datetime.now(KST) - at).total_seconds()/60.0
    if minutes < -3 or minutes > AIRKOREA_STALE_MINUTES:
        return None, f"수창동 측정자료가 오래되었습니다. 최종 측정: {at:%Y-%m-%d %H:%M}"
    return rec, ""


def _metric_tile(label, value, unit="", digits=0):
    return (
        '<div class="kwc-metric">'
        f'<div class="kwc-metric-k">{html.escape(label)}</div>'
        f'<div class="kwc-metric-v">{_metric_num(value, digits)}'
        f'<span class="kwc-metric-u">{html.escape(unit)}</span></div>'
        '</div>'
    )


def _grade_legend():
    items = [
        ("좋음", "#2F80ED", "PM2.5 0–15", "PM10 0–30"),
        ("보통", "#27AE60", "PM2.5 16–35", "PM10 31–80"),
        ("나쁨", "#E78B29", "PM2.5 36–75", "PM10 81–150"),
        ("매우나쁨", "#E65353", "PM2.5 76 이상", "PM10 151 이상"),
    ]
    return '<div class="kwc-legend">' + ''.join(
        f'<div class="kwc-legend-item" style="--grade-color:{color}">'
        f'<div class="kwc-legend-name">{name}</div>'
        f'<div class="kwc-legend-detail">{p25}<br>{p10}</div>'
        '</div>' for name,color,p25,p10 in items
    ) + '</div>'


def _render_childcare_dashboard():
    """One timed fragment; both cards and advice refresh together every 3 min."""
    indoor, indoor_err, cfg = _read_indoor_dashboard()
    outdoor, outdoor_err = _read_outdoor_dashboard()
    status = "실내·실외 측정자료 업데이트 중"
    if indoor and outdoor:
        status = "실내·실외 최신 측정자료 조회 완료"
    elif indoor:
        status = "실내 측정자료 조회 완료 · 실외 자료 확인 중"
    elif outdoor:
        status = "실외 측정자료 조회 완료 · 실내 자료 확인 중"

    content = (
        CHILDCARE_CSS
        + '<div class="kwc-root">'
        + '<div class="kwc-statusbar"><span class="kwc-statusdot"></span>'
        + f'{html.escape(status)} · 페이지 약 3분 간격 자동 갱신</div>'
        + '<div class="kwc-cards">'
        + _make_card("실내", "실내 측정", indoor)
        + _make_card("실외", "수창동 측정소", outdoor)
        + '</div>'
        + '<div class="kwc-subheading">실내 환경 상세 정보</div>'
        + '<div class="kwc-metrics">'
        + _metric_tile("온도", indoor.get("temp") if indoor else None, "°C", 1)
        + _metric_tile("습도", indoor.get("humi") if indoor else None, "%")
        + _metric_tile("이산화탄소 CO₂", indoor.get("co2") if indoor else None, "ppm")
        + _metric_tile("휘발성유기화합물", indoor.get("voc") if indoor else None, "ppb")
        + _metric_tile("소음", indoor.get("noise") if indoor else None, "dB")
        + '</div>'
        + f'<div class="kwc-action"><strong>오늘의 안내</strong> {html.escape(_action_tip(indoor, outdoor))}</div>'
        + '<div class="kwc-subheading">미세먼지 등급 안내</div>'
        + _grade_legend()
        + '<div class="kwc-note">'
        + '※ 등급은 표시된 PM2.5·PM10 중 더 나쁜 등급을 기준으로 구분하며, '
        + '두 자료의 측정 위치와 시각은 서로 다를 수 있습니다.'
        + '</div>'
        + '<div class="kwc-note">'
        + '실내 측정: 케이웨더 Air365 · 실외 측정: 에어코리아 수창동 도시대기측정소(약 0.4 km). '
        + '실외 수치는 어린이집 부지에서 직접 측정한 값이 아닙니다.'
        + '</div>'
        + ( '<div class="kwc-note">현재 실내 측정자료는 어린이집 외의 위치에서 수집 중이며, 현장 설치 이후 해당 시설의 자료로 전환됩니다.</div>'
            if not cfg["installed_at_site"] else '' )
        + '</div>'
    )
    st.markdown(content, unsafe_allow_html=True)
    if indoor_err:
        st.warning("실내 자료 확인: " + indoor_err)
    if outdoor_err:
        st.warning("실외 자료 확인: " + outdoor_err)


if hasattr(st, "fragment"):
    _childcare_dashboard_fragment = st.fragment(run_every="180s")(_render_childcare_dashboard)
else:
    _childcare_dashboard_fragment = _render_childcare_dashboard


def render_childcare_page():
    """Simplified public QR page: no trial banner or model/serial heading."""
    st.markdown(CHILDCARE_CSS, unsafe_allow_html=True)
    st.markdown(
        '<div class="kwc-root"><div class="kwc-head">'
        '<div class="kwc-head-icon">🌿</div>'
        '<div><div class="kwc-head-title">도원센트럴어린이집<br>실내·실외 공기질</div>'
        f'<div class="kwc-head-sub">{html.escape(CHILDCARE_ADDRESS)} · 최신 측정자료 안내</div>'
        '</div></div></div>',
        unsafe_allow_html=True,
    )
    _childcare_dashboard_fragment()

def render_in_main_demo():
    st.divider()
    with st.expander("케이웨더 IAQ-CW 240번 · 공식 API 최신값 시험", expanded=True):
        st.info("현재는 어린이집 설치 예정 장비의 단독 실시간 API 시험입니다. 위 평리3동/아림 자료와 합산하거나 혼용하지 않습니다.")
        # Do not use a timed fragment inside an externally created expander.
        # The separate QR page uses automatic 3-minute refreshing.
        _render_values()
        st.caption("QR 단독 화면: 배포된 웹데모 주소 뒤에 `?view=childcare`를 붙여 접속하세요.")
