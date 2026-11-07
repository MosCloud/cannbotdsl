# DSV4.1 MR348 arena

基于交付包的源码快照：SparseMLA local32/pipe32、28 核支持及 MR348 QLI/QSLI。

## 全量编译 arena wheel

准备 Linux aarch64、Python 3.12、CANN 9.2.0、cannbot-dsl 0.8.0 编译器及 Python 构建依赖后，
在当前 checkout 根目录执行。**无需 arena base wheel 或旧 Git 提交**，也无需挂载 NPU。

```bash
source /usr/local/Ascend/cann-9.2.0/set_env.sh
python3 release/dsv41-mr348-20261105/build_mr348.py \
  --work-root /tmp/arena-mr348-source-build
python3 -m pip install --no-deps --force-reinstall /tmp/arena-mr348-source-build/wheels/*.whl
```

产物名为 `cannbot_arena_net-*.whl`，安装后的模块名为 `ops`。
构建使用默认并发，脚本不覆盖用户的 `OMP_NUM_THREADS`、`MAX_JOBS` 设置。
工作目录使用本地磁盘；首次构建使用新目录，更改源码或工具链后换新目录。

[源码说明、出包命令与 SHA256](release/dsv41-mr348-20261105/README.md)

原始上游为 CANN cannbot-dsl，许可证见 LICENSE。
