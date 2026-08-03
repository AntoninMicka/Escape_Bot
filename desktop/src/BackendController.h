#pragma once

#include <QObject>
#include <QProcess>

class BackendController final : public QObject
{
    Q_OBJECT

public:
    explicit BackendController(QObject *parent = nullptr);
    ~BackendController() override;

    [[nodiscard]] QString adminToken() const;
    [[nodiscard]] QString statusText() const;
    [[nodiscard]] bool running() const;
    [[nodiscard]] bool ready() const;
    [[nodiscard]] QString projectRoot() const;

public slots:
    void start();
    void restart();
    void stop();

signals:
    void stateChanged();
    void readyChanged(bool ready);
    void errorOccurred(const QString &message);

private:
    static QString findProjectRoot();
    static QString createAdminToken();
    QString findPython() const;
    void consumeOutput();
    void setStatus(const QString &status);

    QProcess m_process;
    QString m_projectRoot;
    QString m_adminToken;
    QString m_status;
    QByteArray m_outputBuffer;
    bool m_ready = false;
    bool m_stopping = false;
};

