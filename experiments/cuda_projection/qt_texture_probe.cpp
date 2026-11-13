#include <QtGui/QGuiApplication>
#include <QtQuick/QQuickWindow>
#include <QtQuick/QQuickItem>
#include <QtQuick/QSGSimpleTextureNode>
#include <QtQuick/qsgtexture_platform.h>
#include <QtQuick/QSGRendererInterface>
#include <QtCore/QTimer>
#include <QtCore/QDir>
#include <QtGui/QImage>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cmath>

extern "C" {
__declspec(dllimport) const char* texture_last_error();
__declspec(dllimport) void texture_counts(int*,int*,int*);
__declspec(dllimport) void* texture_create(void*,int,int);
__declspec(dllimport) void* texture_handle(void*,int);
__declspec(dllimport) int texture_begin(void*,int,int,int);
__declspec(dllimport) int texture_end(void*);
__declspec(dllimport) int texture_destroy(void*);
}
static void require(bool ok,const char* label) {
    if(!ok){std::fprintf(stderr,"%s: %s\n",label,texture_last_error());std::fflush(stderr);std::exit(2);}
}
struct SharedNode:QSGSimpleTextureNode {
    void* source=nullptr;
    QSGTexture* wrappers[2]={};
    int width,height,index=0,frame=0;
    bool clear=false;
    SharedNode(QQuickWindow* window,int w,int h):width(w),height(h) {
        auto* ri=window->rendererInterface();
        require(ri->graphicsApi()==QSGRendererInterface::Direct3D11,"Expected D3D11");
        source=texture_create(ri->getResource(window,QSGRendererInterface::DeviceResource),w,h);
        require(source!=nullptr,"Create native source");
        for(int i=0;i<2;i++) {
            wrappers[i]=QNativeInterface::QSGD3D11Texture::fromNative(texture_handle(source,i),window,QSize(w,h));
            require(wrappers[i]!=nullptr,"Wrap native texture");
            wrappers[i]->setFiltering(QSGTexture::Nearest);
        }
        setOwnsTexture(false);setTexture(wrappers[0]);
    }
    ~SharedNode() override {
        require(texture_end(source),"Finish native source");
        delete wrappers[0];delete wrappers[1];
        require(texture_destroy(source),"Destroy native source");
    }
};
class NativeItem:public QQuickItem {
public:
    SharedNode* current=nullptr;
    int textureWidth=3840,textureHeight=1080;
    bool clear=false;
    std::atomic<int> begins{0},ends{0},generations{0};
    std::atomic<int> renderedFrame{0};
    NativeItem(QQuickWindow* win):QQuickItem(win->contentItem()) {
        setFlag(ItemHasContents,true);
        QObject::connect(win,&QQuickWindow::beforeRendering,this,[this] {
            if(current){require(texture_begin(current->source,current->index,current->frame,current->clear),"Begin frame");renderedFrame=current->frame;begins++;}
        },Qt::DirectConnection);
        QObject::connect(win,&QQuickWindow::afterFrameEnd,this,[this] {
            if(current){require(texture_end(current->source),"End frame");ends++;}
        },Qt::DirectConnection);
        QObject::connect(win,&QQuickWindow::sceneGraphInvalidated,this,[this]{current=nullptr;},Qt::DirectConnection);
    }
    QSGNode* updatePaintNode(QSGNode* old,UpdatePaintNodeData*) override {
        auto* node=static_cast<SharedNode*>(old);
        if(node && (node->width!=textureWidth || node->height!=textureHeight)){delete node;node=nullptr;current=nullptr;}
        if(!node){node=new SharedNode(window(),textureWidth,textureHeight);generations++;}
        node->index=1-node->index;node->frame++;node->clear=clear;
        node->setTexture(node->wrappers[node->index]);node->setRect(boundingRect());
        node->markDirty(QSGNode::DirtyMaterial);current=node;return node;
    }
};
int main(int argc,char** argv) {
    QGuiApplication app(argc,argv);
    const bool publicVideo=qEnvironmentVariableIsSet("SCREENTO3D_TEXTURE_PUBLIC") || qEnvironmentVariableIsSet("STEREOTO3D_TEXTURE_PUBLIC") || qEnvironmentVariableIsSet("DEPTHSBS_TEXTURE_PUBLIC");
    const int timeScale=publicVideo?3:1;
    QQuickWindow::setGraphicsApi(QSGRendererInterface::Direct3D11);
    QQuickWindow window;window.setTitle("ScreenTo3D native texture boundary test");
    window.setFlags(Qt::Window|Qt::WindowStaysOnTopHint);
    window.setPersistentSceneGraph(false);window.setPersistentGraphics(false);
    window.setColor(Qt::black);window.resize(960,publicVideo?270:540);
    NativeItem item(&window);item.setSize(QSizeF(window.width(),window.height()));
    QObject::connect(&window,&QQuickWindow::widthChanged,&item,[&]{item.setWidth(window.width());item.update();});
    QObject::connect(&window,&QQuickWindow::heightChanged,&item,[&]{item.setHeight(window.height());item.update();});
    std::atomic<int> swaps{0};
    QObject::connect(&window,&QQuickWindow::frameSwapped,&window,[&]{swaps++;},Qt::DirectConnection);
    int ticks=0;
    QTimer ticker;QObject::connect(&ticker,&QTimer::timeout,&item,[&]{ticks++;item.update();window.update();});ticker.start(16);
    QString output=argc>1?QString::fromLocal8Bit(argv[1]):QStringLiteral("out/qt-texture-probe");QDir().mkpath(output);
    bool patterned=false,cleared=false,restored=false;
    int hiddenBegins=0;
    auto capture=[&](const QString& name,bool black) {
        auto image=window.grabWindow().convertToFormat(QImage::Format_RGBA8888);
        require(!image.isNull(),"Window capture");require(image.save(output+"/"+name+".png"),"Save capture");
        int nonblack=0;for(int y=0;y<image.height();y++)for(int x=0;x<image.width();x++) {
            auto* p=image.constScanLine(y)+x*4;if(p[0] || p[1] || p[2])nonblack++;
        }
        require(black?nonblack==0:nonblack>image.width()*image.height()/2,"Visible pixels");
        int exactSamples=0,frame=item.renderedFrame.load();
        if(!publicVideo)for(int y=3;y<image.height();y+=17)for(int x=3;x<image.width();x+=17) {
            double fx=(x+.5)*item.textureWidth/image.width(),fy=(y+.5)*item.textureHeight/image.height();
            // Exclude nearest-neighbor sample-boundary ties, not color errors.
            if(fx-std::floor(fx)<.05 || fx-std::floor(fx)>.95 || fy-std::floor(fy)<.05 || fy-std::floor(fy)>.95)continue;
            int sx=static_cast<int>(fx),sy=static_cast<int>(fy);
            auto* p=image.constScanLine(y)+x*4;
            bool exact=black?(p[0]==0 && p[1]==0 && p[2]==0):
                (p[0]==(sx+frame)%256 && p[1]==(sy+frame*3)%256 && p[2]==(sx+sy+frame*7)%256);
            if(!exact)std::fprintf(stderr,"Pixel %d,%d source %d,%d frame %d got %d,%d,%d\n",x,y,sx,sy,frame,p[0],p[1],p[2]);
            require(exact && p[3]==255,"Qt sampled color/frame oracle");exactSamples++;
        }
        if(!publicVideo)require(exactSamples>100,"Qt sample coverage");
        if(publicVideo && !black) {
            require(std::abs(double(image.width())/image.height()-double(item.textureWidth)/item.textureHeight)<.01,"Public SBS aspect ratio");
            int differences=0;
            for(int y=0;y<image.height();y++)for(int x=0;x<image.width()/2;x++)
                if(image.pixel(x,y)!=image.pixel(x+image.width()/2,y))differences++;
            require(differences>100,"Distinct public SBS eyes");
        }
        std::printf("{\"capture\":\"%s\",\"nonblack_pixels\":%d,\"exact_color_samples\":%d,\"frame_id\":%d}\n",name.toUtf8().constData(),nonblack,exactSamples,frame);
    };
    window.show();window.raise();window.requestActivate();
    QTimer::singleShot(1000*timeScale,&app,[&]{capture("pattern",false);patterned=true;item.textureWidth=1200;item.textureHeight=420;window.resize(600,publicVideo?210:420);item.update();});
    QTimer::singleShot(2000*timeScale,&app,[&]{capture("resize",false);window.hide();hiddenBegins=item.begins.load();});
    QTimer::singleShot(2300*timeScale,&app,[&]{require(item.begins.load()-hiddenBegins<=1,"Hidden GPU demand pause");window.show();item.update();});
    QTimer::singleShot(3000*timeScale,&app,[&]{capture("restored",false);restored=true;item.textureWidth=7680;item.textureHeight=2160;if(publicVideo)window.resize(960,270);item.update();});
    QTimer::singleShot(4000*timeScale,&app,[&]{capture("large",false);item.clear=true;item.update();});
    QTimer::singleShot(4500*timeScale,&app,[&]{capture("clear",true);cleared=true;item.clear=false;item.textureWidth=3840;item.textureHeight=1080;item.update();});
    QTimer::singleShot(5200*timeScale,&app,[&]{capture("restart",false);ticker.stop();window.hide();window.releaseResources();});
    QTimer::singleShot(5600*timeScale,&app,[&] {
        int live=0,created=0,closed=0;texture_counts(&live,&created,&closed);
        std::printf("{\"live_sources\":%d,\"created_sources\":%d,\"closed_sources\":%d}\n",live,created,closed);
        require(live==0 && created==closed && created>=4,"Explicit native cleanup counts");
        std::printf("{\"diagnostic_swaps\":%d,\"generations\":%d,\"begins\":%d,\"ends\":%d,\"ticks\":%d}\n",swaps.load(),item.generations.load(),item.begins.load(),item.ends.load(),ticks);
        require(patterned && cleared && restored && swaps>30 && item.generations>=4,"Lifecycle assertions");
        std::printf("{\"passed\":true,\"render_begins\":%d,\"render_ends\":%d,\"qt_swaps\":%d,\"generations\":%d,\"public_video\":%s,\"scope\":\"standalone Qt native texture lifecycle; no live application fps claim\"}\n",item.begins.load(),item.ends.load(),swaps.load(),item.generations.load(),publicVideo?"true":"false");
        app.quit();
    });
    return app.exec();
}
