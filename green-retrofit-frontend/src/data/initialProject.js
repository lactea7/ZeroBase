// data/initialProject.js — 프로젝트 기본 상태.
//
// ⚠️ **App 과 시험이 같은 것을 써야 한다.** 시험이 이 모양을 손으로 베끼면
// 드리프트가 생기고, 실제로 `customSchedule.simplifiedParams`·`profiles` 가 빠진
// fixture 때문에 **있지도 않은 결함을 쫓을 뻔했다.**
//
// ⚠️ 매번 **새 객체**를 만든다. 모듈 상수로 두면 한 세션의 수정이 다음 세션과
// 시험 사이에 새어 나간다(중첩 객체가 공유된다).

export function createInitialProjectData() {
  return {
    name: '신규 프로젝트',
    activityId: 1105,
    location: 'KOR_SO_Seoul',
    pvCapacity: 0,
    heatSource: 11, // 난방 열원: 2전기 11지역난방
    // 기존 건물 실측 운영비(선택). 비우면 1.6배 추정으로 계산됨을 결과에 명시 고지.
    //   mode 'bill'=연간 요금(원), 'usage'=연간 사용량(kWh). 빈칸은 백엔드에서 무시.
    baselineActual: { mode: 'bill', elecBill: '', heatBill: '', elecKwh: '', heatKwh: '' },
    geothermalApplied: false,
    // 자기참조 최하층 바닥을 지면 경계로 볼지. 기본 off(단열 경계) —
    // 지하층·필로티·외기 노출 바닥을 지면으로 오분류하면 결과가 크게 틀어진다.
    promoteGroundFloors: false,
    hvacUpgradeActive: false,
    orientation: 0,
    targetBudget: 0,
    lccParameters: {
      discountRate: 5.0,
      inflationRate: 3.0,
      utilityInflation: 4.0,
      lifecycleYears: 20
    },
    ledFixtureCount: 0,
    customSchedule: {
      useCustom: false, // 기본=용도별 자동 스케줄, 켜면 전체 존에 커스텀 override
      mode: 'simplified', // 'simplified' | 'detailed'
      simplifiedParams: {
        weekday: { openTime: 8, closeTime: 18, heatOcc: 20, heatUnocc: 15, coolOcc: 26, coolUnocc: 30, opOcc: 1.0, opUnocc: 0.0 },
        weekend: { openTime: 0, closeTime: 0, heatOcc: 15, heatUnocc: 15, coolOcc: 30, coolUnocc: 30, opOcc: 0.0, opUnocc: 0.0 },
        holiday: { openTime: 0, closeTime: 0, heatOcc: 15, heatUnocc: 15, coolOcc: 30, coolUnocc: 30, opOcc: 0.0, opUnocc: 0.0 }
      },
      holidays: ["01/01", "03/01", "05/05", "06/06", "08/15", "10/03", "10/09", "12/25"],
      profiles: {
        weekday: {
          heating: Array(24).fill().map((_, i) => (i >= 8 && i < 18) ? 20 : 15),
          cooling: Array(24).fill().map((_, i) => (i >= 8 && i < 18) ? 26 : 30),
          operation: Array(24).fill().map((_, i) => (i >= 8 && i < 18) ? 1.0 : 0.0),
        },
        weekend: {
          heating: Array(24).fill(15),
          cooling: Array(24).fill(30),
          operation: Array(24).fill(0.0),
        },
        holiday: {
          heating: Array(24).fill(15),
          cooling: Array(24).fill(30),
          operation: Array(24).fill(0.0),
        }
      }
    }
  };
}
