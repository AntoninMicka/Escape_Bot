#include <QGuiApplication>
#include <QQmlApplicationEngine>
#include <QQmlContext>
#include <QUrl>

#include "BackendBridge.h"
#include "CameraQrBridge.h"

int main(int argc, char *argv[])
{
    QGuiApplication app(argc, argv);

    CameraQrBridge cameraQrBridge;
    BackendBridge backendBridge;

    QQmlApplicationEngine engine;
    engine.rootContext()->setContextProperty("backendBridge", &backendBridge);
    engine.rootContext()->setContextProperty("cameraQrBridge", &cameraQrBridge);
    engine.load(QUrl(QStringLiteral("qrc:/EscapeBot/qml/Main.qml")));

    if (engine.rootObjects().isEmpty()) {
        return -1;
    }

    return app.exec();
}
