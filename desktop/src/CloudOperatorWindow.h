#pragma once

#include <QMainWindow>

class CloudLifecycleController;
class QLineEdit;
class QLabel;
class QPushButton;
class QProcess;
class QTextEdit;
class QWebEngineView;

class CloudOperatorWindow final : public QMainWindow
{
    Q_OBJECT
public:
    explicit CloudOperatorWindow(QWidget *parent = nullptr);

private:
    static QString findProjectRoot();
    void buildUi();
    void loadSettings();
    void saveSettings();
    bool validateCommon(bool requireImage = false);
    QStringList targetArguments() const;
    void runScript(const QString &title, const QString &script, const QStringList &arguments);
    void loadAdmin();
    void loginGoogle();
    void refreshGoogleIdentity();
    void loginAdminDashboard();
    bool confirmPhrase(const QString &title, const QString &message, const QString &phrase);

    CloudLifecycleController *m_controller = nullptr;
    QLineEdit *m_project = nullptr;
    QLineEdit *m_environment = nullptr;
    QLineEdit *m_region = nullptr;
    QLineEdit *m_zone = nullptr;
    QLineEdit *m_vm = nullptr;
    QLineEdit *m_sql = nullptr;
    QLineEdit *m_domain = nullptr;
    QLineEdit *m_image = nullptr;
    QLineEdit *m_terraformDir = nullptr;
    QLineEdit *m_varFile = nullptr;
    QLineEdit *m_archiveDir = nullptr;
    QLineEdit *m_archiveLabel = nullptr;
    QLabel *m_status = nullptr;
    QLabel *m_googleIdentity = nullptr;
    QPushButton *m_cancel = nullptr;
    QTextEdit *m_log = nullptr;
    QWebEngineView *m_web = nullptr;
    QProcess *m_identityProcess = nullptr;
    QProcess *m_adminTokenProcess = nullptr;
    bool m_adminLoginPending = false;
};
