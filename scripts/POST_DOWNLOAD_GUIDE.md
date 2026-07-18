# 数据源后处理脚本使用说明

> 配套脚本:解压 → 元数据提取 → ChromaDB 导入
> 适用环境:Windows 11 + PowerShell 7+ + Python 3.11+
> 创建日期:2026-07-15

## 一、概览

`scripts/` 目录下提供 3 个可执行脚本,串行配合完成下载后处理:

```
[1] unpack_sources.ps1    →  解压所有压缩包(.zip/.tar.gz/.7z ...)
       ↓
[2] extract_metadata.py   →  提取元数据 → data/sources/_metadata_index.jsonl
       ↓
[3] import_to_chromadb.py →  写入 ChromaDB 集合 data_sources
```

---

## 二、脚本 1:unpack_sources.ps1

### 用途
扫描 `data/sources/` 下所有压缩包,按格式分发到对应解压工具,支持断点续解压(已存在目录跳过)。

### 依赖
- Windows PowerShell 5.1 或 PowerShell 7+(`pwsh`)
- 7-Zip(可选,用于 `.7z` / 大型 `.zip` 兜底):`winget install 7zip.7zip`

### 用法

```powershell
# 完整解压(默认:所有格式,解压后删除压缩包)
pwsh scripts\unpack_sources.ps1

# 仅预览,不实际解压
pwsh scripts\unpack_sources.ps1 -DryRun

# 解压后保留压缩包(便于复测)
pwsh scripts\unpack_sources.ps1 -KeepZip

# 只处理特定格式
pwsh scripts\unpack_sources.ps1 -Format zip     # 只处理 .zip
pwsh scripts\unpack_sources.ps1 -Format tar     # tar.gz/tar.bz2/tar.xz
pwsh scripts\unpack_sources.ps1 -Format 7z      # 只处理 .7z
pwsh scripts\unpack_sources.ps1 -Format all     # 默认,所有格式
```

### 参数表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `-DryRun` | switch | False | 仅列出待处理文件,不解压 |
| `-KeepZip` | switch | False | 解压后保留压缩包(默认删除) |
| `-Format` | string | `all` | 处理格式范围:`all`/`zip`/`tar`/`7z` |

### 预期输出

```
======================================================================
  统一解压脚本
======================================================================
数据根: D:\tiaozhanbei\robot-data-integrator\data\sources
日志文件: D:\tiaozhanbei\robot-data-integrator\data\logs\unpack_20260715_103045.log
模式: 实际解压 | 格式: all | 保留压缩包: False

[1/3] 扫描压缩包...
  发现 5 个压缩包
    - datasets\ycb\models\002_master_chef_can.zip (3.2 MB)
    - datasets\ycb\models\003_cracker_box.zip (3.8 MB)
    ...

[2/3] 解压中...
  [10:30:48] [INFO] 解压(zip): 002_master_chef_can.zip -> ...\002_master_chef_can
  [10:30:49] [INFO]   ✅ 002_master_chef_can.zip: 8 文件, 3.2 MB
  [10:30:49] [INFO]     🗑️  已删除压缩包: 002_master_chef_can.zip
  ...

[3/3] 汇总
  ✅ 成功: 5
  ❌ 失败: 0
  ⏭️  跳过: 0

日志文件: D:\tiaozhanbei\robot-data-integrator\data\logs\unpack_20260715_103045.log
```

### 故障排查

| 症状 | 解决方案 |
|------|----------|
| `Expand-Archive` 报"路径太长"错误 | 改用 `-Format zip` 触发 7z 回退分支,或安装 7-Zip |
| `.tar.gz` 解压失败 | PowerShell 7+ 自带 `tar`,如使用 PS 5.1 需先安装 7-Zip |
| `.7z` 报"未找到 7z" | `winget install 7zip.7zip` |
| 残留 `*.aria2` 控制文件 | 手动删除后重跑脚本 |
| 断点续解压误判 | 检查目标目录是否已含 ≥ 5 个文件,如需强制重解压可删除目标目录 |

---

## 三、脚本 2:extract_metadata.py

### 用途
扫描 `data/sources/` 全量数据,按文件后缀分发到对应提取器,生成 JSONL 索引。

### 依赖
- `trimesh`(mesh 元数据)
- `pymupdf`(PDF 元数据,模块名 `fitz`)
- `numpy`(.npy/.npz)
- `xacro`(可选,用于展开 xacro 宏)
- 上述依赖在 `pyproject.toml` 中已配置

### 用法

```powershell
# 完整扫描
python scripts\extract_metadata.py

# 只处理某个子目录
python scripts\extract_metadata.py --source api/arxiv
python scripts\extract_metadata.py --source datasets/ycb

# 只处理某类文件
python scripts\extract_metadata.py --type pdf
python scripts\extract_metadata.py --type urdf

# 自定义输出路径
python scripts\extract_metadata.py --output D:\backup\index.jsonl

# 组合
python scripts\extract_metadata.py --source api/arxiv --type pdf
```

### 参数表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--source` | str | None | 仅扫描 `data/sources/<source>/` 子目录 |
| `--type` | str | None | 仅处理特定扩展名(不带 `.`) |
| `--output` | str | `data/sources/_metadata_index.jsonl` | 输出 JSONL 路径 |

### 支持的格式与提取字段

| 扩展名 | 类型 | 提取字段 |
|--------|------|----------|
| `.obj`/`.stl`/`.ply`/`.glb`/`.dae` | mesh | vertices, faces, bounds, watertight, volume_mm3 |
| `.urdf`/`.xacro` | robot | robot_name, links, joints, link_count, joint_count |
| `.mjcf` | robot | model_name, bodies, joints, actuators |
| `.sdf` | robot | version, models, links |
| `.usd`/`.usda` | robot | root_tag, child_count |
| `.npy` | numeric | shape, dtype, size, min, max |
| `.npz` | numeric | key_count, keys, sample_shape, sample_dtype |
| `.pdf` | paper | page_count, title, author, subject, is_encrypted |
| `.json` | metadata | type(object/array), key_count/length, keys |
| `.xml` | xml | root_tag, root_attrs, child_tags |
| `.zip`/`.tar`/`.gz`/`.bz2`/`.xz`/`.7z` | archive | file_count, compressed_size, first_files |
| `.md`/`.txt`/`.py` | text | line_count, char_count |

### 预期输出

```
======================================================================
  元数据提取脚本
======================================================================
数据根: D:\tiaozhanbei\robot-data-integrator\data\sources
输出:   D:\tiaozhanbei\robot-data-integrator\data\sources\_metadata_index.jsonl

[1/2] 扫描文件...
  发现 142 个待处理文件
  类型分布:
    .pdf: 38
    .json: 39
    .npy: 27
    .obj: 30
    .stl: 8

[2/2] 提取元数据...
  进度: 142/142 (100.0%) [12.3s, ETA 0.0s]

✅ 完成: 成功 142, 失败 0, 耗时 12.3s
📄 输出: D:\tiaozhanbei\robot-data-integrator\data\sources\_metadata_index.jsonl
```

### 输出格式(JSONL,每行一条)

```json
{
  "id": "a3f2c1d8e9b04701",
  "path": "api/arxiv/pdfs/1309.2086v1.pdf",
  "abs_path": "D:\\tiaozhanbei\\robot-data-integrator\\data\\sources\\api\\arxiv\\pdfs\\1309.2086v1.pdf",
  "name": "1309.2086v1.pdf",
  "ext": ".pdf",
  "type": "paper",
  "size_bytes": 2418621,
  "mtime": 1721001234,
  "custom": {
    "format": "pdf",
    "page_count": 11,
    "title": "Dex-Net 2.0: Deep Learning to Plan Robust Grasps...",
    "author": "Mahler, Jeffrey; Liang, Jacky; Niyaz, Sherdil; Laskey, Michael; Doan, Richard; Liu, Xinchen; Ojea, Juan Aparicio; Goldberg, Ken",
    "subject": "",
    "is_encrypted": false
  }
}
```

### 故障排查

| 症状 | 解决方案 |
|------|----------|
| `ModuleNotFoundError: No module named 'trimesh'` | `pip install trimesh` |
| `ModuleNotFoundError: No module named 'fitz'` | `pip install pymupdf` |
| `XML parse` 错误 | xacro 文件需先 `pip install xacro` 后再解析 |
| 内存占用高 | 按 `--type` 分批处理,或限制 `--source` 范围 |
| 输出文件被占用 | 关闭其他占用 `_metadata_index.jsonl` 的进程 |

---

## 四、脚本 3:import_to_chromadb.py

### 用途
读取 `_metadata_index.jsonl`,调用 embedding API 写入 ChromaDB 持久化集合。

### 依赖
- `chromadb>=0.4`
- `httpx`(已有)
- `.env` 中至少一项:`QWEN_API_KEY` 或 `OPENAI_API_KEY`(否则使用 hash 兜底,无语义)

### 用法

```powershell
# 默认导入(读取 _metadata_index.jsonl)
python scripts\import_to_chromadb.py

# 自定义索引文件
python scripts\import_to_chromadb.py --index D:\backup\index.jsonl

# 自定义集合名
python scripts\import_to_chromadb.py --collection my_data_sources

# 自定义 ChromaDB 路径(默认读 .env 的 CHROMADB_PATH)
python scripts\import_to_chromadb.py --chroma-path D:\chroma\db

# 调整批量大小(默认 64)
python scripts\import_to_chromadb.py --batch-size 32
```

### 参数表

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `--index` | str | `data/sources/_metadata_index.jsonl` | 输入 JSONL 路径 |
| `--collection` | str | `.env: CHROMA_COLLECTION` 或 `data_sources` | ChromaDB 集合名 |
| `--chroma-path` | str | `.env: CHROMADB_PATH` | ChromaDB 持久化目录 |
| `--batch-size` | int | 64 | 批量 embedding 大小 |

### Embedding 后端优先级

1. **QWEN(阿里云 DashScope)**:`QWEN_API_KEY` 非空时启用
   - 模型:`.env: QWEN_EMBEDDING_MODEL`(默认 `text-embedding-v3`)
   - 端点:`https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding`
2. **OpenAI 兼容**:`OPENAI_API_KEY` 非空时启用
   - 模型:`text-embedding-3-small`
   - 端点:`.env: OPENAI_BASE_URL`(默认 `https://api.openai.com/v1`)
3. **本地 hash 兜底**:无 API key 时
   - 维度:256(伪 embedding,**仅用于占位,不保证语义匹配**)

### 预期输出

```
======================================================================
  ChromaDB 导入脚本
======================================================================
索引文件:   D:\tiaozhanbei\robot-data-integrator\data\sources\_metadata_index.jsonl
ChromaDB:   D:\tiaozhanbei\robot-data-integrator\data\experience_db
集合名:     data_sources
批量大小:   64

[1/3] 加载索引文件...
  加载 142 条记录

[2/3] 导入 ChromaDB...
  跳过已存在: 0 条
  待导入: 142 条
  Batch 1/3 (64 docs) ✅
  Batch 2/3 (64 docs) ✅
  Batch 3/3 (14 docs) ✅

[3/3] 验证...
  集合 data_sources 当前文档数: 142

======================================================================
  ✅ 导入: 142 | ⏭️  跳过: 0 | ❌ 失败: 0
======================================================================
```

### 故障排查

| 症状 | 解决方案 |
|------|----------|
| `chromadb not installed` | `pip install chromadb` |
| `dashscope 401 Unauthorized` | 检查 `.env` 中 `QWEN_API_KEY` 是否正确 |
| `SSL: CERTIFICATE_VERIFY_FAILED` | 设置 `PYTHONHTTPSVERIFY=0` 或升级 certifi |
| 导入非常慢 | 减小 `--batch-size` 或换用 hash 兜底 |
| ChromaDB 文件锁 | 关闭其他访问 `data/experience_db/` 的进程 |
| 重复导入 | 脚本自动跳过已存在 ID,直接重跑即可 |
| 内存不足 | 减小 `--batch-size` 至 16,或按 `--source` 分批导入 |

---

## 五、一键跑完(推荐)

```powershell
# 进入项目根目录
cd d:\tiaozhanbei\robot-data-integrator

# 1. 解压所有压缩包
pwsh scripts\unpack_sources.ps1 -Format all

# 2. 提取元数据
python scripts\extract_metadata.py

# 3. 导入 ChromaDB(需先在 .env 中配置 QWEN_API_KEY)
python scripts\import_to_chromadb.py

# 4. 验证
python scripts\verify_data.py
python scripts\check_download_progress.py
```

---

## 六、依赖安装

如缺包,运行:

```powershell
pip install trimesh pymupdf numpy chromadb xacro urdf_parser_py
```

完整依赖见 `pyproject.toml`。

---

## 七、相关文件

- 父级指南:[手动数据源下载完整指南.md](file:///d:/tiaozhanbei/.trae/documents/手动数据源下载完整指南.md)
- 连通性测试报告:[connectivity_report.md](file:///d:/tiaozhanbei/robot-data-integrator/data/connectivity_report.md)
- 公共工具:[utils.py](file:///d:/tiaozhanbei/robot-data-integrator/scripts/utils.py)
- 配置管理:[config.py](file:///d:/tiaozhanbei/robot-data-integrator/scripts/config.py)

---

> 文档版本:1.0
> 创建日期:2026-07-15
