from tkinter import messagebox

import config

SETUP_TITLE = "초기 환경 설정 및 하드웨어 안내"
ERROR_TITLE = "오류"
MSG_SQL_REQUIRED = "본 프로그램을 정상적으로 사용하려면 PostgreSQL이 반드시 설치되어 있어야 합니다."
MSG_GPU_REQUIREMENT_1 = "해당 프로그램은 NVIDIA GPU와 16GB 이상의 VRAM으로 분석됩니다."
MSG_GPU_REQUIREMENT_2 = "GPU를 사용할 수 있는 PyTorch가 필요합니다."
MSG_CPU_TORCH = "CPU 전용 버전의 torch입니다. GPU 버전을 설치해주세요."
MSG_NO_GPU = "사용할 수 있는 GPU가 없습니다. NVIDIA GPU 환경을 확인해주세요."
MSG_TORCH_MISSING = "torch가 없습니다. NVIDIA GPU와 CUDA 환경을 확인해주세요."

class EnvChecker:
    def __init__(self, root, on_complete_callback):
        self.root = root
        self.on_complete = on_complete_callback
        
        # 프로그램이 켜질 때 최초 실행 여부 확인
        is_first_run = not bool(getattr(config, 'INSTALLED_LIBRARIES', []))
        
        self.root.withdraw()

        # GPU 및 환경 검사는 최초 실행 여부와 관계없이 항상 실행
        self.root.after(100, lambda: self.run_hardware_and_env_checks(is_first_run))

    def run_hardware_and_env_checks(self, is_first_run):
        # 안내 메시지 콘솔 출력
        print(MSG_SQL_REQUIRED)
        print(MSG_GPU_REQUIREMENT_1)
        print(MSG_GPU_REQUIREMENT_2)
        print("-" * 50)
        
        # 최초 실행 시에만 SQL 설치 안내 팝업 출력
        if is_first_run:
            info_msg = (
                f"{MSG_SQL_REQUIRED}\n\n"
                f"{MSG_GPU_REQUIREMENT_1}\n"
                f"{MSG_GPU_REQUIREMENT_2}"
            )
            messagebox.showinfo(SETUP_TITLE, info_msg)
        
        # Torch 설치 및 CUDA(GPU) 사용 가능 여부 확인 (실행할 때마다 매번 검사)
        try:
            import torch

            # torch의 버전 확인
            if "+cpu" in torch.__version__.lower():
                messagebox.showerror(ERROR_TITLE, MSG_CPU_TORCH)

            # torch에서 사용할 gpu가 있는지 확인
            if not torch.cuda.is_available():
                # GPU 사용 불가 시 경고
                messagebox.showerror(ERROR_TITLE, MSG_NO_GPU)

        except ImportError:
            # Torch 미설치 시 경고
            messagebox.showerror(ERROR_TITLE, MSG_TORCH_MISSING)
            
        # 모든 검증 완료 후 메인 애플리케이션 실행
        self.on_complete()
