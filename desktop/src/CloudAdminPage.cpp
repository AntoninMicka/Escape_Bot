#include "CloudAdminPage.h"
#include <QWebEngineCertificateError>

CloudAdminPage::CloudAdminPage(QObject *parent) : QWebEnginePage(parent)
{
    connect(this, &QWebEnginePage::certificateError, this,
            [](QWebEngineCertificateError error) { error.rejectCertificate(); });
}
