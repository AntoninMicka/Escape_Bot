#include "CloudOperatorWindow.h"
#include "CloudAdminPage.h"
#include "CloudLifecycleController.h"

#include <QCoreApplication>
#include <QDate>
#include <QDateTime>
#include <QDir>
#include <QFileDialog>
#include <QFileInfo>
#include <QFormLayout>
#include <QGroupBox>
#include <QHBoxLayout>
#include <QInputDialog>
#include <QJsonDocument>
#include <QJsonObject>
#include <QLabel>
#include <QLineEdit>
#include <QMessageBox>
#include <QPushButton>
#include <QProcess>
#include <QRegularExpression>
#include <QScrollArea>
#include <QSettings>
#include <QSaveFile>
#include <QSplitter>
#include <QStandardPaths>
#include <QTextEdit>
#include <QUrl>
#include <QVBoxLayout>
#include <QWebEngineView>
#include <QWebEnginePage>

CloudOperatorWindow::CloudOperatorWindow(QWidget *parent) : QMainWindow(parent)
{
    m_controller = new CloudLifecycleController(findProjectRoot(), this);
    buildUi();
    loadSettings();
    m_identityProcess = new QProcess(this);
    m_adminTokenProcess = new QProcess(this);
    m_configProcess = new QProcess(this);
    connect(m_controller, &CloudLifecycleController::outputReady, m_log, &QTextEdit::insertPlainText);
    connect(m_controller, &CloudLifecycleController::busyChanged, this, [this](bool busy) {
        m_cancel->setEnabled(busy);
        m_status->setText(busy ? tr("Probíhá operace…") : tr("Připraveno"));
    });
    connect(m_controller, &CloudLifecycleController::operationFinished, this,
            [this](const QString &name, bool success) {
        m_status->setText(success ? tr("Dokončeno: %1").arg(name) : tr("Chyba: %1").arg(name));
        m_log->append(success ? tr("✓ Operace dokončena.") : tr("✗ Operace selhala."));
        if (name == tr("Přihlášení Google účtu")) refreshGoogleIdentity();
        if (success && (name == tr("Kompletní příprava prostředí") ||
                        name == tr("Příprava ostrého provozu")))
            loginAdminDashboard();
    });
    connect(m_identityProcess, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int exitCode, QProcess::ExitStatus status) {
        const QString account = QString::fromUtf8(m_identityProcess->readAllStandardOutput()).trimmed();
        if (status == QProcess::NormalExit && exitCode == 0 && !account.isEmpty())
            m_googleIdentity->setText(tr("Přihlášen: %1").arg(account));
        else
            m_googleIdentity->setText(tr("Google účet není přihlášen"));
    });
    connect(m_adminTokenProcess, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int exitCode, QProcess::ExitStatus status) {
        QString token = QString::fromUtf8(m_adminTokenProcess->readAllStandardOutput()).trimmed();
        if (status != QProcess::NormalExit || exitCode != 0 || token.isEmpty() ||
            !QRegularExpression("^[a-f0-9]{64}$").match(token).hasMatch()) {
            token.clear();
            QMessageBox::warning(this, tr("Admin přihlášení"),
                                 tr("Admin token se nepodařilo bezpečně načíst ze Secret Manageru."));
            return;
        }
        QString domain = m_domain->text().trimmed();
        if (!domain.startsWith("https://")) domain.prepend("https://");
        QUrl url(domain);
        url.setPath("/admin");
        m_adminLoginPending = true;
        m_web->setProperty("pendingAdminToken", token);
        token.fill(QChar(0));
        m_web->setUrl(url);
    });
    connect(m_configProcess, qOverload<int, QProcess::ExitStatus>(&QProcess::finished), this,
            [this](int exitCode, QProcess::ExitStatus status) {
        const QByteArray output = m_configProcess->readAllStandardOutput();
        const QString mode = m_configProcessMode;
        m_configProcessMode.clear();
        if (status != QProcess::NormalExit || exitCode != 0) {
            QMessageBox::warning(this, tr("Cloud konfigurace"),
                tr("Operace se nezdařila:\n%1").arg(QString::fromUtf8(m_configProcess->readAllStandardError())));
            return;
        }
        if (mode == QStringLiteral("suggest")) {
            applySuggestedValues(QString::fromUtf8(output).trimmed());
            return;
        }
        QJsonParseError error;
        const QJsonDocument document = QJsonDocument::fromJson(output, &error);
        if (error.error != QJsonParseError::NoError || !document.isObject()) {
            QMessageBox::warning(this, tr("Cloud konfigurace"), tr("Terraform outputs nemají očekávaný JSON formát."));
            return;
        }
        const QJsonObject values = document.object();
        auto value = [&values](const QString &name) { return values.value(name).toObject().value("value").toString(); };
        m_project->setText(value("project_id"));
        m_environment->setText(value("environment"));
        m_region->setText(value("region"));
        m_zone->setText(value("vm_zone"));
        m_vm->setText(value("vm_name"));
        m_domain->setText(value("domain"));
        m_image->setText(value("initial_image"));
        saveSettings();
        m_status->setText(tr("Existující prostředí načteno ze vzdáleného state"));
    });
    connect(m_web, &QWebEngineView::loadFinished, this, [this](bool success) {
        if (!success || !m_adminLoginPending) return;
        m_adminLoginPending = false;
        QString token = m_web->property("pendingAdminToken").toString();
        m_web->setProperty("pendingAdminToken", QVariant());
        const QString expectedHost = QUrl(m_web->url()).host();
        if (expectedHost.isEmpty() || m_web->url().scheme() != QStringLiteral("https")) return;
        const QString script = QStringLiteral(
            "if (location.protocol === 'https:' && location.hostname === '%1') {"
            "sessionStorage.setItem('escapeBotAdminToken', '%2'); location.reload(); }")
            .arg(expectedHost, token);
        token.fill(QChar(0));
        m_web->page()->runJavaScript(script);
    });
    refreshGoogleIdentity();
    setWindowTitle(tr("Escape Bot Cloud Operator"));
    resize(1500, 900);
}

QString CloudOperatorWindow::findProjectRoot()
{
    const QStringList starts{QDir::currentPath(), QCoreApplication::applicationDirPath()};
    for (const QString &start : starts) {
        QDir dir(start);
        for (int i = 0; i < 8; ++i) {
            if (QFileInfo::exists(dir.filePath("deploy/gcp/deploy.sh")) &&
                QFileInfo::exists(dir.filePath("infra/terraform/main.tf")))
                return dir.absolutePath();
            if (!dir.cdUp()) break;
        }
    }
    return QDir::currentPath();
}

void CloudOperatorWindow::buildUi()
{
    auto *root = new QSplitter(this);
    auto *left = new QWidget(root);
    auto *leftLayout = new QVBoxLayout(left);
    auto *quickBox = new QGroupBox(tr("Rychlé ovládání krátkodobého provozu"), left);
    auto *quick = new QVBoxLayout(quickBox);
    m_googleIdentity = new QLabel(tr("Kontroluji Google účet…"));
    auto *googleLogin = new QPushButton(tr("Přihlásit Google účet"));
    auto *prepare = new QPushButton(tr("Připravit testovací prostředí"));
    auto *deployFix = new QPushButton(tr("Nasadit opravu"));
    auto *prepareLive = new QPushButton(tr("Připravit ostrý provoz"));
    auto *quickPause = new QPushButton(tr("Pozastavit / ušetřit náklady"));
    auto *quickResume = new QPushButton(tr("Obnovit prostředí"));
    auto *finish = new QPushButton(tr("Stáhnout výsledky a odstranit prostředí"));
    quick->addWidget(m_googleIdentity);
    quick->addWidget(googleLogin);
    quick->addWidget(prepare);
    quick->addWidget(deployFix);
    quick->addWidget(prepareLive);
    quick->addWidget(quickPause);
    quick->addWidget(quickResume);
    quick->addWidget(finish);
    connect(googleLogin, &QPushButton::clicked, this, &CloudOperatorWindow::loginGoogle);
    connect(prepare, &QPushButton::clicked, this, [this] {
        if (!validateCommon(true)) return;
        if (!writeShortRunVarFile()) return;
        if (QMessageBox::question(this, tr("Připravit prostředí"),
            tr("V projektu %1 budou vytvořeny placené prostředky a automatická tajemství. Pokračovat?")
                .arg(m_project->text())) != QMessageBox::Yes) return;
        runScript(tr("Kompletní příprava prostředí"), "deploy/gcp/prepare-short-run.sh",
                  targetArguments() + QStringList{
                    "--region=" + m_region->text(), "--environment=" + m_environment->text(),
                    "--state-bucket=" + m_stateBucket->text(),
                    "--terraform-dir=" + m_terraformDir->text(), "--var-file=" + m_varFile->text(),
                    "--image=" + m_image->text()});
    });
    connect(deployFix, &QPushButton::clicked, this, [this] {
        if (!validateCommon(true) || !writeShortRunVarFile()) return;
        const QString deployScript = QDir(m_controller->projectRoot()).filePath("deploy/gcp/deploy.sh");
        m_controller->runOperation(tr("Nasazení opravy"), {
            {"bash", QStringList{deployScript} + targetArguments() + QStringList{"--image=" + m_image->text()}},
            {"gcloud", {"storage", "cp", m_varFile->text(),
                        QStringLiteral("gs://%1/escape-bot/operator-config/%2.tfvars")
                            .arg(m_stateBucket->text(), m_environment->text())}}
        });
    });
    connect(prepareLive, &QPushButton::clicked, this, [this] {
        if (!validateCommon() || !confirmPhrase(tr("Příprava ostrého provozu"),
            tr("Testovací data budou archivována a herní stav resetován."), "OSTRY-START")) return;
        runScript(tr("Příprava ostrého provozu"), "deploy/gcp/event-lifecycle.sh",
                  targetArguments() + QStringList{"--action=reset", "--label=pre-event"});
    });
    connect(quickPause, &QPushButton::clicked, this, [this] {
        if (!validateCommon()) return;
        runScript(tr("Pozastavení"), "deploy/gcp/pause-short-run.sh",
                  {m_project->text(), m_zone->text(), m_vm->text()});
    });
    connect(quickResume, &QPushButton::clicked, this, [this] {
        if (!validateCommon()) return;
        runScript(tr("Obnovení"), "deploy/gcp/resume-short-run.sh",
                  {m_project->text(), m_zone->text(), m_vm->text()});
    });
    connect(finish, &QPushButton::clicked, this, [this] {
        if (!validateCommon() || !confirmPhrase(tr("Ukončení krátkodobého provozu"),
            tr("Výsledky budou archivovány a po stažení bude infrastruktura nevratně odstraněna."),
            "UKONCIT-A-SMAZAT")) return;
        QDir().mkpath(m_archiveDir->text());
        const QString archiveScript = QDir(m_controller->projectRoot()).filePath("deploy/gcp/event-lifecycle.sh");
        const QString collectScript = QDir(m_controller->projectRoot()).filePath("deploy/gcp/collect-event-archives.sh");
        const QString destroyScript = QDir(m_controller->projectRoot()).filePath("deploy/gcp/destroy-short-run.sh");
        m_controller->runOperation(tr("Archivace, stažení a odstranění"), {
            {"bash", QStringList{archiveScript} + targetArguments() + QStringList{"--action=archive", "--label=final"}},
            {"bash", {collectScript, m_project->text(), m_zone->text(), m_vm->text(), m_archiveDir->text()}},
            {"bash", {destroyScript, "--terraform-dir=" + m_terraformDir->text(),
                      "--var-file=" + m_varFile->text(), "--archive-dir=" + m_archiveDir->text(),
                      "--workspace=" + m_environment->text(), "--state-bucket=" + m_stateBucket->text(),
                      "--confirm-destroy=DESTROY-SHORT-RUN"}}
        });
    });
    auto *configBox = new QGroupBox(tr("Cloud konfigurace"), left);
    auto *form = new QFormLayout(configBox);
    auto addField = [form](const QString &label, QLineEdit *&field) {
        field = new QLineEdit;
        form->addRow(label, field);
    };
    addField(tr("GCP projekt"), m_project);
    addField(tr("Prostředí / workspace"), m_environment);
    addField(tr("GCS bucket pro state"), m_stateBucket);
    addField(tr("Region"), m_region);
    addField(tr("Zóna"), m_zone);
    addField(tr("VM"), m_vm);
    addField(tr("Doména"), m_domain);
    addField(tr("Image digest"), m_image);
    addField(tr("Terraform adresář"), m_terraformDir);
    addField(tr("Terraform var-file"), m_varFile);
    addField(tr("Lokální archivy"), m_archiveDir);
    addField(tr("Označení archivu"), m_archiveLabel);

    auto *configButtons = new QHBoxLayout;
    auto *defaults = new QPushButton(tr("Navrhnout povinné hodnoty"));
    auto *loadExisting = new QPushButton(tr("Načíst existující prostředí"));
    auto *save = new QPushButton(tr("Uložit konfiguraci"));
    configButtons->addWidget(defaults);
    configButtons->addWidget(loadExisting);
    configButtons->addWidget(save);
    form->addRow(configButtons);
    connect(defaults, &QPushButton::clicked, this, &CloudOperatorWindow::suggestRequiredValues);
    connect(loadExisting, &QPushButton::clicked, this, &CloudOperatorWindow::loadRemoteConfiguration);
    connect(save, &QPushButton::clicked, this, &CloudOperatorWindow::saveSettings);

    auto *lifeBox = new QGroupBox(tr("Pokročilé jednotlivé operace"), left);
    lifeBox->setCheckable(true);
    lifeBox->setChecked(false);
    auto *life = new QVBoxLayout(lifeBox);
    auto addAction = [life](const QString &text) { auto *b = new QPushButton(text); life->addWidget(b); return b; };
    auto *prereq = addAction(tr("1. Ověřit nástroje a přihlášení"));
    auto *provision = addAction(tr("2. Vytvořit / aktualizovat infrastrukturu"));
    auto *secrets = addAction(tr("3. Vytvořit cloudová tajemství"));
    auto *deploy = addAction(tr("4. Nasadit novou verzi"));
    auto *pause = addAction(tr("Pozastavit kvůli úspoře"));
    auto *resume = addAction(tr("Obnovit prostředí"));
    auto *archive = addAction(tr("Archivovat stav hry"));
    auto *reset = addAction(tr("Resetovat před ostrým během"));
    auto *collect = addAction(tr("Stáhnout archivy"));
    auto *destroy = addAction(tr("Finálně odstranit infrastrukturu"));
    m_cancel = addAction(tr("Zrušit probíhající operaci"));
    m_cancel->setEnabled(false);
    m_status = new QLabel(tr("Připraveno"));
    life->addWidget(m_status);

    connect(prereq, &QPushButton::clicked, this, [this] {
        m_controller->runOperation(tr("Kontrola nástrojů"), {
            {"gcloud", {"auth", "list", "--filter=status:ACTIVE", "--format=value(account)"}},
            {"terraform", {"version"}}, {"docker", {"version", "--format", "{{.Client.Version}}"}}
        });
    });
    connect(provision, &QPushButton::clicked, this, [this] {
        if (!validateCommon(true) || !writeShortRunVarFile()) return;
        if (QMessageBox::question(this, tr("Vytvořit infrastrukturu"),
                tr("Terraform může vytvořit placené prostředky v projektu %1. Pokračovat?").arg(m_project->text())) != QMessageBox::Yes) return;
        const QString root = m_controller->projectRoot();
        m_controller->runOperation(tr("Provisioning"), {
            {"bash", {QDir(root).filePath("deploy/gcp/bootstrap-state-bucket.sh"),
                      m_project->text(), m_region->text(), m_stateBucket->text()}},
            {"bash", {QDir(root).filePath("deploy/gcp/provision-short-run.sh"),
                      "--terraform-dir=" + m_terraformDir->text(), "--var-file=" + m_varFile->text(),
                      "--workspace=" + m_environment->text(), "--state-bucket=" + m_stateBucket->text()}}
        });
    });
    connect(secrets, &QPushButton::clicked, this, [this] {
        if (!validateCommon()) return;
        const QString prefix = QStringLiteral("escape-bot-%1").arg(m_environment->text());
        runScript(tr("Admin tajemství"), "deploy/gcp/configure-admin-secret.sh",
                  {m_project->text(), prefix + "-admin-token"});
    });
    connect(deploy, &QPushButton::clicked, this, [this] {
        if (!validateCommon(true) || !writeShortRunVarFile()) return;
        const QString script = QDir(m_controller->projectRoot()).filePath("deploy/gcp/deploy.sh");
        m_controller->runOperation(tr("Deploy"), {
            {"bash", QStringList{script} + targetArguments() + QStringList{"--image=" + m_image->text()}},
            {"gcloud", {"storage", "cp", m_varFile->text(),
                        QStringLiteral("gs://%1/escape-bot/operator-config/%2.tfvars")
                            .arg(m_stateBucket->text(), m_environment->text())}}
        });
    });
    connect(pause, &QPushButton::clicked, this, [this] {
        if (!validateCommon()) return;
        runScript(tr("Pozastavení"), "deploy/gcp/pause-short-run.sh",
                  {m_project->text(), m_zone->text(), m_vm->text()});
    });
    connect(resume, &QPushButton::clicked, this, [this] {
        if (!validateCommon()) return;
        runScript(tr("Obnovení"), "deploy/gcp/resume-short-run.sh",
                  {m_project->text(), m_zone->text(), m_vm->text()});
    });
    connect(archive, &QPushButton::clicked, this, [this] {
        if (!validateCommon()) return;
        runScript(tr("Archivace"), "deploy/gcp/event-lifecycle.sh", targetArguments() +
                  QStringList{"--action=archive", "--label=" + m_archiveLabel->text()});
    });
    connect(reset, &QPushButton::clicked, this, [this] {
        if (!validateCommon() || !confirmPhrase(tr("Reset dat"), tr("Reset odstraní aktuální herní data."), "RESET")) return;
        runScript(tr("Reset hry"), "deploy/gcp/event-lifecycle.sh", targetArguments() + QStringList{"--action=reset"});
    });
    connect(collect, &QPushButton::clicked, this, [this] {
        if (!validateCommon()) return;
        QDir().mkpath(m_archiveDir->text());
        runScript(tr("Stažení archivů"), "deploy/gcp/collect-event-archives.sh",
                  {m_project->text(), m_zone->text(), m_vm->text(), m_archiveDir->text()});
    });
    connect(destroy, &QPushButton::clicked, this, [this] {
        if (!validateCommon() || !confirmPhrase(tr("Odstranění infrastruktury"),
            tr("Tento krok nevratně odstraní krátkodobou cloudovou infrastrukturu."), "DESTROY-SHORT-RUN")) return;
        runScript(tr("Odstranění infrastruktury"), "deploy/gcp/destroy-short-run.sh",
                  {"--terraform-dir=" + m_terraformDir->text(), "--var-file=" + m_varFile->text(),
                   "--archive-dir=" + m_archiveDir->text(), "--workspace=" + m_environment->text(),
                   "--state-bucket=" + m_stateBucket->text(),
                   "--confirm-destroy=DESTROY-SHORT-RUN"});
    });
    connect(m_cancel, &QPushButton::clicked, m_controller, &CloudLifecycleController::cancel);

    m_log = new QTextEdit(left);
    m_log->setReadOnly(true);
    m_log->setPlaceholderText(tr("Výstup operací…"));
    leftLayout->addWidget(quickBox);
    leftLayout->addWidget(configBox);
    leftLayout->addWidget(lifeBox);
    leftLayout->addWidget(m_log, 1);

    auto *right = new QWidget(root);
    auto *rightLayout = new QVBoxLayout(right);
    auto *webButtons = new QHBoxLayout;
    auto *load = new QPushButton(tr("Automaticky přihlásit admin dashboard"));
    auto *reload = new QPushButton(tr("Obnovit"));
    webButtons->addWidget(load);
    webButtons->addWidget(reload);
    webButtons->addStretch();
    m_web = new QWebEngineView(right);
    m_web->setPage(new CloudAdminPage(m_web));
    rightLayout->addLayout(webButtons);
    rightLayout->addWidget(m_web, 1);
    connect(load, &QPushButton::clicked, this, &CloudOperatorWindow::loginAdminDashboard);
    connect(reload, &QPushButton::clicked, m_web, &QWebEngineView::reload);
    root->addWidget(left);
    root->addWidget(right);
    root->setStretchFactor(0, 0);
    root->setStretchFactor(1, 1);
    setCentralWidget(root);
}

void CloudOperatorWindow::loadSettings()
{
    QSettings s;
    const QString root = m_controller->projectRoot();
    m_project->setText(s.value("cloud/project").toString());
    m_environment->setText(s.value("cloud/environment", "event-2026").toString());
    m_stateBucket->setText(s.value("cloud/stateBucket").toString());
    m_region->setText(s.value("cloud/region", "europe-west3").toString());
    m_zone->setText(s.value("cloud/zone", "europe-west3-a").toString());
    m_vm->setText(s.value("cloud/vm", "escape-bot-event-2026-vm").toString());
    m_domain->setText(s.value("cloud/domain").toString());
    m_image->setText(s.value("cloud/image").toString());
    m_terraformDir->setText(s.value("cloud/terraformDir", QDir(root).filePath("infra/terraform")).toString());
    m_varFile->setText(s.value("cloud/varFile", QDir(root).filePath("infra/terraform/short-run.tfvars")).toString());
    m_archiveDir->setText(s.value("cloud/archiveDir", QDir(root).filePath("archives")).toString());
    m_archiveLabel->setText(QDateTime::currentDateTime().toString("yyyyMMdd-HHmm"));
}

void CloudOperatorWindow::saveSettings()
{
    QSettings s;
    s.setValue("cloud/project", m_project->text().trimmed());
    s.setValue("cloud/environment", m_environment->text().trimmed());
    s.setValue("cloud/stateBucket", m_stateBucket->text().trimmed());
    s.setValue("cloud/region", m_region->text().trimmed());
    s.setValue("cloud/zone", m_zone->text().trimmed());
    s.setValue("cloud/vm", m_vm->text().trimmed());
    s.setValue("cloud/domain", m_domain->text().trimmed());
    s.setValue("cloud/image", m_image->text().trimmed());
    s.setValue("cloud/terraformDir", m_terraformDir->text().trimmed());
    s.setValue("cloud/varFile", m_varFile->text().trimmed());
    s.setValue("cloud/archiveDir", m_archiveDir->text().trimmed());
    m_status->setText(tr("Konfigurace uložena"));
}

bool CloudOperatorWindow::validateCommon(bool requireImage)
{
    const QList<QLineEdit *> required{m_project, m_environment, m_stateBucket, m_region, m_zone, m_vm};
    for (QLineEdit *field : required) if (field->text().trimmed().isEmpty()) {
        QMessageBox::warning(this, tr("Neúplná konfigurace"), tr("Vyplňte projekt, prostředí, state bucket, region, zónu a VM.")); return false;
    }
    if (m_controller->isBusy()) { QMessageBox::information(this, tr("Operace probíhá"), tr("Nejprve dokončete nebo zrušte aktuální operaci.")); return false; }
    if (requireImage && !QRegularExpression("@sha256:[a-f0-9]{64}$").match(m_image->text()).hasMatch()) {
        QMessageBox::warning(this, tr("Neplatný image"), tr("Deploy vyžaduje image zakončený neměnným SHA-256 digestem.")); return false;
    }
    if (requireImage && m_domain->text().trimmed().isEmpty()) {
        QMessageBox::warning(this, tr("Chybí doména"), tr("Pro přípravu prostředí vyplňte veřejnou doménu.")); return false;
    }
    saveSettings();
    return true;
}

QStringList CloudOperatorWindow::targetArguments() const
{
    return {"--project=" + m_project->text(), "--zone=" + m_zone->text(), "--vm=" + m_vm->text()};
}

void CloudOperatorWindow::runScript(const QString &title, const QString &script, const QStringList &arguments)
{
    m_controller->runScript(title, script, arguments);
}

void CloudOperatorWindow::loadAdmin()
{
    QString domain = m_domain->text().trimmed();
    if (domain.isEmpty()) { QMessageBox::warning(this, tr("Chybí doména"), tr("Vyplňte veřejnou doménu aplikace.")); return; }
    if (!domain.startsWith("https://")) domain.prepend("https://");
    QUrl url(domain);
    url.setPath("/admin");
    m_web->setUrl(url);
}

void CloudOperatorWindow::loginGoogle()
{
    if (m_controller->isBusy()) return;
    m_controller->runOperation(tr("Přihlášení Google účtu"), {
        {"gcloud", {"auth", "login", "--update-adc"}}
    });
}

void CloudOperatorWindow::refreshGoogleIdentity()
{
    if (!m_identityProcess || m_identityProcess->state() != QProcess::NotRunning) return;
    m_googleIdentity->setText(tr("Kontroluji Google účet…"));
    m_identityProcess->start(QStringLiteral("gcloud"),
                             {"auth", "list", "--filter=status:ACTIVE", "--format=value(account)"});
}

void CloudOperatorWindow::loginAdminDashboard()
{
    if (m_domain->text().trimmed().isEmpty() || m_project->text().trimmed().isEmpty() ||
        m_environment->text().trimmed().isEmpty()) {
        QMessageBox::warning(this, tr("Neúplná konfigurace"),
                             tr("Pro admin dashboard vyplňte projekt, prostředí a doménu."));
        return;
    }
    if (m_adminTokenProcess->state() != QProcess::NotRunning) return;
    const QString secret = QStringLiteral("escape-bot-%1-admin-token").arg(m_environment->text().trimmed());
    m_adminTokenProcess->setProcessChannelMode(QProcess::SeparateChannels);
    m_adminTokenProcess->start(QStringLiteral("gcloud"),
        {"secrets", "versions", "access", "latest", "--secret=" + secret,
         "--project=" + m_project->text().trimmed()});
}

void CloudOperatorWindow::suggestRequiredValues()
{
    if (m_configProcess->state() != QProcess::NotRunning) return;
    const QString project = m_project->text().trimmed();
    if (!project.isEmpty()) {
        applySuggestedValues(project);
        return;
    }
    m_configProcessMode = QStringLiteral("suggest");
    m_configProcess->start(QStringLiteral("gcloud"), {"config", "get-value", "project"});
}

void CloudOperatorWindow::applySuggestedValues(const QString &projectId)
{
    if (projectId.isEmpty() || projectId == QStringLiteral("(unset)")) {
        QMessageBox::warning(this, tr("Návrh konfigurace"),
                             tr("Google Cloud nemá nastavený aktivní projekt. Vyplňte jeho ID ručně."));
        return;
    }
    m_project->setText(projectId);
    if (m_environment->text().trimmed().isEmpty())
        m_environment->setText(QStringLiteral("event-%1").arg(QDate::currentDate().year()));
    if (m_region->text().trimmed().isEmpty()) m_region->setText(QStringLiteral("europe-west3"));
    if (m_zone->text().trimmed().isEmpty()) m_zone->setText(m_region->text() + QStringLiteral("-a"));
    const QString environment = m_environment->text().trimmed();
    m_vm->setText(QStringLiteral("escape-bot-%1-vm").arg(environment));
    m_stateBucket->setText(QStringLiteral("%1-escape-bot-tfstate").arg(projectId));
    const QString root = m_controller->projectRoot();
    if (m_terraformDir->text().trimmed().isEmpty()) m_terraformDir->setText(QDir(root).filePath("infra/terraform"));
    if (m_varFile->text().trimmed().isEmpty()) m_varFile->setText(QDir(root).filePath("infra/terraform/short-run.tfvars"));
    if (m_archiveDir->text().trimmed().isEmpty()) m_archiveDir->setText(QDir(root).filePath("archives"));
    saveSettings();
    QStringList missing;
    if (m_domain->text().trimmed().isEmpty()) missing << tr("veřejná doména");
    if (!QRegularExpression("@sha256:[a-f0-9]{64}$").match(m_image->text()).hasMatch()) missing << tr("image digest");
    m_status->setText(missing.isEmpty() ? tr("Povinné hodnoty jsou připravené")
                                       : tr("Doplňte ještě: %1").arg(missing.join(", ")));
}

void CloudOperatorWindow::loadRemoteConfiguration()
{
    if (m_configProcess->state() != QProcess::NotRunning || m_controller->isBusy()) return;
    if (m_project->text().trimmed().isEmpty() || m_environment->text().trimmed().isEmpty() ||
        m_stateBucket->text().trimmed().isEmpty()) {
        QMessageBox::warning(this, tr("Načtení prostředí"),
                             tr("Vyplňte projekt, prostředí a state bucket; ostatní hodnoty se načtou z GCS state."));
        return;
    }
    const QString script = QDir(m_controller->projectRoot()).filePath("deploy/gcp/load-short-run-config.sh");
    m_configProcessMode = QStringLiteral("load");
    m_configProcess->setWorkingDirectory(m_controller->projectRoot());
    m_configProcess->start(QStringLiteral("bash"), {script,
        "--project=" + m_project->text().trimmed(), "--state-bucket=" + m_stateBucket->text().trimmed(),
        "--workspace=" + m_environment->text().trimmed(), "--terraform-dir=" + m_terraformDir->text().trimmed(),
        "--var-file=" + m_varFile->text().trimmed()});
}

bool CloudOperatorWindow::writeShortRunVarFile()
{
    const QString project = m_project->text().trimmed();
    const QString environment = m_environment->text().trimmed();
    const QString region = m_region->text().trimmed();
    const QString zone = m_zone->text().trimmed();
    const QString domain = m_domain->text().trimmed();
    const QString image = m_image->text().trimmed();
    const bool safe = QRegularExpression("^[a-z][a-z0-9-]{4,28}[a-z0-9]$").match(project).hasMatch()
        && QRegularExpression("^event-[a-z0-9-]{1,12}$").match(environment).hasMatch()
        && QRegularExpression("^[a-z]+-[a-z]+[0-9]+$").match(region).hasMatch()
        && QRegularExpression("^[a-z]+-[a-z]+[0-9]+-[a-z]$").match(zone).hasMatch()
        && QRegularExpression("^[a-z0-9.-]+$").match(domain).hasMatch()
        && QRegularExpression("^[a-z0-9./_:@-]+@sha256:[a-f0-9]{64}$").match(image).hasMatch();
    if (!safe) {
        QMessageBox::warning(this, tr("Neplatná konfigurace"),
                             tr("Projekt, prostředí, region, zóna, doména nebo image obsahují neplatnou hodnotu."));
        return false;
    }
    QSaveFile file(m_varFile->text().trimmed());
    if (!file.open(QIODevice::WriteOnly | QIODevice::Text)) {
        QMessageBox::warning(this, tr("Terraform konfigurace"), tr("Nelze zapsat %1.").arg(file.fileName()));
        return false;
    }
    const QString content = QStringLiteral(
        "# Automaticky vytvořeno Escape Bot Cloud Operatorem; neobsahuje tajemství.\n"
        "project_id = \"%1\"\nregion = \"%2\"\nzone = \"%3\"\n"
        "environment = \"%4\"\ndomain = \"%5\"\n"
        "machine_type = \"e2-medium\"\nboot_disk_size_gb = 20\ndata_disk_size_gb = 10\n"
        "enable_cloud_sql = false\ndata_snapshot_retention_days = 7\n"
        "keep_snapshots_after_disk_delete = false\ninitial_image = \"%6\"\n"
        "labels = { lifecycle = \"short-run\", event = \"%4\" }\n")
        .arg(project, region, zone, environment, domain, image);
    file.write(content.toUtf8());
    if (!file.commit()) {
        QMessageBox::warning(this, tr("Terraform konfigurace"), tr("Zápis konfigurace se nepodařilo dokončit."));
        return false;
    }
    return true;
}

bool CloudOperatorWindow::confirmPhrase(const QString &title, const QString &message, const QString &phrase)
{
    bool ok = false;
    const QString value = QInputDialog::getText(this, title, message + tr("\nPro potvrzení napište %1:").arg(phrase),
                                                QLineEdit::Normal, {}, &ok);
    return ok && value == phrase;
}
