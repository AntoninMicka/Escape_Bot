#include "BackendController.h"

#include <QCoreApplication>
#include <QDir>
#include <QFileInfo>
#include <QProcessEnvironment>
#include <QRandomGenerator>
#include <QStandardPaths>

BackendController::BackendController(QObject *parent)
    : QObject(parent)
    , m_projectRoot(findProjectRoot())
    , m_adminToken(createAdminToken())
{
    connect(&m_process, &QProcess::started, this, [this]() {
        setStatus(tr("Backend se spouští…"));
        emit stateChanged();
    });
    connect(&m_process, &QProcess::readyReadStandardOutput, this, &BackendController::consumeOutput);
    connect(&m_process, &QProcess::readyReadStandardError, this, &BackendController::consumeOutput);
    connect(&m_process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int exitCode, QProcess::ExitStatus exitStatus) {
        consumeOutput();
        const bool expected = m_stopping;
        m_stopping = false;
        if (m_ready) {
            m_ready = false;
            emit readyChanged(false);
        }
        setStatus(expected ? tr("Backend byl zastaven.")
                           : tr("Backend skončil (kód %1, stav %2).")
                                 .arg(exitCode)
                                 .arg(exitStatus == QProcess::NormalExit ? tr("normální") : tr("havárie")));
        emit stateChanged();
        if (!expected) {
            emit errorOccurred(m_status);
        }
    });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) {
            setStatus(tr("Proces backendu nelze spustit."));
            emit stateChanged();
            emit errorOccurred(m_status);
        }
    });

    setStatus(m_projectRoot.isEmpty() ? tr("Kořen projektu Escape Bot nebyl nalezen.")
                                      : tr("Backend je připraven ke spuštění."));
}

BackendController::~BackendController()
{
    stop();
    if (m_process.state() != QProcess::NotRunning && !m_process.waitForFinished(3000)) {
        m_process.kill();
        m_process.waitForFinished(1000);
    }
}

QString BackendController::adminToken() const { return m_adminToken; }
QString BackendController::statusText() const { return m_status; }
bool BackendController::running() const { return m_process.state() != QProcess::NotRunning; }
bool BackendController::ready() const { return m_ready; }
QString BackendController::projectRoot() const { return m_projectRoot; }

void BackendController::start()
{
    if (running()) {
        return;
    }
    if (m_projectRoot.isEmpty()) {
        emit errorOccurred(tr("Nelze najít backend/escape_bot/server.py. Spusťte wrapper z projektového stromu."));
        return;
    }

    const QString python = findPython();
    if (python.isEmpty()) {
        emit errorOccurred(tr("Nebyl nalezen Python virtuálního prostředí ani systémový Python 3."));
        return;
    }

    m_ready = false;
    m_stopping = false;
    m_outputBuffer.clear();
    QProcessEnvironment environment = QProcessEnvironment::systemEnvironment();
    environment.insert(QStringLiteral("ESCAPEBOT_ADMIN_TOKEN"), m_adminToken);
    m_process.setProcessEnvironment(environment);
    m_process.setWorkingDirectory(QDir(m_projectRoot).filePath(QStringLiteral("backend")));
    m_process.setProgram(python);
    m_process.setArguments({QStringLiteral("-m"), QStringLiteral("escape_bot.server")});
    setStatus(tr("Spouštím lokální backend…"));
    emit stateChanged();
    m_process.start();
}

void BackendController::restart()
{
    if (!running()) {
        start();
        return;
    }
    m_stopping = true;
    m_process.terminate();
    if (!m_process.waitForFinished(3000)) {
        m_process.kill();
        m_process.waitForFinished(1000);
    }
    start();
}

void BackendController::stop()
{
    if (!running()) {
        return;
    }
    m_stopping = true;
    setStatus(tr("Zastavuji backend…"));
    emit stateChanged();
    m_process.terminate();
}

QString BackendController::findProjectRoot()
{
    const QString applicationDir = QCoreApplication::applicationDirPath();
    const QStringList candidates = {
        QDir::currentPath(), applicationDir,
        QDir(applicationDir).absoluteFilePath(QStringLiteral("..")),
        QDir(applicationDir).absoluteFilePath(QStringLiteral("../..")),
        QDir(applicationDir).absoluteFilePath(QStringLiteral("../../.."))
    };
    for (const QString &candidate : candidates) {
        const QString canonical = QDir(candidate).canonicalPath();
        if (!canonical.isEmpty()
            && QFileInfo::exists(QDir(canonical).filePath(QStringLiteral("backend/escape_bot/server.py")))) {
            return canonical;
        }
    }
    return {};
}

QString BackendController::createAdminToken()
{
    QByteArray token;
    token.reserve(64);
    for (int index = 0; index < 4; ++index) {
        const quint64 value = QRandomGenerator::system()->generate64();
        token.append(QByteArray::number(value, 16).rightJustified(16, '0'));
    }
    return QString::fromLatin1(token);
}

QString BackendController::findPython() const
{
#if defined(Q_OS_WIN)
    const QString virtualPython = QDir(m_projectRoot).filePath(QStringLiteral("backend/.venv/Scripts/python.exe"));
#else
    const QString virtualPython = QDir(m_projectRoot).filePath(QStringLiteral("backend/.venv/bin/python"));
#endif
    if (QFileInfo(virtualPython).isExecutable()) {
        return virtualPython;
    }
    QString python = QStandardPaths::findExecutable(QStringLiteral("python3"));
    if (python.isEmpty()) {
        python = QStandardPaths::findExecutable(QStringLiteral("python"));
    }
    return python;
}

void BackendController::consumeOutput()
{
    m_outputBuffer.append(m_process.readAllStandardOutput());
    m_outputBuffer.append(m_process.readAllStandardError());
    if (!m_ready && (m_outputBuffer.contains("Application startup complete")
                     || m_outputBuffer.contains("Uvicorn running on"))) {
        m_ready = true;
        setStatus(tr("Backend běží na https://localhost:8088."));
        emit stateChanged();
        emit readyChanged(true);
    }
    if (m_outputBuffer.size() > 32768) {
        m_outputBuffer = m_outputBuffer.right(16384);
    }
}

void BackendController::setStatus(const QString &status) { m_status = status; }

