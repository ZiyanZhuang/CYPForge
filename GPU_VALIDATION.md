# 4EJJ 本地 GPU 短程积分验证

2026-10-15，用户在 v1.1.0 发布后授权的小通量真实积分。结论：现有体系可以在本地 GPU 完成原协议前八段及短程自由积分；采样范围内没有数值崩溃或配位宽门限失败。**尚未证明平衡、长时重启等价或生产就绪。**

## 输入、版本与边界

- 执行源码：`release/1.1` 的 `1f81b9b9f17d8317accf7fc37982a791fc73adc7`。F54 是发布后的修复，**已发布 v1.1.0 wheel 不包含它**；tag 仍为 `ba6e4152eaa874ea089b1f8ddedc247168917bcb`。
- 体系：4EJJ、CPDI heme、NCT nicotine；ff19SB + 已提供的 GAFF2 配体参数 + TIP3PBOX，截角八面体盒。71,698 原子、21,833 残基、21,360 个水、6 个 Cl−；仅中和，没有另加生理盐浓度。
- 保留 SDF 化学身份、PDB 构象来源及 identity-safe 映射，CYM410 SG（6612）–HEM466 FE（7540）拓扑键，配体残基 NCT467。沿用用户已确认的 GLU419→GLH、HIE55/299/386→HID 决定，没有新推断质子化或重算电荷。
- 所有执行在独立副本中；原准备目录 `../debug_artifacts/runs/final_4ejj  中文's {ligand_resname} reviewed/` 的 112 个文件逐一 SHA256 保持相同，原工作流仍是 PREPARED、六 PASS/四 PENDING。
- 原始拓扑 SHA256：`f816ed918229c4c8ccd86621ad3aed57d20ae8f5cc0268a09323ce896e97636b`；原始 restart：`4c221fa3a3fbc243c3efbf305e320a8afb11a309cbf3cc2bf1a65b551a461c6f`。
- 硬件：RTX 5060 8 GB，GPU 0，UUID `GPU-6b0e551b-9dc4-18d8-167f-9595f3f40550`；WSL Ubuntu-24.04，现有 Amber26 `pmemd.cuda`（CUDA 12.9/sm_120）及 AmberTools26 CPPTRAJ。没有安装或修改本机软件。
- 单 GPU 串行；完整准备硬上限 2,700 s，短诊断每段 300 s，微探针每段 30 s。未运行原第九段 20 ns NPT 或生产 MD。

## 实际完成的计算

主目录 `../debug_artifacts/gpu_validation_20261015_214526/`，下文简写为 J。执行命令、输入哈希、时间和退出码分别保存在 `J/plan.json`、`pipeline_result.json`、`diagnostics/diagnostic_plan.json`、`diagnostic_results.json` 及微探针目录中。

| 计算 | 步数与步长 | 实际时长 | 条件及结果 |
| --- | --- | --- | --- |
| 原 01–04 最小化 | 1,500 / 5,000 / 5,000 / 8,000 cycles | 不计 MD 时间 | 全部达到指定循环数，正常退出 |
| 原 05、06 NVT | 各 100,000 × 1 fs | 各 100 ps | 原输入逐字节相同，位置约束 10、5 kcal/mol/Å² |
| 原 07、08 NPT | 各 200,000 × 1 fs | 各 200 ps | 原输入逐字节相同，位置约束 2、0.5 kcal/mol/Å² |
| D01 自由 NPT | 10,000 × 2 fs | 20 ps | 从 08 继续，ntr=0、SHAKE，seed=20261015 |
| D02 NVE | 10,000 × 1 fs | 10 ps | 从 D01 继续，关闭温控、压控及 COM 移除 |
| D03 NVE | 5,000 × 2 fs | 10 ps | 与 D02 同一序列化 restart |
| D04→D05 NVE | 各 2,500 × 2 fs | 5 + 5 ps | 与 D03 同起点，同 2 fs 步长的重启对照 |
| A / B→C 微探针 | 2 / 1 / 1 步 × 2 fs | 合计 0.008 ps | 同一 D01 起点，仅改变步数及输出频率 |

原 01–08 包含 **600 ps MD**，总耗时 751.703 s；D01–D05 合计 **50 ps**，耗时 68.017 s。加微探针后本次成功验证累计 650.008 ps，最长单条谱系 630 ps。另保留首次复现 F54 的 100 ps，因此全部尝试累计 750.008 ps；**不能把分支累计时长称作一条 750 ps 轨迹，也不是独立重复实验。**

八段主执行、五段诊断、三个微探针均引擎 exit 0、正常结束、共享 fatal 检查无命中。主执行 wrapper exit 0；公共 Python `validate_pre_md_run` 对所选 01–08 返回 success（八段），不代表第九段或完整十模块完成。主执行 8 个、诊断 5 个及微探针 3 个 restart 的原子数、有限数值、盒子均通过检查。

主执行保存 600 个 MD 帧及四个最小化末态，诊断保存 500 帧，微探针 2/1/1 帧。原 01–08 为 `ntc=ntf=1`、1 fs，水也是柔性的；D01 起采用原第九段的 `ntc=ntf=2`、2 fs。没有为 GPU 偷换原 01–08 输入。05 实际是 tempi=0、temp0=310 的 Langevin 设置，**没有线性 TEMP0 升温表**。

## 观察与计算结果

所有均值和 SD 均为相关时间采样的描述统计，不是独立重复的误差条。

- 原 600 个 MD 帧：Fe–SG 2.3447–2.8376 Å，Fe–O1 1.5723–1.7086 Å；所有帧 O1 与 SG 位于 heme core 平面两侧。诊断 500 帧：Fe–SG 2.3828–2.8281 Å，Fe–O1 1.5577–1.7113 Å，同侧检查亦全部通过。包含四个最小化末态，现有 Fe–SG 1.8–3.0 Å、四个 Fe–N 1.7–2.5 Å 宽门限失败数均为 0。这些门限不证明参数准确或反应态正确。
- 原 08 最后 100 ps：温度 **310.1039 ± 0.9876 K**，密度 **1.047099 ± 0.001199 g/cm³**，末值 1.0476。08 全 200 ps 的几何统计：Fe–SG 2.5901 ± 0.0879 Å，Fe–O1 1.6371 ± 0.0222 Å，O1–Fe–SG 172.454 ± 3.324°。CPDI 参数 Fe–O1 r0=1.639 Å；该轴向角参数的力常数为零，不能把角度接近参考值当作独立参数验证。
- 以初始溶剂化结构为参考，成像后按蛋白 CA 拟合，08 末 CA RMSD **0.2849 Å**，同一变换下配体重原子 RMSD **0.5269 Å**。这些是有约束的短轨迹，低 RMSD 不证明自由稳定性。
- 必须保留的瞬态：08 首个输出点（401 ps）温度 **333.79 K**，CA/配体 RMSD 约 0.5272/1.0293 Å；402 ps 为 319.31 K，404 ps 为 310.99 K。不能只展示末段均值而称全程已平衡。
- D01 解除位置约束并切换 SHAKE 后，20 ps 密度 **1.0476→1.0174 g/cm³**，温度首点 304.93 K、最低 299.46 K、末点 310.72 K。末态相对 08 的 CA/配体 RMSD 0.7401/0.7541 Å。密度仍有明显松弛，**不足以作平衡判断**；约束自由度、体积及能量定义同时变化，不能把 08→D01 的能量差直接解释成积分误差。
- 最小化 04 达到 maxcyc，但末 gradient RMS **0.066369**，高于默认 drms=1e−4；正常退出不等于梯度收敛。

CPPTRAJ 成像后按 1–465 残基 CA 拟合，配体不再独立拟合。配位几何来自 CPPTRAJ 导出的 0.001 Å 精度局部 PDB，所列小数为计算输出的舍入，不能解释为超过输入精度的测量。NVE 能量取实际 pmemd 输出，未以 CPPTRAJ 的非 PME 简化能量替代。

### 水、温压设置的核查

独立检查全部 21,360 个水：拓扑采用 OH/OH/HH 三边谐键，均 k=553，r0 为 0.9572/0.9572/1.5136 Å，没有显式 HOH 角项；与已安装 `frcmod.tip3p` 相同。柔性 06 末 OH 均值约 0.9813 Å、HOH 100.09°；水键能重算约 39,978 kcal/mol，占总 BOND 约 93.62%，与输出总 BOND 的重算差约 0.076%。大 BOND 值本身不是已确认的参数错误。

D01、D03、D05 SHAKE 末态水边长满足拓扑目标，最大误差约 6.4e−14 Å；由这些边长计算的角为 **104.49060265846°**。不能把柔性水与刚性水当作同一自由度的能量基准。

本机 Amber26 源码显示 barostat=2 是 Monte Carlo，默认 mcbarint=100 步；taup 不控制该 MC 尝试频率。不能把输入中 taup=10/5 解释成压力耦合逐级增强。GPU 输出的 PRESS=0 是此路径的不可用占位，**不是实测 0 bar**，未用于压力收敛判断。stderr 的 IEEE_UNDERFLOW_FLAG/IEEE_DENORMAL 提示与 WSL localhostproxy 提示保留；没有把“未出现 fatal”写成“零警告”。

### NVE 与重启数值检查

| 分支 | 全 10 ps Etot 斜率 (kcal/mol/ps) | 从重启后 1 ps 起的斜率 | 全程峰峰差 (kcal/mol) |
| --- | ---: | ---: | ---: |
| 1 fs，D02 | −0.02588 | −0.01655 | 7.1532 |
| 2 fs，D03 | +0.12350 | +0.13022 | 12.7418 |

全程斜率按原子和 ns 归一后分别为 −0.0003609、+0.0017226 kcal/mol/atom/ns。D02、D03 共用 SHAKE 一致的 D01 restart；但默认 ischeme=0/ionstepvelocities=0 序列化交错时刻的位置与速度，irest=1 不因新 dt 重定相位，因此这不是严格同一同步 Hamiltonian 相点的步长收敛实验。这里只报告各自内部的短程漂移，不能据此认定 2 fs 等价、收敛或适合长期生产。

同 2 fs 的 D03 与 D04 前 5 ps：71,698 原子、50 帧原始坐标逐值完全一致，相应 50 个能量记录也一致。D05 重启后首个 0.1 ps 点，全原子最小镜像 RMS 差 7.476e−6 Å，按共同参考成像/拟合后的 CA 差 3.199e−6 Å；630 ps 末 CA/heme/配体差增长到约 **0.60377/0.48209/0.93579 Å**。全原子最小镜像末差约 5.1944 Å，能量末差 −3.2466 kcal/mol。不能以周期盒成像独自解释这些差异，亦未确认长时差异的具体根因或统计等价性。

进一步的 A 连续两步、B 一步再 C 一步微探针，使用双精度 restart 比较同一 620.004 ps 时刻：时间与盒子严格相同；全原子 raw 与三斜最小镜像坐标 RMS 差均 **6.1566e−6 Å**，最大原子向量差 1.0154e−5 Å。坐标轴均值存在约 −2 至 −3e−6 Å 的有符号偏置；CA 拟合后 CA/蛋白重原子 RMS 为 2.54e−9/7.82e−9 Å，物理速度 RMS 差 1.89e−5 Å/ps。A 首轨迹帧与 B restart 转为 float32 后完全一致，可见差符合轨迹写出的舍入。此探针支持接口在极小尺度上连续，**不证明长时差异良性或重启逐 bit 等价**，未将其全部归因于混沌。

### GPU 观测

主执行及短诊断共 91 个设备遥测点：显存 2,143–3,185 MiB（中位 2,900），利用率 2–88%（中位 78%，含启动空档），温度最高 71°C，功率最高 128.89 W。这些是整卡观测，包含桌面及其他后台占用，不能归为 pmemd 独占显存或能耗。全部授权计算结束后 GPU compute-apps 为空。

## F54 软件修复与验证

首次目录 `../debug_artifacts/gpu_validation_20261015_214009/` 的前四个最小化和 100 ps NVT 正常，但旧 shell 将正常参数回显 `vlimit = -1.00000` 误判为 fatal，wrapper exit 6。先添加公共 Python/Bash 回归：**3 failed/7 passed**；再把共享匹配从任意 `vlimit` 缩为 `vlimit +exceeded`，仅一行生产代码，实际超限、NaN、SHAKE、CUDA 等仍拒绝。修复后的真实 01–08 全部通过。

修复后 51 个相关测试通过；完整 native **260 passed/6 skipped**、WSL **256 passed/10 skipped**，各有一个既有 warning。一次同时运行时 native 测试临时目录 rename 出现 WinError5；精确单测及不改代码/fixture 的串行完整重跑通过，独立回归再次双平台通过。

顺序独立审查（代码执行后没有再改生产源码）：

1. 正确性：`../debug_artifacts/gpu_F54_review.txt`，**No issues found.**，SHA256 `9ab94be353b5102f151cfc1a8f77363e551ae63f876546ef7d30fb0cd9946958`。
2. 回归：`../debug_artifacts/gpu_F54_regression_review.txt`，**No issues found.**，SHA256 `3ea33bd0bdc766dff4f573aca020df0ac473afded676acbc396265d27ec5890b`；全新双平台完整测试，以及每端 21 项独立公共边界控制。
3. 一致性：报告完成后对冻结提交独立核查，结果记入 [DEBUG_STATE.md](DEBUG_STATE.md)。

## 本地证据与复算入口

原始 MD/参数文件未提交仓库。以下是本工作区相对路径；其他机器需取得本地证据目录，不能仅克隆仓库便访问它们。

| 内容 | 本地产物 |
| --- | --- |
| 原 01–08 输入、命令、八段公共门控 | `J/plan.json`、`pipeline_result.json`、`actual_pre_md_run_validation.json` |
| 主执行 QC、逐帧 CSV、六面板图 | `J/qc_20261015_215831/summary.json`、`qc_overview.{png,pdf,svg}` |
| NPT/NVE、漂移与分段比较图 | `J/diagnostics/qc_20261015_220221/summary.json`、`diagnostic_overview.{png,pdf,svg}` |
| 重启逐帧、原子级差与共同成像 | `J/diagnostics/restart_comparison_20261015_220558/summary.json` 及同目录图、CSV |
| 微探针精确输入、命令、完整有符号差 | `J/diagnostics/restart_microprobe_20261015_140932_UTC/`；`../debug_artifacts/gpu_restart_microprobe_review.{txt,json,py}` |
| 水拓扑/柔性及 SHAKE 几何独立核算 | `../debug_artifacts/gpu_water_geometry_review.{txt,json,py}`、`gpu_water_after_shake_review.{txt,json,py}` |
| 源输入保护、时长与遥测摘要 | `J/handoff_summary.json`；微探针完成性另见其 JSON |

每组图均有同 stem 原始 CSV、数据字典及 `figure_sidecars.json`，保留变换前全部行、单位、来源哈希与面板映射，并做读回校验。脚本为 `../debug_artifacts/analyze_gpu_validation.py`、`analyze_gpu_diagnostics.py` 及各 QC 目录记录的精确命令；已完成的 GPU 启动脚本不必为了查看结果再次执行。

方法参考：[CPPTRAJ action commands](https://amberhub.chpc.utah.edu/cpptraj/action-commands/)、[energy 的非 PME 能量限制](https://amberhub.chpc.utah.edu/energy/)。版本特定行为另核对本机现有 Amber26 源码，未修改该源码。

## 仍未验证

没有运行 QM/RESP、重拟合或独立验证 CPDI 化学参数，没有独立随机重复、长时平衡、20 ns 第九段或生产轨迹，也没有完成后续 audit/decision/readiness 工作流。下一轮应先约定平衡判据、约束切换的解释及重复预算，再决定更长自由平衡；本轮不自动扩大 MD 范围，不把已发布 v1.1.0 替换为含 F54 的新版本。
