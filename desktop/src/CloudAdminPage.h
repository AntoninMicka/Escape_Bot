#pragma once
#include <QWebEnginePage>

class CloudAdminPage final : public QWebEnginePage
{
    Q_OBJECT
public:
    explicit CloudAdminPage(QObject *parent = nullptr);
};
