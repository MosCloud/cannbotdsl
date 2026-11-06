"""Build only changed QLI/QSLI natives; merge into the validated optimized wheel."""
from pathlib import Path
import ast,base64,concurrent.futures,csv,hashlib,io,json,os,shutil,struct,subprocess,sys,tarfile,traceback,zipfile
import argparse
REPO=Path(__file__).resolve().parents[2]
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--base-wheel',type=Path,required=True)
parser.add_argument('--work-root',type=Path,required=True)
parser.add_argument('--check-inputs',action='store_true')
args=parser.parse_args()
BASE_WHEEL=args.base_wheel.resolve()
R=args.work_root.resolve()
if R==REPO or REPO in R.parents:
 raise SystemExit('--work-root must be outside the repository')
R.mkdir(parents=True,exist_ok=True)
S=R/'publication';S.mkdir(exist_ok=True)
assert hashlib.sha256(BASE_WHEEL.read_bytes()).hexdigest()=='2eae3c85e54eaa213f6bf68765e4851d2f2f4cf1cadfa4769b4449e182adc345', 'base wheel does not match the validated release'
STATE={};P=R/'jobs';P.mkdir(exist_ok=True)
def save(**kw):
 STATE.update(kw);(S/'build-state.json').write_text(json.dumps(STATE,indent=2));print(json.dumps(kw),flush=True)
def stage():
 src=REPO
 manifest=json.loads((Path(__file__).parent/'upstream-manifest.json').read_text())
 for row in manifest['files']:
  matches=list((src/'samples').rglob(row['local_name']))
  assert len(matches)==1,(row['local_name'],matches)
  data=matches[0].read_bytes()
  assert hashlib.sha256(data).hexdigest()==row['sha256'],row['local_name']
  ast.parse(data)
 profiles=json.loads((Path(__file__).parent/'profiles.json').read_text());jobs=[]
 for op,indices in [('qli',[0,2]),('qsli',[0,2])]:
  for idx in indices:jobs.append(dict(name=f'{op}{idx}',op=op,profiles={op:[profiles[op][idx]]}))
 return src,jobs,manifest

def build_job(src,j):
 w=P/j['name'];out=R/'out'/j['name'];pf=P/(j['name']+'.json');pf.write_text(json.dumps(j['profiles']))
 published=out/'operators'/j['op']
 if (published/'native/manifest.json').is_file() and list((published/'wheels').glob('*.whl')):return dict(**j,exit_code=0,output=str(published),cached=True)
 env=dict(os.environ,CANNBOTDSL_DS41_PROFILES=str(pf),PYTHONUNBUFFERED='1',OMP_NUM_THREADS='2',MAX_JOBS='2')
 for inc in Path('/usr/local/Ascend/cann-9.2.0/tools/hcc/aarch64-target-linux-gnu/include/c++').glob('*'):
  if inc.is_dir():env['CPLUS_INCLUDE_PATH']=str(inc)+':'+str(inc/'aarch64-target-linux-gnu')
 cmd=[sys.executable,str(src/'net/native_package/build.py'),'--operator',j['op'],'--work-root',str(w),'--output-root',str(out)]
 with (S/(j['name']+'.log')).open('w') as f:p=subprocess.run(cmd,env=env,stdout=f,stderr=subprocess.STDOUT)
 return dict(**j,exit_code=p.returncode,output=str(published))
def merge(results,upstream):
 def elf_sections(data):
  h=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
  assert h[0][:6]==b'\x7fELF\x02\x01'
  rows=[struct.unpack_from('<IIQQQQIIQQ',data,h[6]+i*h[11]) for i in range(h[12])]
  names=rows[h[13]];table=data[names[4]:names[4]+names[5]]
  return {table[r[0]:].split(b'\0',1)[0].decode():data[r[4]:r[4]+r[5]] for r in rows if r[1]!=8}
 base=BASE_WHEEL
 with zipfile.ZipFile(base) as z:files={name:z.read(name) for name in z.namelist()}
 original=dict(files);old_info=next(n.rsplit('/',1)[0] for n in files if n.endswith('.dist-info/METADATA'))
 old_version='0.3.0+ds41.local32pipe32.20261104';version='0.3.0+ds41.local32pipe32.mr348.20261105'
 info='cannbot_arena_net-'+version+'.dist-info'
 files={n.replace(old_info,info):v for n,v in files.items() if not n.endswith('.dist-info/RECORD')}
 files[info+'/METADATA']=files[info+'/METADATA'].replace(('Version: '+old_version).encode(),('Version: '+version).encode())
 manifest=json.loads(files['ops/_native/manifest.json']);index=json.loads(files['ops/_native/index.json'])
 def changed_native(n):return n.startswith('ops/_native/operators/qli/') or n.startswith('ops/_native/operators/qsli/')
 files={n:v for n,v in files.items() if not changed_native(n)}
 index={k:v for k,v in index.items() if not v['descriptor'].startswith(('operators/qli/','operators/qsli/'))}
 new_index={};operator_info={};aicpu={};sources={}
 for j in sorted(results,key=lambda x:x['name']):
  out=Path(j['output']);native=out/'native';nm=json.loads((native/'manifest.json').read_text())
  for k in ['schema_version','target','binary_key_schema','host_abi_version']:assert nm[k]==manifest[k],k
  for name,digest in nm['files'].items():assert hashlib.sha256((native/name).read_bytes()).hexdigest()==digest,name
  for key,value in json.loads((native/'index.json').read_text()).items():
   assert key not in new_index or new_index[key]==value;new_index[key]=value
  for path in (native/'operators').rglob('*'):
   if not path.is_file():continue
   if path.name=='operator.json':
    v=json.loads(path.read_text());name=v['name']
    if name not in operator_info:operator_info[name]=v
    else:
     old=operator_info[name];old['requests']+=v['requests'];old['artifacts']=sorted(set(old['artifacts']+v['artifacts']));old['variants'].update(v['variants']);old['sources']=list({json.dumps(x,sort_keys=True):x for x in old['sources']+v['sources']}.values())
   else:
    name='ops/_native/'+path.relative_to(native).as_posix();data=path.read_bytes()
    assert name not in files or files[name]==data;files[name]=data
  for path in (out/'aicpu').glob('*.so'):
   data=path.read_bytes()
   if path.name in aicpu:
    a,b=elf_sections(aicpu[path.name]),elf_sections(data)
    assert a.keys()==b.keys()
    assert all(a[k]==b[k] for k in a if k!='.strtab'),path.name
   else:aicpu[path.name]=data
  wheel=next((out/'wheels').glob('*.whl'))
  with zipfile.ZipFile(wheel) as z:
   for row in upstream['files']:
    name='ops/'+row['local_name']
    if name in z.namelist():
     data=z.read(name);assert name not in sources or sources[name]==data;sources[name]=data
 assert len(sources)==4 and len(aicpu)==2,(sources.keys(),aicpu.keys())
 files.update(sources)
 for name,data in aicpu.items():files['ops/_aicpu/'+name]=data
 for name,v in operator_info.items():files['ops/_native/operators/'+name+'/operator.json']=json.dumps(v,sort_keys=True).encode()
 index.update(new_index);files['ops/_native/index.json']=json.dumps(index,sort_keys=True).encode()
 manifest['files']={n.removeprefix('ops/_native/'):hashlib.sha256(v).hexdigest() for n,v in files.items() if n.startswith('ops/_native/') and n!='ops/_native/manifest.json'}
 files['ops/_native/manifest.json']=json.dumps(manifest,sort_keys=True).encode()
 rows=[[n,'sha256='+base64.urlsafe_b64encode(hashlib.sha256(v).digest()).decode().rstrip('='),str(len(v))] for n,v in files.items()]
 rows.append([info+'/RECORD','','']);stream=io.StringIO(newline='');csv.writer(stream,lineterminator='\n').writerows(rows);files[info+'/RECORD']=stream.getvalue().encode()
 out=S/'wheels';out.mkdir(exist_ok=True);wheel=out/('cannbot_arena_net-'+version+'-cp312-cp312-linux_aarch64.whl')
 with zipfile.ZipFile(wheel,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
  for name,data in sorted(files.items()):z.writestr(name,data)
 preserved=[n for n in original if n.startswith(('ops/_native/operators/mqsmla/','ops/_aicpu/mqsmla')) or n=='ops/mixed_quant_sparse_flash_mla.py']
 assert preserved and all(original[n]==files[n] for n in preserved)
 for row in upstream['files']:assert b'q.record_stream(' not in files['ops/'+row['local_name']]
 report=dict(wheel=str(wheel),sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),version=version,upstream=upstream,manual_q_record_stream_retained=False,tensor_argument_tracking_replaces_manual_patch=True,unchanged_SparseMLA_resources=len(preserved),new_qli_qsli_native_variants=len(new_index),all_native_variants=len(index),metadata_rebuilt=list(aicpu),sources_sha256={n:hashlib.sha256(v).hexdigest() for n,v in sources.items()})
 (S/'wheel-build-manifest.json').write_text(json.dumps(report,indent=2));return report
if args.check_inputs:
 src,jobs,upstream=stage();print(json.dumps({'source_checks':'PASS','jobs':jobs},indent=2));sys.exit(0)
try:
 src,jobs,upstream=stage();save(status='BUILDING',head=upstream['head'],jobs=jobs,results=[])
 results=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
  fs=[pool.submit(build_job,src,j) for j in jobs]
  for f in concurrent.futures.as_completed(fs):results.append(f.result());save(results=results)
 assert all(r['exit_code']==0 for r in results),results
 save(status='MERGING');report=merge(results,upstream);save(status='WHEEL_BUILT_UNVALIDATED',wheel=report['wheel'],sha256=report['sha256'])
except Exception:save(status='FAILED',error=traceback.format_exc());raise
