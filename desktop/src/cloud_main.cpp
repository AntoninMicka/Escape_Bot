#include "CloudOperatorWindow.h"
#include <QApplication>
#include <QCoreApplication>

int main(int argc, char *argv[])
{
    QApplication app(argc, argv);
    QCoreApplication::setOrganizationName(QStringLiteral("EscapeBot"));
    QCoreApplication::setApplicationName(QStringLiteral("EscapeBotCloudOperator"));
    CloudOperatorWindow window;
    window.show();
    return app.exec();
}
