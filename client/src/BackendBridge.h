#pragma once

#include <QObject>
#include <QVariantMap>
#include <QWebSocket>

class BackendBridge : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool connected READ connected NOTIFY connectedChanged)

public:
    explicit BackendBridge(QObject *parent = nullptr);

    bool connected() const;

    Q_INVOKABLE void connectToBackend();
    Q_INVOKABLE void sendJson(const QString &type, const QVariantMap &payload);

signals:
    void connectedChanged();
    void messageReceived(const QVariantMap &message);
    void errorOccurred(const QString &message);

private:
    void setConnected(bool connected);
    void sendHello();
    void handleTextMessage(const QString &message);

    QWebSocket m_socket;
    bool m_connected = false;
};
