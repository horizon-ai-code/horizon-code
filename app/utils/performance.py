import asyncio
import time
import pynvml
from typing import List, Dict, Optional

class PerformanceTracker:
    def __init__(self, interval: float = 0.5):
        self.interval = interval
        self._gpu_utilizations: List[float] = []
        self._gpu_memory_usage: List[float] = []
        self._start_time: float = 0
        self._total_inference_time: float = 0
        self._is_running = False
        self._task: Optional[asyncio.Task] = None
        self._has_gpu = False

    async def start_tracking(self):
        self._is_running = True
        self._gpu_utilizations = []
        self._gpu_memory_usage = []
        self._start_time = time.perf_counter()
        
        try:
            pynvml.nvmlInit()
            self._has_gpu = True
            self._task = asyncio.create_task(self._poll_gpu())
        except Exception as e:
            # Silently fail if no GPU is found, but log it to console
            print(f"[PerformanceTracker] NVML initialization failed: {e}")
            self._has_gpu = False

    async def stop_tracking(self):
        self._is_running = False
        if self._task:
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
            
        self._total_inference_time = time.perf_counter() - self._start_time
        
        if self._has_gpu:
            try:
                pynvml.nvmlShutdown()
            except:
                pass
            self._has_gpu = False

    async def _poll_gpu(self):
        try:
            handle = pynvml.nvmlDeviceGetHandleByIndex(0) # Primary GPU
            while self._is_running:
                try:
                    util = pynvml.nvmlDeviceGetUtilizationRates(handle)
                    mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
                    
                    self._gpu_utilizations.append(float(util.gpu))
                    # Memory usage as percentage
                    self._gpu_memory_usage.append(float(mem.used) / float(mem.total) * 100.0)
                except pynvml.NVMLError as err:
                    print(f"[PerformanceTracker] NVML Error during polling: {err}")
                
                await asyncio.sleep(self.interval)
        except Exception as e:
            print(f"[PerformanceTracker] Polling background task error: {e}")

    def get_metrics(self) -> Dict[str, float]:
        avg_util = sum(self._gpu_utilizations) / len(self._gpu_utilizations) if self._gpu_utilizations else 0
        avg_mem = sum(self._gpu_memory_usage) / len(self._gpu_memory_usage) if self._gpu_memory_usage else 0
        
        return {
            "avg_gpu_utilization": round(avg_util, 2),
            "avg_gpu_memory": round(avg_mem, 2),
            "inference_time": round(self._total_inference_time, 2)
        }
