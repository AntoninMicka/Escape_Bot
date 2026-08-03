#pragma once

#include <QMainWindow>

class HotspotController;
class BackendController;
class QComboBox;
class QLabel;
class QLineEdit;
class QPushButton;
class QWebEngineView;

class MainWindow final : public QMainWindow
{
    Q_OBJECT

public:
    explicit MainWindow(QWidget *parent = nullptr);

private slots:
    void refreshHotspotUi();
    void loadAdmin();
    void startHotspot();
    void showOperationResult(bool success, const QString &message);
    void refreshBackendUi();
    void installAdminTokenScript();

private:
    HotspotController *m_hotspotController;
    BackendController *m_backendController;
    QWebEngineView *m_webView;
    QLineEdit *m_urlEdit;
    QComboBox *m_interfaceCombo;
    QLineEdit *m_ssidEdit;
    QLineEdit *m_passwordEdit;
    QPushButton *m_startButton;
    QPushButton *m_stopButton;
    QPushButton *m_refreshButton;
    QLabel *m_networkStatus;
    QLabel *m_backendStatus;
    QPushButton *m_restartBackendButton;
};
