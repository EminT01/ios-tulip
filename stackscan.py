import json,os,socket,struct,subprocess,sys,time,bisect
PAY,OUT,SECS = sys.argv[1],sys.argv[2],float(sys.argv[3]) if len(sys.argv)>3 else 30
p=open(PAY,'rb').read()
ns=struct.unpack_from('<I',p,12)[0]
virt,ent,ao,asz,ke,pb,ms=struct.unpack_from('<7Q',p,0x10)
PG=0x1000; delta=pb-virt
adt_pa=ke+delta; ba_pa=(adt_pa+asz+PG-1)&~(PG-1); top=ba_pa+PG
sps=[struct.unpack_from('<4Q',p,0x2a8+32*i)[0]+delta for i in range(ns)]
start=min(sps+[pb])&~(PG-1)
img=bytearray(top-start)
for i in range(ns):
    vm,vs,fo,fs=struct.unpack_from('<4Q',p,0x2a8+32*i)
    img[vm+delta-start:vm+delta-start+fs]=p[fo:fo+fs]
img[adt_pa-start:adt_pa-start+asz]=p[ao:ao+asz]
cmd=p[0x48:0x48+608]
ba=struct.pack('<HH4x4Q6QI4xQI',2,2,virt,pb,ms,top,0x9d400000,1,1080*4,1080,2280,32,0,adt_pa,asz)
ba+=cmd+b'\0'*4+struct.pack('<2Q',0,ms)
img[ba_pa-start:ba_pa-start+len(ba)]=ba
os.makedirs(OUT,exist_ok=True)
open(f'{OUT}/ram.bin','wb').write(img)
open(f'{OUT}/stub.bin','wb').write(struct.pack('<4I2Q',0x58000080,0x580000a1,0xd61f0020,0xd503201f,ba_pa,ent+delta))
mon=f'{OUT}/m.sock'
if os.path.exists(mon): os.unlink(mon)
pr=subprocess.Popen(['qemu-system-aarch64','-M','virt,gic-version=3','-cpu','cortex-a53','-smp','1',
 '-m','4G','-nographic','-qmp',f'unix:{mon},server,nowait','-no-reboot',
 '-device',f'loader,file={OUT}/ram.bin,addr={start:#x},force-raw=on',
 '-device',f'loader,file={OUT}/stub.bin,addr=0x40200000,force-raw=on',
 '-device','loader,addr=0x40200000,cpu-num=0'],stdin=subprocess.DEVNULL)
time.sleep(SECS)
s=socket.socket(socket.AF_UNIX);s.settimeout(30);s.connect(mon)
f=s.makefile('rw');f.readline()
def call(ex,**a):
    f.write(json.dumps({'execute':ex,'arguments':a})+'\n');f.flush()
    while True:
        r=json.loads(f.readline())
        if 'return' in r or 'error' in r:return r
call('qmp_capabilities');call('stop')
regs=call('human-monitor-command',**{'command-line':'info registers'}).get('return','')
v={}
for tok in regs.replace('\n',' ').split():
    if '=' in tok:
        k,val=tok.split('=',1)
        try:v[k]=int(val,16)
        except:pass
print(f"PC={v.get('PC',0):#x} SP={v.get('SP',0):#x} X29={v.get('X29',0):#x}")
sp=v.get('SP',0)
# VA'dan oku (guest MMU'su uzerinden)
txt=call('human-monitor-command',**{'command-line':f'x/512gx {sp:#x}'}).get('return','')
pr.kill()
stk=b''
vals=[]
for line in txt.splitlines():
    if ':' in line and '0x' in line:
        parts=line.split(':')[1].split()
        for w in parts:
            try: vals.append(int(w,16))
            except: pass
stk=struct.pack('<%dQ'%len(vals), *vals) if vals else b''
base=sp
# kernel text sembolleri
K="kernel/kernel.development.vince";S=[]
for l in subprocess.run(["llvm-nm","-n","--defined-only",K],capture_output=True,text=True).stdout.splitlines():
    q=l.split()
    if len(q)==3:
        try:S.append((int(q[0],16),q[2]))
        except:pass
S.sort();A=[x for x,_ in S]
lo,hi=A[0],A[-1]
def sym(a):
    i=bisect.bisect_right(A,a)-1
    return f"{S[i][1]}+0x{a-S[i][0]:x}" if i>=0 else hex(a)
print("=== stack'te kernel adresleri (cagri zinciri) ===")
seen=[]
for off in range(0,len(stk)-8,8):
    val=struct.unpack_from('<Q',stk,off)[0]
    if lo<=val<=hi:
        n=sym(val)
        if n not in seen:
            seen.append(n)
            print(f"  sp+{off:#06x}  {val:#x}  {n}")
