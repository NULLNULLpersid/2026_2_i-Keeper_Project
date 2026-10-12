# ==========================================
# 1단계: 라이브러리 import
# ==========================================

# python 내장 라이브러리 import
import builtins
import subprocess
import sys
import importlib
import importlib.util
import json
import time
import os
import platform
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# 커스텀 라이브러리 import
import config

class LibraryManager():
    # (import명, pip 패키지명)
    library_list = [
        ("trafilatura",  "trafilatura"),
        ("feedparser",   "feedparser"),
        ("sklearn",      "scikit-learn"),
        ("schedule",     "schedule"),
        ("pandas",       "pandas"),
        ("openpyxl",     "openpyxl"),
        ("aiohttp",      "aiohttp"),
        ("asyncpg",      "asyncpg"),
        ("transformers", "transformers"),
        ("numpy",        "numpy"),
        ("pgvector",     "pgvector")
        ]

    @classmethod
    def update_library_config(cls, installed_list):
        """설치/확인된 라이브러리 목록을 별도 상태 파일에 저장합니다."""
        
        try:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            base_dir = os.path.dirname(current_dir)
            state_path = os.path.join(base_dir, ".installed_libraries.json")
            with open(state_path, "w", encoding="utf-8") as f:
                json.dump(installed_list, f, ensure_ascii=False, indent=2)
            config.INSTALLED_LIBRARIES = list(installed_list)

            print("[CONFIG] 라이브러리 검사 완료 및 목록 저장됨.")
        except Exception as e:
            print(f"[CONFIG] 라이브러리 목록 저장 실패: {e}")

    @classmethod
    def install_library(cls):
        """필요한 라이브러리 확인 및 설치 진행하는 함수"""

        installed_list = []
        for import_name, package_name in cls.library_list:
            try:
            # 1. 설치 여부 확인
                if importlib.util.find_spec(import_name) is None:
                    print(f"[설치 중] {package_name}...")
                    # 2. 설치 진행
                    subprocess.check_call([sys.executable, "-m", "pip", "install", package_name])
                    print(f"[완료] {package_name} 설치 완료")
                else:
                    print(f"[확인] {import_name} 이미 설치됨")

                # 성공적으로 확인된 라이브러리를 리스트에 추가
                installed_list.append(import_name)

            except Exception as e:
                print(f"[오류] {package_name} 설치 중 오류 발생: {e}")

        # 모든 설치가 끝나면 설치 상태 파일에 기록
        cls.update_library_config(installed_list)

    @classmethod
    def verification_libry(cls):
        """라이브러리 누락 및 환경 변경 감지 검증 함수"""

        # import config # 검증을 위해 임시 호출
        saved_libraries = getattr(config, 'INSTALLED_LIBRARIES', [])

        required_imports = [item[0] for item in cls.library_list]

        need_install = False      

        # 1차 검증: 설치 상태 파일에 목록이 누락되었는지
        if not all(lib in saved_libraries for lib in required_imports):
            need_install = True

        # 2차 검증: 설치 목록에 있지만 실제 현재 PC 환경에 모듈이 없는지
        for lib in required_imports:
            if importlib.util.find_spec(lib) is None:
                print(f"[환경 변경 감지] 설치 기록과 달리 현재 PC에 '{lib}' 라이브러리가 없습니다.")
                need_install = True
                break

        # 검증을 통과하지 못했을 때, 설치
        if need_install:
            cls.install_library()

LibraryManager.verification_libry()

# --------------------------------
# python 외부 라이브러리 import
# --------------------------------
import trafilatura
import feedparser
import sklearn
import schedule
import pandas
import openpyxl
import aiohttp
import asyncpg
import numpy
import transformers
from transformers import AutoModel, AutoTokenizer
from pgvector.asyncpg import register_vector

# --------------------------------
# 커스텀 라이브러리 import
# --------------------------------

# 서브 모듈들 불러오기
from collection import crawler, collection_gui as crawler_gui
from init import init_gui
from collection.media_select import media_select_gui, media_select
from setting import setting_gui, setting
import main_gui as gui_main

# ==========================================
# 2단계: 라이브러리 builtins 전역 주입
# ==========================================

# --------------------------------
# 내장 라이브러리 builtins 전역 주입
# --------------------------------
builtins.subprocess = subprocess
builtins.sys = sys
builtins.importlib = importlib
builtins.json = json
builtins.time = time
builtins.os = os
builtins.platform = platform
builtins.threading = threading
builtins.tk = tk
builtins.ttk = ttk
builtins.filedialog = filedialog
builtins.messagebox = messagebox

# --------------------------------
# 외부 라이브러리도 builtins에 주입
# --------------------------------
builtins.trafilatura = trafilatura
builtins.feedparser = feedparser
builtins.sklearn = sklearn
builtins.schedule = schedule
builtins.pandas = pandas
builtins.openpyxl = openpyxl
builtins.aiohttp = aiohttp
builtins.asyncpg = asyncpg
builtins.transformers = transformers
builtins.numpy = numpy
builtins.AutoModel = AutoModel
builtins.AutoTokenizer = AutoTokenizer
builtins.register_vector = register_vector

# --------------------------------
# 커스텀 라이브러리 builtins에 주입
# --------------------------------
builtins.config = config
builtins.gui_main = gui_main

builtins.crawler = crawler
builtins.crawler_gui = crawler_gui

builtins.media_select = media_select
builtins.media_select_gui = media_select_gui

builtins.init = sys.modules[__name__] # 자기 자신(init) 주입
builtins.init_gui = init_gui

builtins.setting = setting
builtins.setting_gui = setting_gui
