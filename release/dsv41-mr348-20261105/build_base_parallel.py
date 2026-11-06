import concurrent.futures,hashlib,importlib.util,json,os,shutil,subprocess,sys,zipfile
from pathlib import Path
R=Path(os.environ['ARENA_BUILD_ROOT']).resolve();P=R/'parallel';P.mkdir(exist_ok=True)
src=R/'source';profiles=json.loads((R/'profiles.json').read_text());jobs=[]
for op in ['qli','qsli']:
 for i,profile in enumerate(profiles[op]):jobs.append(dict(name=f'{op}{i}',op=op,profiles={op:[profile]}))
for has_cmp,has_cl in [(False,False),(True,True),(True,False)]:
 for mode in ['local','pipe','off','local32','pipe32']:
  profile=dict(has_cmp=has_cmp,has_ori_length=True,has_cmp_length=has_cl,has_lse=False,addr_mode=mode)
  jobs.append(dict(name=f'mla{int(has_cmp)}{int(has_cl)}{mode}',op='mqsmla',profiles={'mqsmla':[profile]}))
for op in ['indexer_prologue_qw','indexer_prologue_k','engram_gate','attn_epilogue']:jobs.append(dict(name=op,op=op,profiles={}))
state=dict(status='RUNNING',jobs=jobs)
def save():(P/'state.json').write_text(json.dumps(state,indent=2))
def run(j):
 w=P/'work'/j['name'];out=P/'out'/j['name'];pf=P/(j['name']+'.json');pf.write_text(json.dumps(j['profiles']))
 published=out/'operators'/j['op']
 if (published/'native/manifest.json').exists() and list((published/'wheels').glob('*.whl')):return 0,str(published)
 cache=w/'operators'/j['op']/'cache';cache.parent.mkdir(parents=True,exist_ok=True)
 shared=R/'compile-cache';shared.mkdir(parents=True,exist_ok=True)
 if not cache.exists():cache.symlink_to(shared,target_is_directory=True)
 env=dict(os.environ,CANNBOTDSL_DS41_PROFILES=str(pf),PYTHONUNBUFFERED='1',OMP_NUM_THREADS='2')
 for inc in Path('/usr/local/Ascend/cann-9.2.0/tools/hcc/aarch64-target-linux-gnu/include/c++').glob('*'):
  if inc.is_dir():env['CPLUS_INCLUDE_PATH']=str(inc)+':'+str(inc/'aarch64-target-linux-gnu')
 if not j['profiles']:env.pop('CANNBOTDSL_DS41_PROFILES',None)
 with (P/(j['name']+'.log')).open('w') as f:
  result=subprocess.run([sys.executable,str(src/'net/native_package/build.py'),'--operator',j['op'],'--work-root',str(w),'--output-root',str(out)],env=env,stdout=f,stderr=subprocess.STDOUT)
 return result.returncode,str(out/'operators'/j['op'])
save()
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
 fs={pool.submit(run,j):j for j in jobs}
 for f in concurrent.futures.as_completed(fs):
  j=fs[f];j['exit_code'],j['output']=f.result();save();print(j['name'],j['exit_code'],flush=True)
if any(j['exit_code'] for j in jobs):state['status']='FAIL';save();sys.exit(1)
state['status']='MERGING';save()
native=P/'merged-native';native.mkdir();index={};opinfo={};manifest=None;aicpu={}
for j in jobs:
 out=Path(j['output']);n=out/'native';m=json.loads((n/'manifest.json').read_text())
 if manifest is None:manifest=m
 else:
  for k in ['schema_version','target','binary_key_schema','host_abi_version']:assert m[k]==manifest[k]
 for name,digest in m['files'].items():assert hashlib.sha256((n/name).read_bytes()).hexdigest()==digest
 for key,value in json.loads((n/m['index']).read_text()).items():
  assert key not in index or index[key]==value
  index[key]=value
 for path in (n/'operators').rglob('*'):
  if not path.is_file():continue
  if path.name=='operator.json':
   v=json.loads(path.read_text());name=v['name']
   if name not in opinfo:opinfo[name]=v
   else:
    old=opinfo[name];old['requests']+=v['requests'];old['artifacts']=sorted(set(old['artifacts']+v['artifacts']));old['variants'].update(v['variants']);old['sources']=list({json.dumps(x,sort_keys=True):x for x in old['sources']+v['sources']}.values())
  else:
   dest=native/path.relative_to(n);dest.parent.mkdir(parents=True,exist_ok=True)
   if dest.exists():assert dest.read_bytes()==path.read_bytes()
   else:shutil.copy2(path,dest)
 for path in (out/'aicpu').glob('*.so'):
  data=path.read_bytes();assert data[:4]==b'\x7fELF';aicpu.setdefault(path.name,data)
for name,v in opinfo.items():(native/'operators'/name/'operator.json').write_text(json.dumps(v,sort_keys=True))
(native/'index.json').write_text(json.dumps(index,sort_keys=True));manifest['files']={p.relative_to(native).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in native.rglob('*') if p.is_file()}
(native/'manifest.json').write_text(json.dumps(manifest,sort_keys=True))
spec=importlib.util.spec_from_file_location('builder',src/'net/native_package/build.py');b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
ops,groups=b.load_catalog();flat=P/'flat';b.materialize_flat_sources(flat,groups['ds41'],ops);package=P/'package';b.stage_python_package(package,groups['ds41'],ops,flat)
shutil.copytree(native,package/'src/ops/_native');ad=package/'src/ops/_aicpu';ad.mkdir();assert len(aicpu)==3
for name,data in aicpu.items():(ad/name).write_bytes(data)
dest=R/'artifacts/groups/ds41';dest.mkdir(parents=True,exist_ok=True)
subprocess.run([sys.executable,'-m','pip','wheel','--no-deps','--no-index','--no-build-isolation','--wheel-dir',str(dest/'wheels'),str(package)],check=True)
wheel=max((dest/'wheels').glob('*.whl'),key=lambda p:p.stat().st_mtime)
state.update(status='PASS',variants=len(index),wheel=str(wheel));save();(R/'build.PASS').touch()
