#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <dlfcn.h>
#include <unistd.h>
#include <sys/stat.h>
#include <objc/runtime.h>
#include <objc/message.h>
#define S(x) sel_registerName(x)
#define C(n) ((id)objc_getClass(n))
typedef id (*f0)(id,SEL);
typedef id (*f1)(id,SEL,id);
typedef id (*f2)(id,SEL,id,id*);
typedef id (*fi)(id,SEL,unsigned long);
typedef id (*fc)(id,SEL,const char*);
typedef unsigned long (*fu)(id,SEL);
typedef const char* (*fs)(id,SEL);
#define M0(r,s) ((f0)objc_msgSend)(r,S(s))
#define M1(r,s,a) ((f1)objc_msgSend)(r,S(s),a)
#define MU(r,s) ((fu)objc_msgSend)(r,S(s))
#define MS(r,s) ((fs)objc_msgSend)(r,S(s))
static void say(const char*f,...){char b[600];__builtin_va_list a;__builtin_va_start(a,f);int n=vsnprintf(b,600,f,a);__builtin_va_end(a);write(2,b,n);}
static id ns(const char*s){return ((fc)objc_msgSend)(C("NSString"),S("stringWithUTF8String:"),s);}
static char res[2][400];
static void one(int k,const char*path){
 struct stat st; int sr=stat(path,&st);
 say("PROBE K%d %s stat %d size %ld\n",k,path+strlen(path)-14,sr,(long)st.st_size);
 id err=0;
 id cat=((f2)objc_msgSend)(M0(C("CUICatalog"),"alloc"),S("initWithURL:error:"),M1(C("NSURL"),"fileURLWithPath:",ns(path)),&err);
 if(!cat){snprintf(res[k],400,"K%d nocat",k);return;}
 id all=M0(cat,"allImageNames"); unsigned long cnt=all?MU(all,"count"):0;
 int tot=0,got=0; char ok[300]=""; int ol=0;
 for(unsigned long i=0;i<cnt;i++){
  id nm=((fi)objc_msgSend)(all,S("objectAtIndex:"),i);
  const char*u=nm?MS(nm,"UTF8String"):"?";
  if(strncmp(u,"BoundingPathBitmap",18))continue;
  tot++;
  id d=M1(cat,"dataWithName:",nm);
  if(d){got++; id dd=M0(d,"data"); if(ol<250) ol+=snprintf(ok+ol,300-ol,"%.22s=%lu ",u+19,dd?MU(dd,"length"):0);}
 }
 snprintf(res[k],400,"K%d names %lu tot %d nonnil %d %s",k,cnt,tot,got,ok);
 say("PROBE %s\n",res[k]);
}
int main(int c,char**v){
 const char*dir="/System/Library/PrivateFrameworks/UIKitCore.framework/BoundingPathData.bundle/";
 char p0[300],p1[300]; snprintf(p0,300,"%sAssets.car",dir); snprintf(p1,300,"%sAssets.car.orig",dir);
 say("PROBE v9 start\n");
 dlopen("/System/Library/PrivateFrameworks/CoreUI.framework/CoreUI",RTLD_NOW);
 /* idiom-related selectors of CUICatalog */
 { unsigned n=0; Method*m=class_copyMethodList(C("CUICatalog"),&n); char b[500]=""; int l=0; int cn=0;
   for(unsigned i=0;i<n;i++){ const char*s=sel_getName(method_getName(m[i]));
     if(strcasestr(s,"idiom")||strncmp(s,"dataWith",8)==0||strcasestr(s,"namedData")){ if(l<420) l+=snprintf(b+l,500-l,"%s ",s); cn++; if(l>=420){say("PROBE SEL %s\n",b);l=0;b[0]=0;} } }
   if(l) say("PROBE SEL %s\n",b); say("PROBE SEL total %d of %u\n",cn,n); }
 one(0,p0); one(1,p1);
 for(;;){say("PROBE SUM9 %s | %s\n",res[0],res[1]);sleep(2);}
 return 0;}
