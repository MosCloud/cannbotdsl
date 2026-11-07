# DSV4.1 MR348 arena 源码与出包

本分支对应 2026-11-05 已交付镜像里的 arena 包，保留 SparseMLA 的
local32、pipe32 和 28 核支持，叠加 MR348 的 QLI/QSLI。
本分支发布当前源码快照及原始差异；许可证见仓库根目录 LICENSE。
完整上游 Git 历史 bundle 保存在共享发布目录，未重复上传上游文档站历史。
下面的上游提交号用于追溯；全量构建仅需要当前分支，不需要 checkout 这些旧提交。

## 源码组成

- 上游基线：`9e01355ab8f809050579271c0eadcc5858ed20bc`。
- 本地构建基线：`2545d0195b9547d8e25a26d37e722f5b27fd29ab`，保存原始 SparseMLA profile 导出及模块别名兼容修改。
  SparseMLA 的 local32/pipe32 实现以交付 wheel 中的源码为准，已叠加在当前分支。
- MR348：`e3166de6b6380ef2c51f8f0ee9f988606ebf96db` 的四个 QLI/QSLI 文件。
  上游在 `samples/attention/`，本分支保留旧目录；按文件名和 SHA256 核对。
- 四个 MR 文件、SparseMLA 源码和两个 native package 构建文件保持原始字节。
  构建快照中部分文件带 CRLF，diff 可加 `--ignore-space-at-eol` 查看实质修改。
- 原始构建摘要见 [historical-wheel-build-manifest.json](historical-wheel-build-manifest.json)，
  这里只保存源码、配置、构建脚本和校验信息，不上传 wheel 或编译缓存。

## 从当前分支完整编译（不需要 arena base wheel）

旧版文档把内部增量重编流程作为推荐入口，要求未随仓库交付的 base wheel；
旧全量步骤还引用了公开快照不包含的历史提交。这两个入口已修正。
现在 `build_mr348.py` 直接从当前 checkout 编译全部 DSV4.1 算子，
不读取旧 arena wheel，不要求旧提交，也不复用已安装 arena 包里的二进制。

环境：Linux aarch64、Python 3.12、CANN Toolkit 9.2.0、cannbot-dsl **0.8.0**、
setuptools>=70.1、wheel、torch、pytest。原环境 torch 为 `2.10.0+cpu`、
torch_npu 为 `2.10.0.post7`。目标 `dav-3510`，CPU 编包无需挂载 NPU。

`cannbot-dsl` 是独立的 DSL 编译器依赖，**不是 arena base wheel**。
本仓库包含 arena 算子源码及出包工具，不包含 DSL 编译器实现；
需要能安装 `cannbot-dsl==0.8.0` 的包源，或自行准备该编译器的 wheel。
如果包源没有这个版本，仍需先取得编译器，不能用 arena wheel 代替。

```bash
git clone --branch release/dsv41-mr348-local32-pipe32-20261105 https://github.com/linfeng-yuan/cannbotdsl.git
cd cannbotdsl
source /usr/local/Ascend/cann-9.2.0/set_env.sh
python3 -m pip install 'cannbot-dsl==0.8.0' 'setuptools>=70.1' wheel torch pytest
python3 release/dsv41-mr348-20261105/build_mr348.py \
  --work-root /tmp/arena-mr348-source-build
python3 -m pip install --no-deps --force-reinstall /tmp/arena-mr348-source-build/wheels/*.whl
```

输出：`/tmp/arena-mr348-source-build/wheels/` 下的
`cannbot_arena_net-0.3.0+ds41.local32pipe32.mr348.source20261107-cp312-cp312-linux_aarch64.whl`。
`build-state.json` 记录进度；`jobs/*.log` 保存各编译日志；
`wheel-build-manifest.json` 记录最终 wheel 哈希、native 变体数和 metadata 库。
可先加 `--plan` 查看任务列表。
构建任务使用 Python 默认线程池并发；脚本不设置 `OMP_NUM_THREADS` 或 `MAX_JOBS`，
保留用户已有的编译环境设置。

总计 23 个任务：QLI/QSLI 各 2 个 profile，SparseMLA 3 组可选输入乘
5 个地址模式（含 local32、pipe32），以及 4 个其他算子。
QLI residual 分支由导出函数产生；预计合并为 55 个 native 变体、3 份 AICPU metadata 库。
算子实现保留原来的 28 核支持。

首次使用新的空工作目录；中断后在源码、编译器和工具链不变时用相同命令续编。
更改源码或工具链后换一个工作目录，避免复用旧任务输出。
工作目录使用容器本地磁盘；部分 NAS 不支持编译器的原子目录发布操作。
编译成功只代表产物生成，NPU 精度与模型验收需另外执行。
新版本号区分全量重编包与原历史二进制；不要求新 wheel 的整体 SHA 等于旧包。

`build_base_parallel.py` 仅保留旧命令的兼容入口，现同样编译当前 checkout，
不再需要 `git archive <旧提交>` 或预先拼装 source 目录。

## True / False 如何覆盖

这里的 [profiles.json](profiles.json) 只覆盖本镜像 DSV4.1 的静态配置，不能解释成任意组合全集。

| 开关 | MR348 处理方式 | 本包覆盖 |
| --- | --- | --- |
| QLI `candidate_enabled` | 编译期配置 | 分别导出 False 和 True |
| `has_seqused_q` 等输入有无 | 动态维度，长度允许为 0 | 同一二进制支持传入和不传入 |
| QSLI `has_output_offset` | 编译期配置 | 分别导出默认 True 和 False |

MR348 从编译缓存键移除了输入有无标记；没传入时使用零长度视图，内核按实际长度判断。
因此全量构建只取 QLI 的 profile 0/2、QSLI 的 profile 0/2，
QLI 额外产生 residual 分支，总计 5 个 QLI/QSLI native 变体，合并包总计 55 个。
改变 mask、page size、layout、topk 等静态配置，需要另行导出对应变体。

```bash
python3 -m pip install --no-deps --force-reinstall /path/to/arena.whl
export CANNBOTDSL_NATIVE_BINARY_MODE=require
export CANNBOTDSL_NATIVE_BINARY_REPORT=/tmp/arena-native-report.json
```

`require` 使缺失 native 变体直接失败；它能阻止静默 JIT，但不替代两条运行分支的精度验收。

## 原始产物位置

共享目录：`/mnt/share/y00882530/arena-mr348-20261105/`。
原 base wheel 在该目录根部；交付 MR348 wheel 在 `wheels/` 子目录。
DSL 0.8.0 的 wheel SHA256 为
`2d40711a02a12a72a6983004d96752556650f78892905471c3ead17eb7bf1302`。
其他镜像和框架构建信息见
[vllm-ascend 发布分支](https://github.com/linfeng-yuan/vllm-ascend/tree/release/dsv41-mr348-megamoe-p8192-20261105/release/dsv41-mr348-20261105)。

## 原始差异与历史

[arena-runtime.patch](arena-runtime.patch) 保存相对 9e01355 的七个运行/构建文件差异。
完整历史 bundle：`/mnt/share/y00882530/release-source-publication-20261106/cannbotdsl-publication.bundle`。
源码目录保留全部 `samples/` 和 `net/`，不依赖上游文档站即可编包。
