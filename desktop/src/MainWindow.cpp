#include "MainWindow.h"

#include "BackendController.h"
#include "HotspotController.h"
#include "LocalAdminPage.h"

#include <QComboBox>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QSettings>
#include <QSplitter>
#include <QUrl>
#include <QVBoxLayout>
#include <QWebEngineView>
#include <QWebEngineScript>
#include <QWebEngineScriptCollection>
#include <QWidget>

MainWindow::MainWindow(QWidget *parent)
    : QMainWindow(parent)
    , m_hotspotController(new HotspotController(this))
    , m_backendController(new BackendController(this))
    , m_webView(new QWebEngineView(this))
    , m_urlEdit(new QLineEdit(this))
    , m_interfaceCombo(new QComboBox(this))
    , m_ssidEdit(new QLineEdit(QStringLiteral("EscapeBot-Hra"), this))
    , m_passwordEdit(new QLineEdit(this))
    , m_startButton(new QPushButton(tr("Spustit AP"), this))
    , m_stopButton(new QPushButton(tr("Zastavit AP"), this))
    , m_refreshButton(new QPushButton(tr("Obnovit adaptéry"), this))
    , m_networkStatus(new QLabel(this))
    , m_backendStatus(new QLabel(this))
    , m_restartBackendButton(new QPushButton(tr("Restartovat backend"), this))
{
    setWindowTitle(tr("Escape Bot – administrační stanice"));
    resize(1380, 860);

    QSettings settings;
    m_urlEdit->setText(settings.value(QStringLiteral("adminUrl"),
                                      QStringLiteral("https://localhost:8088/admin")).toString());
    m_passwordEdit->setEchoMode(QLineEdit::Password);
    m_passwordEdit->setPlaceholderText(tr("8–63 znaků; wrapper je neukládá"));
    m_networkStatus->setWordWrap(true);
    m_backendStatus->setWordWrap(true);

    auto *openButton = new QPushButton(tr("Otevřít admin"), this);
    auto *adminBar = new QHBoxLayout;
    adminBar->addWidget(new QLabel(tr("Admin URL:"), this));
    adminBar->addWidget(m_urlEdit, 1);
    adminBar->addWidget(openButton);

    auto *hotspotBox = new QGroupBox(tr("Lokální Wi-Fi AP"), this);
    auto *hotspotForm = new QFormLayout(hotspotBox);
    hotspotForm->addRow(tr("Wi-Fi adaptér:"), m_interfaceCombo);
    hotspotForm->addRow(tr("SSID:"), m_ssidEdit);
    hotspotForm->addRow(tr("Heslo:"), m_passwordEdit);

    auto *hotspotActions = new QHBoxLayout;
    hotspotActions->addWidget(m_startButton);
    hotspotActions->addWidget(m_stopButton);
    hotspotActions->addWidget(m_refreshButton);
    hotspotForm->addRow(hotspotActions);
    hotspotForm->addRow(tr("Stav:"), m_networkStatus);

    auto *backendBox = new QGroupBox(tr("Lokální backend"), this);
    auto *backendLayout = new QVBoxLayout(backendBox);
    backendLayout->addWidget(m_backendStatus);
    backendLayout->addWidget(m_restartBackendButton);

    auto *sidePanel = new QWidget(this);
    auto *sideLayout = new QVBoxLayout(sidePanel);
    sideLayout->addWidget(backendBox);
    sideLayout->addWidget(hotspotBox);
    auto *notice = new QLabel(
        tr("AP používá systémový NetworkManager. Spuštění může vyžádat potvrzení oprávnění. "
           "Wrapper heslo neukládá do svých nastavení; NetworkManager je uchová v chráněném profilu AP. "
           "Systémové HTTPS kontroly se nepodvrhují."), this);
    notice->setWordWrap(true);
    sideLayout->addWidget(notice);
    sideLayout->addStretch();

    m_webView->setPage(new LocalAdminPage(m_webView));
    installAdminTokenScript();
    auto *splitter = new QSplitter(this);
    splitter->addWidget(sidePanel);
    splitter->addWidget(m_webView);
    splitter->setStretchFactor(0, 0);
    splitter->setStretchFactor(1, 1);
    splitter->setSizes({330, 1050});

    auto *central = new QWidget(this);
    auto *centralLayout = new QVBoxLayout(central);
    centralLayout->addLayout(adminBar);
    centralLayout->addWidget(splitter, 1);
    setCentralWidget(central);

    connect(openButton, &QPushButton::clicked, this, &MainWindow::loadAdmin);
    connect(m_urlEdit, &QLineEdit::returnPressed, this, &MainWindow::loadAdmin);
    connect(m_startButton, &QPushButton::clicked, this, &MainWindow::startHotspot);
    connect(m_stopButton, &QPushButton::clicked, m_hotspotController, &HotspotController::stopHotspot);
    connect(m_refreshButton, &QPushButton::clicked, m_hotspotController, &HotspotController::refresh);
    connect(m_hotspotController, &HotspotController::stateChanged, this, &MainWindow::refreshHotspotUi);
    connect(m_hotspotController, &HotspotController::operationFinished,
            this, &MainWindow::showOperationResult);
    connect(m_backendController, &BackendController::stateChanged, this, &MainWindow::refreshBackendUi);
    connect(m_backendController, &BackendController::readyChanged, this, [this](bool ready) {
        if (ready) {
            loadAdmin();
        }
    });
    connect(m_backendController, &BackendController::errorOccurred, this, [this](const QString &message) {
        QMessageBox::warning(this, tr("Backend"), message);
    });
    connect(m_restartBackendButton, &QPushButton::clicked, m_backendController, &BackendController::restart);

    refreshHotspotUi();
    refreshBackendUi();
    m_backendController->start();
}

void MainWindow::refreshBackendUi()
{
    m_backendStatus->setText(m_backendController->statusText());
    m_restartBackendButton->setEnabled(!m_backendController->projectRoot().isEmpty());
}

void MainWindow::installAdminTokenScript()
{
    QWebEngineScript script;
    script.setName(QStringLiteral("EscapeBotLocalAdminLogin"));
    script.setInjectionPoint(QWebEngineScript::DocumentCreation);
    script.setWorldId(QWebEngineScript::MainWorld);
    script.setRunsOnSubFrames(false);
    script.setSourceCode(QStringLiteral(
        "if (location.hostname === 'localhost' || location.hostname === '127.0.0.1' || "
        "location.hostname === '[::1]' || location.hostname === '::1') {"
        "sessionStorage.setItem('escapeBotAdminToken', '%1');"
        "}").arg(m_backendController->adminToken()));
    m_webView->page()->scripts().insert(script);
}

void MainWindow::refreshHotspotUi()
{
    const QString selected = m_interfaceCombo->currentText();
    m_interfaceCombo->clear();
    m_interfaceCombo->addItems(m_hotspotController->wifiInterfaces());
    const int selectedIndex = m_interfaceCombo->findText(selected);
    if (selectedIndex >= 0) {
        m_interfaceCombo->setCurrentIndex(selectedIndex);
    }

    const bool available = m_hotspotController->hotspotSupported();
    const bool busy = m_hotspotController->busy();
    m_startButton->setEnabled(available && !busy && !m_hotspotController->active());
    m_stopButton->setEnabled(available && !busy && m_hotspotController->active());
    m_refreshButton->setEnabled(!busy);
    m_interfaceCombo->setEnabled(available && !busy && !m_hotspotController->active());
    m_networkStatus->setText(m_hotspotController->statusText());
}

void MainWindow::loadAdmin()
{
    QUrl url = QUrl::fromUserInput(m_urlEdit->text().trimmed());
    if (!url.isValid() || url.host().isEmpty()) {
        QMessageBox::warning(this, tr("Neplatná adresa"), tr("Zadejte platnou URL administračního rozhraní."));
        return;
    }
    QSettings settings;
    settings.setValue(QStringLiteral("adminUrl"), url.toString());
    m_webView->load(url);
}

void MainWindow::startHotspot()
{
    m_hotspotController->startHotspot(m_interfaceCombo->currentText(),
                                      m_ssidEdit->text().trimmed(), m_passwordEdit->text());
}

void MainWindow::showOperationResult(bool success, const QString &message)
{
    if (!success) {
        QMessageBox::warning(this, tr("Síťová operace selhala"), message);
    }
}
