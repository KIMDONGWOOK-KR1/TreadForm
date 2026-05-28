# PRD-2: 3대 부상 방지 지표 계산 엔진

> 📍 항상 함께 참조: **[PRD-0-context.md](./PRD-0-context.md)**
> 📍 이전 단계 산출물: **[PRD-1-pose-pipeline.md](./PRD-1-pose-pipeline.md)**
> 📍 관련 단계: **[PRD-8-video-input-spec.md](./PRD-8-video-input-spec.md)** (`run_full_analysis` 시그니처 확장)

---

## 🎯 이 단계의 목표

Step 1에서 만든 깨끗한 keypoints DataFrame + 좌/우 착지 인덱스를 입력받아, **부상 방지 3대 지표 + 좌우 비대칭 보조 지표**를 계산하고 🔴🟡🟢 상태로 판정하는 모듈을 구현한다.

---

## 📥 입력 (의존성)

- **이전 단계 산출물**:
    - 전처리된 DataFrame (33 keypoints × N frames)
    - 좌/우 착지 인덱스 dict (`{"left": np.array, "right": np.array}`)
- **필수 참조**: `PRD-0-context.md`, `PRD-1-pose-pipeline.md`

---

## ✅ 완료 조건 (Definition of Done)

- [ ] `config.py`에 모든 지표 임계값 추가 완료
- [ ] 무릎 굴곡 각도 계산 + 4단계 판정 (Stiff/Borderline/Good/OverBent)
- [ ] Foot Strike 각도 계산 + 3단계 판정 (Heel/Mid/Forefoot)
- [ ] 오버스트라이딩 거리 계산 + 2단계 판정 (Over/Good)
- [ ] 수직 진폭 계산 (1 Stride 단위) + 2단계 판정 (High/Good)
- [x] **cm-aware 모드 (Phase 1, 2026-05-28)**: 신장 입력 + body_norm_length 환산으로 절대 cm 임계 (`VO_HIGH_THRESHOLD_CM=10`), 미입력 시 정규화 fallback. §[R4-cm] 참조.
- [ ] 좌우 비대칭 비율 계산 (보조 지표)
- [ ] 통합 결과 JSON 스키마 정의 (Pydantic 모델)
- [ ] 단위 테스트 모든 케이스 통과
- [ ] 합성 데이터로 임계값 경계 케이스(Borderline) 검증

---

## 📋 작업 항목

### 1. `config.py`에 임계값 상수 추가

```python
# === 무릎 굴곡 각도 ===
KNEE_STIFF_THRESHOLD = 160       # 이상 → Stiff Knee
KNEE_GOOD_MIN = 140              # 정상 범위 하한
KNEE_GOOD_MAX = 160              # 정상 범위 상한
KNEE_OVERBENT_THRESHOLD = 140    # 미만 → Over Bent
KNEE_BORDERLINE_TOLERANCE = 5    # ±5° 경계 → Warning

# === Foot Strike 각도 ===
# 부호 정의 (러닝 메카닉스 기준): 양수 = 발끝 들림 (dorsiflexion) = heel strike 경향
HEEL_STRIKE_THRESHOLD = 3        # 초과 → Heel Strike    🔴
FOREFOOT_STRIKE_THRESHOLD = -3   # 미만 → Forefoot Strike 🟡
# 부호 정정 + ±5→±3 보수성 축소 (2026-05-17). 자세한 근거는 §R2 References.

# === 오버스트라이딩 ===
OVERSTRIDE_THRESHOLD = 0.15      # 정규화 좌표 기준 X 편차 (자체 결정, §R3)

# === 수직 진폭 ===
VERTICAL_OSC_HIGH_THRESHOLD = 0.06  # 정규화 Y 기준 (2026-05-17 0.08→0.06, §R4 fallback)
VO_HIGH_THRESHOLD_CM = 10.0          # cm-aware 모드 (Phase 1, 2026-05-28, §R4-cm)

# === 좌우 비대칭 ===
ASYMMETRY_WARNING_THRESHOLD = 0.1            # 10% (Zifchock 2008, Pappas 2015, §R5)
ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD = 0.10     # 좌/우 발 visibility diff 임계 (§R6)
```

**비대칭 트리거 정책 (2026-05-17):**
- `is_warning` 트리거는 `knee_angle_ratio` 와 `oscillation_ratio` 만 사용.
- `strike_count_ratio` 는 결과 객체에 정보성으로 노출하되 트리거에서 제외 (측면 촬영 occlusion 의 dominant 노이즈 신호이기 때문, §R5/R6).
- 좌/우 발 평균 visibility 차이가 `ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD` 를 초과하면 `strike_count_ratio` 를 NaN 으로 대체 (검출 불가 신호로 명시).
- `is_warning=True` AND `NOT_SIDE_VIEW` quality warning 부재 시 `SIDE_VIEW_ASYM_CAUTION` caveat 카드를 자동 첨부 (`quality_assessor.apply_asymmetry_caveats`).

### 2. `server/analyzer/metrics/knee_flexion.py`

```python
def calculate_knee_angle(hip: np.ndarray, knee: np.ndarray, ankle: np.ndarray) -> float:
    """벡터 내적으로 무릎 굴곡 각도(°) 산출."""

def classify_knee_status(angle: float) -> str:
    """
    Returns: "stiff_knee" | "borderline" | "good_flexion" | "over_bent"
    """

def analyze_knee_flexion(df: pd.DataFrame, strike_indices: dict) -> dict:
    """
    좌/우 무릎 각도를 착지 프레임에서 계산하고 상태별 카운트.

    Returns:
        {
            "avg_angle": float,
            "left_avg": float,
            "right_avg": float,
            "status_counts": {"stiff": int, "good": int, "over_bent": int, "borderline": int},
            "per_strike": [{"frame": int, "angle": float, "status": str, "foot": "left"|"right"}]
        }
    """
```

### 3. `server/analyzer/metrics/foot_strike.py`

```python
def calculate_foot_strike_angle(heel: np.ndarray, foot_index: np.ndarray) -> float:
    """발뒤꿈치-발끝 벡터의 수평 기울기(°)."""

def classify_foot_strike(angle: float) -> str:
    """
    Returns: "heel_strike" | "mid_foot_strike" | "forefoot_strike"
    """

def analyze_foot_strike(df: pd.DataFrame, strike_indices: dict) -> dict:
    """
    Returns:
        {
            "status_counts": {"heel": int, "midfoot": int, "forefoot": int},
            "per_strike": [...]
        }
    """
```

### 4. `server/analyzer/metrics/overstriding.py`

```python
def calculate_overstride_distance(ankle: np.ndarray, hip: np.ndarray) -> float:
    """착지 시점 발목과 골반의 X좌표 차이 (정규화 좌표)."""

def classify_overstride(distance: float) -> str:
    """Returns: "over_stride" | "good_stride" """

def analyze_overstriding(df: pd.DataFrame, strike_indices: dict) -> dict:
    """
    Returns:
        {
            "avg_distance": float,
            "status_counts": {"good": int, "over": int},
            "per_strike": [...]
        }
    """
```

### 5. `server/analyzer/metrics/vertical_osc.py`

```python
def calculate_oscillation_per_stride(hip_y_series: np.ndarray,
                                      same_foot_strikes: np.ndarray) -> list:
    """동일 발 연속 착지 사이(1 Stride) 골반 Y의 max-min."""

def classify_oscillation(value: float,
                          threshold: float = VERTICAL_OSC_HIGH_THRESHOLD) -> str:
    """Returns: "high_oscillation" | "good_oscillation"
    threshold 의 단위는 호출측 책임 (정규화면 norm, cm-aware 모드면 cm 등가 norm)."""

def analyze_vertical_oscillation(
    df: pd.DataFrame,
    strike_indices: dict,
    height_cm: float | None = None,
    body_norm_length: float | None = None,
) -> dict:
    """
    좌/우 각각 1 Stride 단위로 계산 후 평균.

    cm-aware 모드 (Phase 1, 2026-05-28):
        height_cm + body_norm_length 둘 다 주어지면
        scale = height_cm / body_norm_length 로 vo_cm 환산 후 VO_HIGH_THRESHOLD_CM
        임계로 판정. 하나라도 None/NaN/≤0 이면 정규화 임계 fallback.
        body_norm_length 는 analyzer.body_scale.compute_body_norm_length(df) 로 추정
        (프레임별 max(L/R ankle_y) − nose_y 의 median).

    Returns:
        {
            "avg_value": float,                  # 정규화 평균 (항상)
            "left_avg": float,
            "right_avg": float,
            "status": "high" | "good",
            "per_stride": [..., "value", "value_cm" | None, "status", "foot"],
            "avg_value_cm": float | None,        # cm-aware 모드일 때만 값
            "threshold_cm": float | None,
            "threshold_norm": float,             # 실제 적용 정규화 임계
            "scale_cm_per_norm": float | None,
            "height_cm": float | None,
            "body_norm_length": float | None,
        }
    """
```

**height_cm 입력 경로 (Phase 2, 2026-05-28):**
- 일반 모드: 앱 `HomeScreen` 신장 카드 → `AsyncStorage('vr.user_height_cm')` → 업로드 form `user_height_cm`.
- 트레이너 모드: 회원 등록 시 `MemberCreate.height_cm` → `MEMBERS[member_id]["height_cm"]` → 업로드 form 미첨부 시 서버가 자동 fallback (`api/upload._run_analysis_task`).
- 우선순위: form `user_height_cm` > 회원 프로필 `height_cm` > `None` (정규화 fallback).

### 6. `server/analyzer/metrics/asymmetry.py` (보조 지표)

```python
def calculate_asymmetry_ratio(left_value: float, right_value: float) -> float:
    """좌/우 비대칭 비율 = |L - R| / max(L, R)"""

def analyze_asymmetry(strike_indices: dict,
                       knee_result: dict,
                       vertical_result: dict,
                       foot_visibility: dict | None = None) -> dict:
    """
    Args:
        foot_visibility: {"left": float, "right": float} 좌/우 발(heel/foot_index/ankle)
            평균 visibility. diff > ASYMMETRY_FOOT_VIS_DIFF_THRESHOLD 시
            strike_count_ratio → NaN (검출 불가능 신호).

    Returns:
        {
            "strike_count_ratio": float,    # 정보성만 — is_warning 트리거 X
            "knee_angle_ratio": float,      # 트리거 O
            "oscillation_ratio": float,     # 트리거 O
            "is_warning": bool              # knee 또는 osc 가 임계 초과 시 True
        }
    """
```

### 7. `server/models/analysis_result.py` (Pydantic 통합 모델)

```python
from pydantic import BaseModel
from typing import Literal

class StatusCounts(BaseModel):
    # 지표별로 다른 키를 가지므로 dict로 유연하게
    ...

class MetricResult(BaseModel):
    avg_value: float | None = None
    status_counts: dict[str, int]
    per_event: list[dict]  # 착지/스트라이드별 상세

class DangerTimestamp(BaseModel):
    time_sec: float
    type: Literal["heel_strike", "stiff_knee", "over_stride", "high_oscillation"]
    color: Literal["red"] = "red"

class AnalysisResult(BaseModel):
    analysis_id: str
    summary: dict
    metrics: dict  # {knee_flexion, foot_strike, overstriding, vertical_oscillation}
    asymmetry: dict
    danger_timestamps: list[DangerTimestamp]
    # 아래 두 필드는 PRD-8 도입 후 추가됨.
    # confidence: Literal["high", "medium", "low"]
    # warnings: list[QualityWarning]
```

### 8. `server/analyzer/__init__.py`에 통합 함수

```python
def run_full_analysis(video_path: str) -> AnalysisResult:
    """
    전체 파이프라인 실행:
    1. extract_pose_series
    2. preprocess_pose_dataframe
    3. detect_left_right_strikes
    4. analyze_knee_flexion, foot_strike, overstriding, vertical_oscillation
    5. analyze_asymmetry
    6. Danger 타임스탬프 수집
    """
```

> ⚠️ **PRD-8 도입 후 시그니처 확장 예정**
>
> 입력 영상 사양 & 검증 (PRD-8) 구현 시 이 함수는 다음 두 단계가 추가된다:
> - **시작 전**: `video_validator.validate(video_path)` → 하드 요건 미충족 시 `VideoValidationError` 발생 (mediapipe 호출 비용 절약)
> - **종료 직전**: `quality_assessor.assess(raw_df, fps, cadence_spm)` → `confidence` + `warnings` 산출
>
> `AnalysisResult` 에도 두 필드 추가:
> ```python
> confidence: Literal["high", "medium", "low"]
> warnings: list[QualityWarning]
> ```
> 자세한 통합 코드는 PRD-8 §5 참조.

### 9. 테스트 작성

`server/tests/test_metrics.py`

```python
# 합성 데이터 픽스처
@pytest.fixture
def synthetic_running_df():
    """이상적인 러닝 자세를 시뮬레이션한 100프레임 DataFrame."""

# 각 지표별 경계 케이스
def test_knee_angle_exactly_at_threshold():
    """160도 정확히 → borderline 판정"""

def test_knee_angle_at_165():
    """165도 → stiff_knee 판정 (160 + 5 borderline 초과)"""

def test_foot_strike_at_minus_5():
    """경계값 -5° → mid_foot_strike (≤ 조건이므로)"""

def test_overstride_exactly_at_threshold():
    """0.15 정확히 → good_stride (> 조건이므로)"""

def test_vertical_oscillation_per_stride():
    """동일 발 사이만 측정되는지 검증"""

def test_asymmetry_ratio_calculation():
    """L=100, R=120 → ratio = 0.1667"""
```

---

## 🧪 검증 방법

### 1단계: 단위 테스트
```bash
cd server
pytest tests/test_metrics.py -v
```

### 2단계: 합성 데이터 시각화
```python
# 이상적인 자세 → 모든 지표 🟢 나오는지
# 불량 자세 (heel strike 시뮬레이션) → 🔴 정확히 검출되는지
```

### 3단계: 실제 영상 통합 테스트
```python
from analyzer import run_full_analysis

result = run_full_analysis("samples/test_run_10s.mp4")
print(result.model_dump_json(indent=2))

# 검증
assert "knee_flexion" in result.metrics
assert result.summary["total_strikes"] > 0
assert isinstance(result.danger_timestamps, list)
```

---

## 💬 추천 Vibe Coding 명령

```
1. "PRD-2-metrics.md를 보고 config.py에 모든 지표 임계값 상수를 추가해줘."

2. "server/analyzer/metrics/knee_flexion.py에 무릎 굴곡 각도 계산과 4단계 상태 판정 함수를 구현. classify_knee_status는 Borderline 우선 판정 로직 적용."

3. "server/analyzer/metrics/ 폴더에 foot_strike, overstriding, vertical_osc, asymmetry 4개 모듈을 순차적으로 구현해줘. 각각 단위 테스트도 함께."

4. "server/models/analysis_result.py에 Pydantic 모델 정의. AnalysisResult, MetricResult, DangerTimestamp 포함."

5. "analyzer/__init__.py에 run_full_analysis 통합 함수 구현. Step 1 모듈을 import해서 end-to-end로 동작하게."

6. "tests/test_metrics.py에 경계 케이스 중심으로 단위 테스트 작성. Borderline 판정 검증 필수."
```

---

## 📤 산출물

### 생성될 파일
```
server/
├── config.py                          # (업데이트)
├── analyzer/
│   ├── __init__.py                    # (업데이트: run_full_analysis 추가)
│   └── metrics/
│       ├── __init__.py
│       ├── knee_flexion.py
│       ├── foot_strike.py
│       ├── overstriding.py
│       ├── vertical_osc.py
│       └── asymmetry.py
├── models/
│   ├── __init__.py
│   └── analysis_result.py
└── tests/
    └── test_metrics.py
```

### 다음 단계로 넘길 인터페이스

**Step 3(렌더링·코칭)이 사용할 입력**:

```python
# 통합 분석 결과
result: AnalysisResult

# 주요 사용 필드
result.metrics["knee_flexion"]["per_strike"]   # 프레임별 무릎 상태 → 영상 오버레이용
result.danger_timestamps                       # 타임라인 마커용
result.metrics                                 # 코칭 메시지 생성용
result.summary                                 # 요약 출력용
```

---

## ⚠️ 흔한 함정

1. **Borderline 판정 우선순위**
   - `if abs(angle - 160) <= 5: return "borderline"` 먼저 체크
   - 그 후 절대값 비교 (`if angle >= 160: stiff` 등)
   - 순서 바뀌면 Borderline이 검출 안 됨

2. **MediaPipe 좌표는 정규화** (0~1)
   - 오버스트라이딩 임계값 0.15는 정규화 좌표 기준
   - 만약 픽셀 좌표 사용 시 화면 너비로 나누기 필요

3. **수직 진폭은 1 Stride 단위** (Left→Left or Right→Right)
   - Step(좌우 교차) 단위와 혼동 금지
   - 보통 1 Stride는 약 30~50 프레임 (30fps 기준)

4. **per_strike vs per_stride 구분**
   - Foot Strike, Knee Flexion: 착지마다 (per_strike)
   - Vertical Oscillation: 1 Stride마다 (per_stride)

5. **Danger 타임스탬프 변환**
   - `time_sec = frame_idx / TARGET_FPS`
   - 영상 fps가 30이 아닐 수 있으니 메타데이터에서 추출

---

## 📚 학술 근거 / References

각 임계값은 러닝 바이오메카닉스 문헌의 1차 출처에 기반한다. 우리 측정/구현 방식은 측면 트레드밀 영상 기반의 2D 정규화 좌표라는 환경 제약을 반영해 일부 임계는 자체 보정을 거쳤다 — 그 경우에도 출처의 일반 원리를 따른다.

### [R1] 무릎 굴곡 (165° stiff / 140° over_bent / ±3° borderline, 2026-05-25 재조정)

우리 측정 시점은 **착지 시점 (IC, initial contact)** — 발목 Y 가 가장 아래로 내려간 프레임 (foot_strike_detector 가 식별). 측정 방식은 hip-knee-ankle 의 내각(°) (180° = straight leg, 90° = right angle). 즉 임계 165°는 **IC flexion ≈ 15° (stiff knee 경계)**, 140°는 **flexion ≈ 40° (과굴곡 경계)** 에 해당한다.

- **Heiderscheit BC, Chumanov ES, Michalski MP, Wille CMA, Ryan MB.** Effects of step rate manipulation on joint mechanics during running. *Med Sci Sports Exerc.* 2011;43(2):296-302. doi:[10.1249/MSS.0b013e3181ebedf4](https://doi.org/10.1249/MSS.0b013e3181ebedf4) — n=45 healthy recreational runner 의 preferred condition IC knee flexion baseline = **17.8° ± 4.0°** (논문 본문 보고). stiff knee 패턴이 shock absorption 부족과 부상 위험에 연결됨을 정량.

**임계의 통계적 근거 (SD 단위 매핑):** Heiderscheit baseline (17.8° ± 4.0°) ↔ 우리 컨벤션:

| 우리 knee angle | = IC flexion | baseline 기준 위치 |
|---|---|---|
| 162.2° | 17.8° | mean (baseline) |
| **165°** (stiff 임계) | **15°** | **mean − 0.7 SD** (stiff 방향 outlier 경계) |
| 158.5° (자체 평균) | 21.5° | mean + 0.9 SD (숙련 러너 측 더 굽힘) |
| 140° (over_bent) | 40° | mean + 5.6 SD (매우 보수적 하한) |

**자체 데이터 검증:** pace 530/6/7/630 4 영상 200 strikes 평균 158.5° / max 164° / > 165° 0건 / < 140° 0건. False positive 0건. 2026-05-25 재조정 이전 임계 (160°/±5°) 는 분포 모드 [158,160) 정점을 가로질러 94.5% borderline 으로 빠지며 신호 가치 상실 → 165°/±3° 로 완화 후 good 비중 5% → 94.5% 회복.

### [R1-future] Peak Flexion 측정 (향후 작업)

**현재 미구현. Souza 2016 인용을 위한 deferred 작업.**

#### 동기

현재 [R1] 은 IC 시점만 평가하나, 충격 흡수 능력 전체를 평가하려면 **mid-stance peak flexion (입각기 최대 굴곡)** 측정이 표준이다. 같은 IC angle 이더라도 peak 까지 도달하는 굴곡량이 다르면 shock absorption 결과가 다르다 — 즉 IC 와 peak 는 보완 지표.

#### 학술 근거 (deferred citation)

- **Souza RB.** An evidence-based videotaped running biomechanics analysis. *Phys Med Rehabil Clin N Am.* 2016;27(1):217-236. PMC: [PMC4714754](https://pmc.ncbi.nlm.nih.gov/articles/PMC4714754/) — 2D 비디오 running gait analysis 의 표준 프로토콜. **stance phase peak flexion < 45° = stiff** (shock absorption 부족) 권장. 본 지표 구현 시 1차 근거.

#### 구현 의사 코드

```
1. 기존 detect_left_right_strikes() → IC frame 인덱스 확보
2. (신규) detect_toe_off(ankle_y_series, ic_frames) → 각 IC 다음
   ankle_y 가 다시 올라가기 시작하는 frame (find_peaks 응용, 반전된 신호)
3. 각 strike 의 stance phase = [ic_frame, toe_off_frame]
4. 그 범위 내 knee_angle 시리즈의 최솟값 = peak_flexion_angle
5. classify_peak_flexion(angle):
     PEAK_INSUFFICIENT_THRESHOLD = 145  # = IC flexion 35°, Souza 권장 미달
     PEAK_GOOD_TARGET = 135             # = IC flexion 45°, Souza 권장
     return "insufficient_flexion" | "good_peak_flexion" | "borderline"
```

#### 기술 제약

- **Toe-off 검출**: 현재 구현 없음. ankle_y 의 IC 직후 local minimum 종료 시점 식별 알고리즘 필요.
- **시간 분해능**: 60fps 에서 peak flexion 시점 위치 정확도 ±2~3° (peak 근처 변화율 ~5~10°/50ms, 1프레임 ~17ms 분해능). 120fps 영상 입력 시 ±1° 로 향상 가능. 현재 [R1] tolerance ±3° 와 동일 수준이라 충분히 흡수 가능.
- **2D perspective 한계**: peak 시점의 무릎이 sagittal plane 에서 살짝 회전하면 측면 영상에서 각도 측정 오차 증가. Souza 2016 도 같은 한계를 명시.

#### 구현 우선순위

P3 (after 시연 영상 / 사용자 피드백 / 다른 러너 영상 다양화 검증). 단일 측정 (IC) 만으로도 stiff knee 신호 분류 가능하고, peak 추가는 정밀도 향상이지 신호 부재 해소 아님.

### [R2] Foot Strike Pattern (±3° 임계)

발뒤꿈치(HEEL) → 발끝(FOOT_INDEX) 벡터의 수평 기준 기울기. 양수 = 발끝 들림(dorsiflexion, heel strike 경향), 음수 = 발끝 처짐(plantarflexion, forefoot 경향).

- **Altman AR, Davis IS.** A kinematic method for footstrike pattern detection in barefoot and shod runners. *Gait Posture.* 2012;35(2):298-300. doi:[10.1016/j.gaitpost.2011.09.104](https://doi.org/10.1016/j.gaitpost.2011.09.104) — 분류 방법론의 표준. FSA > 0 = rearfoot strike(RFS), < 0 = forefoot/midfoot strike(FFS/MFS), sagittal plane 발 각도. Strike Index 와 R=0.92 강한 상관.
- **Lieberman DE, Venkadesan M, Werbel WA, Daoud AI, D'Andrea S, Davis IS, Mang'eni RO, Pitsiladis Y.** Foot strike patterns and collision forces in habitually barefoot versus shod runners. *Nature.* 2010;463(7280):531-535. doi:[10.1038/nature08723](https://doi.org/10.1038/nature08723) — rearfoot strike 의 충격 부하 및 부상 위험 정량.

**자체 결정 명시:** Altman & Davis 의 cutoff 는 정확히 0°. 우리 ±3° 마진은 **2D 영상 perspective + 발 길이 정규화 노이즈에 대한 안전 마진** (자체, 2026-05-17 ±5 → ±3 으로 임상 분류 관행에 정합 보정).

### [R3] 오버스트라이딩 (정규화 X 편차 0.15)

착지 시 발목이 골반보다 얼마나 앞에 있는가의 수평 거리 (정규화 좌표).

- **Heiderscheit BC et al. 2011 MSSE** ([R1] 동일) — step length 감소 시 hip/knee loading 동시 감소. overstride 가 braking impulse + COM excursion + impact loading 모두를 악화.
- **Schubert AG, Kempf J, Heiderscheit BC.** Influence of stride frequency and length on running mechanics: a systematic review. *Sports Health.* 2014;6(3):210-217. doi:[10.1177/1941738113508544](https://doi.org/10.1177/1941738113508544) — overstride 조건에서 무릎 신전 모멘트와 rearfoot 각속도가 유의 증가, 골절성 부상 메커니즘과 연결.
- 우리 임계 0.15 (정규화)는 1280×720 측면 영상의 자체 보정 — 사람 신장이 화면 60~80% 점유한다는 PRD-8 촬영 가이드를 가정. 임상 절대 거리(cm) 보다 보수적인 임계.

### [R4] 수직 진폭 (정규화 Y 0.06, 1 Stride 단위 max-min)

- **Tartaruga MP, Brisswalter J, Peyré-Tartaruga LA, et al.** The relationship between running economy and biomechanical variables in distance runners. *Res Q Exerc Sport.* 2012;83(3):367-375. doi:[10.1080/02701367.2012.10599870](https://doi.org/10.1080/02701367.2012.10599870) — VO와 running economy 의 유의한 음의 상관.
- **Folland JP, Allen SJ, Black MI, Handsaker JC, Forrester SE.** Running technique is an important component of running economy and performance. *Med Sci Sports Exerc.* 2017;49(7):1412-1423. doi:[10.1249/MSS.0000000000001245](https://doi.org/10.1249/MSS.0000000000001245) — VO 가 modifiable 한 핵심 economy 결정 요인.
- **Cavanagh PR, Williams KR.** The effect of stride length variation on oxygen uptake during distance running. *Med Sci Sports Exerc.* 1982;14(1):30-35. — VO 측정 방법론의 고전 문헌.
- 일반 통념: healthy VO 범위 약 6~10cm. 신장 1.7m + PRD-8 촬영 가이드 (인체 화면 60~80% 점유) 기준 정규화 Y 약 0.035~0.060. **우리 정규화 임계 0.06** 은 healthy upper bound 와 정합 (2026-05-17 0.08 → 0.06 으로 학술 통념에 맞춰 축소).

### [R4-cm] cm-aware 모드 (Phase 1, 2026-05-28)

위 정규화 임계는 신장 1.7m + 프레이밍 60~80% **가정에 묶여** 있다. 키 큰 사람(190cm)이나 줌 차이로 프레이밍이 바뀌면 같은 mechanical VO 도 정규화 값이 달라져 신호가 왜곡됨. 사용자 입력 신장 + 프레임 내 신체 길이 측정으로 절대 cm 환산해 가정을 제거한다.

- **알고리즘**:
  ```
  body_norm_length = median_over_frames(max(L_ankle_y, R_ankle_y) - nose_y)   # 정규화 단위
  scale_cm_per_norm = height_cm / body_norm_length                            # cm / norm
  vo_cm = vo_norm * scale_cm_per_norm
  status = "high" if vo_cm > VO_HIGH_THRESHOLD_CM (10) else "good"
  ```
  좌/우 ankle 중 화면상 더 아래(`y` 큰 값) 를 사용해 한쪽 occlusion 에 robust (`np.fmax`). preprocessor 가 visibility < 0.4 를 NaN 마스킹하므로 별도 visibility 필터링 불필요. **모든 프레임에서 nose+ankle 결측 시 body_norm_length=NaN → 정규화 임계 fallback** (조용한 degrade).
- **임계 근거**: Cavanagh & Williams 1982 의 healthy upper bound 10cm. Folland 2017 / Tartaruga 2012 도 cm 단위로 economy 와의 음의 상관 보고.
- **모드 분기**: `analyze_vertical_oscillation(..., height_cm, body_norm_length)` 가 둘 다 유효(>0)일 때 cm-aware, 아니면 정규화 fallback. 결과 dict 의 `avg_value_cm` / `threshold_cm` / `scale_cm_per_norm` 가 None 이면 fallback 모드임을 나타냄 (csv_reporter / coach_message 가 분기 가능).
- **함정**:
  - body_norm_length 가 너무 작은 값(예: < 0.1) 이면 scale 폭발 → 비현실적 cm. 현재는 보호하지 않음 (PRD-8 측면 촬영 + 프레이밍 60~80% 가이드 가정). 향후 운영 데이터로 sanity bound 추가 검토.
  - 프레이밍이 크게 바뀌는 영상(zoom in/out, panning) 은 median 으로 흡수되지만 극단적으로 변하면 부정확. 트레드밀 + 고정 삼각대 가정에서는 무시 가능.
  - cm 정밀도는 **수직 진폭에만** 적용. overstride 0.15 정규화 임계는 여전히 프레이밍 가정 사용 — 같은 환산을 적용하면 가로 거리(X) 도 cm 환산 가능하나, perspective 왜곡 영향이 커 현재 deferred.

### [R5] 좌우 비대칭 (10% 임계)

- **Zifchock RA, Davis I, Higginson J, Royer T.** The symmetry angle: a novel, robust method of quantifying asymmetry. *Gait Posture.* 2008;27(4):622-627. doi:[10.1016/j.gaitpost.2007.08.006](https://doi.org/10.1016/j.gaitpost.2007.08.006) — Symmetry Index/Angle 정량 방법론 (우리 `|L-R|/max(L,R)` 의 원전).
- **Zifchock RA, Davis I, Hamill J.** Kinetic asymmetry in female runners with and without retrospective tibial stress fractures. *J Biomech.* 2006;39(15):2792-2797. PMID:[16289516](https://pubmed.ncbi.nlm.nih.gov/16289516/) — 부상 이력자 vs 무상자 GRF 비대칭 분포 검증.
- **Pappas P, Paradisis G, Vagenas G.** Leg and vertical stiffness (a)symmetry between dominant and non-dominant legs in young male runners. *Hum Mov Sci.* 2015;40:273-283. doi:[10.1016/j.humov.2015.01.005](https://doi.org/10.1016/j.humov.2015.01.005) PMID:[25625812](https://pubmed.ncbi.nlm.nih.gov/25625812/) — healthy 러너에서 자연 ASI 가 ground reaction force 1.81% / contact time 2.83% / leg stiffness 6.38% 까지 — **즉 10% 가 healthy 분포 너머의 임상 의미 있는 비대칭의 경계점**.
- **Parkinson AO, Apps CL, Morris JG, Barnett CT, Lewis MGC.** The Calculation, Thresholds and Reporting of Inter-Limb Strength Asymmetry: A Systematic Review. *J Sports Sci Med.* 2021;20(4):594-617. doi:[10.52082/jssm.2021.594](https://doi.org/10.52082/jssm.2021.594) PMID:[35321131](https://pubmed.ncbi.nlm.nih.gov/35321131/) — 18편 문헌에서 비대칭 임계 적용 메타분석. 15편이 10~15% 범위 임계를 채택 — **임상 합의 수준**.

### [R6] 비대칭 트리거 격하 + visibility 가중 (자체 검증, 2026-05-16)

- **자체 데이터**: 동일 숙련 러너의 4 페이스(530/6/7/630) 측면 영상에서 strike_count 비대칭이 false positive 다발(diff=2~3, ratio=10~16%) 확인. knee/osc 는 모두 정상 (≤2%).
- **설계 결정**: `is_warning` 트리거에서 strike_count_ratio 제외, knee/osc 만 사용. strike_count_ratio 는 결과 객체에 정보성으로 노출.
- **Visibility-weighted scoring**: occlusion 자동 감지를 위해 좌/우 발 평균 visibility diff > 0.10 시 strike_count_ratio → NaN. 동일 4 영상에서 우측 발(camera-near) 0.96 / 좌측 발(far-side) 0.88 일관 패턴 관측.
- **이론적 배경**: MediaPipe BlazePose visibility 출력은 frame 별 키포인트 검출 신뢰도이며, occluded landmark 의 좌표는 visibility 가 떨어지므로 한쪽이 일관되게 낮은 영상에서는 해당 측 strike 검출이 누락될 가능성이 높다 → 카운트 비대칭이 실제 비대칭이 아닌 검출 누락의 결과.

### [R7] MediaPipe BlazePose (model_complexity=2, Heavy)

- **Bazarevsky V, Grishchenko I, Raveendran K, Zhu T, Zhang F, Grundmann M.** BlazePose: On-device Real-time Body Pose Tracking. *arXiv:2006.10204.* 2020. (Presented at CV4ARVR Workshop, CVPR 2020.) — [arXiv](https://arxiv.org/abs/2006.10204) — 33 keypoints 토폴로지(HEEL, FOOT_INDEX 포함), OpenPose 대비 25~75× 속도, fitness/AR 도메인 정확도. PRD-0 가 BlazePose 채택한 핵심 근거.
