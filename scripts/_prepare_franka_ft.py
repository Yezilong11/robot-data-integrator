"""预处理 Franka 力矩原始数据为 SensorDataSkill 可读的 CSV。

原始数据 franka_ft_real_raw.csv:空格分隔、无表头、无时间戳,26416 行 × 28 列数值矩阵。
推断列结构(基于 README "state_to_pid-corrected-torque"):7 位置 + 7 速度 + 7 加速度 + 7 力矩。
预处理:转逗号分隔 + 加表头 + 加 timestamp 列(1000Hz 反推)。
**不改数值,仅做格式搬运**,保持"真实数据"属性。

用法:uv run python scripts/_prepare_franka_ft.py
"""
from pathlib import Path

import numpy as np

RAW = Path(r"d:\robot-data-integrator-latest\data\sensor_real\franka_ft_real_raw.csv")
OUT = Path(r"d:\robot-data-integrator-latest\data\sensor_real\franka_ft_real.csv")
SAMPLE_RATE_HZ = 1000.0  # README 注明 1000Hz

# 1. 读空格分隔数据,逐行过滤掉列数不一致的残缺行(末尾下载截断)
#    (np.loadtxt 遇到列数变化会抛错,逐行读更稳健)
with open(RAW) as fh:
    expected_cols = None
    rows = []
    skipped = 0
    for line in fh:
        parts = line.split()
        if not parts:
            continue
        if expected_cols is None:
            expected_cols = len(parts)
        if len(parts) == expected_cols:
            rows.append([float(x) for x in parts])
        else:
            skipped += 1
data = np.array(rows)
N, M = data.shape
print(f"loaded: {N} rows x {M} cols (skipped {skipped} malformed rows)")

# 2. 构造表头(推断 4 组 × 7:位置/速度/加速度/力矩)
GROUPS = ["pos", "vel", "acc", "tau"]
n_groups = M // 7
if M % 7 == 0 and n_groups <= len(GROUPS):
    headers = [f"{GROUPS[i]}_{j}" for i in range(n_groups) for j in range(7)]
else:
    headers = [f"sig_{i}" for i in range(M)]
assert len(headers) == M, f"header count {len(headers)} != cols {M}"

# 3. 加时间戳列(由 1000Hz 采样率反推)
timestamps = np.arange(N) / SAMPLE_RATE_HZ

# 4. 写逗号分隔 CSV(timestamp 在首列)
with open(OUT, "w", newline="") as f:
    f.write("timestamp," + ",".join(headers) + "\n")
    for t, row in zip(timestamps, data):
        f.write(f"{t:.6f}," + ",".join(f"{v:.10g}" for v in row) + "\n")
print(f"wrote: {OUT} ({N} data rows + 1 header)")
