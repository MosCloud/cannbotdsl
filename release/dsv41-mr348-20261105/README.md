# DSV4.1 MR348 arena 源码与出包

本分支对应 2026-11-05 已交付镜像里的 arena 包，保留 SparseMLA 的
local32、pipe32 和 28 核支持，叠加 MR348 的 QLI/QSLI。
本分支发布当前源码快照及原始差异；许可证见仓库根目录 LICENSE。
完整上游 Git 历史 bundle 保存在共享发布目录，未重复上传上游文档站历史。

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

## 推荐：保持原 SparseMLA 二进制，只重编 MR348

在 Linux aarch64、Python 3.12.13、CANN 9.2.0、cannbot-dsl 0.8.0 的环境执行。
原环境 torch 为 `2.10.0+cpu`、torch_npu 为 `2.10.0.post7`。
编译目标 `dav-3510`；CPU 编包不需要占用 NPU，实际正确性仍需 NPU 验收。

```bash
git clone --branch release/dsv41-mr348-local32-pipe32-20261105 git@github.com:linfeng-yuan/cannbotdsl.git
cd cannbotdsl
source /usr/local/Ascend/cann-9.2.0/set_env.sh
python3 -m pip install --no-deps /path/to/cannbot_dsl-0.8.0-cp312-cp312-manylinux_2_28_aarch64.whl
python3 release/dsv41-mr348-20261105/build_mr348.py \
  --base-wheel /path/to/cannbot_arena_net-0.3.0+ds41.local32pipe32.20261104-cp312-cp312-linux_aarch64.whl \
  --work-root /tmp/arena-mr348-build --check-inputs
python3 release/dsv41-mr348-20261105/build_mr348.py \
  --base-wheel /path/to/cannbot_arena_net-0.3.0+ds41.local32pipe32.20261104-cp312-cp312-linux_aarch64.whl \
  --work-root /tmp/arena-mr348-build
```

base wheel 必须为原验证包，SHA256 为
`2eae3c85e54eaa213f6bf68765e4851d2f2f4cf1cadfa4769b4449e182adc345`。
脚本检查输入 SHA、源码 SHA、native manifest 和 ABI，重编 QLI/QSLI 及两份 metadata `.so`。
合并时保留其他算子，并逐字节检查 48 项 SparseMLA 资源。
两个同名 metadata 库若存在差异，除 ELF `.strtab` 外所有有效 section 必须一致。
工作目录每轮应使用新的空目录；已有成功构建会复用，修改源码或工具链后必须换目录。

产物：`/tmp/arena-mr348-build/publication/wheels/` 下的
`cannbot_arena_net-0.3.0+ds41.local32pipe32.mr348.20261105-cp312-cp312-linux_aarch64.whl`。
同目录的 `wheel-build-manifest.json` 记录本次产物哈希与资源检查结果。
历史交付包 SHA256 为
`9e7de48477f7e4c78351b411c7392e44c313b1606ad816efa1b21b3175f65315`。
重新编译的 ELF、临时路径和 ZIP 时间可能不同，不能要求新 wheel 的整体哈希等于历史包。

## 需要从源码重建 SparseMLA 时

`build_base_parallel.py` 保存了原 27 个构建任务和合并过程：
QLI/QSLI 各 4 个 profile；SparseMLA 3 组可选输入乘 5 个地址模式；另外 4 个算子。
这是完整基础包的重建入口，不是上面增量流程的前置要求。

```bash
export ARENA_BUILD_ROOT=/tmp/arena-base-build
mkdir -p "$ARENA_BUILD_ROOT/source"
cp -a net samples "$ARENA_BUILD_ROOT/source/"
python3 release/dsv41-mr348-20261105/restore_base_qli.py "$ARENA_BUILD_ROOT/source"
cp samples/mixed_quant_sparse_flash_mla/mixed_quant_sparse_flash_mla.py \
  "$ARENA_BUILD_ROOT/source/samples/mixed_quant_sparse_flash_mla/mixed_quant_sparse_flash_mla.py"
cp release/dsv41-mr348-20261105/profiles.json "$ARENA_BUILD_ROOT/profiles.json"
python3 release/dsv41-mr348-20261105/build_base_parallel.py
```

输出在 `$ARENA_BUILD_ROOT/artifacts/groups/ds41/wheels/`。
基础源码保留当时的 `0.3.0+ds41upstream20261031` 版本字段；这个全量入口输出该版本。
历史 `local32pipe32.20261104` 包还经过发行版本重标记，不能把刚生成的包直接假定成原包。
增量脚本有原 base wheel SHA 的强校验，因此直接复用原 base wheel 最稳妥。

SparseMLA 源码直接取自交付 wheel 的 `ops/mixed_quant_sparse_flash_mla.py`，SHA256 为
`f553440c4623262686aa42b87bb88d3fe396f76e330dcc1423ad5a03bdb7b461`。

## True / False 如何覆盖

这里的 [profiles.json](profiles.json) 只覆盖本镜像 DSV4.1 的静态配置，不能解释成任意组合全集。

| 开关 | MR348 处理方式 | 本包覆盖 |
| --- | --- | --- |
| QLI `candidate_enabled` | 编译期配置 | 分别导出 False 和 True |
| `has_seqused_q` 等输入有无 | 动态维度，长度允许为 0 | 同一二进制支持传入和不传入 |
| QSLI `has_output_offset` | 编译期配置 | 分别导出默认 True 和 False |

MR348 从编译缓存键移除了输入有无标记；没传入时使用零长度视图，内核按实际长度判断。
因此增量构建只取 QLI 的 profile 0/2、QSLI 的 profile 0/2，
QLI 额外产生 residual 分支，总计 5 个新 native 变体，合并包总计 55 个。
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
