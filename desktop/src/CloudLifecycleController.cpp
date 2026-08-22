#include "CloudLifecycleController.h"

#include <QDir>
#include <QFileInfo>

CloudLifecycleController::CloudLifecycleController(QString projectRoot, QObject *parent)
    : QObject(parent), m_projectRoot(std::move(projectRoot))
{
    m_process.setWorkingDirectory(m_projectRoot);
    m_process.setProcessChannelMode(QProcess::MergedChannels);
    connect(&m_process, &QProcess::readyReadStandardOutput, this, [this] {
        emit outputReady(QString::fromUtf8(m_process.readAllStandardOutput()));
    });
    connect(&m_process, &QProcess::errorOccurred, this, [this](QProcess::ProcessError error) {
        if (error == QProcess::FailedToStart) {
            emit outputReady(tr("Proces se nepodařilo spustit: %1\n").arg(m_process.errorString()));
            m_commands.clear();
            const QString name = m_operationName;
            m_operationName.clear();
            emit busyChanged(false);
            emit operationFinished(name, false);
        }
    });
    connect(&m_process, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int exitCode, QProcess::ExitStatus status) {
        const bool ok = status == QProcess::NormalExit && exitCode == 0;
        if (ok && !m_commands.isEmpty()) { startNext(); return; }
        if (!ok) m_commands.clear();
        const QString name = m_operationName;
        m_operationName.clear();
        emit busyChanged(false);
        emit operationFinished(name, ok);
    });
}

bool CloudLifecycleController::isBusy() const { return !m_operationName.isEmpty(); }
QString CloudLifecycleController::projectRoot() const { return m_projectRoot; }

void CloudLifecycleController::runOperation(const QString &name, const QList<Command> &commands)
{
    if (isBusy() || commands.isEmpty()) return;
    m_operationName = name;
    for (const Command &command : commands) m_commands.enqueue(command);
    emit busyChanged(true);
    emit outputReady(tr("\n=== %1 ===\n").arg(name));
    startNext();
}

void CloudLifecycleController::runScript(const QString &name, const QString &relativePath,
                                         const QStringList &arguments)
{
    const QString script = QDir(m_projectRoot).filePath(relativePath);
    if (!QFileInfo::exists(script)) {
        emit outputReady(tr("Skript neexistuje: %1\n").arg(script));
        emit operationFinished(name, false);
        return;
    }
    QStringList scriptArguments{script};
    scriptArguments.append(arguments);
    runOperation(name, {{QStringLiteral("bash"), scriptArguments}});
}

void CloudLifecycleController::cancel()
{
    if (!isBusy()) return;
    m_commands.clear();
    m_process.terminate();
}

void CloudLifecycleController::startNext()
{
    const Command command = m_commands.dequeue();
    emit outputReady(QStringLiteral("$ %1\n").arg(displayCommand(command)));
    m_process.start(command.program, command.arguments);
}

QString CloudLifecycleController::displayCommand(const Command &command)
{
    QStringList parts{command.program};
    for (QString argument : command.arguments) {
        argument.replace(QChar(39), QStringLiteral("'\\''"));
        parts << QStringLiteral("'%1'").arg(argument);
    }
    return parts.join(' ');
}
