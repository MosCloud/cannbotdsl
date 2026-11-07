"""Build the DSV4.1 MR348 arena wheel from this checkout, without a base wheel."""

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

REPO = Path(__file__).resolve().parents[2]
VERSION = "0.3.0+ds41.local32pipe32.mr348.source20261107"


def build_jobs():
    profiles = json.loads((Path(__file__).parent / "profiles.json").read_text())
    jobs = []
    # MR348 makes optional sequence lengths dynamic: profiles 1/3 duplicate 0/2.
    for op in ("qli", "qsli"):
        for i in (0, 2):
            jobs.append(dict(name=f"{op}{i}", op=op, profiles={op: [profiles[op][i]]}))
    for has_cmp, has_cmp_length in ((False, False), (True, True), (True, False)):
        for mode in ("local", "pipe", "off", "local32", "pipe32"):
            profile = dict(has_cmp=has_cmp, has_ori_length=True,
                           has_cmp_length=has_cmp_length, has_lse=False, addr_mode=mode)
            jobs.append(dict(name=f"mla{int(has_cmp)}{int(has_cmp_length)}{mode}",
                             op="mqsmla", profiles={"mqsmla": [profile]}))
    for op in ("indexer_prologue_qw", "indexer_prologue_k", "engram_gate", "attn_epilogue"):
        jobs.append(dict(name=op, op=op, profiles={}))
    return jobs


def build_job(job, root):
    name, op = job["name"], job["op"]
    output = root / "out" / name
    published = output / "operators" / op
    # A failed build publishes nothing. Resume completed jobs in an unchanged checkout.
    if (published / "native/manifest.json").exists() and list((published / "wheels").glob("*.whl")):
        return dict(**job, exit_code=0, output=str(published))
    profile_file = root / "jobs" / (name + ".json")
    profile_file.write_text(json.dumps(job["profiles"]))
    env = dict(os.environ, CANNBOTDSL_DS41_PROFILES=str(profile_file),
               PYTHONUNBUFFERED="1")
    # AICPU compiler headers for the CANN 9.2.0 release toolchain.
    for inc in Path("/usr/local/Ascend/cann-9.2.0/tools/hcc/aarch64-target-linux-gnu/include/c++").glob("*"):
        if inc.is_dir():
            env["CPLUS_INCLUDE_PATH"] = os.pathsep.join(
                filter(None, (str(inc), str(inc / "aarch64-target-linux-gnu"),
                              env.get("CPLUS_INCLUDE_PATH"))))
    command = [sys.executable, str(REPO / "net/native_package/build.py"),
               "--operator", op, "--work-root", str(root / "work" / name),
               "--output-root", str(output)]
    with (root / "jobs" / (name + ".log")).open("w") as log:
        result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT)
    return dict(**job, exit_code=result.returncode, output=str(published))


def merge(results, root):
    spec = importlib.util.spec_from_file_location("arena_builder", REPO / "net/native_package/build.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    operators, groups = builder.load_catalog()
    with tempfile.TemporaryDirectory(prefix="merge-", dir=root) as temp:
        stage = Path(temp)
        flat = stage / "sources"
        builder.materialize_flat_sources(flat, groups["ds41"], operators)
        package = stage / "package"
        builder.stage_python_package(package, groups["ds41"], operators, flat)
        project = package / "pyproject.toml"
        project.write_text(project.read_text().replace(
            'version = "0.3.0+ds41upstream20261031"', f'version = "{VERSION}"'))
        native = package / "src/ops/_native"
        native.mkdir()
        aicpu = package / "src/ops/_aicpu"
        aicpu.mkdir()
        index, operator_info = {}, {}
        manifest = None
        for result in sorted(results, key=lambda row: row["name"]):
            output = Path(result["output"])
            source = output / "native"
            current = json.loads((source / "manifest.json").read_text())
            if manifest is None:
                manifest = current
            for key, value in json.loads((source / current["index"]).read_text()).items():
                if key in index and index[key] != value:
                    raise ValueError(f"conflicting native variant: {key}")
                index[key] = value
            for path in (source / "operators").rglob("*"):
                if not path.is_file():
                    continue
                if path.name == "operator.json":
                    info = json.loads(path.read_text())
                    name = info["name"]
                    if name not in operator_info:
                        operator_info[name] = info
                    else:
                        old = operator_info[name]
                        old["requests"] += info["requests"]
                        old["artifacts"] = sorted(set(old["artifacts"] + info["artifacts"]))
                        old["variants"].update(info["variants"])
                        old["sources"] = list({json.dumps(x, sort_keys=True): x
                                               for x in old["sources"] + info["sources"]}.values())
                else:
                    destination = native / path.relative_to(source)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    if destination.exists() and destination.read_bytes() != path.read_bytes():
                        raise ValueError(f"conflicting native artifact: {destination}")
                    shutil.copy2(path, destination)
            # Each profile of an operator builds the same metadata source.
            for path in (output / "aicpu").glob("*.so"):
                if not (aicpu / path.name).exists():
                    shutil.copy2(path, aicpu / path.name)
        for name, info in operator_info.items():
            (native / "operators" / name / "operator.json").write_text(json.dumps(info, sort_keys=True))
        (native / "index.json").write_text(json.dumps(index, sort_keys=True))
        manifest["files"] = {p.relative_to(native).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in native.rglob("*") if p.is_file()}
        (native / "manifest.json").write_text(json.dumps(manifest, sort_keys=True))
        metadata = sorted(p.name for p in aicpu.glob("*.so"))
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-index",
                        "--no-build-isolation", "--wheel-dir", str(root / "wheels"), str(package)], check=True)
    wheel = next((root / "wheels").glob(f"cannbot_arena_net-{VERSION}-*.whl"))
    return dict(wheel=str(wheel), sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
                version=VERSION, all_native_variants=len(index),
                operators=sorted(operator_info), metadata=metadata)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", type=Path, required=True)
    parser.add_argument("--plan", action="store_true", help="print the source build jobs without compiling")
    args = parser.parse_args()
    jobs = build_jobs()
    if args.plan:
        print(json.dumps(dict(source=str(REPO), version=VERSION, jobs=jobs), indent=2))
        return
    root = args.work_root.resolve()
    (root / "jobs").mkdir(parents=True, exist_ok=True)
    state = dict(status="BUILDING", source=str(REPO), results=[])

    def save():
        (root / "build-state.json").write_text(json.dumps(state, indent=2))

    save()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        futures = [pool.submit(build_job, job, root) for job in jobs]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            state["results"].append(result)
            save()
            print(result["name"], result["exit_code"], flush=True)
    if any(result["exit_code"] for result in state["results"]):
        state["status"] = "FAILED"
        save()
        raise SystemExit(f"Compilation failed; see {root / 'jobs'} for logs")
    state["status"] = "MERGING"
    save()
    report = merge(state["results"], root)
    (root / "wheel-build-manifest.json").write_text(json.dumps(report, indent=2))
    state.update(status="WHEEL_BUILT_UNVALIDATED", **report)
    save()
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
