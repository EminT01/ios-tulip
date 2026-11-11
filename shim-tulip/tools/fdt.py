import struct
def parse(b):
    off_struct,off_str=struct.unpack('>II',b[8:16]); size_str=struct.unpack('>I',b[32:36])[0]
    root={'props':{},'kids':{}}; stack=[root]; p=off_struct
    def s(o): e=b.index(b'\0',off_str+o); return b[off_str+o:e].decode('latin1')
    while True:
        t=struct.unpack('>I',b[p:p+4])[0]; p+=4
        if t==1:
            e=b.index(b'\0',p); name=b[p:e].decode('latin1'); p=(e+4)&~3
            n={'props':{},'kids':{}}; stack[-1]['kids'][name]=n; stack.append(n)
        elif t==2: stack.pop()
        elif t==3:
            ln,no=struct.unpack('>II',b[p:p+8]); p+=8; stack[-1]['props'][s(no)]=b[p:p+ln]; p=(p+ln+3)&~3
        elif t==4: pass
        elif t==9: break
        else: raise ValueError(t)
    return root
def u32s(v): return list(struct.unpack('>%dI'%(len(v)//4),v))
def strs(v): return [x.decode('latin1') for x in v.split(b'\0') if x]
def walk(n,path=''):
    yield path or '/',n
    for k,c in n['kids'].items(): yield from walk(c,(path+'/'+k))
