"""시뮬레이션 조율 계층.

`generate_idf_and_simulate()` 는 EnergyPlus 실행 함수가 아니라 입력 정규화 →
baseline 재실행 → IDF 생성 → 실행 → 결과 파싱 → 경제성 → 대안 재귀 → 응답 조립을
모두 조율하는 **애플리케이션 유스케이스**다. 그것이 여기 온다.

energyplus 나 economics 가 서로를 지배하지 않도록, 이 계층이 둘을 호출한다.
"""
