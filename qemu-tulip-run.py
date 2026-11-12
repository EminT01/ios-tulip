#!/usr/bin/env python3
"""tulip payload'i QEMU virt (GICv3, tulip FB) uzerinde kostur; PC ornekleri + fb.png."""
import json,os,socket,struct,subprocess,sys,time,zlib
PAY,OUT = sys.argv[1], sys.argv[2]
SECS = float(sys.argv[3]) if len(sys.argv)>3 else 60
SAMPLE = float(sys.argv[4]) if len(sys.argv)>4 else 10
FB,W,H,BPP = 0x9d400000,1080,2280,4
ROOTFS = os.environ.get('ROOTFS','rootfs.img')

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
ba=struct.pack('<HH4x4Q6QI4xQI',2,2,virt,pb,ms,top,FB,1,W*BPP,W,H,32,0,adt_pa,asz)
ba+=cmd+b'\0'*4+struct.pack('<2Q',0,ms)
img[ba_pa-start:ba_pa-start+len(ba)]=ba
os.makedirs(OUT,exist_ok=True)
open(f'{OUT}/ram.bin','wb').write(img)
open(f'{OUT}/stub.bin','wb').write(struct.pack('<4I2Q',0x58000080,0x580000a1,0xd61f0020,0xd503201f,ba_pa,ent+delta))
mon=f'{OUT}/m.sock'
if os.path.exists(mon): os.unlink(mon)
pr=subprocess.Popen(['qemu-system-aarch64','-M','virt,gic-version=3','-cpu','cortex-a53','-smp','1',
 '-m','4G','-nographic','-qmp',f'unix:{mon},server,nowait','-no-reboot',
 '-d','int,guest_errors','-D',f'{OUT}/qemu.log',
 '-device',f'loader,file={OUT}/ram.bin,addr={start:#x},force-raw=on',
 '-device',f'loader,file={OUT}/stub.bin,addr=0x40200000,force-raw=on',
 '-device','loader,addr=0x40200000,cpu-num=0',
 '-global','virtio-mmio.force-legacy=false',
 '-drive','file='+ROOTFS+',format=raw,if=none,id=d0,readonly=on',
 '-device','virtio-blk-device,drive=d0'],stdin=subprocess.DEVNULL)
print(f"[*] img_start={start:#x} boot_args={ba_pa:#x} entry={ent+delta:#x}",file=sys.stderr)
time.sleep(3)
s=socket.socket(socket.AF_UNIX);s.settimeout(30);s.connect(mon)
f=s.makefile('rw');f.readline()
def call(ex,**a):
    f.write(json.dumps({'execute':ex,'arguments':a})+'\n');f.flush()
    while True:
        r=json.loads(f.readline())
        if 'return' in r or 'error' in r:return r
call('qmp_capabilities')
samples=[];t0=time.time()
t=SAMPLE
while time.time()-t0<SECS:
    while time.time()-t0<t: time.sleep(0.2)
    call('stop')
    regs=call('human-monitor-command',**{'command-line':'info registers'}).get('return','')
    pc=0
    for tok in regs.replace('\n',' ').split():
        if tok.startswith('PC='): pc=int(tok[3:],16)
    call('cont')
    samples.append({'t':int(t),'pc':pc})
    print(f"sample t={int(t)}s pc={pc:#x}",file=sys.stderr)
    t+=SAMPLE
call('stop')
call('pmemsave',val=FB,size=W*H*BPP,filename=os.path.abspath(f'{OUT}/fb.raw'))
call('pmemsave',val=pb,size=0x18000000,filename=os.path.abspath(f'{OUT}/ramdump.bin'))
pr.kill()
json.dump(samples,open(f'{OUT}/samples.json','w'),indent=1)
raw=open(f'{OUT}/fb.raw','rb').read()
rows=[]
for y in range(H):
    row=raw[y*W*BPP:(y+1)*W*BPP];rgb=bytearray()
    for x in range(W):
        b,g,r,_=row[x*4:x*4+4];rgb+=bytes((r,g,b))
    rows.append(b'\0'+bytes(rgb))
ch=lambda ty,d: struct.pack('>I',len(d))+ty+d+struct.pack('>I',zlib.crc32(ty+d))
png=b'\x89PNG\r\n\x1a\n'+ch(b'IHDR',struct.pack('>IIBBBBB',W,H,8,2,0,0,0))+ch(b'IDAT',zlib.compress(b''.join(rows),6))+ch(b'IEND',b'')
open(f'{OUT}/fb.png','wb').write(png)
print(f"[+] {OUT}/fb.png  {OUT}/qemu.log  {OUT}/samples.json",file=sys.stderr)
