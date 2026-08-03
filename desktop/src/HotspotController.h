#pragma once

#include <QObject>
#include <QProcess>
#include <QStringList>

class HotspotController final : public QObject
{
    Q_OBJECT

public:
    explicit HotspotController(QObject *parent = nullptr);

    [[nodiscard]] QStringList wifiInterfaces() const;
    [[nodiscard]] bool hotspotSupported() const;
    [[nodiscard]] bool busy() const;
    [[nodiscard]] bool active() const;
    [[nodiscard]] QString statusText() const;

public slots:
    void refresh();
    void startHotspot(const QString &interfaceName, const QString &ssid, const QString &password);
    void stopHotspot();

signals:
    void stateChanged();
    void operationFinished(bool success, const QString &message);

private:
    enum class Operation { None, Detect, Start, Stop };

    void detectWithNetworkManager();
    void finishOperation(bool success, const QString &message);
    void setStatus(const QString &status);
    static bool validSsid(const QString &ssid);
    static bool validPassword(const QString &password);

    QProcess m_process;
    Operation m_operation = Operation::None;
    QStringList m_wifiInterfaces;
    bool m_nmcliAvailable = false;
    bool m_active = false;
    QString m_status;
};

