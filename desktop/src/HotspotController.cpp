#include "HotspotController.h"

#include <QNetworkInterface>
#include <QOperatingSystemVersion>
#include <QStandardPaths>

namespace {
constexpr auto connectionName = "EscapeBot-AP";
}

HotspotController::HotspotController(QObject *parent)
    : QObject(parent)
{
    connect(&m_process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int exitCode, QProcess::ExitStatus exitStatus) {
        const QString standardOutput = QString::fromUtf8(m_process.readAllStandardOutput()).trimmed();
        const QString standardError = QString::fromUtf8(m_process.readAllStandardError()).trimmed();
        const bool success = exitStatus == QProcess::NormalExit && exitCode == 0;

        if (m_operation == Operation::Detect) {
            if (success) {
                QStringList networkManagerInterfaces;
                m_active = false;
                for (const QString &line : standardOutput.split('\n', Qt::SkipEmptyParts)) {
                    const QStringList fields = line.split(':');
                    if (fields.size() >= 2 && fields.at(1).trimmed() == QStringLiteral("wifi")) {
                        QString interfaceName = fields.at(0);
                        interfaceName.replace(QStringLiteral("\\:"), QStringLiteral(":"));
                        networkManagerInterfaces.append(interfaceName);
                        if (fields.size() >= 3 && fields.at(2).trimmed() == QString::fromLatin1(connectionName)) {
                            m_active = true;
                        }
                    }
                }
                if (!networkManagerInterfaces.isEmpty()) {
                    m_wifiInterfaces = networkManagerInterfaces;
                }
                m_nmcliAvailable = true;
                setStatus(m_wifiInterfaces.isEmpty()
                              ? tr("Nebyl nalezen Wi-Fi adaptér.")
                              : tr("Wi-Fi adaptér je připraven."));
            } else {
                m_nmcliAvailable = false;
                setStatus(tr("NetworkManager není dostupný: %1").arg(standardError));
            }
            m_operation = Operation::None;
            emit stateChanged();
            return;
        }

        if (m_operation == Operation::Start) {
            m_active = success;
            finishOperation(success,
                            success ? tr("Hotspot Escape Bot byl spuštěn.")
                                    : tr("Hotspot se nepodařilo spustit: %1").arg(standardError));
            return;
        }

        if (m_operation == Operation::Stop) {
            if (success) {
                m_active = false;
            }
            finishOperation(success,
                            success ? tr("Hotspot Escape Bot byl zastaven.")
                                    : tr("Hotspot se nepodařilo zastavit: %1").arg(standardError));
        }
    });

    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) {
            finishOperation(false, tr("Systémový síťový nástroj se nepodařilo spustit."));
        }
    });

    refresh();
}

QStringList HotspotController::wifiInterfaces() const { return m_wifiInterfaces; }
bool HotspotController::busy() const { return m_operation != Operation::None; }
bool HotspotController::active() const { return m_active; }
QString HotspotController::statusText() const { return m_status; }

bool HotspotController::hotspotSupported() const
{
#if defined(Q_OS_LINUX)
    return m_nmcliAvailable && !m_wifiInterfaces.isEmpty();
#else
    return false;
#endif
}

void HotspotController::refresh()
{
    if (busy()) {
        return;
    }

    m_wifiInterfaces.clear();
    const auto interfaces = QNetworkInterface::allInterfaces();
    for (const QNetworkInterface &networkInterface : interfaces) {
        if (networkInterface.type() == QNetworkInterface::Wifi
            && networkInterface.flags().testFlag(QNetworkInterface::IsUp)) {
            m_wifiInterfaces.append(networkInterface.name());
        }
    }

#if defined(Q_OS_LINUX)
    detectWithNetworkManager();
#else
    setStatus(m_wifiInterfaces.isEmpty()
                  ? tr("Nebyl nalezen aktivní Wi-Fi adaptér.")
                  : tr("Wi-Fi adaptér byl nalezen. Vytváření AP je zatím podporováno na Linuxu s NetworkManagerem."));
    emit stateChanged();
#endif
}

void HotspotController::detectWithNetworkManager()
{
    const QString nmcli = QStandardPaths::findExecutable(QStringLiteral("nmcli"));
    if (nmcli.isEmpty()) {
        m_nmcliAvailable = false;
        setStatus(tr("Wi-Fi lze detekovat, ale chybí nmcli/NetworkManager pro vytvoření AP."));
        emit stateChanged();
        return;
    }

    m_operation = Operation::Detect;
    setStatus(tr("Zjišťuji Wi-Fi adaptéry…"));
    emit stateChanged();
    m_process.start(nmcli, {QStringLiteral("-t"), QStringLiteral("-f"),
                            QStringLiteral("DEVICE,TYPE,CONNECTION"), QStringLiteral("device"), QStringLiteral("status")});
}

void HotspotController::startHotspot(const QString &interfaceName, const QString &ssid, const QString &password)
{
    if (busy()) {
        emit operationFinished(false, tr("Probíhá jiná síťová operace."));
        return;
    }
    if (!hotspotSupported() || !m_wifiInterfaces.contains(interfaceName)) {
        emit operationFinished(false, tr("Vybraný Wi-Fi adaptér nepodporuje dostupný AP backend."));
        return;
    }
    if (!validSsid(ssid)) {
        emit operationFinished(false, tr("Název Wi-Fi musí mít 1 až 32 bajtů v UTF-8."));
        return;
    }
    if (!validPassword(password)) {
        emit operationFinished(false, tr("Heslo Wi-Fi musí mít 8 až 63 znaků."));
        return;
    }

    m_operation = Operation::Start;
    setStatus(tr("Spouštím hotspot…"));
    emit stateChanged();
    m_process.start(QStandardPaths::findExecutable(QStringLiteral("nmcli")),
                    {QStringLiteral("--wait"), QStringLiteral("20"), QStringLiteral("device"),
                     QStringLiteral("wifi"), QStringLiteral("hotspot"), QStringLiteral("ifname"),
                     interfaceName, QStringLiteral("con-name"), QString::fromLatin1(connectionName),
                     QStringLiteral("ssid"), ssid, QStringLiteral("password"), password});
}

void HotspotController::stopHotspot()
{
    if (busy()) {
        emit operationFinished(false, tr("Probíhá jiná síťová operace."));
        return;
    }
    if (!m_nmcliAvailable) {
        emit operationFinished(false, tr("NetworkManager není dostupný."));
        return;
    }

    m_operation = Operation::Stop;
    setStatus(tr("Zastavuji hotspot…"));
    emit stateChanged();
    m_process.start(QStandardPaths::findExecutable(QStringLiteral("nmcli")),
                    {QStringLiteral("--wait"), QStringLiteral("15"), QStringLiteral("connection"),
                     QStringLiteral("down"), QString::fromLatin1(connectionName)});
}

void HotspotController::finishOperation(bool success, const QString &message)
{
    m_operation = Operation::None;
    setStatus(message);
    emit stateChanged();
    emit operationFinished(success, message);
}

void HotspotController::setStatus(const QString &status) { m_status = status; }

bool HotspotController::validSsid(const QString &ssid)
{
    const qsizetype bytes = ssid.trimmed().toUtf8().size();
    return bytes >= 1 && bytes <= 32;
}

bool HotspotController::validPassword(const QString &password)
{
    return password.size() >= 8 && password.size() <= 63;
}
