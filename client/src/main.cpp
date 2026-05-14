#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>

#include "CameraQrBridge.h"

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);

    CameraQrBridge cameraQrBridge;

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("cameraQrBridge", &cameraQrBridge);
    engine.loadFromModule("EscapeBot", "Main");

    if (engine.rootObjects().isEmpty()) {
        return -1;
    }

    return app.exec();
}

