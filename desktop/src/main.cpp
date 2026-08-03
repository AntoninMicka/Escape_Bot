#include "MainWindow.h"

#include <QApplication>
#include <QCoreApplication>

int main(int argc, char *argv[])
{
    QApplication application(argc, argv);
    QCoreApplication::setOrganizationName(QStringLiteral("EscapeBot"));
    QCoreApplication::setApplicationName(QStringLiteral("EscapeBotDesktop"));

    MainWindow window;
    window.show();
    return application.exec();
}

