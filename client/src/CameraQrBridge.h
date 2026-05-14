#pragma once

#include <QObject>
#include <QString>

class CameraQrBridge : public QObject
{
    Q_OBJECT
    Q_PROPERTY(bool scanning READ scanning WRITE setScanning NOTIFY scanningChanged)

public:
    explicit CameraQrBridge(QObject *parent = nullptr);

    bool scanning() const;
    void setScanning(bool scanning);

    Q_INVOKABLE void submitDebugQr(const QString &value);

signals:
    void scanningChanged();
    void qrDetected(const QString &value);

private:
    bool m_scanning = false;
};

