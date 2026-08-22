#pragma once

#include <QObject>
#include <QProcess>
#include <QQueue>

class CloudLifecycleController final : public QObject
{
    Q_OBJECT
public:
    struct Command { QString program; QStringList arguments; };
    explicit CloudLifecycleController(QString projectRoot, QObject *parent = nullptr);
    bool isBusy() const;
    QString projectRoot() const;
    void runOperation(const QString &name, const QList<Command> &commands);
    void runScript(const QString &name, const QString &relativePath, const QStringList &arguments);
    void cancel();

signals:
    void busyChanged(bool busy);
    void outputReady(const QString &text);
    void operationFinished(const QString &name, bool success);

private:
    void startNext();
    static QString displayCommand(const Command &command);
    QString m_projectRoot;
    QString m_operationName;
    QQueue<Command> m_commands;
    QProcess m_process;
};
