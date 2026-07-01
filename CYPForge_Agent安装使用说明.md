# CYPForge 基于 Agent 的安装与使用说明

## 项目定位

CYPForge 是面向细胞色素 P450 蛋白-血红素-配体复合体系的 Amber 分子动力学预处理框架。根据当前项目代码结构，CYPForge 并不是一个独立替代 Amber、AmberTools 或 cpptraj 的模拟软件，而是在既有分子模拟工具链之上提供严格的流程编排、参数化调用、日志记录和门控审计。其核心思想是将 CYP450 体系预处理拆分为可复现的连续模块，由 agent 按照预定义顺序调用项目脚本和外部工具，并在每一阶段依据清晰的证据文件判断是否继续、暂停或终止。

项目主要由四个层次组成。`src/cypforge_core/` 保存工作流编排、模块定义、门控检查、上下文构建和 `cypforge` CLI 逻辑；`src/cypforge/` 保存较底层的血红素、轴向半胱氨酸及相关结构处理逻辑；`cypforge module ...` 提供每个核心步骤的标准命令入口；`skills/cypforge/` 则定义 agent 应遵循的十个技能模块、执行纪律、输入输出规范和失败停止条件。因此，用户在使用本项目时，不应只把它理解为若干 Python 脚本的集合，而应将其视为一个由 agent 驱动的 CYP450 Amber 预处理外壳。

## 运行环境准备

V1.3 推荐使用标准 Python 包安装入口。在项目根目录执行 `pip install -e ".[qm,test]"` 后，`cypforge` 控制台命令会加入当前环境的 `PATH`。用户应优先使用 `cypforge init`、`cypforge prep-only`、`cypforge run`、`cypforge status`、`cypforge context` 以及 `cypforge module ...`；`cypforge.cmd` 和 `scripts/cypforge_run.py` 仅作为旧版本兼容入口保留。

除 Python 环境外，CYPForge 的科学计算部分依赖 Amber/AmberTools 工具链。代码逻辑显示，Windows 环境下 Amber 命令通过 WSL 调用，并要求能够在 WSL 中访问 `tleap`、`pmemd.cuda`、`cpptraj`、`antechamber` 和 `parmchk2`。用户需要提供 Amber 初始化脚本路径，通常通过 `AMBER_SH` 环境变量或初始化命令中的 `--amber-sh` 参数传入。若进行 Core 2 的配体 RESP/ESP 电荷拟合，还需要提供 Multiwfn 可执行文件路径，可通过 `MULTIWFN_BIN` 环境变量或 `--multiwfn-bin` 参数指定。若这些关键程序不可用，agent 应在 `environment_check` 阶段停止，而不应继续执行后续化学步骤。

在 Windows PowerShell 中，一个典型的环境准备方式如下：

```powershell
cd "<PROJECT_ROOT>"
pip install -e ".[qm,test]"
$env:AMBER_SH = "/path/to/amber.sh"
$env:MULTIWFN_BIN = "/path/to/Multiwfn_noGUI"
```

安装后可直接运行 `cypforge --version` 检查入口是否可用；同时仍需保证 Amber、WSL 用户名以及 Multiwfn 等外部程序路径能够被正确解析。

## Agent 工作流安装与识别

对于具备 skill 或项目上下文读取能力的 agent，安装和使用本项目的关键在于识别 `skills/cypforge/SKILL.md` 与 `skills/cypforge/skills_manifest.json`。前者给出总体约束，明确 CYPForge 是一个严格的 CYP450-heme-ligand 工作流外壳；后者定义十个按顺序执行的模块。agent 在开始运行前应读取这些文件，并把其中的非协商科学规则作为执行边界。例如，SDF 是配体化学图、键级、芳香性、形式电荷和 GAFF2 类型的来源；PDB 是蛋白、血红素和配体构象坐标的来源；不能将 PDB 键级当作配体化学真值；不能在没有显式决策文件的情况下自动修改关键残基名称；任何硬门控失败都必须停止流程。

本项目的 agent 顺序为：`cypforge.environment_check`、`cypforge.core1_prepare_heme_cym`、`cypforge.core2_prepare_ligand_resp_gaff2`、`cypforge.core3_finalize_protonation`、`cypforge.core3_solvate_ionize`、`cypforge.core3_render_pre_md`、`cypforge.core3_run_pre_md`、`cypforge.global_audit`、`cypforge.equilibration_decision` 和 `cypforge.production_readiness_check`。这个顺序反映了项目的三核心设计：Core 1 处理 CYP450 蛋白、HEME 与轴向 CYM；Core 2 从 SDF 和复合物 PDB 生成配体 GAFF2/RESP 参数并建立 LEaP 映射；Core 3 完成质子化决策应用、溶剂化和离子化、预 MD 输入生成、九阶段预平衡运行、全局审计及生产准备度判断。

## 初始化一次运行

用户应为每个研究体系建立独立运行目录。项目代码的默认运行根目录依据操作系统决定：Windows 上为 `C:\cypforge_runs\<run_name>`，POSIX 上为 `~/cypforge_runs/<run_name>`；也可以通过环境变量 `$env:CYPFORGE_RUNS_DIR`（PowerShell）/`$CYPFORGE_RUNS_DIR`（POSIX）全局覆盖，或通过 `--run-root` 在单次运行中显式指定。初始化时必须提供至少两个体系输入：含蛋白与血红素的 PDB 文件，以及作为配体化学模板的 SDF 文件。PDB 负责提供坐标、残基名、原子名和链标识；SDF 负责提供配体图结构和键级信息。对于 CYP450 体系，还应根据体系实际情况指定血红素状态、血红素残基名、蛋白链、血红素链、轴向半胱氨酸编号、配体残基名、配体链、配体形式电荷和自旋多重度等参数。

使用外层控制器初始化运行的示例如下：

```powershell
cypforge init my_run `
  --pdb "C:\path\to\protein_heme_ligand.pdb" `
  --sdf "C:\path\to\ligand.sdf" `
  --heme-state IC6 `
  --heme-resname HEM `
  --protein-chain A `
  --heme-chain A `
  --axial-cys-resid 442 `
  --ligand-resname NCT `
  --blank-ligand-chain `
  --formal-charge 0 `
  --spin 1 `
  --wsl-user <your-wsl-user> `
  --amber-sh "/path/to/amber.sh" `
  --multiwfn-bin "/path/to/Multiwfn_noGUI"
```

初始化命令会在运行目录中写入 `run_config.json` 和 `run_manifest.json`。其中，`run_config.json` 保存本次体系的输入路径、力场选项、配体电荷设置、WSL/Amber 路径和流程控制参数；`run_manifest.json` 保存十个模块的状态。初始化后所有模块通常处于 `PENDING` 状态，agent 后续会从第一个未完成模块开始执行。

## 执行完整流程或仅执行预处理

完整流程可通过 `run` 命令启动。该命令会读取已有的运行配置和清单，从当前检查点开始执行所有待完成模块。执行过程中，项目的 `CYPForgeOrchestrator` 会调用 `ModuleRunner` 按模块运行命令，写入日志，并由 `GateChecker` 判断门控结果。若模块返回 `PASS`，流程进入下一阶段；若返回 `WARN` 且初始化时未指定 `--auto-accept-warn`，流程会暂停，等待人工审阅；若返回 `FAIL`，流程状态变为 `STOPPED_ON_FAIL`，agent 不应继续执行下游模块。

完整执行示例如下：

```powershell
cypforge run my_run
```

如果用户只希望生成并审查预 MD 输入文件，而不希望调用 `pmemd.cuda`、`pmemd` 或 `sander` 启动预平衡计算，可以使用 `prep-only` 命令。缺少质子化决策时，该命令在 Core 2 后暂停；用户完成 `protonation recommend`、人工审核和 `protonation apply` 后，再次执行 `prep-only`，流程会在 `cypforge.core3_run_pre_md` 之前停止。

```powershell
cypforge prep-only my_run
```

## 状态查看、上下文导出与恢复

用户和 agent 可随时通过 `status` 命令查看当前运行状态。该命令会列出十个模块的状态和门控结果，包括 `PENDING`、`RUNNING`、`PASS`、`WARN`、`FAIL` 和 `SKIPPED` 等状态。若流程暂停或失败，状态表会指出阻塞模块，用户应优先检查该模块的输出目录、日志目录和报告文件，而不是直接跳过该阶段。

```powershell
cypforge status my_run
```

当需要让 LLM agent 对当前流程进行结构化判断时，可使用 `context` 命令导出 JSON 上下文。该命令不会打印启动横幅，而是直接在标准输出中给出可供 agent 消费的结构化信息，包括工作流状态、已完成模块、门控结果、化学指标和策略提醒。用户可以将其重定向为文件，作为下一轮 agent 决策输入。

```powershell
cypforge context my_run > agent_input.json
```

若流程因 `WARN` 暂停，用户应阅读对应模块的人类可读报告和证据文件，确认警告是否可以接受；若流程因 `FAIL` 停止，用户应先修复输入文件、环境变量、参数化结果或决策 JSON 中的问题。完整流程可使用 `resume` 恢复。以 no-MD 为终点时必须再次使用 `prep-only`，因为 `resume` 可能继续进入 `core3_run_pre_md`。

```powershell
cypforge resume my_run
```

## 输出目录与证据文件

CYPForge 的输出不是单一结果文件，而是一个带有证据链的运行目录。根据项目定义，典型目录包括 `00_environment_check`、`01_heme_only`、`02_heme_mapping_leapin`、`10_ligand_gpu4pyscf_esp`、`13_ligand_mapping_leapin`、`14_complex_protonation_finalize`、`15_complex_solvation_ionization`、`17_complex_pre_md_equilibration`、`18_global_cyp450_audit` 和 `logs`。每个模块会生成相应的 manifest、日志和审计报告。agent 在判断是否进入下一阶段时，应优先依据这些 manifest 和门控报告，而不是仅依据命令是否返回零退出码。

这种设计对于学术使用尤为重要。CYPForge 明确区分“命令执行成功”和“化学模型可信”两个层次。例如，`tleap` 成功并不自动证明质子化状态、残基映射或配体电荷分配正确；总电荷正确也不证明每个原子的 RESP 电荷映射正确；20 ns 自由 NPT 预平衡也不等价于生产模拟已经具备充分科学结论。因此，用户在论文方法学或补充材料中描述 CYPForge 结果时，应引用具体的审计文件、门控状态和人工决策依据。

## 质子化决策与人工审阅

Core 3 的质子化最终化步骤需要显式的 `protonation_decision_json`。该文件用于记录需要修改的残基质子化状态或残基命名决策。项目规则要求 agent 不得在缺少明确决策文件的情况下自动猜测 GLH、HID、CYM 等关键残基状态，也不得基于视觉或隐含规则擅自删除跨膜螺旋区段。若用户确实需要裁剪跨膜区域，必须提供精确的链和残基范围，并明确确认该操作。

因此，推荐用户在进入 `core3_finalize_protonation` 前准备并审阅质子化决策文件。若尚未准备该文件，可以先运行早期步骤，结合结构检查、PROPKA/reduce/pdb2pqr 等外部证据和人工判断生成决策 JSON，再恢复后续流程。对于不确定的质子化或残基命名问题，agent 应返回 `WARN` 或 `FAIL`，而不是静默修正。

## 生产模拟边界

CYPForge 的 agent 外壳不允许直接运行生产 MD。当前工作流最多执行预处理、预平衡、全局审计和生产准备度检查。`production_readiness_check` 的意义是防止用户过早将预平衡或输入生成结果解释为生产模拟证据。即使该检查通过，也只能说明已有证据支持进一步设置生产模拟输入，而不能证明体系已经完成充分采样，也不能替代独立的生产 MD 设计、重复轨迹、收敛性分析和机制解释。

在实际研究中，用户可将 CYPForge 输出作为 Amber 生产模拟前的标准化预处理证据链。论文方法部分可描述：CYPForge 通过 agent 控制的十阶段流程，完成 CYP450 HEME/CYM 结构准备、配体 GAFF2/RESP 参数化、质子化决策应用、溶剂化和离子化、九阶段预 MD 输入生成及运行、全局审计和生产准备度判定；所有阶段均保留命令、日志、manifest 和门控状态。这样可以增强计算流程的透明度和可复现性。

## 常见问题处理

若出现 Python 导入错误，首先确认已经在项目根目录执行 `pip install -e ".[qm,test]"`，或确认当前环境的 `PYTHONPATH` 包含项目 `src` 目录。若出现 Amber 环境未配置错误，应确认 `AMBER_SH` 或 `--amber-sh` 是否指向 WSL 中可 source 的 Amber 初始化脚本，并确认 WSL 用户能够执行 `tleap`、`pmemd.cuda`、`cpptraj`、`antechamber` 和 `parmchk2`。若 Core 2 报告 Multiwfn 缺失，应设置 `MULTIWFN_BIN` 或在初始化时传入 `--multiwfn-bin`。若 ligand mapping 失败，用户应检查 SDF 与 PDB 中配体元素组成、残基名、链 ID、坐标构象和形式电荷是否一致。

对于含中文路径的 Windows 环境，应尽量使用完整引号包裹路径，并避免通过不稳定的管道或临时编码方式向原生命令传递路径。当前项目的外层命令和 WSL 路径转换逻辑能够处理常见 Windows 路径，但外部程序仍可能受编码、权限或挂载方式影响。为降低风险，建议将运行目录放在 ASCII 路径下（Windows 上的默认 `C:\cypforge_runs\<run_name>`、POSIX 上的 `~/cypforge_runs/<run_name>`，或自定义的 `$CYPFORGE_RUNS_DIR`），同时保持项目目录和输入文件路径在命令中被准确引用。

## 推荐使用原则

用户使用 CYPForge 时，应将 agent 视为严格执行者和审计者，而不是任意自动修复化学模型的黑箱。每一次运行都应从环境检查开始，以 manifest 和日志作为证据，以 `PASS`、`WARN` 和 `FAIL` 作为流程控制语义。`PASS` 表示硬门控通过且无显著未解决警告；`WARN` 表示硬门控通过但需要人工审阅；`FAIL` 表示必须停止并修复。只有在这些状态语义被完整保留的前提下，CYPForge 输出才适合作为学术计算流程的一部分。
