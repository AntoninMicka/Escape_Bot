#include "CameraQrBridge.h"

CameraQrBridge::CameraQrBridge(QObject *parent)
    : QObject(parent)
{
}

bool CameraQrBridge::scanning() const
{
    return m_scanning;
}

void CameraQrBridge::setScanning(bool scanning)
{
    if (m_scanning == scanning) {
        return;
    }

    m_scanning = scanning;
    emit scanningChanged();
}

void CameraQrBridge::submitDebugQr(const QString &value)
{
    if (!value.trimmed().isEmpty()) {
        emit qrDetected(value.trimmed());
    }
}

