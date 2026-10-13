"""설정·언론사 선택을 동일한 원자적 저장 경로로 기록한다."""
import ast
import os
import tempfile
from pathlib import Path
from init import config

ALLOWED_KEYS = {
    "POSTGRES_BIN", "SAVE_PATH", "BACKUP_PATH", "DB_HOST", "DB_PORT",
    "DB_USER", "DB_PASSWORD", "DB_NAME", "SELECTED_RSS", "INSTALLED_LIBRARIES",
}

def save_config(new_settings):
    """다중 행 설정도 정확히 교체하고 저장 성공 후 공유 설정을 갱신한다."""
    unknown = set(new_settings) - ALLOWED_KEYS
    if unknown:
        raise ValueError(f"지원하지 않는 설정: {sorted(unknown)}")
    path = Path(config.__file__)
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    changes, found = [], set()
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id in new_settings:
            changes.append((node.lineno-1, node.end_lineno,
                            f"{target.id} = {new_settings[target.id]!r}\n"))
            found.add(target.id)
    for start, end, value in reversed(changes):
        lines[start:end] = [value]
    updated = "".join(lines)
    for key in new_settings.keys() - found:
        updated += f"\n{key} = {new_settings[key]!r}\n"
    compile(updated, str(path), "exec")
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                dir=path.parent, suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(updated)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    for key, value in new_settings.items():
        setattr(config, key, value)

# 기존 설정 호출과 호환되는 이름.
save_db_config = save_config

def postgres_binaries_exist(path):
    if not str(path).strip():
        return False
    suffix = ".exe" if os.name == "nt" else ""
    return all((Path(path) / (name + suffix)).is_file()
               for name in ("initdb", "pg_ctl", "psql"))

def validate_db_settings(values):
    """설정 저장과 수집 시작에서 같은 기준으로 검증한다."""
    if values["DB_HOST"] not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("현재 DB 로직은 로컬 서버만 지원합니다.")
    if not values["DB_USER"] or not values["DB_PASSWORD"]:
        raise ValueError("사용자와 비밀번호를 입력해주세요.")
    if any(c in values["DB_PASSWORD"] for c in "\r\n\x00"):
        raise ValueError("비밀번호에 줄바꿈 또는 NUL 문자를 사용할 수 없습니다.")
    if "\x00" in values["DB_NAME"] or not 1 <= len(values["DB_NAME"].encode("utf-8")) <= 63:
        raise ValueError("데이터베이스 이름은 UTF-8 기준 1~63바이트여야 합니다.")
    if type(values["DB_PORT"]) is not int or not 1 <= values["DB_PORT"] <= 65535:
        raise ValueError("포트는 1~65535 정수여야 합니다.")
    if not postgres_binaries_exist(values["POSTGRES_BIN"]):
        raise ValueError("initdb, pg_ctl, psql이 있는 PostgreSQL bin 폴더를 지정해주세요.")
    if not str(values["SAVE_PATH"]).strip():
        raise ValueError("서버 데이터 저장 폴더를 지정해주세요.")
    path = Path(values["SAVE_PATH"])
    if path.exists() and not path.is_dir():
        raise ValueError("서버 데이터 저장 위치는 폴더여야 합니다.")
