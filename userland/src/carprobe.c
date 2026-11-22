#include <stdio.h>
#include <string.h>
#include <dlfcn.h>
#include <unistd.h>
#include <objc/runtime.h>
#include <objc/message.h>
#define S(x) sel_registerName(x)
#define M ((id(*)(id,SEL,...))objc_msgSend)
static void say(const char*f,...){char b[512];__builtin_va_list a;__builtin_va_start(a,f);int n=vsnprintf(b,512,f,a);__builtin_va_end(a);write(2,b,n);}
static id ns(const char*s){return M((id)objc_getClass("NSString"),S("stringWithUTF8String:"),s);}
int main(int c,char**v){
 const char*path=c>1?v[1]:"/System/Library/PrivateFrameworks/SpringBoardHome.framework/BoundingPath-Assets.car";
 say("PROBE open %s\n",path);
 void*h=dlopen("/System/Library/PrivateFrameworks/CoreUI.framework/CoreUI",RTLD_NOW);
 say("PROBE coreui %p\n",h);
 id url=M((id)objc_getClass("NSURL"),S("fileURLWithPath:"),ns(path));
 id err=0;
 id cat=M(M((id)objc_getClass("CUICatalog"),S("alloc")),S("initWithURL:error:"),url,&err);
 say("PROBE cat %p err %p\n",cat,err);
 if(!cat)return 1;
 id all=M(cat,S("allImageNames"));
 say("PROBE allImageNames %p count %lu\n",all,all?(unsigned long)M(all,S("count")):0);
 const char*n[]={"BoundingPathBitmap-1125x2436-375x812-3.00x","BoundingPathBitmap-1125x2436-320x693-3.00x","BoundingPathBitmap-1080x2340-375x812-3.00x","BoundingPathBitmap-1170x2532-390x844-3.00x",0};
 for(int i=0;n[i];i++){
  id d=M(cat,S("dataWithName:"),ns(n[i]));
  say("PROBE %s -> %p len %lu\n",n[i],d,d?(unsigned long)M(d,S("length")):0);
  id nd=M(cat,S("namedDataWithName:"),ns(n[i]));
  say("PROBE   named %p\n",nd);
 }
 return 0;}
