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
 void*hf=dlopen("/System/Library/Frameworks/Foundation.framework/Foundation",RTLD_NOW);
 say("PROBE foundation %p nsurl %p cucat %p\n",hf,C("NSURL"),C("CUICatalog"));
 id url=M1(C("NSURL"),"fileURLWithPath:",ns(path));
 say("PROBE url %p\n",url);
 id err=0;
 id cat=((f2)objc_msgSend)(M0(C("CUICatalog"),"alloc"),S("initWithURL:error:"),url,&err);
 say("PROBE cat %p err %p\n",cat,err);
 if(!cat){for(;;){say("PROBE SUM cat NULL\n");sleep(2);}}
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
