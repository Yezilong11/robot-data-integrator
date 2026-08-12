"""预处理末端 6 轴 F/T 传感器原始数据为 SensorDataSkill 标准输入。

原始数据来源: Mendeley Data DOI 10.17632/26674p3hvg.1
"Robotic assembly data of threaded fasteners: aeronautical collars"
- Kuka KR16 工业机器人腕部安装 6 轴力/力矩传感器
- CSV 列: time,x,y,z,rotx,roty,rotz,fx,fy,fz,mx,my,mz,vx,vy,vz,vrotx,vroty,vrotz
- fx/fy/fz: 力(N), mx/my/mz: 力矩(N·m), 均为传感器坐标系

预处理(只搬格式不改数值):
- 取 time + 6 路 F/T (fx,fy,fz,mx,my,mz),丢弃运动学列
- 重命名 time→timestamp, mx→tx, my→ty, mz→tz,匹配 Skill 时间戳列名识别
- 保持逗号分隔 + 表头 + 数值原样

用法: uv run python scripts/_prepare_ft_end_effector.py
"""
from pathlib import Path

RAW = Path(r"d:\robot-data-integrator-latest\data\sensor_real\ft_end_effector_raw_x9999040.csv")
OUT = Path(r"d:\robot-data-integrator-latest\data\sensor_real\ft_end_effector_prepared.csv")

# 列名映射: 原始 → 目标
RENAME = {
    "time": "timestamp",
    "fx": "fx",
    "fy": "fy",
    "fz": "fz",
    "mx": "tx",
    "my": "ty",
    "mz": "tz",
}

with open(RAW, newline="") as fh:
    lines = fh.readlines()

header = lines[0].strip().split(",")
idx = {name: i for i, name in enumerate(header)}

# 校验必需列都存在
missing = [c for c in RENAME if c not in idx]
assert not missing, f"原始 CSV 缺少列: {missing}; 实际表头: {header}"

target_cols = list(RENAME.keys())  # 按固定顺序输出
out_header = [RENAME[c] for c in target_cols]

with open(OUT, "w", newline="") as fh:
    fh.write(",".join(out_header) + "\n")
    for line in lines[1:]:
        parts = line.strip().split(",")
        if len(parts) != len(header):
            continue  # 跳过残缺行
        fh.write(",".join(parts[idx[c]] for c in target_cols) + "\n")

print(f"wrote: {OUT}")
print(f"  rows: {len(lines) - 1} -> {len(lines) - 1} (unchanged)")
print(f"  cols: {out_header}")
