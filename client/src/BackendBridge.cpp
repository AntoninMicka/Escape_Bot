#include "BackendBridge.h"

#include <QAbstractSocket>
#include <QDateTime>
#include <QJsonDocument>
#include <QJsonObject>
#include <QJsonValue>
#include <QUrl>

BackendBridge::BackendBridge(QObject *parent)
    : QObject(parent)
{
    connect(&m_socket, &QWebSocket::connected, this, [this]() {
        setConnected(true);
        sendHello();
    });
    connect(&m_socket, &QWebSocket::disconnected, this, [this]() {
        setConnected(false);
    });
    connect(&m_socket, &QWebSocket::textMessageReceived, this, &BackendBridge::handleTextMessage);
#if QT_VERSION >= QT_VERSION_CHECK(6, 5, 0)
    connect(&m_socket, &QWebSocket::errorOccurred, this, [this](QAbstractSocket::SocketError) {
#else
    connect(&m_socket, QOverload<QAbstractSocket::SocketError>::of(&QWebSocket::error), this, [this](QAbstractSocket::SocketError) {
#endif
        emit errorOccurred(m_socket.errorString());
    });
}

bool BackendBridge::connected() const
{
    return m_connected;
}

void BackendBridge::connectToBackend()
{
    if (m_socket.state() == QAbstractSocket::ConnectedState
        || m_socket.state() == QAbstractSocket::ConnectingState) {
        return;
    }

    m_socket.open(QUrl(QStringLiteral("ws://127.0.0.1:8765")));
}

void BackendBridge::sendJson(const QString &type, const QVariantMap &payload)
{
    if (!m_connected) {
        emit errorOccurred(QStringLiteral("Backend neni pripojeny."));
        return;
    }

    QJsonObject message;
    message.insert(QStringLiteral("type"), type);
    message.insert(QStringLiteral("request_id"), QString::number(QDateTime::currentMSecsSinceEpoch()));
    message.insert(QStringLiteral("payload"), QJsonObject::fromVariantMap(payload));

    m_socket.sendTextMessage(QString::fromUtf8(QJsonDocument(message).toJson(QJsonDocument::Compact)));
}

void BackendBridge::setConnected(bool connected)
{
    if (m_connected == connected) {
        return;
    }

    m_connected = connected;
    emit connectedChanged();
}

void BackendBridge::sendHello()
{
    sendJson(QStringLiteral("client.hello"), {
        {QStringLiteral("client_name"), QStringLiteral("Escape Bot QML")},
        {QStringLiteral("protocol_version"), 1},
    });
}

void BackendBridge::handleTextMessage(const QString &message)
{
    const QJsonDocument document = QJsonDocument::fromJson(message.toUtf8());
    if (!document.isObject()) {
        emit errorOccurred(QStringLiteral("Backend poslal neplatny JSON."));
        return;
    }

    emit messageReceived(document.object().toVariantMap());
}
