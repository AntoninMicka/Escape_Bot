#pragma once

#include <QWebEnginePage>

class LocalAdminPage final : public QWebEnginePage
{
    Q_OBJECT

public:
    explicit LocalAdminPage(QObject *parent = nullptr);
};
