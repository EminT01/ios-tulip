#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <unistd.h>
#include <objc/runtime.h>
#include <objc/message.h>
#define S(x) sel_registerName(x)
#define C(n) ((id)objc_getClass(n))
typedef id (*f0)(id,SEL);
typedef id (*f1)(id,SEL,id);
typedef id (*f2)(id,SEL,id,id*);
typedef id (*fc)(id,SEL,const char*);
typedef unsigned long (*fu)(id,SEL);
typedef const char* (*fs)(id,SEL);
#include <sys/stat.h>
#define MS(r,s) ((fs)objc_msgSend)(r,S(s))
#define M0(r,s) ((f0)objc_msgSend)(r,S(s))
#define M1(r,s,a) ((f1)objc_msgSend)(r,S(s),a)
#define MU(r,s) ((fu)objc_msgSend)(r,S(s))
static char sum[1024];static int sl;
static void say(const char*f,...){char b[512];__builtin_va_list a;__builtin_va_start(a,f);int n=vsnprintf(b,512,f,a);__builtin_va_end(a);write(2,b,n);}
static id ns(const char*s){return ((fc)objc_msgSend)(C("NSString"),S("stringWithUTF8String:"),s);}
int main(int c,char**v){
 const char*path=c>1?v[1]:"/System/Library/PrivateFrameworks/SpringBoardHome.framework/BoundingPath-Assets.car";
 say("PROBE open %s\n",path);
 void*h=dlopen("/System/Library/PrivateFrameworks/CoreUI.framework/CoreUI",RTLD_NOW);
 say("PROBE coreui %p\n",h);
 say("PROBE s1 getClass NSString\n"); id k1=C("NSString"); say("PROBE s2 %p\n",k1);
 say("PROBE s3 getClass NSURL\n"); id k2=C("NSURL"); say("PROBE s4 %p\n",k2);
 say("PROBE s5 getClass CUICatalog\n"); id k3=C("CUICatalog"); say("PROBE s6 %p\n",k3);
 say("PROBE s7 nsstring\n"); id ps=ns(path); say("PROBE s8 %p\n",ps);
 id url=M1(C("NSURL"),"fileURLWithPath:",ps);
 say("PROBE url %p\n",url);
 id err=0;
 say("PROBE s9 alloc\n"); id al=M0(C("CUICatalog"),"alloc"); say("PROBE s10 %p\n",al);
 id cat=((f2)objc_msgSend)(al,S("initWithURL:error:"),url,&err);
 say("PROBE cat %p err %p\n",cat,err);
 if(!cat){
  struct stat st; int sr=stat(path,&st);
  say("PROBE F1 stat %d size %ld\n",sr,(long)st.st_size);
  if(err){
   unsigned long code=MU(err,"code"); say("PROBE F2 code %lu\n",code);
   id dom=M0(err,"domain"); say("PROBE F3 dom %p\n",dom);
   const char*dd=dom?MS(dom,"UTF8String"):"?"; say("PROBE F4 domain %s\n",dd);
   id ui=M0(err,"userInfo"); say("PROBE F5 userinfo %p\n",ui);
   id desc=M0(err,"description"); say("PROBE F6 desc %p\n",desc);
   const char*d=desc?MS(desc,"UTF8String"):"?"; say("PROBE F7 %.300s\n",d);
  }
  for(;;){say("PROBE FAIL stat %d size %ld err %p\n",sr,(long)st.st_size,err);sleep(2);}}
 id all=M0(cat,"allImageNames");
 unsigned long cnt=all?MU(all,"count"):0;
 say("PROBE allImageNames %p count %lu\n",all,cnt);
 const char*n[]={"BoundingPathBitmap-1125x2436-375x812-3.00x","BoundingPathBitmap-1125x2436-320x693-3.00x","BoundingPathBitmap-1080x2340-375x812-3.00x","BoundingPathBitmap-1170x2532-390x844-3.00x",0};
 for(int i=0;n[i];i++){
  id d=M1(cat,"dataWithName:",ns(n[i]));
  unsigned long l=d?MU(d,"length"):0;
  say("PROBE %s -> %p len %lu\n",n[i],d,l);
  sl+=snprintf(sum+sl,sizeof(sum)-sl,"%d=%lu ",i,l);
 }
 for(;;){say("PROBE SUM cat %p names %lu lens %s\n",cat,cnt,sum);sleep(2);}
 return 0;}
