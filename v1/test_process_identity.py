"""Windows native-host regression: identity, pipes, spawn and relocated runtime."""
import argparse,ctypes as ct,json,multiprocessing as mp,os,shutil,struct,subprocess,sys
from pathlib import Path
from zipfile import ZipFile

ROOT=Path(__file__).resolve().parents[1]

def identity():
    kernel=ct.WinDLL('kernel32');kernel.GetModuleFileNameW.argtypes=[ct.c_void_p,ct.c_wchar_p,ct.c_uint]
    path=ct.create_unicode_buffer(32768);assert kernel.GetModuleFileNameW(None,path,len(path))
    return dict(executable=sys.executable,image=path.value,pid=os.getpid(),console=kernel.GetConsoleWindow())

def spawned(connection):
    connection.send(identity());connection.close()

def file_description(path):
    dll=ct.WinDLL('version');dll.GetFileVersionInfoSizeW.argtypes=[ct.c_wchar_p,ct.c_void_p]
    dll.GetFileVersionInfoW.argtypes=[ct.c_wchar_p,ct.c_uint,ct.c_uint,ct.c_void_p]
    dll.VerQueryValueW.argtypes=[ct.c_void_p,ct.c_wchar_p,ct.POINTER(ct.c_void_p),ct.POINTER(ct.c_uint)]
    size=dll.GetFileVersionInfoSizeW(str(path),None);assert size
    buffer=ct.create_string_buffer(size);assert dll.GetFileVersionInfoW(str(path),0,size,buffer)
    ptr=ct.c_void_p();length=ct.c_uint();assert dll.VerQueryValueW(buffer,r'\StringFileInfo\040904b0\FileDescription',ct.byref(ptr),ct.byref(length))
    return ct.wstring_at(ptr.value)

def imported_dlls(path):
    data=path.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0]
    count=struct.unpack_from('<H',data,pe+6)[0];size=struct.unpack_from('<H',data,pe+20)[0];optional=pe+24;table=optional+size
    assert struct.unpack_from('<H',data,optional)[0]==0x20b
    sections=[]
    for i in range(count):
        virtual,base,raw_size,raw=struct.unpack_from('<IIII',data,table+40*i+8)
        sections.append((base,max(virtual,raw_size),raw))
    def offset(rva):return next(raw+rva-base for base,size,raw in sections if base<=rva<base+size)
    pos=offset(struct.unpack_from('<I',data,optional+120)[0]);names=[]
    while any(data[pos:pos+20]):
        start=offset(struct.unpack_from('<I',data,pos+12)[0]);names.append(data[start:data.index(b'\0',start)].decode('ascii'));pos+=20
    return names

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--host',type=Path);parser.add_argument('--python-zip',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--spawn-probe',action='store_true');parser.add_argument('--qprocess-probe',action='store_true');args=parser.parse_args()
    if args.spawn_probe:
        context=mp.get_context('spawn');parent,child=context.Pipe();worker=context.Process(target=spawned,args=(child,));worker.start();child.close()
        try:
            assert parent.poll(15),'Spawn child timeout';result=parent.recv();worker.join(10);assert worker.exitcode==0;print(json.dumps(dict(parent=identity(),worker=result)))
        finally:
            if worker.is_alive():worker.terminate();worker.join(5)
            parent.close()
        return
    if args.qprocess_probe:
        from PySide6.QtCore import QCoreApplication,QProcess
        app=QCoreApplication([]);process=QProcess();process.setProgram(sys.executable);process.setArguments(['-u','-c',"import json,sys;print(json.dumps({'event':'done','text':'파일 변환 통신'},ensure_ascii=False));print('worker diagnostic',file=sys.stderr)"])
        process.start();assert process.waitForStarted(5000);assert process.waitForFinished(15000);assert process.exitCode()==0
        value=bytes(process.readAllStandardOutput()).decode('utf-8');error=bytes(process.readAllStandardError()).decode('utf-8');assert json.loads(value)['event']=='done' and 'worker diagnostic' in error;print(json.dumps(dict(qprocess_json=True,program=process.program())))
        return
    assert args.host and args.python_zip and args.output
    host=args.host.resolve();args.output.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,PYTHONIOENCODING='utf-8')
    def run(exe,arguments,**kwargs):
        return subprocess.run([str(exe),*arguments],capture_output=True,text=True,encoding='utf-8',env=env,timeout=40,creationflags=subprocess.CREATE_NO_WINDOW,**kwargs)
    report=dict(passed=False,scope='Native host and worker contracts; no capture/inference or visual Task Manager automation',checks={})
    try:
        data=host.read_bytes();pe=struct.unpack_from('<I',data,0x3c)[0];assert data[pe:pe+4]==b'PE\0\0';assert struct.unpack_from('<H',data,pe+24+68)[0]==2
        assert host.name=='ScreenTo3D.exe' and file_description(host)=='ScreenTo3D'
        report['checks']['resource_identity_and_gui_subsystem']=True
        system={'kernel32.dll','shell32.dll','user32.dll','ucrtbase.dll'}
        imports=imported_dlls(host)
        missing=[name for name in imports if name.lower() not in system and not name.lower().startswith('api-ms-win-') and not (host.parent/name).is_file()]
        assert not missing,'Host requires unbundled runtime DLLs: '+str(missing)
        report['checks']['no_unbundled_runtime_dependency']=True;report['imported_dlls']=imports
        text='입력 테스트\n';code="import sys,json,ctypes;print(json.dumps(dict(executable=sys.executable,isolated=sys.flags.isolated,console=ctypes.windll.kernel32.GetConsoleWindow(),literal='파일 변환 통신',input=sys.stdin.readline()),ensure_ascii=False));print('stderr probe',file=sys.stderr)"
        result=run(host,['-I','-c',code],input=text);assert result.returncode==0,result.stderr;value=json.loads(result.stdout);assert Path(value['executable']).resolve()==host and value['isolated']==1 and value['console']==0 and value['input']==text and value['literal']=='파일 변환 통신' and 'stderr probe' in result.stderr
        report['checks']['unicode_pipes_and_isolated_runtime']=True
        result=run(host,[str(Path(__file__).resolve()),'--spawn-probe']);assert result.returncode==0,result.stderr;value=json.loads(result.stdout)
        for entry in value.values():assert Path(entry['image']).resolve()==host and Path(entry['executable']).resolve()==host and entry['console']==0
        report['checks']['spawned_worker_identity']=True
        result=run(host,[str(Path(__file__).resolve()),'--qprocess-probe']);assert result.returncode==0,result.stderr;assert json.loads(result.stdout)['qprocess_json'];report['checks']['qprocess_json_protocol']=True
        assert run(host,['-c','raise SystemExit(37)']).returncode==37;assert run(host,['--unknown-host-option']).returncode==2;report['checks']['exit_status_and_argument_errors']=True
        relocated=args.output/'한글 공백 경로'/'python'
        with ZipFile(args.python_zip) as archive:archive.extractall(relocated)
        moved=relocated/'ScreenTo3D.exe';shutil.copy2(host,moved)
        arguments=['한글 공백','a"b','C:\\trailing space\\'];result=run(moved,['-I','-c','import sys,json;print(json.dumps(sys.argv[1:],ensure_ascii=False))',*arguments],cwd=args.output)
        assert result.returncode==0 and json.loads(result.stdout)==arguments,result.stderr;report['checks']['relocated_unicode_space_paths_and_quoted_arguments']=True
        missing=args.output/'missing-runtime';missing.mkdir();shutil.copy2(host,missing/host.name);result=run(missing/host.name,['-c','print(1)']);assert result.returncode==126 and 'cannot load adjacent' in result.stderr;report['checks']['missing_adjacent_runtime_fails_closed']=True
        report['passed']=True
    finally:
        (args.output/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report),flush=True)

if __name__=='__main__':main()
