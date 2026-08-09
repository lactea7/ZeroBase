"""CI 환경변수가 애플리케이션 설정을 덮지 않는지.

⚠️ 워크플로의 `env:` 는 그 job 의 **모든 프로세스**로 흘러든다. 애플리케이션이
같은 이름을 읽으면 CI 에서만 다른 값이 나온다.

실제로 그랬다: IDD 다운로드용으로 넣은 `EP_VERSION: 25.2.0` 이 pytest 로 새어
들어가 IDF 의 `Version` 객체가 `25.2` → `25.2.0` 이 됐고, 골든 IDF 가 깨졌다.
로컬에서는 그 변수가 없어 절대 안 보인다.
"""
import os
import re
import sys

import pytest

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO = os.path.dirname(BACKEND)
WORKFLOWS = os.path.join(REPO, ".github", "workflows")

#: 애플리케이션이 읽는 환경변수들. 워크플로가 이 이름을 쓰면 안 된다.
APP_ENV_VARS = ("EP_VERSION", "ENERGYPLUS_IDD", "GBXML_DATA_DIR", "ALLOWED_ORIGINS")


def _workflow_files():
    if not os.path.isdir(WORKFLOWS):
        pytest.skip("워크플로 디렉터리가 없다")
    return [os.path.join(WORKFLOWS, f) for f in sorted(os.listdir(WORKFLOWS))
            if f.endswith((".yml", ".yaml"))]


def test_app_reads_ep_version_from_env():
    """이 시험의 전제 — 애플리케이션이 실제로 그 이름을 읽는다."""
    src = open(os.path.join(BACKEND, "src", "ep_simulator.py"), encoding="utf-8").read()
    assert 'os.environ.get("EP_VERSION"' in src, (
        "애플리케이션이 EP_VERSION 을 안 읽으면 이 시험의 전제가 사라진다 — "
        "APP_ENV_VARS 를 갱신할 것")


@pytest.mark.parametrize("name", APP_ENV_VARS)
def test_workflows_do_not_shadow_app_env(name):
    """⚠️ 워크플로가 애플리케이션 변수 이름을 쓰면 CI 에서만 결과가 달라진다."""
    offenders = []
    # `  NAME: value` 형태의 env 선언만 본다(사용처 `${NAME}` 은 무관).
    decl = re.compile(rf"^\s+{re.escape(name)}\s*:", re.M)
    for path in _workflow_files():
        if decl.search(open(path, encoding="utf-8").read()):
            offenders.append(os.path.basename(path))
    assert offenders == [], (
        f"워크플로 {offenders} 가 애플리케이션 변수 '{name}' 을 덮어쓴다. "
        f"다른 이름을 쓸 것 (예: EP_RELEASE).")


def test_idf_version_default_matches_golden():
    """⚠️ 골든 IDF 는 기본 버전 문자열로 만들어졌다 — 기본값이 바뀌면 함께 갱신해야 한다."""
    golden = os.path.join(BACKEND, "tests", "golden", "representative.idf")
    if not os.path.exists(golden):
        pytest.skip("golden IDF 없음")
    text = open(golden, encoding="utf-8").read()
    m = re.search(r"^Version,\s*\n\s*([\d.]+);", text, re.M)
    assert m, "골든에서 Version 객체를 못 찾았다"

    sys.path.insert(0, BACKEND)
    src = open(os.path.join(BACKEND, "src", "ep_simulator.py"), encoding="utf-8").read()
    default = re.search(r'os\.environ\.get\("EP_VERSION",\s*"([\d.]+)"\)', src).group(1)
    assert m.group(1) == default, (
        f"골든의 Version({m.group(1)}) 과 코드 기본값({default}) 이 다르다")
