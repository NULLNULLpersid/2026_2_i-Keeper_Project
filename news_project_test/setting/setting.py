"""config.py 사용자 설정 저장. DB 처리는 db 패키지가 담당합니다."""

import os
import re


import config


def save_db_config(new_settings):
    """Save database settings to config.py and update the active config module."""
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(project_dir, "config.py")

    with open(config_path, "r", encoding="utf-8") as config_file:
        lines = config_file.readlines()

    updated_keys = set()
    output_lines = []
    for line in lines:
        matched_key = next(
            (
                key for key in new_settings
                if re.match(rf"^\s*{re.escape(key)}\s*=", line)
            ),
            None,
        )
        if matched_key is None:
            output_lines.append(line)
            continue

        output_lines.append(f"{matched_key} = {new_settings[matched_key]!r}\n")
        updated_keys.add(matched_key)

    for key, value in new_settings.items():
        if key not in updated_keys:
            output_lines.append(f"\n{key} = {value!r}\n")

    temporary_path = config_path + ".tmp"
    with open(temporary_path, "w", encoding="utf-8", newline="\n") as config_file:
        config_file.writelines(output_lines)
    os.replace(temporary_path, config_path)

    for key, value in new_settings.items():
        setattr(config, key, value)
