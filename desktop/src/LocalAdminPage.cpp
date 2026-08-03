#include "LocalAdminPage.h"

#include <QWebEngineCertificateError>

LocalAdminPage::LocalAdminPage(QObject *parent)
    : QWebEnginePage(parent)
{
    connect(this, &QWebEnginePage::certificateError, this,
            [](QWebEngineCertificateError error) {
        const QString host = error.url().host().toLower();
        const bool localBackend = host == QStringLiteral("localhost")
                                  || host == QStringLiteral("127.0.0.1")
                                  || host == QStringLiteral("::1");
        if (localBackend && error.isOverridable()) {
            error.acceptCertificate();
        } else {
            error.rejectCertificate();
        }
    });
}
